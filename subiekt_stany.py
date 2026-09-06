# -*- coding: utf-8 -*-
"""
Podgląd stanów magazynowych z Subiekta nexo PRO dla pozycji projektu RM_BAZA.
TYLKO ODCZYT — ten moduł nigdy nic nie zapisuje do Subiekta.

Wywołanie z RM_BAZA (przycisk „SUBIEKT" w pasku):

    import subiekt_stany
    subiekt_stany.open_window(parent, project_id=22, only_drawings=[...])

`only_drawings` jest opcjonalne — bez niego okno bierze cały BOM projektu.

Dane idą przez most C# (`NexoRecon.exe stan --symbols-file=... --out=...`),
bo Sfera nexo to .NET 8 x64 i nie da się jej wołać wprost z Pythona.
Szczegóły i uzasadnienie: SUBIEKT_INTEGRACJA_PLAN.md, sekcje 10–12.
"""

import json
import os
import re
import subprocess
import sqlite3
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from rm_kreciolek import Kreciolek

try:
    from tksheet import Sheet
except ImportError:                 # brak biblioteki — okno powie wprost
    Sheet = None

# ── Ścieżki ─────────────────────────────────────────────────────────────────
# Most budowany jest do bin/Release obok repo. W .exe (PyInstaller) __file__
# wskazuje na katalog tymczasowy, więc trzymamy też ścieżkę stałą — ta sama
# pułapka co z kluczem AI (patrz pamięć „Pułapka .exe — trwałe ścieżki").
_HERE = os.path.dirname(os.path.abspath(__file__))
EXE_CANDIDATES = [
    os.path.join(_HERE, "subiekt_sfera", "NexoRecon", "bin", "Release", "NexoRecon.exe"),
    r"C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER\subiekt_sfera\NexoRecon\bin\Release\NexoRecon.exe",
    # Stanowisko usera: most lezy OBOK SDK Sfery, ktorego i tak potrzebuje
    # w runtime (C:\iLogic\SUBIEKT\Bin — 435 bibliotek InsERT doladowywanych
    # w locie przez NexoSession.PodepnijSdk). Jedno miejsce na wszystko,
    # co dotyczy Subiekta.
    r"C:\iLogic\Subiekt\MOST\NexoRecon.exe",
    # Poprzednia lokalizacja (do 06.09.2026) — zostaje, zeby stanowiska,
    # ktore zdazyly pobrac most przed zmiana, nie przestaly dzialac.
    r"C:\RMPAK_CLIENT\NexoRecon\NexoRecon.exe",
]
# Sciezka konfiguracji trzymana w subiekt_konfig — to samo miejsce, z ktorego
# okno logowania ja ZAPISUJE. Trzy niezalezne kopie tej stalej grozily
# rozjazdem, gdy doszedl zapis (06.09.2026).
from subiekt_konfig import CONFIG_PATH
# projects_dir zalezy od maszyny (firma: Y:\RM_BAZA\projects, dom/M-OLD:
# C:/RMPAK_CLIENT/RM_BAZY/RM_BAZA/projects) - RM_BAZA juz to rozwiazuje
# poprawnie na kazdej maszynie przez sync_config.json (patrz np.
# RM_BAZA_v15_MAG_STATS_ORG.py, db_manager.projects_dir). Ten modul
# czytal wlasna, twarda sciezke Y: niezalezna od tego configu, wiec na
# M-OLD (gdzie ten sam zasob siedzi pod V:) pekal - "Y:\RM_BAZA\projects\
# project_71.sqlite" (znalezione 2026-09-03). Czytamy teraz ten sam
# sync_config.json co reszta apki, zamiast duplikowac logike.
_SYNC_CONFIG_PATH = r"C:\RMPAK_CLIENT\sync_config.json"
_PROJECTS_DIR_FALLBACK = r"Y:\RM_BAZA\projects"


