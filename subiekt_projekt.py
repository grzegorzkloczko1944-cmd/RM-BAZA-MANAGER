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
from rm_kreciolek import Kreciolek

import subiekt_mapowania
from subiekt_stany import (_find_exe, blad_mostu, jedna_linia, CONFIG_PATH,
                           PROJECTS_DIR, looks_like_drawing_no, wysrodkuj,
                           wczytaj_szerokosci, zapisz_szerokosci)

TIMEOUT_S = 600          # zapis bywa wolniejszy od odczytu — kartoteki idą pojedynczo

#: Lokalny log techniczny (ślad każdej operacji tej maszyny).
LOG_DIR = r"C:\RMPAK_CLIENT\subiekt_logi"

# Wspólna historia operacji na Subiekcie — patrz subiekt_historia.py.
import subiekt_historia
from subiekt_historia import historia_dir, zapisz_historie, znajdz_logi

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
        bib_col = ["dwf_biblioteka"] if "dwf_biblioteka" in cols else []
        sel = ["work_drawing_no", "norm_drawing_no", "src_drawing_no"] + name_cols + qty_cols + cls_cols + bib_col
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
    c1 = c0 + len(cls_cols)     # koniec kolumn typu, przed dwf_biblioteka

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
        typ = first(r[c0:c1])
        typ = str(typ).strip().upper() if typ else "UNKNOWN"
        biblioteczne = bool(bib_col) and bool(r[c1])

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
            "biblioteczne": biblioteczne,
        })
    return out


def read_hidden_drawings(project_id):
    """{NUMER: nazwa} — pozycje UKRYTE w arkuszu (is_hidden = 1).

    Potrzebne, żeby odróżnić dwie zupełnie różne przyczyny tego samego
    objawu „składnika z drzewka nie ma w BOM-ie":
      * pozycja UKRYTA  → wystarczy ją odkryć w arkuszu,
      * numer ZMIENIONY → trzeba poprawić w Inventorze i przeimportować.
    Bez tego okno zgadywało drugą przyczynę także wtedy, gdy chodziło
    o pierwszą (zgłoszone 06.09.2026).

    Nazwy, bo sam numer nie mówi, co to za część — a ukrytej pozycji nie ma
    w BOM-ie, więc okno nie ma skąd jej nazwy wziąć.
    """
    path = os.path.join(PROJECTS_DIR, f"project_{project_id}.sqlite")
    if not os.path.isfile(path):
        return {}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info('items')")}
        if "is_hidden" not in cols:
            return {}
        nr_cols = [c for c in ("work_drawing_no", "norm_drawing_no", "src_drawing_no") if c in cols]
        nm_cols = [c for c in ("work_name", "src_name") if c in cols]
        rows = con.execute(
            f"SELECT {', '.join(nr_cols + nm_cols)} FROM items "
            "WHERE COALESCE(is_hidden, 0) = 1").fetchall()
    finally:
        con.close()

    def pierwsza(vals):
        for v in vals:
            if v is not None and str(v).strip():
                return jedna_linia(v).strip()
        return ""

    ukryte = {}
    n = len(nr_cols)
    for r in rows:                       # ta sama kolejność co przy czytaniu BOM-u
        nr = pierwsza(r[:n])
        if nr:
            ukryte[nr.upper()] = pierwsza(r[n:])
    return ukryte


def read_tree(project_name):
    """{rodzic: [(dziecko, ilosc_lokalna)]} z arkusza „DRZEWKO TEKST".

    Zwraca (kids, powod, nazwy), gdzie `nazwy` to {NUMER: nazwa z drzewka} —
    dla składników spoza BOM-u jedyne źródło nazwy, bo w BOM-ie ich nie ma.

    Przy niepowodzeniu ({}, powod, {}) — wtedy komplety nie powstaną (nie ma
    z czego zbudować składu), ale kartoteki i ZK owszem.
    """
    try:
        from pathlib import Path
        from import_bom import find_project_folder, find_out_files, find_assembly_tree_rows
    except Exception as e:
        return {}, f"brak import_bom: {e}", {}

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
        return {}, f"katalog projektów niedostępny (próbowano: {', '.join(str(p) for p in kandydaci)})", {}

    folder = find_project_folder(v_root, project_name)
    if not folder:
        return {}, f"nie znaleziono folderu projektu „{project_name}” w {v_root}", {}

    kids = {}
    nazwy = {}          # {NUMER: nazwa z drzewka}
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
            # Nazwa z drzewka — dla składników spoza BOM-u to jedyne miejsce,
            # z którego okno może ją wziąć (w BOM-ie ich nie ma).
            nazwy.setdefault(child.upper(), (row.get("nazwa") or "").strip())
            kids.setdefault(parent, [])
            if not any(c[0].upper() == child.upper() for c in kids[parent]):
                kids[parent].append((child, qty))

    if not found:
        return {}, "nie znaleziono arkusza „DRZEWKO TEKST” w plikach *_OUT.xlsx", {}
    return kids, None, nazwy


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


#: Znaki dopuszczone w symbolu kartoteki, poza literami i cyframi.
#: Tylko te trzy, bo tylko one występują w numerach rysunku RMPAK
#: (2627-100.01, 012-100.16) i nie sprawiają kłopotu nigdzie indziej.
DOZWOLONE_W_SYMBOLU = "-_."

#: Znaki zamieniane na myślnik zamiast wycinane — niosą podział, więc ich
#: usunięcie skleiłoby człony w nieczytelną kaszę („1/2 cala" → „12cala").
NA_MYSLNIK = "/\\+&"


def _tylko_bezpieczne(s):
    """Zostawia w symbolu wyłącznie [A-Za-z0-9-_.], resztę wycina.

    ⚠️ Sam ASCII NIE WYSTARCZY. Code 128 formalnie koduje 32–126, ale
    w praktyce symbol jest też KLUCZEM: wpisywanym ręcznie, wklejanym,
    porównywanym i szukanym. Spacja i znaki `+ & ( ) [ ] " * ; %` gubią się
    przy skanowaniu, rozjeżdżają dopasowanie po TRIM-ie i potrafią wywalić
    filtry w Subiekcie. Zgłoszone 07.09.2026: generator wypuszczał „+”
    w symbolu pozycji.

    Znaki niosące podział (`/`, `\\`, `+`, `&`) zamieniamy na myślnik, żeby
    „Zawór 1/2 + korek” dało „Zawor1-2-korek”, a nie „Zawor12korek”.
    Pełna nazwa i tak zostaje w polu Nazwa kartoteki.
    """
    for znak in NA_MYSLNIK:
        s = s.replace(znak, "-")
    s = s.replace(",", " ")
    s = "".join(c if (c.isalnum() and c.isascii()) or c in DOZWOLONE_W_SYMBOLU
                else (" " if c == " " else "")
                for c in s)
    # Myślniki z zamiany bywają zdublowane („a / + b”) — zwijamy je,
    # tak samo jak spacje; wiodące i końcowe nie niosą nic.
    while "--" in s:
        s = s.replace("--", "-")
    return " ".join(s.split()).strip("-. ")


def symbol_z_nazwy(nazwa):
    """Nazwa → symbol kartoteki dla pozycji BEZ numeru rysunku.

    Elementy znormalizowane (łożyska, paski, uszczelki) nie mają numeru
    rysunku — identyfikuje je nazwa. Ta trafia więc w pole Symbol, ale musi
    być przycięta i pozbawiona znaków, które w symbolu przeszkadzają.
    Zostają wyłącznie litery, cyfry i `- _ .` — patrz _tylko_bezpieczne.
    Pełna nazwa zostaje w polu Nazwa.
    """
    # do_ascii PRZED resztą czyszczenia — polskie znaki i typograficzne
    # myślniki nie mogą trafić do symbolu (kod kreskowy ich nie zakoduje).
    s = " ".join(do_ascii(nazwa).split())
    s = _tylko_bezpieczne(s)

    # SPACJI NIE MA W SYMBOLU NIGDY — nie tylko przy skracaniu. Symbol jest
    # kluczem: wpisywanym z ręki, wklejanym, skanowanym i porównywanym po
    # TRIM-ie. Spacja w środku („Kolo 50 szer") gubi się przy skanowaniu
    # i rozjeżdża dopasowanie tak samo jak „+" (07.09.2026). Wcześniej
    # znikała dopiero, gdy nazwa nie mieściła się w 13 znakach — więc krótkie
    # nazwy przepuszczały ją do Subiekta.
    #
    # Usuwamy je zamiast ciąć na granicy słowa. Przy 13 znakach cięcie po
    # słowie gubiło rozróżniające końcówki: „5M L2525 szer25" → „5M L2525"
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
    # To samo sito co w symbol_z_nazwy — inaczej „+" czy nawias wróciłby
    # tędy, omijając tamto czyszczenie (07.09.2026).
    pelna = _tylko_bezpieczne(" ".join(do_ascii(nazwa).split()))

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
    # Rozdzielamy MYŚLNIKIEM, nie „#": ten znak sam wypadał z symbolu przy
    # czyszczeniu, więc licznik dawał symbol niezgodny z resztą reguł
    # („uszczelkiTC#2” → po sicie „uszczelkiTC2”, czyli co innego niż
    # zapisano). Myślnik jest dozwolony i występuje w numerach rysunku.
    baza = (kandydat or symbol_z_nazwy(nazwa))[:MAX_SYMBOL - 2]
    i = 2
    while f"{baza}-{i}" in uzyte:
        i += 1
    return f"{baza}-{i}"


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
    """Buduje plan dla mostu + dane do wyświetlenia.

    Zwraca (plan, items, ostrzezenie, poza_bom, ukryte_cale_galezie), gdzie `poza_bom` to
    {rodzic: [numer, …]} — składniki obecne w DRZEWKU, ale nieobecne w BOM-ie.
    Nie trafią do Subiekta, więc okno musi je pokazać (patrz komentarz przy
    zbieraniu tej mapy).
    """
    items = read_project_items(project_id)
    # Pozycje z numerem rysunku muszą wyglądać jak numer (odsiewa opisy wpisane
    # w to pole). Pozycje BEZ numeru — znormalizowane, identyfikowane nazwą —
    # przepuszczamy, bo inaczej wypadłyby łożyska, paski i simmeringi.
    items = [it for it in items
             if it.get("bez_numeru") or looks_like_drawing_no(it["nr"])]
    kids, warn, nazwy_drzewka = read_tree(project_name)

    by_nr = {it["nr"].upper(): it for it in items}
    # Składniki z DRZEWKA, których NIE MA w BOM-ie:
    #   {rodzic: [(numer, "ukryta" | "nieznana"), …]}
    # Dwie różne przyczyny, dwa różne lekarstwa: pozycję UKRYTĄ wystarczy
    # odkryć w arkuszu, a numer NIEZNANY (zmieniony ręcznie albo z innej
    # wersji projektu) trzeba poprawić w Inventorze i przeimportować —
    # drzewko siedzi w pliku *_OUT.xlsx na V: i o zmianach w RM_BAZA nie wie.
    # Wcześniej takie pozycje wypadały po cichu i komplet powstawał NIEPEŁNY
    # ze statusem „utworzony”, czyli wyglądał na sukces (zgłoszone 06.09.2026).
    poza_bom = {}
    # {numer: nazwa} — złożenie Z/ZZ z BIBLIOTEKI (dwf_biblioteka=1) bez ANI
    # JEDNEGO składnika w drzewku. Inny przypadek niż poza_bom: tam dziecko
    # jest w drzewku, tylko brak go w BOM-ie — tu drzewko (V:\...\*_OUT.xlsx)
    # w ogóle nie zna składu, bo skład złożenia bibliotecznego mieszka
    # w bibliotece (B:\), nie w folderze projektu. Sprawdzone na żywych danych
    # 07.09.2026 (projekt 3500, "027-100.00Z Zespół wrzeciona" i
    # "027-300.06Z Uchwyt czujnika" — biblioteka ma tu bałagan, więc drzewko
    # milczy zamiast dać skład).
    #
    # Bez tego rozróżnienia komplet zakładał się PUSTY i wyglądał na sukces —
    # magazynier nie miałby z czego go złożyć i nie wiedziałby o tym, dopóki
    # nie trafiłby na realizację. Stąd osobna kategoria: user MUSI zobaczyć
    # to jawnie i zdecydować (założyć bez składu świadomie / uzupełnić ręcznie /
    # wyłączyć z tego zapisu), zamiast to przechodziło po cichu.
    biblioteczne_bez_skladu = {}
    ukryte = read_hidden_drawings(project_id)
    pozycje = []
    for it in items:
        skladniki = []
        if it["typ"] in KOMPLETY:
            for child_nr, child_qty in kids.get(it["nr"].upper(), []):
                # Do składu kompletu bierzemy tylko to, co jest w BOM-ie —
                # inaczej wpisalibyśmy do Subiekta pozycję, której RM_BAZA nie zna.
                if child_nr.upper() in by_nr:
                    skladniki.append({"symbol": child_nr, "ilosc": child_qty})
                else:
                    # Ukryta czy nieznana? To decyduje, co user ma zrobić.
                    klucz_ch = child_nr.strip().upper()
                    if klucz_ch in ukryte:
                        powod, nazwa_ch = "ukryta", ukryte[klucz_ch]
                    else:
                        powod, nazwa_ch = "nieznana", nazwy_drzewka.get(klucz_ch, "")
                    poza_bom.setdefault(it["nr"], []).append((child_nr, powod, nazwa_ch))
            if not skladniki and it.get("biblioteczne"):
                biblioteczne_bez_skladu[it["nr"]] = it["nazwa"] or it["nr"]
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
            "biblioteczne": bool(it.get("biblioteczne")),
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
    # Ile ukrytych pozycji jest składnikami złożeń, których i tak nie ma
    # w projekcie (ukryta cała gałąź). To NIE jest problem — służy tylko do
    # wyjaśnienia, czemu przy setkach ukrytych ostrzeżenie wymienia kilka.
    poza_zgloszone = {n.strip().upper() for lst in poza_bom.values() for n, _, _ in lst}
    w_drzewku = {c[0].strip().upper() for lst in kids.values() for c in lst}
    ukryte_cale_galezie = sum(
        1 for nr in ukryte if nr in w_drzewku and nr not in poza_zgloszone)
    return plan, items, warn, poza_bom, ukryte_cale_galezie, biblioteczne_bez_skladu


