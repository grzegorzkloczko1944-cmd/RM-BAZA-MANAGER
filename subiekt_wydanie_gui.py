# -*- coding: utf-8 -*-
"""Okno magazyniera — wydanie materiału z magazynu na projekt.

    import subiekt_wydanie_gui
    subiekt_wydanie_gui.open_window(parent, project_id, project_name)

Skan kodu → sesja pozycji → JEDNO RW ze wszystkimi pozycjami.

SKĄD CO SIĘ BIERZE (RM_BAZA_OKNO_WYDANIA_RW_PLAN.md §1)
-------------------------------------------------------
    POTRZEBA          Subiekt: ZK dla zakupów, PW dla produkcji własnej
    STAN, LOKACJA     Subiekt
    WYDANO WCZEŚNIEJ  dokumenty RW tego projektu

Całe okno operuje na FAKTACH z Subiekta, nie na założeniach konstrukcyjnych:
ZK mówi, co trzeba wydać z zakupów, PW co przyjęto z własnej produkcji, RW co
już wyszło. BOM zostaje źródłem konstrukcyjnym, ale nie licznikiem magazynowym.

⚠️ `delivered_qty` NIE JEST RUSZANE. To pole ma stare znaczenie „dostarczono
od dostawcy" i zasila arkusz główny oraz stary skaner. Wydania magazynowe to
inny fakt — trzymanie obu w jednej kolumnie zrobiłoby z niej liczbę bez
znaczenia.

BEZ LOCKA PROJEKTU
------------------
Skanowanie i wydawanie nie zapisuje NIC do bazy projektu — powstaje wyłącznie
dokument w Subiekcie. Dlatego dwóch magazynierów może pracować równocześnie na
tym samym projekcie; kolizję wykrywa ponowny odczyt przed zapisem (punkt 4
planu, jeszcze nie zaimplementowany).

STARY SKANER ZOSTAJE
--------------------
„SKANER — Uzupełnianie DOSTARCZONO" w RM_BAZA działa dalej bez zmian —
projekty prowadzone starą ścieżką wciąż są w toku. To okno powstaje OBOK,
nie zamiast.

STAN: punkt 2 planu — szkielet z danymi z mostu. Sesja wydania i wystawianie
RW dochodzą w punktach 3-4.
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

from rm_kreciolek import Kreciolek
from subiekt_stany import wysrodkuj

TLO = "#ecf0f1"
TLO_SEKCJI = "#ffffff"
TLO_PASKA = "#34495e"
TEKST = "#2c3e50"
TEKST_SZARY = "#7f8c8d"
OK_ZIELONY = "#1e8449"
UWAGA_TLO = "#fcf3cf"
BLAD_TLO = "#f2dede"
SKAN_TLO = "#eaf2f8"

#: Magazyn, z którego wydajemy. Ten sam domyślny co w produkcji RMPAK.
MAGAZYN = "MASTER"


def _liczba(x, dom=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return dom


def _ilo(x):
    """Ilość bez zbędnych zer: „4" zamiast „4.0", ale „1.5" zostaje."""
    f = _liczba(x)
    return str(int(f)) if f == int(f) else ("%g" % f)


def _naturalnie(tekst):
    """Klucz sortowania, w którym liczby są liczbami: R3/P5 przed R22/P6.

    Lokacje to „regał/półka" (R6/P5), więc porównanie tekstowe ustawiało
    R22 przed R3 i trasa po magazynie robiła się bez sensu.
    """
    import re
    return [int(c) if c.isdigit() else c.upper()
            for c in re.split(r"(\d+)", tekst or "")]


def _poz(n):
    """Odmiana słowa „pozycja" — „1 pozycja", „3 pozycje", „7 pozycji"."""
    if n == 1:
        return "pozycja"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "pozycje"
    return "pozycji"


