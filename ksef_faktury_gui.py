# -*- coding: utf-8 -*-
"""Faktury z KSeF — okno decyzji per pozycja (panel SUBIEKT, kafel 🧾).

    import ksef_faktury_gui
    ksef_faktury_gui.open_window(arkusz, katalog_archiwum, ksef_cfg)

Czym się różni od archiwum w menu KSeF (`ksef_archiwum.OknoArchiwum`):
tamto pokazuje, CO przyszło. To okno odpowiada na pytanie „CZYM JEST każda
linia faktury" — towar z kartoteki dostawcy, usługa, pozycja zbiorcza czy
detal z naszego rysunku — i zapamiętuje odpowiedź. Klikasz wiersz, decydujesz
w panelu na dole, zapisujesz, przechodzisz do następnego braku.

Układ (na wzór makiety z 17.09.2026, ale nie 1:1):

    ┌ pasek narzędzi ────────────────────────────────────────────────────┐
    │ drzewo faktur │ nagłówek faktury: numer, dostawca, nabywca, WZ …    │
    │ (po dacie,    ├─────────────────────────────────────────────────────┤
    │  odznaki)     │ zakładki: Pozycje | Dodatkowe informacje | Plik XML │
    │               │   liczniki, tabela pozycji ze statusami             │
    │               ├─────────────────────────────────────────────────────┤
    │               │ DECYZJA dla wybranej pozycji — wbudowana, nie modal │
    └ pasek stanu ───────────────────────────────────────────────────────┘

⚠️ GDZIE CO SIĘ ZAPISUJE — i dlaczego NIE ma tu własnej tabeli mapowań:

  * symbol dostawcy → kartoteka        → SUBIEKT, `DaneAsortymentuDlaPodmiotu`
                                          (most, tryb `symbole-dostawcy`).
                                          Sfera ma to wbudowane razem z
                                          `WyszukajPoSymboluDostawcy`; własna
                                          tabela dublowałaby mechanizm, który
                                          Subiekt już prowadzi.
  * numer rysunku RM → kartoteka       → `mapowania` (istniejąca tabela na
                                          NASZE detale, klucz `numer_rysunku`)
  * „czym jest ta linia" (typ, projekt,
    komentarz)                         → `FV_KSEF.pozycje.decyzja` (JSON)

Powiązanie w Subiekcie jest ODWRACALNE. Nieodwracalne jest tylko założenie
nowej kartoteki — i to idzie przez wspólny formularz `subiekt_asortyment`,
który sam pyta „Baza PRODUKCYJNA — założyć?".

Okno ma działać także BEZ mostu: kartoteka wtedy z cache na dysku, bez
powiązań z Subiekta — dopasowanie jest uboższe, ale nic nie wisi.
"""

import csv
import json
import os
import queue
import re
import tempfile
import threading
import tkinter as tk
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox, filedialog

import ksef_kartoteki as kk
from ksef_archiwum import (ArchiwumKsef, pobierz_nowe, uprosc, _zl,
                           _bezpieczna_nazwa, WZOR_NUMERU_KSEF)
from rm_kreciolek import Kreciolek
from subiekt_panel import TLO, TLO_SEKCJI, OBRAMOWANIE, TEKST, TEKST_SZARY
from subiekt_stany import wysrodkuj

# ── wygląd statusów ─────────────────────────────────────────────────────────
#: status → (etykieta, tło wiersza, kolor tekstu). Kolory świadomie stonowane:
#: wiersz ma być czytelny, nie krzyczeć.
STATUSY = {
    kk.KARTOTEKA:        ("✔  KARTOTEKA",         "#e8f8e8", "#1e7e34"),
    kk.NOWA_KARTOTEKA:   ("✔  NOWA KARTOTEKA",    "#e8f8e8", "#1e7e34"),
    kk.RYSUNEK_RM:       ("📐  RYSUNEK RM",       "#e8f0fb", "#1f5fa8"),
    kk.POZYCJA_ZBIORCZA: ("◫  POZYCJA ZBIORCZA",  "#f1e8fb", "#6c3fb5"),
    kk.USLUGA:           ("—  USŁUGA",            "#f2f2f2", "#666666"),
    kk.BRAK_DECYZJI:     ("!  BRAK DECYZJI",      "#fdecea", "#c0392b"),
}

#: Cztery typy pozycji do wyboru w panelu decyzji. To pytanie brzmi „czym
#: to jest", NIE „załóż kartotekę" — przy części pozycji kartoteka jest złym
#: pytaniem (usługa, pozycja zbiorcza alu-frost, detal z naszego rysunku).
TYPY = [
    ("towar",    "Towar handlowy",       "z kartoteki dostawcy",        "#e8f8e8"),
    ("usluga",   "Usługa",               "nie wchodzi na stan",         "#f2f2f2"),
    ("zbiorcza", "Pozycja zbiorcza",     "jedna linia = wiele detali",  "#f1e8fb"),
    ("rysunek",  "Detal z naszego rysunku", "numer rysunku RM, projekt", "#e8f0fb"),
]

#: Odznaki faktur w drzewie. „Gotowa do PZ" celowo zamiast „Rozliczona" z
#: makiety — rozliczenie to osobny etap (FZ w Subiekcie), którego to okno
#: nie robi. Nie obiecujemy więcej, niż wiemy.
ODZNAKI = {
    "nowa":   ("Nowa",           "#eaf3fb"),
    "wtoku":  ("W toku",         "#fdf2e6"),
    "gotowa": ("Rozstrzygnięta", "#e8f8e8"),
    "pusta":  ("Bez pozycji",    "#f2f2f2"),
}

#: Szerokości dobrane tak, żeby przy 1540 px CAŁA tabela — ze Statusem —
#: mieściła się bez przewijania w bok. Numer rysunku nie ma własnej kolumny:
#: dla detalu z rysunku identyfikatorem JEST numer rysunku, a panel decyzji
#: pokazuje go osobno.
KOL_POZYCJE = [
    ("lp",        "Lp.",            38,  "e"),
    ("ident",     "Identyfikator",  140, "w"),
    ("typ",       "Typ",            62,  "c"),
    ("nazwa",     "Nazwa / opis",   190, "w"),
    ("ilosc",     "Ilość",          52,  "e"),
    ("jm",        "JM",             40,  "c"),
    ("cena",      "Cena netto",     72,  "e"),
    ("wz",        "WZ",             84,  "w"),
    ("kartoteka", "Kartoteka",      150, "w"),
    ("projekty",  "Projekty",       78,  "w"),
    ("status",    "Status",         140, "w"),
]

FONT = ("Arial", 9)
FONT_B = ("Arial", 9, "bold")
FONT_TYTUL = ("Arial", 15, "bold")


class Pozycja:
    """Wiersz faktury z archiwum + decyzja człowieka (dict albo None)."""

    __slots__ = ("nr_wiersza", "nazwa", "jednostka", "ilosc", "cena_netto",
                 "wartosc_netto", "indeks", "dodatkowe", "decyzja")

    def __init__(self, w):
        self.nr_wiersza = w.get("nr_wiersza")
        self.nazwa = (w.get("nazwa") or "").strip()
        self.jednostka = (w.get("jednostka") or "").strip()
        self.ilosc = w.get("ilosc")
        self.cena_netto = w.get("cena_netto")
        self.wartosc_netto = w.get("wartosc_netto")
        self.indeks = (w.get("indeks") or "").strip()
        self.dodatkowe = _json_lub(w.get("dodatkowe"), {})
        self.decyzja = _json_lub(w.get("decyzja"), None)


def _json_lub(tekst, domyslne):
    if not tekst:
        return domyslne
    if isinstance(tekst, (dict, list)):
        return tekst
    try:
        return json.loads(tekst)
    except (ValueError, TypeError):
        return domyslne


def _kto():
    return os.environ.get("USERNAME") or "?"


# ── nagłówek faktury z XML ──────────────────────────────────────────────────
def _lt(e):
    return e.tag.split("}", 1)[-1]


def _pierwszy(root, nazwa):
    for e in root.iter():
        if _lt(e) == nazwa:
            return e
    return None


def _tekst(e, nazwa, domyslne=""):
    if e is None:
        return domyslne
    for c in e:
        if _lt(c) == nazwa:
            return (c.text or "").strip() or domyslne
    return domyslne


def _podmiot(e):
    if e is None:
        return {}
    dane = _pierwszy(e, "DaneIdentyfikacyjne")
    adres = _pierwszy(e, "Adres")
    kontakt = _pierwszy(e, "DaneKontaktowe")
    linie = [_tekst(adres, "AdresL1"), _tekst(adres, "AdresL2")]
    return {
        "nip": _tekst(dane, "NIP"),
        "nazwa": _tekst(dane, "Nazwa"),
        "adres": ", ".join(x for x in linie if x),
        "kraj": _tekst(adres, "KodKraju"),
        "email": _tekst(kontakt, "Email"),
        "telefon": _tekst(kontakt, "Telefon"),
        "eori": _tekst(e, "NrEORI"),
    }


#: Adnotacje FA(3): pole → (opis, wartość „tak"). Większość to 1=tak / 2=nie.
_ADNOTACJE = [
    ("P_16", "metoda kasowa"), ("P_17", "samofakturowanie"),
    ("P_18", "odwrotne obciążenie"), ("P_18A", "mechanizm podzielonej płatności"),
    ("P_23", "procedura uproszczona (trójstronna)"),
]


def naglowek_z_xml(xml_text):
    """Pola nagłówka, których parser faktur NIE zwraca (daty, WZ, adresy…).

    Parser (`ksef_invoice_parser`) celowo bierze minimum wspólne dla FA(2)
    i FA(3). Okno potrzebuje więcej — ale tylko do POKAZANIA, więc czytamy
    to wprost z XML-a trzymanego w bazie, bez zmian w parserze.
    """
    out = {"wz": [], "adnotacje": [], "dodatkowe_faktury": []}
    if not xml_text:
        return out
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    fa = _pierwszy(root, "Fa")
    out["waluta"] = _tekst(fa, "KodWaluty")
    out["data_wystawienia"] = _tekst(fa, "P_1")
    out["miejsce"] = _tekst(fa, "P_1M")
    out["numer"] = _tekst(fa, "P_2")
    out["data_sprzedazy"] = _tekst(fa, "P_6")
    out["netto"] = _tekst(fa, "P_13_1")
    out["vat"] = _tekst(fa, "P_14_1")
    out["brutto"] = _tekst(fa, "P_15")
    out["rodzaj"] = _tekst(fa, "RodzajFaktury")
    if fa is not None:
        for c in fa:
            if _lt(c) == "WZ" and (c.text or "").strip():
                out["wz"].append(c.text.strip())
            elif _lt(c) == "DodatkowyOpis":
                # Wpisy BEZ NrWiersza dotyczą całej faktury (te z numerem
                # są już przy pozycjach jako `dodatkowe`).
                if _tekst(c, "NrWiersza"):
                    continue
                out["dodatkowe_faktury"].append((_tekst(c, "Klucz"), _tekst(c, "Wartosc")))
    adn = _pierwszy(fa, "Adnotacje") if fa is not None else None
    if adn is not None:
        for pole, opis in _ADNOTACJE:
            v = _tekst(adn, pole)
            if v:
                out["adnotacje"].append((opis, "tak" if v == "1" else "nie"))
        zw = _pierwszy(adn, "Zwolnienie")
        if zw is not None:
            out["adnotacje"].append(("zwolnienie z VAT",
                                     "nie" if _tekst(zw, "P_19N") == "1" else "tak"))
        nst = _pierwszy(adn, "NoweSrodkiTransportu")
        if nst is not None:
            out["adnotacje"].append(("nowe środki transportu",
                                     "nie" if _tekst(nst, "P_22N") == "1" else "tak"))
        pm = _pierwszy(adn, "PMarzy")
        if pm is not None:
            out["adnotacje"].append(("procedura marży",
                                     "nie" if _tekst(pm, "P_PMarzyN") == "1" else "tak"))
    out["podmiot1"] = _podmiot(_pierwszy(root, "Podmiot1"))
    out["podmiot2"] = _podmiot(_pierwszy(root, "Podmiot2"))
    out["termin"] = _tekst(_pierwszy(root, "TerminPlatnosci"), "Termin")
    return out


