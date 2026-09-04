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
import subprocess
import sqlite3
import sys
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

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
        data = json.load(f)

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
    } for z in data.get("zamowione", [])]

    # Podmioty przychodzą tym samym wywołaniem — okno potrzebuje ich do listy
    # wyboru dostawcy, a osobne uruchomienie mostu kosztowałoby drugie ~8 s.
    return pozycje, data.get("podmioty", []), zamowione


def stan_pozycji(symbole, projekt=None, timeout=TIMEOUT_S):
    """{symbol: {kartoteka, stan, zk, zd, dostawca, status_zd}} — dla kolumny
    SUBIEKT w arkuszu głównym RM_BAZA.

    Trzy stany naraz, bo to trzy różne informacje dla planującego produkcję:
    czy asortyment w ogóle istnieje w Subiekcie, czy jest na liście projektu
    (ZK) i czy zamówiony u dostawcy (ZD).
    """
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")
    symbole = [str(s).strip() for s in (symbole or []) if str(s).strip()]
    if not symbole:
        return {}

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
        data = json.load(f)
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


def _nazwy_dostawcow():
    """{supplier_id: nazwa} z bazy głównej RM_BAZA."""
    master = os.path.join(os.path.dirname(PROJECTS_DIR.rstrip("\\/")), "master.sqlite")
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
    master = os.path.join(os.path.dirname(PROJECTS_DIR.rstrip("\\/")), "master.sqlite")
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

        sup = dostawcy.get(r[-1]) if has_sup else None
        out[klucz.strip().upper()] = {
            "nazwa": nazwa,
            "typ": str(typ).strip().upper(),
            "dostawca": str(sup).strip() if sup else "",
            # Numer projektu — dla pozycji już zamówionych to jedyne źródło
            # przypisania do projektu (nie mają już powiązania przez ZK).
            "projekt": numer_projektu or "",
        }
    return out


def numer_projektu_z_uwag(uwagi):
    """Numer projektu z Uwag na ZK — tam RM_BAZA go wpisuje przy zakładaniu."""
    return (uwagi or "").strip()


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
    def uprosc(x):
        return "".join(c for c in x.lower() if c.isalnum())
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
            "zk": ", ".join(sorted({z.get("Numer", "") for z in p["zk"] if z.get("Numer")})),
            # Numer ZD wpisywany po utworzeniu — zostaje w arkuszu, żeby było
            # widać, co już zamówione, zanim odświeżenie usunie pozycję.
            "zd": "",
        })
    # Zamówione — tylko te, których nie ma już w zapotrzebowaniu (te same
    # symbole mogą tam wisieć, jeśli ZD pokryło część ilości).
    juz = {w["symbol"].strip().upper() for w in wiersze}
    for z in zamowione or ():
        sym = z["symbol"].strip().upper()
        if sym in juz:
            continue
        b = bom.get(sym, {})
        projekt = b.get("projekt", "") if b else ""
        if tylko_projekt and projekt != tylko_projekt:
            continue
        wiersze.append({
            "sel": False,
            "symbol": z["symbol"],
            "nazwa": b.get("nazwa") or z["nazwa_subiekt"],
            "typ": b.get("typ", ""),
            # Pozycji nie ma już w zapotrzebowaniu (pokryta przez ZD), więc
            # „potrzeba" = ilość, którą realnie zamówiono. Stanu magazynowego
            # zapotrzebowanie już dla niej nie zwraca.
            "potrzeba": z["ilosc"],
            "dostepne": 0.0,
            "zarezerwowane": 0.0,
            "ze_stanu": 0.0,
            "stan_min": 0.0,
            "stan_opt": 0.0,
            "ilosc": z["ilosc"],
            "jm": "szt",
            "dostawca": z["dostawca"],
            "dostawca_bom": b.get("dostawca", ""),
            "projekty": projekt,
            "zk": "",
            "zd": z["zd"],
            "zd_status": z.get("status", ""),
            "zd_data": z.get("data", ""),
        })

    wiersze.sort(key=lambda w: (bool(w.get("zd")), w["dostawca"] == "",
                                w["dostawca"], w["symbol"]))
    return wiersze


