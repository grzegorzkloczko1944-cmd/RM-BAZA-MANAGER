import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime


RMPAK_SUPPLIER_NAME = "RMPAK"


def _get_rmpak_supplier_ids(master_con):
    rows = master_con.execute(
        "SELECT supplier_id FROM suppliers WHERE name LIKE ?",
        (f"%{RMPAK_SUPPLIER_NAME}%",)
    ).fetchall()
    return [r[0] for r in rows]


def _get_hourly_rate(master_con):
    row = master_con.execute(
        "SELECT value FROM settings WHERE key = 'rmpak_hourly_rate'"
    ).fetchone()
    if row:
        try:
            return float(row[0])
        except (ValueError, TypeError):
            return 0.0
    return 0.0


def _save_hourly_rate(master_con, rate):
    master_con.execute(
        """INSERT INTO settings (key, value, updated_at) VALUES ('rmpak_hourly_rate', ?, ?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (str(rate), datetime.now().isoformat())
    )
    master_con.commit()


def _ensure_calc_columns(project_con):
    existing = {row[1] for row in project_con.execute("PRAGMA table_info(items)")}
    for col, coltype in [("calc_hours", "REAL"), ("calc_material", "REAL"), ("calc_extra", "REAL")]:
        if col not in existing:
            project_con.execute(f"ALTER TABLE items ADD COLUMN {col} {coltype} DEFAULT 0")
    project_con.commit()


def _load_rmpak_items(project_con, supplier_ids):
    if not supplier_ids:
        return []
    placeholders = ",".join("?" * len(supplier_ids))
    rows = project_con.execute(
        f"""SELECT id, COALESCE(work_name, src_name, ''), src_modul, price_pln,
                   COALESCE(calc_hours, 0), COALESCE(calc_material, 0), COALESCE(calc_extra, 0),
                   COALESCE(work_qty, order_qty, 1),
                   COALESCE(work_drawing_no, src_drawing_no, '')
            FROM items
            WHERE supplier_id IN ({placeholders})
            ORDER BY src_modul, work_name""",
        supplier_ids
    ).fetchall()
    return rows


class RmpakCalculatorDialog:
    def __init__(self, parent, master_con, project_con, project_name="", on_price_saved=None, on_save_item=None):
        self.master_con = master_con
        self.project_con = project_con

        supplier_ids = _get_rmpak_supplier_ids(master_con)
        if not supplier_ids:
            messagebox.showwarning("Brak dostawcy", "Nie znaleziono dostawcy RMPAK w bazie.")
            return

        _ensure_calc_columns(project_con)

        self.supplier_ids = supplier_ids
        self.hourly_rate = _get_hourly_rate(master_con)
        self.selected_item_id = None
        self._updating = False
        self.on_price_saved = on_price_saved
        self.on_save_item = on_save_item  # fn(item_id, price_pln, hours, material, extra)

        self.win = tk.Toplevel(parent)
        self.win.title(f"Kalkulator RMPAK — {project_name}")
        self.win.geometry("1050x620")
        self.win.resizable(True, True)

        self._build_ui()
        self._load_items()

    def _build_ui(self):
        # --- górny pasek: stawka godzinowa ---
        top = tk.Frame(self.win, pady=6, padx=8)
        top.pack(fill="x")

        tk.Label(top, text="Stawka godzinowa (PLN/h):").pack(side="left")
        self.rate_var = tk.StringVar(value=str(self.hourly_rate))
        rate_entry = tk.Entry(top, textvariable=self.rate_var, width=10)
        rate_entry.pack(side="left", padx=4)
        self._bind_select_all(rate_entry)
        tk.Button(top, text="Zapisz stawkę", command=self._save_rate).pack(side="left", padx=4)

        # --- tabela pozycji ---
        frame_table = tk.Frame(self.win)
        frame_table.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        cols = ("ID", "Nr rysunku", "Nazwa", "Szt.", "Godz./partia", "Materiał", "Dodatkowe", "Cena/szt.", "Wartość partii")
        self.tree = ttk.Treeview(frame_table, columns=cols, show="headings", selectmode="browse")
        widths = (40, 110, 280, 45, 90, 90, 90, 90, 110)
        anchors = ("center", "w", "w", "e", "e", "e", "e", "e", "e")
        for col, w, a in zip(cols, widths, anchors):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor=a)

        style = ttk.Style()
        style.configure("RMPAK.Treeview",
                        rowheight=22,
                        borderwidth=1,
                        relief="solid")
        style.configure("RMPAK.Treeview.Heading", font=("", 9, "bold"))
        style.layout("RMPAK.Treeview", [
            ("RMPAK.Treeview.treearea", {"sticky": "nswe"})
        ])
        self.tree.configure(style="RMPAK.Treeview")
        self.tree.tag_configure("odd",  background="#ffffff")
        self.tree.tag_configure("even", background="#dce9f5")

        vsb = ttk.Scrollbar(frame_table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # --- dolny obszar: kalkulator + suma ---
        bottom_area = tk.Frame(self.win)
        bottom_area.pack(fill="x", padx=8, pady=(0, 8))

        bottom = tk.LabelFrame(bottom_area, text="Kalkulator dla wybranej pozycji", padx=8, pady=6)
        bottom.pack(side="left", fill="both", expand=True)

        self._loaded_vals = None  # wartości załadowane z tabeli dla bieżącej pozycji
        self._prev_iid = None

        self.selected_label = tk.Label(bottom, text="(wybierz pozycję z listy)", anchor="w", fg="gray")
        self.selected_label.grid(row=0, column=0, columnspan=10, sticky="w", pady=(0, 6))

        fields = [
            ("Czas partii (h lub h:mm):", 0),
            ("Materiał (PLN):", 2),
            ("Dodatkowe (PLN):", 4),
        ]
        self.calc_vars = [tk.StringVar(value="0"), tk.StringVar(value="0"), tk.StringVar(value="0")]

        for (lbl, col), var in zip(fields, self.calc_vars):
            tk.Label(bottom, text=lbl).grid(row=1, column=col, sticky="e", padx=(4, 2))
            e = tk.Entry(bottom, textvariable=var, width=10)
            e.grid(row=1, column=col + 1, padx=(0, 8))
            self._bind_select_all(e)
            var.trace_add("write", self._recalc)

        tk.Label(bottom, text="Ilość szt.:").grid(row=1, column=6, sticky="e", padx=(16, 2))
        self.qty_label = tk.Label(bottom, text="—", width=6, anchor="w", font=("", 10))
        self.qty_label.grid(row=1, column=7, sticky="w")

        tk.Label(bottom, text="Cena/szt.:").grid(row=2, column=0, sticky="e", padx=(4, 2), pady=(6, 0))
        self.price_per_unit_var = tk.StringVar(value="—")
        tk.Label(bottom, textvariable=self.price_per_unit_var, font=("", 11, "bold"), fg="darkgreen", width=10, anchor="w").grid(row=2, column=1, sticky="w", pady=(6, 0))

        tk.Label(bottom, text="Wartość partii:").grid(row=2, column=2, sticky="e", padx=(4, 2), pady=(6, 0))
        self.price_total_var = tk.StringVar(value="—")
        tk.Label(bottom, textvariable=self.price_total_var, font=("", 11, "bold"), fg="navy", width=12, anchor="w").grid(row=2, column=3, sticky="w", pady=(6, 0))

        tk.Button(bottom, text="💾 Zapisz cenę/szt.", command=self._save_price,
                  bg="#4CAF50", fg="white", font=("", 10, "bold")).grid(row=2, column=6, columnspan=2, padx=(16, 0), pady=(6, 0))

        # --- suma całkowita (prawy dolny róg) ---
        sum_frame = tk.LabelFrame(bottom_area, text="Suma całkowita", padx=10, pady=8)
        sum_frame.pack(side="right", fill="y", padx=(8, 0))

        tk.Label(sum_frame, text="Wszystkie pozycje RMPAK:", anchor="w").pack(anchor="w")
        self.grand_total_var = tk.StringVar(value="— PLN")
        tk.Label(sum_frame, textvariable=self.grand_total_var,
                 font=("", 14, "bold"), fg="darkred", anchor="e").pack(anchor="e", pady=(4, 0))

    def _load_items(self):
        self.tree.delete(*self.tree.get_children())
        self._items = {}
        self._qtys = {}
        rows = _load_rmpak_items(self.project_con, self.supplier_ids)
        grand_total = 0.0
        for lp, row in enumerate(rows, start=1):
            item_id, name, modul, price, hours, material, extra, qty, drawing_no = row
            qty = qty or 1
            price_str = f"{price:.2f}" if price is not None else "—"
            total = price * qty if price is not None else None
            total_str = f"{total:.2f}" if total is not None else "—"
            if total is not None:
                grand_total += total
            tag = "odd" if lp % 2 else "even"
            iid = self.tree.insert("", "end", tags=(tag,), values=(
                lp, drawing_no or "", name or "", int(qty),
                hours or 0, f"{material:.2f}", f"{extra:.2f}", price_str, total_str
            ))
            self._items[iid] = item_id
            self._qtys[iid] = qty
        self.grand_total_var.set(f"{grand_total:,.2f} PLN")

    @staticmethod
    def _bind_select_all(entry):
        def _select(e):
            e.widget.select_range(0, "end")
            e.widget.icursor("end")
        entry.bind("<FocusIn>", _select)

    def _has_unsaved_changes(self):
        if self._loaded_vals is None or self.selected_item_id is None:
            return False
        current = [self.calc_vars[0].get().strip(),
                   self.calc_vars[1].get().strip(),
                   self.calc_vars[2].get().strip()]
        return current != list(self._loaded_vals)

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        # sprawdź czy są niezapisane zmiany w poprzedniej pozycji
        if self._has_unsaved_changes() and iid != self._prev_iid:
            answer = messagebox.askyesnocancel(
                "Niezapisane zmiany",
                "Masz niezapisane zmiany dla tej pozycji.\nCzy zapisać przed przejściem dalej?",
                parent=self.win
            )
            if answer is None:  # Anuluj — przywróć pola poprzedniej pozycji bez zmiany selekcji
                self._updating = True
                self.calc_vars[0].set(self._loaded_vals[0])
                self.calc_vars[1].set(self._loaded_vals[1])
                self.calc_vars[2].set(self._loaded_vals[2])
                self._updating = False
                self._recalc()
                return
            if answer:  # Tak — zapisz
                self._save_price()

        self._prev_iid = iid
        self.selected_item_id = self._items.get(iid)
        vals = self.tree.item(iid, "values")
        self.selected_label.config(text=f"Pozycja: {vals[2]}", fg="black")
        qty = self._qtys.get(iid, 1)
        self.qty_label.config(text=str(qty))
        self._updating = True
        self.calc_vars[0].set(str(vals[4]))   # godz./partia
        self.calc_vars[1].set(str(vals[5]))   # materiał
        self.calc_vars[2].set(str(vals[6]))   # dodatkowe
        self._updating = False
        self._loaded_vals = (self.calc_vars[0].get().strip(),
                             self.calc_vars[1].get().strip(),
                             self.calc_vars[2].get().strip())
        self._recalc()

    @staticmethod
    def _parse(val):
        s = (val or "0").strip()
        if ":" in s:
            parts = s.split(":", 1)
            h = float(parts[0] or "0")
            m = float(parts[1] or "0")
            return h + m / 60.0
        return float(s.replace(",", "."))

    def _recalc(self, *_):
        if self._updating:
            return
        try:
            rate = self._parse(self.rate_var.get())
            hours = self._parse(self.calc_vars[0].get())
            material = self._parse(self.calc_vars[1].get())
            extra = self._parse(self.calc_vars[2].get())
            qty_text = self.qty_label.cget("text")
            qty = float(qty_text) if qty_text not in ("—", "") else 1.0
            total = rate * hours + material + extra
            per_unit = total / qty if qty else 0.0
            self.price_per_unit_var.set(f"{per_unit:.2f} PLN")
            self.price_total_var.set(f"{total:.2f} PLN")
        except ValueError:
            self.price_per_unit_var.set("—")
            self.price_total_var.set("—")

    def _save_rate(self):
        try:
            rate = self._parse(self.rate_var.get())
        except ValueError:
            messagebox.showerror("Błąd", "Nieprawidłowa stawka godzinowa.", parent=self.win)
            return
        _save_hourly_rate(self.master_con, rate)
        self.hourly_rate = rate
        messagebox.showinfo("OK", f"Stawka {rate:.2f} PLN/h zapisana.", parent=self.win)

    def _save_price(self):
        if not self.selected_item_id:
            messagebox.showwarning("Brak wyboru", "Wybierz pozycję z listy.", parent=self.win)
            return
        try:
            rate = self._parse(self.rate_var.get())
            hours = self._parse(self.calc_vars[0].get())
            material = self._parse(self.calc_vars[1].get())
            extra = self._parse(self.calc_vars[2].get())
            qty_text = self.qty_label.cget("text")
            qty = float(qty_text) if qty_text not in ("—", "") else 1.0
            total = rate * hours + material + extra
            price_per_unit = total / qty if qty else 0.0
        except ValueError:
            messagebox.showerror("Błąd", "Nieprawidłowe wartości.", parent=self.win)
            return

        if self.on_save_item:
            self.on_save_item(self.selected_item_id, price_per_unit, hours, material, extra)
        else:
            self.project_con.execute(
                """UPDATE items SET price_pln=?, calc_hours=?, calc_material=?, calc_extra=?
                   WHERE id=?""",
                (price_per_unit, hours, material, extra, self.selected_item_id)
            )
            self.project_con.commit()
        self._loaded_vals = (self.calc_vars[0].get().strip(),
                             self.calc_vars[1].get().strip(),
                             self.calc_vars[2].get().strip())

        # odśwież wiersz w tabeli
        sel = self.tree.selection()
        if sel:
            iid = sel[0]
            qty = self._qtys.get(iid, 1)
            vals = list(self.tree.item(iid, "values"))
            vals[4] = hours
            vals[5] = material
            vals[6] = extra
            vals[7] = f"{price_per_unit:.2f}"
            vals[8] = f"{price_per_unit * qty:.2f}"
            self.tree.item(iid, values=vals)
        # przelicz sumę całkowitą
        grand = 0.0
        for child in self.tree.get_children():
            v = self.tree.item(child, "values")[8]
            try:
                grand += float(v)
            except (ValueError, TypeError):
                pass
        self.grand_total_var.set(f"{grand:,.2f} PLN")

        if self.on_price_saved:
            self.on_price_saved()