# ── nałożenie decyzji na dopasowanie ────────────────────────────────────────
def nalozyc_decyzje(d):
    """Decyzja człowieka wygrywa z automatem — modyfikuje `Dopasowanie` w miejscu.

    Automat (`kk.dopasuj`) mówi, co WIDZI; decyzja mówi, co JEST. Usługa nie
    zostanie towarem, bo pasuje symbolem, a detal z rysunku nie zostanie
    brakiem, bo w kartotece go nie ma.
    """
    dec = getattr(d.pozycja, "decyzja", None)
    if not dec:
        return
    typ = dec.get("typ")
    kart_id = dec.get("asortyment_id")
    if kart_id:
        d.asortyment_id = kart_id
        d.symbol_subiekt = dec.get("symbol") or d.symbol_subiekt
        d.nazwa_subiekt = dec.get("nazwa") or d.nazwa_subiekt
        d.zrodlo = "decyzja"
    if typ == "usluga":
        d.status = kk.USLUGA
    elif typ == "zbiorcza":
        d.status = kk.POZYCJA_ZBIORCZA
    elif typ == "rysunek":
        d.status = kk.RYSUNEK_RM
        if dec.get("numer_rysunku"):
            d.identyfikator = dec["numer_rysunku"]
            d.zrodlo_identyfikatora = kk.IDENT_RYSUNEK
    elif typ == "towar":
        if kart_id:
            d.status = kk.NOWA_KARTOTEKA if dec.get("nowa") else kk.KARTOTEKA
        else:
            d.status = kk.BRAK_DECYZJI


def _typ_z_dopasowania(d):
    """Domyślny typ w panelu — z decyzji, a gdy jej nie ma, z tego, co widać."""
    dec = getattr(d.pozycja, "decyzja", None)
    if dec and dec.get("typ") in {t[0] for t in TYPY}:
        return dec["typ"]
    if d.status == kk.RYSUNEK_RM or d.zrodlo_identyfikatora == kk.IDENT_RYSUNEK:
        return "rysunek"
    if d.status == kk.USLUGA or kk.wyglada_na_usluge(d.pozycja):
        return "usluga"
    if d.status == kk.POZYCJA_ZBIORCZA or not d.identyfikator:
        return "zbiorcza"
    return "towar"


def _etykieta_typu(d):
    typ = _typ_z_dopasowania(d)
    return {"towar": "Dostawca", "usluga": "Usługa",
            "zbiorcza": "Opis", "rysunek": "Rysunek"}[typ]


def _opis_pozycji(d):
    """Kolumna „Nazwa / opis": to, co NIE jest identyfikatorem.

    QUAY: `P_7` = symbol, opis siedzi w `DodatkowyOpis/Opis` („Łożysko").
    AMB: nazwa = reszta `P_7` po kodzie rysunku. alu-frost: całe `P_7`.
    """
    dod = getattr(d.pozycja, "dodatkowe", None) or {}
    opis = (dod.get("Opis") or "").strip()
    marka = (dod.get("Marka") or "").strip()
    if opis:
        return f"{opis} ({marka})" if marka else opis
    if d.nazwa_pozycji and d.nazwa_pozycji != d.identyfikator:
        return d.nazwa_pozycji
    return marka