# ── Zapis ZD ────────────────────────────────────────────────────────────────
def utworz_zd(pozycje, timeout=TIMEOUT_S):
    """Tworzy ZD w Subiekcie. pozycje: [{symbol, ilosc, dostawca}]."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")

    tmpdir = tempfile.mkdtemp(prefix="subiekt_zd_")
    plan_path = os.path.join(tmpdir, "zd.json")
    out = os.path.join(tmpdir, "wynik.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump({"pozycje": pozycje}, f, ensure_ascii=False, indent=1)

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
class ZamowieniaWindow(tk.Toplevel):
    # Kolumny arkusza. Indeksy muszą się zgadzać z COL_* niżej.
    # Cztery ilości z kroku 3 przepływu: potrzeba / dostępne / ze stanu / kupić.
    # „Kupić" (= Brakuje) to ta, którą realnie zamawiamy — jest edytowalna.
    # „Na stanie" to ilość DOSTĘPNA (Subiekt odejmuje już rezerwacje);
    # „Rezerw." pokazuje, ile z magazynu jest zajęte. „Min/Opt" to progi
    # zamawiania z kartoteki (np. „10/15" = domawiaj przy 10, uzupełnij do 15).
    HEADERS = ["✓", "Nr rysunku", "Nazwa", "Typ", "Potrzeba", "Na stanie", "Rezerw.",
               "Min/Opt", "Ze stanu", "Kupić", "J.m.", "Dostawca (Subiekt)",
               "wg BOM", "Projekt", "ZK", "ZD", "Data ZD"]
    (COL_SEL, COL_SYMBOL, COL_NAZWA, COL_TYP, COL_POTRZEBA, COL_DOSTEPNE, COL_REZERW,
     COL_MINOPT, COL_ZE_STANU, COL_ILOSC, COL_JM, COL_DOSTAWCA, COL_DOST_BOM,
     COL_PROJ, COL_ZK, COL_ZD, COL_DATA_ZD) = range(17)
    SZEROKOSCI = [30, 115, 165, 48, 60, 60, 56, 60, 56, 50, 34, 145, 88, 56, 88, 92, 74]

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
        self.combo_dostawca.bind("<<ComboboxSelected>>", lambda _e: self._refill())

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
        tk.Label(s, text="   (klik w ✓ przełącza wiersz • DWUKLIK w Dostawcę = wybór z listy Subiekta "
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
            # Shift+klik zaznacza zakres w arkuszu — te akcje przekładają go
            # na kolumnę ✓ (co realnie idzie do ZD).
            self.sheet.popup_menu_add_command("✓ Zaznacz wiersze",
                                              lambda: self._zaznacz_wybrane(True))
            self.sheet.popup_menu_add_command("☐ Odznacz wiersze",
                                              lambda: self._zaznacz_wybrane(False))
            self.sheet.popup_menu_add_command("Ustaw dostawcę dla wierszy…",
                                              self._ustaw_dostawce_masowo)
            self.sheet.popup_menu_add_command("🗑 Usuń zamówienia (ZD)…", self._usun_zd)
            self.sheet.pack(fill=tk.BOTH, expand=True)

        bottom = tk.Frame(self)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))
        self.btn_zd = tk.Button(bottom, text="🛒 Utwórz ZD z zaznaczonych",
                                command=self._utworz_zd, bg="#e67e22", fg="white",
                                font=("Arial", 9, "bold"), padx=14, pady=5,
                                relief=tk.RAISED, bd=2, state=tk.DISABLED)
        self.btn_zd.pack(side=tk.RIGHT)
        tk.Label(bottom, text="Powstanie osobne ZD dla każdego dostawcy.",
                 fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.LEFT, pady=8)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    # ── wczytywanie ────────────────────────────────────────────────────────
    def _load_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.btn_zd.config(state=tk.DISABLED)
        self.status.config(text="Pytam Subiekta o zapotrzebowanie (~10 s)…")
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
            if self.project_name:
                numery.add(self.project_name.strip().split(" ")[0])
            bom = {}
            for pid, pname in projekty_po_numerze(numery).items():
                bom.update(dane_z_bom(pid, (pname or "").strip().split(" ")[0]))
            if self.project_id and not bom:
                bom = dane_z_bom(self.project_id,
                                 self.project_name.strip().split(" ")[0] if self.project_name else None)

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
        self.btn_refresh.config(state=tk.NORMAL)
        if error:
            self.status.config(text="Błąd.")
            self.summary.config(text=error.split("\n")[0][:200])
            messagebox.showerror("Subiekt", error, parent=self)
            return

        self.wszystkie = wiersze
        self.podmioty = list(podmioty or [])
        dostawcy = sorted({w["dostawca"] for w in wiersze if w["dostawca"]})
        self.combo_dostawca["values"] = [FILTR_WSZYSCY] + dostawcy + [FILTR_BRAK_DOSTAWCY]
        projekty = sorted({p for w in wiersze for p in w["projekty"].split(", ") if p})
        self.combo_projekt["values"] = [FILTR_WSZYSCY] + projekty

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
        self.only_bez_dostawcy_var.set(0)
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

        out = []
        for w in wiersze:
            # Nic nie znika samo — o widoczności decyduje wyłącznie ten filtr.
            if stan == STAN_DO_ZAMOWIENIA and w.get("zd"):
                continue
            if stan == STAN_ZAMOWIONE and not w.get("zd"):
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
            if not self._typ_pasuje(w):
                continue
            if tylko_bez and w["dostawca"]:
                continue
            out.append(w)
        return out

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
        self.widoczne = self._filtruj(self.wszystkie)
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
              f"{w.get('potrzeba', 0):g}" if w.get("potrzeba") else "",
              f"{w.get('dostepne', 0):g}" if w.get("dostepne") else "",
              f"{w.get('zarezerwowane', 0):g}" if w.get("zarezerwowane") else "",
              self._min_opt(w),
              f"{w.get('ze_stanu', 0):g}" if w.get("ze_stanu") else "",
              f"{w['ilosc']:g}", w["jm"], w["dostawca"], w.get("dostawca_bom", ""),
              w["projekty"], w["zk"], w.get("zd", ""), w.get("zd_data", "")]
             for w in self.widoczne],
            reset_col_positions=False, redraw=False)

        # Dostawcę wybiera się dwuklikiem (okno z listą 629 podmiotów), NIE
        # przez create_dropdown: strzałka dropdowna w tksheet rozciąga się na
        # sąsiednią kolumnę i zasłania „wg BOM" — wygląda to, jakby dostawcy
        # w ogóle się nie wczytali (zgłoszone 04.09.2026).
        # Wyłącznie highlight_cells — mieszanie z highlight_rows dawało
        # niespójny efekt przy zmianie filtra (kolory wierszy i komórek
        # czyszczą się inaczej).
        ostatnia = len(self.HEADERS) - 1
        for i, w in enumerate(self.widoczne):
            if w.get("zd"):
                # Zamówione — cały wiersz na zielono, jak „na stanie" w oknie stanów.
                for c in range(ostatnia + 1):
                    self.sheet.highlight_cells(row=i, column=c, bg="#d5f5e3")
            else:
                if w["ilosc"] <= 0:
                    # Cała potrzeba pokryta ze stanu — nie ma czego zamawiać.
                    for c in range(ostatnia + 1):
                        self.sheet.highlight_cells(row=i, column=c, bg="#eafaf1")
                # Kolor kolumny Dostawca mówi, SKĄD się wziął — bo od tego
                # zależy, czy trzeba go sprawdzić okiem:
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

    def _usun_zd(self):
        """PPM → okno z listą DOKUMENTÓW ZD do usunięcia.

        Zaznacza się numery ZD, nie pozycje — bo kasowany jest cały dokument.
        Wcześniej działało to na wierszach arkusza i było mylące: zaznaczałeś
        jedną pozycję, a znikało całe zamówienie (zgłoszone 04.09.2026).
        """
        zd = {}
        for w in self.wszystkie:
            nr = w.get("zd")
            if nr:
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
        if error:
            self.status.config(text="Nie udało się usunąć ZD.")
            messagebox.showerror("Usuń ZD", error, parent=self)
            return
        kroki = wynik.get("kroki", [])
        usuniete = [k for k in kroki if k.get("Status") == "usuniete"]
        bledy = [k for k in kroki if k.get("Status") == "blad"]
        zapisz_log(wynik)

        lines = [f"Usunięte ZD: {len(usuniete)}"]
        lines += [f"  • {k['Numer']} — {k.get('Szczegoly') or ''}" for k in usuniete[:12]]
        if bledy:
            lines += ["", f"Nieusunięte ({len(bledy)}):"]
            lines += [f"  • {k['Numer']}: {k.get('Szczegoly') or ''}" for k in bledy[:8]]
        (messagebox.showwarning if bledy else messagebox.showinfo)(
            "Usuwanie ZD", "\n".join(lines), parent=self)
        self._load_async()      # pozycje wracają do zapotrzebowania

    def _on_dblclick(self, event):
        """Dwuklik w kolumnę Dostawca → wybór z listy podmiotów Subiekta."""
        if not self.sheet:
            return
        try:
            r = self.sheet.identify_row(event, allow_end=False)
            c = self.sheet.identify_column(event, allow_end=False)
        except Exception:
            return
        if r is None or c != self.COL_DOSTAWCA or not (0 <= r < len(self.widoczne)):
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
        wysrodkuj(dlg, self, 520, 430)

        if z_bom:
            tk.Label(dlg, text="wg BOM: " + ", ".join(z_bom[:3]),
                     fg="#7f8c8d", font=("Arial", 8)).pack(padx=14, pady=(10, 0), anchor="w")

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
        """Klik w kolumnę ✓ przełącza wiersz.

        Z wciśniętym Shift/Ctrl NIE przełączamy — wtedy user zaznacza zakres
        w arkuszu, a przełączanie ✓ przy każdym kliknięciu psułoby zaznaczanie.
        Do zbiorczego przełączania służy „Zaznacz: widoczne/nic/odwróć" i PPM.
        """
        if not self.sheet:
            return
        if event.state & 0x0001 or event.state & 0x0004:      # Shift / Ctrl
            return
        try:
            r = self.sheet.identify_row(event, allow_end=False)
            c = self.sheet.identify_column(event, allow_end=False)
        except Exception:
            return
        if r is None or c != self.COL_SEL or not (0 <= r < len(self.widoczne)):
            return
        self.widoczne[r]["sel"] = not self.widoczne[r]["sel"]
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
        poz = [{"symbol": w["symbol"], "ilosc": w["ilosc"], "dostawca": w["dostawca"]}
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