# ── Wywołanie mostu ─────────────────────────────────────────────────────────
def run_bridge(plan, zapisz=False, timeout=TIMEOUT_S, tryb="projekt"):
    """Suchy przebieg (zapisz=False) albo realny zapis. Zwraca dict z JSON-a.

    `tryb="projekt-cofnij"` używa tego samego planu do USUNIĘCIA tego, co
    "projekt" założyło (subiekt_sfera/NexoRecon/ProjektCofnij.cs) — ten sam
    kanał, ta sama obsługa błędów, inny tryb mostu.
    """
    exe = _find_exe()
    if not exe:
        raise RuntimeError(
            "Nie znaleziono NexoRecon.exe.\n\n"
            "Zbuduj most:\n  cd subiekt_sfera\\NexoRecon\n  dotnet build -c Release")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")

    # ZAPIS, i to najcięższy — zakłada/usuwa kartoteki, komplety i ZK naraz.
    # Żadnego ponawiania (plan, sekcja 14): powtórzenie po niejednoznacznym
    # błędzie zdublowałoby (albo dwukrotnie próbowało skasować) dokumenty projektu.
    args = {"plan": plan}
    if zapisz:
        args["zapisz"] = True
    try:
        import subiekt_bridge
        return subiekt_bridge.call(
            tryb, args, timeout=timeout, write=zapisz,
            fallback=lambda: _projekt_cli(plan, zapisz, timeout, tryb))
    except ImportError:
        return _projekt_cli(plan, zapisz, timeout, tryb)


