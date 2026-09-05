# -*- coding: utf-8 -*-
"""
Założenie projektu RM_BAZA w Subiekcie nexo PRO: kartoteki, komplety i ZK.

    import subiekt_projekt
    subiekt_projekt.open_window(parent, project_id=22, project_name="2222 Ceramizator")

Co robi (SUBIEKT_PROJEKTY_WYDANIA.md, sekcje 3 i 5):

  * czyta BOM projektu i klasyfikację X / XX / Z / ZZ (kolumna class_effective),
  * z arkusza „DRZEWKO TEKST" odtwarza, co wchodzi w skład czego,
  * pokazuje drzewo z zaznaczeniem, co powstanie w Subiekcie,
  * po potwierdzeniu zakłada kartoteki, komplety (Z, potem ZZ) i ZK projektu.

Reguła typów — Z i ZZ to komplety, X i XX to zwykłe kartoteki:

    X, XX  → kartoteka-towar (liść drzewa, nie ma składników)
    Z      → komplet ze składników X/XX
    ZZ     → komplet ze składników Z  (komplet w komplecie)

UWAGA: to jedyny moduł RM_BAZA, który ZAPISUJE do Subiekta. Zapis idzie na
bazę produkcyjną, więc: zawsze najpierw suchy przebieg, potwierdzenie z
podsumowaniem, i log co powstało (do ewentualnego cofnięcia w Subiekcie).
"""

import json
import os
import subprocess
import sqlite3
import sys
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

import subiekt_mapowania
from subiekt_stany import (_find_exe, blad_mostu, jedna_linia, CONFIG_PATH,
                           PROJECTS_DIR, looks_like_drawing_no,
                           wczytaj_szerokosci, zapisz_szerokosci)

TIMEOUT_S = 600          # zapis bywa wolniejszy od odczytu — kartoteki idą pojedynczo
LOG_DIR = r"C:\RMPAK_CLIENT\subiekt_logi"

KOMPLETY = ("Z", "ZZ")   # tylko te typy zakładają komplet
LISCIE = ("X", "XX")     # zwykłe kartoteki

# Filtr typu — nazewnictwo jak w arkuszu głównym („(WSZYSTKO)").
TYP_WSZYSTKO = "(WSZYSTKO)"
TYP_BEZ_TYPU = "(bez typu)"


# ── Dane projektu ───────────────────────────────────────────────────────────
def read_project_items(project_id):
    """[{nr, nazwa, qty, typ}] — pozycje BOM z klasyfikacją X/XX/Z/ZZ.

    Kolejność kolumn (work > norm > src, *_over pierwsze) jest ta sama co w
    subiekt_stany.read_project_drawings, żeby oba okna widziały to samo.
    """
    path = os.path.join(PROJECTS_DIR, f"project_{project_id}.sqlite")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info('items')")}
        # UWAGA: kolumny *_over (name_over, order_qty_over…) to FLAGI nadpisania
        # (INTEGER 0/1), NIE wartości — wzięte tutaj dawały nazwę „0” i ilość 0
        # na ZK. Kolejność jak w reszcie RM_BAZA: COALESCE(order_qty, work_qty, src_qty).
        name_cols = [c for c in ("work_name", "src_name") if c in cols]
        qty_cols = [c for c in ("order_qty", "work_qty", "src_qty") if c in cols]
        cls_cols = [c for c in ("class_manual", "class_effective", "class_auto") if c in cols]
        sel = ["work_drawing_no", "norm_drawing_no", "src_drawing_no"] + name_cols + qty_cols + cls_cols
        # Ukryte pozycje (przycisk „Ukryj zaznaczone" w arkuszu) nie mają
        # trafiać do Subiekta — COALESCE bo starsze wiersze mogą mieć NULL
        # zamiast 0 (ten sam wzorzec co database_manager.get_project_items).
        where = " WHERE COALESCE(is_hidden, 0) = 0" if "is_hidden" in cols else ""
        rows = con.execute(f"SELECT {', '.join(sel)} FROM items{where}").fetchall()
    finally:
        con.close()

    n0 = 3
    q0 = n0 + len(name_cols)
    c0 = q0 + len(qty_cols)

    def first(vals):
        for v in vals:
            if v is not None and str(v).strip() != "":
                return v
        return None


    out, seen = [], set()
    uzyte_symbole = set()      # przycinanie nazw może dać dwa te same symbole
    for r in rows:
        nr = jedna_linia(first(r[0:3]))
        nazwa = jedna_linia(first(r[n0:q0]))
        typ = first(r[c0:])
        typ = str(typ).strip().upper() if typ else "UNKNOWN"

        # Elementy ZNORMALIZOWANE (łożyska „6004ZZ", paski „5M L2525 szer25",
        # simmeringi) mają PUSTY numer rysunku — całą tożsamość niosą w nazwie
        # (89 z 273 pozycji w projekcie 2621). Wcześniej wypadały tu całkowicie
        # i w oknie widać było tylko 2 znormalizowane zamiast 89
        # (zgłoszone 04.09.2026). Dla nich kluczem jest nazwa.
        klucz = nr or nazwa
        if not klucz or klucz in seen:
            continue
        seen.add(klucz)
        # Symbol kartoteki: numer rysunku, a gdy go nie ma — nazwa przycięta
        # do długości akceptowanej przez Subiekta (pełna zostaje w Nazwie).
        symbol = nr or symbol_z_nazwy(nazwa)
        if not nr and symbol in uzyte_symbole:
            symbol = rozroznij_symbol(nazwa, uzyte_symbole)
        uzyte_symbole.add(symbol)

        out.append({
            "nr": symbol,
            "bez_numeru": not nr,    # do rozpoznania przy zakładaniu kartotek
            "nazwa": nazwa,
            "qty": first(r[q0:c0]),
            "typ": typ,
        })
    return out


def read_tree(project_name):
    """{rodzic: [(dziecko, ilosc_lokalna)]} z arkusza „DRZEWKO TEKST".

    Zwraca ({}, powod) jeśli drzewa nie da się wczytać — wtedy komplety nie
    powstaną (nie ma z czego zbudować składu), ale kartoteki i ZK owszem.
    """
    try:
        from pathlib import Path
        from import_bom import find_project_folder, find_out_files, find_assembly_tree_rows
    except Exception as e:
        return {}, f"brak import_bom: {e}"

    # Projekty (pliki *_OUT.xlsx) leżą na V:. Ścieżka z konfiguracji ma
    # pierwszeństwo, ale gdy wskazuje na nieistniejący katalog — a tak bywa,
    # bo konfig bywa przestawiony — schodzimy na V: zamiast zgłaszać błąd.
    kandydaci = []
    try:
        from RM_BAZA_v15_MAG_STATS_ORG import get_assembly_tree_root
        kandydaci.append(Path(get_assembly_tree_root()))
    except Exception:
        pass
    kandydaci.append(Path("V:/"))

    v_root = next((p for p in kandydaci if p.exists()), None)
    if v_root is None:
        return {}, f"katalog projektów niedostępny (próbowano: {', '.join(str(p) for p in kandydaci)})"

    folder = find_project_folder(v_root, project_name)
    if not folder:
        return {}, f"nie znaleziono folderu projektu „{project_name}” w {v_root}"

    kids = {}
    found = False
    for out_path in find_out_files(folder):
        rows = find_assembly_tree_rows(out_path)
        if not rows:
            continue
        found = True
        for row in rows:
            sciezka = row.get("sciezka") or []
            if len(sciezka) < 2:
                continue                      # korzeń nie ma rodzica
            parent = sciezka[-2].strip().upper()
            child = row["nr_rysunku"].strip()
            if not parent or not child:
                continue
            qty = row.get("ilosc_lokalna")
            try:
                qty = float(str(qty).replace(",", ".")) if qty not in (None, "") else 1.0
            except (TypeError, ValueError):
                qty = 1.0
            kids.setdefault(parent, [])
            if not any(c[0].upper() == child.upper() for c in kids[parent]):
                kids[parent].append((child, qty))

    if not found:
        return {}, "nie znaleziono arkusza „DRZEWKO TEKST” w plikach *_OUT.xlsx"
    return kids, None