def _projects_dir():
    try:
        with open(_SYNC_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg["paths"]["projects_dir"]
    except Exception:
        return _PROJECTS_DIR_FALLBACK


PROJECTS_DIR = _projects_dir()

TIMEOUT_S = 180


def _find_exe():
    for p in EXE_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


# Szerokości kolumn okien Subiekta — jeden plik, klucz per okno.
# Osobno od config.json arkusza głównego, żeby nie mieszać do cudzego pliku.
SZEROKOSCI_PLIK = r"C:\RMPAK_CLIENT\subiekt_kolumny.json"


def wczytaj_szerokosci(klucz):
    """[int] albo None — zapamiętane szerokości kolumn dla danego okna."""
    try:
        if not os.path.isfile(SZEROKOSCI_PLIK):
            return None
        with open(SZEROKOSCI_PLIK, encoding="utf-8") as f:
            return (json.load(f) or {}).get(klucz)
    except Exception:
        return None          # szerokości nie są warte psucia startu okna


def zapisz_szerokosci(klucz, szerokosci):
    try:
        dane = {}
        if os.path.isfile(SZEROKOSCI_PLIK):
            try:
                with open(SZEROKOSCI_PLIK, encoding="utf-8") as f:
                    dane = json.load(f) or {}
            except Exception:
                dane = {}
        dane[klucz] = [int(x) for x in szerokosci]
        os.makedirs(os.path.dirname(SZEROKOSCI_PLIK), exist_ok=True)
        with open(SZEROKOSCI_PLIK, "w", encoding="utf-8") as f:
            json.dump(dane, f, indent=1)
    except Exception:
        pass


def podepnij_szerokosci(okno, sheet, klucz, domyslne=None):
    """Wczytuje zapamiętane szerokości i pilnuje ich zapisu przy zmianie.

    Wzorzec z arkusza głównego RM_BAZA (_on_column_resized): tksheet 7.5.19
    nie ma zdarzenia „kolumna zmieniła szerokość", więc łapiemy puszczenie
    myszy na PASKU NAGŁÓWKÓW — tam kończy się przeciąganie. after_idle, bo
    w momencie ButtonRelease tksheet nie zapisał jeszcze nowej szerokości;
    porównanie z ostatnim stanem, żeby zwykłe klikanie nie waliło w dysk.
    """
    zapisane = wczytaj_szerokosci(klucz)

    # ⚠️ Zapamiętane szerokości pasują TYLKO do tego układu kolumn, w którym
    # powstały. Po dołożeniu kolumny stara lista nakładała się z przesunięciem:
    # nowa kolumna dostawała szerokość sąsiada, a ostatnia wypadała poza ekran
    # — wyglądało to, jakby kolumny w ogóle nie było (zgłoszone 05.09.2026,
    # brak kolumny „PDF"). Przy niezgodnej długości bierzemy domyślne.
    try:
        ile_kolumn = len(sheet.headers())
    except Exception:
        ile_kolumn = len(domyslne or zapisane or [])
    if zapisane and ile_kolumn and len(zapisane) != ile_kolumn:
        print(f"ℹ️  Układ kolumn „{klucz}” zmienił się "
              f"({len(zapisane)} → {ile_kolumn}) — szerokości ustawiam domyślne.")
        zapisane = None

    if zapisane:
        for i, w in enumerate(zapisane):
            try:
                sheet.column_width(column=i, width=int(w))
            except Exception:
                break        # węższa tabela niż zapis — reszta zostaje domyślna
    elif domyslne:
        for i, w in enumerate(domyslne):
            try:
                sheet.column_width(column=i, width=int(w))
            except Exception:
                break

    ostatnie = {"v": None}

    def sprawdz():
        try:
            obecne = list(sheet.get_column_widths())
            if obecne and obecne != ostatnie["v"]:
                ostatnie["v"] = obecne
                zapisz_szerokosci(klucz, obecne)
        except Exception:
            pass

    def po_puszczeniu(_event=None):
        try:
            okno.after_idle(sprawdz)
        except Exception:
            pass

    try:
        sheet.CH.bind("<ButtonRelease-1>", po_puszczeniu, add="+")
    except Exception:
        pass                 # starsze tksheet — szerokości po prostu się nie zapiszą


def jedna_linia(s):
    """Skleja tekst złamany na kilka linii w jedną.

    BOM-y importowane z Excela mają w komórkach twarde entery — nazwa
    „CHEM UPE-\\n050" to JEDNA nazwa zawinięta w arkuszu. Bez sklejenia
    wiersz w tabeli rozjeżdża się na dwie linie, a do Subiekta poszedłby
    symbol ze znakiem nowej linii w środku (zgłoszone 04.09.2026).
    Łącznik na końcu linii („CHEM UPE-\\n050") sklejamy bez spacji.
    """
    s = str(s or "").replace("\r\n", "\n").replace("\r", "\n")
    czesci = [c.strip() for c in s.split("\n") if c.strip()]
    if not czesci:
        return ""
    out = czesci[0]
    for c in czesci[1:]:
        out += c if out.endswith("-") else " " + c
    return " ".join(out.split())          # zwielokrotnione spacje i taby


def wysrodkuj(okno, rodzic, szerokosc=None, wysokosc=None):
    """Ustawia okno na środku okna rodzica (nie ekranu).

    Bez tego Tk stawia Toplevel w lewym górnym rogu ekranu — na dwóch
    monitorach okno potrafi wyskoczyć zupełnie gdzie indziej niż aplikacja.
    Wołać PO zbudowaniu zawartości, żeby okno znało swój rozmiar.
    """
    try:
        okno.update_idletasks()
        w = szerokosc or okno.winfo_width() or okno.winfo_reqwidth()
        h = wysokosc or okno.winfo_height() or okno.winfo_reqheight()

        # Rodzic zmaksymalizowany albo jeszcze nierozłożony — bierzemy ekran.
        rw, rh = rodzic.winfo_width(), rodzic.winfo_height()
        if rw > 1 and rh > 1:
            x = rodzic.winfo_rootx() + (rw - w) // 2
            y = rodzic.winfo_rooty() + (rh - h) // 2
        else:
            x = (okno.winfo_screenwidth() - w) // 2
            y = (okno.winfo_screenheight() - h) // 2

        # Nie wypychamy okna poza ekran (ujemne współrzędne = tytuł poza kadrem).
        x = max(0, min(x, okno.winfo_screenwidth() - w))
        y = max(0, min(y, okno.winfo_screenheight() - h))
        okno.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass          # pozycjonowanie nie może wywalić okna


def most_starszy_niz_zrodla(exe):
    """(True, opis) jeśli .exe jest starszy niż pliki .cs mostu.

    `bin/` jest w .gitignore, więc po `git pull` przychodzą źródła BEZ
    binarki. Python woła wtedy tryb, którego stary .exe nie zna — a ten
    ignoruje nieznany argument i uruchamia domyślne rozpoznanie: kończy się
    kodem 0, nie tworzy pliku --out, i wypluwa listę magazynów i kartotek.
    Wygląda to jak problem z połączeniem, choć połączenie działa (zdarzyło
    się realnie 04.09.2026 po pullu z trybem „katalog").
    """
    try:
        if not exe or not os.path.isfile(exe):
            return False, ""
        t_exe = os.path.getmtime(exe)
        src_dir = os.path.join(_HERE, "subiekt_sfera", "NexoRecon")
        nowsze = []
        for nazwa in os.listdir(src_dir):
            if not nazwa.lower().endswith(".cs"):
                continue
            p = os.path.join(src_dir, nazwa)
            if os.path.getmtime(p) > t_exe + 1:      # 1 s luzu na zaokrąglenia
                nowsze.append(nazwa)
        if not nowsze:
            return False, ""
        return True, ", ".join(sorted(nowsze))
    except Exception:
        return False, ""                              # diagnostyka nie może wywalić wywołania


def blad_mostu(exe, tryb, proc, out_path):
    """Czytelny komunikat błędu wywołania mostu.

    Najpierw sprawdza najczęstszą przyczynę (nieaktualny .exe po pullu),
    bo surowy wypis rozpoznania myli — wygląda jak błąd Subiekta.
    """
    stary, pliki = most_starszy_niz_zrodla(exe)
    if stary and proc.returncode == 0 and not os.path.isfile(out_path):
        return (
            "NIEAKTUALNY MOST — trzeba go przebudować.\n\n"
            f"NexoRecon.exe nie zna trybu „{tryb}”: jest starszy niż źródła\n"
            f"({pliki}). Katalog bin/ nie idzie przez gita, więc po „git pull”\n"
            "binarkę trzeba zbudować u siebie:\n\n"
            "    cd subiekt_sfera\\NexoRecon\n"
            "    dotnet build -c Release -nowarn:MSB3277\n\n"
            "Połączenie z Subiektem jest sprawne — problem jest tylko w wersji mostu."
        )
    msg = (proc.stdout or "").strip() or (proc.stderr or "").strip() or "nieznany błąd"
    return f"Most zwrócił błąd (kod {proc.returncode}):\n\n{msg}"


# ── Odczyt numerów rysunków z bazy projektu ─────────────────────────────────
def nazwa_projektu(project_id):
    """Nazwa projektu z master.sqlite ("3000 Testowy") albo "".

    Potrzebna do struktury zlozen: read_tree() szuka folderu projektu po
    NAZWIE, nie po id. Okno stanow dostaje z RM_BAZA samo project_id, wiec
    dociagamy ja tutaj, zamiast zmieniac sygnature open_window i wszystkie
    wywolania.
    """
    sciezka = os.path.join(os.path.dirname(PROJECTS_DIR), "master.sqlite")
    if not os.path.isfile(sciezka):
        return ""
    try:
        con = sqlite3.connect(f"file:{sciezka}?mode=ro", uri=True, timeout=5)
        try:
            r = con.execute("SELECT name FROM projects WHERE project_id=?",
                            (project_id,)).fetchone()
        finally:
            con.close()
        return (r[0] or "").strip() if r else ""
    except sqlite3.Error:
        return ""


def read_project_drawings(project_id):
    """[(numer, nazwa, ilosc_bom, modul)] — jedna pozycja na numer rysunku.

    Kolejność work > norm > src jest ta sama, której użyto przy porównaniu
    zbiorów w planie (sekcja 12.2), żeby wyniki się zgadzały.
    """
    path = os.path.join(PROJECTS_DIR, f"project_{project_id}.sqlite")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info('items')")}
        # Nazwa i ilość mają te same prefiksy co numer rysunku (work_ > src_),
        # a *_over to ręczne nadpisanie przez użytkownika — ma pierwszeństwo.
        # Kolumny *_over to FLAGI nadpisania (INTEGER 0/1), nie wartości —
        # brane tutaj dawały nazwę „0” i zerową „Ilość BOM”.
        name_cols = [c for c in ("work_name", "src_name") if c in cols]
        qty_cols = [c for c in ("order_qty", "work_qty", "src_qty") if c in cols]
        # Modul do grupowania w widoku drzewka. Kolejnosc work > src taka sama
        # jak w arkuszu (COALESCE(NULLIF(work_modul,''), src_modul)) — inaczej
        # drzewko rozjechaloby sie z tym, co user widzi w RM_BAZA.
        modul_cols = [c for c in ("work_modul", "src_modul") if c in cols]
        sel = ["work_drawing_no", "norm_drawing_no", "src_drawing_no"] + name_cols + qty_cols + modul_cols
        # Ukryte pozycje (przycisk „Ukryj zaznaczone" w arkuszu) nie mają
        # trafiać do Subiekta — COALESCE bo starsze wiersze mogą mieć NULL
        # zamiast 0 (ten sam wzorzec co database_manager.get_project_items).
        where = " WHERE COALESCE(is_hidden, 0) = 0" if "is_hidden" in cols else ""
        rows = con.execute(f"SELECT {', '.join(sel)} FROM items{where}").fetchall()
    finally:
        con.close()

    n0 = 3
    q0 = n0 + len(name_cols)
    m0 = q0 + len(qty_cols)

    def first(vals):
        for v in vals:
            if v is not None and str(v).strip() != "":
                return v
        return None

    out, seen = [], set()
    for r in rows:
        nr = first(r[0:3])
        nr = str(nr).strip() if nr is not None else None
        # ⚠️ POZYCJE BEZ NUMERU RYSUNKU TEZ SA TOWAREM. Normalia handlowe
        # (lozyska „6001RS", paski „5M 25 CP") maja w BOM-ie tylko nazwe —
        # a ta nazwa JEST symbolem katalogowym, wiec pytamy o nia Subiekta
        # tak samo jak o numer. Wczesniej takie wiersze wypadaly tutaj i okno
        # pokazywalo 283 z 359 pozycji projektu, bez sladu po brakujacych
        # 76 (zgloszone 06.09.2026). Brak kartoteki nie jest bledem: znaczy,
        # ze pozycja jest nowa i kartoteka powstanie przy pierwszym zamowieniu.
        if not nr:
            nazwa_zam = first(r[n0:q0])
            nr = str(nazwa_zam).strip() if nazwa_zam is not None else None
        if not nr or nr in seen:
            continue
        seen.add(nr)
        nazwa = first(r[n0:q0])
        qty = first(r[q0:m0])
        modul = first(r[m0:])
        out.append((nr, str(nazwa).strip() if nazwa is not None else "", qty,
                    str(modul).strip() if modul is not None else ""))
    return out


#: Pozycja bez modulu — wlasna galaz, zeby nie znikala z drzewka.
MODUL_BRAK = "(bez modulu)"

#: iid wezla zbierajacego pozycje spoza struktury zlozen.
# Czytelny, bo tksheet POKAZUJE iid w naglowku bocznym drzewa. Kolizja
# z numerem rysunku niemozliwa — zaden numer nie ma spacji i polskich liter.
POZA_IID = "poza strukturą"


def moduly_pozycji(modul):
    """Lista modulow jednej pozycji. Pozycja bywa w KILKU naraz.

    W BOM-ach spotyka sie "350,380" albo "000,200,350" — to detal wspolny dla
    kilku modulow. Arkusz glowny rozbija to po przecinku i pokazuje pozycje
    przy KAZDYM z nich (patrz filtr modulu w RM_BAZA_v15_MAG_STATS_ORG),
    wiec drzewko robi tak samo. Skutek uboczny: sumy na wezlach nie zsumuja
    sie do liczby pozycji — i tak ma byc, pisze o tym podpis pod tabela.

    Format z nawiasem ("KABINA(2)x3") tez wystepuje — bierzemy sam poczatek,
    jak arkusz.
    """
    surowy = (modul or "").strip()
    if not surowy:
        return [MODUL_BRAK]
    czesci = []
    for kawalek in surowy.split(","):
        kawalek = kawalek.strip()
        if not kawalek:
            continue
        dop = re.match(r"([^(]+)\s*\((\d+)\)(?:x(\d+))?", kawalek)
        czesci.append(dop.group(1).strip() if dop else kawalek)
    return czesci or [MODUL_BRAK]


def looks_like_drawing_no(s):
    """Czy to wygląda na numer rysunku, a nie na opis?

    W BOM-ach trafiają się nazwy wpisane w pole numeru („Przygotowanie
    powietrza", „Obejma") — sprawdzanie ich w Subiekcie nie ma sensu
    (plan, sekcja 12.2). Numer musi mieć cyfrę i nie może mieć spacji.

    ⚠️ Warunek „bez spacji" ODRZUCA TEZ REALNE SYMBOLE normaliow („5M 25 CP",
    „UCFL 204") — dlatego okno stanow uzywa `wyglada_na_towar`, a nie tej
    funkcji. Ta zostaje dla miejsc, ktore naprawde chca samych numerow
    rysunkow.
    """
    s = (s or "").strip()
    return bool(s) and any(c.isdigit() for c in s) and " " not in s


def wyglada_na_towar(s):
    """Czy to symbol, o ktory warto zapytac Subiekta.

    Szersze niz `looks_like_drawing_no`: przepuszcza symbole katalogowe ze
    spacjami („5M 25 CP", „61906ZZ"), bo normalia w BOM-ie siedza w polu
    nazwy i tak wlasnie wygladaja. Odcinamy tylko opisy — zdania bez zadnej
    cyfry („Przygotowanie powietrza") albo bardzo dlugie.
    """
    s = (s or "").strip()
    # Bez warunku "ma cyfre": odrzucal "Filtr", "Zamek", "mikroguma",
    # "sprezyna klawiszy" (280 szt.!) — pozycje BOM bez numeru rysunku
    # i bez cyfry w nazwie, ktore trzeba zamowic tak samo jak reszte.
    # Zasada uzytkownika (06.09.2026): nie ma symbolu = pozycja jest nowa,
    # kartoteka powstanie przy pierwszym zamowieniu. Odcinamy juz tylko
    # puste i absurdalnie dlugie (zdania-opisy).
    return bool(s) and len(s) <= 60


# ── Wywołanie mostu ─────────────────────────────────────────────────────────
def query_stock(symbols, timeout=TIMEOUT_S):
    """Pyta Subiekta o stany. Zwraca {pytany_symbol: dict}. Rzuca RuntimeError.

    Idzie przez stały most — druga i kolejna próba nie płaci ~10 s za start
    procesu i logowanie. Gdy mostu nie ma, leci starym CLI.
    """
    try:
        import subiekt_bridge
    except ImportError:
        return _query_stock_cli(symbols, timeout)

    dane = subiekt_bridge.call(
        "stan", {"symbols": list(symbols)}, timeout=timeout,
        fallback=lambda: _query_stock_cli(symbols, timeout))
    if isinstance(dane, dict) and "pozycje" in dane:
        return {p["Pytany"]: p for p in dane.get("pozycje", [])}
    return dane          # fallback zwrócił gotowy słownik


def _query_stock_cli(symbols, timeout=TIMEOUT_S):
    """Stara ścieżka: osobny proces NexoRecon.exe na każde zapytanie."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError(
            "Nie znaleziono NexoRecon.exe.\n\n"
            "Zbuduj most:\n"
            "  cd subiekt_sfera\\NexoRecon\n"
            "  dotnet build -c Release"
        )
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")

    tmpdir = tempfile.mkdtemp(prefix="subiekt_")
    lst = os.path.join(tmpdir, "symbole.txt")
    out = os.path.join(tmpdir, "stan.json")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("\n".join(symbols))

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            [exe, "stan", f"--symbols-file={lst}", f"--out={out}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=flags,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Subiekt nie odpowiedział w {timeout} s.")

    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, "stan", proc, out))

    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    return {p["Pytany"]: p for p in data.get("pozycje", [])}


# ── Okno ────────────────────────────────────────────────────────────────────
class SubiektStanyWindow(tk.Toplevel, Kreciolek):
    #: Kolor tła wiersza per kategoria. Jedno źródło prawdy dla tagów
    #: Treeview i dla próbek w legendzie — inaczej rozjechałyby się przy
    #: pierwszej zmianie odcienia.
    KOLORY = {
        "ok":     "#d5f5e3",   # starczy na magazynie
        "czesc":  "#fdebd0",   # jest, ale za mało
        "brak":   "#fadbd8",   # jest kartoteka, stan 0
        "nokart": "#eaecee",   # brak kartoteki
    }

    COLS = [
        # Lp. jako ZWYKLA kolumna: w drzewku naglowek boczny zajmuje
        # struktura (wciecia, strzalki), wiec numeracja tksheet znika.
        # Numerujemy tylko pozycje — wezly zlozen bez pozycji zostaja puste,
        # zeby ostatni numer mowil, ile jest realnych pozycji (06.09.2026).
        ("lp",     "Lp.",             48, "e"),
        ("nr",     "Nr rysunku",     140, "w"),
        # Nazwa zaraz za numerem — numer sam nic nie mowi, a szukajac pozycji
        # czyta sie te dwie kolumny razem. Wczesniej siedziala za trzema
        # kolumnami liczb (zgloszone 06.09.2026).
        ("nazwa",  "Nazwa w Subiekcie", 260, "w"),
        ("bom",    "Ilość BOM",       75, "e"),
        ("stan",   "Stan Subiekt",    95, "e"),
        ("brak",   "Do zamówienia",   95, "e"),
        ("cena",   "Ost. cena zak.",  95, "e"),
        ("data",   "Data zakupu",      90, "c"),
        ("status", "Status",          150, "w"),
    ]

    def __init__(self, parent, project_id, only_drawings=None):
        super().__init__(parent)
        self.project_id = project_id
        self.only_drawings = only_drawings
        self.rows = []
        self.project_name = nazwa_projektu(project_id)
        #: {rodzic: [(dziecko, ilosc)]} — struktura zlozen z *_OUT.xlsx
        self.kids = {}
        #: tag koloru per wiersz — tksheet koloruje po indeksie, nie po tagu
        self._tagi = []
        #: iid wezlow majacych potomstwo — do "Rozwin wszystko"
        self._iid_wezlow = []
        self.blad_drzewa = None

        self.title(f"Stany w Subiekcie — projekt {project_id}")
        # Okno startuje ZMAKSYMALIZOWANE, jak Magazyn i Zamowienia — lista
        # bywa dluga (283 pozycje w projekcie 89), a domyslny rozmiar Tk
        # pokazywal kilkanascie wierszy. geometry() zostaje jako rozmiar po
        # przywroceniu z maksymalizacji, minsize() pilnuje, zeby po recznym
        # zwezeniu dalo sie jeszcze czytac naglowki kolumn.
        # state("zoomed") jest windowsowe — gdzie indziej rzuca TclError.
        self.geometry("1250x700")
        self.minsize(900, 420)
        # ŚWIADOMIE bez transient(): okno-dziecko z transient dostaje w Windows
        # tylko przycisk „×", bez minimalizacji i maksymalizacji. To pelnoprawny
        # arkusz roboczy (283 pozycje), wiec ma miec komplet (— □ ×) — tak samo
        # jak Zamowienia i Magazyn (zgloszone 06.09.2026).
        try:
            self.state("zoomed")
        except tk.TclError:
            wysrodkuj(self, parent)

        self._build_ui()
        self.after(100, self._load_async)

    def _build_ui(self):
        top = tk.Frame(self, bg="#34495e", height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)

        tk.Label(top, text="📦 Stany pozycji projektu w Subiekcie",
                 bg="#34495e", fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)

        self.btn_refresh = tk.Button(top, text="🔄 Odśwież", command=self._load_async,
                                     bg="#3498db", fg="white", font=("Arial", 8),
                                     padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_refresh.pack(side=tk.RIGHT, padx=10, pady=8)

        # Zdejmuje zaznaczone pozycje Z TEGO WIDOKU. Nic nie zapisuje — okno
        # jest tylko do odczytu, a po "Odswiez" pozycje wracaja. Sluzy do
        # przyciecia listy przed dalszymi krokami (np. gdy czegos swiadomie
        # nie zamawiamy przez Subiekta), dopoki nic nie poszlo dalej.
        # Etykieta mowi wprost, ze to tylko widok — "Usun pozycje" sugerowalo
        # zapis do projektu (06.09.2026).
        tk.Button(top, text="🗑 Usuń z widoku (nie zapisuje)", command=self._usun_pozycje,
                  bg="#c0392b", fg="white", font=("Arial", 8),
                  padx=8, pady=2, relief=tk.RAISED, bd=1
                  ).pack(side=tk.RIGHT, padx=4, pady=8)

        # Widok drzewka domyslnie i ZWINIETY: 283 pozycje to 9 wierszy modulow
        # zamiast dlugiej listy — od razu widac, ktory modul jest niezaopatrzony
        # (ustalone 06.09.2026). Plaska lista zostaje pod przyciskiem, bez zmian.
        self.var_drzewko = tk.BooleanVar(value=True)

        self.chk_drzewko = tk.Checkbutton(
            top, text="Drzewko", variable=self.var_drzewko,
            command=self._przelacz_widok, bg="#34495e", fg="white",
            selectcolor="#27ae60", font=("Arial", 8),
            activebackground="#34495e", activeforeground="white")
        self.chk_drzewko.pack(side=tk.RIGHT, padx=4)

        # Rozwijanie hurtem — te same przyciski co w oknie "Zaloz projekt",
        # bo przy 49 zlozeniach klikanie kazdego z osobna to droga donikad.
        # Chowane w widoku plaskim: tam nie ma czego rozwijac.
        self.ramka_rozwin = tk.Frame(top, bg="#34495e")
        self.ramka_rozwin.pack(side=tk.RIGHT, padx=4)
        for txt, cmd in (("\u229e Rozwiń wszystko", lambda: self._rozwin(True)),
                         ("\u229f Zwiń", lambda: self._rozwin(False))):
            tk.Button(self.ramka_rozwin, text=txt, command=cmd, bg="#5499c7",
                      fg="white", font=("Arial", 8), padx=8, pady=1,
                      relief=tk.RAISED, bd=1, cursor="hand2"
                      ).pack(side=tk.LEFT, padx=3, pady=4)

        self.var_only_missing = tk.BooleanVar(value=False)
        tk.Checkbutton(top, text="Tylko braki", variable=self.var_only_missing,
                       command=self._refill, bg="#34495e", fg="white", selectcolor="#e67e22",
                       font=("Arial", 8), activebackground="#34495e",
                       activeforeground="white").pack(side=tk.RIGHT, padx=4)

        # Pasek podsumowania: ile ma kartotekę, ile na stanie, ile brakuje.
        #
        # Liczniki kategorii są zarazem LEGENDĄ kolorów wierszy — każdy dostaje
        # próbkę w tym samym kolorze co tło wiersza w tabeli. Wcześniej pasek
        # używał symboli (✅ ⚠ ❌), których w tabeli nie ma, więc nie dało się
        # powiązać kategorii z kolorem inaczej niż zgadywaniem (zgłoszone
        # 06.09.2026).
        self.summary = tk.Frame(self, bg="#ecf0f1")
        self.summary.pack(side=tk.TOP, fill=tk.X)
        self._summary_wnetrze = None
        self._summary_tekst("Wczytywanie…")

        wrap = tk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 8))

        # tksheet, nie ttk.Treeview — ten sam widget co w Zamowieniach
        # i Magazynie (zgloszone 06.09.2026: "zrob w takim samym formacie").
        # Powod techniczny: Treeview NIE MA linii siatki, a stylowanie
        # "Treeview.Cell" nic nie daje — takiego elementu w ttk nie ma.
        # tksheet rysuje siatke sam, numeruje wiersze w naglowku bocznym
        # i pamieta szerokosci kolumn miedzy sesjami. Drzewko zlozen zostaje:
        # tksheet 7.x ma tree_build() z kolumna id i kolumna rodzica.
        if Sheet is None:
            tk.Label(wrap, fg="#c0392b", font=("Arial", 10),
                     text="Brak biblioteki tksheet — zainstaluj: pip install tksheet"
                     ).pack(pady=20)
            self.sheet = None
        else:
            # ⚠️ treeview=True JUZ TUTAJ. Samo tree_build() na zwyklym arkuszu
            # buduje strukture, ale nie wlacza trybu drzewa: nie ma strzalek
            # rozwijania i klik w naglowek boczny nic nie robi — "drzewko nie
            # dziala" (06.09.2026). Widok plaski przelacza tryb z powrotem
            # przez set_options(treeview=False) w _refill.
            self.sheet = Sheet(wrap, headers=[c[1] for c in self.COLS],
                               column_width=120, theme="light blue",
                               treeview=True)
            self.sheet.set_options(show_selected_cells_border=True,
                                   enable_edit_cell_auto_resize=False,
                                   empty_horizontal=0, empty_vertical=0)
            self.sheet.enable_bindings((
                "single_select", "drag_select", "ctrl_select", "select_all",
                "column_width_resize", "arrowkeys", "right_click_popup_menu",
                "rc_select", "copy",
            ))
            try:
                self.sheet.readonly_columns(columns=list(range(len(self.COLS))))
            except Exception:
                pass            # starsza tksheet — tabela i tak jest do odczytu
            podepnij_szerokosci(self, self.sheet, "stany",
                                [c[2] for c in self.COLS])
            self.sheet.bind("<Double-Button-1>", self._show_details, add="+")
            self.sheet.pack(fill=tk.BOTH, expand=True)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    # ── wczytywanie ────────────────────────────────────────────────────────
    def _load_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.start_kreciolek("Łączenie z Subiektem")
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        try:
            # Struktura zlozen z arkusza "DRZEWKO TEKST" (*_OUT.xlsx z Inventora)
            # — to samo zrodlo, z ktorego korzysta okno "Zaloz projekt
            # w Subiekcie", zeby oba drzewka wygladaly tak samo. Brak plikow
            # nie jest bledem: okno pokazuje wtedy plaska liste.
            try:
                from subiekt_projekt import read_tree
                kids, blad_drzewa, _nazwy = read_tree(self.project_name or "")
            except Exception as e:
                kids, blad_drzewa = {}, str(e)

            items = read_project_drawings(self.project_id)
            if self.only_drawings:
                wanted = {str(d).strip() for d in self.only_drawings}
                items = [it for it in items if it[0] in wanted]

            good = [it for it in items if wyglada_na_towar(it[0])]
            skipped = len(items) - len(good)
            if not good:
                self.after(0, lambda: self._done([], 0, "Brak pozycji z numerem rysunku."))
                return

            stock = query_stock([it[0] for it in good])
            rows = []
            for nr, nazwa, qty, modul in good:
                info = stock.get(nr, {})
                rows.append({
                    "nr": nr, "bom_name": nazwa, "bom_qty": qty,
                    "modul": modul,
                    "istnieje": bool(info.get("Istnieje")),
                    "symbol": info.get("Symbol"),
                    "nazwa": info.get("Nazwa") or "",
                    "stan": float(info.get("Dostepne") or 0),
                    "cena": info.get("OstatniaCenaZakupu"),
                    "data": info.get("DataOstatniegoZakupu") or "",
                    "dop": info.get("Dopasowanie") or "brak",
                    "mags": info.get("Magazyny") or [],
                })
            self.after(0, lambda: self._done(rows, skipped, None, kids, blad_drzewa))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._done([], 0, err))

    def _done(self, rows, skipped, error, kids=None, blad_drzewa=None):
        self.btn_refresh.config(state=tk.NORMAL)
        self.rows = rows
        self.kids = kids or {}
        self.blad_drzewa = blad_drzewa
        # Bez struktury drzewko nie ma sensu — przelaczamy na plaska liste
        # i mowimy dlaczego, zamiast pokazywac pusta ramke.
        if not self.kids:
            self.var_drzewko.set(False)
        if error:
            self.stop_kreciolek()
            self.status.config(text="Błąd.")
            self._summary_tekst(error.split("\n")[0])
            messagebox.showerror("Subiekt", error, parent=self)
            return
        self._refill()
        note = f"   ({skipped} pozycji pominięto — w polu numeru jest opis, nie numer)" if skipped else ""
        self.stop_kreciolek()
        self.status.config(text=f"Odczyt zakończony. Nic nie zapisano do Subiekta.{note}")

    # ── prezentacja ────────────────────────────────────────────────────────
    @staticmethod
    def _classify(r):
        if not r["istnieje"]:
            return "nokart", "brak kartoteki"
        need = r["bom_qty"]
        try:
            need = float(need) if need not in (None, "") else None
        except (TypeError, ValueError):
            need = None
        if r["stan"] <= 0:
            return "brak", "kartoteka, stan 0"
        if need and r["stan"] < need:
            return "czesc", f"za mało (brakuje {need - r['stan']:g})"
        label = "na stanie"
        if r["dop"] == "luzne":
            label += "  ⚠ dopasowano luźno"
        return "ok", label

    def _rozwin(self, otwarte):
        """Rozwija albo zwija cale drzewo naraz.

        Bez tego pozycje siedza schowane w zlozeniach i wyglada, jakby ich
        nie bylo — ten sam powod co w oknie "Zaloz projekt w Subiekcie".
        """
        if not self.sheet:
            return
        try:
            if otwarte:
                self.sheet.tree_set_open(open_ids=list(self._iid_wezlow))
            else:
                self.sheet.tree_set_open(open_ids=[])
        except Exception:
            pass
        self._odswiez_kolory()

    def _rozwiniete_teraz(self):
        """Numery aktualnie rozwinietych wezlow.

        „Tylko braki" buduje tabele od nowa, wiec bez tego kazde klikniecie
        filtra zwijalo wszystko do korzenia (zgloszone 06.09.2026). Stan
        czytamy WPROST z arkusza, bez skrotu typu "rozwinieto wszystko" —
        inaczej pozniejsze reczne zwiniecie jednej galezi byloby cofane.
        """
        if not self.sheet:
            return []
        try:
            return list(self.sheet.tree_get_open())
        except Exception:
            return []

    def _przelacz_widok(self):
        """Lista <-> drzewko."""
        self._refill()

    def _wiersz_wartosci(self, r):
        """(krotka do kolumn, tag koloru, ile brakuje) dla jednej pozycji.

        Wspolne dla obu widokow — inaczej drzewko i lista rozjechalyby sie
        przy pierwszej zmianie sposobu liczenia brakow.
        """
        tag, status = self._classify(r)
        need = r["bom_qty"]
        try:
            need_f = float(need) if need not in (None, "") else None
        except (TypeError, ValueError):
            need_f = None
        # Brakuje = ile trzeba dokupic. Bez kartoteki nie ma nic na stanie,
        # wiec brakuje calej ilosci z BOM (wczesniej zostawialo pusto, co
        # wygladalo, jakby modul nic nie policzyl).
        missing, brak_f = "", 0.0
        if need_f is not None:
            brak = need_f - (r["stan"] if r["istnieje"] else 0)
            if brak > 0:
                missing, brak_f = f"{brak:g}", brak
        wartosci = [
            "",                     # Lp. — nadawane w _refill po zbudowaniu
            r["nr"],
            r["nazwa"] or (r["bom_name"] if not r["istnieje"] else ""),
            "" if need in (None, "") else f"{need:g}" if isinstance(need, (int, float)) else need,
            f"{r['stan']:g}" if r["istnieje"] else "brak kart.",
            missing,
            f"{r['cena']:.2f}" if r["cena"] is not None else "",
            r["data"],
            status,
        ]
        return wartosci, tag, brak_f

    def _refill(self):
        if not self.sheet:
            return
        otwarte_przed = self._rozwiniete_teraz()
        only_missing = self.var_only_missing.get()
        drzewko = bool(self.var_drzewko.get() and self.kids)
        n_kart = n_ok = n_czesc = n_brak = n_nokart = 0

        widoczne = []
        for r in self.rows:
            tag, _status = self._classify(r)
            if tag == "ok":
                n_ok += 1
            elif tag == "czesc":
                n_czesc += 1
            elif tag == "brak":
                n_brak += 1
            else:
                n_nokart += 1
            if r["istnieje"]:
                n_kart += 1
            if only_missing and tag == "ok":
                continue
            widoczne.append(r)

        # Kolor per wiersz trzymamy osobno: tksheet koloruje po INDEKSIE
        # wiersza, a nie po tagu jak Treeview.
        self._tagi = []
        self._iid_wezlow = []
        if drzewko:
            dane = self._dane_drzewka(widoczne)
        else:
            dane = []
            for r in widoczne:
                wartosci, tag, _ = self._wiersz_wartosci(r)
                dane.append([r["nr"], ""] + wartosci)
                self._tagi.append(tag)

        lp = 0
        for w, tag in zip(dane, self._tagi):
            if tag != "modul":
                lp += 1
                w[2] = lp

        try:
            # ⚠️ tksheet rysuje DRZEWO W NAGLOWKU BOCZNYM (tam, gdzie w liscie
            # sa numery wierszy): wciecia, strzalki rozwijania i tekst iid.
            # Domyslna szerokosc tego naglowka miesci trzy znaki — numery
            # rysunkow byly ucinane do "263", a strzalek nie bylo widac
            # w ogole ("okno sie rozsypalo", 06.09.2026). Stad szerokosc
            # ustawiana per widok. Przed lista trzeba tez WYLACZYC tryb
            # drzewa (tree_reset), inaczej set_sheet_data zostawia arkusz
            # w polowie drogi miedzy jednym a drugim.
            if not drzewko:
                try:
                    self.sheet.tree_reset()
                except Exception:
                    pass
                self.sheet.set_options(treeview=False)
                # Naglowek boczny schowany: numeruje sam, a Lp. juz jest
                # kolumna — w liscie byly dwie numeracje obok siebie.
                self.sheet.hide(canvas="row_index")
            else:
                self.sheet.set_options(treeview=True)
                self.sheet.show(canvas="row_index")
                self.sheet.set_index_width(230)
            if not dane:
                self.sheet.set_sheet_data([], reset_col_positions=False)
            elif drzewko:
                # iid_column=0, parent_column=1 — techniczne, wiec
                # include_*=False, zeby nie pokazaly sie w arkuszu.
                self.sheet.tree_build(
                    data=[list(w) for w in dane], iid_column=0, parent_column=1,
                    include_iid_column=False, include_parent_column=False,
                    open_ids=[x for x in otwarte_przed if x in self._iid_wezlow])
            else:
                self.sheet.set_sheet_data([w[2:] for w in dane],
                                          reset_col_positions=False)
                # ⚠️ Po tree_reset() arkusz zostaje z all_rows_displayed=False
                # i PUSTA lista wierszy do pokazania (zwiniete wezly ukrywaly
                # potomstwo przez displayed_rows, a reset tego nie cofa).
                # Lista wygladala na pusta mimo 354 wierszy danych
                # ("nie dziala plaska wersja", 06.09.2026).
                self.sheet.display_rows("all")
        except Exception:
            # tree_build bywa kapryśny przy niespojnej strukturze — plaska
            # lista zawsze zadziala i jest lepsza niz puste okno.
            self.sheet.set_sheet_data([list(w[2:]) for w in dane],
                                      reset_col_positions=False)
        self._odswiez_kolory()

        total = len(self.rows)
        pct = (n_kart / total * 100) if total else 0
        self._summary_liczniki(total, n_kart, pct, n_ok, n_czesc, n_brak, n_nokart)

    def _odswiez_kolory(self):
        """Tlo wierszy wg kategorii — to ono wiaze tabele z legenda."""
        if not self.sheet:
            return
        try:
            self.sheet.dehighlight_all()
            # highlight_cells od kolumny 1, NIE highlight_rows: kolor kategorii
            # ma byc na danych pozycji, a nie na kolumnie Lp. ani na naglowku
            # bocznym z drzewkiem — te maja zostac neutralne, jak numeracja
            # w Zamowieniach (zgloszone 06.09.2026).
            kolumny = range(1, len(self.COLS))
            for i, tag in enumerate(self._tagi):
                kolor = self.KOLORY.get(tag)
                if kolor:
                    for c in kolumny:
                        self.sheet.highlight_cells(row=i, column=c, bg=kolor)
            self.sheet.refresh()
        except Exception:
            pass                    # kolory to kosmetyka, nie moga wywalic okna

    def _dane_drzewka(self, widoczne):
        """Wiersze w STRUKTURZE ZLOZEN: [iid, parent, ...kolumny].

        Hierarchia pochodzi z arkusza „DRZEWKO TEKST" (`kids`: rodzic ->
        [(dziecko, ilosc)]), a nie z pol bazy — RM_BAZA trzyma BOM plasko.

        Trzy rzeczy, ktore musi ogarnac:
          * pozycje spoza drzewa (normalia, ktorych nie ma w *_OUT.xlsx) —
            leca do wezla „poza strukturą", zeby zadna nie zniknela;
          * cykle w danych (A -> B -> A) — `sciezka` przerywa zejscie, bo
            inaczej rekurencja leci w nieskonczonosc;
          * filtr „Tylko braki" — gdy dziecko odpadlo, rodzic zostaje, jesli
            ma jakiekolwiek widoczne potomstwo (inaczej znika kontekst).
        """
        wg_nr = {r["nr"].strip().upper(): r for r in widoczne}
        dzieci_of = {k.strip().upper(): v for k, v in (self.kids or {}).items()}
        wszystkie_dzieci = {c[0].strip().upper()
                            for lista in dzieci_of.values() for c in lista}
        korzenie = [k for k in dzieci_of if k not in wszystkie_dzieci]

        dane, uzyte = [], set()

        def wstaw(rodzic_iid, nr_up, sciezka):
            if nr_up in sciezka or nr_up in uzyte:
                return              # cykl albo pozycja juz wstawiona
            r = wg_nr.get(nr_up)
            potomstwo = dzieci_of.get(nr_up, [])
            widoczne_dzieci = [c for c in potomstwo
                               if self._ma_cokolwiek(c[0].strip().upper(), wg_nr,
                                                     dzieci_of, sciezka | {nr_up})]
            if r is None and not widoczne_dzieci:
                return
            if r is not None:
                wartosci, tag = self._wiersz_wartosci(r)[:2]
            else:
                # Zlozenie jest w strukturze, ale nie ma go w BOM-ie (albo
                # odpadlo na filtrze) — sam numer, zeby dzieci mialy sie
                # pod czym zaczepic.
                wartosci = ["", nr_up, "", "", "", "", "", "", ""]
                tag = "modul"
            uzyte.add(nr_up)
            dane.append([nr_up, rodzic_iid] + list(wartosci))
            self._tagi.append(tag)
            if potomstwo:
                self._iid_wezlow.append(nr_up)
            for dziecko, _qty in potomstwo:
                wstaw(nr_up, dziecko.strip().upper(), sciezka | {nr_up})

        for k in sorted(korzenie):
            wstaw("", k, frozenset())

        poza = [r for r in widoczne if r["nr"].strip().upper() not in uzyte]
        if poza:
            naglowek = [POZA_IID, "", "", f"poza strukturą ({len(poza)} poz.)",
                        "", "", "", "", "", ""]
            dane.append(naglowek)
            self._tagi.append("modul")
            self._iid_wezlow.append(POZA_IID)
            for r in poza:
                wartosci, tag = self._wiersz_wartosci(r)[:2]
                dane.append([r["nr"].strip().upper(), POZA_IID] + list(wartosci))
                self._tagi.append(tag)
        return dane

    def _ma_cokolwiek(self, nr_up, wg_nr, dzieci_of, sciezka):
        """Czy ten wezel albo cokolwiek pod nim jest widoczne."""
        if nr_up in sciezka:
            return False
        if nr_up in wg_nr:
            return True
        return any(self._ma_cokolwiek(c[0].strip().upper(), wg_nr, dzieci_of,
                                      sciezka | {nr_up})
                   for c in dzieci_of.get(nr_up, []))

    def _summary_czysc(self):
        if self._summary_wnetrze is not None:
            self._summary_wnetrze.destroy()
        self._summary_wnetrze = tk.Frame(self.summary, bg="#ecf0f1")
        self._summary_wnetrze.pack(fill=tk.X, padx=12, pady=6)
        return self._summary_wnetrze

    def _summary_tekst(self, tekst):
        """Pasek jako zwykły komunikat — przy wczytywaniu i przy błędzie."""
        ramka = self._summary_czysc()
        tk.Label(ramka, text=tekst, bg="#ecf0f1", fg="#2c3e50",
                 font=("Arial", 9), anchor="w").pack(side=tk.LEFT)

    def _summary_liczniki(self, total, n_kart, pct, n_ok, n_czesc, n_brak, n_nokart):
        """Liczniki kategorii z próbką koloru — zarazem legenda tabeli."""
        ramka = self._summary_czysc()

        def tekst(t, bold=False):
            tk.Label(ramka, text=t, bg="#ecf0f1", fg="#2c3e50",
                     font=("Arial", 9, "bold" if bold else "normal")).pack(side=tk.LEFT)

        def kategoria(tag, etykieta, ile):
            # Próbka w kolorze tła wiersza — to ona wiąże licznik z tabelą.
            # Obramowanie, bo „brak kartoteki" jest jasnoszary i na jasnym
            # pasku bez ramki wyglądałby jak puste miejsce.
            tk.Frame(ramka, bg=self.KOLORY[tag], width=13, height=13,
                     highlightthickness=1, highlightbackground="#95a5a6").pack(
                         side=tk.LEFT, padx=(10, 4))
            tk.Label(ramka, text=f"{etykieta}: {ile}", bg="#ecf0f1", fg="#2c3e50",
                     font=("Arial", 9)).pack(side=tk.LEFT)

        tekst(f"Pozycji: {total}    z kartoteką: {n_kart} ({pct:.0f}%)")
        kategoria("ok", "na stanie", n_ok)
        kategoria("czesc", "za mało", n_czesc)
        kategoria("brak", "stan 0", n_brak)
        kategoria("nokart", "brak kartoteki", n_nokart)
        tekst(f"      → do zamówienia: {n_czesc + n_brak + n_nokart}", bold=True)

    def _sort_by(self, key, _state={}):
        """Zostawione dla zgodnosci — tksheet sortuje sam po klikniecie
        w naglowek, i robi to poprawnie takze w drzewku (w obrebie
        rodzenstwa). Wlasne przestawianie wierszy zniszczyloby hierarchie."""
        return

    def _usun_pozycje(self):
        """Usuwa zaznaczone wiersze z listy w oknie (nie z projektu)."""
        if not self.sheet:
            return
        try:
            wiersze = sorted(self.sheet.get_selected_rows())
        except Exception:
            wiersze = []
        if not wiersze:
            self.status.config(text="Zaznacz wiersze do usunięcia (klik w numer wiersza, Shift/Ctrl = kilka).")
            return
        idx_nr = [c[0] for c in self.COLS].index("nr")
        numery = set()
        for i in wiersze:
            try:
                nr = str(self.sheet.get_cell_data(i, idx_nr) or "").strip()
            except Exception:
                continue
            if nr:
                numery.add(nr.upper())
        if not numery:
            self.status.config(text="Zaznaczone wiersze to węzły złożeń — usuń konkretne pozycje.")
            return
        przed = len(self.rows)
        self.rows = [r for r in self.rows if r["nr"].strip().upper() not in numery]
        self._refill()
        self.status.config(text=f"Usunięto {przed - len(self.rows)} poz. z widoku "
                                f"(nic nie zapisano — „Odśwież” przywraca).")

    def _show_details(self, _event=None):
        """Dwuklik: karta pozycji (subiekt_pozycja_gui) — nawigator po
        strukturze zlozen z danymi BOM-u i Subiekta. Zastapila messagebox
        ze stanami per magazyn (06.09.2026): z karty da sie przejsc do
        rodzica i skladnikow, messagebox byl slepa uliczka."""
        if not self.sheet:
            return
        try:
            wiersze = list(self.sheet.get_selected_rows())
            if not wiersze:
                return
            idx_nr = [c[0] for c in self.COLS].index("nr")
            nr = str(self.sheet.get_cell_data(wiersze[0], idx_nr) or "").strip()
        except Exception:
            return
        if not nr:
            return                  # wezel zlozenia bez pozycji
        import subiekt_pozycja_gui
        subiekt_pozycja_gui.otworz(self, nr, self.project_id, self.project_name)


def open_window(parent, project_id, only_drawings=None):
    """Punkt wejścia dla RM_BAZA."""
    if not project_id:
        messagebox.showwarning("Subiekt", "Najpierw wybierz projekt.", parent=parent)
        return None
    return SubiektStanyWindow(parent, project_id, only_drawings)


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 22
    root = tk.Tk()
    root.withdraw()
    w = open_window(root, pid)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
