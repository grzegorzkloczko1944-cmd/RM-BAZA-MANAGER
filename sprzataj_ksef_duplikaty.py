# -*- coding: utf-8 -*-
r"""Usuwa duplikaty `LOKALNA-` z archiwum faktur KSeF (17.09.2026).

Uruchomic NA SERWERZE W2019S:

    python C:\Apps\RM_SERWER\sprzataj_ksef_duplikaty.py          # tylko pokaz
    python C:\Apps\RM_SERWER\sprzataj_ksef_duplikaty.py --kasuj  # wykonaj

Skad sie biora duplikaty: faktura wczytana z dysku nie ma numeru KSeF (nadaje
go system przy wysylce), wiec dostaje klucz zastepczy `LOKALNA-<NIP>-<numer>`.
Gdy TA SAMA faktura przyszla wczesniej przez API, w archiwum sa dwa wpisy.

Kasujemy WYLACZNIE wpis `LOKALNA-`, i tylko wtedy, gdy istnieje blizniaczy
wpis z prawdziwym numerem KSeF (ten sam NIP + ten sam numer faktury). Faktura
istniejaca TYLKO jako `LOKALNA-` zostaje nietknieta.

Bez restartu uslugi. Domyslnie nic nie kasuje — trzeba podac --kasuj.
"""
import re
import sqlite3
import sys

BAZA = r"C:\Apps\RM_SERWER\dane\FV_KSEF.sqlite"
#: Prawdziwy numer KSeF: 10 cyfr NIP, myslnik, data, myslnik, reszta.
WZOR_KSEF = re.compile(r"^\d{10}-\d{8}-")


def _norm(s):
    """Numer faktury do porownania — tak samo, jak robi to `zastepcze_id`."""
    return re.sub(r"[^A-Za-z0-9]+", "-", (s or "").strip()).strip("-")


def main(kasuj):
    con = sqlite3.connect(BAZA, timeout=15)
    con.execute("PRAGMA busy_timeout=10000")
    con.row_factory = sqlite3.Row

    pary = {}
    for r in con.execute("SELECT ksef_number, numer_faktury, sprzedawca_nip,"
                         "       sprzedawca, pozycji FROM faktury"):
        klucz = (r["sprzedawca_nip"] or "", _norm(r["numer_faktury"]))
        pary.setdefault(klucz, []).append(r)

    do_kasacji = []
    for (nip, numer), wiersze in sorted(pary.items()):
        if len(wiersze) < 2:
            continue
        prawdziwe = [w for w in wiersze if WZOR_KSEF.match(w["ksef_number"] or "")]
        lokalne = [w for w in wiersze if w["ksef_number"].startswith("LOKALNA-")]
        if not prawdziwe or not lokalne:
            # Dwa wpisy, ale zaden nie jest para oryginal+LOKALNA — nie ruszamy,
            # bo nie wiadomo, ktory jest wlasciwy. Do obejrzenia recznie.
            print("? POMIJAM (niejasne): %s / %s -> %s"
                  % (nip, numer, [w["ksef_number"] for w in wiersze]))
            continue
        for w in lokalne:
            do_kasacji.append(w)
            print("- %s  (duplikat %s, %s, %s poz.)"
                  % (w["ksef_number"], prawdziwe[0]["ksef_number"],
                     w["sprzedawca"], w["pozycji"]))

    if not do_kasacji:
        print("Brak duplikatow do usuniecia.")
        return 0

    print("\nDo usuniecia: %d wpisow" % len(do_kasacji))
    if not kasuj:
        print("To byl tylko podglad. Aby wykonac, uruchom z --kasuj")
        return 0

    for w in do_kasacji:
        con.execute("DELETE FROM pozycje WHERE ksef_number = ?", (w["ksef_number"],))
        con.execute("DELETE FROM faktury WHERE ksef_number = ?", (w["ksef_number"],))
    con.commit()

    print("USUNIETO. W archiwum zostalo: %d faktur, %d pozycji"
          % (con.execute("SELECT COUNT(*) FROM faktury").fetchone()[0],
             con.execute("SELECT COUNT(*) FROM pozycje").fetchone()[0]))
    print("integrity_check:", con.execute("PRAGMA integrity_check").fetchone()[0])
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main("--kasuj" in sys.argv))
