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

#: Waga informacji w raporcie zapisu — decyduje o kolorze tla wiersza.
#: Bez tego "bez-zmian" krzyczalo tak samo glosno jak "do-zalozenia".
WAGA_STATUSU = {
    "blad": "uwaga",
    "pominiety-brak-skladnikow": "uwaga",
    "do-zalozenia": "nowe",
    "zalozona": "nowe",
    "do-zmiany": "zmiana",
    "do-ustawienia": "zmiana",
    "zmieniona": "zmiana",
    "sklad-ustawiony": "zmiana",
    "bez-zmian": "info",
}

#: waga → (tlo, kolor tekstu). Tlo, nie sam tekst: wiersz ma byc
#: rozpoznawalny kątem oka, bez czytania kolumny Status.
KOLORY_WAGI = {
    "uwaga":  ("#f9d6d5", "#922b21"),   # czerwone — wymaga reakcji
    "nowe":   ("#d6eaf8", "#1a5276"),   # niebieskie — powstaje nowy byt
    "zmiana": ("#fcf3cf", "#7d6608"),   # zolte — istniejace dane sie zmieniaja
    "info":   ("#ffffff", "#95a5a6"),   # szare — nic sie nie dzieje
}

JEDNOSTKI = ["szt", "kpl", "usl", "m", "mb", "kg", "rbg", "kpl."]

#: Symbole stawek VAT — dopasowywane w Subiekcie po polu Symbol encji
#: StawkaVat. Pusty = „nie ruszaj", kartoteka zostaje z tym, co ma.
STAWKI_VAT = ["", "23", "8", "5", "0", "zw", "np"]

#: Pola własne dostępne w edytorze. PoleWlasne1 CELOWO pominięte —
#: jest zajęte na Położenie magazynowe (regał/półka, patrz MAGAZYN.md),
#: a most i tak odrzuci próbę jego nadpisania.
POLA_WLASNE = [f"PoleWlasne{i}" for i in range(2, 9)]


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
        #: Symbole stawek VAT ("23", "zw"...). Pusty = nie zmieniaj w Subiekcie.
        self.vat_sprzedaz = ""
        self.vat_zakup = ""
        #: {"PoleWlasne2": "Stal nierdzewna", ...} — tylko 2..8.
        self.pola_wlasne = {}
        #: Położenie magazynowe (regał/półka) = PoleWlasne1. None znaczy
        #: "nie było w formularzu, nie ruszaj" — inaczej zapis kartoteki
        #: z pustym polem skasowałby regał wgrany przy migracji magazynu.
        self.polozenie = None
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
        # Puste pola pomijamy — most traktuje brak klucza jako „nie ruszaj",
        # więc nie nadpiszemy przypadkiem tego, co ktoś ustawił w Subiekcie.
        if self.vat_sprzedaz:
            d["vatSprzedaz"] = self.vat_sprzedaz
        if self.vat_zakup:
            d["vatZakup"] = self.vat_zakup
        wypelnione = {k: v for k, v in self.pola_wlasne.items() if v.strip()}
        if wypelnione:
            d["polaWlasne"] = wypelnione
        # Klucz leci tylko gdy pole było wypełniane — patrz komentarz przy
        # self.polozenie. Most tak samo traktuje brak klucza jako "nie ruszaj".
        if self.polozenie is not None:
            d["polozenie"] = self.polozenie
        return d


