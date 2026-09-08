# -*- coding: utf-8 -*-
"""Edytor kartotek Subiekta — duże okno do budowania kartotek i kompletów.

    import subiekt_edytor_gui
    subiekt_edytor_gui.open_window(parent)                    # nowy zestaw
    subiekt_edytor_gui.open_window(parent, symbol="SZ-100")   # edycja istniejącej

Czym się różni od okna „Dodaj asortyment" (subiekt_asortyment_gui):

    Dodaj asortyment — szybkie „wrzuć JEDNĄ pozycję", wywoływane z różnych
                       miejsc aplikacji. Zostaje bez zmian.
    Asortyment       — przegląd całej kartoteki Subiekta, zmiana nazwy/ceny.
    Edytor kartotek  — TU: układasz 10-30 pozycji w drzewie, określasz składy
                       kompletów i zapisujesz CAŁOŚĆ jednym ruchem.

Zamiast „Dodaj → zapisz → Dodaj → zapisz" jest:
„ułóż drzewo → Sprawdź całość → zobacz co powstanie → Załóż całość".

── MODEL: GRAF, NIE DRZEWO ─────────────────────────────────────────────────

W GUI widać drzewo, ale wewnętrznie dane są grafem:

    pozycje = {"SR-M5": Kartoteka(...), ...}       # symbol → dane, JEDEN raz
    relacje = [("SZ-100", "KORP-01", 1.0), ...]    # (rodzic, dziecko, ilość)

Dlaczego nie zwykłe drzewo: `DIN 912 M6x20` bywa w pięciu kompletach naraz.
W drzewie pokażemy ją pięć razy, ale kartoteka jest JEDNA — zmiana nazwy czy
ceny w jednym miejscu musi być widoczna we wszystkich wystąpieniach. Drzewo
przechowujące dane w węzłach zrobiłoby z tego pięć rozjeżdżających się kopii.

To zresztą zgodne z tym, co Subiekt i karta pozycji już pokazują: „zawiera"
i „wchodzi w skład" to relacje w obie strony, czyli graf.

── SYMBOL JEST KLUCZEM ─────────────────────────────────────────────────────

Po zapisaniu do Subiekta symbolu NIE WOLNO zmieniać — jest kluczem w kodach
kreskowych, na dokumentach i w składach kompletów (patrz Symbole.cs i pułapka
ze spacją wiodącą w MAGAZYN.md). Pozycje już istniejące w Subiekcie mają pole
Symbol zablokowane.
"""

import json
import os
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from rm_kreciolek import Kreciolek
from subiekt_stany import wysrodkuj
#: Wywołanie mostu — ta sama funkcja, której używa okno „Dodaj asortyment":
#: stały most z fallbackiem na CLI, więc nie duplikujemy tu obsługi protokołu.
from subiekt_asortyment_gui import _uruchom

TLO = "#ecf0f1"
TLO_SEKCJI = "#ffffff"
TEKST = "#2c3e50"
TEKST_SZARY = "#7f8c8d"
LINK = "#1f618d"
OK_ZIELONY = "#1e8449"
BLAD_CZERWONY = "#c0392b"
NOWY_NIEBIESKI = "#1f618d"

TIMEOUT_S = 600

#: Rodzaje kartotek — etykieta w GUI → wartość dla mostu.
RODZAJE = [("Towar", "towar"), ("Komplet (Z)", "komplet"), ("Usługa", "usluga")]
#: Skróty przy węzłach drzewa — od razu widać, co jest czym.
SKROT = {"towar": "TW", "komplet": "KT", "usluga": "US"}

JEDNOSTKI = ["szt", "kpl", "usl", "m", "mb", "kg", "rbg", "kpl."]


def pobierz_katalog(timeout=TIMEOUT_S):
    """[{Symbol, Nazwa, CenaEwidencyjna}] — wszystkie kartoteki Subiekta.

    Tryb „katalog" świadomie nie czyta stanów (najdroższa część odczytu),
    więc 3444 kartoteki wchodzą w ~9 s zamiast kilkudziesięciu.
    """
    out = os.path.join(tempfile.mkdtemp(prefix="subiekt_edyt_"), "katalog.json")
    return _uruchom("katalog", [], out, timeout).get("pozycje", [])


def pobierz_komplet(symbol, timeout=TIMEOUT_S):
    """Skład kompletu z Subiekta — do wczytania istniejącej struktury."""
    out = os.path.join(tempfile.mkdtemp(prefix="subiekt_edyt_"), "komplet.json")
    wynik = _uruchom("komplet", [f"--symbol={symbol}"], out, timeout,
                     symbole=[symbol])
    return (wynik.get("pozycje") or [{}])[0]


