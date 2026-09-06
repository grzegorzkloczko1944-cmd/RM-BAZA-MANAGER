# -*- coding: utf-8 -*-
"""
Dopasowanie nazw kartotek Subiekta — NARZĘDZIE POMIAROWE, nie produkcyjne.

╔══════════════════════════════════════════════════════════════════════════╗
║ ⛔ NIE PODPINAĆ znajdz_podobne() DO GUI ANI DO KOJARZENIA POZYCJI.        ║
║                                                                          ║
║ Plan („Krok 2b") przewidywał przycisk „Szukaj podobnych w Subiekcie"     ║
║ oparty o fuzzy match po nazwie. Pomiar na realnych danych (2026-09-04,   ║
║ projekt 2627, 161 pozycji) ten pomysł ODRZUCIŁ:                          ║
║                                                                          ║
║   389 par RÓŻNYCH detali przekroczyło próg podobieństwa, m.in.           ║
║     0.933  'Płyta zewnętrzna'  vs  'Płyta wewnętrzna'   ← przeciwieństwa ║
║     0.909  'WSQ_06_30 L120'    vs  'WSQ_06_30 L103'     ← inna długość   ║
║     0.889  'Korek 14mm'        vs  'Korek 64mm'         ← inny wymiar    ║
║     0.889  'Szuflada 1'        vs  'Szuflada 2'         ← inny wariant   ║
║     0.867  'Chwytak potrójny'  vs  'Chwytak podwójny'                    ║
║                                                                          ║
║ Żaden próg tego nie rozdziela: prawdziwe trafienia (różnica samej        ║
║ pisowni) dają 1.000, a te fałszywe siedzą tuż pod nimi.                  ║
║                                                                          ║
║ Do tego 'Uchwyt czujnika' to nazwa DWÓCH różnych detali (2627-270.12ZZ   ║
║ i 027-300.06Z) — nazwa nie jest kluczem, nawet po normalizacji.          ║
║                                                                          ║
║ Gdyby to trafiło do GUI: user zatwierdziłby złe skojarzenie, ono poszłoby║
║ do globalnej tabeli mapowań i po cichu działało we WSZYSTKICH przyszłych ║
║ projektach — RM_BAZA zamawiałaby zły detal.                              ║
║                                                                          ║
║ Co zamiast tego: subiekt_raport_duplikatow.py — dopasowanie po           ║
║ znormalizowanym KODZIE (jednoznaczne), do przejrzenia przez człowieka.   ║
╚══════════════════════════════════════════════════════════════════════════╝

Co w tym pliku jest nadal użyteczne:

* `normalizuj()`   — sprowadzenie nazwy do postaci porównywalnej (ogonki,
                     wielkość liter, separatory). To ta część, która działa.
* `pobierz_katalog()` — pełna kartoteka Subiekta przez `NexoRecon.exe katalog`.
* `podobienstwo()` / `raport()` — do POMIARU, gdyby ktoś chciał powtórzyć
                     eksperyment na innych danych (np. po zmianie nazewnictwa).

TYLKO ODCZYT — nic nie zapisuje ani do Subiekta, ani do mapowań.

    import subiekt_podobne
    katalog = subiekt_podobne.pobierz_katalog()
    print(subiekt_podobne.raport([("Kątownik", "Katownik")]))
"""

import difflib
import json
import os
import re
import subprocess
import tempfile
import unicodedata

_HERE = os.path.dirname(os.path.abspath(__file__))
EXE_CANDIDATES = [
    os.path.join(_HERE, "subiekt_sfera", "NexoRecon", "bin", "Release", "NexoRecon.exe"),
    r"C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER\subiekt_sfera\NexoRecon\bin\Release\NexoRecon.exe",
    r"C:\RMPAK_CLIENT\NexoRecon\NexoRecon.exe",
]
# Sciezka konfiguracji trzymana w subiekt_konfig — to samo miejsce, z ktorego
# okno logowania ja ZAPISUJE. Trzy niezalezne kopie tej stalej grozily
# rozjazdem, gdy doszedl zapis (06.09.2026).
from subiekt_konfig import CONFIG_PATH

