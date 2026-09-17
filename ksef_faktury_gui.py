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
from subiekt_stany import wysrodkuj, podepnij_szerokosci

try:
    from tksheet import Sheet
except ImportError:
    Sheet = None

# ── paleta: TA SAMA co w „Dokumenty w Subiekcie" (subiekt_dokumenty_gui) ────
#: Okna zakładki SUBIEKT mają wyglądać jak jeden program, a nie jak zbiór
#: osobnych narzędzi — stąd te same kolory, ten sam granatowy pasek tytułu,
#: te same małe przyciski i ta sama stopka. Zmiana tutaj = rozjazd z resztą.
GRANAT = "#34495e"          # pasek tytułu, pasek panelu, stopka
GRANAT_CIEMNY = "#2c3e50"   # selectcolor checkbuttonów na granacie, tekst
SZARY = "#ecf0f1"           # pasek filtrów, podsumowanie, legenda
TEKST = "#2c3e50"
TEKST_SZARY = "#7f8c8d"
NIEBIESKI = "#3498db"       # Odśwież
ZIELONY = "#27ae60"         # akcja tworząca (nowa kartoteka)
GRANAT_AKCJA = "#2980b9"    # akcja główna (zapis decyzji)
SZAROSC_AKCJA = "#95a5a6"   # akcja drugorzędna
STAL = "#7f8c8d"            # akcja trzeciorzędna
CZERWONY = "#c0392b"

# ── wygląd statusów ─────────────────────────────────────────────────────────
#: status → (etykieta, tło wiersza, kolor tekstu). Odcienie z rodziny
#: „Dokumentów": pastelowe tła z legendy, nie własna paleta.
STATUSY = {
    kk.KARTOTEKA:        ("✔ KARTOTEKA",        "#d5f0dd", "#1e7e34"),
    kk.NOWA_KARTOTEKA:   ("✔ NOWA KARTOTEKA",   "#d5f0dd", "#1e7e34"),
    kk.RYSUNEK_RM:       ("📐 RYSUNEK RM",      "#d6eaf8", "#1f5fa8"),
    kk.POZYCJA_ZBIORCZA: ("◫ POZYCJA ZBIORCZA", "#f4ecf7", "#6c3fb5"),
    kk.USLUGA:           ("— USŁUGA",           "#eaecee", "#566573"),
    kk.BRAK_DECYZJI:     ("! BRAK DECYZJI",     "#fdebd0", "#a04000"),
}

#: Cztery typy pozycji do wyboru w panelu decyzji. To pytanie brzmi „czym
#: to jest", NIE „załóż kartotekę" — przy części pozycji kartoteka jest złym
#: pytaniem (usługa, pozycja zbiorcza alu-frost, detal z naszego rysunku).
#: Kolory = tła statusów, żeby wybór typu i kolor wiersza znaczyły to samo.
#:
#: Skróty TW / US wg nomenklatury z reszty okien (`subiekt_edytor_gui.SKROT`,
#: `subiekt_asortyment_gui.KODY_RODZAJU`): TW = towar, KT = komplet, US =
#: usługa. ZB i RM są WŁASNE — pozycja zbiorcza i detal z naszego rysunku nie
#: mają odpowiednika wśród rodzajów kartotek Subiekta, bo to nie są rodzaje
#: kartoteki, tylko odpowiedzi na pytanie „czym jest ta linia faktury".
#: Kompletu (KT) tu nie ma świadomie: faktura dostawcy nie dostarcza złożeń.
TYPY = [
    ("towar",    "TW",  "Towar handlowy",          "z kartoteki dostawcy",       "#d5f0dd"),
    ("usluga",   "US",  "Usługa",                  "nie wchodzi na stan",        "#eaecee"),
    ("zbiorcza", "ZB",  "Pozycja zbiorcza",        "jedna linia = wiele detali", "#f4ecf7"),
    ("rysunek",  "RM",  "Detal z naszego rysunku", "numer rysunku RM, projekt",  "#d6eaf8"),
]
#: klucz typu → skrót do kolumny „Typ" w tabeli pozycji.
SKROT_TYPU = {t[0]: t[1] for t in TYPY}

#: Odznaki faktur w drzewie. „Rozstrzygnięta" celowo zamiast „Rozliczona"
#: z makiety — rozliczenie to osobny etap (FZ w Subiekcie), którego to okno
#: nie robi. Nie obiecujemy więcej, niż wiemy.
ODZNAKI = {
    "nowa":   ("Nowa",           "#d6eaf8"),
    "wtoku":  ("W toku",         "#fdebd0"),
    "gotowa": ("Rozstrzygnięta", "#d5f0dd"),
    "pusta":  ("Bez pozycji",    "#eaecee"),
}

#: (klucz, nagłówek, szerokość) — ten sam format co `KOL_DOK` w oknie
#: dokumentów, bo szerokości zapamiętuje ten sam `podepnij_szerokosci`.
#: Numer rysunku nie ma własnej kolumny: dla detalu z rysunku identyfikatorem
#: JEST numer rysunku, a panel decyzji pokazuje go osobno.
#: ⚠️ „Nazwa / opis" występuje DWA razy i to celowo:
#:   * kolumna 3  — opis z FAKTURY (co napisał dostawca),
#:   * kolumna 9  — nazwa KARTOTEKI z Subiekta (co mamy u siebie).
#: Zestawienie ich obok siebie jest sednem tego okna: widać, czy wskazana
#: kartoteka faktycznie odpowiada temu, co jest na fakturze.
KOL_POZYCJE = [
    ("lp", "Lp.", 40), ("ident", "Identyfikator", 150),
    ("typ", "Typ", 70), ("nazwa", "Nazwa / opis", 200),
    ("ilosc", "Ilość", 60), ("jm", "J.m.", 50),
    ("cena", "Cena netto", 85), ("wz", "Numer wydania", 105),
    ("kartoteka", "Kartoteka", 140), ("nazwa_kart", "Nazwa kartoteki", 190),
    # „Opis" to pole z KARTOTEKI (wymiary, gatunek, norma) — ta sama kolumna
    # i ten sam powód co w oknie dokumentów: sama nazwa bywa za krótka, żeby
    # rozpoznać detal.
    ("opis_kart", "Opis kartoteki", 160),
    ("projekty", "Projekty", 90), ("status", "Status", 150),
]
#: Indeksy kolumn używane przy kolorowaniu — trzymane obok definicji, żeby
#: dołożenie kolumny nie wymagało szukania magicznych liczb w kodzie.
K_LP = 0
K_TYP = 2
K_KARTOTEKA = 8
K_STATUS = len(KOL_POZYCJE) - 1

