# -*- coding: utf-8 -*-
"""
Przegląd dokumentów Subiekta: ZK, ZD, PW, RW, WZ — z pozycjami.

    import subiekt_dokumenty_gui
    subiekt_dokumenty_gui.open_window(parent)

Po co: RM_BAZA potrafi już zakładać ZK i tworzyć ZD, ale nie było gdzie
zobaczyć, co w Subiekcie realnie jest. Żeby sprawdzić stan projektu, trzeba
było przełączać się do Subiekta i filtrować listy ręcznie.

Układ dwupanelowy, OBOK SIEBIE:
  * lewa   — lista dokumentów (rodzaj, numer, data, podmiot, projekt, pozycje),
  * prawa  — pozycje klikniętego dokumentu albo WSZYSTKIE płasko.

Panele stoją w poziomie, nie w pionie: dokumentów bywa 31, a pozycji
w jednym ZK ponad 180, więc dzielenie wysokości znaczyło, że w obu tabelach
widać po kilka wierszy.

Wyszukiwarka działa na OBU poziomach: wpisanie numeru rysunku pokazuje
dokumenty, które go zawierają — po tym widać, na którym ZK/ZD siedzi dana
część i czy została już wydana. Przełącznik „Wszystkie pozycje" spłaszcza
dokumenty w jedną listę (z kolumnami Dokument i Rodzaj), żeby szukać detalu
bez zgadywania, w którym dokumencie siedzi.

Dane idą jednym wywołaniem mostu (~9 s): pozycje przychodzą razem
z nagłówkami, bo most jest bezstanowy i pytanie o każdy dokument osobno
kosztowałoby tyle samo co całość.
"""

import json
import os
import sqlite3
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

from rm_kreciolek import Kreciolek
from subiekt_stany import (_find_exe, blad_mostu, wysrodkuj,
                           podepnij_szerokosci, CONFIG_PATH)

try:
    from tksheet import Sheet
except ImportError:
    Sheet = None

TIMEOUT_S = 300

RODZ_WSZYSTKIE = "— wszystkie —"
RODZAJE = ["ZK", "ZD", "PW", "RW", "WZ"]
OPIS_RODZAJU = {
    "ZK": "ZK — lista projektu",
    "ZD": "ZD — zamówienie do dostawcy",
    # PW stoi PRZED RW, bo taka jest kolejność w torze produkcji: najpierw
    # przyjmujemy z warsztatu na magazyn, potem wydajemy na projekt.
    "PW": "PW — przyjęcie z produkcji własnej",
    "RW": "RW — wydanie na produkcję",
    "WZ": "WZ — wydanie zewnętrzne",
}
PROJ_WSZYSTKIE = "— wszystkie —"
PROJ_BEZ = "(bez projektu)"


def pobierz_dokumenty(limit=200, timeout=TIMEOUT_S):
    """[{rodzaj, numer, data, podmiot, tytul, uwagi, status, wartosc, pozycje}].

    Idzie przez stały most; gdy mostu nie ma, starym CLI.
    """
    try:
        import subiekt_bridge
    except ImportError:
        return _przelicz_dokumenty(_pobierz_dokumenty_cli(limit, timeout))

    dane = subiekt_bridge.call(
        "dokumenty", {"limit": limit}, timeout=timeout,
        fallback=lambda: _pobierz_dokumenty_cli(limit, timeout))
    return _przelicz_dokumenty(dane)


