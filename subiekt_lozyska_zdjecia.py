# -*- coding: utf-8 -*-
"""Miniatury PNG łożysk → galeria zdjęć kartotek Subiekta.

    python subiekt_lozyska_zdjecia.py            # suchy przebieg — NIC nie zapisuje
    python subiekt_lozyska_zdjecia.py --zapisz   # realna wysyłka

Po co: 28.09.2026 założyliśmy 1127 kartotek łożysk (4 warianty na oznaczenie:
ZZ / 2RS / SS ZZ / SS 2RS) z modeli w `C:\\iLogic\\LOZYSKA\\gotowe`. Renderer
Inventora generuje do nich PNG-i w `C:\\iLogic\\LOZYSKA\\miniatury`. Ten skrypt
dowozi je do Subiekta.

JAK ŁĄCZY PLIK Z KARTOTEKĄ
    Nazwa pliku PNG = nazwa kartoteki, np. `SS 6004 2RS 20x42x12.png`.
    Symbol kartoteki to ta nazwa BEZ wymiarów: `SS 6004 2RS` (tak samo robi
    generator planu kartotek — Part Number z iProperties modelu).

DOMYŚLNIE NIE NADPISUJEMY (ta sama zasada co w subiekt_miniatury_masowo.py):
   kartoteka, która ma już jakiekolwiek zdjęcie, jest pomijana. Dzięki temu
   skrypt można puszczać wielokrotnie w miarę, jak renderer dorabia PNG-i —
   drugi przebieg nie zdubluje galerii i nie ruszy tego, co już wgrane.

   `--nadpisz` odwraca to: stare zdjęcie jest kasowane, wchodzi świeży
   render. ⚠️ Użyte RAZ, 28.09.2026, przy pierwszym wgraniu — i to była
   zgoda JEDNORAZOWA, nie stała reguła dla łożysk. Każde kolejne
   nadpisanie UZGODNIĆ Z UŻYTKOWNIKIEM PRZED uruchomieniem.

⚠️ SUCHY PRZEBIEG JEST DOMYŚLNY. Bez `--zapisz` skrypt tylko liczy i pokazuje,
   co by zrobił.
"""
import argparse
import base64
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")       # emoji na polskiej konsoli

import subiekt_bridge

#: Gdzie renderer Inventora kładzie PNG-i.
KATALOG_MINIATUR = r"C:\iLogic\LOZYSKA\miniatury"

#: Nazwa pliku → (symbol, wymiary). „SS 6004 2RS 20x42x12" → („SS 6004 2RS", …)
WZOR = re.compile(r"^(.*?)\s+(\d+x\d+x[\d.]+)$")


def symbol_z_nazwy(nazwa):
    """Symbol kartoteki z nazwy pliku (bez rozszerzenia). None, gdy nie pasuje."""
    m = WZOR.match(nazwa)
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zapisz", action="store_true",
                    help="realna wysyłka do Subiekta (bez tego suchy przebieg)")
    ap.add_argument("--limit", type=int, default=0,
                    help="weź tylko N pierwszych (0 = wszystkie)")
    ap.add_argument("--katalog", default=KATALOG_MINIATUR)
    # ⚠️ NIE URUCHAMIAĆ BEZ PYTANIA. Zgoda na nadpisanie padła RAZ,
    # 28.09.2026, dla pierwszego wgrania łożysk — użytkownik zastrzegł
    # wprost, że to decyzja na tamten dzień, a nie stała reguła.
    # Reszta systemu zdjęć nie nadpisuje nigdy (subiekt_miniatury_masowo.py).
    ap.add_argument("--nadpisz", action="store_true",
                    help="zastąp istniejące zdjęcia (usuwa stare z galerii)")
    a = ap.parse_args()

    print("1. Szukam miniatur PNG…")
    if not os.path.isdir(a.katalog):
        print(f"   ⛔ Nie ma katalogu {a.katalog}")
        return 1
    pliki = {}
    for f in sorted(os.listdir(a.katalog)):
        if not f.lower().endswith(".png"):
            continue
        sym = symbol_z_nazwy(os.path.splitext(f)[0])
        if sym:
            pliki[sym] = os.path.join(a.katalog, f)
    print(f"   {len(pliki)} plików z rozpoznanym symbolem ({a.katalog})")
    if not pliki:
        return 1

    kandydaci = sorted(pliki)
    if a.limit:
        kandydaci = kandydaci[:a.limit]
        print(f"   --limit {a.limit}: biorę {len(kandydaci)}")

    print("\n2. Sprawdzam, które kartoteki mają już zdjęcie, i wysyłam brakujące…")
    if not a.zapisz:
        print("   (SUCHY PRZEBIEG — nic nie zostanie zapisane)")
    maja, wyslane, brak_kartoteki, bledy = 0, 0, [], []
    zastapione = 0
    t0 = time.time()
    for i, symbol in enumerate(kandydaci, 1):
        try:
            stan = subiekt_bridge.call(
                "zdjecie", {"plan": {"akcja": "lista", "symbol": symbol},
                            "zapisz": False}, timeout=120, write=False)
            # Brak kartoteki i kartoteka bez zdjęć wyglądają podobnie —
            # rozróżnia je pole „istnieje" w odpowiedzi mostu.
            if stan is None or stan.get("istnieje") is False:
                brak_kartoteki.append(symbol)
                continue
            stare = (stan or {}).get("zdjecia") or []
            if stare and not a.nadpisz:
                maja += 1
                continue
            if stare and a.nadpisz and a.zapisz:
                # Najpierw kasujemy stare, potem dodajemy nowe — inaczej
                # galeria rosłaby przy każdym przebiegu.
                subiekt_bridge.call(
                    "zdjecie", {"plan": {"akcja": "usun", "symbol": symbol,
                                         "numery": [z["Numer"] for z in stare]},
                                "zapisz": True}, timeout=120, write=True)
                zastapione += 1
            elif stare and a.nadpisz:
                zastapione += 1              # suchy przebieg — tylko liczymy
            if a.zapisz:
                with open(pliki[symbol], "rb") as f:
                    dane = f.read()
                subiekt_bridge.call(
                    "zdjecie",
                    {"plan": {"akcja": "dodaj", "symbol": symbol,
                              "nazwa": f"{symbol}.png", "typ": "png",
                              "dane_b64": base64.b64encode(dane).decode("ascii")},
                     "zapisz": True}, timeout=300, write=True)
            wyslane += 1
        except Exception as e:
            bledy.append(f"{symbol}: {str(e)[:70]}")
        if i % 50 == 0 or i == len(kandydaci):
            minelo = time.time() - t0
            print(f"   {i}/{len(kandydaci)}  wysłane {wyslane} (w tym zastąpione {zastapione}), "
                  f"miały {maja}, bez kartoteki {len(brak_kartoteki)}, błędy {len(bledy)}  ({minelo:.0f} s)")

    print(f"\n{'WYSŁANE' if a.zapisz else 'DO WYSŁANIA (sucho)'}: {wyslane}")
    if zastapione:
        print(f"Zastąpione (stare zdjęcie usunięte): {zastapione}")
    print(f"Miały już zdjęcie (pominięte): {maja}")
    if brak_kartoteki:
        print(f"Bez kartoteki w Subiekcie: {len(brak_kartoteki)} — np. {brak_kartoteki[:5]}")
    if bledy:
        print(f"BŁĘDY: {len(bledy)}")
        for b in bledy[:10]:
            print("   ", b)
    if not a.zapisz:
        print("\nTo był suchy przebieg. Realna wysyłka: --zapisz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
