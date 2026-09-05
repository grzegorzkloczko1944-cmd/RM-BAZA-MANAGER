# -*- coding: utf-8 -*-
"""
Zamówienia do dostawców (ZD) na podstawie zapotrzebowania z ZK projektów.

    import subiekt_zamowienia
    subiekt_zamowienia.open_window(parent, project_id=36, project_name="2619 ...")

Skąd się biorą dane (SUBIEKT_ZD_I_WYDANIA_PLAN.md, sekcja 2):

    ZK projektu (RM_BAZA już je zakłada)
        ↓  Subiekt sam liczy, czego brakuje
    ZapotrzebowanieNaAsortyment()  → pozycje niepokryte stanem ani zamówieniem
        ↓  zaznaczasz wiersze w arkuszu
    UtworzNaPodstawieZapotrzebowania()  → ZD, osobne dla każdego dostawcy

Arkusz jest na tym samym silniku (tksheet) co arkusz główny RM_BAZA i ma te
same nawyki: filtry nad arkuszem, sortowanie klikiem w nagłówek, zaznaczanie
wierszy, edycja w miejscu (dostawca, ilość).

⚠️ Kolumna Dostawca: Subiekt podpowiada ją z kartoteki, ale w praktyce jest
pusta (sprawdzone 04.09.2026 — 0 z 6 pozycji miało dostawcę), więc domyślnie
wypełniamy ją z BOM-u RM_BAZA. To jedna z rzeczy, których sam Subiekt nie ma.
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
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox

from rm_kreciolek import Kreciolek
from subiekt_stany import (_find_exe, blad_mostu, wysrodkuj, podepnij_szerokosci,
                           jedna_linia as _jedna_linia, CONFIG_PATH, PROJECTS_DIR)

try:
    from tksheet import Sheet
except ImportError:
    Sheet = None

TIMEOUT_S = 300
LOG_DIR = r"C:\RMPAK_CLIENT\subiekt_logi"

FILTR_WSZYSCY = "— wszyscy —"
FILTR_BRAK_DOSTAWCY = "(bez dostawcy)"

# Filtr stanu pozycji. Domyślnie WSZYSTKIE — arkusz nigdy nic sam nie chowa,
# widocznością steruje wyłącznie belka filtrów.
ZD_WSZYSTKIE = "— wszystkie ZD —"
STAN_WSZYSTKIE = "— wszystkie —"
STAN_DO_ZAMOWIENIA = "do zamówienia"
STAN_ZAMOWIONE = "zamówione (ZD)"

# Filtr typu pozycji — nazewnictwo jak w arkuszu głównym („(WSZYSTKO)").
TYP_WSZYSTKO = "(WSZYSTKO)"
TYP_BEZ_TYPU = "(bez typu)"

# Akcje zaznaczania (combobox „Zaznacz:").
ZAZNACZ_ETYKIETA = "(wybierz)"
ZAZNACZ_WIDOCZNE = "widoczne"
ZAZNACZ_NIC = "nic"
ZAZNACZ_ODWROC = "odwróć"


# ── Dane ────────────────────────────────────────────────────────────────────
def pobierz_zapotrzebowanie(timeout=TIMEOUT_S):
    """[{symbol, nazwa, ilosc, jm, dostawca, zk:[...]}] — czego brakuje na ZK.

    Uwaga: to zapotrzebowanie ze WSZYSTKICH otwartych ZK — Sfera nie pozwala
    zawęzić go do jednego dokumentu. Filtr per projekt robimy niżej, po
    Uwagach na ZK (tam RM_BAZA wpisuje numer projektu).
    """
    try:
        import subiekt_bridge
        data = subiekt_bridge.call(
            "zapotrzebowanie", timeout=timeout,
            fallback=lambda: _zapotrzebowanie_cli(timeout))
    except ImportError:
        data = _zapotrzebowanie_cli(timeout)

    pozycje = [{
        "symbol": p.get("Symbol") or "",
        "nazwa_subiekt": p.get("Nazwa") or "",
        "ilosc": float(p.get("Ilosc") or 0),        # ile BRAKUJE (= „kupić")
        "dostepne": float(p.get("Dostepne") or 0),  # stan PO odjęciu rezerwacji
        "zadysponowane": float(p.get("Zadysponowane") or 0),
        "zarezerwowane": float(p.get("Zarezerwowane") or 0),
        "stan_min": float(p.get("StanMinimalny") or 0),
        "stan_opt": float(p.get("StanOptymalny") or 0),
        "jm": p.get("JednostkaMiary") or "szt",
        "dostawca_subiekt": p.get("Dostawca") or "",
        "zk": p.get("Zk") or [],
    } for p in data.get("pozycje", [])]
    # Zamówione: pozycje z ZD „do realizacji". Znikają z zapotrzebowania (są
    # pokryte), więc bez tej listy user nie widzi, co się z nimi stało.
    zamowione = [{
        "symbol": z.get("Symbol") or "",
        "nazwa_subiekt": z.get("Nazwa") or "",
        "ilosc": float(z.get("Ilosc") or 0),
        "zd": z.get("Numer") or "",
        "dostawca": (z.get("Dostawca") or "").strip(),
        "data": z.get("Data") or "",
        "status": z.get("Status") or "",
        # ZK, które ta pozycja realizuje — most czyta je z powiązania
        # PozycjeRealizowane. Bez tego kolumna ZK pustoszała po zamówieniu.
        "zk": z.get("Zk") or "",
        # Numer projektu z Uwag ZK — to ZK wie, dla kogo powstała, nie BOM.
        "projekt": z.get("Projekt") or "",
    } for z in data.get("zamowione", [])]

    # Podmioty przychodzą tym samym wywołaniem — okno potrzebuje ich do listy
    # wyboru dostawcy, a osobne uruchomienie mostu kosztowałoby drugie ~8 s.
    return pozycje, data.get("podmioty", []), zamowione


def _zapotrzebowanie_cli(timeout):
    """Stara ścieżka: osobny proces NexoRecon.exe na każde wywołanie."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError(
            "Nie znaleziono NexoRecon.exe.\n\n"
            "Zbuduj most:\n  cd subiekt_sfera\\NexoRecon\n  dotnet build -c Release")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")

    tmpdir = tempfile.mkdtemp(prefix="subiekt_zap_")
    out = os.path.join(tmpdir, "zap.json")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            [exe, "zapotrzebowanie", f"--out={out}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Subiekt nie odpowiedział w {timeout} s.")

    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, "zapotrzebowanie", proc, out))

    with open(out, encoding="utf-8") as f:
        return json.load(f)


def stan_pozycji(symbole, projekt=None, timeout=TIMEOUT_S):
    """{symbol: {kartoteka, stan, zk, zd, dostawca, status_zd}} — dla kolumny
    SUBIEKT w arkuszu głównym RM_BAZA.

    Trzy stany naraz, bo to trzy różne informacje dla planującego produkcję:
    czy asortyment w ogóle istnieje w Subiekcie, czy jest na liście projektu
    (ZK) i czy zamówiony u dostawcy (ZD).
    """
    symbole = [str(s).strip() for s in (symbole or []) if str(s).strip()]
    if not symbole:
        return {}

    args = {"symbols": symbole}
    if projekt:
        args["projekt"] = projekt
    try:
        import subiekt_bridge
        data = subiekt_bridge.call(
            "stan-pozycji", args, timeout=timeout,
            fallback=lambda: _stan_pozycji_cli(symbole, projekt, timeout))
    except ImportError:
        data = _stan_pozycji_cli(symbole, projekt, timeout)

    return {p["Pytany"]: {
        "kartoteka": bool(p.get("MaKartoteke")),
        "nazwa": p.get("Nazwa") or "",
        "stan": float(p.get("Stan") or 0),
        "zk": p.get("Zk") or "",
        "ilosc_zk": float(p.get("IloscZk") or 0),
        "zd": p.get("Zd") or "",
        "dostawca": (p.get("Dostawca") or "").strip(),
        "ilosc_zd": float(p.get("IloscZd") or 0),
        "status_zd": p.get("StatusZd") or "",
    } for p in data.get("pozycje", [])}


