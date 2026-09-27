# -*- coding: utf-8 -*-
"""Jednorazowe nadrobienie: miniatury DWF do WSZYSTKICH kartotek Subiekta.

    python subiekt_miniatury_masowo.py            # suchy przebieg — NIC nie zapisuje
    python subiekt_miniatury_masowo.py --zapisz   # realna wysyłka

Po co: od 27.09.2026 nowe kartoteki dostają miniaturę rysunku przy zasiewie
projektu (`subiekt_projekt._wyslij_miniatury_dwf`). Ten skrypt nadrabia to,
co powstało WCZEŚNIEJ — 2791 kartotek z symbolem wyglądającym na numer
rysunku. Uruchamia się RĘCZNIE i raz; potem wystarcza automat z zasiewu.

JAK SZUKA RYSUNKÓW
    Jeden przelot po `B:\\` (biblioteka) i po folderach projektów na `V:\\`
    buduje mapę `numer rysunku -> plik .dwf`. 2463 pliki w bibliotece
    znajduje w ~20 s — szukanie osobno dla każdej kartoteki trwałoby
    wielokrotnie dłużej.

    Numer rysunku wyciągamy z NAZWY PLIKU: „2455-780.09 Wałek napędu.dwf"
    -> „2455-780.09". Tak samo robi `import_bom.find_dwf_in_library`.

⚠️ NIE NADPISUJEMY (decyzja użytkownika 27.09.2026): kartoteka, która ma
   już jakiekolwiek zdjęcie, jest pomijana. Dzięki temu skrypt można puścić
   ponownie — drugi przebieg nie zdubluje galerii.

⚠️ SUCHY PRZEBIEG JEST DOMYŚLNY. Bez `--zapisz` skrypt tylko liczy i pokazuje,
   co by zrobił. Realna wysyłka to setki zapisów do Subiekta.
"""
import argparse
import base64
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")       # emoji na polskiej konsoli

import dwf_thumb
import subiekt_bridge
import subiekt_scalanie as S
from subiekt_stany import looks_like_drawing_no

#: Gdzie szukać rysunków. Biblioteka + katalog projektów — ta sama para,
#: z której korzysta arkusz (`_dwf_thumb_path_for_drawing`).
KATALOGI = [r"B:\\", r"V:\\"]

#: Ile sekund maksymalnie na skanowanie JEDNEGO drzewa. V: bywa ogromne,
#: a rysunki leżą w folderach projektów — bez limitu skan potrafi
#: przeciągnąć się w nieskończoność na archiwach.
LIMIT_SKANU_S = 240


def numer_z_nazwy(nazwa):
    """„2455-780.09 Wałek napędu.dwf" -> „2455-780.09"."""
    trzon = os.path.splitext(nazwa)[0].strip()
    return trzon.split(" ", 1)[0].strip().upper() if trzon else ""


def zbuduj_mape():
    """{NUMER RYSUNKU: ścieżka .dwf} — jeden przelot po dyskach."""
    mapa = {}
    for root in KATALOGI:
        if not os.path.isdir(root):
            print(f"   {root:6} — niedostępny, pomijam")
            continue
        t0, ile = time.time(), 0
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if not f.lower().endswith(".dwf"):
                    continue
                nr = numer_z_nazwy(f)
                # Pierwsze trafienie wygrywa: B: skanujemy przed V:, więc
                # wersja biblioteczna ma pierwszeństwo nad kopią w projekcie.
                if nr and nr not in mapa:
                    mapa[nr] = os.path.join(dirpath, f)
                    ile += 1
            if time.time() - t0 > LIMIT_SKANU_S:
                print(f"   {root:6} — przerwano po {LIMIT_SKANU_S}s")
                break
        print(f"   {root:6} — {ile} rysunków w {time.time() - t0:.0f}s")
    return mapa


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zapisz", action="store_true",
                    help="realna wysyłka (bez tego suchy przebieg)")
    ap.add_argument("--limit", type=int, default=0,
                    help="przetwórz najwyżej N kartotek (do próby)")
    a = ap.parse_args()

    print("=" * 72)
    print("MINIATURY DWF -> KARTOTEKI SUBIEKTA" +
          ("" if a.zapisz else "   [SUCHY PRZEBIEG — nic nie zapisuję]"))
    print("=" * 72)

    print("\n1. Szukam rysunków:")
    mapa = zbuduj_mape()
    print(f"   RAZEM unikalnych numerów: {len(mapa)}")
    if not mapa:
        print("   Brak rysunków — kończę.")
        return 1

    print("\n2. Czytam katalog Subiekta…")
    katalog = S.wczytaj_katalog_subiekta(max_wiek_h=999999)
    kandydaci = [k for k in katalog
                 if looks_like_drawing_no((k.get("symbol") or ""))
                 and (k.get("symbol") or "").strip().upper() in mapa]
    print(f"   kartotek: {len(katalog)}   z rysunkiem na dysku: {len(kandydaci)}")
    if a.limit:
        kandydaci = kandydaci[:a.limit]
        print(f"   --limit {a.limit}: biorę {len(kandydaci)}")
    if not kandydaci:
        print("   Nie ma czego uzupełniać — kończę.")
        return 0

    print("\n3. Sprawdzam, które mają już zdjęcie, i wysyłam brakujące…")
    maja, wyslane, bledy, puste = 0, 0, [], 0
    t0 = time.time()
    for i, k in enumerate(kandydaci, 1):
        symbol = (k.get("symbol") or "").strip()
        try:
            stan = subiekt_bridge.call(
                "zdjecie", {"plan": {"akcja": "lista", "symbol": symbol},
                            "zapisz": False}, timeout=120, write=False)
            if (stan or {}).get("zdjecia"):
                maja += 1
            else:
                sciezka = dwf_thumb.get_cached_thumb_path(mapa[symbol.upper()])
                if not sciezka or not os.path.isfile(sciezka):
                    puste += 1          # DWF bez sekcji miniatury
                elif a.zapisz:
                    with open(sciezka, "rb") as f:
                        dane = f.read()
                    subiekt_bridge.call(
                        "zdjecie",
                        {"plan": {"akcja": "dodaj", "symbol": symbol,
                                  "nazwa": f"{symbol}.png", "typ": "png",
                                  "dane_b64": base64.b64encode(dane).decode("ascii")},
                         "zapisz": True}, timeout=300, write=True)
                    wyslane += 1
                else:
                    wyslane += 1        # suchy przebieg — tylko liczymy
        except Exception as e:
            bledy.append(f"{symbol}: {str(e)[:70]}")
        if i % 50 == 0 or i == len(kandydaci):
            minelo = time.time() - t0
            zostalo = (minelo / i) * (len(kandydaci) - i)
            print(f"   {i:>5}/{len(kandydaci)}   wysłane {wyslane:>4}   "
                  f"mają {maja:>4}   bez miniatury {puste:>3}   "
                  f"błędy {len(bledy):>3}   zostało ~{zostalo / 60:.0f} min")

    print("\n" + "=" * 72)
    print(f"{'WYSŁANE' if a.zapisz else 'DO WYSŁANIA'}: {wyslane}")
    print(f"POMINIĘTE (mają już zdjęcie): {maja}")
    print(f"DWF BEZ MINIATURY: {puste}")
    print(f"BŁĘDY: {len(bledy)}")
    for b in bledy[:20]:
        print("   ⚠ " + b)
    if not a.zapisz:
        print("\nTo był SUCHY PRZEBIEG. Realna wysyłka: --zapisz")
    return 0


if __name__ == "__main__":
    sys.exit(main())