TIMEOUT_S = 180

# Ile kandydatów pokazać. Plan mówi 3–5; 5 daje szansę trafienia, a wciąż
# mieści się na ekranie bez przewijania.
TOP_N = 5

# Poniżej tego progu kandydat nie jest pokazywany w ogóle. Wartość dobrana
# tak, żeby przepuścić literówki i różnice pisowni ("Tuleja fi12" vs
# "tuleja FI 12"), a odciąć przypadkowe zbieżności pojedynczych słów.
#
# ⚠ Próg jest ŚWIADOMIE prowizoryczny — plan (sekcja „Krok 2b") mówi wprost,
# że ma go dobrać człowiek, mając pod ręką realne pary nazw z obu systemów.
# Do tego służy `raport()` na dole pliku: puszcza się go na prawdziwym
# projekcie i patrzy, gdzie próg tnie za wcześnie albo za późno.
PROG = 0.55


def _find_exe():
    for p in EXE_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def blad_mostu(exe, tryb, proc, out_path):
    """Czytelny komunikat błędu — wspólny z subiekt_stany (m.in. wykrywa
    nieaktualny .exe po git pullu). Fallback, gdyby importu nie było."""
    try:
        from subiekt_stany import blad_mostu as _wspolny
        return _wspolny(exe, tryb, proc, out_path)
    except Exception:
        msg = (proc.stdout or "").strip() or (proc.stderr or "").strip() or "nieznany błąd"
        return f"Most zwrócił błąd (kod {proc.returncode}):\n\n{msg}"


# ── Normalizacja ────────────────────────────────────────────────────────────
# Różnice, które dziś realnie widać między BOM a Subiektem, to głównie
# pisownia (wielkość liter, spacje, ogonki), nie parafrazy nazw — plan,
# sekcja 12.2. Dlatego najpierw normalizujemy, a fuzzy match liczy się
# dopiero na tym, co po normalizacji ZOSTAŁO różne.
_NIEISTOTNE = re.compile(r"[\s\-_.,;:/\\()\[\]{}\"'`]+")


def normalizuj(s):
    """Nazwa sprowadzona do postaci porównywalnej.

    Ogonki → ASCII (bo w jednym systemie bywa „Kątownik", w drugim
    „Katownik"), wielkość liter ujednolicona, znaki nieistotne (spacje,
    myślniki, kropki) usunięte — „fi 12", „fi12" i „FI-12" mają wypaść tak
    samo, bo dla człowieka to ta sama rzecz.
    """
    s = (s or "").strip().lower()
    # NFKD rozbija „ą" na „a" + ogonek, potem wyrzucamy same znaki łączące.
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # „ł" nie ma rozkładu NFKD — trzeba osobno.
    s = s.replace("ł", "l")
    return _NIEISTOTNE.sub("", s)


