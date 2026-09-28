# -*- coding: utf-8 -*-
"""Zasiew indeksu modeli 3D dla ŁOŻYSK — wpisy ręczne, bez IDW.

    python indeks_lozyska_zasiew.py            # suchy przebieg — NIC nie zapisuje
    python indeks_lozyska_zasiew.py --zapisz   # realny zapis do bazy mapowań

Po co: `indeks_modeli_3d.py` buduje mapę „numer rysunku → model" z plików
**.idw** (rysunek wskazuje swój model). Łożyska z Content Center rysunków
NIE MAJĄ — są gołymi .ipt w `B:\\Znormalizowane\\Łożyska katalog\\gotowe`,
więc automat ich nie widzi i kolumna „3D" w MAG zostaje pusta.

Ten skrypt wpisuje je wprost, jako `zrodlo='reczny'`. Takie wiersze są
CHRONIONE: `map-model3d-zapisz` nie nadpisze ich automatem, a
`map-model3d-usun-*` ich nie kasuje (rm_serwer_operacje.py) — nocny indeks
może chodzić bez obaw.

KLUCZ: numer_rysunku = symbol kartoteki Subiekta, czyli nazwa pliku BEZ
wymiarów — `6004 ZZ 20x42x12.ipt` → `6004 ZZ`. Ta sama reguła, co przy
zakładaniu kartotek i wgrywaniu zdjęć (Part Number z iProperties modelu).

⚠️ MINIATURY 3D bierze osobny krok zlecenia „Synchronizuj 3D" — czyta je
   z pliku .ipt. Modele łożysk generowane przed 28.09.2026 18:00 miały
   miniaturę przybliżoną na przekrój kulki (wygląda jak śmieć); nowe,
   robione przez API, pokazują całe łożysko. Zasiew rób PO przerobieniu
   wszystkich plików, inaczej indeks zapamięta złe kadry.
"""
import argparse
import glob
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

import rm_klient

#: Katalog z modelami łożysk (biblioteka).
KATALOG = r"B:\Znormalizowane\Łożyska katalog\gotowe"

#: Nazwa pliku → symbol. „SS 6004 2RS 20x42x12" → „SS 6004 2RS"
WZOR = re.compile(r"^(.*?)\s+(\d+x\d+x[\d.]+)$")

#: Ile wierszy w jednej paczce do serwera.
PACZKA = 100


def symbol_z_nazwy(nazwa):
    m = WZOR.match(nazwa)
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zapisz", action="store_true",
                    help="realny zapis (bez tego suchy przebieg)")
    ap.add_argument("--katalog", default=KATALOG)
    a = ap.parse_args()

    print(f"1. Czytam modele z {a.katalog}")
    if not os.path.isdir(a.katalog):
        print("   ⛔ Nie ma takiego katalogu.")
        return 1
    # OldVersions: Inventor trzyma tam poprzednie wersje plików — pomijamy,
    # inaczej ten sam symbol dostałby dwie ścieżki.
    pliki = [p for p in glob.glob(os.path.join(a.katalog, "*.ipt"))
             if "oldversions" not in p.lower()]
    wiersze, bez_symbolu = [], []
    kiedy = time.strftime("%Y-%m-%dT%H:%M:%S")
    kto = "%s@%s" % (os.environ.get("USERNAME", "?"), os.environ.get("COMPUTERNAME", "?"))
    for p in sorted(pliki):
        sym = symbol_z_nazwy(os.path.splitext(os.path.basename(p))[0])
        if not sym:
            bez_symbolu.append(os.path.basename(p))
            continue
        wiersze.append({"numer_rysunku": sym.upper(), "sciezka": p, "kolejnosc": 0,
                        "part_number": sym, "idw": None, "idw_mtime": None,
                        "zrodlo": "reczny", "kto": kto, "kiedy": kiedy})
    print(f"   plików .ipt: {len(pliki)}   z rozpoznanym symbolem: {len(wiersze)}")
    if bez_symbolu:
        print(f"   ⚠️  bez wymiarów w nazwie (pominięte): {len(bez_symbolu)} — np. {bez_symbolu[:3]}")
    if not wiersze:
        return 1

    # Duplikat symbolu = dwa pliki na tę samą kartotekę; PRIMARY KEY tego nie
    # blokuje (klucz to para numer+ścieżka), więc lepiej pokazać od razu.
    widziane, dubel = set(), []
    for w in wiersze:
        if w["numer_rysunku"] in widziane:
            dubel.append(w["numer_rysunku"])
        widziane.add(w["numer_rysunku"])
    if dubel:
        print(f"   ⚠️  ten sam symbol w kilku plikach: {len(dubel)} — np. {dubel[:3]}")

    print(f"\n2. {'ZAPIS' if a.zapisz else 'SUCHY PRZEBIEG'}: {len(wiersze)} wierszy"
          f" (zrodlo='reczny' — automat ich nie ruszy)")
    print(f"   przykład: {wiersze[0]['numer_rysunku']}  ->  {wiersze[0]['sciezka']}")
    if not a.zapisz:
        print("\nTo był suchy przebieg. Realny zapis: --zapisz")
        return 0

    zapisane = 0
    for i in range(0, len(wiersze), PACZKA):
        paczka = wiersze[i:i + PACZKA]
        rm_klient.master_batch(
            [{"operation": "map-model3d-zapisz", "params": w} for w in paczka])
        zapisane += len(paczka)
        print(f"   {zapisane}/{len(wiersze)}")
    print(f"\nZAPISANE: {zapisane} modeli łożysk w indeksie 3D.")
    print("W MAG widać je po synchronizacji kopii (Synchronizuj SUBIEKT).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
