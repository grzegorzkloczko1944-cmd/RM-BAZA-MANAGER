# -*- coding: utf-8 -*-
"""
Magazyn — stany, progi min/opt i zamówienia NA SKŁAD (cały Subiekt).

    import subiekt_magazyn_gui
    subiekt_magazyn_gui.open_window(parent)

Trzy zadania w jednym oknie, bo wszystkie kręcą się wokół tej samej listy
kartotek ze stanem:

1. PRZEGLĄD — co w ogóle mam na magazynie (to było tu od początku).
2. PROGI — stan minimalny / optymalny per kartoteka, edytowane wprost
   w tabeli i zapisywane do Subiekta (tryb mostu „progi"). Do 05.09.2026
   żadna z 3442 kartotek ich nie miała: magazynier biegał z karteczkami,
   a mechanizm „domów, gdy spadnie poniżej" w Subiekcie leżał odłogiem.
3. ZAMÓWIENIE NA MAGAZYN — ZD dla zaznaczonych pozycji, BEZ projektu:
   w Uwagach dokumentu jest „MAGAZYN", więc w Przeglądzie dokumentów widać,
   że to zakup na skład, a nie pod zamówienie klienta. Pozycje idą jako
   „ręczne" (tryb zd, reczna=True), bo nie ma za nimi żadnej ZK.

Czym się różni od „Zamówienia do dostawców" (subiekt_zamowienia.py): tamto
okno jest napędzane ZAPOTRZEBOWANIEM z ZK — pokazuje braki wynikające
z zamówień klientów. Tutaj punktem wyjścia jest stan magazynu i próg.

Dane idą mostem (`NexoRecon.exe magazyn`, ~15 s). Kolumna „Kupić" liczy się
sama: gdy stan ≤ min, kupić = opt − stan; da się nadpisać ręcznie.
"""

import json
import os
import subprocess
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

from rm_kreciolek import Kreciolek
from subiekt_stany import (_find_exe, blad_mostu, wysrodkuj,
                           podepnij_szerokosci, CONFIG_PATH)

try:
    from tksheet import Sheet
except ImportError:
    Sheet = None

TIMEOUT_S = 600
#: Magazyn, do którego zapisujemy progi i na który idzie ZD. Firma ma jeden
#: towarowy — ten sam, którego używa Zd.cs, gdy ZD nie ma magazynu.
MAGAZYN = "MAG"
#: Znacznik w Uwagach ZD na skład — kolumna „Projekt" w Przeglądzie dokumentów
#: bierze się z Uwag, więc zamówienie magazynowe pokaże się tam jako MAGAZYN.
UWAGI_MAGAZYN = "MAGAZYN"
#: Znak nowej linii do składania komunikatów w okienkach.
NL = chr(10)


# ── most ────────────────────────────────────────────────────────────────────
def _uruchom(tryb, argv, out, timeout):
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run([exe, tryb, f"--out={out}", *argv],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=flags)
    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, tryb, proc, out))
    with open(out, encoding="utf-8") as f:
        return json.load(f)


def pobierz_magazyn(tylko_niezerowe=True, timeout=TIMEOUT_S):
    """[{Id, Symbol, Nazwa, Rodzaj, Dostepne, Zadysponowane, Zarezerwowane,
        CenaEwidencyjna, Magazyny:[{Magazyn, Dostepne, Zadysponowane}],
        StanMinimalny, StanOptymalny, Dostawca, Zd}]."""
    out = os.path.join(tempfile.mkdtemp(prefix="subiekt_mag_"), "magazyn.json")
    argv = ["--tylko-niezerowe"] if tylko_niezerowe else []
    return _uruchom("magazyn", argv, out, timeout).get("pozycje", [])


