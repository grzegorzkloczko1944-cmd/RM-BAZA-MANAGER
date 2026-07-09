import tkinter as tk
from tkinter import ttk, messagebox
import math
from datetime import datetime


DEFAULT_MATERIALS = [
    # (nazwa, gęstość g/cm3, domyślna cena PLN/kg)
    ("Tworzywo", 1.4, 0.0),
    ("304", 7.9, 0.0),
    ("316", 8.0, 0.0),
    ("Stal czarna", 7.85, 0.0),
    ("PTFE", 2.2, 0.0),
    ("Mosiądz", 8.5, 0.0),
    ("PA6 (aluminium)", 2.7, 0.0),
]

PROFILES = ("Pręt", "Rura", "Płaskownik", "Profil prostokąt", "Sześciokąt", "Kątownik")


def _ensure_material_table(master_con):
    master_con.execute("""
        CREATE TABLE IF NOT EXISTS material_prices (
            material TEXT PRIMARY KEY,
            density REAL NOT NULL,
            price_per_kg REAL NOT NULL DEFAULT 0,
            updated_at TEXT
        )
    """)
    existing = {row[0] for row in master_con.execute("SELECT material FROM material_prices")}
    for name, density, price in DEFAULT_MATERIALS:
        if name not in existing:
            master_con.execute(
                "INSERT INTO material_prices (material, density, price_per_kg, updated_at) VALUES (?, ?, ?, ?)",
                (name, density, price, datetime.now().isoformat())
            )
    master_con.commit()


def _load_materials(master_con):
    rows = master_con.execute(
        "SELECT material, density, price_per_kg FROM material_prices ORDER BY material"
    ).fetchall()
    return {name: (density, price) for name, density, price in rows}


def _save_material_price(master_con, material, density, price):
    master_con.execute(
        """INSERT INTO material_prices (material, density, price_per_kg, updated_at) VALUES (?, ?, ?, ?)
           ON CONFLICT(material) DO UPDATE SET density=excluded.density, price_per_kg=excluded.price_per_kg,
               updated_at=excluded.updated_at""",
        (material, density, price, datetime.now().isoformat())
    )
    master_con.commit()


def _cross_section_mm2(profile, dims):
    """dims: dict wymiarów w mm. Zwraca pole przekroju w mm^2."""
    if profile == "Pręt":
        d = dims["d"]
        return math.pi * (d / 2) ** 2
    if profile == "Rura":
        d_out = dims["d_out"]
        wall = dims["wall"]
        r_out = d_out / 2
        r_in = max(r_out - wall, 0)
        return math.pi * (r_out ** 2 - r_in ** 2)
    if profile == "Płaskownik":
        return dims["width"] * dims["height"]
    if profile == "Profil prostokąt":
        w, h, wall = dims["width"], dims["height"], dims["wall"]
        inner_w = max(w - 2 * wall, 0)
        inner_h = max(h - 2 * wall, 0)
        return w * h - inner_w * inner_h
    if profile == "Sześciokąt":
        s = dims["width"]  # wymiar "pod klucz" (rozstaw równoległych ścian)
        return (math.sqrt(3) / 2) * s ** 2
    if profile == "Kątownik":
        w, h, wall = dims["width"], dims["height"], dims["wall"]
        return (w + h - wall) * wall
    raise ValueError(f"Nieznany profil: {profile}")


def calculate_material_price(profile, dims, length_mm, density, price_per_kg):
    area_mm2 = _cross_section_mm2(profile, dims)
    volume_mm3 = area_mm2 * length_mm
    volume_cm3 = volume_mm3 / 1000.0
    mass_kg = (volume_cm3 * density) / 1000.0
    price = mass_kg * price_per_kg
    return mass_kg, price


