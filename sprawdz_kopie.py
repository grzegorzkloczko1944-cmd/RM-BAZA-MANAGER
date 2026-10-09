# -*- coding: utf-8 -*-
"""sprawdz_kopie.py — strażnik plików wspólnych dla repo NOW i RM-BAZA-MANAGER.

Ten plik i kopie_miedzy_repo.json są IDENTYCZNE w obu repo (10.10.2026: stats_*.py w RM_MANAGER
rozjechały się z RM_STATS na 2,5 miesiąca, a w RM-BAZA-MANAGER leżała porzucona kopia
RM_Tray_Organizer — nikt nie wiedział, która wersja jest prawdziwa).

    python sprawdz_kopie.py            pełny raport (exit 1, gdy jest problem)
    python sprawdz_kopie.py --hook     tryb pre-commit: zatrzymuje commit tylko z powodu plików
                                       z TEGO commita (staged) — cudzy rozjazd nie blokuje pracy

Sprawdza:
  1. kopie z listy (kopie_miedzy_repo.json): „identyczne” / „identyczne_poza” (z pominięciem
     linii z „ignoruj_linie”) / „rozne_z_zalozenia” (tylko czy oba pliki są);
  2. NOWE duble: plik .py/.pyw o tej samej nazwie w obu repo, którego nie ma na liście.

Drugie repo szukane obok (../NOW, ../RM-BAZA-MANAGER) albo w zmiennej RMPAK_DRUGIE_REPO.
Gdy go nie ma na tej maszynie (np. serwer) — tylko informacja, commit przechodzi.
Hook: .githooks/pre-commit, włączenie raz na klon: git config core.hooksPath .githooks
"""
import json
import os
import re
import subprocess
import sys

TU = os.path.dirname(os.path.abspath(__file__))
LISTA = os.path.join(TU, "kopie_miedzy_repo.json")
ROZSZERZENIA = (".py", ".pyw")


def git(repo, *arg):
    try:
        return subprocess.run(["git", "-C", repo, *arg], capture_output=True, text=True,
                              encoding="utf-8", errors="replace").stdout
    except OSError:
        return ""


def czytaj(sciezka):
    with open(sciezka, "rb") as f:
        return f.read().replace(b"\r\n", b"\n").decode("utf-8", errors="replace")


def ktore_repo(sciezka, repozytoria):
    for nazwa, opis in repozytoria.items():
        if os.path.isfile(os.path.join(sciezka, opis["znacznik"])):
            return nazwa
    return None


def znajdz_drugie(ja, repozytoria):
    drugie = [n for n in repozytoria if n != ja][0]
    kandydaci = [os.environ.get("RMPAK_DRUGIE_REPO", ""),
                 os.path.join(TU, "..", repozytoria[drugie]["katalog"])]
    for k in kandydaci:
        if k and ktore_repo(os.path.abspath(k), repozytoria) == drugie:
            return drugie, os.path.abspath(k)
    return drugie, None


def porownaj(wpis, plik_ja, plik_drugi):
    """None = zgodne, inaczej opis różnicy."""
    if not os.path.isfile(plik_ja) or not os.path.isfile(plik_drugi):
        brak = plik_ja if not os.path.isfile(plik_ja) else plik_drugi
        return "brak pliku %s" % brak
    tryb = wpis.get("tryb")
    if tryb == "rozne_z_zalozenia":
        return None
    a, b = czytaj(plik_ja), czytaj(plik_drugi)
    if tryb == "identyczne_poza":
        wzory = [re.compile(w) for w in wpis.get("ignoruj_linie", [])]
        filtr = lambda t: [l for l in t.split("\n") if not any(w.search(l) for w in wzory)]  # noqa: E731
        a, b = filtr(a), filtr(b)
    if a == b:
        return None
    if isinstance(a, str):
        a, b = a.split("\n"), b.split("\n")
    rozne = sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))
    return "różnią się (%d linii)" % rozne


def main():
    hook = "--hook" in sys.argv
    lista = json.load(open(LISTA, encoding="utf-8"))
    repozytoria = lista["repozytoria"]
    ja = ktore_repo(TU, repozytoria)
    if ja is None:
        print("sprawdz_kopie: nie rozpoznaję repo w %s — pomijam." % TU)
        return 0
    drugie, sciezka_drugiego = znajdz_drugie(ja, repozytoria)
    if not sciezka_drugiego:
        print("sprawdz_kopie: brak repo %s obok (%s) — kopii nie sprawdzam." % (drugie, TU))
        return 0

    staged = set()
    dodane = set()
    if hook:
        staged = {p.strip() for p in git(TU, "diff", "--cached", "--name-only").splitlines() if p.strip()}
        dodane = {p.strip() for p in git(TU, "diff", "--cached", "--name-only", "--diff-filter=AR").splitlines()
                  if p.strip()}

    problemy = []
    znane_nazwy = set(lista.get("ta_sama_nazwa_inny_plik", {}).get("nazwy", []))
    for wpis in lista["kopie"]:
        moj, cudzy = wpis.get(ja), wpis.get(drugie)
        if not moj or not cudzy:
            continue
        znane_nazwy.add(os.path.basename(moj))
        znane_nazwy.add(os.path.basename(cudzy))
        if hook and moj not in staged:
            continue
        roznica = porownaj(wpis, os.path.join(TU, moj), os.path.join(sciezka_drugiego, cudzy))
        if roznica:
            problemy.append(
                "KOPIA %s (%s) ↔ %s/%s: %s.\n"
                "   Kopia ma być %s — przenieś zmianę do drugiego repo (skopiuj plik, commit tam też)%s."
                % (moj, wpis.get("tryb"), drugie, cudzy, roznica, wpis.get("tryb"),
                   "; źródło: %s" % wpis["zrodlo"] if wpis.get("zrodlo") not in (None, "-", "oba") else ""))

    # NOWE duble: ta sama nazwa .py w obu repo, nie ma jej na liście
    def nazwy(repo):
        out = {}
        for p in git(repo, "ls-files").splitlines():
            if p.lower().endswith(ROZSZERZENIA):
                out.setdefault(os.path.basename(p), []).append(p)
        return out

    moje, cudze = nazwy(TU), nazwy(sciezka_drugiego)
    if hook:
        for p in dodane:
            if p.lower().endswith(ROZSZERZENIA):
                moje.setdefault(os.path.basename(p), [])
                if p not in moje[os.path.basename(p)]:
                    moje[os.path.basename(p)].append(p)
    for nazwa in sorted(set(moje) & set(cudze) - znane_nazwy):
        if hook and not any(p in dodane for p in moje[nazwa]):
            continue
        problemy.append(
            "DUBEL %s: jest w %s (%s) i w %s (%s), a nie ma go w kopie_miedzy_repo.json.\n"
            "   Jedno miejsce na kod: użyj tego z drugiego repo albo zmień nazwę. Jeśli kopia MUSI być —\n"
            "   dopisz ją do kopie_miedzy_repo.json w OBU repo (tryb + dlaczego)."
            % (nazwa, ja, ", ".join(moje[nazwa]), drugie, ", ".join(cudze[nazwa])))

    if problemy:
        print("\n⛔ sprawdz_kopie (%s ↔ %s):\n" % (ja, drugie))
        for p in problemy:
            print(" • " + p + "\n")
        if hook:
            print("Commit zatrzymany. Szczegóły: CLAUDE.md → „Wspólne pliki z drugim repo”.")
        return 1
    if not hook:
        print("✔ sprawdz_kopie: %d kopii zgodnych, nowych dubli brak (%s ↔ %s)."
              % (len(lista["kopie"]), ja, drugie))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
