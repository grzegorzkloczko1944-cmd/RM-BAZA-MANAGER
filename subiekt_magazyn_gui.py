# -*- coding: utf-8 -*-
"""
Stany magazynowe CAŁEGO Subiekta — przegląd niezależny od projektu.

    import subiekt_magazyn_gui
    subiekt_magazyn_gui.open_window(parent)

Czym się różni od „Stany pozycji projektu" (subiekt_stany.py): tamto okno
odpowiada na pytanie „czy mam to, czego potrzebuję do TEGO projektu" — bierze
BOM i pyta punktowo o jego numery. Tutaj chodzi o „co w ogóle mam na
magazynie", bez wiązania z jakimkolwiek projektem.

Dane idą mostem (`NexoRecon.exe magazyn`), ~14 s przy magazynie demo. Most
czyta StanyMagazynowe per kartoteka — to najdroższa część odczytu, dlatego
domyślnie pomijamy kartoteki bez ruchu (`--tylko-niezerowe`); przełącznik
„pokaż też zerowe" pobiera komplet.

Rozbicie na magazyny jest w danych (kolumna Magazyny) i pokazuje się
w dolnym panelu po kliknięciu w pozycję — w tabeli głównej byłoby nieczytelne,
bo liczba magazynów bywa różna dla różnych kartotek.
"""

import json
import os
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from rm_kreciolek import Kreciolek
from subiekt_stany import (_find_exe, blad_mostu, wysrodkuj,
                           podepnij_szerokosci, CONFIG_PATH)

try:
    from tksheet import Sheet
except ImportError:
    Sheet = None

TIMEOUT_S = 600