def zapisz_progi(plan, timeout=TIMEOUT_S):
    """Zapisuje progi do Subiekta. plan: [{symbol, min, opt}].
    Zwraca {zmienione, kroki:[{Symbol, Min, Opt, Status, Szczegoly}]}."""
    tmp = tempfile.mkdtemp(prefix="subiekt_progi_")
    plan_path = os.path.join(tmp, "plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False)
    return _uruchom("progi", [f"--plan={plan_path}", "--zapisz", f"--magazyn={MAGAZYN}"],
                    os.path.join(tmp, "wynik.json"), timeout)


def pobierz_katalog(timeout=TIMEOUT_S):
    """[{Id, Symbol, Nazwa, CenaEwidencyjna}] — WSZYSTKIE kartoteki Subiekta.

    Tryb „katalog" świadomie NIE czyta stanów — to najdroższa część odczytu
    (osobne zapytanie per kartoteka). Dzięki temu 3444 kartoteki wchodzą
    w ~9 s, czyli tyle, co sam start mostu; „magazyn" z pełnymi stanami dla
    794 pozycji ze stanem trwa 16 s.
    """
    out = os.path.join(tempfile.mkdtemp(prefix="subiekt_kat_"), "katalog.json")
    return _uruchom("katalog", [], out, timeout).get("pozycje", [])


def utworz_rw(pozycje, uwagi, magazyn=MAGAZYN, zapisz=True, timeout=TIMEOUT_S):
    """Rozchód wewnętrzny — zdejmuje towar ze stanu. pozycje: [{symbol, ilosc}].
    Zwraca {zapisano, numer, kroki}. zapisz=False = suchy przebieg."""
    tmp = tempfile.mkdtemp(prefix="subiekt_rw_")
    plan_path = os.path.join(tmp, "plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump({"pozycje": pozycje, "uwagi": uwagi, "magazyn": magazyn}, f, ensure_ascii=False)
    argv = [f"--plan={plan_path}"] + (["--zapisz"] if zapisz else [])
    return _uruchom("rw", argv, os.path.join(tmp, "wynik.json"), timeout)


def usun_kartoteki(symbole, zapisz=False, timeout=TIMEOUT_S):
    """Kasuje kartoteki z Subiekta. Zwraca {zapisano, usuniete, kroki}.
    Subiekt odmawia dla kartotek z dokumentami/stanem — most raportuje to
    per symbol po WERYFIKACJI (Usun() potrafi milczeć o odmowie)."""
    tmp = tempfile.mkdtemp(prefix="subiekt_ku_")
    argv = ["--symbole=" + ";".join(symbole)] + (["--zapisz"] if zapisz else [])
    return _uruchom("kartoteka-usun", argv, os.path.join(tmp, "wynik.json"), timeout)


def _liczba(tekst, domyslna=0.0):
    try:
        return float(str(tekst).replace(",", ".").strip() or 0)
    except (TypeError, ValueError):
        return domyslna


def _f(x):
    """Liczba do komórki: całkowite bez „.0", puste dla zera."""
    x = float(x or 0)
    if x == 0:
        return ""
    return f"{x:g}"


class MagazynWindow(tk.Toplevel, Kreciolek):
    KOLUMNY = [("sel", "✓", 30), ("symbol", "Symbol", 150), ("nazwa", "Nazwa", 260),
               ("rodzaj", "Rodzaj", 90), ("dostepne", "Dostępne", 78),
               ("zadysponowane", "Zadysp.", 70), ("zarezerwowane", "Rezerw.", 70),
               ("min", "Min", 60), ("opt", "Opt", 60), ("kupic", "Kupić", 64),
               ("dostawca", "Dostawca", 170), ("zd", "ZD", 120),
               ("cena", "Cena ewid.", 80), ("magazynow", "Mag.", 44)]
    (COL_SEL, COL_SYMBOL, COL_NAZWA, COL_RODZAJ, COL_DOSTEPNE, COL_ZADYSP, COL_REZERW,
     COL_MIN, COL_OPT, COL_KUPIC, COL_DOSTAWCA, COL_ZD, COL_CENA, COL_MAG) = range(14)
    EDYTOWALNE = (COL_MIN, COL_OPT, COL_KUPIC)
    KOL_MAG = [("magazyn", "Magazyn", 180), ("dostepne", "Dostępne", 110),
               ("zadysponowane", "Zadysponowane", 130)]

    def __init__(self, parent):
        super().__init__(parent)
        self.pozycje = []
        self.widoczne = []
        self.kontrahenci = None         # lista z Subiekta, ładowana przy pierwszym wyborze
        self.katalog = None             # wszystkie kartoteki, ładowane przy „Dodaj z katalogu"
        self._ostatni_klik = None

        self.title("Subiekt — magazyn: stany, progi, zamówienia na skład")
        self.geometry("1360x760")
        self.minsize(980, 480)
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
        tk.Label(top, text="📦 Magazyn — stany, progi min/opt, zamówienia na skład",
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
        tk.Entry(f, textvariable=self.var_szukaj, width=24,
                 font=("Arial", 9)).pack(side=tk.LEFT, pady=6)
        tk.Label(f, text="(symbol albo nazwa)", bg="#ecf0f1", fg="#7f8c8d",
                 font=("Arial", 8)).pack(side=tk.LEFT, padx=(4, 0))

        # Domyślny widok magazyniera: „co jest do domówienia". Przełącznik
        # ustawia się sam po wczytaniu — gdy żadna kartoteka nie ma progu,
        # lista „poniżej progu" byłaby pusta i wyglądałaby na zepsutą.
        self.var_ponizej = tk.IntVar(value=0)
        self.chk_ponizej = tk.Checkbutton(
            f, text="tylko poniżej progu (do domówienia)", variable=self.var_ponizej,
            command=self._odswiez_liste, bg="#ecf0f1", font=("Arial", 9, "bold"),
            fg="#a04000", activebackground="#ecf0f1")
        self.chk_ponizej.pack(side=tk.LEFT, padx=(16, 0), pady=6)

        # ⚠️ ŚWIADOMIE BEZ przełącznika „pokaż też bez stanu". Most pyta Subiekta
        # o stany, zakresy i dostawców OSOBNO dla każdej kartoteki — przy 794
        # ze stanem to ~15 s, ale przy wszystkich 3442 okno wisiało minutami
        # (zgłoszone 05.09.2026). Kartoteka bez stanu i bez progu nie jest
        # niczym, co magazynier domawia; gdy trzeba zamówić coś nowego, wpisuje
        # to przyciskiem „Dodaj pozycję spoza listy".
        tk.Button(f, text="➕ Dodaj z katalogu…", command=self._dodaj_reczna,
                  bg="#27ae60", fg="white", font=("Arial", 8), padx=8, pady=2,
                  relief=tk.RAISED, bd=1).pack(side=tk.LEFT, padx=(14, 0), pady=6)

        leg = tk.Frame(self, bg="#ecf0f1")
        leg.pack(side=tk.TOP, fill=tk.X)
        tk.Label(leg, text="Edycja wprost w tabeli: Min, Opt, Kupić.  DWUKLIK w Dostawcę = wybór "
                           "z listy Subiekta.  Klik w ✓ zaznacza (Shift = zakres).",
                 bg="#ecf0f1", fg="#7f8c8d", font=("Arial", 8), anchor="w",
                 padx=12).pack(side=tk.LEFT, pady=(0, 2))
        # Legenda nazywa KOLUMNY, nie abstrakcyjne stany — inaczej trzeba
        # zgadywać, do której liczby odnosi się dany kolor.
        for kolor, opis in (("#fadbd8", "Dostępne — poniżej progu"),
                            ("#eaeded", "Min / Opt — próg zamawiania"),
                            ("#e74c3c", "Kupić — tyle brakuje"),
                            ("#f9e79f", "próg zmieniony — do zapisu"),
                            ("#aed6f1", "ZD — jest już zamówienie")):
            tk.Label(leg, text="  ", bg=kolor, relief=tk.SOLID, bd=1).pack(side=tk.LEFT, padx=(10, 2))
            tk.Label(leg, text=opis, bg="#ecf0f1", fg="#7f8c8d",
                     font=("Arial", 8)).pack(side=tk.LEFT)

        self.podsumowanie = tk.Label(self, text="Wczytywanie…", bg="#ecf0f1",
                                     fg="#2c3e50", font=("Arial", 9), anchor="w",
                                     padx=12, pady=6)
        self.podsumowanie.pack(side=tk.TOP, fill=tk.X)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        bottom = tk.Frame(self)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 6))
        self.btn_zd = tk.Button(bottom, text="🛒 Utwórz ZD na magazyn (0)",
                                command=self._utworz_zd, bg="#8e44ad", fg="white",
                                font=("Arial", 9, "bold"), padx=14, pady=5,
                                relief=tk.RAISED, bd=2, state=tk.DISABLED)
        self.btn_zd.pack(side=tk.RIGHT)
        self.btn_progi = tk.Button(bottom, text="💾 Zapisz progi (0)",
                                   command=self._zapisz_progi, bg="#27ae60", fg="white",
                                   font=("Arial", 9, "bold"), padx=12, pady=5,
                                   relief=tk.RAISED, bd=2, state=tk.DISABLED)
        self.btn_progi.pack(side=tk.RIGHT, padx=(0, 8))
        tk.Button(bottom, text="Dostawca dla zaznaczonych…",
                  command=self._dostawca_dla_zaznaczonych, font=("Arial", 9),
                  padx=10, pady=5, relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=(0, 8))
        # Dwie RÓŻNE operacje, świadomie osobno i w innych kolorach:
        #   RW  — zdejmij towar ze stanu, kartoteka i historia zostają,
        #   usuń — skasuj indeks; Subiekt pozwala tylko bez żadnej historii.
        tk.Button(bottom, text="📤 Zdejmij ze stanu (RW)…", command=self._zdejmij_rw,
                  bg="#d35400", fg="white", font=("Arial", 9, "bold"), padx=10, pady=5,
                  relief=tk.RAISED, bd=2).pack(side=tk.RIGHT, padx=(0, 8))
        tk.Button(bottom, text="🗑 Usuń kartoteki z Subiekta…", command=self._usun_kartoteki,
                  bg="#7f8c8d", fg="white", font=("Arial", 9), padx=10, pady=5,
                  relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=(0, 8))
        tk.Label(bottom, text="ZD na skład dostaje w Uwagach „MAGAZYN” — bez projektu, "
                              "nie miesza się z zapotrzebowaniem ZK.",
                 fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.LEFT)

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
            "rc_select", "copy", "edit_cell",
        ))
        # Edytowalne tylko Min / Opt / Kupić — reszta to odczyt z Subiekta.
        try:
            self.sheet.readonly_columns(
                columns=[i for i in range(len(self.KOLUMNY)) if i not in self.EDYTOWALNE])
        except Exception:
            pass
        podepnij_szerokosci(self, self.sheet, "magazyn", [k[2] for k in self.KOLUMNY])
        self.sheet.extra_bindings("cell_select", self._wybor_pozycji)
        self.sheet.extra_bindings("row_select", self._wybor_pozycji)
        self.sheet.bind("<<SheetModified>>", self._on_edit)
        self.sheet.bind("<ButtonRelease-1>", self._on_click, add="+")
        self.sheet.bind("<Double-Button-1>", self._on_dblclick, add="+")
        self.sheet.popup_menu_add_command("☑ Zaznacz wiersze", lambda: self._zaznacz_wybrane(True))
        self.sheet.popup_menu_add_command("☐ Odznacz wiersze", lambda: self._zaznacz_wybrane(False))
        self.sheet.popup_menu_add_command("Ustaw dostawcę dla wierszy…",
                                          self._dostawca_dla_wybranych_wierszy)
        self.sheet.pack(fill=tk.BOTH, expand=True)
        self._podepnij_tooltip()

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
        self.start_kreciolek("Czytam stany, progi i otwarte ZD z Subiekta (~15 s)")
        threading.Thread(target=self._wczytaj_worker, daemon=True).start()

    def _wczytaj_worker(self):
        try:
            poz = pobierz_magazyn(tylko_niezerowe=True)
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._wczytaj_done(None, err))
            return
        # Numery ZD przychodzą RAZEM ze stanami (tryb „magazyn" zwraca je
        # w polu Zd) — osobne wywołanie mostu kosztowało drugie ~10 s na sam
        # start Sfery, więcej niż cały odczyt stanów.
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

        # Odświeżenie NIE może kasować pracy użytkownika: niezapisane progi,
        # ręczny dostawca i zaznaczenia przeżywają przeładowanie (ta sama
        # zasada co w oknie zamówień).
        poprzednie = {p["Symbol"].strip().upper(): p for p in self.pozycje}
        nowe = []
        for p in poz or []:
            p["min"] = float(p.get("StanMinimalny") or 0)
            p["opt"] = float(p.get("StanOptymalny") or 0)
            p["min_subiekt"], p["opt_subiekt"] = p["min"], p["opt"]
            p["dostawca"] = (p.get("Dostawca") or "").strip()
            p["sel"] = False
            # Numer z Subiekta (pole Zd z mostu) ma pierwszeństwo nad tym,
            # co okno zapamiętało po własnym zamówieniu.
            p["zd"] = (p.get("Zd") or "").strip()
            p["kupic_reczne"] = False
            stare = poprzednie.get(p["Symbol"].strip().upper())
            if stare:
                if stare.get("prog_zmieniony"):
                    p["min"], p["opt"] = stare["min"], stare["opt"]
                if stare.get("dostawca"):
                    p["dostawca"] = stare["dostawca"]
                p["sel"] = stare.get("sel", False)
                if not p["zd"]:
                    p["zd"] = stare.get("zd", "")
                if stare.get("kupic_reczne"):
                    p["kupic"], p["kupic_reczne"] = stare["kupic"], True
            self._przelicz_kupic(p)
            nowe.append(p)
        self.pozycje = nowe
        self.zaznacz_odczyt(self.lbl_wiek)

        # Filtr „poniżej progu" włącza się sam, gdy jest co pokazać.
        if not poprzednie:
            self.var_ponizej.set(1 if any(self._ponizej(p) for p in self.pozycje) else 0)
        self._odswiez_liste()

    # ── model ──────────────────────────────────────────────────────────────
    @staticmethod
    def _ponizej(p):
        return p["min"] > 0 and float(p.get("Dostepne") or 0) <= p["min"]

    def _przelicz_kupic(self, p):
        """Kupić = optymalny − stan, gdy stan spadł do minimum. Ręczny wpis
        użytkownika ma pierwszeństwo, dopóki nie zmieni progu."""
        p["prog_zmieniony"] = (p["min"] != p["min_subiekt"] or p["opt"] != p["opt_subiekt"])
        if p.get("kupic_reczne"):
            return
        if self._ponizej(p):
            cel = p["opt"] if p["opt"] > 0 else p["min"]
            p["kupic"] = max(0.0, cel - float(p.get("Dostepne") or 0))
        else:
            p["kupic"] = 0.0

    # ── lista ──────────────────────────────────────────────────────────────
    def _odswiez_liste(self):
        if not self.sheet:
            return
        szukaj = (self.var_szukaj.get() or "").strip().lower()
        self.widoczne = [
            p for p in self.pozycje
            if (not szukaj
                or szukaj in str(p.get("Symbol", "")).lower()
                or szukaj in str(p.get("Nazwa", "")).lower())
            and (not self.var_ponizej.get() or self._ponizej(p) or p.get("prog_zmieniony"))
        ]
        self.sheet.set_sheet_data([[
            "✓" if p["sel"] else "☐",
            p.get("Symbol", ""), p.get("Nazwa", ""), p.get("Rodzaj") or "",
            f"{p.get('Dostepne', 0):g}", _f(p.get("Zadysponowane")), _f(p.get("Zarezerwowane")),
            _f(p["min"]), _f(p["opt"]), _f(p.get("kupic")),
            p["dostawca"], p["zd"],
            f"{p.get('CenaEwidencyjna', 0):g}", str(len(p.get("Magazyny") or [])),
        ] for p in self.widoczne], reset_col_positions=False, redraw=False)

        try:
            self.sheet.dehighlight_all()
        except Exception:
            pass
        for i, p in enumerate(self.widoczne):
            # ZD koloruje TYLKO swoją kolumnę. Wcześniej brało cały wiersz
            # i zasłaniało pomarańczowe „poniżej progu" na ilościach —
            # a to one mówią, ile brakuje (zgłoszone 05.09.2026). Obie
            # informacje są potrzebne naraz: „mało" i „już zamówione".
            # KOLORY MUSZĄ SIĘ RÓŻNIĆ NA PIERWSZY RZUT OKA. Pierwsza wersja
            # dawała blady pomarańcz na ilościach i blady błękit na ZD —
            # o zbliżonej jasności, więc zlewały się w jedno pasmo
            # (zgłoszone 05.09.2026). Teraz: BRAK = czerwony, ZAMÓWIONE =
            # zielony, czyli ten sam język co „stop / załatwione".
            # ZD na NIEBIESKO. Zielony rezerwujemy dla zrealizowanych dostaw —
            # „zamówione" i „przyjęte" to dwa różne stany i nie mogą wyglądać
            # tak samo (zgłoszone 05.09.2026).
            if p["zd"]:
                self.sheet.highlight_cells(row=i, column=self.COL_ZD,
                                           bg="#aed6f1", fg="#1b4f72")
            if self._ponizej(p):
                # Trzy różne role, trzy różne kolory:
                #   Dostępne — CO MAM (czerwone, bo za mało),
                #   Min/Opt  — PRÓG, wartość odniesienia (szare, spokojne),
                #   Kupić    — DO DZIAŁANIA (pełny czerwony).
                # Wcześniej wszystkie trzy były tym samym różem i zlewały się.
                self.sheet.highlight_cells(row=i, column=self.COL_DOSTEPNE,
                                           bg="#fadbd8", fg="#922b21")
                for c in (self.COL_MIN, self.COL_OPT):
                    self.sheet.highlight_cells(row=i, column=c, bg="#eaeded", fg="#566573")
                self.sheet.highlight_cells(row=i, column=self.COL_KUPIC,
                                           bg="#e74c3c", fg="white")
            if p.get("prog_zmieniony"):
                for c in (self.COL_MIN, self.COL_OPT):
                    self.sheet.highlight_cells(row=i, column=c, bg="#f9e79f", fg="#7d6608")
            if p["sel"] and not p["dostawca"]:
                self.sheet.highlight_cells(row=i, column=self.COL_DOSTAWCA, bg="#fdedec")
        self.sheet.redraw()

        self._przelicz_podsumowanie()
        if self.sheet_mag:
            self.sheet_mag.set_sheet_data([], reset_col_positions=False)

    def _przelicz_podsumowanie(self):
        ponizej = sum(1 for p in self.pozycje if self._ponizej(p))
        do_zapisu = sum(1 for p in self.pozycje if p.get("prog_zmieniony"))
        zazn = sum(1 for p in self.pozycje if p["sel"])
        bez_dost = sum(1 for p in self.pozycje if p["sel"] and not p["dostawca"])
        wartosc = sum(float(p.get("Dostepne") or 0) * float(p.get("CenaEwidencyjna") or 0)
                      for p in self.widoczne)
        self.podsumowanie.config(
            text=f"Pozycji: {len(self.widoczne)} z {len(self.pozycje)} "
                 f"(kartoteki ze stanem albo z progiem)    "
                 f"poniżej progu: {ponizej}    zaznaczonych: {zazn}"
                 + (f"  (bez dostawcy: {bez_dost})" if bez_dost else "")
                 + f"    wartość widocznych wg ceny ewid.: {wartosc:,.2f} zł".replace(",", " "))
        try:
            self.btn_progi.config(text=f"💾 Zapisz progi ({do_zapisu})",
                                  state=tk.NORMAL if do_zapisu else tk.DISABLED)
            self.btn_zd.config(text=f"🛒 Utwórz ZD na magazyn ({zazn})",
                               state=tk.NORMAL if zazn else tk.DISABLED)
        except tk.TclError:
            pass

    # ── edycja ─────────────────────────────────────────────────────────────
    def _on_edit(self, _event=None):
        """Min / Opt / Kupić z tabeli wracają do modelu."""
        if not self.sheet:
            return
        try:
            dane = self.sheet.get_sheet_data()
        except Exception:
            return
        for i, p in enumerate(self.widoczne):
            if i >= len(dane):
                break
            n_min = _liczba(dane[i][self.COL_MIN], p["min"])
            n_opt = _liczba(dane[i][self.COL_OPT], p["opt"])
            n_kup = _liczba(dane[i][self.COL_KUPIC], p.get("kupic", 0))
            if n_min != p["min"] or n_opt != p["opt"]:
                p["min"], p["opt"] = n_min, n_opt
                p["kupic_reczne"] = False       # nowy próg = nowe wyliczenie
            elif n_kup != float(p.get("kupic") or 0):
                p["kupic"], p["kupic_reczne"] = n_kup, True
            self._przelicz_kupic(p)
        self._odswiez_liste()

    def _on_click(self, event):
        """Klik w ✓ przełącza wiersz; Shift+klik cały zakres (jak w zamówieniach)."""
        if not self.sheet or event.state & 0x0004:
            return
        shift = bool(event.state & 0x0001)
        try:
            r = self.sheet.identify_row(event, allow_end=False)
            c = self.sheet.identify_column(event, allow_end=False)
        except Exception:
            return
        if r is None or c != self.COL_SEL or not (0 <= r < len(self.widoczne)):
            return
        if shift and self._ostatni_klik is not None:
            od, do = sorted((self._ostatni_klik, r))
            stan = not self.widoczne[r]["sel"]
            for i in range(od, min(do, len(self.widoczne) - 1) + 1):
                self.widoczne[i]["sel"] = stan
        else:
            self.widoczne[r]["sel"] = not self.widoczne[r]["sel"]
        self._ostatni_klik = r
        self._odswiez_liste()

    def _on_dblclick(self, event):
        """Dwuklik w Dostawcę → wybór z listy podmiotów Subiekta."""
        if not self.sheet:
            return
        try:
            r = self.sheet.identify_row(event, allow_end=False)
            c = self.sheet.identify_column(event, allow_end=False)
        except Exception:
            return
        if r is None or c != self.COL_DOSTAWCA or not (0 <= r < len(self.widoczne)):
            return
        self._wybierz_dostawce([self.widoczne[r]])

    def _zaznacz_wybrane(self, stan):
        try:
            rows = self.sheet.get_selected_rows(get_cells_as_rows=True)
        except Exception:
            rows = []
        for r in rows:
            if 0 <= r < len(self.widoczne):
                self.widoczne[r]["sel"] = stan
        self._odswiez_liste()

    def _dostawca_dla_wybranych_wierszy(self):
        try:
            rows = self.sheet.get_selected_rows(get_cells_as_rows=True)
        except Exception:
            rows = []
        poz = [self.widoczne[r] for r in rows if 0 <= r < len(self.widoczne)]
        if poz:
            self._wybierz_dostawce(poz)

    def _dostawca_dla_zaznaczonych(self):
        poz = [p for p in self.pozycje if p["sel"]]
        if not poz:
            messagebox.showinfo("Dostawca", "Najpierw zaznacz ✓ pozycje.", parent=self)
            return
        self._wybierz_dostawce(poz)

    # ── wybór dostawcy ─────────────────────────────────────────────────────
    def _wybierz_dostawce(self, pozycje):
        """Okno z wyszukiwarką po podmiotach Subiekta (bywa ich ~600).

        Listę kontrahentów bierzemy z mostu przy PIERWSZYM użyciu i trzymamy
        w oknie — to drugi odczyt (~10 s), nie ma sensu robić go przy otwarciu,
        skoro większość wejść tu to tylko przegląd stanów.
        """
        if self.kontrahenci is None:
            self.start_kreciolek("Pobieram listę kontrahentów z Subiekta (~10 s)")

            def worker():
                try:
                    from subiekt_dostawcy import pobierz_kontrahentow
                    lista = pobierz_kontrahentow()
                except Exception as e:
                    err = str(e)
                    self.after(0, lambda: self._kontrahenci_done(None, err, pozycje))
                    return
                self.after(0, lambda: self._kontrahenci_done(lista, None, pozycje))
            threading.Thread(target=worker, daemon=True).start()
            return
        self._okno_dostawcy(pozycje)

    def _kontrahenci_done(self, lista, error, pozycje):
        self.stop_kreciolek()
        if error:
            messagebox.showerror("Kontrahenci", error, parent=self)
            return
        self.kontrahenci = sorted({(k.get("nazwa") or "").strip() for k in lista} - {""})
        self._okno_dostawcy(pozycje)

    def _okno_dostawcy(self, pozycje):
        dlg = tk.Toplevel(self)
        dlg.title(f"Dostawca dla {len(pozycje)} pozycji")
        dlg.transient(self)
        dlg.grab_set()
        wysrodkuj(dlg, self, 520, 430)
        tk.Label(dlg, text="Szukaj kontrahenta:", font=("Arial", 9)).pack(
            padx=14, pady=(12, 2), anchor="w")
        var = tk.StringVar()
        ent = tk.Entry(dlg, textvariable=var, font=("Arial", 10))
        ent.pack(fill=tk.X, padx=14)
        ent.focus_set()
        lb = tk.Listbox(dlg, font=("Arial", 9), activestyle="dotbox")
        lb.pack(fill=tk.BOTH, expand=True, padx=14, pady=8)

        def odswiez(*_):
            t = var.get().strip().lower()
            lb.delete(0, tk.END)
            for n in self.kontrahenci:
                if not t or t in n.lower():
                    lb.insert(tk.END, n)
            if lb.size():
                lb.selection_set(0)
        var.trace_add("write", odswiez)
        odswiez()

        def zastosuj(*_):
            sel = lb.curselection()
            if not sel:
                return
            nazwa = lb.get(sel[0])
            for p in pozycje:
                p["dostawca"] = nazwa
            dlg.destroy()
            self._odswiez_liste()
            self.status.config(text=f"Dostawca „{nazwa}” ustawiony dla {len(pozycje)} poz.")

        def wyczysc():
            for p in pozycje:
                p["dostawca"] = ""
            dlg.destroy()
            self._odswiez_liste()

        lb.bind("<Double-Button-1>", zastosuj)
        ent.bind("<Return>", zastosuj)
        stopka = tk.Frame(dlg)
        stopka.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=(0, 10))
        tk.Button(stopka, text="Wybierz", command=zastosuj, bg="#2980b9", fg="white",
                  font=("Arial", 9, "bold"), padx=14, pady=4).pack(side=tk.RIGHT)
        tk.Button(stopka, text="Wyczyść", command=wyczysc, font=("Arial", 9),
                  padx=10, pady=4).pack(side=tk.RIGHT, padx=6)
        tk.Button(stopka, text="Anuluj", command=dlg.destroy, font=("Arial", 9),
                  padx=10, pady=4).pack(side=tk.RIGHT)

    def _dodaj_reczna(self):
        """Przeglądarka WSZYSTKICH kartotek Subiekta z wyszukiwarką.

        Lista główna pokazuje tylko kartoteki ze stanem albo z progiem (794
        z 3444) — reszta to indeksy bez ruchu, a odczyt ich stanów trwałby
        minutami. Domówić trzeba jednak czasem rzecz, której akurat nie ma na
        stanie, więc katalog jest tutaj: bez stanów, za to cały i szybki (~9 s).
        """
        if self.katalog is None:
            self.start_kreciolek("Czytam katalog kartotek z Subiekta (~9 s)")

            def worker():
                try:
                    lista = pobierz_katalog()
                except Exception as e:
                    err = str(e)
                    self.after(0, lambda: self._katalog_done(None, err))
                    return
                self.after(0, lambda: self._katalog_done(lista, None))
            threading.Thread(target=worker, daemon=True).start()
            return
        self._okno_katalogu()

    def _katalog_done(self, lista, error):
        self.stop_kreciolek()
        if error:
            messagebox.showerror("Katalog", error, parent=self)
            return
        self.katalog = lista or []
        self._okno_katalogu()

    def _okno_katalogu(self):
        dlg = tk.Toplevel(self)
        dlg.title("Katalog kartotek Subiekta — wybierz pozycje do zamówienia")
        dlg.transient(self)
        dlg.grab_set()
        wysrodkuj(dlg, self, 900, 620)

        gora = tk.Frame(dlg, bg="#ecf0f1")
        gora.pack(side=tk.TOP, fill=tk.X)
        tk.Label(gora, text="Szukaj:", bg="#ecf0f1",
                 font=("Arial", 9)).pack(side=tk.LEFT, padx=(12, 3), pady=8)
        var = tk.StringVar()
        ent = tk.Entry(gora, textvariable=var, width=34, font=("Arial", 10))
        ent.pack(side=tk.LEFT, pady=8)
        ent.focus_set()
        lbl_ile = tk.Label(gora, text="", bg="#ecf0f1", fg="#7f8c8d", font=("Arial", 8))
        lbl_ile.pack(side=tk.LEFT, padx=(10, 0))
        tk.Label(gora, text="(symbol albo nazwa; Enter dodaje zaznaczone)",
                 bg="#ecf0f1", fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.LEFT, padx=(10, 0))

        ramka = tk.Frame(dlg)
        ramka.pack(fill=tk.BOTH, expand=True, padx=10, pady=(6, 0))
        # Listbox, nie tksheet: tu nie ma czego edytować ani kolorować, a lista
        # bywa długa — Listbox z EXTENDED radzi sobie z tym bez kombinowania.
        scroll = tk.Scrollbar(ramka)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        lb = tk.Listbox(ramka, font=("Consolas", 9), activestyle="dotbox",
                        selectmode=tk.EXTENDED, yscrollcommand=scroll.set)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=lb.yview)

        # Symbole już na liście głównej — nie ma sensu dodawać ich drugi raz.
        juz = {p["Symbol"].strip().upper() for p in self.pozycje}
        widoczne = []

        def odswiez(*_):
            t = var.get().strip().lower()
            lb.delete(0, tk.END)
            widoczne.clear()
            for k in self.katalog:
                sym = (k.get("Symbol") or "").strip()
                naz = (k.get("Nazwa") or "").strip()
                if t and t not in sym.lower() and t not in naz.lower():
                    continue
                widoczne.append(k)
                znacznik = "✓ " if sym.upper() in juz else "  "
                lb.insert(tk.END, f"{znacznik}{sym:<28} {naz[:60]}")
            lbl_ile.config(text=f"{len(widoczne)} z {len(self.katalog)}")
            if lb.size():
                lb.selection_set(0)

        var.trace_add("write", odswiez)
        odswiez()

        def dodaj(*_):
            wybrane = [widoczne[i] for i in lb.curselection() if i < len(widoczne)]
            if not wybrane:
                return
            dodane, pominiete = 0, 0
            for k in wybrane:
                sym = (k.get("Symbol") or "").strip()
                if not sym or sym.upper() in juz:
                    pominiete += 1
                    continue
                juz.add(sym.upper())
                self.pozycje.insert(0, {
                    "Symbol": sym, "Nazwa": (k.get("Nazwa") or "").strip(),
                    "Rodzaj": "", "Dostepne": 0, "Zadysponowane": 0, "Zarezerwowane": 0,
                    "CenaEwidencyjna": float(k.get("CenaEwidencyjna") or 0),
                    "Magazyny": [], "min": 0.0, "opt": 0.0,
                    "min_subiekt": 0.0, "opt_subiekt": 0.0,
                    "dostawca": "", "sel": True, "zd": "", "kupic": 1.0,
                    "kupic_reczne": True, "prog_zmieniony": False,
                })
                dodane += 1
            dlg.destroy()
            # Dodane pozycje nie mają progu, więc filtr „poniżej progu" by je ukrył.
            self.var_ponizej.set(0)
            self.var_szukaj.set("")
            self._odswiez_liste()
            self.status.config(
                text=f"Dodano {dodane} poz. z katalogu — ustaw ilość w kolumnie Kupić "
                     f"i dostawcę." + (f"  ({pominiete} już było na liście)" if pominiete else ""))

        lb.bind("<Double-Button-1>", dodaj)
        ent.bind("<Return>", dodaj)
        lb.bind("<Return>", dodaj)

        stopka = tk.Frame(dlg)
        stopka.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        tk.Label(stopka, text="✓ na początku wiersza = ta pozycja jest już na głównej "
                              "liście magazynu (nie doda się drugi raz)",
                 fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.LEFT)
        tk.Button(stopka, text="Dodaj zaznaczone", command=dodaj, bg="#27ae60", fg="white",
                  font=("Arial", 9, "bold"), padx=14, pady=4).pack(side=tk.RIGHT)
        tk.Button(stopka, text="Anuluj", command=dlg.destroy, font=("Arial", 9),
                  padx=10, pady=4).pack(side=tk.RIGHT, padx=6)

    # ── zapis progów ───────────────────────────────────────────────────────
    def _zapisz_progi(self):
        zmienione = [p for p in self.pozycje if p.get("prog_zmieniony")]
        if not zmienione:
            return
        zle = [p["Symbol"] for p in zmienione if p["opt"] > 0 and p["opt"] < p["min"]]
        if zle:
            messagebox.showwarning(
                "Progi", "Optymalny nie może być mniejszy od minimalnego:\n\n"
                + "\n".join(f"  • {s}" for s in zle[:10]), parent=self)
            return
        if not messagebox.askyesno(
                "Zapis progów — potwierdzenie",
                f"Baza PRODUKCYJNA Subiekta.\n\nZapisać progi min/opt dla "
                f"{len(zmienione)} kartotek (magazyn {MAGAZYN})?\n\n"
                "Zero w Min znaczy „nie pilnuj” — tak kasuje się próg.",
                parent=self, icon="warning"):
            return
        plan = [{"symbol": p["Symbol"], "min": p["min"], "opt": p["opt"]} for p in zmienione]
        self.btn_progi.config(state=tk.DISABLED)
        self.start_kreciolek(f"Zapisuję progi {len(plan)} kartotek w Subiekcie (~10 s)")
        threading.Thread(target=self._progi_worker, args=(plan,), daemon=True).start()

    def _progi_worker(self, plan):
        try:
            wynik = zapisz_progi(plan)
            self.after(0, lambda: self._progi_done(wynik, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._progi_done(None, err))

    def _progi_done(self, wynik, error):
        self.stop_kreciolek()
        if error:
            self.status.config(text="Nie udało się zapisać progów.")
            messagebox.showerror("Progi", error, parent=self)
            self._przelicz_podsumowanie()
            return
        kroki = wynik.get("kroki", [])
        ok = {k["Symbol"].strip().upper() for k in kroki if k.get("Status") == "zmieniono"}
        bledy = [k for k in kroki if k.get("Status") == "blad"]
        for p in self.pozycje:
            if p["Symbol"].strip().upper() in ok:
                p["min_subiekt"], p["opt_subiekt"] = p["min"], p["opt"]
                p["prog_zmieniony"] = False
        self._odswiez_liste()
        tekst = f"Zapisano progi: {len(ok)}"
        if bledy:
            tekst += f"\n\nBłędy ({len(bledy)}):\n" + "\n".join(
                f"  • {b.get('Symbol')}: {b.get('Szczegoly')}" for b in bledy[:8])
        (messagebox.showwarning if bledy else messagebox.showinfo)("Progi", tekst, parent=self)
        self.status.config(text=f"Zapisano progi {len(ok)} kartotek.")

    # ── ZD na magazyn ──────────────────────────────────────────────────────
    def _utworz_zd(self):
        zazn = [p for p in self.pozycje if p["sel"]]
        if not zazn:
            return
        bez_ilosci = [p["Symbol"] for p in zazn if float(p.get("kupic") or 0) <= 0]
        if bez_ilosci:
            messagebox.showwarning(
                "ZD", "Te pozycje mają „Kupić” = 0 — wpisz ilość albo odznacz:\n\n"
                + "\n".join(f"  • {s}" for s in bez_ilosci[:10]), parent=self)
            return
        bez_dost = [p["Symbol"] for p in zazn if not p["dostawca"]]
        if bez_dost:
            messagebox.showwarning(
                "ZD", "Te pozycje nie mają dostawcy (dwuklik w kolumnę Dostawca):\n\n"
                + "\n".join(f"  • {s}" for s in bez_dost[:10]), parent=self)
            return
        dostawcy = sorted({p["dostawca"] for p in zazn})
        if not messagebox.askyesno(
                "Utworzenie ZD na magazyn — potwierdzenie",
                f"Baza PRODUKCYJNA.\n\nPowstanie {len(dostawcy)} zamówień do dostawców "
                f"(Uwagi: {UWAGI_MAGAZYN}):\n"
                + "\n".join(f"  • {d}: {sum(1 for p in zazn if p['dostawca'] == d)} poz."
                            for d in dostawcy[:10])
                + f"\n\nŁącznie pozycji: {len(zazn)}\n\nUtworzyć?",
                parent=self, icon="warning"):
            return
        # reczna=True: nie ma za tym żadnej ZK, most dopisuje pozycje wprost.
        poz = [{"symbol": p["Symbol"], "ilosc": float(p["kupic"]),
                "dostawca": p["dostawca"], "reczna": True} for p in zazn]
        self.btn_zd.config(state=tk.DISABLED)
        self.start_kreciolek("Tworzę ZD w Subiekcie — nie zamykaj okna…")
        threading.Thread(target=self._zd_worker, args=(poz,), daemon=True).start()

    def _zd_worker(self, pozycje):
        try:
            from subiekt_zamowienia import utworz_zd, zapisz_log
            wynik = utworz_zd(pozycje, uwagi=UWAGI_MAGAZYN)
            try:
                wynik["_log"] = zapisz_log(wynik)
            except Exception:
                wynik["_log"] = None
            self.after(0, lambda: self._zd_done(wynik, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._zd_done(None, err))

    def _zd_done(self, wynik, error):
        self.stop_kreciolek()
        if error:
            self.status.config(text="Nie udało się utworzyć ZD.")
            messagebox.showerror("ZD", error, parent=self)
            self._przelicz_podsumowanie()
            return
        utworzone = wynik.get("zd", [])
        bledy = [k for k in wynik.get("kroki", []) if k.get("Status") == "blad"]
        po_dostawcy = {(z.get("Dostawca") or "").strip(): z.get("Numer", "")
                       for z in utworzone}
        for p in self.pozycje:
            if p["sel"] and po_dostawcy.get(p["dostawca"].strip()):
                p["zd"] = po_dostawcy[p["dostawca"].strip()]
                p["sel"] = False
        self._odswiez_liste()
        lines = [f"Utworzone ZD: {len(utworzone)}"]
        lines += [f"  • {z.get('Numer', '?')} — {z.get('Dostawca', '?')}" for z in utworzone[:12]]
        if bledy:
            lines += ["", f"Błędy ({len(bledy)}):"]
            lines += [f"  • {b.get('Symbol', '')}: {b.get('Szczegoly', '')}" for b in bledy[:8]]
        if wynik.get("_log"):
            lines += ["", f"Log: {wynik['_log']}"]
        (messagebox.showwarning if bledy else messagebox.showinfo)(
            "ZD utworzone", "\n".join(lines), parent=self)
        self.status.config(text=f"Utworzono {len(utworzone)} ZD na magazyn. "
                                "Wyślij je dostawcom z okna Przegląd dokumentów.")

    # ── zdjęcie ze stanu (RW) ──────────────────────────────────────────────
    def _zdejmij_rw(self):
        """Rozchód wewnętrzny dla zaznaczonych pozycji.

        Ilość domyślnie = cały stan („nie ma tego już na półce"), do poprawienia
        per pozycja. Powód wpisywany raz trafia do Uwag dokumentu — to on
        odróżnia „zużyte" od „uszkodzone" za pół roku, gdy ktoś spyta, gdzie
        się podziało 30 obejm. Stan w Subiekcie schodzi, kartoteka zostaje.
        """
        wszystkie_zazn = [p for p in self.pozycje if p["sel"]]
        if not wszystkie_zazn:
            messagebox.showinfo("RW", "Najpierw zaznacz ✓ pozycje do zdjęcia ze stanu.", parent=self)
            return
        zazn = [p for p in wszystkie_zazn if float(p.get("Dostepne") or 0) > 0]
        bez_stanu = [p["Symbol"] for p in wszystkie_zazn if p not in zazn]
        if bez_stanu:
            # Wcześniej pomijaliśmy je po cichu — przy jednej zaznaczonej
            # pozycji okno mówiło ogólnikowo "zaznacz to, co ma stan" i nie
            # było jasne, KTÓRĄ pozycję odrzucono ani dlaczego (zgłoszone
            # 05.09.2026). Teraz mówimy wprost, po symbolu.
            messagebox.showinfo(
                "RW", "Te zaznaczone pozycje mają stan 0 — nie ma czego zdjąć, pomijam je:"
                + NL + NL.join(f"  • {s}" for s in bez_stanu[:10]),
                parent=self)
        if not zazn:
            return

        dlg = tk.Toplevel(self)
        dlg.title(f"Zdejmij ze stanu — RW dla {len(zazn)} pozycji")
        dlg.transient(self); dlg.grab_set()
        dlg.minsize(560, 360)
        # Wysokość STAŁA, nie zależna od liczby pozycji — poprzednia wersja
        # liczyła ją z len(zazn) i przy 1-2 pozycjach wychodziła za niska na
        # cały układ (nagłówek + lista + pole powodu + stopka), więc przyciski
        # na dole były obcięte (zgłoszone 05.09.2026). Lista przy wielu
        # pozycjach i tak przewija się w środku — okno nie musi rosnąć.
        wysrodkuj(dlg, self, 640, 520)

        # Stopka i pole powodu PAKOWANE JAKO PIERWSZE od dołu — dopiero potem
        # rozciągliwa lista (expand=True) zajmuje to, co zostało. W innej
        # kolejności rozciągliwy element zabierał miejsce stopce.
        stopka = tk.Frame(dlg); stopka.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=10)
        tk.Button(stopka, text="Anuluj", command=dlg.destroy, font=("Arial", 9),
                  padx=10, pady=4).pack(side=tk.RIGHT, padx=6)
        # command podpięty niżej, gdy `wykonaj` już istnieje (definicja w dalszej
        # części funkcji) — przycisk trzymamy w zmiennej i łączymy na końcu.
        btn_wykonaj = tk.Button(stopka, text="Wystaw RW", bg="#d35400", fg="white",
                                font=("Arial", 9, "bold"), padx=14, pady=4)
        btn_wykonaj.pack(side=tk.RIGHT)

        blok_powodu = tk.Frame(dlg); blok_powodu.pack(side=tk.BOTTOM, fill=tk.X, padx=14)
        tk.Label(blok_powodu, text="Powód (trafi do Uwag dokumentu):",
                 font=("Arial", 9)).pack(pady=(8, 2), anchor="w")
        var_powod = tk.StringVar(value="zużyte na produkcji")
        tk.Entry(blok_powodu, textvariable=var_powod, font=("Arial", 9)).pack(fill=tk.X)

        tk.Label(dlg, text="Ile zdjąć ze stanu (domyślnie cały stan):",
                 font=("Arial", 9, "bold")).pack(padx=14, pady=(12, 4), anchor="w")

        ramka = tk.Frame(dlg); ramka.pack(fill=tk.BOTH, expand=True, padx=14)
        canvas = tk.Canvas(ramka, highlightthickness=0)
        sb = tk.Scrollbar(ramka, command=canvas.yview)
        wn = tk.Frame(canvas)
        wn.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=wn, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); sb.pack(side=tk.RIGHT, fill=tk.Y)

        pola = []
        for i, p in enumerate(zazn):
            stan = float(p.get("Dostepne") or 0)
            tk.Label(wn, text=f"{p['Symbol']}  {p.get('Nazwa', '')[:40]}", font=("Arial", 9),
                     anchor="w", width=52).grid(row=i, column=0, sticky="w", pady=1)
            tk.Label(wn, text=f"stan {stan:g}", fg="#7f8c8d", font=("Arial", 8)).grid(row=i, column=1, padx=6)
            v = tk.StringVar(value=f"{stan:g}")
            tk.Entry(wn, textvariable=v, width=8, font=("Arial", 9), justify="right").grid(row=i, column=2)
            pola.append((p, v))

        def wykonaj():
            poz, zle = [], []
            for p, v in pola:
                il = _liczba(v.get(), -1)
                stan = float(p.get("Dostepne") or 0)
                if il <= 0 or il > stan:
                    zle.append(f"{p['Symbol']}: {v.get()!r} (stan {stan:g})")
                    continue
                poz.append({"symbol": p["Symbol"], "ilosc": il})
            if zle:
                messagebox.showwarning("RW", "Ilość musi być > 0 i ≤ stan:" + NL + NL
                                       + NL.join("  • " + z for z in zle[:10]), parent=dlg)
                return
            powod = var_powod.get().strip()
            if not powod:
                messagebox.showwarning("RW", "Wpisz powód — bez niego za pół roku nikt nie będzie "
                                             "wiedział, dlaczego stan zszedł.", parent=dlg)
                return
            if not messagebox.askyesno(
                    "RW — potwierdzenie",
                    f"Baza PRODUKCYJNA Subiekta." + NL + NL
                    + f"Powstanie rozchód wewnętrzny (RW) na magazyn {MAGAZYN}:" + NL
                    + NL.join(f"  • {x['symbol']}: {x['ilosc']:g}" for x in poz[:10])
                    + ("" if len(poz) <= 10 else NL + "  …")
                    + NL + NL + f"Uwagi: {UWAGI_MAGAZYN}: {powod}" + NL + NL
                    + "Stan w Subiekcie ZEJDZIE o te ilości. Wykonać?",
                    parent=dlg, icon="warning"):
                return
            dlg.destroy()
            self.start_kreciolek("Wystawiam RW w Subiekcie (~10 s)")
            threading.Thread(target=self._rw_worker, args=(poz, f"{UWAGI_MAGAZYN}: {powod}"),
                             daemon=True).start()

        btn_wykonaj.config(command=wykonaj)

    def _rw_worker(self, poz, uwagi):
        try:
            wynik = utworz_rw(poz, uwagi, zapisz=True)
            self.after(0, lambda: self._rw_done(wynik, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._rw_done(None, err))

    def _rw_done(self, wynik, error):
        self.stop_kreciolek()
        if error:
            self.status.config(text="Nie udało się wystawić RW.")
            messagebox.showerror("RW", error, parent=self)
            return
        numer = wynik.get("numer")
        bledy = [k for k in wynik.get("kroki", []) if k.get("Status") == "blad"]
        if numer:
            messagebox.showinfo("RW wystawione",
                                f"Utworzono {numer}." + NL + NL
                                + "Stan w Subiekcie zszedł. Kliknij „Odśwież”, żeby zobaczyć nowe ilości.",
                                parent=self)
            self.status.config(text=f"Wystawiono {numer}. Odśwież, żeby zobaczyć stany po RW.")
            for p in self.pozycje:
                p["sel"] = False
            self._odswiez_liste()
        else:
            messagebox.showerror("RW", "RW nie powstało:" + NL + NL
                                 + NL.join(f"  • {b.get('Symbol', '')}: {b.get('Szczegoly', '')}"
                                           for b in bledy[:8]), parent=self)

    # ── usuwanie kartotek ──────────────────────────────────────────────────
    def _usun_kartoteki(self):
        """Kasuje zaznaczone kartoteki z Subiekta — TYLKO bez historii.

        Subiekt odmawia, gdy kartoteka ma jakikolwiek dokument, stan albo jest
        składnikiem kompletu; most raportuje to per symbol (po weryfikacji, bo
        Usun() potrafi milczeć). Dlatego najpierw suchy przebieg, potem
        potwierdzenie z listą tego, co realnie zniknie.
        """
        zazn = [p for p in self.pozycje if p["sel"]]
        if not zazn:
            messagebox.showinfo("Usuwanie", "Zaznacz ✓ kartoteki do usunięcia.", parent=self)
            return
        ze_stanem = [p["Symbol"] for p in zazn if float(p.get("Dostepne") or 0) > 0]
        if ze_stanem:
            messagebox.showwarning(
                "Usuwanie",
                "Te kartoteki MAJĄ stan — Subiekt nie pozwoli ich usunąć:" + NL + NL
                + NL.join(f"  • {x}" for x in ze_stanem[:10]) + NL + NL
                + "Najpierw zdejmij stan (RW), a kartotekę kasuj dopiero bez żadnej historii.",
                parent=self)
            return
        symbole = [p["Symbol"] for p in zazn]
        if not messagebox.askyesno(
                "Usuwanie kartotek — NIEODWRACALNE",
                f"Baza PRODUKCYJNA Subiekta." + NL + NL
                + f"Usunąć {len(symbole)} kartotek z katalogu?" + NL
                + NL.join(f"  • {x}" for x in symbole[:10]) + ("" if len(symbole) <= 10 else NL + "  …")
                + NL + NL + "Kartoteki z dokumentami Subiekt pominie i powie dlaczego." + NL
                + "Usuniętych NIE da się przywrócić. Kontynuować?",
                parent=self, icon="warning"):
            return
        self.start_kreciolek(f"Usuwam {len(symbole)} kartotek z Subiekta (~10 s)")
        threading.Thread(target=self._usun_worker, args=(symbole,), daemon=True).start()

    def _usun_worker(self, symbole):
        try:
            wynik = usun_kartoteki(symbole, zapisz=True)
            self.after(0, lambda: self._usun_done(wynik, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._usun_done(None, err))

    def _usun_done(self, wynik, error):
        self.stop_kreciolek()
        if error:
            self.status.config(text="Nie udało się usunąć kartotek.")
            messagebox.showerror("Usuwanie", error, parent=self)
            return
        kroki = wynik.get("kroki", [])
        usuniete = {k["Symbol"].strip().upper() for k in kroki if k.get("Status") == "usunieta"}
        bledy = [k for k in kroki if k.get("Status") == "blad"]
        self.pozycje = [p for p in self.pozycje if p["Symbol"].strip().upper() not in usuniete]
        if self.katalog is not None:
            self.katalog = [k for k in self.katalog
                            if (k.get("Symbol") or "").strip().upper() not in usuniete]
        self._odswiez_liste()
        tekst = f"Usunięto kartotek: {len(usuniete)}"
        if bledy:
            tekst += NL + NL + f"Pominięte ({len(bledy)}) — Subiekt odmówił:" + NL + NL.join(
                f"  • {b.get('Symbol')}: {b.get('Szczegoly')}" for b in bledy[:8])
        (messagebox.showwarning if bledy else messagebox.showinfo)("Usuwanie", tekst, parent=self)
        self.status.config(text=f"Usunięto {len(usuniete)} kartotek."
                                + (f" Pominięto {len(bledy)} (mają historię)." if bledy else ""))

    # ── dymki dla obciętych kolumn ───────────────────────────────────────────
    #: nagłówki kolumn z dymkiem — te same zasady co w subiekt_zamowienia
    #: (TOOLTIP_KOLUMNY): tylko tam, gdzie treść realnie nie mieści się
    #: w szerokości. „ZD” bywa zbiorcze i z ilościami („ZD 1/CENTRALA/2026 (2),
    #: ZD 2/…”) i obcina się w wąskiej kolumnie — stąd dymek.
    TOOLTIP_KOLUMNY = {"nazwa", "dostawca", "zd"}

    def _podepnij_tooltip(self):
        """Dymek dla kolumn, których treść nie mieści się w szerokości.

        Ten sam mechanizm co w subiekt_zamowienia.py — tksheet nie ma
        własnych tooltipów, więc robimy je na Toplevel bez ramki.
        """
        self._tip = None
        self._tip_kom = None          # (wiersz, kolumna) — żeby nie mrugał
        self._tip_after = None
        self.sheet.bind("<Motion>", self._tip_ruch, add="+")
        self.sheet.bind("<Leave>", lambda _e: self._tip_ukryj(), add="+")
        self.sheet.bind("<Button-1>", lambda _e: self._tip_ukryj(), add="+")
        self.sheet.bind("<MouseWheel>", lambda _e: self._tip_ukryj(), add="+")
        self.bind("<Destroy>", lambda _e: self._tip_ukryj(), add="+")

    def _tip_ukryj(self):
        if self._tip_after:
            try:
                self.after_cancel(self._tip_after)
            except Exception:
                pass
            self._tip_after = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None
        self._tip_kom = None

    def _tip_ruch(self, event):
        try:
            r = self.sheet.identify_row(event, allow_end=False)
            c = self.sheet.identify_column(event, allow_end=False)
        except Exception:
            return
        if r is None or c is None:
            self._tip_ukryj()
            return
        if (r, c) == self._tip_kom:
            return                     # ta sama komórka — nie przerysowuj
        self._tip_ukryj()

        try:
            naglowek = self.KOLUMNY[c][1].strip().lower()
        except Exception:
            return
        if naglowek not in self.TOOLTIP_KOLUMNY:
            return

        try:
            tekst = str(self.sheet.get_cell_data(r, c) or "").strip()
        except Exception:
            return
        if not tekst:
            return

        self._tip_kom = (r, c)
        # Krótka zwłoka — bez niej dymki migoczą przy przesuwaniu myszy.
        self._tip_after = self.after(
            400, lambda: self._tip_pokaz(tekst, event.x_root, event.y_root))

    def _tip_pokaz(self, tekst, x, y):
        self._tip_after = None
        if self._tip is not None:
            return
        tip = tk.Toplevel(self)
        tip.overrideredirect(True)     # bez ramki okna — to dymek
        tip.attributes("-topmost", True)
        tk.Label(tip, text=tekst, bg="#ffffe0", fg="#2c3e50",
                 relief=tk.SOLID, bd=1, justify=tk.LEFT, anchor="w",
                 font=("Arial", 9), padx=6, pady=3,
                 wraplength=520).pack()
        # Poniżej kursora, żeby nie zasłaniać komórki, na którą patrzysz.
        tip.update_idletasks()
        szer, wys = tip.winfo_width(), tip.winfo_height()
        ekran_x = tip.winfo_screenwidth()
        tip.geometry(f"+{min(x + 14, ekran_x - szer - 8)}+{y + 20}")
        self._tip = tip

    # ── rozbicie na magazyny ───────────────────────────────────────────────
    def _wybor_pozycji(self, _event=None):
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
        # Pasek stanu należy do kręciołka — gdy się kręci, nie nadpisujemy.
        if not getattr(self, "_kreci", False):
            self.status.config(text=f"{p.get('Symbol', '')} — {p.get('Nazwa', '')}")


def open_window(parent):
    return MagazynWindow(parent)