def zapisz_kartoteki(plan, zapisz, timeout=TIMEOUT_S):
    """Wsad do mostu: kartoteki + składy kompletów, BEZ ZK.

    zapisz=False to „Sprawdź całość" — most mówi, co powstanie i co się
    zmieni, nie dotykając bazy.
    """
    tmp = tempfile.mkdtemp(prefix="subiekt_edyt_")
    plan_path = os.path.join(tmp, "plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False)
    argv = [f"--plan={plan_path}"] + (["--zapisz"] if zapisz else [])
    return _uruchom("kartoteki", argv, os.path.join(tmp, "wynik.json"),
                    timeout, plan=plan, write=zapisz)


class Kartoteka:
    """Jedna kartoteka — dane wspólne dla WSZYSTKICH wystąpień w drzewie."""

    def __init__(self, symbol, nazwa="", rodzaj="towar", jm="szt",
                 cena=0.0, opis="", w_subiekcie=False):
        self.symbol = symbol
        self.nazwa = nazwa or symbol
        self.rodzaj = rodzaj
        self.jm = jm
        self.cena = cena
        self.opis = opis
        #: Czy kartoteka jest już w Subiekcie — blokuje zmianę symbolu
        #: i decyduje, czy to „założymy" czy „zmienimy".
        self.w_subiekcie = w_subiekcie

    def czy_komplet(self):
        return self.rodzaj == "komplet"

    def do_planu(self, skladniki):
        d = {"symbol": self.symbol, "nazwa": self.nazwa,
             "rodzaj": self.rodzaj, "jm": self.jm,
             "cena": self.cena, "opis": self.opis}
        if skladniki:
            d["skladniki"] = skladniki
        return d


class EdytorWindow(tk.Toplevel, Kreciolek):
    KOL_SKLAD = [("lp", "Lp.", 40), ("symbol", "Symbol", 130),
                 ("nazwa", "Nazwa", 220), ("ilosc", "Ilość", 70),
                 ("jm", "JM", 50)]
    KOL_LISTA = [("symbol", "Symbol", 130), ("nazwa", "Nazwa", 200),
                 ("rodzaj", "Rodzaj", 80), ("cena", "Cena netto", 80)]

    def __init__(self, parent, symbol=None):
        super().__init__(parent)
        self.title("Edytor kartotek — Subiekt nexo PRO")
        self.configure(bg=TLO)
        self.geometry("1500x820")

        # ── MODEL (graf, patrz docstring) ────────────────────────────────
        self.pozycje = {}        # symbol -> Kartoteka
        self.relacje = []        # [(rodzic, dziecko, ilosc)]
        self.korzenie = []       # symbole bez rodzica — wierzchołki drzewa
        self.katalog = []        # kartoteki z Subiekta (do listy 4)
        self._zaznaczony = None  # symbol aktualnie edytowanej pozycji
        self._blokada = False    # blokada zapisu pól przy przeładowaniu

        self._buduj()
        wysrodkuj(self, parent)
        self.after(100, self._wczytaj_katalog)
        if symbol:
            self.after(200, lambda: self._wczytaj_istniejaca(symbol))

    # ── BUDOWA OKNA ─────────────────────────────────────────────────────

    def _buduj(self):
        pasek = tk.Frame(self, bg="#34495e", height=44)
        pasek.pack(fill=tk.X)
        pasek.pack_propagate(False)
        tk.Label(pasek, text="✎  EDYTOR KARTOTEK SUBIEKTA", bg="#34495e",
                 fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)
        tk.Button(pasek, text="Anuluj", command=self.destroy,
                  font=("Arial", 9)).pack(side=tk.RIGHT, padx=8, pady=7)
        self.btn_zapisz = tk.Button(pasek, text="Załóż / Zapisz", state=tk.DISABLED,
                                    command=self._zapisz_calosc, bg="#2980b9", fg="white",
                                    font=("Arial", 9, "bold"))
        self.btn_zapisz.pack(side=tk.RIGHT, padx=4, pady=7)
        tk.Button(pasek, text="Sprawdź całość", command=self._sprawdz_calosc,
                  font=("Arial", 9)).pack(side=tk.RIGHT, padx=4, pady=7)

        self.status = tk.Label(self, text="", bg=TLO, fg=TEKST_SZARY,
                               font=("Arial", 9), anchor="w")
        self.status.pack(fill=tk.X, padx=10, pady=(6, 0))

        srodek = tk.Frame(self, bg=TLO)
        srodek.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        self._panel_drzewo(srodek)
        self._panel_szczegoly(srodek)
        self._panel_sklad_i_lista(srodek)

    def _panel_drzewo(self, rodzic):
        ram = tk.LabelFrame(rodzic, text=" 1. Struktura kartoteki (drzewo) ",
                            bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9, "bold"))
        ram.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 6))
        ram.configure(width=340)
        ram.pack_propagate(False)

        wrap = tk.Frame(ram, bg=TLO_SEKCJI)
        wrap.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.tree = ttk.Treeview(wrap, columns=("ilosc",), show="tree headings",
                                 selectmode="browse")
        self.tree.heading("#0", text="Symbol / Nazwa")
        self.tree.heading("ilosc", text="Ilość")
        self.tree.column("#0", width=230)
        self.tree.column("ilosc", width=60, anchor="e", stretch=False)
        sc = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sc.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._na_wybor_wezla)

        # Kolory rodzajów — od razu widać komplet vs towar vs usługa.
        self.tree.tag_configure("komplet", foreground="#b9770e")
        self.tree.tag_configure("usluga", foreground="#6c3483")
        self.tree.tag_configure("nowy", foreground=NOWY_NIEBIESKI)

        pa = tk.Frame(ram, bg=TLO_SEKCJI)
        pa.pack(fill=tk.X, padx=6, pady=(0, 6))
        for txt, cmd in (("+ Pozycja", self._dodaj_pozycje),
                         ("+ Składnik", self._dodaj_skladnik),
                         ("+ Istniejąca", self._dodaj_istniejaca)):
            tk.Button(pa, text=txt, command=cmd, font=("Arial", 8)).pack(side=tk.LEFT, padx=2)
        pb = tk.Frame(ram, bg=TLO_SEKCJI)
        pb.pack(fill=tk.X, padx=6, pady=(0, 8))
        for txt, cmd in (("Duplikuj", self._duplikuj), ("Usuń", self._usun_wezel),
                         ("↑", lambda: self._przesun(-1)), ("↓", lambda: self._przesun(1))):
            tk.Button(pb, text=txt, command=cmd, font=("Arial", 8),
                      width=8 if len(txt) > 2 else 3).pack(side=tk.LEFT, padx=2)
        tk.Button(pb, text="Z projektu…", command=self._wczytaj_z_projektu,
                  font=("Arial", 8)).pack(side=tk.RIGHT, padx=2)

    def _panel_szczegoly(self, rodzic):
        ram = tk.LabelFrame(rodzic, text=" 2. Kartoteka — szczegóły ",
                            bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9, "bold"))
        ram.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6)

        self.karty = ttk.Notebook(ram)
        self.karty.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        pod = tk.Frame(self.karty, bg=TLO_SEKCJI)
        self.karty.add(pod, text="Podstawowe")

        self.pola = {}
        wiersze = [("symbol", "Symbol:"), ("nazwa", "Nazwa:")]
        for i, (klucz, etykieta) in enumerate(wiersze):
            tk.Label(pod, text=etykieta, bg=TLO_SEKCJI, fg=TEKST,
                     font=("Arial", 9), anchor="w", width=12).grid(
                row=i, column=0, sticky="w", padx=8, pady=6)
            v = tk.StringVar()
            e = tk.Entry(pod, textvariable=v, font=("Arial", 9), width=44)
            e.grid(row=i, column=1, sticky="we", padx=4, pady=6)
            v.trace_add("write", lambda *_a, k=klucz: self._pole_zmienione(k))
            self.pola[klucz] = (v, e)

        tk.Label(pod, text="Rodzaj:", bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9),
                 anchor="w", width=12).grid(row=2, column=0, sticky="w", padx=8, pady=6)
        self.var_rodzaj = tk.StringVar(value=RODZAJE[0][0])
        cb = ttk.Combobox(pod, textvariable=self.var_rodzaj, state="readonly",
                          values=[r[0] for r in RODZAJE], width=20, font=("Arial", 9))
        cb.grid(row=2, column=1, sticky="w", padx=4, pady=6)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._pole_zmienione("rodzaj"))

        tk.Label(pod, text="Jednostka:", bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9),
                 anchor="w", width=12).grid(row=3, column=0, sticky="w", padx=8, pady=6)
        self.var_jm = tk.StringVar(value="szt")
        cbj = ttk.Combobox(pod, textvariable=self.var_jm, values=JEDNOSTKI,
                           width=12, font=("Arial", 9))
        cbj.grid(row=3, column=1, sticky="w", padx=4, pady=6)
        cbj.bind("<<ComboboxSelected>>", lambda _e: self._pole_zmienione("jm"))
        self.var_jm.trace_add("write", lambda *_a: self._pole_zmienione("jm"))

        tk.Label(pod, text="Cena ewid.:", bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9),
                 anchor="w", width=12).grid(row=4, column=0, sticky="w", padx=8, pady=6)
        self.var_cena = tk.StringVar(value="0,00")
        ec = tk.Entry(pod, textvariable=self.var_cena, font=("Arial", 9), width=14)
        ec.grid(row=4, column=1, sticky="w", padx=4, pady=6)
        self.var_cena.trace_add("write", lambda *_a: self._pole_zmienione("cena"))

        tk.Label(pod, text="Opis:", bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9),
                 anchor="nw", width=12).grid(row=5, column=0, sticky="nw", padx=8, pady=6)
        self.txt_opis = tk.Text(pod, height=5, width=44, font=("Arial", 9), wrap="word")
        self.txt_opis.grid(row=5, column=1, sticky="we", padx=4, pady=6)
        self.txt_opis.bind("<KeyRelease>", lambda _e: self._pole_zmienione("opis"))
        pod.grid_columnconfigure(1, weight=1)

        self.lbl_info = tk.Label(
            pod, text="Symbol po zapisie do Subiekta nie podlega zmianie —\n"
                      "jest kluczem w kodach kreskowych, dokumentach i składach kompletów.",
            bg="#eaf2f8", fg=TEKST_SZARY, font=("Arial", 8), justify="left", anchor="w")
        self.lbl_info.grid(row=6, column=0, columnspan=2, sticky="we", padx=8, pady=(10, 8))

        for tytul in ("Handlowe", "Magazyn", "Dodatkowe"):
            f = tk.Frame(self.karty, bg=TLO_SEKCJI)
            self.karty.add(f, text=tytul)
            tk.Label(f, text=f"„{tytul}" + "” — do uzupełnienia w kolejnej wersji.\n\n"
                             "Most przekazuje dziś: symbol, nazwa, rodzaj, jednostka,\n"
                             "cena ewidencyjna, opis i skład kompletu.",
                     bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 9),
                     justify="left").pack(padx=16, pady=16, anchor="w")

    def _panel_sklad_i_lista(self, rodzic):
        ram = tk.Frame(rodzic, bg=TLO)
        ram.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        gora = tk.LabelFrame(ram, text=" 3. Skład kompletu ", bg=TLO_SEKCJI,
                             fg=TEKST, font=("Arial", 9, "bold"))
        gora.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.lbl_sklad = tk.Label(gora, text="(zaznacz komplet w drzewie)",
                                  bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8), anchor="w")
        self.lbl_sklad.pack(fill=tk.X, padx=6, pady=(4, 0))
        self.tab_sklad = ttk.Treeview(gora, columns=[k[0] for k in self.KOL_SKLAD],
                                      show="headings", height=7)
        for klucz, naglowek, szer in self.KOL_SKLAD:
            self.tab_sklad.heading(klucz, text=naglowek)
            self.tab_sklad.column(klucz, width=szer,
                                  anchor="e" if klucz in ("lp", "ilosc") else "w")
        self.tab_sklad.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self.tab_sklad.bind("<Double-1>", self._edytuj_ilosc)

        ps = tk.Frame(gora, bg=TLO_SEKCJI)
        ps.pack(fill=tk.X, padx=6, pady=(0, 6))
        tk.Label(ps, text="Dwuklik na ilości = zmiana", bg=TLO_SEKCJI,
                 fg=TEKST_SZARY, font=("Arial", 8)).pack(side=tk.LEFT)
        tk.Button(ps, text="Usuń składnik", command=self._usun_skladnik,
                  font=("Arial", 8)).pack(side=tk.RIGHT, padx=2)

        dol = tk.LabelFrame(ram, text=" 4. Lista istniejących kartotek (Subiekt) ",
                            bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9, "bold"))
        dol.pack(fill=tk.BOTH, expand=True)
        sz = tk.Frame(dol, bg=TLO_SEKCJI)
        sz.pack(fill=tk.X, padx=6, pady=4)
        tk.Label(sz, text="Szukaj:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9)).pack(side=tk.LEFT)
        self.var_szukaj = tk.StringVar()
        tk.Entry(sz, textvariable=self.var_szukaj, font=("Arial", 9)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.var_szukaj.trace_add("write", lambda *_a: self._odswiez_liste())

        self.tab_lista = ttk.Treeview(dol, columns=[k[0] for k in self.KOL_LISTA],
                                      show="headings", height=8)
        for klucz, naglowek, szer in self.KOL_LISTA:
            self.tab_lista.heading(klucz, text=naglowek)
            self.tab_lista.column(klucz, width=szer,
                                  anchor="e" if klucz == "cena" else "w")
        self.tab_lista.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self.tab_lista.bind("<Double-1>", lambda _e: self._dodaj_istniejaca())
        tk.Label(dol, text="Dwuklik = dodaj jako składnik zaznaczonego kompletu",
                 bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8), anchor="w").pack(
            fill=tk.X, padx=6, pady=(0, 6))

    # ── DANE Z SUBIEKTA ─────────────────────────────────────────────────

    def _wczytaj_katalog(self):
        self.start_kreciolek("Wczytuję kartoteki z Subiekta")
        threading.Thread(target=self._katalog_worker, daemon=True).start()

    def _katalog_worker(self):
        try:
            dane = pobierz_katalog()
            blad = None
        except Exception as e:
            dane, blad = [], str(e)
        self.after(0, lambda: self._katalog_gotowy(dane, blad))

    def _katalog_gotowy(self, dane, blad):
        self.stop_kreciolek()
        if blad:
            self.status.config(text=f"Nie udało się wczytać kartotek: {blad}",
                               fg=BLAD_CZERWONY)
            return
        self.katalog = dane
        self._odswiez_liste()
        self.status.config(text=f"Kartotek w Subiekcie: {len(dane)}", fg=TEKST_SZARY)

    def _odswiez_liste(self):
        szukaj = (self.var_szukaj.get() or "").strip().lower()
        for w in self.tab_lista.get_children():
            self.tab_lista.delete(w)
        n = 0
        for k in self.katalog:
            sym = str(k.get("Symbol") or "").strip()
            naz = str(k.get("Nazwa") or "").strip()
            if szukaj and szukaj not in sym.lower() and szukaj not in naz.lower():
                continue
            self.tab_lista.insert("", "end", values=(
                sym, naz, k.get("Rodzaj") or "", f"{float(k.get('CenaEwidencyjna') or 0):g}"))
            n += 1
            if n >= 400:      # lista podglądowa — filtr zawęża, nie przewijamy tysięcy
                break

    def _wczytaj_istniejaca(self, symbol):
        """Tryb edycji: wciąga kartotekę z Subiekta wraz ze składem."""
        self.start_kreciolek(f"Wczytuję {symbol}")
        threading.Thread(target=self._istniejaca_worker, args=(symbol,), daemon=True).start()

    def _istniejaca_worker(self, symbol):
        try:
            dane, blad = pobierz_komplet(symbol), None
        except Exception as e:
            dane, blad = {}, str(e)
        self.after(0, lambda: self._istniejaca_gotowa(symbol, dane, blad))

    def _istniejaca_gotowa(self, symbol, dane, blad):
        self.stop_kreciolek()
        if blad:
            self.status.config(text=f"Nie udało się wczytać {symbol}: {blad}",
                               fg=BLAD_CZERWONY)
            return
        rodzaj = (dane.get("Rodzaj") or "Towar").lower()
        rodzaj = "komplet" if "komplet" in rodzaj else ("usluga" if "usług" in rodzaj else "towar")
        self.pozycje[symbol] = Kartoteka(
            symbol, dane.get("Nazwa") or symbol, rodzaj,
            w_subiekcie=True)
        if symbol not in self.korzenie:
            self.korzenie.append(symbol)
        for s in dane.get("Skladniki") or []:
            ssym = str(s.get("Symbol") or "").strip()
            if not ssym:
                continue
            if ssym not in self.pozycje:
                srodzaj = (s.get("Rodzaj") or "Towar").lower()
                srodzaj = ("komplet" if "komplet" in srodzaj
                           else "usluga" if "usług" in srodzaj else "towar")
                self.pozycje[ssym] = Kartoteka(ssym, s.get("Nazwa") or ssym,
                                               srodzaj, w_subiekcie=True)
            self.relacje.append((symbol, ssym, float(s.get("Ilosc") or 1)))
        self._odswiez_drzewo()
        self.status.config(text=f"Wczytano {symbol} ze składem "
                                f"({len(dane.get('Skladniki') or [])} skł.)", fg=TEKST_SZARY)

    # ── DRZEWO ──────────────────────────────────────────────────────────

    def _dzieci(self, symbol):
        return [(d, il) for (r, d, il) in self.relacje if r == symbol]

    def _odswiez_drzewo(self):
        rozwiniete = {self.tree.item(i, "text").split()[1]
                      for i in self.tree.get_children("") if self.tree.item(i, "open")}
        for w in self.tree.get_children(""):
            self.tree.delete(w)
        for sym in self.korzenie:
            self._wstaw_wezel("", sym, None, set())
        for i in self.tree.get_children(""):
            self.tree.item(i, open=True)
        self._aktualizuj_przycisk_zapisu()

    def _wstaw_wezel(self, rodzic_id, symbol, ilosc, sciezka):
        k = self.pozycje.get(symbol)
        if k is None:
            return
        # Cykl (A zawiera B, B zawiera A) — pokazujemy i przerywamy, zamiast
        # zapętlić GUI. Sam Subiekt też takiego składu nie przyjmie.
        if symbol in sciezka:
            self.tree.insert(rodzic_id, "end", text=f"⟲ {symbol} (cykl!)", values=("",))
            return
        tagi = [k.rodzaj]
        if not k.w_subiekcie:
            tagi.append("nowy")
        wid = self.tree.insert(
            rodzic_id, "end",
            text=f"{SKROT.get(k.rodzaj, '??')} {symbol}   {k.nazwa}",
            values=(f"x{ilosc:g}" if ilosc else "",), tags=tuple(tagi))
        for dziecko, il in self._dzieci(symbol):
            self._wstaw_wezel(wid, dziecko, il, sciezka | {symbol})

    def _symbol_wezla(self, item=None):
        item = item or (self.tree.selection() or [None])[0]
        if not item:
            return None
        txt = self.tree.item(item, "text")
        czesci = txt.split(None, 2)
        return czesci[1] if len(czesci) > 1 else None

    def _na_wybor_wezla(self, _e=None):
        sym = self._symbol_wezla()
        if not sym or sym not in self.pozycje:
            return
        self._zaznaczony = sym
        k = self.pozycje[sym]
        self._blokada = True
        try:
            self.pola["symbol"][0].set(k.symbol)
            self.pola["nazwa"][0].set(k.nazwa)
            # Symbol istniejącej kartoteki jest kluczem — nie wolno go zmieniać.
            self.pola["symbol"][1].config(
                state="readonly" if k.w_subiekcie else "normal")
            for etykieta, wartosc in RODZAJE:
                if wartosc == k.rodzaj:
                    self.var_rodzaj.set(etykieta)
            self.var_jm.set(k.jm)
            self.var_cena.set(f"{k.cena:.2f}".replace(".", ","))
            self.txt_opis.delete("1.0", "end")
            self.txt_opis.insert("1.0", k.opis or "")
        finally:
            self._blokada = False
        self._odswiez_sklad()

    def _pole_zmienione(self, klucz):
        if self._blokada or not self._zaznaczony:
            return
        k = self.pozycje.get(self._zaznaczony)
        if k is None:
            return
        if klucz == "nazwa":
            k.nazwa = self.pola["nazwa"][0].get().strip() or k.symbol
        elif klucz == "symbol" and not k.w_subiekcie:
            nowy = self.pola["symbol"][0].get().strip()
            if nowy and nowy != k.symbol and nowy not in self.pozycje:
                self._zmien_symbol(k.symbol, nowy)
                return
        elif klucz == "rodzaj":
            etykieta = self.var_rodzaj.get()
            k.rodzaj = dict((e, w) for e, w in RODZAJE).get(etykieta, "towar")
            self._odswiez_sklad()
        elif klucz == "jm":
            k.jm = self.var_jm.get().strip() or "szt"
        elif klucz == "cena":
            try:
                k.cena = float(self.var_cena.get().replace(",", ".") or 0)
            except ValueError:
                pass
        elif klucz == "opis":
            k.opis = self.txt_opis.get("1.0", "end").strip()
        self._odswiez_drzewo()
        self._zaznacz_w_drzewie(k.symbol)

    def _zmien_symbol(self, stary, nowy):
        """Zmiana symbolu pozycji, która NIE jest jeszcze w Subiekcie."""
        k = self.pozycje.pop(stary)
        k.symbol = nowy
        self.pozycje[nowy] = k
        self.relacje = [(nowy if r == stary else r, nowy if d == stary else d, il)
                        for (r, d, il) in self.relacje]
        self.korzenie = [nowy if s == stary else s for s in self.korzenie]
        self._zaznaczony = nowy
        self._odswiez_drzewo()
        self._zaznacz_w_drzewie(nowy)

    def _zaznacz_w_drzewie(self, symbol):
        def szukaj(rodzic=""):
            for i in self.tree.get_children(rodzic):
                if self._symbol_wezla(i) == symbol:
                    return i
                z = szukaj(i)
                if z:
                    return z
            return None
        wid = szukaj()
        if wid:
            self.tree.selection_set(wid)
            self.tree.see(wid)

    # ── OPERACJE NA DRZEWIE ─────────────────────────────────────────────

    def _nowy_symbol(self, baza="NOWA"):
        i = 1
        while f"{baza}-{i:02d}" in self.pozycje:
            i += 1
        return f"{baza}-{i:02d}"

    def _dodaj_pozycje(self):
        """Nowa pozycja jako KORZEŃ drzewa (samodzielny produkt/komplet)."""
        sym = self._nowy_symbol()
        self.pozycje[sym] = Kartoteka(sym, "", "komplet", "kpl")
        self.korzenie.append(sym)
        self._odswiez_drzewo()
        self._zaznacz_w_drzewie(sym)
        self.pola["symbol"][1].focus_set()

    def _dodaj_skladnik(self):
        """Nowa pozycja jako SKŁADNIK zaznaczonego kompletu."""
        rodzic = self._symbol_wezla()
        if not rodzic or rodzic not in self.pozycje:
            messagebox.showinfo("Edytor", "Zaznacz najpierw komplet w drzewie.", parent=self)
            return
        if not self.pozycje[rodzic].czy_komplet():
            messagebox.showwarning(
                "Edytor", f"„{rodzic}” nie jest kompletem — składniki można dodać\n"
                          "tylko do pozycji rodzaju Komplet.", parent=self)
            return
        sym = self._nowy_symbol("SKL")
        self.pozycje[sym] = Kartoteka(sym, "", "towar", "szt")
        self.relacje.append((rodzic, sym, 1.0))
        self._odswiez_drzewo()
        self._zaznacz_w_drzewie(sym)
        self.pola["symbol"][1].focus_set()

    def _dodaj_istniejaca(self):
        """Kartoteka z Subiekta jako składnik zaznaczonego kompletu."""
        wyb = self.tab_lista.selection()
        if not wyb:
            messagebox.showinfo("Edytor", "Zaznacz kartotekę na liście (sekcja 4).", parent=self)
            return
        sym, naz, rodzaj, cena = self.tab_lista.item(wyb[0], "values")
        rodzaj_n = ("komplet" if "omplet" in rodzaj else
                    "usluga" if "sług" in rodzaj or "slug" in rodzaj else "towar")
        if sym not in self.pozycje:
            try:
                cena_f = float(str(cena).replace(",", ".") or 0)
            except ValueError:
                cena_f = 0.0
            self.pozycje[sym] = Kartoteka(sym, naz, rodzaj_n, cena=cena_f, w_subiekcie=True)

        rodzic = self._symbol_wezla()
        if rodzic and rodzic in self.pozycje and self.pozycje[rodzic].czy_komplet():
            self.relacje.append((rodzic, sym, 1.0))
        elif sym not in self.korzenie:
            self.korzenie.append(sym)
        self._odswiez_drzewo()
        self._zaznacz_w_drzewie(sym)

    def _duplikuj(self):
        sym = self._symbol_wezla()
        if not sym or sym not in self.pozycje:
            return
        zrodlo = self.pozycje[sym]
        nowy = self._nowy_symbol(sym.split("-")[0] if "-" in sym else "KOPIA")
        self.pozycje[nowy] = Kartoteka(nowy, zrodlo.nazwa, zrodlo.rodzaj,
                                       zrodlo.jm, zrodlo.cena, zrodlo.opis)
        # Kopiujemy też skład — duplikat kompletu ma sens tylko z zawartością.
        for dziecko, il in self._dzieci(sym):
            self.relacje.append((nowy, dziecko, il))
        self.korzenie.append(nowy)
        self._odswiez_drzewo()
        self._zaznacz_w_drzewie(nowy)

    def _usun_wezel(self):
        item = (self.tree.selection() or [None])[0]
        sym = self._symbol_wezla(item)
        if not sym:
            return
        rodzic_item = self.tree.parent(item)
        rodzic = self._symbol_wezla(rodzic_item) if rodzic_item else None
        if rodzic:
            # Usuwamy TYLKO to wystąpienie (relację) — kartoteka i pozostałe
            # wystąpienia zostają. To jest sedno modelu grafowego.
            for i, (r, d, il) in enumerate(self.relacje):
                if r == rodzic and d == sym:
                    self.relacje.pop(i)
                    break
        else:
            if sym in self.korzenie:
                self.korzenie.remove(sym)
            self.relacje = [(r, d, il) for (r, d, il) in self.relacje
                            if r != sym and d != sym]
            uzyta = any(d == sym for (_r, d, _i) in self.relacje)
            if not uzyta and sym in self.pozycje:
                del self.pozycje[sym]
        self._zaznaczony = None
        self._odswiez_drzewo()

    def _przesun(self, kierunek):
        item = (self.tree.selection() or [None])[0]
        sym = self._symbol_wezla(item)
        if not sym:
            return
        rodzic_item = self.tree.parent(item)
        rodzic = self._symbol_wezla(rodzic_item) if rodzic_item else None
        if rodzic:
            idx = [i for i, (r, d, _i) in enumerate(self.relacje)
                   if r == rodzic and d == sym]
            if not idx:
                return
            i = idx[0]
            j = i + kierunek
            # Szukamy sąsiada w obrębie TEGO SAMEGO rodzica.
            while 0 <= j < len(self.relacje) and self.relacje[j][0] != rodzic:
                j += kierunek
            if 0 <= j < len(self.relacje):
                self.relacje[i], self.relacje[j] = self.relacje[j], self.relacje[i]
        else:
            if sym not in self.korzenie:
                return
            i = self.korzenie.index(sym)
            j = i + kierunek
            if 0 <= j < len(self.korzenie):
                self.korzenie[i], self.korzenie[j] = self.korzenie[j], self.korzenie[i]
        self._odswiez_drzewo()
        self._zaznacz_w_drzewie(sym)

    # ── SKŁAD KOMPLETU ──────────────────────────────────────────────────

    def _odswiez_sklad(self):
        for w in self.tab_sklad.get_children():
            self.tab_sklad.delete(w)
        sym = self._zaznaczony
        if not sym or sym not in self.pozycje:
            self.lbl_sklad.config(text="(zaznacz komplet w drzewie)")
            return
        k = self.pozycje[sym]
        if not k.czy_komplet():
            self.lbl_sklad.config(
                text=f"„{sym}” to {k.rodzaj} — skład mają tylko komplety")
            return
        dzieci = self._dzieci(sym)
        self.lbl_sklad.config(text=f"dla: {sym}   ({len(dzieci)} składników)")
        for i, (dziecko, il) in enumerate(dzieci, 1):
            kd = self.pozycje.get(dziecko)
            self.tab_sklad.insert("", "end", values=(
                i, dziecko, kd.nazwa if kd else "", f"{il:g}", kd.jm if kd else ""))

    def _edytuj_ilosc(self, _e=None):
        wyb = self.tab_sklad.selection()
        if not wyb or not self._zaznaczony:
            return
        wartosci = self.tab_sklad.item(wyb[0], "values")
        dziecko, obecna = wartosci[1], wartosci[3]
        dlg = tk.Toplevel(self)
        dlg.title("Ilość")
        dlg.configure(bg=TLO)
        tk.Label(dlg, text=f"Ilość „{dziecko}” w „{self._zaznaczony}”:",
                 bg=TLO, fg=TEKST, font=("Arial", 9)).pack(padx=14, pady=(12, 6))
        v = tk.StringVar(value=str(obecna))
        e = tk.Entry(dlg, textvariable=v, font=("Arial", 10), width=12, justify="right")
        e.pack(padx=14)
        e.focus_set()
        e.select_range(0, "end")

        def zapisz(_ev=None):
            try:
                nowa = float(v.get().replace(",", "."))
            except ValueError:
                messagebox.showwarning("Ilość", "Podaj liczbę.", parent=dlg)
                return
            if nowa <= 0:
                messagebox.showwarning("Ilość", "Ilość musi być dodatnia.", parent=dlg)
                return
            for i, (r, d, _il) in enumerate(self.relacje):
                if r == self._zaznaczony and d == dziecko:
                    self.relacje[i] = (r, d, nowa)
                    break
            dlg.destroy()
            self._odswiez_sklad()
            self._odswiez_drzewo()
            self._zaznacz_w_drzewie(self._zaznaczony)

        e.bind("<Return>", zapisz)
        pa = tk.Frame(dlg, bg=TLO)
        pa.pack(pady=10)
        tk.Button(pa, text="OK", command=zapisz, width=8).pack(side=tk.LEFT, padx=4)
        tk.Button(pa, text="Anuluj", command=dlg.destroy, width=8).pack(side=tk.LEFT, padx=4)
        wysrodkuj(dlg, self)

    def _usun_skladnik(self):
        wyb = self.tab_sklad.selection()
        if not wyb or not self._zaznaczony:
            return
        dziecko = self.tab_sklad.item(wyb[0], "values")[1]
        for i, (r, d, _il) in enumerate(self.relacje):
            if r == self._zaznaczony and d == dziecko:
                self.relacje.pop(i)
                break
        self._odswiez_sklad()
        self._odswiez_drzewo()
        self._zaznacz_w_drzewie(self._zaznaczony)

    # ── IMPORT Z PROJEKTU ───────────────────────────────────────────────

    def _wczytaj_z_projektu(self):
        messagebox.showinfo(
            "Z projektu",
            "Wczytywanie struktury Z/ZZ z BOM-u projektu RM_BAZA.\n\n"
            "Do podpięcia w kolejnym kroku — subiekt_projekt.build_plan()\n"
            "zwraca dokładnie taką strukturę (pozycje + składniki),\n"
            "więc wystarczy ją przepisać na model pozycje/relacje.",
            parent=self)

    # ── PLAN I ZAPIS ────────────────────────────────────────────────────

    def _zbuduj_plan(self):
        pozycje = []
        for sym, k in self.pozycje.items():
            skl = [{"symbol": d, "ilosc": il} for (r, d, il) in self.relacje if r == sym]
            pozycje.append(k.do_planu(skl if k.czy_komplet() else None))
        return {"pozycje": pozycje}

    def _aktualizuj_przycisk_zapisu(self):
        self.btn_zapisz.config(state=tk.NORMAL if self.pozycje else tk.DISABLED)

    def _waliduj(self):
        """Błędy, które nie mają sensu wysyłać do Subiekta."""
        bledy = []
        for sym, k in self.pozycje.items():
            if not sym.strip():
                bledy.append("pozycja bez symbolu")
            if k.czy_komplet() and not self._dzieci(sym):
                bledy.append(f"„{sym}” to komplet bez składników — Subiekt go odrzuci")
        # Cykl: komplet zawierający sam siebie (choćby pośrednio).
        def cykl(sym, sciezka):
            if sym in sciezka:
                return sym
            for d, _il in self._dzieci(sym):
                z = cykl(d, sciezka | {sym})
                if z:
                    return z
            return None
        for sym in list(self.pozycje):
            z = cykl(sym, set())
            if z:
                bledy.append(f"cykl w składzie: „{z}” zawiera sam siebie")
                break
        return bledy

    def _sprawdz_calosc(self):
        bledy = self._waliduj()
        if bledy:
            messagebox.showwarning("Sprawdzenie", "\n".join(f"• {b}" for b in bledy),
                                   parent=self)
            return
        if not self.pozycje:
            messagebox.showinfo("Sprawdzenie", "Drzewo jest puste.", parent=self)
            return
        self.start_kreciolek("Sprawdzam w Subiekcie")
        threading.Thread(target=self._zapis_worker, args=(self._zbuduj_plan(), False),
                         daemon=True).start()

    def _zapisz_calosc(self):
        bledy = self._waliduj()
        if bledy:
            messagebox.showwarning("Zapis", "\n".join(f"• {b}" for b in bledy), parent=self)
            return
        nowe = sum(1 for k in self.pozycje.values() if not k.w_subiekcie)
        istn = len(self.pozycje) - nowe
        if not messagebox.askyesno(
                "Zapis do Subiekta",
                f"Zapisać do Subiekta?\n\n"
                f"  nowych kartotek:      {nowe}\n"
                f"  istniejących (edycja): {istn}\n"
                f"  kompletów ze składem:  "
                f"{sum(1 for s, k in self.pozycje.items() if k.czy_komplet() and self._dzieci(s))}\n\n"
                "Symbol po zapisie nie podlega zmianie.", parent=self):
            return
        self.start_kreciolek("Zapisuję do Subiekta")
        threading.Thread(target=self._zapis_worker, args=(self._zbuduj_plan(), True),
                         daemon=True).start()

    def _zapis_worker(self, plan, zapisz):
        try:
            wynik, blad = zapisz_kartoteki(plan, zapisz), None
        except Exception as e:
            wynik, blad = None, str(e)
        self.after(0, lambda: self._zapis_gotowy(wynik, blad, zapisz))

    def _zapis_gotowy(self, wynik, blad, zapisz):
        self.stop_kreciolek()
        if blad:
            messagebox.showerror("Subiekt", blad, parent=self)
            return
        kroki = wynik.get("kroki") or []
        bledy = [k for k in kroki if "blad" in str(k.get("Status", ""))]
        self._pokaz_raport(wynik, kroki, bledy, zapisz)
        if zapisz and not bledy:
            # Po udanym zapisie wszystko jest już w Subiekcie — symbole blokujemy.
            for k in self.pozycje.values():
                k.w_subiekcie = True
            self._odswiez_drzewo()

    def _pokaz_raport(self, wynik, kroki, bledy, zapisz):
        okno = tk.Toplevel(self)
        okno.title("Sprawdzenie całości" if not zapisz else "Wynik zapisu")
        okno.configure(bg=TLO)
        okno.geometry("760x520")

        naglowek = (f"założonych: {wynik.get('zalozonych', 0)}   "
                    f"zmienionych: {wynik.get('zmienionych', 0)}   "
                    f"składów: {wynik.get('skladow', 0)}") if zapisz else \
                   f"pozycji w planie: {len(kroki)}"
        tk.Label(okno, text=naglowek, bg=TLO, fg=BLAD_CZERWONY if bledy else OK_ZIELONY,
                 font=("Arial", 10, "bold")).pack(padx=12, pady=(12, 6), anchor="w")

        kol = ("rodzaj", "symbol", "status", "szczegoly")
        tab = ttk.Treeview(okno, columns=kol, show="headings")
        for k, naz, sz in (("rodzaj", "Co", 90), ("symbol", "Symbol", 150),
                           ("status", "Status", 150), ("szczegoly", "Szczegóły", 330)):
            tab.heading(k, text=naz)
            tab.column(k, width=sz)
        tab.tag_configure("blad", foreground=BLAD_CZERWONY)
        tab.tag_configure("ok", foreground=OK_ZIELONY)
        for k in kroki:
            st = str(k.get("Status") or "")
            tag = "blad" if "blad" in st else ("ok" if st in
                  ("zalozona", "zmieniona", "sklad-ustawiony") else "")
            tab.insert("", "end", values=(k.get("Rodzaj"), k.get("Symbol"), st,
                                          k.get("Szczegoly") or ""), tags=(tag,))
        tab.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        tk.Button(okno, text="Zamknij", command=okno.destroy,
                  font=("Arial", 9)).pack(pady=10)
        wysrodkuj(okno, self)


def open_window(parent, symbol=None):
    """Otwiera Edytor kartotek. symbol != None → tryb edycji istniejącej."""
    return EdytorWindow(parent, symbol=symbol)