# Maksymalna długość symbolu kartoteki — TYLE, CO NUMER RYSUNKU.
#
# Pomiar 04.09.2026 na 890 numerach z czterech projektów: 11-13 znaków
# obejmuje 85 % (średnia 12,0; „011-100.05" to 10). Dzięki jednolitej
# długości kody kreskowe wychodzą tej samej szerokości niezależnie od tego,
# czy pozycja ma numer rysunku, czy symbol powstał z nazwy.
#
# Wpływ na ETYKIETY: w Code 128 znak to ~11 modułów, więc przy 0,33 mm/moduł
# symbol 13-znakowy daje kod ~59 mm, a 40-znakowy ~157 mm (nie mieści się
# na żadnej typowej etykiecie).
#
# Pełna nazwa zawsze zostaje w polu Nazwa kartoteki — skracamy tylko symbol.
MAX_SYMBOL = 13

# ⚠️ SYMBOL MUSI BYĆ CZYSTYM ASCII — inaczej nie da się wydrukować kodu
# kreskowego. Code 128 koduje wyłącznie ASCII (0-127); „ł", „ś", „ę" wywalają
# generator albo dają kod nie do odczytania skanerem. Zgłoszone 05.09.2026,
# gdy w Subiekcie były już 14 takich kartotek — m.in. „ZaślepkaDN50D”
# i „KróciećTC505” z tego generatora.
#
# Osobna pułapka: „2115‐103.60/16” w kartotece ma MYŚLNIK U+2010, nie ASCII
# — wygląda identycznie jak zwykły, a kodu z niego nie będzie. Dlatego
# podmieniamy też myślniki, cudzysłowy i spacje niełamliwe wklejane z Worda
# i Excela.
OGONKI = str.maketrans({
    "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n",
    "ó": "o", "ś": "s", "ź": "z", "ż": "z",
    "Ą": "A", "Ć": "C", "Ę": "E", "Ł": "L", "Ń": "N",
    "Ó": "O", "Ś": "S", "Ź": "Z", "Ż": "Z",
    # znaki typograficzne udające ASCII
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    "‘": "'", "’": "'", "‚": "'",
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    " ": " ", " ": " ", " ": " ",
})


def do_ascii(s):
    """Tekst → czysty ASCII nadający się na symbol kartoteki i kod kreskowy.

    Najpierw transliteracja (ł→l, „–"→„-"), potem twarde odsianie tego, co
    zostało poza ASCII — żeby żaden niespodziewany znak (µ, ±, °, alfabet
    grecki z opisu materiału) nie przeciekł do symbolu.
    """
    s = str(s or "").translate(OGONKI)
    return "".join(c for c in s if 32 <= ord(c) < 127)


def symbol_z_nazwy(nazwa):
    """Nazwa → symbol kartoteki dla pozycji BEZ numeru rysunku.

    Elementy znormalizowane (łożyska, paski, uszczelki) nie mają numeru
    rysunku — identyfikuje je nazwa. Ta trafia więc w pole Symbol, ale musi
    być przycięta i pozbawiona znaków, które w symbolu przeszkadzają
    (`#`, backtick, `°`, przecinki). Pełna nazwa zostaje w polu Nazwa.
    """
    # do_ascii PRZED resztą czyszczenia — polskie znaki i typograficzne
    # myślniki nie mogą trafić do symbolu (kod kreskowy ich nie zakoduje).
    s = " ".join(do_ascii(nazwa).split())
    for zly in "`#":
        s = s.replace(zly, "")
    s = s.replace(",", " ").replace("/", "-")
    s = " ".join(s.split())
    if len(s) <= MAX_SYMBOL:
        return s

    # Usuwamy spacje zamiast ciąć na granicy słowa. Przy 13 znakach cięcie
    # po słowie gubiło rozróżniające końcówki: „5M L2525 szer25" → „5M L2525"
    # (znika szerokość paska), a trzy różne obejmy dawały „Obejmy TC #2/#3/#4".
    # Bez spacji mieści się więcej treści: „5ML2525szer25", „ObejmyTCDN100".
    bez_spacji = s.replace(" ", "")
    if len(bez_spacji) <= MAX_SYMBOL:
        return bez_spacji

    # Co odróżnia podobne pozycje, siedzi zwykle na KOŃCU nazwy (średnica,
    # długość, materiał): „uszczelki TC DN100 EPDM" vs „...DN50 EPDM".
    # Samo obcięcie z przodu dawało dla wszystkich „uszczelkiTCDN" i licznik
    # #2/#3/#4, po którym nie da się poznać, o którą chodzi. Dlatego przy
    # kolizji zostawiamy początek i doklejamy ogon nazwy.
    poczatek = bez_spacji[:MAX_SYMBOL]
    return poczatek


def rozroznij_symbol(nazwa, uzyte):
    """Symbol dla nazwy, która po przycięciu koliduje z już użytym.

    Przy 13 znakach nazwy typu „uszczelki TC DN40 EPDM" nie mieszczą się, a
    to, co je odróżnia (średnica, długość, materiał), siedzi na KOŃCU. Proste
    obcięcie dawało dla wszystkich „uszczelkiTCDN", a wycinanie środka —
    nieczytelne „uszczelk0EPDM", gdzie cyfra to przypadkowy fragment.

    Dlatego bierzemy WYRÓŻNIKI: człony nazwy zawierające cyfry (DN40, M6,
    fi119, L2525) — bo to one zwykle rozróżniają warianty tej samej rzeczy.
    """
    pelna = " ".join(do_ascii(nazwa).split())
    for zly in "`#":
        pelna = pelna.replace(zly, "")

    czlony = pelna.split()
    z_cyfra = [c for c in czlony if any(z.isdigit() for z in c)]
    bez_cyfr = [c for c in czlony if c not in z_cyfra]

    # Wyróżniki na końcu, reszta z przodu — tyle, ile się zmieści.
    ogon = "".join(z_cyfra)[:MAX_SYMBOL - 3]
    przod = "".join(bez_cyfr).replace(" ", "")
    kandydat = (przod[:MAX_SYMBOL - len(ogon)] + ogon)[:MAX_SYMBOL]
    if kandydat and kandydat not in uzyte:
        return kandydat

    # Nazwy nierozróżnialne po oczyszczeniu — licznik jako ostateczność.
    baza = (kandydat or symbol_z_nazwy(nazwa))[:MAX_SYMBOL - 2]
    i = 2
    while f"{baza}#{i}" in uzyte:
        i += 1
    return f"{baza}#{i}"


def numer_projektu(project_name, project_id=None):
    """Numer projektu do Uwag na ZK — pierwszy człon nazwy.

    Firma już oznacza dokumenty w Subiekcie samym numerem (Uwagi: „2115",
    „2453", „2509" — patrz SUBIEKT_PROJEKTY_WYDANIA.md sekcja 2.1), więc
    filtrowanie F8 po Uwagach szuka numeru, nie nazwy.

        „2607 Platyn"        → „2607"
        „ZP179 ZTD"          → „ZP179"
        „2558 Olmaj Wciskarka" → „2558"

    Człon musi zawierać cyfrę — inaczej („Kabina testowa") nie jest numerem
    i wtedy lepszy jest project_id niż mylące pierwsze słowo.
    """
    czlon = (project_name or "").strip().split(" ")[0].strip() if project_name else ""
    if czlon and any(c.isdigit() for c in czlon):
        return czlon
    return str(project_id) if project_id is not None else (czlon or "")


