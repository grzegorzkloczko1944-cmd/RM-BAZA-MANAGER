# -*- coding: utf-8 -*-
"""Zdjęcia kartotek w Subiekcie z miniatur biblioteki (PNG) — KROK OBOWIĄZKOWY każdego zasiewu.

Zasada usera (08.10.2026): każda pozycja zasiewana z biblioteki (O-ringi, łożyska, tuleje, HIWIN, IGUS, ELESA, …)
idzie do Subiekta Z MINIATURĄ (zdjęciem). Wywołuje to `indeks_oringi_zasiew.py --zapisz` automatycznie
(wyłączenie: `--bez-zdjec`); można też osobno:

    python zdjecia_do_subiekta.py --katalog "B:\\Znormalizowane\\Tuleje zaciskowe" --lista tuleje_modele.csv [--zapisz]

Zasady: dodaje tylko kartotekom BEZ zdjęcia (nie nadpisuje); brak kartoteki w Subiekcie = pominięcie z raportem.
Działa tylko na stacji z mostem Subiekta (MONGO). Lista CSV: symbol;plik;png[;material], z nagłówkiem.
"""
import argparse
import base64
import csv
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")


def wgraj(katalog, lista, zapisz=False, wypisz=print):
    """Zwraca (wyslane, mialy, bez_kartoteki, bledy)."""
    import subiekt_bridge as B
    sciezka = lista if os.path.isabs(lista) else os.path.join(katalog, lista)
    wiersze = list(csv.DictReader(open(sciezka, encoding="utf-8-sig"), delimiter=";"))
    wyslane, mialy, brak, bledy = 0, 0, [], []
    for w in wiersze:
        s = (w.get("symbol") or "").strip()
        png = w.get("png") or ""
        png = png if os.path.isabs(png) else os.path.join(katalog, png)
        try:
            if not s or not os.path.exists(png):
                bledy.append("%s: brak PNG" % s)
                continue
            st = B.call("zdjecie", {"plan": {"akcja": "lista", "symbol": s}, "zapisz": False}, timeout=120, write=False)
            if any(k.get("Status") == "blad" for k in st.get("kroki", [])):
                brak.append(s)
                continue
            if st.get("zdjecia"):
                mialy += 1
                continue
            if zapisz:
                with open(png, "rb") as f:
                    dane = base64.b64encode(f.read()).decode("ascii")
                B.call("zdjecie", {"plan": {"akcja": "dodaj", "symbol": s, "nazwa": s + ".png", "typ": "png",
                                            "dane_b64": dane}, "zapisz": True}, timeout=300, write=True)
            wyslane += 1
        except Exception as e:
            bledy.append("%s: %s" % (s, str(e)[:70]))
    wypisz("   zdjęcia w Subiekcie: %s %d | miały już %d | bez kartoteki %d | błędy %d" % (
        "wysłane" if zapisz else "DO WYSŁANIA", wyslane, mialy, len(brak), len(bledy)))
    if brak:
        wypisz("   bez kartoteki: %s" % brak[:10])
    for b in bledy[:10]:
        wypisz("   ⛔ " + b)
    return wyslane, mialy, brak, bledy


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--katalog", required=True)
    ap.add_argument("--lista", required=True)
    ap.add_argument("--zapisz", action="store_true")
    a = ap.parse_args()
    wgraj(a.katalog, a.lista, a.zapisz)
