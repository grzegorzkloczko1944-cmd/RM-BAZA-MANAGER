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
    for col, coltype in [
        ("calc_hours", "REAL"), ("calc_material", "REAL"), ("calc_extra", "REAL"), ("calc_rate", "REAL"),
        ("calc_mode", "TEXT"), ("calc_semi_price", "REAL"), ("calc_semi_name", "TEXT"), ("calc_semi_supplier_id", "INTEGER"),
    ]:
        if col not in existing:
            default = " DEFAULT 0" if coltype == "REAL" else ""
            project_con.execute(f"ALTER TABLE items ADD COLUMN {col} {coltype}{default}")
    project_con.commit()


def _get_supplier_id_by_exact_name(master_con, name):
    row = master_con.execute(
        "SELECT supplier_id FROM suppliers WHERE name = ?", (name,)
    ).fetchone()
    return row[0] if row else None


def _load_rmpak_items(project_con, supplier_ids):
    if not supplier_ids:
        return []
    placeholders = ",".join("?" * len(supplier_ids))
    rows = project_con.execute(
        f"""SELECT id, COALESCE(work_name, src_name, ''), src_modul, price_pln,
                   COALESCE(calc_hours, 0), COALESCE(calc_material, 0), COALESCE(calc_extra, 0),
                   COALESCE(work_qty, order_qty, src_qty, 1),
                   COALESCE(work_drawing_no, src_drawing_no, ''),
                   COALESCE(calc_rate, 0),
                   COALESCE(ordered_flag, 0),
                   COALESCE(delivered_qty, 0),
                   COALESCE(order_qty, work_qty, src_qty, 1),
                   COALESCE(calc_mode, 'cut'),
                   COALESCE(calc_semi_price, 0),
                   COALESCE(calc_semi_name, ''),
                   calc_semi_supplier_id,
                   supplier_id
            FROM items
            WHERE supplier_id IN ({placeholders})
            ORDER BY src_modul, work_name""",
        supplier_ids
    ).fetchall()
    return rows