class EdytorWindow(tk.Toplevel, Kreciolek):
    KOL_SKLAD = [("lp", "Lp.", 40), ("symbol", "Symbol", 130),
                 ("nazwa", "Nazwa", 220), ("ilosc", "Ilość", 70),
                 ("jm", "JM", 50)]
    KOL_LISTA = [("w", "✓", 28), ("symbol", "Symbol", 130), ("nazwa", "Nazwa", 200),
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
        self._zmienione = False  # czy sa niezapisane modyfikacje
        self._dnd_zrodlo = None   # symbol przeciaganej pozycji
        self._dnd_cel = None      # id wezla podswietlonego jako cel
        self._dnd_start_xy = None # punkt nacisniecia - prog na prawdziwy drag
        self._dnd_aktywny = False # True dopiero po ruchu > prog

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
        tk.Button(pasek, text="Anuluj", command=self._anuluj,
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

    def _anuluj(self):
        """Zamknięcie edytora — z ostrzeżeniem, jeśli są niezapisane zmiany."""
        if self._zmienione and not messagebox.askyesno(
                "Zamknąć edytor?",
                "W edytorze są zmiany, których nie zapisano do Subiekta.\n\n"
                "Zamknąć i porzucić je?", parent=self):
            return
        self.destroy()

    def _panel_drzewo(self, rodzic):
        ram = tk.LabelFrame(rodzic, text=" 1. Struktura kartoteki (drzewo) ",
                            bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9, "bold"))
        ram.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 6))
        ram.configure(width=420)
        ram.pack_propagate(False)

        wrap = tk.Frame(ram, bg=TLO_SEKCJI)
        wrap.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        # Wlasny styl TYLKO dla tego drzewa (osobna nazwa, zeby nie ruszyc
        # tabel w reszcie RM_BAZA). Domyslne ~20 px wciecia na poziom bylo
        # za male: przy komplecie w komplecie poziom 2 i 3 wygladaly tak
        # samo i nie dalo sie odczytac, co do czego nalezy.
        styl = ttk.Style()
        try:
            styl.configure("Edytor.Treeview", indent=28, rowheight=22)
        except tk.TclError:
            pass          # starszy Tk bez opcji indent — drzewo dziala dalej
        # "sym" to kolumna ROBOCZA (displaycolumns ja ukrywa): trzyma symbol
        # pozycji, zeby nie wyciagac go z tekstu wiersza. Symbole ze spacja
        # ("DN20 K=34") rozbijaly takie parsowanie i operacje na nich cicho
        # nie dzialaly.
        self.tree = ttk.Treeview(wrap, columns=("ilosc", "sym"), show="tree headings",
                                 selectmode="browse", displaycolumns=("ilosc",),
                                 style="Edytor.Treeview")
        self.tree.heading("#0", text="Symbol / Nazwa")
        self.tree.heading("ilosc", text="Ilość")
        # minwidth wiekszy niz width: kolumna rosnie z oknem, a poziomy pasek
        # pozwala dojechac do konca glebokich wciec zamiast je scinac.
        self.tree.column("#0", width=300, minwidth=300, stretch=True)
        self.tree.column("ilosc", width=60, anchor="e", stretch=False)
        sc = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        sc_poz = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sc.set, xscrollcommand=sc_poz.set)
        sc_poz.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._na_wybor_wezla)
        # Przeciaganie myszą — patrz _dnd_start / _dnd_ruch / _dnd_koniec.
        self.tree.bind("<Button-1>", self._dnd_start, add="+")
        self.tree.bind("<B1-Motion>", self._dnd_ruch)
        self.tree.bind("<ButtonRelease-1>", self._dnd_koniec)

        # Kolory rodzajów — od razu widać komplet vs towar vs usługa.
        self.tree.tag_configure("komplet", foreground="#b9770e")
        self.tree.tag_configure("usluga", foreground="#6c3483")
        self.tree.tag_configure("nowy", foreground=NOWY_NIEBIESKI)
        # Cel przeciagania — podswietlenie w trakcie przenoszenia.
        self.tree.tag_configure("cel_dnd", background="#d4efdf")
        # Rodzic zaznaczonego skladnika - zeby bylo widac, do czego nalezy.
        self.tree.tag_configure("rodzic_zazn", background="#fdf3d0")

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
        # Dokad trafi "+ Skladnik" / "+ Istniejaca" - zawsze widoczne, zeby
        # nie zgadywac. Wynika z zaznaczenia (patrz _cel_dla_skladnika).
        self.lbl_cel = tk.Label(ram, text="", bg="#eaf2f8", fg=TEKST,
                                font=("Arial", 8, "bold"), anchor="w", padx=6)
        self.lbl_cel.pack(fill=tk.X, padx=6, pady=(0, 4))
        tk.Label(ram, text="Przeciaganie: upusc na komplet = wloz do skladu; "
                           "upusc na puste pole pod lista = wyciagnij na wierzch",
                 bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8),
                 wraplength=320, justify="left", anchor="w").pack(
            fill=tk.X, padx=6, pady=(0, 6))

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

        self._karta_handlowe()
        self._karta_magazyn()
        self._karta_dodatkowe()

    def _karta_handlowe(self):
        """Stawki VAT — jedyne pola handlowe, które encja Asortyment ma wprost.

        Cen sprzedaży netto/brutto tu nie ma świadomie: w Subiekcie idą przez
        cenniki (osobny mechanizm), nie przez pole na kartotece.
        """
        f = tk.Frame(self.karty, bg=TLO_SEKCJI)
        self.karty.add(f, text="Handlowe")

        tk.Label(f, text="Domyślne stawki VAT dla dokumentów:", bg=TLO_SEKCJI,
                 fg=TEKST, font=("Arial", 9, "bold"), anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(12, 8))

        self.var_vat_sprzedaz = tk.StringVar()
        self.var_vat_zakup = tk.StringVar()
        for i, (etykieta, zmienna, klucz) in enumerate((
                ("VAT sprzedaży:", self.var_vat_sprzedaz, "vat_sprzedaz"),
                ("VAT zakupu:", self.var_vat_zakup, "vat_zakup")), start=1):
            tk.Label(f, text=etykieta, bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9),
                     anchor="w", width=14).grid(row=i, column=0, sticky="w", padx=8, pady=6)
            cb = ttk.Combobox(f, textvariable=zmienna, values=STAWKI_VAT,
                              width=10, font=("Arial", 9), state="readonly")
            cb.grid(row=i, column=1, sticky="w", padx=4, pady=6)
            cb.bind("<<ComboboxSelected>>", lambda _e, k=klucz: self._pole_zmienione(k))

        tk.Label(f, text="Puste = nie zmieniaj tego, co kartoteka ma w Subiekcie.\n"
                         "Stawka dopasowywana po symbolu — jeśli w słowniku Subiekta\n"
                         "nie ma takiego symbolu, raport zapisu to zgłosi.",
                 bg="#eaf2f8", fg=TEKST_SZARY, font=("Arial", 8),
                 justify="left", anchor="w").grid(
            row=3, column=0, columnspan=2, sticky="we", padx=8, pady=(14, 8))
        f.grid_columnconfigure(1, weight=1)

    def _karta_magazyn(self):
        """Położenie (regał/półka). Progi min/opt zostają w oknie Magazyn."""
        f = tk.Frame(self.karty, bg=TLO_SEKCJI)
        self.karty.add(f, text="Magazyn")

        tk.Label(f, text="Położenie (regał / półka):", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9, "bold"), anchor="w").grid(
            row=0, column=0, sticky="w", padx=8, pady=(14, 4))
        self.var_polozenie = tk.StringVar()
        tk.Entry(f, textvariable=self.var_polozenie, font=("Arial", 10),
                 width=28).grid(row=0, column=1, sticky="we", padx=4, pady=(14, 4))
        self.var_polozenie.trace_add(
            "write", lambda *_a: self._pole_zmienione("polozenie"))

        tk.Label(f, text="Siedzi w polu własnym PoleWlasne1 — tym samym, które\n"
                         "pokazuje kolumna Położenie w oknie Magazyn.\n"
                         "Puste pole NIE kasuje regału: żeby wyczyścić położenie,\n"
                         "trzeba je skasować w Subiekcie.",
                 bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8),
                 justify="left", anchor="w").grid(
            row=1, column=0, columnspan=2, sticky="we", padx=8, pady=(2, 12))

        tk.Label(f, text="Progi zamawiania (min/opt) ustawia się w oknie Magazyn\n"
                         "— ma własny tryb mostu i widok całej listy naraz.\n\n"
                         "Masy i objętości encja Asortyment w Sferze NIE MA —\n"
                         "nie da się ich tu zapisać.",
                 bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 9),
                 justify="left", anchor="w").grid(
            row=2, column=0, columnspan=2, sticky="we", padx=8, pady=8)
        f.grid_columnconfigure(1, weight=1)

    def _karta_dodatkowe(self):
        """Proste pola własne 2..8 — na parametry konstrukcyjne."""
        f = tk.Frame(self.karty, bg=TLO_SEKCJI)
        self.karty.add(f, text="Dodatkowe")

        tk.Label(f, text="Pola własne kartoteki (materiał, gwint, certyfikat…):",
                 bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9, "bold"), anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(12, 8))

        self.pola_wlasne_var = {}
        for i, pole in enumerate(POLA_WLASNE, start=1):
            tk.Label(f, text=f"{pole}:", bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9),
                     anchor="w", width=14).grid(row=i, column=0, sticky="w", padx=8, pady=4)
            v = tk.StringVar()
            tk.Entry(f, textvariable=v, font=("Arial", 9), width=36).grid(
                row=i, column=1, sticky="we", padx=4, pady=4)
            v.trace_add("write", lambda *_a, p=pole: self._pole_wlasne_zmienione(p))
            self.pola_wlasne_var[pole] = v

        tk.Label(f, text="PoleWlasne1 jest zajęte na Położenie magazynowe (regał/półka)\n"
                         "i dlatego nie ma go na tej liście — most odrzuca próby nadpisania.",
                 bg="#fdf2e9", fg=TEKST_SZARY, font=("Arial", 8),
                 justify="left", anchor="w").grid(
            row=len(POLA_WLASNE) + 1, column=0, columnspan=2, sticky="we", padx=8, pady=(14, 8))
        f.grid_columnconfigure(1, weight=1)

    def _panel_sklad_i_lista(self, rodzic):
        ram = tk.Frame(rodzic, bg=TLO)
        ram.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        gora = tk.LabelFrame(ram, text=" 3. Skład kompletu ", bg=TLO_SEKCJI,
                             fg=TEKST, font=("Arial", 9, "bold"))
        gora.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.lbl_sklad = tk.Label(gora, text="(zaznacz komplet w drzewie)",
                                  bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8), anchor="w")
        self.lbl_sklad.pack(fill=tk.X, padx=6, pady=(4, 0))
        wrap_s = tk.Frame(gora, bg=TLO_SEKCJI)
        wrap_s.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self.tab_sklad = ttk.Treeview(wrap_s, columns=[k[0] for k in self.KOL_SKLAD],
                                      show="headings", height=7)
        for klucz, naglowek, szer in self.KOL_SKLAD:
            self.tab_sklad.heading(klucz, text=naglowek)
            self.tab_sklad.column(klucz, width=szer, minwidth=szer,
                                  anchor="e" if klucz in ("lp", "ilosc") else "w")
        sc_s = ttk.Scrollbar(wrap_s, orient="vertical", command=self.tab_sklad.yview)
        sc_s_poz = ttk.Scrollbar(wrap_s, orient="horizontal", command=self.tab_sklad.xview)
        self.tab_sklad.configure(yscrollcommand=sc_s.set, xscrollcommand=sc_s_poz.set)
        sc_s_poz.pack(side=tk.BOTTOM, fill=tk.X)
        self.tab_sklad.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc_s.pack(side=tk.RIGHT, fill=tk.Y)
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

        wrap_l = tk.Frame(dol, bg=TLO_SEKCJI)
        wrap_l.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self.tab_lista = ttk.Treeview(wrap_l, columns=[k[0] for k in self.KOL_LISTA],
                                      show="headings", height=8)
        for klucz, naglowek, szer in self.KOL_LISTA:
            self.tab_lista.heading(klucz, text=naglowek)
            self.tab_lista.column(klucz, width=szer, minwidth=szer,
                                  anchor="e" if klucz == "cena" else "w")
        sc_l = ttk.Scrollbar(wrap_l, orient="vertical", command=self.tab_lista.yview)
        sc_l_poz = ttk.Scrollbar(wrap_l, orient="horizontal", command=self.tab_lista.xview)
        self.tab_lista.configure(yscrollcommand=sc_l.set, xscrollcommand=sc_l_poz.set)
        sc_l_poz.pack(side=tk.BOTTOM, fill=tk.X)
        self.tab_lista.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc_l.pack(side=tk.RIGHT, fill=tk.Y)
        self.tab_lista.tag_configure("w_drzewie", foreground=TEKST_SZARY)
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
        """Przebudowa listy 4 - WSZYSTKIE kartoteki, filtr zaweza.

        Byl tu limit 400 wierszy i robil zludzenie "pozycja zniknela":
        po skasowaniu wyszukiwania dodana kartoteka byla poza pierwsza
        czterysetka. 3469 wierszy to dla Treeview ulamek sekundy.
        """
        szukaj = (self.var_szukaj.get() or "").strip().lower()
        for w in self.tab_lista.get_children():
            self.tab_lista.delete(w)
        for k in self.katalog:
            sym = str(k.get("Symbol") or "").strip()
            naz = str(k.get("Nazwa") or "").strip()
            if szukaj and szukaj not in sym.lower() and szukaj not in naz.lower():
                continue
            w_drzewie = sym in self.pozycje
            self.tab_lista.insert("", "end", values=(
                "✓" if w_drzewie else "", sym, naz, k.get("Rodzaj") or "",
                f"{float(k.get('CenaEwidencyjna') or 0):g}"),
                tags=("w_drzewie",) if w_drzewie else ())

    def _oznacz_w_liscie(self):
        """Aktualizuje TYLKO fajki i szarosc na liscie 4, bez przebudowy.

        Wolane przy kazdym odswiezeniu drzewa - przebudowa 3469 wierszy przy
        kazdym wpisanym znaku w polu Nazwa bylaby odczuwalna, zmiana tagow nie.
        Nie ukrywamy pozycji bedacych w drzewie: ta sama kartoteka moze isc
        do drugiego kompletu (model grafowy).
        """
        for w in self.tab_lista.get_children():
            wartosci = list(self.tab_lista.item(w, "values"))
            if len(wartosci) < 2:
                continue
            w_drzewie = wartosci[1] in self.pozycje
            fajka = "✓" if w_drzewie else ""
            if wartosci[0] != fajka:
                wartosci[0] = fajka
                self.tab_lista.item(w, values=wartosci,
                                    tags=("w_drzewie",) if w_drzewie else ())

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
        k = Kartoteka(symbol, dane.get("Nazwa") or symbol, rodzaj,
                      opis=str(dane.get("Opis") or "").strip(),
                      w_subiekcie=True)
        # Polozenie pokazujemy takie, jakie jest w Subiekcie, ale zostawiamy
        # None dopoki user go nie tknie — plan wysyla klucz tylko przy zmianie.
        k.polozenie = str(dane.get("Polozenie") or "").strip() or None
        self.pozycje[symbol] = k
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
        for w in self.tree.get_children(""):
            self.tree.delete(w)
        for sym in self.korzenie:
            self._wstaw_wezel("", sym, None, set())
        # Rozwijamy CALE drzewo, nie tylko poziom 0. Wczesniej komplet
        # przeciagniety do innego kompletu zostawal zwiniety i jego sklad
        # znikal z widoku — wygladalo to na zgubienie skladnikow.
        self._rozwin_wszystko()
        self._aktualizuj_przycisk_zapisu()
        self._odswiez_etykiete_celu()
        self._oznacz_w_liscie()

    def _rozwin_wszystko(self, rodzic=""):
        """Rozwija kazda galaz. Struktura jest tu mala, a sens tego okna
        to widziec caly sklad naraz."""
        for i in self.tree.get_children(rodzic):
            self.tree.item(i, open=True)
            self._rozwin_wszystko(i)

    def _wstaw_wezel(self, rodzic_id, symbol, ilosc, sciezka):
        k = self.pozycje.get(symbol)
        if k is None:
            return
        # Cykl (A zawiera B, B zawiera A) — pokazujemy i przerywamy, zamiast
        # zapętlić GUI. Sam Subiekt też takiego składu nie przyjmie.
        if symbol in sciezka:
            self.tree.insert(rodzic_id, "end", text=f"⟲ {symbol} (cykl!)",
                             values=("", symbol))
            return
        tagi = [k.rodzaj]
        if not k.w_subiekcie:
            tagi.append("nowy")
        # Bez wlasnego prefiksu glebokosci: dublowal sie z wcieciami Treeview
        # i robil balagan. Czytelnosc zalatwia szerszy panel + poziomy pasek.
        wid = self.tree.insert(
            rodzic_id, "end",
            text=f"{SKROT.get(k.rodzaj, '??')} {symbol}   {k.nazwa}",
            values=(f"x{ilosc:g}" if ilosc else "", symbol), tags=tuple(tagi))
        for dziecko, il in self._dzieci(symbol):
            self._wstaw_wezel(wid, dziecko, il, sciezka | {symbol})

    def _symbol_wezla(self, item=None):
        item = item or (self.tree.selection() or [None])[0]
        if not item:
            return None
        wartosci = self.tree.item(item, "values")
        return wartosci[1] if len(wartosci) > 1 and wartosci[1] else None

    def _podswietl_rodzica(self):
        """Zolte tlo na komplecie-rodzicu zaznaczonego wiersza."""
        for i in self.tree.get_children(""):
            self._wyczysc_rodzica(i)
        item = (self.tree.selection() or [None])[0]
        if not item:
            return
        rodzic = self.tree.parent(item)
        if rodzic:
            self._odswiez_tagi(rodzic, dodaj_cel=False, rodzic_zazn=True)

    def _wyczysc_rodzica(self, item):
        tagi = self.tree.item(item, "tags")
        if "rodzic_zazn" in tagi:
            self._odswiez_tagi(item, dodaj_cel=False)
        for c in self.tree.get_children(item):
            self._wyczysc_rodzica(c)

    def _na_wybor_wezla(self, _e=None):
        self._podswietl_rodzica()
        sym = self._symbol_wezla()
        if not sym or sym not in self.pozycje:
            return
        self._zaznaczony = sym
        k = self.pozycje[sym]
        self._odswiez_etykiete_celu()
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
            self.var_vat_sprzedaz.set(k.vat_sprzedaz or "")
            self.var_vat_zakup.set(k.vat_zakup or "")
            for pole, v in self.pola_wlasne_var.items():
                v.set(k.pola_wlasne.get(pole, ""))
            self.var_polozenie.set(k.polozenie or "")
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
        elif klucz == "vat_sprzedaz":
            k.vat_sprzedaz = self.var_vat_sprzedaz.get().strip()
        elif klucz == "vat_zakup":
            k.vat_zakup = self.var_vat_zakup.get().strip()
        elif klucz == "polozenie":
            # Pusty tekst zapisujemy jako None ("nie ruszaj"), nie jako "".
            tekst = self.var_polozenie.get().strip()
            k.polozenie = tekst or None
            self._zmienione = True
        self._odswiez_drzewo()
        self._zaznacz_w_drzewie(k.symbol)

    def _pole_wlasne_zmienione(self, pole):
        if self._blokada or not self._zaznaczony:
            return
        k = self.pozycje.get(self._zaznaczony)
        if k is None:
            return
        k.pola_wlasne[pole] = self.pola_wlasne_var[pole].get()
        self._zmienione = True

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

    # ── PRZECIAGANIE MYSZA ──────────────────────────────────────────────
    #
    # Zasada: przeciagniecie pozycji NA KOMPLET wklada ja do jego skladu,
    # przeciagniecie na puste miejsce wyciaga ja na poziom glowny.
    # Przenosimy WYSTAPIENIE (relacje), nie kartoteke — ta sama pozycja moze
    # dalej byc w innych kompletach.

    #: Ile pikseli trzeba przesunac mysz, zanim klikniecie stanie sie
    #: przeciaganiem. Bez tego progu kazde drgniecie przy kliknieciu bylo
    #: traktowane jak drag i wyciagalo skladniki z kompletow.
    DND_PROG_PX = 8

    def _dnd_start(self, event):
        item = self.tree.identify_row(event.y)
        self._dnd_zrodlo = self._symbol_wezla(item) if item else None
        self._dnd_zrodlo_item = item
        self._dnd_cel = None
        self._dnd_start_xy = (event.x, event.y)
        self._dnd_aktywny = False

    def _dnd_ruch(self, event):
        if not self._dnd_zrodlo or not self._dnd_start_xy:
            return
        if not self._dnd_aktywny:
            dx = abs(event.x - self._dnd_start_xy[0])
            dy = abs(event.y - self._dnd_start_xy[1])
            if dx < self.DND_PROG_PX and dy < self.DND_PROG_PX:
                return                      # to jeszcze klikniecie, nie drag
            self._dnd_aktywny = True
        self.tree.config(cursor="hand2")
        cel_item = self.tree.identify_row(event.y)
        if cel_item == self._dnd_cel:
            return
        # Zdejmujemy poprzednie podswietlenie.
        if self._dnd_cel:
            self._odswiez_tagi(self._dnd_cel, dodaj_cel=False)
        self._dnd_cel = None
        if not cel_item or cel_item == self._dnd_zrodlo_item:
            return
        cel_sym = self._symbol_wezla(cel_item)
        # Podswietlamy tylko komplety — reszta i tak nie przyjmie skladnika.
        if cel_sym and cel_sym in self.pozycje and self.pozycje[cel_sym].czy_komplet():
            self._dnd_cel = cel_item
            self._odswiez_tagi(cel_item, dodaj_cel=True)

    def _odswiez_tagi(self, item, dodaj_cel, rodzic_zazn=False):
        """Dokłada/zdejmuje tag podswietlenia, nie gubiac tagow rodzaju."""
        sym = self._symbol_wezla(item)
        k = self.pozycje.get(sym) if sym else None
        if k is None:
            return
        tagi = [k.rodzaj]
        if not k.w_subiekcie:
            tagi.append("nowy")
        if dodaj_cel:
            tagi.append("cel_dnd")
        if rodzic_zazn:
            tagi.append("rodzic_zazn")
        try:
            self.tree.item(item, tags=tuple(tagi))
        except Exception:
            pass

    def _dnd_koniec(self, event):
        self.tree.config(cursor="")
        zrodlo, cel_item = self._dnd_zrodlo, self._dnd_cel
        zrodlo_item = getattr(self, "_dnd_zrodlo_item", None)
        aktywny = self._dnd_aktywny
        self._dnd_zrodlo = self._dnd_cel = self._dnd_start_xy = None
        self._dnd_aktywny = False
        if cel_item:
            self._odswiez_tagi(cel_item, dodaj_cel=False)
        # Nie bylo prawdziwego przeciagania -> to bylo klikniecie. Koniec.
        if not aktywny or not zrodlo or not zrodlo_item:
            return

        pod_kursorem = self.tree.identify_row(event.y)
        if pod_kursorem == zrodlo_item:
            return

        stary_rodzic_item = self.tree.parent(zrodlo_item)
        stary_rodzic = self._symbol_wezla(stary_rodzic_item) if stary_rodzic_item else None

        if cel_item:
            nowy_rodzic = self._symbol_wezla(cel_item)
        elif not pod_kursorem:
            nowy_rodzic = None               # puste pole pod lista = na wierzch
        else:
            # Upuszczono na zwykly towar - to NIE jest cel. Nic nie robimy,
            # zeby drgniecie myszy nie rozwalalo struktury.
            self.status.config(
                text="Upusc na KOMPLET (wloz do skladu) albo na puste pole "
                     "pod lista (wyciagnij na wierzch)", fg=TEKST_SZARY)
            return

        if nowy_rodzic == stary_rodzic:
            return
        # Do samego siebie ani do wlasnego potomka — zrobiloby cykl.
        if nowy_rodzic and (nowy_rodzic == zrodlo or self._czy_potomek(zrodlo, nowy_rodzic)):
            messagebox.showwarning(
                "Przenoszenie",
                "Nie mozna wlozyc pozycji do niej samej ani do jej wlasnego skladnika "
                "- powstalby cykl, ktorego Subiekt nie przyjmie.", parent=self)
            return
        if nowy_rodzic and any(r == nowy_rodzic and d == zrodlo for (r, d, _i) in self.relacje):
            messagebox.showinfo(
                "Przenoszenie",
                "Pozycja \"" + zrodlo + "\" jest juz w skladzie \"" + nowy_rodzic + "\".",
                parent=self)
            return

        # Odpinamy od starego miejsca.
        ilosc = 1.0
        if stary_rodzic:
            for i, (r, d, il) in enumerate(self.relacje):
                if r == stary_rodzic and d == zrodlo:
                    ilosc = il
                    self.relacje.pop(i)
                    break
        elif zrodlo in self.korzenie:
            self.korzenie.remove(zrodlo)

        # Podpinamy w nowym - NA POCZATKU skladu, nie na koncu. Doklejenie
        # na koniec wygladalo jak "pozycja wypadla poza drzewko": gdy cel jest
        # korzeniem, jego ostatnie dziecko jest ostatnim wierszem calej listy.
        if nowy_rodzic:
            wstaw = len(self.relacje)
            for i, (r, _d, _il) in enumerate(self.relacje):
                if r == nowy_rodzic:
                    wstaw = i
                    break
            self.relacje.insert(wstaw, (nowy_rodzic, zrodlo, ilosc))
            self.status.config(
                text="Przeniesiono \"" + zrodlo + "\" do skladu \"" + nowy_rodzic + "\"",
                fg=TEKST_SZARY)
        else:
            if zrodlo not in self.korzenie:
                self.korzenie.append(zrodlo)
            self.status.config(
                text="Pozycja \"" + zrodlo + "\" wyciagnieta na poziom glowny",
                fg=TEKST_SZARY)

        self._zmienione = True
        self._odswiez_drzewo()
        self._zaznacz_w_drzewie(zrodlo)

    def _czy_potomek(self, przodek, szukany):
        """Czy `szukany` jest gdzies w skladzie `przodek` (dowolnie gleboko)."""
        odwiedzone = set()

        def idz(sym):
            if sym in odwiedzone:
                return False
            odwiedzone.add(sym)
            for dziecko, _il in self._dzieci(sym):
                if dziecko == szukany or idz(dziecko):
                    return True
            return False

        return idz(przodek)

    def _cel_dla_skladnika(self):
        """Komplet, do ktorego trafi nowy skladnik - WYLACZNIE z zaznaczenia.

        Zaznaczony komplet -> on sam. Zaznaczony skladnik -> komplet, w ktorym
        siedzi (jestes "w srodku" tego kompletu, wiec tam dokladasz). Korzen
        niebedacy kompletem -> brak celu. Zadnej ukrytej pamieci: to, co widac
        na etykiecie pod drzewem, jest jedyna prawda.
        """
        item = (self.tree.selection() or [None])[0]
        sym = self._symbol_wezla(item) if item else None
        if sym and sym in self.pozycje and self.pozycje[sym].czy_komplet():
            return sym
        rodzic_item = self.tree.parent(item) if item else ""
        rodzic = self._symbol_wezla(rodzic_item) if rodzic_item else None
        if rodzic and rodzic in self.pozycje and self.pozycje[rodzic].czy_komplet():
            return rodzic
        # Swiadomie NIE zgadujemy celu, gdy z zaznaczenia nic nie wynika.
        # Wczesniej "jedyny komplet w drzewie" byl domyslnym celem i swiezo
        # dodane kartoteki same wchodzily do srodka. Nowe maja lezec luzno
        # na dole; do skladu wklada sie je przeciagnieciem albo majac
        # zaznaczony komplet.
        return None

    def _odswiez_etykiete_celu(self):
        cel = self._cel_dla_skladnika()
        if not hasattr(self, "lbl_cel"):
            return
        if cel:
            self.lbl_cel.config(text="+ Skladnik / + Istniejaca  ->  do skladu: " + cel,
                                fg=TEKST)
        else:
            self.lbl_cel.config(text="+ Skladnik / + Istniejaca  ->  na dol, luzno "
                                     "(zaznacz komplet, zeby dodawac do srodka; "
                                     "luzne wciagniesz przeciagnieciem)",
                                fg=TEKST_SZARY)

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
        rodzic = self._cel_dla_skladnika()
        if not rodzic:
            wskazany = self._symbol_wezla()
            if wskazany and wskazany in self.pozycje:
                messagebox.showwarning(
                    "Edytor",
                    "Pozycja \"" + wskazany + "\" to " + self.pozycje[wskazany].rodzaj
                    + " - skladniki mozna dodawac tylko do pozycji rodzaju Komplet.\n\n"
                    "Zmien Rodzaj na Komplet (Z) albo zaznacz w drzewie inny komplet.",
                    parent=self)
            else:
                messagebox.showinfo(
                    "Edytor", "Zaznacz najpierw komplet w drzewie.", parent=self)
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
        _w, sym, naz, rodzaj, cena = self.tab_lista.item(wyb[0], "values")
        rodzaj_n = ("komplet" if "omplet" in rodzaj else
                    "usluga" if "sług" in rodzaj or "slug" in rodzaj else "towar")
        if sym not in self.pozycje:
            try:
                cena_f = float(str(cena).replace(",", ".") or 0)
            except ValueError:
                cena_f = 0.0
            self.pozycje[sym] = Kartoteka(sym, naz, rodzaj_n, cena=cena_f, w_subiekcie=True)

        rodzic = self._cel_dla_skladnika()
        if rodzic:
            # Ten sam skladnik moze byc w komplecie tylko raz - drugie dodanie
            # byloby duplikatem w skladzie (dokladnie ten blad naprawialismy
            # w kartotekach Subiekta 06.09.2026).
            if any(r == rodzic and d == sym for (r, d, _il) in self.relacje):
                messagebox.showinfo(
                    "Edytor",
                    "Pozycja \"" + sym + "\" jest juz w skladzie \"" + rodzic + "\".\n\n"
                    "Ilosc zmienia sie dwuklikiem w sekcji 3.", parent=self)
                return
            self.relacje.append((rodzic, sym, 1.0))
            self.status.config(
                text="Dodano \"" + sym + "\" do skladu \"" + rodzic + "\"", fg=TEKST_SZARY)
        else:
            if sym not in self.korzenie and not any(
                    d == sym for (_r, d, _il) in self.relacje):
                self.korzenie.append(sym)
            self.status.config(
                text="Pozycja \"" + sym + "\" dodana jako osobna - w drzewie nie byl "
                     "zaznaczony zaden komplet", fg=TEKST_SZARY)
        self._zmienione = True
        # Zaznaczenie ZOSTAJE tam gdzie bylo: jesli dodawales do kompletu,
        # kolejny dwuklik trafi do tego samego kompletu; jesli dokladasz
        # luzne pozycje, kolejne tez leca na dol. Wczesniejsze przeskakiwanie
        # zaznaczenia na dodana pozycje cicho zmienialo cel dodawania.
        zachowane = self._zaznaczony
        self._odswiez_drzewo()
        if zachowane and zachowane in self.pozycje:
            self._zaznacz_w_drzewie(zachowane)

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
            dzieci = [d for (r, d, _il) in self.relacje if r == sym]
            self.relacje = [(r, d, il) for (r, d, il) in self.relacje
                            if r != sym and d != sym]
            # Skladniki usunietego kompletu, ktorych nie ma nigdzie indziej,
            # wychodza NA WIERZCH. Wczesniej zostawaly w `pozycje` jako duchy:
            # niewidoczne w drzewie, ale przy zapisie poszlyby do Subiekta
            # jako osobne kartoteki. Teraz je widac i mozna usunac osobno.
            for d in dzieci:
                nadal_uzyty = any(dd == d for (_r, dd, _i) in self.relacje)
                if not nadal_uzyty and d not in self.korzenie and d in self.pozycje:
                    self.korzenie.append(d)
            uzyta = any(d == sym for (_r, d, _i) in self.relacje)
            if not uzyta and sym in self.pozycje:
                del self.pozycje[sym]
        self._zaznaczony = None
        self._zmienione = True
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
        if not self.pozycje:
            messagebox.showinfo("Zapis", "Drzewo jest puste.", parent=self)
            return
        # Potwierdzenie w osobnym oknie, nie w messageboxie: trzy liczby nie
        # mowily, JAK sie kartoteki nazywaja ani co wejdzie w sklad kompletu,
        # a symbol po zapisie jest juz nie do zmiany.
        if not self._potwierdz_zapis():
            return
        self.start_kreciolek("Zapisuję do Subiekta")
        threading.Thread(target=self._zapis_worker, args=(self._zbuduj_plan(), True),
                         daemon=True).start()

    def _potwierdz_zapis(self):
        """Okno z pelna struktura do zapisu. True = user potwierdzil."""
        okno = tk.Toplevel(self)
        okno.title("Zapis do Subiekta — podsumowanie")
        okno.configure(bg=TLO)
        okno.geometry("820x620")
        okno.transient(self)

        nowe = [k for k in self.pozycje.values() if not k.w_subiekcie]
        istn = [k for k in self.pozycje.values() if k.w_subiekcie]
        komplety = [s for s, k in self.pozycje.items()
                    if k.czy_komplet() and self._dzieci(s)]

        tk.Label(okno, text="Co trafi do Subiekta", bg=TLO, fg=TEKST,
                 font=("Arial", 13, "bold"), anchor="w").pack(
            fill=tk.X, padx=14, pady=(12, 2))

        pas = tk.Frame(okno, bg=TLO)
        pas.pack(fill=tk.X, padx=14, pady=(0, 8))
        for etykieta, ile, kolor in (
                ("nowych kartotek", len(nowe), NOWY_NIEBIESKI),
                ("istniejących (edycja)", len(istn), TEKST),
                ("kompletów ze składem", len(komplety), TEKST)):
            ramka = tk.Frame(pas, bg=TLO_SEKCJI, bd=1, relief="solid")
            ramka.pack(side=tk.LEFT, padx=(0, 8))
            tk.Label(ramka, text=str(ile), bg=TLO_SEKCJI, fg=kolor,
                     font=("Arial", 18, "bold")).pack(padx=16, pady=(6, 0))
            tk.Label(ramka, text=etykieta, bg=TLO_SEKCJI, fg=TEKST_SZARY,
                     font=("Arial", 8)).pack(padx=16, pady=(0, 6))

        wrap = tk.Frame(okno, bg=TLO_SEKCJI)
        wrap.pack(fill=tk.BOTH, expand=True, padx=14, pady=4)
        kol = ("nazwa", "ilosc", "co")
        tab = ttk.Treeview(wrap, columns=kol, show="tree headings",
                           style="Edytor.Treeview")
        tab.heading("#0", text="Symbol")
        tab.heading("nazwa", text="Nazwa")
        tab.heading("ilosc", text="Ilość")
        tab.heading("co", text="Co się stanie")
        tab.column("#0", width=230, minwidth=230, stretch=True)
        tab.column("nazwa", width=250, minwidth=180)
        tab.column("ilosc", width=55, anchor="e", stretch=False)
        tab.column("co", width=150, minwidth=150)
        tab.tag_configure("nowa", foreground=NOWY_NIEBIESKI)
        tab.tag_configure("komplet", font=("Arial", 9, "bold"))
        sc = ttk.Scrollbar(wrap, orient="vertical", command=tab.yview)
        sc_poz = ttk.Scrollbar(wrap, orient="horizontal", command=tab.xview)
        tab.configure(yscrollcommand=sc.set, xscrollcommand=sc_poz.set)
        sc_poz.pack(side=tk.BOTTOM, fill=tk.X)
        tab.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)

        def wstaw(rodzic_id, symbol, ilosc, sciezka):
            k = self.pozycje.get(symbol)
            if k is None or symbol in sciezka:
                return
            dzieci = self._dzieci(symbol)
            if k.czy_komplet():
                co = ("zostanie założony" if not k.w_subiekcie
                      else "skład zostanie ustawiony")
                co += f" — {len(dzieci)} skl."
            else:
                co = "zostanie założona" if not k.w_subiekcie else "edycja danych"
            tagi = []
            if not k.w_subiekcie:
                tagi.append("nowa")
            if k.czy_komplet():
                tagi.append("komplet")
            wid = tab.insert(
                rodzic_id, "end", text=f"{SKROT.get(k.rodzaj, '??')}  {symbol}",
                values=(k.nazwa, f"x{ilosc:g}" if ilosc else "", co),
                tags=tuple(tagi), open=True)
            for dziecko, il in dzieci:
                wstaw(wid, dziecko, il, sciezka | {symbol})

        for sym in self.korzenie:
            wstaw("", sym, None, set())

        tk.Label(okno, text="Symbol po zapisie NIE podlega zmianie — sprawdź, czy "
                            "komplety nie zostały z roboczą nazwą typu \u201eNOWA-01\u201d.",
                 bg="#fdf2e9", fg=TEKST, font=("Arial", 9), justify="left",
                 anchor="w", wraplength=780).pack(fill=tk.X, padx=14, pady=(8, 4))

        wynik = {"ok": False}

        def zatwierdz():
            wynik["ok"] = True
            okno.destroy()

        pb = tk.Frame(okno, bg=TLO)
        pb.pack(fill=tk.X, padx=14, pady=(4, 12))
        tk.Button(pb, text="Zapisz do Subiekta", command=zatwierdz,
                  bg=OK_ZIELONY, fg="white", font=("Arial", 10, "bold"),
                  padx=14, pady=4).pack(side=tk.RIGHT)
        tk.Button(pb, text="Anuluj", command=okno.destroy,
                  font=("Arial", 10), padx=14, pady=4).pack(side=tk.RIGHT, padx=8)

        wysrodkuj(okno, self)
        okno.grab_set()
        self.wait_window(okno)
        return wynik["ok"]

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
            self._zmienione = False
            self._odswiez_drzewo()
            self.status.config(
                text=f"✔ Zapisano do Subiekta: założonych {wynik.get('zalozonych', 0)}, "
                     f"zmienionych {wynik.get('zmienionych', 0)}, "
                     f"składów {wynik.get('skladow', 0)}",
                fg=OK_ZIELONY)

    def _pokaz_raport(self, wynik, kroki, bledy, zapisz):
        okno = tk.Toplevel(self)
        okno.title("Sprawdzenie całości" if not zapisz else "Wynik zapisu")
        okno.configure(bg=TLO)
        okno.geometry("760x520")

        # Waga kazdego statusu — decyduje o kolorze tla wiersza.
        wagi = [WAGA_STATUSU.get(str(k.get("Status") or ""), "info") for k in kroki]
        ile = {w: wagi.count(w) for w in ("uwaga", "nowe", "zmiana", "info")}

        naglowek = (f"założonych: {wynik.get('zalozonych', 0)}   "
                    f"zmienionych: {wynik.get('zmienionych', 0)}   "
                    f"składów: {wynik.get('skladow', 0)}") if zapisz else \
                   f"pozycji w planie: {len(kroki)}"
        tk.Label(okno, text=naglowek, bg=TLO, fg=BLAD_CZERWONY if bledy else OK_ZIELONY,
                 font=("Arial", 10, "bold")).pack(padx=12, pady=(12, 2), anchor="w")

        # Legenda — przy dlugiej liscie mowi od razu, czy cos wymaga uwagi,
        # bez przegladania wiersz po wierszu. Puste grupy pomijamy.
        leg = tk.Frame(okno, bg=TLO)
        leg.pack(fill=tk.X, padx=12, pady=(0, 6))
        for waga, etykieta in (("uwaga", "wymaga uwagi"), ("nowe", "nowe w Subiekcie"),
                               ("zmiana", "zmiana danych"), ("info", "bez zmian")):
            if not ile.get(waga):
                continue
            tlo, kolor = KOLORY_WAGI[waga]
            tk.Label(leg, text=f"  {ile[waga]} — {etykieta}  ", bg=tlo, fg=kolor,
                     font=("Arial", 8, "bold"), bd=1, relief="solid").pack(
                side=tk.LEFT, padx=(0, 6))

        wrap_r = tk.Frame(okno, bg=TLO_SEKCJI)
        wrap_r.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        kol = ("rodzaj", "symbol", "status", "szczegoly")
        tab = ttk.Treeview(wrap_r, columns=kol, show="headings",
                           style="Edytor.Treeview")
        for k, naz, sz in (("rodzaj", "Co", 90), ("symbol", "Symbol", 150),
                           ("status", "Status", 150), ("szczegoly", "Szczegóły", 330)):
            tab.heading(k, text=naz)
            tab.column(k, width=sz, minwidth=sz)
        for waga, (tlo, kolor) in KOLORY_WAGI.items():
            tab.tag_configure(waga, background=tlo, foreground=kolor)
        tab.tag_configure("uwaga", background=KOLORY_WAGI["uwaga"][0],
                          foreground=KOLORY_WAGI["uwaga"][1],
                          font=("Arial", 9, "bold"))
        sc_r = ttk.Scrollbar(wrap_r, orient="vertical", command=tab.yview)
        sc_r_poz = ttk.Scrollbar(wrap_r, orient="horizontal", command=tab.xview)
        tab.configure(yscrollcommand=sc_r.set, xscrollcommand=sc_r_poz.set)
        sc_r_poz.pack(side=tk.BOTTOM, fill=tk.X)
        tab.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc_r.pack(side=tk.RIGHT, fill=tk.Y)

        for k, waga in zip(kroki, wagi):
            tab.insert("", "end", values=(k.get("Rodzaj"), k.get("Symbol"),
                                          str(k.get("Status") or ""),
                                          k.get("Szczegoly") or ""), tags=(waga,))
        tk.Button(okno, text="Zamknij", command=okno.destroy,
                  font=("Arial", 9)).pack(pady=10)
        wysrodkuj(okno, self)


def open_window(parent, symbol=None):
    """Otwiera Edytor kartotek. symbol != None → tryb edycji istniejącej."""
    return EdytorWindow(parent, symbol=symbol)
