# -*- coding: utf-8 -*-
"""Zasiew indeksu modeli 3D dla ORINGÓW — wpisy ręczne + białe miniatury.

    python indeks_oringi_zasiew.py            # suchy przebieg — NIC nie zapisuje
    python indeks_oringi_zasiew.py --zapisz   # realny zapis (mapowania + miniatury MAG)
    python indeks_oringi_zasiew.py --katalog "B:\\Znormalizowane\\Łożyska w oprawach" --lista lozyska_oprawy_modele.csv
                                              # to samo dla łożysk w oprawach (katalog_opraw/)

Po co (29.09.2026): modele oringów zrobił `katalog_oringow/generuj_modele.py`
w `B:\\Znormalizowane\\Oringi` (205 plików, Part Number = symbol kartoteki).
Oringi nie mają rysunków IDW, więc indeks z automatu ich nie widzi —
jak łożyska ([[project_lozyska_katalog_28_09]], `indeks_lozyska_zasiew.py`).

Źródło: `<katalog>\\oringi_modele.csv` (symbol;plik;png;material) z generatora.
1. `map-model3d-zapisz` jako `zrodlo='reczny'` — nocny indeks tego nie ruszy;
   automatyczny wpis „bez modelu" (pusta ścieżka) dla symbolu jest usuwany.
2. Biały render z generatora → `sub-mini3d-zapisz` z `mtime = -1` (render
   z Inventora — indeks nie nadpisze go obrazkiem z pliku).
Zdjęć do SUBIEKTA ten skrypt NIE wgrywa (to zapis do Subiekta — osobna zgoda).
"""
import argparse
import base64
import csv
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

import rm_klient
from indeks_modeli_3d import skonfiguruj_serwer, MTIME_RENDER

KATALOG = r"B:\Znormalizowane\Oringi"
PACZKA = 40


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zapisz", action="store_true", help="realny zapis (bez tego suchy przebieg)")
    ap.add_argument("--katalog", default=KATALOG)
    ap.add_argument("--serwer", help="host:port RM_SERWER (domyślnie z sync_config.json)")
    ap.add_argument("--lista", default="oringi_modele.csv",
                    help="lista w katalogu (np. lozyska_oprawy_modele.csv dla opraw)")
    a = ap.parse_args()

    lista = a.lista if os.path.isabs(a.lista) else os.path.join(a.katalog, a.lista)
    if not os.path.exists(lista):
        print("⛔ Brak listy %s — najpierw katalog_oringow/generuj_modele.py" % lista)
        return 1
    wiersze = list(csv.DictReader(open(lista, encoding="utf-8-sig"), delimiter=";"))
    brak_pliku = [w["symbol"] for w in wiersze if not os.path.exists(w["plik"])]
    wiersze = [w for w in wiersze if os.path.exists(w["plik"])]
    print("1. %s: %d modeli (brak pliku: %d %s)" % (lista, len(wiersze), len(brak_pliku), brak_pliku[:3]))

    skonfiguruj_serwer(a.serwer)
    print("2. %s" % rm_klient.opis())
    bez_kartoteki = []
    for w in wiersze:
        if not rm_klient.master_read("sub-kartoteka", {"symbol": w["symbol"]}):
            bez_kartoteki.append(w["symbol"])
    print("   bez kartoteki w kopii Subiekta: %d %s" % (len(bez_kartoteki), bez_kartoteki[:5]))
    stan = {x["numer_rysunku"]: x for x in rm_klient.master_read("map-model3d-wszystkie", timeout=120)}
    juz = [w["symbol"] for w in wiersze
           if stan.get(w["symbol"].upper(), {}).get("sciezka") == w["plik"]]
    print("   już przypisane (ten sam plik): %d" % len(juz))

    print("\n3. %s: %d przypisań (zrodlo='reczny') + %d białych miniatur"
          % ("ZAPIS" if a.zapisz else "SUCHY PRZEBIEG", len(wiersze),
             sum(1 for w in wiersze if w["png"] and os.path.exists(w["png"]))))
    print("   przykład: %s -> %s" % (wiersze[0]["symbol"], wiersze[0]["plik"]))
    if not a.zapisz:
        print("\nTo był suchy przebieg. Realny zapis: --zapisz")
        return 0

    kiedy = time.strftime("%Y-%m-%dT%H:%M:%S")
    kto = "%s@%s" % (os.environ.get("USERNAME", "?"), os.environ.get("COMPUTERNAME", "?"))
    ops = []
    for w in wiersze:
        klucz = w["symbol"].upper()
        ops.append({"operation": "map-model3d-usun-pusty-auto", "params": {"numer_rysunku": klucz}})
        ops.append({"operation": "map-model3d-zapisz", "params": {
            "numer_rysunku": klucz, "sciezka": w["plik"], "kolejnosc": 0,
            "part_number": w["symbol"], "idw": None, "idw_mtime": None,
            "zrodlo": "reczny", "kto": kto, "kiedy": kiedy}})
    for i in range(0, len(ops), 200):
        rm_klient.master_batch(ops[i:i + 200], timeout=120)
    print("   przypisania: %d" % len(wiersze))

    mini, paczka = 0, []
    for w in wiersze:
        if not (w["png"] and os.path.exists(w["png"])):
            continue
        with open(w["png"], "rb") as f:
            dane = f.read()
        paczka.append({"operation": "sub-mini3d-zapisz", "params": {
            "sciezka": w["plik"], "mtime": MTIME_RENDER, "typ": "png",
            "dane_b64": base64.b64encode(dane).decode("ascii"), "kto": kto, "kiedy": kiedy}})
        if len(paczka) >= PACZKA:
            rm_klient.master_batch(paczka, timeout=120)
            mini += len(paczka)
            paczka = []
    if paczka:
        rm_klient.master_batch(paczka, timeout=120)
        mini += len(paczka)
    print("   miniatury 3D (białe, render): %d" % mini)
    print("\nGOTOWE. MAG pokaże modele od razu (kolumna 3D).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