class RmpakCalculatorDialog:
    def __init__(self, parent, master_con, project_con, project_name="", on_price_saved=None, on_save_item=None, on_jump_to_item=None):
        self.master_con = master_con
        self.project_con = project_con

        supplier_ids = _get_rmpak_supplier_ids(master_con)
        if not supplier_ids:
            messagebox.showwarning("Brak dostawcy", "Nie znaleziono dostawcy RMPAK w bazie.")
            return

        _ensure_calc_columns(project_con)

        self.supplier_ids = supplier_ids
        self.project_name = project_name    # do Uwag na PW/RW
        self.hourly_rate = _get_hourly_rate(master_con)
        self.selected_item_id = None
        self._updating = False
        self.rmpak_cut_id = _get_supplier_id_by_exact_name(master_con, "RMPAK")
        self.rmpak_semi_id = _get_supplier_id_by_exact_name(master_con, "RMPAK+")
        self.suppliers_map = {
            row[0]: row[1] for row in master_con.execute("SELECT supplier_id, name FROM suppliers")
        }
        self.on_price_saved = on_price_saved
        self.on_save_item = on_save_item  # fn(item_id, price_pln, hours, material, extra, rate)
        self.on_jump_to_item = on_jump_to_item  # fn(item_id)

        self.win = tk.Toplevel(parent)
        self.win.title(f"Kalkulator RMPAK — {project_name}")
        self.win.resizable(True, True)
        w, h = 1400, 700
        self.win.update_idletasks()
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.win.minsize(1400, 600)

        self._build_ui()
        self._load_items()
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

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

        # --- legenda kolorów + odśwież ---
        legend_frame = tk.Frame(top)
        legend_frame.pack(side="right", padx=(0, 4))
        tk.Button(legend_frame, text="Odśwież", command=self._load_items,
                  bg="#2980b9", fg="white", font=("", 9, "bold")).pack(side="left", padx=(0, 12))
        for color, label in (("#90EE90", "Zrealizowano"), ("#FFFACD", "Zamówiono")):
            tk.Label(legend_frame, text="  ", bg=color, relief="solid", bd=1).pack(side="left", padx=(8, 2))
            tk.Label(legend_frame, text=label).pack(side="left", padx=(0, 4))

        # --- pasek filtrów: RMPAK/RMPAK+ + szukaj ---
        filter_bar = tk.Frame(self.win, padx=8)
        filter_bar.pack(fill="x", pady=(0, 4))

        self.filter_rmpak_var = tk.BooleanVar(value=True)
        self.filter_rmpak_plus_var = tk.BooleanVar(value=True)
        tk.Checkbutton(filter_bar, text="RMPAK", variable=self.filter_rmpak_var,
                       command=self._load_items).pack(side="left", padx=(0, 8))
        tk.Checkbutton(filter_bar, text="RMPAK+", variable=self.filter_rmpak_plus_var,
                       command=self._load_items).pack(side="left", padx=(0, 16))

        tk.Label(filter_bar, text="Szukaj:").pack(side="left", padx=(0, 3))
        self.search_var = tk.StringVar(value="")
        search_entry = tk.Entry(filter_bar, textvariable=self.search_var, width=24)
        search_entry.pack(side="left", padx=(0, 16))
        search_entry.bind("<KeyRelease>", lambda _e: self._load_items())

        tk.Label(filter_bar, text="Dostawca:").pack(side="left", padx=(0, 3))
        self.filter_supplier_var = tk.StringVar(value="(wszyscy)")
        self.filter_supplier_id = None
        self.filter_supplier_btn = tk.Button(filter_bar, textvariable=self.filter_supplier_var,
                                              relief="groove", width=18, anchor="w",
                                              bg="white", fg="black",
                                              command=lambda: self._show_supplier_picker(
                                                  self.filter_supplier_id, self._on_filter_supplier_chosen))
        self.filter_supplier_btn.pack(side="left", padx=(0, 16))

        tk.Label(filter_bar, text="Cena od:").pack(side="left", padx=(0, 3))
        self.filter_price_min_var = tk.StringVar(value="")
        price_min_entry = tk.Entry(filter_bar, textvariable=self.filter_price_min_var, width=8)
        price_min_entry.pack(side="left", padx=(0, 8))
        price_min_entry.bind("<KeyRelease>", lambda _e: self._load_items())

        tk.Label(filter_bar, text="do:").pack(side="left", padx=(0, 3))
        self.filter_price_max_var = tk.StringVar(value="")
        price_max_entry = tk.Entry(filter_bar, textvariable=self.filter_price_max_var, width=8)
        price_max_entry.pack(side="left", padx=(0, 16))
        price_max_entry.bind("<KeyRelease>", lambda _e: self._load_items())

        tk.Button(filter_bar, text="🗑️", command=self._clear_filters,
                  bg="#95a5a6", fg="white", font=("Arial", 10, "bold"),
                  width=3, relief="raised", bd=2).pack(side="left")

        # --- pasek filtrów: status realizacji ---
        status_bar = tk.Frame(self.win, padx=8)
        status_bar.pack(fill="x", pady=(0, 4))

        self.filter_delivered_var = tk.BooleanVar(value=True)
        self.filter_not_delivered_var = tk.BooleanVar(value=True)
        self.filter_ordered_var = tk.BooleanVar(value=True)
        self.filter_to_order_var = tk.BooleanVar(value=True)
        for text, var in (
            ("Dostarczone", self.filter_delivered_var),
            ("Nie dostarczone", self.filter_not_delivered_var),
            ("Zamówione", self.filter_ordered_var),
            ("Do zamówienia", self.filter_to_order_var),
        ):
            tk.Checkbutton(status_bar, text=text, variable=var,
                           command=self._load_items).pack(side="left", padx=(0, 12))

        # --- tabela pozycji ---
        frame_table = tk.Frame(self.win)
        frame_table.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        cols = ("ID", "Nr rysunku", "Nazwa", "Szt.", "Godz./partia", "Materiał cięty", "Dodatkowe", "Stawka", "Cena/szt.", "Wartość partii", "Półprodukt", "Dostawca", "RMPAK")
        self.tree = ttk.Treeview(frame_table, columns=cols, show="headings", selectmode="browse")
        widths = (40, 110, 220, 45, 90, 90, 90, 70, 90, 110, 140, 140, 90)
        anchors = ("center", "w", "w", "e", "e", "e", "e", "e", "e", "e", "w", "w", "center")
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
        self.tree.tag_configure("odd",       background="#eef4fb")
        self.tree.tag_configure("even",      background="#ddeaf6")
        self.tree.tag_configure("delivered", background="#90EE90")
        self.tree.tag_configure("ordered",   background="#FFFACD")

        vsb = ttk.Scrollbar(frame_table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-Button-1>", self._on_double_click)

        # --- dolny obszar: kalkulator + suma ---
        bottom_area = tk.Frame(self.win)
        bottom_area.pack(fill="x", padx=8, pady=(0, 8))

        self.bottom = tk.LabelFrame(bottom_area, text="Kalkulator dla wybranej pozycji", padx=8, pady=6)
        self.bottom.pack(side="left", fill="both", expand=True)
        bottom = self.bottom

        self._loaded_vals = None  # wartości załadowane z tabeli dla bieżącej pozycji
        self._prev_iid = None

        self.lbl_prefix = tk.Label(bottom, text="Pozycja:", anchor="w")
        self.lbl_prefix.grid(row=0, column=0, sticky="w", padx=(0, 4), pady=(0, 6))
        self.selected_label = tk.Label(bottom, text="(wybierz pozycję z listy)", anchor="w", fg="gray", font=("", 9, "bold"))
        self.selected_label.grid(row=0, column=1, columnspan=9, sticky="w", pady=(0, 6))

        # --- przełącznik trybu: Materiał cięty (RMPAK) / Półprodukt (RMPAK+) ---
        self.calc_mode_var = tk.StringVar(value="cut")
        mode_frame = tk.Frame(bottom)
        mode_frame.grid(row=1, column=0, columnspan=8, sticky="w", pady=(0, 4))
        tk.Radiobutton(mode_frame, text="Materiał cięty z metra (RMPAK)", variable=self.calc_mode_var,
                       value="cut", command=self._on_mode_change).pack(side="left", padx=(0, 12))
        tk.Radiobutton(mode_frame, text="Półprodukt od Dostawcy (RMPAK+)", variable=self.calc_mode_var,
                       value="semi", command=self._on_mode_change).pack(side="left")

        tk.Label(bottom, text="Czas partii (h lub h:mm):").grid(row=2, column=0, sticky="e", padx=(4, 2))
        self.calc_vars = [tk.StringVar(value="0"), tk.StringVar(value="0"), tk.StringVar(value="0")]
        hours_entry = tk.Entry(bottom, textvariable=self.calc_vars[0], width=10)
        hours_entry.grid(row=2, column=1, padx=(0, 8))
        self._bind_select_all(hours_entry)
        self.calc_vars[0].trace_add("write", self._recalc)

        self.lbl_material = tk.Label(bottom, text="Materiał cięty (PLN):")
        self.lbl_material.grid(row=2, column=2, sticky="e", padx=(4, 2))
        material_frame = tk.Frame(bottom)
        material_frame.grid(row=2, column=3, padx=(0, 8), sticky="w")
        self.material_entry = tk.Entry(material_frame, textvariable=self.calc_vars[1], width=10)
        self.material_entry.pack(side="left")
        self._bind_select_all(self.material_entry)
        self.calc_vars[1].trace_add("write", self._recalc)
        self.material_calc_btn = tk.Button(material_frame, text="🧮", width=2, command=self._open_material_calculator)
        self.material_calc_btn.pack(side="left", padx=(2, 0))

        tk.Label(bottom, text="Dodatkowe (PLN):").grid(row=2, column=4, sticky="e", padx=(4, 2))
        extra_entry = tk.Entry(bottom, textvariable=self.calc_vars[2], width=10)
        extra_entry.grid(row=2, column=5, padx=(0, 8))
        self._bind_select_all(extra_entry)
        self.calc_vars[2].trace_add("write", self._recalc)

        tk.Label(bottom, text="Ilość szt.:").grid(row=2, column=6, sticky="e", padx=(16, 2))
        self.qty_label = tk.Label(bottom, text="—", width=6, anchor="w", font=("", 10))
        self.qty_label.grid(row=2, column=7, sticky="w")

        # --- pola półproduktu (aktywne tylko w trybie 'semi') ---
        self.lbl_semi_price = tk.Label(bottom, text="Cena półproduktu (PLN)/szt.:")
        self.lbl_semi_price.grid(row=3, column=0, sticky="e", padx=(4, 2), pady=(4, 0))
        self.semi_price_var = tk.StringVar(value="0")
        self.semi_price_entry = tk.Entry(bottom, textvariable=self.semi_price_var, width=10)
        self.semi_price_entry.grid(row=3, column=1, padx=(0, 8), pady=(4, 0))
        self._bind_select_all(self.semi_price_entry)
        self.semi_price_var.trace_add("write", self._recalc)

        tk.Label(bottom, text="Nazwa półproduktu:").grid(row=3, column=2, sticky="e", padx=(4, 2), pady=(4, 0))
        self.semi_name_var = tk.StringVar(value="")
        self.semi_name_entry = tk.Entry(bottom, textvariable=self.semi_name_var, width=20)
        self.semi_name_entry.grid(row=3, column=3, columnspan=2, sticky="w", padx=(0, 8), pady=(4, 0))
        self._bind_select_all(self.semi_name_entry)

        tk.Label(bottom, text="Dostawca:").grid(row=3, column=5, sticky="e", padx=(4, 2), pady=(4, 0))
        self.semi_supplier_var = tk.StringVar(value="(brak)")
        self.semi_supplier_label = tk.Label(bottom, textvariable=self.semi_supplier_var, anchor="w",
                                             relief="groove", width=16, bg="white")
        self.semi_supplier_label.grid(row=3, column=6, sticky="w", pady=(4, 0))
        self.semi_supplier_btn = tk.Button(bottom, text="Wybierz…", command=self._pick_semi_supplier)
        self.semi_supplier_btn.grid(row=3, column=7, sticky="w", padx=(4, 0), pady=(4, 0))
        self.semi_supplier_id = None

        tk.Label(bottom, text="Stawka (PLN/h):").grid(row=4, column=0, sticky="e", padx=(4, 2), pady=(6, 0))
        self.item_rate_var = tk.StringVar(value=str(self.hourly_rate))
        item_rate_entry = tk.Entry(bottom, textvariable=self.item_rate_var, width=10)
        item_rate_entry.grid(row=4, column=1, padx=(0, 8), pady=(6, 0))
        self._bind_select_all(item_rate_entry)
        self.item_rate_var.trace_add("write", self._recalc)

        tk.Label(bottom, text="Cena/szt.:").grid(row=4, column=2, sticky="e", padx=(4, 2), pady=(6, 0))
        self.price_per_unit_var = tk.StringVar(value="—")
        tk.Label(bottom, textvariable=self.price_per_unit_var, font=("", 11, "bold"), fg="darkgreen", width=10, anchor="w").grid(row=4, column=3, sticky="w", pady=(6, 0))

        tk.Label(bottom, text="Wartość partii:").grid(row=4, column=4, sticky="e", padx=(4, 2), pady=(6, 0))
        self.price_total_var = tk.StringVar(value="—")
        tk.Label(bottom, textvariable=self.price_total_var, font=("", 11, "bold"), fg="navy", width=12, anchor="w").grid(row=4, column=5, sticky="w", pady=(6, 0))

        tk.Button(bottom, text="💾 Zapisz cenę/szt.", command=self._save_price,
                  bg="#4CAF50", fg="white", font=("", 10, "bold")).grid(row=4, column=6, columnspan=2, padx=(16, 0), pady=(6, 0))

        self._update_mode_widgets()

        # --- suma całkowita (prawy dolny róg) ---
        sum_frame = tk.LabelFrame(bottom_area, text="Suma całkowita", padx=10, pady=8, width=220)
        sum_frame.pack(side="right", fill="y", padx=(8, 0))
        sum_frame.pack_propagate(False)

        tk.Label(sum_frame, text="Wszystkie pozycje RMPAK:", anchor="w").pack(anchor="w", fill="x")
        self.grand_total_var = tk.StringVar(value="— PLN")
        tk.Label(sum_frame, textvariable=self.grand_total_var,
                 font=("", 14, "bold"), fg="darkred", anchor="e").pack(anchor="e", fill="x", pady=(4, 0))

        # --- dokumenty produkcji: PW / RW ---
        # Sekcja DOKŁADANA do istniejącego okna, nie nowa aplikacja: lista
        # kalkulatora JEST listą produkcyjną projektu (ustalenia §7).
        doc_frame = tk.LabelFrame(bottom_area, text="Dokumenty produkcji — Subiekt",
                                  padx=10, pady=8, width=250)
        doc_frame.pack(side="right", fill="y", padx=(8, 0))
        doc_frame.pack_propagate(False)

        self.pw_status_var = tk.StringVar(value="PW: —")
        tk.Label(doc_frame, textvariable=self.pw_status_var, anchor="w",
                 font=("", 9)).pack(anchor="w", fill="x")
        self.rw_status_var = tk.StringVar(value="RW: —")
        tk.Label(doc_frame, textvariable=self.rw_status_var, anchor="w",
                 font=("", 9)).pack(anchor="w", fill="x")

        # Ile pozycji faktycznie pójdzie na dokument — liczone z BAZY, nie
        # z widocznych wierszy. User musi to widzieć ZANIM kliknie (§8).
        self.pw_info_var = tk.StringVar(value="")
        tk.Label(doc_frame, textvariable=self.pw_info_var, anchor="w",
                 font=("", 8), fg="gray30", wraplength=225,
                 justify="left").pack(anchor="w", fill="x", pady=(6, 0))

        self.btn_pw = tk.Button(doc_frame, text="📥 Wystaw PW", command=self._podglad_pw,
                                bg="#337ab7", fg="white", font=("", 9, "bold"))
        self.btn_pw.pack(anchor="e", fill="x", pady=(8, 0))
        self.btn_rw = tk.Button(doc_frame, text="📤 Wystaw RW", state="disabled",
                                font=("", 9, "bold"))
        self.btn_rw.pack(anchor="e", fill="x", pady=(4, 0))

        tk.Button(sum_frame, text="Zamknij", command=self._on_close,
                  width=12, bg="#d9534f", fg="white", font=("", 9, "bold")).pack(anchor="e", pady=(10, 0))

        self._odswiez_status_pw()

    # ── Dokumenty produkcji (PW / RW) ────────────────────────────────────
    def _pozycje_pw(self):
        """(pozycje, pominiete_komplety) z BAZY. (None, None) gdy się nie da."""
        try:
            import subiekt_produkcja
            pid = subiekt_produkcja.project_id_z_polaczenia(self.project_con)
            if pid is None:
                return None, None
            return subiekt_produkcja.lista_do_pw(pid)
        except Exception:
            return None, None

    def _odswiez_numery_dokumentow(self):
        """PW/RW z Subiekta — W TLE, bo odczyt idzie przez most (~1 s).

        Numerów nie trzymamy w bazie projektu: bez locka jest READ-ONLY, więc
        zapis się nie udawał i dokument istniał w Subiekcie, o którym RM_BAZA
        nie wiedziała. Ten sam wzorzec co „Ilość (zam.)": Subiekt jest
        właścicielem, my odświeżamy.
        """
        import threading

        def worker():
            try:
                import subiekt_produkcja
                dok = subiekt_produkcja.dokumenty_produkcji(self.project_name)
            except Exception:
                dok = None
            try:
                self.win.after(0, lambda: self._pokaz_numery(dok))
            except Exception:
                pass                      # okno zamknięte w trakcie odczytu

        threading.Thread(target=worker, daemon=True).start()

    def _pokaz_numery(self, dok):
        """Wynik odczytu na etykiety. None = nie udało się połączyć."""
        if dok is None:
            self.pw_status_var.set("PW: (brak połączenia)")
            self.rw_status_var.set("RW: (brak połączenia)")
            return
        self._dok_produkcji = dok
        pw, rw = dok.get("PW") or [], dok.get("RW") or []
        self.pw_status_var.set("PW: " + (", ".join(d["numer"] for d in pw) if pw else "—"))
        self.rw_status_var.set("RW: " + (", ".join(d["numer"] for d in rw) if rw else "—"))
        # RW dopiero po PW — i tylko raz (§6: 1 projekt = 1 PW = 1 RW).
        try:
            self.btn_rw.config(state="normal" if (pw and not rw) else "disabled",
                               bg="#337ab7" if (pw and not rw) else "SystemButtonFace",
                               fg="white" if (pw and not rw) else "gray40",
                               command=self._podglad_rw)
        except Exception:
            pass

    def _odswiez_status_pw(self):
        """Podpis pod przyciskiem: ile pozycji i czego brakuje.

        Liczone z bazy przy każdym odświeżeniu listy, żeby po zapisaniu ceny
        licznik braków od razu malał — inaczej user poprawia i nie widzi
        efektu, dopóki nie kliknie „Wystaw PW".
        """
        poz, pom = self._pozycje_pw()
        if poz is None:
            self.pw_info_var.set("Nie udało się odczytać listy do PW.")
            self.btn_pw.config(state="disabled")
            return
        try:
            import subiekt_produkcja
            braki = subiekt_produkcja.braki_przed_pw(poz)
            # Numery PW/RW czytane z SUBIEKTA, nie trzymane lokalnie — ten sam
            # wzorzec co „Ilość (zam.)" i termin dostawy: Subiekt jest
            # właścicielem wystawionego dokumentu, RM_BAZA go tylko odświeża.
            self._odswiez_numery_dokumentow()
        except Exception:
            braki = []
        opis = f"{len(poz)} poz. na PW"
        if pom:
            opis += f", {len(pom)} kompletów pominiętych (powstają ze składników)"
        if braki:
            ile = len({s for s, _ in braki})
            opis += f"\n⚠ {ile} poz. bez ceny/ilości — uzupełnij przed PW"
        self.pw_info_var.set(opis)
        self.btn_pw.config(state="normal" if poz else "disabled")

    def _podglad_pw(self):
        """Okno „co pójdzie do Subiekta". NIC nie zapisuje.

        Zgodnie z zasadą „nic po cichu": user widzi pełną listę z cenami
        i wartościami, zanim powstanie jakikolwiek dokument.
        """
        poz, pom = self._pozycje_pw()
        if poz is None:
            messagebox.showerror("PW", "Nie udało się odczytać listy pozycji z bazy projektu.",
                                 parent=self.win)
            return
        import subiekt_produkcja
        braki = subiekt_produkcja.braki_przed_pw(poz)

        dlg = tk.Toplevel(self.win)
        dlg.title("Podgląd PW — przyjęcie produkcji własnej")
        dlg.transient(self.win)
        dlg.geometry("820x560")

        tk.Label(dlg, text=f"ZOSTANIE UTWORZONY DOKUMENT PW — {self.project_name}",
                 bg="#337ab7", fg="white", font=("", 10, "bold"),
                 anchor="w", padx=12, pady=8).pack(fill="x")

        # Braki NA GÓRZE, nie w stopce — to one decydują, czy PW w ogóle
        # powstanie, więc nie mogą wymagać przewijania.
        if braki:
            ramka = tk.Frame(dlg, bg="#f2dede", padx=12, pady=8)
            ramka.pack(fill="x")
            symbole = sorted({s for s, _ in braki})
            tk.Label(ramka, bg="#f2dede", fg="#a94442", anchor="w", justify="left",
                     font=("", 9, "bold"),
                     text=f"⛔ NIE MOŻNA WYSTAWIĆ PW — {len(symbole)} poz. bez ceny lub ilości"
                     ).pack(anchor="w")
            tk.Label(ramka, bg="#f2dede", fg="#a94442", anchor="w", justify="left",
                     wraplength=780, font=("", 8),
                     text=", ".join(symbole[:20]) + (" …" if len(symbole) > 20 else "")
                     ).pack(anchor="w")
            # Najczęstsza przyczyna „BRAK" mimo policzonej ceny: kalkulacja
            # siedzi w polach, ale nie kliknięto „Zapisz cenę/szt.". Podgląd
            # czyta bazę OSOBNYM połączeniem read-only, więc niezapisanej
            # transakcji nie widzi (zgłoszone 09.09.2026).
            if self._has_unsaved_changes():
                tk.Label(ramka, bg="#f2dede", fg="#a94442", anchor="w", justify="left",
                         wraplength=780, font=("", 9, "bold"),
                         text="⚠ Masz NIEZAPISANĄ kalkulację w oknie kalkulatora — "
                              "kliknij „💾 Zapisz cenę/szt.”, potem otwórz podgląd ponownie."
                         ).pack(anchor="w", pady=(6, 0))

        cols = ("Symbol", "Nazwa", "Ilość", "Cena/szt.", "Wartość")
        tree = ttk.Treeview(dlg, columns=cols, show="headings", height=14)
        for c, w in zip(cols, (150, 300, 70, 90, 100)):
            tree.heading(c, text=c)
            tree.column(c, width=w, anchor="e" if c in ("Ilość", "Cena/szt.", "Wartość") else "w")
        tree.pack(fill="both", expand=True, padx=10, pady=(8, 0))

        razem = 0.0
        for p in poz:
            cena = p["cena"]
            wart = (cena or 0) * p["ilosc"]
            razem += wart
            tree.insert("", "end", values=(
                p["symbol"], p["nazwa"], f"{p['ilosc']:g}",
                f"{cena:.2f}" if cena else "— BRAK —",
                f"{wart:.2f}" if cena else "—"),
                tags=() if cena else ("brak",))
        tree.tag_configure("brak", background="#f2dede")

        stopka = tk.Frame(dlg, padx=12, pady=10)
        stopka.pack(fill="x")
        tk.Label(stopka, text=f"RAZEM: {razem:,.2f} PLN".replace(",", " "),
                 font=("", 12, "bold"), fg="darkred").pack(side="left")
        tk.Label(stopka, text=f"Uwagi: RM_BAZA — PROJEKT {self.project_name}",
                 font=("", 8), fg="gray30").pack(side="left", padx=(16, 0))

        tk.Button(stopka, text="Zamknij", command=dlg.destroy, width=12).pack(side="right")
        btn = tk.Button(stopka, text="Wystaw PW", width=14, font=("", 9, "bold"),
                        bg="#337ab7", fg="white")
        btn.config(command=lambda: self._wystaw_pw(poz, dlg, btn))
        if braki:
            btn.config(state="disabled", bg="#cccccc", fg="gray40")
        btn.pack(side="right", padx=(0, 8))

        if pom:
            tk.Label(dlg, anchor="w", justify="left", fg="gray30", font=("", 8),
                     wraplength=790, padx=12,
                     text=f"Pominięte złożenia ({len(pom)}): powstają w Subiekcie ze swoich "
                          f"składników, więc nie przyjmujemy ich osobno — "
                          + ", ".join(p["symbol"] for p in pom[:12])
                          + (" …" if len(pom) > 12 else "")).pack(fill="x", pady=(0, 8))

    def _podglad_rw(self):
        """Okno „co pójdzie na RW". Źródłem jest POTWIERDZONE PW, nie BOM.

        Ilości nie są tu edytowane (§16 v2): RW wydaje dokładnie to, co
        przyjęło PW, żeby oba dokumenty nie rozjechały się po późniejszej
        zmianie w projekcie.
        """
        import subiekt_produkcja
        poz, numer_pw, blad = subiekt_produkcja.pw_do_rw(self.project_name)
        if blad:
            messagebox.showwarning("RW", blad, parent=self.win)
            return

        dlg = tk.Toplevel(self.win)
        dlg.title("Podgląd RW — wydanie produkcji na projekt")
        dlg.transient(self.win)
        dlg.geometry("820x520")

        tk.Label(dlg, text=f"ZOSTANIE UTWORZONY DOKUMENT RW — {self.project_name}",
                 bg="#e67e22", fg="white", font=("", 10, "bold"),
                 anchor="w", padx=12, pady=8).pack(fill="x")
        tk.Label(dlg, text=f"Źródło: {numer_pw}   ·   ilości i pozycje prosto z PW, bez przeliczania",
                 bg="#fdebd0", fg="#7d4b12", font=("", 9), anchor="w",
                 padx=12, pady=6).pack(fill="x")

        # Ceny NIE IDĄ na dokument — kolumny mówią to wprost, żeby nikt nie
        # brał ich za wartość, którą RW faktycznie będzie miało. Wartość
        # rozchodu liczy Subiekt ze swojej ewidencji: ten sam detal bywa na
        # magazynie w kilku partiach po różnych cenach i tylko magazyn wie,
        # którą zdejmuje (FIFO / średnia ważona).
        cols = ("Symbol", "Nazwa", "Ilość", "Cena z PW", "Wartość wg PW")
        tree = ttk.Treeview(dlg, columns=cols, show="headings", height=13)
        for c, w in zip(cols, (150, 290, 70, 95, 110)):
            tree.heading(c, text=c)
            tree.column(c, width=w, anchor="e" if c in ("Ilość", "Cena z PW", "Wartość wg PW") else "w")
        tree.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        razem = 0.0
        for p in poz:
            wart = p["cena"] * p["ilosc"]
            razem += wart
            tree.insert("", "end", values=(p["symbol"], p["nazwa"], f"{p['ilosc']:g}",
                                           f"{p['cena']:.2f}", f"{wart:.2f}"))

        stopka = tk.Frame(dlg, padx=12, pady=10)
        stopka.pack(fill="x")
        tk.Label(stopka, text=f"WG PW: {razem:,.2f} PLN".replace(",", " "),
                 font=("", 12, "bold"), fg="darkred").pack(side="left")
        tk.Label(stopka, text="— RW wystawiamy BEZ ceny (dokument będzie miał 0,00)",
                 font=("", 8), fg="gray40").pack(side="left", padx=(6, 0))
        tk.Label(stopka, text=f"Uwagi: RM_BAZA — PROJEKT {self.project_name} | PW: {numer_pw}",
                 font=("", 8), fg="gray30").pack(side="left", padx=(16, 0))
        tk.Button(stopka, text="Zamknij", command=dlg.destroy, width=12).pack(side="right")
        btn = tk.Button(stopka, text="Wystaw RW", width=14, font=("", 9, "bold"),
                        bg="#e67e22", fg="white")
        btn.config(command=lambda: self._wystaw_rw(poz, numer_pw, dlg, btn))
        btn.pack(side="right", padx=(0, 8))

    def _wystaw_rw(self, pozycje, numer_pw, dlg, btn):
        """Suchy przebieg → potwierdzenie → zapis → read-back względem PW."""
        import subiekt_produkcja
        plan = subiekt_produkcja.plan_rw(self.project_name, pozycje, numer_pw)

        btn.config(state="disabled", text="Sprawdzam…")
        dlg.update_idletasks()
        try:
            sucho = subiekt_produkcja.wyslij_rw(plan, zapisz=False)
        except Exception as e:
            btn.config(state="normal", text="Wystaw RW")
            messagebox.showerror("RW", f"Nie udało się połączyć z Subiektem:\n\n{e}", parent=dlg)
            return
        bledy = [k for k in (sucho or {}).get("kroki", []) if k.get("Status") == "blad"]
        if bledy:
            btn.config(state="normal", text="Wystaw RW")
            opis = "\n".join(f"• {k.get('Symbol') or '—'}: {k.get('Szczegoly')}" for k in bledy[:12])
            messagebox.showerror(
                "RW — suchy przebieg wykrył problemy",
                f"Dokument NIE został utworzony.\n\n{opis}"
                + ("\n…" if len(bledy) > 12 else "")
                + "\n\nCzęsty powód: za mały stan magazynowy — RW zdejmuje "
                  "z magazynu to, co PW na niego przyjęło.", parent=dlg)
            return

        razem = sum(p["cena"] * p["ilosc"] for p in pozycje)
        if not messagebox.askyesno(
                "Potwierdź zapis RW",
                f"Subiekt utworzy dokument RW:\n\n"
                f"    pozycji:  {len(pozycje)}\n"
                f"    wg PW:    {razem:,.2f} PLN  (RW powstanie BEZ ceny — 0,00)\n".replace(",", " ")
                + f"    magazyn:  {plan['magazyn']}\n"
                  f"    źródło:   {numer_pw}\n\n"
                  "To ZDEJMIE towar ze stanu magazynu.\n"
                  "Dokumentu magazynowego nie cofa się jednym kliknięciem.\n\nZapisać?",
                icon="question", default="no", parent=dlg):
            btn.config(state="normal", text="Wystaw RW")
            return

        btn.config(text="Zapisuję…")
        dlg.update_idletasks()
        try:
            wynik = subiekt_produkcja.wyslij_rw(plan, zapisz=True)
        except Exception as e:
            btn.config(state="normal", text="Wystaw RW")
            messagebox.showerror(
                "RW", f"Zapis nie powiódł się:\n\n{e}\n\n"
                "NIE ponawiaj automatycznie — najpierw sprawdź w Subiekcie, "
                "czy dokument mimo to nie powstał.", parent=dlg)
            return

        ok, numer, uwagi = subiekt_produkcja.sprawdz_rw(wynik, plan, numer_pw)
        if ok:
            self._odswiez_status_pw()
            messagebox.showinfo(
                "RW zapisane i potwierdzone",
                f"✅ {numer}\n\nProjekt: {self.project_name}\nŹródło: {numer_pw}\n"
                f"{len(pozycje)} pozycji\n\n"
                "Dokument bez ceny (0,00) — wartość niesie PW, RW tylko "
                "zdejmuje towar ze stanu."
                + "\n\n✅ PROCES RMPAK ZAKOŃCZONY", parent=dlg)
            dlg.destroy()
        else:
            messagebox.showwarning(
                "NIE POTWIERDZONO ZAPISU RW",
                (f"Dokument {numer} mógł zostać zapisany, ale odczyt z Subiekta "
                 f"nie zgadza się z PW {numer_pw}:\n\n" if numer else "Zapis nieudany:\n\n")
                + "\n".join(f"• {u}" for u in uwagi[:10])
                + "\n\nNIE twórz drugiego RW — sprawdź dokument w Subiekcie.", parent=dlg)
            btn.config(state="normal", text="Wystaw RW")

    def _wystaw_pw(self, pozycje, dlg, btn):
        """Suchy przebieg → potwierdzenie → zapis → read-back → numer w bazie.

        Kolejność z ustaleń §13. Suchy przebieg PRZED pytaniem, bo dopiero on
        wie, czy wszystkie pozycje mają kartotekę w Subiekcie — pytanie
        „zapisać?" przed sprawdzeniem byłoby pytaniem w ciemno.
        """
        import subiekt_produkcja
        # Czy PW już jest — pytamy SUBIEKTA, nie lokalnego zapisu. Odczyt
        # na żywo, bo między otwarciem okna a kliknięciem ktoś mógł je wystawić.
        try:
            _dok = subiekt_produkcja.dokumenty_produkcji(self.project_name)
            _pw = _dok.get("PW") or []
        except Exception:
            _pw = []                      # brak połączenia wyjdzie w suchym przebiegu
        numer_ist = ", ".join(d["numer"] for d in _pw)
        data_ist = _pw[0]["data"] if _pw else ""
        if numer_ist:
            # Blokada MIĘKKA (§15): pokazujemy istniejący, ale nie zamykamy drogi.
            if not messagebox.askyesno(
                    "PW już istnieje",
                    f"Dla tego projektu zapisano już PW:\n\n    {numer_ist}\n    z {data_ist}\n\n"
                    "Obowiązuje zasada 1 projekt = 1 PW.\n\n"
                    "Wystawić mimo to KOLEJNY dokument?",
                    icon="warning", default="no", parent=dlg):
                return

        plan = subiekt_produkcja.plan_pw(
            subiekt_produkcja.project_id_z_polaczenia(self.project_con),
            self.project_name, pozycje)

        btn.config(state="disabled", text="Sprawdzam…")
        dlg.update_idletasks()
        try:
            sucho = subiekt_produkcja.wyslij_pw(plan, zapisz=False)
        except Exception as e:
            btn.config(state="normal", text="Wystaw PW")
            messagebox.showerror("PW", f"Nie udało się połączyć z Subiektem:\n\n{e}", parent=dlg)
            return

        bledy = [k for k in (sucho or {}).get("kroki", []) if k.get("Status") == "blad"]
        if bledy:
            btn.config(state="normal", text="Wystaw PW")
            opis = "\n".join(f"• {k.get('Symbol') or '—'}: {k.get('Szczegoly')}" for k in bledy[:12])
            messagebox.showerror(
                "PW — suchy przebieg wykrył problemy",
                f"Dokument NIE został utworzony.\n\n{opis}"
                + ("\n…" if len(bledy) > 12 else "")
                + "\n\nKartotekę można założyć z okna „Dodaj asortyment do Subiekta”.",
                parent=dlg)
            return

        razem = sum((p["cena"] or 0) * p["ilosc"] for p in pozycje)
        if not messagebox.askyesno(
                "Potwierdź zapis PW",
                f"Subiekt utworzy dokument PW:\n\n"
                f"    pozycji:  {len(pozycje)}\n"
                f"    wartość:  {razem:,.2f} PLN\n".replace(",", " ")
                + f"    magazyn:  {plan['magazyn']}\n"
                  f"    uwagi:    {plan['uwagi']}\n\n"
                  "Dokumentu magazynowego nie cofa się jednym kliknięciem.\n\nZapisać?",
                icon="question", default="no", parent=dlg):
            btn.config(state="normal", text="Wystaw PW")
            return

        btn.config(text="Zapisuję…")
        dlg.update_idletasks()
        try:
            wynik = subiekt_produkcja.wyslij_pw(plan, zapisz=True)
        except Exception as e:
            btn.config(state="normal", text="Wystaw PW")
            messagebox.showerror(
                "PW", f"Zapis nie powiódł się:\n\n{e}\n\n"
                "NIE ponawiaj automatycznie — najpierw sprawdź w Subiekcie, "
                "czy dokument mimo to nie powstał.", parent=dlg)
            return

        ok, numer, uwagi = subiekt_produkcja.sprawdz_pw(wynik, plan)
        if ok:
            # Nic nie zapisujemy lokalnie — numer żyje w Subiekcie, w Uwagach
            # dokumentu. Odświeżenie odczyta go z powrotem.
            self._odswiez_status_pw()
            messagebox.showinfo(
                "PW zapisane i potwierdzone",
                f"✅ {numer}\n\nProjekt: {self.project_name}\n"
                f"{len(pozycje)} pozycji\n{razem:,.2f} PLN".replace(",", " "),
                parent=dlg)
            dlg.destroy()
        else:
            messagebox.showwarning(
                "NIE POTWIERDZONO ZAPISU PW",
                (f"Dokument {numer} mógł zostać zapisany, ale odczyt z Subiekta "
                 "nie zgadza się z planem:\n\n" if numer else "Zapis nieudany:\n\n")
                + "\n".join(f"• {u}" for u in uwagi[:10])
                + "\n\nNIE twórz drugiego PW — sprawdź dokument w Subiekcie.",
                parent=dlg)
            btn.config(state="normal", text="Wystaw PW")

    def _load_items(self):
        prev_item_id = self.selected_item_id
        self.tree.delete(*self.tree.get_children())
        self._items = {}
        self._qtys = {}
        self._rates = {}
        self._modes = {}
        self._semi_data = {}

        show_rmpak = self.filter_rmpak_var.get()
        show_rmpak_plus = self.filter_rmpak_plus_var.get()
        search_text = self.search_var.get().strip().lower()
        filter_supplier_id = self.filter_supplier_id
        try:
            price_min = float(self.filter_price_min_var.get().replace(",", ".").strip())
        except ValueError:
            price_min = None
        try:
            price_max = float(self.filter_price_max_var.get().replace(",", ".").strip())
        except ValueError:
            price_max = None
        show_delivered = self.filter_delivered_var.get()
        show_not_delivered = self.filter_not_delivered_var.get()
        show_ordered = self.filter_ordered_var.get()
        show_to_order = self.filter_to_order_var.get()

        rows = _load_rmpak_items(self.project_con, self.supplier_ids)
        grand_total = 0.0
        lp = 0
        for row in rows:
            (item_id, name, modul, price, hours, material, extra, qty, drawing_no, calc_rate,
             ordered_flag, delivered_qty, target_qty, calc_mode, semi_price, semi_name,
             semi_supplier_id, supplier_id) = row
            calc_mode = calc_mode or "cut"

            try:
                is_delivered = float(target_qty or 0) > 0 and float(delivered_qty or 0) >= float(target_qty or 0)
            except (ValueError, TypeError):
                is_delivered = False
            is_ordered_flag = bool(int(ordered_flag or 0))

            if calc_mode == "semi" and not show_rmpak_plus:
                continue
            if calc_mode != "semi" and not show_rmpak:
                continue
            if filter_supplier_id is not None and semi_supplier_id != filter_supplier_id:
                continue
            if price_min is not None and (price is None or price < price_min):
                continue
            if price_max is not None and (price is None or price > price_max):
                continue
            if not show_delivered and is_delivered:
                continue
            if not show_not_delivered and not is_delivered:
                continue
            if not show_ordered and is_ordered_flag:
                continue
            if not show_to_order and not is_ordered_flag:
                continue
            if search_text:
                semi_supplier_name_search = self.suppliers_map.get(semi_supplier_id, "") if semi_supplier_id else ""
                haystack = " ".join([
                    name or "", drawing_no or "", semi_name or "", semi_supplier_name_search
                ]).lower()
                if search_text not in haystack:
                    continue

            lp += 1
            qty = qty or 1
            price_str = f"{price:.2f}" if price is not None else "—"
            total = price * qty if price is not None else None
            total_str = f"{total:.2f}" if total is not None else "—"
            rate_str = f"{calc_rate:.2f}" if calc_rate else "—"
            if total is not None:
                grand_total += total
            if is_delivered:
                tag = "delivered"
            elif is_ordered_flag:
                tag = "ordered"
            else:
                tag = "odd" if lp % 2 else "even"
            semi_supplier_name = self.suppliers_map.get(semi_supplier_id, "") if semi_supplier_id else ""
            rmpak_label = "RMPAK+" if calc_mode == "semi" else "RMPAK" if calc_mode == "cut" else (self.suppliers_map.get(supplier_id, "") or "")
            iid = self.tree.insert("", "end", tags=(tag,), values=(
                lp, drawing_no or "", name or "", int(qty),
                hours or 0, f"{material:.2f}", f"{extra:.2f}", rate_str, price_str, total_str,
                semi_name or "", semi_supplier_name, rmpak_label
            ))
            self._items[iid] = item_id
            self._qtys[iid] = qty
            self._rates[iid] = calc_rate or 0.0
            self._modes[iid] = calc_mode or "cut"
            self._semi_data[iid] = (semi_price or 0.0, semi_name or "", semi_supplier_id)
        self.grand_total_var.set(f"{grand_total:,.2f} PLN")

        if prev_item_id:
            for iid, item_id in self._items.items():
                if item_id == prev_item_id:
                    self.tree.selection_set(iid)
                    self.tree.see(iid)
                    break

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
                   self.calc_vars[2].get().strip(),
                   self.item_rate_var.get().strip(),
                   self.calc_mode_var.get(),
                   self.semi_price_var.get().strip(),
                   self.semi_name_var.get().strip(),
                   str(self.semi_supplier_id)]
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
                self.item_rate_var.set(self._loaded_vals[3])
                self.calc_mode_var.set(self._loaded_vals[4])
                self.semi_price_var.set(self._loaded_vals[5])
                self.semi_name_var.set(self._loaded_vals[6])
                self.semi_supplier_id = None if self._loaded_vals[7] == "None" else int(self._loaded_vals[7])
                self._update_semi_supplier_label()
                self._update_mode_widgets()
                self._updating = False
                self._recalc()
                return
            if answer:  # Tak — zapisz
                self._save_price()

        self._prev_iid = iid
        self.selected_item_id = self._items.get(iid)

        tag = (self.tree.item(iid, "tags") or ("",))[0]
        bg = "#90EE90" if tag == "delivered" else "#FFFACD" if tag == "ordered" else "#f0f0f0"
        self.bottom.config(bg=bg)
        for child in self.bottom.winfo_children():
            if isinstance(child, tk.Label) and child is not self.semi_supplier_label:
                try:
                    child.config(bg=bg)
                except Exception:
                    pass
        self.lbl_prefix.config(bg=bg)
        vals = self.tree.item(iid, "values")
        nr = vals[1] or ""
        nazwa = vals[2] or ""
        tekst = f"{nr}  {nazwa}" if nr else nazwa
        self.selected_label.config(text=tekst, fg="black")
        qty = self._qtys.get(iid, 1)
        self.qty_label.config(text=str(qty))
        saved_rate = self._rates.get(iid, 0.0)
        mode = self._modes.get(iid, "cut")
        semi_price, semi_name, semi_supplier_id = self._semi_data.get(iid, (0.0, "", None))
        self._updating = True
        self.calc_vars[0].set(str(vals[4]))   # godz./partia
        self.calc_vars[1].set(str(vals[5]))   # materiał cięty
        self.calc_vars[2].set(str(vals[6]))   # dodatkowe
        if saved_rate:
            self.item_rate_var.set(str(saved_rate))
        else:
            self.item_rate_var.set(str(self.hourly_rate))
        self.calc_mode_var.set(mode)
        self.semi_price_var.set(f"{semi_price:.2f}")
        self.semi_name_var.set(semi_name)
        self.semi_supplier_id = semi_supplier_id
        self._update_semi_supplier_label()
        self._update_mode_widgets()
        self._updating = False
        self._loaded_vals = (self.calc_vars[0].get().strip(),
                             self.calc_vars[1].get().strip(),
                             self.calc_vars[2].get().strip(),
                             self.item_rate_var.get().strip(),
                             self.calc_mode_var.get(),
                             self.semi_price_var.get().strip(),
                             self.semi_name_var.get().strip(),
                             str(self.semi_supplier_id))
        self._recalc()

    def _on_mode_change(self):
        self._update_mode_widgets()
        self._recalc()

    def _update_mode_widgets(self):
        is_semi = self.calc_mode_var.get() == "semi"
        self.material_entry.config(state="disabled" if is_semi else "normal")
        self.material_calc_btn.config(state="disabled" if is_semi else "normal")
        self.lbl_material.config(fg="gray" if is_semi else "black")
        for w in (self.semi_price_entry, self.semi_name_entry, self.semi_supplier_btn):
            w.config(state="normal" if is_semi else "disabled")
        fg = "black" if is_semi else "gray"
        self.lbl_semi_price.config(fg=fg)

    def _update_semi_supplier_label(self):
        name = self.suppliers_map.get(self.semi_supplier_id, "") if self.semi_supplier_id else ""
        self.semi_supplier_var.set(name or "(brak)")

    def _on_filter_supplier_chosen(self, sid, name):
        self.filter_supplier_id = sid
        self.filter_supplier_var.set(name if name else "(wszyscy)")
        self._load_items()

    def _clear_filters(self):
        self.search_var.set("")
        self.filter_supplier_id = None
        self.filter_supplier_var.set("(wszyscy)")
        self.filter_price_min_var.set("")
        self.filter_price_max_var.set("")
        self.filter_delivered_var.set(True)
        self.filter_not_delivered_var.set(True)
        self.filter_ordered_var.set(True)
        self.filter_to_order_var.set(True)
        self._load_items()

    def _pick_semi_supplier(self):
        def on_choose(sid, name):
            self.semi_supplier_id = sid
            self._update_semi_supplier_label()
        self._show_supplier_picker(self.semi_supplier_id, on_choose)

    def _open_material_calculator(self):
        from material_calculator import MaterialCalculatorDialog

        def on_use(price):
            self.calc_vars[1].set(f"{price:.2f}")

        MaterialCalculatorDialog(self.win, self.master_con, on_use=on_use)

    def _show_supplier_picker(self, current_id, on_choose):
        """Okno wyboru dostawcy — identyczne jak w głównym arkuszu (prawy klik na Dostawca)."""
        popup = tk.Toplevel(self.win)
        popup.transient(self.win)

        main_frame = tk.Frame(popup, bg="white", relief="solid", bd=1)
        main_frame.pack(fill="both", expand=True)

        list_frame = tk.Frame(main_frame, bg="white")
        list_frame.pack(fill="both", expand=True, padx=2, pady=2)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(
            list_frame, height=20, width=35, font=("Arial", 10),
            yscrollcommand=scrollbar.set, selectmode="single", activestyle="dotbox"
        )
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

        current_name = self.suppliers_map.get(current_id, "") if current_id else ""
        suppliers_list = sorted(self.suppliers_map.items(), key=lambda x: x[1].lower())
        current_index = None
        for idx, (sid, name) in enumerate(suppliers_list):
            display_text = f"✓ {name}" if name == current_name else f"  {name}"
            listbox.insert("end", display_text)
            listbox.itemconfig(idx, {"bg": "#e8f4f8" if name == current_name else "white"})
            if name == current_name:
                current_index = idx
        if current_index is not None:
            listbox.selection_set(current_index)
            listbox.see(current_index)

        separator = tk.Frame(main_frame, height=1, bg="#cccccc")
        separator.pack(fill="x", padx=2)

        btn_frame = tk.Frame(main_frame, bg="white")
        btn_frame.pack(fill="x", padx=2, pady=2)

        def clear_choice():
            on_choose(None, "")
            close()

        tk.Button(btn_frame, text="Wyczyść", command=clear_choice, font=("Arial", 9),
                  bg="#fff3cd", relief="flat", padx=8, pady=2).pack(side="left", padx=2)

        def on_select(_event=None):
            sel = listbox.curselection()
            if sel:
                idx = sel[0]
                sid, name = suppliers_list[idx]
                on_choose(sid, name)
            close()

        def close(_event=None):
            try:
                if hasattr(popup, "_click_binding_id"):
                    self.win.unbind_all("<Button-1>", popup._click_binding_id)
            except Exception:
                pass
            popup.destroy()

        def check_click_outside(event):
            widget = event.widget
            while widget:
                if widget == popup:
                    return
                try:
                    widget = widget.master
                except Exception:
                    break
            close()

        _typeahead_buf = []
        _typeahead_after = [None]

        def on_key(event):
            ch = event.char
            if not ch or not ch.isprintable():
                return
            if _typeahead_after[0]:
                popup.after_cancel(_typeahead_after[0])
            _typeahead_buf.append(ch)
            query = "".join(_typeahead_buf).lower()
            for i, (sid, name) in enumerate(suppliers_list):
                if name.lower().startswith(query):
                    listbox.selection_clear(0, "end")
                    listbox.selection_set(i)
                    listbox.activate(i)
                    listbox.see(i)
                    break
            _typeahead_after[0] = popup.after(700, _typeahead_buf.clear)

        def on_arrow(event):
            popup.after(1, lambda: (
                listbox.selection_clear(0, "end"),
                listbox.selection_set(listbox.index("active"))
            ))

        listbox.bind("<Up>", on_arrow, add="+")
        listbox.bind("<Down>", on_arrow, add="+")
        listbox.bind("<Key>", on_key)
        listbox.bind("<ButtonRelease-1>", on_select)
        listbox.bind("<Return>", on_select)
        listbox.bind("<Escape>", close)

        popup.update_idletasks()
        x = self.win.winfo_pointerx()
        y = self.win.winfo_pointery()
        popup_height = popup.winfo_reqheight()
        screen_height = popup.winfo_screenheight()
        if y + popup_height > screen_height - 50:
            y = y - popup_height - 10
        popup.wm_geometry(f"+{x}+{y}")

        listbox.focus_set()
        popup._click_binding_id = self.win.bind_all("<Button-1>", check_click_outside, add="+")

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
            rate = self._parse(self.item_rate_var.get())
            hours = self._parse(self.calc_vars[0].get())
            extra = self._parse(self.calc_vars[2].get())
            qty_text = self.qty_label.cget("text")
            qty = float(qty_text) if qty_text not in ("—", "") else 1.0
            if self.calc_mode_var.get() == "semi":
                semi_price = self._parse(self.semi_price_var.get())
                total = rate * hours + semi_price * qty + extra
            else:
                material = self._parse(self.calc_vars[1].get())
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
        if not self.selected_item_id:
            self.item_rate_var.set(str(rate))
        messagebox.showinfo("OK", f"Stawka {rate:.2f} PLN/h zapisana.", parent=self.win)

    def _save_price(self):
        if not self.selected_item_id:
            messagebox.showwarning("Brak wyboru", "Wybierz pozycję z listy.", parent=self.win)
            return
        mode = self.calc_mode_var.get()
        try:
            rate = self._parse(self.item_rate_var.get())
            hours = self._parse(self.calc_vars[0].get())
            extra = self._parse(self.calc_vars[2].get())
            qty_text = self.qty_label.cget("text")
            qty = float(qty_text) if qty_text not in ("—", "") else 1.0
            if mode == "semi":
                material = 0.0
                semi_price = self._parse(self.semi_price_var.get())
                total = rate * hours + semi_price * qty + extra
            else:
                material = self._parse(self.calc_vars[1].get())
                semi_price = 0.0
                total = rate * hours + material + extra
            price_per_unit = total / qty if qty else 0.0
        except ValueError:
            messagebox.showerror("Błąd", "Nieprawidłowe wartości.", parent=self.win)
            return

        semi_name = self.semi_name_var.get().strip() if mode == "semi" else ""
        semi_supplier_id = self.semi_supplier_id if mode == "semi" else None

        if self.on_save_item:
            self.on_save_item(self.selected_item_id, price_per_unit, hours, material, extra, rate,
                               mode, semi_price, semi_name, semi_supplier_id)
        else:
            self.project_con.execute(
                """UPDATE items SET price_pln=?, calc_hours=?, calc_material=?, calc_extra=?, calc_rate=?,
                       calc_mode=?, calc_semi_price=?, calc_semi_name=?, calc_semi_supplier_id=?
                   WHERE id=?""",
                (price_per_unit, hours, material, extra, rate,
                 mode, semi_price, semi_name, semi_supplier_id, self.selected_item_id)
            )
            self.project_con.commit()

        # auto-przełącz dostawcę pozycji: RMPAK (cięty) / RMPAK+ (półprodukt)
        target_supplier_id = self.rmpak_semi_id if mode == "semi" else self.rmpak_cut_id
        if target_supplier_id is not None:
            self.project_con.execute(
                "UPDATE items SET supplier_id=? WHERE id=?",
                (target_supplier_id, self.selected_item_id)
            )
            self.project_con.commit()

        self._loaded_vals = (self.calc_vars[0].get().strip(),
                             self.calc_vars[1].get().strip(),
                             self.calc_vars[2].get().strip(),
                             self.item_rate_var.get().strip(),
                             mode,
                             self.semi_price_var.get().strip(),
                             self.semi_name_var.get().strip(),
                             str(self.semi_supplier_id))

        # odśwież wiersz w tabeli
        sel = self.tree.selection()
        if sel:
            iid = sel[0]
            qty = self._qtys.get(iid, 1)
            rmpak_label = "RMPAK+" if mode == "semi" else "RMPAK"
            semi_supplier_name = self.suppliers_map.get(semi_supplier_id, "") if semi_supplier_id else ""
            vals = list(self.tree.item(iid, "values"))
            vals[4] = hours
            vals[5] = material
            vals[6] = extra
            vals[7] = f"{rate:.2f}"
            vals[8] = f"{price_per_unit:.2f}"
            vals[9] = f"{price_per_unit * qty:.2f}"
            vals[10] = semi_name
            vals[11] = semi_supplier_name
            vals[12] = rmpak_label
            self.tree.item(iid, values=vals)
            self._rates[iid] = rate
            self._modes[iid] = mode
            self._semi_data[iid] = (semi_price, semi_name, semi_supplier_id)
        # przelicz sumę całkowitą
        grand = 0.0
        for child in self.tree.get_children():
            v = self.tree.item(child, "values")[9]
            try:
                grand += float(v)
            except (ValueError, TypeError):
                pass
        self.grand_total_var.set(f"{grand:,.2f} PLN")

        # Licznik braków ma maleć NA OCZACH — inaczej user przelicza pozycje
        # i nie widzi, czy zbliża się do kompletu, dopóki nie otworzy podglądu.
        try:
            self._odswiez_status_pw()
        except Exception:
            pass

        if self.on_price_saved:
            self.on_price_saved()

    def _on_double_click(self, _event=None):
        if not self.on_jump_to_item or not self.selected_item_id:
            return
        self.on_jump_to_item(self.selected_item_id)

    def _on_close(self):
        if self._has_unsaved_changes():
            answer = messagebox.askyesnocancel(
                "Niezapisane zmiany",
                "Masz niezapisane zmiany dla tej pozycji.\nCzy zapisać przed zamknięciem?",
                parent=self.win
            )
            if answer is None:  # Anuluj — nie zamykaj
                return
            if answer:  # Tak — zapisz i zamknij
                self._save_price()
        self.win.destroy()
