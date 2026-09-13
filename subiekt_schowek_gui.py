# -*- coding: utf-8 -*-
"""Okno „Schowek wydań" — bufor montażowy, obok okna „Wydaj".

Zbudowane NA oknie wydania (`WydanieWindow`), nie obok niego: skaner,
miniatury rysunku, alarm awarii mostu, suchy przebieg i read-back są tam
już dopracowane i przetestowane. Dziedziczymy je i nadpisujemy wyłącznie
to, co w schowku działa inaczej.

JEDEN SCHOWEK NA PROJEKT, MONTER W KOLUMNIE
───────────────────────────────────────────
Nie ma listy schowków do wybierania — zeskanowana pozycja ląduje OD RAZU
w tabeli po prawej. Kto pobrał, zapisuje się przy pozycji (kolumna
„Pobrał"), więc jeden schowek obsługuje wszystkich monterów pracujących
przy tym projekcie. Wcześniejszy wariant z listą schowków po lewej został
wyrzucony jako zbędny krok między skanem a wynikiem.

Monter bierze się z pola „Pobiera" w nagłówku — zmiana pola przed skanem
przypisze kolejne pozycje komu innemu.

CZYM SIĘ RÓŻNI OD OKNA WYDAŃ
────────────────────────────
* Prawa tabela pokazuje ZAWARTOŚĆ SCHOWKA (bilans ruchów), nie „co zostało
  do wydania w projekcie".
* Dwa kierunki skanowania: „Dodaj do schowka" (+N) i „Zdejmij ze schowka"
  (−N, zwrot od montera). Zwrot tego samego dnia znosi pobranie i NIE
  zostawia śladu na RW — to jest sedno całego pomysłu.
* Przy rozliczeniu pozycje spoza BOM-u dopisują się do arkusza
  (SCHOWEK_RW_ALGORYTM.md) — okno wydań tego nie robi.

Specyfikacje: BUFOR_SCHOWEK_MONTAZOWY.md, SCHOWEK_RW_ALGORYTM.md
"""

import tkinter as tk
from tkinter import ttk, messagebox

import subiekt_schowek as SCH
import subiekt_schowek_bom as BOM
from subiekt_wydanie_gui import (
    WydanieWindow, TLO_SEKCJI, TEKST, TEKST_SZARY, OK_ZIELONY,
    BLAD_TLO, UWAGA_TLO, wysrodkuj, _ilo, _liczba,
)


#: Kolumny tabeli schowka. „Potrzeba / Wydano / Pozostało" pokazujemy, bo
#: schowek jest zawsze przypięty do projektu — magazynier ma widzieć, ile
#: z tego, co bierze, było w ogóle planowane.
KOL_SCHOWEK = [("lp", "Lp.", 32), ("symbol", "Symbol", 118),
               ("nazwa", "Nazwa", 168), ("potrzeba", "Potrzeba", 56),
               ("wydano", "Wydano", 52), ("schowek", "W schowku", 66),
               ("pozostalo", "Pozost.", 52), ("stan", "Stan", 46),
               ("pobral", "Pobrał", 104)]