def build_plan(project_id, project_name, podmiot, tytul):
    """Buduje plan dla mostu + dane do wyświetlenia. Zwraca (plan, items, ostrzezenie)."""
    items = read_project_items(project_id)
    # Pozycje z numerem rysunku muszą wyglądać jak numer (odsiewa opisy wpisane
    # w to pole). Pozycje BEZ numeru — znormalizowane, identyfikowane nazwą —
    # przepuszczamy, bo inaczej wypadłyby łożyska, paski i simmeringi.
    items = [it for it in items
             if it.get("bez_numeru") or looks_like_drawing_no(it["nr"])]
    kids, warn = read_tree(project_name)

    by_nr = {it["nr"].upper(): it for it in items}
    pozycje = []
    for it in items:
        skladniki = []
        if it["typ"] in KOMPLETY:
            for child_nr, child_qty in kids.get(it["nr"].upper(), []):
                # Do składu kompletu bierzemy tylko to, co jest w BOM-ie —
                # inaczej wpisalibyśmy do Subiekta pozycję, której RM_BAZA nie zna.
                if child_nr.upper() in by_nr:
                    skladniki.append({"symbol": child_nr, "ilosc": child_qty})
        try:
            qty = float(str(it["qty"]).replace(",", ".")) if it["qty"] not in (None, "") else 1.0
        except (TypeError, ValueError):
            qty = 1.0
        pozycje.append({
            "symbol": it["nr"],
            "nazwa": it["nazwa"] or it["nr"],
            "typ": it["typ"],
            # Pozycje bez numeru rysunku (znormalizowane) mają symbol = nazwa.
            # Okno pokazuje to wprost, żeby nie wyglądało na błąd danych.
            "bez_numeru": bool(it.get("bez_numeru")),
            "ilosc": qty,
            "skladniki": skladniki,
        })

    # W Uwagach sam numer — tak firma oznacza dokumenty i tak po nich filtruje
    # (F8 / kolumna Uwagi). Pełna nazwa idzie w Tytule, gdzie jest czytelna.
    numer = numer_projektu(project_name, project_id)
    plan = {
        "projekt": numer,
        "tytul": tytul,
        "podmiot": podmiot,
        "uwagi": numer,
        "pozycje": pozycje,
    }
    return plan, items, warn