def _stan_pozycji_cli(symbole, projekt, timeout):
    """Stara ścieżka: osobny proces NexoRecon.exe na każde wywołanie."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")

    tmpdir = tempfile.mkdtemp(prefix="subiekt_sp_")
    lst = os.path.join(tmpdir, "symbole.txt")
    out = os.path.join(tmpdir, "wynik.json")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("\n".join(symbole))

    cmd = [exe, "stan-pozycji", f"--symbols-file={lst}", f"--out={out}"]
    if projekt:
        cmd.append(f"--projekt={projekt}")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=flags)
    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, "stan-pozycji", proc, out))

    with open(out, encoding="utf-8") as f:
        return json.load(f)


def opis_stanu(info):
    """Krótki prefiks do kolumny SUBIEKT — wzorzec kolumny WYCENA z RFQ.

    Kolejność od najdalszego etapu: zamówione bije „jest w ZK", a to bije
    „istnieje kartoteka" — pokazujemy najświeższą informację o pozycji.
    """
    if not info:
        return ""
    if info.get("zd"):
        return f"🛒 {info['zd']}"
    if info.get("zk"):
        return f"📋 {info['zk']}"
    if info.get("kartoteka"):
        stan = info.get("stan") or 0
        return "📇 kartoteka" + (f" (stan {stan:g})" if stan else "")
    return "⬜ brak"


def _sciezka_master():
    """Ścieżka do master.sqlite — leży obok katalogu projektów."""
    return os.path.join(os.path.dirname(PROJECTS_DIR.rstrip("\\/")), "master.sqlite")


def _nazwy_dostawcow():
    """{supplier_id: nazwa} z bazy głównej RM_BAZA."""
    master = _sciezka_master()
    if not os.path.isfile(master):
        return {}
    try:
        con = sqlite3.connect(f"file:{master}?mode=ro", uri=True)
        try:
            return {r[0]: r[1] for r in
                    con.execute("SELECT supplier_id, name FROM suppliers")}
        finally:
            con.close()
    except sqlite3.Error:
        return {}


def projekty_po_numerze(numery):
    """{project_id: nazwa} dla numerów z Uwag na ZK (np. {„2619", „2607"}).

    Numer projektu to pierwszy człon nazwy w RM_BAZA („2619 CERAMIZATOR…"),
    a na ZK trafia sam numer — więc dopasowujemy po prefiksie nazwy.
    """
    numery = {str(n).strip() for n in (numery or []) if str(n).strip()}
    if not numery:
        return {}
    master = _sciezka_master()
    if not os.path.isfile(master):
        return {}
    out = {}
    try:
        con = sqlite3.connect(f"file:{master}?mode=ro", uri=True)
        try:
            for pid, nazwa in con.execute("SELECT project_id, name FROM projects"):
                pierwszy = (nazwa or "").strip().split(" ")[0]
                if pierwszy in numery:
                    out[pid] = nazwa
        finally:
            con.close()
    except sqlite3.Error:
        return {}
    return out


def dane_z_bom(project_id, numer_projektu=None):
    """{SYMBOL: {nazwa, dostawca}} — z BOM-u projektu.

    Subiekt nie zna dostawców (kartoteki ich nie mają), a RM_BAZA zna — więc
    to stąd bierzemy podpowiedź. Nazwa też z BOM: dane konstrukcyjne mają
    źródło prawdy w RM_BAZA, nie w Subiekcie.
    """
    path = os.path.join(PROJECTS_DIR, f"project_{project_id}.sqlite")
    if not os.path.isfile(path):
        return {}
    out = {}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            cols = {r[1] for r in con.execute("PRAGMA table_info('items')")}
            name_cols = [c for c in ("work_name", "src_name") if c in cols]
            # Typ pozycji (X / XX / Z / ZZ / STANDARD / ZNORMALIZOWANE) — ta sama
            # kolejność co w subiekt_projekt.py, żeby oba okna widziały to samo.
            cls_cols = [c for c in ("class_manual", "class_effective", "class_auto")
                        if c in cols]
            sel = ["work_drawing_no", "norm_drawing_no", "src_drawing_no"] + name_cols + cls_cols
            has_sup = "supplier_id" in cols
            if has_sup:
                sel.append("supplier_id")
            # `id` ZAWSZE ostatnie: para (project_id, item_id) to adres wiersza,
            # pod który po wysyłce ZD wraca „Zamówiono". Symbol nie wystarczy —
            # ten sam detal bywa w kilku projektach naraz.
            sel.append("id")
            where = " WHERE COALESCE(is_hidden, 0) = 0" if "is_hidden" in cols else ""
            rows = con.execute(f"SELECT {', '.join(sel)} FROM items{where}").fetchall()

        finally:
            con.close()
    except sqlite3.Error:
        return {}

    # Nazwy dostawców są w BAZIE GŁÓWNEJ (master.sqlite → suppliers), nie w
    # bazie projektu — ta trzyma tylko supplier_id. Tabela suppliers_cache
    # w projekcie bywa, ale nie zawsze (w project_36 jej nie ma), więc
    # źródłem jest master.
    dostawcy = _nazwy_dostawcow() if has_sup else {}

    # Symbol dla pozycji BEZ numeru rysunku liczy subiekt_projekt — oba okna
    # MUSZĄ generować ten sam symbol, inaczej pozycje z ZK (założone tamtym
    # oknem) nie dopasują się tutaj do BOM-u i mają pusty typ.
    from subiekt_projekt import symbol_z_nazwy, rozroznij_symbol

    n0 = 3
    uzyte = set()
    for r in rows:
        nr = next((v for v in r[0:3] if v is not None and str(v).strip()), None)
        nazwa = next((v for v in r[n0:n0 + len(name_cols)]
                      if v is not None and str(v).strip()), "")
        nazwa = _jedna_linia(nazwa)
        c0 = n0 + len(name_cols)
        typ = next((v for v in r[c0:c0 + len(cls_cols)]
                    if v is not None and str(v).strip()), "")

        # Elementy znormalizowane (łożyska, paski, uszczelki) nie mają numeru
        # rysunku — identyfikuje je nazwa. Pomijanie ich tutaj sprawiało, że
        # z 88 znormalizowanych w oknie ZD widać było 2 (zgłoszone 04.09.2026).
        if nr:
            klucz = _jedna_linia(nr)
        else:
            klucz = symbol_z_nazwy(nazwa)
            if not klucz:
                continue
            if klucz in uzyte:
                # Ta sama reguła rozróżniania co przy zakładaniu kartotek —
                # inaczej pozycja miałaby w tym oknie inny symbol niż w Subiekcie.
                klucz = rozroznij_symbol(nazwa, uzyte)
        uzyte.add(klucz)

        item_id = r[-1]
        sup = dostawcy.get(r[-2]) if has_sup else None
        out[klucz.strip().upper()] = {
            "nazwa": nazwa,
            "typ": str(typ).strip().upper(),
            "dostawca": str(sup).strip() if sup else "",
            # Numer projektu — dla pozycji już zamówionych to jedyne źródło
            # przypisania do projektu (nie mają już powiązania przez ZK).
            "projekt": numer_projektu or "",
            # Czy pozycja ma numer rysunku w BOM. To FAKT z danych, nie
            # zgadywanie z kształtu napisu: 'A-8-10-10' czy '6304ZZ' wyglądają
            # jak numery, a są kodami katalogowymi. Panel plików używa tego,
            # żeby nie zgłaszać braku rysunku dla łożyska.
            "ma_rysunek": bool(nr),
            "project_id": project_id,
            "item_id": item_id,
        }
    return out


def numer_projektu_z_uwag(uwagi):
    """Numer projektu z Uwag na ZK — tam RM_BAZA go wpisuje przy zakładaniu."""
    return (uwagi or "").strip()


def _numery_zd(tekst):
    """Czyste numery ZD z tego, co pokazuje kolumna ZD.

    Kolumna trzyma zapis DLA OKA: numer z ilością i możliwie kilka dokumentów
    naraz — „ZD 4/CENTRALA/2026 (8), ZD 7/CENTRALA/2026 (2)". Do wysyłki,
    usuwania i do portalu musi iść sam numer dokumentu; inaczej ten sam ZD
    zakłada w portalu kilka zamówień, bo ilość zmienia się między wysyłkami
    (zgłoszone 05.09.2026: „mam różne ZD4").
    """
    out = []
    for czesc in (tekst or "").split(","):
        nr = re.sub(r"\s*\(\d+(?:[.,]\d+)?\)\s*$", "", czesc.strip()).strip()
        if nr and nr not in out:
            out.append(nr)
    return out


def _klucz_zd(numer):
    """Sortowanie numerów ZD: „ZD 6/09/2026" → (2026, 9, 6).

    Zwykłe sortowanie tekstem dawało „ZD 10/09" przed „ZD 6/09", a przy
    zmianie miesiąca mieszało kolejność.
    """
    cyfry = [int(x) for x in re.findall(r"\d+", numer or "")]
    nr = cyfry[0] if cyfry else 0
    mies = cyfry[1] if len(cyfry) > 1 else 0
    rok = cyfry[-1] if len(cyfry) > 2 else 0
    return (rok, mies, nr)


def _zd_z_iloscia(zamowione):
    """„ZD 4/CENTRALA/2026 (8)" — numery ZD z ilościami, jak kolumna ZK.

    Ten sam detal bywa w kilku zamówieniach (dokładka, drugi dostawca),
    a sam numer nie mówił, ile z którego pochodzi.
    """
    wg_numeru = {}
    for z in zamowione or ():
        numer = (z.get("zd") or "").strip()
        if not numer:
            continue
        wg_numeru[numer] = wg_numeru.get(numer, 0.0) + float(z.get("ilosc") or 0)
    return ", ".join(f"{n} ({il:g})" if il else n
                     for n, il in sorted(wg_numeru.items()))


def _zk_z_iloscia(zk):
    """„ZK 7/CENTRALA/2026 (4), ZK 8/CENTRALA/2026 (4)".

    Subiekt liczy zapotrzebowanie ze wszystkich ZK naraz, więc jedna pozycja
    bywa sumą kilku dokumentów. Ilość przy numerze pokazuje, ile z tej sumy
    pochodzi z którego zamówienia — sam numer tego nie mówił.
    """
    wg_numeru = {}
    for z in zk or ():
        numer = (z.get("Numer") or "").strip()
        if not numer:
            continue
        wg_numeru[numer] = wg_numeru.get(numer, 0.0) + float(z.get("Ilosc") or 0)
    return ", ".join(f"{n} ({il:g})" if il else n
                     for n, il in sorted(wg_numeru.items()))


def _uprosc_nazwe(x):
    """Nazwa firmy do porównań: same znaki alfanumeryczne, małe litery.

    MAJA ↔ „MA-JA”, „Sp. z o.o.” ↔ „SPÓŁKA Z O.O.” — interpunkcja i spacje
    w nazwach firm są przypadkowe, więc do dopasowania się nie liczą.
    """
    return "".join(c for c in (x or "").lower() if c.isalnum())


def dopasuj_dostawce(nazwa_rm_baza, podmioty):
    """Nazwa dostawcy z RM_BAZA → nazwa podmiotu w Subiekcie, albo "".

    Pomiar na projekcie 2619 (04.09.2026): z 15 nazw z BOM-u pasuje 7.
    Reszta to dopiski („Alufrost domówione"), dwie firmy w jednym polu
    („DAGAR + RMPAK") albo wcale nie dostawcy („magazyn", „anulowane").
    Dlatego to tylko PODPOWIEDŹ — ostatnie słowo ma człowiek, wybierając
    z listy w arkuszu.
    """
    s = (nazwa_rm_baza or "").strip()
    if not s or not podmioty:
        return ""
    low = {p.lower(): p for p in podmioty}
    if s.lower() in low:
        return low[s.lower()]
    # Bez znaków, które w RM_BAZA bywają ozdobnikami, a w Subiekcie częścią
    # nazwy (MAJA ↔ "MA-JA").
    uprosc = _uprosc_nazwe
    su = uprosc(s)
    if not su:
        return ""
    for p in podmioty:
        if uprosc(p) == su:
            return p
    # Nazwa z dopiskiem: „Alufrost domówione" → pierwszy człon.
    pierwszy = s.split()[0]
    if len(pierwszy) >= 3:
        pu = uprosc(pierwszy)
        trafienia = [p for p in podmioty if uprosc(p).startswith(pu)]
        if len(trafienia) == 1:
            return trafienia[0]
    return ""


def scal_bom(bom, dane, numer_projektu):
    """Dokłada BOM jednego projektu do wspólnego słownika {SYMBOL: …}.

    ⚠️ NIE `bom.update()`. Ten sam symbol bywa w kilku projektach (kopia
    testowa 3000 ma te same rysunki co 2632 Feniks) i update() zostawiał
    adres wiersza OSTATNIEGO projektu — „Zamówiono" z wysyłki ZD trafiało
    do 3000 zamiast do Feniksa (zgłoszone 05.09.2026). Adresy trzymamy
    per projekt w `refs`: {numer projektu: (project_id, item_id)}, a wiersz
    wybiera z nich te z kolumny „Projekt".
    """
    for sym, d in (dane or {}).items():
        wpis = bom.setdefault(sym, d)
        if d.get("item_id"):
            wpis.setdefault("refs", {})[numer_projektu] = (d["project_id"], d["item_id"])


def refy_bom(b, projekty):
    """Adresy wierszy BOM-u dla pozycji: tylko z projektów, do których należy.

    `projekty` — numery z kolumny „Projekt" (z Uwag na ZK). Gdy pozycja nie
    ma ich wcale, a symbol jest w jednym projekcie — bierzemy ten jeden.
    Gdy jest w kilku i nie wiadomo w którym — nie zgadujemy (lepiej nie
    oznaczyć niż oznaczyć w cudzym projekcie) i mówimy o tym w konsoli.
    """
    refs = (b or {}).get("refs") or {}
    if not refs:
        return []
    wybrane = [refs[p] for p in (projekty or ()) if p in refs]
    if wybrane:
        return wybrane
    if len(refs) == 1:
        return list(refs.values())
    print(f"⚠️  Symbol w {len(refs)} projektach ({', '.join(refs)}), "
          f"pozycja bez numeru projektu — „Zamówiono” nie zostanie oznaczone.")
    return []


def zbuduj_wiersze(zapotrzebowanie, bom, podmioty=(), tylko_projekt=None, zamowione=()):
    """Łączy dane z Subiekta z BOM-em. tylko_projekt=„2619" zawęża do projektu.

    `zamowione` (pozycje z ZD) dokładane są jako wiersze z wypełnioną kolumną
    ZD — inaczej po zamówieniu znikałyby bez śladu.
    """
    wiersze = []
    for p in zapotrzebowanie:
        projekty = sorted({numer_projektu_z_uwag(z.get("Uwagi"))
                           for z in p["zk"] if numer_projektu_z_uwag(z.get("Uwagi"))})
        if tylko_projekt and tylko_projekt not in projekty:
            continue
        b = bom.get(p["symbol"].strip().upper(), {})
        z_bom = b.get("dostawca") or ""
        # Skąd wziął się dostawca — user musi widzieć różnicę między „Subiekt
        # tak ma w kartotece" a „automat zgadł z nazwy w BOM-ie". To drugie
        # trafia ~55 % (pomiar 04.09.2026) i wymaga sprawdzenia okiem.
        if p["dostawca_subiekt"]:
            dostawca, zrodlo = p["dostawca_subiekt"], "subiekt"
        else:
            dostawca = dopasuj_dostawce(z_bom, podmioty)
            zrodlo = "automat" if dostawca else ""

        # Cztery wartości z kroku 3 przepływu (SUBIEKT_PRZEPLYW_OPIS.md):
        #   potrzeba  — ile trzeba na projekt (suma z pozycji ZK)
        #   dostępne  — co Subiekt pokazuje jako stan
        #   ze stanu  — ile realnie da się pokryć z magazynu
        #   kupić     — reszta; to właśnie zwraca zapotrzebowanie
        # Potrzeba: suma z pozycji ZK. Bywa pusta (Sfera nie zawsze wypełnia
        # PozycjeZK) — wtedy najbliższą prawdy wartością jest samo zapotrzebowanie.
        potrzeba = sum(float(z.get("Ilosc") or 0) for z in p["zk"]) or p["ilosc"]

        # Ilość per projekt — Subiekt zwraca JEDNĄ pozycję na detal, więc
        # 2602-100.45ZZ po 4 szt. w ZK 7 (proj. 2627) i ZK 8 (proj. 3500) ma
        # ilość 8. Przy filtrze projektu wyglądało to, jakby całe 8 szło na
        # ten jeden projekt (zgłoszone 05.09.2026). Rozbicie liczy się przy
        # wyświetlaniu, bo wtedy dopiero wiadomo, który projekt jest wybrany.
        zk_ilosci = {}
        for z in p["zk"]:
            pr = numer_projektu_z_uwag(z.get("Uwagi"))
            if pr:
                zk_ilosci[pr] = zk_ilosci.get(pr, 0.0) + float(z.get("Ilosc") or 0)
        dostepne = p.get("dostepne", 0.0)
        ze_stanu = min(potrzeba, dostepne) if dostepne > 0 else 0.0

        # „Kupić" to RESZTA po pokryciu ze stanu (SUBIEKT_PRZEPLYW_OPIS.md,
        # krok 3: „potrzeba 20, stan 12 → 12 ze stanu, 8 do kupienia").
        #
        # ⚠️ NIE bierzemy tego wprost z zapotrzebowania Subiekta. Ono liczy
        # niezrealizowaną część ZK niezależnie od magazynu — dla 011-100.20
        # kazało kupić 3 sztuki przy 63 na stanie. Zgłoszone 04.09.2026:
        # „po co kupić jak mam na stanie 63?".
        kupic = max(0.0, potrzeba - ze_stanu)

        wiersze.append({
            "sel": False,
            "symbol": p["symbol"],
            # Nazwa z BOM-u ma pierwszeństwo — RM_BAZA jest źródłem prawdy
            # dla danych konstrukcyjnych (plan integracji, sekcja 1).
            "nazwa": b.get("nazwa") or p["nazwa_subiekt"],
            "typ": b.get("typ", ""),
            "potrzeba": potrzeba,
            # {numer projektu: ilość} — do rozbicia potrzeby przy filtrze.
            "zk_ilosci": zk_ilosci,
            "dostepne": dostepne,
            "zarezerwowane": p.get("zarezerwowane", 0.0) + p.get("zadysponowane", 0.0),
            "ze_stanu": ze_stanu,
            # Progi z kartoteki Subiekta: „10/15" = domawiaj przy 10, do 15.
            "stan_min": p.get("stan_min", 0.0),
            "stan_opt": p.get("stan_opt", 0.0),
            "ilosc": kupic,           # „kupić" = potrzeba − ze stanu
            "brak_wg_subiekta": p["ilosc"],   # co mówi samo zapotrzebowanie
            "jm": p["jm"],
            "dostawca": dostawca,
            "zrodlo_dostawcy": zrodlo,   # subiekt | automat | reczny | ""
            # Co było w BOM — pokazujemy, gdy dopasowanie nie wyszło, żeby
            # user wiedział, czego szukać na liście.
            "dostawca_bom": z_bom,
            "projekty": ", ".join(projekty),
            # Numery ZK z ILOŚCIAMI — bez nich widać było tylko, że potrzeba
            # wynika z dwóch dokumentów, ale nie ile z którego.
            "zk": _zk_z_iloscia(p["zk"]),
            # Numer ZD wpisywany po utworzeniu — zostaje w arkuszu, żeby było
            # widać, co już zamówione, zanim odświeżenie usunie pozycję.
            "zd": "",
            # Adresy wierszy BOM-u (po jednym na projekt z kolumny „Projekt")
            # — po wysyłce ZD tędy wraca „Zamówiono".
            "bom_ref": refy_bom(b, projekty),
        })
    # Zamówione — tylko te, których nie ma już w zapotrzebowaniu (te same
    # symbole mogą tam wisieć, jeśli ZD pokryło część ilości).
    #
    # Ten sam detal bywa w KILKU ZD (dwa zamówienia u różnych dostawców albo
    # dokładka po pierwszym). Grupujemy je po symbolu, żeby kolumna ZD mogła
    # pokazać komplet z ilościami — jak kolumna ZK.
    wg_symbolu = {}
    for z in zamowione or ():
        wg_symbolu.setdefault(z["symbol"].strip().upper(), []).append(z)

    juz = {w["symbol"].strip().upper() for w in wiersze}
    for sym, grupa in wg_symbolu.items():
        if sym in juz:
            continue
        z = grupa[0]
        b = bom.get(sym, {})
        # Projekt z UWAG ZK (przez most), BOM tylko awaryjnie: symbol bywa
        # w kilku BOM-ach (kopia testowa 3000 ma rysunki Feniksa 2632)
        # i BOM wskazywał zły projekt (zgłoszone 05.09.2026).
        projekt = (next((x.get("projekt") for x in grupa if x.get("projekt")), "")
                   or (b.get("projekt", "") if b else ""))
        projekty_zk = [p.strip() for p in projekt.split(",") if p.strip()]
        if tylko_projekt and tylko_projekt not in projekty_zk:
            continue
        wiersze.append({
            "sel": False,
            "symbol": z["symbol"],
            "nazwa": b.get("nazwa") or z["nazwa_subiekt"],
            "typ": b.get("typ", ""),
            # Pozycji nie ma już w zapotrzebowaniu (pokryta przez ZD), więc
            # „potrzeba" = ilość, którą realnie zamówiono — suma ze WSZYSTKICH
            # ZD tego detalu, nie z pierwszego napotkanego.
            "potrzeba": sum(float(x.get("ilosc") or 0) for x in grupa),
            "dostepne": 0.0,
            "zarezerwowane": 0.0,
            "ze_stanu": 0.0,
            "stan_min": 0.0,
            "stan_opt": 0.0,
            "ilosc": sum(float(x.get("ilosc") or 0) for x in grupa),
            "jm": "szt",
            "dostawca": z["dostawca"],
            "dostawca_bom": b.get("dostawca", ""),
            "projekty": projekt,
            # Numery ZK z powiązania ZD→ZK. Pozycja zniknęła z zapotrzebowania,
            # ale zamówienie klienta nadal istnieje — kolumna pokazuje je
            # SZARO, jako informację historyczną (patrz _refill).
            "zk": ", ".join(sorted({x.get("zk") for x in grupa if x.get("zk")})),
            "zk_historyczne": True,
            # Numery ZD z ilościami — ten sam format co kolumna ZK, żeby było
            # widać, ile z której dostawy pochodzi.
            "zd": _zd_z_iloscia(grupa),
            "zd_status": z.get("status", ""),
            "zd_data": z.get("data", ""),
            "bom_ref": refy_bom(b, projekty_zk),
        })

    wiersze.sort(key=lambda w: (bool(w.get("zd")), w["dostawca"] == "",
                                w["dostawca"], w["symbol"]))
    return wiersze


# ── Zapis ZD ────────────────────────────────────────────────────────────────
def utworz_zd(pozycje, timeout=TIMEOUT_S, uwagi=None):
    """Tworzy ZD w Subiekcie. pozycje: [{symbol, ilosc, dostawca[, reczna]}].

    `uwagi` — tekst do pola Uwagi każdego utworzonego ZD. Okno magazynu
    wpisuje „MAGAZYN", żeby zamówienie na skład dało się odróżnić od
    projektowych; zamówienia z ZK nie podają nic i Uwagi zostają puste.
    """
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")

    plan = {"pozycje": pozycje}
    if uwagi:
        plan["uwagi"] = uwagi

    # ZAPIS — most nie ponawia operacji po niejednoznacznym błędzie, bo
    # powtórzone „zd" to drugi dokument w Subiekcie (plan, sekcja 14).
    # Fallback do CLI jest bezpieczny tylko dlatego, że wchodzi wyłącznie
    # wtedy, gdy most w ogóle nie wystartował — czyli nic się nie wykonało.
    try:
        import subiekt_bridge
        return subiekt_bridge.call(
            "zd", {"plan": plan, "zapisz": True}, timeout=timeout, write=True,
            fallback=lambda: _utworz_zd_cli(plan, timeout))
    except ImportError:
        return _utworz_zd_cli(plan, timeout)


def _utworz_zd_cli(plan, timeout):
    """Stara ścieżka: osobny proces NexoRecon.exe."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")

    tmpdir = tempfile.mkdtemp(prefix="subiekt_zd_")
    plan_path = os.path.join(tmpdir, "zd.json")
    out = os.path.join(tmpdir, "wynik.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            [exe, "zd", f"--plan={plan_path}", f"--out={out}", "--zapisz"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Subiekt nie odpowiedział w {timeout} s.")

    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, "zd", proc, out))

    with open(out, encoding="utf-8") as f:
        return json.load(f)


def usun_zd(numery, zapisz=False, timeout=TIMEOUT_S):
    """Kasuje ZD o podanych numerach. zapisz=False → tylko podgląd.

    Numery muszą być podane jawnie — most nie przyjmuje zakresów ani filtrów.
    Usunięcie dokumentu jest nieodwracalne.
    """
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")
    if not numery:
        raise RuntimeError("Nie podano numerów ZD do usunięcia.")

    # USUWANIE — nieodwracalne, więc żadnego automatycznego ponawiania
    # (plan, sekcja 14). zapisz=False to sam podgląd i wtedy nic nie znika.
    args = {"numery": ";".join(numery)}
    if zapisz:
        args["zapisz"] = True
    try:
        import subiekt_bridge
        return subiekt_bridge.call(
            "zd-usun", args, timeout=timeout, write=zapisz,
            fallback=lambda: _usun_zd_cli(numery, zapisz, timeout))
    except ImportError:
        return _usun_zd_cli(numery, zapisz, timeout)


def _usun_zd_cli(numery, zapisz, timeout):
    """Stara ścieżka: osobny proces NexoRecon.exe."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")

    tmpdir = tempfile.mkdtemp(prefix="subiekt_zdu_")
    out = os.path.join(tmpdir, "wynik.json")
    cmd = [exe, "zd-usun", "--numery=" + ";".join(numery), f"--out={out}"]
    if zapisz:
        cmd.append("--zapisz")

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Subiekt nie odpowiedział w {timeout} s.")

    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, "zd-usun", proc, out))

    with open(out, encoding="utf-8") as f:
        return json.load(f)


def zapisz_log(wynik):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        p = os.path.join(LOG_DIR, f"zd_{datetime.now():%Y%m%d_%H%M%S}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(wynik, f, ensure_ascii=False, indent=1)
        return p
    except Exception:
        return None


# ── Okno ────────────────────────────────────────────────────────────────────
class ZamowieniaWindow(tk.Toplevel, Kreciolek):
    # Kolumny arkusza. Indeksy muszą się zgadzać z COL_* niżej.
    # Cztery ilości z kroku 3 przepływu: potrzeba / dostępne / ze stanu / kupić.
    # „Kupić" (= Brakuje) to ta, którą realnie zamawiamy — jest edytowalna.
    # „Na stanie" to ilość DOSTĘPNA (Subiekt odejmuje już rezerwacje);
    # „Rezerw." pokazuje, ile z magazynu jest zajęte. „Min/Opt" to progi
    # zamawiania z kartoteki (np. „10/15" = domawiaj przy 10, uzupełnij do 15).
    HEADERS = ["✓", "Nr rysunku", "Nazwa", "Typ", "Potrzeba", "Na stanie", "Rezerw.",
               "Min/Opt", "Ze stanu", "Kupić", "J.m.", "Dostawca (Subiekt)",
               "wg BOM", "Projekt", "ZK", "ZD", "Data ZD", "PDF"]
    (COL_SEL, COL_SYMBOL, COL_NAZWA, COL_TYP, COL_POTRZEBA, COL_DOSTEPNE, COL_REZERW,
     COL_MINOPT, COL_ZE_STANU, COL_ILOSC, COL_JM, COL_DOSTAWCA, COL_DOST_BOM,
     COL_PROJ, COL_ZK, COL_ZD, COL_DATA_ZD, COL_PDF) = range(18)
    SZEROKOSCI = [30, 115, 165, 48, 60, 60, 56, 60, 56, 50, 34, 145, 88, 56, 88, 92, 74, 40]

    # Wartości filtra typu — DOKŁADNIE jak FILTER_CLASS_VALUES w arkuszu
    # głównym RM_BAZA, razem z LASER / LASER EXPORT (rozwijane do X i XX).
    TYPY = ["X", "XX", "Z", "ZZ", "STANDARD", "ZNORMALIZOWANE",
            "LASER", "LASER EXPORT"]

    def __init__(self, parent, project_id=None, project_name=None):
        super().__init__(parent)
        self.project_id = project_id
        self.project_name = project_name or (str(project_id) if project_id else "")
        self.wszystkie = []        # pełne dane z Subiekta (przed filtrem)
        self.widoczne = []         # to, co realnie jest w arkuszu
        self.podmioty = []         # nazwy firm z Subiekta — lista wyboru dostawcy
        self.filter_typ_modes = {}  # {typ: 'show'|'hide'} — kafelek ✚
        self._ostatni_klik = None   # kotwica dla Shift+klik w kolumnie ✓

        self.title("Zamówienia do dostawców (ZD)" +
                   (f" — projekt {self.project_name}" if self.project_name else ""))
        self.geometry("1250x700")
        self.minsize(900, 400)
        # ŚWIADOMIE bez transient(): okno-dziecko z transient dostaje w Windows
        # tylko przycisk „×", bez minimalizacji i maksymalizacji. To pełnoprawny
        # arkusz roboczy, więc ma się zachowywać jak okno główne RM_BAZA
        # (— □ ×) i dać się zmaksymalizować.
        try:
            self.state("zoomed")      # startuje na pełnym ekranie, jak arkusz główny
        except tk.TclError:
            pass                      # inne środowisko okienkowe — zostaje geometry()

        self._build_ui()
        self.after(100, self._load_async)

    # ── UI ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        top = tk.Frame(self, bg="#34495e", height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🛒 Zamówienia do dostawców — braki z ZK projektów",
                 bg="#34495e", fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)
        # Wiek odczytu dużą czcionką — dane z Subiekta starzeją się (ktoś
        # w firmie zakłada ZD, zmienia stany), a nic tego nie sygnalizowało.
        # Kolor rośnie od zielonego do czerwonego wraz z upływem czasu.
        self.lbl_wiek = tk.Label(top, text="", bg="#34495e", fg="#e74c3c",
                                 font=("Arial", 13, "bold"))
        self.lbl_wiek.pack(side=tk.LEFT, padx=(16, 0))
        self.btn_refresh = tk.Button(top, text="🔄 Odśwież", command=self._load_async,
                                     bg="#3498db", fg="white", font=("Arial", 8),
                                     padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_refresh.pack(side=tk.RIGHT, padx=10, pady=8)

        # ── Pasek filtrów (wzorzec z arkusza głównego: tk.*Var + _apply_filters)
        f = tk.Frame(self, bg="#ecf0f1")
        f.pack(side=tk.TOP, fill=tk.X)

        tk.Label(f, text="Szukaj:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(12, 3), pady=6)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refill())
        tk.Entry(f, textvariable=self.search_var, width=22, font=("Arial", 9)).pack(side=tk.LEFT, pady=6)

        tk.Label(f, text="Dostawca:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(14, 3), pady=6)
        self.filter_dostawca_var = tk.StringVar(value=FILTR_WSZYSCY)
        self.combo_dostawca = ttk.Combobox(f, textvariable=self.filter_dostawca_var,
                                           width=24, state="readonly", font=("Arial", 9))
        self.combo_dostawca["values"] = [FILTR_WSZYSCY]
        self.combo_dostawca.pack(side=tk.LEFT, pady=6)
        self.combo_dostawca.bind("<<ComboboxSelected>>", self._dostawca_wybrany)
        #: pełna lista dostawców — do zawężania listy rozwijanej wyszukiwarką
        self._dostawcy_wszyscy = [FILTR_WSZYSCY]

        # Szukanie dostawcy: OSOBNE pole, nie edytowalne combo. Dostawców bywa
        # ponad sto i przewijanie listy do „QUAY” trwało dłużej niż wpisanie
        # trzech liter (zgłoszone 05.09.2026). Wpisywanie wprost w combo
        # mieszało się z wyświetlaną wartością („maja— wszyscy —”), więc filtr
        # jest tutaj, a combo tylko pokazuje wynik.
        self._dost_placeholder = "szukaj…"
        self.dostawca_szukaj_var = tk.StringVar(value=self._dost_placeholder)
        self.dostawca_szukaj_var.trace_add("write", lambda *_: self._szukaj_dostawcy())
        self.ent_dost_szukaj = tk.Entry(f, textvariable=self.dostawca_szukaj_var,
                                        width=10, font=("Arial", 9), fg="#95a5a6")
        self.ent_dost_szukaj.pack(side=tk.LEFT, padx=(3, 0), pady=6)

        def _wejscie(_e=None):
            if self.dostawca_szukaj_var.get() == self._dost_placeholder:
                self.dostawca_szukaj_var.set("")
            self.ent_dost_szukaj.config(fg="#2c3e50")

        def _wyjscie(_e=None):
            if not self.dostawca_szukaj_var.get().strip():
                self.ent_dost_szukaj.config(fg="#95a5a6")
                self.dostawca_szukaj_var.set(self._dost_placeholder)

        self.ent_dost_szukaj.bind("<FocusIn>", _wejscie)
        self.ent_dost_szukaj.bind("<FocusOut>", _wyjscie)
        self.ent_dost_szukaj.bind("<Escape>", lambda _e: self.dostawca_szukaj_var.set(""))

        # Typ pozycji — jak filtr „Typ" w arkuszu głównym RM_BAZA.
        tk.Label(f, text="Typ:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(14, 3), pady=6)
        self.filter_typ_var = tk.StringVar(value=TYP_WSZYSTKO)
        self.combo_typ = ttk.Combobox(f, textvariable=self.filter_typ_var, width=15,
                                      state="readonly", font=("Arial", 9))
        self.combo_typ["values"] = [TYP_WSZYSTKO] + self.TYPY + [TYP_BEZ_TYPU]
        self.combo_typ.pack(side=tk.LEFT, pady=6)
        self.combo_typ.bind("<<ComboboxSelected>>", lambda _e: self._refill())

        # Kafelek multi-select z negacją — sklejony z combo, jak w arkuszu głównym.
        self.btn_typ_multi = tk.Button(f, text="✚", command=self._okno_filtru_typu,
                                       bg="#7f8c8d", fg="white", font=("Arial", 8),
                                       width=3, relief=tk.RAISED, bd=1, cursor="hand2")
        self.btn_typ_multi.pack(side=tk.LEFT, padx=(0, 2), pady=6)

        tk.Label(f, text="Projekt:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(14, 3), pady=6)
        self.filter_projekt_var = tk.StringVar(value=FILTR_WSZYSCY)
        self.combo_projekt = ttk.Combobox(f, textvariable=self.filter_projekt_var,
                                          width=12, state="readonly", font=("Arial", 9))
        self.combo_projekt["values"] = [FILTR_WSZYSCY]
        self.combo_projekt.pack(side=tk.LEFT, pady=6)
        self.combo_projekt.bind("<<ComboboxSelected>>", lambda _e: self._refill())

        self.only_bez_dostawcy_var = tk.IntVar(value=0)
        tk.Checkbutton(f, text="tylko bez dostawcy", variable=self.only_bez_dostawcy_var,
                       command=self._refill, bg="#ecf0f1", font=("Arial", 8),
                       activebackground="#ecf0f1").pack(side=tk.LEFT, padx=(14, 0), pady=6)

        # Stan pozycji — jeden filtr zamiast znikania. Zasada okna: arkusz
        # pokazuje WSZYSTKO, widocznością steruje wyłącznie belka filtrów.
        tk.Label(f, text="Stan:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(14, 3), pady=6)
        self.filter_stan_var = tk.StringVar(value=STAN_WSZYSTKIE)
        combo_stan = ttk.Combobox(f, textvariable=self.filter_stan_var, width=18,
                                  state="readonly", font=("Arial", 9))
        combo_stan["values"] = [STAN_WSZYSTKIE, STAN_DO_ZAMOWIENIA, STAN_ZAMOWIONE]
        combo_stan.pack(side=tk.LEFT, pady=6)
        combo_stan.bind("<<ComboboxSelected>>", lambda _e: self._refill())

        # Filtr po KONKRETNYM zamówieniu — „pokaż, co poszło w ZD 6/09/2026”.
        # Lista buduje się z tego, co realnie jest na liście (patrz _load_done),
        # więc nie ma tu numerów, których nie da się wybrać. Numer z ilością
        # („ZD 6/09/2026 (4)”) jest zapisem DLA OKA, więc do filtra idzie sam
        # numer dokumentu (_numery_zd) — jedna pozycja bywa w kilku ZD naraz.
        tk.Label(f, text="ZD:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(14, 3), pady=6)
        self.filter_zd_var = tk.StringVar(value=ZD_WSZYSTKIE)
        self.combo_zd = ttk.Combobox(f, textvariable=self.filter_zd_var, width=20,
                                     state="readonly", font=("Arial", 9))
        self.combo_zd["values"] = [ZD_WSZYSTKIE]
        self.combo_zd.pack(side=tk.LEFT, pady=6)
        self.combo_zd.bind("<<ComboboxSelected>>", lambda _e: self._refill())

        # Czyszczenie filtrów — ta sama ikona i kolor co w arkuszu głównym.
        tk.Button(f, text="🗑️", command=self._wyczysc_filtry, bg="#95a5a6", fg="white",
                  font=("Arial", 11, "bold"), width=3, relief=tk.RAISED, bd=2,
                  cursor="hand2").pack(side=tk.LEFT, padx=(10, 2), pady=4)

        # ── Zaznaczanie (te same nawyki co w arkuszu głównym)
        s = tk.Frame(self, bg="#f4ecf7")
        s.pack(side=tk.TOP, fill=tk.X)
        tk.Label(s, text="Zaznacz:", bg="#f4ecf7", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(12, 6), pady=4)
        # Combobox w stylu paska RM_BAZA (readonly, Arial 8) — wybór wykonuje
        # akcję i wraca do etykiety, bo to polecenie, nie stan filtra.
        self.zaznacz_var = tk.StringVar(value=ZAZNACZ_ETYKIETA)
        cmb_zaznacz = ttk.Combobox(s, textvariable=self.zaznacz_var,
                                   values=[ZAZNACZ_WIDOCZNE, ZAZNACZ_NIC, ZAZNACZ_ODWROC],
                                   state="readonly", width=14, font=("Arial", 8))
        cmb_zaznacz.pack(side=tk.LEFT, padx=2, pady=4)
        cmb_zaznacz.bind("<<ComboboxSelected>>", self._on_zaznacz_combo)
        tk.Label(s, text="   (klik w ✓ przełącza wiersz • SHIFT+klik w ✓ = cały zakres "
                         "• DWUKLIK w Dostawcę = wybór z listy Subiekta "
                         "• PPM = ustaw dostawcę dla wielu naraz)",
                 bg="#f4ecf7", fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.LEFT, padx=6)

        # Legenda kolorów kolumny Dostawca — bez niej trzeba by zgadywać,
        # czym różni się żółty od zielonego.
        leg = tk.Frame(self, bg="#f8f9f9")
        leg.pack(side=tk.TOP, fill=tk.X)
        tk.Label(leg, text="Dostawca:", bg="#f8f9f9", font=("Arial", 8, "bold")
                 ).pack(side=tk.LEFT, padx=(12, 4), pady=2)
        for kolor, opis in (("#d5f5e3", "z Subiekta / wskazany ręcznie"),
                            ("#fcf3cf", "zgadnięty z nazwy w BOM — sprawdź"),
                            ("#fdedec", "brak — ZD nie powstanie")):
            tk.Label(leg, text="  ", bg=kolor, relief=tk.SOLID, bd=1).pack(side=tk.LEFT, padx=(6, 2), pady=2)
            tk.Label(leg, text=opis, bg="#f8f9f9", fg="#7f8c8d",
                     font=("Arial", 8)).pack(side=tk.LEFT, pady=2)

        # Tło CAŁEGO wiersza znaczy co innego niż kolor komórki dostawcy —
        # bez tego rozdziału user widział jednolitą zieleń i nie umiał
        # odczytać źródła dostawcy.
        tk.Label(leg, text="   Wiersz:", bg="#f8f9f9", font=("Arial", 8, "bold")
                 ).pack(side=tk.LEFT, padx=(18, 4), pady=2)
        for kolor, opis in (("#dfeaf7", "zamówione (jest ZD)"),
                            ("#eef1f3", "pokryte ze stanu — nic nie kupujemy")):
            tk.Label(leg, text="  ", bg=kolor, relief=tk.SOLID, bd=1).pack(side=tk.LEFT, padx=(6, 2), pady=2)
            tk.Label(leg, text=opis, bg="#f8f9f9", fg="#7f8c8d",
                     font=("Arial", 8)).pack(side=tk.LEFT, pady=2)

        self.summary = tk.Label(self, text="Wczytywanie…", bg="#ecf0f1", fg="#2c3e50",
                                font=("Arial", 9), anchor="w", padx=12, pady=6)
        self.summary.pack(side=tk.TOP, fill=tk.X)

        # ── Arkusz (ten sam silnik co arkusz główny RM_BAZA)
        wrap = tk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 4))
        if Sheet is None:
            tk.Label(wrap, text="Brak biblioteki tksheet — zainstaluj: pip install tksheet",
                     fg="#c0392b", font=("Arial", 10)).pack(pady=20)
            self.sheet = None
        else:
            self.sheet = Sheet(wrap, headers=list(self.HEADERS),
                               column_width=120, height=460, theme="light blue")
            self.sheet.set_options(show_selected_cells_border=True,
                                   enable_edit_cell_auto_resize=False,
                                   row_drag_and_drop_perform=False,
                                   empty_horizontal=0, empty_vertical=0)
            # drag_select rejestruje <Shift-Button-1> i <Control-Button-1> —
            # bez niego Shift+klik nie zaznacza zakresu, a przy 170 pozycjach
            # klikanie po jednej jest bez sensu (zgłoszone 04.09.2026).
            self.sheet.enable_bindings((
                "single_select", "drag_select", "ctrl_select", "select_all",
                "column_width_resize", "arrowkeys", "right_click_popup_menu",
                "rc_select", "copy", "paste", "edit_cell",
            ))
            # Szerokości kolumn zapamiętywane między sesjami, jak w arkuszu głównym.
            podepnij_szerokosci(self, self.sheet, "zamowienia", self.SZEROKOSCI)
            self.sheet.bind("<<SheetModified>>", self._on_edit)
            self.sheet.bind("<ButtonRelease-1>", self._on_click, add="+")
            self.sheet.bind("<Double-Button-1>", self._on_dblclick, add="+")
            # Kolumny z długą treścią (ZK/ZD z ilościami, pełne nazwy) nie
            # mieszczą się w szerokości arkusza — dymek pokazuje całość bez
            # zmiany układu (zgłoszone 05.09.2026: „jest ciasno, mało widać").
            self._podepnij_tooltip()
            # Shift+klik zaznacza zakres w arkuszu — te akcje przekładają go
            # na kolumnę ✓ (co realnie idzie do ZD).
            self.sheet.popup_menu_add_command("✓ Zaznacz wiersze",
                                              lambda: self._zaznacz_wybrane(True))
            self.sheet.popup_menu_add_command("☐ Odznacz wiersze",
                                              lambda: self._zaznacz_wybrane(False))
            self.sheet.popup_menu_add_command("Ustaw dostawcę dla wierszy…",
                                              self._ustaw_dostawce_masowo)
            self.sheet.popup_menu_add_command("✉ Wyślij ZD dostawcy…", self._wyslij_zd)
            self.sheet.popup_menu_add_command("👁 Podgląd PDF zamówienia", self._podglad_pdf)
            self.sheet.popup_menu_add_command("🗑 Usuń zamówienia (ZD)…", self._usun_zd)
            self.sheet.pack(fill=tk.BOTH, expand=True)

        bottom = tk.Frame(self)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))
        self.btn_zd = tk.Button(bottom, text="🛒 Utwórz ZD z zaznaczonych",
                                command=self._utworz_zd, bg="#e67e22", fg="white",
                                font=("Arial", 9, "bold"), padx=14, pady=5,
                                relief=tk.RAISED, bd=2, state=tk.DISABLED)
        self.btn_zd.pack(side=tk.RIGHT)
        # Wysyłka gotowego ZD do dostawcy: PDF z Subiekta + rysunki z serwera,
        # otwarte jako wiadomość w programie pocztowym (nic nie wychodzi samo).
        self.btn_mail = tk.Button(bottom, text="✉ Wyślij ZD dostawcy",
                                  command=self._wyslij_zd, bg="#2980b9", fg="white",
                                  font=("Arial", 9, "bold"), padx=12, pady=5,
                                  relief=tk.RAISED, bd=2)
        self.btn_mail.pack(side=tk.RIGHT, padx=(0, 8))
        # Podgląd wydruku ZD — ten sam plik, który idzie w mailu. Gotowy
        # otwiera się od razu; „Nowy PDF” wymusza świeży (~11 s przez most).
        tk.Button(bottom, text="👁 Podgląd PDF", command=self._podglad_pdf,
                  bg="#7f8c8d", fg="white", font=("Arial", 9), padx=10, pady=5,
                  relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=(0, 6))
        tk.Button(bottom, text="🔁 Nowy PDF",
                  command=lambda: self._podglad_pdf(wymus_nowy=True),
                  bg="#95a5a6", fg="white", font=("Arial", 9), padx=10, pady=5,
                  relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=(0, 8))
        # Pozycja spoza BOM-u i zapotrzebowania (śruby, materiał pomocniczy) —
        # wspólny formularz zakłada kartotekę i dorzuca wiersz do listy.
        tk.Button(bottom, text="➕ Dodaj pozycję spoza BOM", command=self._dodaj_reczna,
                  bg="#27ae60", fg="white", font=("Arial", 9),
                  padx=10, pady=5, relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=(0, 8))
        # Kasowanie dokumentów WPROST na belce, nie tylko pod prawym klawiszem
        # — po testach integracji zostają śmieci i szukanie tego w menu
        # kontekstowym było uciążliwe (zgłoszone 05.09.2026).
        #
        # ⚠️ KOLEJNOŚĆ MA ZNACZENIE: najpierw ZD, potem ZK. ZD powstaje
        # z powiązaniem do ZK (Zd.cs) — skasowanie ZK jako pierwszego zostawia
        # osierocone zamówienie, a Subiekt potrafi wtedy odmówić usunięcia ZK.
        # Dlatego „Usuń ZK" stoi PO „Usuń ZD" i sam o tej kolejności przypomina.
        tk.Button(bottom, text="🗑 Usuń ZK", command=self._usun_zk,
                  bg="#c0392b", fg="white", font=("Arial", 9),
                  padx=10, pady=5, relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=(0, 8))
        tk.Button(bottom, text="🗑 Usuń ZD", command=self._usun_zd,
                  bg="#e74c3c", fg="white", font=("Arial", 9),
                  padx=10, pady=5, relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=(0, 8))
        tk.Label(bottom, text="Powstanie osobne ZD dla każdego dostawcy.",
                 fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.LEFT, pady=8)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    # ── wczytywanie ────────────────────────────────────────────────────────
    def _load_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.btn_zd.config(state=tk.DISABLED)
        self.start_kreciolek("Pytam Subiekta o zapotrzebowanie")
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        try:
            zap, podmioty, zamowione = pobierz_zapotrzebowanie()

            # BOM-y wszystkich projektów, których dotyczy zapotrzebowanie —
            # nie tylko tego wybranego w RM_BAZA. Wcześniej okno otwarte bez
            # wybranego projektu cicho gubiło kolumnę „wg BOM" i nazwy
            # (zgłoszone 04.09.2026): pokazywało puste pola zamiast danych.
            numery = {numer_projektu_z_uwag(z.get("Uwagi"))
                      for p in zap for z in p["zk"]}
            numery.discard("")
            # Także projekty pozycji JUŻ zamówionych — ich ZK nie ma już
            # w zapotrzebowaniu, więc bez tego BOM ich projektu się nie
            # wczytywał i adres „Zamówiono" szedł do innego projektu z tym
            # samym symbolem (zgłoszone 05.09.2026).
            numery |= {p.strip() for z in zamowione
                       for p in (z.get("projekt") or "").split(",") if p.strip()}
            if self.project_name:
                numery.add(self.project_name.strip().split(" ")[0])
            bom = {}
            for pid, pname in projekty_po_numerze(numery).items():
                nr = (pname or "").strip().split(" ")[0]
                scal_bom(bom, dane_z_bom(pid, nr), nr)
            if self.project_id and not bom:
                nr = self.project_name.strip().split(" ")[0] if self.project_name else ""
                scal_bom(bom, dane_z_bom(self.project_id, nr), nr)

            wiersze = zbuduj_wiersze(zap, bom, podmioty, zamowione=zamowione)

            # Odświeżenie NIE może kasować pracy użytkownika: wybrani ręcznie
            # dostawcy i zaznaczenia przeżywają przeładowanie. Bez tego po
            # kliknięciu „Odśwież" lista wyglądała jak na starcie i sprawiała
            # wrażenie, że nic się nie odświeżyło (zgłoszone 04.09.2026).
            poprzednie = {w["symbol"].strip().upper(): w for w in self.wszystkie}
            for w in wiersze:
                stare = poprzednie.get(w["symbol"].strip().upper())
                if not stare:
                    continue
                if stare.get("dostawca") and not w.get("zd"):
                    w["dostawca"] = stare["dostawca"]
                    w["zrodlo_dostawcy"] = stare.get("zrodlo_dostawcy", "")
                    w["sel"] = stare.get("sel", False)

            self.after(0, lambda: self._load_done(wiersze, None, podmioty))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._load_done([], err, []))

    def _load_done(self, wiersze, error, podmioty=()):
        self.stop_kreciolek()      # także przy błędzie — inaczej kręci się dalej
        self.zaznacz_odczyt(self.lbl_wiek)
        self.btn_refresh.config(state=tk.NORMAL)
        if error:
            self.status.config(text="Błąd.")
            self.summary.config(text=error.split("\n")[0][:200])
            messagebox.showerror("Subiekt", error, parent=self)
            return

        self.wszystkie = wiersze
        self.podmioty = list(podmioty or [])
        dostawcy = sorted({w["dostawca"] for w in wiersze if w["dostawca"]})
        self._dostawcy_wszyscy = [FILTR_WSZYSCY] + dostawcy + [FILTR_BRAK_DOSTAWCY]
        self.combo_dostawca["values"] = self._dostawcy_wszyscy
        projekty = sorted({p for w in wiersze for p in w["projekty"].split(", ") if p})
        self.combo_projekt["values"] = [FILTR_WSZYSCY] + projekty

        # Numery ZD obecne na liście — sortowane od najnowszego (numer rośnie
        # w obrębie miesiąca), bo szuka się zwykle tego, co przed chwilą
        # powstało. Wybrany numer przeżywa odświeżenie, o ile dokument nadal
        # istnieje — inaczej filtr wskazywałby na skasowane ZD i lista
        # wyglądałaby na pustą.
        zdki = sorted({nr for w in wiersze for nr in _numery_zd(w.get("zd"))},
                      key=_klucz_zd, reverse=True)
        self.combo_zd["values"] = [ZD_WSZYSTKIE] + zdki
        if self.filter_zd_var.get() not in ([ZD_WSZYSTKIE] + zdki):
            self.filter_zd_var.set(ZD_WSZYSTKIE)

        # Lista typów jest STAŁA — dokładnie ta sama co w arkuszu głównym
        # (FILTER_CLASS_VALUES). Ograniczanie jej do typów obecnych w danych
        # sprawiało, że filtr wyglądał inaczej w każdym projekcie.

        # Otwarte z konkretnego projektu → od razu zawęź do niego.
        if self.project_name:
            nr = self.project_name.strip().split(" ")[0]
            if nr in projekty:
                self.filter_projekt_var.set(nr)

        self.btn_zd.config(state=tk.NORMAL)
        self._refill()

        # Godzina odczytu — bez niej nie widać, czy „Odśwież" w ogóle zadziałał,
        # gdy dane się nie zmieniły.
        czas = datetime.now().strftime("%H:%M:%S")
        do_zam = sum(1 for w in wiersze if not w.get("zd"))
        zamow = sum(1 for w in wiersze if w.get("zd"))
        bez_dost = sum(1 for w in wiersze if not w["dostawca"] and not w.get("zd"))

        czesci = [f"Odczyt {czas}: {do_zam} do zamówienia"]
        if zamow:
            czesci.append(f"{zamow} już w ZD")
        if bez_dost == do_zam and do_zam:
            czesci.append("ŻADNA nie ma dostawcy — dwuklik w kolumnę „Dostawca (Subiekt)”")
        elif bez_dost:
            czesci.append(f"{bez_dost} bez dostawcy — dwuklik, żeby wybrać")
        czesci.append("w Subiekcie nic nie zmieniono")
        self.status.config(text=".   ".join(czesci) + ".")

    # ── filtry (wzorzec _apply_filters z arkusza głównego) ──────────────────
    @staticmethod
    def _rozwin_typ(t):
        """LASER / LASER EXPORT → {X, XX}; „(bez typu)" → {""} — jak w arkuszu głównym."""
        if t in ("LASER", "LASER EXPORT"):
            return {"X", "XX"}
        if t == TYP_BEZ_TYPU:
            return {""}
        return {t}

    def _typ_pasuje(self, w):
        """Filtr typu: combo (jeden) + kafelek ✚ (wiele, z negacją)."""
        typ = w.get("typ", "")

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
                self._refill()               # NA ŻYWO, bez zatwierdzania

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
            self._refill()

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

    def _wyczysc_filtry(self):
        """Wszystkie filtry do stanu wyjściowego — łącznie z kafelkiem ✚."""
        self.search_var.set("")
        self.filter_dostawca_var.set(FILTR_WSZYSCY)
        self.filter_projekt_var.set(FILTR_WSZYSCY)
        self.filter_typ_var.set(TYP_WSZYSTKO)
        self.filter_stan_var.set(STAN_WSZYSTKIE)
        self.filter_zd_var.set(ZD_WSZYSTKIE)
        self.only_bez_dostawcy_var.set(0)
        try:
            self.dostawca_szukaj_var.set(self._dost_placeholder)
            self.ent_dost_szukaj.config(fg="#95a5a6")
            self.combo_dostawca["values"] = self._dostawcy_wszyscy
        except Exception:
            pass
        self.filter_typ_modes = {}
        try:
            self.btn_typ_multi.config(bg="#7f8c8d")
        except Exception:
            pass
        self._refill()

    def _filtruj(self, wiersze):
        szukaj = (self.search_var.get() or "").strip().lower()
        dost = self.filter_dostawca_var.get()
        proj = self.filter_projekt_var.get()
        tylko_bez = bool(self.only_bez_dostawcy_var.get())

        stan = self.filter_stan_var.get()
        zd_filtr = self.filter_zd_var.get()

        out = []
        for w in wiersze:
            # Nic nie znika samo — o widoczności decyduje wyłącznie ten filtr.
            if stan == STAN_DO_ZAMOWIENIA and w.get("zd"):
                continue
            if stan == STAN_ZAMOWIONE and not w.get("zd"):
                continue
            if zd_filtr != ZD_WSZYSTKIE and zd_filtr not in _numery_zd(w.get("zd")):
                continue
            if szukaj and szukaj not in f"{w['symbol']} {w['nazwa']}".lower():
                continue
            if dost == FILTR_BRAK_DOSTAWCY:
                if w["dostawca"]:
                    continue
            elif dost != FILTR_WSZYSCY and w["dostawca"] != dost:
                continue
            if proj != FILTR_WSZYSCY and proj not in w["projekty"].split(", "):
                continue
            # Ile z sumarycznej potrzeby przypada na WYBRANY projekt. Liczone
            # tutaj, a nie w zbuduj_wiersze, bo wiersze powstają raz (bez
            # filtra), a projekt wybiera się później — inaczej rozbicie nigdy
            # się nie pokazywało.
            w["potrzeba_tu"] = self._potrzeba_na_projekt(w, proj)
            if not self._typ_pasuje(w):
                continue
            if tylko_bez and w["dostawca"]:
                continue
            out.append(w)
        return out

    # ── dymek z pełną treścią komórki ──────────────────────────────────────
    def _podepnij_tooltip(self):
        """Dymek dla kolumn, których treść nie mieści się w szerokości.

        Tylko te kolumny, gdzie realnie brakuje miejsca — dla liczb dymek
        byłby szumem. tksheet nie ma własnych tooltipów, więc robimy je na
        Toplevel bez ramki, jak podpowiedzi w podpowiedziach nazw.
        """
        self._tip = None
        self._tip_kom = None          # (wiersz, kolumna) — żeby nie mrugał
        self._tip_after = None
        self.sheet.bind("<Motion>", self._tip_ruch, add="+")
        self.sheet.bind("<Leave>", lambda _e: self._tip_ukryj(), add="+")
        # Kliknięcie i przewijanie chowają dymek — inaczej wisi nad zmienioną
        # już zawartością.
        self.sheet.bind("<Button-1>", lambda _e: self._tip_ukryj(), add="+")
        self.sheet.bind("<MouseWheel>", lambda _e: self._tip_ukryj(), add="+")
        # Dymek to osobne okno — bez tego zostałby na ekranie po zamknięciu
        # arkusza (i po zamknięciu całego okna zamówień).
        self.bind("<Destroy>", lambda _e: self._tip_ukryj(), add="+")

    #: nagłówki kolumn z dymkiem (reszta to liczby, daty i znaczniki).
    #: Dopasowanie DOKŁADNE — „zd" jako fragment łapało też „Data ZD",
    #: gdzie dymek jest zbędny.
    TOOLTIP_KOLUMNY = {"nazwa", "dostawca (subiekt)", "projekt", "zk", "zd",
                       "wg bom"}

    def _tip_ukryj(self):
        if self._tip_after:
            try:
                self.after_cancel(self._tip_after)
            except Exception:
                pass
            self._tip_after = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None
        self._tip_kom = None

    def _tip_ruch(self, event):
        try:
            r = self.sheet.identify_row(event, allow_end=False)
            c = self.sheet.identify_column(event, allow_end=False)
        except Exception:
            return
        if r is None or c is None:
            self._tip_ukryj()
            return
        if (r, c) == self._tip_kom:
            return                     # ta sama komórka — nie przerysowuj
        self._tip_ukryj()

        # Które kolumny mają dymek: po nagłówku, nie po indeksie — kolumny
        # bywają przestawiane, a indeksy zmieniają się przy zmianach układu.
        try:
            naglowek = self.HEADERS[c].strip().lower()
        except Exception:
            return
        if naglowek not in self.TOOLTIP_KOLUMNY:
            return

        try:
            tekst = str(self.sheet.get_cell_data(r, c) or "").strip()
        except Exception:
            return
        if not tekst:
            return

        self._tip_kom = (r, c)
        # Krótka zwłoka — bez niej dymki migoczą przy przesuwaniu myszy.
        self._tip_after = self.after(
            400, lambda: self._tip_pokaz(tekst, event.x_root, event.y_root))

    def _tip_pokaz(self, tekst, x, y):
        self._tip_after = None
        if self._tip is not None:
            return
        tip = tk.Toplevel(self)
        tip.overrideredirect(True)     # bez ramki okna — to dymek
        tip.attributes("-topmost", True)
        tk.Label(tip, text=tekst, bg="#ffffe0", fg="#2c3e50",
                 relief=tk.SOLID, bd=1, justify=tk.LEFT, anchor="w",
                 font=("Arial", 9), padx=6, pady=3,
                 wraplength=520).pack()
        # Poniżej kursora, żeby nie zasłaniać komórki, na którą patrzysz.
        tip.update_idletasks()
        szer, wys = tip.winfo_width(), tip.winfo_height()
        ekran_x = tip.winfo_screenwidth()
        tip.geometry(f"+{min(x + 14, ekran_x - szer - 8)}+{y + 20}")
        self._tip = tip

    @staticmethod
    def _potrzeba_na_projekt(w, proj):
        """Część potrzeby przypadająca na `proj`, albo None gdy nie ma o czym mówić.

        None, gdy filtr wyłączony albo pozycja dotyczy jednego projektu —
        wtedy kolumna pokazuje samą liczbę, bez dopisku.
        """
        if not proj or proj == FILTR_WSZYSCY:
            return None
        projekty = [p for p in (w.get("projekty") or "").split(", ") if p]
        if len(projekty) < 2:
            return None
        # Ilości per dokument ZK — zapamiętane przy budowaniu wiersza.
        wg_zk = w.get("zk_ilosci") or {}
        if not wg_zk:
            return None
        suma = sum(il for pr, il in wg_zk.items() if pr == proj)
        return suma or None

    @staticmethod
    def _potrzeba_tekst(w):
        """Ilość w kolumnie „Potrzeba"; przy kilku projektach też część na ten.

        Subiekt liczy zapotrzebowanie ze WSZYSTKICH otwartych ZK naraz, więc
        detal używany w dwóch projektach ma jedną, sumaryczną pozycję:
        2602-100.45ZZ po 4 szt. w ZK 7 (proj. 2627) i ZK 8 (proj. 3500) daje
        jeden wiersz z ilością 8. Przy włączonym filtrze projektu sama liczba
        „8" sugerowała, że tyle idzie na ten projekt (zgłoszone 05.09.2026).
        """
        potrzeba = w.get("potrzeba") or 0
        if not potrzeba:
            return ""
        tu = w.get("potrzeba_tu")
        if tu is not None and tu != potrzeba:
            return f"{potrzeba:g}  (tutaj {tu:g})"
        return f"{potrzeba:g}"

    @staticmethod
    def _min_opt(w):
        """„10/15" — próg domawiania / poziom docelowy. Puste, gdy nieustawione."""
        mn, opt = w.get("stan_min", 0), w.get("stan_opt", 0)
        if not mn and not opt:
            return ""
        return f"{mn:g}/{opt:g}" if opt else f"{mn:g}/–"

    def _refill(self):
        if not self.sheet:
            return
        poprzednie = [id(w) for w in self.widoczne]
        self.widoczne = self._filtruj(self.wszystkie)
        # Kotwica Shift+klik wskazuje POZYCJĘ w widocznej liście, więc traci
        # sens dopiero wtedy, gdy zmieni się ZESTAW wierszy (filtr, odczyt) —
        # nie przy zwykłym przerysowaniu po kliknięciu. Zerowanie w _filtruj
        # kasowało ją po KAŻDYM kliknięciu i Shift nie miał od czego liczyć
        # zakresu (zgłoszone 05.09.2026: „zaznacza tylko podświetlenie").
        if [id(w) for w in self.widoczne] != poprzednie:
            self._ostatni_klik = None
        # Kolory są przypisane do NUMERÓW wierszy, nie do danych — bez
        # wyczyszczenia zostają po zmianie filtra na zupełnie innych pozycjach
        # (zgłoszone 04.09.2026: po powrocie z „zamówione" na „wszystkie"
        # podświetlone było wszystko).
        try:
            self.sheet.dehighlight_all()
        except Exception:
            pass

        self.sheet.set_sheet_data(
            [[("✓" if w["sel"] else "☐"), w["symbol"], w["nazwa"], w.get("typ", ""),
              self._potrzeba_tekst(w),
              f"{w.get('dostepne', 0):g}" if w.get("dostepne") else "",
              f"{w.get('zarezerwowane', 0):g}" if w.get("zarezerwowane") else "",
              self._min_opt(w),
              f"{w.get('ze_stanu', 0):g}" if w.get("ze_stanu") else "",
              f"{w['ilosc']:g}", w["jm"], w["dostawca"], w.get("dostawca_bom", ""),
              w["projekty"], w["zk"], w.get("zd", ""), w.get("zd_data", ""),
              "📄" if self._plik_pdf(w.get("zd")) else ""]
             for w in self.widoczne],
            reset_col_positions=False, redraw=False)

        # Dostawcę wybiera się dwuklikiem (okno z listą 629 podmiotów), NIE
        # przez create_dropdown: strzałka dropdowna w tksheet rozciąga się na
        # sąsiednią kolumnę i zasłania „wg BOM" — wygląda to, jakby dostawcy
        # w ogóle się nie wczytali (zgłoszone 04.09.2026).
        # Wyłącznie highlight_cells — mieszanie z highlight_rows dawało
        # niespójny efekt przy zmianie filtra (kolory wierszy i komórek
        # czyszczą się inaczej).
        # Kolor WIERSZA i kolor KOMÓRKI muszą się różnić, inaczej znaczenie
        # ginie: zamówiony wiersz malowany tym samym zielonym co „dostawca
        # z Subiekta" dawał jednolitą planszę, na której nie dało się odczytać
        # źródła dostawcy (zgłoszone 04.09.2026 — „w poziomie i pionie ten sam
        # kolor"). Stąd wiersze na chłodnym niebieskim, komórki dostawcy na
        # zielono/żółto/różowo.
        ostatnia = len(self.HEADERS) - 1
        for i, w in enumerate(self.widoczne):
            if w.get("zd"):
                # Zamówione — cały wiersz na niebiesko (stan pozycji).
                for c in range(ostatnia + 1):
                    self.sheet.highlight_cells(row=i, column=c, bg="#dfeaf7")
                # ZK odbudowane z powiązania ZD→ZK: zamówienie klienta nadal
                # istnieje, ale ta pozycja nie jest już w zapotrzebowaniu.
                # Szara czcionka mówi „informacja historyczna", a nie
                # „jest do zamówienia z tego ZK".
                if w.get("zk_historyczne") and w.get("zk"):
                    self.sheet.highlight_cells(row=i, column=self.COL_ZK,
                                               bg="#dfeaf7", fg="#95a5a6")
            elif w["ilosc"] <= 0:
                # Cała potrzeba pokryta ze stanu — nie ma czego zamawiać.
                for c in range(ostatnia + 1):
                    self.sheet.highlight_cells(row=i, column=c, bg="#eef1f3")

            # Kolor kolumny Dostawca mówi, SKĄD się wziął — bo od tego zależy,
            # czy trzeba go sprawdzić okiem. Malowany PO tle wiersza i także
            # dla pozycji zamówionych: „skąd dostawca" trzeba widzieć również
            # wtedy, gdy ZD już powstało.
            #   różowy  — brak, ZD nie powstanie
            #   żółty   — zgadnięty z nazwy w BOM (~55 % trafień), do weryfikacji
            #   zielony — wskazany ręcznie albo wzięty z kartoteki Subiekta
            zrodlo = w.get("zrodlo_dostawcy", "")
            if not w["dostawca"]:
                self.sheet.highlight_cells(row=i, column=self.COL_DOSTAWCA, bg="#fdedec")
            elif zrodlo == "automat":
                self.sheet.highlight_cells(row=i, column=self.COL_DOSTAWCA, bg="#fcf3cf")
            elif zrodlo in ("reczny", "subiekt"):
                self.sheet.highlight_cells(row=i, column=self.COL_DOSTAWCA, bg="#d5f5e3")

            # Wyróżnienia liczbowe — niezależne od tego, skąd wziął się
            # dostawca, więc poza łańcuchem if/elif powyżej.
            if w.get("ze_stanu"):
                # Część potrzeby pokryta z magazynu — nie trzeba tego kupować.
                self.sheet.highlight_cells(row=i, column=self.COL_ZE_STANU, bg="#d5f5e3")
            if w.get("stan_min") and w.get("dostepne", 0) <= w["stan_min"]:
                # Stan spadł do progu — trzeba domówić niezależnie od projektu.
                self.sheet.highlight_cells(row=i, column=self.COL_MINOPT, bg="#fdebd0")
            if w.get("zarezerwowane"):
                # Część stanu zajęta — „mam 63" znaczy co innego niż
                # „mam 63, ale 60 zarezerwowane".
                self.sheet.highlight_cells(row=i, column=self.COL_REZERW, bg="#fdebd0")
        self.sheet.redraw()
        self._przelicz()

    def _przelicz(self):
        zazn = [w for w in self.wszystkie if w["sel"]]
        bez_dost = [w for w in zazn if not w["dostawca"]]
        dostawcy = {w["dostawca"] for w in zazn if w["dostawca"]}
        zamowione = [w for w in self.wszystkie if w.get("zd")]
        do_zam = len(self.wszystkie) - len(zamowione)
        # Ilu dostawców zgadł automat — te warto sprawdzić przed utworzeniem ZD.
        auto = sum(1 for w in self.wszystkie
                   if w.get("zrodlo_dostawcy") == "automat" and not w.get("zd"))
        self.summary.config(text=(
            f"Pozycji: {len(self.wszystkie)}    do zamówienia: {do_zam}"
            + (f"    ✅ zamówione: {len(zamowione)}" if zamowione else "")
            + f"    pokazanych: {len(self.widoczne)}    zaznaczonych: {len(zazn)}"
            + (f"    → ZD: {len(dostawcy)} (po jednym na dostawcę)" if dostawcy else "")
            + (f"    ⚠ bez dostawcy: {len(bez_dost)}" if bez_dost else "")
            + (f"    🟡 zgadnięci przez automat: {auto}" if auto else "")
        ))

    # ── pozycja ręczna ─────────────────────────────────────────────────────
    def _dodaj_reczna(self):
        """Dorzuca do listy pozycję, której nie ma w BOM-ie ani w zapotrzebowaniu."""
        import subiekt_asortyment
        projekt = self.project_name.strip().split(" ")[0] if self.project_name else ""

        def po_zapisie(d):
            sym = d["symbol"].strip()
            if any(w["symbol"].strip().upper() == sym.upper() for w in self.wszystkie):
                messagebox.showinfo("Pozycja", f"„{sym}” już jest na liście.", parent=self)
                return
            self.wszystkie.append({
                "sel": True, "symbol": sym, "nazwa": d["nazwa"], "typ": "",
                "potrzeba": 1.0, "dostepne": 0.0, "zarezerwowane": 0.0, "ze_stanu": 0.0,
                "stan_min": 0.0, "stan_opt": 0.0, "ilosc": 1.0, "brak_wg_subiekta": 0.0,
                "jm": d.get("jm") or "szt", "dostawca": "", "zrodlo_dostawcy": "",
                "dostawca_bom": "", "projekty": projekt, "zk": "", "zd": "",
                "zd_data": "", "zd_status": "",
                # Nie ma jej w zapotrzebowaniu Subiekta — most dołoży ją do ZD
                # wprost, zamiast przez UtworzNaPodstawieZapotrzebowania.
                "reczna": True,
            })
            self._refill()
            self.status.config(text=f"Dodano „{sym}” — ustaw ilość w kolumnie Kupić i dostawcę (dwuklik).")

        subiekt_asortyment.okno_nowa_kartoteka(self, po_zapisie=po_zapisie)

    # ── zaznaczanie i edycja ───────────────────────────────────────────────
    def _on_zaznacz_combo(self, _event=None):
        """Wybór z combo wykonuje akcję i wraca do etykiety — to polecenie,
        nie stan, więc nie ma sensu zostawiać go jako wybranej wartości."""
        akcja = {ZAZNACZ_WIDOCZNE: "widoczne",
                 ZAZNACZ_NIC: "nic",
                 ZAZNACZ_ODWROC: "odwroc"}.get(self.zaznacz_var.get())
        self.zaznacz_var.set(ZAZNACZ_ETYKIETA)
        if akcja:
            self._zaznacz(akcja)

    def _zaznacz(self, akcja):
        widoczne = {id(w) for w in self.widoczne}
        for w in self.wszystkie:
            if id(w) not in widoczne:
                continue
            w["sel"] = (akcja == "widoczne") if akcja != "odwroc" else (not w["sel"])
        self._refill()

    def _zaznacz_wybrane(self, wartosc):
        """PPM na zaznaczeniu w arkuszu — jak w arkuszu głównym."""
        if not self.sheet:
            return
        try:
            rows = sorted(self.sheet.get_selected_rows(get_cells_as_rows=True))
        except Exception:
            rows = []
        for r in rows:
            if 0 <= r < len(self.widoczne):
                self.widoczne[r]["sel"] = wartosc
        self._refill()

    def _ustaw_dostawce_masowo(self):
        """PPM → jeden dostawca dla wielu wierszy. Typowe, bo cała grupa
        pozycji zwykle idzie do tego samego kontrahenta."""
        if not self.sheet:
            return
        try:
            rows = sorted(self.sheet.get_selected_rows(get_cells_as_rows=True))
        except Exception:
            rows = []
        if not rows:
            messagebox.showinfo("Dostawca", "Zaznacz najpierw wiersze w arkuszu.", parent=self)
            return
        self._wybierz_dostawce(rows)

    def _wyslij_zd(self):
        """
        ✉ → wybór DOKUMENTU ZD, potem okno wysyłki: PDF zamówienia z Subiekta
        + rysunki pozycji z serwera, otwarte w programie pocztowym.

        Wybieramy dokument, nie pozycje — tak samo jak przy usuwaniu, bo mail
        dotyczy całego zamówienia. Gdy kursor stoi na wierszu z ZD, ten numer
        jest domyślny i przy jednym kandydacie idziemy od razu dalej.
        """
        # Kolumna ZD pokazuje numer Z ILOŚCIĄ i bywa zbiorcza — do wysyłki
        # i usuwania idzie CZYSTY numer dokumentu (patrz _numery_zd).
        zd = {}
        for w in self.wszystkie:
            for nr in _numery_zd(w.get("zd")):
                zd.setdefault(nr, {"dostawca": w.get("dostawca", ""),
                                   "data": w.get("zd_data", ""), "poz": []})
                zd[nr]["poz"].append(w)
        if not zd:
            messagebox.showinfo("Wyślij ZD",
                                "Na liście nie ma żadnych zamówień do dostawców.\n\n"
                                "Najpierw utwórz ZD z zaznaczonych pozycji.", parent=self)
            return

        # ⚠️ Wysyłamy ISTNIEJĄCY DOKUMENT ZD, a nie pozycje zaznaczone ✓.
        # To dwie różne rzeczy: ✓ służy do UTWORZENIA nowego ZD („Utwórz ZD
        # z zaznaczonych"), a tu wybieramy dokument, który już jest w Subiekcie.
        # Bez tego rozróżnienia okno pokazywało pozycje zupełnie innego
        # zamówienia niż zaznaczone (zgłoszone 05.09.2026).
        zaznaczone_bez_zd = [w for w in self.wszystkie
                             if w.get("sel") and not _numery_zd(w.get("zd"))]

        # Numer z wiersza pod kursorem — „wyślij to, na co patrzę".
        # _numery_zd, bo kolumna trzyma numer Z ILOŚCIĄ („ZD 4/… (8)"),
        # a klucze słownika `zd` są czyste.
        biezacy = None
        try:
            for r in self.sheet.get_selected_rows(get_cells_as_rows=True):
                if 0 <= r < len(self.widoczne):
                    nry = _numery_zd(self.widoczne[r].get("zd"))
                    if nry:
                        biezacy = nry[0]
                        break
        except Exception:
            pass

        if biezacy and biezacy in zd:
            self._wyslij_dokument(biezacy, zd[biezacy])
            return

        if zaznaczone_bez_zd:
            # Typowa pomyłka: user zaznacza ✓ i klika ✉, spodziewając się, że
            # pójdą właśnie te pozycje. Mówimy wprost, czego brakuje.
            messagebox.showinfo(
                "Wyślij ZD",
                f"Zaznaczono ✓ {len(zaznaczone_bez_zd)} pozycji, ale nie mają one "
                "jeszcze zamówienia w Subiekcie.\n\n"
                "Ten przycisk wysyła GOTOWY dokument ZD.\n"
                "Kolejność jest taka:\n"
                "  1. „🛒 Utwórz ZD z zaznaczonych” — powstaje dokument,\n"
                "  2. dopiero potem „✉ Wyślij ZD dostawcy”.",
                parent=self)
            return

        if len(zd) == 1:
            nr, dane = next(iter(zd.items()))
            self._wyslij_dokument(nr, dane)
            return

        # Kilka dokumentów, kursor nie wskazuje żadnego — pytamy który.
        dlg = tk.Toplevel(self)
        dlg.title("Wyślij zamówienie do dostawcy")
        dlg.transient(self)
        dlg.grab_set()
        wysrodkuj(dlg, self, 560, 340)

        tk.Label(dlg, text="Wybierz zamówienie do wysłania:",
                 font=("Arial", 9, "bold")).pack(padx=14, pady=(12, 2), anchor="w")
        tk.Label(dlg, text="To są dokumenty ZD istniejące już w Subiekcie — "
                           "nie pozycje zaznaczone ✓ w arkuszu.",
                 fg="#7f8c8d", font=("Arial", 8)).pack(padx=14, pady=(0, 6), anchor="w")

        ramka = tk.Frame(dlg)
        ramka.pack(fill=tk.BOTH, expand=True, padx=14, pady=4)
        lb = tk.Listbox(ramka, font=("Consolas", 9), activestyle="none")
        sv = ttk.Scrollbar(ramka, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sv.set)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sv.pack(side=tk.RIGHT, fill=tk.Y)

        numery = sorted(zd.keys())
        for nr in numery:
            d = zd[nr]
            lb.insert(tk.END, f"{nr:16} {d['dostawca'][:32]:34} {len(d['poz'])} poz.")
        lb.selection_set(0)

        def dalej(_ev=None):
            sel = lb.curselection()
            if not sel:
                return
            nr = numery[sel[0]]
            dlg.destroy()
            self._wyslij_dokument(nr, zd[nr])

        lb.bind("<Double-1>", dalej)
        stopka = tk.Frame(dlg)
        stopka.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=10)
        tk.Button(stopka, text="Dalej →", command=dalej, bg="#2980b9", fg="white",
                  font=("Arial", 9, "bold"), padx=14, pady=4).pack(side=tk.RIGHT)
        tk.Button(stopka, text="Anuluj", command=dlg.destroy,
                  font=("Arial", 9), padx=12, pady=4).pack(side=tk.RIGHT, padx=6)

    def _wyslij_dokument(self, numer_zd, dane):
        """Otwiera okno wysyłki dla jednego ZD."""
        try:
            import subiekt_wyslij_zd
        except Exception as e:
            messagebox.showerror("Wyślij ZD", f"Brak modułu wysyłki:\n{e}", parent=self)
            return

        # Piąty element: czy pozycja ma numer rysunku (z BOM-u, nie z kształtu
        # symbolu). Panel plików nie zgłasza wtedy braku dokumentacji dla
        # łożysk i innych elementów katalogowych.
        # Szósty element: numery projektów pozycji (kolumna „Projekt"). ZD
        # zbiera detale z KILKU projektów, a szukanie plików startowało od
        # projektu otwartego w arkuszu — czyli często nie tego (zgłoszone
        # 05.09.2026). Mając je, szukamy najpierw tam, gdzie detal powstał.
        # Siódmy element: adresy wierszy BOM-u [(project_id, item_id), …] — po
        # jednym na projekt pozycji; po wysyłce okno zapisuje pod nie „Zamówiono".
        pozycje = [(w.get("symbol", ""), w.get("nazwa", ""),
                    w.get("ilosc", "") or w.get("potrzeba", ""), w.get("jm", "szt."),
                    w.get("ma_rysunek"), w.get("projekty", ""), w.get("bom_ref"))
                   for w in dane["poz"]]

        # Adres e-mail i nadawca pochodzą z RM_BAZA — okno pozwala je poprawić.
        email = self._email_dostawcy(dane["dostawca"])
        nadawca = self._nadawca()

        # Panel plików ten sam co w oknie „Wyślij do RFQ" — stąd komplet
        # zależności z arkusza głównego. getattr, bo starsze wersje okna
        # mogą ich nie mieć; panel działa wtedy w okrojonym trybie.
        okno = self.master
        subiekt_wyslij_zd.open_window(
            self, numer_zd, dane["dostawca"], email,
            self.project_name or "", pozycje, nadawca,
            szukaj_plikow=self._pliki_rysunku,
            szukaj_maila=self._email_po_nip,
            szukaj_dalej=self._szukaj_dalej_rysunku,
            szukaj_hurtem=self._szukaj_hurtem_biblioteka,
            needs_dxf=getattr(okno, "_rfq_needs_dxf", None),
            register_drop=getattr(okno, "_register_file_drop", None),
            dozwolone_ext=getattr(okno, "RFQ_PORTAL_EXTS", None),
            blad_serwera=lambda: getattr(okno, "_rfq_server_error", None),
            # Fabryka agenta portalu — arkusz zna ścieżkę do master.sqlite tej
            # maszyny, więc tworzy agenta sam. Bez niej combo „Rysunki"
            # w oknie wysyłki ma tylko tryb mailowy.
            agent_portalu=getattr(okno, "_get_rfq_agent", None))

    def _email_dostawcy(self, nazwa_subiekt):
        """
        Adres dostawcy z bazy RM_BAZA. Dopasowanie po nazwie tą samą funkcją,
        którą okno wiąże dostawców z podmiotami Subiekta.
        """
        if not nazwa_subiekt:
            return ""
        try:
            master = _sciezka_master()
            con = sqlite3.connect(f"file:{master}?mode=ro", uri=True)
            try:
                wiersze = con.execute(
                    "SELECT name, COALESCE(NULLIF(TRIM(email),''),"
                    "                      NULLIF(TRIM(email_default),'')) "
                    "FROM suppliers WHERE is_active=1").fetchall()
            finally:
                con.close()
        except Exception as e:
            print(f"⚠️  Nie udało się odczytać maili dostawców: {e}")
            return ""

        cel = _uprosc_nazwe(nazwa_subiekt)
        for nazwa, mail in wiersze:
            if mail and _uprosc_nazwe(nazwa or "") == cel:
                return mail
        # Dopasowanie luźne — nazwy w Subiekcie bywają pełne („SPÓŁKA Z O.O.”),
        # a w RM_BAZA skrócone.
        for nazwa, mail in wiersze:
            u = _uprosc_nazwe(nazwa or "")
            if mail and u and (u in cel or cel in u):
                return mail
        return ""

    def _email_po_nip(self, nip):
        """
        Adres dostawcy po NIP-cie — klucz pewniejszy niż nazwa, bo firmy
        w RM_BAZA i w Subiekcie macie już powiązane właśnie po NIP.
        """
        cyfry = "".join(c for c in (nip or "") if c.isdigit())
        if not cyfry:
            return ""
        try:
            con = sqlite3.connect(f"file:{_sciezka_master()}?mode=ro", uri=True)
            try:
                for nazwa, mail, n in con.execute(
                        "SELECT name, COALESCE(NULLIF(TRIM(email),''),"
                        "                      NULLIF(TRIM(email_default),'')), nip "
                        "FROM suppliers WHERE nip IS NOT NULL AND TRIM(nip)<>''"):
                    if mail and "".join(c for c in (n or "") if c.isdigit()) == cyfry:
                        return mail
            finally:
                con.close()
        except Exception as e:
            print(f"⚠️  Szukanie maila po NIP {cyfry}: {e}")
        return ""

    def _nadawca(self):
        """Imię i nazwisko zalogowanego użytkownika RM_BAZA (display_name)."""
        try:
            uzytkownik = getattr(self.master, "current_user", None)
            if not uzytkownik:
                return ""
            master = _sciezka_master()
            con = sqlite3.connect(f"file:{master}?mode=ro", uri=True)
            try:
                r = con.execute("SELECT display_name FROM users WHERE username=?",
                                (uzytkownik,)).fetchone()
            finally:
                con.close()
            return (r[0] if r and r[0] else uzytkownik) or ""
        except Exception:
            return ""

    def _pliki_rysunku(self, symbol, projekty=None):
        """
        Pliki rysunku (PDF/DXF/STEP…) z serwera — tą samą drogą co RFQ.
        Woła _find_files_for_drawing z arkusza głównego, żeby nie dublować
        logiki szukania po katalogach projektu.

        `projekty` — numery z kolumny „Projekt". Szukanie w arkuszu startuje
        od projektu tam otwartego, a ZD zbiera detale z kilku projektów naraz,
        więc bez tego rysunek bywał szukany nie tam, gdzie powstał
        (zgłoszone 05.09.2026). Przekazujemy je dalej; gdy arkusz jest starszy
        i ich nie przyjmuje, szukanie leci po staremu.
        """
        okno = self.master
        szukaj = getattr(okno, "_find_files_for_drawing", None)
        if not callable(szukaj) or not symbol:
            return []
        try:
            if projekty:
                try:
                    return szukaj(symbol, projekty)
                except TypeError:
                    pass                # starsza sygnatura bez `projekty`
            return szukaj(symbol)
        except Exception as e:
            print(f"⚠️  Szukanie plików dla {symbol}: {e}")
            return []

    def _szukaj_hurtem_biblioteka(self, numery, zrodlo="library"):
        """Jedno przejście po dysku dla wszystkich brakujących pozycji.

        Skan pozycja po pozycji to tyle przemiałów dysku sieciowego, ile
        brakujących rysunków — a katalog i tak trzeba przeczytać w całości.

        `zrodlo`: "library" (dysk B: — komponenty wspólne) albo "server"
        (dysk V: — całe drzewo projektów, wolniej, ale szerzej).
        """
        okno = self.master
        skanuj = getattr(okno, "_rfq_deep_scan_wiele", None)
        if not callable(skanuj):
            return {}
        glowny = sys.modules.get(type(okno).__module__)
        if zrodlo == "server":
            korzen = getattr(glowny, "SERVER_DIR", None)
            tytul = "Skanowanie serwera"
        else:
            korzen = getattr(glowny, "LIBRARY_ROOT", None)
            tytul = "Skanowanie biblioteki"
        if not korzen:
            print(f"⚠️  Brak ścieżki dla źródła {zrodlo!r}")
            return {}
        try:
            return skanuj(Path(korzen), numery, tytul, parent=self) or {}
        except Exception as e:
            print(f"⚠️  Skan zbiorczy ({zrodlo}): {e}")
            return {}

    def _szukaj_dalej_rysunku(self, pozycja):
        """Alternatywne źródło plików — biblioteka albo głęboki skan serwera.

        Ta sama droga co „Szukaj dalej…" w oknie RFQ: pytamy SKĄD szukać,
        potem skanujemy i — gdy nic nie ma — pytamy ponownie, żeby user mógł
        spróbować drugiego źródła bez zamykania okna.
        """
        okno = self.master
        pytaj = getattr(okno, "_ask_rfq_scan_source", None)
        skanuj = getattr(okno, "_rfq_deep_scan", None)
        if not callable(pytaj) or not callable(skanuj):
            return []

        # Ścieżki biorę z modułu głównego przez sys.modules, a nie importem —
        # subiekt_zamowienia jest importowane PRZEZ RM_BAZA, więc import
        # w drugą stronę zrobiłby cykl.
        glowny = sys.modules.get(type(okno).__module__)
        biblioteka = getattr(glowny, "LIBRARY_ROOT", None)
        serwer = getattr(glowny, "SERVER_DIR", None)

        numer = pozycja.get("drawing_no", "")
        while True:
            try:
                zrodlo = pytaj(numer, self)
                if zrodlo is None:
                    return []
                korzen = Path(biblioteka if zrodlo == "library" else serwer or "")
                if not korzen or str(korzen) in ("", "."):
                    print(f"⚠️  Brak ścieżki dla źródła {zrodlo!r}")
                    return []
                tytul = ("Skanowanie biblioteki" if zrodlo == "library"
                         else "Skanowanie serwera")
                znalezione = skanuj(korzen, numer, tytul, parent=self) or []
            except Exception as e:
                print(f"⚠️  Szukanie dalej dla {numer}: {e}")
                return []
            if znalezione:
                return znalezione
            if not messagebox.askyesno(
                    "Nie znaleziono",
                    f"Nie znaleziono plików dla:\n{numer}\n\nSzukać w innym miejscu?",
                    parent=self):
                return []

    def _usun_zk(self):
        """Okno z listą ZAMÓWIEŃ OD KLIENTÓW (ZK) do usunięcia.

        ZK nie ma na liście zapotrzebowania (to zamówienia klientów, nie
        dostawców), więc numery pobieramy wprost z Subiekta — tym samym
        odczytem, którego używa okno przeglądu dokumentów.

        ⚠️ Kasuj ZK DOPIERO PO ZD. ZD powstaje z powiązaniem do ZK, więc
        usunięcie ZK jako pierwszego zostawia osierocone zamówienie do
        dostawcy, a Subiekt potrafi wtedy odmówić skasowania samego ZK.
        """
        # Numery ZK są w kolumnie ZK tego okna (zapotrzebowanie liczy się
        # właśnie z nich), więc nie ma po co pytać Subiekta drugi raz.
        # Kolumna bywa zbiorcza i z ilościami — _numery_zd czyści jedno i drugie.
        zk = {}
        for w in self.wszystkie:
            for nr in _numery_zd(w.get("zk")):
                zk.setdefault(nr, {"projekty": set(), "poz": []})
                zk[nr]["poz"].append(w)
                for p in (w.get("projekty") or "").split(", "):
                    if p:
                        zk[nr]["projekty"].add(p)
        if not zk:
            messagebox.showinfo("Usuń ZK",
                                "Na liście nie ma pozycji powiązanych z ZK.",
                                parent=self)
            return

        dlg = tk.Toplevel(self)
        dlg.title("Usuń zamówienia od klientów (ZK)")
        dlg.transient(self)
        dlg.grab_set()
        wysrodkuj(dlg, self, 620, 420)

        tk.Label(dlg, text="Zaznacz dokumenty do usunięcia:",
                 font=("Arial", 9, "bold")).pack(padx=14, pady=(12, 2), anchor="w")
        tk.Label(dlg, text="Usuwany jest CAŁY dokument ze wszystkimi pozycjami. "
                           "Operacja nieodwracalna.",
                 font=("Arial", 8), fg="#c0392b").pack(padx=14, anchor="w")
        tk.Label(dlg, text="Najpierw usuń powiązane ZD — inaczej Subiekt może "
                           "odmówić skasowania ZK.",
                 font=("Arial", 8), fg="#e67e22").pack(padx=14, anchor="w", pady=(2, 0))

        ramka = tk.Frame(dlg)
        ramka.pack(fill=tk.BOTH, expand=True, padx=14, pady=8)
        canvas = tk.Canvas(ramka, borderwidth=0, highlightthickness=0)
        sb = ttk.Scrollbar(ramka, orient="vertical", command=canvas.yview)
        wnetrze = tk.Frame(canvas)
        wnetrze.bind("<Configure>",
                     lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=wnetrze, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Wstępnie zaznaczone: ZK z wiersza pod kursorem — „usuń to, na co patrzę".
        wstepne = set()
        try:
            for r in self.sheet.get_selected_rows(get_cells_as_rows=True):
                if 0 <= r < len(self.widoczne):
                    wstepne.update(_numery_zd(self.widoczne[r].get("zk")))
        except Exception:
            pass

        zmienne = {}
        for nr in sorted(zk):
            info = zk[nr]
            v = tk.IntVar(value=1 if nr in wstepne else 0)
            zmienne[nr] = v
            projekty = ", ".join(sorted(info["projekty"]))
            tekst = (f"{nr}   —   {len(info['poz'])} poz. na liście"
                     + (f"   (projekt {projekty})" if projekty else ""))
            tk.Checkbutton(wnetrze, text=tekst, variable=v, anchor="w",
                           font=("Arial", 9)).pack(fill=tk.X, pady=1)
            # Co widać na liście z tego ZK — kilka symboli dla orientacji.
            symbole = ", ".join(w["symbol"] for w in info["poz"][:6])
            if len(info["poz"]) > 6:
                symbole += ", …"
            tk.Label(wnetrze, text=f"        {symbole}", anchor="w",
                     fg="#7f8c8d", font=("Arial", 8)).pack(fill=tk.X, pady=(0, 4))

        wybrane = {}

        def zatwierdz():
            wybrane["numery"] = sorted(nr for nr, v in zmienne.items() if v.get())
            dlg.destroy()

        box = tk.Frame(dlg)
        box.pack(pady=(0, 12))
        tk.Button(box, text="Usuń zaznaczone", command=zatwierdz, bg="#c0392b",
                  fg="white", font=("Arial", 9, "bold"), padx=16, pady=4).pack(side=tk.LEFT, padx=4)
        tk.Button(box, text="Anuluj", command=dlg.destroy,
                  font=("Arial", 9), padx=14, pady=4).pack(side=tk.LEFT, padx=4)

        self.wait_window(dlg)
        numery = wybrane.get("numery") or []
        if not numery:
            return

        opis = "\n".join(f"  • {nr} ({len(zk[nr]['poz'])} poz. na liście)"
                         for nr in numery)
        if not messagebox.askyesno(
                "Usunięcie ZK — potwierdzenie",
                "Baza PRODUKCYJNA. Operacja NIEODWRACALNA.\n\n"
                f"Zostaną usunięte dokumenty ({len(numery)}):\n{opis}\n\n"
                "Zapotrzebowanie policzy się od nowa bez tych zamówień.\n\nUsunąć?",
                parent=self, icon="warning"):
            return

        self.status.config(text="Usuwam ZK…")
        threading.Thread(target=self._usun_worker, args=(numery,), daemon=True).start()

    def _usun_zd(self):
        """Okno z listą DOKUMENTÓW ZD do usunięcia.

        Zaznacza się numery ZD, nie pozycje — bo kasowany jest cały dokument.
        Wcześniej działało to na wierszach arkusza i było mylące: zaznaczałeś
        jedną pozycję, a znikało całe zamówienie (zgłoszone 04.09.2026).
        """
        # Kolumna ZD pokazuje numer Z ILOŚCIĄ i bywa zbiorcza — do wysyłki
        # i usuwania idzie CZYSTY numer dokumentu (patrz _numery_zd).
        zd = {}
        for w in self.wszystkie:
            for nr in _numery_zd(w.get("zd")):
                zd.setdefault(nr, {"dostawca": w.get("dostawca", ""),
                                   "data": w.get("zd_data", ""), "poz": []})
                zd[nr]["poz"].append(w)
        if not zd:
            messagebox.showinfo("Usuń ZD", "Na liście nie ma żadnych zamówień do dostawców.",
                                parent=self)
            return

        # Wstępnie zaznaczone: ZD z wiersza, na którym stoi kursor — częsty
        # przypadek to „usuń to, na co patrzę".
        wstepne = set()
        try:
            for r in self.sheet.get_selected_rows(get_cells_as_rows=True):
                if 0 <= r < len(self.widoczne) and self.widoczne[r].get("zd"):
                    wstepne.add(self.widoczne[r]["zd"])
        except Exception:
            pass

        dlg = tk.Toplevel(self)
        dlg.title("Usuń zamówienia do dostawców")
        dlg.transient(self)
        dlg.grab_set()
        wysrodkuj(dlg, self, 560, 380)

        tk.Label(dlg, text="Zaznacz dokumenty do usunięcia:",
                 font=("Arial", 9, "bold")).pack(padx=14, pady=(12, 2), anchor="w")
        tk.Label(dlg, text="Usuwany jest CAŁY dokument ze wszystkimi pozycjami. "
                           "Operacja nieodwracalna.",
                 font=("Arial", 8), fg="#c0392b").pack(padx=14, anchor="w")

        ramka = tk.Frame(dlg)
        ramka.pack(fill=tk.BOTH, expand=True, padx=14, pady=8)
        canvas = tk.Canvas(ramka, borderwidth=0, highlightthickness=0)
        sb = ttk.Scrollbar(ramka, orient="vertical", command=canvas.yview)
        wnetrze = tk.Frame(canvas)
        wnetrze.bind("<Configure>",
                     lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=wnetrze, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        zmienne = {}
        for nr in sorted(zd):
            info = zd[nr]
            v = tk.IntVar(value=1 if nr in wstepne else 0)
            zmienne[nr] = v
            tekst = (f"{nr}   —   {info['dostawca'] or '(bez dostawcy)'}   "
                     f"({len(info['poz'])} poz."
                     + (f", {info['data']}" if info["data"] else "") + ")")
            tk.Checkbutton(wnetrze, text=tekst, variable=v, anchor="w",
                           font=("Arial", 9)).pack(fill=tk.X, pady=1)
            # Co dokładnie zniknie razem z dokumentem.
            symbole = ", ".join(w["symbol"] for w in info["poz"][:6])
            if len(info["poz"]) > 6:
                symbole += ", …"
            tk.Label(wnetrze, text=f"        {symbole}", anchor="w",
                     fg="#7f8c8d", font=("Arial", 8)).pack(fill=tk.X, pady=(0, 4))

        wybrane = {}

        def zatwierdz():
            wybrane["numery"] = sorted(nr for nr, v in zmienne.items() if v.get())
            dlg.destroy()

        box = tk.Frame(dlg)
        box.pack(pady=(0, 12))
        tk.Button(box, text="Usuń zaznaczone", command=zatwierdz, bg="#c0392b",
                  fg="white", font=("Arial", 9, "bold"), padx=16, pady=4).pack(side=tk.LEFT, padx=4)
        tk.Button(box, text="Anuluj", command=dlg.destroy,
                  font=("Arial", 9), padx=14, pady=4).pack(side=tk.LEFT, padx=4)

        self.wait_window(dlg)
        numery = wybrane.get("numery") or []
        if not numery:
            return

        opis = "\n".join(f"  • {nr} — {zd[nr]['dostawca']} ({len(zd[nr]['poz'])} poz.)"
                         for nr in numery)
        ok = messagebox.askyesno(
            "Usunięcie ZD — potwierdzenie",
            "Baza PRODUKCYJNA. Operacja NIEODWRACALNA.\n\n"
            f"Zostaną usunięte dokumenty ({len(numery)}):\n{opis}\n\n"
            "Pozycje wrócą do zapotrzebowania jako braki.\n\nUsunąć?",
            parent=self, icon="warning")
        if not ok:
            return

        self.status.config(text="Usuwam ZD…")
        threading.Thread(target=self._usun_worker, args=(numery,), daemon=True).start()

    def _usun_worker(self, numery):
        try:
            wynik = usun_zd(numery, zapisz=True)
            self.after(0, lambda: self._usun_done(wynik, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._usun_done(None, err))

    def _usun_done(self, wynik, error):
        # Wspólne dla ZD i ZK — most kasuje oba typy, więc komunikaty mówią
        # „dokumenty", a rodzaj widać przy każdym numerze w szczegółach.
        if error:
            self.status.config(text="Nie udało się usunąć dokumentów.")
            messagebox.showerror("Usuwanie dokumentów", error, parent=self)
            return
        kroki = wynik.get("kroki", [])
        usuniete = [k for k in kroki if k.get("Status") == "usuniete"]
        bledy = [k for k in kroki if k.get("Status") == "blad"]
        zapisz_log(wynik)

        lines = [f"Usunięte dokumenty: {len(usuniete)}"]
        lines += [f"  • {k['Numer']} — {k.get('Szczegoly') or ''}" for k in usuniete[:12]]
        if bledy:
            lines += ["", f"Nieusunięte ({len(bledy)}):"]
            lines += [f"  • {k['Numer']}: {k.get('Szczegoly') or ''}" for k in bledy[:8]]
        (messagebox.showwarning if bledy else messagebox.showinfo)(
            "Usuwanie ZD", "\n".join(lines), parent=self)
        self._load_async()      # pozycje wracają do zapotrzebowania

    # ── szukanie dostawcy w filtrze ────────────────────────────────────────
    def _szukaj_dostawcy(self):
        """Wpisany tekst zawęża listę dostawców w combo obok.

        Dopasowanie po FRAGMENCIE, nie od początku: „quay” trafia w „QUAY”
        BIURO HANDLOWO-USŁUGOWE…, a „sasin” w ADR-CNC Adrian Sasin.
        Jedno trafienie ustawia filtr od razu — po to się szuka; przy wielu
        combo pokazuje tylko pasujące i wybiera się z rozwinięcia.
        Puste pole przywraca pełną listę, nie ruszając bieżącego filtra.
        """
        if not hasattr(self, "combo_dostawca"):
            return
        tekst = self.dostawca_szukaj_var.get().strip().lower()
        if tekst == getattr(self, "_dost_placeholder", "").lower():
            tekst = ""
        if not tekst:
            self.combo_dostawca["values"] = self._dostawcy_wszyscy
            return
        pasuje = [d for d in self._dostawcy_wszyscy
                  if tekst in d.lower() and d not in (FILTR_WSZYSCY, FILTR_BRAK_DOSTAWCY)]
        if not pasuje:
            # Brak trafień: zostawiamy pełną listę i mówimy o tym w pasku —
            # ciche wyczyszczenie wyglądałoby jak zawieszenie.
            self.combo_dostawca["values"] = self._dostawcy_wszyscy
            self.status.config(text=f"Brak dostawcy pasującego do „{tekst}”.")
            return
        self.combo_dostawca["values"] = [FILTR_WSZYSCY] + pasuje
        if len(pasuje) == 1:
            self.filter_dostawca_var.set(pasuje[0])
            # Dostawca wybrany — pole szukania spełniło rolę i się sprząta.
            # Zostawiony tekst wyglądał, jakby filtr wciąż był zawężony
            # (zgłoszone 05.09.2026).
            self.after(1, self._wyczysc_szukaj_dostawcy)
            self._refill()
        else:
            self.status.config(text=f"Pasuje {len(pasuje)} dostawców — wybierz z listy.")

    def _dostawca_wybrany(self, _event=None):
        """Wybór z rozwiniętej listy — pole szukania już niepotrzebne."""
        self._wyczysc_szukaj_dostawcy()
        self._refill()

    def _wyczysc_szukaj_dostawcy(self):
        """Czyści pole szukania i przywraca pełną listę w combo.

        Wołane po wybraniu dostawcy: tekst w polu przestaje cokolwiek
        znaczyć, a przycięta lista rozwijana utrudniałaby wybór następnego.
        """
        try:
            self.combo_dostawca["values"] = self._dostawcy_wszyscy
            if self.ent_dost_szukaj.focus_get() is not self.ent_dost_szukaj:
                self.ent_dost_szukaj.config(fg="#95a5a6")
                self.dostawca_szukaj_var.set(self._dost_placeholder)
            else:
                self.dostawca_szukaj_var.set("")   # kursor w polu — zostaw puste
        except Exception:
            pass

    # ── wydruk ZD ──────────────────────────────────────────────────────────
    def _katalog_pdf(self):
        """Wspólny katalog wydruków na Y:, nie lokalny %TEMP% — ten sam,
        z którego korzystają okna wysyłki i przeglądu dokumentów."""
        import subiekt_wyslij_zd
        return subiekt_wyslij_zd._katalog_pdf_domyslny()

    def _plik_pdf(self, kolumna_zd):
        """Ścieżka gotowego wydruku PIERWSZEGO ZD z kolumny albo None.

        Nazwa pliku powstaje z numeru dokumentu tak samo jak w moście, więc
        nie trzeba niczego zapamiętywać — wystarczy sprawdzić katalog.
        Kolumna ZD trzyma numer Z ILOŚCIĄ i bywa zbiorcza, stąd _numery_zd.
        """
        numery = _numery_zd(kolumna_zd)
        if not numery:
            return None
        try:
            nazwa = numery[0].replace("/", "-").replace("\\", "-").replace(" ", "_") + ".pdf"
            sciezka = self._katalog_pdf() / nazwa
            return sciezka if sciezka.exists() else None
        except Exception:
            return None        # brak dostępu do Y: nie może wywalić rysowania listy

    def _podglad_pdf(self, wymus_nowy=False):
        """Wydruk ZD z wiersza pod kursorem — ten sam, który idzie mailem.

        Gotowy plik otwiera się NATYCHMIAST; generowanie z Subiekta trwa ~11 s
        (start mostu i logowanie do Sfery), więc robimy je tylko, gdy wydruku
        jeszcze nie ma albo ktoś chce świeży.
        """
        w = None
        try:
            for r in self.sheet.get_selected_rows(get_cells_as_rows=True):
                if 0 <= r < len(self.widoczne):
                    w = self.widoczne[r]
                    break
        except Exception:
            pass
        numery = _numery_zd(w.get("zd")) if w else []
        if not numery:
            messagebox.showinfo("Podgląd PDF",
                                "Ustaw kursor na wierszu, który ma już zamówienie (kolumna ZD).",
                                parent=self)
            return
        numer = numery[0]

        if not wymus_nowy:
            gotowy = self._plik_pdf(w.get("zd"))
            if gotowy:
                from datetime import datetime as _dt
                kiedy = _dt.fromtimestamp(gotowy.stat().st_mtime)
                os.startfile(str(gotowy))
                self.status.config(
                    text=f"Otwarto wydruk {numer} z {kiedy:%d.%m.%Y %H:%M} "
                         f"(gotowy plik; „Nowy PDF” wygeneruje aktualny).")
                return

        self.start_kreciolek(f"Generuję PDF {numer} z Subiekta")
        threading.Thread(target=self._podglad_pdf_worker, args=(numer,),
                         daemon=True).start()

    def _podglad_pdf_worker(self, numer):
        """Eksport wydruku w tle — most odpowiada ~11 s, GUI ma nie zamarzać."""
        plik, blad = None, ""
        try:
            import subiekt_wyslij_zd
            pdfy, bledy = subiekt_wyslij_zd.eksportuj_pdf([numer], self._katalog_pdf())
            plik = (pdfy.get(numer) or {}).get("plik")
            blad = bledy[0] if bledy else ""
        except Exception as e:
            blad = str(e)
        self.after(0, lambda: self._podglad_pdf_done(numer, plik, blad))

    def _podglad_pdf_done(self, numer, plik, blad):
        self.stop_kreciolek()
        if not plik or not Path(plik).exists():
            self.status.config(text="PDF nie powstał.")
            messagebox.showwarning("Podgląd PDF",
                                   f"Nie udało się wygenerować wydruku {numer}."
                                   + (f"{NL}{NL}{blad}" if blad else ""), parent=self)
            return
        try:
            os.startfile(str(plik))
        except Exception as e:
            messagebox.showerror("Podgląd PDF", str(e), parent=self)
            return
        self.status.config(text=f"Otwarto podgląd {numer}.")
        self._refill()             # kolumna PDF ma pokazać 📄 dla świeżego wydruku

    def _on_dblclick(self, event):
        """Dwuklik: kolumna Dostawca → wybór podmiotu, kolumna PDF → wydruk."""
        if not self.sheet:
            return
        try:
            r = self.sheet.identify_row(event, allow_end=False)
            c = self.sheet.identify_column(event, allow_end=False)
        except Exception:
            return
        if r is None or not (0 <= r < len(self.widoczne)):
            return
        if c == self.COL_PDF:
            self._podglad_pdf()
            return
        if c != self.COL_DOSTAWCA:
            return
        self._wybierz_dostawce([r])

    def _wybierz_dostawce(self, rows):
        """Okno wyboru kontrahenta z wyszukiwarką (podmiotów bywa ~600)."""
        # Wiersze z ZD są zamknięte na edycję: dostawca jest już zapisany
        # w dokumencie Subiekta i zmiana w arkuszu niczego by tam nie zmieniła.
        zamowione = [r for r in rows
                     if 0 <= r < len(self.widoczne) and self.widoczne[r].get("zd")]
        if zamowione:
            nry = sorted({self.widoczne[r]["zd"] for r in zamowione})
            messagebox.showinfo(
                "Dostawca",
                f"Te pozycje są już zamówione ({', '.join(nry)}).\n\n"
                "Dostawca jest zapisany w dokumencie Subiekta — zmiana w arkuszu\n"
                "nic by tam nie zmieniła.\n\n"
                "Żeby zamówić u kogoś innego: PPM → „Usuń ZD”, potem utwórz nowe.",
                parent=self)
            return

        if not self.podmioty:
            messagebox.showinfo("Dostawca",
                                "Lista podmiotów z Subiekta jest pusta — odśwież okno.",
                                parent=self)
            return

        # Podpowiedź: co RM_BAZA miała w polu Dostawca dla tych wierszy —
        # user zwykle szuka właśnie tego (np. „AMBProdukt lasery" → AMB PRODUKT).
        z_bom = sorted({self.widoczne[r].get("dostawca_bom", "")
                        for r in rows if 0 <= r < len(self.widoczne)} - {""})

        dlg = tk.Toplevel(self)
        dlg.title(f"Dostawca dla {len(rows)} " + ("pozycji" if len(rows) > 1 else "pozycji"))
        dlg.transient(self)
        dlg.grab_set()
        wysrodkuj(dlg, self, 520, 505)   # +75 px na ramkę ostrzeżenia (3 linie)

        # Wybór stąd trafia DO ZD W SUBIEKCIE (przez _utworz_zd → most). Do
        # arkusza RM_BAZA wraca dopiero PO WYSŁANIU ZD — razem z „Zamówiono"
        # i terminem (zd_zamowione_pozycje, nakładane przy locku projektu).
        # Do tego czasu arkusz pokazuje poprzedniego dostawcę — stąd
        # informacja, nie już czerwone ostrzeżenie (złagodzone 05.09.2026;
        # wcześniej dostawca nie wracał wcale).
        ostrz = tk.Frame(dlg, bg="#fdf2e0")
        ostrz.pack(fill=tk.X, padx=14, pady=(10, 0))
        tk.Label(ostrz, text="ℹ Dostawca wybrany tutaj trafi do ZD w Subiekcie.",
                 bg="#fdf2e0", fg="#8a5a00", font=("Arial", 9, "bold"),
                 anchor="w").pack(fill=tk.X, padx=8, pady=(5, 0))
        tk.Label(ostrz, text="Do arkusza projektu (kolumna Dostawca) wróci razem "
                             "z „Zamówiono” i terminem\ndopiero po WYSŁANIU zamówienia — "
                             "do tego czasu arkusz pokazuje poprzedniego.\n"
                             "Na stałe dostawcę ustawia się w arkuszu RM_BAZA.",
                 bg="#fdf2e0", fg="#8a5a00", font=("Arial", 8), justify="left",
                 anchor="w").pack(fill=tk.X, padx=8, pady=(0, 5))

        if z_bom:
            tk.Label(dlg, text="wg BOM: " + ", ".join(z_bom[:3]),
                     fg="#7f8c8d", font=("Arial", 8)).pack(padx=14, pady=(8, 0), anchor="w")

        tk.Label(dlg, text="Szukaj kontrahenta:", font=("Arial", 9)).pack(
            padx=14, pady=(8, 2), anchor="w")
        var_szukaj = tk.StringVar(value=(z_bom[0].split()[0] if z_bom else ""))
        ent = tk.Entry(dlg, textvariable=var_szukaj, font=("Arial", 9))
        ent.pack(fill=tk.X, padx=14)
        ent.focus_set()
        ent.select_range(0, tk.END)

        ramka = tk.Frame(dlg)
        ramka.pack(fill=tk.BOTH, expand=True, padx=14, pady=8)
        lista = tk.Listbox(ramka, font=("Arial", 9))
        sb = ttk.Scrollbar(ramka, orient="vertical", command=lista.yview)
        lista.configure(yscrollcommand=sb.set)
        lista.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        def odswiez(*_):
            q = var_szukaj.get().strip().lower()
            lista.delete(0, tk.END)
            for p in self.podmioty:
                if not q or q in p.lower():
                    lista.insert(tk.END, p)
            if lista.size():
                lista.selection_set(0)

        var_szukaj.trace_add("write", odswiez)
        odswiez()

        def zastosuj(*_):
            sel = lista.curselection()
            if not sel:
                return
            nazwa = lista.get(sel[0])
            for r in rows:
                if 0 <= r < len(self.widoczne):
                    self.widoczne[r]["dostawca"] = nazwa
                    # Wybór człowieka — inny kolor niż podpowiedź automatu.
                    self.widoczne[r]["zrodlo_dostawcy"] = "reczny" if nazwa else ""
            dlg.destroy()
            self._refill()

        def wyczysc():
            # Tylko dla pozycji jeszcze nie zamówionych. Przy wierszu z ZD
            # wyczyszczenie dostawcy kłamałoby: dokument w Subiekcie zostaje,
            # a arkusz pokazywałby pozycję jako „bez dostawcy".
            zamowione = [r for r in rows
                         if 0 <= r < len(self.widoczne) and self.widoczne[r].get("zd")]
            if zamowione:
                messagebox.showwarning(
                    "Dostawca",
                    f"{len(zamowione)} z zaznaczonych pozycji ma już ZD.\n\n"
                    "Dostawcy nie da się usunąć z arkusza — dokument w Subiekcie\n"
                    "i tak zostanie. Żeby zmienić dostawcę: PPM → „Usuń ZD”,\n"
                    "a potem utwórz nowe zamówienie.",
                    parent=dlg)
                return
            for r in rows:
                if 0 <= r < len(self.widoczne):
                    self.widoczne[r]["dostawca"] = ""
            dlg.destroy()
            self._refill()

        box = tk.Frame(dlg)
        box.pack(pady=(0, 12))
        tk.Button(box, text="Ustaw", command=zastosuj, bg="#27ae60", fg="white",
                  font=("Arial", 9), padx=16, pady=3).pack(side=tk.LEFT, padx=4)
        tk.Button(box, text="Wyczyść", command=wyczysc,
                  font=("Arial", 9), padx=12, pady=3).pack(side=tk.LEFT, padx=4)
        tk.Button(box, text="Anuluj", command=dlg.destroy,
                  font=("Arial", 9), padx=12, pady=3).pack(side=tk.LEFT, padx=4)
        lista.bind("<Double-Button-1>", zastosuj)
        ent.bind("<Return>", zastosuj)
        ent.bind("<Down>", lambda _e: (lista.focus_set(), lista.selection_set(0)))

    def _on_click(self, event):
        """Klik w kolumnę ✓ przełącza wiersz. Shift+klik przełącza CAŁY ZAKRES.

        Wcześniej Shift w tej kolumnie nic nie stawiał — tylko podświetlał
        wiersze w arkuszu, a ✓ trzeba było dostawiać osobno przez PPM. Przy
        276 pozycjach to znaczyło klikanie jednej po drugiej (zgłoszone
        05.09.2026). Teraz działa jak w każdej liście z checkboxami:
        klik pierwszej, Shift+klik ostatniej i cały zakres zmienia stan.

        Ctrl zostawiamy arkuszowi — to jego sposób na zaznaczanie
        pojedynczych, rozproszonych wierszy do PPM.
        """
        if not self.sheet:
            return
        if event.state & 0x0004:                              # Ctrl — arkusz
            return
        shift = bool(event.state & 0x0001)
        try:
            r = self.sheet.identify_row(event, allow_end=False)
            c = self.sheet.identify_column(event, allow_end=False)
        except Exception:
            return
        if r is None or c != self.COL_SEL or not (0 <= r < len(self.widoczne)):
            return

        if shift and self._ostatni_klik is not None:
            od, do = sorted((self._ostatni_klik, r))
            if 0 <= od and do < len(self.widoczne):
                # Stan bierzemy z wiersza, w który kliknięto — dzięki temu
                # Shift+klik zarówno zaznacza, jak i odznacza cały zakres.
                nowy = not self.widoczne[r]["sel"]
                for i in range(od, do + 1):
                    self.widoczne[i]["sel"] = nowy
                self._ostatni_klik = r
                self._refill()
                return

        self.widoczne[r]["sel"] = not self.widoczne[r]["sel"]
        self._ostatni_klik = r
        self._refill()

    def _on_edit(self, _event=None):
        """Edycja w miejscu: dostawca i ilość wracają do modelu."""
        if not self.sheet:
            return
        try:
            dane = self.sheet.get_sheet_data()
        except Exception:
            return
        for i, w in enumerate(self.widoczne):
            if i >= len(dane):
                break
            w["dostawca"] = str(dane[i][self.COL_DOSTAWCA] or "").strip()
            try:
                w["ilosc"] = float(str(dane[i][self.COL_ILOSC]).replace(",", "."))
            except (TypeError, ValueError):
                pass
        self._przelicz()

    # ── tworzenie ZD ───────────────────────────────────────────────────────
    def _utworz_zd(self):
        zazn = [w for w in self.wszystkie if w["sel"]]
        if not zazn:
            messagebox.showwarning("ZD", "Nie zaznaczono żadnej pozycji.", parent=self)
            return

        # Pozycje pokryte ze stanu — nie ma czego zamawiać, ZD z ilością 0
        # byłoby bez sensu.
        ze_stanu = [w for w in zazn if w["ilosc"] <= 0]
        if ze_stanu:
            messagebox.showwarning(
                "ZD",
                f"{len(ze_stanu)} zaznaczonych pozycji jest w całości pokrytych stanem "
                "magazynu (kolumna „Kupić” = 0).\n\n"
                "Nie ma czego zamawiać — odznacz je albo wpisz ilość w kolumnie „Kupić”.",
                parent=self)
            return

        bez_dost = [w for w in zazn if not w["dostawca"]]
        if bez_dost:
            messagebox.showwarning(
                "ZD",
                f"{len(bez_dost)} zaznaczonych pozycji nie ma dostawcy.\n\n"
                "ZD powstaje per dostawca, więc te pozycje nie mają gdzie trafić.\n"
                "Uzupełnij kolumnę Dostawca (edycja w arkuszu) albo je odznacz.",
                parent=self)
            return

        dostawcy = sorted({w["dostawca"] for w in zazn})
        ok = messagebox.askyesno(
            "Utworzenie ZD — potwierdzenie",
            f"Baza PRODUKCYJNA.\n\n"
            f"Powstanie {len(dostawcy)} zamówień do dostawców:\n"
            + "\n".join(f"  • {d}: {sum(1 for w in zazn if w['dostawca'] == d)} poz."
                        for d in dostawcy[:10])
            + ("\n  …" if len(dostawcy) > 10 else "")
            + f"\n\nŁącznie pozycji: {len(zazn)}\n\n"
            "ZD można w Subiekcie usunąć.\n\nUtworzyć?",
            parent=self, icon="warning")
        if not ok:
            return

        self.btn_zd.config(state=tk.DISABLED)
        self.status.config(text="Tworzę ZD w Subiekcie — nie zamykaj okna…")
        poz = [{"symbol": w["symbol"], "ilosc": w["ilosc"], "dostawca": w["dostawca"],
                "reczna": bool(w.get("reczna"))}
               for w in zazn]
        threading.Thread(target=self._zd_worker, args=(poz,), daemon=True).start()

    def _zd_worker(self, pozycje):
        try:
            wynik = utworz_zd(pozycje)
            self.after(0, lambda: self._zd_done(wynik, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._zd_done(None, err))

    def _zd_done(self, wynik, error):
        self.btn_zd.config(state=tk.NORMAL)
        if error:
            self.status.config(text="Nie udało się utworzyć ZD.")
            messagebox.showerror("ZD", error, parent=self)
            return

        utworzone = wynik.get("zd", [])
        bledy = [k for k in wynik.get("kroki", []) if k.get("Status") == "blad"]
        log = zapisz_log(wynik)

        # Numer ZD wprost do arkusza — user ma widzieć w tabelce, co poszło
        # i pod jakim numerem, a nie tylko w oknie komunikatu. ZD powstaje
        # per dostawca, więc numer trafia do wszystkich pozycji tego dostawcy.
        po_dostawcy = {(z.get("Dostawca") or "").strip(): z.get("Numer", "")
                       for z in utworzone}
        oznaczone = 0
        for w in self.wszystkie:
            if not w["sel"]:
                continue
            numer = po_dostawcy.get((w["dostawca"] or "").strip())
            if numer:
                w["zd"] = numer
                w["zd_data"] = datetime.now().strftime("%Y-%m-%d")
                w["sel"] = False          # zamówione — zdejmujemy zaznaczenie
                oznaczone += 1

        # ŚWIADOMIE bez _load_async(): odświeżenie zabrałoby te pozycje
        # z zapotrzebowania (Subiekt uzna je za pokryte) i numery ZD zniknęłyby
        # z oczu, zanim user zdąży je zobaczyć. Odświeża ręcznie, przyciskiem.
        self._refill()

        lines = [f"Utworzone ZD: {len(utworzone)}"]
        lines += [f"  • {z.get('Numer', '?')} — {z.get('Dostawca', '?')}"
                  for z in utworzone[:12]]
        if bledy:
            lines += ["", f"Błędy ({len(bledy)}):"]
            lines += [f"  • {b.get('Symbol', '')}: {b.get('Szczegoly', '')}" for b in bledy[:8]]
        if log:
            lines += ["", f"Log: {log}"]

        (messagebox.showwarning if bledy else messagebox.showinfo)(
            "ZD utworzone", "\n".join(lines), parent=self)
        self.status.config(
            text=f"Utworzono {len(utworzone)} ZD ({oznaczone} pozycji oznaczonych). "
                 "„Odśwież” pobierze aktualne zapotrzebowanie — zamówione pozycje z niego znikną.")


def open_window(parent, project_id=None, project_name=None):
    """Punkt wejścia dla RM_BAZA. Bez projektu pokazuje braki ze wszystkich ZK."""
    return ZamowieniaWindow(parent, project_id, project_name)


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    pname = sys.argv[2] if len(sys.argv) > 2 else None
    root = tk.Tk()
    root.withdraw()
    w = open_window(root, pid, pname)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