class MaterialCalculatorDialog:
    def __init__(self, parent, master_con, on_use=None):
        self.master_con = master_con
        self.on_use = on_use  # fn(price_pln)

        _ensure_material_table(master_con)
        self.materials = _load_materials(master_con)

        self.win = tk.Toplevel(parent)
        self.win.title("Kalkulator materiału")
        self.win.resizable(False, False)
        self.win.transient(parent)

        self._build_ui()
        self._on_profile_change()
        self._center_on_screen()

    def _center_on_screen(self):
        self.win.update_idletasks()
        w = self.win.winfo_reqwidth() + 20
        h = self.win.winfo_reqheight() + 20
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    @staticmethod
    def _bind_select_all(entry):
        def _select(e):
            e.widget.select_range(0, "end")
            e.widget.icursor("end")
        entry.bind("<FocusIn>", _select)

    def _build_ui(self):
        frm = tk.Frame(self.win, padx=10, pady=10)
        frm.pack(fill="both", expand=True)

        tk.Label(frm, text="Materiał:").grid(row=0, column=0, sticky="e", padx=(0, 4), pady=4)
        self.material_var = tk.StringVar(value=next(iter(self.materials), ""))
        material_combo = ttk.Combobox(frm, textvariable=self.material_var, state="readonly",
                                       values=sorted(self.materials.keys()), width=20)
        material_combo.grid(row=0, column=1, sticky="w", pady=4)
        material_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_material_change())

        tk.Label(frm, text="Gęstość (g/cm³):").grid(row=0, column=2, sticky="e", padx=(16, 4), pady=4)
        self.density_var = tk.StringVar(value="0")
        density_entry = tk.Entry(frm, textvariable=self.density_var, width=10)
        density_entry.grid(row=0, column=3, sticky="w", pady=4)
        self._bind_select_all(density_entry)
        self.density_var.trace_add("write", self._recalc)

        tk.Label(frm, text="Cena (PLN/kg):").grid(row=1, column=2, sticky="e", padx=(16, 4), pady=4)
        self.price_kg_var = tk.StringVar(value="0")
        price_kg_entry = tk.Entry(frm, textvariable=self.price_kg_var, width=10)
        price_kg_entry.grid(row=1, column=3, sticky="w", pady=4)
        self._bind_select_all(price_kg_entry)
        self.price_kg_var.trace_add("write", self._recalc)

        tk.Button(frm, text="Zapisz cenę materiału", command=self._save_material
                  ).grid(row=1, column=0, columnspan=2, sticky="w", pady=4)

        tk.Label(frm, text="Profil:").grid(row=2, column=0, sticky="e", padx=(0, 4), pady=(12, 4))
        self.profile_var = tk.StringVar(value=PROFILES[0])
        profile_combo = ttk.Combobox(frm, textvariable=self.profile_var, state="readonly",
                                      values=PROFILES, width=20)
        profile_combo.grid(row=2, column=1, sticky="w", pady=(12, 4))
        profile_combo.bind("<<ComboboxSelected>>", lambda _e: (self._on_profile_change(), self._center_on_screen()))

        self.dims_frame = tk.Frame(frm)
        self.dims_frame.grid(row=3, column=0, columnspan=4, sticky="w", pady=(4, 8))
        self.dim_vars = {}

        self.length_row_frame = tk.Frame(frm)
        self.length_row_frame.grid(row=4, column=0, columnspan=4, sticky="w", pady=(0, 4))
        tk.Label(self.length_row_frame, text="Długość cięcia (mm):", width=22, anchor="e").pack(side="left", padx=(0, 4))
        self.length_var = tk.StringVar(value="0")
        length_entry = tk.Entry(self.length_row_frame, textvariable=self.length_var, width=10)
        length_entry.pack(side="left")
        self._bind_select_all(length_entry)
        self.length_var.trace_add("write", self._recalc)

        tk.Label(frm, text="Masa:").grid(row=5, column=0, sticky="e", padx=(0, 4), pady=(12, 4))
        self.mass_var = tk.StringVar(value="—")
        tk.Label(frm, textvariable=self.mass_var, font=("", 10, "bold")).grid(row=5, column=1, sticky="w", pady=(12, 4))

        tk.Label(frm, text="Cena materiału:").grid(row=5, column=2, sticky="e", padx=(16, 4), pady=(12, 4))
        self.result_price_var = tk.StringVar(value="— PLN")
        tk.Label(frm, textvariable=self.result_price_var, font=("", 12, "bold"), fg="darkgreen"
                 ).grid(row=5, column=3, sticky="w", pady=(12, 4))

        btn_frame = tk.Frame(frm)
        btn_frame.grid(row=6, column=0, columnspan=4, sticky="e", pady=(12, 0))
        if self.on_use:
            tk.Button(btn_frame, text="Użyj w Materiał cięty", command=self._use_result,
                      bg="#4CAF50", fg="white", font=("", 9, "bold")).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="Zamknij", command=self.win.destroy).pack(side="left")

        self._on_material_change()

    def _on_material_change(self):
        name = self.material_var.get()
        density, price = self.materials.get(name, (0.0, 0.0))
        self.density_var.set(str(density))
        self.price_kg_var.set(str(price))

    def _save_material(self):
        name = self.material_var.get()
        if not name:
            return
        try:
            density = float(self.density_var.get().replace(",", "."))
            price = float(self.price_kg_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Błąd", "Nieprawidłowe wartości gęstości/ceny.", parent=self.win)
            return
        _save_material_price(self.master_con, name, density, price)
        self.materials[name] = (density, price)
        messagebox.showinfo("OK", f"Zapisano cenę materiału {name}.", parent=self.win)

    def _on_profile_change(self):
        for child in self.dims_frame.winfo_children():
            child.destroy()
        self.dim_vars = {}

        profile = self.profile_var.get()
        fields = {
            "Pręt": [("Średnica (mm):", "d")],
            "Rura": [("Średnica zewn. (mm):", "d_out"), ("Ścianka (mm):", "wall")],
            "Płaskownik": [("Szerokość (mm):", "width"), ("Wysokość (mm):", "height")],
            "Profil prostokąt": [("Szerokość (mm):", "width"), ("Wysokość (mm):", "height"), ("Ścianka (mm):", "wall")],
            "Sześciokąt": [("Szerokość - pod klucz (mm):", "width")],
            "Kątownik": [("Szerokość (mm):", "width"), ("Wysokość (mm):", "height"), ("Ścianka (mm):", "wall")],
        }[profile]

        for row, (label, key) in enumerate(fields):
            tk.Label(self.dims_frame, text=label, width=22, anchor="e").grid(row=row, column=0, sticky="e", padx=(0, 4), pady=2)
            var = tk.StringVar(value="0")
            entry = tk.Entry(self.dims_frame, textvariable=var, width=10)
            entry.grid(row=row, column=1, sticky="w", pady=2)
            self._bind_select_all(entry)
            var.trace_add("write", self._recalc)
            self.dim_vars[key] = var

        self._recalc()

    def _recalc(self, *_):
        try:
            density = float(self.density_var.get().replace(",", "."))
            price_per_kg = float(self.price_kg_var.get().replace(",", "."))
            length_mm = float(self.length_var.get().replace(",", "."))
            dims = {k: float(v.get().replace(",", ".")) for k, v in self.dim_vars.items()}
        except ValueError:
            self.mass_var.set("—")
            self.result_price_var.set("— PLN")
            self._last_price = None
            return

        try:
            mass_kg, price = calculate_material_price(
                self.profile_var.get(), dims, length_mm, density, price_per_kg
            )
        except (ValueError, ZeroDivisionError):
            self.mass_var.set("—")
            self.result_price_var.set("— PLN")
            self._last_price = None
            return

        self.mass_var.set(f"{mass_kg:.3f} kg")
        self.result_price_var.set(f"{price:.2f} PLN")
        self._last_price = price

    def _use_result(self):
        price = getattr(self, "_last_price", None)
        if price is None:
            messagebox.showwarning("Brak wyniku", "Najpierw kliknij 'Oblicz'.", parent=self.win)
            return
        if self.on_use:
            self.on_use(price)
        self.win.destroy()
