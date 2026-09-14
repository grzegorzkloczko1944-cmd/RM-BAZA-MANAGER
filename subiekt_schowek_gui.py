# -*- coding: utf-8 -*-
"""Okno „Schowek wydań" — bufor montażowy, obok okna „Wydaj".

Zbudowane NA oknie wydania (`WydanieWindow`), nie obok niego: skaner,
miniatury rysunku, alarm awarii mostu, suchy przebieg i read-back są tam
już dopracowane i przetestowane. Dziedziczymy je i nadpisujemy wyłącznie
to, co w schowku działa inaczej.

JEDEN SCHOWEK, PROJEKT PRZY POZYCJI
───────────────────────────────────
⚠️ Schowek NIE NALEŻY do projektu — jest JEDEN, wspólny dla stanowiska,
a projekt siedzi przy KAŻDEJ POZYCJI (decyzja 14.09.2026: „schowek ma nie
być przypisany do projektu tylko niezależny, pozycje przypisujemy do
projektu").

Magazynier przełącza pole „Projekt" w nagłówku i skanuje — kolejne pozycje
lecą na wybrany projekt. Tak samo działa pole „Pobiera" dla montera.
Zeskanowana pozycja ląduje OD RAZU w tabeli po prawej; nie ma żadnej listy
schowków do wybierania.

Przy rozliczeniu powstaje TYLE RW, ILE PROJEKTÓW w schowku — każdy dokument
musi mieć swój numer w Uwagach, bo po nim Subiekt liczy wydania per projekt.

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
    WydanieWindow, MAGAZYN, TLO_SEKCJI, TEKST, TEKST_SZARY, OK_ZIELONY,
    BLAD_TLO, UWAGA_TLO, wysrodkuj, _ilo, _liczba,
)


#: Kolumny tabeli schowka. „Potrzeba / Wydano / Pozostało" pokazujemy, bo
#: schowek jest zawsze przypięty do projektu — magazynier ma widzieć, ile
#: z tego, co bierze, było w ogóle planowane.
KOL_SCHOWEK = [("lp", "Lp.", 30), ("projekt", "Projekt", 62),
               ("symbol", "Symbol", 112), ("nazwa", "Nazwa", 150),
               ("potrzeba", "Potrzeba", 54), ("wydano", "Wydano", 50),
               ("schowek", "W schowku", 64), ("pozostalo", "Pozost.", 50),
               ("stan", "Stan", 44), ("pobral", "Pobrał", 96)]


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
        #: JEDEN schowek stanowiska — zakładany przy pierwszym skanie.
        self.schowek_id = None
        #: Zawartość: [{symbol, nazwa, ilosc, monterzy}]
        self.zawartosc = []
        super().__init__(parent, project_id, project_name)
        self.title("Schowek wydań — %s" % (self.project_name or "wybierz projekt"))

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
        tk.Button(akcje, text="✏ Popraw ilość", command=self._popraw_ilosc,
                  font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        tk.Button(akcje, text="🗑 Usuń pozycję (pomyłka)",
                  command=self._usun_z_sesji,
                  font=("Arial", 8)).pack(side=tk.LEFT, padx=6)
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
        self.tab.bind("<Double-1>", lambda _e: self._popraw_ilosc())

    def _panel_skanera(self, rodzic):
        super()._panel_skanera(rodzic)
        # DWA KIERUNKI: pobranie i zwrot.
        #
        # ⚠️ RAMKĘ PRZYCISKÓW PRZYPINAMY DO DOŁU (`side=tk.BOTTOM`).
        # Panel skanera ma `pack_propagate(False)` i stałą wysokość, a ramka
        # przycisków jest w nim OSTATNIA — gdy miniatura rysunku zajmie
        # miejsce, cała ramka wypada poza panel i znikają OBA przyciski
        # (14.09.2026: „gdzie jest te zdejmij?" — nie było też „Dodaj").
        # Przypięta do dołu ma pierwszeństwo i zawsze zostaje widoczna.
        przyciski = self.btn_dodaj.master
        przyciski.pack_forget()
        przyciski.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(8, 12))

        self.btn_dodaj.config(text="➜  DODAJ  (Enter)", bg="#2980b9",
                              fg="white")
        self.btn_zdejmij = tk.Button(
            przyciski, text="←  ZDEJMIJ  (zwrot)", command=self._zdejmij,
            font=("Arial", 10, "bold"), bg="#e67e22", fg="white",
            state=tk.DISABLED)
        self.btn_zdejmij.pack(side=tk.LEFT, fill=tk.X, expand=True,
                              padx=(8, 0))

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

    def _pasek_gorny(self):
        """Nagłówek schowka — jak w oknie wydań, ale PROJEKT DO WYBORU.

        Budujemy własny zamiast łatać dziedziczony: wcześniejsza wersja
        wyszukiwała etykietę projektu wśród cudzych widgetów i podmieniała
        ją na combo. Działało w teście, ale w praktyce combo bywało
        niewidoczne — zależało od kolejności i zagnieżdżenia ramek, na które
        nie mamy wpływu (zgłoszone 14.09.2026: „nie widać dobrze comboxa").
        """
        from datetime import datetime

        pasek = self.pasek_gorny = tk.Frame(self, bg=TLO_SEKCJI, height=76)
        pasek.pack(fill=tk.X)
        pasek.pack_propagate(False)
        tk.Frame(self, bg="#d5dbdb", height=1).pack(fill=tk.X)

        def sekcja(ikona, tytul, pierwsza=False):
            ram = tk.Frame(pasek, bg=TLO_SEKCJI)
            ram.pack(side=tk.LEFT, padx=(14 if pierwsza else 22, 0), pady=10)
            gora = tk.Frame(ram, bg=TLO_SEKCJI)
            gora.pack(anchor="w")
            tk.Label(gora, text=ikona, bg=TLO_SEKCJI, fg=TEKST_SZARY,
                     font=("Arial", 11)).pack(side=tk.LEFT, padx=(0, 6))
            tk.Label(gora, text=tytul, bg=TLO_SEKCJI, fg=TEKST_SZARY,
                     font=("Arial", 9)).pack(side=tk.LEFT)
            return ram

        # PROJEKT — WYBIERANY. Schowek jest jeden i niezależny od projektu,
        # więc to magazynier decyduje, na co idzie kolejna zeskanowana
        # pozycja. Szerokie pole, bo nazwy projektów bywają długie.
        s = sekcja("⚙", "Projekt pozycji:", pierwsza=True)
        self.var_projekt = tk.StringVar(value=self.project_name)
        self.combo_projekt = ttk.Combobox(
            s, textvariable=self.var_projekt, width=26, state="readonly",
            font=("Arial", 11, "bold"))
        self.combo_projekt.pack(anchor="w", pady=(2, 0))
        # Wybor projektu dociaga potrzebe i stany — inaczej kolumny
        # „Potrzeba / Wydano" zostalyby puste az do „Odswiez".
        self.combo_projekt.bind("<<ComboboxSelected>>",
                                lambda _e: self._projekt_zmieniony())
        self.var_kontekst = tk.StringVar(value="")
        tk.Label(s, textvariable=self.var_kontekst, bg=TLO_SEKCJI,
                 fg=TEKST_SZARY, font=("Arial", 8), anchor="w").pack(anchor="w")

        s = sekcja("🏠", "Magazyn:")
        self.var_magazyn = tk.StringVar(value=MAGAZYN)
        ttk.Combobox(s, textvariable=self.var_magazyn, width=12,
                     state="readonly", font=("Arial", 10),
                     values=[MAGAZYN]).pack(anchor="w", pady=(2, 0))

        s = sekcja("🔑", "Wydał:")
        self.var_wydal = tk.StringVar()
        self.combo_wydal = ttk.Combobox(s, textvariable=self.var_wydal,
                                        width=18, state="readonly",
                                        font=("Arial", 10))
        self.combo_wydal.pack(anchor="w", pady=(2, 0))

        s = sekcja("👤", "Pobiera:")
        self.var_pobiera = tk.StringVar()
        self.combo_pobiera = ttk.Combobox(s, textvariable=self.var_pobiera,
                                          width=18, state="readonly",
                                          font=("Arial", 10))
        self.combo_pobiera.pack(anchor="w", pady=(2, 0))
        self._wczytaj_osoby()
        self._wczytaj_projekty()

        s = sekcja("📅", "Data:")
        tk.Label(s, text=datetime.now().strftime("%d.%m.%Y"), bg=TLO_SEKCJI,
                 fg=TEKST, font=("Arial", 11), anchor="w").pack(
            anchor="w", pady=(2, 0))

        s = sekcja("📄", "Tworzymy:")
        tk.Label(s, text="RW (magazynowy)", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 11, "bold"), anchor="w").pack(anchor="w")
        tk.Label(s, text="Po jednym na projekt", bg=TLO_SEKCJI,
                 fg=TEKST_SZARY, font=("Arial", 8), anchor="w").pack(anchor="w")

        tk.Button(pasek, text="Odśwież", command=self._odswiez,
                  font=("Arial", 8)).pack(side=tk.RIGHT, padx=14)

        # Diplodok — żart dla magazyniera. Brak pliku niczego nie psuje.
        self._dino = None
        try:
            import os
            from PIL import Image, ImageTk
            plik = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "diplodok.png")
            if os.path.isfile(plik):
                im = Image.open(plik).convert("RGBA")
                im.thumbnail((120, 56), Image.LANCZOS)
                plansza = Image.new("RGBA", im.size, TLO_SEKCJI)
                plansza.alpha_composite(im)
                self._dino = ImageTk.PhotoImage(plansza.convert("RGB"))
                tk.Label(pasek, image=self._dino, bg=TLO_SEKCJI).pack(
                    side=tk.RIGHT, padx=(0, 10))
        except Exception:
            pass

    def _wczytaj_projekty(self):
        """Lista projektów do wyboru — te same, co w selektorze RM_BAZA."""
        nazwy = []
        try:
            db = getattr(self._arkusz, "db_manager", None)
            if db is not None:
                # TYLKO MACHINE. Projekty WAREHOUSE to magazyny wewnetrzne,
                # nie maszyny — nie wydaje sie na nie detali ze schowka
                # (14.09.2026: przez brak filtra do poczekalni trafil
                # projekt 16 CHWYTAK, ktory nie ma nawet pliku bazy).
                nazwy = [w["name"] for w in db.master_read("projekty-do-selektora")
                         if w.get("active")
                         and (w.get("project_type") or "MACHINE") == "MACHINE"]
        except Exception as e:
            print("Nie wczytano listy projektow: %s" % e)
        if self.project_name and self.project_name not in nazwy:
            nazwy.insert(0, self.project_name)
        try:
            self.combo_projekt["values"] = nazwy
            if self.project_name:
                self.var_projekt.set(self.project_name)
        except Exception:
            pass

    def _projekt_zmieniony(self):
        """Magazynier wybrał projekt w nagłówku — dociągamy jego dane.

        Przy pierwszym wyborze (okno otwarte bez projektu) ustawiamy też
        `project_name`, bo od niego zależy odczyt z Subiekta i tytuł okna.
        """
        wybrany = (self.var_projekt.get() or "").strip()
        if not wybrany:
            return
        self.project_name = wybrany
        self.title("Schowek wydań — %s" % wybrany)
        self._odswiez()

    def _projekt_pozycji(self):
        """Numer projektu dla KOLEJNEJ skanowanej pozycji."""
        return SCH.sam_numer(getattr(self, "var_projekt", None)
                             and self.var_projekt.get() or self.project_name)

    # ── schowek stanowiska ─
    def _schowek(self):
        """JEDEN otwarty schowek stanowiska (bez przypisania do projektu)."""
        try:
            s = SCH.biezacy()
            self.schowek_id = s["id"]
            return s
        except SCH.BladSchowka as e:
            self._uwaga("⛔ %s" % e, BLAD_TLO)
            return None

    def _schowek_lub_zaloz(self):
        return self._schowek()

    def _odswiez_zawartosc(self):
        s = self._schowek()
        if not s:
            self.zawartosc = []
            return self._przerysuj()
        try:
            self.zawartosc = SCH.stan_schowka(s["id"])
        except SCH.BladSchowka as e:
            self.zawartosc = []
            self._uwaga("⛔ %s" % e, BLAD_TLO)
        projekty = sorted({p["projekt"] for p in self.zawartosc if p["projekt"]})
        self.var_podtytul.set(
            "Schowek #%s otwarty od %s   ·   %s   ·   "
            "wydanie powstanie na koniec: %s"
            % (s["id"], s["data"],
               ("projekty: " + ", ".join(projekty)) if projekty
               else "pusty — skanuj detale",
               ("%d RW (po jednym na projekt)" % len(projekty)) if len(projekty) > 1
               else "jedno RW"))
        self._przerysuj()

    def _przerysuj(self):
        self.tab.delete(*self.tab.get_children())
        for i, p in enumerate(self.zawartosc, 1):
            wpis = self.stan.get(p["symbol"].upper()) or {}
            stan_mag = self._stan_symbolu(p["symbol"])
            potrzeba = wpis.get("potrzeba")
            wart = {
                "lp": i, "projekt": p.get("projekt") or "—",
                "symbol": p["symbol"], "nazwa": p["nazwa"],
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
            # iid MUSI zawierac projekt: ten sam symbol bywa na dwoch
            # projektach naraz i jako dwa osobne wiersze.
            self.tab.insert("", tk.END,
                            iid="%s|%s" % (p.get("projekt") or "", p["symbol"]),
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

    def _odswiez(self):
        """Stan z Subiekta — TYLKO gdy znamy projekt.

        ⚠️ Bez projektu most odrzuca `wydanie-stan` (pusty numer = kod 1),
        a okno pokazywało to jako CZERWONY ALARM „brak połączenia
        z Subiektem" — mylące, bo połączenie było w porządku, brakowało
        tylko projektu (14.09.2026).

        Schowek działa bez projektu: magazynier wybiera go z listy przed
        pierwszym skanem. Do tego czasu nie ma czego liczyć — kolumny
        „Potrzeba / Wydano" i tak dotyczą konkretnego projektu.
        """
        if not (self.project_name or "").strip():
            self.polaczony = True          # most jest sprawny, brak tylko projektu
            self._ustaw_blokade_awarii(False)
            self.var_polaczenie.set("● Połączono z Subiektem NEXO")
            self.lbl_polaczenie.config(fg=OK_ZIELONY)
            self.var_status.set("Wybierz projekt w nagłówku, żeby zobaczyć "
                                "potrzebę i stany")
            self.stan, self.plan = {}, []
            self._odswiez_zawartosc()
            return
        super()._odswiez()

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

        projekt = self._projekt_pozycji()
        if not projekt:
            return self._uwaga("⛔ Wybierz w nagłówku PROJEKT, na który "
                               "idzie ta pozycja.", BLAD_TLO)
        s = self._schowek_lub_zaloz()
        if not s:
            return
        # ⛔ PONAD STAN — TWARDA BLOKADA. Subiekt i tak odrzuci RW, wiec
        # przepuszczenie tego przesunieloby blad na koniec sesji, gdy
        # magazynier ma juz wszystko zebrane.
        #
        # ⚠️ Od stanu odejmujemy CALY SCHOWEK, nie tylko biezacy projekt:
        # ten sam detal bywa pobrany na kilka projektow naraz, a fizycznie
        # z polki schodzi raz. Liczenie per projekt pozwoliloby wydac
        # trzy razy to samo (14.09.2026).
        if kierunek > 0:
            # ⚠️ STAN BIERZEMY Z ZESKANOWANEJ POZYCJI, nie z planu projektu.
            # `_stan_symbolu` czyta `self.plan`, który zna tylko pozycje z ZK
            # i PW TEGO projektu — dla detalu spoza planu zwracał None
            # i blokada w ogóle się nie wykonywała. `poz_biezaca["stan"]`
            # pochodzi wprost z kartoteki Subiekta, więc jest zawsze
            # (14.09.2026: 3455 szt. weszło przy stanie 0).
            stan = p.get("stan")
            if stan is None:
                stan = self._stan_symbolu(p["symbol"])
            if stan is not None:
                w_schowku = sum(x["ilosc"] for x in self.zawartosc
                                if x["symbol"].strip().upper()
                                == p["symbol"].strip().upper())
                wolne = stan - w_schowku
                if ile > wolne:
                    return self._ponad_stan(p, ile, wolne, w_schowku)

        funkcja = SCH.pobrano if kierunek > 0 else SCH.oddano
        etykieta = "POBRANO" if kierunek > 0 else "ODDANO"
        try:
            teraz = funkcja(s["id"], p["symbol"], ile, nazwa=p.get("nazwa"),
                            operator=(self.var_wydal.get() or "").strip(),
                            monter=monter, projekt=projekt)
        except SCH.BladSchowka as e:
            # Zwrot bez pokrycia w schowku to najczęściej zwrot PO wydaniu:
            # towar zszedł już ze stanu dokumentem RW, więc nie ma czego
            # odejmować od bufora — trzeba go PRZYJĄĆ z powrotem.
            if kierunek < 0:
                return self._zwrot_po_rw(p, ile, projekt, monter, str(e))
            return self._uwaga("⛔ %s" % e, BLAD_TLO)

        self._odswiez_zawartosc()
        self.var_ostatni.set("%s %s szt. — %s → %s (%s)"
                             % (etykieta, _ilo(ile), p["symbol"], projekt, monter))
        self._uwaga("✓ %s: %s %s szt. na projekt %s   ·   w schowku: %s szt."
                    "   ·   %s"
                    % (etykieta, p["symbol"], _ilo(ile), projekt,
                       _ilo(teraz), monter),
                    "#e8f8e8" if kierunek > 0 else UWAGA_TLO)
        try:
            self.bell()
        except tk.TclError:
            pass
        klucz = "%s|%s" % (projekt, p["symbol"])
        if self.tab.exists(klucz):
            self.tab.selection_set(klucz)
            self.tab.see(klucz)
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

    def _zwrot_po_rw(self, poz, ile, projekt, monter, powod):
        """Monter oddaje coś, czego nie ma już w schowku — PW zwrotu.

        Dwa różne zwroty, dwie różne drogi:

          PRZED wystawieniem RW → „Zdejmij ze schowka" znosi pobranie
            i pozycja nie trafia na dokument w ogóle (`SCH.oddano`).

          PO wystawieniu RW → towar JEST JUŻ ZDJĘTY ZE STANU w Subiekcie.
            Bufora nie ma czego korygować; trzeba przyjąć towar z powrotem
            osobnym dokumentem PW. Tego nie da się zrobić „po cichu" —
            to ruch magazynowy w drugą stronę.

        Wcześniej taki zwrot kończył się samym komunikatem „w schowku jest
        0 szt.", bez podpowiedzi co dalej (14.09.2026).
        """
        s = self._schowek()
        w_schowku = 0
        if s:
            try:
                w_schowku = SCH.ile_w_schowku(s["id"], poz["symbol"], projekt)
            except Exception:
                pass

        if w_schowku > 0:
            # Częściowe pokrycie: część można znieść w buforze, resztę PW.
            tresc = ("W schowku jest tylko %s szt. „%s” na projekcie %s, "
                     "a monter oddaje %s.\n\n"
                     "Zdejmij najpierw tyle, ile jest w schowku, a resztę "
                     "przyjmij dokumentem PW." % (_ilo(w_schowku), poz["symbol"],
                                                  projekt, _ilo(ile)))
            return messagebox.showwarning("Zwrot częściowo poza schowkiem",
                                          tresc, parent=self)

        if not messagebox.askyesno(
                "Zwrot po wydaniu",
                "„%s” nie ma już w schowku na projekcie %s — najpewniej "
                "poszło na RW.\n\n"
                "Towar jest ZDJĘTY ZE STANU w Subiekcie, więc zwrot wymaga "
                "przyjęcia go z powrotem osobnym dokumentem.\n\n"
                "Wystawić PW zwrotu na %s szt.?"
                % (poz["symbol"], projekt, _ilo(ile)),
                icon="question", parent=self):
            return

        try:
            numer = self._wystaw_pw_zwrotu(poz, ile, projekt, monter)
        except Exception as e:
            return messagebox.showerror(
                "PW zwrotu nie powstało",
                "%s\n\nTowar NIE został przyjęty na magazyn." % e, parent=self)

        messagebox.showinfo(
            "Zwrot przyjęty",
            "Wystawiono %s\n\n%s — %s szt., projekt %s\n\n"
            "Towar wrócił na stan magazynu."
            % (numer, poz["symbol"], _ilo(ile), projekt), parent=self)
        self._odswiez()

    def _wystaw_pw_zwrotu(self, poz, ile, projekt, monter):
        """PW przyjmujące towar z powrotem. Zwraca numer albo rzuca.

        BEZ CENY — most wtedy bierze cenę z kartoteki (Pw.cs: „cena jest
        OPCJONALNA"). Zgadywanie ceny przyjęcia przy zwrocie rozjechałoby
        wartość magazynu; kartoteka wie lepiej.
        """
        from subiekt_produkcja import wyslij_pw
        from subiekt_zamowienia import zloz_uwagi, tytul_dokumentu

        opis = ["ZWROT z RW"]
        if monter:
            opis.append("ODDAŁ: %s" % monter)
        wydal = (self.var_wydal.get() or "").strip()
        if wydal:
            opis.append("PRZYJĄŁ: %s" % wydal)

        plan = {
            "pozycje": [{"symbol": poz["symbol"], "ilosc": float(ile)}],
            "uwagi": zloz_uwagi(projekt, "   ".join(opis)),
            "tytul": tytul_dokumentu(),
            "magazyn": self.var_magazyn.get() or MAGAZYN,
        }

        sucho = wyslij_pw(plan, zapisz=False, timeout=300)
        zle = [k for k in (sucho or {}).get("kroki", [])
               if k.get("Status") == "blad"]
        if zle:
            raise RuntimeError("; ".join(
                (k.get("Szczegoly") or k.get("Status")) for k in zle[:5]))

        wynik = wyslij_pw(plan, zapisz=True, timeout=600)
        numer = (wynik or {}).get("numer") or ""
        if not (wynik or {}).get("zapisano") or not numer:
            raise RuntimeError("Most nie potwierdził numeru dokumentu.")
        return numer

    def _ponad_stan(self, poz, chciane, wolne, w_schowku):
        """Nie ma tyle na magazynie — mowimy DLACZEGO, nie tylko ze nie.

        Magazynier musi wiedziec, czy zabraklo na polce, czy sam wczesniej
        wzial ten detal na inny projekt — to dwie rozne sytuacje i dwie
        rozne reakcje.
        """
        stan = self._stan_symbolu(poz["symbol"])
        czesci = ["Na magazynie: %s szt." % _ilo(stan or 0)]
        if w_schowku:
            czesci.append("W schowku juz masz: %s szt. (wszystkie projekty)"
                          % _ilo(w_schowku))
        czesci.append("Zostaje do pobrania: %s szt." % _ilo(max(wolne, 0)))
        self._uwaga("⛔ %s — chcesz %s szt.\n%s"
                    % (poz["symbol"], _ilo(chciane), "   ·   ".join(czesci)),
                    BLAD_TLO)
        try:
            self.bell()
        except tk.TclError:
            pass

    def _zaznaczony_wiersz(self):
        """(projekt, symbol) zaznaczonego wiersza albo (None, None).

        iid ma postać „projekt|symbol", bo ten sam detal bywa w schowku na
        dwóch projektach naraz i jako dwa osobne wiersze.
        """
        wyb = self.tab.selection()
        if not wyb:
            return None, None
        iid = wyb[0]
        if "|" in iid:
            projekt, symbol = iid.split("|", 1)
            return projekt or None, symbol
        return None, iid

    def _historia(self):
        """Wszystkie ruchy schowka — kto, kiedy, ile, na jaki projekt.

        Zwroty (ruchy ujemne) na żółto: to jedyne miejsce, gdzie widać, że
        detal był brany i oddany, bo w bilansie znosi się do zera.
        """
        s = self._schowek()
        if not s:
            return self._uwaga("Schowek jest pusty — nie ma historii.", None)
        okno = tk.Toplevel(self)
        okno.title("Historia ruchów — schowek #%s" % s["id"])
        okno.geometry("860x460")
        okno.transient(self)
        tk.Label(okno, text="Każdy skan, od najnowszego. "
                            "Ruchy ujemne to zwroty od montera.",
                 bg="#2980b9", fg="white", font=("Arial", 10, "bold"),
                 anchor="w", padx=12, pady=6).pack(fill=tk.X)
        kol = [("czas", "Czas", 130), ("projekt", "Projekt", 70),
               ("symbol", "Symbol", 130), ("nazwa", "Nazwa", 190),
               ("ilosc", "Ruch", 60), ("monter", "Pobrał/oddał", 110),
               ("operator", "Wydał", 90)]
        tab = ttk.Treeview(okno, columns=[k[0] for k in kol], show="headings")
        for k, n, w in kol:
            tab.heading(k, text=n)
            tab.column(k, width=w, anchor="e" if k == "ilosc" else "w")
        tab.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        tab.tag_configure("oddane", background=UWAGA_TLO)
        try:
            for r in SCH.historia(s["id"]):
                tab.insert("", tk.END,
                           tags=("oddane",) if r["ilosc"] < 0 else (),
                           values=(r["czas"], r.get("projekt", ""),
                                   r["symbol"], r.get("nazwa", ""),
                                   ("+" if r["ilosc"] > 0 else "")
                                   + _ilo(r["ilosc"]),
                                   r.get("monter", ""), r.get("operator", "")))
        except SCH.BladSchowka as e:
            messagebox.showerror("Historia", str(e), parent=okno)
        wysrodkuj(okno, self)

    def _popraw_ilosc(self):
        """Wpisanie NOWEJ ilości wprost — zamiast liczenia, ile zdjąć.

        Magazynier pomylił się przy wpisywaniu i chce po prostu poprawić
        liczbę (14.09.2026: „chcę móc edytować w schowku ilość W SCHOWKU").

        Pod spodem powstaje RUCH KORYGUJĄCY na różnicę, nie kasowanie
        historii — inaczej zniknąłby ślad, kto ile faktycznie wziął.
        """
        s = self._schowek()
        projekt, symbol = self._zaznaczony_wiersz()
        if not s or not symbol:
            return self._uwaga("Zaznacz wiersz, w którym chcesz poprawić "
                               "ilość.", None)
        teraz = 0.0
        for p in self.zawartosc:
            if p["symbol"] == symbol and (p.get("projekt") or "") == (projekt or ""):
                teraz = p["ilosc"]
                break

        okno = tk.Toplevel(self)
        okno.title("Popraw ilości przyciskiem „Popraw ilość” albo usuń te pozycje "
                "ze schowka, a potem wystaw ponownie.\n\n"
                "Nie powstał ŻADEN dokument — pozostałe projekty też czekają."
                % (lista, wiecej), parent=self)

        opis = "\n".join(
            "   %s: %d poz. / %s szt."
            % (pr, len(poz), _ilo(sum(x["ilosc"] for x in poz)))
            for pr, poz in sorted(grupy.items()))
        if not messagebox.askyesno(
                "Wydanie z magazynu",
                "Powstanie %d dokument(ow) RW:\n\n%s\n\nWystawiamy?"
                % (len(grupy), opis), parent=self):
            return

        self.btn_zakoncz.config(state=tk.DISABLED, text="Zapisuję…")
        self.update_idletasks()
        udane, bledy = [], []
        for projekt, pozycje in sorted(grupy.items()):
            try:
                numer = self._wystaw_rw(projekt, pozycje)
                udane.append((projekt, numer, len(pozycje)))
            except Exception as e:
                bledy.append((projekt, str(e)))
                break          # nie brniemy dalej — reszta zostaje w schowku
        self._po_wystawieniu(s, udane, bledy)

    def _usun_z_sesji(self):
        """Kasuje pozycję razem z historią — cofnięcie POMYŁKI skanowania.

        To nie jest zwrot: zwrot zostawia ślad (przycisk „Zdejmij"), a to
        czyści tak, jakby skanu nigdy nie było.
        """
        s = self._schowek()
        projekt, symbol = self._zaznaczony_wiersz()
        if not s or not symbol:
            return self._uwaga("Zaznacz wiersz, który chcesz usunąć.", None)
        if not messagebox.askyesno(
                "Usuń pozycję",
                "Usunąć „%s” (projekt %s) razem z całą historią ruchów?\n\n"
                "To jest cofnięcie POMYŁKI skanowania — nie zostanie żaden "
                "ślad.\n"
                "Jeśli monter fizycznie oddaje element, użyj „Zdejmij”."
                % (symbol, projekt or "—"), parent=self):
            return
        try:
            SCH.usun_pozycje(s["id"], symbol, projekt=projekt)
        except SCH.BladSchowka as e:
            return self._uwaga("⛔ %s" % e, BLAD_TLO)
        self._odswiez_zawartosc()

    def _wyczysc_sesje(self):
        """Kasuje CAŁY schowek — wszystkie projekty naraz."""
        s = self._schowek()
        if not s or not self.zawartosc:
            return
        if not messagebox.askyesno(
                "Wyczyść schowek",
                "Usunąć WSZYSTKIE %d pozycji ze schowka?\n\n"
                "Historia przepadnie — to nie jest zwrot towaru."
                % len(self.zawartosc), parent=self):
            return
        try:
            SCH.wyczysc(s["id"])
        except SCH.BladSchowka as e:
            return self._uwaga("⛔ %s" % e, BLAD_TLO)
        self._odswiez_zawartosc()

    def _pozycje_sesji(self):
        """Wszystko, co w schowku — do podglądu i liczników."""
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

    def _uwagi_rw(self, projekt, pozycje):
        """Uwagi JEDNEGO dokumentu: numer projektu w 1. wierszu, ludzie niżej.

        Monterów bierzemy z POZYCJI TEGO PROJEKTU — na dokument trafiają
        tylko ci, którzy faktycznie coś z niego wzięli. Uwagi się drukują,
        więc ma być widać, komu towar poszedł.
        """
        from subiekt_zamowienia import zloz_uwagi
        czesci = []
        wydal = (self.var_wydal.get() or "").strip()
        if wydal:
            czesci.append("WYDAŁ: %s" % wydal)
        ludzie = []
        for p in pozycje:
            for n in (p.get("monterzy") or "").split(","):
                n = n.strip()
                if n and n not in ludzie:
                    ludzie.append(n)
        if ludzie:
            czesci.append("POBRAŁ: %s" % ", ".join(ludzie))
        return zloz_uwagi(projekt, "   ".join(czesci) if czesci else None)

    def _podglad_rw(self):
        """Co powstanie w Subiekcie — OSOBNA SEKCJA NA KAŻDY PROJEKT.

        Nie dziedziczymy wersji z okna wydań: tamta woła `_uwagi_rw()` bez
        argumentów i pokazuje jeden dokument, a tu powstaje ich tyle, ile
        projektów.
        """
        if not self.zawartosc:
            return
        grupy = {}
        for p in self.zawartosc:
            grupy.setdefault(p.get("projekt") or "(brak projektu)", []).append(p)

        okno = tk.Toplevel(self)
        okno.title("Podgląd — co powstanie w Subiekcie")
        okno.geometry("900x600")
        okno.transient(self)
        tk.Label(okno, text="POWSTANIE %d DOKUMENT(ÓW) RW" % len(grupy),
                 bg="#2980b9", fg="white", font=("Arial", 11, "bold"),
                 anchor="w", padx=12, pady=8).pack(fill=tk.X)

        stopka = tk.Frame(okno, padx=12, pady=10)
        stopka.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Button(stopka, text="Zamknij", command=okno.destroy,
                  width=12).pack(side=tk.RIGHT)

        plotno = tk.Frame(okno)
        plotno.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 0))
        for projekt, poz in sorted(grupy.items()):
            szt = sum(x["ilosc"] for x in poz)
            tk.Label(plotno, text="RW — projekt %s   (%d poz. / %s szt.)"
                     % (projekt, len(poz), _ilo(szt)), anchor="w",
                     font=("Arial", 10, "bold"), bg="#eef3f7",
                     padx=8, pady=4).pack(fill=tk.X, pady=(8, 0))
            tk.Label(plotno, text="Uwagi: " + self._uwagi_rw(
                         projekt, poz).replace(chr(10), "  ⏎  "),
                     font=("Arial", 8), fg="gray30", anchor="w",
                     padx=8).pack(fill=tk.X)
            tab = ttk.Treeview(plotno, columns=("symbol", "nazwa", "ilosc",
                                                "stan", "pobral"),
                               show="headings", height=min(len(poz), 6))
            for k, n, w in (("symbol", "Symbol", 150), ("nazwa", "Nazwa", 250),
                            ("ilosc", "Ilość", 70), ("stan", "Stan", 60),
                            ("pobral", "Pobrał", 130)):
                tab.heading(k, text=n)
                tab.column(k, width=w,
                           anchor="e" if k in ("ilosc", "stan") else "w")
            tab.tag_configure("brak", background=BLAD_TLO)
            for x in poz:
                stan = self._stan_symbolu(x["symbol"])
                # Czerwony wiersz od razu mówi, czego Subiekt nie wyda.
                zle = stan is not None and x["ilosc"] > stan
                tab.insert("", tk.END, tags=("brak",) if zle else (),
                           values=(x["symbol"], x.get("nazwa", ""),
                                   _ilo(x["ilosc"]),
                                   _ilo(stan) if stan is not None else "—",
                                   x.get("monterzy") or "—"))
            tab.pack(fill=tk.X, padx=8)
        wysrodkuj(okno, self)

    # ── rozliczenie: JEDNO RW NA PROJEKT ─────────────────────────────────
    def _zakoncz(self):
        """Tyle dokumentów, ile projektów w schowku.

        NIE dziedziczymy `_zakoncz` z okna wydań: tamto zna jeden projekt
        i wystawia jeden dokument. Schowek zbiera pozycje z wielu projektów
        naraz, a każdy RW musi mieć SWÓJ numer w Uwagach — po nim Subiekt
        liczy wydania per projekt (WydanieStan.cs).
        """
        if not self.polaczony:
            return self._uwaga("⛔ Brak połączenia z Subiektem — "
                               "kliknij „Odśwież”.", BLAD_TLO)
        s = self._schowek()
        if not s or not self.zawartosc:
            return
        grupy = {}
        for poz in self.zawartosc:
            grupy.setdefault(poz.get("projekt") or "", []).append(poz)
        if "" in grupy:
            return messagebox.showerror(
                "Pozycje bez projektu",
                "W schowku są pozycje bez przypisanego projektu.\n\n"
                "Usuń je albo zeskanuj ponownie z wybranym projektem — "
                "RW musi mieć numer projektu w Uwagach.", parent=self)

        # ⛔ TWARDA BLOKADA — BRAKI ZATRZYMUJĄ CAŁE WYDANIE.
        #
        # Decyzja użytkownika (14.09.2026): „wszystkie ilości mają się
        # zgadzać z magazynem, dopiero można puścić RW do realizacji.
        # Bez wyjątków".
        #
        # Sprawdzone na demo: Subiekt i tak ODRZUCA RW ponad stan
        # (zapisano=False, bez numeru), a suchy przebieg tego NIE wykrywa —
        # zgłasza tylko brak ceny. Bez tej kontroli magazynier dowiadywałby
        # się na końcu, z komunikatu, który nie mówi czego brakuje.
        #
        # Blokujemy CAŁE wydanie, nie tylko projekt z brakiem: dokumenty
        # powstają w pętli, a przerwanie w środku zostawiłoby część
        # projektów rozliczonych, a część nie.
        braki = self._sprawdz_stany(grupy)
        if braki:
            lista = "\n".join(
                "   %-20s potrzeba %s,  na stanie %s   →  BRAKUJE %s"
                % (sym, _ilo(chc), _ilo(ma), _ilo(chc - ma))
                for sym, chc, ma in braki[:15])
            wiecej = ("\n   … i %d dalszych" % (len(braki) - 15)
                      if len(braki) > 15 else "")
            return messagebox.showerror(
                "Nie można wydać — brakuje na magazynie",
                "WYDANIE WSTRZYMANE. Subiekt nie wyda towaru, którego nie ma "
                "na stanie.\n\n%s%s\n\n"
                "Popraw ilości przyciskiem „Popraw ilość” albo usuń te "
                "pozycje ze schowka, a potem wystaw ponownie.\n\n"
                "Nie powstał ŻADEN dokument — pozostałe projekty też czekają."
                % (lista, wiecej), parent=self)

        opis = "\n".join(
            "   %s: %d poz. / %s szt."
            % (pr, len(poz), _ilo(sum(x["ilosc"] for x in poz)))
            for pr, poz in sorted(grupy.items()))
        if not messagebox.askyesno(
                "Wydanie z magazynu",
                "Powstanie %d dokument(ów) RW:\n\n%s\n\nWystawiamy?"
                % (len(grupy), opis), parent=self):
            return

        self.btn_zakoncz.config(state=tk.DISABLED, text="Zapisuję…")
        self.update_idletasks()
        udane, bledy = [], []
        for projekt, pozycje in sorted(grupy.items()):
            try:
                numer = self._wystaw_rw(projekt, pozycje)
                udane.append((projekt, numer, len(pozycje)))
            except Exception as e:
                bledy.append((projekt, str(e)))
                break          # nie brniemy dalej — reszta zostaje w schowku
        self._po_wystawieniu(s, udane, bledy)

    def _sprawdz_stany(self, grupy):
        """[(symbol, chciane, na_stanie)] dla pozycji bez pokrycia.

        Pyta Subiekta o stany WSZYSTKICH symboli jednym zapytaniem i sumuje
        zapotrzebowanie po projektach: ten sam detal wydawany na trzy
        projekty schodzi z półki raz, więc porównujemy SUMĘ, nie każdy
        projekt osobno.

        Cisza przy błędzie jest celowa — brak odpowiedzi mostu nie może
        zablokować wydania, bo suchy przebieg i tak to złapie.
        """
        chciane = {}
        for pozycje in grupy.values():
            for p in pozycje:
                k = p["symbol"].strip().upper()
                chciane[k] = chciane.get(k, 0.0) + float(p["ilosc"])
        if not chciane:
            return []
        try:
            import subiekt_stany
            kartoteki = subiekt_stany.query_stock(
                sorted({p["symbol"] for g in grupy.values() for p in g}),
                timeout=180) or {}
        except Exception as e:
            print("Nie sprawdzono stanow przed RW: %s" % e)
            return []

        po_kluczu = {(k or "").strip().upper(): v for k, v in kartoteki.items()}
        braki = []
        for symbol, ile in sorted(chciane.items()):
            k = po_kluczu.get(symbol)
            if not k:
                continue                  # kartoteki nie ma — powie suchy przebieg
            stan = self._stan_w_magazynie(k)
            if ile > stan:
                braki.append((symbol, ile, stan))
        return braki

    def _wystaw_rw(self, projekt, pozycje):
        """Jeden dokument dla jednego projektu. Zwraca numer albo rzuca.

        Kolejność jak w SCHOWEK_RW_ALGORYTM.md §4.3: najpierw BOM (żeby
        wydanie miało się do czego przypiąć), potem suchy przebieg, dopiero
        na końcu zapis.
        """
        import rm_klient
        from subiekt_magazyn_gui import utworz_rw
        from subiekt_zamowienia import tytul_dokumentu

        pid = self._id_projektu(projekt)
        if pid:
            BOM.przygotuj(self._con_projektu(), rm_klient, pid, pozycje,
                          self._czy_lock(),
                          kto=(self.var_wydal.get() or "").strip())

        do_rw = [{"symbol": p["symbol"], "ilosc": p["ilosc"]} for p in pozycje]
        uwagi = self._uwagi_rw(projekt, pozycje)
        magazyn = self.var_magazyn.get() or MAGAZYN

        sucho = utworz_rw(do_rw, uwagi, magazyn=magazyn, zapisz=False,
                          timeout=300, tytul=tytul_dokumentu())
        zle = [k for k in (sucho or {}).get("kroki", [])
               if k.get("Status") == "blad"]
        if zle:
            raise RuntimeError("; ".join(
                (k.get("Szczegoly") or k.get("Status")) for k in zle[:5]))

        wynik = utworz_rw(do_rw, uwagi, magazyn=magazyn, zapisz=True,
                          timeout=600, tytul=tytul_dokumentu())
        numer = (wynik or {}).get("numer") or ""
        if not (wynik or {}).get("zapisano") or not numer:
            raise RuntimeError("Most nie potwierdził numeru dokumentu.")
        if pid:
            self._dopisz_wydane(pid, projekt)
        return numer

    def _id_projektu(self, numer):
        """project_id dla numeru projektu — potrzebny do zapisu w BOM-ie."""
        try:
            db = getattr(self._arkusz, "db_manager", None)
            if db is None:
                return None
            for w in db.master_read("projekty-do-selektora"):
                if (w.get("project_type") or "MACHINE") != "MACHINE":
                    continue        # WAREHOUSE — nie nasz tor
                if SCH.sam_numer(w["name"]) == SCH.sam_numer(numer):
                    return w["project_id"]
        except Exception as e:
            print("Nie ustalono project_id dla %s: %s" % (numer, e))
        return None

    def _dopisz_wydane(self, pid, projekt):
        """Ilość dostarczonych z Subiekta — po udanym RW tego projektu."""
        con = self._con_projektu()
        if con is None or not self._czy_lock():
            return
        try:
            import subiekt_wydane_do_arkusza as WYD
            WYD.odswiez(con, pid, projekt)
        except Exception as e:
            print("Nie dopisano wydan dla %s: %s" % (projekt, e))

    def _po_wystawieniu(self, s, udane, bledy):
        self.btn_zakoncz.config(state=tk.NORMAL,
                                text="Wydaj / Utwórz RW\nw Subiekcie")
        if udane:
            # Ze schowka znikają TYLKO rozliczone projekty — reszta zostaje,
            # żeby dało się poprawić przyczynę i dokończyć.
            for projekt, _numer, _ile in udane:
                try:
                    SCH.usun_projekt(s["id"], projekt)
                except Exception as e:
                    print("Nie wyczyszczono %s: %s" % (projekt, e))
        if bledy:
            projekt, tresc = bledy[0]
            czolo = ("Wystawiono: " + ", ".join(n for _p, n, _i in udane)
                     if udane else "Nie wystawiono żadnego dokumentu.")
            messagebox.showerror(
                "Wydanie przerwane",
                "%s\n\nProjekt %s: %s\n\nPozycje tego i kolejnych projektów "
                "ZOSTAJĄ w schowku — popraw przyczynę i wystaw ponownie."
                % (czolo, projekt, tresc), parent=self)
        elif udane:
            messagebox.showinfo(
                "Wydanie zapisane",
                "Wystawiono %d dokument(ow):\n\n%s"
                % (len(udane), "\n".join(
                    "   %s — projekt %s, %d poz." % (n, p, i)
                    for p, n, i in udane)), parent=self)
        self._odswiez_zawartosc()
        self._odswiez()


def open_window(parent, project_id, project_name=None,
                con_projektu=None, mamy_lock=False):
    """Punkt wejścia dla RM_BAZA."""
    # BEZ WYMOGU PROJEKTU — schowek nie należy do projektu. Gdy w arkuszu
    # nic nie wybrano, okno startuje z pustym polem „Projekt pozycji"
    # i magazynier wybiera go z listy przed pierwszym skanem.
    return SchowekWindow(parent, project_id, project_name,
                         con_projektu=con_projektu, mamy_lock=mamy_lock)