# ── Wywołanie mostu ─────────────────────────────────────────────────────────
def run_bridge(plan, zapisz=False, timeout=TIMEOUT_S):
    """Suchy przebieg (zapisz=False) albo realny zapis. Zwraca dict z JSON-a."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError(
            "Nie znaleziono NexoRecon.exe.\n\n"
            "Zbuduj most:\n  cd subiekt_sfera\\NexoRecon\n  dotnet build -c Release")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")

    tmpdir = tempfile.mkdtemp(prefix="subiekt_proj_")
    plan_path = os.path.join(tmpdir, "plan.json")
    out_path = os.path.join(tmpdir, "wynik.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)

    cmd = [exe, "projekt", f"--plan={plan_path}", f"--out={out_path}"]
    if zapisz:
        cmd.append("--zapisz")

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Subiekt nie odpowiedział w {timeout} s.")

    if proc.returncode != 0 or not os.path.isfile(out_path):
        raise RuntimeError(blad_mostu(exe, "projekt", proc, out_path))

    with open(out_path, encoding="utf-8") as f:
        return json.load(f)


def zapisz_mapowania(wynik):
    """Zapamiętuje w globalnej tabeli, co Subiekt potwierdził.

    Dzięki temu następny projekt z tym samym numerem rysunku ma trafienie
    lokalnie, bez pytania Subiekta przez sieć (plan, „Zapamiętanie skojarzenia").
    """
    wpisy = []
    for k in (wynik or {}).get("kroki", []):
        if k.get("Rodzaj") != "kartoteka":
            continue
        symbol = (k.get("Symbol") or "").strip()
        if not symbol:
            continue
        if k.get("Status") == "istnieje":
            wpisy.append((symbol, symbol, subiekt_mapowania.SPOSOB_AUTO))
        elif k.get("Status") == "zalozona":
            wpisy.append((symbol, symbol, subiekt_mapowania.SPOSOB_ZALOZONA))
    try:
        return subiekt_mapowania.put_many(wpisy)
    except Exception:
        return 0          # brak dostępu do bazy mapowań nie może wywalić całego zapisu


def save_log(project_id, wynik):
    """Zapisuje co powstało — bez tego nie da się potem posprzątać w Subiekcie."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(LOG_DIR, f"projekt_{project_id}_{stamp}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(wynik, f, ensure_ascii=False, indent=1)
        return path
    except Exception:
        return None


# ── Okno ────────────────────────────────────────────────────────────────────
class SubiektProjektWindow(tk.Toplevel):
    COLS = [
        ("sel",    "✓",             30, "c"),
        ("nr",     "Nr rysunku",   150, "w"),
        ("typ",    "Typ",           55, "c"),
        ("qty",    "Ilość",         60, "e"),
        ("co",     "Co powstanie", 175, "w"),
        # Nazwy bywają długie („Zaślepka DN50 DIN 32676") — ta kolumna jako
        # jedyna się rozciąga, resztę treści pokazuje dymek.
        ("nazwa",  "Nazwa",        420, "w"),
    ]

    # Wartości filtra typu — DOKŁADNIE jak FILTER_CLASS_VALUES w arkuszu
    # głównym RM_BAZA, razem z LASER / LASER EXPORT (rozwijane do X i XX).
    TYPY = ["X", "XX", "Z", "ZZ", "STANDARD", "ZNORMALIZOWANE",
            "LASER", "LASER EXPORT"]

    def __init__(self, parent, project_id, project_name=None):
        super().__init__(parent)
        self.project_id = project_id
        self.project_name = project_name or str(project_id)
        self.plan = None
        self.items = []
        self.dry = None
        # Symbole (UPPER) wybrane do założenia w Subiekcie. Pozycje, które już
        # mają kartotekę, nie są tu trzymane — nie ma czego zakładać.
        self.wybrane = set()
        self.filter_typ_modes = {}  # {typ: 'show'|'hide'} — kafelek ✚

        self.title(f"Załóż projekt w Subiekcie — {self.project_name}")
        self.geometry("1080x680")
        self.minsize(900, 400)
        # ŚWIADOMIE bez transient(): okno-dziecko z transient dostaje w Windows
        # tylko przycisk „×", bez minimalizacji i maksymalizacji. To pełnoprawny
        # arkusz roboczy, więc ma się zachowywać jak okno główne RM_BAZA (— □ ×).
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self._build_ui()
        self.after(100, self._dry_run_async)

    def _build_ui(self):
        top = tk.Frame(self, bg="#34495e", height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🏗 Załóż projekt w Subiekcie (kartoteki + komplety + ZK)",
                 bg="#34495e", fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)

        self.btn_refresh = tk.Button(top, text="🔄 Przelicz", command=self._dry_run_async,
                                     bg="#3498db", fg="white", font=("Arial", 8),
                                     padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_refresh.pack(side=tk.RIGHT, padx=10, pady=8)

        # Parametry ZK — podmiot jest wymagany przez Subiekta (sekcja 4).
        par = tk.Frame(self, bg="#ecf0f1")
        par.pack(side=tk.TOP, fill=tk.X, padx=0, pady=0)
        tk.Label(par, text="Podmiot na ZK:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(12, 4), pady=6)
        self.var_podmiot = tk.StringVar(value="RMPAK")
        tk.Entry(par, textvariable=self.var_podmiot, width=28, font=("Arial", 9)).pack(side=tk.LEFT, pady=6)
        tk.Label(par, text="Tytuł ZK:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(16, 4), pady=6)
        # Tytuł: pełna nazwa projektu (z numerem na początku), bez słowa
        # „Projekt” — na liście dokumentów w Subiekcie od razu widać, o co
        # chodzi. Sam numer idzie osobno w Uwagi, bo po nich się filtruje.
        self.var_tytul = tk.StringVar(value=(self.project_name or str(self.project_id)).strip())
        tk.Entry(par, textvariable=self.var_tytul, width=38, font=("Arial", 9)).pack(side=tk.LEFT, pady=6)

        # Wybór, co zakładać w asortymencie Subiekta. Domyślnie NIE cały BOM —
        # zakładanie 198 kartotek jednym kliknięciem to zmiana reguły „kartoteka
        # na żądanie", a kartotek nie da się potem łatwo usunąć.
        sel = tk.Frame(self, bg="#f4ecf7")
        sel.pack(side=tk.TOP, fill=tk.X)
        tk.Label(sel, text="Zakładaj kartoteki dla:", bg="#f4ecf7",
                 font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(12, 6), pady=5)
        for etykieta, tryb, opis in (
            ("komplety + składniki", "komplety", "tylko Z/ZZ i to, co w nie wchodzi"),
            ("wszystko", "wszystko", "cały BOM"),
            ("nic", "nic", "tylko istniejące kartoteki"),
        ):
            tk.Button(sel, text=etykieta, command=lambda t=tryb: self._zaznacz_tryb(t),
                      bg="#8e44ad", fg="white", font=("Arial", 8), padx=8, pady=1,
                      relief=tk.RAISED, bd=1, cursor="hand2").pack(side=tk.LEFT, padx=3, pady=5)
        tk.Label(sel, text="   (klik w kolumnę ✓ przełącza pojedynczą pozycję)",
                 bg="#f4ecf7", fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.LEFT, padx=6)

        # Widok drzewa. Domyślnie otwarty jest tylko pierwszy poziom, więc
        # elementy handlowe (STANDARD, ZNORMALIZOWANE) siedzą schowane wewnątrz
        # złożeń — przy 180 pozycjach wyglądało to, jakby ich w ogóle nie było
        # (zgłoszone 04.09.2026: „nie widzę elementów handlowych").
        wid = tk.Frame(self, bg="#eaf2f8")
        wid.pack(side=tk.TOP, fill=tk.X)
        tk.Label(wid, text="Widok:", bg="#eaf2f8",
                 font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(12, 6), pady=4)
        for txt, cmd in (("⊞ Rozwiń wszystko", lambda: self._rozwin(True)),
                         ("⊟ Zwiń", lambda: self._rozwin(False))):
            tk.Button(wid, text=txt, command=cmd, bg="#5499c7", fg="white",
                      font=("Arial", 8), padx=8, pady=1, relief=tk.RAISED, bd=1,
                      cursor="hand2").pack(side=tk.LEFT, padx=3, pady=4)

        self.plaska_var = tk.IntVar(value=0)
        tk.Checkbutton(wid, text="płaska lista (bez drzewa)", variable=self.plaska_var,
                       command=self._przerysuj, bg="#eaf2f8", font=("Arial", 8),
                       activebackground="#eaf2f8").pack(side=tk.LEFT, padx=(12, 0), pady=4)

        # Filtr typu — skopiowany z okna zamówień (a tam z arkusza głównego).
        tk.Label(wid, text="Typ:", bg="#eaf2f8", font=("Arial", 9)).pack(side=tk.LEFT, padx=(14, 3), pady=4)
        self.filter_typ_var = tk.StringVar(value=TYP_WSZYSTKO)
        self.combo_typ = ttk.Combobox(wid, textvariable=self.filter_typ_var, width=15,
                                      state="readonly", font=("Arial", 9))
        self.combo_typ["values"] = [TYP_WSZYSTKO] + self.TYPY + [TYP_BEZ_TYPU]
        self.combo_typ.pack(side=tk.LEFT, pady=4)
        self.combo_typ.bind("<<ComboboxSelected>>", lambda _e: self._przerysuj())

        # Kafelek multi-select z negacją — sklejony z combo, jak w arkuszu głównym.
        self.btn_typ_multi = tk.Button(wid, text="✚", command=self._okno_filtru_typu,
                                       bg="#7f8c8d", fg="white", font=("Arial", 8),
                                       width=3, relief=tk.RAISED, bd=1, cursor="hand2")
        self.btn_typ_multi.pack(side=tk.LEFT, padx=(0, 2), pady=4)

        # Czyszczenie filtrów — ta sama ikona i kolor co w arkuszu głównym.
        tk.Button(wid, text="🗑️", command=self._wyczysc_filtry, bg="#95a5a6", fg="white",
                  font=("Arial", 11, "bold"), width=3, relief=tk.RAISED, bd=2,
                  cursor="hand2").pack(side=tk.LEFT, padx=(10, 2), pady=3)

        self.summary = tk.Label(self, text="Wczytywanie…", bg="#ecf0f1", fg="#2c3e50",
                                font=("Arial", 9), anchor="w", padx=12, pady=6)
        self.summary.pack(side=tk.TOP, fill=tk.X)

        wrap = tk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 4))
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in self.COLS], show="tree headings")
        self.tree.heading("#0", text="Struktura")
        self.tree.column("#0", width=230, stretch=False)
        # Szerokości zapamiętane z poprzedniej sesji mają pierwszeństwo przed
        # domyślnymi (Treeview, więc obsługa własna — nie tksheet).
        zapamietane = wczytaj_szerokosci("projekt") or []
        for i, (key, label, width, anchor) in enumerate(self.COLS):
            self.tree.heading(key, text=label)
            if i < len(zapamietane):
                try:
                    width = int(zapamietane[i])
                except (TypeError, ValueError):
                    pass
            # stretch=False dla wszystkich — inaczej kolumny same dopasowują się
            # do okna i poziomy pasek nigdy nie ma czego przewijać, a długie
            # nazwy dalej się urywają.
            self.tree.column(key, width=width, anchor=anchor, stretch=False, minwidth=50)
        if len(zapamietane) > len(self.COLS):
            try:
                self.tree.column("#0", width=int(zapamietane[-1]))
            except (TypeError, ValueError):
                pass
        # grid, nie pack: przy pack(side=LEFT, expand=True) drzewo zabiera całą
        # szerokość i pionowy pasek bywa wypychany poza kadr. Dochodzi też pasek
        # POZIOMY — kolumny są szersze niż okno (nazwy po 100 znaków).
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)

        # Zapis szerokości po przeciągnięciu — Treeview nie ma zdarzenia
        # „kolumna zmieniła szerokość", więc łapiemy puszczenie myszy nad
        # nagłówkiem (ta sama zasada co w arkuszu głównym RM_BAZA).
        self.tree.bind("<ButtonRelease-1>", self._zapisz_szerokosci, add="+")
        self.tree.bind("<Button-1>", self._toggle_pozycja, add="+")
        # Długie nazwy („Zaślepka DN50 DIN 32676", „Wąż POLYPAL") nie mieszczą
        # się w kolumnie i urywają się bez śladu. Poszerzanie kolumny nie pomoże
        # — nazwy bywają bardzo różnej długości. Dymek pokazuje pełną treść,
        # jak przy selektorze projektu w arkuszu głównym.
        self._tip = None
        self._tip_wiersz = None
        self.tree.bind("<Motion>", self._tooltip_ruch, add="+")
        self.tree.bind("<Leave>", lambda _e: self._tooltip_ukryj(), add="+")

        self.tree.tag_configure("komplet", background="#d4e6f1")   # Z / ZZ
        self.tree.tag_configure("istnieje", background="#d5f5e3")  # jest w Subiekcie
        self.tree.tag_configure("nowy",    background="#fdebd0")   # do założenia
        self.tree.tag_configure("blad",    background="#fadbd8")

        bottom = tk.Frame(self)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))
        self.btn_write = tk.Button(bottom, text="💾 Zapisz do Subiekta", command=self._write_async,
                                   bg="#e67e22", fg="white", font=("Arial", 9, "bold"),
                                   padx=14, pady=5, relief=tk.RAISED, bd=2, state=tk.DISABLED)
        self.btn_write.pack(side=tk.RIGHT)
        # Pozycja spoza BOM-u do ZK — wspólny formularz zakłada kartotekę,
        # potem plan jest przeliczany, żeby most zobaczył ją jako istniejącą.
        self.btn_dodaj = tk.Button(bottom, text="➕ Dodaj pozycję spoza BOM",
                                   command=self._dodaj_reczna, bg="#27ae60", fg="white",
                                   font=("Arial", 9), padx=10, pady=5, relief=tk.RAISED, bd=1,
                                   state=tk.DISABLED)
        self.btn_dodaj.pack(side=tk.RIGHT, padx=(0, 8))
        tk.Label(bottom, text="Podgląd nie zmienia niczego w Subiekcie. Zapis wymaga potwierdzenia.",
                 fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.LEFT, pady=8)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    # ── suchy przebieg ─────────────────────────────────────────────────────
    def _dry_run_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.btn_write.config(state=tk.DISABLED)
        self.status.config(text="Czytam BOM i pytam Subiekta (nic nie zapisuję)…")
        threading.Thread(target=self._dry_run_worker, daemon=True).start()

    def _dry_run_worker(self):
        try:
            plan, items, warn = build_plan(
                self.project_id, self.project_name,
                self.var_podmiot.get().strip(), self.var_tytul.get().strip())
            if not plan["pozycje"]:
                self.after(0, lambda: self._dry_done(None, None, [], "Brak pozycji z numerem rysunku."))
                return
            wynik = run_bridge(plan, zapisz=False)
            # Suchy przebieg też jest okazją do zapamiętania trafień — kolejny
            # projekt z tymi numerami nie będzie musiał pytać Subiekta.
            zapisz_mapowania(wynik)
            self.after(0, lambda: self._dry_done(plan, wynik, items, warn))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._dry_done(None, None, [], err))

    def _dry_done(self, plan, wynik, items, warn):
        self.btn_refresh.config(state=tk.NORMAL)
        if plan is None:
            self.status.config(text="Błąd.")
            self.summary.config(text=(warn or "")[:200])
            if warn:
                messagebox.showerror("Subiekt", warn, parent=self)
            return

        self.plan, self.dry, self.items = plan, wynik, items
        self._fill_tree(plan, wynik)
        self.btn_write.config(state=tk.NORMAL)
        self.btn_dodaj.config(state=tk.NORMAL)

        # Domyślnie „komplety + składniki", nie cały BOM: zakładanie wszystkich
        # kartotek naraz to zmiana reguły „kartoteka na żądanie", a kartotek nie
        # da się potem łatwo usunąć. Użytkownik może rozszerzyć jednym kliknięciem.
        self._zaznacz_tryb("komplety")

        pust = sum(1 for k in wynik.get("kroki", [])
                   if k["Rodzaj"] == "komplet" and k["Status"] == "pominiety-brak-skladnikow")
        note = f"   ⚠ {warn}" if warn else ""
        extra = f"   ⚠ {pust} kompletów bez składników w drzewie" if pust else ""
        self.status.config(text=f"Podgląd gotowy — w Subiekcie nic nie zmieniono.{extra}{note}")

    # ── wybór, co zakładać ─────────────────────────────────────────────────
    def _do_zalozenia(self):
        """Symbole (UPPER), które nie mają jeszcze kartoteki w Subiekcie."""
        if not self.dry:
            return set()
        return {k["Symbol"].strip().upper() for k in self.dry.get("kroki", [])
                if k["Rodzaj"] == "kartoteka" and k["Status"] == "do-zalozenia"}

    def _zaznacz_tryb(self, tryb):
        """Szybkie zaznaczenie wg trybu. Działa tylko na pozycjach bez kartoteki."""
        if not self.plan:
            return
        brakujace = self._do_zalozenia()

        if tryb == "nic":
            self.wybrane = set()
        elif tryb == "wszystko":
            self.wybrane = set(brakujace)
        else:   # komplety + ich składniki (rekurencyjnie, bo ZZ zawiera ZZ)
            by = {p["symbol"].strip().upper(): p for p in self.plan["pozycje"]}
            chciane = set()

            def dodaj(sym, sciezka=()):
                s = sym.strip().upper()
                if s in sciezka or s in chciane:
                    return
                chciane.add(s)
                p = by.get(s)
                if not p:
                    return
                for skl in p["skladniki"]:
                    dodaj(skl["symbol"], sciezka + (s,))

            for p in self.plan["pozycje"]:
                if p["typ"] in KOMPLETY and p["skladniki"]:
                    dodaj(p["symbol"])
            self.wybrane = chciane & brakujace

        self._odswiez_znaczniki()

    def _toggle_pozycja(self, event):
        """Klik w kolumnę ✓ przełącza pojedynczą pozycję."""
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":      # kolumna „sel"
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        sym = (self.tree.set(item, "nr") or "").strip().upper()
        if not sym or sym not in self._do_zalozenia():
            return                                  # już ma kartotekę — nie ma czego zakładać
        self.wybrane.symmetric_difference_update({sym})
        self._odswiez_znaczniki()

    def _odswiez_znaczniki(self):
        """Przerysowuje kolumnę ✓ i podsumowanie bez przebudowy drzewa."""
        brakujace = self._do_zalozenia()

        def przejdz(node):
            for i in self.tree.get_children(node):
                sym = (self.tree.set(i, "nr") or "").strip().upper()
                if sym:
                    if sym not in brakujace:
                        self.tree.set(i, "sel", "—")     # istnieje, nic nie robimy
                    else:
                        self.tree.set(i, "sel", "✓" if sym in self.wybrane else "☐")
                przejdz(i)

        przejdz("")
        self._przelicz_podsumowanie()

    def _przelicz_podsumowanie(self):
        """Podsumowanie liczy się z aktualnego wyboru, nie z suchego przebiegu."""
        if not self.plan or not self.dry:
            return
        kroki = self.dry.get("kroki", [])
        jest = sum(1 for k in kroki if k["Rodzaj"] == "kartoteka" and k["Status"] == "istnieje")
        brakujace = self._do_zalozenia()
        do_zal = len(self.wybrane)
        pominiete = len(brakujace) - do_zal

        # Komplet powstanie tylko wtedy, gdy on sam i wszystkie jego składniki
        # będą miały kartotekę (istniejącą albo zakładaną teraz).
        dostepne = (set(p["symbol"].strip().upper() for p in self.plan["pozycje"]) - brakujace) | self.wybrane
        pelne = niepelne = 0
        for p in self.plan["pozycje"]:
            if p["typ"] not in KOMPLETY or not p["skladniki"]:
                continue
            if p["symbol"].strip().upper() not in dostepne:
                niepelne += 1
            elif all(s["symbol"].strip().upper() in dostepne for s in p["skladniki"]):
                pelne += 1
            else:
                niepelne += 1

        # Rozbicie typów — od razu widać, ile jest elementów handlowych,
        # nawet gdy siedzą schowane w złożeniach.
        from collections import Counter
        t = Counter(p["typ"] for p in self.plan["pozycje"])
        handlowe = t.get("STANDARD", 0) + t.get("ZNORMALIZOWANE", 0)
        blachy = t.get("X", 0) + t.get("XX", 0)
        zloz = t.get("Z", 0) + t.get("ZZ", 0)

        self.summary.config(text=(
            f"Pozycji: {len(self.plan['pozycje'])}"
            f"  (złożenia {zloz} · blachy {blachy} · handlowe {handlowe})    "
            f"kartoteki — jest: {jest}, do założenia: {do_zal}"
            + (f" (pomijasz {pominiete})" if pominiete else "")
            + f"    komplety: {pelne} pełnych"
            + (f", {niepelne} niepełnych ⚠" if niepelne else "")
        ))

    # ── dymek z pełną treścią uciętej komórki ──────────────────────────────
    def _tooltip_ukryj(self):
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None
            self._tip_wiersz = None

    def _tooltip_ruch(self, event):
        """Dymek nad wierszem: pełny numer i nazwa.

        Kolumny mają stałą szerokość, a nazwy bywają dowolnie długie
        („Zaślepka DN50 DIN 32676") — bez tego urywają się bez śladu.
        """
        try:
            wiersz = self.tree.identify_row(event.y)
        except Exception:
            return
        if not wiersz:
            self._tooltip_ukryj()
            return
        if wiersz == self._tip_wiersz:
            return                      # ten sam wiersz — nie migamy dymkiem

        self._tooltip_ukryj()
        try:
            v = self.tree.item(wiersz)["values"]
        except Exception:
            return
        if not v or len(v) < 6:
            return
        symbol, typ, nazwa = str(v[1]), str(v[2]), str(v[5])
        if not symbol and not nazwa:
            return

        tekst = symbol + (f"   [{typ}]" if typ else "")
        if nazwa and nazwa != symbol:
            tekst += f"\n{nazwa}"

        self._tip_wiersz = wiersz
        self._tip = tk.Toplevel(self)
        self._tip.wm_overrideredirect(True)
        self._tip.attributes("-topmost", True)
        tk.Label(self._tip, text=tekst, justify=tk.LEFT, bg="#ffffe0",
                 relief=tk.SOLID, borderwidth=1, font=("Arial", 9),
                 padx=6, pady=3).pack()
        self._tip.geometry(f"+{event.x_root + 16}+{event.y_root + 12}")

    def _dodaj_reczna(self):
        """Dorzuca do planu pozycję, której nie ma w BOM-ie RM_BAZA."""
        if not self.plan:
            return
        import subiekt_asortyment

        def po_zapisie(d):
            sym = d["symbol"].strip()
            if any(p["symbol"].strip().upper() == sym.upper() for p in self.plan["pozycje"]):
                messagebox.showinfo("Pozycja", f"„{sym}” już jest w planie.", parent=self)
                return
            self.plan["pozycje"].append({
                "symbol": sym, "nazwa": d["nazwa"],
                "typ": "STANDARD" if d.get("rodzaj") != "komplet" else "Z",
                "bez_numeru": True, "ilosc": 1.0, "skladniki": [],
            })
            # Przeliczenie: kartoteka właśnie powstała, więc suchy przebieg
            # pokaże ją jako „istnieje" i trafi do ZK bez dodatkowych kroków.
            self.status.config(text=f"Dodano „{sym}” — przeliczam plan…")
            self._dry_run_async()

        subiekt_asortyment.okno_nowa_kartoteka(self, po_zapisie=po_zapisie)

    def _zapisz_szerokosci(self, event=None):
        """Zapamiętuje szerokości kolumn, gdy się zmieniły.

        Wołane przy każdym puszczeniu myszy nad drzewem, więc najpierw
        porównujemy z ostatnim stanem — inaczej zwykłe klikanie waliłoby
        w dysk przy każdym wierszu.
        """
        def sprawdz():
            try:
                if self.tree.identify_region(event.x, event.y) not in ("separator", "heading"):
                    return          # zwykły klik w wiersz, nie zmiana szerokości
            except Exception:
                pass
            try:
                obecne = [self.tree.column(c[0], "width") for c in self.COLS]
                obecne.append(self.tree.column("#0", "width"))
                if obecne != getattr(self, "_ost_szerokosci", None):
                    self._ost_szerokosci = obecne
                    zapisz_szerokosci("projekt", obecne)
            except Exception:
                pass
        try:
            self.after_idle(sprawdz)
        except Exception:
            pass

    def _wyczysc_filtry(self):
        """Filtry widoku do stanu wyjściowego. NIE rusza zaznaczeń ✓ —
        to praca użytkownika, nie filtr."""
        self.filter_typ_var.set(TYP_WSZYSTKO)
        self.filter_typ_modes = {}
        self.plaska_var.set(0)
        try:
            self.btn_typ_multi.config(bg="#7f8c8d")
        except Exception:
            pass
        self._przerysuj()

    def _rozwin(self, otwarte):
        """Rozwija/zwija całe drzewo — bez tego elementy handlowe siedzą
        schowane w złożeniach i wygląda, jakby ich nie było."""
        def przejdz(node):
            for c in self.tree.get_children(node):
                self.tree.item(c, open=otwarte)
                przejdz(c)
        przejdz("")

    def _przerysuj(self):
        """Przebudowa drzewa po zmianie filtra/trybu — bez pytania Subiekta."""
        if self.plan and self.dry:
            self._fill_tree(self.plan, self.dry)

    # ── filtr typu (skopiowany z subiekt_zamowienia, a tam z arkusza głównego)
    @staticmethod
    def _rozwin_typ(t):
        """LASER / LASER EXPORT → {X, XX}; „(bez typu)" → {""} — jak w arkuszu głównym."""
        if t in ("LASER", "LASER EXPORT"):
            return {"X", "XX"}
        if t == TYP_BEZ_TYPU:
            return {""}
        return {t}

    def _typ_pasuje(self, typ):
        """Filtr typu: combo (jeden) + kafelek ✚ (wiele, z negacją)."""
        typ = typ or ""
        wybrany = self.filter_typ_var.get()
        if wybrany != TYP_WSZYSTKO and typ not in self._rozwin_typ(wybrany):
            return False

        # Kafelek działa RÓWNOLEGLE do combo — oba warunki muszą się zgadzać
        # (ta sama zasada co w arkuszu głównym).
        pokaz, ukryj = set(), set()
        for t, tryb in (self.filter_typ_modes or {}).items():
            (pokaz if tryb == "show" else ukryj).update(self._rozwin_typ(t))
        if pokaz and typ not in pokaz:
            return False
        if typ in ukryj:
            return False
        return True

    def _okno_filtru_typu(self):
        """Kafelek ✚ — dwie kolumny checkboxów (pokaż / ukryj) per typ.

        Odwzorowanie okna „Filtr Typ" z arkusza głównego RM_BAZA
        (open_class_filter_dialog): ten sam układ, te same nazwy przycisków,
        filtrowanie NA ŻYWO bez zatwierdzania, okno pod kafelkiem, ponowny
        klik zamyka.
        """
        istniejace = getattr(self, "_okno_typu", None)
        if istniejace is not None:
            try:
                if istniejace.winfo_exists():
                    istniejace.destroy()
                    self._okno_typu = None
                    return
            except Exception:
                pass

        dlg = tk.Toplevel(self)
        self._okno_typu = dlg
        dlg.title("Filtr Typ")
        dlg.configure(bg="#2c3e50", bd=1, relief=tk.SOLID)

        tk.Label(dlg, text="Filtr Typ — zaznacz pokaż lub ukryj przy typach:",
                 bg="#2c3e50", fg="#ecf0f1", font=("Arial", 8), anchor="w"
                 ).pack(fill=tk.X, padx=8, pady=(6, 4))

        body = tk.Frame(dlg, bg="white")
        body.pack(fill=tk.BOTH, expand=True, padx=1, pady=(0, 1))

        hdr = tk.Frame(body, bg="#f0f0f0")
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="", bg="#f0f0f0", width=16, anchor="w").pack(side=tk.LEFT)
        tk.Label(hdr, text="pokaż", bg="#f0f0f0", fg="#27ae60", width=6,
                 font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        tk.Label(hdr, text="ukryj", bg="#f0f0f0", fg="#c0392b", width=6,
                 font=("Arial", 8, "bold")).pack(side=tk.LEFT)

        zmienne = {}

        def wiersz(typ):
            row = tk.Frame(body, bg="white")
            row.pack(fill=tk.X, padx=4, pady=1)
            etykieta = typ + ("  (laser)" if typ in ("LASER", "LASER EXPORT") else "")
            tk.Label(row, text=etykieta, bg="white", anchor="w", width=16,
                     font=("Arial", 9)).pack(side=tk.LEFT)

            biezacy = self.filter_typ_modes.get(typ)
            v_show = tk.IntVar(value=1 if biezacy == "show" else 0)
            v_hide = tk.IntVar(value=1 if biezacy == "hide" else 0)
            zmienne[typ] = (v_show, v_hide)

            def zastosuj(t=typ, sv=v_show, hv=v_hide):
                if sv.get():
                    self.filter_typ_modes[t] = "show"
                elif hv.get():
                    self.filter_typ_modes[t] = "hide"
                else:
                    self.filter_typ_modes.pop(t, None)
                self.btn_typ_multi.config(
                    bg="#e67e22" if self.filter_typ_modes else "#7f8c8d")
                self._przerysuj()               # NA ŻYWO, bez zatwierdzania

            def on_show(sv=v_show, hv=v_hide):
                if sv.get():
                    hv.set(0)                # pokaż i ukryj wykluczają się
                zastosuj()

            def on_hide(sv=v_show, hv=v_hide):
                if hv.get():
                    sv.set(0)
                zastosuj()

            tk.Checkbutton(row, variable=v_show, bg="white", width=5,
                           command=on_show).pack(side=tk.LEFT)
            tk.Checkbutton(row, variable=v_hide, bg="white", width=5,
                           command=on_hide).pack(side=tk.LEFT)

        for typ in self.TYPY + [TYP_BEZ_TYPU]:
            wiersz(typ)

        foot = tk.Frame(dlg, bg="#2c3e50")
        foot.pack(fill=tk.X, padx=8, pady=(2, 6))

        def resetuj():
            for sv, hv in zmienne.values():
                sv.set(0)
                hv.set(0)
            self.filter_typ_modes = {}
            self.btn_typ_multi.config(bg="#7f8c8d")
            self._przerysuj()

        tk.Button(foot, text="Resetuj", command=resetuj,
                  font=("Arial", 8)).pack(side=tk.LEFT)
        tk.Button(foot, text="Zamknij", font=("Arial", 8),
                  command=lambda: (dlg.destroy(), setattr(self, "_okno_typu", None))
                  ).pack(side=tk.RIGHT)

        # Pod kafelkiem, z zabezpieczeniem przed wyjściem poza ekran.
        try:
            dlg.update_idletasks()
            szer = dlg.winfo_reqwidth() or 220
            wys = dlg.winfo_reqheight() or 300
            bx = self.btn_typ_multi.winfo_rootx()
            by = self.btn_typ_multi.winfo_rooty() + self.btn_typ_multi.winfo_height()
            if bx <= 0 and by <= 0:
                bx, by = self.winfo_pointerx(), self.winfo_pointery() + 10
            sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
            dlg.geometry(f"{szer}x{wys}+{max(0, min(bx, sw - szer))}+{max(0, min(by, sh - wys))}")
        except Exception:
            dlg.geometry(f"+{self.winfo_rootx() + 200}+{self.winfo_rooty() + 120}")

    def _filtr_typu_aktywny(self):
        return (self.filter_typ_var.get() != TYP_WSZYSTKO
                or bool(self.filter_typ_modes))

    def _fill_tree(self, plan, wynik):
        self.tree.delete(*self.tree.get_children())
        status = {}
        for k in wynik.get("kroki", []):
            status.setdefault(k["Rodzaj"], {})[k["Symbol"].upper()] = k

        by_symbol = {p["symbol"].upper(): p for p in plan["pozycje"]}
        dzieci = set()
        for p in plan["pozycje"]:
            for s in p["skladniki"]:
                dzieci.add(s["symbol"].upper())

        def opis(p):
            kart = status.get("kartoteka", {}).get(p["symbol"].upper())
            kom = status.get("komplet", {}).get(p["symbol"].upper())
            czesci = []
            if kart:
                czesci.append("kartoteka: " + ("jest" if kart["Status"] == "istnieje" else "NOWA"))
            if kom:
                czesci.append("komplet: " + kom["Status"].replace("do-utworzenia", "utworzy"))
            return "   ".join(czesci) or "—"

        def tag(p):
            kart = status.get("kartoteka", {}).get(p["symbol"].upper())
            if p["typ"] in KOMPLETY:
                return "komplet"
            if kart and kart["Status"] == "istnieje":
                return "istnieje"
            return "nowy"

        def wstaw(parent_id, p, glebokosc=0, sciezka=()):
            node = self.tree.insert(
                parent_id, "end", text=p["symbol"],
                values=("", p["symbol"], p["typ"], f"{p['ilosc']:g}", opis(p), p["nazwa"]),
                open=(glebokosc < 1), tags=(tag(p),))
            # Drzewa bywają głębokie (realnie widziane 4 poziomy, firma mówi
            # o nawet 6), więc nie ucinamy po stałej głębokości — pilnujemy
            # tylko cyklu (ten sam symbol na własnej ścieżce), który zawiesiłby
            # rekurencję. Subiekt ma na to własną walidację przy zapisie.
            klucz = p["symbol"].upper()
            if klucz in sciezka:
                return
            dalej = sciezka + (klucz,)
            for s in p["skladniki"]:
                child = by_symbol.get(s["symbol"].upper())
                if child:
                    wstaw(node, child, glebokosc + 1, dalej)

        # Korzenie: ZZ i Z, które same nie są niczyim składnikiem; potem reszta.
        korzenie = [p for p in plan["pozycje"]
                    if p["typ"] in KOMPLETY and p["symbol"].upper() not in dzieci]
        # Filtr typu albo tryb płaski → jedna lista zamiast hierarchii.
        # Przy filtrze drzewo i tak by się rozpadło (pokazanie samych STANDARD
        # bez ich rodziców nie jest drzewem), więc świadomie pokazujemy płasko.
        if self.plaska_var.get() or self._filtr_typu_aktywny():
            # Płaska lista nie ma hierarchii, więc kolumna „Struktura" tylko
            # duplikowałaby numer rysunku i zabierała 230 px nazwom.
            self.tree.column("#0", width=0, minwidth=0, stretch=False)
            pasujace = [p for p in plan["pozycje"] if self._typ_pasuje(p["typ"])]
            for p in sorted(pasujace, key=lambda x: x["symbol"]):
                self.tree.insert(
                    "", "end", text="",
                    values=("", p["symbol"], p["typ"], f"{p['ilosc']:g}", opis(p), p["nazwa"]),
                    tags=(tag(p),))
            return

        self.tree.column("#0", width=230, minwidth=80, stretch=False)

        for p in sorted(korzenie, key=lambda x: (x["typ"] != "ZZ", x["symbol"])):
            wstaw("", p)

        luzne = [p for p in plan["pozycje"]
                 if p["symbol"].upper() not in dzieci and p not in korzenie]
        if luzne:
            grupa = self.tree.insert("", "end", text="Pozostałe pozycje",
                                     values=("", "", "", "", f"{len(luzne)} poz. bez złożenia", ""), open=False)
            for p in sorted(luzne, key=lambda x: x["symbol"]):
                wstaw(grupa, p)

    # ── zapis ──────────────────────────────────────────────────────────────
    def _plan_do_zapisu(self):
        """Plan ograniczony do wybranych pozycji.

        Do Subiekta idzie tylko to, co ma kartotekę (istniejącą) albo zostało
        zaznaczone do założenia. Pozycje pominięte znikają też ze składów
        kompletów i z ZK — inaczej most próbowałby dodać coś, czego nie ma.
        """
        brakujace = self._do_zalozenia()
        dostepne = {p["symbol"].strip().upper() for p in self.plan["pozycje"]}
        dostepne = (dostepne - brakujace) | self.wybrane

        pozycje = []
        for p in self.plan["pozycje"]:
            if p["symbol"].strip().upper() not in dostepne:
                continue
            q = dict(p)
            q["skladniki"] = [s for s in p["skladniki"]
                              if s["symbol"].strip().upper() in dostepne]
            pozycje.append(q)

        plan = dict(self.plan)
        plan["pozycje"] = pozycje
        plan["podmiot"] = self.var_podmiot.get().strip()
        plan["tytul"] = self.var_tytul.get().strip()
        return plan

    def _write_async(self):
        if not self.plan:
            return

        podmiot = self.var_podmiot.get().strip()
        if not podmiot:
            messagebox.showwarning("Subiekt", "Podaj podmiot na ZK.", parent=self)
            return

        plan = self._plan_do_zapisu()
        nowe = len(self.wybrane)
        kompl = sum(1 for p in plan["pozycje"] if p["typ"] in KOMPLETY and p["skladniki"])
        pominiete = len(self._do_zalozenia()) - nowe

        if not plan["pozycje"]:
            messagebox.showwarning(
                "Subiekt",
                "Nic nie zostało wybrane do zapisu.\n\n"
                "Żadna pozycja nie ma kartoteki i nic nie jest zaznaczone —\n"
                "ZK nie miałoby z czego powstać.",
                parent=self)
            return

        # Co się stanie z ZK — most już to ustalił w suchym przebiegu. Bez tego
        # okno pisało „ZK … — 266 pozycji" nawet wtedy, gdy realnie dopisywało
        # kilka pozycji do istniejącego dokumentu (zgłoszone 04.09.2026).
        opis_zk = (f"  • ZK „{self.var_tytul.get().strip()}” dla podmiotu „{podmiot}”\n"
                   f"    — {len(plan['pozycje'])} pozycji, "
                   f"Uwagi: „{numer_projektu(self.project_name, self.project_id)}”\n")
        for k in (self.dry or {}).get("kroki", []):
            if k.get("Rodzaj") != "zk":
                continue
            if k.get("Status") == "do-dopisania":
                opis_zk = (f"  • istniejące {k['Symbol']} — {k.get('Szczegoly') or 'dopisanie pozycji'}\n"
                           f"    (nowy dokument NIE powstanie)\n")
            elif k.get("Status") == "bez-zmian":
                opis_zk = f"  • {k['Symbol']} — bez zmian, wszystko już na dokumencie\n"
            break

        # Zapis idzie na bazę produkcyjną — potwierdzenie musi mówić wprost,
        # co powstanie i czego (kartotek) nie da się łatwo cofnąć.
        ok = messagebox.askyesno(
            "Zapis do Subiekta — potwierdzenie",
            f"Baza PRODUKCYJNA.\n\n"
            f"Powstanie:\n"
            f"  • kartoteki: {nowe}"
            + (f"   (pomijasz {pominiete} pozycji bez kartoteki)" if pominiete else "") + "\n"
            f"  • komplety (Z/ZZ): {kompl}\n"
            + opis_zk +
            f"\nZK można w Subiekcie usunąć. Kartotek i kompletów tak łatwo nie —\n"
            f"zostaną w kartotece asortymentu.\n\n"
            f"Zapisać?",
            parent=self, icon="warning")
        if not ok:
            return

        self.btn_write.config(state=tk.DISABLED)
        self.btn_refresh.config(state=tk.DISABLED)
        self.status.config(text="Zapisuję do Subiekta — nie zamykaj okna…")
        threading.Thread(target=self._write_worker, daemon=True).start()

    def _write_worker(self):
        try:
            wynik = run_bridge(self._plan_do_zapisu(), zapisz=True)
            self.after(0, lambda: self._write_done(wynik, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._write_done(None, err))

    def _write_done(self, wynik, error):
        self.btn_refresh.config(state=tk.NORMAL)
        if error:
            self.status.config(text="Zapis nieudany.")
            messagebox.showerror("Subiekt — zapis", error, parent=self)
            self.btn_write.config(state=tk.NORMAL)
            return

        kroki = wynik.get("kroki", [])
        zal = sum(1 for k in kroki if k["Status"] == "zalozona")
        kom = sum(1 for k in kroki if k["Rodzaj"] == "komplet" and k["Status"].startswith("utworzony"))
        bledy = [k for k in kroki if k["Status"] == "blad"]
        zk = wynik.get("zk")
        log = save_log(self.project_id, wynik)
        zmap = zapisz_mapowania(wynik)

        # Co się stało z ZK — „utworzone" i „dopisano do istniejącego" to dwie
        # różne informacje, a użytkownik musi wiedzieć, którą dostał.
        zk_opis = f"ZK: {zk or '—'}"
        for k in kroki:
            if k.get("Rodzaj") == "zk" and k.get("Status"):
                zk_opis = f"ZK {k['Symbol']}: {k['Status']}"
                break

        lines = [
            f"Kartoteki założone: {zal}",
            f"Komplety utworzone: {kom}",
            zk_opis,
            f"Mapowań zapamiętanych: {zmap}",
        ]
        if bledy:
            lines += ["", f"Błędy ({len(bledy)}):"]
            lines += [f"  • {b['Rodzaj']} {b['Symbol']}: {b.get('Szczegoly') or ''}" for b in bledy[:12]]
            if len(bledy) > 12:
                lines.append(f"  … i {len(bledy) - 12} więcej (szczegóły w logu)")
        if log:
            lines += ["", f"Log: {log}"]

        self.status.config(text=f"Zapisano. ZK: {zk or '—'}" + (f"   ⚠ błędów: {len(bledy)}" if bledy else ""))
        (messagebox.showwarning if bledy else messagebox.showinfo)(
            "Subiekt — zapis zakończony", "\n".join(lines), parent=self)
        self._dry_run_async()      # odśwież — pokaże już założone kartoteki jako istniejące


def open_window(parent, project_id, project_name=None):
    """Punkt wejścia dla RM_BAZA."""
    if not project_id:
        messagebox.showwarning("Subiekt", "Najpierw wybierz projekt.", parent=parent)
        return None
    return SubiektProjektWindow(parent, project_id, project_name)


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 22
    pname = sys.argv[2] if len(sys.argv) > 2 else None
    root = tk.Tk()
    root.withdraw()
    w = open_window(root, pid, pname)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