class SchowekWindow(WydanieWindow):
    """Schowek wydań — skan do bufora, rozliczenie jednym RW."""

    def __init__(self, parent, project_id, project_name=None,
                 con_projektu=None, mamy_lock=False):
        #: Arkusz RM_BAZA — bierzemy z niego POŁĄCZENIE I LOCK NA ŚWIEŻO,
        #: w chwili zapisu.
        #:
        #: ⚠️ NIE wolno zapamiętać `project_con` przy otwieraniu okna:
        #: RM_BAZA zamyka i otwiera to połączenie przy każdym przełączeniu
        #: projektu i przy przejmowaniu locka, więc zapamiętany uchwyt
        #: wywala się jako „Cannot operate on a closed database" (13.09.2026,
        #: pozycja 2627-200.12 w projekcie 3500). Z tego samego powodu lock
        #: czytamy na bieżąco — mógł dojść albo zniknąć, odkąd okno stoi.
        self._arkusz = parent
        self._con_awaryjne = con_projektu
        self._lock_awaryjny = bool(mamy_lock)
        #: Jeden schowek na projekt — zakładany przy pierwszym skanie.
        self.schowek_id = None
        #: Zawartość: [{symbol, nazwa, ilosc, monterzy}]
        self.zawartosc = []
        super().__init__(parent, project_id, project_name)
        self.title("Schowek wydań — %s" % self.project_name)

    # ── budowa: różnice względem okna wydań ──────────────────────────────
    def _panel_sesji(self, rodzic):
        ram = tk.Frame(rodzic, bg=TLO_SEKCJI, bd=1, relief=tk.SOLID)
        ram.pack(fill=tk.BOTH, expand=True)

        naglowek = tk.Frame(ram, bg=TLO_SEKCJI)
        naglowek.pack(fill=tk.X, padx=10, pady=(8, 0))
        tk.Label(naglowek, text="🧺  Schowek — do wydania", bg=TLO_SEKCJI,
                 fg=TEKST, font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        self.var_licznik = tk.StringVar(value="0 pozycji")
        tk.Label(naglowek, textvariable=self.var_licznik, bg=TLO_SEKCJI,
                 fg=TEKST_SZARY, font=("Arial", 9)).pack(side=tk.RIGHT)

        self.var_podtytul = tk.StringVar(
            value="Skanuj detale — wydanie powstanie na koniec, jednym RW")
        tk.Label(ram, textvariable=self.var_podtytul, bg=TLO_SEKCJI,
                 fg=TEKST_SZARY, font=("Arial", 8), anchor="w").pack(
            fill=tk.X, padx=10, pady=(0, 4))

        # STOPKA PRZED TABELĄ — tabela z expand=True zjadłaby wysokość
        # i przyciski wypadłyby poza okno (ta sama pułapka co w oknie wydań).
        stopka = tk.Frame(ram, bg=TLO_SEKCJI)
        stopka.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

        kafel = tk.Frame(stopka, bg="#f4f6f7", bd=1, relief=tk.SOLID)
        kafel.pack(side=tk.LEFT, padx=(0, 10))
        self.var_w_schowku = tk.StringVar(value="0 pozycji / 0 szt.")
        self.var_ostatni = tk.StringVar(value="—")
        for i, (tytul, zmienna, kolor) in enumerate((
                ("W schowku:", self.var_w_schowku, TEKST),
                ("Ostatni ruch:", self.var_ostatni, OK_ZIELONY))):
            tk.Label(kafel, text=tytul, bg="#f4f6f7", fg=TEKST,
                     font=("Arial", 9, "bold"), anchor="w").grid(
                row=i, column=0, sticky="w", padx=(10, 16),
                pady=(6 if i == 0 else 0, 6))
            tk.Label(kafel, textvariable=zmienna, bg="#f4f6f7", fg=kolor,
                     font=("Arial", 11, "bold"), anchor="e").grid(
                row=i, column=1, sticky="e", padx=(0, 12))

        self.btn_zakoncz = tk.Button(
            stopka, text="Wydaj / Utwórz RW\nw Subiekcie",
            command=self._zakoncz, bg="#27ae60", fg="white",
            font=("Arial", 10, "bold"), padx=14, state=tk.DISABLED)
        self.btn_zakoncz.pack(side=tk.RIGHT)
        self.btn_podglad_rw = tk.Button(
            stopka, text="📄 Podgląd RW", command=self._podglad_rw,
            font=("Arial", 9), padx=12, state=tk.DISABLED)
        self.btn_podglad_rw.pack(side=tk.RIGHT, padx=(0, 8))

        akcje = tk.Frame(ram, bg=TLO_SEKCJI)
        akcje.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 4))
        # „Usuń pozycję" kasuje CAŁĄ historię symbolu — to cofnięcie pomyłki
        # skanowania, nie zwrot. Zwrot robi się skanem w trybie „Zdejmij",
        # bo tylko wtedy zostaje ślad kto i kiedy oddał.
        tk.Button(akcje, text="🗑 Usuń pozycję (pomyłka)",
                  command=self._usun_z_sesji, font=("Arial", 8)).pack(side=tk.LEFT)
        tk.Button(akcje, text="🕘 Historia ruchów", command=self._historia,
                  font=("Arial", 8)).pack(side=tk.LEFT, padx=6)
        tk.Button(akcje, text="✖ Wyczyść schowek", command=self._wyczysc_sesje,
                  font=("Arial", 8)).pack(side=tk.LEFT)

        wrap = tk.Frame(ram, bg=TLO_SEKCJI)
        wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 0))
        self.tab = ttk.Treeview(wrap, columns=[k[0] for k in KOL_SCHOWEK],
                                show="headings", selectmode="browse")
        for klucz, tytul, szer in KOL_SCHOWEK:
            self.tab.heading(klucz, text=tytul)
            self.tab.column(klucz, width=szer, minwidth=32,
                            stretch=(klucz == "nazwa"),
                            anchor="w" if klucz in ("symbol", "nazwa", "pobral")
                            else "e")
        sc = ttk.Scrollbar(wrap, orient="vertical", command=self.tab.yview)
        sc_x = ttk.Scrollbar(wrap, orient="horizontal", command=self.tab.xview)
        self.tab.configure(yscrollcommand=sc.set, xscrollcommand=sc_x.set)
        sc_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tab.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        self.tab.tag_configure("brak_stanu", background=BLAD_TLO)
        self.tab.tag_configure("poza_bom", background="#f4ecf7")
        self.tab.bind("<Delete>", lambda _e: self._usun_z_sesji())

    def _panel_skanera(self, rodzic):
        super()._panel_skanera(rodzic)
        # DWA kierunki zamiast jednego przycisku. Różnią się kolorem, bo
        # pomyłka kierunku to błędny stan magazynu.
        self.btn_dodaj.config(text="➜  DODAJ DO SCHOWKA  (Enter)",
                              bg="#2980b9", fg="white")
        self.btn_zdejmij = tk.Button(
            self.btn_dodaj.master, text="←  ZDEJMIJ ZE SCHOWKA  (zwrot)",
            command=self._zdejmij, font=("Arial", 9, "bold"),
            bg="#e67e22", fg="white", state=tk.DISABLED)
        self.btn_zdejmij.pack(fill=tk.X, pady=(4, 0))

    # ── stan arkusza czytany NA ŚWIEŻO ───────────────────────────────────
    def _con_projektu(self):
        """Aktualne połączenie arkusza do bazy projektu albo None.

        Pytamy arkusz za każdym razem, bo między otwarciem okna a zapisem
        mógł przełączyć projekt lub przejąć lock — a wtedy stary uchwyt
        jest już zamknięty.
        """
        con = None
        db = getattr(self._arkusz, "db_manager", None)
        if db is not None:
            con = getattr(db, "project_con", None)
        if con is None:
            con = self._con_awaryjne
        if con is None:
            return None
        try:
            con.execute("SELECT 1")          # żywe? (zamknięte rzuca wyjątek)
        except Exception:
            return None
        return con

    def _czy_lock(self):
        """Czy arkusz TERAZ trzyma lock tego projektu."""
        stan = getattr(self._arkusz, "have_lock", None)
        return bool(self._lock_awaryjny if stan is None else stan)

    # ── schowek projektu ─────────────────────────────────────────────────
    def _schowek(self):
        """Schowek TEGO projektu — zakładany przy pierwszym użyciu.

        Jeden na projekt: pozycje różnych monterów leżą razem, rozróżnia
        je kolumna „Pobrał". Dzięki temu magazynier nie wybiera schowka
        przed skanowaniem.
        """
        if self.schowek_id is not None:
            try:
                return SCH.pobierz(self.schowek_id)
            except SCH.BladSchowka:
                self.schowek_id = None
        for s in SCH.lista(tylko_otwarte=True, projekt=self.project_name):
            if s.get("projekt") == self.project_name:
                self.schowek_id = s["id"]
                return s
        return None

    def _schowek_lub_zaloz(self):
        s = self._schowek()
        if s:
            return s
        monter = (self.var_pobiera.get() or "").strip()
        self.schowek_id = SCH.utworz(monter or "—", projekt=self.project_name)
        return SCH.pobierz(self.schowek_id)

    def _odswiez_zawartosc(self):
        s = self._schowek()
        if not s:
            self.zawartosc = []
            self.var_podtytul.set(
                "Skanuj detale — wydanie powstanie na koniec, jednym RW")
            return self._przerysuj()
        try:
            self.zawartosc = self._bilans_z_monterami(s["id"])
        except SCH.BladSchowka as e:
            self.zawartosc = []
            self._uwaga("⛔ %s" % e, BLAD_TLO)
        self.var_podtytul.set(
            "Schowek #%s otwarty od %s   ·   projekt %s   ·   "
            "wydanie powstanie na koniec, jednym RW"
            % (s["id"], s["data"], self.project_name))
        self._przerysuj()

    def _bilans_z_monterami(self, schowek_id):
        """Bilans netto + KTO pobrał daną pozycję.

        Monter siedzi przy każdym ruchu, a nie przy schowku, więc jedna
        pozycja może mieć kilku — wtedy pokazujemy ich po przecinku.
        Liczą się tylko ci, którzy mają dodatni wkład: kto wziął i oddał,
        nie zostaje na liście, bo nic nie wynosi z magazynu.
        """
        wklad = {}
        for r in SCH.historia(schowek_id):
            k = (r["symbol"] or "").strip().upper()
            kto = (r.get("monter") or "").strip()
            if kto:
                wklad.setdefault(k, {})
                wklad[k][kto] = wklad[k].get(kto, 0.0) + float(r["ilosc"])
        out = []
        for p in SCH.stan_schowka(schowek_id):
            ludzie = [n for n, ile in sorted(
                wklad.get(p["symbol"].strip().upper(), {}).items()) if ile > 0]
            out.append(dict(p, monterzy=", ".join(ludzie)))
        return out

    def _przerysuj(self):
        self.tab.delete(*self.tab.get_children())
        for i, p in enumerate(self.zawartosc, 1):
            wpis = self.stan.get(p["symbol"].upper()) or {}
            stan_mag = self._stan_symbolu(p["symbol"])
            potrzeba = wpis.get("potrzeba")
            wart = {
                "lp": i, "symbol": p["symbol"], "nazwa": p["nazwa"],
                "schowek": _ilo(p["ilosc"]),
                "stan": _ilo(stan_mag) if stan_mag is not None else "—",
                "pobral": p.get("monterzy") or "—",
                "potrzeba": _ilo(potrzeba) if potrzeba is not None else "—",
                "wydano": _ilo(wpis.get("wydano", 0)) if wpis else "—",
                "pozostalo": (_ilo(max(0.0, float(potrzeba)
                                       - float(wpis.get("wydano", 0))))
                              if potrzeba is not None else "—"),
            }
            # Czerwone TYLKO gdy stan jest ZNANY i faktycznie za mały —
            # patrz `_stan_symbolu`.
            tagi = ()
            if stan_mag is not None and p["ilosc"] > stan_mag:
                tagi = ("brak_stanu",)
            elif not wpis:
                tagi = ("poza_bom",)      # nie ma jej w ZK ani PW projektu
            self.tab.insert("", tk.END, iid=p["symbol"],
                            values=[wart[k] for k, _, _ in KOL_SCHOWEK],
                            tags=tagi)
        szt = sum(p["ilosc"] for p in self.zawartosc)
        self.var_licznik.set("%d pozycji" % len(self.zawartosc))
        self.var_w_schowku.set("%d pozycji / %s szt."
                               % (len(self.zawartosc), _ilo(szt)))
        gotowy = bool(self.zawartosc)
        self.btn_zakoncz.config(state=tk.NORMAL if gotowy else tk.DISABLED)
        self.btn_podglad_rw.config(state=tk.NORMAL if gotowy else tk.DISABLED)

    def _stan_symbolu(self, symbol):
        """Stan magazynu z PLANU albo None, gdy nieznany.

        ⚠️ Rozróżnienie „0" od „nie wiem" jest tu istotne. `_zbuduj_plan`
        wpisuje `stan: 0.0` także wtedy, gdy kartoteka w ogóle nie przyszła
        z Subiekta (`… if k else 0.0`) — dla okna wydań to bez znaczenia, bo
        ono pokazuje wyłącznie pozycje z ZK/PW. W schowku bywają detale
        spoza BOM-u, więc zwrócenie zera malowałoby je na czerwono jako
        „brak stanu", choć stanu po prostu nie sprawdzono.
        """
        klucz = (symbol or "").strip().upper()
        for w in (self.plan or ()):
            if (w.get("symbol") or "").strip().upper() == klucz:
                stan = w.get("stan")
                if not stan and not (w.get("nazwa") or "").strip():
                    return None
                return stan
        return None

    def _odswiez_plan(self):
        """Prawa tabela pokazuje SCHOWEK, nie plan projektu.

        Dane z Subiekta nadal się wczytują — zasilają kolumny „potrzeba /
        wydano / stan" — ale rysuje je `_przerysuj`.
        """
        self._przerysuj()

    def _po_odczycie(self, dane, blad, kartoteki=None):
        super()._po_odczycie(dane, blad, kartoteki)
        if not blad:
            self._odswiez_zawartosc()

    # ── ruchy ────────────────────────────────────────────────────────────
    def _ruch(self, kierunek):
        """Wspólna obsługa obu przycisków — różni je funkcja i etykieta."""
        if not self.polaczony:
            return self._uwaga("⛔ Brak połączenia z Subiektem — "
                               "kliknij „Odśwież”.", BLAD_TLO)
        p = getattr(self, "poz_biezaca", None)
        if not p:
            return self._uwaga("⛔ Najpierw zeskanuj pozycję.", BLAD_TLO)
        monter = (self.var_pobiera.get() or "").strip()
        if not monter:
            self._uwaga("⛔ Wybierz w nagłówku, KTO pobiera — "
                        "nazwisko trafia do pozycji.", BLAD_TLO)
            return self.combo_pobiera.focus_set()
        ile = _liczba(self.var_ilosc.get(), 0.0)
        if ile <= 0:
            self._uwaga("⛔ Podaj ilość większą od zera.", BLAD_TLO)
            return self.spin_ilosc.focus_set()

        s = self._schowek_lub_zaloz()
        funkcja = SCH.pobrano if kierunek > 0 else SCH.oddano
        etykieta = "POBRANO" if kierunek > 0 else "ODDANO"
        try:
            teraz = funkcja(s["id"], p["symbol"], ile, nazwa=p.get("nazwa"),
                            operator=(self.var_wydal.get() or "").strip(),
                            monter=monter)
        except SCH.BladSchowka as e:
            return self._uwaga("⛔ %s" % e, BLAD_TLO)

        self._odswiez_zawartosc()
        self.var_ostatni.set("%s %s szt. — %s (%s)"
                             % (etykieta, _ilo(ile), p["symbol"], monter))
        self._uwaga("✓ %s: %s %s szt.   ·   w schowku: %s szt.   ·   %s"
                    % (etykieta, p["symbol"], _ilo(ile), _ilo(teraz), monter),
                    "#e8f8e8" if kierunek > 0 else UWAGA_TLO)
        try:
            self.bell()
        except tk.TclError:
            pass
        if self.tab.exists(p["symbol"]):
            self.tab.selection_set(p["symbol"])
            self.tab.see(p["symbol"])
        self._wyczysc_pozycje(zostaw_uwage=True)

    def _dodaj_do_sesji(self):
        """Enter / „Dodaj do schowka" — monter WZIĄŁ element (+N)."""
        self._ruch(+1)

    def _zdejmij(self):
        """Zwrot od montera (−N).

        To NIE jest usunięcie pozycji z listy: zostaje ślad w historii, kto
        i kiedy oddał. Dzięki temu „wziął i oddał tego samego dnia" znosi
        się do zera i nie trafia na RW — po to jest cały schowek.
        """
        self._ruch(-1)

    def _usun_z_sesji(self):
        s = self._schowek()
        symbol = self._zaznaczony()
        if not s or not symbol:
            return
        if not messagebox.askyesno(
                "Usuń pozycję",
                "Usunąć „%s” ze schowka razem z całą historią ruchów?\n\n"
                "To jest cofnięcie POMYŁKI skanowania — nie zostanie żaden "
                "ślad.\nJeśli monter fizycznie oddaje element, użyj "
                "„Zdejmij ze schowka”." % symbol, parent=self):
            return
        try:
            SCH.usun_pozycje(s["id"], symbol)
        except SCH.BladSchowka as e:
            return self._uwaga("⛔ %s" % e, BLAD_TLO)
        self._odswiez_zawartosc()

    def _wyczysc_sesje(self):
        s = self._schowek()
        if not s:
            return
        if not messagebox.askyesno(
                "Wyczyść schowek",
                "Usunąć WSZYSTKIE ruchy ze schowka?\n\n"
                "Historia przepadnie — to nie jest zwrot towaru.",
                parent=self):
            return
        try:
            SCH.wyczysc(s["id"])
        except SCH.BladSchowka as e:
            return self._uwaga("⛔ %s" % e, BLAD_TLO)
        self._odswiez_zawartosc()

    def _historia(self):
        s = self._schowek()
        if not s:
            return self._uwaga("Schowek jest pusty — nie ma historii.", None)
        okno = tk.Toplevel(self)
        okno.title("Historia ruchów — schowek #%s" % s["id"])
        okno.geometry("780x460")
        okno.transient(self)
        tk.Label(okno, text="Każdy skan, od najnowszego. "
                            "Ruchy ujemne to zwroty od montera.",
                 bg="#2980b9", fg="white", font=("Arial", 10, "bold"),
                 anchor="w", padx=12, pady=6).pack(fill=tk.X)
        kol = [("czas", "Czas", 130), ("symbol", "Symbol", 130),
               ("nazwa", "Nazwa", 190), ("ilosc", "Ruch", 70),
               ("monter", "Pobrał/oddał", 120), ("operator", "Wydał", 100)]
        tab = ttk.Treeview(okno, columns=[k[0] for k in kol], show="headings")
        for k, n, w in kol:
            tab.heading(k, text=n)
            tab.column(k, width=w, anchor="e" if k == "ilosc" else "w")
        tab.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        tab.tag_configure("oddane", background=UWAGA_TLO)
        try:
            for r in SCH.historia(s["id"]):
                tab.insert("", tk.END, tags=("oddane",) if r["ilosc"] < 0 else (),
                           values=(r["czas"], r["symbol"], r.get("nazwa", ""),
                                   ("+" if r["ilosc"] > 0 else "") + _ilo(r["ilosc"]),
                                   r.get("monter", ""), r.get("operator", "")))
        except SCH.BladSchowka as e:
            messagebox.showerror("Historia", str(e), parent=okno)
        wysrodkuj(okno, self)

    # ── rozliczenie ──────────────────────────────────────────────────────
    def _pozycje_sesji(self):
        """Co pójdzie na RW — bilans netto schowka.

        Nadpisuje wersję z okna wydań, żeby cała maszyneria kontroli przed
        zapisem (świeży odczyt, porównanie ze stanem, suchy przebieg,
        read-back) działała bez zmian — różni się tylko ŹRÓDŁO pozycji.
        """
        return [dict(p) for p in self.zawartosc]

    @property
    def sesja(self):
        """Zgodność z oknem wydań: {SYMBOL: ilość}."""
        return {p["symbol"]: p["ilosc"] for p in getattr(self, "zawartosc", [])}

    @sesja.setter
    def sesja(self, _wartosc):
        # Okno wydań zeruje sesję po zapisie; w schowku o stanie decyduje
        # plik roboczy, więc podstawienie ignorujemy.
        pass

    def _uwagi_rw(self):
        """Uwagi RW: numer projektu w 1. wierszu, ludzie niżej.

        Monterów wypisujemy z POZYCJI, nie z pola w nagłówku — przy jednym
        schowku na projekt bywa ich kilku, a Uwagi się drukują, więc na
        dokumencie ma być widać, komu towar poszedł.
        """
        from subiekt_zamowienia import zloz_uwagi
        czesci = []
        wydal = (self.var_wydal.get() or "").strip()
        if wydal:
            czesci.append("WYDAŁ: %s" % wydal)
        ludzie = []
        for p in self.zawartosc:
            for n in (p.get("monterzy") or "").split(","):
                n = n.strip()
                if n and n not in ludzie:
                    ludzie.append(n)
        if ludzie:
            czesci.append("POBRAŁ: %s" % ", ".join(ludzie))
        return zloz_uwagi(self.project_name,
                          "   ".join(czesci) if czesci else None)

    def _zapisz_po_suchym(self, pozycje, kroki):
        """⛔ BRAMKA: BOM najpierw, RW dopiero po potwierdzeniu.

        Wydanie z Subiekta nie może pojawić się wcześniej niż wiersz, do
        którego ma się przypiąć (SCHOWEK_RW_ALGORYTM.md §4.3). Dlatego
        pozycje spoza BOM-u dopisujemy TU, przed zapisem — a gdy się nie
        uda, RW w ogóle nie powstaje.
        """
        try:
            import rm_klient
            dopisane, odlozone = BOM.przygotuj(
                self._con_projektu(), rm_klient, self.project_id, pozycje,
                self._czy_lock(), kto=(self.var_wydal.get() or "").strip())
        except Exception as e:
            # ŁAPIEMY WSZYSTKO, nie tylko BladBom: wyjątek lecący z `after`
            # nie ma kto obsłużyć, więc przycisk zostawałby na „Zapisuję…"
            # i okno wyglądałoby na zawieszone (13.09.2026).
            self.btn_zakoncz.config(state=tk.NORMAL,
                                    text="Wydaj / Utwórz RW\nw Subiekcie")
            return messagebox.showerror(
                "RW nie zostało wystawione",
                "%s\n\nTowar NIE zszedł ze stanu, schowek został nietknięty."
                % e, parent=self)
        self._po_bom = (dopisane, odlozone)
        super()._zapisz_po_suchym(pozycje, kroki)

    def _po_zapisie(self, wynik, bledy, sucho):
        super()._po_zapisie(wynik, bledy, sucho)
        if bledy or sucho or not (wynik or {}).get("numer"):
            return
        # „Ilość dostarczonych" = ile detalu dotarło na projekt, wszystko
        # jedno czy od dostawcy, czy z magazynu (decyzja 13.09.2026:
        # „wydane to ma iść do odebrane"). Dopisujemy PO potwierdzonym RW,
        # nigdy przed — inaczej arkusz pokazywałby ilość bez pokrycia
        # w dokumencie.
        pozycje = self._pozycje_sesji()
        con = self._con_projektu()
        if con is not None and self._czy_lock():
            try:
                BOM.dopisz_wydane(con, self.project_id, pozycje)
            except Exception as e:
                messagebox.showwarning(
                    "Arkusz nie zaktualizowany",
                    "RW %s powstało i towar zszedł ze stanu, ale nie udało "
                    "się dopisać ilości do arkusza:\n%s\n\n"
                    "Popraw „Ilość dostarczonych” ręcznie."
                    % (wynik["numer"], e), parent=self)
        else:
            # Bez locka baza projektu jest READ-ONLY. Nie zapisujemy po cichu
            # w próżnię — magazynier musi wiedzieć, czemu arkusz się nie zmienił.
            messagebox.showinfo(
                "Arkusz bez zmian — brak locka",
                "RW %s powstało, towar zszedł ze stanu.\n\n"
                "„Ilość dostarczonych” w arkuszu NIE została zwiększona, bo "
                "projekt nie jest przejęty.\nPrzejmij lock i popraw ręcznie "
                "albo wystawiaj wydania przy przejętym projekcie."
                % wynik["numer"], parent=self)

        s = self._schowek()
        if s:
            try:
                SCH.oznacz_rozliczony(s["id"], wynik["numer"])
                self.schowek_id = None      # następny skan założy nowy
            except SCH.BladSchowka as e:
                messagebox.showwarning(
                    "Schowek nie zamknięty",
                    "RW %s powstało, ale nie udało się zamknąć schowka:\n%s\n\n"
                    "Wyczyść go ręcznie, żeby nie wydać tego drugi raz."
                    % (wynik["numer"], e), parent=self)
        # Pozycje odłożone w poczekalni: magazynier zajrzy do arkusza i ich
        # nie znajdzie, więc musi wiedzieć, czemu i kiedy się pojawią.
        _, odlozone = getattr(self, "_po_bom", (0, 0))
        if odlozone:
            messagebox.showinfo(
                "Nowe pozycje czekają na lock",
                "%d nowych pozycji pojawi się w arkuszu, gdy ktoś przejmie "
                "projekt.\n\nTeraz lock trzyma kto inny, więc nie dało się "
                "ich dopisać od razu.\nRW jest wystawione — towar zszedł "
                "ze stanu." % odlozone, parent=self)
        self._odswiez_zawartosc()


def open_window(parent, project_id, project_name=None,
                con_projektu=None, mamy_lock=False):
    """Punkt wejścia dla RM_BAZA."""
    if not project_id:
        messagebox.showwarning("Schowek wydań",
                               "Najpierw wybierz projekt.", parent=parent)
        return None
    return SchowekWindow(parent, project_id, project_name,
                         con_projektu=con_projektu, mamy_lock=mamy_lock)
