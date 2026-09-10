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
from tkinter import ttk, messagebox, filedialog

from rm_kreciolek import Kreciolek
from subiekt_stany import wysrodkuj
# Okno komunikatu centrowane na rodzicu — messagebox (natywny dialog Tk)
# pozycjonuje sie wzgledem monitora GLOWNEGO i przy trzech monitorach
# wyskakuje na innym ekranie niz aplikacja (09.09.2026).
from subiekt_projekt import komunikat as komunikat_ed
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

#: Zaslepka nazwy w widokach. Do Subiekta NIE trafia — tam za pusta
#: nazwe wchodzi symbol (patrz Kartoteka.do_planu).
BEZ_NAZWY = "(bez nazwy — uzupełnij)"

#: Waga informacji w raporcie zapisu — decyduje o kolorze tla wiersza.
#: Bez tego "bez-zmian" krzyczalo tak samo glosno jak "do-zalozenia".
WAGA_STATUSU = {
    "blad": "uwaga",
    "pominiety-brak-skladnikow": "uwaga",
    "do-zalozenia": "nowe",
    "zalozona": "nowe",
    # Nadpisanie tego, co juz jest w Subiekcie — kasuje czyjas wczesniejsza
    # wartosc, wiec wlasna waga. "do-ustawienia" tylko wypelnia sklad
    # swiezo zakladanego kompletu, czyli puste miejsce.
    "do-zmiany": "nadpisanie",
    "zmieniona": "nadpisanie",
    "do-ustawienia": "zmiana",
    "sklad-ustawiony": "zmiana",
    "bez-zmian": "info",
}

