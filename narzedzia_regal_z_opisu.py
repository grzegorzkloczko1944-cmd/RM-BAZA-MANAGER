# -*- coding: utf-8 -*-
"""Regał z pola Opis → Położenie (PoleWlasne1) w kartotekach Subiekta.

    python narzedzia_regal_z_opisu.py                 # SUCHY PRZEBIEG (raport)
    python narzedzia_regal_z_opisu.py --zapisz        # przenosi
    python narzedzia_regal_z_opisu.py --zapisz --czysc-opis   # + czyści Opis

PO CO (03.10.2026)
──────────────────
Migracja na magazyn nr 2 (09.2026) wpisała regały do PoleWlasne1 dla 1367
kartotek. Poza nią zostały pozycje, które mają regał WPISANY W OPIS
(„REG.5.4", „Reg 1.4", „Reg 21.3") i puste Położenie. Dla nich kolumna
Położenie w oknie Magazyn i w oknie wydania jest pusta — magazynier nie
znajdzie detalu po lokalizacji.

⚠️ RUSZAMY TYLKO TE Z PUSTYM POŁOŻENIEM. Gdy oba pola są wypełnione, nie
zgadujemy, które jest prawdziwe — trafiają do raportu „KONFLIKT".

⚠️ Opis domyślnie ZOSTAJE. Notatka z migracji ostrzega, że część opisów to
świadome zmiany; kasowanie jest osobną, jawną decyzją (--czysc-opis).
"""
import re
import sys

# „REG.5.4", „Reg 1.4", „Reg 21.3", „Reg 1", „R6/P4" — regał z numerem.
# Celowo WĄSKI wzorzec: łapie tylko to, co bez wątpienia jest lokalizacją.
WZORZEC = re.compile(r"^(REG|R)[\s.\-/]*\d+([\s.\-/]*\d+)?$", re.I)


def normalizuj(tekst):
    """„Reg 4.3" / „REG.5.4" / „Reg16.2" → „R4/P3". Sam regał: „Reg 1" → „R1".

    Konwencja RX/PX jest obowiązująca (ustalenie użytkownika 03.10.2026) —
    tak wygląda 1369 kartotek wpisanych przy migracji magazynu nr 2. Opisy
    niosą ten sam adres w trzech starych zapisach; normalizacja scala je do
    jednego, żeby sortowanie i szukanie po lokalizacji działało tak samo
    dla wszystkich kartotek.
    """
    liczby = re.findall(r"\d+", str(tekst or ""))
    if not liczby:
        return ""
    if len(liczby) == 1:
        return "R%s" % int(liczby[0])          # sam regał, bez półki
    return "R%s/P%s" % (int(liczby[0]), int(liczby[1]))


def kandydaci(poz):
    """(do_przeniesienia, konflikty) z listy kartotek z trybu `magazyn`."""
    do_przen, konflikt = [], []
    for p in poz:
        opis = str(p.get("Opis") or "").strip()
        polo = str(p.get("Polozenie") or "").strip()
        if not opis or not WZORZEC.match(opis):
            continue
        (konflikt if polo else do_przen).append(p)
    return do_przen, konflikt


def main():
    sys.path.insert(0, r"C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER")
    import subiekt_bridge

    zapisz = "--zapisz" in sys.argv
    czysc = "--czysc-opis" in sys.argv

    dane = subiekt_bridge.call("magazyn", {}, timeout=600, write=False) or {}
    poz = dane.get("pozycje") or []
    print("kartotek w Subiekcie: %d" % len(poz))

    do_przen, konflikt = kandydaci(poz)
    print("do przeniesienia (Opis=regał, Położenie puste): %d" % len(do_przen))
    print("KONFLIKT (oba pola wypełnione, NIE ruszam):     %d\n" % len(konflikt))

    for p in konflikt:
        print("  KONFLIKT %-16s Opis=%-12r Położenie=%r"
              % (p.get("Symbol"), p.get("Opis"), p.get("Polozenie")))
    if konflikt:
        print()

    for p in do_przen[:40]:
        print("  %-16s Opis=%-12r → Położenie=%-9r %s"
              % (p.get("Symbol"), p.get("Opis"),
                 normalizuj(p.get("Opis")),
                 "(Opis czyszczony)" if czysc else "(Opis zostaje)"))
    if len(do_przen) > 40:
        print("  … i %d dalszych" % (len(do_przen) - 40))

    if not zapisz:
        print("\nTo był SUCHY PRZEBIEG. Zapis: --zapisz"
              " (opcjonalnie --czysc-opis)")
        return

    # Jedna paczka do mostu — nie pozycja po pozycji (CLAUDE.md: zapis hurtem).
    pozycje = []
    for p in do_przen:
        wpis = {"symbol": p.get("Symbol"), "polozenie": normalizuj(p.get("Opis"))}
        if czysc:
            wpis["opis"] = ""
        pozycje.append(wpis)
    if not pozycje:
        print("Nic do zrobienia.")
        return

    wynik = subiekt_bridge.call("kartoteki", {"plan": {"pozycje": pozycje},
                                              "zapisz": True},
                                timeout=900, write=True) or {}
    kroki = wynik.get("kroki") or []
    ile = {}
    for k in kroki:
        ile[k.get("Status")] = ile.get(k.get("Status"), 0) + 1
    print("\nWYNIK:", ", ".join("%s=%d" % (s, n) for s, n in sorted(ile.items())))
    for k in kroki:
        if k.get("Status") not in ("zmieniona", "bez-zmian", "istnieje"):
            print("  %-16s %-14s %s" % (k.get("Symbol"), k.get("Status"),
                                        (k.get("Szczegoly") or "")[:70]))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