def pobierz_magazyn(tylko_niezerowe=True, timeout=TIMEOUT_S):
    """[{Id, Symbol, Nazwa, Rodzaj, Dostepne, Zadysponowane, Zarezerwowane,
        CenaEwidencyjna, Magazyny:[{Magazyn, Dostepne, Zadysponowane}]}]."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")

    tmpdir = tempfile.mkdtemp(prefix="subiekt_mag_")
    out = os.path.join(tmpdir, "magazyn.json")
    cmd = [exe, "magazyn", f"--out={out}"]
    if tylko_niezerowe:
        cmd.append("--tylko-niezerowe")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=flags)
    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, "magazyn", proc, out))

    with open(out, encoding="utf-8") as f:
        return json.load(f).get("pozycje", [])


class MagazynWindow(tk.Toplevel, Kreciolek):
    KOLUMNY = [("symbol", "Symbol", 170), ("nazwa", "Nazwa", 330),
               ("rodzaj", "Rodzaj", 110), ("dostepne", "Dostępne", 90),
               ("zadysponowane", "Zadysponowane", 110),
               ("zarezerwowane", "Zarezerwowane", 110),
               ("cena", "Cena ewid.", 95), ("magazynow", "Magazynów", 85)]
    KOL_MAG = [("magazyn", "Magazyn", 180), ("dostepne", "Dostępne", 110),
               ("zadysponowane", "Zadysponowane", 130)]

    def __init__(self, parent):
        super().__init__(parent)
        self.pozycje = []
        self.widoczne = []

        self.title("Subiekt — stany magazynowe (cały magazyn)")
        self.geometry("1200x720")
        self.minsize(900, 450)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self._buduj()
        self.after(100, self._wczytaj_async)

    # ── UI ─────────────────────────────────────────────────────────────────
    def _buduj(self):
        top = tk.Frame(self, bg="#34495e", height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="📦 Stany magazynowe — cały Subiekt",
                 bg="#34495e", fg="white",
                 font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)
        self.lbl_wiek = tk.Label(top, text="", bg="#34495e", fg="#e74c3c",
                                 font=("Arial", 13, "bold"))
        self.lbl_wiek.pack(side=tk.LEFT, padx=(16, 0))
        self.btn_refresh = tk.Button(top, text="🔄 Odśwież", command=self._wczytaj_async,
                                     bg="#3498db", fg="white", font=("Arial", 8),
                                     padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_refresh.pack(side=tk.RIGHT, padx=10, pady=8)

        f = tk.Frame(self, bg="#ecf0f1")
        f.pack(side=tk.TOP, fill=tk.X)
        tk.Label(f, text="Szukaj:", bg="#ecf0f1",
                 font=("Arial", 9)).pack(side=tk.LEFT, padx=(12, 3), pady=6)
        self.var_szukaj = tk.StringVar()
        self.var_szukaj.trace_add("write", lambda *_: self._odswiez_liste())
        tk.Entry(f, textvariable=self.var_szukaj, width=26,
                 font=("Arial", 9)).pack(side=tk.LEFT, pady=6)
        tk.Label(f, text="(symbol albo nazwa)", bg="#ecf0f1", fg="#7f8c8d",
                 font=("Arial", 8)).pack(side=tk.LEFT, padx=(4, 0))

        # Kartoteki bez ruchu to zwykle martwe indeksy — domyślnie poza listą,
        # bo wydłużają odczyt i zaśmiecają widok.
        self.var_zerowe = tk.IntVar(value=0)
        tk.Checkbutton(f, text="pokaż też pozycje bez stanu", variable=self.var_zerowe,
                       command=self._wczytaj_async, bg="#ecf0f1", font=("Arial", 8),
                       activebackground="#ecf0f1").pack(side=tk.LEFT, padx=(14, 0), pady=6)

        self.podsumowanie = tk.Label(self, text="Wczytywanie…", bg="#ecf0f1",
                                     fg="#2c3e50", font=("Arial", 9), anchor="w",
                                     padx=12, pady=6)
        self.podsumowanie.pack(side=tk.TOP, fill=tk.X)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        panel = ttk.PanedWindow(self, orient=tk.VERTICAL)
        panel.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 4))

        gora = tk.Frame(panel)
        panel.add(gora, weight=3)
        if Sheet is None:
            tk.Label(gora, text="Brak biblioteki tksheet", fg="#c0392b").pack(pady=20)
            self.sheet = self.sheet_mag = None
            return

        self.sheet = Sheet(gora, headers=[k[1] for k in self.KOLUMNY],
                           column_width=140, theme="light blue")
        self.sheet.set_options(show_selected_cells_border=True,
                               enable_edit_cell_auto_resize=False,
                               empty_horizontal=0, empty_vertical=0)
        self.sheet.enable_bindings((
            "single_select", "drag_select", "ctrl_select", "select_all",
            "column_width_resize", "arrowkeys", "right_click_popup_menu",
            "rc_select", "copy",
        ))
        podepnij_szerokosci(self, self.sheet, "magazyn", [k[2] for k in self.KOLUMNY])
        self.sheet.extra_bindings("cell_select", self._wybor_pozycji)
        self.sheet.extra_bindings("row_select", self._wybor_pozycji)
        self.sheet.pack(fill=tk.BOTH, expand=True)

        dol = tk.Frame(panel)
        panel.add(dol, weight=1)
        tk.Label(dol, text="Rozbicie na magazyny", bg="#ecf0f1", anchor="w",
                 font=("Arial", 8, "bold"), padx=8, pady=3).pack(side=tk.TOP, fill=tk.X)
        self.sheet_mag = Sheet(dol, headers=[k[1] for k in self.KOL_MAG],
                               column_width=150, theme="light blue")
        self.sheet_mag.set_options(show_selected_cells_border=True,
                                   enable_edit_cell_auto_resize=False,
                                   empty_horizontal=0, empty_vertical=0)
        self.sheet_mag.enable_bindings(("single_select", "column_width_resize",
                                        "arrowkeys", "copy"))
        podepnij_szerokosci(self, self.sheet_mag, "magazyn_rozbicie",
                            [k[2] for k in self.KOL_MAG])
        self.sheet_mag.pack(fill=tk.BOTH, expand=True)

    # ── wczytywanie ────────────────────────────────────────────────────────
    def _wczytaj_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.start_kreciolek("Czytam stany magazynowe z Subiekta (~15 s)")
        threading.Thread(target=self._wczytaj_worker, daemon=True).start()

    def _wczytaj_worker(self):
        try:
            poz = pobierz_magazyn(tylko_niezerowe=not self.var_zerowe.get())
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._wczytaj_done(None, err))
            return
        self.after(0, lambda: self._wczytaj_done(poz, None))

    def _wczytaj_done(self, poz, error):
        self.stop_kreciolek()
        try:
            self.btn_refresh.config(state=tk.NORMAL)
        except tk.TclError:
            return                      # okno zamknięte w trakcie odczytu
        if error:
            self.status.config(text="Błąd odczytu.")
            messagebox.showerror("Subiekt", error, parent=self)
            return
        self.pozycje = poz or []
        self.zaznacz_odczyt(self.lbl_wiek)
        self._odswiez_liste()

    # ── lista ──────────────────────────────────────────────────────────────
    def _odswiez_liste(self):
        if not self.sheet:
            return
        szukaj = (self.var_szukaj.get() or "").strip().lower()
        self.widoczne = [
            p for p in self.pozycje
            if not szukaj
            or szukaj in str(p.get("Symbol", "")).lower()
            or szukaj in str(p.get("Nazwa", "")).lower()
        ]
        self.sheet.set_sheet_data([[
            p.get("Symbol", ""), p.get("Nazwa", ""), p.get("Rodzaj") or "",
            f"{p.get('Dostepne', 0):g}", f"{p.get('Zadysponowane', 0):g}",
            f"{p.get('Zarezerwowane', 0):g}", f"{p.get('CenaEwidencyjna', 0):g}",
            str(len(p.get("Magazyny") or [])),
        ] for p in self.widoczne], reset_col_positions=False)

        laczna = sum(float(p.get("Dostepne") or 0) for p in self.widoczne)
        wartosc = sum(float(p.get("Dostepne") or 0) * float(p.get("CenaEwidencyjna") or 0)
                      for p in self.widoczne)
        self.podsumowanie.config(
            text=f"Pozycji: {len(self.widoczne)} z {len(self.pozycje)}    "
                 f"sztuk łącznie: {laczna:g}    "
                 f"wartość wg ceny ewidencyjnej: {wartosc:,.2f} zł".replace(",", " "))
        if self.sheet_mag:
            self.sheet_mag.set_sheet_data([], reset_col_positions=False)

    def _wybor_pozycji(self, _event=None):
        """Rozbicie na magazyny dla klikniętej pozycji."""
        if not self.sheet or not self.sheet_mag:
            return
        try:
            rows = self.sheet.get_selected_rows(get_cells_as_rows=True)
        except Exception:
            rows = []
        if not rows:
            return
        r = sorted(rows)[0]
        if not (0 <= r < len(self.widoczne)):
            return
        p = self.widoczne[r]
        self.sheet_mag.set_sheet_data([[
            m.get("Magazyn", ""), f"{m.get('Dostepne', 0):g}",
            f"{m.get('Zadysponowane', 0):g}",
        ] for m in (p.get("Magazyny") or [])], reset_col_positions=False)
        self.status.config(text=f"{p.get('Symbol', '')} — {p.get('Nazwa', '')}")


def open_window(parent):
    return MagazynWindow(parent)