#: waga → (tlo, kolor tekstu). Tlo, nie sam tekst: wiersz ma byc
#: rozpoznawalny kątem oka, bez czytania kolumny Status.
KOLORY_WAGI = {
    "uwaga":  ("#f9d6d5", "#922b21"),   # czerwone — wymaga reakcji
    "nowe":   ("#d6eaf8", "#1a5276"),   # niebieskie — powstaje nowy byt
    "nadpisanie": ("#f5c6a5", "#a04000"),  # lososiowe — nadpisujemy stan z Subiekta
    "zmiana": ("#fcf3cf", "#7d6608"),   # zolte — uzupelnienie, nic sie nie traci
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


def scal_kartoteki(cel, zrodla, zapisz, timeout=TIMEOUT_S):
    """Tryb "scal" mostu: przepiecie uzycia zrodel na cel + wycofanie zrodel.

    zapisz=False to "Sprawdz scalanie" — pelny raport bez dotykania bazy.
    """
    tmp = tempfile.mkdtemp(prefix="subiekt_scal_")
    plan = {"cel": cel, "zrodla": list(zrodla)}
    argv = ["--zapisz"] if zapisz else []
    return _uruchom("scal", argv, os.path.join(tmp, "wynik.json"),
                    timeout, plan=plan, write=zapisz)


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
        #: Pusta nazwa ZOSTAJE pusta. Wczesniej podmieniala sie na symbol,
        #: wiec drzewo pokazywalo "SKL-01  SKL-01" i nie bylo widac, ze
        #: pozycja czeka na uzupelnienie. Zaslepke rysuje dopiero widok.
        self.nazwa = nazwa
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
        d = {"symbol": self.symbol, "nazwa": self.nazwa or self.symbol,
             "rodzaj": self.rodzaj, "jm": self.jm,
             "opis": self.opis}
        # CENA ZERO NIE IDZIE DO MOSTU (10.09.2026). Pole "Cena ewid." startuje
        # z "0,00" i tyle samo pokazuje kartoteka, ktorej ceny nie znamy, wiec
        # zapis kartoteki bez dotykania tego pola zerowal cene ustawiona
        # w Subiekcie. Brak klucza = "nie ruszaj" — tak samo jak przy VAT-ach
        # i polozeniu. Zeby wpisac zero swiadomie, trzeba je ustawic
        # w Subiekcie: przez ten edytor sie nie da i to jest celowe.
        if self.cena:
            d["cena"] = self.cena
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


#: Szerokosc kolumny "✓" w sekcji 4 — jedyna, ktora sie NIE rozciaga
#: (miesci ptaszek, nie tekst), wiec _dopasuj_kolumny_listy odejmuje ja
#: od dostepnej szerokosci przed podzialem reszty.
KOL_LISTA_STALE = 28


class EdytorWindow(tk.Toplevel, Kreciolek):
    KOL_SKLAD = [("lp", "Lp.", 40), ("symbol", "Symbol", 130),
                 ("nazwa", "Nazwa", 220), ("ilosc", "Ilość", 70),
                 ("jm", "JM", 50)]
    #: Opis miedzy Nazwa a Rodzaj (10.09.2026) — sam symbol i nazwa nie
    #: wystarczaly, zeby odroznic warianty tej samej czesci na liscie.
    KOL_LISTA = [("w", "✓", KOL_LISTA_STALE), ("symbol", "Symbol", 130), ("nazwa", "Nazwa", 190),
                 ("opis", "Opis", 160),
                 ("rodzaj", "Rodzaj", 75), ("stan", "Stan", 55),
                 ("cena", "Cena netto", 75)]

    def __init__(self, parent, symbol=None):
        super().__init__(parent)
        self.title("Edytor kartotek — Subiekt nexo PRO")
        self.configure(bg=TLO)
        # 1900, nie 1500: sekcja 4 ma dzis SIEDEM kolumn (doszly "Opis"
        # i "Stan", ~815 px), a dostaje tylko czesc szerokosci okna — przy
        # 1760 koncowe kolumny znow wypadaly za krawedz. Wysokosc 860, bo
        # kolumne srodkowa dzieli teraz panel 5 (Scalanie).
        #
        # Okno i tak zwezi sie do ekranu: wysrodkuj() przycina rozmiar do
        # granic pulpitu, a _dopasuj_kolumny_listy rozdziela szerokosc
        # proporcjonalnie, wiec na mniejszym monitorze nic nie wypada.
        self.geometry("1900x860")

        # ── MODEL (graf, patrz docstring) ────────────────────────────────
        self.pozycje = {}        # symbol -> Kartoteka
        self.relacje = []        # [(rodzic, dziecko, ilosc)]
        self.korzenie = []       # symbole bez rodzica — wierzchołki drzewa
        self.katalog = []        # kartoteki z Subiekta (do listy 4)
        #: {SYMBOL: ilosc w magazynie} — dociagane razem z katalogiem.
        self._stany = {}
        self._zaznaczony = None  # symbol aktualnie edytowanej pozycji
        #: Czy _zaznaczony przyszlo z listy 4, a nie z drzewa. Rozroznienie
        #: jest potrzebne, bo wybor z listy USTAWIA _zaznaczony — bez tego
        #: kolejne klikniecie na liscie odbijaloby sie od wlasnego poprzedniego
        #: wyboru i dalo sie kliknac tylko pierwsza kartoteke.
        self._z_listy = False
        self._blokada = False    # blokada zapisu pól przy przeładowaniu
        self._zmienione = False  # czy sa niezapisane modyfikacje
        self._dnd_zrodlo = None   # symbol przeciaganej pozycji
        self._dnd_cel = None      # id wezla podswietlonego jako cel
        self._dnd_start_xy = None # punkt nacisniecia - prog na prawdziwy drag
        self._dnd_aktywny = False # True dopiero po ruchu > prog

        self._buduj()
        self._podepnij_klawiature()
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

        # ── DOKUMENTY Z POZYCJI DRZEWA ─────────────────────────────
        # Drzewo z sekcji 1 jest roboczym koszykiem: zebrane w nim pozycje
        # ida na JEDEN dokument zbiorczy, nie na osobny per kartoteka
        # (SUBIEKT_FORMULARZE_DOKUMENTOW.md §2). Kolejnosc wdrazania:
        # RW → PW → ZK → ZD → MM/PZ/WZ; niegotowe mowia wprost, ze ich nie ma,
        # zamiast udawac dzialajacy przycisk.
        tk.Frame(pasek, bg="#4a6278", width=1).pack(side=tk.LEFT, fill=tk.Y,
                                                    padx=10, pady=9)
        tk.Label(pasek, text="Dokument:", bg="#34495e", fg="#bdc3c7",
                 font=("Arial", 8)).pack(side=tk.LEFT, padx=(0, 4))
        for etykieta, akcja in (("RW", self._dokument_rw),
                                ("PW", self._wkrotce("PW")),
                                ("ZD", self._wkrotce("ZD")),
                                ("ZK", self._wkrotce("ZK")),
                                ("Więcej ▾", self._wkrotce("MM / PZ / WZ"))):
            tk.Button(pasek, text=etykieta, command=akcja, font=("Arial", 9),
                      padx=8).pack(side=tk.LEFT, padx=2, pady=7)

        self.status = tk.Label(self, text="", bg=TLO, fg=TEKST_SZARY,
                               font=("Arial", 9), anchor="w")
        self.status.pack(fill=tk.X, padx=10, pady=(6, 0))

        srodek = tk.Frame(self, bg=TLO)
        srodek.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        self._panel_drzewo(srodek)
        self._panel_szczegoly(srodek)
        self._panel_sklad_i_lista(srodek)

    # ── DOKUMENTY ─────────────────────────────────────────

    def _wkrotce(self, nazwa):
        """Zaslepka dla dokumentow jeszcze niezrobionych.

        Lepsze niz ukrywanie przyciskow: user widzi, co jest planowane,
        i nie szuka funkcji, ktorej nie ma.
        """
        def pokaz():
            messagebox.showinfo(
                nazwa,
                f"Formularz {nazwa} jeszcze nie jest gotowy.\n\n"
                "Kolejność wdrażania: RW → PW → ZK → ZD → MM/PZ/WZ\n"
                "(SUBIEKT_FORMULARZE_DOKUMENTOW.md)", parent=self)
        return pokaz

    def _wezly_zrodlowe(self):
        """Symbole, od których liczymy pozycje dokumentu.

        ZAZNACZONE w drzewie, a gdy nic nie zaznaczono — wszystkie korzenie
        (czyli całe drzewo). Zaznaczyć można DOWOLNY węzeł, nie tylko korzeń;
        zaznaczony komplet wchodzi Z CAŁYM PODDRZEWEM — w dół schodzi
        `pozycje_z_drzewa` według wybranego trybu rozwijania, my podajemy
        tylko punkty startowe (ustalenie z 10.09.2026).

        Węzły ZAGNIEŻDŻONE w innych zaznaczonych są ODSIEWANE: zaznaczenie
        kompletu RAZEM z jego składnikiem policzyłoby ten składnik dwa razy
        — raz z rozwinięcia kompletu, raz wprost.
        """
        zazn = []
        for it in self.tree.selection():
            sym = self._symbol_wezla(it)
            if sym and sym in self.pozycje:
                zazn.append((it, sym))
        if not zazn:
            return list(self.korzenie)

        # Pracujemy na ID WĘZŁÓW, nie na symbolach: ta sama kartoteka może
        # wystąpić w kilku miejscach drzewa (model grafowy), a zaznaczone
        # bywa tylko jedno z nich.
        zazn_id = {it for it, _s in zazn}
        wynik = []
        for it, sym in zazn:
            rodzic = self.tree.parent(it)
            pod_innym = False
            while rodzic:
                if rodzic in zazn_id:
                    pod_innym = True
                    break
                rodzic = self.tree.parent(rodzic)
            if not pod_innym and sym not in wynik:
                wynik.append(sym)
        return wynik

    def _pozycje_na_dokument(self, tryb):
        """Pozycje z drzewa dla formularza dokumentu, wg trybu rozwijania."""
        from subiekt_dokument_form import pozycje_z_drzewa
        poz = pozycje_z_drzewa(self.pozycje, self.relacje, self.korzenie, tryb,
                               tylko_symbole=self._wezly_zrodlowe())
        # Stan magazynowy dokladamy z tego, co juz wczytalismy razem
        # z katalogiem — bez dodatkowego pytania do Subiekta.
        for p in poz:
            p["stan"] = self._stany.get(p["symbol"].upper())
        return poz

    def _dokument_rw(self):
        """RW z pozycji zebranych w drzewie (sekcja 1)."""
        from subiekt_dokument_form import BEZPOSREDNIO
        poz = self._pozycje_na_dokument(BEZPOSREDNIO)
        if not poz:
            messagebox.showinfo(
                "RW", "Drzewo jest puste — nie ma czego wydać.\n\n"
                "Wciągnij pozycje z listy 4 (dwuklik) albo dodaj nowe.",
                parent=self)
            return
        # Mowimy wprost, co weszlo do dokumentu — przy zaznaczonym komplecie
        # pozycji bywa wiecej niz zaznaczonych wezlow i bez tego wygladaloby
        # to na przypadek.
        ile_zazn = len(self.tree.selection())
        self.status.config(
            text=(f"RW: {len(poz)} pozycji z {ile_zazn} zaznaczonych węzłów"
                  if ile_zazn else f"RW: {len(poz)} pozycji z całego drzewa "
                                   "(nic nie zaznaczono)"),
            fg=TEKST_SZARY)
        # Pozycje bez kartoteki w Subiekcie odpadaja od razu — most i tak
        # by je odrzucil, a tu mozna powiedziec o tym po ludzku.
        brak = [p["symbol"] for p in poz
                if p["symbol"] in self.pozycje and not self.pozycje[p["symbol"]].w_subiekcie]
        if brak:
            messagebox.showwarning(
                "RW",
                "Te pozycje nie są jeszcze w Subiekcie i nie mogą zejść ze stanu:\n\n"
                + "\n".join(f"  • {b}" for b in brak[:10])
                + ("" if len(brak) <= 10 else f"\n  … i {len(brak) - 10} więcej")
                + "\n\nNajpierw je załóż („Załóż / Zapisz”).", parent=self)
            poz = [p for p in poz if p["symbol"] not in brak]
            if not poz:
                return
        import subiekt_rw_gui
        subiekt_rw_gui.otworz(self, poz, {
            "magazyny": self._magazyny(),
            "przelicz": self._pozycje_na_dokument,
            "po_zapisie": self._wczytaj_katalog,   # stany sie zmienily
        })

    def _magazyny(self):
        """Symbole magazynów do wyboru w formularzu — z wczytanych stanów."""
        from subiekt_rw_gui import MAGAZYN_DOMYSLNY
        symbole = set()
        try:
            for p in self.katalog or []:
                for m in (p.get("Magazyny") or []):
                    sym = str(m.get("Magazyn") or "").strip()
                    if sym:
                        symbole.add(sym)
        except Exception:
            pass
        symbole.add(MAGAZYN_DOMYSLNY)
        return sorted(symbole)

    # ── KLAWIATURA ────────────────────────────────────────

    def _podepnij_klawiature(self):
        """Skroty klawiszowe okna (10.09.2026).

        Strzalki, PgUp/PgDn, Home/End obsluguje SAM Treeview — pod warunkiem,
        ze ma fokus. Dlatego nie podpinamy ich recznie (duplikat ruszalby
        zaznaczenie dwa razy na jedno nacisniecie): zamiast tego dajemy
        klikniecie=fokus, Tab miedzy listami i strzalki dzialajace takze wtedy,
        gdy fokus siedzi w polu tekstowym panelu 2.

        Esc zamyka okno, ale NIE gdy user wlasnie pisze w polu — wtedy
        najpierw oddaje fokus liscie. Inaczej odruchowe Esc po zlej literce
        wyrzucaloby z calego edytora (z ostrzezeniem o niezapisanych zmianach,
        ale i tak niepotrzebnie).
        """
        # Esc — na oknie, nie na widgetach: lapie niezaleznie od tego,
        # co ma fokus.
        self.bind("<Escape>", self._na_escape)

        # Del kasuje zaznaczone — osobno w drzewie i w skladzie, bo to dwie
        # rozne operacje (wezel struktury vs skladnik kompletu). NIE na oknie:
        # inaczej Del w polu tekstowym kasowalby pozycje zamiast znaku.
        self.tree.bind("<Delete>", self._usun_wezel)
        self.tab_sklad.bind("<Delete>", lambda _e: self._usun_skladnik())

        # Klikniecie w tabele = fokus na niej. Bez tego strzalki nie dzialaja
        # po samym zaznaczeniu myszka (Treeview nie bierze fokusu z klikniecia
        # w Windows, gdy okno ma pola Entry).
        for tab in (self.tree, self.tab_lista, self.tab_sklad):
            tab.bind("<Button-1>", lambda _e, t=tab: t.focus_set(), add="+")

        # Ctrl+strzalki dzialaja ZAWSZE — takze z pola tekstowego, gdzie
        # zwykle strzalki musza zostac przy kursorze w tekscie.
        self.bind("<Control-Up>", lambda _e: self._ruch_po_liscie(-1))
        self.bind("<Control-Down>", lambda _e: self._ruch_po_liscie(1))
        self.bind("<Control-Prior>", lambda _e: self._ruch_po_liscie(-10))
        self.bind("<Control-Next>", lambda _e: self._ruch_po_liscie(10))
        self.bind("<Control-Home>", lambda _e: self._ruch_po_liscie(None, skraj="start"))
        self.bind("<Control-End>", lambda _e: self._ruch_po_liscie(None, skraj="koniec"))

        # Tab / Shift+Tab miedzy trzema tabelami — szybkie przeskoki bez myszy.
        for tab in (self.tree, self.tab_lista, self.tab_sklad):
            tab.bind("<Tab>", self._nastepna_tabela)
            tab.bind("<Shift-ISO_Left_Tab>", self._poprzednia_tabela)
            tab.bind("<Shift-Tab>", self._poprzednia_tabela)

        # Enter na liscie 4 = to samo co dwuklik (dodaj jako skladnik).
        self.tab_lista.bind("<Return>", lambda _e: self._dodaj_istniejaca())
        # Enter w polu Nazwa przenosi do listy — typowy odruch po wpisaniu.
        self.pola["nazwa"][1].bind("<Return>", lambda _e: self.tab_lista.focus_set())

    def _na_escape(self, _e=None):
        """Esc: z pola tekstowego oddaj fokus liscie, z tabeli zamknij okno."""
        w = self.focus_get()
        if isinstance(w, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox)):
            self.tab_lista.focus_set()
            return "break"
        self._anuluj()
        return "break"

    def _aktywna_tabela(self):
        """Tabela, ktora ma fokus — albo lista 4, gdy fokus jest gdzie indziej."""
        w = self.focus_get()
        return w if w in (self.tree, self.tab_lista, self.tab_sklad) else self.tab_lista

    def _ruch_po_liscie(self, krok, skraj=None):
        """Przesuwa zaznaczenie w aktywnej tabeli o `krok` wierszy.

        Uzywane przez Ctrl+strzalki, ktore maja dzialac takze z pola
        tekstowego. Zwykle strzalki zostawiamy Treeview — robi to sam
        i lepiej (zna wysokosc widoku dla PgUp/PgDn).
        """
        tab = self._aktywna_tabela()
        dzieci = tab.get_children()
        if not dzieci:
            return "break"
        if skraj == "start":
            cel = dzieci[0]
        elif skraj == "koniec":
            cel = dzieci[-1]
        else:
            biezacy = tab.selection()
            i = dzieci.index(biezacy[0]) if biezacy and biezacy[0] in dzieci else -1
            cel = dzieci[max(0, min(len(dzieci) - 1, i + krok))] if i >= 0 else dzieci[0]
        tab.selection_set(cel)
        tab.focus(cel)
        tab.see(cel)
        return "break"

    def _nastepna_tabela(self, _e=None):
        return self._przeskocz(1)

    def _poprzednia_tabela(self, _e=None):
        return self._przeskocz(-1)

    def _przeskocz(self, kierunek):
        kolejnosc = [self.tree, self.tab_lista, self.tab_sklad]
        w = self.focus_get()
        i = kolejnosc.index(w) if w in kolejnosc else 0
        kolejnosc[(i + kierunek) % len(kolejnosc)].focus_set()
        return "break"

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
        # "sym" to kolumna ROBOCZA (displaycolumns ja ukrywa): trzyma symbol
        # pozycji — patrz _symbol_wezla. "typ" pokazuje skrot rodzaju wlasnym
        # kolorem; w tekscie wezla nie da sie pokolorowac samego fragmentu.
        self.tree = ttk.Treeview(wrap, columns=("ilosc", "sym", "typ"),
                                 # "extended", nie "browse": Ctrl+klik i Shift+klik
                                 # zaznaczaja wiele wezlow naraz, zeby dalo sie
                                 # skasowac je jednym Del (10.09.2026).
                                 show="tree headings", selectmode="extended",
                                 displaycolumns=("typ", "ilosc"),
                                 style="Edytor.Treeview")
        self.tree.heading("#0", text="Symbol / Nazwa")
        self.tree.heading("typ", text="Typ")
        self.tree.heading("ilosc", text="Ilość")
        self.tree.column("typ", width=38, minwidth=38, anchor="center",
                         stretch=False)
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
        tk.Button(pb, text="Z pliku…", command=self._wczytaj_z_pliku,
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
        # Kolumna srodkowa: panel 2 (szczegoly) u gory, panel 5 (scalanie)
        # pod nim. Osobna ramka, bo oba maja byc jedna kolumna miedzy
        # drzewem a skladem, a pack(side=LEFT) na dwoch panelach ustawilby
        # je obok siebie.
        kolumna = tk.Frame(rodzic, bg=TLO)
        kolumna.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6)
        ram = tk.LabelFrame(kolumna, text=" 2. Kartoteka — szczegóły ",
                            bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9, "bold"))
        ram.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._panel_scalanie(kolumna)

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
            # 28 zamiast 44 znakow: pole i tak rozciaga sie z oknem
            # (sticky="we"), a sztywne 44 wypychalo zawartosc poza ramke.
            e = tk.Entry(pod, textvariable=v, font=("Arial", 9), width=28)
            e.grid(row=i, column=1, sticky="we", padx=4, pady=6)
            v.trace_add("write", lambda *_a, k=klucz: self._pole_zmienione(k))
            self.pola[klucz] = (v, e)
        # Auto — nadaje nastepny wolny symbol, zeby nie wymyslac go recznie.
        self.btn_auto = tk.Button(pod, text="Auto", command=self._auto_symbol,
                                  font=("Arial", 8), padx=6)
        self.btn_auto.grid(row=0, column=2, sticky="w", padx=(0, 8), pady=6)

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

        # POŁOŻENIE tutaj, nie tylko w zakładce Magazyn: przy kompletowaniu
        # trzeba wiedzieć, z której półki wziąć detal, bez klikania w zakładki
        # (09.09.2026). To ta sama zmienna co w karcie Magazyn — jedno pole
        # w dwóch miejscach, więc wpis widać od razu w obu.
        tk.Label(pod, text="Położenie:", bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9),
                 anchor="w", width=12).grid(row=5, column=0, sticky="w", padx=8, pady=6)
        self.var_polozenie = tk.StringVar()
        tk.Entry(pod, textvariable=self.var_polozenie, font=("Arial", 9),
                 width=20).grid(row=5, column=1, sticky="w", padx=4, pady=6)
        self.var_polozenie.trace_add(
            "write", lambda *_a: self._pole_zmienione("polozenie"))
        tk.Label(pod, text="regał / półka", bg=TLO_SEKCJI, fg=TEKST_SZARY,
                 font=("Arial", 8), anchor="w").grid(row=5, column=2, sticky="w", padx=(0, 8))

        tk.Label(pod, text="Opis:", bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9),
                 anchor="nw", width=12).grid(row=6, column=0, sticky="nw", padx=8, pady=6)
        self.txt_opis = tk.Text(pod, height=5, width=44, font=("Arial", 9), wrap="word")
        self.txt_opis.grid(row=6, column=1, sticky="we", padx=4, pady=6)
        self.txt_opis.bind("<KeyRelease>", lambda _e: self._pole_zmienione("opis"))
        pod.grid_columnconfigure(1, weight=1)

        # ZAPIS SAMEJ TEJ POZYCJI — obok "Załóż / Zapisz" z paska górnego,
        # który wysyła CAŁE drzewo. Przy poprawianiu jednej kartoteki
        # (nazwa, cena, położenie) wysyłanie wszystkiego jest i wolne,
        # i ryzykowne — dotyka pozycji, których user w ogóle nie tknął.
        pasek_poz = tk.Frame(pod, bg=TLO_SEKCJI)
        pasek_poz.grid(row=7, column=0, columnspan=3, sticky="we", padx=8, pady=(10, 2))
        self.btn_zapisz_pozycje = tk.Button(
            pasek_poz, text="\U0001f4be Zapisz tę pozycję do Subiekta",
            command=self._zapisz_pozycje, state=tk.DISABLED,
            bg="#27ae60", fg="white", font=("Arial", 9, "bold"),
            padx=10, pady=4, cursor="hand2")
        self.btn_zapisz_pozycje.pack(side=tk.LEFT)
        tk.Label(pasek_poz, text="tylko ta kartoteka — bez reszty drzewa",
                 bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8)).pack(
            side=tk.LEFT, padx=(8, 0))

        self.lbl_info = tk.Label(
            pod, text="Symbol po zapisie do Subiekta nie podlega zmianie —\n"
                      "jest kluczem w kodach kreskowych, dokumentach i składach kompletów.",
            bg="#eaf2f8", fg=TEKST_SZARY, font=("Arial", 8), justify="left", anchor="w")
        self.lbl_info.grid(row=8, column=0, columnspan=2, sticky="we", padx=8, pady=(6, 8))

        self._karta_handlowe()
        self._karta_magazyn()
        self._karta_dodatkowe()

    # ── 5. SCALANIE POZYCJI ───────────────────────────────────

    KOL_SCAL = [("cel", "●", 26), ("symbol", "Symbol", 120),
                ("nazwa", "Nazwa", 150), ("opis", "Opis", 100),
                ("ilosc", "Ilość", 52), ("rodzaj", "Rodzaj", 60)]

    def _panel_scalanie(self, rodzic):
        """Scalanie zduplikowanych kartotek Subiekta w jedna docelowa.

        Zasada (10.09.2026): symbol jest kluczem, wiec scalanie NIE zmienia
        symboli i NIE zaklada nowej kartoteki. Cel zostaje dokladnie taki,
        jaki jest; zrodla sa przepinane (uzycie w kompletach, ilosci sumowane
        przy kolizji) i wycofywane znacznikiem "SCALONO DO". Reszte robi
        most (tryb "scal"), tu jest tylko zebranie decyzji i raport.

        Tylko Towar→Towar i Usluga→Usluga. Komplety blokujemy — scalanie
        kompletow wymaga decyzji o obu skladach i to jest osobny etap.
        """
        ram = tk.LabelFrame(rodzic, text=" 5. Scalanie pozycji ",
                            bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9, "bold"))
        ram.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))
        tk.Label(ram, text="Połącz duplikaty w jedną kartotekę docelową — "
                           "symbole zostają, źródła są przepinane i wycofywane",
                 bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8), anchor="w").pack(
            fill=tk.X, padx=8, pady=(4, 2))

        srodek = tk.Frame(ram, bg=TLO_SEKCJI)
        srodek.pack(fill=tk.X, padx=8, pady=2)

        lewa = tk.Frame(srodek, bg=TLO_SEKCJI)
        lewa.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(lewa, text="Pozycje do scalenia (● = docelowa)", bg=TLO_SEKCJI,
                 fg=TEKST, font=("Arial", 8, "bold"), anchor="w").pack(fill=tk.X)
        wrap = tk.Frame(lewa, bg=TLO_SEKCJI)
        wrap.pack(fill=tk.BOTH, expand=True)
        self.tab_scal = ttk.Treeview(wrap, columns=[k[0] for k in self.KOL_SCAL],
                                     show="headings", height=4, selectmode="browse")
        for klucz, naglowek, szer in self.KOL_SCAL:
            self.tab_scal.heading(klucz, text=naglowek)
            self.tab_scal.column(klucz, width=szer, minwidth=szer,
                                 stretch=(klucz == "nazwa"),
                                 anchor="center" if klucz == "cel"
                                 else "e" if klucz == "ilosc" else "w")
        sc = ttk.Scrollbar(wrap, orient="vertical", command=self.tab_scal.yview)
        self.tab_scal.configure(yscrollcommand=sc.set)
        self.tab_scal.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        self.tab_scal.tag_configure("cel", font=("Arial", 9, "bold"), foreground=OK_ZIELONY)
        self.tab_scal.bind("<Double-1>", lambda _e: self._scal_ustaw_cel())
        self.tab_scal.bind("<Delete>", lambda _e: self._scal_usun())

        przyciski = tk.Frame(lewa, bg=TLO_SEKCJI)
        przyciski.pack(fill=tk.X, pady=(3, 0))
        tk.Button(przyciski, text="+ Zaznaczone w drzewie",
                  command=self._scal_dodaj_z_listy, font=("Arial", 8)).pack(side=tk.LEFT)
        tk.Button(przyciski, text="● Ustaw jako docelową", command=self._scal_ustaw_cel,
                  font=("Arial", 8)).pack(side=tk.LEFT, padx=4)
        tk.Button(przyciski, text="Usuń", command=self._scal_usun,
                  font=("Arial", 8)).pack(side=tk.LEFT)
        tk.Button(przyciski, text="Wyczyść", command=self._scal_wyczysc,
                  font=("Arial", 8)).pack(side=tk.LEFT, padx=4)

        prawa = tk.Frame(srodek, bg=TLO_SEKCJI)
        prawa.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0))
        tk.Label(prawa, text="Po scaleniu:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 8, "bold"), anchor="w").pack(fill=tk.X)
        for t in ("✓ użycie w kompletach przepięte na docelową",
                  "✓ ilości zsumowane, gdy obie są w jednym komplecie",
                  "✓ stare symbole zapamiętane jako aliasy",
                  "✓ źródła oznaczone „SCALONO DO” (zostają w bazie)",
                  "✓ dane kartoteki docelowej bez zmian",
                  "✗ kompletów ten tryb nie scala"):
            tk.Label(prawa, text=t, bg=TLO_SEKCJI, fg=TEKST_SZARY,
                     font=("Arial", 8), anchor="w").pack(fill=tk.X)

        stopka = tk.Frame(ram, bg=TLO_SEKCJI)
        stopka.pack(fill=tk.X, padx=8, pady=(4, 6))
        self.lbl_scal = tk.Label(stopka, text="", bg=TLO_SEKCJI, fg=TEKST_SZARY,
                                 font=("Arial", 8), anchor="w")
        self.lbl_scal.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_scal = tk.Button(stopka, text="SCAL POZYCJE", command=self._scal_wykonaj,
                                  bg="#c0392b", fg="white", font=("Arial", 9, "bold"),
                                  padx=10, state=tk.DISABLED)
        self.btn_scal.pack(side=tk.RIGHT)
        self.btn_scal_sprawdz = tk.Button(stopka, text="Sprawdź scalanie",
                                          command=self._scal_sprawdz, font=("Arial", 9),
                                          padx=8, state=tk.DISABLED)
        self.btn_scal_sprawdz.pack(side=tk.RIGHT, padx=(0, 6))

        self._scal_pozycje = []      # [{symbol, nazwa, rodzaj}]
        self._scal_cel = None        # symbol docelowy
        self._scal_sprawdzone = None  # wynik ostatniego suchego przebiegu

    def _scal_odswiez(self):
        for w in self.tab_scal.get_children():
            self.tab_scal.delete(w)
        for p in self._scal_pozycje:
            cel = p["symbol"] == self._scal_cel
            self.tab_scal.insert("", "end", iid=p["symbol"], values=(
                "●" if cel else "", p["symbol"], p["nazwa"],
                p.get("opis", ""), self._ilosc_txt(p.get("stan")), p["rodzaj"]),
                tags=("cel",) if cel else ())
        bledy = self._scal_waliduj()
        self.lbl_scal.config(text=bledy[0] if bledy else
                             f"{len(self._scal_pozycje) - 1} źródło/źródła → {self._scal_cel}",
                             fg=BLAD_CZERWONY if bledy else OK_ZIELONY)
        self.btn_scal_sprawdz.config(state=tk.DISABLED if bledy else tk.NORMAL)
        # Wykonac mozna TYLKO po sprawdzeniu tego samego ukladu — zmiana
        # listy uniewaznia raport.
        self._scal_sprawdzone = None
        self.btn_scal.config(state=tk.DISABLED)

    def _scal_waliduj(self):
        if len(self._scal_pozycje) < 2:
            return ["zaznacz w drzewie co najmniej dwie pozycje i dodaj je tutaj"]
        if not self._scal_cel:
            return ["wskaż pozycję docelową (dwuklik / ●)"]
        komplety = [p["symbol"] for p in self._scal_pozycje if "omplet" in p["rodzaj"]]
        if komplety:
            return [f"kompletów nie scalamy: {', '.join(komplety)}"]
        rodzaje = {p["rodzaj"] for p in self._scal_pozycje}
        if len(rodzaje) > 1:
            return [f"różne rodzaje: {' / '.join(sorted(rodzaje))} — tylko Towar→Towar, Usługa→Usługa"]
        return []

    def _scal_dodaj_z_listy(self):
        """Dodaje do scalania zaznaczone kartoteki — z listy 4 I z drzewa.

        Pierwsza wersja czytala tylko liste 4. User zaznaczal pozycje
        w DRZEWIE (tam tez sa kartoteki z Subiekta) i klikal przycisk —
        a ten brał stare zaznaczenie listy 4, trafial na "juz jest" i cicho
        nic nie robil (10.09.2026). Teraz: oba zrodla + kartoteka otwarta
        w panelu 2, i zawsze komunikat, co sie stalo.
        """
        # ZRODLEM JEST WYLACZNIE DRZEWO (okno 1) — decyzja usera, 10.09.2026.
        # Drzewo pelni role podrecznej listy: kartoteki wciaga sie do niego
        # dwuklikiem z listy 4, wiec i tak przechodza tamtedy. Czytanie kilku
        # zrodel naraz (lista 4 + drzewo + panel 2) dawalo dwie pozycje po
        # klinieciu jednej — zaznaczenie w drzewie doklejalo sie do wyboru
        # z listy.
        etykiety = {"komplet": "Komplet", "usluga": "Usługa", "towar": "Towar"}
        kandydaci = []                       # [(symbol, nazwa, opis, rodzaj)]
        nowe_bez_subiekta = []
        for it in self.tree.selection():
            sym = self._symbol_wezla(it)
            k = self.pozycje.get(sym) if sym else None
            if not k:
                continue
            if not k.w_subiekcie:            # nowa, niezapisana — nie ma czego scalac
                nowe_bez_subiekta.append(sym)
                continue
            kandydaci.append((sym, k.nazwa, k.opis or "",
                              etykiety.get(k.rodzaj, k.rodzaj)))

        if not kandydaci and not nowe_bez_subiekta:
            messagebox.showinfo(
                "Scalanie",
                "Zaznacz pozycje w drzewie (sekcja 1) — Ctrl / Shift = kilka naraz.\n\n"
                "Kartoteki z listy 4 wciąga się do drzewa dwuklikiem.",
                parent=self)
            return

        znane = {p["symbol"] for p in self._scal_pozycje}
        dodane, juz = [], []
        for sym, naz, opis, rodzaj in kandydaci:
            if sym in znane:
                if sym not in juz:
                    juz.append(sym)
                continue
            self._scal_pozycje.append({"symbol": sym, "nazwa": naz,
                                       "opis": opis or "", "rodzaj": rodzaj,
                                       "stan": None})
            znane.add(sym)
            dodane.append(sym)
        # Pierwsza dodana staje sie celem — zwykle to ta "wlasciwa", a i tak
        # da sie zmienic dwuklikiem.
        if not self._scal_cel and self._scal_pozycje:
            self._scal_cel = self._scal_pozycje[0]["symbol"]
        self._scal_odswiez()
        if dodane:
            self._scal_doczytaj_stany(dodane)

        # Komunikat ZAWSZE — cichy brak reakcji wygladal jak zepsuty przycisk.
        czesci = []
        if dodane:
            czesci.append("dodano: " + ", ".join(dodane))
        if juz and not dodane:
            czesci.append("już na liście: " + ", ".join(juz))
        if nowe_bez_subiekta:
            czesci.append("pominięto (nie ma ich jeszcze w Subiekcie): "
                          + ", ".join(nowe_bez_subiekta))
        if czesci and (not dodane or nowe_bez_subiekta or juz):
            self.status.config(text="Scalanie — " + "; ".join(czesci),
                               fg=TEKST_SZARY if dodane else BLAD_CZERWONY)
        elif dodane:
            self.status.config(text="Scalanie — " + czesci[0], fg=TEKST_SZARY)

    @staticmethod
    def _ilosc_txt(v):
        """Stan magazynowy do komorki: None = jeszcze niewczytany."""
        if v in (None, ""):
            return "?"
        try:
            return f"{float(v):g}"
        except (TypeError, ValueError):
            return "?"

    def _scal_doczytaj_stany(self, symbole):
        """Stan magazynowy dopisanych pozycji — w tle, tryb "stan" mostu.

        Katalog (lista 4) stanow NIE MA: to najdrozsza czesc odczytu, a wchodzi
        do niego 3200 kartotek. Tutaj pytamy punktowo o kilka wlasnie dodanych,
        wiec koszt jest znikomy — a przy decyzji "czy to ten sam element"
        ilosc na stanie bywa rozstrzygajaca.
        """
        def worker():
            try:
                from subiekt_asortyment_gui import pobierz_stany
                wyniki = pobierz_stany(list(symbole))
            except Exception:
                wyniki = []
            self.after(0, lambda: gotowe(wyniki))

        def gotowe(wyniki):
            wg = {}
            for r in wyniki or []:
                klucz = (r.get("Symbol") or r.get("Pytany") or "").strip().upper()
                mag = r.get("Magazyny") or []
                # Stan = dostepne + rezerwacje, tak samo jak okno Asortyment:
                # towar zarezerwowany nadal lezy w firmie.
                rez = sum(float(m.get("RezerwacjaIlosciowa") or 0)
                          + float(m.get("RezerwacjaDostawowa") or 0) for m in mag)
                wg[klucz] = float(r.get("Dostepne") or 0) + rez
            zmiana = False
            for p in self._scal_pozycje:
                if p["symbol"].upper() in wg:
                    p["stan"] = wg[p["symbol"].upper()]
                    zmiana = True
            if zmiana:
                self._scal_odswiez_komorki()

        threading.Thread(target=worker, daemon=True).start()

    def _scal_odswiez_komorki(self):
        """Same ilosci w istniejacych wierszach — BEZ przebudowy tabeli.

        _scal_odswiez() kasuje wynik sprawdzenia i gubi zaznaczenie, a stan
        dochodzi asynchronicznie, gdy user moze juz klikac dalej.
        """
        for p in self._scal_pozycje:
            if not self.tab_scal.exists(p["symbol"]):
                continue
            w = list(self.tab_scal.item(p["symbol"], "values"))
            if len(w) >= 5:
                w[4] = self._ilosc_txt(p.get("stan"))
                self.tab_scal.item(p["symbol"], values=w)

    def _scal_ustaw_cel(self):
        wyb = self.tab_scal.selection()
        if wyb:
            self._scal_cel = wyb[0]
            self._scal_odswiez()

    def _scal_usun(self):
        wyb = self.tab_scal.selection()
        if not wyb:
            return
        self._scal_pozycje = [p for p in self._scal_pozycje if p["symbol"] != wyb[0]]
        if self._scal_cel == wyb[0]:
            self._scal_cel = None
        self._scal_odswiez()

    def _scal_wyczysc(self):
        self._scal_pozycje, self._scal_cel = [], None
        self._scal_odswiez()

    def _scal_zrodla(self):
        return [p["symbol"] for p in self._scal_pozycje if p["symbol"] != self._scal_cel]

    def _scal_sprawdz(self):
        if self._scal_waliduj():
            return
        self.start_kreciolek("Sprawdzam scalanie w Subiekcie")
        threading.Thread(target=self._scal_worker, args=(False,), daemon=True).start()

    def _scal_wykonaj(self):
        """Faktyczne scalanie — dopiero po sprawdzeniu i potwierdzeniu."""
        if self._scal_waliduj() or not self._scal_sprawdzone:
            messagebox.showinfo("Scalanie", "Najpierw „Sprawdź scalanie”.", parent=self)
            return
        w = self._scal_sprawdzone
        if not w.get("ok"):
            messagebox.showwarning("Scalanie", "Sprawdzenie zgłosiło błędy — popraw listę.",
                                   parent=self)
            return
        zrodla = self._scal_zrodla()
        if not messagebox.askyesno(
                "Wykonać scalanie?",
                f"{len(zrodla)} kartotek(i) zostanie WYCOFANYCH na rzecz {self._scal_cel}:\n\n"
                + "\n".join(f"  • {z}" for z in zrodla)
                + f"\n\nPrzepięć w kompletach: {w.get('doPrzepiecia', 0)}"
                f"   (w tym sumowań: {w.get('kolizje', 0)})\n"
                f"Różnic danych zignorowanych na rzecz celu: {w.get('roznice', 0)}\n\n"
                "Tej operacji nie da się cofnąć jednym kliknięciem.",
                parent=self, icon="warning"):
            return
        self.start_kreciolek(f"Scalam do {self._scal_cel}")
        threading.Thread(target=self._scal_worker, args=(True,), daemon=True).start()

    def _scal_worker(self, zapisz):
        cel, zrodla = self._scal_cel, self._scal_zrodla()
        try:
            wynik, blad = scal_kartoteki(cel, zrodla, zapisz), None
        except Exception as e:
            wynik, blad = None, str(e)
        self.after(0, lambda: self._scal_gotowe(wynik, blad, zapisz, cel))

    def _scal_gotowe(self, wynik, blad, zapisz, cel):
        self.stop_kreciolek()
        if blad:
            messagebox.showerror("Scalanie", blad, parent=self)
            return
        if not zapisz:
            self._scal_sprawdzone = wynik
            self.btn_scal.config(state=tk.NORMAL if wynik.get("ok") else tk.DISABLED)
            self._scal_raport(wynik, False)
            return

        # Zapisano w Subiekcie — teraz strona RM_BAZA: aliasy + przepiecie
        # mapowan. Osobno od mostu, bo to metadana RM_BAZA, nie Subiekta.
        przepiete = 0
        if wynik.get("ok"):
            try:
                import subiekt_mapowania
                zrodla_id = {s: i for s, i in (wynik.get("idZrodel") or {}).items()}
                for z in self._scal_zrodla():
                    zrodla_id.setdefault(z, None)
                przepiete = subiekt_mapowania.zapisz_scalenie(cel, wynik.get("idCel"), zrodla_id)
            except Exception as e:
                wynik.setdefault("kroki", []).append(
                    {"Rodzaj": "alias", "Symbol": cel, "Status": "blad",
                     "Szczegoly": f"aliasy w RM_BAZA nie zapisane: {e}"})
        wynik["przepieteMapowania"] = przepiete
        self._scal_raport(wynik, True)
        if wynik.get("ok"):
            self.status.config(text=f"✔ Scalono do {cel}: przepięć {wynik.get('doPrzepiecia', 0)}, "
                                    f"wycofanych {len(self._scal_zrodla())}, mapowań RM_BAZA {przepiete}",
                               fg=OK_ZIELONY)
            self._scal_wyczysc()
            self._wczytaj_katalog()          # lista 4 ma pokazac znaczniki SCALONO

    def _scal_raport(self, w, zapisano):
        """Raport scalania — uklad wg specyfikacji z 10.09.2026."""
        okno = tk.Toplevel(self)
        okno.title("Wynik scalania" if zapisano else "Sprawdzenie scalania")
        okno.configure(bg=TLO)
        okno.geometry("1240x600")
        okno.transient(self)

        cel = w.get("cel") or ""
        zrodla = w.get("zrodla") or []
        ok = bool(w.get("ok"))
        tk.Label(okno, text=f"SCALANIE: {', '.join(zrodla)}  →  {cel}",
                 bg=TLO, fg=OK_ZIELONY if ok else BLAD_CZERWONY,
                 font=("Arial", 11, "bold"), anchor="w").pack(fill=tk.X, padx=14, pady=(12, 4))

        pas = tk.Frame(okno, bg=TLO)
        pas.pack(fill=tk.X, padx=14, pady=(0, 6))
        for etykieta, ile in (("źródła", len(zrodla)),
                              ("użycie w kompletach", w.get("uzycieWKompletach", 0)),
                              ("do przepięcia", w.get("doPrzepiecia", 0)),
                              ("sumowania ilości", w.get("kolizje", 0)),
                              ("różnice danych", w.get("roznice", 0))):
            ramka = tk.Frame(pas, bg=TLO_SEKCJI, bd=1, relief="solid")
            ramka.pack(side=tk.LEFT, padx=(0, 8))
            tk.Label(ramka, text=str(ile), bg=TLO_SEKCJI, fg=TEKST,
                     font=("Arial", 16, "bold")).pack(padx=14, pady=(4, 0))
            tk.Label(ramka, text=etykieta, bg=TLO_SEKCJI, fg=TEKST_SZARY,
                     font=("Arial", 8)).pack(padx=14, pady=(0, 4))

        # Stopka PRZED tabela — inaczej przyciski wypadaja poza okno.
        stopka = tk.Frame(okno, bg=TLO)
        stopka.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=10)
        tk.Button(stopka, text="Zamknij", command=okno.destroy,
                  font=("Arial", 9), padx=14).pack(side=tk.RIGHT)
        if not zapisano and ok:
            def wykonaj():
                okno.destroy()
                self._scal_wykonaj()
            tk.Button(stopka, text="Wykonaj scalanie", command=wykonaj,
                      bg="#c0392b", fg="white", font=("Arial", 9, "bold"),
                      padx=14).pack(side=tk.RIGHT, padx=(0, 8))
        if zapisano:
            tk.Label(stopka, text=(f"aliasy zapisane w RM_BAZA, przepiętych mapowań: "
                                   f"{w.get('przepieteMapowania', 0)}" if ok else
                                   "scalanie NIE zostało wykonane w całości — patrz błędy"),
                     bg=TLO, fg=TEKST_SZARY if ok else BLAD_CZERWONY,
                     font=("Arial", 8)).pack(side=tk.LEFT)

        wrap = tk.Frame(okno, bg=TLO_SEKCJI)
        wrap.pack(fill=tk.BOTH, expand=True, padx=14, pady=4)
        # Nazwa i Opis miedzy Symbolem a Statusem: sam symbol ("016-100.06")
        # nie mowi, co scalamy — a to decyzja nieodwracalna (10.09.2026).
        tab = ttk.Treeview(wrap, columns=("co", "symbol", "nazwa", "opis", "ilosc",
                                          "status", "szcz"),
                           show="headings", style="Edytor.Treeview")
        for k, naz, sz, roz in (("co", "Co", 70, False), ("symbol", "Symbol", 140, False),
                                ("nazwa", "Nazwa", 175, False), ("opis", "Opis", 110, False),
                                ("ilosc", "Ilość", 55, False),
                                ("status", "Status", 105, False), ("szcz", "Szczegóły", 440, True)):
            tab.heading(k, text=naz)
            tab.column(k, width=sz, minwidth=50, stretch=roz,
                       anchor="e" if k == "ilosc" else "w")
        wagi = {"blad": "uwaga", "roznica": "nadpisanie", "kolizja": "nadpisanie",
                "do-przepiecia": "zmiana", "przepiety": "zmiana",
                "do-wycofania": "nowe", "wycofana": "nowe",
                "cel": "info", "zrodlo": "info", "bez-zmian": "info"}
        for waga, (tlo, kolor) in KOLORY_WAGI.items():
            tab.tag_configure(waga, background=tlo, foreground=kolor)
        for k in w.get("kroki") or []:
            st = str(k.get("Status") or "")
            tab.insert("", "end", values=(k.get("Rodzaj"), k.get("Symbol"),
                                          k.get("Nazwa") or "", k.get("Opis") or "",
                                          self._ilosc_txt(k.get("Stan")),
                                          st, k.get("Szczegoly") or ""),
                       tags=(wagi.get(st, "info"),))
        sc = ttk.Scrollbar(wrap, orient="vertical", command=tab.yview)
        tab.configure(yscrollcommand=sc.set)
        tab.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        wysrodkuj(okno, self)

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
        # TA SAMA zmienna co pole „Położenie" na karcie Podstawowe — wpis
        # w jednym miejscu widać od razu w drugim. Nie tworzymy nowej
        # StringVar, bo nadpisałaby tamtą i pola przestałyby się zgadzać.
        tk.Entry(f, textvariable=self.var_polozenie, font=("Arial", 10),
                 width=28).grid(row=0, column=1, sticky="we", padx=4, pady=(14, 4))

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
            # minwidth=40, NIE szer: _dopasuj_kolumny_listy zweza kolumny przy
            # waskim oknie, a minwidth rowny szerokosci startowej blokowalby
            # to zwezanie i koncowe kolumny znow chowalyby sie za krawedzia.
            self.tab_lista.column(klucz, width=szer,
                                  minwidth=KOL_LISTA_STALE if klucz == "w" else 40,
                                  stretch=False,
                                  anchor="e" if klucz in ("cena", "stan") else "w")
        sc_l = ttk.Scrollbar(wrap_l, orient="vertical", command=self.tab_lista.yview)
        sc_l_poz = ttk.Scrollbar(wrap_l, orient="horizontal", command=self.tab_lista.xview)
        self.tab_lista.configure(yscrollcommand=sc_l.set, xscrollcommand=sc_l_poz.set)
        sc_l_poz.pack(side=tk.BOTTOM, fill=tk.X)
        self.tab_lista.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc_l.pack(side=tk.RIGHT, fill=tk.Y)
        self.tab_lista.tag_configure("w_drzewie", foreground=TEKST_SZARY)
        # WSZYSTKIE KOLUMNY ZAWSZE WIDOCZNE (10.09.2026): szerokosci z KOL_LISTA
        # to tylko proporcje startowe. Przy kazdej zmianie rozmiaru panelu
        # rozdzielamy dostepna szerokosc miedzy kolumny wedlug tych proporcji,
        # zeby nic nie wypadalo poza krawedz i zeby poziomy pasek nie byl
        # potrzebny. "✓" zostaje staly — to ikonka, nie tekst.
        self.tab_lista.bind("<Configure>", self._dopasuj_kolumny_listy)
        self.tab_lista.bind("<Double-1>", lambda _e: self._dodaj_istniejaca())
        self.tab_lista.bind("<<TreeviewSelect>>", self._na_wybor_z_listy)
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
        # Stany w TYM SAMYM watku, zaraz po katalogu (10.09.2026). Tryb
        # "magazyn" zwraca 1378 pozycji ze stanem w ~0,1 s przy stalym moscie,
        # wiec kolumna "Stan" nie kosztuje juz tego, co kiedys — dawna uwaga
        # "katalog swiadomie nie czyta stanow" dotyczyla czasow, gdy kazde
        # wywolanie startowalo Sfere od nowa (~10 s).
        #
        # Blad stanow NIE moze przewrocic listy kartotek: bez stanow lista
        # dziala dalej, tylko kolumna pokazuje "?".
        stany = {}
        try:
            from subiekt_magazyn_gui import pobierz_magazyn
            for p in pobierz_magazyn(tylko_niezerowe=True) or []:
                sym = str(p.get("Symbol") or "").strip().upper()
                if sym:
                    stany[sym] = float(p.get("Dostepne") or 0) \
                        + float(p.get("Zarezerwowane") or 0)
        except Exception:
            stany = {}
        self.after(0, lambda: self._katalog_gotowy(dane, blad, stany))

    def _katalog_gotowy(self, dane, blad, stany=None):
        self.stop_kreciolek()
        if blad:
            self.status.config(text=f"Nie udało się wczytać kartotek: {blad}",
                               fg=BLAD_CZERWONY)
            return
        self.katalog = dane
        self._stany = stany or {}
        self._odswiez_liste()
        ze_stanem = sum(1 for v in self._stany.values() if v)
        self.status.config(
            text=f"Kartotek w Subiekcie: {len(dane)}   (na stanie: {ze_stanem})",
            fg=TEKST_SZARY)

    @staticmethod
    def _stan_txt(v):
        """Ilość w magazynie do komórki listy 4.

        Pusto, nie "0": kartoteka bez stanu to norma (czesc kupowana pod
        zamowienie), a 3200 zer na liscie tylko zaszumia widok. "?" znaczy
        "stanow nie udalo sie wczytac" — to co innego niz zero.
        """
        if v is None:
            return ""
        try:
            return f"{float(v):g}" if float(v) else ""
        except (TypeError, ValueError):
            return "?"

    def _odswiez_liste(self):
        """Przebudowa listy 4 - WSZYSTKIE kartoteki, filtr zaweza.

        Byl tu limit 400 wierszy i robil zludzenie "pozycja zniknela":
        po skasowaniu wyszukiwania dodana kartoteka byla poza pierwsza
        czterysetka. 3469 wierszy to dla Treeview ulamek sekundy.
        """
        szukaj = (self.var_szukaj.get() or "").strip().lower()
        osadzone = set(self._osadzone())      # patrz _oznacz_w_liscie
        for w in self.tab_lista.get_children():
            self.tab_lista.delete(w)
        for k in self.katalog:
            sym = str(k.get("Symbol") or "").strip()
            naz = str(k.get("Nazwa") or "").strip()
            opis_k = str(k.get("Opis") or "").strip()
            if (szukaj and szukaj not in sym.lower() and szukaj not in naz.lower()
                    and szukaj not in opis_k.lower()):
                continue
            w_drzewie = sym in osadzone
            self.tab_lista.insert("", "end", values=(
                "✓" if w_drzewie else "", sym, naz,
                str(k.get("Opis") or "").strip(),
                k.get("Rodzaj") or "",
                self._stan_txt(self._stany.get(sym.upper())),
                f"{float(k.get('CenaEwidencyjna') or 0):g}"),
                tags=("w_drzewie",) if w_drzewie else ())

    def _dopasuj_kolumny_listy(self, _e=None):
        """Rozciaga kolumny sekcji 4 na cala szerokosc widoku.

        Treeview nie umie tego sam: `stretch` rozdaje tylko NADMIAR, a przy
        zwezeniu i tak chowa koncowe kolumny za krawedz. Liczymy wiec
        szerokosci proporcjonalnie do KOL_LISTA przy kazdym <Configure>.
        Ponizej sumy minimalnej nie schodzimy — wtedy dziala pasek poziomy,
        bo scisniecie "Cena netto" do zera niczego by nie uratowalo.
        """
        szer = self.tab_lista.winfo_width()
        if szer <= 1:                      # widget jeszcze niezmapowany
            return
        staly = KOL_LISTA_STALE            # "✓" ma stala szerokosc
        elastyczne = [(k, w) for k, _n, w in self.KOL_LISTA if k != "w"]
        suma = sum(w for _k, w in elastyczne) or 1
        # -4 px na obramowanie: bez tego ostatnia kolumna wystaje o wlos
        # i pasek poziomy pojawia sie mimo wszystko.
        dostepne = max(szer - staly - 4, suma // 2)
        for klucz, waga in elastyczne:
            self.tab_lista.column(klucz, width=max(int(dostepne * waga / suma), 40))

    def _oznacz_w_liscie(self):
        """Aktualizuje TYLKO fajki i szarosc na liscie 4, bez przebudowy.

        Wolane przy kazdym odswiezeniu drzewa - przebudowa 3469 wierszy przy
        kazdym wpisanym znaku w polu Nazwa bylaby odczuwalna, zmiana tagow nie.
        Nie ukrywamy pozycji bedacych w drzewie: ta sama kartoteka moze isc
        do drugiego kompletu (model grafowy).
        """
        # Fajka = pozycja OSADZONA W DRZEWIE, nie "obecna w self.pozycje"
        # (10.09.2026). Podglad z listy 4 dopisuje kartoteke do self.pozycje,
        # zeby dalo sie ja edytowac i zapisac — przy starym kryterium samo
        # KLIKNIECIE odfajkowywalo i wyszarzalo pozycje, choc do drzewa nic
        # nie wchodzilo. _osadzone() liczy od korzeni w dol, wiec mowi
        # dokladnie to, co user widzi w sekcji 1.
        osadzone = set(self._osadzone())
        for w in self.tab_lista.get_children():
            wartosci = list(self.tab_lista.item(w, "values"))
            if len(wartosci) < 2:
                continue
            w_drzewie = wartosci[1] in osadzone
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

    def _sprzatnij_osierocona(self, sym):
        """Usuwa z modelu pozycje, ktora wypadla z drzewa.

        Kartoteka Z SUBIEKTA majaca wlasny sklad zostaje — wyciagamy ja na
        wierzch zamiast kasowac, bo user moze chciec ja dalej edytowac,
        a razem z nia zgubilby sie caly jej sklad.
        """
        if sym in self.korzenie:
            return
        if any(d == sym for (_r, d, _il) in self.relacje):
            return                      # wisi jeszcze w innym komplecie
        k = self.pozycje.get(sym)
        if k is None:
            return
        if k.w_subiekcie and self._dzieci(sym):
            self.korzenie.append(sym)
            return
        # Zabieramy tez jej wlasny sklad — inaczej zostalby po niej
        # osierocony ogon relacji.
        dzieci = [d for (r, d, _il) in self.relacje if r == sym]
        self.relacje = [(r, d, il) for (r, d, il) in self.relacje if r != sym]
        del self.pozycje[sym]
        for d in dzieci:
            self._sprzatnij_osierocona(d)

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
                             values=("", symbol, "!"))
            return
        tagi = [k.rodzaj]
        if not k.w_subiekcie:
            tagi.append("nowy")
        # Bez wlasnego prefiksu glebokosci: dublowal sie z wcieciami Treeview
        # i robil balagan. Czytelnosc zalatwia szerszy panel + poziomy pasek.
        wid = self.tree.insert(
            rodzic_id, "end",
            text=f"{symbol}   {k.nazwa or BEZ_NAZWY}",
            values=(f"x{ilosc:g}" if ilosc else "", symbol,
                    SKROT.get(k.rodzaj, "??")), tags=tuple(tagi))
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
        self._z_listy = False
        k = self.pozycje[sym]
        self._odswiez_etykiete_celu()
        self._blokada = True
        try:
            self.pola["symbol"][0].set(k.symbol)
            self.pola["nazwa"][0].set(k.nazwa)
            # Symbol istniejącej kartoteki jest kluczem — nie wolno go zmieniać.
            self.pola["symbol"][1].config(
                state="readonly" if k.w_subiekcie else "normal")
            # Auto tez wygaszamy — zeby nie kusilo kliknięciem, ktore i tak
            # skonczy sie odmowa.
            self.btn_auto.config(state="disabled" if k.w_subiekcie else "normal")
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
        self._aktualizuj_przycisk_pozycji()

    def _na_wybor_z_listy(self, _e=None):
        """Kartoteka zaznaczona w sekcji 4 — do EDYCJI w panelu 2.

        Dziala TYLKO gdy w drzewie nic nie jest zaznaczone (a wiec zwykle
        gdy drzewo jest puste): panel 2 stalby wtedy pusty, mimo ze user
        patrzy na konkretna kartotekę z Subiekta. Gdy cos jest wybrane
        w drzewie, panel nalezy do TAMTEJ pozycji i klikanie po liscie
        nie ma prawa go podmienic — inaczej wpisy przepadalyby w trakcie
        edycji.

        Kartoteka WCHODZI DO MODELU (self.pozycje) i staje sie zaznaczona,
        bo inaczej pola panelu 2 nie mialyby czego zapisywac: _pole_zmienione
        odklada zmiany do self.pozycje[self._zaznaczony], a "Zapisz tę
        pozycję" wymaga wlasnie zaznaczenia (10.09.2026 — pierwsza wersja
        byla read-only i przycisk zostawal szary).

        Do DRZEWA jej nie dokladamy: korzeniem robi ja dopiero dwuklik albo
        "+ Istniejaca". Zapis pojedynczej pozycji dziala mimo to, bo idzie
        przez _plan_pozycji(sym), a nie przez _osadzone().
        """
        # Blokuje tylko zaznaczenie W DRZEWIE. Wlasny poprzedni wybor z listy
        # nie moze blokowac nastepnego — inaczej dalo by sie kliknac tylko
        # PIERWSZA kartoteke, a kolejne bylyby ignorowane.
        if self._zaznaczony and not self._z_listy:
            return
        wyb = self.tab_lista.selection()
        if not wyb:
            return
        try:
            _w, sym, naz, opis, rodzaj, _stan, cena = self.tab_lista.item(wyb[0], "values")
        except ValueError:
            return
        rodzaj_n = ("komplet" if "omplet" in str(rodzaj) else
                    "usluga" if "sług" in str(rodzaj) or "slug" in str(rodzaj)
                    else "towar")
        try:
            cena_f = float(str(cena).replace(",", ".") or 0)
        except ValueError:
            cena_f = 0.0

        # Kartoteka JUZ obecna w modelu (bo user wciagnal ja wczesniej do
        # drzewa) zostaje nietknieta — inaczej podmiana skasowalaby jego
        # zmiany samym klinieciem na liste.
        if sym not in self.pozycje:
            self.pozycje[sym] = Kartoteka(
                sym, naz, rodzaj_n, "kpl" if rodzaj_n == "komplet" else "szt",
                cena=cena_f, opis=str(opis or "").strip(), w_subiekcie=True)
        self._zaznaczony = sym
        self._z_listy = True
        k = self.pozycje[sym]

        self._blokada = True
        try:
            self.pola["symbol"][0].set(k.symbol)
            self.pola["nazwa"][0].set(k.nazwa)
            # Symbol kartoteki z Subiekta jest kluczem — nie do zmiany.
            self.pola["symbol"][1].config(state="readonly")
            self.btn_auto.config(state="disabled")
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

        # Sklad kompletu w sekcji 3. Gdy kartoteka jest juz w modelu, sklad
        # bierzemy STAMTAD (moze byc zmieniony), a nie z Subiekta.
        if rodzaj_n == "komplet" and not self._dzieci(sym):
            self._pokaz_sklad_z_subiekta(sym)
        else:
            self._odswiez_sklad()

        self._oznacz_w_liscie()
        self._aktualizuj_przycisk_pozycji()
        self.status.config(
            text=f"Kartoteka z Subiekta: {sym} — popraw pola i kliknij "
                 f"„Zapisz tę pozycję” (dwuklik wciąga ją do drzewa)",
            fg=TEKST_SZARY)

    def _wyczysc_sklad(self):
        """Pusta sekcja 3 — podglad towaru nie ma skladu."""
        for w in self.tab_sklad.get_children():
            self.tab_sklad.delete(w)
        if hasattr(self, "lbl_sklad"):
            self.lbl_sklad.config(text="")

    def _pokaz_sklad_z_subiekta(self, symbol):
        """Sklad kompletu prosto z Subiekta — do podgladu z sekcji 4."""
        self._wyczysc_sklad()
        if hasattr(self, "lbl_sklad"):
            self.lbl_sklad.config(text=f"dla: {symbol} (z Subiekta…)")
        self.start_kreciolek(f"Czytam skład {symbol}")

        def worker():
            try:
                dane, blad = pobierz_komplet(symbol), None
            except Exception as e:
                dane, blad = None, str(e)
            self.after(0, lambda: gotowe(dane, blad))

        def gotowe(dane, blad):
            self.stop_kreciolek()
            # W miedzyczasie user mogl kliknac cos innego — nie nadpisujemy
            # sekcji 3 wynikiem dla nieaktualnej kartoteki.
            wyb = self.tab_lista.selection()
            aktualny = (self.tab_lista.item(wyb[0], "values")[1]
                        if wyb else None)
            if self._zaznaczony or aktualny != symbol:
                return
            if blad or not dane:
                if hasattr(self, "lbl_sklad"):
                    self.lbl_sklad.config(text=f"dla: {symbol}")
                return
            skl = dane.get("skladniki") or []
            for i, poz in enumerate(skl, start=1):
                self.tab_sklad.insert("", "end", values=(
                    i, poz.get("symbol") or "", poz.get("nazwa") or "",
                    f"{float(poz.get('ilosc') or 0):g}", poz.get("jm") or ""))
            if hasattr(self, "lbl_sklad"):
                self.lbl_sklad.config(
                    text=f"dla: {symbol}  ({len(skl)} składników)")

        threading.Thread(target=worker, daemon=True).start()

    def _pole_zmienione(self, klucz):
        if self._blokada or not self._zaznaczony:
            return
        k = self.pozycje.get(self._zaznaczony)
        if k is None:
            return
        if klucz == "nazwa":
            # Skasowanie nazwy zostawia pusto (i zapala blad w walidacji),
            # zamiast po cichu wpisywac symbol.
            k.nazwa = self.pola["nazwa"][0].get().strip()
        elif klucz == "symbol" and not k.w_subiekcie:
            nowy = self.pola["symbol"][0].get().strip()
            if nowy and nowy != k.symbol and nowy not in self.pozycje:
                self._zmien_symbol(k.symbol, nowy)
                return
        elif klucz == "rodzaj":
            etykieta = self.var_rodzaj.get()
            nowy_rodzaj = dict((e, w) for e, w in RODZAJE).get(etykieta, "towar")
            if not self._zmien_rodzaj(k, nowy_rodzaj):
                return
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

    def _zmien_rodzaj(self, k, nowy_rodzaj):
        """Zmiana rodzaju pozycji. False = user sie rozmyslil.

        Tylko komplet ma sklad. Zejscie z kompletu na towar/usluge musi wiec
        rozstrzygnac los skladnikow — wczesniej zostawaly w relacjach,
        wisialy w drzewie, ale plan ich nie wysylal. Do Subiekta szedl towar,
        a pozycje znikaly bez slowa.
        """
        if nowy_rodzaj == k.rodzaj:
            return True
        dzieci = self._dzieci(k.symbol)
        if k.czy_komplet() and nowy_rodzaj != "komplet" and dzieci:
            nazwa_rodzaju = dict((w, e) for e, w in RODZAJE).get(nowy_rodzaj,
                                                                nowy_rodzaj)
            if not messagebox.askyesno(
                    "Zmiana rodzaju",
                    f"„{k.symbol}” ma {len(dzieci)} składnik(ów), a {nazwa_rodzaju} "
                    "nie może mieć składu.\n\n"
                    "Odpiąć składniki? Zostaną w drzewie jako osobne pozycje "
                    "na wierzchu — nic nie ginie.\n\n"
                    "Nie = zostaw jako Komplet.", parent=self):
                # Cofamy combobox do stanu faktycznego.
                self._blokada = True
                try:
                    for etykieta, wartosc in RODZAJE:
                        if wartosc == k.rodzaj:
                            self.var_rodzaj.set(etykieta)
                finally:
                    self._blokada = False
                return False
            for dziecko, _il in dzieci:
                if dziecko not in self.korzenie:
                    self.korzenie.append(dziecko)
            self.relacje = [(r, d, il) for (r, d, il) in self.relacje
                            if r != k.symbol]
            self.status.config(
                text="Odpięto " + str(len(dzieci)) + " składnik(ów) — są teraz "
                     "osobnymi pozycjami na wierzchu drzewa", fg=TEKST_SZARY)
        k.rodzaj = nowy_rodzaj
        return True

    def _pole_wlasne_zmienione(self, pole):
        if self._blokada or not self._zaznaczony:
            return
        k = self.pozycje.get(self._zaznaczony)
        if k is None:
            return
        k.pola_wlasne[pole] = self.pola_wlasne_var[pole].get()
        self._zmienione = True

    def _auto_symbol(self):
        """Symbol Z NAZWY — ta sama regula, co w oknie Nowa kartoteka.

        Uzywamy subiekt_projekt.symbol_z_nazwy / rozroznij_symbol, bo tym
        samym generatorem zaklada kartoteki automat z projektu. Wlasna
        numeracja (KPL-001) rozjechalaby te sama pozycje na dwie rozne
        kartoteki w Subiekcie, zaleznie od tego, ktoredy zostala zalozona.
        """
        sym = self._zaznaczony
        if not sym or sym not in self.pozycje:
            messagebox.showinfo("Auto", "Zaznacz najpierw pozycję w drzewie.",
                                parent=self)
            return
        k = self.pozycje[sym]
        if k.w_subiekcie:
            messagebox.showinfo(
                "Auto", "„" + sym + "” jest już w Subiekcie — symbolu "
                "istniejącej kartoteki nie wolno zmieniać.", parent=self)
            return
        nazwa = (k.nazwa or "").strip()
        if not nazwa:
            messagebox.showinfo(
                "Auto", "Najpierw wpisz Nazwę — symbol powstaje z niej.",
                parent=self)
            self.pola["nazwa"][1].focus_set()
            return
        try:
            from subiekt_projekt import symbol_z_nazwy, rozroznij_symbol
        except Exception as e:
            messagebox.showerror("Auto", "Brak reguły generowania symbolu:\n"
                                 + str(e), parent=self)
            return

        # Zajete = kartoteki z Subiekta ORAZ pozycje juz w drzewie (poza ta
        # edytowana). Bez tego drugiego dwie nowe pozycje o podobnych nazwach
        # dostalyby ten sam symbol i jedna nadpisalaby druga przy zapisie.
        zajete = {str(p.get("Symbol") or "").strip().upper()
                  for p in self.katalog}
        zajete |= {s2.upper() for s2 in self.pozycje if s2 != sym}
        zajete.discard("")

        kandydat = symbol_z_nazwy(nazwa)
        rozrozniony = False
        if kandydat.upper() in zajete:
            kandydat = rozroznij_symbol(nazwa, zajete)
            rozrozniony = True
        if not kandydat:
            messagebox.showinfo(
                "Auto", "Z tej nazwy nie da się zbudować symbolu — "
                "wpisz go ręcznie.", parent=self)
            return
        if kandydat == sym:
            self.status.config(text="Symbol „" + sym + "” już wynika z nazwy",
                               fg=TEKST_SZARY)
            return
        self._zmien_symbol(sym, kandydat)
        self.status.config(
            text="Symbol z nazwy: „" + kandydat + "”"
                 + ("   (nazwa zajęta — użyto wyróżników)" if rozrozniony else ""),
            fg=TEKST_SZARY)

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

    #: Maski stanu klawiszy w evencie Tk: Shift = bit 0, Control = bit 2.
    MASKA_SHIFT = 0x0001
    MASKA_CTRL = 0x0004

    def _dnd_start(self, event):
        # Ctrl/Shift + klik to ZAZNACZANIE wielu wezlow (selectmode="extended"),
        # nie poczatek przeciagania. Bez tego proba zaznaczenia zakresu
        # konczyla sie przeniesieniem pozycji w drzewie (10.09.2026).
        if event.state & (self.MASKA_SHIFT | self.MASKA_CTRL):
            self._dnd_zrodlo = None
            self._dnd_start_xy = None
            self._dnd_aktywny = False
            return
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
        # Fokus na NAZWĘ, nie na symbol: symbol ma już wartość roboczą
        # („NOWA-01") i zwykle nadaje się go przyciskiem „Auto" Z NAZWY,
        # więc to nazwa jest pierwszą rzeczą do wpisania (09.09.2026).
        self.pola["nazwa"][1].focus_set()

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
        self.pola["nazwa"][1].focus_set()   # jak wyżej: najpierw nazwa

    def _dodaj_istniejaca(self):
        """Kartoteka z Subiekta jako składnik zaznaczonego kompletu."""
        wyb = self.tab_lista.selection()
        if not wyb:
            messagebox.showinfo("Edytor", "Zaznacz kartotekę na liście (sekcja 4).", parent=self)
            return
        _w, sym, naz, opis, rodzaj, _stan, cena = self.tab_lista.item(wyb[0], "values")
        rodzaj_n = ("komplet" if "omplet" in rodzaj else
                    "usluga" if "sług" in rodzaj or "slug" in rodzaj else "towar")
        if sym not in self.pozycje:
            try:
                cena_f = float(str(cena).replace(",", ".") or 0)
            except ValueError:
                cena_f = 0.0
            self.pozycje[sym] = Kartoteka(sym, naz, rodzaj_n, cena=cena_f,
                                          opis=str(opis or "").strip(),
                                          w_subiekcie=True)

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

    def _usun_wezel(self, _e=None):
        """Usuwa WSZYSTKIE zaznaczone wezly (Del albo przycisk "Usun").

        Kasujemy po jednym, w kolejnosci od najglebszych: usuniecie rodzica
        przebudowuje drzewo i identyfikatory jego dzieci przestaja istniec,
        wiec odwrotna kolejnosc sypalaby sie na polowie zaznaczenia.
        Pracujemy na SYMBOLACH plus symbol rodzica, bo tylko ta para jest
        stabilna miedzy przebudowami (item id juz nie).
        """
        zazn = list(self.tree.selection())
        if not zazn:
            return "break"
        # (glebokosc, symbol, symbol rodzica) — glebokosc liczymy PRZED
        # jakimkolwiek usunieciem, bo potem drzewo juz nie odpowiada.
        cele = []
        for it in zazn:
            sym = self._symbol_wezla(it)
            if not sym:
                continue
            gleb, p = 0, self.tree.parent(it)
            while p:
                gleb += 1
                p = self.tree.parent(p)
            rodzic_it = self.tree.parent(it)
            cele.append((gleb, sym, self._symbol_wezla(rodzic_it) if rodzic_it else None))
        if not cele:
            return "break"
        if len(cele) > 1 and not messagebox.askyesno(
                "Usunąć zaznaczone?",
                f"Zaznaczono {len(cele)} pozycji.\n\nUsunąć je z drzewa?",
                parent=self):
            return "break"
        for _gleb, sym, rodzic in sorted(cele, key=lambda c: -c[0]):
            self._usun_jeden(sym, rodzic)
        self._zaznaczony = None
        self._zmienione = True
        self._odswiez_drzewo()
        return "break"

    def _usun_jeden(self, sym, rodzic):
        """Usuwa jedno wystapienie `sym` spod `rodzic` (None = korzen).

        Wydzielone z _usun_wezel, zeby kasowanie wielu zaznaczonych
        wykonywalo dokladnie te sama logike co kasowanie jednego.
        """
        if sym not in self.pozycje:
            return
        if rodzic:
            # Usuwamy TYLKO to wystąpienie (relację) — kartoteka i pozostałe
            # wystąpienia zostają. To jest sedno modelu grafowego.
            for i, (r, d, il) in enumerate(self.relacje):
                if r == rodzic and d == sym:
                    self.relacje.pop(i)
                    break
            # ...ale jesli to bylo OSTATNIE wystapienie, pozycja nie moze
            # zostac w modelu: znika z drzewa, a i tak szlaby do walidacji
            # i do zapisu. Tak wlasnie pusty komplet blokowal zapis
            # komunikatem o pozycji, ktorej na ekranie juz nie bylo.
            self._sprzatnij_osierocona(sym)
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
                i, dziecko, (kd.nazwa or BEZ_NAZWY) if kd else "", f"{il:g}",
                kd.jm if kd else ""))

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

    def _wczytaj_z_pliku(self):
        """Wczytuje strukturę z pliku BOM-u: CSV (płaskie) albo *_OUT.xlsx (drzewko).

        Dwa formaty, bo tak wyglądają eksporty z Inventora:
          * CSV  — jedno złożenie, wszystkie wiersze to jego składniki.
            Tożsamość kompletu niesie NAZWA PLIKU („2622-200.81ZZ Zestaw
            Wagi.csv" → symbol „2622-200.81ZZ"), bo samego złożenia nie ma
            w wierszach.
          * XLSX — pełne drzewko z arkusza „DRZEWKO TEKST": wielopoziomowa
            struktura Z/ZZ z ilościami lokalnymi.

        Czytamy tymi samymi funkcjami co reszta systemu (subiekt_projekt,
        import_bom), żeby symbole i typy powstawały wszędzie tak samo.
        """
        sciezka = filedialog.askopenfilename(
            parent=self, title="Wybierz plik BOM-u",
            filetypes=[("BOM — CSV lub Excel", "*.csv *.xlsx"),
                       ("CSV (płaskie złożenie)", "*.csv"),
                       ("Excel *_OUT.xlsx (drzewko)", "*.xlsx"),
                       ("Wszystkie pliki", "*.*")])
        if not sciezka:
            return

        try:
            if sciezka.lower().endswith(".csv"):
                pozycje, relacje, korzenie = self._z_csv(sciezka)
            else:
                pozycje, relacje, korzenie = self._z_xlsx(sciezka)
        except Exception as e:
            komunikat_ed(self, "Z pliku",
                         f"Nie udało się odczytać pliku:\n\n{e}", rodzaj="error")
            return

        if not pozycje:
            komunikat_ed(self, "Z pliku",
                         "W pliku nie ma pozycji z numerem rysunku ani nazwą.",
                         rodzaj="warn")
            return

        # Dokładamy do tego, co już jest — user może złożyć strukturę
        # z kilku plików. Symbol już obecny zostaje nietknięty (jego dane
        # mogły być ręcznie poprawione), dopisujemy tylko brakujące relacje.
        nowe = 0
        for sym, kart in pozycje.items():
            if sym not in self.pozycje:
                self.pozycje[sym] = kart
                nowe += 1
        for r in relacje:
            if r not in self.relacje:
                self.relacje.append(r)
        for k in korzenie:
            if k not in self.korzenie and not any(d == k for _r, d, _i in self.relacje):
                self.korzenie.append(k)

        self._odswiez_drzewo()
        self._aktualizuj_przycisk_zapisu()
        komunikat_ed(
            self, "Z pliku",
            f"Wczytano {nowe} nowych pozycji z:\n{os.path.basename(sciezka)}\n\n"
            f"Złożeń (KT): {sum(1 for k in pozycje.values() if k.czy_komplet())}\n"
            f"Powiązań w składzie: {len(relacje)}")

    def _z_csv(self, sciezka):
        """({symbol: Kartoteka}, [(rodzic, dziecko, ilość)], [korzenie]) z CSV."""
        from subiekt_projekt import read_items_csv, tree_z_csv
        items = read_items_csv(sciezka)
        kids, _nazwy, sym_zl, naz_zl = tree_z_csv(sciezka, items)

        pozycje, relacje = {}, []
        for it in items:
            sym = (it["nr"] or "").strip()
            if not sym:
                continue
            pozycje[sym] = Kartoteka(
                sym, it.get("nazwa") or "",
                "komplet" if str(it.get("typ", "")).upper() in ("Z", "ZZ") else "towar",
                "kpl" if str(it.get("typ", "")).upper() in ("Z", "ZZ") else "szt")

        # Samo złożenie nie jest wierszem CSV — dopisujemy je z nazwy pliku.
        if sym_zl and sym_zl not in pozycje:
            pozycje[sym_zl] = Kartoteka(sym_zl, naz_zl or "", "komplet", "kpl")
        elif sym_zl:
            pozycje[sym_zl].rodzaj = "komplet"
            pozycje[sym_zl].jm = "kpl"

        for rodzic, dzieci in (kids or {}).items():
            r = self._symbol_jak_w(pozycje, rodzic)
            for dziecko, ilosc in dzieci:
                d = self._symbol_jak_w(pozycje, dziecko)
                if r and d:
                    relacje.append((r, d, float(ilosc or 1)))
        return pozycje, relacje, [sym_zl] if sym_zl else []

    def _z_xlsx(self, sciezka):
        """({symbol: Kartoteka}, [(rodzic, dziecko, ilość)], [korzenie]) z *_OUT.xlsx."""
        from pathlib import Path
        from import_bom import find_assembly_tree_rows, infer_type_from_drawing_no

        wiersze = find_assembly_tree_rows(Path(sciezka))
        if not wiersze:
            # find_assembly_tree_rows zwraca [] z KILKU powodow i sam ich nie
            # rozroznia. Bez tego user dostawal zawsze "nie ma arkusza
            # DRZEWKO TEKST" — takze gdy plik byl otwarty w Excelu albo
            # brakowalo openpyxl w .exe. Mowimy, co naprawde zaszlo.
            try:
                from import_bom import ostatni_blad_drzewka
                przyczyna = ostatni_blad_drzewka()
            except Exception:
                przyczyna = None
            if przyczyna:
                raise ValueError(
                    f"Nie da się otworzyć tego pliku.\n\n{przyczyna}\n\n"
                    "Najczęstsze przyczyny: plik jest otwarty w Excelu,\n"
                    "leży na niedostępnym dysku sieciowym albo jest uszkodzony.")

            # Plik otwarty poprawnie, tylko bez naszego arkusza — wypisujemy,
            # co w nim JEST, zeby user od razu widzial, czy wybral zly plik.
            nazwy = []
            try:
                import openpyxl
                _wb = openpyxl.load_workbook(Path(sciezka), read_only=True)
                try:
                    nazwy = list(_wb.sheetnames)
                finally:
                    _wb.close()
            except Exception:
                pass
            maja = ("\n\nArkusze w tym pliku: " + ", ".join(nazwy)) if nazwy else ""
            raise ValueError(
                "W tym pliku nie ma arkusza „DRZEWKO TEKST”"
                " (albo brakuje w nim kolumn\n"
                "Poziom / Nr rysunku / Nazwa / Ścieżka)."
                f"{maja}\n\n"
                "Wybierz plik *_OUT.xlsx wyeksportowany z Inventora\n"
                "albo płaski CSV jednego złożenia.")

        def rodzaj_z(nr, typ):
            t = (typ or "").upper()
            if "Z" in t and "ZNORMALIZOWANE" not in t:
                return "komplet"
            return "komplet" if str(infer_type_from_drawing_no(nr) or "").upper() in ("Z", "ZZ") else "towar"

        pozycje, relacje, dzieci = {}, [], set()
        for w in wiersze:
            nr = (w.get("nr_rysunku") or "").strip()
            if not nr:
                continue
            if nr not in pozycje:
                rodz = rodzaj_z(nr, w.get("typ"))
                pozycje[nr] = Kartoteka(nr, (w.get("nazwa") or "").strip(),
                                        rodz, "kpl" if rodz == "komplet" else "szt")
            sciezka_w = w.get("sciezka") or []
            if len(sciezka_w) >= 2:
                rodzic = (sciezka_w[-2] or "").strip()
                if rodzic:
                    try:
                        ile = float(w.get("ilosc_lokalna") or 1)
                    except (TypeError, ValueError):
                        ile = 1.0
                    if (rodzic, nr, ile) not in relacje:
                        relacje.append((rodzic, nr, ile))
                    dzieci.add(nr.upper())
                    # Rodzic z drzewka musi istnieć w modelu, nawet gdy nie ma
                    # własnego wiersza (bywa tylko w ścieżkach).
                    if rodzic not in pozycje:
                        pozycje[rodzic] = Kartoteka(rodzic, "", "komplet", "kpl")
                    else:
                        pozycje[rodzic].rodzaj = "komplet"
                        pozycje[rodzic].jm = "kpl"

        # MATKA JEST JUŻ W DRZEWKU — plik OUT zawiera całe złożenie razem
        # z nadrzędnym, więc korzeń wychodzi naturalnie jako ten symbol,
        # który nie jest niczyim dzieckiem. Nie dokładamy nic z nazwy pliku
        # (inaczej niż w CSV, gdzie samego złożenia w wierszach nie ma).
        korzenie = [s for s in pozycje if s.upper() not in dzieci]
        return pozycje, relacje, korzenie

    @staticmethod
    def _symbol_jak_w(pozycje, symbol):
        """Symbol w takiej postaci, w jakiej trafił do modelu (bez różnic wielkości liter)."""
        s = (symbol or "").strip()
        if s in pozycje:
            return s
        for k in pozycje:
            if k.upper() == s.upper():
                return k
        return None

    # ── PLAN I ZAPIS ────────────────────────────────────────────────────

    def _zbuduj_plan(self):
        pozycje = []
        # Tylko to, co widac w drzewie — patrz _osadzone().
        for sym in self._osadzone():
            k = self.pozycje[sym]
            skl = [{"symbol": d, "ilosc": il} for (r, d, il) in self.relacje if r == sym]
            pozycje.append(k.do_planu(skl if k.czy_komplet() else None))
        return {"pozycje": pozycje}

    def _aktualizuj_przycisk_zapisu(self):
        self.btn_zapisz.config(state=tk.NORMAL if self.pozycje else tk.DISABLED)
        self._aktualizuj_przycisk_pozycji()

    def _aktualizuj_przycisk_pozycji(self):
        """Zapis pojedynczej pozycji ma sens tylko, gdy coś jest zaznaczone."""
        btn = getattr(self, "btn_zapisz_pozycje", None)
        if btn is None:          # panel jeszcze nie zbudowany
            return
        aktywny = bool(self._zaznaczony and self._zaznaczony in self.pozycje)
        btn.config(state=tk.NORMAL if aktywny else tk.DISABLED)

    def _plan_pozycji(self, sym):
        """Plan dla JEDNEJ kartoteki — ten sam kształt, co _zbuduj_plan().

        Skład dołączamy tylko kompletom: dla towaru klucz "skladniki"
        w ogóle nie powstaje, więc most nie ruszy niczego poza polami
        samej kartoteki.
        """
        k = self.pozycje[sym]
        skl = [{"symbol": d, "ilosc": il} for (r, d, il) in self.relacje if r == sym]
        return {"pozycje": [k.do_planu(skl if k.czy_komplet() else None)]}

    def _waliduj_pozycje(self, sym):
        """Błędy blokujące zapis tej jednej kartoteki."""
        bledy = []
        k = self.pozycje[sym]
        if not sym.strip():
            bledy.append("pozycja bez symbolu")
        if not (k.nazwa or "").strip():
            bledy.append(f"„{sym}” nie ma nazwy — uzupełnij pole Nazwa")
        if k.czy_komplet() and not self._dzieci(sym):
            bledy.append(f"„{sym}” to komplet bez składników — Subiekt go odrzuci")
        return bledy

    def _zapisz_pozycje(self):
        """Wysyła do Subiekta wyłącznie kartotekę zaznaczoną w drzewie."""
        sym = self._zaznaczony
        if not sym or sym not in self.pozycje:
            messagebox.showinfo("Zapis pozycji",
                                "Zaznacz najpierw pozycję w drzewie.", parent=self)
            return
        bledy = self._waliduj_pozycje(sym)
        if bledy:
            messagebox.showwarning("Zapis pozycji",
                                   "\n".join(f"• {b}" for b in bledy), parent=self)
            return
        # Składniki kompletu muszą już być w Subiekcie — most nie założy
        # ich przy okazji, bo do planu idzie tylko ta jedna pozycja.
        k = self.pozycje[sym]
        if k.czy_komplet():
            brak = [d for d, _il in self._dzieci(sym)
                    if d in self.pozycje and not self.pozycje[d].w_subiekcie]
            if brak:
                lista = "\n".join(f"• {b}" for b in brak[:12])
                wiecej = f"\n… i {len(brak) - 12} więcej" if len(brak) > 12 else ""
                messagebox.showwarning(
                    "Zapis pozycji",
                    f"„{sym}” to komplet, a te składniki nie są jeszcze "
                    f"w Subiekcie:\n\n{lista}{wiecej}\n\n"
                    "Zapis pojedynczej pozycji ich nie założy — użyj "
                    "„Załóż / Zapisz” dla całego drzewa.",
                    parent=self)
                return
        if not self._potwierdz_zapis_pozycji(sym):
            return
        self.start_kreciolek(f"Zapisuję {sym}")
        threading.Thread(target=self._zapis_worker,
                         args=(self._plan_pozycji(sym), True, sym),
                         daemon=True).start()

    def _potwierdz_zapis_pozycji(self, sym):
        """Okno ze zmianami dla jednej kartoteki. True = user potwierdził."""
        k = self.pozycje[sym]
        nowa = not k.w_subiekcie
        dzieci = self._dzieci(sym) if k.czy_komplet() else []

        okno = tk.Toplevel(self)
        okno.title("Zapis pozycji do Subiekta")
        okno.configure(bg=TLO)
        okno.geometry("640x520")
        okno.transient(self)
        self.after_idle(lambda: wysrodkuj(okno, self))

        tk.Label(okno, text=("Zostanie ZAŁOŻONA nowa kartoteka"
                             if nowa else "Zostanie ZMIENIONA istniejąca kartoteka"),
                 bg=TLO, fg=(NOWY_NIEBIESKI if nowa else TEKST),
                 font=("Arial", 12, "bold"), anchor="w").pack(
            fill=tk.X, padx=14, pady=(12, 2))

        ramka = tk.Frame(okno, bg=TLO_SEKCJI, bd=1, relief="solid")
        ramka.pack(fill=tk.X, padx=14, pady=8)
        wiersze = [("Symbol", k.symbol),
                   ("Nazwa", k.nazwa or BEZ_NAZWY),
                   ("Rodzaj", dict((e, w) for e, w in RODZAJE).get(k.rodzaj, k.rodzaj)),
                   ("Jednostka", k.jm),
                   ]
        # Cene pokazujemy TYLKO gdy naprawde pojdzie do Subiekta — zero jest
        # pomijane w do_planu(), wiec wypisanie "0,00" obiecywaloby zmiane,
        # ktorej nie bedzie.
        if k.cena:
            wiersze.append(("Cena ewid.", f"{k.cena:.2f}".replace(".", ",")))
        else:
            wiersze.append(("Cena ewid.", "bez zmian (nie ruszamy)"))
        if k.vat_sprzedaz:
            wiersze.append(("VAT sprzedaży", k.vat_sprzedaz))
        if k.vat_zakup:
            wiersze.append(("VAT zakupu", k.vat_zakup))
        if k.polozenie is not None:
            wiersze.append(("Położenie", k.polozenie or "(puste)"))
        if (k.opis or "").strip():
            skrot = k.opis.strip().replace("\n", " ")
            wiersze.append(("Opis", skrot[:70] + ("…" if len(skrot) > 70 else "")))
        for i, (etykieta, wartosc) in enumerate(wiersze):
            tk.Label(ramka, text=etykieta + ":", bg=TLO_SEKCJI, fg=TEKST_SZARY,
                     font=("Arial", 9), anchor="w", width=14).grid(
                row=i, column=0, sticky="w", padx=(10, 4), pady=3)
            tk.Label(ramka, text=str(wartosc), bg=TLO_SEKCJI, fg=TEKST,
                     font=("Arial", 9, "bold"), anchor="w").grid(
                row=i, column=1, sticky="w", padx=4, pady=3)
        ramka.grid_columnconfigure(1, weight=1)

        if k.czy_komplet():
            tk.Label(okno, text=f"Skład kompletu — {len(dzieci)} składników "
                                f"(zostanie USTAWIONY na dokładnie tę listę):",
                     bg=TLO, fg=TEKST, font=("Arial", 9, "bold"), anchor="w").pack(
                fill=tk.X, padx=14, pady=(6, 2))
            wrap = tk.Frame(okno, bg=TLO_SEKCJI)
            wrap.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 4))
            lista = ttk.Treeview(wrap, columns=("nazwa", "ilosc"), show="tree headings",
                                 style="Edytor.Treeview", height=8)
            lista.heading("#0", text="Symbol")
            lista.heading("nazwa", text="Nazwa")
            lista.heading("ilosc", text="Ilość")
            lista.column("#0", width=170, stretch=False)
            lista.column("ilosc", width=60, anchor="e", stretch=False)
            sc = ttk.Scrollbar(wrap, orient="vertical", command=lista.yview)
            lista.configure(yscrollcommand=sc.set)
            lista.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sc.pack(side=tk.RIGHT, fill=tk.Y)
            for d, il in dzieci:
                kd = self.pozycje.get(d)
                lista.insert("", "end", text=d,
                             values=((kd.nazwa if kd else "") or "", f"x{il:g}"))
        else:
            tk.Label(okno, text="Towar — skład kompletu nie jest ruszany.",
                     bg=TLO, fg=TEKST_SZARY, font=("Arial", 9), anchor="w").pack(
                fill=tk.X, padx=14, pady=(6, 2))

        tk.Label(okno, text=("Puste pola NIE kasują danych w Subiekcie — "
                             "brak wartości znaczy „nie ruszaj”."),
                 bg="#eaf2f8", fg=TEKST_SZARY, font=("Arial", 8),
                 justify="left", anchor="w").pack(fill=tk.X, padx=14, pady=(4, 2))

        # Stopka PRZED obszarem rozciągliwym — inaczej przyciski wypadają
        # poza okno przy małej wysokości (ta sama pułapka co w raporcie).
        wynik = {"ok": False}

        def zatwierdz():
            wynik["ok"] = True
            okno.destroy()

        stopka = tk.Frame(okno, bg=TLO)
        stopka.pack(fill=tk.X, side=tk.BOTTOM, padx=14, pady=10)
        tk.Button(stopka, text="Anuluj", command=okno.destroy,
                  font=("Arial", 9), padx=14, pady=4).pack(side=tk.RIGHT)
        tk.Button(stopka, text=("Załóż w Subiekcie" if nowa else "Zapisz zmiany"),
                  command=zatwierdz, bg="#27ae60", fg="white",
                  font=("Arial", 9, "bold"), padx=14, pady=4).pack(
            side=tk.RIGHT, padx=(0, 8))

        wysrodkuj(okno, self)
        okno.grab_set()
        self.wait_window(okno)
        return wynik["ok"]

    def _osadzone(self):
        """Symbole faktycznie widoczne w drzewie — od korzeni w dol.

        Model moze przejsciowo trzymac pozycje, ktora wypadla ze struktury.
        Do walidacji i do zapisu bierzemy tylko to, co user naprawde widzi.
        """
        widoczne = []

        def idz(sym, sciezka):
            if sym in sciezka or sym not in self.pozycje:
                return
            if sym not in widoczne:
                widoczne.append(sym)
            for d, _il in self._dzieci(sym):
                idz(d, sciezka | {sym})

        for sym in self.korzenie:
            idz(sym, set())
        return widoczne

    def _waliduj(self):
        """Błędy, które nie mają sensu wysyłać do Subiekta."""
        bledy = []
        for sym in self._osadzone():
            k = self.pozycje[sym]
            if not sym.strip():
                bledy.append("pozycja bez symbolu")
            if not (k.nazwa or "").strip():
                bledy.append(f"„{sym}” nie ma nazwy — uzupełnij pole Nazwa")
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
        for sym in self._osadzone():
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
        # Na srodku okna matki, nie ekranu — na trzech monitorach Tk stawialby
        # je na monitorze glownym, czyli nie tam, gdzie stoi Edytor.
        self.after_idle(lambda: wysrodkuj(okno, self))

        # Liczniki z tego, co OSADZONE w drzewie — musza zgadzac sie
        # z lista ponizej i z tym, co naprawde pojdzie do Subiekta.
        osadzone = self._osadzone()
        nowe = [s for s in osadzone if not self.pozycje[s].w_subiekcie]
        istn = [s for s in osadzone if self.pozycje[s].w_subiekcie]
        komplety = [s for s in osadzone
                    if self.pozycje[s].czy_komplet() and self._dzieci(s)]

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
        kol = ("typ", "nazwa", "ilosc", "co")
        tab = ttk.Treeview(wrap, columns=kol, show="tree headings",
                           style="Edytor.Treeview")
        tab.heading("#0", text="Symbol")
        tab.heading("typ", text="Typ")
        tab.column("typ", width=38, minwidth=38, anchor="center", stretch=False)
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
                rodzic_id, "end", text=symbol,
                values=(SKROT.get(k.rodzaj, "??"), k.nazwa or BEZ_NAZWY,
                        f"x{ilosc:g}" if ilosc else "", co),
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

    def _zapis_worker(self, plan, zapisz, tylko_sym=None):
        try:
            wynik, blad = zapisz_kartoteki(plan, zapisz), None
        except Exception as e:
            wynik, blad = None, str(e)
        self.after(0, lambda: self._zapis_gotowy(wynik, blad, zapisz, tylko_sym))

    def _zapis_gotowy(self, wynik, blad, zapisz, tylko_sym=None):
        self.stop_kreciolek()
        if blad:
            messagebox.showerror("Subiekt", blad, parent=self)
            return
        kroki = wynik.get("kroki") or []
        bledy = [k for k in kroki if "blad" in str(k.get("Status", ""))]
        self._pokaz_raport(wynik, kroki, bledy, zapisz)
        if zapisz and not bledy:
            # Po udanym zapisie symbole blokujemy — ale tylko tym pozycjom,
            # ktore faktycznie poszly. Przy zapisie pojedynczej pozycji jest
            # to WYŁĄCZNIE ona: reszta drzewa nie została wysłana i musi
            # dalej uchodzić za niezapisaną.
            if tylko_sym:
                if tylko_sym in self.pozycje:
                    self.pozycje[tylko_sym].w_subiekcie = True
                self._odswiez_drzewo()
                self._zaznacz_w_drzewie(tylko_sym)
                self.status.config(
                    text=f"✔ Zapisano do Subiekta: {tylko_sym}", fg=OK_ZIELONY)
                return
            for sym in self._osadzone():
                self.pozycje[sym].w_subiekcie = True
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
        okno.geometry("1040x560")
        okno.transient(self)
        self.after_idle(lambda: wysrodkuj(okno, self))

        # Waga kazdego statusu — decyduje o kolorze tla wiersza.
        wagi = [WAGA_STATUSU.get(str(k.get("Status") or ""), "info") for k in kroki]
        ile = {w: wagi.count(w)
               for w in ("uwaga", "nadpisanie", "nowe", "zmiana", "info")}

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
        for waga, etykieta in (("uwaga", "wymaga uwagi"),
                               ("nadpisanie", "nadpisanie danych z Subiekta"),
                               ("nowe", "nowe w Subiekcie"),
                               ("zmiana", "uzupełnienie składu"),
                               ("info", "bez zmian")):
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
        # Szczegoly rosna razem z oknem — to najdluzsza tresc i to ona
        # odpowiada na pytanie "co sie zmieni", wiec nie moze byc obcieta.
        for k, naz, sz, rozciag in (("rodzaj", "Co", 90, False),
                                    ("symbol", "Symbol", 150, False),
                                    ("status", "Status", 150, False),
                                    ("szczegoly", "Szczegóły", 620, True)):
            tab.heading(k, text=naz)
            tab.column(k, width=sz, minwidth=70, stretch=rozciag)
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

        # Kolumna "Co": dla kroku kartoteki pokazujemy RODZAJ POZYCJI
        # (Towar/Komplet/Usluga), bo "kartoteka" nic nie mowilo — rodzaj
        # kroku mostu jest tu bez znaczenia dla czytajacego.
        etykiety = dict((w, e) for e, w in RODZAJE)

        def co_to(krok):
            rodzaj_kroku = str(krok.get("Rodzaj") or "")
            if rodzaj_kroku != "kartoteka":
                return "skład"
            poz = self.pozycje.get(str(krok.get("Symbol") or ""))
            r = poz.rodzaj if poz else ""
            return etykiety.get(r, r or rodzaj_kroku)

        for k, waga in zip(kroki, wagi):
            tab.insert("", "end", values=(co_to(k), k.get("Symbol"),
                                          str(k.get("Status") or ""),
                                          k.get("Szczegoly") or ""), tags=(waga,))
        # Dymek z pelna trescia wiersza — niezalezny od szerokosci okna.
        dymek = {"okno": None}

        def schowaj_dymek(_e=None):
            if dymek["okno"] is not None:
                dymek["okno"].destroy()
                dymek["okno"] = None

        def pokaz_dymek(e):
            wiersz = tab.identify_row(e.y)
            if not wiersz:
                schowaj_dymek()
                return
            if dymek.get("wiersz") == wiersz and dymek["okno"] is not None:
                return
            schowaj_dymek()
            dymek["wiersz"] = wiersz
            w_ = tab.item(wiersz, "values")
            if len(w_) < 4:
                return
            tresc = f"{w_[0]}  {w_[1]}\n{w_[2]}"
            if w_[3]:
                tresc += f"\n\n{w_[3]}"
            d = tk.Toplevel(tab)
            d.wm_overrideredirect(True)
            d.wm_geometry(f"+{e.x_root + 16}+{e.y_root + 18}")
            tk.Label(d, text=tresc, bg="#ffffe0", fg=TEKST, font=("Arial", 9),
                     justify="left", anchor="w", relief="solid", bd=1,
                     wraplength=560, padx=8, pady=6).pack()
            dymek["okno"] = d

        tab.bind("<Motion>", pokaz_dymek)
        tab.bind("<Leave>", schowaj_dymek)
        okno.bind("<Destroy>", lambda _e: schowaj_dymek(), add="+")

        def kopiuj(_e=None):
            """Ctrl+C — zaznaczone wiersze (albo caly raport) do schowka."""
            wybrane = tab.selection() or tab.get_children("")
            linie = ["\t".join(str(x) for x in tab.item(i, "values"))
                     for i in wybrane]
            okno.clipboard_clear()
            okno.clipboard_append("\n".join(linie))

        tab.bind("<Control-c>", kopiuj)

        pb = tk.Frame(okno, bg=TLO)
        pb.pack(fill=tk.X, padx=12, pady=(0, 10))
        tk.Label(pb, text="Najedź na wiersz, żeby zobaczyć całą treść. "
                         "Ctrl+C kopiuje zaznaczone.",
                 bg=TLO, fg=TEKST_SZARY, font=("Arial", 8)).pack(side=tk.LEFT)
        tk.Button(pb, text="Kopiuj wszystko", command=lambda: (tab.selection_remove(
                      *tab.selection()), kopiuj()), font=("Arial", 9)).pack(
            side=tk.RIGHT, padx=(6, 0))
        tk.Button(pb, text="Zamknij", command=okno.destroy,
                  font=("Arial", 9), padx=10).pack(side=tk.RIGHT)
        wysrodkuj(okno, self)


def open_window(parent, symbol=None):
    """Otwiera Edytor kartotek. symbol != None → tryb edycji istniejącej."""
    return EdytorWindow(parent, symbol=symbol)