# ═══════════════════════════════════════════════════════════════════════════
class OknoFaktury(tk.Toplevel, Kreciolek):

    def __init__(self, parent, katalog, ksef_cfg=None):
        super().__init__(parent)
        self.parent_app = parent
        self.arch = ArchiwumKsef(katalog)
        self.ksef_cfg = ksef_cfg or {}
        self.title("🧾 RM_BAZA — Faktury z KSeF")
        self.geometry("1540x920")
        self.minsize(1180, 700)
        self.configure(bg=TLO)

        # dane w tle
        self.katalog_sub = []          # [{"id","symbol","nazwa"}]
        self._kat_po_id = {}
        self.powiazania = {}           # nip -> {SYMBOL: {"asortyment_id","symbol","nazwa"}}
        self.kontrahenci = {}          # nip -> {"Id","NazwaSkrocona"}
        self.rysunki = {}              # NUMER (upper) -> [{"projekt","nazwa","ilosc"}]
        self.most_ok = None            # None = nie wiadomo jeszcze
        self._wszystkie_pozycje = {}   # ksef -> [Pozycja]
        self.stan_faktur = {}          # ksef -> {"odznaka", "brak", "razem", ...}

        # bieżąca faktura
        self.faktury = []
        self._biezaca = None
        self._naglowek = {}
        self._xml = ""
        self._pozycje = []
        self._dop = []
        self._map_rysunki = {}
        self._wybrany_lp = None
        self._wybrana_kartoteka = None

        self._wyniki = queue.Queue()
        self._szukaj_po = None

        self._buduj()
        self._odswiez_liste()
        self._start_tla()
        self._pompuj()
        wysrodkuj(self, parent)
        self.protocol("WM_DELETE_WINDOW", self._zamknij)

    # ── budowa ─────────────────────────────────────────────────────────────
    def _buduj(self):
        self._pasek_narzedzi()

        glowny = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        glowny.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

        lewy = tk.Frame(glowny, bg=TLO_SEKCJI, highlightthickness=1,
                        highlightbackground=OBRAMOWANIE)
        self._panel_faktur(lewy)
        glowny.add(lewy, weight=0)

        prawy = ttk.PanedWindow(glowny, orient=tk.VERTICAL)
        gora = tk.Frame(prawy, bg=TLO)
        self._naglowek_faktury(gora)
        self._zakladki(gora)
        prawy.add(gora, weight=3)
        dol = tk.Frame(prawy, bg=TLO_SEKCJI, highlightthickness=1,
                       highlightbackground=OBRAMOWANIE)
        self._panel_decyzji(dol)
        prawy.add(dol, weight=0)
        glowny.add(prawy, weight=1)

        self._pasek_stanu()

    def _pasek_narzedzi(self):
        p = tk.Frame(self, bg=TLO)
        p.pack(fill=tk.X, padx=8, pady=8)

        def przycisk(tekst, cmd, **kw):
            b = tk.Button(p, text=tekst, command=cmd, bg="white", fg=TEKST,
                          relief=tk.SOLID, bd=1, font=FONT, padx=12, pady=5,
                          cursor="hand2", **kw)
            b.pack(side=tk.LEFT, padx=(0, 8))
            return b

        przycisk("📂  Wczytaj XML z dysku", self._wczytaj_pliki)
        self.btn_pobierz = przycisk("☁  Pobierz nowe z KSeF", self._pobierz)
        przycisk("⟳  Odśwież", self._odswiez_wszystko)
        self.lbl_licznik = tk.Label(p, text="", bg=TLO, fg=TEKST, font=FONT_B)
        self.lbl_licznik.pack(side=tk.RIGHT, padx=(8, 0))
        self.lbl_most = tk.Label(p, text="most: sprawdzam…", bg=TLO, fg=TEKST_SZARY, font=FONT)
        self.lbl_most.pack(side=tk.RIGHT, padx=(8, 16))

    def _panel_faktur(self, r):
        tk.Label(r, text="Faktury (archiwum)", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 11, "bold"), anchor="w").pack(fill=tk.X, padx=10, pady=(10, 4))
        szuk = tk.Frame(r, bg=TLO_SEKCJI)
        szuk.pack(fill=tk.X, padx=10, pady=(0, 6))
        self.var_szukaj = tk.StringVar()
        e = ttk.Entry(szuk, textvariable=self.var_szukaj, font=FONT)
        e.pack(side=tk.LEFT, fill=tk.X, expand=True)
        e.bind("<KeyRelease>", self._szukaj_opoznione)
        e.bind("<Return>", lambda _e: self._odswiez_liste())
        tk.Label(szuk, text="  numer, dostawca, NIP, pozycja", bg=TLO_SEKCJI,
                 fg=TEKST_SZARY, font=("Arial", 8)).pack(side=tk.LEFT)

        wrap = tk.Frame(r, bg=TLO_SEKCJI)
        wrap.pack(fill=tk.BOTH, expand=True, padx=(10, 0), pady=(0, 6))
        self.tv_f = ttk.Treeview(wrap, columns=("dostawca", "netto", "stan"),
                                 show="tree headings", selectmode="browse")
        self.tv_f.heading("#0", text="Data / numer")
        self.tv_f.heading("dostawca", text="Dostawca")
        self.tv_f.heading("netto", text="Netto")
        self.tv_f.heading("stan", text="Stan")
        self.tv_f.column("#0", width=135, minwidth=110)
        self.tv_f.column("dostawca", width=112, minwidth=80)
        self.tv_f.column("netto", width=68, anchor="e", minwidth=60)
        self.tv_f.column("stan", width=104, minwidth=70)
        sc = ttk.Scrollbar(wrap, orient="vertical", command=self.tv_f.yview)
        self.tv_f.configure(yscrollcommand=sc.set)
        self.tv_f.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        for klucz, (_, tlo) in ODZNAKI.items():
            self.tv_f.tag_configure(klucz, background=tlo)
        self.tv_f.tag_configure("data", font=FONT_B, background="#f4f6f8")
        self.tv_f.bind("<<TreeviewSelect>>", self._wybrano_fakture)

        self.lbl_razem = tk.Label(r, text="", bg=TLO_SEKCJI, fg=TEKST_SZARY,
                                  font=("Arial", 8), anchor="w")
        self.lbl_razem.pack(fill=tk.X, padx=10, pady=(0, 8))

    def _naglowek_faktury(self, r):
        n = tk.Frame(r, bg=TLO_SEKCJI, highlightthickness=1, highlightbackground=OBRAMOWANIE)
        n.pack(fill=tk.X, padx=(6, 0), pady=(0, 6))
        # ⚠️ Bez wag na kolumnach z wartościami. Gdy treść jest szersza niż
        # ramka, grid ODBIERA miejsce kolumnom z wagą — lewa kolumna wartości
        # zapadała się do zera i „Data wystawienia" stała pusta obok „Numery
        # WZ" (zrzut z testu 17.09.2026). Nadmiar bierze pusta kolumna 5.
        n.columnconfigure(5, weight=1)

        tyt = tk.Frame(n, bg=TLO_SEKCJI)
        tyt.grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(10, 2))
        self.lbl_numer = tk.Label(tyt, text="— wybierz fakturę —", bg=TLO_SEKCJI,
                                  fg=TEKST, font=FONT_TYTUL)
        self.lbl_numer.pack(side=tk.LEFT)
        self.lbl_odznaka = tk.Label(tyt, text="", bg=TLO_SEKCJI, fg="white",
                                    font=FONT_B, padx=8, pady=2)
        self.lbl_odznaka.pack(side=tk.LEFT, padx=(12, 0))
        self.lbl_zrodlo = tk.Label(tyt, text="", bg=TLO_SEKCJI, fg=TEKST_SZARY, font=FONT)
        self.lbl_zrodlo.pack(side=tk.LEFT, padx=(8, 0))

        self._pola_nagl = {}

        def pole(wiersz, kol, etykieta, klucz, przycisk=None):
            tk.Label(n, text=etykieta, bg=TLO_SEKCJI, fg=TEKST_SZARY, font=FONT,
                     anchor="w").grid(row=wiersz, column=kol, sticky="w", padx=(12, 6), pady=1)
            f = tk.Frame(n, bg=TLO_SEKCJI)
            f.grid(row=wiersz, column=kol + 1, sticky="w", pady=1)
            l = tk.Label(f, text="", bg=TLO_SEKCJI, fg=TEKST, font=FONT_B, anchor="w")
            l.pack(side=tk.LEFT)
            self._pola_nagl[klucz] = l
            if przycisk:
                tk.Button(f, text=przycisk[0], command=przycisk[1], font=("Arial", 8),
                          relief=tk.FLAT, bg="#eef2f6", cursor="hand2", padx=6
                          ).pack(side=tk.LEFT, padx=(8, 0))

        pole(1, 0, "Data wystawienia", "data_wystawienia")
        pole(2, 0, "Data sprzedaży", "data_sprzedazy")
        pole(3, 0, "Miejsce / waluta", "miejsce_waluta")
        pole(4, 0, "Rodzaj faktury", "rodzaj")
        pole(1, 2, "Numery WZ", "wz", ("Pokaż wszystkie", self._pokaz_wz))
        pole(2, 2, "Kwoty", "kwoty")
        pole(3, 2, "Numer KSeF", "ksef", ("Kopiuj", self._kopiuj_ksef))
        pole(4, 2, "Kontrahent w Subiekcie", "kontrahent")

        # dostawca / nabywca — jeden POD drugim po prawej. Obok siebie blok
        # miał ~500 px i przy 1540 px okna nabywca wychodził poza ramkę.
        strony = tk.Frame(n, bg=TLO_SEKCJI)
        strony.grid(row=0, column=4, rowspan=5, sticky="ne", padx=12, pady=(8, 6))
        self._strony = {}
        for i, (klucz, tytul) in enumerate((("podmiot1", "Dostawca (Podmiot1)"),
                                            ("podmiot2", "Nabywca (Podmiot2)"))):
            b = tk.Frame(strony, bg=TLO_SEKCJI)
            b.grid(row=i, column=0, sticky="nw", pady=(0, 4))
            tk.Label(b, text=tytul, bg=TLO_SEKCJI, fg=TEKST, font=FONT_B,
                     anchor="w").pack(fill=tk.X)
            l = tk.Label(b, text="", bg=TLO_SEKCJI, fg=TEKST, font=FONT,
                         anchor="w", justify="left", wraplength=300)
            l.pack(fill=tk.X)
            self._strony[klucz] = l

    def _zakladki(self, r):
        self.nb = ttk.Notebook(r)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=(6, 0))

        # ── Pozycje ──
        poz = tk.Frame(self.nb, bg=TLO_SEKCJI)
        self.nb.add(poz, text="Pozycje")
        pas = tk.Frame(poz, bg=TLO_SEKCJI)
        pas.pack(fill=tk.X, padx=8, pady=6)

        def mały(tekst, cmd):
            b = tk.Button(pas, text=tekst, command=cmd, bg="white", fg=TEKST,
                          relief=tk.SOLID, bd=1, font=FONT, padx=10, pady=3, cursor="hand2")
            b.pack(side=tk.LEFT, padx=(0, 6))
            return b

        self.btn_dopasuj = mały("⟳  Dopasuj ponownie", self._dopasuj_ponownie)
        mały("📄  Eksport do CSV", self._eksport_csv)
        mały("⏭  Następny brak", self._nastepny_brak)

        # Liczniki w OSOBNYM rzędzie — w jednym z przyciskami nachodziły na
        # siebie i „Brak decyzji" wyświetlało się jako „ak decyzji".
        chipy = tk.Frame(poz, bg=TLO_SEKCJI)
        chipy.pack(fill=tk.X, padx=8, pady=(0, 4))
        self._chipy = {}
        for klucz, etykieta, kolor in (("razem", "Pozycji", TEKST),
                                       ("kartoteka", "Kartoteka", "#1e7e34"),
                                       ("rysunki", "Rysunek RM", "#1f5fa8"),
                                       ("zbiorcze", "Zbiorcze", "#6c3fb5"),
                                       ("uslugi", "Usługi", "#666666"),
                                       ("brak", "Brak decyzji", "#c0392b")):
            l = tk.Label(chipy, text=f"{etykieta}: –", bg="#f4f6f8", fg=kolor, font=FONT_B,
                         padx=8, pady=3, relief=tk.FLAT)
            l.pack(side=tk.LEFT, padx=(0, 6))
            self._chipy[klucz] = l

        wrap = tk.Frame(poz, bg=TLO_SEKCJI)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.tv_p = ttk.Treeview(wrap, columns=[k[0] for k in KOL_POZYCJE],
                                 show="headings", selectmode="browse")
        for klucz, etykieta, szer, kotw in KOL_POZYCJE:
            self.tv_p.heading(klucz, text=etykieta)
            self.tv_p.column(klucz, width=szer, anchor=kotw, minwidth=40,
                             stretch=(klucz in ("nazwa", "kartoteka")))
        sc = ttk.Scrollbar(wrap, orient="vertical", command=self.tv_p.yview)
        scx = ttk.Scrollbar(wrap, orient="horizontal", command=self.tv_p.xview)
        self.tv_p.configure(yscrollcommand=sc.set, xscrollcommand=scx.set)
        self.tv_p.grid(row=0, column=0, sticky="nsew")
        sc.grid(row=0, column=1, sticky="ns")
        scx.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        for status, (_, tlo, fg) in STATUSY.items():
            self.tv_p.tag_configure(status, background=tlo)
        self.tv_p.bind("<<TreeviewSelect>>", self._wybrano_pozycje)
        self.tv_p.bind("<Double-1>", lambda _e: self.ent_kart.focus_set())

        # ── Dodatkowe informacje ──
        info = tk.Frame(self.nb, bg=TLO_SEKCJI)
        self.nb.add(info, text="Dodatkowe informacje")
        self.txt_info = tk.Text(info, font=("Consolas", 10), wrap="word", bg="white",
                                relief=tk.FLAT, padx=12, pady=10)
        sci = ttk.Scrollbar(info, orient="vertical", command=self.txt_info.yview)
        self.txt_info.configure(yscrollcommand=sci.set, state=tk.DISABLED)
        self.txt_info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sci.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_info.tag_configure("h", font=("Consolas", 10, "bold"), foreground="#1f5fa8")
        self.txt_info.tag_configure("k", foreground=TEKST_SZARY)

        # ── Plik XML ──
        x = tk.Frame(self.nb, bg=TLO_SEKCJI)
        self.nb.add(x, text="Plik XML")
        px = tk.Frame(x, bg=TLO_SEKCJI)
        px.pack(fill=tk.X, padx=8, pady=6)
        tk.Button(px, text="Otwórz w programie systemowym", command=self._otworz_xml,
                  bg="white", fg=TEKST, relief=tk.SOLID, bd=1, font=FONT, padx=10, pady=3,
                  cursor="hand2").pack(side=tk.LEFT)
        self.lbl_plik = tk.Label(px, text="", bg=TLO_SEKCJI, fg=TEKST_SZARY, font=FONT)
        self.lbl_plik.pack(side=tk.LEFT, padx=12)
        self.txt_xml = tk.Text(x, font=("Consolas", 9), wrap="none", bg="white",
                               relief=tk.FLAT, padx=8, pady=6)
        scy = ttk.Scrollbar(x, orient="vertical", command=self.txt_xml.yview)
        self.txt_xml.configure(yscrollcommand=scy.set, state=tk.DISABLED)
        self.txt_xml.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scy.pack(side=tk.RIGHT, fill=tk.Y)

    def _panel_decyzji(self, r):
        self.lbl_decyzja_tytul = tk.Label(r, text="Decyzja dla wybranej pozycji",
                                          bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 11, "bold"),
                                          anchor="w")
        self.lbl_decyzja_tytul.pack(fill=tk.X, padx=12, pady=(8, 2))

        body = tk.Frame(r, bg=TLO_SEKCJI)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)

        # typ pozycji — cztery „karty"
        typy = tk.Frame(body, bg=TLO_SEKCJI)
        typy.grid(row=0, column=0, sticky="nw", padx=(0, 14))
        tk.Label(typy, text="Czym jest ta pozycja?", bg=TLO_SEKCJI, fg=TEKST,
                 font=FONT_B, anchor="w").pack(fill=tk.X, pady=(0, 4))
        self.var_typ = tk.StringVar(value="towar")
        self._radio_typ = {}
        for klucz, tytul, opis, kolor in TYPY:
            rb = tk.Radiobutton(typy, text=f"{tytul}\n{opis}", value=klucz,
                                variable=self.var_typ, indicatoron=0, justify="left",
                                anchor="w", bg="white", selectcolor=kolor, relief=tk.RIDGE,
                                bd=1, padx=10, pady=5, font=FONT, width=24,
                                command=self._zmiana_typu, cursor="hand2")
            rb.pack(fill=tk.X, pady=2)
            self._radio_typ[klucz] = rb

        # pola
        pola = tk.Frame(body, bg=TLO_SEKCJI)
        pola.grid(row=0, column=1, sticky="nsew", padx=(0, 14))
        pola.columnconfigure(1, weight=1)

        def wiersz(i, etykieta):
            tk.Label(pola, text=etykieta, bg=TLO_SEKCJI, fg=TEKST_SZARY, font=FONT,
                     anchor="w").grid(row=i, column=0, sticky="w", padx=(0, 8), pady=3)

        wiersz(0, "Identyfikator z faktury")
        self.var_ident = tk.StringVar()
        ttk.Entry(pola, textvariable=self.var_ident, font=FONT, state="readonly"
                  ).grid(row=0, column=1, sticky="ew", pady=3)
        wiersz(1, "Źródło identyfikatora")
        self.lbl_zrodlo_id = tk.Label(pola, text="", bg=TLO_SEKCJI, fg=TEKST, font=FONT, anchor="w")
        self.lbl_zrodlo_id.grid(row=1, column=1, sticky="w", pady=3)
        wiersz(2, "Numer rysunku RM")
        self.var_rysunek = tk.StringVar()
        self.ent_rysunek = ttk.Entry(pola, textvariable=self.var_rysunek, font=FONT)
        self.ent_rysunek.grid(row=2, column=1, sticky="ew", pady=3)
        self.ent_rysunek.bind("<KeyRelease>", lambda _e: self._odswiez_projekty())
        wiersz(3, "Projekt (z BOM-ów)")
        self.var_projekt = tk.StringVar()
        self.cb_projekt = ttk.Combobox(pola, textvariable=self.var_projekt, font=FONT,
                                       state="readonly")
        self.cb_projekt.grid(row=3, column=1, sticky="ew", pady=3)
        wiersz(4, "Komentarz")
        self.var_komentarz = tk.StringVar()
        ttk.Entry(pola, textvariable=self.var_komentarz, font=FONT
                  ).grid(row=4, column=1, sticky="ew", pady=3)

        # kartoteka — wyszukiwarka
        kart = tk.Frame(body, bg=TLO_SEKCJI)
        kart.grid(row=0, column=2, sticky="nsew", padx=(0, 14))
        kart.columnconfigure(0, weight=1)
        kart.rowconfigure(2, weight=1)
        tk.Label(kart, text="Kartoteka w Subiekcie", bg=TLO_SEKCJI, fg=TEKST_SZARY,
                 font=FONT, anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 3))
        sz = tk.Frame(kart, bg=TLO_SEKCJI)
        sz.grid(row=1, column=0, sticky="ew")
        sz.columnconfigure(0, weight=1)
        self.var_kart = tk.StringVar()
        self.ent_kart = ttk.Entry(sz, textvariable=self.var_kart, font=FONT)
        self.ent_kart.grid(row=0, column=0, sticky="ew")
        self.ent_kart.bind("<KeyRelease>", lambda _e: self._szukaj_kartoteki())
        self.ent_kart.bind("<Return>", lambda _e: self._wybierz_pierwsza())
        self.ent_kart.bind("<Down>", lambda _e: self.lb_kart.focus_set())
        tk.Button(sz, text="✕", command=self._wyczysc_kartoteke, font=("Arial", 8),
                  relief=tk.FLAT, bg="#eef2f6", cursor="hand2", padx=6
                  ).grid(row=0, column=1, padx=(4, 0))
        self.lb_kart = tk.Listbox(kart, height=5, font=FONT, activestyle="none",
                                  selectbackground="#d6e4f0", selectforeground=TEKST)
        self.lb_kart.grid(row=2, column=0, sticky="nsew", pady=(3, 3))
        self.lb_kart.bind("<<ListboxSelect>>", self._wybrano_z_listy)
        self.lb_kart.bind("<Return>", self._wybrano_z_listy)
        self.lb_kart.bind("<Double-1>", self._wybrano_z_listy)
        self.lbl_kart = tk.Label(kart, text="— nie wskazano —", bg="#f4f6f8", fg=TEKST,
                                 font=FONT_B, anchor="w", padx=8, pady=4)
        self.lbl_kart.grid(row=3, column=0, sticky="ew")
        self._kandydaci_kart = []

        # akcje
        akcje = tk.Frame(body, bg=TLO_SEKCJI)
        akcje.grid(row=0, column=3, sticky="ne")
        self.btn_zapisz = tk.Button(akcje, text="✔  Zapisz decyzję", command=self._zapisz_decyzje,
                                    bg="#2980b9", fg="white", disabledforeground="#a9cce8",
                                    relief=tk.FLAT, font=FONT_B, padx=14, pady=7, cursor="hand2",
                                    state=tk.DISABLED)
        self.btn_zapisz.pack(fill=tk.X, pady=(0, 6))
        self.btn_nowa = tk.Button(akcje, text="➕  Załóż nową kartotekę", command=self._zaloz_kartoteke,
                                  bg="white", fg=TEKST, relief=tk.SOLID, bd=1, font=FONT,
                                  padx=12, pady=5, cursor="hand2", state=tk.DISABLED)
        self.btn_nowa.pack(fill=tk.X, pady=(0, 6))
        self.btn_wyczysc = tk.Button(akcje, text="↶  Cofnij decyzję", command=self._cofnij_decyzje,
                                     bg="white", fg=TEKST, relief=tk.SOLID, bd=1, font=FONT,
                                     padx=12, pady=5, cursor="hand2", state=tk.DISABLED)
        self.btn_wyczysc.pack(fill=tk.X, pady=(0, 6))
        self.var_potwierdzaj = tk.BooleanVar(value=True)
        tk.Checkbutton(akcje, text="pytaj przed zapisem\ndo Subiekta", variable=self.var_potwierdzaj,
                       bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8), justify="left",
                       anchor="w").pack(fill=tk.X)

        # co zostanie zapisane (PRZED) / co się zapisało (PO)
        self.lbl_plan = tk.Label(r, text="Kliknij pozycję w tabeli.", bg="#f4f6f8", fg=TEKST,
                                 font=FONT, anchor="w", justify="left", padx=12, pady=6)
        self.lbl_plan.pack(fill=tk.X, padx=12, pady=(0, 8))
        for v in (self.var_typ, self.var_rysunek, self.var_projekt, self.var_komentarz):
            v.trace_add("write", lambda *_a: self._odswiez_plan())

    def _pasek_stanu(self):
        p = tk.Frame(self, bg="#eef2f6")
        p.pack(fill=tk.X, side=tk.BOTTOM)
        self.status = tk.Label(p, text="Gotowe.", bg="#eef2f6", fg=TEKST, font=FONT, anchor="w")
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12, pady=5)
        tk.Label(p, text=f"Zalogowany: {_kto()}", bg="#eef2f6", fg=TEKST_SZARY,
                 font=FONT).pack(side=tk.RIGHT, padx=12)

    # ── pętla wyników z wątków ─────────────────────────────────────────────
    def _pompuj(self):
        try:
            while True:
                fn = self._wyniki.get_nowait()
                try:
                    fn()
                except Exception as e:
                    print(f"⚠️  faktury_gui: {type(e).__name__}: {e}")
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._pompuj)

    def _w_tle(self, praca, potem):
        """`praca()` w wątku; `potem(wynik, blad)` w wątku GUI."""
        def run():
            try:
                w = praca()
                self._wyniki.put(lambda: potem(w, None))
            except Exception as e:
                self._wyniki.put(lambda: potem(None, e))
        threading.Thread(target=run, daemon=True).start()

    # ── dane w tle: kartoteka, powiązania, kontrahenci, rysunki ──────────
    def _start_tla(self):
        # 1. kartoteka z cache — natychmiast, żeby tabela miała z czym pracować
        try:
            import subiekt_scalanie
            self._ustaw_katalog(subiekt_scalanie.wczytaj_katalog_subiekta(tylko_cache=True))
        except Exception:
            pass
        self.start_kreciolek("Pytam Subiekta o kartotekę i powiązania")
        self._w_tle(self._tlo_praca, self._tlo_gotowe)
        self._w_tle(self._rysunki_praca, self._rysunki_gotowe)
        self._w_tle(lambda: self.arch._czytaj("ksef-pozycje-wszystkie"), self._pozycje_gotowe)

    def _tlo_praca(self):
        import subiekt_bridge
        import subiekt_scalanie
        wynik = {"most": False}
        try:
            subiekt_bridge.zapewnij_most()
            wynik["most"] = True
        except Exception:
            return wynik                          # bez mostu: zostaje cache
        wynik["katalog"] = subiekt_scalanie.wczytaj_katalog_subiekta()
        dane = subiekt_bridge.call("symbole-dostawcy", {}, timeout=60)
        wynik["powiazania"] = (dane or {}).get("powiazania", [])
        k = subiekt_bridge.call("kontrahenci", {}, timeout=60)
        wynik["kontrahenci"] = (k or {}).get("kontrahenci", [])
        return wynik

    def _tlo_gotowe(self, w, blad):
        self.stop_kreciolek()
        if blad or not w:
            self.most_ok = False
            self.lbl_most.config(text="most: niedostępny — kartoteka z cache", fg="#c0392b")
            self.status.config(text=f"Most niedostępny: {blad}" if blad else "Most niedostępny.")
            self._przelicz_odznaki()
            return
        self.most_ok = w.get("most", False)
        if not self.most_ok:
            self.lbl_most.config(text="most: niedostępny — kartoteka z cache", fg="#c0392b")
        else:
            self.lbl_most.config(text="most: ONLINE", fg="#1e7e34")
            self._ustaw_katalog(w.get("katalog") or self.katalog_sub)
            self.powiazania = {}
            for p in w.get("powiazania", []):
                nip = re.sub(r"\D", "", p.get("Nip") or "")
                sym = (p.get("SymbolDostawcy") or "").strip().upper()
                if nip and sym:
                    self.powiazania.setdefault(nip, {})[sym] = {
                        "asortyment_id": p.get("AsortymentId"),
                        "symbol": p.get("Symbol") or "",
                        "nazwa": p.get("Nazwa") or ""}
            self.kontrahenci = {re.sub(r"\D", "", k.get("NIP") or ""): k
                                for k in w.get("kontrahenci", []) if k.get("NIP")}
            n = sum(len(v) for v in self.powiazania.values())
            self.status.config(text=f"Kartoteka: {len(self.katalog_sub)} pozycji, "
                                    f"powiązań symboli dostawców w Subiekcie: {n}.")
        self._przelicz_odznaki()
        if self._biezaca:
            self._dopasuj_biezaca()
            # Użytkownik mógł już kliknąć pozycję, zanim most odpowiedział —
            # panel ma dostać kartotekę z powiązania, nie zostać „pusty".
            if self._wybrany_lp is not None and self.tv_p.exists(str(self._wybrany_lp)):
                self.tv_p.selection_set(str(self._wybrany_lp))
                self._wybrano_pozycje()

    def _ustaw_katalog(self, katalog):
        self.katalog_sub = katalog or []
        self._kat_po_id = {k.get("id"): k for k in self.katalog_sub if k.get("id") is not None}

    def _rysunki_praca(self):
        import rm_klient
        d = rm_klient.indeks_rysunkow() or {}
        # ⚠️ Porównujemy BEZ wielkości liter: faktura AMB pisze `013-100.30B`,
        # BOM ma `013-100.30b` — ten sam detal (pomiar 17.09.2026, 4554 numery,
        # jedyna kolizja po upper() to „Uszczelka"/„uszczelka"). Serwer buduje
        # indeks z zachowaniem liter, więc scalamy tu.
        out = {}
        for numer, lista in (d.get("rysunki") or {}).items():
            out.setdefault((numer or "").strip().upper(), []).extend(lista or [])
        return out

    def _rysunki_gotowe(self, w, blad):
        if blad:
            self.status.config(text=f"Indeks rysunków niedostępny: {blad}")
            return
        self.rysunki = w or {}
        if self._biezaca:
            self._wypelnij_tabele()

    def _pozycje_gotowe(self, w, blad):
        if blad:
            return
        self._wszystkie_pozycje = {}
        for r in w or []:
            self._wszystkie_pozycje.setdefault(r["ksef_number"], []).append(Pozycja(r))
        self._przelicz_odznaki()

    # ── lista faktur ───────────────────────────────────────────────────────
    def _szukaj_opoznione(self, _e=None):
        if self._szukaj_po:
            self.after_cancel(self._szukaj_po)
        self._szukaj_po = self.after(350, self._odswiez_liste)

    def _odswiez_liste(self):
        self._szukaj_po = None
        try:
            self.faktury = self.arch.faktury(szukaj=self.var_szukaj.get().strip())
        except Exception as e:
            self.status.config(text=f"Nie udało się wczytać listy faktur: {e}")
            self.faktury = []
        self._wypelnij_drzewo()

    def _wypelnij_drzewo(self):
        zaznaczona = self._biezaca
        self.tv_f.delete(*self.tv_f.get_children())
        po_dacie = {}
        for f in self.faktury:
            po_dacie.setdefault(f[1] or "bez daty", []).append(f)
        for data in sorted(po_dacie, reverse=True):
            grupa = po_dacie[data]
            iid_d = f"d:{data}"
            self.tv_f.insert("", "end", iid=iid_d, text=f"{_data_pl(data)}  ({len(grupa)})",
                             open=True, tags=("data",))
            for ksef, _d, numer, sprzedawca, nip, pozycji, wartosc, _x in grupa:
                stan = self.stan_faktur.get(ksef)
                odz = stan["odznaka"] if stan else "nowa"
                tekst = ODZNAKI[odz][0]
                if stan and stan.get("brak"):
                    tekst += f" ({stan['brak']})"
                self.tv_f.insert(iid_d, "end", iid=ksef, text=numer or "(bez numeru)",
                                 values=(sprzedawca or nip or "", _zl(wartosc), tekst),
                                 tags=(odz,))
        self.lbl_razem.config(text=f"Razem faktur: {len(self.faktury)}")
        self.lbl_licznik.config(text=f"{len(self.faktury)} faktur")
        if zaznaczona and self.tv_f.exists(zaznaczona):
            self.tv_f.selection_set(zaznaczona)
            self.tv_f.see(zaznaczona)

    def _przelicz_odznaki(self):
        """Odznaki w drzewie — z dopasowania WSZYSTKICH faktur, w tle."""
        if not self._wszystkie_pozycje:
            return
        kat = self.katalog_sub
        pow_ = self.powiazania
        faktury = {f[0]: f[4] for f in self.faktury}
        pozycje = self._wszystkie_pozycje

        def praca():
            out = {}
            for ksef, poz in pozycje.items():
                nip = re.sub(r"\D", "", faktury.get(ksef) or "")
                dop = kk.dopasuj(poz, kat, pow_.get(nip, {}))
                for d in dop:
                    nalozyc_decyzje(d)
                s = kk.podsumowanie(dop)
                decyzji = sum(1 for p in poz if p.decyzja)
                if not poz:
                    s["odznaka"] = "pusta"
                elif s["brak"] == 0:
                    s["odznaka"] = "gotowa"
                elif decyzji:
                    s["odznaka"] = "wtoku"
                else:
                    s["odznaka"] = "nowa"
                out[ksef] = s
            return out

        def potem(w, blad):
            if blad:
                return
            self.stan_faktur = w
            self._wypelnij_drzewo()
            if self._biezaca:
                self._ustaw_odznake(self._biezaca)

        self._w_tle(praca, potem)

    # ── wybór faktury ──────────────────────────────────────────────────────
    def _wybrano_fakture(self, _e=None):
        sel = self.tv_f.selection()
        if not sel or sel[0].startswith("d:"):
            return
        # Przebudowa drzewa (odznaki) zaznacza tę samą fakturę na nowo i Tk
        # zgłasza to jak klik — bez tego warunku okno przeładowywało fakturę
        # i czyściło panel decyzji tuż po zapisie (test 17.09.2026).
        if sel[0] == self._biezaca:
            return
        self._pokaz_fakture(sel[0])

    def _pokaz_fakture(self, ksef):
        self._biezaca = ksef
        self._wybrany_lp = None
        f = next((x for x in self.faktury if x[0] == ksef), None)
        try:
            w = self.arch._czytaj("ksef-xml", {"ksef_number": ksef})
            r = w[0] if w else {}
        except Exception:
            r = {}
        self._xml = r.get("xml") or ""
        self._plik = r.get("plik") or ""
        self._naglowek = naglowek_z_xml(self._xml)
        try:
            self._pozycje = [Pozycja(x) for x in self.arch._czytaj("ksef-pozycje", {"ksef_number": ksef})]
        except Exception as e:
            self._pozycje = []
            self.status.config(text=f"Nie udało się wczytać pozycji: {e}")
        self._wszystkie_pozycje[ksef] = self._pozycje

        n = self._naglowek
        numer = (f[2] if f else "") or n.get("numer") or "(bez numeru)"
        self.lbl_numer.config(text=numer)
        self.lbl_zrodlo.config(text="(z KSeF)" if WZOR_NUMERU_KSEF.match(ksef) else "(z pliku XML)")
        self._pola_nagl["data_wystawienia"].config(text=_data_pl(n.get("data_wystawienia") or (f[1] if f else "")))
        self._pola_nagl["data_sprzedazy"].config(text=_data_pl(n.get("data_sprzedazy", "")))
        self._pola_nagl["miejsce_waluta"].config(
            text=" / ".join(x for x in (n.get("miejsce", ""), n.get("waluta", "")) if x) or "—")
        self._pola_nagl["rodzaj"].config(text=n.get("rodzaj") or "—")
        wz = n.get("wz", [])
        self._pola_nagl["wz"].config(
            text=(", ".join(wz[:2]) + (f" … razem {len(wz)}" if len(wz) > 2 else "")) if wz else "brak")
        kw = []
        if n.get("netto"):
            kw.append(f"netto {_zl(float(n['netto']))}")
        if n.get("vat"):
            kw.append(f"VAT {_zl(float(n['vat']))}")
        if n.get("brutto"):
            kw.append(f"brutto {_zl(float(n['brutto']))}")
        self._pola_nagl["kwoty"].config(text="   ".join(kw) or "—")
        self._pola_nagl["ksef"].config(text=ksef)
        nip = re.sub(r"\D", "", (f[4] if f else "") or n.get("podmiot1", {}).get("nip", ""))
        self._nip = nip
        self._ustaw_kontrahenta(nip)
        for klucz in ("podmiot1", "podmiot2"):
            p = n.get(klucz) or {}
            if not p and klucz == "podmiot1" and f:
                p = {"nip": f[4], "nazwa": f[3]}
            self._strony[klucz].config(
                text=f"NIP {p.get('nip') or '—'}   {p.get('nazwa') or '—'}\n{p.get('adres') or ''}".rstrip())
        self._ustaw_odznake(ksef)
        self._wypelnij_info()
        self._wypelnij_xml()
        self._map_rysunki = {}
        self._dopasuj_biezaca()
        self._wyczysc_panel()
        self.nb.tab(0, text=f"Pozycje ({len(self._pozycje)})")

    def _ustaw_kontrahenta(self, nip):
        if not self.kontrahenci:
            tekst, kolor = ("sprawdzam…" if self.most_ok is None else "—"), TEKST_SZARY
        elif nip in self.kontrahenci:
            k = self.kontrahenci[nip]
            tekst, kolor = f"{k.get('NazwaSkrocona')}  (Id {k.get('Id')})", "#1e7e34"
        else:
            tekst, kolor = "BRAK — powiązania symboli nie zapiszą się, dopóki nie założysz kontrahenta", "#c0392b"
        self._pola_nagl["kontrahent"].config(text=tekst, fg=kolor)

    def _ustaw_odznake(self, ksef):
        stan = self.stan_faktur.get(ksef)
        odz = stan["odznaka"] if stan else "nowa"
        etykieta, tlo = ODZNAKI[odz]
        kolory = {"nowa": "#2980b9", "wtoku": "#e67e22", "gotowa": "#1e7e34", "pusta": "#7f8c8d"}
        self.lbl_odznaka.config(text=etykieta, bg=kolory[odz])

    def _dopasuj_biezaca(self):
        if not self._biezaca:
            return
        nip = getattr(self, "_nip", "")
        self._dop = kk.dopasuj(self._pozycje, self.katalog_sub, self.powiazania.get(nip, {}))
        # Detale z NASZEGO rysunku: kartoteka z tabeli `mapowania`, gdy ktoś
        # już ją kiedyś wskazał (klucz numer rysunku, nie symbol dostawcy).
        numery = [d.identyfikator for d in self._dop if d.zrodlo_identyfikatora == kk.IDENT_RYSUNEK]
        if numery and not self._map_rysunki:
            def praca():
                import subiekt_mapowania
                return subiekt_mapowania.get_many(numery)

            def potem(w, blad):
                if blad or not w:
                    return
                self._map_rysunki = w
                self._dopasuj_biezaca()
            self._w_tle(praca, potem)
        for d in self._dop:
            if d.status == kk.RYSUNEK_RM and not d.asortyment_id:
                m = self._map_rysunki.get(d.identyfikator.upper())
                if m and m.get("id_subiekt"):
                    d.asortyment_id = m["id_subiekt"]
                    d.symbol_subiekt = m.get("symbol_subiekt") or ""
                    d.nazwa_subiekt = m.get("nazwa_subiekt") or ""
                    d.zrodlo = kk.ZRODLO_MAPOWANIE
            nalozyc_decyzje(d)
        self._wypelnij_tabele()

    def _wypelnij_tabele(self):
        zaznacz = self._wybrany_lp
        self.tv_p.delete(*self.tv_p.get_children())
        for d in self._dop:
            p = d.pozycja
            ident = d.identyfikator or ""
            rys = ident if d.zrodlo_identyfikatora == kk.IDENT_RYSUNEK or d.status == kk.RYSUNEK_RM else ""
            if rys and (p.decyzja or {}).get("numer_rysunku"):
                rys = p.decyzja["numer_rysunku"]
            kart = ""
            if d.asortyment_id:
                kart = f"ID {d.asortyment_id}  {d.symbol_subiekt}"
                if d.zrodlo == kk.ZRODLO_NORMALIZACJA:
                    kart += "  (kandydat)"
            proj = ""
            dec = p.decyzja or {}
            if dec.get("projekt"):
                proj = f"► {dec['projekt']}"
            elif rys:
                lista = self.rysunki.get(rys.upper(), [])
                nr = sorted({str(x.get("projekt")) for x in lista})
                proj = ", ".join(nr[:4]) + (f" +{len(nr) - 4}" if len(nr) > 4 else "")
            self.tv_p.insert("", "end", iid=str(p.nr_wiersza), tags=(d.status,), values=(
                p.nr_wiersza, rys or ident, _etykieta_typu(d), _opis_pozycji(d),
                _ilosc(p.ilosc), p.jednostka, _zl(p.cena_netto),
                (p.dodatkowe or {}).get("Numer wydania", ""), kart, proj,
                STATUSY[d.status][0]))
        s = kk.podsumowanie(self._dop)
        self._chipy["razem"].config(text=f"Pozycji: {s['razem']}")
        self._chipy["kartoteka"].config(text=f"Kartoteka: {s['znalezione']}")
        self._chipy["rysunki"].config(text=f"Rysunek RM: {s['rysunki']}")
        self._chipy["zbiorcze"].config(text=f"Zbiorcze: {s['zbiorcze']}")
        self._chipy["uslugi"].config(text=f"Usługi: {s['uslugi']}")
        self._chipy["brak"].config(text=f"Brak decyzji: {s['brak']}",
                                   bg="#fdecea" if s["brak"] else "#e8f8e8")
        if zaznacz is not None and self.tv_p.exists(str(zaznacz)):
            self.tv_p.selection_set(str(zaznacz))

    def _wypelnij_info(self):
        n = self._naglowek
        t = self.txt_info
        t.config(state=tk.NORMAL)
        t.delete("1.0", tk.END)

        def sekcja(tytul):
            t.insert(tk.END, f"\n{tytul}\n", "h")

        def para(k, v):
            t.insert(tk.END, f"  {k:<28}", "k")
            t.insert(tk.END, f"{v}\n")

        sekcja("Kwoty")
        para("Netto", _zl(float(n["netto"])) if n.get("netto") else "—")
        para("VAT", _zl(float(n["vat"])) if n.get("vat") else "—")
        para("Brutto", _zl(float(n["brutto"])) if n.get("brutto") else "—")
        para("Waluta", n.get("waluta") or "—")
        para("Termin płatności", _data_pl(n.get("termin", "")) or "—")
        sekcja(f"Numery WZ ({len(n.get('wz', []))})")
        t.insert(tk.END, "  " + (", ".join(n.get("wz", [])) or "brak") + "\n")
        sekcja("Adnotacje")
        for k, v in n.get("adnotacje", []):
            para(k, v)
        if not n.get("adnotacje"):
            t.insert(tk.END, "  brak\n")
        for klucz, tytul in (("podmiot1", "Dostawca (Podmiot1)"), ("podmiot2", "Nabywca (Podmiot2)")):
            p = n.get(klucz) or {}
            sekcja(tytul)
            for k, e in (("NIP", "nip"), ("Nazwa", "nazwa"), ("Adres", "adres"), ("Kraj", "kraj"),
                         ("E-mail", "email"), ("Telefon", "telefon"), ("EORI", "eori")):
                if p.get(e):
                    para(k, p[e])
        if n.get("dodatkowe_faktury"):
            sekcja("Dodatkowy opis faktury (bez numeru wiersza)")
            for k, v in n["dodatkowe_faktury"]:
                para(k, v)
        t.config(state=tk.DISABLED)

    def _wypelnij_xml(self):
        t = self.txt_xml
        t.config(state=tk.NORMAL)
        t.delete("1.0", tk.END)
        tresc = self._xml
        if tresc:
            try:
                from xml.dom import minidom
                tresc = minidom.parseString(tresc.encode("utf-8")).toprettyxml(indent="  ")
            except Exception:
                pass
        t.insert(tk.END, tresc or "(brak treści XML w bazie)")
        t.config(state=tk.DISABLED)
        self.lbl_plik.config(text=Path(self._plik).name if self._plik else "")

    def _pokaz_wz(self):
        wz = self._naglowek.get("wz", [])
        messagebox.showinfo("Numery WZ", "\n".join(wz) if wz else "Faktura nie podaje numerów WZ.",
                            parent=self)

    def _kopiuj_ksef(self):
        if self._biezaca:
            self.clipboard_clear()
            self.clipboard_append(self._biezaca)
            self.status.config(text="Numer KSeF skopiowany do schowka.")

    def _otworz_xml(self):
        if not self._xml:
            messagebox.showwarning("XML", "Brak treści XML tej faktury.", parent=self)
            return
        nazwa = Path(self._plik).name if self._plik else f"{_bezpieczna_nazwa(self._biezaca, 60)}.xml"
        tmp = Path(tempfile.gettempdir()) / nazwa
        tmp.write_text(self._xml, encoding="utf-8")
        os.startfile(str(tmp))

    # ── wybór pozycji → panel ──────────────────────────────────────────────
    def _dop_dla(self, lp):
        return next((d for d in self._dop if str(d.pozycja.nr_wiersza) == str(lp)), None)

    def _wybrano_pozycje(self, _e=None):
        sel = self.tv_p.selection()
        if not sel:
            return
        d = self._dop_dla(sel[0])
        if d is None:
            return
        # Klik człowieka w INNĄ pozycję kasuje raport z poprzedniego zapisu;
        # skok automatyczny po zapisie (`_auto_skok`) i odświeżenie tej samej
        # pozycji — nie.
        if d.pozycja.nr_wiersza != self._wybrany_lp and not getattr(self, "_auto_skok", False):
            self._raport = ""
        self._auto_skok = False
        self._wybrany_lp = d.pozycja.nr_wiersza
        p = d.pozycja
        dec = p.decyzja or {}
        self.lbl_decyzja_tytul.config(
            text=f"Decyzja dla pozycji Lp. {p.nr_wiersza}:  {p.nazwa}"
                 + (f"   —   zapisana {dec.get('kiedy', '')[:16].replace('T', ' ')} ({dec.get('kto', '')})"
                    if dec else ""))
        self.var_typ.set(_typ_z_dopasowania(d))
        self.var_ident.set(d.identyfikator or p.nazwa)
        self.lbl_zrodlo_id.config(text={
            kk.IDENT_INDEKS: "pole <Indeks> faktury",
            kk.IDENT_SYMBOL: "całe P_7 jako symbol dostawcy",
            kk.IDENT_NAZWA: "kod wyłuskany z nazwy — propozycja",
            kk.IDENT_RYSUNEK: "numer rysunku RM",
            kk.IDENT_BRAK: "brak — indeks powtarza się w kilku wierszach (kategoria)",
        }.get(d.zrodlo_identyfikatora, d.zrodlo_identyfikatora))
        self.var_rysunek.set(dec.get("numer_rysunku") or
                             (d.identyfikator if d.zrodlo_identyfikatora == kk.IDENT_RYSUNEK else ""))
        self.var_komentarz.set(dec.get("komentarz", ""))
        self._odswiez_projekty(dec.get("projekt"))
        if d.asortyment_id:
            self._ustaw_kartoteke({"id": d.asortyment_id, "symbol": d.symbol_subiekt,
                                   "nazwa": d.nazwa_subiekt}, zrodlo=d.zrodlo)
        else:
            self._wyczysc_kartoteke()
        self.var_kart.set("")
        self._szukaj_kartoteki(domyslnie=d.identyfikator or p.nazwa)
        self.btn_zapisz.config(state=tk.NORMAL)
        self.btn_wyczysc.config(state=tk.NORMAL if dec else tk.DISABLED)
        self._zmiana_typu()

    def _wyczysc_panel(self):
        self._wybrany_lp = None
        self._raport = ""
        self._auto_skok = False
        self.lbl_decyzja_tytul.config(text="Decyzja dla wybranej pozycji")
        for v in (self.var_ident, self.var_rysunek, self.var_projekt, self.var_komentarz, self.var_kart):
            v.set("")
        self.lbl_zrodlo_id.config(text="")
        self._wyczysc_kartoteke()
        self.lb_kart.delete(0, tk.END)
        self.btn_zapisz.config(state=tk.DISABLED)
        self.btn_nowa.config(state=tk.DISABLED)
        self.btn_wyczysc.config(state=tk.DISABLED)
        self.lbl_plan.config(text="Kliknij pozycję w tabeli.", bg="#f4f6f8", fg=TEKST)

    def _zmiana_typu(self):
        typ = self.var_typ.get()
        self.ent_rysunek.config(state=tk.NORMAL if typ == "rysunek" else tk.DISABLED)
        self.cb_projekt.config(state="readonly" if typ == "rysunek" else tk.DISABLED)
        kart_ma_sens = typ in ("towar", "rysunek")
        self.ent_kart.config(state=tk.NORMAL if kart_ma_sens else tk.DISABLED)
        self.btn_nowa.config(state=tk.NORMAL if (typ == "towar" and self._wybrany_lp is not None
                                                 and not self._wybrana_kartoteka) else tk.DISABLED)
        self._odswiez_plan()

    def _odswiej_projekty_lista(self, numer):
        lista = self.rysunki.get((numer or "").strip().upper(), [])
        po_proj = {}
        for x in lista:
            po_proj.setdefault(str(x.get("projekt")), x)
        return [f"{k} — {v.get('nazwa') or ''}".rstrip(" —") for k, v in sorted(po_proj.items())]

    def _odswiez_projekty(self, wybrany=None):
        wartosci = self._odswiej_projekty_lista(self.var_rysunek.get())
        self.cb_projekt["values"] = wartosci
        if wybrany:
            for w in wartosci:
                if w.split(" — ")[0] == str(wybrany):
                    self.var_projekt.set(w)
                    return
            self.var_projekt.set(str(wybrany))
        elif wartosci and self.var_projekt.get() not in wartosci:
            self.var_projekt.set("")

    # ── kartoteka: wyszukiwarka ────────────────────────────────────────────
    def _szukaj_kartoteki(self, domyslnie=None):
        fraza = uprosc(self.var_kart.get().strip() or domyslnie or "")
        self.lb_kart.delete(0, tk.END)
        self._kandydaci_kart = []
        if not fraza or not self.katalog_sub:
            return
        # Najpierw po znormalizowanym symbolu (IR 12*16*20 ~ IR12-16-20),
        # potem po podciągu w symbolu/nazwie. Bez fuzzy po nazwie — celowo.
        norm = kk.normalizuj_symbol(fraza)
        trafione, reszta = [], []
        for k in self.katalog_sub:
            sym, naz = k.get("symbol") or "", k.get("nazwa") or ""
            if norm and norm == kk.normalizuj_symbol(sym):
                trafione.append(k)
            elif fraza in uprosc(sym) or fraza in uprosc(naz):
                reszta.append(k)
            if len(trafione) + len(reszta) > 200:
                break
        # Pełny identyfikator (`618/4 2Z=684 2Z`) często nie trafia w nic —
        # wtedy pokazujemy kandydatów po pierwszym członie (`618/4`), żeby
        # człowiek miał od czego zacząć zamiast pustej listy.
        if not trafione and not reszta and domyslnie:
            czlon = re.split(r"[\s=]+", fraza)[0]
            if len(czlon) >= 3 and czlon != fraza:
                for k in self.katalog_sub:
                    if czlon in uprosc(k.get("symbol") or ""):
                        reszta.append(k)
                        if len(reszta) >= 40:
                            break
        self._kandydaci_kart = (trafione + reszta)[:60]
        for k in self._kandydaci_kart:
            self.lb_kart.insert(tk.END, f"{k.get('symbol')}   —   {k.get('nazwa')}")
        if trafione:
            self.lb_kart.itemconfig(0, bg="#e8f8e8")

    def _wybierz_pierwsza(self):
        if self._kandydaci_kart:
            self._ustaw_kartoteke(self._kandydaci_kart[0], zrodlo="ręcznie")

    def _wybrano_z_listy(self, _e=None):
        sel = self.lb_kart.curselection()
        if sel and sel[0] < len(self._kandydaci_kart):
            self._ustaw_kartoteke(self._kandydaci_kart[sel[0]], zrodlo="ręcznie")

    def _ustaw_kartoteke(self, k, zrodlo=""):
        self._wybrana_kartoteka = {"id": k.get("id"), "symbol": k.get("symbol") or "",
                                   "nazwa": k.get("nazwa") or ""}
        opis = {kk.ZRODLO_MAPOWANIE: "z powiązania w Subiekcie", kk.ZRODLO_SYMBOL: "dokładny symbol",
                kk.ZRODLO_NORMALIZACJA: "KANDYDAT po normalizacji — sprawdź",
                kk.ZRODLO_RYSUNEK: "numer rysunku = symbol", "decyzja": "z zapisanej decyzji",
                "ręcznie": "wskazana ręcznie"}.get(zrodlo, zrodlo)
        self.lbl_kart.config(text=f"ID {k.get('id')}   {k.get('symbol')}   {k.get('nazwa')}"
                                  + (f"\n({opis})" if opis else ""),
                             bg="#fdf2e6" if zrodlo == kk.ZRODLO_NORMALIZACJA else "#e8f8e8")
        self.btn_nowa.config(state=tk.DISABLED)
        self._odswiez_plan()

    def _wyczysc_kartoteke(self):
        self._wybrana_kartoteka = None
        self.lbl_kart.config(text="— nie wskazano —", bg="#f4f6f8")
        if self._wybrany_lp is not None and self.var_typ.get() == "towar":
            self.btn_nowa.config(state=tk.NORMAL)
        self._odswiez_plan()

    # ── plan zapisu (PRZED) ────────────────────────────────────────────────
    def _co_zapiszemy(self):
        """(decyzja, do_subiekta, do_mapowan) — jedno źródło prawdy dla
        opisu PRZED, potwierdzenia i samego zapisu."""
        d = self._dop_dla(self._wybrany_lp) if self._wybrany_lp is not None else None
        if d is None:
            return None, None, None
        typ = self.var_typ.get()
        k = self._wybrana_kartoteka if typ in ("towar", "rysunek") else None
        dec = {"typ": typ,
               "asortyment_id": (k or {}).get("id"),
               "symbol": (k or {}).get("symbol", ""),
               "nazwa": (k or {}).get("nazwa", ""),
               "numer_rysunku": self.var_rysunek.get().strip() if typ == "rysunek" else "",
               "projekt": self.var_projekt.get().split(" — ")[0].strip() if typ == "rysunek" else "",
               "komentarz": self.var_komentarz.get().strip(),
               "kto": _kto(), "kiedy": datetime.now().isoformat(timespec="seconds")}
        do_subiekta = None
        if typ == "towar" and k and k.get("id"):
            juz = self.powiazania.get(getattr(self, "_nip", ""), {}).get((d.identyfikator or "").upper())
            if not juz or juz.get("asortyment_id") != k["id"]:
                do_subiekta = {"nip": getattr(self, "_nip", ""),
                               "symbolDostawcy": d.identyfikator or d.pozycja.nazwa,
                               "symbol": k["symbol"], "asortymentId": k["id"],
                               "nazwaUDostawcy": (d.pozycja.nazwa or "")[:64],
                               "cenaDeklarowana": d.pozycja.cena_netto}
        do_mapowan = None
        if typ == "rysunek" and k and k.get("id") and dec["numer_rysunku"]:
            do_mapowan = (dec["numer_rysunku"], k["symbol"], k["id"], k["nazwa"])
        return dec, do_subiekta, do_mapowan

    def _odswiez_plan(self):
        if self._wybrany_lp is None:
            return
        dec, do_sub, do_map = self._co_zapiszemy()
        if dec is None:
            return
        # Raport PO z ostatniego zapisu zostaje na wierzchu, dopóki człowiek
        # sam nie kliknie innej pozycji — automatyczny skok do następnego
        # braku nie może go zdmuchnąć, bo wtedy nikt nie widzi, co się zapisało.
        linie = [self._raport] if getattr(self, "_raport", "") else []
        typ_nazwa = dict((t[0], t[1]) for t in TYPY)[dec["typ"]]
        linie.append(f"Zapis w archiwum faktur: typ „{typ_nazwa}”"
                     + (f", kartoteka {dec['symbol']}" if dec["asortyment_id"] else "")
                     + (f", rysunek {dec['numer_rysunku']}" if dec["numer_rysunku"] else "")
                     + (f", projekt {dec['projekt']}" if dec["projekt"] else "") + ".")
        if do_sub:
            linie.append(f"Zapis w SUBIEKCIE: symbol dostawcy „{do_sub['symbolDostawcy']}” "
                         f"→ kartoteka {do_sub['symbol']} (ID {do_sub['asortymentId']}). "
                         f"Odwracalne — powiązanie da się zmienić.")
        elif dec["typ"] == "towar" and dec["asortyment_id"]:
            linie.append("Subiekt zna już to powiązanie — nic tam nie dopiszemy.")
        elif dec["typ"] == "towar":
            linie.append("⚠️ Towar bez kartoteki = nadal BRAK DECYZJI. Wskaż kartotekę albo załóż nową.")
        if do_map:
            linie.append(f"Zapis w mapowaniach RM: rysunek {do_map[0]} → {do_map[1]} (ID {do_map[2]}).")
        if dec["typ"] == "rysunek" and not dec["numer_rysunku"]:
            linie.append("⚠️ Podaj numer rysunku.")
        ostrzeznie = any(l.startswith("⚠️") for l in linie)
        self.lbl_plan.config(text="\n".join(linie),
                             bg="#fdf2e6" if ostrzeznie else ("#e8f8e8" if getattr(self, "_raport", "") else "#f4f6f8"),
                             fg=TEKST)

    # ── zapis decyzji ──────────────────────────────────────────────────────
    def _zapisz_decyzje(self, nowa_kartoteka=False):
        if self._wybrany_lp is None or not self._biezaca:
            return
        dec, do_sub, do_map = self._co_zapiszemy()
        if dec is None:
            return
        if dec["typ"] == "rysunek" and not dec["numer_rysunku"]:
            messagebox.showwarning("Decyzja", "Podaj numer rysunku RM.", parent=self)
            return
        if nowa_kartoteka:
            dec["nowa"] = True
        if do_sub and self.var_potwierdzaj.get():
            if not messagebox.askyesno(
                    "Zapis do Subiekta",
                    f"Powiązać w Subiekcie symbol dostawcy\n\n"
                    f"    {do_sub['symbolDostawcy']}\n\n"
                    f"z kartoteką\n\n"
                    f"    {do_sub['symbol']}  (ID {do_sub['asortymentId']})\n"
                    f"    {dec['nazwa']}\n\n"
                    f"Kontrahent: NIP {do_sub['nip']}. Powiązanie jest odwracalne.\n"
                    f"Przy następnej fakturze tego dostawcy pozycja dopasuje się sama.",
                    parent=self):
                return

        ksef, lp = self._biezaca, self._wybrany_lp
        self.btn_zapisz.config(state=tk.DISABLED)
        self.start_kreciolek("Zapisuję decyzję")

        def praca():
            wynik = {"archiwum": False, "subiekt": None, "mapowania": None}
            self.arch._pisz("ksef-decyzja-zapisz", {
                "decyzja": json.dumps(dec, ensure_ascii=False), "ksef_number": ksef, "nr_wiersza": lp})
            wynik["archiwum"] = True
            if do_sub:
                import subiekt_bridge
                odp = subiekt_bridge.call("symbole-dostawcy",
                                          {"plan": {"powiazania": [do_sub]}, "zapisz": True},
                                          timeout=90, write=True)
                kroki = (odp or {}).get("kroki") or []
                wynik["subiekt"] = kroki[0] if kroki else {"Status": "blad", "Szczegoly": "brak odpowiedzi"}
            if do_map:
                import subiekt_mapowania
                numer, symbol, id_sub, nazwa = do_map
                wynik["mapowania"] = subiekt_mapowania.put(
                    numer, symbol, "faktura", id_subiekt=id_sub, nazwa_subiekt=nazwa,
                    uwagi=f"z faktury {self.lbl_numer.cget('text')}")
            return wynik

        def potem(w, blad):
            self.stop_kreciolek()
            self.btn_zapisz.config(state=tk.NORMAL)
            if blad:
                self.status.config(text=f"Błąd zapisu: {blad}")
                messagebox.showerror("Zapis decyzji", str(blad), parent=self)
                return
            # PO — co faktycznie się stało
            for p in self._pozycje:
                if p.nr_wiersza == lp:
                    p.decyzja = dec
            raport = [f"Lp. {lp}: decyzja zapisana w archiwum."]
            s = w.get("subiekt")
            if s:
                st = s.get("Status")
                if st == "powiazano":
                    self.powiazania.setdefault(do_sub["nip"], {})[do_sub["symbolDostawcy"].upper()] = {
                        "asortyment_id": do_sub["asortymentId"], "symbol": do_sub["symbol"],
                        "nazwa": dec["nazwa"]}
                    raport.append(f"Subiekt: powiązano „{do_sub['symbolDostawcy']}” → {do_sub['symbol']}.")
                elif st == "istnieje":
                    raport.append("Subiekt: powiązanie już istniało.")
                else:
                    raport.append(f"⚠️ Subiekt: {st} — {s.get('Szczegoly')}")
                    messagebox.showwarning("Zapis do Subiekta",
                                           f"Decyzja zapisana w archiwum, ale Subiekt odrzucił powiązanie:\n\n"
                                           f"{s.get('Szczegoly')}", parent=self)
            if w.get("mapowania") is not None:
                raport.append("Mapowania RM: zapisano." if w["mapowania"]
                              else "Mapowania RM: wpis ręczny już istnieje — nie nadpisano.")
            self.status.config(text="   ".join(raport))
            self._raport = "✔ " + "   ".join(raport)
            self._auto_skok = True
            self._dopasuj_biezaca()
            self._przelicz_odznaki()
            self.after(150, self._nastepny_brak)

        self._w_tle(praca, potem)

    def _cofnij_decyzje(self):
        if self._wybrany_lp is None or not self._biezaca:
            return
        if not messagebox.askyesno(
                "Cofnij decyzję",
                "Usunąć zapisaną decyzję dla tej pozycji?\n\n"
                "Powiązanie symbolu w Subiekcie (jeśli powstało) ZOSTAJE — "
                "to osobna rzecz, zmienia się ją w Subiekcie.", parent=self):
            return
        ksef, lp = self._biezaca, self._wybrany_lp
        try:
            self.arch._pisz("ksef-decyzja-zapisz", {"decyzja": None, "ksef_number": ksef, "nr_wiersza": lp})
        except Exception as e:
            messagebox.showerror("Cofnij decyzję", str(e), parent=self)
            return
        for p in self._pozycje:
            if p.nr_wiersza == lp:
                p.decyzja = None
        self.status.config(text=f"Lp. {lp}: decyzja cofnięta.")
        self._dopasuj_biezaca()
        self._przelicz_odznaki()
        self._wybrano_pozycje()

    def _nastepny_brak(self):
        """Przeskok do następnej pozycji bez decyzji — żeby lecieć fakturą po kolei."""
        if not self._dop:
            return
        start = 0
        if self._wybrany_lp is not None:
            for i, d in enumerate(self._dop):
                if d.pozycja.nr_wiersza == self._wybrany_lp:
                    start = i + 1
                    break
        kolejnosc = self._dop[start:] + self._dop[:start]
        for d in kolejnosc:
            if d.status == kk.BRAK_DECYZJI:
                iid = str(d.pozycja.nr_wiersza)
                self.tv_p.selection_set(iid)
                self.tv_p.see(iid)
                return
        self.status.config(text="Ta faktura nie ma już pozycji bez decyzji.")

    # ── nowa kartoteka (nieodwracalne — przez wspólny formularz) ──────────
    def _zaloz_kartoteke(self):
        d = self._dop_dla(self._wybrany_lp) if self._wybrany_lp is not None else None
        if d is None:
            return
        try:
            import subiekt_asortyment
        except ImportError as e:
            messagebox.showerror("Subiekt", f"Brak modułu subiekt_asortyment.py\n\n{e}", parent=self)
            return
        p = d.pozycja
        symbol = (d.identyfikator or p.nazwa)[:64]
        rodzaj = "usluga" if self.var_typ.get() == "usluga" else "towar"

        def po_zapisie(w):
            # Formularz założył kartotekę — dociągamy świeżą kartotekę z mostu,
            # wskazujemy nową pozycję i zapisujemy decyzję (+ powiązanie symbolu).
            sym = (w.get("symbol") or symbol).strip()

            def praca():
                import subiekt_scalanie
                return subiekt_scalanie.wczytaj_katalog_subiekta(max_wiek_h=0)

            def potem(kat, blad):
                if kat:
                    self._ustaw_katalog(kat)
                k = next((x for x in self.katalog_sub
                          if (x.get("symbol") or "").strip().upper() == sym.upper()), None)
                if not k:
                    self.status.config(text=f"Kartoteka {sym} założona, ale nie widzę jej jeszcze w kartotece — "
                                            f"kliknij „Dopasuj ponownie”.")
                    return
                self._ustaw_kartoteke(k, zrodlo="ręcznie")
                self._zapisz_decyzje(nowa_kartoteka=True)
            self._w_tle(praca, potem)

        subiekt_asortyment.okno_nowa_kartoteka(
            self, symbol=symbol, nazwa=kk.proponowana_nazwa(p), rodzaj=rodzaj, po_zapisie=po_zapisie)

    # ── pozostałe akcje ────────────────────────────────────────────────────
    def _dopasuj_ponownie(self):
        self._map_rysunki = {}
        self.start_kreciolek("Odświeżam kartotekę i powiązania z Subiekta")
        self._w_tle(self._tlo_praca, self._tlo_gotowe)

    def _odswiez_wszystko(self):
        self._odswiez_liste()
        self._w_tle(lambda: self.arch._czytaj("ksef-pozycje-wszystkie"), self._pozycje_gotowe)
        if self._biezaca:
            self._pokaz_fakture(self._biezaca)

    def _eksport_csv(self):
        if not self._dop:
            return
        numer = _bezpieczna_nazwa(self.lbl_numer.cget("text"), 40)
        sciezka = filedialog.asksaveasfilename(
            parent=self, title="Eksport pozycji do CSV", defaultextension=".csv",
            initialfile=f"faktura_{numer}.csv", filetypes=[("CSV", "*.csv")])
        if not sciezka:
            return
        with open(sciezka, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([k[1] for k in KOL_POZYCJE] + ["Wartość netto", "Komentarz"])
            for iid in self.tv_p.get_children():
                d = self._dop_dla(iid)
                w.writerow(list(self.tv_p.item(iid, "values"))
                           + [_zl(d.pozycja.wartosc_netto) if d else "",
                              ((d.pozycja.decyzja or {}).get("komentarz", "") if d else "")])
        self.status.config(text=f"Zapisano {sciezka}")

    def _wczytaj_pliki(self):
        """Import XML-i z dysku — ta sama ścieżka co w archiwum (`wczytaj_plik`)."""
        sciezki = filedialog.askopenfilenames(
            parent=self, title="Wybierz pliki XML faktur (FA(2)/FA(3)) — można zaznaczyć wiele",
            filetypes=[("Faktury XML", "*.xml"), ("Wszystkie pliki", "*.*")])
        if not sciezki:
            return
        dodane, nadpisane, bledy = [], 0, []
        for s in sciezki:
            try:
                _, faktura, nowa = self.arch.wczytaj_plik(s)
            except ValueError as e:
                bledy.append((Path(s).name, f"to nie jest faktura: {e}"))
                continue
            except Exception as e:
                bledy.append((Path(s).name, str(e)))
                continue
            if nowa:
                dodane.append(faktura)
            else:
                nadpisane += 1
        self._odswiez_wszystko()
        tresc = f"Dodano nowych faktur: {len(dodane)}"
        if nadpisane:
            tresc += f"\nByły już w archiwum (odświeżone): {nadpisane}"
        if dodane:
            tresc += "\n\n" + "\n".join(
                f"• {f.numer_faktury or '(bez numeru)'} — {f.sprzedawca_nazwa or '?'} ({len(f.pozycje)} poz.)"
                for f in dodane[:10])
        if bledy:
            tresc += f"\n\nNie udało się wczytać {len(bledy)} plików (patrz konsola)."
            for nazwa, blad in bledy:
                print(f"⚠️  {nazwa}: {blad}")
            messagebox.showwarning("Wczytaj XML", tresc, parent=self)
        else:
            messagebox.showinfo("Wczytaj XML", tresc, parent=self)

    def _pobierz(self):
        nip = re.sub(r"\D", "", self.ksef_cfg.get("nip", ""))
        token = self.ksef_cfg.get("token", "")
        srodowisko = self.ksef_cfg.get("environment", "test")
        if not nip or not token:
            messagebox.showwarning(
                "Brak konfiguracji KSEF",
                "Uzupełnij NIP firmy i token API KSEF w menu\n"
                "'Ustawienia → Ścieżki do baz danych' (sekcja KSEF).", parent=self)
            return
        from tkinter import simpledialog
        dni = simpledialog.askinteger("Pobierz nowe faktury", "Sprawdzić faktury z ilu ostatnich dni?",
                                      initialvalue=30, minvalue=1, maxvalue=730, parent=self)
        if not dni:
            return
        if srodowisko != "production":
            if not messagebox.askyesno(
                    "Środowisko testowe",
                    "KSeF jest ustawiony na środowisko TESTOWE — pobiorą się faktury testowe.\n\n"
                    "Kontynuować mimo to?", parent=self):
                return
        self.btn_pobierz.config(state=tk.DISABLED)
        self.start_kreciolek("Łączę się z KSeF")

        def praca():
            arch = ArchiwumKsef(self.arch.katalog)
            try:
                return pobierz_nowe(arch, nip, token, srodowisko, dni,
                                    lambda t: self._wyniki.put(lambda: self.tekst_kreciolka(t)))
            finally:
                arch.zamknij()

        def potem(w, blad):
            self.stop_kreciolek()
            self.btn_pobierz.config(state=tk.NORMAL)
            if blad:
                self.status.config(text="Błąd pobierania.")
                messagebox.showerror("Pobieranie z KSeF", str(blad), parent=self)
                return
            nowe, pominiete, bledy = w
            self._odswiez_wszystko()
            self.status.config(text=f"Pobrano {len(nowe)} nowych faktur ({pominiete} już było).")
            tresc = f"Nowych faktur: {len(nowe)}\nJuż w archiwum (pominięto): {pominiete}"
            if bledy:
                tresc += f"\nBłędy: {len(bledy)} (patrz konsola)"
                for numer, b in bledy:
                    print(f"⚠️  {numer}: {b}")
            messagebox.showinfo("Pobieranie z KSeF", tresc, parent=self)

        self._w_tle(praca, potem)

    def _zamknij(self):
        try:
            self.arch.zamknij()
        except Exception:
            pass
        self.destroy()


# ── drobne ──────────────────────────────────────────────────────────────────
def _data_pl(iso):
    if not iso or len(iso) < 10:
        return iso or ""
    return f"{iso[8:10]}.{iso[5:7]}.{iso[0:4]}"


def _ilosc(x):
    if x is None:
        return ""
    try:
        return f"{x:g}" if float(x) != int(float(x)) else str(int(float(x)))
    except (TypeError, ValueError):
        return str(x)


def open_window(parent, katalog, ksef_cfg=None):
    return OknoFaktury(parent, katalog, ksef_cfg)
