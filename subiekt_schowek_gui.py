# -*- coding: utf-8 -*-
"""Okno „Schowek wydań" — bufor montażowy, obok okna „Wydaj".

Zbudowane NA oknie wydania (`WydanieWindow`), nie obok niego: skaner,
miniatury rysunku, alarm awarii mostu i obsługa kartotek są tam już
dopracowane i przetestowane. Dziedziczymy je i nadpisujemy wyłącznie to,
co w schowku działa inaczej.

CZYM SIĘ RÓŻNI OD OKNA WYDAŃ
────────────────────────────
* Prawa tabela pokazuje ZAWARTOŚĆ SCHOWKA (bilans ruchów), nie „co zostało
  do wydania w projekcie".
* Dwa kierunki skanowania: „Dodaj do schowka" (+N) i „Zdejmij ze schowka"
  (−N, zwrot od montera). Zwrot tego samego dnia znosi pobranie i NIE
  zostawia śladu na RW — to jest sedno całego pomysłu.
* Lewa kolumna: lista schowków — jeden projekt może mieć kilka naraz, po
  jednym na montera przy różnej maszynie.
* Pole MONTER na każdym schowku: komu wydajemy i kto zwraca.
* Przy rozliczeniu pozycje spoza BOM-u dopisują się do arkusza
  (SCHOWEK_RW_ALGORYTM.md) — okno wydań tego nie robi.

Specyfikacje: BUFOR_SCHOWEK_MONTAZOWY.md, SCHOWEK_RW_ALGORYTM.md
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

import subiekt_schowek as SCH
import subiekt_schowek_bom as BOM
from subiekt_wydanie_gui import (
    WydanieWindow, MAGAZYN, TLO, TLO_SEKCJI, TEKST, TEKST_SZARY, OK_ZIELONY,
    BLAD_TLO, UWAGA_TLO, wysrodkuj, _ilo, _liczba,
)


#: Kolumny tabeli schowka. „Potrzeba / Wydano / Pozostało" tylko przy
#: schowku PROJEKTOWYM — przy ogólnym nie ma ZK ani PW, więc nie ma z czym
#: porównywać i puste kolumny tylko myliłyby magazyniera.
KOL_PROJEKT = [("lp", "Lp.", 32), ("symbol", "Symbol", 116),
               ("nazwa", "Nazwa", 170), ("potrzeba", "Potrzeba", 56),
               ("wydano", "Wydano", 52), ("schowek", "W schowku", 66),
               ("pozostalo", "Pozost.", 54), ("stan", "Stan", 46),
               ("monter", "Monter", 92)]

KOL_OGOLNY = [("lp", "Lp.", 32), ("symbol", "Symbol", 130),
              ("nazwa", "Nazwa", 250), ("schowek", "W schowku", 70),
              ("stan", "Stan", 56), ("monter", "Monter", 110)]


class SchowekWindow(WydanieWindow):
    """Schowek wydań — skan do bufora, rozliczenie jednym RW."""

    def __init__(self, parent, project_id, project_name=None,
                 con_projektu=None, mamy_lock=False):
        #: Połączenie arkusza do bazy projektu (db_manager.project_con) —
        #: potrzebne, żeby dopisać pozycję spoza BOM-u. Bez locka jest
        #: READ-ONLY i wtedy wiersz idzie do poczekalni w master.
        self.con_projektu = con_projektu
        self.mamy_lock = bool(mamy_lock)
        self.schowek_id = None
        self.schowki = []
        #: Zawartość wybranego schowka: [{symbol, nazwa, ilosc}]
        self.zawartosc = []
        super().__init__(parent, project_id, project_name)
        self.title("Schowek wydań — %s" % self.project_name)

    # ── budowa: różnice względem okna wydań ──────────────────────────────
    def _panel_sesji(self, rodzic):
        srodek = tk.Frame(rodzic, bg=TLO)
        srodek.pack(fill=tk.BOTH, expand=True)
        self._panel_listy(srodek)

        ram = tk.Frame(srodek, bg=TLO_SEKCJI, bd=1, relief=tk.SOLID)
        ram.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        naglowek = tk.Frame(ram, bg=TLO_SEKCJI)
        naglowek.pack(fill=tk.X, padx=10, pady=(8, 0))
        tk.Label(naglowek, text="🧺  Zawartość schowka", bg=TLO_SEKCJI,
                 fg=TEKST, font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        self.var_licznik = tk.StringVar(value="0 pozycji")
        tk.Label(naglowek, textvariable=self.var_licznik, bg=TLO_SEKCJI,
                 fg=TEKST_SZARY, font=("Arial", 9)).pack(side=tk.RIGHT)

        self.var_podtytul = tk.StringVar(
            value="Wybierz schowek z listy albo załóż nowy")
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
            stopka, text="Rozlicz schowek\nUtwórz RW w Subiekcie",
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
        self.tab = ttk.Treeview(wrap, show="headings", selectmode="browse")
        sc = ttk.Scrollbar(wrap, orient="vertical", command=self.tab.yview)
        sc_x = ttk.Scrollbar(wrap, orient="horizontal", command=self.tab.xview)
        self.tab.configure(yscrollcommand=sc.set, xscrollcommand=sc_x.set)
        sc_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tab.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        self.tab.tag_configure("brak_stanu", background=BLAD_TLO)
        self.tab.tag_configure("poza_bom", background="#f4ecf7")
        self.tab.bind("<Delete>", lambda _e: self._usun_z_sesji())
        self._ustaw_kolumny()

    def _panel_listy(self, rodzic):
        ram = tk.Frame(rodzic, bg=TLO_SEKCJI, bd=1, relief=tk.SOLID, width=232)
        ram.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        ram.pack_propagate(False)

        gora = tk.Frame(ram, bg=TLO_SEKCJI)
        gora.pack(fill=tk.X, padx=8, pady=(8, 4))
        tk.Label(gora, text="Schowki", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 11, "bold")).pack(side=tk.LEFT)
        tk.Button(gora, text="+ Nowy", command=self._nowy_schowek,
                  font=("Arial", 8), bg="#2980b9", fg="white").pack(side=tk.RIGHT)

        self.var_tylko_otwarte = tk.BooleanVar(value=True)
        tk.Checkbutton(ram, text="tylko otwarte", variable=self.var_tylko_otwarte,
                       bg=TLO_SEKCJI, activebackground=TLO_SEKCJI,
                       font=("Arial", 8), command=self._odswiez_liste).pack(
            anchor="w", padx=8)

        wrap = tk.Frame(ram, bg=TLO_SEKCJI)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))
        self.lista = tk.Listbox(wrap, font=("Arial", 9), activestyle="none",
                                exportselection=False)
        sc = ttk.Scrollbar(wrap, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=sc.set)
        self.lista.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        self.lista.bind("<<ListboxSelect>>", lambda _e: self._wybrano())

    def _ustaw_kolumny(self):
        """Kolumny zależą od rodzaju schowka — ogólny nie ma czego porównywać."""
        s = self._schowek()
        self._kolumny = KOL_PROJEKT if (s and s.get("projekt")) else KOL_OGOLNY
        self.tab.configure(columns=[k[0] for k in self._kolumny])
        for klucz, naglowek, szer in self._kolumny:
            self.tab.heading(klucz, text=naglowek)
            self.tab.column(klucz, width=szer, minwidth=32,
                            stretch=(klucz == "nazwa"),
                            anchor="w" if klucz in ("symbol", "nazwa", "monter")
                            else "e")

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

    # ── dane ─────────────────────────────────────────────────────────────
    def _schowek(self):
        for s in self.schowki:
            if s["id"] == self.schowek_id:
                return s
        return None

    def _odswiez_liste(self):
        try:
            self.schowki = SCH.lista(tylko_otwarte=self.var_tylko_otwarte.get(),
                                     projekt=self.project_name)
        except SCH.BladSchowka as e:
            self.schowki = []
            return self._uwaga("⛔ %s" % e, BLAD_TLO)
        self.lista.delete(0, tk.END)
        for s in self.schowki:
            znak = "●" if s["status"] == SCH.OTWARTY else "✓"
            self.lista.insert(tk.END, "%s %s  (%d poz. / %s szt.)"
                              % (znak, SCH.opis(s), s["pozycji"], _ilo(s["sztuk"])))
            if s["id"] == self.schowek_id:
                self.lista.selection_set(tk.END)

    def _wybrano(self):
        wyb = self.lista.curselection()
        if not wyb or wyb[0] >= len(self.schowki):
            return
        self.schowek_id = self.schowki[wyb[0]]["id"]
        self._ustaw_kolumny()
        self._odswiez_zawartosc()

    def _odswiez_zawartosc(self):
        s = self._schowek()
        if not s:
            self.zawartosc = []
            self.var_podtytul.set("Wybierz schowek z listy albo załóż nowy")
            return self._przerysuj()
        try:
            self.zawartosc = SCH.stan_schowka(s["id"])
        except SCH.BladSchowka as e:
            self.zawartosc = []
            self._uwaga("⛔ %s" % e, BLAD_TLO)
        rozliczony = s["status"] != SCH.OTWARTY
        self.var_podtytul.set(
            "Monter: %s   ·   %s   ·   %s"
            % (s["monter"],
               ("projekt %s" % s["projekt"]) if s["projekt"] else "schowek ogólny",
               ("ROZLICZONY — RW %s" % (s["rw_numer"] or "?")) if rozliczony
               else "otwarty od %s" % s["data"]))
        # Rozliczonego schowka nie wolno ruszać — RW już jest w Subiekcie.
        for w in (self.btn_dodaj, self.btn_zdejmij):
            w.config(state=tk.DISABLED if rozliczony else tk.NORMAL)
        self._przerysuj()

    def _przerysuj(self):
        self.tab.delete(*self.tab.get_children())
        klucze = [k[0] for k in getattr(self, "_kolumny", KOL_OGOLNY)]
        monter = (self._schowek() or {}).get("monter", "")
        for i, p in enumerate(self.zawartosc, 1):
            wpis = self.stan.get(p["symbol"].upper()) or {}
            stan_mag = self._stan_symbolu(p["symbol"])
            potrzeba = wpis.get("potrzeba")
            wart = {
                "lp": i, "symbol": p["symbol"], "nazwa": p["nazwa"],
                "schowek": _ilo(p["ilosc"]),
                "stan": _ilo(stan_mag) if stan_mag is not None else "—",
                "monter": monter,
                "potrzeba": _ilo(potrzeba) if potrzeba is not None else "—",
                "wydano": _ilo(wpis.get("wydano", 0)) if wpis else "—",
                "pozostalo": (_ilo(max(0.0, float(potrzeba) - float(wpis.get("wydano", 0))))
                              if potrzeba is not None else "—"),
            }
            # Czerwone TYLKO gdy stan jest ZNANY i faktycznie za mały.
            # `plan` powstaje z odpowiedzi `wydanie-stan`, więc pozycji spoza
            # BOM-u w ogóle w nim nie ma — brak wpisu znaczy „nie wiem", a nie
            # „zero". Malowanie takiej pozycji na czerwono byłoby fałszywym
            # alarmem przy każdym detalu dołożonym z magazynu.
            tagi = ()
            if stan_mag is not None and p["ilosc"] > stan_mag:
                tagi = ("brak_stanu",)
            elif not wpis:
                tagi = ("poza_bom",)      # nie ma jej w ZK ani PW projektu
            self.tab.insert("", tk.END, iid=p["symbol"],
                            values=[wart.get(k, "") for k in klucze], tags=tagi)
        szt = sum(p["ilosc"] for p in self.zawartosc)
        self.var_licznik.set("%d pozycji" % len(self.zawartosc))
        self.var_w_schowku.set("%d pozycji / %s szt."
                               % (len(self.zawartosc), _ilo(szt)))
        gotowy = bool(self.zawartosc) and (self._schowek() or {}).get(
            "status") == SCH.OTWARTY
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
                # 0 z pozycji bez nazwy = kartoteka nie dojechała, nie „zero".
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

    # ── akcje ────────────────────────────────────────────────────────────
    def _nowy_schowek(self):
        okno = tk.Toplevel(self)
        okno.title("Nowy schowek")
        okno.configure(bg=TLO_SEKCJI)
        okno.transient(self)
        okno.resizable(False, False)

        tk.Label(okno, text="Dla kogo zakładamy schowek?", bg=TLO_SEKCJI,
                 fg=TEKST, font=("Arial", 11, "bold")).pack(padx=20, pady=(16, 8))

        ramka = tk.Frame(okno, bg=TLO_SEKCJI)
        ramka.pack(padx=20, pady=(0, 8), fill=tk.X)
        tk.Label(ramka, text="Monter:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9)).grid(row=0, column=0, sticky="w", pady=4)
        var_monter = tk.StringVar()
        combo = ttk.Combobox(ramka, textvariable=var_monter, width=26,
                             values=list(self.combo_pobiera["values"] or ()))
        combo.grid(row=0, column=1, sticky="w", padx=(8, 0))

        var_ogolny = tk.BooleanVar(value=False)
        tk.Checkbutton(
            ramka, text="schowek ogólny (bez projektu — serwis, eksploatacja)",
            variable=var_ogolny, bg=TLO_SEKCJI, activebackground=TLO_SEKCJI,
            font=("Arial", 8)).grid(row=1, column=0, columnspan=2,
                                    sticky="w", pady=(6, 0))

        tk.Label(ramka, text="Opis:", bg=TLO_SEKCJI, fg=TEKST_SZARY,
                 font=("Arial", 8)).grid(row=2, column=0, sticky="w", pady=4)
        var_nazwa = tk.StringVar()
        tk.Entry(ramka, textvariable=var_nazwa, width=28).grid(
            row=2, column=1, sticky="w", padx=(8, 0))

        def zaloz():
            monter = (var_monter.get() or "").strip()
            if not monter:
                return messagebox.showwarning("Nowy schowek", "Podaj montera.",
                                              parent=okno)
            try:
                nowy = SCH.utworz(
                    monter,
                    projekt=None if var_ogolny.get() else self.project_name,
                    nazwa=var_nazwa.get())
            except SCH.BladSchowka as e:
                return messagebox.showerror("Nowy schowek", str(e), parent=okno)
            okno.destroy()
            self.schowek_id = nowy
            self._odswiez_liste()
            self._ustaw_kolumny()
            self._odswiez_zawartosc()
            self.ent_kod.focus_set()

        przyciski = tk.Frame(okno, bg=TLO_SEKCJI)
        przyciski.pack(pady=(4, 16))
        tk.Button(przyciski, text="Załóż schowek", command=zaloz,
                  bg="#27ae60", fg="white", font=("Arial", 10, "bold"),
                  padx=16, pady=4).pack(side=tk.LEFT, padx=4)
        tk.Button(przyciski, text="Anuluj", command=okno.destroy,
                  font=("Arial", 9), padx=12).pack(side=tk.LEFT, padx=4)
        combo.focus_set()
        wysrodkuj(okno, self)
        okno.grab_set()

    def _wymagaj_schowka(self):
        s = self._schowek()
        if not s:
            self._uwaga("⛔ Najpierw wybierz schowek albo załóż nowy.", BLAD_TLO)
            return None
        if s["status"] != SCH.OTWARTY:
            self._uwaga("⛔ Schowek rozliczony (RW %s) — nie można go zmieniać."
                        % (s["rw_numer"] or "?"), BLAD_TLO)
            return None
        return s

    def _ruch(self, kierunek):
        """Wspólna obsługa obu przycisków — różni je tylko funkcja i etykieta."""
        if not self.polaczony:
            return self._uwaga("⛔ Brak połączenia z Subiektem — "
                               "kliknij „Odśwież”.", BLAD_TLO)
        s = self._wymagaj_schowka()
        if not s:
            return
        p = getattr(self, "poz_biezaca", None)
        if not p:
            return self._uwaga("⛔ Najpierw zeskanuj pozycję.", BLAD_TLO)
        ile = _liczba(self.var_ilosc.get(), 0.0)
        if ile <= 0:
            self._uwaga("⛔ Podaj ilość większą od zera.", BLAD_TLO)
            return self.spin_ilosc.focus_set()

        funkcja = SCH.pobrano if kierunek > 0 else SCH.oddano
        etykieta = "POBRANO" if kierunek > 0 else "ODDANO"
        try:
            teraz = funkcja(s["id"], p["symbol"], ile, nazwa=p.get("nazwa"),
                            operator=(self.var_wydal.get() or "").strip(),
                            monter=s["monter"])
        except SCH.BladSchowka as e:
            return self._uwaga("⛔ %s" % e, BLAD_TLO)

        self._odswiez_liste()
        self._odswiez_zawartosc()
        self.var_ostatni.set("%s %s szt. — %s" % (etykieta, _ilo(ile), p["symbol"]))
        self._uwaga("✓ %s: %s %s szt.   ·   w schowku: %s szt.   ·   %s"
                    % (etykieta, p["symbol"], _ilo(ile), _ilo(teraz), s["monter"]),
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
        s = self._wymagaj_schowka()
        if not s:
            return
        symbol = self._zaznaczony()
        if not symbol:
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
        self._odswiez_liste()
        self._odswiez_zawartosc()

    def _wyczysc_sesje(self):
        s = self._wymagaj_schowka()
        if not s:
            return
        if not messagebox.askyesno(
                "Wyczyść schowek",
                "Usunąć WSZYSTKIE ruchy ze schowka „%s”?\n\n"
                "Historia przepadnie — to nie jest zwrot towaru."
                % SCH.opis(s), parent=self):
            return
        try:
            SCH.wyczysc(s["id"])
        except SCH.BladSchowka as e:
            return self._uwaga("⛔ %s" % e, BLAD_TLO)
        self._odswiez_liste()
        self._odswiez_zawartosc()

    def _historia(self):
        s = self._schowek()
        if not s:
            return
        okno = tk.Toplevel(self)
        okno.title("Historia ruchów — %s" % SCH.opis(s))
        okno.geometry("780x460")
        okno.transient(self)
        tk.Label(okno, text="Każdy skan, od najnowszego. "
                            "Ruchy ujemne to zwroty od montera.",
                 bg="#2980b9", fg="white", font=("Arial", 10, "bold"),
                 anchor="w", padx=12, pady=6).pack(fill=tk.X)
        kol = [("czas", "Czas", 130), ("symbol", "Symbol", 130),
               ("nazwa", "Nazwa", 200), ("ilosc", "Ruch", 70),
               ("monter", "Monter", 110), ("operator", "Wydał", 100)]
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
        """Uwagi RW: numer projektu w 1. wierszu, ludzie i schowek niżej."""
        from subiekt_zamowienia import zloz_uwagi
        s = self._schowek() or {}
        czesci = []
        wydal = (self.var_wydal.get() or "").strip()
        if wydal:
            czesci.append("WYDAŁ: %s" % wydal)
        if s.get("monter"):
            czesci.append("POBRAŁ: %s" % s["monter"])
        czesci.append("SCHOWEK #%s" % s.get("id", "?"))
        return zloz_uwagi(s.get("projekt") or self.project_name,
                          "   ".join(czesci))

    def _zapisz_po_suchym(self, pozycje, kroki):
        """⛔ BRAMKA: BOM najpierw, RW dopiero po potwierdzeniu.

        Wydanie z Subiekta nie może pojawić się wcześniej niż wiersz, do
        którego ma się przypiąć (SCHOWEK_RW_ALGORYTM.md §4.3). Dlatego
        pozycje spoza BOM-u dopisujemy TU, przed zapisem — a gdy się nie
        uda, RW w ogóle nie powstaje.
        """
        s = self._schowek() or {}
        if s.get("projekt"):                  # schowek ogólny nie ma BOM-u
            try:
                dopisane, odlozone = BOM.przygotuj(
                    self.con_projektu, self._serwer(), self.project_id,
                    pozycje, self.mamy_lock,
                    kto=(self.var_wydal.get() or "").strip())
            except BOM.BladBom as e:
                return messagebox.showerror(
                    "RW nie zostało wystawione", str(e), parent=self)
            self._po_bom = (dopisane, odlozone)
        else:
            self._po_bom = (0, 0)
        super()._zapisz_po_suchym(pozycje, kroki)

    def _serwer(self):
        import rm_klient
        return rm_klient

    def _po_zapisie(self, wynik, bledy, sucho):
        super()._po_zapisie(wynik, bledy, sucho)
        if bledy or sucho or not (wynik or {}).get("numer"):
            return
        s = self._schowek()
        if not s:
            return
        try:
            SCH.oznacz_rozliczony(s["id"], wynik["numer"])
        except SCH.BladSchowka as e:
            messagebox.showwarning(
                "Schowek nie zamknięty",
                "RW %s powstało, ale nie udało się zamknąć schowka:\n%s\n\n"
                "Zamknij go ręcznie, żeby nie wydać tego drugi raz."
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
        self._odswiez_liste()
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