def _projekt_cli(plan, zapisz, timeout, tryb="projekt"):
    """Stara ścieżka: osobny proces NexoRecon.exe."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")

    tmpdir = tempfile.mkdtemp(prefix="subiekt_proj_")
    plan_path = os.path.join(tmpdir, "plan.json")
    out_path = os.path.join(tmpdir, "wynik.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)

    cmd = [exe, tryb, f"--plan={plan_path}", f"--out={out_path}"]
    if zapisz:
        cmd.append("--zapisz")

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Subiekt nie odpowiedział w {timeout} s.")

    if proc.returncode != 0 or not os.path.isfile(out_path):
        raise RuntimeError(blad_mostu(exe, tryb, proc, out_path))

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


def save_log(project_id, wynik, plan=None):
    """Zapisuje co powstało — bez tego nie da się potem posprzątać w Subiekcie.

    `plan` (gdy podany) trafia do tego samego pliku pod kluczem "plan" — to
    DOKŁADNIE ten sam plan.json, którego most użył do założenia, więc tryb
    "projekt-cofnij" (subiekt_sfera/NexoRecon/ProjektCofnij.cs) może go użyć
    wprost, bez odtwarzania z samego "wynik" (który ma tylko listę kroków —
    symbole i statusy — a nie typ/składniki potrzebne do cofnięcia w
    poprawnej kolejności). Bez tego "cofnij po kilku dniach" nie miałoby
    z czego korzystać, bo self.plan w oknie żyje tylko w pamięci sesji.
    """
    return zapisz_historie("projekt", wynik, project_id=project_id, plan=plan)


def znajdz_logi_projektu(project_id):
    """Wszystkie logi zapisu tego projektu, najnowszy pierwszy — kandydaci do cofnięcia.

    Szuka NAJPIERW we wspólnym katalogu na serwerze (tam trafiają zapisy
    wszystkich stanowisk), potem lokalnie. Ta sama nazwa pliku w obu miejscach
    to ten sam zapis — liczy się raz, wersja serwerowa ma pierwszeństwo.
    """
    return znajdz_logi("projekt", project_id=project_id, wymagaj_planu=True)


# ── Okno ────────────────────────────────────────────────────────────────────
class SubiektProjektWindow(tk.Toplevel, Kreciolek):
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
        #: {rodzic: [numer, …]} — składniki z drzewka spoza BOM-u (rozjazd numerów)
        self.poza_bom = {}
        #: powód nieczytania drzewka (None = wczytane) — bez niego brak kompletów
        self.brak_drzewka = None
        #: ukryte pozycje będące składnikami złożeń, których też nie ma w BOM-ie
        self.ukryte_cale_galezie = 0
        #: {numer: nazwa} złożeń Z/ZZ z biblioteki bez ani jednego składnika
        self.bib_bez_skladu = {}
        #: numery (UPPER) bibliotecznych, dla których user podjął decyzję
        self.bib_potwierdzone = set()
        #: {numer: "bez_skladu"|"pomin"} — jaka to była decyzja
        self._bib_decyzje = {}
        self.plan = None
        self.items = []
        self.dry = None
        # Symbole (UPPER) wybrane do założenia w Subiekcie. Pozycje, które już
        # mają kartotekę, nie są tu trzymane — nie ma czego zakładać.
        self.wybrane = set()
        self.filter_typ_modes = {}  # {typ: 'show'|'hide'} — kafelek ✚

        self.title(f"Projekt / Aktualizacja w Subiekcie — {self.project_name}")
        self.geometry("1080x680")
        self.minsize(900, 400)
        # ŚWIADOMIE bez transient(): okno-dziecko z transient dostaje w Windows
        # tylko przycisk „×", bez minimalizacji i maksymalizacji. To pełnoprawny
        # arkusz roboczy, więc ma się zachowywać jak okno główne RM_BAZA (— □ ×).
        #
        # ⚠️ Skutek uboczny: bez transient Windows nie wie, że to okno-dziecko,
        # więc po zamknięciu modalnego messageboxa fokus wraca do OKNA GŁÓWNEGO
        # RM_BAZA i przykrywa ten arkusz (zgłoszone 07.09.2026 przy zakładaniu
        # projektu — po komunikacie o zapisie na wierzch wyskakiwał arkusz).
        # Dlatego po każdym dialogu przywracamy warstwę przez _na_wierzch().
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self._build_ui()
        self.after(100, self._dry_run_async)

    def _na_wierzch(self):
        """Przywraca to okno na wierzch po zamknięciu modalnego dialogu.

        Bez transient() Windows oddaje fokus oknu głównemu RM_BAZA, a nie temu,
        z którego dialog wyszedł — arkusz przykrywał wtedy okno projektu
        (07.09.2026). lift() + focus_force() na samym oknie wystarczy; NIE
        ustawiamy „-topmost", bo to trzymałoby je nad wszystkim, także nad
        innymi aplikacjami.

        Wołane po dialogu, przez after_idle — w chwili powrotu z messageboxa
        Windows jeszcze przestawia fokus i natychmiastowy lift() bywa zjadany.
        """
        def podnies():
            try:
                self.lift()
                self.focus_force()
            except tk.TclError:
                pass            # okno zamknięte razem z dialogiem
        try:
            self.after_idle(podnies)
        except tk.TclError:
            pass

    def _build_ui(self):
        top = tk.Frame(self, bg="#34495e", height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🏗 Projekt / Aktualizacja w Subiekcie (kartoteki + komplety + ZK)",
                 bg="#34495e", fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)

        self.btn_refresh = tk.Button(top, text="🔄 Przelicz", command=self._dry_run_async,
                                     bg="#3498db", fg="white", font=("Arial", 8),
                                     padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_refresh.pack(side=tk.RIGHT, padx=10, pady=8)

        # Na GÓRNEJ belce, nie na dole: to rzeczy, o których user ma pamiętać
        # przez cały czas pracy z oknem, a nie dopiero przy zapisie.
        self.btn_todo = tk.Button(top, text="📋 Do zrobienia",
                                  command=self._okno_notatki, bg="#8e44ad", fg="white",
                                  font=("Arial", 8), padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_todo.pack(side=tk.RIGHT, padx=(0, 4), pady=8)
        # Powrót do okna decyzji o bibliotecznych — pokazywany tylko wtedy,
        # gdy jakaś pozycja czeka na decyzję (patrz _odswiez_stan_zapisu).
        self.btn_bib = tk.Button(top, text="⛔ Decyzje", command=self._pokaz_biblioteczne,
                                 bg="#c0392b", fg="white", font=("Arial", 8, "bold"),
                                 padx=8, pady=2, relief=tk.RAISED, bd=1)
        # Rozjazd RM_BAZA ↔ drzewko — też tylko na żądanie, nie samo z siebie.
        self.btn_poza = tk.Button(top, text="⚠ Rozjazd drzewka", command=self._pokaz_poza_bom,
                                  bg="#e67e22", fg="white", font=("Arial", 8),
                                  padx=8, pady=2, relief=tk.RAISED, bd=1)

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

        # Wybór, co zakładać w asortymencie Subiekta.
        sel = tk.Frame(self, bg="#f4ecf7")
        sel.pack(side=tk.TOP, fill=tk.X)
        tk.Label(sel, text="Zakładaj kartoteki dla:", bg="#f4ecf7",
                 font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(12, 6), pady=5)
        #: przyciski trybu — aktywny jest wyróżniony (patrz _podswietl_tryb)
        self._btn_tryby = {}
        for etykieta, tryb, opis in (
            ("złożenia z zawartością", "komplety", "tylko Z/ZZ i to, co w nie wchodzi"),
            ("złożenia z zawartością + pozostałe", "wszystko", "cały BOM"),
            ("nic", "nic", "tylko istniejące kartoteki"),
        ):
            b = tk.Button(sel, text=etykieta, command=lambda t=tryb: self._zaznacz_tryb(t),
                          bg="#8e44ad", fg="white", font=("Arial", 8), padx=8, pady=1,
                          relief=tk.RAISED, bd=1, cursor="hand2")
            b.pack(side=tk.LEFT, padx=3, pady=5)
            self._btn_tryby[tryb] = b
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

        # Legenda kolorów. Bez niej trzeba było zgadywać, czy pomarańczowy
        # znaczy „jest" czy „nie ma" — a to decyduje o tym, co się zaznaczy
        # do założenia (zgłoszone 07.09.2026). Kolory MUSZĄ się zgadzać
        # z tag_configure niżej; opisy mówią, co zrobić, nie tylko co to jest.
        leg = tk.Frame(self, bg="#ecf0f1")
        leg.pack(side=tk.TOP, fill=tk.X)
        tk.Label(leg, text="Kolory:", bg="#ecf0f1", fg="#7f8c8d",
                 font=("Arial", 8, "bold"), padx=12).pack(side=tk.LEFT, pady=(0, 4))
        for kolor, opis in (
                ("#d5f5e3", "jest w Subiekcie — nic do zrobienia"),
                ("#d4e6f1", "złożenie (Z/ZZ), kartoteka jest — będzie komplet"),
                ("#fdebd0", "BRAK kartoteki — zaznacz ✓, żeby założyć"),
                ("#fadbd8", "błąd — pozycja nie przejdzie")):
            tk.Label(leg, text="   ", bg=kolor, relief=tk.SOLID, bd=1).pack(
                side=tk.LEFT, padx=(8, 3), pady=(0, 4))
            tk.Label(leg, text=opis, bg="#ecf0f1", fg="#7f8c8d",
                     font=("Arial", 8)).pack(side=tk.LEFT, pady=(0, 4))

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
        # Dymki z pełną nazwą — WYŁĄCZONE na życzenie (07.09.2026). Wyskakiwały
        # przy każdym przesunięciu myszy nad drzewkiem i zasłaniały wiersze,
        # a przy przeglądaniu listy przeszkadzały bardziej, niż pomagały.
        # Kod (_tooltip_ruch / _tooltip_ukryj) zostaje — żeby przywrócić,
        # wystarczy zdjąć ten przełącznik.
        #
        # Ucięte nazwy da się zobaczyć inaczej: poszerzając kolumnę (szerokość
        # jest zapamiętywana między sesjami) albo w karcie pozycji.
        self.DYMKI = False
        self._tip = None
        self._tip_wiersz = None
        if self.DYMKI:
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

        # Pasek blokady — nad statusem, tuż pod przyciskiem zapisu. Pokazywany
        # tylko gdy coś blokuje zapis (patrz _odswiez_stan_zapisu).
        self.pasek_blokady = tk.Label(self, text="", anchor="w", padx=12, pady=5,
                                      bg="#c0392b", fg="white",
                                      font=("Arial", 9, "bold"))

    # ── suchy przebieg ─────────────────────────────────────────────────────
    def _dry_run_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.btn_write.config(state=tk.DISABLED)
        self.start_kreciolek("Czytam BOM i pytam Subiekta (nic nie zapisuję)")
        threading.Thread(target=self._dry_run_worker, daemon=True).start()

    def _dry_run_worker(self):
        try:
            plan, items, warn, poza_bom, ukryte_galezie, bib_bez_skladu = build_plan(
                self.project_id, self.project_name,
                self.var_podmiot.get().strip(), self.var_tytul.get().strip())
            if not plan["pozycje"]:
                self.after(0, lambda: self._dry_done(None, None, [], "Brak pozycji z numerem rysunku.", {}, 0, {}))
                return
            wynik = run_bridge(plan, zapisz=False)
            # Suchy przebieg też jest okazją do zapamiętania trafień — kolejny
            # projekt z tymi numerami nie będzie musiał pytać Subiekta.
            zapisz_mapowania(wynik)
            self.after(0, lambda: self._dry_done(plan, wynik, items, warn, poza_bom, ukryte_galezie, bib_bez_skladu))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._dry_done(None, None, [], err, {}, 0, {}))

    def _dry_done(self, plan, wynik, items, warn, poza_bom=None, ukryte_galezie=0, bib_bez_skladu=None):
        self.btn_refresh.config(state=tk.NORMAL)
        if plan is None:
            self.stop_kreciolek()
            self.status.config(text="Błąd.")
            self.summary.config(text=(warn or "")[:200])
            if warn:
                messagebox.showerror("Subiekt", warn, parent=self)
                self._na_wierzch()
            return

        self.plan, self.dry, self.items = plan, wynik, items
        # Powód, dla którego drzewko się nie wczytało (brak folderu na V:,
        # brak arkusza „DRZEWKO TEKST”). Bez drzewka NIE POWSTANIE ŻADEN
        # komplet, więc informacja musi dojść też do potwierdzenia zapisu —
        # sam dopisek w pasku statusu ginie (zgłoszone 06.09.2026).
        self.brak_drzewka = warn
        # {numer: nazwa} — złożenia Z/ZZ z BIBLIOTEKI (B:\) bez ŻADNEGO składnika
        # w drzewku. Skład bibliotecznych złożeń nie mieszka w folderze projektu
        # na V:, więc drzewko o nim nie wie — inny przypadek niż poza_bom.
        # User MUSI to jawnie potwierdzić per pozycja, inaczej zapis jest
        # zablokowany (zgłoszone 07.09.2026: "magazynier ma z czego te dwa
        # złożenia złożyć, ale nie ma na to papierów" — komplet zakładałby się
        # PUSTY i wyglądałby na sukces, dopóki ktoś nie trafi na realizację).
        self.bib_bez_skladu = bib_bez_skladu or {}
        self.bib_potwierdzone = set()   # numery, dla których user kliknął decyzję
        self._fill_tree(plan, wynik)
        self.btn_dodaj.config(state=tk.NORMAL)

        # Domyślnie WSZYSTKO — cały BOM zaznaczony.
        #
        # Wcześniej domyślne były „złożenia z zawartością", z obawy przed
        # zakładaniem kartotek, których nie da się łatwo usunąć. Ale to mylące:
        # okno pokazywało „pomijasz 44" bez wyjaśnienia, skąd te 44 się biorą,
        # a user i tak zwykle chce cały projekt (zgłoszone 08.09.2026).
        # Obawa jest dziś mniejsza: tryb „projekt-cofnij" usuwa to, co założone,
        # a okno potwierdzenia wypisuje pozycja po pozycji, co powstanie.
        self._zaznacz_tryb("wszystko")

        # Okno decyzji NIE otwiera się samo — tylko przyciskiem „⛔ Decyzje"
        # na górnej belce. Jest modalne (grab_set), więc każde automatyczne
        # wyskoczenie odbierało fokus i wypychało arkusz główny RM_BAZA na
        # wierzch (zgłoszone 08.09.2026, dwukrotnie). Nic przez to nie
        # przechodzi po cichu: zapis zostaje zablokowany do czasu decyzji,
        # przycisk pokazuje ile ich czeka, a pasek statusu mówi wprost dlaczego.
        self._odswiez_stan_zapisu()

        # Lista „do zrobienia" — dokładamy to, co ten podgląd wykrył, bez
        # ruszania odhaczeń i zadań dopisanych ręcznie.
        try:
            subiekt_historia.scal_zadania(self.project_id, self._wykryte_zadania())
        except Exception:
            pass
        self._odswiez_licznik_todo()

        pust = sum(1 for k in wynik.get("kroki", [])
                   if k["Rodzaj"] == "komplet" and k["Status"] == "pominiety-brak-skladnikow")
        note = f"   ⚠ {warn}" if warn else ""
        extra = f"   ⚠ {pust} kompletów bez składników w drzewie" if pust else ""
        self.poza_bom = poza_bom or {}
        self.ukryte_cale_galezie = ukryte_galezie
        ile_poza = sum(len(v) for v in self.poza_bom.values())
        rozjazd = f"   ⚠ {ile_poza} składników z drzewka NIE wejdzie do kompletów" if ile_poza else ""
        self.stop_kreciolek()
        self.status.config(
            text=f"Podgląd gotowy — w Subiekcie nic nie zmieniono.{extra}{rozjazd}{note}")

        # Rozjazd RM_BAZA ↔ drzewko też NIE wyskakuje sam (ta sama przyczyna
        # co przy oknie decyzji: modalne okno zabiera fokus i wypycha arkusz
        # główny na wierzch). Informacja nie ginie — jest w pasku statusu,
        # na przycisku z licznikiem i jako zadanie na liście „Do zrobienia".
        try:
            if ile_poza:
                self.btn_poza.config(text=f"⚠ Rozjazd drzewka ({ile_poza})")
                self.btn_poza.pack(side=tk.RIGHT, padx=(0, 4), pady=8)
            else:
                self.btn_poza.pack_forget()
        except (AttributeError, tk.TclError):
            pass

    # ── rozjazd RM_BAZA ↔ drzewko ──────────────────────────────────────────
    def _pokaz_poza_bom(self):
        """Pełna lista składników z drzewka, których nie ma w BOM-ie.

        Osobne okno, nie messagebox: lista bywa długa, a użytkownik musi móc
        ją skopiować i porównać z arkuszem. Tekst jest zaznaczalny.
        """
        wszystkie = [(r, n, p) for r, lst in self.poza_bom.items() for n, p, _ in lst]
        ile = len(wszystkie)
        n_ukryte = sum(1 for _, _, p in wszystkie if p == "ukryta")
        n_nieznane = ile - n_ukryte
        # Nazwy kompletów (rodziców) z BOM-u — sam numer nie mówi, co to za zespół.
        nazwy_rodzicow = {it["nr"].upper(): (it.get("nazwa") or "")
                          for it in (self.items or [])}

        okno = tk.Toplevel(self)
        okno.title("Uwaga: składniki, których nie będzie w kompletach")
        okno.geometry("660x480")
        okno.transient(self)

        naglowek = tk.Frame(okno, bg="#c0392b")
        naglowek.pack(fill=tk.X)
        tk.Label(naglowek, text=f"⚠ {ile} składników z drzewka NIE wejdzie do kompletów",
                 bg="#c0392b", fg="white", font=("Arial", 11, "bold"),
                 anchor="w", padx=12, pady=8).pack(fill=tk.X)

        # Porada zależy od przyczyny — ukrytą pozycję wystarczy odkryć,
        # zmieniony numer wymaga poprawki w Inventorze i reimportu.
        opis = ["Te numery są w drzewku (arkusz „DRZEWKO TEKST” w pliku *_OUT.xlsx),",
                "ale nie ma ich w BOM-ie, więc nie trafią do składu kompletów",
                "w Subiekcie. Komplety powstaną, tylko NIEPEŁNE.", ""]
        if n_ukryte:
            opis += [f"• {n_ukryte} UKRYTYCH w arkuszu — odkryj je w RM_BAZA,",
                     "  jeśli mają wejść w skład kompletu."]
        # Ukrytych pozycji bywają setki, ale liczą się tylko te, których
        # rodzic ZOSTAŁ w projekcie. Ukryte całe gałęzie (złożenie razem ze
        # składnikami) nie są problemem — tych kompletów i tak nie zakładamy.
        # Bez tego zdania „1 składników" przy 127 ukrytych wygląda podejrzanie
        # (zgłoszone 06.09.2026).
        if self.ukryte_cale_galezie:
            opis += ["",
                     f"Pozostałe ukryte pozycje ({self.ukryte_cale_galezie}) to całe złożenia",
                     "ukryte razem ze składnikami — tych kompletów nie zakładasz,",
                     "więc nic tam nie brakuje."]
        if n_nieznane:
            opis += [f"• {n_nieznane} NIEZNANYCH — nie ma ich w projekcie pod tym numerem.",
                     "  Zwykle numer zmieniony ręcznie albo drzewko z innej wersji;",
                     "  popraw w Inventorze i przeimportuj projekt."]
        tk.Label(okno, justify="left", anchor="w", padx=12, pady=8, wraplength=620,
                 text="\n".join(opis)).pack(fill=tk.X)

        ramka = tk.Frame(okno)
        ramka.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        txt = tk.Text(ramka, wrap="none", font=("Consolas", 9), bg="#fdfefe")
        vs = tk.Scrollbar(ramka, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=vs.set)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)

        for rodzic in sorted(self.poza_bom):
            dzieci = self.poza_bom[rodzic]
            nazwa_r = nazwy_rodzicow.get(rodzic.upper(), "")
            txt.insert("end", f"{rodzic}  {nazwa_r}".rstrip()
                              + f"   (brakuje {len(dzieci)}):\n")
            for numer, powod, nazwa in sorted(dzieci):
                znacznik = "ukryta  " if powod == "ukryta" else "nieznana"
                txt.insert("end", f"      [{znacznik}] {numer:<18} {nazwa}\n")
            txt.insert("end", "\n")
        txt.config(state="disabled")      # do czytania i kopiowania, nie do edycji

        stopka = tk.Frame(okno)
        stopka.pack(fill=tk.X, padx=12, pady=(0, 10))
        tk.Button(stopka, text="Kopiuj listę", command=lambda: self._kopiuj_poza_bom(okno),
                  bg="#7f8c8d", fg="white", relief=tk.FLAT, padx=12).pack(side=tk.LEFT)
        tk.Button(stopka, text="Rozumiem", command=okno.destroy,
                  bg="#2c3e50", fg="white", relief=tk.FLAT, padx=18).pack(side=tk.RIGHT)

        wysrodkuj(okno, self)
        okno.grab_set()

    def _pokaz_biblioteczne(self):
        """Złożenia Z/ZZ z BIBLIOTEKI bez żadnego składnika w drzewku.

        User MUSI zdecydować per pozycja — zapis jest zablokowany, dopóki
        każda z nich nie dostanie jawnej decyzji. Nie ma tu przycisku
        "Rozumiem, zamknij" bez wyboru: to dokładnie ta ścieżka, którą trzeba
        zamknąć, żeby pusty komplet nie przeszedł po cichu.
        """
        okno = tk.Toplevel(self)
        okno.title("Decyzja wymagana: złożenia biblioteczne bez składu")
        # Wysokość rośnie z liczbą pozycji, ale nie przekracza ekranu.
        wys = min(560, 300 + 62 * len(self.bib_bez_skladu))
        okno.geometry(f"760x{wys}")
        okno.minsize(680, 320)
        okno.resizable(True, True)
        okno.transient(self)
        # X i Escape zamykają okno BEZ decyzji (jak przycisk „Anuluj") —
        # zapis zostaje zablokowany, tak jak był, i user wraca do niego przez
        # „Odśwież". Wcześniej X/Escape były całkiem zablokowane i jedynym
        # wyjściem było wybranie „Pomiń" wbrew swojej woli — user nie miał
        # jak się wycofać z całej procedury (zgłoszone 08.09.2026: „brak
        # anulu, esc, jak chce odstąpić od procedury").
        okno.protocol("WM_DELETE_WINDOW", okno.destroy)
        okno.bind("<Escape>", lambda e: okno.destroy())

        naglowek = tk.Frame(okno, bg="#c0392b")
        naglowek.pack(fill=tk.X)
        tk.Label(naglowek,
                 text=f"⛔ {len(self.bib_bez_skladu)} złożeń z BIBLIOTEKI bez ani jednego składnika",
                 bg="#c0392b", fg="white", font=("Arial", 11, "bold"),
                 anchor="w", padx=12, pady=8).pack(fill=tk.X)

        tk.Label(okno, justify="left", anchor="w", padx=12, pady=8, wraplength=730, text=(
            "Skład tych złożeń pochodzi z biblioteki (B:\\), a drzewko projektu "
            "(V:\\…_OUT.xlsx) go nie zna. Bez decyzji powstałby PUSTY komplet — "
            "wyglądałby na sukces, a magazynier nie miałby z czego go złożyć.")).pack(fill=tk.X)

        # STOPKA PAKOWANA PRZED LISTĄ — inaczej przy kilku pozycjach lista
        # rozpycha okno i przycisk „Zatwierdź" wypada poza ekran (zgłoszone
        # 07.09.2026: „użera przyciski w oknie").
        stopka = tk.Frame(okno)
        stopka.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=10)

        ramka = tk.Frame(okno)
        ramka.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))
        kanwa = tk.Canvas(ramka, highlightthickness=0)
        vs = tk.Scrollbar(ramka, orient="vertical", command=kanwa.yview)
        wnetrze = tk.Frame(kanwa)
        wnetrze.bind("<Configure>", lambda e: kanwa.configure(scrollregion=kanwa.bbox("all")))
        kanwa.create_window((0, 0), window=wnetrze, anchor="nw")
        kanwa.configure(yscrollcommand=vs.set)
        kanwa.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)

        self._bib_decyzje = getattr(self, "_bib_decyzje", {})   # {numer: "bez_skladu"|"pomin"}
        zmienne = {}
        for numer, nazwa in sorted(self.bib_bez_skladu.items()):
            # Ramka z obwódką: przy kilku pozycjach od razu widać, gdzie kończy
            # się jedna decyzja, a zaczyna druga.
            wiersz = tk.Frame(wnetrze, pady=6, padx=8, relief=tk.GROOVE, bd=1)
            wiersz.pack(fill=tk.X, anchor="w", pady=(0, 6))
            tk.Label(wiersz, text=f"{numer}   {nazwa}", anchor="w",
                     font=("Consolas", 10, "bold")).pack(fill=tk.X)
            # Wartość początkowa "brak", nie "" — pusty string zbiega się
            # z domyślnym stanem Radiobuttona i OBA wyglądały na zaznaczone,
            # choć decyzji nie było (zgłoszone 07.09.2026).
            var = tk.StringVar(value=self._bib_decyzje.get(numer, "brak"))
            zmienne[numer] = var
            # Jeden pod drugim, nie obok siebie — obok siebie drugi wypadał
            # poza szerokość okna i user widział tylko jedną opcję.
            tk.Radiobutton(wiersz, variable=var, value="bez_skladu", anchor="w",
                           text="Załóż jako zwykłą kartotekę (bez składu) — magazynier kompletuje ręcznie",
                           ).pack(fill=tk.X, padx=(12, 0))
            tk.Radiobutton(wiersz, variable=var, value="pomin", anchor="w",
                           text="Pomiń — nie zakładaj tej pozycji w Subiekcie",
                           ).pack(fill=tk.X, padx=(12, 0))

        def zatwierdz():
            brak = [n for n, v in zmienne.items() if v.get() not in ("bez_skladu", "pomin")]
            if brak:
                messagebox.showwarning(
                    "Decyzja wymagana",
                    f"Brakuje decyzji dla {len(brak)} pozycji:\n\n   "
                    + "\n   ".join(sorted(brak))
                    + "\n\nZaznacz jedną z dwóch opcji przy każdej z nich.",
                    parent=okno)
                return
            for n, v in zmienne.items():
                self._bib_decyzje[n] = v.get()
                if v.get() == "bez_skladu":
                    self.bib_potwierdzone.add(n.strip().upper())
                    # Most zakłada Z/ZZ z szablonem Komplet niezależnie od tego,
                    # czy ma składniki — bez tej zmiany typu powstałby PUSTY
                    # komplet (kartoteka rodzaju Komplet bez zdefiniowanego
                    # składu). "Załóż bez składu" ma dać zwykłą kartotekę-towar,
                    # to jawna decyzja usera, nie domyślne zejście po cichu.
                    for p in self.plan["pozycje"]:
                        if p["symbol"].strip().upper() == n.strip().upper():
                            p["typ"] = "STANDARD"
                            break
                else:
                    self.bib_potwierdzone.discard(n.strip().upper())
                    # "Pomiń" = ta pozycja (i jej Z/ZZ-owy status) NIE trafia do
                    # zapisu wcale — usuwamy ją z planu, żeby nie robić z niej
                    # ani kompletu, ani zwykłej kartoteki bez pytania.
                    self.plan["pozycje"] = [p for p in self.plan["pozycje"]
                                             if p["symbol"].strip().upper() != n.strip().upper()]
            okno.destroy()
            self._odswiez_znaczniki()
            self.status.config(text="Decyzje o złożeniach bibliotecznych zapisane.")

        tk.Label(stopka, text="Bez decyzji dla wszystkich pozycji zapis pozostanie zablokowany.",
                 fg="#7f8c8d").pack(side=tk.LEFT)
        tk.Button(stopka, text="Zatwierdź", command=zatwierdz,
                  bg="#2c3e50", fg="white", relief=tk.FLAT,
                  font=("Arial", 10, "bold"), padx=24, pady=4,
                  cursor="hand2").pack(side=tk.RIGHT)
        tk.Button(stopka, text="Anuluj", command=okno.destroy,
                  bg="#95a5a6", fg="white", relief=tk.FLAT,
                  padx=18, pady=4).pack(side=tk.RIGHT, padx=(0, 8))

        wysrodkuj(okno, self)
        okno.grab_set()

    # ── notatka „do zrobienia" ─────────────────────────────────────────────
    def _wykryte_zadania(self):
        """Rzeczy, których okno NIE załatwia — wyliczane z aktualnego podglądu.

        To jest lista tego, co po zamknięciu okna zostaje na głowie człowieka:
        biblioteczne bez składu, złożenia bez węzła w drzewku, składniki spoza
        BOM-u, pominięte pozycje. Wcześniej znikało razem z oknem.
        """
        zadania = []
        for numer, nazwa in sorted(getattr(self, "bib_bez_skladu", {}).items()):
            zadania.append(f"Uzupełnić skład bibliotecznego złożenia {numer} ({nazwa}) "
                           f"— biblioteka B:\\ nie podaje, z czego się składa")

        if self.plan:
            for p in self.plan["pozycje"]:
                if (p["typ"] in KOMPLETY and not p["skladniki"]
                        and p["symbol"].strip().upper() not in getattr(self, "bib_bez_skladu", {})):
                    zadania.append(f"Poprawić drzewko dla {p['symbol']} ({p.get('nazwa') or ''}) "
                                   f"— złożenie {p['typ']} bez żadnego składnika w *_OUT.xlsx")

        for rodzic, dzieci in sorted(getattr(self, "poza_bom", {}).items()):
            ukryte = [n for n, powod, _ in dzieci if powod == "ukryta"]
            nieznane = [n for n, powod, _ in dzieci if powod != "ukryta"]
            if ukryte:
                zadania.append(f"Odkryć w arkuszu {len(ukryte)} pozycji dla kompletu {rodzic}: "
                               + ", ".join(sorted(ukryte)[:5])
                               + (" …" if len(ukryte) > 5 else ""))
            if nieznane:
                zadania.append(f"Poprawić numery w Inventorze i przeimportować — komplet {rodzic} "
                               f"nie znajduje: " + ", ".join(sorted(nieznane)[:5])
                               + (" …" if len(nieznane) > 5 else ""))
        return zadania

    def _odswiez_licznik_todo(self):
        """Liczba niezrobionych na przycisku — inaczej nikt tam nie zajrzy."""
        try:
            dane = subiekt_historia.wczytaj_notatke(self.project_id) or {}
            ile = sum(1 for z in dane.get("zadania", []) if not z.get("zrobione"))
            self.btn_todo.config(
                text=f"📋 Do zrobienia ({ile})" if ile else "📋 Do zrobienia",
                bg="#c0392b" if ile else "#8e44ad")
        except Exception:
            pass

    def _okno_notatki(self):
        """Lista „do zrobienia" projektu — odhaczanie, dopisywanie, notatka.

        Leży we WSPÓLNYM katalogu (subiekt_historia), więc widzi ją każdy
        użytkownik: notuje jeden, robi często ktoś inny.
        """
        dane = subiekt_historia.wczytaj_notatke(self.project_id) or {"zadania": [], "tekst": ""}
        zadania = list(dane.get("zadania", []))

        okno = tk.Toplevel(self)
        okno.title(f"Do zrobienia — projekt {self.project_name}")
        okno.geometry("820x600")
        okno.minsize(640, 420)
        okno.transient(self)
        okno.bind("<Escape>", lambda e: okno.destroy())

        naglowek = tk.Frame(okno, bg="#8e44ad")
        naglowek.pack(fill=tk.X)
        tk.Label(naglowek, text="📋 Czego okno NIE zrobiło — zostaje na Twojej głowie",
                 bg="#8e44ad", fg="white", font=("Arial", 11, "bold"),
                 anchor="w", padx=12, pady=8).pack(fill=tk.X)
        tk.Label(okno, text="Lista jest wspólna dla wszystkich stanowisk — notuje jeden, robi kto inny.",
                 fg="#7f8c8d", font=("Arial", 8), anchor="w", padx=12, pady=4).pack(fill=tk.X)

        # Stopka przed listą — inaczej przy wielu zadaniach przyciski wypadają.
        stopka = tk.Frame(okno)
        stopka.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=10)

        dodaj_ramka = tk.Frame(okno)
        dodaj_ramka.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 6))
        var_nowe = tk.StringVar()
        tk.Entry(dodaj_ramka, textvariable=var_nowe, font=("Arial", 9)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, ipady=3)

        ramka = tk.Frame(okno)
        ramka.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))
        kanwa = tk.Canvas(ramka, highlightthickness=0)
        vs = ttk.Scrollbar(ramka, orient="vertical", command=kanwa.yview)
        wnetrze = tk.Frame(kanwa)
        wnetrze.bind("<Configure>", lambda e: kanwa.configure(scrollregion=kanwa.bbox("all")))
        okno_id = kanwa.create_window((0, 0), window=wnetrze, anchor="nw")
        kanwa.bind("<Configure>", lambda e: kanwa.itemconfig(okno_id, width=e.width))
        kanwa.configure(yscrollcommand=vs.set)
        kanwa.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)

        zmienne = []

        def zapisz_stan():
            for z, var in zmienne:
                nowy = bool(var.get())
                if nowy != bool(z.get("zrobione")):
                    z["zrobione"] = nowy
                    if nowy:
                        z["zrobil"] = os.environ.get("USERNAME") or "?"
                        z["zrobione_kiedy"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    else:
                        z.pop("zrobil", None)
                        z.pop("zrobione_kiedy", None)
            subiekt_historia.zapisz_notatke(self.project_id, zadania=zadania,
                                            tekst=txt.get("1.0", tk.END).strip())
            self._odswiez_licznik_todo()

        def przeladuj():
            for w in wnetrze.winfo_children():
                w.destroy()
            zmienne.clear()
            if not zadania:
                tk.Label(wnetrze, text="Nic do zrobienia — wszystko czysto.",
                         fg="#7f8c8d", anchor="w", padx=6, pady=10).pack(fill=tk.X)
            for z in zadania:
                wiersz = tk.Frame(wnetrze, pady=3)
                wiersz.pack(fill=tk.X, anchor="w")
                var = tk.BooleanVar(value=bool(z.get("zrobione")))
                zmienne.append((z, var))
                cb = tk.Checkbutton(wiersz, variable=var, anchor="nw",
                                    text=z.get("tekst", ""), justify="left",
                                    wraplength=600, command=zapisz_stan)
                if z.get("zrobione"):
                    cb.config(fg="#95a5a6")
                cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
                # Dwuklik w treść = edycja. Także dla auto-zadań: user często
                # chce dopisać ustalenie („czeka na rysunek od Kowalskiego”),
                # a nie zaczynać od zera. Zmieniony tekst przestaje być „auto”,
                # więc kolejny podgląd go nie nadpisze ani nie zdubluje.
                cb.bind("<Double-Button-1>", lambda e, zz=z: edytuj(zz))
                tk.Button(wiersz, text="✎", command=lambda zz=z: edytuj(zz),
                          bg="#ecf0f1", fg="#2c3e50", relief=tk.FLAT,
                          padx=6, cursor="hand2").pack(side=tk.RIGHT)
                if z.get("zrodlo") == "reczne":
                    tk.Button(wiersz, text="✕", command=lambda zz=z: usun(zz),
                              bg="#ecf0f1", fg="#c0392b", relief=tk.FLAT,
                              padx=6, cursor="hand2").pack(side=tk.RIGHT)
                podpis = []
                if z.get("zrobione") and z.get("zrobil"):
                    podpis.append(f"✓ {z['zrobil']} {z.get('zrobione_kiedy','')}")
                elif z.get("kto"):
                    podpis.append(f"{z['kto']}")
                if podpis:
                    tk.Label(wiersz, text="   ".join(podpis), fg="#95a5a6",
                             font=("Arial", 7)).pack(side=tk.RIGHT, padx=6)

        def usun(z):
            zadania.remove(z)
            subiekt_historia.zapisz_notatke(self.project_id, zadania=zadania)
            self._odswiez_licznik_todo()
            przeladuj()

        def edytuj(z):
            """Zmiana treści zadania w małym oknie (tekst bywa długi)."""
            dlg = tk.Toplevel(okno)
            dlg.title("Edycja zadania")
            dlg.geometry("620x220")
            dlg.transient(okno)
            dlg.bind("<Escape>", lambda e: dlg.destroy())
            tk.Label(dlg, text="Treść zadania:", anchor="w", padx=12, pady=6,
                     font=("Arial", 9, "bold")).pack(fill=tk.X)
            pole = tk.Text(dlg, height=5, wrap="word", font=("Arial", 9))
            pole.pack(fill=tk.BOTH, expand=True, padx=12)
            pole.insert("1.0", z.get("tekst", ""))
            pole.focus_set()

            def ok():
                nowy = pole.get("1.0", tk.END).strip()
                if not nowy:
                    messagebox.showwarning("Edycja", "Treść nie może być pusta.", parent=dlg)
                    return
                if nowy != z.get("tekst"):
                    z["tekst"] = nowy
                    # Zmieniony ręcznie — automat nie ma prawa go nadpisać,
                    # a przy kolejnym podglądzie oryginał wróci jako nowe
                    # zadanie tylko wtedy, gdy problem nadal istnieje.
                    z["zrodlo"] = "reczne"
                    z["kto"] = os.environ.get("USERNAME") or "?"
                    z["kiedy"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    subiekt_historia.zapisz_notatke(self.project_id, zadania=zadania)
                    self._odswiez_licznik_todo()
                dlg.destroy()
                przeladuj()

            pasek = tk.Frame(dlg)
            pasek.pack(fill=tk.X, padx=12, pady=10)
            tk.Button(pasek, text="Zapisz", command=ok, bg="#2c3e50", fg="white",
                      relief=tk.FLAT, font=("Arial", 9, "bold"), padx=18,
                      pady=4, cursor="hand2").pack(side=tk.RIGHT)
            tk.Button(pasek, text="Anuluj", command=dlg.destroy, bg="#95a5a6",
                      fg="white", relief=tk.FLAT, padx=14, pady=4).pack(side=tk.RIGHT, padx=(0, 8))
            wysrodkuj(dlg, okno)
            dlg.grab_set()

        def dodaj(event=None):
            tekst = var_nowe.get().strip()
            if not tekst:
                return
            zadania.append({"tekst": tekst, "zrobione": False, "zrodlo": "reczne",
                            "kto": os.environ.get("USERNAME") or "?",
                            "kiedy": datetime.now().strftime("%Y-%m-%d %H:%M")})
            var_nowe.set("")
            subiekt_historia.zapisz_notatke(self.project_id, zadania=zadania)
            self._odswiez_licznik_todo()
            przeladuj()

        tk.Button(dodaj_ramka, text="➕ Dodaj", command=dodaj, bg="#27ae60", fg="white",
                  relief=tk.FLAT, padx=14, pady=3, cursor="hand2").pack(side=tk.LEFT, padx=(8, 0))
        okno.bind("<Return>", dodaj)

        tk.Label(okno, text="Notatki:", anchor="w", padx=12,
                 font=("Arial", 8, "bold")).pack(side=tk.BOTTOM, fill=tk.X)
        txt = tk.Text(okno, height=4, wrap="word", font=("Arial", 9))
        txt.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 4))
        txt.insert("1.0", dane.get("tekst", ""))

        przeladuj()

        tk.Button(stopka, text="Zapisz i zamknij",
                  command=lambda: (zapisz_stan(), okno.destroy()),
                  bg="#2c3e50", fg="white", relief=tk.FLAT,
                  font=("Arial", 10, "bold"), padx=20, pady=5,
                  cursor="hand2").pack(side=tk.RIGHT)
        tk.Label(stopka, text="Zmiany zapisują się od razu; notatki przy zamknięciu.",
                 fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.LEFT)

        wysrodkuj(okno, self)

    def _kopiuj_poza_bom(self, okno):
        # TSV z nagłówkiem — do wklejenia wprost w Excel i porównania z arkuszem.
        nazwy_rodzicow = {it["nr"].upper(): (it.get("nazwa") or "")
                          for it in (self.items or [])}
        linie = ["Komplet\tNazwa kompletu\tSkładnik\tPrzyczyna\tNazwa składnika"]
        for rodzic in sorted(self.poza_bom):
            nazwa_r = nazwy_rodzicow.get(rodzic.upper(), "")
            for numer, powod, nazwa in sorted(self.poza_bom[rodzic]):
                linie.append(f"{rodzic}\t{nazwa_r}\t{numer}\t{powod}\t{nazwa}")
        okno.clipboard_clear()
        okno.clipboard_append("\n".join(linie))

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

        self._podswietl_tryb(tryb)
        self._odswiez_znaczniki()

    def _podswietl_tryb(self, tryb):
        """Wyróżnia aktywny przycisk trybu.

        Wszystkie trzy wyglądały identycznie, więc nie było widać, który
        jest włączony — przy „pomijasz N" user nie wiedział, skąd to N się
        bierze (zgłoszone 08.09.2026).
        """
        for nazwa, b in getattr(self, "_btn_tryby", {}).items():
            try:
                if nazwa == tryb:
                    b.config(bg="#4a235a", relief=tk.SUNKEN, bd=2,
                             font=("Arial", 8, "bold"))
                else:
                    b.config(bg="#b07cc6", relief=tk.RAISED, bd=1,
                             font=("Arial", 8))
            except tk.TclError:
                pass

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
        pelne = niepelne = puste_biblioteczne = puste_blad = 0
        for p in self.plan["pozycje"]:
            if p["typ"] not in KOMPLETY:
                continue
            if not p["skladniki"]:
                # Bez tego rozróżnienia te pozycje znikały z liczenia (dawny
                # `continue` tu w miejscu) — 27 złożeń, 25 "pełnych", a 2
                # brakujące nie były ani pełne, ani zaraportowane jako błąd.
                if p["symbol"].strip().upper() in self.bib_bez_skladu:
                    puste_biblioteczne += 1
                else:
                    puste_blad += 1
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

        nieprzy = sum(1 for n in self.bib_bez_skladu if n not in self._bib_decyzje)
        self.summary.config(text=(
            f"Pozycji: {len(self.plan['pozycje'])}"
            f"  (złożenia {zloz} · blachy {blachy} · handlowe {handlowe})    "
            f"kartoteki — jest: {jest}, do założenia: {do_zal}"
            + (f" (pomijasz {pominiete})" if pominiete else "")
            + f"    komplety: {pelne} pełnych"
            + (f", {niepelne} niepełnych ⚠" if niepelne else "")
            + (f", {puste_blad} BEZ SKŁADU (błąd danych!) ⛔" if puste_blad else "")
            + (f", {puste_biblioteczne} bibliotecznych bez składu" if puste_biblioteczne else "")
            + (f" [{nieprzy} niepotwierdzone ⛔]" if nieprzy else "")
        ))
        self._odswiez_stan_zapisu()

    def _mozna_zapisac(self):
        """Blokuje zapis TYLKO przy rzeczach, których nie wolno przepuścić cicho.

        Blokują: złożenia biblioteczne bez decyzji usera (powstałby pusty
        komplet) oraz złożenia bez składu nie będące bibliotecznymi (realny
        błąd danych — brak węzła w drzewku).

        NIE blokują: pominięte pozycje. Domyślny tryb „złożenia z zawartością"
        celowo pomija to, co nie wchodzi w skład żadnego złożenia — blokada
        na tym unieruchomiłaby okno w normalnym scenariuszu. Pominięcia są
        widoczne w podsumowaniu i wypisane w oknie potwierdzenia zapisu.
        """
        if not self.plan or not self.dry:
            return False
        # Liczy się PODJĘCIE decyzji, nie jej treść — „pomiń" jest tak samo
        # świadomym wyborem jak „załóż bez składu" (pozycja znika z planu,
        # więc nie ma jej w bib_potwierdzone).
        if any(n not in self._bib_decyzje for n in self.bib_bez_skladu):
            return False
        for p in self.plan["pozycje"]:
            if (p["typ"] in KOMPLETY and not p["skladniki"]
                    and p["symbol"].strip().upper() not in self.bib_bez_skladu):
                return False
        return True

    def _odswiez_stan_zapisu(self):
        """Włącza/wyłącza zapis i MÓWI DLACZEGO — szary przycisk bez powodu
        jest gorszy niż brak blokady (user nie wie, co ma zrobić)."""
        mozna = self._mozna_zapisac()
        nieprzy = [n for n in self.bib_bez_skladu if n not in self._bib_decyzje]
        blad = [p["symbol"] for p in (self.plan or {}).get("pozycje", [])
                if p["typ"] in KOMPLETY and not p["skladniki"]
                and p["symbol"].strip().upper() not in self.bib_bez_skladu]

        # Sam przycisk mówi, CZEGO brakuje. Szary „Zapisz do Subiekta" bez
        # słowa wyjaśnienia user po prostu klika i dziwi się, że nic się nie
        # dzieje — a pasek statusu na samym dole łatwo przeoczyć
        # (zgłoszone 08.09.2026: „jak zrobić, żeby user nie przegapił decyzji").
        if mozna:
            self.btn_write.config(state=tk.NORMAL, text="💾 Zapisz do Subiekta",
                                  bg="#e67e22")
        elif nieprzy:
            self.btn_write.config(state=tk.DISABLED, bg="#95a5a6",
                                  text=f"⛔ Najpierw decyzje ({len(nieprzy)})")
        elif blad:
            self.btn_write.config(state=tk.DISABLED, bg="#95a5a6",
                                  text=f"⛔ Popraw drzewko ({len(blad)})")
        else:
            self.btn_write.config(state=tk.DISABLED, bg="#95a5a6",
                                  text="💾 Zapisz do Subiekta")

        # Przycisk powrotu do decyzji — okno nie wyskakuje już samo przy każdym
        # podglądzie, więc musi być jak do niego wrócić.
        try:
            if nieprzy:
                self.btn_bib.config(text=f"⛔ Decyzje ({len(nieprzy)})", state=tk.NORMAL)
                self.btn_bib.pack(side=tk.RIGHT, padx=(0, 4), pady=8)
                self._migaj_decyzje()
            else:
                self.btn_bib.pack_forget()
        except (AttributeError, tk.TclError):
            pass

        # Pasek TUŻ NAD przyciskiem zapisu — tam patrzy oko, gdy chce zapisać.
        try:
            if nieprzy:
                self.pasek_blokady.config(
                    text=f"⛔ {len(nieprzy)} złożeń bibliotecznych czeka na decyzję "
                         f"({', '.join(sorted(nieprzy)[:3])}{'…' if len(nieprzy) > 3 else ''})"
                         "  —  kliknij „⛔ Decyzje” na górnej belce",
                    bg="#c0392b")
                self.pasek_blokady.pack(side=tk.BOTTOM, fill=tk.X, before=self.status)
            elif blad:
                self.pasek_blokady.config(
                    text=f"⛔ {len(blad)} złożeń Z/ZZ nie ma ŻADNEGO składnika w drzewku "
                         f"({', '.join(sorted(blad)[:3])}{'…' if len(blad) > 3 else ''})"
                         "  —  popraw *_OUT.xlsx albo ukryj te pozycje w arkuszu",
                    bg="#c0392b")
                self.pasek_blokady.pack(side=tk.BOTTOM, fill=tk.X, before=self.status)
            else:
                self.pasek_blokady.pack_forget()
        except (AttributeError, tk.TclError):
            pass

    def _migaj_decyzje(self, ile=6):
        """Kilka mrugnięć przyciskiem decyzji — przyciąga wzrok bez zabierania
        fokusu (modalne okno robiło to kosztem wypchnięcia arkusza na wierzch).
        Miga tylko po zmianie stanu, nie w kółko — irytujący element user
        nauczy się ignorować."""
        if getattr(self, "_miga", False):
            return
        self._miga = True

        def krok(n):
            try:
                if n <= 0 or not self.btn_bib.winfo_ismapped():
                    self.btn_bib.config(bg="#c0392b")
                    self._miga = False
                    return
                self.btn_bib.config(bg="#e74c3c" if n % 2 else "#7b241c")
                self.after(280, lambda: krok(n - 1))
            except tk.TclError:
                self._miga = False

        krok(ile)

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
                self._na_wierzch()
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
            # BRAK KARTOTEKI MA PIERWSZEŃSTWO nad „to złożenie”. Wcześniej
            # Z/ZZ zawsze dostawało niebieski, więc złożenie bez kartoteki
            # wyglądało identycznie jak z kartoteką — a to właśnie ono wymaga
            # zaznaczenia, żeby komplet w ogóle powstał (07.09.2026).
            # Kolor ma mówić „co zrobić", a dopiero potem „czym to jest";
            # rodzaj widać i tak w kolumnie Typ oraz po drzewku.
            kart = status.get("kartoteka", {}).get(p["symbol"].upper())
            if kart and kart["Status"] == "istnieje":
                return "komplet" if p["typ"] in KOMPLETY else "istnieje"
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

        # Ostatnia bariera — przycisk bywa wyszarzony, ale gdyby stan zdążył
        # się rozjechać (np. „Przelicz" wykrył nowe pozycje), zapis nie może
        # przejść bez decyzji. Zamiast samego „nie da się" prowadzimy wprost
        # do okna, w którym się ją podejmuje.
        czekaja = [n for n in self.bib_bez_skladu if n not in self._bib_decyzje]
        if czekaja:
            messagebox.showwarning(
                "Najpierw decyzje",
                f"{len(czekaja)} złożeń bibliotecznych czeka na decyzję:\n\n   "
                + "\n   ".join(sorted(czekaja))
                + "\n\nBez niej powstałby PUSTY komplet — kartoteka rodzaju Komplet\n"
                  "bez składu, z której magazynier nic nie złoży.\n\n"
                  "Za chwilę otworzę okno decyzji.",
                parent=self)
            self._na_wierzch()
            self._pokaz_biblioteczne()
            return

        podmiot = self.var_podmiot.get().strip()
        if not podmiot:
            messagebox.showwarning("Subiekt", "Podaj podmiot na ZK.", parent=self)
            self._na_wierzch()
            return

        plan = self._plan_do_zapisu()
        nowe = len(self.wybrane)
        pominiete = len(self._do_zalozenia()) - nowe

        # Komplety NOWE vs AKTUALIZOWANE — most rozróżnia to w suchym przebiegu
        # (do-utworzenia / do-aktualizacji). Bez tego rozdzielenia okno pisało
        # „TRWALE powstaną komplety: 25" także przy ponownym zakładaniu tego
        # samego projektu, gdzie wszystkie 25 już istniały i były tylko
        # nadpisywane (zgłoszone 08.09.2026).
        w_planie = {p["symbol"].strip().upper() for p in plan["pozycje"]}
        kompl = kompl_akt = kompl_bez_zmian = 0
        for k in (self.dry or {}).get("kroki", []):
            if k.get("Rodzaj") != "komplet":
                continue
            if (k.get("Symbol") or "").strip().upper() not in w_planie:
                continue          # pozycja wypadła z planu (np. „pomiń")
            st = k.get("Status")
            if st == "do-aktualizacji":
                kompl_akt += 1
            elif st == "bez-zmian":
                # Skład identyczny — zapis go przepisze, ale wynik będzie ten
                # sam. Liczymy osobno, żeby nie straszyć „25 aktualizacji",
                # gdy realnie zmienią się dwie (zgłoszone 08.09.2026).
                kompl_bez_zmian += 1
            elif str(st or "").startswith("do-utworzenia"):
                kompl += 1

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
        #
        # Trwałe (kartoteki, komplety) i odwracalne (ZK) są rozdzielone, bo
        # wcześniej lista zaczynała się od „Powstanie: kartoteki 0, komplety 0"
        # i brzmiała jak „nic się nie stanie", choć niżej zapowiadała ZK na
        # 81 pozycji (zgłoszone 06.09.2026). Gdy nic trwałego nie powstaje,
        # mówimy to wprost zamiast wypisywać zera.
        trwale = []
        if nowe:
            trwale.append(f"  • kartoteki: {nowe}")
        if kompl:
            trwale.append(f"  • komplety (Z/ZZ): {kompl}")

        if trwale:
            czesc_trwala = (
                "TRWALE (w Subiekcie zostaną — nie da się ich łatwo usunąć):\n"
                + "\n".join(trwale) + "\n\n")
        else:
            czesc_trwala = "Żadna NOWA kartoteka ani komplet nie powstanie.\n\n"

        # Aktualizacja istniejących kompletów to co innego niż zakładanie —
        # user musi wiedzieć, że nadpisuje skład, który już tam jest.
        if kompl_akt:
            czesc_trwala += (
                f"ZMIENI SKŁAD {kompl_akt} istniejących kompletów (Z/ZZ) — "
                "skład z BOM-u różni się od tego w Subiekcie.\n\n")
        if kompl_bez_zmian:
            czesc_trwala += (
                f"{kompl_bez_zmian} kompletów ma JUŻ identyczny skład — zapis ich nie zmieni.\n\n")

        uwagi = []
        # Brak drzewka jest najważniejszy: bez niego NIE POWSTANIE ŻADEN
        # komplet, choć pozycje Z/ZZ są w projekcie i wyglądają na gotowe.
        zzz = sum(1 for p in plan["pozycje"] if p["typ"] in KOMPLETY)
        if getattr(self, "brak_drzewka", None) and zzz:
            uwagi.append(f"BRAK DRZEWKA — {self.brak_drzewka}.\n"
                         f"   Żaden z {zzz} kompletów (Z/ZZ) nie powstanie — nie wiadomo,\n"
                         f"   co ma w sobie zawierać. Powstaną same kartoteki.")
        if pominiete:
            uwagi.append(f"Pomijasz {pominiete} pozycji bez kartoteki — nie trafią na ZK.")
        ile_poza = sum(len(v) for v in getattr(self, "poza_bom", {}).values())
        if ile_poza:
            uwagi.append(f"{ile_poza} składników z drzewka nie ma w BOM-ie — "
                         "komplety powstaną niepełne.")

        # Które komplety wyjdą NIEPEŁNE przez pominięcie ich składników.
        # Sama liczba pominiętych tego nie pokazuje: pominięta blacha wygląda
        # niewinnie, dopóki nie wiadomo, że przez nią złożenie pojedzie do
        # Subiekta bez części składu (zgłoszone 07.09.2026 — nic nie może
        # przejść po cichu). Liczone na planie PO filtrowaniu, czyli na tym,
        # co realnie poleci do mostu.
        oberwane = []
        pelny_sklad = {p["symbol"].strip().upper(): len(p["skladniki"])
                       for p in self.plan["pozycje"] if p["typ"] in KOMPLETY}
        for p in plan["pozycje"]:
            if p["typ"] not in KOMPLETY:
                continue
            bylo = pelny_sklad.get(p["symbol"].strip().upper(), 0)
            if bylo and len(p["skladniki"]) < bylo:
                oberwane.append(f"{p['symbol']} ({len(p['skladniki'])} z {bylo})")
        if oberwane:
            uwagi.append("NIEPEŁNE komplety przez pominięte składniki:\n   "
                         + "\n   ".join(oberwane[:8])
                         + (f"\n   … i {len(oberwane) - 8} więcej" if len(oberwane) > 8 else ""))

        # Złożenia biblioteczne, dla których user wybrał „załóż bez składu" —
        # w Subiekcie powstaną jako ZWYKŁE kartoteki, nie komplety.
        bez_skladu = [n for n, d in getattr(self, "_bib_decyzje", {}).items() if d == "bez_skladu"]
        if bez_skladu:
            uwagi.append("Złożenia biblioteczne bez składu (Twoja decyzja) —\n"
                         "   powstaną jako zwykłe kartoteki, magazynier kompletuje ręcznie:\n   "
                         + ", ".join(sorted(bez_skladu)))

        # Szczegóły do tabeli: co dokładnie powstanie i co zostanie nadpisane.
        # Same liczby („komplety: 25") nie mówiły, KTÓRE i CZYM — przy zapisie
        # na produkcję to za mało (zgłoszone 08.09.2026).
        w_planie = {p["symbol"].strip().upper() for p in plan["pozycje"]}
        nazwy = {p["symbol"].strip().upper(): p.get("nazwa") or "" for p in plan["pozycje"]}
        wiersze = []
        for k in (self.dry or {}).get("kroki", []):
            sym = (k.get("Symbol") or "").strip()
            if sym.upper() not in w_planie:
                continue
            st = k.get("Status") or ""
            if k.get("Rodzaj") == "kartoteka" and st == "do-zalozenia":
                if sym.upper() in self.wybrane:
                    wiersze.append(("NOWA KARTOTEKA", sym, nazwy.get(sym.upper(), ""), ""))
            elif k.get("Rodzaj") == "komplet":
                if st == "do-aktualizacji":
                    wiersze.append(("ZMIENIA SKŁAD", sym, nazwy.get(sym.upper(), ""),
                                    k.get("Szczegoly") or ""))
                elif st == "bez-zmian":
                    wiersze.append(("bez zmian", sym, nazwy.get(sym.upper(), ""),
                                    k.get("Szczegoly") or ""))
                elif st.startswith("do-utworzenia"):
                    wiersze.append(("NOWY KOMPLET", sym, nazwy.get(sym.upper(), ""),
                                    k.get("Szczegoly") or ""))
        for n in sorted(bez_skladu):
            wiersze.append(("BIBLIOTECZNE bez składu", n, self.bib_bez_skladu.get(n, ""),
                            "powstanie jako zwykła kartoteka"))

        # Najpierw to, co się realnie zmienia; „bez zmian" na koniec — inaczej
        # dwie istotne zmiany giną wśród dwudziestu trzech nieistotnych wierszy.
        waga = {"NOWA KARTOTEKA": 0, "NOWY KOMPLET": 1, "ZMIENIA SKŁAD": 2,
                "BIBLIOTECZNE bez składu": 3, "bez zmian": 9}
        wiersze.sort(key=lambda w: (waga.get(w[0], 5), w[1]))

        ok = self._potwierdz_zapis(czesc_trwala, opis_zk, uwagi, wiersze,
                                   nowe, kompl, kompl_akt, kompl_bez_zmian)
        self._na_wierzch()
        if not ok:
            return

        self.btn_write.config(state=tk.DISABLED)
        self.btn_refresh.config(state=tk.DISABLED)
        self.status.config(text="Zapisuję do Subiekta — nie zamykaj okna…")
        threading.Thread(target=self._write_worker, daemon=True).start()

    def _potwierdz_zapis(self, czesc_trwala, opis_zk, uwagi, wiersze,
                         nowe, kompl, kompl_akt, kompl_bez_zmian=0):
        """Potwierdzenie zapisu z TABELĄ — co dokładnie powstanie i co zostanie
        nadpisane, pozycja po pozycji.

        Wąski messagebox pokazywał tylko liczby („komplety: 25"), z których nie
        dało się wyczytać ani KTÓRE to komplety, ani że 25 z nich już istnieje
        i zostanie nadpisanych (zgłoszone 08.09.2026).
        """
        okno = tk.Toplevel(self)
        okno.title("Zapis do Subiekta — potwierdzenie")
        # Rozmiar startowy dopasowany do liczby wierszy, ale okno JEST
        # rozciągalne — przy dużym projekcie 12 widocznych wierszy to za mało,
        # żeby ocenić zapis (zgłoszone 08.09.2026).
        wys = max(600, min(900, 380 + 22 * len(wiersze)))
        okno.geometry(f"1000x{wys}")
        okno.minsize(760, 480)
        okno.resizable(True, True)
        okno.transient(self)
        wynik = {"ok": False}

        naglowek = tk.Frame(okno, bg="#c0392b")
        naglowek.pack(fill=tk.X)
        tk.Label(naglowek, text="BAZA PRODUKCYJNA — sprawdź, zanim zapiszesz",
                 bg="#c0392b", fg="white", font=("Arial", 12, "bold"),
                 anchor="w", padx=12, pady=8).pack(fill=tk.X)

        # Nagłówki liczbowe DUŻYMI literami — od razu widać skalę operacji.
        pasek = tk.Frame(okno, bg="#ecf0f1")
        pasek.pack(fill=tk.X)
        for tekst, liczba, kolor in (
            ("NOWE KARTOTEKI", nowe, "#27ae60"),
            ("NOWE KOMPLETY", kompl, "#27ae60"),
            ("ZMIENIĄ SKŁAD", kompl_akt, "#d35400"),
            ("BEZ ZMIAN", kompl_bez_zmian, "#95a5a6"),
        ):
            if not liczba:
                continue
            kafel = tk.Frame(pasek, bg="#ecf0f1", padx=16, pady=8)
            kafel.pack(side=tk.LEFT)
            tk.Label(kafel, text=str(liczba), bg="#ecf0f1", fg=kolor,
                     font=("Arial", 20, "bold")).pack()
            tk.Label(kafel, text=tekst, bg="#ecf0f1", fg="#2c3e50",
                     font=("Arial", 8, "bold")).pack()

        tk.Label(okno, text=opis_zk.strip() or "ZK: —", justify="left", anchor="w",
                 padx=12, pady=6, font=("Arial", 9)).pack(fill=tk.X)

        # Filtr: przy 25 kompletach dwie realne zmiany toną wśród 23 wierszy
        # „bez zmian". Domyślnie WŁĄCZONY, gdy jest co ukrywać.
        ile_bez_zmian = sum(1 for w in wiersze if w[0] == "bez zmian")
        pasek_f = tk.Frame(okno)
        pasek_f.pack(fill=tk.X, padx=12)
        var_tylko = tk.BooleanVar(value=bool(ile_bez_zmian))
        if ile_bez_zmian:
            tk.Checkbutton(pasek_f, variable=var_tylko,
                           text=f"Pokaż tylko zmiany (ukryj {ile_bez_zmian} bez zmian)",
                           command=lambda: przeladuj()).pack(side=tk.LEFT)

        # ── TABELA ────────────────────────────────────────────────────────
        ramka = tk.Frame(okno)
        ramka.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 6))
        kol = ("co", "symbol", "nazwa", "szczegoly")
        tab = ttk.Treeview(ramka, columns=kol, show="headings", height=12)
        for c, tekst, szer in (("co", "Co się stanie", 165), ("symbol", "Symbol", 135),
                               ("nazwa", "Nazwa", 210), ("szczegoly", "Co się zmienia", 370)):
            tab.heading(c, text=tekst)
            tab.column(c, width=szer, anchor="w")
        vs = ttk.Scrollbar(ramka, orient="vertical", command=tab.yview)
        tab.configure(yscrollcommand=vs.set)
        tab.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)

        tab.tag_configure("nowe", background="#d5f5e3")
        tab.tag_configure("akt", background="#fdebd0")
        tab.tag_configure("bib", background="#fadbd8")
        tab.tag_configure("nic", foreground="#95a5a6")   # bez tła — to nie jest zmiana

        def przeladuj():
            tab.delete(*tab.get_children())
            for co, sym, nazwa, szcz in wiersze:
                if co == "bez zmian":
                    if var_tylko.get():
                        continue
                    tag = "nic"
                elif "ZMIENIA" in co:
                    tag = "akt"
                elif "BIBLIOTECZNE" in co:
                    tag = "bib"
                else:
                    tag = "nowe"
                tab.insert("", "end", values=(co, sym, nazwa, szcz), tags=(tag,))
            # Widok startuje na GÓRZE — tam są zmiany po sortowaniu.
            dzieci = tab.get_children()
            if dzieci:
                tab.see(dzieci[0])

        przeladuj()

        if uwagi:
            tk.Label(okno, text="⚠ " + "\n⚠ ".join(uwagi), justify="left", anchor="w",
                     padx=12, pady=6, fg="#c0392b", font=("Arial", 9),
                     wraplength=860).pack(fill=tk.X)

        # Opis trwałości NAD przyciskami, nie obok — obok wypychał przycisk
        # „ZAPISZ" poza krawędź okna (zgłoszone 08.09.2026).
        tk.Label(okno, text=czesc_trwala.strip(), justify="left", anchor="w",
                 fg="#7f8c8d", font=("Arial", 8), padx=12,
                 wraplength=860).pack(fill=tk.X)

        stopka = tk.Frame(okno)
        stopka.pack(fill=tk.X, padx=12, pady=10)

        def tak():
            wynik["ok"] = True
            okno.destroy()

        tk.Button(stopka, text="Nie, wróć", command=okno.destroy, bg="#95a5a6", fg="white",
                  relief=tk.FLAT, padx=20, pady=6).pack(side=tk.RIGHT, padx=(8, 0))
        tk.Button(stopka, text="ZAPISZ do Subiekta", command=tak, bg="#c0392b", fg="white",
                  relief=tk.FLAT, font=("Arial", 10, "bold"), padx=24, pady=6,
                  cursor="hand2").pack(side=tk.RIGHT)

        wysrodkuj(okno, self)
        okno.grab_set()
        self.wait_window(okno)
        return wynik["ok"]

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
            self._na_wierzch()
            self.btn_write.config(state=tk.NORMAL)
            return

        kroki = wynik.get("kroki", [])
        zal = sum(1 for k in kroki if k["Status"] == "zalozona")
        kom = sum(1 for k in kroki if k["Rodzaj"] == "komplet" and k["Status"].startswith("utworzony"))
        bledy = [k for k in kroki if k["Status"] == "blad"]
        zk = wynik.get("zk")
        log = save_log(self.project_id, wynik, plan=self._plan_do_zapisu())
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
        self._na_wierzch()         # inaczej arkusz główny przykryje to okno
        self._dry_run_async()      # odśwież — pokaże już założone kartoteki jako istniejące


def open_window(parent, project_id, project_name=None):
    """Punkt wejścia dla RM_BAZA."""
    if not project_id:
        messagebox.showwarning("Subiekt", "Najpierw wybierz projekt.", parent=parent)
        return None
    return SubiektProjektWindow(parent, project_id, project_name)


# ── Cofnięcie projektu ───────────────────────────────────────────────────────
# Osobne okno, nie przycisk w SubiektProjektWindow: to okno ma sens dopiero
# PO tym, jak sesja zakładania już dawno się skończyła — "self.plan" wtedy
# nie istnieje. Źródłem prawdy jest log z tabeli "plan" (save_log), zapisany
# przy każdym udanym zapisie — dokładnie ten sam plan.json, którego użył
# most do założenia, więc ProjektCofnij.cs wie, co ma szukać i w jakiej
# kolejności usuwać (ZK → komplety od góry → kartoteki).
class SubiektProjektCofnijWindow(tk.Toplevel, Kreciolek):
    def __init__(self, parent, project_id, project_name=None):
        tk.Toplevel.__init__(self, parent)
        Kreciolek.__init__(self)
        self.project_id = project_id
        self.project_name = project_name or str(project_id)
        self.title(f"Subiekt — cofnij projekt {self.project_name}")
        self.geometry("720x480")
        self.dry = None
        self.plan = None

        logi = znajdz_logi_projektu(project_id)
        if not logi:
            messagebox.showinfo(
                "Subiekt — cofnij projekt",
                "Brak zapisanego logu zakładania dla tego projektu\n"
                f"(szukane w {LOG_DIR}).\n\n"
                "Bez logu nie wiadomo, jakie symbole i w jakim typie (Z/ZZ/X/XX)\n"
                "zostały założone — cofnięcie nie może zgadywać.",
                parent=self)
            self.after(10, self.destroy)
            return

        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)
        ttk.Label(top, text="Log zakładania:").pack(side=tk.LEFT)
        self.var_log = tk.StringVar()
        etykiety = [f"{os.path.basename(p)} — {len(d['plan'].get('pozycje', []))} poz." for p, d in logi]
        combo = ttk.Combobox(top, textvariable=self.var_log, values=etykiety, state="readonly", width=60)
        combo.current(0)
        combo.pack(side=tk.LEFT, padx=6)
        self._logi = logi

        self.txt = tk.Text(self, wrap="word")
        self.txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.txt.insert("1.0",
            "Wybierz log i kliknij „Sprawdź” — pokaże, co dałoby się usunąć\n"
            "(ZK projektu, komplety, kartoteki), zanim cokolwiek zniknie.\n\n"
            "Subiekt sam odmówi usunięcia czegokolwiek, co ma powiązania spoza\n"
            "tego planu (inny projekt używa tej samej pozycji, coś już wydano) —\n"
            "to nie jest coś, co to okno próbuje przewidzieć, tylko uczciwie\n"
            "zaraportuje po fakcie.")
        self.txt.config(state=tk.DISABLED)

        btns = ttk.Frame(self, padding=8)
        btns.pack(fill=tk.X)
        self.btn_check = ttk.Button(btns, text="Sprawdź (suchy przebieg)", command=self._check)
        self.btn_check.pack(side=tk.LEFT)
        self.btn_go = ttk.Button(btns, text="Usuń w Subiekcie", command=self._confirm, state=tk.DISABLED)
        self.btn_go.pack(side=tk.LEFT, padx=6)
        self.status = ttk.Label(btns, text="")
        self.status.pack(side=tk.LEFT, padx=10)

    def _na_wierzch(self):
        """To samo co w SubiektProjektWindow — przywraca okno po dialogu.

        Ta klasa dziedziczy po tk.Toplevel, nie po SubiektProjektWindow, więc
        nie dostawała tej metody. Efekt był groźny: wywołanie po messageboxie
        potwierdzenia rzucało AttributeError PRZED usuwaniem, więc przycisk
        „Usuń w Subiekcie" nie robił NIC, a okno nie pokazywało żadnego błędu
        (zgłoszone 08.09.2026 — user kliknął, nic się nie usunęło).
        """
        def podnies():
            try:
                self.lift()
                self.focus_force()
            except tk.TclError:
                pass
        try:
            self.after_idle(podnies)
        except tk.TclError:
            pass

    def _opis_pozostalosci(self):
        """Tekst o dokumentach do RĘCZNEGO usunięcia — z powodem, dlaczego zostają."""
        try:
            reszta = dokumenty_do_recznego_usuniecia(self.plan or {})
        except Exception:
            return ""
        if not reszta:
            return ""

        linie = ["", "=" * 68,
                 "DO RĘCZNEGO USUNIĘCIA — te dokumenty ZOSTAJĄ:", ""]
        for numer, rodzaj, nasze, razem, podmiot in reszta:
            czyje = f"{nasze} z {razem} poz. tego projektu"
            linie.append(f"   {numer:<24} {czyje:<28} {podmiot}")
        linie += [
            "",
            "DLACZEGO ZOSTAJĄ:",
            "   Cofanie usuwa tylko to, co samo założyło: ZK, komplety i kartoteki.",
            "   ZD/RW/WZ powstają później, osobną decyzją (zakup, wydanie na produkcję),",
            "   i NIE mają numeru projektu w dokumencie — powiązanie z projektem liczy",
            "   RM_BAZA z BOM-u. Jedno ZD potrafi zbierać pozycje z kilku projektów naraz,",
            "   więc automat mógłby skasować cudze zamówienie.",
            "",
            "GDZIE JE USUNĄĆ:",
            "   ZD → okno Zamówienia do dostawców → przycisk 🗑 Usuń ZD",
            "        (albo PPM na wierszu → Usuń zamówienia (ZD)…)",
            "   RW/WZ → okno Przegląd dokumentów",
            "",
            "   ⚠ Kolejność: najpierw ZD, potem ZK — odwrotnie Subiekt potrafi",
            "     odmówić skasowania ZK powiązanego z zamówieniem do dostawcy.",
            "=" * 68]
        return "\n".join(linie)

    def _wybrany_plan(self):
        idx = 0
        try:
            idx = [f"{os.path.basename(p)} — {len(d['plan'].get('pozycje', []))} poz." for p, d in self._logi].index(self.var_log.get())
        except ValueError:
            pass
        return self._logi[idx][1]["plan"]

    def _pokaz(self, tekst):
        self.txt.config(state=tk.NORMAL)
        self.txt.delete("1.0", tk.END)
        self.txt.insert("1.0", tekst)
        self.txt.config(state=tk.DISABLED)

    def _check(self):
        self.plan = self._wybrany_plan()
        self.btn_check.config(state=tk.DISABLED)
        self.status.config(text="Sprawdzam…")
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self):
        try:
            wynik = run_bridge(self.plan, zapisz=False, tryb="projekt-cofnij")
            self.after(0, lambda: self._check_done(wynik, None))
        except Exception as e:
            self.after(0, lambda: self._check_done(None, str(e)))

    def _check_done(self, wynik, error):
        self.btn_check.config(state=tk.NORMAL)
        if error:
            self.status.config(text="Błąd.")
            messagebox.showerror("Subiekt", error, parent=self)
            self._na_wierzch()
            return
        self.dry = wynik
        kroki = wynik.get("kroki", [])
        linie = [f"  {k['Rodzaj']:10} {k['Symbol']:24} {k['Status']}" for k in kroki]
        do_usun = sum(1 for k in kroki if k["Status"] == "do-usuniecia")
        brak = sum(1 for k in kroki if k["Status"] == "brak")
        self._pokaz(f"Do usunięcia: {do_usun}   Nie znaleziono: {brak}\n\n"
                    + "\n".join(linie) + self._opis_pozostalosci())
        self.status.config(text=f"Do usunięcia: {do_usun}")
        self.btn_go.config(state=tk.NORMAL if do_usun else tk.DISABLED)

    def _confirm(self):
        do_usun = sum(1 for k in (self.dry or {}).get("kroki", []) if k["Status"] == "do-usuniecia")
        ok = messagebox.askyesno(
            "Subiekt — potwierdzenie",
            f"Baza PRODUKCYJNA.\n\nUsunąć {do_usun} obiektów (ZK, komplety, kartoteki)\n"
            f"projektu {self.project_name}?\n\n"
            "Subiekt odmówi tego, co ma powiązania spoza tego planu —\n"
            "to zostanie i raport pokaże dlaczego.",
            parent=self, icon="warning")
        self._na_wierzch()
        if not ok:
            return
        self.btn_go.config(state=tk.DISABLED)
        self.status.config(text="Usuwam — nie zamykaj okna…")
        threading.Thread(target=self._go_worker, daemon=True).start()

    def _go_worker(self):
        try:
            wynik = run_bridge(self.plan, zapisz=True, tryb="projekt-cofnij")
            self.after(0, lambda: self._go_done(wynik, None))
        except Exception as e:
            self.after(0, lambda: self._go_done(None, str(e)))

    def _go_done(self, wynik, error):
        if error:
            self.status.config(text="Usuwanie nieudane.")
            messagebox.showerror("Subiekt — cofnięcie", error, parent=self)
            self._na_wierzch()
            self.btn_go.config(state=tk.NORMAL)
            return
        kroki = wynik.get("kroki", [])
        usuniete = sum(1 for k in kroki if k["Status"] in ("usuniete", "usunieta"))
        bledy = [k for k in kroki if k["Status"] == "blad"]
        linie = [f"  {k['Rodzaj']:10} {k['Symbol']:24} {k['Status']:12} {k.get('Szczegoly') or ''}" for k in kroki]
        # Pozostałości liczone PO usunięciu — ZK już nie ma, więc lista pokazuje
        # dokładnie to, co realnie zostało do ręcznej roboty.
        try:
            reszta = dokumenty_do_recznego_usuniecia(self.plan or {})
        except Exception:
            reszta = []
        self._pokaz(f"Usunięto: {usuniete}   Błędów: {len(bledy)}\n\n"
                    + "\n".join(linie) + self._opis_pozostalosci())
        self.status.config(text=f"Usunięto {usuniete}."
                           + (f"   ⚠ {len(bledy)} błędów" if bledy else "")
                           + (f"   ⚠ zostało {len(reszta)} dokumentów do ręcznego usunięcia" if reszta else ""))
        self._raport_koncowy(usuniete, bledy, reszta)
        self._na_wierzch()

    def _raport_koncowy(self, usuniete, bledy, reszta):
        """Raport po cofnięciu — to, co WYMAGA UWAGI, na wierzchu i w całości.

        Wcześniej wszystko szło do pola tekstowego pod listą 194 wierszy:
        żeby zobaczyć 16 błędów i wiszące ZD trzeba było przewinąć na sam dół,
        więc user by to przegapił (zgłoszone 08.09.2026). Teraz najpierw
        podsumowanie w kolorowych panelach, a surowa lista zostaje w oknie
        pod spodem do wglądu.
        """
        okno = tk.Toplevel(self)
        okno.title("Cofnięcie zakończone")
        okno.geometry("860x560")
        okno.minsize(700, 400)
        okno.transient(self)
        okno.protocol("WM_DELETE_WINDOW", okno.destroy)
        okno.bind("<Escape>", lambda e: okno.destroy())

        czy_uwaga = bool(bledy or reszta)
        tlo = "#c0392b" if czy_uwaga else "#27ae60"
        naglowek = tk.Frame(okno, bg=tlo)
        naglowek.pack(fill=tk.X)
        tk.Label(naglowek,
                 text=("⚠ COFNIĘTO — ale zostało coś do zrobienia ręcznie"
                       if czy_uwaga else "✓ COFNIĘTO — wszystko usunięte"),
                 bg=tlo, fg="white", font=("Arial", 12, "bold"),
                 anchor="w", padx=14, pady=10).pack(fill=tk.X)

        pasek = tk.Frame(okno, bg="#ecf0f1")
        pasek.pack(fill=tk.X)
        for tekst, liczba, kolor in (("USUNIĘTO", usuniete, "#27ae60"),
                                     ("NIE DA SIĘ USUNĄĆ", len(bledy), "#c0392b"),
                                     ("DOKUMENTY DO RĘCZNEGO USUNIĘCIA", len(reszta), "#d35400")):
            if not liczba:
                continue
            kafel = tk.Frame(pasek, bg="#ecf0f1", padx=18, pady=8)
            kafel.pack(side=tk.LEFT)
            tk.Label(kafel, text=str(liczba), bg="#ecf0f1", fg=kolor,
                     font=("Arial", 22, "bold")).pack()
            tk.Label(kafel, text=tekst, bg="#ecf0f1", fg="#2c3e50",
                     font=("Arial", 8, "bold")).pack()

        tresc = tk.Frame(okno)
        tresc.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)
        txt = tk.Text(tresc, wrap="word", font=("Consolas", 9), bg="#fdfefe",
                      relief=tk.FLAT, padx=8, pady=6)
        vs = ttk.Scrollbar(tresc, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=vs.set)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)

        txt.tag_configure("h", font=("Arial", 10, "bold"), foreground="#c0392b",
                          spacing1=8, spacing3=4)
        txt.tag_configure("h2", font=("Arial", 9, "bold"), foreground="#2c3e50",
                          spacing1=8, spacing3=2)
        txt.tag_configure("poz", foreground="#c0392b")
        txt.tag_configure("info", foreground="#555555")

        if reszta:
            txt.insert("end", f"DOKUMENTY DO RĘCZNEGO USUNIĘCIA ({len(reszta)})\n", "h")
            for numer, rodzaj, nasze, razem, podmiot in reszta:
                txt.insert("end", f"   {numer}   —   {nasze} z {razem} poz. tego projektu"
                                  + (f"   ({podmiot})" if podmiot else "") + "\n", "poz")
            txt.insert("end", "\nDlaczego zostają\n", "h2")
            txt.insert("end",
                       "Cofanie usuwa tylko to, co samo założyło: ZK, komplety i kartoteki.\n"
                       "ZD/RW/WZ powstają później, osobną decyzją (zakup, wydanie na produkcję),\n"
                       "i nie mają numeru projektu w dokumencie — powiązanie z projektem liczy\n"
                       "RM_BAZA z BOM-u. Jedno ZD potrafi zbierać pozycje z kilku projektów\n"
                       "naraz, więc automat mógłby skasować cudze zamówienie.\n", "info")
            txt.insert("end", "\nGdzie je usunąć\n", "h2")
            txt.insert("end",
                       "   ZD      →  okno „Zamówienia do dostawców” →  przycisk 🗑 Usuń ZD\n"
                       "   RW / WZ →  okno „Przegląd dokumentów”\n\n"
                       "   Kolejność: najpierw ZD, potem ZK — odwrotnie Subiekt potrafi\n"
                       "   odmówić skasowania ZK powiązanego z zamówieniem do dostawcy.\n", "info")

        if bledy:
            txt.insert("end", f"\nSUBIEKT ODMÓWIŁ USUNIĘCIA ({len(bledy)})\n", "h")
            for b in bledy:
                txt.insert("end", f"   {b['Symbol']}\n", "poz")
            txt.insert("end", "\nDlaczego\n", "h2")
            txt.insert("end",
                       "Te kartoteki są użyte na dokumencie, mają stan magazynowy albo\n"
                       "wchodzą w skład kompletu spoza tego projektu. To zabezpieczenie\n"
                       "Subiekta — usunięcie rozspójniłoby dokumenty, które je wymieniają.\n"
                       "Zwykle znikną po usunięciu dokumentów wypisanych wyżej; jeśli\n"
                       "używa ich inny projekt, mają zostać.\n", "info")

        if not czy_uwaga:
            txt.insert("end", "\nWszystko, co ten projekt założył w Subiekcie, zostało usunięte.\n", "info")

        txt.config(state="disabled")

        stopka = tk.Frame(okno)
        stopka.pack(fill=tk.X, padx=12, pady=10)
        if reszta:
            tk.Button(stopka, text="Otwórz Zamówienia do dostawców",
                      command=lambda: self._otworz_zamowienia(okno),
                      bg="#d35400", fg="white", relief=tk.FLAT,
                      padx=16, pady=5, cursor="hand2").pack(side=tk.LEFT)
        tk.Button(stopka, text="Zamknij", command=okno.destroy,
                  bg="#2c3e50", fg="white", relief=tk.FLAT,
                  font=("Arial", 10, "bold"), padx=24, pady=5,
                  cursor="hand2").pack(side=tk.RIGHT)

        wysrodkuj(okno, self)
        okno.grab_set()

    def _otworz_zamowienia(self, okno=None):
        """Skrót do okna, w którym usuwa się ZD — żeby nie szukać go w menu."""
        if okno is not None:
            okno.destroy()
        arkusz = self.master
        metoda = getattr(arkusz, "open_subiekt_zamowienia", None)
        if metoda is None:
            messagebox.showinfo("Subiekt",
                                "Otwórz okno „Zamówienia do dostawców” z menu SUBIEKT.",
                                parent=self)
            return
        try:
            metoda()
        except Exception as e:
            messagebox.showerror("Subiekt", str(e), parent=self)


def dokumenty_do_recznego_usuniecia(plan, limit=300):
    """Dokumenty, których „projekt-cofnij" NIE rusza, a zawierają pozycje projektu.

    Tryb usuwa tylko to, co sam założył: ZK + komplety + kartoteki z planu.
    ZD/RW/WZ powstają PÓŹNIEJ, osobnymi decyzjami (zakup, wydanie na produkcję)
    i nie mają numeru projektu w dokumencie — sprawdzone 08.09.2026 na
    ZD 1/CENTRALA/2026: Uwagi puste, Tytuł generyczny „Zamówienie do dostawcy".
    Powiązanie z projektem liczy RM_BAZA z BOM-u, nie z Subiekta.

    Automatyczne kasowanie byłoby więc ryzykowne — jedno ZD potrafi zbierać
    pozycje z kilku projektów naraz i automat skasowałby cudze zamówienie.
    Zamiast tego WYPISUJEMY je, żeby nie zostały niezauważone (zgłoszone
    08.09.2026: „usunąłeś, a ZD wisi").

    Zwraca [(numer, rodzaj, ile_pozycji_projektu, ile_pozycji_razem, dostawca)].
    """
    symbole = {p["symbol"].strip().upper() for p in (plan.get("pozycje") or [])}
    if not symbole:
        return []
    try:
        import subiekt_bridge
        dane = subiekt_bridge.call("dokumenty", {"limit": limit}, timeout=TIMEOUT_S)
    except Exception:
        return []

    znalezione = []
    for d in (dane or {}).get("dokumenty", []):
        rodzaj = str(d.get("Rodzaj") or (d.get("Numer") or "").split(" ")[0]).upper()
        if rodzaj == "ZK":
            continue                      # ZK usuwa sam tryb projekt-cofnij
        pozycje = d.get("Pozycje") or []
        nasze = sum(1 for p in pozycje
                    if (p.get("Symbol") or "").strip().upper() in symbole)
        if nasze:
            znalezione.append((d.get("Numer") or "?", rodzaj, nasze, len(pozycje),
                               d.get("Podmiot") or ""))
    return sorted(znalezione)


def open_cofnij_window(parent, project_id, project_name=None):
    """Punkt wejścia dla RM_BAZA — cofnięcie projektu założonego (kiedykolwiek) w Subiekcie."""
    if not project_id:
        messagebox.showwarning("Subiekt", "Najpierw wybierz projekt.", parent=parent)
        return None
    return SubiektProjektCofnijWindow(parent, project_id, project_name)


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 22
    pname = sys.argv[2] if len(sys.argv) > 2 else None
    root = tk.Tk()
    root.withdraw()
    w = open_window(root, pid, pname)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
