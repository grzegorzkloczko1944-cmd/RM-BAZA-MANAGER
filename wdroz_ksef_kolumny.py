# -*- coding: utf-8 -*-
r"""Wdrozenie kolumn `indeks` i `dodatkowe` w archiwum faktur KSeF (17.09.2026).

Uruchomic NA SERWERZE W2019S:

    python C:\Apps\RM_SERWER\wdroz_ksef_kolumny.py

Nie wymaga restartu uslugi RM_SERWER — ALTER TABLE wchodzi przy otwartym
polaczeniu serwera (baza ma busy_timeout, journal_mode=DELETE). Skrypt jest
idempotentny: puszczony drugi raz nic nie zmienia.
"""
import sqlite3
import sys

BAZA = r"C:\Apps\RM_SERWER\dane\FV_KSEF.sqlite"
KOLUMNY = ("indeks", "dodatkowe")


def main():
    con = sqlite3.connect(BAZA, timeout=15)
    con.execute("PRAGMA busy_timeout=10000")

    tabele = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "pozycje" not in tabele:
        print("BLAD: brak tabeli `pozycje` w %s" % BAZA)
        return 1

    # Dziennik idempotencji — bez niego KAZDY zapis `ksef-*` konczy sie bledem
    # "no such table: _server_request_log". FV_KSEF jako jedyna z czterech baz
    # serwera go nie dostala przy zakladaniu.
    if "_server_request_log" not in tabele:
        con.execute("""CREATE TABLE IF NOT EXISTS _server_request_log (
                           request_id  TEXT PRIMARY KEY,
                           operation   TEXT NOT NULL,
                           kto         TEXT,
                           result_json TEXT,
                           created_at  TEXT NOT NULL)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_server_request_log_czas"
                    " ON _server_request_log(created_at)")
        print("+ dodano tabele _server_request_log")

    kol = {r[1] for r in con.execute("PRAGMA table_info(pozycje)")}
    print("kolumny `pozycje` przed:", sorted(kol))
    for nazwa in KOLUMNY:
        if nazwa in kol:
            print("  = %s juz jest, pomijam" % nazwa)
            continue
        con.execute("ALTER TABLE pozycje ADD COLUMN %s TEXT" % nazwa)
        print("  + dodano %s" % nazwa)
    con.commit()

    print("kolumny `pozycje` po:  ",
          sorted(r[1] for r in con.execute("PRAGMA table_info(pozycje)")))
    print("integrity_check:", con.execute("PRAGMA integrity_check").fetchone()[0])
    print("faktur w archiwum:",
          con.execute("SELECT COUNT(*) FROM faktury").fetchone()[0])
    con.close()
    print("\nGOTOWE. Restart uslugi NIE jest potrzebny.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