#: Lista faktur — drzewo (grupowanie po dacie), więc zostaje ttk.Treeview.
KOL_FAKTURY = [("dostawca", "Dostawca", 130), ("netto", "Netto", 80),
               ("stan", "Stan", 110)]

#: Filtr dostawcy w pasku — ta sama konwencja napisu co w oknie dokumentów
#: (`PROJ_WSZYSTKIE`).
DOST_WSZYSCY = "— wszyscy —"

FONT = ("Arial", 9)
FONT_S = ("Arial", 8)
FONT_B = ("Arial", 9, "bold")
FONT_TYTUL = ("Arial", 14, "bold")


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
    """Skrót typu do kolumny „Typ" — TW / US / ZB / RM (nomenklatura okien)."""
    return SKROT_TYPU[_typ_z_dopasowania(d)]


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
        self.title("Faktury z KSeF — pozycje, kartoteki, decyzje")
        self.geometry("1450x860")
        self.minsize(1100, 650)
        # Jak w oknie dokumentów: startujemy zmaksymalizowani, bo tabela
        # pozycji ma jedenaście kolumn i w oknie 1100 px nie widać Statusu.
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

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
        self._widoczne = []            # podzbiór `_dop` pokazany w arkuszu
        self.filtr_pozycji = None
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
        self._pasek_tytulu()
        self._pasek_filtrow()
        self._legenda()

        # Dwa panele OBOK SIEBIE — jak w „Dokumentach": lista po lewej,
        # szczegóły po prawej. Faktur bywa kilkadziesiąt, a pozycji w jednej
        # ponad pięćdziesiąt, więc dzielenie wysokości dusiłoby obie tabele.
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 4))

        lewy = tk.Frame(paned)
        prawy = tk.Frame(paned)
        paned.add(lewy, weight=2)
        paned.add(prawy, weight=7)

        self._panel_faktur(lewy)

        # Po prawej: nagłówek faktury + zakładki, a pod nimi panel decyzji.
        pion = ttk.PanedWindow(prawy, orient=tk.VERTICAL)
        pion.pack(fill=tk.BOTH, expand=True)
        gora = tk.Frame(pion)
        dol = tk.Frame(pion)
        pion.add(gora, weight=5)
        pion.add(dol, weight=3)
        self._naglowek_faktury(gora)
        self._zakladki(gora)
        self._panel_decyzji(dol)

        self._pasek_stanu()

    def _pasek_tytulu(self):
        """Granatowy pasek z tytułem i akcjami — wzorzec z okna dokumentów."""
        top = tk.Frame(self, bg=GRANAT, height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🧾 Faktury z KSeF — pozycje, kartoteki, decyzje",
                 bg=GRANAT, fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)
        # Stan mostu w miejscu, gdzie „Dokumenty" pokazują wiek odczytu —
        # tu ważniejsze jest, czy w ogóle mamy kartotekę i powiązania.
        self.lbl_most = tk.Label(top, text="most: sprawdzam…", bg=GRANAT,
                                 fg="#f5b041", font=("Arial", 9, "bold"))
        self.lbl_most.pack(side=tk.LEFT, padx=(16, 0))

        def akcja(tekst, cmd, kolor, pad=(0, 4)):
            b = tk.Button(top, text=tekst, command=cmd, bg=kolor, fg="white",
                          font=FONT_S, padx=8, pady=2, relief=tk.RAISED, bd=1,
                          cursor="hand2")
            b.pack(side=tk.RIGHT, padx=pad, pady=8)
            return b

        self.btn_odswiez = akcja("🔄 Odśwież", self._odswiez_wszystko, NIEBIESKI, (0, 10))
        self.btn_pobierz = akcja("☁ Pobierz nowe z KSeF", self._pobierz, GRANAT_AKCJA)
        akcja("📂 Wczytaj XML z dysku", self._wczytaj_pliki, ZIELONY)

    def _pasek_filtrow(self):
        f = tk.Frame(self, bg=SZARY)
        f.pack(side=tk.TOP, fill=tk.X)
        tk.Label(f, text="Szukaj:", bg=SZARY, font=FONT).pack(side=tk.LEFT, padx=(12, 3), pady=6)
        self.var_szukaj = tk.StringVar()
        e = tk.Entry(f, textvariable=self.var_szukaj, width=26, font=FONT)
        e.pack(side=tk.LEFT, pady=6)
        e.bind("<KeyRelease>", self._szukaj_opoznione)
        e.bind("<Return>", lambda _e: self._odswiez_liste())
        tk.Label(f, text="(numer faktury, dostawca, NIP, nazwa pozycji)", bg=SZARY,
                 fg=TEKST_SZARY, font=FONT_S).pack(side=tk.LEFT, padx=(4, 0))

        tk.Label(f, text="Dostawca:", bg=SZARY, font=FONT).pack(side=tk.LEFT, padx=(14, 3), pady=6)
        self.var_dostawca = tk.StringVar(value=DOST_WSZYSCY)
        self.cmb_dost = ttk.Combobox(f, textvariable=self.var_dostawca, width=22,
                                     state="readonly", font=FONT, values=[DOST_WSZYSCY])
        self.cmb_dost.pack(side=tk.LEFT, pady=6)
        self.cmb_dost.bind("<<ComboboxSelected>>", lambda _e: self._wypelnij_drzewo())

        self.var_tylko_braki = tk.IntVar(value=0)
        tk.Checkbutton(f, text="tylko z brakami decyzji", variable=self.var_tylko_braki,
                       command=self._wypelnij_drzewo, bg=SZARY, font=FONT_S,
                       activebackground=SZARY).pack(side=tk.LEFT, padx=(12, 0), pady=6)

        tk.Button(f, text="🗑️", command=self._wyczysc_filtry, bg=SZAROSC_AKCJA, fg="white",
                  font=("Arial", 11, "bold"), width=3, relief=tk.RAISED, bd=2,
                  cursor="hand2").pack(side=tk.LEFT, padx=(10, 2), pady=4)

        # Akcje dotyczące WYBRANEJ faktury — po prawej, jak w „Dokumentach".
        tk.Button(f, text="📄 Eksport do CSV", command=self._eksport_csv, bg=STAL, fg="white",
                  font=FONT_S, padx=8, pady=2, relief=tk.RAISED, bd=1,
                  cursor="hand2").pack(side=tk.RIGHT, padx=(0, 12), pady=4)
        tk.Button(f, text="⏭ Następny brak", command=self._nastepny_brak, bg=SZAROSC_AKCJA,
                  fg="white", font=FONT_S, padx=8, pady=2, relief=tk.RAISED, bd=1,
                  cursor="hand2").pack(side=tk.RIGHT, padx=(0, 4), pady=4)
        self.btn_dopasuj = tk.Button(f, text="🔎 Dopasuj ponownie", command=self._dopasuj_ponownie,
                                     bg=GRANAT_AKCJA, fg="white", font=FONT_S, padx=8, pady=2,
                                     relief=tk.RAISED, bd=1, cursor="hand2")
        self.btn_dopasuj.pack(side=tk.RIGHT, padx=(0, 4), pady=4)

        self.summary = tk.Label(self, text="Wczytywanie…", bg=SZARY, fg=TEKST,
                                font=FONT, anchor="w", padx=12, pady=6)
        self.summary.pack(side=tk.TOP, fill=tk.X)

    def _legenda(self):
        """Kolory statusów — próbka obok znaczenia, jak w oknie dokumentów.

        ⚠️ Wartości MUSZĄ się zgadzać ze słownikiem `STATUSY` — inaczej
        legenda kłamie.
        """
        leg = tk.Frame(self, bg=SZARY)
        leg.pack(side=tk.TOP, fill=tk.X)
        tk.Label(leg, text="Legenda:", bg=SZARY, fg=TEKST_SZARY,
                 font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=(12, 6), pady=(0, 5))
        for status, opis in ((kk.KARTOTEKA, "kartoteka wskazana"),
                             (kk.RYSUNEK_RM, "detal z naszego rysunku"),
                             (kk.POZYCJA_ZBIORCZA, "pozycja zbiorcza — nie na PZ"),
                             (kk.USLUGA, "usługa — nie wchodzi na stan"),
                             (kk.BRAK_DECYZJI, "brak decyzji — blokuje PZ")):
            tk.Label(leg, text="  ", bg=STATUSY[status][1], relief=tk.SOLID, bd=1).pack(
                side=tk.LEFT, padx=(6, 3), pady=(0, 5))
            tk.Label(leg, text=opis, bg=SZARY, fg=TEKST, font=FONT_S).pack(
                side=tk.LEFT, pady=(0, 5))
        tk.Label(leg, text="✎ = zapisana decyzja człowieka (wygrywa z automatem)",
                 bg=SZARY, fg=TEKST_SZARY, font=FONT_S).pack(side=tk.LEFT, padx=(16, 0), pady=(0, 5))

    def _panel_faktur(self, r):
        pasek = tk.Frame(r, bg=GRANAT)
        pasek.pack(side=tk.TOP, fill=tk.X)
        tk.Label(pasek, text="Faktury w archiwum", bg=GRANAT, fg="white",
                 font=("Arial", 9, "bold"), anchor="w", padx=10, pady=4).pack(
            side=tk.LEFT, fill=tk.X, expand=True)

        wrap = tk.Frame(r)
        wrap.pack(fill=tk.BOTH, expand=True)
        self.tv_f = ttk.Treeview(wrap, columns=[k[0] for k in KOL_FAKTURY],
                                 show="tree headings", selectmode="browse")
        self.tv_f.heading("#0", text="Data / numer")
        self.tv_f.column("#0", width=150, minwidth=110)
        for klucz, naglowek, szer in KOL_FAKTURY:
            self.tv_f.heading(klucz, text=naglowek)
            self.tv_f.column(klucz, width=szer, minwidth=60,
                             anchor="e" if klucz == "netto" else "w")
        sc = ttk.Scrollbar(wrap, orient="vertical", command=self.tv_f.yview)
        self.tv_f.configure(yscrollcommand=sc.set)
        self.tv_f.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        for klucz, (_, tlo) in ODZNAKI.items():
            self.tv_f.tag_configure(klucz, background=tlo)
        self.tv_f.tag_configure("data", font=FONT_B, background=SZARY)
        self.tv_f.bind("<<TreeviewSelect>>", self._wybrano_fakture)

    def _naglowek_faktury(self, r):
        n = tk.Frame(r, bg="white", highlightthickness=1, highlightbackground="#bdc3c7")
        n.pack(fill=tk.X, pady=(0, 4))
        # ⚠️ Bez wag na kolumnach z wartościami. Gdy treść jest szersza niż
        # ramka, grid ODBIERA miejsce kolumnom z wagą — lewa kolumna wartości
        # zapadała się do zera i „Data wystawienia" stała pusta obok „Numery
        # WZ" (zrzut z testu 17.09.2026). Nadmiar bierze pusta kolumna 5.
        n.columnconfigure(5, weight=1)

        tyt = tk.Frame(n, bg="white")
        tyt.grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(8, 2))
        self.lbl_numer = tk.Label(tyt, text="— wybierz fakturę —", bg="white",
                                  fg=TEKST, font=FONT_TYTUL)
        self.lbl_numer.pack(side=tk.LEFT)
        self.lbl_odznaka = tk.Label(tyt, text="", bg="white", fg=TEKST,
                                    font=("Arial", 8, "bold"), padx=8, pady=2,
                                    relief=tk.SOLID, bd=1)
        self.lbl_odznaka.pack(side=tk.LEFT, padx=(12, 0))
        self.lbl_zrodlo = tk.Label(tyt, text="", bg="white", fg=TEKST_SZARY, font=FONT_S)
        self.lbl_zrodlo.pack(side=tk.LEFT, padx=(8, 0))

        self._pola_nagl = {}

        def pole(wiersz, kol, etykieta, klucz, przycisk=None):
            tk.Label(n, text=etykieta, bg="white", fg=TEKST_SZARY, font=FONT_S,
                     anchor="w").grid(row=wiersz, column=kol, sticky="w", padx=(12, 6), pady=1)
            f = tk.Frame(n, bg="white")
            f.grid(row=wiersz, column=kol + 1, sticky="w", pady=1)
            l = tk.Label(f, text="", bg="white", fg=TEKST, font=FONT_B, anchor="w")
            l.pack(side=tk.LEFT)
            self._pola_nagl[klucz] = l
            if przycisk:
                tk.Button(f, text=przycisk[0], command=przycisk[1], font=FONT_S,
                          bg=SZARY, fg=TEKST, relief=tk.RAISED, bd=1, cursor="hand2",
                          padx=6).pack(side=tk.LEFT, padx=(8, 0))

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
        strony = tk.Frame(n, bg="white")
        strony.grid(row=0, column=4, rowspan=5, sticky="ne", padx=12, pady=(8, 6))
        self._strony = {}
        for i, (klucz, tytul) in enumerate((("podmiot1", "Dostawca (Podmiot1)"),
                                            ("podmiot2", "Nabywca (Podmiot2)"))):
            b = tk.Frame(strony, bg="white")
            b.grid(row=i, column=0, sticky="nw", pady=(0, 4))
            tk.Label(b, text=tytul, bg="white", fg=TEKST_SZARY, font=("Arial", 8, "bold"),
                     anchor="w").pack(fill=tk.X)
            l = tk.Label(b, text="", bg="white", fg=TEKST, font=FONT_S,
                         anchor="w", justify="left", wraplength=320)
            l.pack(fill=tk.X)
            self._strony[klucz] = l

    def _zakladki(self, r):
        self.nb = ttk.Notebook(r)
        self.nb.pack(fill=tk.BOTH, expand=True)

        # ── Pozycje ──
        poz = tk.Frame(self.nb)
        self.nb.add(poz, text="Pozycje")

        pasek = tk.Frame(poz, bg=GRANAT)
        pasek.pack(side=tk.TOP, fill=tk.X)
        self.lbl_poz = tk.Label(pasek, text="Pozycje — kliknij wiersz, żeby zdecydować",
                                bg=GRANAT, fg="white", font=("Arial", 9, "bold"),
                                anchor="w", padx=10, pady=4)
        self.lbl_poz.pack(side=tk.LEFT, fill=tk.X, expand=True)
        # Liczniki są FILTRAMI — klik pokazuje tylko pozycje danego rodzaju,
        # drugi klik wraca do wszystkich. Wcześniej wyglądały jak filtry,
        # ale nic nie robiły (zgłoszone 17.09.2026).
        self._chipy = {}
        self.filtr_pozycji = None
        for klucz, etykieta, kolor in (("brak", "Brak decyzji", "#f5b041"),
                                       ("uslugi", "Usługi", "#d5dbdb"),
                                       ("zbiorcze", "Zbiorcze", "#d7bde2"),
                                       ("rysunki", "Rysunek RM", "#aed6f1"),
                                       ("kartoteka", "Kartoteka", "#a9dfbf"),
                                       ("razem", "Pozycji", "white")):
            l = tk.Label(pasek, text=f"{etykieta}: –", bg=GRANAT, fg=kolor, font=FONT_B,
                         cursor="hand2", padx=6, pady=2)
            l.pack(side=tk.RIGHT, padx=(4, 0), pady=3)
            l.bind("<Button-1>", lambda _e, k=klucz: self._filtruj_pozycje(k))
            self._chipy[klucz] = l
        tk.Label(pasek, text="filtr:", bg=GRANAT, fg="#95a5a6", font=FONT_S).pack(
            side=tk.RIGHT, padx=(10, 2))

        if Sheet is None:
            tk.Label(poz, text="Brak biblioteki tksheet", fg=CZERWONY).pack(pady=20)
            self.sheet = None
            return
        self.sheet = Sheet(poz, headers=[k[1] for k in KOL_POZYCJE],
                           column_width=120, theme="light blue")
        self.sheet.set_options(show_selected_cells_border=True,
                               enable_edit_cell_auto_resize=False,
                               empty_horizontal=0, empty_vertical=0)
        self.sheet.enable_bindings((
            "single_select", "drag_select", "ctrl_select", "select_all",
            "column_width_resize", "arrowkeys", "right_click_popup_menu",
            "rc_select", "copy",
        ))
        podepnij_szerokosci(self, self.sheet, "ksef_faktury_pozycje",
                            [k[2] for k in KOL_POZYCJE])
        self.sheet.bind("<ButtonRelease-1>", self._wybrano_pozycje, add="+")
        self.sheet.bind("<Double-Button-1>", lambda _e: self.ent_kart.focus_set(), add="+")
        self.sheet.pack(fill=tk.BOTH, expand=True)

        # ── Dodatkowe informacje ──
        info = tk.Frame(self.nb)
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
        x = tk.Frame(self.nb)
        self.nb.add(x, text="Plik XML")
        px = tk.Frame(x, bg=SZARY)
        px.pack(fill=tk.X)
        tk.Button(px, text="📂 Otwórz w programie systemowym", command=self._otworz_xml,
                  bg=STAL, fg="white", font=FONT_S, padx=8, pady=2, relief=tk.RAISED,
                  bd=1, cursor="hand2").pack(side=tk.LEFT, padx=8, pady=4)
        self.lbl_plik = tk.Label(px, text="", bg=SZARY, fg=TEKST_SZARY, font=FONT_S)
        self.lbl_plik.pack(side=tk.LEFT, padx=8)
        self.txt_xml = tk.Text(x, font=("Consolas", 9), wrap="none", bg="white",
                               relief=tk.FLAT, padx=8, pady=6)
        scy = ttk.Scrollbar(x, orient="vertical", command=self.txt_xml.yview)
        self.txt_xml.configure(yscrollcommand=scy.set, state=tk.DISABLED)
        self.txt_xml.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scy.pack(side=tk.RIGHT, fill=tk.Y)

    def _panel_decyzji(self, r):
        pasek = tk.Frame(r, bg=GRANAT)
        pasek.pack(side=tk.TOP, fill=tk.X)
        self.lbl_decyzja_tytul = tk.Label(pasek, text="Decyzja — wybierz pozycję",
                                          bg=GRANAT, fg="white", font=("Arial", 9, "bold"),
                                          anchor="w", padx=10, pady=4)
        self.lbl_decyzja_tytul.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.var_potwierdzaj = tk.BooleanVar(value=True)
        tk.Checkbutton(pasek, text="pytaj przed zapisem do Subiekta",
                       variable=self.var_potwierdzaj, bg=GRANAT, fg="white",
                       selectcolor=GRANAT_CIEMNY, activebackground=GRANAT,
                       activeforeground="white", font=FONT_S).pack(side=tk.RIGHT, padx=(6, 10))

        body = tk.Frame(r, bg="white")
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)

        # typ pozycji — cztery „karty"
        typy = tk.Frame(body, bg="white")
        typy.grid(row=0, column=0, sticky="nw", padx=(12, 14), pady=8)
        tk.Label(typy, text="Czym jest ta pozycja?", bg="white", fg=TEKST,
                 font=FONT_B, anchor="w").pack(fill=tk.X, pady=(0, 4))
        self.var_typ = tk.StringVar(value="towar")
        self._radio_typ = {}
        for klucz, skrot, tytul, opis, kolor in TYPY:
            rb = tk.Radiobutton(typy, text=f"{skrot}  —  {tytul}\n{opis}", value=klucz,
                                variable=self.var_typ, indicatoron=0, justify="left",
                                anchor="w", bg="white", selectcolor=kolor, relief=tk.RAISED,
                                bd=1, padx=10, pady=4, font=FONT_S, width=26,
                                command=self._zmiana_typu, cursor="hand2")
            rb.pack(fill=tk.X, pady=2)
            self._radio_typ[klucz] = rb

        # pola
        pola = tk.Frame(body, bg="white")
        pola.grid(row=0, column=1, sticky="nsew", padx=(0, 14), pady=8)
        pola.columnconfigure(1, weight=1)

        def wiersz(i, etykieta):
            tk.Label(pola, text=etykieta, bg="white", fg=TEKST_SZARY, font=FONT_S,
                     anchor="w").grid(row=i, column=0, sticky="w", padx=(0, 8), pady=3)

        wiersz(0, "Identyfikator z faktury")
        self.var_ident = tk.StringVar()
        tk.Entry(pola, textvariable=self.var_ident, font=FONT, state="readonly",
                 readonlybackground=SZARY, relief=tk.SOLID, bd=1
                 ).grid(row=0, column=1, sticky="ew", pady=3)
        wiersz(1, "Źródło identyfikatora")
        self.lbl_zrodlo_id = tk.Label(pola, text="", bg="white", fg=TEKST, font=FONT_S, anchor="w")
        self.lbl_zrodlo_id.grid(row=1, column=1, sticky="w", pady=3)
        wiersz(2, "Numer rysunku RM")
        self.var_rysunek = tk.StringVar()
        self.ent_rysunek = tk.Entry(pola, textvariable=self.var_rysunek, font=FONT,
                                    relief=tk.SOLID, bd=1)
        self.ent_rysunek.grid(row=2, column=1, sticky="ew", pady=3)
        self.ent_rysunek.bind("<KeyRelease>", lambda _e: self._odswiez_projekty())
        wiersz(3, "Projekt (z BOM-ów)")
        self.var_projekt = tk.StringVar()
        self.cb_projekt = ttk.Combobox(pola, textvariable=self.var_projekt, font=FONT,
                                       state="readonly")
        self.cb_projekt.grid(row=3, column=1, sticky="ew", pady=3)
        wiersz(4, "Komentarz")
        self.var_komentarz = tk.StringVar()
        tk.Entry(pola, textvariable=self.var_komentarz, font=FONT, relief=tk.SOLID, bd=1
                 ).grid(row=4, column=1, sticky="ew", pady=3)

        # kartoteka — wyszukiwarka
        kart = tk.Frame(body, bg="white")
        kart.grid(row=0, column=2, sticky="nsew", padx=(0, 14), pady=8)
        kart.columnconfigure(0, weight=1)
        kart.rowconfigure(2, weight=1)
        tk.Label(kart, text="Kartoteka w Subiekcie", bg="white", fg=TEKST_SZARY,
                 font=FONT_S, anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 3))
        sz = tk.Frame(kart, bg="white")
        sz.grid(row=1, column=0, sticky="ew")
        sz.columnconfigure(0, weight=1)
        self.var_kart = tk.StringVar()
        self.ent_kart = tk.Entry(sz, textvariable=self.var_kart, font=FONT,
                                 relief=tk.SOLID, bd=1)
        self.ent_kart.grid(row=0, column=0, sticky="ew")
        self.ent_kart.bind("<KeyRelease>", lambda _e: self._szukaj_kartoteki())
        self.ent_kart.bind("<Return>", lambda _e: self._wybierz_pierwsza())
        self.ent_kart.bind("<Down>", lambda _e: self.lb_kart.focus_set())
        tk.Button(sz, text="✕", command=self._wyczysc_kartoteke, font=FONT_S,
                  bg=SZARY, fg=TEKST, relief=tk.RAISED, bd=1, cursor="hand2", padx=6
                  ).grid(row=0, column=1, padx=(4, 0))
        self.lb_kart = tk.Listbox(kart, height=5, font=FONT, activestyle="none",
                                  relief=tk.SOLID, bd=1,
                                  selectbackground="#b3d1ec", selectforeground=TEKST)
        self.lb_kart.grid(row=2, column=0, sticky="nsew", pady=(3, 3))
        self.lb_kart.bind("<<ListboxSelect>>", self._wybrano_z_listy)
        self.lb_kart.bind("<Return>", self._wybrano_z_listy)
        self.lb_kart.bind("<Double-1>", self._wybrano_z_listy)
        self.lbl_kart = tk.Label(kart, text="— nie wskazano —", bg=SZARY, fg=TEKST,
                                 font=FONT_S, anchor="w", padx=8, pady=4,
                                 relief=tk.SOLID, bd=1, justify="left")
        self.lbl_kart.grid(row=3, column=0, sticky="ew")
        self._kandydaci_kart = []

        # akcje
        akcje = tk.Frame(body, bg="white")
        akcje.grid(row=0, column=3, sticky="ne", padx=(0, 12), pady=8)
        self.btn_zapisz = tk.Button(akcje, text="✔ Zapisz decyzję", command=self._zapisz_decyzje,
                                    bg=GRANAT_AKCJA, fg="white", disabledforeground="#bdc3c7",
                                    font=FONT_B, padx=12, pady=6, relief=tk.RAISED, bd=1,
                                    cursor="hand2", state=tk.DISABLED)
        self.btn_zapisz.pack(fill=tk.X, pady=(0, 6))
        self.btn_nowa = tk.Button(akcje, text="➕ Załóż nową kartotekę", command=self._zaloz_kartoteke,
                                  bg=ZIELONY, fg="white", disabledforeground="#bdc3c7",
                                  font=FONT_S, padx=10, pady=4, relief=tk.RAISED, bd=1,
                                  cursor="hand2", state=tk.DISABLED)
        self.btn_nowa.pack(fill=tk.X, pady=(0, 6))
        self.btn_wyczysc = tk.Button(akcje, text="↶ Cofnij decyzję", command=self._cofnij_decyzje,
                                     bg=SZAROSC_AKCJA, fg="white", disabledforeground="#d5d8dc",
                                     font=FONT_S, padx=10, pady=4, relief=tk.RAISED, bd=1,
                                     cursor="hand2", state=tk.DISABLED)
        self.btn_wyczysc.pack(fill=tk.X)

        # co zostanie zapisane (PRZED) / co się zapisało (PO)
        self.lbl_plan = tk.Label(r, text="Kliknij pozycję w tabeli.", bg=SZARY, fg=TEKST,
                                 font=FONT_S, anchor="w", justify="left", padx=12, pady=5)
        self.lbl_plan.pack(fill=tk.X, side=tk.BOTTOM)
        for v in (self.var_typ, self.var_rysunek, self.var_projekt, self.var_komentarz):
            v.trace_add("write", lambda *_a: self._odswiez_plan())

    def _pasek_stanu(self):
        self.status = tk.Label(self, text="Wczytywanie…", anchor="w", padx=12, pady=3,
                               bg=GRANAT, fg=SZARY, font=FONT_S)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

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
        # 1. kartoteka z cache — natychmiast, żeby tabela miała z czym pracować.
        #    Cache nie ma `Opis` (zapisuje go `wczytaj_katalog_subiekta` bez
        #    tego pola), więc kolumna „Opis kartoteki" zostaje pusta do czasu
        #    odpowiedzi mostu. Lepsze to niż puste okno przez 10 s.
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
        wynik = {"most": False}
        try:
            subiekt_bridge.zapewnij_most()
            wynik["most"] = True
        except Exception:
            return wynik                          # bez mostu: zostaje cache
        # Katalog czytamy WPROST z mostu, nie przez `wczytaj_katalog_subiekta`:
        # tamta funkcja zwraca tylko {id, symbol, nazwa} i gubi `Opis`, a to
        # osobna kolumna tego okna. Wspólnej funkcji nie ruszamy — używają jej
        # inne okna i jej format jest ich kontraktem.
        dane = subiekt_bridge.call("katalog", {}, timeout=120)
        wynik["katalog"] = [{"id": k.get("Id"),
                             "symbol": (k.get("Symbol") or "").strip(),
                             "nazwa": (k.get("Nazwa") or "").strip(),
                             "opis": (k.get("Opis") or "").strip(),
                             "rodzaj": (k.get("Rodzaj") or "").strip()}
                            for k in (dane or {}).get("pozycje", [])]
        dane = subiekt_bridge.call("symbole-dostawcy", {}, timeout=60)
        wynik["powiazania"] = (dane or {}).get("powiazania", [])
        k = subiekt_bridge.call("kontrahenci", {}, timeout=60)
        wynik["kontrahenci"] = (k or {}).get("kontrahenci", [])
        return wynik

    def _tlo_gotowe(self, w, blad):
        self.stop_kreciolek()
        if blad or not w:
            self.most_ok = False
            self.lbl_most.config(text="⚠ most niedostępny — kartoteka z cache", fg="#f5b041")
            self.status.config(text=f"Most niedostępny: {blad}" if blad else "Most niedostępny.")
            self._przelicz_odznaki()
            return
        self.most_ok = w.get("most", False)
        if not self.most_ok:
            self.lbl_most.config(text="⚠ most niedostępny — kartoteka z cache", fg="#f5b041")
        else:
            # Jasna zieleń, nie #1e7e34 — ciemny zielony na granacie jest
            # nieczytelny (zrzut z 17.09.2026).
            self.lbl_most.config(text="most: ONLINE", fg="#a9dfbf")
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
            if self._wybrany_lp is not None and self._wiersz_lp(self._wybrany_lp) is not None:
                self._zaznacz_wiersz(self._wybrany_lp)
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

        dostawca = self.var_dostawca.get()
        tylko_braki = bool(self.var_tylko_braki.get())
        widoczne, po_dacie = 0, {}
        for f in self.faktury:
            ksef, data, numer, sprzedawca, nip = f[0], f[1], f[2], f[3], f[4]
            if dostawca != DOST_WSZYSCY and (sprzedawca or nip or "") != dostawca:
                continue
            if tylko_braki and not (self.stan_faktur.get(ksef) or {}).get("brak"):
                continue
            po_dacie.setdefault(data or "bez daty", []).append(f)
            widoczne += 1

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

        # Lista dostawców do filtra — z tego, co realnie jest w archiwum.
        dostawcy = sorted({(f[3] or f[4] or "") for f in self.faktury if (f[3] or f[4])})
        self.cmb_dost["values"] = [DOST_WSZYSCY] + dostawcy
        if dostawca != DOST_WSZYSCY and dostawca not in dostawcy:
            self.var_dostawca.set(DOST_WSZYSCY)

        # Podsumowanie w pasku — jak „Dokumentów: 63 z 63" w oknie dokumentów.
        braki = sum(1 for f in self.faktury if (self.stan_faktur.get(f[0]) or {}).get("brak"))
        poz = sum((self.stan_faktur.get(f[0]) or {}).get("razem", 0) for f in self.faktury)
        licz = {}
        for f in self.faktury:
            odz = (self.stan_faktur.get(f[0]) or {}).get("odznaka", "nowa")
            licz[odz] = licz.get(odz, 0) + 1
        self.summary.config(text=(
            f"Faktur: {widoczne} z {len(self.faktury)}    "
            + "   ".join(f"{ODZNAKI[k][0]}: {licz.get(k, 0)}"
                         for k in ("nowa", "wtoku", "gotowa") if licz.get(k))
            + f"    pozycji łącznie: {poz}"
            + (f"    ⚠ z brakami decyzji: {braki}" if braki else "")))

        if zaznaczona and self.tv_f.exists(zaznaczona):
            self.tv_f.selection_set(zaznaczona)
            self.tv_f.see(zaznaczona)

    def _wyczysc_filtry(self):
        """Zeruje wyszukiwarkę i filtry — ta sama ikona i zachowanie co w arkuszu."""
        self.var_szukaj.set("")
        self.var_dostawca.set(DOST_WSZYSCY)
        self.var_tylko_braki.set(0)
        self._odswiez_liste()

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
        """Odznaka przy numerze faktury — pastel z legendy + ciemny tekst.

        Te same kolory co wiersze w drzewie, żeby odznaka i lista mówiły
        to samo; wcześniej były to dwie różne palety.
        """
        stan = self.stan_faktur.get(ksef)
        odz = stan["odznaka"] if stan else "nowa"
        etykieta, tlo = ODZNAKI[odz]
        fg = {"nowa": "#1f5fa8", "wtoku": "#a04000",
              "gotowa": "#1e7e34", "pusta": "#566573"}[odz]
        if stan and stan.get("brak"):
            etykieta += f" — {stan['brak']} bez decyzji"
        self.lbl_odznaka.config(text=etykieta, bg=tlo, fg=fg)

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
        """Tabela pozycji w tksheet — jak arkusze w oknie dokumentów.

        Kolor niesie KOLUMNA STATUS, nie cały wiersz: przy jedenastu kolumnach
        pełne tło dawało pasiastą ścianę, w której nie dało się czytać nazw.
        Tam, gdzie kolor znaczy coś jeszcze (kandydat po normalizacji, zapisana
        decyzja), podświetlamy tę konkretną komórkę.
        """
        if self.sheet is None:
            return
        zaznacz = self._wybrany_lp
        # `_widoczne` to podzbiór `_dop` pokazany w arkuszu — wiersz i-ty
        # arkusza to `_widoczne[i]`, NIE `_dop[i]`. Wszystko, co mapuje
        # wiersz na pozycję, musi iść przez `_widoczne`.
        self._widoczne = [d for d in self._dop if self._pasuje_do_filtra(d)]
        dane, kolory = [], []
        for d in self._widoczne:
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
            # Nazwa kartoteki z Subiekta — do porównania z opisem z faktury.
            # `nazwa_subiekt` bywa puste przy starszych decyzjach, więc gdy
            # trzeba, dociągamy ją z kartoteki po Id.
            kart_rec = self._kat_po_id.get(d.asortyment_id) or {}
            nazwa_kart = d.nazwa_subiekt or kart_rec.get("nazwa", "")
            opis_kart = kart_rec.get("opis", "") if d.asortyment_id else ""
            proj = ""
            dec = p.decyzja or {}
            if dec.get("projekt"):
                proj = f"► {dec['projekt']}"
            elif rys:
                lista = self.rysunki.get(rys.upper(), [])
                nr = sorted({str(x.get("projekt")) for x in lista})
                proj = ", ".join(nr[:4]) + (f" +{len(nr) - 4}" if len(nr) > 4 else "")
            # ✎ przy Lp. = decyzja człowieka, zgodnie z legendą. Numer wiersza
            # tksheet rysuje sam po lewej, ale to numer WIDOKU — Lp. z faktury
            # zostaje, bo to ono jest w decyzji i w komunikatach.
            dane.append([f"✎ {p.nr_wiersza}" if dec else p.nr_wiersza,
                         rys or ident, _etykieta_typu(d), _opis_pozycji(d),
                         _ilosc(p.ilosc), p.jednostka, _zl(p.cena_netto),
                         (p.dodatkowe or {}).get("Numer wydania", ""),
                         kart, nazwa_kart, opis_kart, proj, STATUSY[d.status][0]])
            kolory.append((d, bool(dec)))

        try:
            self.sheet.dehighlight_all()
        except Exception:
            pass
        self.sheet.set_sheet_data(dane, reset_col_positions=False, redraw=False)
        for i, (d, ma_decyzje) in enumerate(kolory):
            tlo, fg = STATUSY[d.status][1], STATUSY[d.status][2]
            self.sheet.highlight_cells(row=i, column=K_STATUS, bg=tlo, fg=fg)
            self.sheet.highlight_cells(row=i, column=K_TYP, bg=tlo, fg=fg)
            if ma_decyzje:
                self.sheet.highlight_cells(row=i, column=K_LP, bg="#d6eaf8", fg="#1f5fa8")
            if d.zrodlo == kk.ZRODLO_NORMALIZACJA:
                # Kandydat po normalizacji — pomarańczowo, jak niewysłane ZD
                # w oknie dokumentów: „jest, ale wymaga sprawdzenia".
                self.sheet.highlight_cells(row=i, column=K_KARTOTEKA, bg="#f5b041", fg="#7d3c00")
        self.sheet.redraw()

        s = kk.podsumowanie(self._dop)
        self._chipy["razem"].config(text=f"Pozycji: {s['razem']}")
        self._chipy["kartoteka"].config(text=f"Kartoteka: {s['znalezione']}")
        self._chipy["rysunki"].config(text=f"Rysunek RM: {s['rysunki']}")
        self._chipy["zbiorcze"].config(text=f"Zbiorcze: {s['zbiorcze']}")
        self._chipy["uslugi"].config(text=f"Usługi: {s['uslugi']}")
        self._chipy["brak"].config(text=f"Brak decyzji: {s['brak']}",
                                   fg="#f5b041" if s["brak"] else "#a9dfbf")
        # Aktywny filtr widać po podświetleniu licznika.
        for klucz, l in self._chipy.items():
            wlaczony = (klucz == self.filtr_pozycji)
            l.config(bg="#1a2530" if wlaczony else GRANAT,
                     relief=tk.SOLID if wlaczony else tk.FLAT, bd=1 if wlaczony else 0)
        self.lbl_poz.config(text=(
            "Pozycje — kliknij wiersz, żeby zdecydować" if not self.filtr_pozycji
            else f"Pozycje — filtr: {self._chipy[self.filtr_pozycji].cget('text')}"
                 f"  (kliknij licznik ponownie, żeby pokazać wszystkie)"))
        if zaznacz is not None:
            self._zaznacz_wiersz(zaznacz)

    def _pasuje_do_filtra(self, d):
        """Czy pozycja wchodzi do widoku przy aktywnym filtrze licznika."""
        f = self.filtr_pozycji
        if not f or f == "razem":
            return True
        if f == "brak":
            return d.status == kk.BRAK_DECYZJI
        if f == "uslugi":
            return d.status == kk.USLUGA
        if f == "zbiorcze":
            return d.status == kk.POZYCJA_ZBIORCZA
        if f == "rysunki":
            return d.status == kk.RYSUNEK_RM
        if f == "kartoteka":
            return d.status in (kk.KARTOTEKA, kk.NOWA_KARTOTEKA)
        return True

    def _filtruj_pozycje(self, klucz):
        """Klik w licznik = filtr; klik w ten sam albo w „Pozycji" = wszystkie."""
        self.filtr_pozycji = None if (klucz in ("razem", self.filtr_pozycji)) else klucz
        self._wypelnij_tabele()

    # ── praca na wierszach tksheet (odpowiedniki iid z Treeview) ──────────
    def _wiersz_lp(self, lp):
        """Indeks WIDOCZNEGO wiersza dla danego Lp. — albo None (odfiltrowany)."""
        for i, d in enumerate(getattr(self, "_widoczne", self._dop)):
            if str(d.pozycja.nr_wiersza) == str(lp):
                return i
        return None

    def _zaznacz_wiersz(self, lp):
        i = self._wiersz_lp(lp)
        if i is None or self.sheet is None:
            return
        try:
            self.sheet.select_row(i)
            self.sheet.see(row=i, column=0)
        except Exception:
            pass

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
        if self.sheet is None:
            return
        try:
            wiersze = sorted(set(self.sheet.get_selected_rows(get_cells_as_rows=True)))
        except Exception:
            wiersze = []
        widoczne = getattr(self, "_widoczne", self._dop)
        if not wiersze or wiersze[0] >= len(widoczne):
            return
        d = widoczne[wiersze[0]]
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
                # Filtr nie może ukryć celu skoku — gdy pozycji nie widać,
                # zdejmujemy filtr zamiast udawać, że braków nie ma.
                if self._wiersz_lp(d.pozycja.nr_wiersza) is None:
                    self.filtr_pozycji = None
                    self._wypelnij_tabele()
                self._zaznacz_wiersz(d.pozycja.nr_wiersza)
                self._wybrano_pozycje()
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
                # Świeży katalog Z OPISEM — ta sama ścieżka co przy starcie,
                # żeby nowa kartoteka od razu pokazała Nazwę i Opis.
                return self._tlo_praca().get("katalog")

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
            # Eksportujemy TO, CO WIDAĆ — z filtrem włącznie. Inaczej plik nie
            # odpowiadałby temu, na co patrzy człowiek klikając „Eksport".
            for i, d in enumerate(getattr(self, "_widoczne", self._dop)):
                try:
                    wiersz = list(self.sheet.get_row_data(i))
                except Exception:
                    wiersz = []
                w.writerow(wiersz + [_zl(d.pozycja.wartosc_netto),
                                     (d.pozycja.decyzja or {}).get("komentarz", "")])
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
