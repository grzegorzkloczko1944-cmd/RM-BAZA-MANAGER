# -*- coding: utf-8 -*-
"""Natywne miniatury w plikach modeli — z białych renderów, przez Inventora.

    python katalog_opraw/miniatury_w_plikach.py --lista "B:\\Znormalizowane\\Oringi\\oringi_modele.csv"
    python katalog_opraw/miniatury_w_plikach.py --lista "B:\\...\\lozyska_oprawy_modele.csv" --zapisz

Po co (user, 29.09.2026: „modele nie mają natywnych miniatur, nie widzę ich
w Eksploratorze"): generator oringów i konwerter opraw zapisują dokumenty
otwarte NIEWIDOCZNIE — bez okna widoku Inventor nie ma z czego zrobić
miniatury (oringi: pusty obrazek 383 B, oprawy: brak). Poprawka = otworzyć
w Inventorze, `SetThumbnailSaveOption(kImportFromFile=79877, render.png)`,
zapisać. Sprawdzone: po zapisie miniatura w pliku 14 KB i Eksplorator
pokazuje model (czerwony oring).

Lista CSV jak z generatorów: symbol;plik;png[;material]. Działa w OSOBNYM,
ukrytym Inventorze (DispatchEx) — nigdy w sesji usera. Bez `--zapisz`
suchy przebieg. Pliki już mające sensowną miniaturę (> 2 KB) pomija,
chyba że `--wszystkie`.
"""
import argparse
import csv
import os
import sys
import time

K_IMPORT = 79877            # ThumbnailSaveOptionEnum.kImportFromFile (RxInventor.tlb 2013)


def nowy_inventor():
    import pythoncom
    from win32com.client import DispatchEx, dynamic
    pythoncom.CoInitialize()
    app = dynamic.Dispatch(DispatchEx("Inventor.Application")._oleobj_)
    t0 = time.time()
    while time.time() - t0 < 90:
        try:
            if app.Ready:
                break
        except Exception:
            pass
        time.sleep(1)
    time.sleep(2)
    app.Visible = False
    app.SilentOperation = True
    return app


def ma_miniature(plik):
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import indeks_modeli_3d as x
        _t, dane = x.miniatura_modelu(plik)
        return len(dane) > 2048
    except Exception:
        return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lista", required=True)
    ap.add_argument("--zapisz", action="store_true")
    ap.add_argument("--wszystkie", action="store_true", help="także pliki z miniaturą")
    a = ap.parse_args()

    wiersze = list(csv.DictReader(open(a.lista, encoding="utf-8-sig"), delimiter=";"))
    plan = [w for w in wiersze if w.get("png") and os.path.exists(w["png"]) and os.path.exists(w["plik"])]
    if not a.wszystkie:
        plan = [w for w in plan if not ma_miniature(w["plik"])]
    print("1. %s: %d modeli, do poprawy %d" % (a.lista, len(wiersze), len(plan)))
    if not a.zapisz:
        print("SUCHY PRZEBIEG — nic nie zmieniono. Realnie: --zapisz")
        return 0

    from win32com.client import dynamic
    app, ok, bledy, t0 = None, 0, [], time.time()
    try:
        for i, w in enumerate(plan, 1):
            for proba in (1, 2):
                try:
                    if app is None:
                        app = nowy_inventor()
                    d = dynamic.Dispatch(app.Documents.Open(w["plik"], False)._oleobj_)
                    try:
                        d.SetThumbnailSaveOption(K_IMPORT, w["png"])
                        d.Save()
                    finally:
                        d.Close(True)
                    ok += 1
                    # Zapis odkłada w OldVersions kopię SPRZED poprawki (bez
                    # miniatury) — w bibliotece zbędna. Tylko kopie tego pliku.
                    import glob
                    baza = os.path.splitext(os.path.basename(w["plik"]))[0]
                    for st in glob.glob(os.path.join(os.path.dirname(w["plik"]), "OldVersions",
                                                     glob.escape(baza) + ".*" + os.path.splitext(w["plik"])[1])):
                        try:
                            os.remove(st)
                        except OSError:
                            pass
                    break
                except Exception as e:
                    # Inventor padł/zawiesił się — nowy proces i druga próba.
                    try:
                        app.Quit()
                    except Exception:
                        pass
                    app = None
                    if proba == 2:
                        bledy.append("%s: %s" % (w["symbol"], str(e)[:100]))
            if i % 20 == 0 or i == len(plan):
                print("   %d/%d  ok %d, błędy %d  (%.0f s)" % (i, len(plan), ok, len(bledy), time.time() - t0),
                      flush=True)
    finally:
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
    print("2. MINIATURY WSTAWIONE: %d, błędy: %d" % (ok, len(bledy)))
    for b in bledy[:20]:
        print("   ⛔", b)
    return 1 if bledy else 0


if __name__ == "__main__":
    sys.exit(main())