def podobienstwo(a, b):
    """0..1 — jak bardzo dwie nazwy są podobne PO normalizacji.

    SequenceMatcher z biblioteki standardowej: bez nowych zależności, a dla
    literówek i przestawionych znaków zachowuje się rozsądnie. Świadomie NIE
    Levenshtein z zewnętrznej paczki — przy kilku tysiącach porównań na
    pozycję różnica prędkości jest bez znaczenia, a zależność kosztuje.
    """
    na, nb = normalizuj(a), normalizuj(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0        # różniła się tylko pisownia — pewne trafienie
    return difflib.SequenceMatcher(None, na, nb).ratio()


# ── Katalog z Subiekta ──────────────────────────────────────────────────────
def pobierz_katalog(timeout=TIMEOUT_S):
    """[{"symbol": ..., "nazwa": ...}] — pełna kartoteka Subiekta.

    Idzie przez stały most (subiekt_bridge), więc drugie i kolejne wywołanie
    kosztuje milisekundy zamiast ~10 s — nie trzeba już płacić za start
    procesu i logowanie do Sfery przy każdym otwarciu okna.
    Gdy mostu nie da się uruchomić, leci starym CLI (_pobierz_katalog_cli).
    """
    def przez_cli():
        return _pobierz_katalog_cli(timeout)

    try:
        import subiekt_bridge
    except ImportError:
        return przez_cli()

    dane = subiekt_bridge.call("katalog", timeout=timeout, fallback=przez_cli)
    # Fallback zwraca gotową listę, most — surowe {"pozycje": [...]}.
    if isinstance(dane, list):
        return dane
    return _przelicz(dane)


def _przelicz(data):
    """Surowa odpowiedź mostu -> lista kartotek w formacie tego modułu."""
    return [{"id": p.get("Id"),
             "symbol": p.get("Symbol") or "",
             "nazwa": p.get("Nazwa") or ""}
            for p in data.get("pozycje", [])]


def _pobierz_katalog_cli(timeout=TIMEOUT_S):
    """Stara ścieżka: osobny proces NexoRecon.exe na każde wywołanie.

    Zostaje na czas migracji jako fallback (plan, sekcja 17) — most bywa
    niedostępny (nie zbudowany po „git pull”, zajęty port), a wtedy okno
    ma dalej działać, tylko wolniej.
    """
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

    tmpdir = tempfile.mkdtemp(prefix="subiekt_kat_")
    out = os.path.join(tmpdir, "katalog.json")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            [exe, "katalog", f"--out={out}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=flags,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Subiekt nie odpowiedział w {timeout} s.")

    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, "katalog", proc, out))

    with open(out, encoding="utf-8") as f:
        return _przelicz(json.load(f))


# ── Dopasowanie ─────────────────────────────────────────────────────────────
def znajdz_podobne(nazwa_bom, katalog, top_n=TOP_N, prog=PROG, pomijaj_symbole=()):
    """[(wynik, kartoteka)] — najbardziej podobne kartoteki, najlepsza pierwsza.

    ⛔ NIE UŻYWAĆ DO KOJARZENIA POZYCJI — patrz ostrzeżenie na górze pliku.
    Na realnych nazwach detali daje fałszywe trafienia przy 0.87–0.93
    ('Płyta zewnętrzna' vs 'Płyta wewnętrzna'), których żaden próg nie
    odsiewa. Zostawione wyłącznie do powtórzenia pomiaru.

    `pomijaj_symbole` służy do odsiania kartotek, które i tak już są
    przypisane do innych pozycji tego samego projektu — inaczej ta sama
    kartoteka podpowiadałaby się kilku różnym detalom naraz.
    """
    if not (nazwa_bom or "").strip():
        return []
    pomijane = {str(s).strip().upper() for s in pomijaj_symbole}

    oceny = []
    for k in katalog:
        if k["symbol"].strip().upper() in pomijane:
            continue
        w = podobienstwo(nazwa_bom, k["nazwa"])
        if w >= prog:
            oceny.append((w, k))

    # Malejąco po wyniku; przy remisie krótsza nazwa pierwsza — zwykle jest
    # tą bardziej ogólną, a nie wariantem z dopiskiem.
    oceny.sort(key=lambda t: (-t[0], len(t[1]["nazwa"])))
    return oceny[:top_n]


def raport(pary, prog=PROG):
    """Tekstowy podgląd dopasowań — narzędzie do DOBRANIA progu, nie do GUI.

    `pary` to [(nazwa_z_BOM, nazwa_z_Subiekta)]. Pokazuje wynik każdej pary
    i czy przeszłaby przez próg, żeby dało się zobaczyć na realnych danych,
    gdzie próg tnie za wcześnie albo za późno (plan: próg „do dobrania
    w firmie, mając pod ręką realne przykłady").
    """
    linie = [f"próg = {prog}", ""]
    for a, b in pary:
        w = podobienstwo(a, b)
        znak = "✓" if w >= prog else "·"
        linie.append(f"{znak} {w:.3f}  {a!r}\n         {b!r}")
    return "\n".join(linie)
