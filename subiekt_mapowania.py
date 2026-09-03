# -*- coding: utf-8 -*-
"""
Globalna tabela mapowań numer rysunku → kartoteka Subiekta.

Warstwa pośrednicząca między RM_BAZA a Subiektem (SUBIEKT_INTEGRACJA_PLAN.md,
sekcja „Zapamiętanie skojarzenia"). Trzy rzeczy, dla których istnieje:

1. **Globalna, nie per projekt.** Jeśli `013-100.22X` raz został skojarzony
   z kartoteką Subiekta, każdy następny projekt zna to skojarzenie od razu.
   Dlatego mieszka obok master.sqlite, a nie w bazie projektu.

2. **Warstwa filtrująca przed siecią.** Krok „sprawdź w Subiekcie" pyta
   najpierw tutaj (SELECT po indeksie — mikrosekundy, zero sieci) i dopiero
   przy braku trafienia leci przez Sferę (15–30 s dla 300 pozycji). To nie
   zamiennik zapytania do Subiekta, tylko filtr przed nim.

3. **Ślad, skąd wzięło się dopasowanie.** `sposob` rozróżnia trafienie
   automatyczne po symbolu od ręcznego wyboru użytkownika (fuzzy) — plan
   wymaga, żeby dało się to pokazać w arkuszu jako różne stany, bo ręczne
   dopasowanie mogło być pomyłką.

Nazwy/opisów detali NIE zapisujemy z Subiekta — źródłem prawdy dla danych
konstrukcyjnych zostaje RM_BAZA (plan, sekcja 1/12.1).
"""

import json
import os
import sqlite3
import threading
from datetime import datetime

# Obok master.sqlite — to metadana integracji dla całej firmy, nie pojedynczego
# projektu. Ścieżka realna, jak reszta baz (patrz pamięć „Ścieżki do bazy danych").
#
# Zależy od maszyny (firma: Y:\RM_BAZA\, dom/M-OLD: C:/RMPAK_CLIENT/RM_BAZY/RM_BAZA/)
# — wyprowadzana z katalogu tego samego master.sqlite z sync_config.json, którego
# już poprawnie używa reszta RM_BAZA, zamiast twardej ścieżki Y: niezależnej od
# configu (ta sama pułapka co w subiekt_stany.py, znaleziona 2026-09-03 na M-OLD).
_SYNC_CONFIG_PATH = r"C:\RMPAK_CLIENT\sync_config.json"
_DB_PATH_FALLBACK = r"Y:\RM_BAZA\subiekt_mapowania.sqlite"


def _db_path():
    try:
        with open(_SYNC_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        master = cfg["paths"]["master"]
        return os.path.join(os.path.dirname(master), "subiekt_mapowania.sqlite")
    except Exception:
        return _DB_PATH_FALLBACK


DB_PATH = _db_path()

SPOSOB_AUTO = "auto"        # trafienie 1:1 po symbolu = numer rysunku
SPOSOB_LUZNY = "luzny"      # TRIM + wielkość liter (spacje/a-A w bazie Subiekta)
SPOSOB_RECZNY = "reczny"    # użytkownik wskazał kartotekę (fuzzy match)
SPOSOB_ZALOZONA = "zalozona"  # kartoteka założona przez RM_BAZA

_lock = threading.Lock()


def _connect(path=None, readonly=False):
    p = path or DB_PATH
    if readonly:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5.0, check_same_thread=False)
    else:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        con = sqlite3.connect(p, timeout=15.0, check_same_thread=False)
        # WAL nie działa przez SMB — ta sama pułapka co w rm_database_manager.
        con.execute("PRAGMA journal_mode=DELETE")
        con.execute("PRAGMA busy_timeout=5000")
        con.execute("PRAGMA synchronous=NORMAL")
    con.row_factory = sqlite3.Row
    return con