def _pobierz_dokumenty_cli(limit, timeout):
    """Stara ścieżka: osobny proces NexoRecon.exe na każde wywołanie."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")

    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="subiekt_dok_")
    out = os.path.join(tmpdir, "dok.json")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run([exe, "dokumenty", f"--limit={limit}", f"--out={out}"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=flags)
    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, "dokumenty", proc, out))

    with open(out, encoding="utf-8") as f:
        return json.load(f)


def _przelicz_dokumenty(data):
    """Surowa odpowiedź mostu -> format okna przeglądu dokumentów."""
    # Jedna reguła czytania Uwag dla całego programu — patrz docstring tam.
    from subiekt_zamowienia import numer_projektu_z_uwag, uwagi_czlowieka
    wynik = [{
        "rodzaj": d.get("Rodzaj") or "",
        "numer": d.get("Numer") or "",
        # Id z Subiekta — TRWAŁY klucz dokumentu. Numer wraca do obiegu po
        # usunięciu (07.09.2026), więc dziennik wysyłek trzyma się Id.
        "Id": d.get("Id") or 0,
        "data": d.get("Data") or "",
        "podmiot": (d.get("Podmiot") or "").strip(),
        "tytul": _tytul_czytelny(d.get("Tytul")),
        # Kolumna Projekt bierze PIERWSZY CZŁON Uwag — reszta pierwszego wiersza
        # („Projekt") i wiersze niżej to treść dla człowieka, nie numer.
        # Całe Uwagi zostają osobno, żeby dało się je pokazać w szczegółach.
        "projekt": numer_projektu_z_uwag(d.get("Uwagi")),
        "uwagi": (d.get("Uwagi") or "").strip(),
        "status": d.get("Status") or "",
        # Termin dostawy — ta sama nazwa co kolumna w arkuszu głównym RM_BAZA.
        # Mają go tylko zamówienia; przy WZ/RW zostaje pusty.
        "termin": d.get("Termin") or "",
        "magazyn": d.get("Magazyn") or "",
        "wartosc": float(d.get("Wartosc") or 0),
        "pozycje": [{
            "symbol": p.get("Symbol") or "",
            "nazwa": p.get("Nazwa") or "",
            # Opis z kartoteki asortymentu (wymiary, gatunek, norma). Stare
            # mosty tego pola nie zwracają — pusty string, kolumna po prostu
            # zostaje pusta i nic się nie wywraca.
            "opis": p.get("Opis") or "",
            "ilosc": float(p.get("Ilosc") or 0),
            "jm": p.get("Jm") or "szt",
            "cena": float(p.get("Cena") or 0),
            # Koszt magazynowy — dla PW/RW/WZ to ON niesie wartość. „Cena
            # netto" jest parametrem HANDLOWYM i na dokumencie magazynowym
            # bywa zerowa: RW 1/MASTER/2026 miało cenę 0, a koszt 4848 zł
            # (10.09.2026). Subiekt liczy koszt sam z ceny przyjęcia.
            "koszt_jedn": float(p.get("KosztJedn") or 0),
            "koszt": float(p.get("Koszt") or 0),
            # Projekt pozycji z Uwag ZK, którą realizuje — „2632, 3000" gdy
            # jedno ZD zbiera detale z kilku projektów. Tylko przy ZD.
            "projekt": p.get("Projekt") or "",
            # Id pozycji i ilość DO REALIZACJI — dla okna przyjęcia dostawy,
            # które wskazuje Sferze konkretne pozycje ZD do przyjęcia
            # (WypelnijNaPodstawieZD). Stare mosty ich nie zwracają → 0.
            "id": int(p.get("Id") or 0),
            "do_realizacji": float(p.get("DoRealizacji") or 0),
        } for p in (d.get("Pozycje") or [])],
    } for d in data.get("dokumenty", [])]

    # Projekt NAGŁÓWKA dla ZD: Uwagi zamówienia do dostawcy są puste (numer
    # projektu RM_BAZA wpisuje na ZK, nie na ZD), więc kolumna „Projekt”
    # świeciła pustką przy wszystkich ZD poza magazynowym — nie było widać,
    # pod co idzie zamówienie (zgłoszone 05.09.2026). Most zwraca projekt PER
    # POZYCJA (z Uwag realizowanej ZK), więc tutaj tylko go scalamy.
    # Jedno ZD potrafi zbierać detale z kilku projektów — stąd „2632, 3000”.
    for d in wynik:
        # Dokumenty MAGAZYNOWE (ZD na skład, RW zdjęcia ze stanu) mają w Uwagach
        # „MAGAZYN" albo „MAGAZYN: powód". Do kolumny Projekt i filtra idzie
        # sam znacznik, powód ląduje w Tytule — inaczej filtr projektów
        # rozmnażałby się o każdy wpisany powód.
        if d["projekt"].upper().startswith(UWAGI_MAGAZYN):
            # Powód stoi za znacznikiem: w tym samym wierszu („MAGAZYN: brak
            # miejsca") albo — po zmianie formatu Uwag — wierszem niżej.
            reszta = (d["uwagi"].strip()[len(UWAGI_MAGAZYN):].lstrip(" :").strip()
                      or uwagi_czlowieka(d["uwagi"]))
            d["projekt"] = UWAGI_MAGAZYN
            if reszta:
                d["tytul"] = reszta
            continue
        if d["projekt"]:
            continue
        z_pozycji = []
        for poz in d["pozycje"]:
            for nr in (poz.get("projekt") or "").split(","):
                nr = nr.strip()
                if nr and nr not in z_pozycji:
                    z_pozycji.append(nr)
        if z_pozycji:
            d["projekt"] = ", ".join(sorted(z_pozycji))
    return wynik


#: Uwagi ZD zalozonego z okna magazynu — zakup na sklad, bez projektu.
#: Ta sama wartosc co subiekt_magazyn_gui.UWAGI_MAGAZYN.
UWAGI_MAGAZYN = "MAGAZYN"


def _numery_projektow(d):
    """Numery projektow dokumentu — Uwagi ZD bywaja zbiorcze („2627,3500")."""
    return [n.strip() for n in str(d.get("projekt") or "").split(",") if n.strip()]

#: Domyślne nazwy typów, które Subiekt sam wstawia w pole Tytuł.
#:
#: Kolumna „Rodzaj" mówi już ZK / ZD / PW / RW / WZ, więc powtarzanie tego
#: słowami zjadało pół szerokości tabeli na zero informacji (zgłoszone
#: 11.09.2026: „przegląd dokumentów jest nieczytelny"). W kolumnie zostaje
#: tylko treść, którą ktoś wpisał świadomie — nasz znacznik „RM_BAZA <nr>"
#: albo opis wpisany ręcznie w Subiekcie.
TYTULY_DOMYSLNE = {
    "zamówienie od klienta", "zamówienie do dostawcy",
    "przychód wewnętrzny", "rozchód wewnętrzny",
    "wydanie zewnętrzne", "przyjęcie zewnętrzne",
    "faktura sprzedaży", "faktura zakupu",
}


def _tytul_czytelny(tytul):
    """Tytuł bez domyślnej nazwy typu — pusty, gdy nic ponadto nie niesie."""
    t = (tytul or "").strip()
    return "" if t.lower() in TYTULY_DOMYSLNE else t


class DokumentyWindow(tk.Toplevel, Kreciolek):
    KOL_DOK = [("rodzaj", "Rodzaj", 70), ("numer", "Numer", 130),
               ("data", "Data", 90), ("projekt", "Projekt", 80),
               ("podmiot", "Podmiot / dostawca", 250), ("tytul", "Tytuł", 130),
               ("pozycji", "Pozycji", 65), ("wartosc", "Wartość", 90),
               ("termin", "Termin dostawy", 100), ("wyslano", "Wysłano", 105),
               ("pdf", "PDF", 40), ("status", "Status", 140)]
    #: „Opis" to pole z KARTOTEKI asortymentu (wymiary, gatunek, norma) — stoi
    #: zaraz za Nazwą, bo razem czyta się je jako jeden opis pozycji. Sama
    #: nazwa bywa za krótka, żeby rozpoznać detal przy zamawianiu (zgłoszone
    #: 15.09.2026: „dodaj kolumnę Opis, bardzo jej brakuje").
    #: ⚠️ SUMA MUSI SIĘ MIEŚCIĆ W PRAWYM PANELU.
    #:
    #: Panel pozycji siedzi w PanedWindow z wagą 3 z 8, więc przy oknie
    #: 1250 px dostaje ~460 px, a zmaksymalizowanym na FullHD ~700 px.
    #: Suma 1090 px (do 02.10.2026) nie mieściła się NIGDY: „Cena netto"
    #: i „Wartość" uciekały poza prawą krawędź i trzeba było przewijać
    #: w bok, żeby zobaczyć kwoty — a to one są powodem, dla którego ktoś
    #: otwiera pozycje dokumentu.
    #:
    #: Teraz 690 px: mieści się przy zmaksymalizowanym oknie w całości,
    #: a przy wąskim zostaje do dojechania tylko „Wartość". Rozciąga się
    #: WYŁĄCZNIE „Nazwa" (jak w oknie wydania — jedna kolumna zbiera cały
    #: nadmiar, reszta stoi w miejscu).
    #:
    #: „Opis" jest w tych dokumentach prawie zawsze pusty (na zrzucie
    #: z 02.10.2026 wszystkie trzy pozycje RW miały go pustego), więc to
    #: on oddaje najwięcej: 260 → 90.
    KOL_POZ = [("symbol", "Nr rysunku / symbol", 150), ("nazwa", "Nazwa", 190),
               ("opis", "Opis", 90),
               ("ilosc", "Ilość", 50), ("jm", "J.m.", 40),
               ("cena", "Cena netto", 80), ("wartosc", "Wartość", 90)]
    #: Dokumenty MAGAZYNOWE: wartość niesie koszt magazynowy, nie cena netto
    #: (parametr handlowy, na PW/RW/WZ zwykle zerowy). Nagłówki zmieniają się
    #: razem z danymi, żeby kolumna nie kłamała o tym, co pokazuje.
    RODZAJE_MAGAZYNOWE = ("PW", "RW", "WZ")
    NAGL_KOSZT = ("Koszt jedn.", "Wartość magazynowa")

    def __init__(self, parent, szukaj=None, projekt=None):
        """`szukaj` — numer dokumentu do pokazania od razu po otwarciu.

        Uzywa tego okno wydania: klik w numer RW przy pozycji otwiera ten
        przeglad juz odfiltrowany do tego dokumentu i podswietla go
        (02.10.2026). Bez tego magazynier musial przepisywac numer recznie.
        """
        super().__init__(parent)
        from subiekt_stany import ukryj_do_zbudowania
        ukryj_do_zbudowania(self)      # pokazane dopiero zbudowane
        #: Numer do zaznaczenia po pierwszym wypelnieniu listy. Czyszczony
        #: po uzyciu, zeby kolejne „Odswiez" nie przeskakiwalo kursorem.
        self._do_zaznaczenia = (szukaj or "").strip() or None
        #: Numer projektu wybranego w RM_BAZA — filtr „Projekt" ustawiany nim
        #: przy PIERWSZYM wczytaniu (02.10.2026). Pomijany, gdy okno otwarto
        #: na konkretny dokument (`szukaj`), bo ten moze byc z innego projektu.
        self._projekt_startowy = (None if self._do_zaznaczenia
                                  else ((projekt or "").strip().split(" ")[0] or None))
        #: Kolejnosc pozycji jak w arkuszu RM_BAZA — {numer projektu: {KLUCZ: miejsce}}
        #: i {numer: project_id}. Czytane RAZ na okno (pakietem), nie per klik.
        self._kolejnosc_proj = {}
        self._pid_po_numerze = None
        self._poz_dok = None        # dokument pokazany w panelu pozycji
        self.dokumenty = []
        self.widoczne = []
        self.biezacy = None
        self._wyslane = {}          # {Id dokumentu: (kiedy, ile razy)} — kolumna „Wysłano”

        self.title("Subiekt — przegląd dokumentów (ZK / ZD / PW / RW / WZ)")
        self.geometry("1250x760")
        self.minsize(900, 450)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self._build_ui()
        self.after(100, self._load_async)

    # ── UI ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        top = tk.Frame(self, bg="#34495e", height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="📚 Dokumenty w Subiekcie — zamówienia i wydania",
                 bg="#34495e", fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)
        # Wiek odczytu — dane z Subiekta starzeją się, a nic tego nie pokazywało.
        self.lbl_wiek = tk.Label(top, text="", bg="#34495e", fg="#e74c3c",
                                 font=("Arial", 13, "bold"))
        self.lbl_wiek.pack(side=tk.LEFT, padx=(16, 0))
        self.btn_refresh = tk.Button(top, text="🔄 Odśwież", command=self._load_async,
                                     bg="#3498db", fg="white", font=("Arial", 8),
                                     padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_refresh.pack(side=tk.RIGHT, padx=10, pady=8)
        # Wspólny formularz nowej kartoteki (subiekt_asortyment) — tu bez
        # callbacku, bo przegląd nic nie buduje; kartoteka pojawi się w
        # dokumentach dopiero, gdy ktoś jej użyje.
        tk.Button(top, text="➕ Nowa kartoteka", command=self._nowa_kartoteka,
                  bg="#27ae60", fg="white", font=("Arial", 8),
                  padx=8, pady=2, relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=(0, 4), pady=8)
        # Kasowanie tego, co zaznaczone w tabeli. To okno widzi WSZYSTKIE typy
        # (ZK/ZD/RW/WZ), a most rozpoznaje rodzaj po prefiksie numeru, więc
        # jeden przycisk sprząta mieszany zaznaczony zestaw.
        #
        # ⚠️ ZD kasuj PRZED powiązanym ZK — inaczej Subiekt potrafi odmówić
        # usunięcia ZK. Okno potwierdzenia samo o tym przypomina, gdy w liście
        # są oba typy naraz.
        # Nazwa mówi WPROST, że chodzi o całe dokumenty — „Usuń zaznaczone"
        # myliło się z pozycjami (02.10.2026). Pozycję usuwa się prawym
        # klikiem w panelu pozycji („Usuń pozycję z ZK…").
        tk.Button(top, text="🗑 Usuń zaznaczone DOKUMENTY", command=self._usun_zaznaczone,
                  bg="#c0392b", fg="white", font=("Arial", 8),
                  padx=8, pady=2, relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=(0, 4), pady=8)
        # ⚠️ Przyciski dotyczące ZAZNACZONEGO dokumentu (Wyślij ZD, Podgląd PDF)
        # są w pasku filtrów NIŻEJ, nie tutaj. Pasek górny mieści tylko cztery
        # elementy — piąty wyjeżdżał poza prawą krawędź i zostawało z niego
        # ucięte „Podg…” (zgłoszone 05.09.2026).

        f = tk.Frame(self, bg="#ecf0f1")
        f.pack(side=tk.TOP, fill=tk.X)
        tk.Label(f, text="Szukaj:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(12, 3), pady=6)
        self.search_var = tk.StringVar(value=self._do_zaznaczenia or "")
        self.search_var.trace_add("write", lambda *_: self._refill_po_wpisaniu())
        tk.Entry(f, textvariable=self.search_var, width=26, font=("Arial", 9)).pack(side=tk.LEFT, pady=6)
        tk.Label(f, text="(numer rysunku, nazwa, numer dokumentu)", bg="#ecf0f1",
                 fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.LEFT, padx=(4, 0))

        tk.Label(f, text="Rodzaj:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(14, 3), pady=6)
        self.rodzaj_var = tk.StringVar(value=RODZ_WSZYSTKIE)
        cmb_r = ttk.Combobox(f, textvariable=self.rodzaj_var, width=10, state="readonly",
                             font=("Arial", 9), values=[RODZ_WSZYSTKIE] + RODZAJE)
        cmb_r.pack(side=tk.LEFT, pady=6)
        cmb_r.bind("<<ComboboxSelected>>", lambda _e: self._refill())

        tk.Label(f, text="Projekt:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(14, 3), pady=6)
        self.projekt_var = tk.StringVar(value=PROJ_WSZYSTKIE)
        self.cmb_proj = ttk.Combobox(f, textvariable=self.projekt_var, width=14,
                                     state="readonly", font=("Arial", 9),
                                     values=[PROJ_WSZYSTKIE])
        self.cmb_proj.pack(side=tk.LEFT, pady=6)
        self.cmb_proj.bind("<<ComboboxSelected>>", lambda _e: self._refill())

        self.only_otwarte_var = tk.IntVar(value=0)
        tk.Checkbutton(f, text="tylko niezrealizowane", variable=self.only_otwarte_var,
                       command=self._refill, bg="#ecf0f1", font=("Arial", 8),
                       activebackground="#ecf0f1").pack(side=tk.LEFT, padx=(12, 0), pady=6)

        # Czyszczenie filtrów — ta sama ikona i kolor co w arkuszu głównym.
        tk.Button(f, text="🗑️", command=self._wyczysc_filtry, bg="#95a5a6", fg="white",
                  font=("Arial", 11, "bold"), width=3, relief=tk.RAISED, bd=2,
                  cursor="hand2").pack(side=tk.LEFT, padx=(10, 2), pady=4)

        # Akcje na ZAZNACZONYM dokumencie — po prawej stronie paska filtrów,
        # bo w górnym już się nie mieściły.
        tk.Button(f, text="👁 Podgląd PDF", command=self._podglad_pdf,
                  bg="#7f8c8d", fg="white", font=("Arial", 8), padx=8, pady=2,
                  relief=tk.RAISED, bd=1, cursor="hand2").pack(side=tk.RIGHT, padx=(0, 12), pady=4)
        # Świeży wydruk — gdy dokument zmienił się po ostatnim wygenerowaniu.
        tk.Button(f, text="🔁 Nowy PDF",
                  command=lambda: self._podglad_pdf(wymus_nowy=True),
                  bg="#95a5a6", fg="white", font=("Arial", 8), padx=8, pady=2,
                  relief=tk.RAISED, bd=1, cursor="hand2").pack(side=tk.RIGHT, padx=(0, 4), pady=4)
        tk.Button(f, text="✉ Wyślij ZD", command=self._wyslij_zd,
                  bg="#2980b9", fg="white", font=("Arial", 8), padx=8, pady=2,
                  relief=tk.RAISED, bd=1, cursor="hand2").pack(side=tk.RIGHT, padx=(0, 4), pady=4)

        self.summary = tk.Label(self, text="Wczytywanie…", bg="#ecf0f1", fg="#2c3e50",
                                font=("Arial", 9), anchor="w", padx=12, pady=6)
        self.summary.pack(side=tk.TOP, fill=tk.X)

        # Legenda — kolory same w sobie nic nie mówią, a jest ich sześć.
        # Próbki, nie opis słowny: kolor obok znaczenia czyta się od razu.
        # ⚠️ Wartości MUSZĄ się zgadzać ze słownikiem `kolory` w _refill()
        # i z tłem anulowanych/trafień — inaczej legenda kłamie.
        leg = tk.Frame(self, bg="#ecf0f1")
        leg.pack(side=tk.TOP, fill=tk.X)
        tk.Label(leg, text="Legenda:", bg="#ecf0f1", fg="#7f8c8d",
                 font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=(12, 6), pady=(0, 5))
        for kolor, opis in (("#d6eaf8", "ZK — zamówienie od klienta"),
                            ("#dfeaf7", "ZD niewysłane — dostawca nie wie"),
                            ("#b3d1ec", "ZD wysłane do dostawcy"),
                            ("#d5f0dd", "PW — przyjęcie z produkcji własnej"),
                            ("#fdebd0", "RW — wydanie na produkcję"),
                            ("#f4ecf7", "WZ — wydanie zewnętrzne"),
                            ("#eaecee", "anulowany"),
                            ("#e8daef", "📦 MAGAZYN — zakup na skład, bez projektu"),
                            ("#fcf3cf", "pasuje do wyszukiwarki")):
            tk.Label(leg, text="  ", bg=kolor, relief=tk.SOLID, bd=1).pack(
                side=tk.LEFT, padx=(6, 3), pady=(0, 5))
            tk.Label(leg, text=opis, bg="#ecf0f1", fg="#2c3e50",
                     font=("Arial", 8)).pack(side=tk.LEFT, pady=(0, 5))
        tk.Label(leg, text="📄 = jest gotowy wydruk PDF (dwuklik otwiera)",
                 bg="#ecf0f1", fg="#7f8c8d", font=("Arial", 8)).pack(
            side=tk.LEFT, padx=(16, 0), pady=(0, 5))

        # Dwa panele OBOK SIEBIE: dokumenty po lewej, pozycje po prawej.
        # W pionie obie tabele dusiły się nawzajem — dokumentów bywa 31,
        # a pozycji w jednym ZK ponad 180, więc dzielenie wysokości znaczyło,
        # że w obu widać po kilka wierszy.
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 4))

        gora = tk.Frame(paned)      # lewa: lista dokumentów
        dol = tk.Frame(paned)       # prawa: pozycje
        # Lista dokumentów dostaje WIĘCEJ miejsca niż panel pozycji: to po nią
        # otwiera się to okno, a pozycje są podglądem klikniętego wiersza.
        # Przy 3:4 panel pozycji zasłaniał listę (zgłoszone 11.09.2026).
        paned.add(gora, weight=5)
        paned.add(dol, weight=3)

        # Wagi rozdzielają tylko NADMIAR miejsca, a obie tabele żądają teraz
        # małej szerokości — wyszłoby pół na pół. Lista dokumentów ma 60%.
        def _podzial():
            try:
                szer = paned.winfo_width()
                if szer > 100:
                    paned.sashpos(0, int(szer * 0.6))
                else:
                    self.after(100, _podzial)
            except tk.TclError:
                pass
        self.after(200, _podzial)

        if Sheet is None:
            tk.Label(gora, text="Brak biblioteki tksheet", fg="#c0392b").pack(pady=20)
            self.sheet = self.sheet_poz = None
            return

        # width/height MAŁE celowo: bez tego Sheet żąda szerokości wszystkich
        # kolumn naraz, wychodzi poza swój panel i chowa się pod panelem
        # pozycji razem z paskiem przewijania (02.10.2026). Rozmiar i tak
        # nadaje pack(fill, expand) w granicach panelu.
        self.sheet = Sheet(gora, headers=[k[1] for k in self.KOL_DOK],
                           column_width=120, theme="light blue", width=200, height=200)
        self.sheet.set_options(show_selected_cells_border=True,
                               enable_edit_cell_auto_resize=False,
                               empty_horizontal=0, empty_vertical=0)
        self.sheet.enable_bindings((
            "single_select", "drag_select", "ctrl_select", "select_all",
            "column_width_resize", "arrowkeys", "right_click_popup_menu",
            "rc_select", "copy",
        ))
        # Szerokości kolumn zapamiętywane między sesjami — osobno dla obu
        # arkuszy, bo to niezależne tabele.
        podepnij_szerokosci(self, self.sheet, "dokumenty",
                            [k[2] for k in self.KOL_DOK])
        self.sheet.bind("<ButtonRelease-1>", self._on_wybor_dokumentu, add="+")
        # Dwuklik w kolumnę PDF otwiera gotowy wydruk — bez sięgania po przycisk.
        self.sheet.bind("<Double-Button-1>", self._on_dwuklik, add="+")
        self.sheet.pack(fill=tk.BOTH, expand=True)

        # Pasek panelu pozycji: opis + przełącznik trybu. „Wszystkie pozycje"
        # spłaszcza dokumenty w jedną listę — szukanie konkretnego detalu bez
        # zgadywania, w którym z 31 dokumentów siedzi.
        pasek_poz = tk.Frame(dol, bg="#34495e")
        pasek_poz.pack(side=tk.TOP, fill=tk.X)
        self.lbl_poz = tk.Label(pasek_poz, text="Pozycje — kliknij dokument",
                                bg="#34495e", fg="white", font=("Arial", 9, "bold"),
                                anchor="w", padx=10, pady=4)
        self.lbl_poz.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.wszystkie_poz_var = tk.BooleanVar(value=False)
        tk.Checkbutton(pasek_poz, text="Wszystkie pozycje",
                       variable=self.wszystkie_poz_var, command=self._przelacz_pozycje,
                       bg="#34495e", fg="white", selectcolor="#2c3e50",
                       activebackground="#34495e", activeforeground="white",
                       font=("Arial", 8)).pack(side=tk.RIGHT, padx=(6, 10))
        # Szukanie W POZYCJACH pokazanego dokumentu (02.10.2026) — ZK projektu
        # ma 169-301 pozycji, a gorne „Szukaj" filtruje DOKUMENTY.
        self.szukaj_poz_var = tk.StringVar()
        tk.Entry(pasek_poz, textvariable=self.szukaj_poz_var, width=18,
                 font=("Arial", 9)).pack(side=tk.RIGHT, padx=(2, 8), pady=3)
        tk.Label(pasek_poz, text="🔍 w pozycjach:", bg="#34495e", fg="white",
                 font=("Arial", 8)).pack(side=tk.RIGHT)
        self.szukaj_poz_var.trace_add("write", lambda *_: self._szukaj_poz_po_wpisaniu())

        self.sheet_poz = Sheet(dol, headers=[k[1] for k in self.KOL_POZ],
                               column_width=120, theme="light green", width=200, height=200)
        self.sheet_poz.set_options(show_selected_cells_border=True,
                                   enable_edit_cell_auto_resize=False,
                                   empty_horizontal=0, empty_vertical=0)
        self.sheet_poz.enable_bindings((
            "single_select", "drag_select", "ctrl_select", "select_all",
            "column_width_resize", "arrowkeys", "right_click_popup_menu",
            "rc_select", "copy",
        ))
        podepnij_szerokosci(self, self.sheet_poz, "dokumenty_pozycje",
                            [k[2] for k in self.KOL_POZ])
        # Dwuklik w pozycje dokumentu -> karta pozycji. Z dokumentu (ZD/WZ/RW)
        # czesto trzeba sprawdzic, do jakiego zlozenia detal nalezy.
        # Dwuklik w „Ilość" pozycji ZK = zmiana ilości w Subiekcie (02.10.2026);
        # w pozostałe kolumny — karta pozycji jak dotąd.
        self.sheet_poz.bind("<Double-Button-1>", self._dwuklik_poz, add="+")
        self.sheet_poz.popup_menu_add_command("🔍 Karta pozycji (złożenie, BOM, Subiekt)",
                                              self._karta_pozycji)
        self.sheet_poz.popup_menu_add_command("🗑 Usuń pozycję z ZK…", self._usun_pozycje_zk)
        self.sheet_poz.pack(fill=tk.BOTH, expand=True)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    # ── wczytywanie ────────────────────────────────────────────────────────
    def _load_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.start_kreciolek("Czytam dokumenty z Subiekta")
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        try:
            import subiekt_panel
            dok = subiekt_panel.odczyt_z_panelu("dokumenty")
            if dok is None:
                dok = pobierz_dokumenty()
            self.after(0, lambda: self._load_done(dok, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._load_done([], err))

    def _load_done(self, dok, error):
        self.stop_kreciolek()      # także przy błędzie — inaczej kręci się dalej
        self.zaznacz_odczyt(self.lbl_wiek)
        self.btn_refresh.config(state=tk.NORMAL)
        if error:
            self.status.config(text="Błąd.")
            messagebox.showerror("Subiekt", error, parent=self)
            return
        self.dokumenty = dok
        # Ślad wysyłki z RM_BAZA — do kolumny „Wysłano”. Odczyt tanio (jedno
        # zapytanie), a odświeża się razem z listą, więc po wysłaniu maila
        # wystarczy „Odśwież”, żeby zobaczyć datę.
        self._wyslane = self._historia_wyslania()
        # Kolejność jak w górnej belce arkusza RM_BAZA: najnowsze numery na
        # górze (2637 przed 2430), potem literowe. Zwykłe `sorted()` dawało
        # odwrotnie — 2430, 2457, 2518… (zgłoszone 30.09.2026).
        from subiekt_zamowienia import klucz_projektu
        # Pojedyncze numery, nie zlepki: ZD wspolne dla dwoch projektow ma
        # w Uwagach „2627,3500" — na liscie byla osobna pozycja „2627,3500",
        # a filtr „2627" takiego ZD nie pokazywal (02.10.2026).
        projekty = sorted({n for d in dok for n in _numery_projektow(d)},
                          key=klucz_projektu)
        # MAGAZYN na poczatek listy: to nie numer projektu, a szuka sie go
        # czesto ("co zamowilem na sklad").
        if UWAGI_MAGAZYN in projekty:
            projekty = [UWAGI_MAGAZYN] + [p for p in projekty if p != UWAGI_MAGAZYN]
        self.cmb_proj["values"] = [PROJ_WSZYSTKIE] + projekty + [PROJ_BEZ]
        if self._projekt_startowy:
            if self._projekt_startowy in projekty:
                self.projekt_var.set(self._projekt_startowy)
            self._projekt_startowy = None      # tylko pierwszy odczyt
        self._refill()
        self._zaznacz_zadany()
        from datetime import datetime
        self.status.config(text=f"Odczyt {datetime.now():%H:%M:%S}. "
                                "Okno tylko czyta — nic nie zapisuje do Subiekta.")

    # ── filtry ─────────────────────────────────────────────────────────────
    def _pasuje(self, d, szukaj):
        """Szukaj obejmuje też POZYCJE — wpisanie numeru rysunku pokazuje
        dokumenty, które go zawierają. To główny sposób odpowiedzi na pytanie
        „gdzie jest ta część"."""
        if not szukaj:
            return True
        w_naglowku = szukaj in " ".join((d["numer"], d["podmiot"], d["tytul"],
                                         d["projekt"], d["status"])).lower()
        if w_naglowku:
            return True
        return any(szukaj in f"{p['symbol']} {p['nazwa']}".lower() for p in d["pozycje"])

    def _nowa_kartoteka(self):
        import subiekt_asortyment
        subiekt_asortyment.okno_nowa_kartoteka(self)

    def _wyczysc_filtry(self):
        """Wszystkie filtry do stanu wyjściowego — jedno odświeżenie na końcu."""
        self.search_var.set("")          # trace odpali _refill, ale poniżej i tak wołamy
        self.rodzaj_var.set(RODZ_WSZYSTKIE)
        self.projekt_var.set(PROJ_WSZYSTKIE)
        self.only_otwarte_var.set(0)
        self._refill()

    def _refill_po_wpisaniu(self):
        """Lista odświeża się po krótkiej przerwie w pisaniu, nie po każdym
        znaku — przy kilkuset wierszach każde przerysowanie jest odczuwalne."""
        zadanie = getattr(self, "_zadanie_szukaj", None)
        if zadanie:
            self.after_cancel(zadanie)
        self._zadanie_szukaj = self.after(250, self._szukaj_teraz)

    def _szukaj_teraz(self):
        self._zadanie_szukaj = None
        self._refill()

    def _refill(self):
        if not self.sheet:
            return
        szukaj = (self.search_var.get() or "").strip().lower()
        rodzaj = self.rodzaj_var.get()
        projekt = self.projekt_var.get()
        tylko_otw = bool(self.only_otwarte_var.get())

        out = []
        for d in self.dokumenty:
            if rodzaj != RODZ_WSZYSTKIE and d["rodzaj"] != rodzaj:
                continue
            if projekt == PROJ_BEZ:
                if d["projekt"]:
                    continue
            elif projekt != PROJ_WSZYSTKIE and projekt not in _numery_projektow(d):
                continue
            if tylko_otw and ("zrealizowan" in d["status"].lower()
                              or "anulowan" in d["status"].lower()):
                continue
            if not self._pasuje(d, szukaj):
                continue
            out.append(d)
        self.widoczne = out

        try:
            self.sheet.dehighlight_all()
        except Exception:
            pass
        self.sheet.set_sheet_data(
            [[d["rodzaj"], d["numer"], d["data"],
              # Zamowienie na sklad nie ma projektu — surowy napis "MAGAZYN"
              # w kolumnie Projekt wygladal jak numer projektu. Ikona odroznia
              # go od "2632" na pierwszy rzut oka (zgloszone 05.09.2026).
              ("📦 " + d["projekt"]) if d["projekt"] == UWAGI_MAGAZYN else d["projekt"],
              d["podmiot"],
              d["tytul"], len(d["pozycje"]),
              f"{d['wartosc']:.2f}" if d["wartosc"] else "",
              d.get("termin", ""), self._opis_wyslania(d),
              "📄" if self._plik_pdf(d) else "", d["status"]]
             for d in out], reset_col_positions=False, redraw=False)

        # Kolor po rodzaju — od razu widać, co jest zamówieniem, a co wydaniem.
        # ZD ma DWA kolory, te same co w oknie Zamówień (07.09.2026):
        #   jasny  — wystawione, ale NIEWYSŁANE; dostawca nie wie, jest co zrobić,
        #   mocny  — wysłane do dostawcy.
        # Wcześniej ZD było zielone i nie odróżniało jednego od drugiego,
        # a to jedyna rzecz, którą w tym oknie trzeba widzieć o ZD.
        # PW zielonkawe — przychód, odróżnia się od pomarańczowego RW
        # (rozchód). Para PW/RW to jeden tor, więc kolory sąsiadują.
        kolory = {"ZK": "#d6eaf8", "PW": "#d5f0dd", "RW": "#fdebd0", "WZ": "#f4ecf7"}
        wyslane = getattr(self, "_wyslane", None) or {}
        for i, d in enumerate(out):
            if d["rodzaj"] == "ZD":
                # Dopasowanie po Id, nie po numerze — numer wraca do
                # obiegu po usunieciu dokumentu (07.09.2026).
                if (d.get("Id") or 0) in wyslane:
                    self.sheet.highlight_cells(row=i, column=0, bg="#b3d1ec")
                else:
                    self.sheet.highlight_cells(row=i, column=0, bg="#dfeaf7")
                    # Niewysłane ZD — kolumna „Wysłano" na pomarańczowo, żeby
                    # zaległość rzucała się w oczy bez porównywania odcieni.
                    self.sheet.highlight_cells(row=i, column=9, bg="#f5b041", fg="#7d3c00")
            else:
                bg = kolory.get(d["rodzaj"])
                if bg:
                    self.sheet.highlight_cells(row=i, column=0, bg=bg)
            # Zakup na sklad — wyrozniony w kolumnie Projekt, zeby nie mylil
            # sie z zamowieniem pod konkretny projekt klienta.
            if d["projekt"] == UWAGI_MAGAZYN:
                self.sheet.highlight_cells(row=i, column=3, bg="#e8daef", fg="#4a235a")
            if "anulowan" in d["status"].lower():
                for c in range(len(self.KOL_DOK)):
                    self.sheet.highlight_cells(row=i, column=c, bg="#eaecee")
        self.sheet.redraw()

        from collections import Counter
        licz = Counter(d["rodzaj"] for d in out)
        poz = sum(len(d["pozycje"]) for d in out)
        self.summary.config(text=(
            f"Dokumentów: {len(out)} z {len(self.dokumenty)}    "
            + "   ".join(f"{r}: {licz.get(r, 0)}" for r in RODZAJE)
            + f"    pozycji łącznie: {poz}"
            + (f"    🔍 znaleziono w pozycjach" if szukaj else "")
        ))

        # Płaska lista żyje z tych samych filtrów co tabela dokumentów —
        # po każdej zmianie filtra albo frazy musi się przeliczyć.
        if getattr(self, "wszystkie_poz_var", None) and self.wszystkie_poz_var.get():
            self._pokaz_wszystkie_pozycje()

    # ── usuwanie dokumentów ────────────────────────────────────────────────
    def _zaznaczony_dokument(self, tylko_zd=False, akcja="tej operacji"):
        """Jeden dokument spod kursora. None + komunikat, gdy nic nie wybrano."""
        if not self.sheet:
            return None
        try:
            rows = sorted(set(self.sheet.get_selected_rows(get_cells_as_rows=True)))
        except Exception:
            rows = []
        wybrane = [self.widoczne[r] for r in rows if 0 <= r < len(self.widoczne)]
        if not wybrane:
            messagebox.showinfo("Subiekt", f"Zaznacz w tabeli dokument do {akcja}.",
                                parent=self)
            return None
        d = wybrane[0]
        if tylko_zd and d.get("rodzaj") != "ZD":
            messagebox.showinfo(
                "Wyślij ZD",
                f"To działa tylko dla zamówień do dostawcy (ZD).\n\n"
                f"Zaznaczony dokument to {d.get('rodzaj')} {d.get('numer')}.",
                parent=self)
            return None
        return d

    def _podglad_pdf(self, wymus_nowy=False):
        """
        Otwiera PDF zaznaczonego dokumentu — ten sam wydruk, który idzie mailem.

        Gotowy plik z katalogu wydruków otwiera się NATYCHMIAST; generowanie
        z Subiekta trwa ~11 s (uruchomienie mostu i zalogowanie do Sfery), więc
        robimy je tylko, gdy wydruku jeszcze nie ma albo ktoś chce świeży
        (zgłoszone 05.09.2026: „długo otwiera te PDF").
        """
        d = self._zaznaczony_dokument(akcja="podglądu")
        if not d:
            return
        numer = d.get("numer") or ""

        if not wymus_nowy:
            gotowy = self._plik_pdf(d)
            if gotowy:
                from datetime import datetime as _dt
                kiedy = _dt.fromtimestamp(gotowy.stat().st_mtime)
                os.startfile(str(gotowy))
                self.status.config(
                    text=f"Otwarto wydruk {numer} z {kiedy:%d.%m.%Y %H:%M} "
                         f"(gotowy plik; „Nowy PDF” wygeneruje aktualny).")
                return

        self.status.config(text=f"Generowanie PDF {numer}… (~11 s)")
        self.update_idletasks()
        try:
            import subiekt_wyslij_zd
            pdfy, bledy = subiekt_wyslij_zd.eksportuj_pdf([numer], self._katalog_pdf())
        except Exception as e:
            self.status.config(text="Nie udało się wygenerować PDF.")
            messagebox.showerror("Podgląd PDF", str(e), parent=self)
            return
        dane = pdfy.get(numer) or {}
        plik = dane.get("plik")
        if not plik or not Path(plik).exists():
            self.status.config(text="PDF nie powstał.")
            messagebox.showwarning("Podgląd PDF",
                                   "Nie udało się wygenerować wydruku tego dokumentu."
                                   + (f"\n\n{bledy[0]}" if bledy else ""), parent=self)
            return
        os.startfile(plik)
        self.status.config(text=f"Otwarto podgląd {numer}.")

    def _plik_pdf(self, dok):
        """
        Ścieżka gotowego wydruku tego dokumentu albo None.

        Nazwa pliku powstaje z numeru dokumentu tak samo jak w moście
        (ukośniki i spacje zamienione), więc nie trzeba niczego zapamiętywać
        — wystarczy sprawdzić, czy plik jest w katalogu wydruków.
        """
        import subiekt_wyslij_zd
        return subiekt_wyslij_zd.gotowy_pdf(dok.get("numer"))

    def _katalog_pdf(self):
        """Wspólny katalog wydruków na dysku Y:, nie lokalny %TEMP%."""
        import subiekt_wyslij_zd
        return subiekt_wyslij_zd._katalog_pdf_domyslny()

    def _historia_wyslania(self):
        """{numer ZD: (kiedy, ile razy)} — pusty słownik, gdy nic nie wysyłano."""
        try:
            import subiekt_wyslij_zd
            return subiekt_wyslij_zd.historia_wyslania()
        except Exception as e:
            print(f"⚠️  Historia wysyłek niedostępna: {e}")
            return {}

    def _opis_wyslania(self, dok):
        """
        Treść kolumny „Wysłano": data ostatniej wysyłki, a przy powtórkach
        licznik („2026-09-05 ×2").

        Ślad pochodzi z RM_BAZA, nie z Subiekta — status dokumentu w Subiekcie
        („Do realizacji") mówi o stanie magazynowym i nie zmienia się po
        wysłaniu maila.
        """
        wpis = (getattr(self, "_wyslane", None) or {}).get(dok.get("Id") or 0)
        if not wpis:
            return ""
        kiedy, ile = wpis
        data = (kiedy or "")[:10]
        return f"{data} ×{ile}" if ile > 1 else data

    def _pozycje_z_bomem(self, dok):
        """
        Pozycje ZD w formacie oczekiwanym przez okno wysyłki:
        (symbol, nazwa, ilość, j.m., ma_rysunek, projekty, bom_ref).

        Symbol, nazwa i ilość są z dokumentu w Subiekcie. Reszta z BOM-u
        RM_BAZA: `ma_rysunek` wycisza fałszywe „brak dokumentacji" dla
        elementów katalogowych, `projekty` mówi, gdzie szukać rysunków,
        a `bom_ref` [(project_id, item_id), …] to adresy, pod które po
        wysyłce wraca „Zamówiono" — po jednym na projekt pozycji.

        Projekt POZYCJI idzie z Uwag ZK, którą realizuje (most, tryb
        dokumenty). Wcześniej brany był z Uwag samego ZD — a te są puste,
        więc okno wysyłało bez adresów i „Zamówiono" nie trafiało nigdzie
        (05.09.2026). Ten sam mechanizm co w oknie zamówień: scal_bom/refy_bom.

        Gdy BOM-u nie da się wczytać, zostają same dane z Subiekta: wysyłka
        działa, tylko szukanie plików i „Zamówiono" są słabsze.
        """
        surowe = dok.get("pozycje") or []
        projekt_dok = (dok.get("projekt") or "").strip()

        def _lista(tekst):
            return [x.strip() for x in (tekst or "").split(",") if x.strip()]

        bom = {}
        try:
            import subiekt_zamowienia as sz
            numery = {n for p in surowe for n in _lista(p.get("projekt"))}
            if projekt_dok:
                numery.add(projekt_dok)
            for pid, pname in sz.projekty_po_numerze(numery).items():
                nr = (pname or "").strip().split(" ")[0]
                sz.scal_bom(bom, sz.dane_z_bom(pid, nr), nr)
        except Exception as e:
            print(f"⚠️  Nie udało się doczytać BOM-u dla {dok.get('numer')}: {e}")
            sz = None

        pozycje = []
        for p in surowe:
            symbol = p.get("symbol") or ""
            info = bom.get(symbol.strip().upper()) or {}
            projekty = _lista(p.get("projekt")) or _lista(projekt_dok)
            refy = sz.refy_bom(info, projekty) if (sz and info) else []
            pozycje.append((
                symbol,
                p.get("nazwa") or info.get("nazwa") or "",
                p.get("ilosc") or "",
                p.get("jm") or "szt.",
                # Bez wpisu w BOM-ie nie wiemy — None znaczy „nie orzekam",
                # a nie „nie ma rysunku".
                info.get("ma_rysunek") if info else None,
                ", ".join(projekty),
                refy,
            ))
        return pozycje

    def _email_dostawcy(self, dok):
        """E-mail dostawcy RM_BAZA dla podmiotu dokumentu (dokładnie, potem luźno)."""
        try:
            import subiekt_zamowienia as sz
            nazwa = (dok.get("podmiot") or "").strip()
            if not nazwa:
                return ""
            wiersze = [(w.get("name"),
                        (w.get("email") or "").strip() or (w.get("email_default") or "").strip() or None)
                       for w in sz._serwer().master_read("suppliers-list") if w.get("is_active")]
            cel = sz._uprosc_nazwe(nazwa)
            for n, mail in wiersze:
                if mail and sz._uprosc_nazwe(n or "") == cel:
                    return mail
            for n, mail in wiersze:
                u = sz._uprosc_nazwe(n or "")
                if mail and u and (u in cel or cel in u):
                    return mail
        except Exception as e:
            print(f"⚠️  Mail dostawcy: {e}")
        return ""

    def _nadawca(self):
        """Podpis pod mailem: imię i nazwisko, e-mail, telefon prowadzącego.

        Delegujemy do okna zamówień zamiast powtarzać zapytanie do bazy —
        obie drogi do wysyłki (Zamówienia i Przegląd dokumentów) mają dać
        ten sam podpis. Wcześniej była tu kopia czytająca samo display_name
        i po poprawieniu tamtej wersji ta nadal podpisywała maile „ADMIN”
        (zgłoszone 06.09.2026).
        """
        try:
            import subiekt_zamowienia as sz
            return sz.podpis_nadawcy(getattr(self.master, "current_user", None))
        except Exception:
            return ""

    def _wyslij_zd(self):
        """
        ✉ → okno wysyłki dla zaznaczonego ZD. To samo okno co w „Zamówieniach
        do dostawców”, tylko dane pozycji pochodzą z dokumentu w Subiekcie,
        a nie z BOM-u — dlatego dobieramy je z RM_BAZA po numerze rysunku
        (patrz _pozycje_z_bomem), żeby panel plików szukał tak samo dobrze.
        """
        d = self._zaznaczony_dokument(tylko_zd=True, akcja="wysłania")
        if not d:
            return
        try:
            import subiekt_wyslij_zd
        except Exception as e:
            messagebox.showerror("Wyślij ZD", f"Brak modułu wysyłki:\n{e}", parent=self)
            return

        pozycje = self._pozycje_z_bomem(d)
        okno = self.master
        subiekt_wyslij_zd.open_window(
            # Id z mostu — trwaly klucz dziennika wysylek (numer wraca do
            # obiegu po usunieciu dokumentu).
            self, d.get("numer") or "", d.get("podmiot") or "",
            self._email_dostawcy(d), d.get("projekt") or "", pozycje, self._nadawca(),
            szukaj_plikow=getattr(okno, "_find_files_for_drawing", None),
            # „Szukaj dalej…" to nie jest samo _rfq_deep_scan — najpierw trzeba
            # zapytać, SKĄD szukać (biblioteka czy serwer), i podać korzeń.
            # Całą tę drogę ma już okno zamówień, więc ją pożyczamy zamiast
            # pisać drugą. Podpięcie _rfq_deep_scan wprost dawało przycisk,
            # który nic nie robił (zgłoszone 05.09.2026).
            szukaj_dalej=self._szukaj_dalej_rysunku,
            dokument_id=d.get("Id") or d.get("id"),
            szukaj_hurtem=self._szukaj_hurtem_biblioteka,
            needs_dxf=getattr(okno, "_rfq_needs_dxf", None),
            # ⚠️ metoda nazywa się _register_file_drop, nie _register_drop_target
            # — zła nazwa cicho wyłączała przeciąganie plików.
            register_drop=getattr(okno, "_register_file_drop", None),
            dozwolone_ext=getattr(okno, "RFQ_PORTAL_EXTS", None),
            blad_serwera=lambda: getattr(okno, "_rfq_server_error", None),
            agent_portalu=getattr(okno, "_get_rfq_agent", None),
            # Po potwierdzonej wysyłce lista ma pokazać nową datę w kolumnie
            # „Wysłano” i termin — bez tego trzeba było klikać „Odśwież”
            # ręcznie, żeby zobaczyć skutek własnej operacji.
            po_wyslaniu=self._load_async)

    def _szukaj_dalej_rysunku(self, pozycja):
        """Alternatywne źródło plików — ta sama droga co w oknie zamówień."""
        import subiekt_zamowienia as sz
        return sz.ZamowieniaWindow._szukaj_dalej_rysunku(self, pozycja)

    def _szukaj_hurtem_biblioteka(self, numery, zrodlo="library"):
        """Skan zbiorczy (biblioteka albo serwer) — pożyczony z okna zamówień."""
        import subiekt_zamowienia as sz
        return sz.ZamowieniaWindow._szukaj_hurtem_biblioteka(self, numery, zrodlo)

    def _usun_zaznaczone(self):
        """Kasuje dokumenty zaznaczone w tabeli. Most (tryb zd-usun) rozpoznaje
        rodzaj po prefiksie numeru, więc obsłuży mieszany zestaw ZK/ZD/RW/WZ."""
        if not self.sheet:
            return
        try:
            rows = sorted(set(self.sheet.get_selected_rows(get_cells_as_rows=True)))
        except Exception:
            rows = []
        wybrane = [self.widoczne[r] for r in rows if 0 <= r < len(self.widoczne)]
        if not wybrane:
            messagebox.showinfo(
                "Usuń dokumenty",
                "Zaznacz w tabeli dokumenty do usunięcia.\n\n"
                "Klik w wiersz zaznacza jeden, Ctrl+klik dokłada kolejne.",
                parent=self)
            return

        numery = [d["numer"] for d in wybrane if d.get("numer")]
        opis = "\n".join(
            f"  • {d['rodzaj']} {d['numer']} — {d.get('podmiot') or '—'} "
            f"({len(d.get('pozycje') or [])} poz.)" for d in wybrane[:15])
        if len(wybrane) > 15:
            opis += f"\n  … i {len(wybrane) - 15} więcej"

        # ZD trzyma się ZK — kasowanie ZK przed jego ZD kończy się odmową
        # Subiekta. Ostrzegamy tylko wtedy, gdy w zestawie są oba typy.
        rodzaje = {d.get("rodzaj") for d in wybrane}
        uwaga = ("\n⚠️ W zaznaczeniu są ZK i ZD. Jeśli są powiązane, usuń "
                 "najpierw ZD — Subiekt może nie pozwolić skasować ZK "
                 "z wiszącym zamówieniem.\n"
                 if {"ZK", "ZD"} <= rodzaje else "")

        if not messagebox.askyesno(
                "Usunięcie dokumentów — potwierdzenie",
                "Baza PRODUKCYJNA. Operacja NIEODWRACALNA.\n\n"
                f"Zostaną usunięte ({len(numery)}):\n{opis}\n{uwaga}\nUsunąć?",
                parent=self, icon="warning"):
            return

        # Usuwane dokumenty (z pozycjami) trzeba zapamiętać TERAZ — po
        # skasowaniu i przeładowaniu listy nie ma już skąd wziąć ich pozycji,
        # a cofnięcie „Zamówiono" w arkuszu idzie po pozycjach dokumentu.
        norm = lambda s: " ".join(str(s or "").split()).upper()
        self._dok_do_usuniecia = {norm(d.get("numer")): d for d in wybrane if d.get("numer")}
        self.status.config(text="Usuwam dokumenty…")
        self.start_kreciolek("Usuwam dokumenty w Subiekcie")
        threading.Thread(target=self._usun_worker, args=(numery,),
                         daemon=True).start()

    def _usun_worker(self, numery):
        try:
            from subiekt_zamowienia import usun_zd
            wynik = usun_zd(numery, zapisz=True)
            self.after(0, lambda: self._usun_done(wynik, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._usun_done(None, err))

    def _usun_done(self, wynik, error):
        self.stop_kreciolek()
        if error:
            self.status.config(text="Nie udało się usunąć dokumentów.")
            messagebox.showerror("Usuwanie dokumentów", error, parent=self)
            return
        kroki = wynik.get("kroki", [])
        usuniete = [k for k in kroki if k.get("Status") == "usuniete"]
        bledy = [k for k in kroki if k.get("Status") == "blad"]

        linie = [f"Usunięte dokumenty: {len(usuniete)}"]
        linie += [f"  • {k['Numer']} — {k.get('Szczegoly') or ''}" for k in usuniete[:12]]
        if bledy:
            linie += ["", f"Nieusunięte ({len(bledy)}):"]
            linie += [f"  • {k['Numer']}: {k.get('Szczegoly') or ''}" for k in bledy[:8]]
        # To samo, co robi okno Zamówień po usunięciu ZD — TEN SAM mechanizm,
        # ta sama kolejność. Do 07.09.2026 tylko tamto okno cofało „Zamówiono"
        # i unieważniało dziennik wysyłek; usunięcie ZD stąd zostawiało
        # w arkuszu flagę, datę i termin, a w dzienniku żywy wpis, który
        # dziedziczył następny dokument pod tym samym numerem.
        zd_numery = [k["Numer"] for k in usuniete
                     if str(k.get("Numer") or "").strip().upper().startswith("ZD")]
        if zd_numery:
            opis = self._cofnij_po_usunieciu(zd_numery)
            if opis:
                linie += ["", opis]
        (messagebox.showwarning if bledy else messagebox.showinfo)(
            "Usuwanie dokumentów", "\n".join(linie), parent=self)
        self._load_async()      # lista musi pokazać stan po usunięciu

    def _cofnij_po_usunieciu(self, numery_zd):
        """Cofa „Zamówiono" (flaga, data, termin z tej wysyłki) w arkuszu
        RM_BAZA dla pozycji usuniętych ZD i unieważnia ich wpisy w dzienniku
        wysyłek. Zwraca opis do komunikatu.

        Adresy BOM biorą się z _pozycje_z_bomem — tego samego, którym okno
        wysyłki nakłada „Zamówiono", więc cofnięcie trafia dokładnie tam,
        gdzie poszło nałożenie. KOLEJNOŚĆ: najpierw cofnięcie (czyta termin
        z żywego wpisu dziennika), dopiero potem unieważnienie wpisu.
        """
        try:
            from subiekt_wyslij_zd import cofnij_zamowienia, uniewaznij_wyslania
        except Exception as e:
            print(f"⚠️  Brak modułu cofania „Zamówiono”: {e}")
            return ""
        norm = lambda s: " ".join(str(s or "").split()).upper()
        zapamietane = getattr(self, "_dok_do_usuniecia", None) or {}
        refy, bez_adresu, numery = set(), [], []
        # Id usunietych dokumentow — po nich sprzatamy dziennik wysylek.
        # Numer sie nie nadaje: Subiekt nada go zaraz nastepnemu ZD.
        idy = []
        for nr in numery_zd:
            dok = zapamietane.get(norm(nr))
            numer = (dok or {}).get("numer") or " ".join(str(nr).split())
            numery.append(numer)
            if (dok or {}).get("Id"):
                idy.append(dok["Id"])
            adresow = 0
            if dok:
                try:
                    for poz in self._pozycje_z_bomem(dok):
                        for ref in (poz[6] if len(poz) > 6 else None) or []:
                            if ref and ref[0] and ref[1]:
                                refy.add((int(ref[0]), int(ref[1]), numer))
                                adresow += 1
                except Exception as e:
                    print(f"⚠️  Adresy BOM dla {numer}: {e}")
            print(f"🧾 Cofanie „Zamówiono” {numer} (Dokumenty): "
                  f"dokument {'znany' if dok else 'NIEZNANY na liście'}, adresów BOM={adresow}")
            if not adresow:
                bez_adresu.append(numer)

        arkusz = getattr(self, "master", None)
        pod_lockiem = bool(getattr(arkusz, "have_lock", False))
        try:
            odlozone, poprawione = cofnij_zamowienia(
                numery, bom_refy=sorted(refy),
                project_con=(arkusz.db_manager.project_con if pod_lockiem and arkusz else None),
                project_id=(getattr(arkusz, "current_project_id", None) if pod_lockiem else None),
                log=getattr(arkusz, "_log_item_change", None))
        except Exception as e:
            print(f"⚠️  Nie cofnięto „Zamówiono”: {e}")
            odlozone, poprawione = 0, 0
        # Dopiero teraz — cofnięcie wyżej potrzebowało jeszcze żywego wpisu.
        try:
            n = uniewaznij_wyslania(idy)
            if n:
                print(f"🧾 Dziennik wysyłek: usunięto {n} wpisów skasowanych ZD")
        except Exception as e:
            print(f"⚠️  Nie posprzątano dziennika wysyłek: {e}")
        if poprawione and arkusz is not None:
            try:
                arkusz.after(0, arkusz.refresh_data)
            except Exception:
                pass

        opis = ""
        if odlozone:
            opis = f"Cofnięto „Zamówiono” i termin z tej wysyłki dla {odlozone} poz."
            opis += (f" (w otwartym projekcie poprawiono {poprawione})" if poprawione
                     else (" — w arkuszu zniknie przy najbliższym przejęciu projektu."
                           if not pod_lockiem else ""))
        if bez_adresu:
            opis += ("\n" if opis else "") + (
                "⚠ Dla " + ", ".join(bez_adresu) + " nie ustalono pozycji w arkuszu "
                "RM_BAZA — „Zamówiono” i termin ZOSTAJĄ, odznacz je ręcznie.")
        return opis

    # ── pozycje wybranego dokumentu ────────────────────────────────────────
    def _karta_pozycji(self, _event=None):
        """Karta pozycji dla zaznaczonego wiersza w arkuszu POZYCJI dokumentu."""
        if not self.sheet_poz:
            return
        rows = set()
        try:
            rows |= set(self.sheet_poz.get_selected_rows(get_cells_as_rows=True))
        except Exception:
            pass
        try:
            # Pojedyncza komorka: get_selected_rows() zwraca pusty zbior,
            # wiersz zna tylko get_currently_selected() (patrz subiekt_stany).
            biezacy = self.sheet_poz.get_currently_selected()
            if biezacy and getattr(biezacy, "row", None) is not None:
                rows.add(biezacy.row)
        except Exception:
            pass
        if not rows:
            return
        try:
            symbol = str(self.sheet_poz.get_cell_data(sorted(rows)[0], 0) or "").strip()
        except Exception:
            return
        if not symbol:
            return
        import subiekt_pozycja_gui
        subiekt_pozycja_gui.otworz(self, symbol)

    def _dwuklik_poz(self, event=None):
        """Dwuklik w panelu pozycji: „Ilość" pozycji ZK → zmiana w Subiekcie,
        reszta → karta pozycji."""
        try:
            biezacy = self.sheet_poz.get_currently_selected()
            row = getattr(biezacy, "row", None)
            col = getattr(biezacy, "column", None)
        except Exception:
            row = col = None
        klucze = [k[0] for k in self.KOL_POZ]
        pola = {klucze.index("ilosc"): "ilosc", klucze.index("cena"): "cena"}
        d = getattr(self, "_poz_dok", None)
        if (not self.wszystkie_poz_var.get() and d is not None and d.get("rodzaj") == "ZK"
                and col in pola and row is not None
                and 0 <= row < len(getattr(self, "_poz_widoczne", []))):
            self._zmien_ilosc_zk(d, self._poz_widoczne[row], pole=pola[col])
            return "break"
        return self._karta_pozycji(event)

    def _wybrana_pozycja(self):
        """(dokument, pozycja) zaznaczona w panelu pozycji albo (None, None)."""
        d = getattr(self, "_poz_dok", None)
        if self.wszystkie_poz_var.get() or d is None:
            return None, None
        try:
            biezacy = self.sheet_poz.get_currently_selected()
            row = getattr(biezacy, "row", None)
        except Exception:
            row = None
        poz = getattr(self, "_poz_widoczne", [])
        if row is None or not (0 <= row < len(poz)):
            return d, None
        return d, poz[row]

    def _usun_pozycje_zk(self):
        """Usuwa zaznaczoną pozycję z ZK (tryb mostu `zk-poz-usun`, ZK po numerze).

        Te same bezpieczniki co „Zdejmij z ZK" w arkuszu: pozycji, która
        poszła na ZD, most nie usunie; dokumentu nie z RM_BAZA nie ruszy.
        NIC PO CICHU: suchy przebieg → czerwone okno → zapis → odczyt.
        """
        from subiekt_projekt import komunikat
        import subiekt_bridge
        d, p = self._wybrana_pozycja()
        if d is None or d.get("rodzaj") != "ZK":
            komunikat(self, "Usuń z ZK", "Usuwać można tylko pozycje dokumentu ZK.\n"
                      "Kliknij ZK na liście, potem pozycję.", rodzaj="warn")
            return
        if p is None:
            komunikat(self, "Usuń z ZK", "Najpierw zaznacz pozycję.", rodzaj="warn")
            return
        sym = str(p.get("symbol") or "").strip()
        plan = {"zk": d["numer"], "symbole": [sym]}
        self.config(cursor="watch"); self.update_idletasks()
        try:
            suchy = subiekt_bridge.call("zk-poz-usun", {"plan": plan, "zapisz": False},
                                        timeout=TIMEOUT_S, write=False)
        except Exception as e:
            self.config(cursor="")
            komunikat(self, "Usuń z ZK", f"Most nie odpowiedział:\n\n{e}", rodzaj="error")
            return
        self.config(cursor="")
        kroki = (suchy or {}).get("kroki", [])
        k = next((x for x in kroki if x.get("Rodzaj") == "zk-poz"), None) \
            or next(iter(kroki), {})
        if not str(k.get("Status") or "").startswith("do-usuniecia"):
            komunikat(self, "Usuń z ZK", f"{d['numer']} — {sym}\n\n{k.get('Szczegoly') or k.get('Status')}",
                      rodzaj="error")
            return
        if not komunikat(
                self, "Usuń pozycję z ZK — zapis do Subiekta",
                f"{d['numer']}\n\n    {sym} — {p.get('nazwa', '')}\n    ({k.get('Szczegoly')})\n\n"
                "Pozycja zniknie z ZK w Subiekcie.\n\n"
                "⚠ Jeśli jest w BOM projektu, Projekt/Aktualizacja DODA JĄ Z POWROTEM.\n"
                "Żeby zniknęła na stałe, ukryj ją też w arkuszu RM_BAZA.\n\n"
                "Usunąć?", rodzaj="error", pytanie=True):
            return
        self.config(cursor="watch"); self.update_idletasks()
        try:
            wynik = subiekt_bridge.call("zk-poz-usun", {"plan": plan, "zapisz": True},
                                        timeout=TIMEOUT_S, write=True)
        except Exception as e:
            self.config(cursor="")
            komunikat(self, "Usuń z ZK", f"Most nie wykonał zapisu:\n\n{e}\n\nSprawdź ZK w Subiekcie.",
                      rodzaj="error")
            return
        self.config(cursor="")
        kroki = (wynik or {}).get("kroki", [])
        zk = next((x for x in kroki if x.get("Rodzaj") == "zk" and x.get("Status") in ("zapisane", "blad")), {})
        komunikat(self, "Usuń z ZK", f"{d['numer']} — {sym}\n\n{zk.get('Szczegoly') or 'brak potwierdzenia — sprawdź w Subiekcie'}",
                  rodzaj="info" if zk.get("Status") == "zapisane" else "error")
        self._do_zaznaczenia = d["numer"]
        self._load_async()

    def _okno_ilosci(self, d, p, pole="ilosc"):
        """Okno wpisania nowej ilości pozycji ZK. Zwraca liczbę albo None.

        Własne okno zamiast `simpledialog` (02.10.2026: „to okno ma być
        ładne") — ten sam styl co `komunikat`: ciemny pasek, karta pozycji,
        duże liczby „teraz → nowa", różnica liczona na żywo i walidacja
        w oknie (0 i nie-liczba blokują „Dalej", zamiast osobnych błędów).
        """
        GRANAT, SZARY, JASNY, TLO = "#2c3e50", "#7f8c8d", "#bdc3c7", "#f4f6f8"
        cena = pole == "cena"
        teraz = float(p.get("cena") or 0) if cena else float(p.get("ilosc") or 0)
        jm = "zł netto" if cena else str(p.get("jm") or "szt")
        fmt = (lambda v: f"{v:.2f}") if cena else (lambda v: f"{v:g}")

        okno = tk.Toplevel(self)
        okno.title("Zmień cenę na ZK" if cena else "Zmień ilość na ZK")
        okno.resizable(False, False)
        okno.configure(bg="white")
        try:
            okno.transient(self)
        except tk.TclError:
            pass
        wynik = {"ilosc": None}

        # ── pasek ──
        pasek = tk.Frame(okno, bg=GRANAT)
        pasek.pack(fill=tk.X)
        tk.Label(pasek, text="✏  Zmiana ceny na ZK" if cena else "✏  Zmiana ilości na ZK",
                 bg=GRANAT, fg="white",
                 font=("Arial", 12, "bold"), anchor="w", padx=16, pady=(10)
                 ).pack(fill=tk.X)
        tk.Label(pasek, text=d["numer"] + (f"   ·   projekt {d['projekt']}" if d.get("projekt") else ""),
                 bg=GRANAT, fg=JASNY, font=("Arial", 9), anchor="w", padx=16
                 ).pack(fill=tk.X, pady=(0, 10))

        # ── pozycja ──
        karta = tk.Frame(okno, bg="white")
        karta.pack(fill=tk.X, padx=20, pady=(16, 4))
        tk.Label(karta, text=str(p.get("symbol") or ""), bg="white", fg=GRANAT,
                 font=("Arial", 13, "bold"), anchor="w").pack(fill=tk.X)
        if p.get("nazwa"):
            tk.Label(karta, text=p["nazwa"], bg="white", fg=SZARY, font=("Arial", 9),
                     anchor="w", justify="left", wraplength=380).pack(fill=tk.X)

        # ── teraz → nowa ──
        rzad = tk.Frame(okno, bg="white")
        rzad.pack(padx=20, pady=(14, 4))

        def kafel(rodzic, napis):
            f = tk.Frame(rodzic, bg=TLO, highlightthickness=1, highlightbackground="#dfe4ea")
            tk.Label(f, text=napis, bg=TLO, fg=SZARY, font=("Arial", 8, "bold")
                     ).pack(anchor="w", padx=12, pady=(8, 0))
            return f

        k1 = kafel(rzad, "CENA TERAZ" if cena else "NA ZK TERAZ")
        k1.grid(row=0, column=0, sticky="ns")
        tk.Label(k1, text=fmt(teraz), bg=TLO, fg=SZARY, font=("Arial", 24, "bold"),
                 width=6 if cena else 5).pack(padx=12)
        tk.Label(k1, text=jm, bg=TLO, fg=SZARY, font=("Arial", 9)).pack(pady=(0, 8))

        tk.Label(rzad, text="→", bg="white", fg=JASNY, font=("Arial", 22, "bold")
                 ).grid(row=0, column=1, padx=12)

        k2 = kafel(rzad, "NOWA CENA" if cena else "NOWA ILOŚĆ")
        k2.grid(row=0, column=2, sticky="ns")
        k2.configure(highlightbackground="#3498db", highlightcolor="#3498db",
                     highlightthickness=2)
        wpis_rzad = tk.Frame(k2, bg=TLO)
        wpis_rzad.pack(padx=8)
        var = tk.StringVar(value=fmt(teraz))

        def krok(o):
            try:
                v = float(var.get().replace(",", ".")) + o
            except ValueError:
                v = teraz
            var.set(fmt(max(v, 0)))
            wpis.icursor(tk.END)

        tk.Button(wpis_rzad, text="−", width=2, font=("Arial", 12, "bold"),
                  relief=tk.FLAT, bg="#dfe4ea", command=lambda: krok(-1)).pack(side=tk.LEFT)
        wpis = tk.Entry(wpis_rzad, textvariable=var, width=8 if cena else 6, justify="center",
                        font=("Arial", 24, "bold"), fg=GRANAT, relief=tk.FLAT, bg="white")
        wpis.pack(side=tk.LEFT, padx=4, ipady=2)
        tk.Button(wpis_rzad, text="+", width=2, font=("Arial", 12, "bold"),
                  relief=tk.FLAT, bg="#dfe4ea", command=lambda: krok(+1)).pack(side=tk.LEFT)
        tk.Label(k2, text=jm, bg=TLO, fg=SZARY, font=("Arial", 9)).pack(pady=(0, 8))

        roznica = tk.Label(okno, text="", bg="white", font=("Arial", 10, "bold"))
        roznica.pack(pady=(8, 0))
        tk.Label(okno, text=("Cena netto za jednostkę. " if cena else "Ilość docelowa, nie różnica. ")
                            + "Przed zapisem zobaczysz,\n"
                            "co dokładnie zmieni się w Subiekcie.",
                 bg="white", fg=SZARY, font=("Arial", 8), justify="center"
                 ).pack(pady=(4, 14))

        # ── stopka ──
        stopka = tk.Frame(okno, bg=TLO)
        stopka.pack(fill=tk.X)

        def zamknij(ok):
            if ok:
                if btn_dalej["state"] == tk.DISABLED:
                    return
                wynik["ilosc"] = float(var.get().replace(",", "."))
            okno.destroy()

        btn_dalej = tk.Button(stopka, text="Dalej  →", width=12, font=("Arial", 10, "bold"),
                              bg="#27ae60", fg="white", activebackground="#229954",
                              activeforeground="white", relief=tk.FLAT,
                              command=lambda: zamknij(True))
        btn_dalej.pack(side=tk.RIGHT, padx=(6, 14), pady=10)
        tk.Button(stopka, text="Anuluj", width=10, relief=tk.FLAT, bg="#dfe4ea",
                  command=lambda: zamknij(False)).pack(side=tk.RIGHT, pady=10)

        def odswiez(*_):
            try:
                v = float(var.get().replace(",", "."))
            except ValueError:
                roznica.config(text="To nie jest liczba", fg="#c0392b")
                btn_dalej.config(state=tk.DISABLED, bg="#95a5a6")
                return
            if v < 0 or (v == 0 and not cena):
                roznica.config(text="Cena nie może być ujemna" if cena
                               else "0 nie — pozycję się usuwa, nie zeruje", fg="#c0392b")
                btn_dalej.config(state=tk.DISABLED, bg="#95a5a6")
                return
            if v == teraz:
                roznica.config(text="bez zmian", fg=SZARY)
                btn_dalej.config(state=tk.DISABLED, bg="#95a5a6")
                return
            o = v - teraz
            roznica.config(text=f"{'+' if o > 0 else '−'}{fmt(abs(o))} {jm}",
                           fg="#27ae60" if o > 0 else "#d35400")
            btn_dalej.config(state=tk.NORMAL, bg="#27ae60")

        var.trace_add("write", odswiez)
        odswiez()
        okno.bind("<Return>", lambda e: zamknij(True))
        okno.bind("<Escape>", lambda e: zamknij(False))
        okno.bind("<Up>", lambda e: krok(+1))
        okno.bind("<Down>", lambda e: krok(-1))

        wysrodkuj(okno, self)
        okno.grab_set()
        wpis.focus_set()
        wpis.select_range(0, tk.END)
        self.wait_window(okno)
        return wynik["ilosc"]

    def _zmien_ilosc_zk(self, d, p, pole="ilosc"):
        """Ilość pozycji na ZK — WPROST w Subiekcie (tryb mostu `zk-ilosc`).

        Po zasiewie właścicielem ilości jest Subiekt, więc to jest właściwe
        miejsce na zmianę; arkusz RM_BAZA pobierze nową wartość przy
        następnym przejęciu locka. NIC PO CICHU: suchy przebieg → okno
        z „na ZK X → ustawi Y" → zapis → wynik potwierdzony odczytem.
        """
        from subiekt_projekt import komunikat
        import subiekt_bridge
        sym = str(p.get("symbol") or "").strip()
        if not sym:
            return
        nowa = self._okno_ilosci(d, p, pole)
        if nowa is None:
            return
        tryb = "zk-cena" if pole == "cena" else "zk-ilosc"
        tytul = "Zmień cenę na ZK" if pole == "cena" else "Zmień ilość na ZK"
        plan = {"zk": d["numer"], "pozycje": [{"symbol": sym, pole: nowa}]}

        def krok(wynik):
            return next((k for k in (wynik or {}).get("kroki", [])
                         if k.get("Rodzaj") == "zk-poz"
                         and str(k.get("Symbol") or "").upper() == sym.upper()), None) \
                or next((k for k in (wynik or {}).get("kroki", [])), None) or {}

        self.config(cursor="watch"); self.update_idletasks()
        try:
            suchy = subiekt_bridge.call(tryb, {"plan": plan, "zapisz": False},
                                        timeout=TIMEOUT_S, write=False)
        except Exception as e:
            self.config(cursor="")
            komunikat(self, tytul, f"Most nie odpowiedział:\n\n{e}", rodzaj="error")
            return
        self.config(cursor="")
        k = krok(suchy)
        status = str(k.get("Status") or "")
        if not status.startswith("do-zmiany"):
            komunikat(self, tytul,
                      f"{d['numer']} — {sym}\n\n{k.get('Szczegoly') or status or 'brak odpowiedzi mostu'}",
                      rodzaj="info" if status == "bez-zmian" else "error")
            return
        if not komunikat(
                self, tytul + " — zapis do Subiekta",
                f"{d['numer']}\n\n    {sym}: {k.get('Szczegoly')}\n\n"
                "Zmiana idzie WPROST do Subiekta.\n"
                + ("" if pole == "cena" else
                   "Arkusz RM_BAZA pobierze nową ilość przy następnym przejęciu locka.\n")
                + "\n"
                "Zapisać?", rodzaj="warn", pytanie=True):
            return

        self.config(cursor="watch"); self.update_idletasks()
        try:
            wynik = subiekt_bridge.call(tryb, {"plan": plan, "zapisz": True},
                                        timeout=TIMEOUT_S, write=True)
        except Exception as e:
            self.config(cursor="")
            komunikat(self, tytul,
                      f"Most nie wykonał zapisu:\n\n{e}\n\nSprawdź ilość w Subiekcie.", rodzaj="error")
            return
        self.config(cursor="")
        k = krok(wynik)
        if k.get("Status") == "zmieniona":
            komunikat(self, tytul, f"{d['numer']}\n\n    {sym}: {k.get('Szczegoly')}")
        else:
            komunikat(self, tytul,
                      f"{d['numer']} — {sym}\n\n{k.get('Szczegoly') or k.get('Status') or 'nieznany wynik'}",
                      rodzaj="error")
        # Lista ma pokazać stan po zapisie — z powrotem na tym samym ZK.
        self._do_zaznaczenia = d["numer"]
        self._load_async()

    def _on_dwuklik(self, _event=None):
        """Dwuklik w kolumnie PDF → otwiera gotowy wydruk zaznaczonego dokumentu."""
        if not self.sheet:
            return
        try:
            komorki = self.sheet.get_selected_cells()
            kolumna = next(iter(komorki))[1] if komorki else None
        except Exception:
            kolumna = None
        indeks_pdf = [k for k, *_ in self.KOL_DOK].index("pdf")
        if kolumna != indeks_pdf:
            return
        self._podglad_pdf()

    def _zaznacz_zadany(self):
        """Zaznacza i przewija do dokumentu podanego przy otwarciu okna.

        Numer porownujemy po obcieciu bialych znakow i wielkosci liter —
        okno wydania podaje go tak, jak zwrocil go most. Gdy dokumentu nie
        ma na liscie (inny filtr, usuniety), nie robimy nic: wyszukiwarka
        i tak zostala wypelniona, wiec user widzi, czego szukano.
        """
        numer = getattr(self, "_do_zaznaczenia", None)
        if not numer or not self.sheet:
            return
        self._do_zaznaczenia = None          # jednorazowo, nie przy kazdym odswiezeniu
        cel = numer.strip().upper()
        for i, d in enumerate(self.widoczne):
            if (d.get("numer") or "").strip().upper() != cel:
                continue
            try:
                self.sheet.select_row(i)
                self.sheet.see(row=i, column=0)
            except Exception:
                pass                          # starsze tksheet — zaznaczenie nieistotne
            # Pozycje dokumentu w dolnej tabeli — bez tego klik z okna wydania
            # pokazywalby pusty dol, choc dokument jest zaznaczony.
            try:
                self._on_wybor_dokumentu()
            except Exception:
                pass
            break

    def _on_wybor_dokumentu(self, _event=None):
        if not self.sheet or not self.sheet_poz:
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
        d = self.widoczne[r]
        self.biezacy = d
        if self.wszystkie_poz_var.get():
            # W trybie płaskim kliknięcie dokumentu nie przestawia panelu —
            # lista ma zostać taka, jaka jest, żeby nie gubić miejsca w szukaniu.
            return

        self._pokaz_pozycje(d)

    def _szukaj_poz_po_wpisaniu(self):
        """Filtr pozycji po krotkiej przerwie w pisaniu, nie po kazdym znaku."""
        zadanie = getattr(self, "_zadanie_szukaj_poz", None)
        if zadanie:
            self.after_cancel(zadanie)
        self._zadanie_szukaj_poz = self.after(250, self._szukaj_poz_teraz)

    def _szukaj_poz_teraz(self):
        self._zadanie_szukaj_poz = None
        if self.wszystkie_poz_var.get():
            self._pokaz_wszystkie_pozycje()
        elif self._poz_dok is not None:
            self._pokaz_pozycje(self._poz_dok)

    def _kolejnosc_arkusza(self, numer):
        """{KLUCZ WIELKIMI: miejsce} — kolejnosc wierszy arkusza RM_BAZA.

        To samo ORDER BY co arkusz (`database_manager.get_project_items`):
        znormalizowane na gorze, potem numer rysunku, potem nazwa. Kluczem
        jest symbol Subiekta, numer rysunku i nazwa wiersza — pozycja
        dokumentu trafia po ktoremukolwiek. Odczyt RAZ na projekt i okno.
        """
        if numer in self._kolejnosc_proj:
            return self._kolejnosc_proj[numer]
        miejsca = {}
        try:
            if self._pid_po_numerze is None:
                # Jedno zapytanie o wszystkie projekty z listy dokumentow.
                from subiekt_zamowienia import projekty_po_numerze
                nr = {n for d in self.dokumenty for n in _numery_projektow(d)}
                self._pid_po_numerze = {
                    (nazwa or "").strip().split(" ")[0]: pid
                    for pid, nazwa in projekty_po_numerze(nr).items()}
            pid = self._pid_po_numerze.get(numer)
            if pid:
                import os, sqlite3
                from subiekt_stany import PROJECTS_DIR
                sciezka = os.path.join(PROJECTS_DIR, f"project_{pid}.sqlite")
                con = sqlite3.connect(f"file:{sciezka}?mode=ro", uri=True)
                try:
                    kol = {k[1] for k in con.execute("PRAGMA table_info(items)")}
                    sym = "subiekt_symbol" if "subiekt_symbol" in kol else "NULL"
                    klasa = ("COALESCE(class_manual, class_auto)"
                             if {"class_manual", "class_auto"} <= kol else "NULL")
                    wiersze = con.execute(f"""
                        SELECT COALESCE(NULLIF(work_drawing_no, ''), src_drawing_no) AS dn,
                               COALESCE(NULLIF(work_name, ''), src_name) AS nm, {sym}
                        FROM items WHERE COALESCE(is_hidden, 0) = 0
                        ORDER BY CASE WHEN {klasa} = 'ZNORMALIZOWANE' THEN 0 ELSE 1 END,
                                 dn COLLATE NOCASE, nm COLLATE NOCASE, id""").fetchall()
                finally:
                    con.close()
                for i, (dn, nm, sy) in enumerate(wiersze):
                    for k in (sy, dn, nm):
                        k = str(k or "").strip().upper()
                        if k and k not in miejsca:
                            miejsca[k] = i
        except Exception as e:
            print(f"⚠️  Kolejność arkusza dla {numer}: {e}")
        self._kolejnosc_proj[numer] = miejsca
        return miejsca

    def _posortuj_jak_arkusz(self, d, pozycje):
        """Pozycje w kolejnosci arkusza projektu; spoza arkusza — na koncu,
        po symbolu. Dokument bez projektu (MAGAZYN) — po symbolu."""
        miejsca = {}
        for n in _numery_projektow(d):
            for k, v in self._kolejnosc_arkusza(n).items():
                miejsca.setdefault(k, v)

        def klucz(p):
            sym = str(p.get("symbol") or "").strip().upper()
            naz = str(p.get("nazwa") or "").strip().upper()
            m = miejsca.get(sym, miejsca.get(naz))
            return (0, m, "") if m is not None else (1, 0, sym or naz)
        return sorted(pozycje, key=klucz)

    def _pokaz_pozycje(self, d):
        """Pozycje jednego dokumentu: kolejnosc arkusza RM_BAZA + filtr."""
        self._poz_dok = d
        self._poz_widoczne = []     # pozycje w kolejnosci wierszy panelu
        szukaj = (self.search_var.get() or "").strip().lower()
        filtr = (self.szukaj_poz_var.get() or "").strip().lower()
        pozycje = self._posortuj_jak_arkusz(d, d["pozycje"])
        if filtr:
            pozycje = [p for p in pozycje
                       if filtr in f"{p['symbol']} {p['nazwa']} {p.get('opis', '')}".lower()]
        self._poz_widoczne = pozycje
        # Dokument magazynowy → koszt zamiast ceny netto, także w nagłówkach.
        mag = d["rodzaj"] in self.RODZAJE_MAGAZYNOWE
        naglowki = [k[1] for k in self.KOL_POZ]
        if mag:
            # Indeksy liczone z KOL_POZ, nie wpisane na sztywno: po dołożeniu
            # kolumny „Opis" zapis [4], [5] wskazywałby już J.m. i Cenę.
            i_cena = [k[0] for k in self.KOL_POZ].index("cena")
            naglowki[i_cena], naglowki[i_cena + 1] = self.NAGL_KOSZT
        self.sheet_poz.headers(naglowki)
        self.sheet_poz.set_sheet_data(
            [[p["symbol"], p["nazwa"], p.get("opis", ""),
              f"{p['ilosc']:g}", p["jm"],
              (f"{p['koszt_jedn']:.2f}" if p.get("koszt_jedn") else "") if mag
              else (f"{p['cena']:.2f}" if p["cena"] else ""),
              (f"{p['koszt']:.2f}" if p.get("koszt") else "") if mag
              else (f"{p['cena'] * p['ilosc']:.2f}" if p["cena"] else "")]
             for p in pozycje], reset_col_positions=False, redraw=False)

        # Podświetl pozycje pasujące do wyszukiwarki — po to się szukało.
        try:
            self.sheet_poz.dehighlight_all()
        except Exception:
            pass
        if szukaj:
            for i, p in enumerate(pozycje):
                if szukaj in f"{p['symbol']} {p['nazwa']}".lower():
                    for c in range(len(self.KOL_POZ)):
                        self.sheet_poz.highlight_cells(row=i, column=c, bg="#fcf3cf")
        self.sheet_poz.redraw()

        opis = OPIS_RODZAJU.get(d["rodzaj"], d["rodzaj"])
        self.lbl_poz.config(
            text=f"{opis}   ·   {d['numer']}   ·   {d['podmiot']}"
                 + (f"   ·   projekt {d['projekt']}" if d["projekt"] else "")
                 + (f"   ·   {len(pozycje)} z {len(d['pozycje'])} poz. (🔍 „{filtr}”)"
                    if filtr else f"   ·   {len(d['pozycje'])} poz.")
                 + (f"   ·   {d['wartosc']:.2f} zł" if d["wartosc"] else ""))


    # ── płaska lista wszystkich pozycji ────────────────────────────────────
    def _przelacz_pozycje(self):
        """Przełącza panel: pozycje jednego dokumentu ↔ wszystkie płasko."""
        if self.wszystkie_poz_var.get():
            self._pokaz_wszystkie_pozycje()
        else:
            # Powrót do trybu „jeden dokument": nagłówki i szerokości wracają
            # do KOL_POZ, inaczej zostałyby te z listy płaskiej (9 kolumn).
            self.sheet_poz.headers([k[1] for k in self.KOL_POZ])
            for c, k in enumerate(self.KOL_POZ):
                try:
                    self.sheet_poz.column_width(column=c, width=k[2], redraw=False)
                except Exception:
                    pass
            if self.biezacy:
                d, self.biezacy = self.biezacy, None
                self._pokaz_pozycje(d)
            else:
                self.sheet_poz.set_sheet_data([], reset_col_positions=False)
                self.lbl_poz.config(text="Pozycje — kliknij dokument")

    def _pokaz_wszystkie_pozycje(self):
        """Pozycje ze WSZYSTKICH widocznych dokumentów w jednej liście.

        Bierzemy `self.widoczne`, nie `self.dokumenty` — filtry rodzaju
        i projektu mają działać także tutaj, inaczej lista kłamałaby o tym,
        co użytkownik właśnie zawęził.
        """
        szukaj = (self.search_var.get() or "").strip().lower()
        filtr = (self.szukaj_poz_var.get() or "").strip().lower()
        wiersze, trafienia = [], []
        for d in self.widoczne:
            for p in d["pozycje"]:
                if szukaj and szukaj not in f"{p['symbol']} {p['nazwa']}".lower():
                    continue
                if filtr and filtr not in f"{p['symbol']} {p['nazwa']} {p.get('opis', '')}".lower():
                    continue
                trafienia.append(bool(szukaj))
                wiersze.append([
                    d["numer"], d["rodzaj"], p["symbol"], p["nazwa"],
                    f"{p['ilosc']:g}", p["jm"],
                    # Magazynowe (PW/RW/WZ) niosą KOSZT, handlowe cenę netto.
                    # W liście płaskiej mieszają się rodzaje, więc wybór jest
                    # per wiersz, a nagłówek mówi „/ koszt" dla obu wariantów.
                    (f"{p['koszt_jedn']:.2f}" if p.get("koszt_jedn")
                     else f"{p['cena']:.2f}" if p["cena"] else ""),
                    (f"{p['koszt']:.2f}" if p.get("koszt")
                     else f"{p['cena'] * p['ilosc']:.2f}" if p["cena"] else ""),
                    d["projekt"] or ""])

        self.sheet_poz.headers(["Dokument", "Rodzaj", "Nr rysunku / symbol", "Nazwa",
                                "Ilość", "J.m.", "Cena / koszt jedn.",
                                "Wartość", "Projekt"])
        self.sheet_poz.set_sheet_data(wiersze, reset_col_positions=False, redraw=False)
        # Szerokości USTAWIANE JAWNIE: zapamiętane w JSON-ie dotyczą 7 kolumn
        # trybu „jeden dokument", a tu jest 9 — bez tego dwie ostatnie miałyby
        # przypadkową szerokość.
        #
        # ⚠️ Suma zwężona 02.10.2026 (1060 → 700 px) z tego samego powodu co
        # w KOL_POZ: panel pozycji dostaje ~460-700 px, więc „Wartość"
        # i „Projekt" uciekały poza prawą krawędź.
        for c, w in enumerate((110, 50, 130, 160, 50, 40, 80, 90, 70)):
            try:
                self.sheet_poz.column_width(column=c, width=w, redraw=False)
            except Exception:
                pass
        try:
            self.sheet_poz.dehighlight_all()
        except Exception:
            pass
        # Kolor wiersza wg rodzaju dokumentu — ta sama paleta co w tabeli
        # dokumentów, żeby oko łączyło jedno z drugim.
        kolory = {"ZK": "#d6eaf8", "ZD": "#dfeaf7", "PW": "#d5f0dd",
                  "RW": "#fdebd0", "WZ": "#f4ecf7"}
        for i, w in enumerate(wiersze):
            bg = "#fcf3cf" if trafienia[i] else kolory.get(w[1])
            if bg:
                for c in range(9):
                    self.sheet_poz.highlight_cells(row=i, column=c, bg=bg)
        self.sheet_poz.redraw()

        wart = sum(float(w[7]) for w in wiersze if w[7])
        self.lbl_poz.config(
            text=f"WSZYSTKIE POZYCJE   ·   {len(wiersze)} poz."
                 + (f"   ·   🔍 „{szukaj}”" if szukaj else "")
                 + f"   ·   z {len(self.widoczne)} dok."
                 + (f"   ·   {wart:,.2f} zł".replace(",", " ") if wart else ""))


def open_window(parent, szukaj=None, projekt=None):
    """Punkt wejścia dla RM_BAZA.

    `szukaj` — numer dokumentu, na którym okno ma się ustawić od razu
    (używa tego klik w numer RW w oknie wydania).
    `projekt` — nazwa projektu wybranego w RM_BAZA; filtr „Projekt" startuje
    na jego numerze.
    """
    return DokumentyWindow(parent, szukaj=szukaj, projekt=projekt)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    root = tk.Tk()
    root.withdraw()
    w = open_window(root)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