class WydanieWindow(tk.Toplevel, Kreciolek):
    """Okno wydania materiału na projekt."""

    #: Kolumny listy kompletacyjnej: (klucz, nagłówek, szerokość)
    #:
    #: To NIE jest lista „co zeskanowałem" — to PLAN WYDANIA: co zostało do
    #: zebrania, ile już wyszło i ile magazynier przygotował w tej sesji.
    #: Dzięki temu nie zaczyna od pustego ekranu i nie potrzeba drugiej tabeli.
    KOL_PLAN = [("lp", "Lp.", 38), ("lokacja", "Lokacja", 80),
                ("symbol", "Symbol", 130), ("nazwa", "Nazwa", 210),
                ("zrodlo", "Źródło", 60), ("potrzeba", "Potrzeba", 70),
                ("wydano", "Wydano", 65), ("pozostalo", "Pozostało", 75),
                ("stan", "Stan", 60), ("teraz", "Teraz", 60),
                ("status", "Status", 140)]

    def __init__(self, parent, project_id, project_name=None):
        super().__init__(parent)
        self.project_id = project_id
        self.project_name = (project_name or str(project_id or "")).strip()

        #: {SYMBOL: {potrzeba, zrodlo, wydano}} — stan z Subiekta.
        self.stan = {}
        #: PLAN WYDANIA — lista wierszy prawej tabeli. Nie jest to „co
        #: zeskanowałem", tylko „co zostało do wydania w tym projekcie":
        #: {symbol, nazwa, lokacja, zrodlo, potrzeba, wydano, pozostalo,
        #:  stan, teraz, poza_bom}
        self.plan = []
        #: {SYMBOL: ilość} — ile magazynier przygotował w TEJ sesji.
        #: Trzymane osobno od planu, żeby odświeżenie z Subiekta (które
        #: przebudowuje plan) nie skasowało pracy magazyniera.
        self.sesja = {}
        #: Po czym sortować plan. Domyślnie LOKACJA — magazynier ma iść
        #: regałami po kolei, a nie biegać od półki do półki.
        self._sort_kolumna = "lokacja"
        self._sort_malejaco = False
        #: Konflikty ZK/PW i pominięte RW z ostatniego odczytu.
        self.konflikty = []
        self.rw_bez_projektu = []
        #: Zeskanowana pozycja czekająca na dodanie do sesji.
        self.poz_biezaca = None
        #: Połączenie read-only do bazy projektu (metadane z BOM-u).
        self._con = None

        self.title(f"Wydanie z magazynu — {self.project_name}")
        self.geometry("1500x860")
        self.minsize(1150, 700)
        self.configure(bg=TLO)
        self.transient(parent)

        self._buduj()
        wysrodkuj(self, parent)
        # Odczyt startuje po pokazaniu okna: user widzi układ od razu,
        # a nie po kilku sekundach patrzenia w szare tło.
        self.after(80, self._odswiez)

    # ── budowa okna ─────────────────────────────────────────────────────

    def _buduj(self):
        self._pasek_gorny()

        # Pasek stanu i historia PRZED środkiem — inaczej panele z expand=True
        # zjadają wysokość i dolne sekcje wypadają poza okno.
        self._pasek_stanu()
        self._panel_historii()

        srodek = tk.Frame(self, bg=TLO)
        srodek.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 0))

        lewa = tk.Frame(srodek, bg=TLO)
        lewa.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 8))
        self._panel_skanera(lewa)

        prawa = tk.Frame(srodek, bg=TLO)
        prawa.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._panel_sesji(prawa)

    def _pasek_gorny(self):
        """Nagłówek: projekt, magazyn, kto pobiera, data, co powstanie."""
        pasek = tk.Frame(self, bg=TLO_SEKCJI, height=76)
        pasek.pack(fill=tk.X)
        pasek.pack_propagate(False)
        tk.Frame(self, bg="#d5dbdb", height=1).pack(fill=tk.X)

        def sekcja(ikona, tytul, kolumna_startowa=False):
            ram = tk.Frame(pasek, bg=TLO_SEKCJI)
            ram.pack(side=tk.LEFT, padx=(14 if kolumna_startowa else 22, 0),
                     pady=10)
            gora = tk.Frame(ram, bg=TLO_SEKCJI)
            gora.pack(anchor="w")
            tk.Label(gora, text=ikona, bg=TLO_SEKCJI, fg=TEKST_SZARY,
                     font=("Arial", 11)).pack(side=tk.LEFT, padx=(0, 6))
            tk.Label(gora, text=tytul, bg=TLO_SEKCJI, fg=TEKST_SZARY,
                     font=("Arial", 9)).pack(side=tk.LEFT)
            return ram

        # PROJEKT — tylko do odczytu. Magazynier go nie wybiera: przychodzi
        # jako kontekst z RM_BAZA (specyfikacja użytkownika).
        s = sekcja("⚙", "Projekt:", kolumna_startowa=True)
        tk.Label(s, text=self.project_name, bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 13, "bold"), anchor="w").pack(anchor="w")
        self.var_kontekst = tk.StringVar(value="")
        tk.Label(s, textvariable=self.var_kontekst, bg=TLO_SEKCJI,
                 fg=TEKST_SZARY, font=("Arial", 8), anchor="w").pack(anchor="w")

        s = sekcja("🏠", "Magazyn:")
        self.var_magazyn = tk.StringVar(value=MAGAZYN)
        ttk.Combobox(s, textvariable=self.var_magazyn, width=14,
                     state="readonly", font=("Arial", 10),
                     values=[MAGAZYN]).pack(anchor="w", pady=(2, 0))

        s = sekcja("👤", "Pobiera:")
        self.var_pobiera = tk.StringVar()
        self.combo_pobiera = ttk.Combobox(s, textvariable=self.var_pobiera,
                                          width=22, state="readonly",
                                          font=("Arial", 10))
        self.combo_pobiera.pack(anchor="w", pady=(2, 0))
        self._wczytaj_osoby()

        s = sekcja("📅", "Data:")
        from datetime import datetime
        tk.Label(s, text=datetime.now().strftime("%d.%m.%Y"), bg=TLO_SEKCJI,
                 fg=TEKST, font=("Arial", 11), anchor="w").pack(anchor="w",
                                                                pady=(2, 0))

        # Co powstanie — żeby nikt nie musiał zgadywać, czym kończy się sesja.
        s = sekcja("📄", "Tworzymy:")
        tk.Label(s, text="RW (magazynowy)", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 11, "bold"), anchor="w").pack(anchor="w")
        tk.Label(s, text="Po zakończeniu sesji", bg=TLO_SEKCJI, fg=TEKST_SZARY,
                 font=("Arial", 8), anchor="w").pack(anchor="w")

        tk.Button(pasek, text="Odśwież", command=self._odswiez,
                  font=("Arial", 8)).pack(side=tk.RIGHT, padx=14)

    def _panel_skanera(self, rodzic):
        ram = tk.LabelFrame(rodzic, text=" Skaner ", bg=TLO_SEKCJI, fg=TEKST,
                            font=("Arial", 9, "bold"), width=560)
        ram.pack(fill=tk.BOTH, expand=True)
        ram.pack_propagate(False)

        naglowek = tk.Frame(ram, bg=SKAN_TLO)
        naglowek.pack(fill=tk.X, padx=8, pady=(8, 0))
        tk.Label(naglowek, text="▌▌▌  SKANUJ KOD KRESKOWY", bg=SKAN_TLO,
                 fg=TEKST, font=("Arial", 13, "bold")).pack(pady=(8, 0))
        tk.Label(naglowek, text="Zeskanuj kod albo wpisz numer rysunku ręcznie",
                 bg=SKAN_TLO, fg=TEKST_SZARY, font=("Arial", 8)).pack(pady=(0, 6))

        self.var_kod = tk.StringVar()
        self.ent_kod = tk.Entry(naglowek, textvariable=self.var_kod,
                                font=("Arial", 14), justify="center")
        self.ent_kod.pack(fill=tk.X, padx=10, pady=(0, 10), ipady=6)
        # Czytnik kodów kończy transmisję Enterem — to jest cała jego obsługa.
        self.ent_kod.bind("<Return>", lambda _e: self._skanuj())
        self.ent_kod.bind("<Escape>", lambda _e: self._wyczysc_pozycje())

        # ── dane zeskanowanej pozycji + miniatura rysunku ────────────
        dane = tk.Frame(ram, bg=TLO_SEKCJI)
        dane.pack(fill=tk.X, padx=10, pady=(10, 0))

        siatka = tk.Frame(dane, bg=TLO_SEKCJI)
        siatka.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.var_symbol = tk.StringVar(value="—")
        self.var_nazwa = tk.StringVar(value="—")
        for i, (etykieta, zmienna) in enumerate((("Symbol:", self.var_symbol),
                                                 ("Nazwa:", self.var_nazwa))):
            tk.Label(siatka, text=etykieta, bg=TLO_SEKCJI, fg=TEKST_SZARY,
                     font=("Arial", 9), anchor="w", width=8).grid(
                row=i, column=0, sticky="w", pady=3)
            tk.Label(siatka, textvariable=zmienna, bg="#f4f6f7", fg=TEKST,
                     font=("Arial", 11, "bold"), anchor="w", padx=8,
                     pady=5).grid(row=i, column=1, sticky="we", pady=3)
        siatka.grid_columnconfigure(1, weight=1)

        # Miniatura rysunku — magazynier wydaje detal, którego nie zna
        # z numeru. Obrazek pochodzi z DWF projektu (ten sam cache co arkusz).
        mini = tk.Frame(dane, bg=TLO_SEKCJI)
        mini.pack(side=tk.LEFT, padx=(10, 0))
        self.lbl_rysunek = tk.Label(mini, bg="#f4f6f7", width=14, height=6,
                                    bd=1, relief=tk.SOLID, text="—",
                                    fg=TEKST_SZARY, font=("Arial", 8))
        self.lbl_rysunek.pack()
        self.btn_podglad = tk.Button(mini, text="🔍 Podgląd", font=("Arial", 8),
                                     command=self._podglad_rysunku,
                                     state=tk.DISABLED)
        self.btn_podglad.pack(fill=tk.X, pady=(4, 0))
        #: Referencja na PhotoImage — bez niej obrazek znika po GC.
        self._foto = None
        self._sciezka_rysunku = None

        # Cztery liczby, po których magazynier decyduje. Każda ma własne tło,
        # żeby dało się je rozróżnić bez czytania etykiet.
        kafle = tk.Frame(ram, bg=TLO_SEKCJI)
        kafle.pack(fill=tk.X, padx=10, pady=(14, 0))
        self.var_potrzeba = tk.StringVar(value="—")
        self.var_wydano = tk.StringVar(value="—")
        self.var_pozostalo = tk.StringVar(value="—")
        self.var_stan = tk.StringVar(value="—")
        for i, (tytul, zmienna, tlo, kolor) in enumerate((
                ("Potrzeba na projekt:", self.var_potrzeba, "#fdf3d0", "#7d6608"),
                ("Wydano wcześniej:", self.var_wydano, "#e8f0fb", "#1f618d"),
                ("Pozostało:", self.var_pozostalo, "#e8f8e8", "#196f3d"),
                ("Stan magazynu:", self.var_stan, "#eaf6ff", "#1a5276"))):
            kol = tk.Frame(kafle, bg=TLO_SEKCJI)
            kol.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            tk.Label(kol, text=tytul, bg=TLO_SEKCJI, fg=TEKST,
                     font=("Arial", 8), anchor="w").pack(anchor="w")
            tk.Label(kol, textvariable=zmienna, bg=tlo, fg=kolor,
                     font=("Arial", 16, "bold"), anchor="w", padx=10,
                     pady=6).pack(fill=tk.X, pady=(3, 0))
            kafle.grid_columnconfigure(i, weight=1)

        # ── ilość i lokacja ──────────────────────────────────────────
        dol = tk.Frame(ram, bg=TLO_SEKCJI)
        dol.pack(fill=tk.X, padx=10, pady=(12, 0))
        tk.Label(dol, text="Ilość wydawana teraz:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.var_ilosc = tk.StringVar()
        self.spin_ilosc = tk.Spinbox(dol, textvariable=self.var_ilosc, from_=0,
                                     to=999999, width=10, font=("Arial", 12),
                                     justify="right")
        self.spin_ilosc.pack(side=tk.LEFT, padx=(8, 20))
        self.spin_ilosc.bind("<Return>", lambda _e: self._dodaj_do_sesji())

        tk.Label(dol, text="Lokacja:", bg=TLO_SEKCJI, fg=TEKST_SZARY,
                 font=("Arial", 9)).pack(side=tk.LEFT)
        self.var_lokacja = tk.StringVar(value="—")
        tk.Label(dol, textvariable=self.var_lokacja, bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=(6, 0))

        # Metadane pozycji — kontekst, po którym magazynier poznaje, czy
        # trzyma w ręku to co trzeba. Jedna linia, żeby nie zabierać miejsca.
        self.var_meta = tk.StringVar(
            value="Typ: —   |   Grubość: —   |   Dostawca: —   |   Zamówiono: —")
        tk.Label(ram, textvariable=self.var_meta, bg="#f4f6f7", fg=TEKST_SZARY,
                 font=("Arial", 8), anchor="w", padx=10, pady=6).pack(
            fill=tk.X, padx=10, pady=(12, 0))

        # Miejsce na ostrzeżenia: ponad potrzebę / poza BOM / ponad stan.
        self.lbl_uwaga = tk.Label(ram, text="", bg=TLO_SEKCJI, fg=TEKST,
                                  font=("Arial", 9), anchor="w",
                                  justify="left", wraplength=520)
        self.lbl_uwaga.pack(fill=tk.X, padx=10, pady=(8, 0))

        przyciski = tk.Frame(ram, bg=TLO_SEKCJI)
        przyciski.pack(fill=tk.X, padx=10, pady=12)
        self.btn_dodaj = tk.Button(przyciski, text="✔ Dodaj do wydania (Enter)",
                                   command=self._dodaj_do_sesji, bg=OK_ZIELONY,
                                   fg="white", font=("Arial", 10, "bold"),
                                   state=tk.DISABLED)
        self.btn_dodaj.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(przyciski, text="Wyczyść (ESC)", command=self._wyczysc_pozycje,
                  font=("Arial", 9)).pack(side=tk.LEFT, padx=(8, 0))

    def _panel_sesji(self, rodzic):
        ram = tk.Frame(rodzic, bg=TLO_SEKCJI, bd=1, relief=tk.SOLID)
        ram.pack(fill=tk.BOTH, expand=True)

        naglowek = tk.Frame(ram, bg=TLO_SEKCJI)
        naglowek.pack(fill=tk.X, padx=10, pady=(8, 0))
        tk.Label(naglowek, text="☰  Do wydania w projekcie", bg=TLO_SEKCJI,
                 fg=TEKST, font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        self.var_licznik = tk.StringVar(value="0 pozycji")
        tk.Label(naglowek, textvariable=self.var_licznik, bg=TLO_SEKCJI,
                 fg=TEKST_SZARY, font=("Arial", 9)).pack(side=tk.RIGHT)
        tk.Label(ram, text="Pozycje, które pozostały do wydania dla projektu %s"
                 % self.project_name, bg=TLO_SEKCJI, fg=TEKST_SZARY,
                 font=("Arial", 8), anchor="w").pack(fill=tk.X, padx=10,
                                                     pady=(0, 4))

        # STOPKA PRZED TABELĄ — tabela z expand=True zjadłaby wysokość
        # i przyciski wypadłyby poza okno (ta sama pułapka co w kalkulatorze).
        stopka = tk.Frame(ram, bg=TLO_SEKCJI)
        stopka.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

        # Kafel z sumami. Rozdzielone świadomie: „Do wydania" dotyczy CAŁEGO
        # projektu, „Przygotowano teraz" tylko tej sesji. Wspólna liczba
        # („łącznie pozycji: 37") myliła, bo nie było wiadomo, czego dotyczy.
        kafel = tk.Frame(stopka, bg="#f4f6f7", bd=1, relief=tk.SOLID)
        kafel.pack(side=tk.LEFT, padx=(0, 10))
        self.var_do_wydania = tk.StringVar(value="0 pozycji")
        self.var_przygotowano = tk.StringVar(value="0 pozycji / 0 szt.")
        for i, (tytul, zmienna, kolor) in enumerate((
                ("Do wydania:", self.var_do_wydania, TEKST),
                ("Przygotowano teraz:", self.var_przygotowano, OK_ZIELONY))):
            tk.Label(kafel, text=tytul, bg="#f4f6f7", fg=TEKST,
                     font=("Arial", 9, "bold"), anchor="w").grid(
                row=i, column=0, sticky="w", padx=(10, 16),
                pady=(6 if i == 0 else 0, 6))
            tk.Label(kafel, textvariable=zmienna, bg="#f4f6f7", fg=kolor,
                     font=("Arial", 11, "bold"), anchor="e").grid(
                row=i, column=1, sticky="e", padx=(0, 12))

        self.btn_zakoncz = tk.Button(
            stopka, text="Zakończ wydanie\nUtwórz RW w Subiekcie",
            command=self._zakoncz, bg="#2980b9", fg="white",
            font=("Arial", 10, "bold"), padx=14, state=tk.DISABLED)
        self.btn_zakoncz.pack(side=tk.RIGHT)
        self.btn_podglad_rw = tk.Button(
            stopka, text="📄 Podgląd RW", command=self._podglad_rw,
            font=("Arial", 9), padx=12, state=tk.DISABLED)
        self.btn_podglad_rw.pack(side=tk.RIGHT, padx=(0, 8))

        akcje = tk.Frame(ram, bg=TLO_SEKCJI)
        akcje.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 4))
        # „Usuń z wydania" zeruje kolumnę Teraz — NIE usuwa pozycji z planu
        # projektu. Plan wynika z ZK/PW i nie jest naszą własnością.
        tk.Button(akcje, text="🗑 Usuń z wydania", command=self._usun_z_sesji,
                  font=("Arial", 8)).pack(side=tk.LEFT)
        tk.Button(akcje, text="✏ Popraw ilość", command=self._popraw_ilosc,
                  font=("Arial", 8)).pack(side=tk.LEFT, padx=6)
        tk.Button(akcje, text="✖ Wyczyść sesję", command=self._wyczysc_sesje,
                  font=("Arial", 8)).pack(side=tk.LEFT)
        self.var_tylko_do_wydania = tk.IntVar(value=1)
        tk.Checkbutton(akcje, text="tylko pozostałe do wydania",
                       variable=self.var_tylko_do_wydania, bg=TLO_SEKCJI,
                       font=("Arial", 8), activebackground=TLO_SEKCJI,
                       command=self._odswiez_plan).pack(side=tk.RIGHT)

        wrap = tk.Frame(ram, bg=TLO_SEKCJI)
        wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 0))
        self.tab = ttk.Treeview(wrap, columns=[k[0] for k in self.KOL_PLAN],
                                show="headings", selectmode="browse")
        for klucz, naglowek, szer in self.KOL_PLAN:
            self.tab.heading(klucz, text=naglowek,
                             command=lambda k=klucz: self._sortuj(k))
            self.tab.column(klucz, width=szer, minwidth=36,
                            stretch=(klucz == "nazwa"),
                            anchor="w" if klucz in ("lokacja", "symbol", "nazwa",
                                                    "zrodlo", "status")
                            else "e")
        sc = ttk.Scrollbar(wrap, orient="vertical", command=self.tab.yview)
        self.tab.configure(yscrollcommand=sc.set)
        self.tab.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        # Status kolorem wiersza — bez popupu przy każdym skanie, bo
        # magazynier skanuje seriami (§8 planu).
        self.tab.tag_configure("gotowe", background="#e8f8e8")
        self.tab.tag_configure("czesciowo", background=UWAGA_TLO)
        self.tab.tag_configure("brak_stanu", background=BLAD_TLO)
        self.tab.tag_configure("poza_bom", background="#f4ecf7")
        self.tab.bind("<Double-1>", lambda _e: self._popraw_ilosc())
        self.tab.bind("<Delete>", lambda _e: self._usun_z_sesji())

    #: Kolumny historii skanów: (klucz, nagłówek, szerokość)
    KOL_HIST = [("czas", "Czas", 80), ("symbol", "Symbol", 150),
                ("nazwa", "Nazwa", 300), ("ilosc", "Ilość", 70),
                ("stan", "Stan", 70), ("lokacja", "Lokacja", 90)]

    def _panel_historii(self):
        """Ostatnie skany — ślad tego, co magazynier robił w tej sesji.

        Nie jest to duplikat listy pozycji: tam widać STAN sesji (po
        poprawkach i usunięciach), tutaj KOLEJNOŚĆ ZDARZEŃ. Przy sporze
        „skanowałem to czy nie" liczy się drugie.
        """
        ram = tk.Frame(self, bg=TLO_SEKCJI, bd=1, relief=tk.SOLID, height=190)
        ram.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(6, 6))
        ram.pack_propagate(False)

        tk.Label(ram, text="🕘  Ostatnie skany (historia sesji)", bg=TLO_SEKCJI,
                 fg=TEKST, font=("Arial", 10, "bold"), anchor="w").pack(
            fill=tk.X, padx=10, pady=(6, 4))

        wrap = tk.Frame(ram, bg=TLO_SEKCJI)
        wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))
        self.tab_hist = ttk.Treeview(wrap, columns=[k[0] for k in self.KOL_HIST],
                                     show="headings", height=5)
        for klucz, naglowek, szer in self.KOL_HIST:
            self.tab_hist.heading(klucz, text=naglowek)
            self.tab_hist.column(klucz, width=szer, minwidth=50,
                                 stretch=(klucz == "nazwa"),
                                 anchor="e" if klucz in ("ilosc", "stan") else "w")
        sc = ttk.Scrollbar(wrap, orient="vertical", command=self.tab_hist.yview)
        self.tab_hist.configure(yscrollcommand=sc.set)
        self.tab_hist.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)

    def _pasek_stanu(self):
        pas = tk.Frame(self, bg="#e5e8e8", height=26)
        pas.pack(side=tk.BOTTOM, fill=tk.X)
        pas.pack_propagate(False)

        self.var_polaczenie = tk.StringVar(value="● Łączenie z Subiektem…")
        self.lbl_polaczenie = tk.Label(pas, textvariable=self.var_polaczenie,
                                       bg="#e5e8e8", fg=TEKST_SZARY,
                                       font=("Arial", 8), anchor="w")
        self.lbl_polaczenie.pack(side=tk.LEFT, padx=10)

        self.var_status = tk.StringVar(value="Wczytywanie stanu…")
        tk.Label(pas, textvariable=self.var_status, bg="#e5e8e8",
                 fg=TEKST_SZARY, font=("Arial", 8), anchor="w").pack(
            side=tk.LEFT, padx=(14, 0))

        # Klikalne: pokazuje, KTÓRE RW zostały pominięte. Bez tego różnica
        # „stan spadł, a licznik nie" zostaje bez wyjaśnienia (§8 planu).
        self.lbl_pominiete = tk.Label(pas, text="", bg="#e5e8e8", fg="#8e6b1f",
                                      font=("Arial", 8, "underline"),
                                      cursor="hand2", anchor="w")
        self.lbl_pominiete.pack(side=tk.LEFT, padx=(14, 0))
        self.lbl_pominiete.bind("<Button-1>", lambda _e: self._pokaz_pominiete())

        import os
        tk.Label(pas, text="Użytkownik: %s" % (os.environ.get("USERNAME") or "?"),
                 bg="#e5e8e8", fg=TEKST_SZARY, font=("Arial", 8)).pack(
            side=tk.RIGHT, padx=10)

    # ── dane ────────────────────────────────────────────────────────────

    def _wczytaj_osoby(self):
        """Lista do pola „Pobiera" — z tabeli users w master.sqlite."""
        osoby = []
        try:
            import sqlite3
            from subiekt_stany import PROJECTS_DIR
            import os
            master = os.path.join(os.path.dirname(PROJECTS_DIR.rstrip("\\/")),
                                  "master.sqlite")
            con = sqlite3.connect("file:%s?mode=ro" % master, uri=True)
            osoby = [r[0] for r in con.execute(
                "SELECT COALESCE(NULLIF(TRIM(display_name), ''), username) "
                "FROM users WHERE COALESCE(is_active, 1) = 1 "
                "ORDER BY 1") if r[0]]
            con.close()
        except Exception as e:
            print("⚠️  Nie wczytano listy osób: %s" % e)
        self.combo_pobiera["values"] = osoby
        if osoby:
            self.var_pobiera.set(osoby[0])

    def _odswiez(self):
        """Stan z Subiekta w tle — okno zostaje responsywne."""
        self.var_status.set("Wczytywanie stanu z Subiekta…")

        def worker():
            try:
                import subiekt_bridge
                import subiekt_stany
                from subiekt_zamowienia import sam_numer
                dane = subiekt_bridge.call(
                    "wydanie-stan",
                    {"projekt": sam_numer(self.project_name), "magazyn": MAGAZYN},
                    timeout=300, write=False)
                # Stany i lokacje HURTEM, jednym zapytaniem — pytanie osobno
                # o każdą z ~190 pozycji trwałoby minuty.
                symbole = [(p.get("symbol") or "").strip()
                           for p in (dane or {}).get("pozycje", [])]
                kartoteki = {}
                if symbole:
                    kartoteki = subiekt_stany.query_stock(symbole, timeout=300) or {}
                self.after(0, lambda: self._po_odczycie(dane, None, kartoteki))
            except Exception as e:
                self.after(0, lambda: self._po_odczycie(None, str(e), None))

        threading.Thread(target=worker, daemon=True).start()

    def _po_odczycie(self, dane, blad, kartoteki=None):
        if blad:
            # Bez świeżego odczytu NIE WOLNO wydawać (§4 planu) — magazynier
            # musi to widzieć od razu, nie dopiero przy „Zakończ wydanie".
            self.var_polaczenie.set("● Brak połączenia z Subiektem")
            self.lbl_polaczenie.config(fg="#c0392b")
            self.var_status.set("⛔ Wydanie niemożliwe: %s" % blad)
            return

        self.var_polaczenie.set("● Połączono z Subiektem NEXO")
        self.lbl_polaczenie.config(fg=OK_ZIELONY)
        self.stan = {}
        for p in (dane or {}).get("pozycje", []):
            self.stan[(p.get("symbol") or "").strip().upper()] = p
        self.konflikty = (dane or {}).get("konflikty") or []
        self.rw_bez_projektu = (dane or {}).get("rw_bez_projektu") or []

        self._zbuduj_plan(kartoteki or {})

        czesci = ["%d pozycji projektu" % len(self.stan)]
        if self.konflikty:
            czesci.append("⚠ %d konfliktów ZK/PW" % len(self.konflikty))
        self.var_status.set("   ·   ".join(czesci))
        self.lbl_pominiete.config(
            text=("ℹ RW bez numeru projektu nie są liczone (%d)"
                  % len(self.rw_bez_projektu)) if self.rw_bez_projektu else "")
        self.ent_kod.focus_set()

    def _zbuduj_plan(self, kartoteki):
        """Lista kompletacyjna: co zostało do wydania w tym projekcie.

        Sesja (kolumna „Teraz") NIE jest tu odtwarzana z planu — leży
        w self.sesja i przeżywa odświeżenie. Inaczej „Odśwież" w środku
        kompletacji kasowałby to, co magazynier zdążył przygotować.
        """
        self.plan = []
        for klucz, p in self.stan.items():
            symbol = (p.get("symbol") or "").strip()
            k = kartoteki.get(symbol) or {}
            potrzeba = p.get("potrzeba")
            wydano = _liczba(p.get("wydano"))
            pozostalo = (None if potrzeba is None
                         else max(0.0, _liczba(potrzeba) - wydano))
            self.plan.append({
                "symbol": symbol,
                "nazwa": k.get("Nazwa") or "",
                "lokacja": (k.get("Polozenie") or "").strip(),
                "zrodlo": p.get("zrodlo") or "—",
                "potrzeba": potrzeba,
                "wydano": wydano,
                "pozostalo": pozostalo,
                "stan": self._stan_w_magazynie(k) if k else 0.0,
                "poza_bom": potrzeba is None,
            })
        self._odswiez_plan()

    def _sortuj(self, kolumna):
        """Klik w nagłówek — przesortuj plan."""
        if self._sort_kolumna == kolumna:
            self._sort_malejaco = not self._sort_malejaco
        else:
            self._sort_kolumna, self._sort_malejaco = kolumna, False
        self._odswiez_plan()

    def _pokaz_pominiete(self):
        if not self.rw_bez_projektu:
            return
        wiersze = "\n".join(
            "   %-22s %-12s %s poz." % (d.get("numer") or "?",
                                        d.get("data") or "",
                                        d.get("pozycji") or 0)
            for d in self.rw_bez_projektu[:30])
        messagebox.showinfo(
            "RW bez numeru projektu",
            "Te dokumenty RW nie mają numeru projektu w Uwagach, więc NIE są\n"
            "liczone jako wydania tego projektu:\n\n" + wiersze
            + "\n\nJeśli któryś dotyczy tego projektu, wpisz w jego Uwagi\n"
              "numer projektu w pierwszym wierszu.", parent=self)

    # ── skanowanie ──────────────────────────────────────────────────────

    def _skanuj(self):
        """Enter w polu skanera: znajdź pozycję i pokaż jej liczby.

        Czytnik kodów kończy transmisję Enterem, więc to jest cała jego
        obsługa — żadnego trybu „nasłuchu klawiatury".
        """
        kod = (self.var_kod.get() or "").strip()
        if not kod:
            return
        # ⚠️ NIE TNIEMY NA SPACJI. Symbole w Subiekcie potrafią ją zawierać —
        # „6212 2RS", „UCFL204 UCFL 204", „DIN 933 M8x30". Cięcie na pierwszej
        # spacji (tak robi stary skaner, bo tam kluczem jest numer rysunku)
        # zamieniało „6212 2RS" w „6212" i kartoteka nie była znajdowana
        # (sprawdzone 11.09.2026). Pytamy więc o CAŁY wpisany tekst, a dopiero
        # gdy nic nie ma — o pierwszy człon, na wypadek gdyby pole zostało
        # uzupełnione nazwą po poprzednim skanie.
        kandydaci = [kod]
        if " " in kod:
            kandydaci.append(kod.split()[0])

        self.var_status.set("Sprawdzam %s…" % kod)
        self.btn_dodaj.config(state=tk.DISABLED)

        def worker():
            try:
                import subiekt_stany
                dane = subiekt_stany.query_stock(kandydaci, timeout=120) or {}
                for k in kandydaci:
                    wpis = dane.get(k)
                    if wpis and wpis.get("Istnieje"):
                        self.after(0, lambda w=wpis, s=k: self._po_skanie(s, w, None))
                        return
                self.after(0, lambda: self._po_skanie(kod, None, None))
            except Exception as e:
                self.after(0, lambda: self._po_skanie(kod, None, str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _po_skanie(self, symbol, kartoteka, blad):
        if blad:
            self.var_status.set("⛔ %s" % blad)
            self._uwaga("Nie udało się sprawdzić stanu: %s" % blad, BLAD_TLO)
            return
        if not kartoteka or not kartoteka.get("Istnieje"):
            self.var_status.set("Nie znaleziono kartoteki")
            self._uwaga("⛔ %s — nie ma takiej kartoteki w Subiekcie.\n"
                        "Sprawdź kod albo załóż kartotekę w Edytorze."
                        % symbol, BLAD_TLO)
            self._wyczysc_pozycje(zostaw_uwage=True)
            return

        sym = (kartoteka.get("Symbol") or symbol).strip()
        self.poz_biezaca = {
            "symbol": sym,
            "nazwa": kartoteka.get("Nazwa") or "",
            "lokacja": (kartoteka.get("Polozenie") or "").strip(),
            "stan": self._stan_w_magazynie(kartoteka),
        }

        # Potrzeba i wcześniejsze wydania — z odczytu „wydanie-stan".
        wpis = self.stan.get(sym.upper()) or {}
        potrzeba = wpis.get("potrzeba")
        wydano = _liczba(wpis.get("wydano"), 0.0)
        # Sesja jeszcze niezapisana też się liczy — inaczej magazynier
        # skanujący dwa razy ten sam detal zobaczyłby to samo „pozostało".
        w_sesji = self.sesja.get(sym.upper(), 0.0)
        self.poz_biezaca.update({
            "potrzeba": potrzeba,
            "zrodlo": wpis.get("zrodlo"),
            "wydano": wydano,
            "w_sesji": w_sesji,
        })

        self.var_symbol.set(sym)
        self.var_nazwa.set(self.poz_biezaca["nazwa"] or "—")
        self.var_lokacja.set(self.poz_biezaca["lokacja"] or "—")
        self.var_stan.set(_ilo(self.poz_biezaca["stan"]))
        self.var_wydano.set(_ilo(wydano + w_sesji) if (wydano or w_sesji) else "0")

        if potrzeba is None:
            # POZA BOM — nie udajemy potrzeby, której nie ma (§8 planu).
            self.var_potrzeba.set("—")
            self.var_pozostalo.set("—")
            domyslna = 0
        else:
            pozostalo = max(0.0, _liczba(potrzeba) - wydano - w_sesji)
            self.var_potrzeba.set(_ilo(potrzeba))
            self.var_pozostalo.set(_ilo(pozostalo))
            # Domyślnie tyle, ile brakuje — ale nie więcej niż jest na stanie.
            domyslna = min(pozostalo, self.poz_biezaca["stan"])

        self.var_ilosc.set(_ilo(domyslna) if domyslna > 0 else "")
        self.var_meta.set(self._opis_meta(sym, kartoteka))
        self._pokaz_rysunek(sym)
        self._uwaga_po_skanie()

        self.btn_dodaj.config(state=tk.NORMAL)
        self.var_status.set("%d pozycji projektu" % len(self.stan))
        # Fokus wraca na ilość: najczęstsza poprawka to właśnie ona.
        self.spin_ilosc.focus_set()
        self.spin_ilosc.selection_range(0, tk.END)

    def _stan_w_magazynie(self, kartoteka):
        """Dostępne w NASZYM magazynie, nie suma ze wszystkich."""
        chciany = (self.var_magazyn.get() or MAGAZYN).strip().upper()
        for m in kartoteka.get("Magazyny") or []:
            if (m.get("Magazyn") or "").strip().upper() == chciany:
                return _liczba(m.get("Dostepne"))
        return _liczba(kartoteka.get("Dostepne"))

    def _opis_meta(self, symbol, kartoteka):
        """Pasek kontekstu pod ilością — z BOM-u projektu i z kartoteki."""
        typ = grubosc = dostawca = "—"
        try:
            import sqlite3
            from database_manager import DatabaseManager  # noqa: F401
        except Exception:
            pass
        try:
            con = self._projekt_con()
            if con is not None:
                r = con.execute(
                    "SELECT class_effective, thickness_mm, "
                    "       COALESCE(mat_effective_text, '') "
                    "FROM items WHERE UPPER(COALESCE(NULLIF(TRIM(work_drawing_no),''),"
                    "      NULLIF(TRIM(norm_drawing_no),''), src_drawing_no)) = ? "
                    "  AND COALESCE(is_hidden,0)=0 LIMIT 1",
                    (symbol.upper(),)).fetchone()
                if r:
                    typ = r[0] or "—"
                    grubosc = _ilo(r[1]) if r[1] is not None else "—"
                    dostawca = r[2] or "—"
        except Exception:
            pass
        wpis = self.stan.get(symbol.upper()) or {}
        zam = wpis.get("potrzeba")
        return ("Typ: %s   |   Grubość: %s   |   Materiał: %s   |   %s: %s"
                % (typ, grubosc, dostawca,
                   "Zamówiono (ZK)" if wpis.get("zrodlo") == "ZK"
                   else "Przyjęto (PW)" if wpis.get("zrodlo") == "PW" else "Plan",
                   _ilo(zam) if zam is not None else "—"))

    def _projekt_con(self):
        """Połączenie read-only do bazy projektu — do metadanych z BOM-u."""
        if getattr(self, "_con", None) is not None:
            return self._con
        try:
            import os
            import sqlite3
            from subiekt_stany import PROJECTS_DIR
            sciezka = os.path.join(PROJECTS_DIR, "project_%s.sqlite" % self.project_id)
            if not os.path.isfile(sciezka):
                return None
            self._con = sqlite3.connect("file:%s?mode=ro" % sciezka, uri=True)
        except Exception:
            self._con = None
        return self._con

    def _pokaz_rysunek(self, symbol):
        """Miniatura DWF — ten sam cache co arkusz główny RM_BAZA."""
        self._foto = None
        self._sciezka_rysunku = None
        self.lbl_rysunek.config(image="", text="—")
        self.btn_podglad.config(state=tk.DISABLED)
        try:
            from pathlib import Path
            from import_bom import find_dwf_for_drawing, find_dwf_in_library
            import dwf_thumb
            from PIL import Image, ImageTk
            sciezka = (find_dwf_for_drawing(Path("V:/"), self.project_name, symbol)
                       or find_dwf_in_library(symbol, "B:/"))
            if not sciezka:
                self.lbl_rysunek.config(text="brak\nrysunku")
                return
            thumb = dwf_thumb.get_cached_thumb_path(str(sciezka))
            im = Image.open(thumb).convert("RGB")
            im.thumbnail((150, 110), Image.LANCZOS)
            self._foto = ImageTk.PhotoImage(im)
            self._sciezka_rysunku = thumb
            self.lbl_rysunek.config(image=self._foto, text="")
            self.btn_podglad.config(state=tk.NORMAL)
        except Exception:
            # Brak rysunku nie może przeszkodzić w wydaniu — to tylko pomoc.
            self.lbl_rysunek.config(text="brak\nrysunku")

    def _uwaga(self, tekst, tlo=None):
        self.lbl_uwaga.config(text=tekst, bg=tlo or TLO_SEKCJI)

    def _uwaga_po_skanie(self):
        """Ostrzeżenia widoczne PRZED dodaniem, bez popupu (§8 planu)."""
        p = self.poz_biezaca
        if p.get("potrzeba") is None:
            self._uwaga("⚠ POZYCJA SPOZA BOM-U PROJEKTU — nie występuje w ZK "
                        "ani PW tego projektu.\nMożna wydać; trafi na RW ze "
                        "znacznikiem POZA BOM.", "#f4ecf7")
        elif p["stan"] <= 0:
            self._uwaga("⛔ Stan magazynu %s = 0 — nie ma czego wydać."
                        % (self.var_magazyn.get() or MAGAZYN), BLAD_TLO)
        else:
            self._uwaga("")

    def _wyczysc_pozycje(self, zostaw_uwage=False):
        self.var_kod.set("")
        self.poz_biezaca = None
        for z in (self.var_symbol, self.var_nazwa):
            z.set("—")
        for z in (self.var_potrzeba, self.var_wydano, self.var_pozostalo,
                  self.var_stan, self.var_lokacja):
            z.set("—")
        self.var_ilosc.set("")
        self.var_meta.set("Typ: —   |   Grubość: —   |   Materiał: —   |   Plan: —")
        self.lbl_rysunek.config(image="", text="—")
        self._foto = None
        self.btn_podglad.config(state=tk.DISABLED)
        if not zostaw_uwage:
            self._uwaga("")
        self.btn_dodaj.config(state=tk.DISABLED)
        self.ent_kod.focus_set()

    def _dodaj_do_sesji(self):
        """Dokłada zeskanowaną pozycję do sesji. NIC jeszcze nie idzie do Subiekta."""
        p = getattr(self, "poz_biezaca", None)
        if not p:
            return
        ile = _liczba(self.var_ilosc.get(), 0.0)
        if ile <= 0:
            self._uwaga("⛔ Podaj ilość większą od zera.", BLAD_TLO)
            self.spin_ilosc.focus_set()
            return

        # ⛔ PONAD STAN — TWARDA BLOKADA (§8 planu). Subiekt i tak odrzuci
        # dokument, więc przepuszczenie tego tylko przesunęłoby błąd na koniec
        # sesji, gdy magazynier ma już wszystko zebrane.
        wolne = p["stan"] - self.sesja.get(p["symbol"].upper(), 0.0)
        if ile > wolne:
            self._brak_stanu(p, ile, wolne)
            return

        # ⚠ PONAD POTRZEBĘ — tylko ostrzeżenie: fizyczne wydanie jest
        # ważniejsze od założenia BOM-u. Bez popupu, bo magazynier skanuje
        # seriami — widać to kolorem wiersza i w podsumowaniu przed RW.
        uwaga, ponad = "", False
        if p.get("potrzeba") is not None:
            pozostalo = max(0.0, _liczba(p["potrzeba"]) - p["wydano"] - p["w_sesji"])
            if ile > pozostalo:
                ponad = True
                uwaga = "⚠ ponad potrzebę o %s szt." % _ilo(ile - pozostalo)

        klucz = p["symbol"].upper()
        # Ten sam detal zeskanowany drugi raz DOKŁADA się do „Teraz",
        # nie zakłada drugiego wiersza — plan ma jedną linię na symbol.
        self.sesja[klucz] = self.sesja.get(klucz, 0.0) + ile

        # Pozycja spoza BOM-u nie ma wiersza w planie (nie ma jej na ZK ani
        # PW), więc dokładamy ją — inaczej magazynier nie zobaczyłby tego,
        # co właśnie przygotował.
        if not any(w["symbol"].upper() == klucz for w in self.plan):
            self.plan.append({
                "symbol": p["symbol"], "nazwa": p["nazwa"],
                "lokacja": p["lokacja"], "zrodlo": p.get("zrodlo") or "—",
                "potrzeba": p.get("potrzeba"), "wydano": p["wydano"],
                "pozostalo": None if p.get("potrzeba") is None else
                             max(0.0, _liczba(p["potrzeba"]) - p["wydano"]),
                "stan": p["stan"], "poza_bom": p.get("potrzeba") is None,
            })

        self._odswiez_plan()
        self._pokaz_wiersz(klucz)
        self._dopisz_historie(p["symbol"], p["nazwa"], ile, p["stan"], p["lokacja"])
        if uwaga:
            self._uwaga("⚠ %s — %s" % (p["symbol"], uwaga), UWAGA_TLO)
        # Fokus WRACA DO SKANERA — magazynier skanuje dalej bez sięgania po mysz.
        self._wyczysc_pozycje(zostaw_uwage=bool(uwaga))

    def _pozycje_sesji(self):
        """Sesja jako lista pozycji do wydania — w kolejności z planu.

        Jedna pozycja na symbol: ten sam detal zeskanowany kilka razy ma
        pójść na dokument jako JEDEN wiersz z sumą.
        """
        out = []
        for p in self._widoczne_wiersze():
            ile = self.sesja.get(p["symbol"].upper(), 0.0)
            if ile > 0:
                out.append(dict(p, ilosc=ile))
        return out

    def _pokaz_wiersz(self, klucz):
        """Zaznacza i przewija do pozycji, którą właśnie zeskanowano."""
        for i, p in enumerate(self._widoczne_wiersze()):
            if p["symbol"].upper() == klucz:
                dzieci = self.tab.get_children()
                if i < len(dzieci):
                    self.tab.selection_set(dzieci[i])
                    self.tab.see(dzieci[i])
                return

    def _brak_stanu(self, p, chciane, wolne):
        """Blokada z wyjściem: ustaw tyle, ile jest, albo odśwież stan."""
        okno = tk.Toplevel(self)
        okno.title("Brak stanu")
        okno.transient(self)
        okno.resizable(False, False)
        tk.Label(okno, text="⛔ Brak wystarczającego stanu", bg="#c0392b",
                 fg="white", font=("Arial", 11, "bold"), anchor="w",
                 padx=14, pady=8).pack(fill=tk.X)
        tk.Label(okno, padx=16, pady=12, justify="left", anchor="w",
                 font=("Arial", 10),
                 text=("%s\n\nStan magazynu: %s szt.\nPróba wydania: %s szt."
                       % (p["symbol"], _ilo(wolne), _ilo(chciane))
                       + ("\n\n(w tej sesji masz już %s szt. tej pozycji)"
                          % _ilo(p["stan"] - wolne) if wolne < p["stan"] else ""))
                 ).pack(fill=tk.X)
        stopka = tk.Frame(okno, padx=14, pady=12)
        stopka.pack(fill=tk.X)

        def ustaw():
            self.var_ilosc.set(_ilo(wolne))
            okno.destroy()
            self.spin_ilosc.focus_set()

        def odswiez():
            okno.destroy()
            self.var_kod.set(p["symbol"])
            self._skanuj()

        tk.Button(stopka, text="Ustaw %s" % _ilo(wolne), command=ustaw,
                  width=12, state=tk.NORMAL if wolne > 0 else tk.DISABLED
                  ).pack(side=tk.LEFT)
        tk.Button(stopka, text="Odśwież stan", command=odswiez,
                  width=14).pack(side=tk.LEFT, padx=8)
        tk.Button(stopka, text="Anuluj", command=okno.destroy,
                  width=10).pack(side=tk.RIGHT)
        wysrodkuj(okno, self)
        okno.grab_set()

    def _zaznaczony(self):
        """Wiersz planu wskazany w tabeli, albo None."""
        sel = self.tab.selection()
        if not sel:
            return None
        widoczne = self._widoczne_wiersze()
        idx = self.tab.index(sel[0])
        return widoczne[idx] if 0 <= idx < len(widoczne) else None

    def _usun_z_sesji(self):
        """Zeruje „Teraz" — pozycja ZOSTAJE w planie projektu.

        Plan wynika z ZK/PW i nie jest naszą własnością: usunięcie wiersza
        znaczyłoby „tego nie trzeba wydać", a chodzi tylko o „nie wydaję
        tego teraz".
        """
        p = self._zaznaczony()
        if p is None:
            messagebox.showinfo("Wydanie", "Zaznacz pozycję na liście.",
                                parent=self)
            return
        self.sesja.pop(p["symbol"].upper(), None)
        self._odswiez_plan()

    def _wyczysc_sesje(self):
        """Zeruje CAŁĄ kolumnę „Teraz" — plan zostaje nietknięty."""
        if self.sesja and not messagebox.askyesno(
                "Wyczyść sesję",
                "Wyzerować wszystko, co przygotowano w tej sesji?\n\n"
                "Lista pozycji do wydania zostaje bez zmian.", parent=self):
            return
        self.sesja = {}
        self._odswiez_plan()

    def _popraw_ilosc(self):
        p = self._zaznaczony()
        if p is None:
            messagebox.showinfo("Wydanie", "Zaznacz pozycję na liście.",
                                parent=self)
            return
        klucz = p["symbol"].upper()
        okno = tk.Toplevel(self)
        okno.title("Ilość do wydania")
        okno.transient(self)
        okno.resizable(False, False)
        tk.Label(okno, text="%s\n%s" % (p["symbol"], p.get("nazwa") or ""),
                 font=("Arial", 10, "bold"), padx=16, pady=(12, 4),
                 justify="left").pack(anchor="w")
        tk.Label(okno, padx=16, fg=TEKST_SZARY, font=("Arial", 8),
                 justify="left", anchor="w",
                 text="pozostało: %s      stan magazynu: %s"
                      % ("—" if p["pozostalo"] is None else _ilo(p["pozostalo"]),
                         _ilo(p["stan"]))).pack(anchor="w")
        var = tk.StringVar(value=_ilo(self.sesja.get(klucz, 0.0)))
        ent = tk.Entry(okno, textvariable=var, font=("Arial", 13),
                       justify="right", width=12)
        ent.pack(padx=16, pady=10)
        ent.focus_set()
        ent.selection_range(0, tk.END)

        def zapisz():
            ile = _liczba(var.get(), 0.0)
            if ile < 0:
                return
            # Ta sama twarda blokada co przy skanowaniu: czego nie ma na
            # stanie, tego Subiekt nie wyda.
            if ile > p["stan"]:
                messagebox.showerror(
                    "Za mało na stanie",
                    "Stan magazynu: %s szt.\nPróba wydania: %s szt."
                    % (_ilo(p["stan"]), _ilo(ile)), parent=okno)
                return
            if ile == 0:
                self.sesja.pop(klucz, None)
            else:
                self.sesja[klucz] = ile
            okno.destroy()
            self._odswiez_plan()

        ent.bind("<Return>", lambda _e: zapisz())
        stopka = tk.Frame(okno, padx=16, pady=10)
        stopka.pack(fill=tk.X)
        tk.Button(stopka, text="Zapisz", command=zapisz, width=10,
                  bg=OK_ZIELONY, fg="white").pack(side=tk.LEFT)
        tk.Button(stopka, text="Anuluj", command=okno.destroy,
                  width=10).pack(side=tk.RIGHT)
        wysrodkuj(okno, self)
        okno.grab_set()

    def _odswiez_plan(self):
        """Przerysowuje listę kompletacyjną i liczniki."""
        for w in self.tab.get_children():
            self.tab.delete(w)

        widoczne = self._widoczne_wiersze()
        for i, p in enumerate(widoczne, 1):
            teraz = self.sesja.get(p["symbol"].upper(), 0.0)
            status, tag = self._status_wiersza(p, teraz)
            self.tab.insert("", "end", values=(
                i, p["lokacja"] or "—", p["symbol"], p["nazwa"],
                p["zrodlo"],
                "—" if p["potrzeba"] is None else _ilo(p["potrzeba"]),
                _ilo(p["wydano"]),
                "—" if p["pozostalo"] is None else _ilo(p["pozostalo"]),
                _ilo(p["stan"]), _ilo(teraz) if teraz else "0",
                status), tags=(tag,) if tag else ())

        # Dwa różne liczniki: plan dotyczy PROJEKTU, sesja tego, co magazynier
        # przygotował TERAZ. Wspólna liczba nie mówiła, czego dotyczy.
        do_wydania = sum(1 for p in self.plan
                         if p["pozostalo"] is None or p["pozostalo"] > 0)
        w_sesji = {s: i for s, i in self.sesja.items() if i > 0}
        sztuk = sum(w_sesji.values())
        self.var_do_wydania.set("%d %s" % (do_wydania, _poz(do_wydania)))
        self.var_przygotowano.set("%d %s / %s szt."
                                  % (len(w_sesji), _poz(len(w_sesji)), _ilo(sztuk)))
        self.var_licznik.set("%d %s" % (len(widoczne), _poz(len(widoczne))))

        stan = tk.NORMAL if w_sesji else tk.DISABLED
        self.btn_zakoncz.config(state=stan)
        self.btn_podglad_rw.config(state=stan)

    def _widoczne_wiersze(self):
        """Plan po filtrze i sortowaniu."""
        wiersze = list(self.plan)
        if self.var_tylko_do_wydania.get():
            # Pozycja w pełni wydana znika z listy — chyba że magazynier
            # przygotował ją w tej sesji (wtedy musi ją widzieć).
            wiersze = [p for p in wiersze
                       if (p["pozostalo"] is None or p["pozostalo"] > 0
                           or self.sesja.get(p["symbol"].upper(), 0) > 0)]

        k = self._sort_kolumna

        def klucz(p):
            if k in ("potrzeba", "wydano", "pozostalo", "stan"):
                w = p.get(k)
                return (w is None, _liczba(w))
            if k == "teraz":
                return (False, self.sesja.get(p["symbol"].upper(), 0.0))
            # Pozycje BEZ lokacji na koniec — magazynier i tak musi ich
            # szukać, więc nie mogą rozbijać trasy po regałach.
            wart = str(p.get(k) or "")
            if k == "lokacja":
                # Sortowanie NATURALNE: „R3/P5" ma iść przed „R22/P6".
                # Zwykłe tekstowe dawało R1, R22, R3, R31 — magazynier
                # chodziłby po magazynie w kółko.
                return (not wart, _naturalnie(wart))
            return (not wart, wart.upper())

        wiersze.sort(key=klucz, reverse=self._sort_malejaco)
        return wiersze

    def _status_wiersza(self, p, teraz):
        """Status i kolor wiersza — czytelne bez wczytywania się w liczby."""
        if teraz > 0:
            return "🟢 przygotowane", "gotowe"
        if p["poza_bom"]:
            return "⬤ poza BOM", "poza_bom"
        if p["stan"] <= 0:
            return "⚠ brak na stanie", "brak_stanu"
        if p["pozostalo"] is not None and p["pozostalo"] > p["stan"]:
            return "⚠ za mały stan", "brak_stanu"
        if p["wydano"] > 0:
            return "🟠 częściowo wydane", "czesciowo"
        return "🔴 do wydania", ""

    def _dopisz_historie(self, symbol, nazwa, ilosc, stan, lokacja):
        """Ślad skanu — NAJNOWSZY NA GÓRZE, jak w makiecie."""
        from datetime import datetime
        self.tab_hist.insert("", 0, values=(
            datetime.now().strftime("%H:%M:%S"), symbol, nazwa or "",
            _ilo(ilosc), _ilo(stan) if stan not in (None, "") else "—",
            lokacja or "—"))

    def _podglad_rysunku(self):
        """Powiększenie miniatury — dochodzi razem ze skanowaniem (punkt 3)."""
        pass

    def _podglad_rw(self):
        """Co pójdzie na dokument. NIC nie zapisuje."""
        if not self.sesja:
            return
        okno = tk.Toplevel(self)
        okno.title("Podgląd RW — co powstanie w Subiekcie")
        okno.geometry("820x520")
        okno.transient(self)

        tk.Label(okno, text="ZOSTANIE UTWORZONY DOKUMENT RW — %s"
                 % self.project_name, bg="#2980b9", fg="white",
                 font=("Arial", 10, "bold"), anchor="w", padx=12,
                 pady=8).pack(fill=tk.X)

        stopka = tk.Frame(okno, padx=12, pady=10)
        stopka.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Label(stopka, text="Uwagi: " + self._uwagi_rw().replace("\n", " ⏎ "),
                 font=("", 8), fg="gray30", anchor="w").pack(side=tk.LEFT)
        tk.Button(stopka, text="Zamknij", command=okno.destroy,
                  width=12).pack(side=tk.RIGHT)

        kol = ("Symbol", "Nazwa", "Lokacja", "Źródło", "Ilość", "Uwaga")
        tab = ttk.Treeview(okno, columns=kol, show="headings")
        for c, szer in zip(kol, (150, 240, 90, 65, 65, 150)):
            tab.heading(c, text=c)
            tab.column(c, width=szer, anchor="e" if c == "Ilość" else "w")
        tab.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 0))
        for p in self._pozycje_sesji():
            tab.insert("", "end", values=(
                p["symbol"], p.get("nazwa") or "", p.get("lokacja") or "—",
                p.get("zrodlo") or "—", _ilo(p["ilosc"]),
                "POZA BOM" if p.get("poza_bom") else ""))
        wysrodkuj(okno, self)

    def _uwagi_rw(self):
        """Uwagi dokumentu: numer projektu w 1. wierszu, kto pobrał niżej.

        Pierwszy wiersz należy do numeru projektu — po nim liczą się wydania
        (patrz WydanieStan.cs). „POBRAŁ" idzie do drugiego; Uwagi SIĘ DRUKUJĄ,
        więc nazwisko będzie widoczne na dokumencie.
        """
        from subiekt_zamowienia import zloz_uwagi
        kto = (self.var_pobiera.get() or "").strip()
        return zloz_uwagi(self.project_name,
                          "POBRAŁ: %s" % kto if kto else None)

    # ── wystawienie RW ──────────────────────────────────────────────────

    def _zakoncz(self):
        """ŚWIEŻY ODCZYT → analiza różnic → potwierdzenie → zapis → read-back.

        Świeży odczyt jest OBOWIĄZKOWY (§4 planu): okno nie trzyma locka, więc
        drugi magazynier mógł w międzyczasie wydać to samo. Bez tego dwie sesje
        zdjęłyby ten sam towar dwa razy.
        """
        if not self.sesja:
            return
        if not (self.var_pobiera.get() or "").strip():
            messagebox.showwarning("Wydanie",
                                   "Wybierz osobę w polu „Pobiera”.",
                                   parent=self)
            return

        self.btn_zakoncz.config(state=tk.DISABLED, text="Sprawdzam…")
        self.var_status.set("Ponowny odczyt z Subiekta przed zapisem…")

        def worker():
            try:
                import subiekt_bridge
                import subiekt_stany
                from subiekt_zamowienia import sam_numer
                swiezy = subiekt_bridge.call(
                    "wydanie-stan",
                    {"projekt": sam_numer(self.project_name), "magazyn": MAGAZYN},
                    timeout=300, write=False)
                stany = subiekt_stany.query_stock(
                    sorted({p["symbol"] for p in self._pozycje_sesji()}),
                    timeout=180) or {}
                self.after(0, lambda: self._po_kontroli(swiezy, stany, None))
            except Exception as e:
                self.after(0, lambda: self._po_kontroli(None, None, str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _po_kontroli(self, swiezy, stany, blad):
        self.btn_zakoncz.config(state=tk.NORMAL, text="Zakończ wydanie\n"
                                                      "Utwórz RW w Subiekcie")
        if blad:
            # Bez świeżego odczytu NIE WOLNO wydawać — nie wiemy, co się
            # zmieniło (§4 planu).
            messagebox.showerror(
                "Wydanie wstrzymane",
                "Nie udało się odczytać stanu z Subiekta:\n\n%s\n\n"
                "Bez świeżego odczytu nie wolno wystawić RW — ktoś mógł\n"
                "w międzyczasie wydać ten sam towar." % blad, parent=self)
            return

        # Podmieniamy stan na świeży: to on obowiązuje przy zapisie.
        self.stan = {(p.get("symbol") or "").strip().upper(): p
                     for p in (swiezy or {}).get("pozycje", [])}
        self.rw_bez_projektu = (swiezy or {}).get("rw_bez_projektu") or []

        braki, ponad = [], []
        for p in self._pozycje_sesji():
            klucz = p["symbol"].upper()
            wpis = self.stan.get(klucz) or {}

            # ⛔ STAN — twarda blokada. Subiekt i tak odrzuci dokument.
            k = stany.get(p["symbol"]) or {}
            dostepne = self._stan_w_magazynie(k) if k else 0.0
            razem = _liczba(p["ilosc"])
            if razem > dostepne:
                braki.append((p["symbol"], razem, dostepne))

            # ⚠ POTRZEBA — tylko ostrzeżenie: magazynier trzyma towar w ręku.
            potrzeba = wpis.get("potrzeba")
            if potrzeba is not None:
                wydano = _liczba(wpis.get("wydano"))
                if wydano + razem > _liczba(potrzeba):
                    ponad.append((p["symbol"], _liczba(potrzeba), wydano, razem))

        if braki:
            self._blad_stanu_przy_zapisie(braki)
            return
        if ponad and not self._potwierdz_ponad(ponad):
            return
        self._potwierdz_i_zapisz()

    def _blad_stanu_przy_zapisie(self, braki):
        """Stan spadł poniżej sesji — BEZ „wystaw mimo to" (§4 planu)."""
        lista = "\n".join(
            "   %-20s w sesji %s, na stanie już tylko %s"
            % (s, _ilo(chce), _ilo(jest)) for s, chce, jest in braki[:12])
        messagebox.showerror(
            "Za mało towaru na stanie",
            "Stan magazynu zmienił się od czasu skanowania — ktoś wydał\n"
            "w międzyczasie:\n\n" + lista
            + "\n\nSubiekt nie przyjmie takiego dokumentu. Popraw ilości\n"
              "albo usuń te pozycje z sesji.", parent=self)

    def _potwierdz_ponad(self, ponad):
        """Zmieniła się POTRZEBA — ostrzeżenie z wyjściem „wystaw mimo to"."""
        wiersze = "\n".join(
            "   %-18s potrzeba %s, wydano już %s, teraz %s  →  będzie %s"
            % (s, _ilo(pot), _ilo(wyd), _ilo(ter), _ilo(wyd + ter))
            for s, pot, wyd, ter in ponad[:12])
        return messagebox.askyesno(
            "Stan projektu zmienił się podczas pracy",
            "Po zapisaniu te pozycje przekroczą potrzebę projektu:\n\n"
            + wiersze
            + "\n\nTo może być w porządku — fizyczne wydanie jest ważniejsze\n"
              "od założenia BOM-u. Ale musi być Twoją świadomą decyzją.\n\n"
              "Wystawić mimo to?",
            icon="warning", default="no", parent=self)

    def _potwierdz_i_zapisz(self):
        poz_sesji = self._pozycje_sesji()
        sztuk = sum(_liczba(p["ilosc"]) for p in poz_sesji)
        if not messagebox.askyesno(
                "Potwierdź wydanie",
                "Subiekt utworzy dokument RW:\n\n"
                "    pozycji:  %d\n    sztuk:    %s\n    magazyn:  %s\n"
                "    pobiera:  %s\n    uwagi:    %s\n\n"
                "To ZDEJMIE towar ze stanu magazynu.\n"
                "Dokumentu magazynowego nie cofa się jednym kliknięciem.\n\n"
                "Zapisać?"
                % (len(poz_sesji), _ilo(sztuk), self.var_magazyn.get(),
                   self.var_pobiera.get(),
                   self._uwagi_rw().replace("\n", " ⏎ ")),
                icon="question", default="no", parent=self):
            return

        self.btn_zakoncz.config(state=tk.DISABLED, text="Zapisuję…")
        self.update_idletasks()

        # Sumujemy po symbolu: ten sam detal zeskanowany dwa razy ma pójść
        # jako JEDNA pozycja dokumentu, nie dwie.
        pozycje = [{"symbol": p["symbol"], "ilosc": p["ilosc"]}
                   for p in poz_sesji]

        def worker():
            try:
                from subiekt_magazyn_gui import utworz_rw
                from subiekt_zamowienia import tytul_dokumentu
                # Suchy przebieg PRZED zapisem — dopiero on wie, czy most
                # przyjmie wszystkie pozycje (ten sam wzorzec co PW/RW
                # w kalkulatorze RMPAK).
                sucho = utworz_rw(pozycje, self._uwagi_rw(),
                                  magazyn=self.var_magazyn.get() or MAGAZYN,
                                  zapisz=False, timeout=300,
                                  tytul=tytul_dokumentu(self.project_name))
                kroki = (sucho or {}).get("kroki", [])
                bledy = [k for k in kroki if k.get("Status") == "blad"]
                if bledy:
                    self.after(0, lambda: self._po_zapisie(None, bledy, True))
                    return
                # Suchy przebieg przeszedł — decyzję o pozycjach bez ceny
                # podejmuje GŁÓWNY wątek (pytanie w okienku), potem on woła
                # właściwy zapis. Wątek roboczy nie może czekać na odpowiedź
                # użytkownika: zablokowałby GUI, które ma ją pokazać.
                self.after(0, lambda: self._zapisz_po_suchym(pozycje, kroki))
            except Exception as e:
                self.after(0, lambda: self._po_zapisie(None, [{"Szczegoly": str(e)}], True))

        threading.Thread(target=worker, daemon=True).start()

    def _zapisz_po_suchym(self, pozycje, kroki):
        """Suchy przebieg OK → ewentualne pytanie → właściwy zapis."""
        # Pozycje bez ceny przyjęcia NIE blokują wydania: towar fizycznie
        # wychodzi z magazynu. Ale wartość dokumentu będzie zaniżona i
        # magazynier ma to zobaczyć PRZED zapisem, nie po.
        bez_ceny = [k for k in kroki if k.get("Status") == "bez-wyceny"]
        if bez_ceny:
            lista = "\n".join("   %-20s %s" % (k.get("Symbol") or "?",
                                               k.get("Szczegoly") or "")
                              for k in bez_ceny[:12])
            if not messagebox.askyesno(
                    "Pozycje bez ceny przyjęcia",
                    "Te pozycje nie mają ceny przyjęcia, więc NIE podniosą\n"
                    "wartości dokumentu RW:\n\n" + lista
                    + "\n\nTowar i tak zejdzie ze stanu — to tylko wartość\n"
                      "księgowa dokumentu będzie zaniżona.\n\nWystawić mimo to?",
                    icon="warning", default="yes", parent=self):
                self.btn_zakoncz.config(state=tk.NORMAL,
                                        text="Zakończ wydanie\n"
                                             "Utwórz RW w Subiekcie")
                return

        self.btn_zakoncz.config(state=tk.DISABLED, text="Zapisuję…")

        def worker():
            try:
                from subiekt_magazyn_gui import utworz_rw
                from subiekt_zamowienia import tytul_dokumentu
                wynik = utworz_rw(pozycje, self._uwagi_rw(),
                                  magazyn=self.var_magazyn.get() or MAGAZYN,
                                  zapisz=True, timeout=600,
                                  tytul=tytul_dokumentu(self.project_name))
                self.after(0, lambda: self._po_zapisie(wynik, None, False))
            except Exception as e:
                self.after(0, lambda: self._po_zapisie(None, [{"Szczegoly": str(e)}], False))

        threading.Thread(target=worker, daemon=True).start()

    def _po_zapisie(self, wynik, bledy, sucho):
        self.btn_zakoncz.config(state=tk.NORMAL, text="Zakończ wydanie\n"
                                                      "Utwórz RW w Subiekcie")
        if bledy:
            opis = "\n".join("• %s" % (k.get("Szczegoly") or k.get("Status"))
                             for k in bledy[:10])
            messagebox.showerror(
                "RW nie powstało" if sucho else "Zapis nieudany",
                ("Suchy przebieg zgłosił problemy — NIC nie zapisano:\n\n"
                 if sucho else "Subiekt odrzucił zapis:\n\n") + opis,
                parent=self)
            return

        numer = (wynik or {}).get("numer") or ""
        if not (wynik or {}).get("zapisano") or not numer:
            messagebox.showwarning(
                "Nie potwierdzono zapisu",
                "Most nie potwierdził numeru dokumentu.\n\n"
                "NIE wystawiaj drugiego RW — sprawdź najpierw w Subiekcie,\n"
                "czy dokument powstał.", parent=self)
            return

        poz_sesji = self._pozycje_sesji()
        sztuk = sum(_liczba(p["ilosc"]) for p in poz_sesji)
        messagebox.showinfo(
            "Wydanie zapisane",
            "✓ Wystawiono %s\n✓ %d pozycji, %s szt.\n"
            "✓ zapisano wydanie dla projektu %s\n\nPobrał: %s"
            % (numer, len(poz_sesji), _ilo(sztuk), self.project_name,
               self.var_pobiera.get()), parent=self)

        # Sesja zamknięta — kolejne wydanie zaczyna się od zera, a liczby
        # „wydano wcześniej" muszą już uwzględniać ten dokument.
        self.sesja = {}
        self._odswiez_plan()
        self._wyczysc_pozycje()
        self._odswiez()


def open_window(parent, project_id, project_name=None):
    """Punkt wejścia dla RM_BAZA."""
    if not project_id:
        messagebox.showwarning("Wydanie z magazynu",
                               "Najpierw wybierz projekt.", parent=parent)
        return None
    return WydanieWindow(parent, project_id, project_name)


if __name__ == "__main__":
    import sys
    root = tk.Tk()
    root.withdraw()
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 71
    nazwa = sys.argv[2] if len(sys.argv) > 2 else "3500 dupal"
    w = open_window(root, pid, nazwa)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