def ensure_schema(path=None):
    """Tworzy tabelę, jeśli jej nie ma. Bezpieczne do wołania wielokrotnie."""
    with _lock:
        con = _connect(path)
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS mapowania (
                    numer_rysunku   TEXT PRIMARY KEY,   -- klucz: numer z RM_BAZA (TRIM, wielkie litery)
                    symbol_subiekt  TEXT NOT NULL,      -- symbol dokładnie taki, jak w Subiekcie
                    id_subiekt      INTEGER,            -- Id kartoteki, jeśli znane
                    nazwa_subiekt   TEXT,               -- tylko do podglądu; NIE nadpisuje nazwy w RM_BAZA
                    sposob          TEXT NOT NULL,      -- auto | luzny | reczny | zalozona
                    kto             TEXT,
                    kiedy           TEXT NOT NULL,
                    uwagi           TEXT
                )
            """)
            # Wyszukiwanie idzie po kluczu głównym, ale raporty „co dopasowano
            # ręcznie" chodzą po sposobie — stąd drugi indeks.
            con.execute("CREATE INDEX IF NOT EXISTS idx_map_sposob ON mapowania(sposob)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_map_symbol ON mapowania(symbol_subiekt)")
            con.commit()
        finally:
            con.close()


def _key(numer):
    return (numer or "").strip().upper()


def get(numer, path=None):
    """Jedno mapowanie albo None."""
    k = _key(numer)
    if not k:
        return None
    try:
        con = _connect(path, readonly=True)
    except sqlite3.OperationalError:
        return None                      # brak pliku = brak mapowań, nie błąd
    try:
        row = con.execute("SELECT * FROM mapowania WHERE numer_rysunku = ?", (k,)).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None                      # brak tabeli — jeszcze nic nie zapisano
    finally:
        con.close()


def get_many(numery, path=None):
    """{NUMER: mapowanie} dla listy numerów — jedno zapytanie zamiast N.

    To jest ta „warstwa filtrująca": wołane raz na całą listę BOM zanim
    cokolwiek poleci do Subiekta przez sieć.
    """
    klucze = [_key(n) for n in (numery or []) if _key(n)]
    if not klucze:
        return {}
    try:
        con = _connect(path, readonly=True)
    except sqlite3.OperationalError:
        return {}
    try:
        out = {}
        # SQLite ma limit zmiennych w zapytaniu (domyślnie 999) — dzielimy na paczki.
        for i in range(0, len(klucze), 500):
            paczka = klucze[i:i + 500]
            q = f"SELECT * FROM mapowania WHERE numer_rysunku IN ({','.join('?' * len(paczka))})"
            for row in con.execute(q, paczka):
                out[row["numer_rysunku"]] = dict(row)
        return out
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()


def put(numer, symbol_subiekt, sposob, id_subiekt=None, nazwa_subiekt=None,
        kto=None, uwagi=None, path=None):
    """Zapisuje/aktualizuje mapowanie.

    Ręczny wybór użytkownika nie jest nadpisywany automatem — decyzja
    człowieka ma pierwszeństwo, bo automat mógłby ją cofnąć przy następnym
    przebiegu (plan: ręczne dopasowanie to świadoma decyzja, nie przypadek).
    """
    k = _key(numer)
    if not k or not (symbol_subiekt or "").strip():
        return False

    ensure_schema(path)
    with _lock:
        con = _connect(path)
        try:
            stare = con.execute(
                "SELECT sposob FROM mapowania WHERE numer_rysunku = ?", (k,)).fetchone()
            if stare and stare["sposob"] == SPOSOB_RECZNY and sposob != SPOSOB_RECZNY:
                return False
            con.execute("""
                INSERT INTO mapowania
                    (numer_rysunku, symbol_subiekt, id_subiekt, nazwa_subiekt, sposob, kto, kiedy, uwagi)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(numer_rysunku) DO UPDATE SET
                    symbol_subiekt = excluded.symbol_subiekt,
                    id_subiekt     = COALESCE(excluded.id_subiekt, mapowania.id_subiekt),
                    nazwa_subiekt  = COALESCE(excluded.nazwa_subiekt, mapowania.nazwa_subiekt),
                    sposob         = excluded.sposob,
                    kto            = excluded.kto,
                    kiedy          = excluded.kiedy,
                    uwagi          = excluded.uwagi
            """, (k, symbol_subiekt.strip(), id_subiekt, nazwa_subiekt, sposob,
                  kto or os.environ.get("USERNAME") or "?",
                  datetime.now().isoformat(timespec="seconds"), uwagi))
            con.commit()
            return True
        finally:
            con.close()


def put_many(wpisy, path=None):
    """[(numer, symbol, sposob, id, nazwa)] → liczba zapisanych.

    Wołane po suchym przebiegu/zapisie, żeby zapamiętać, co Subiekt potwierdził.
    """
    n = 0
    for w in wpisy or []:
        numer, symbol, sposob = w[0], w[1], w[2]
        id_s = w[3] if len(w) > 3 else None
        nazwa = w[4] if len(w) > 4 else None
        if put(numer, symbol, sposob, id_s, nazwa, path=path):
            n += 1
    return n


def delete(numer, path=None):
    """Usuwa mapowanie — gdy okaże się błędne (np. zły ręczny wybór)."""
    k = _key(numer)
    if not k:
        return False
    ensure_schema(path)
    with _lock:
        con = _connect(path)
        try:
            cur = con.execute("DELETE FROM mapowania WHERE numer_rysunku = ?", (k,))
            con.commit()
            return cur.rowcount > 0
        finally:
            con.close()


def stats(path=None):
    """{sposob: liczba, 'razem': n} — do podglądu i diagnostyki."""
    try:
        con = _connect(path, readonly=True)
    except sqlite3.OperationalError:
        return {"razem": 0}
    try:
        out = {r["sposob"]: r["n"] for r in
               con.execute("SELECT sposob, COUNT(*) n FROM mapowania GROUP BY sposob")}
        out["razem"] = sum(out.values())
        return out
    except sqlite3.OperationalError:
        return {"razem": 0}
    finally:
        con.close()


if __name__ == "__main__":
    ensure_schema()
    print(f"Baza mapowań: {DB_PATH}")
    print("Statystyki:", stats())
