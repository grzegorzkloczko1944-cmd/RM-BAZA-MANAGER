# -*- coding: utf-8 -*-
"""Modele 3D oringów z wymiarówki Subiekta — przez API Inventora.

    python katalog_oringow/generuj_modele.py              # suchy przebieg — NIC nie tworzy
    python katalog_oringow/generuj_modele.py --zapisz     # tworzy modele w B:\\Znormalizowane\\Oringi
    python katalog_oringow/generuj_modele.py --zapisz --limit 1 --katalog C:\\tmp\\oringi_test

Po co (user, 29.09.2026): kartoteki oringów (205, `oringi_wymiarowka.csv`
— wymiarówka z 28.09.2026) nie mają modeli, więc MAG nie ma czego wstawić.

JAK: ta sama metoda co TOOLS++ „funkcja 18 — Utwórz O-ring" (Module4,
TOOLS_CreateOring): szkic pierścienia (ID, OD = ID + 2×przekrój) na XY,
wyciągnięcie na wysokość = przekrój, zaokrąglenie 4 krawędzi kołowych
R = 0,4×przekrój. Inventor 2013: `Documents.Add` + `SaveAs` pada (err 5),
więc KOPIUJEMY SZABLON na docelową ścieżkę i otwieramy kopię — jak makro.

MATERIAŁ = kolor gumy (czerwony) — tylko te, które są w Inventorze usera:
EPDM, NBR- (z myślnikiem!), VITON, SILIKON. FKM/FPM to VITON (kauczuk
fluorowy), VMQ to silikon. Pusty materiał w CSV → odczyt z symbolu/nazwy.
Dlatego model na KARTOTEKĘ (205), nie na wymiar (148): ten sam wymiar
w dwóch gumach to dwa kolory.

PLIK:  `<symbol>.ipt`, „/" w symbolu → „x" (`OR-1,6/2-70EPDM` → `OR-1,6x2-70EPDM.ipt`)
iProperties: Part Number = SYMBOL KARTOTEKI (klucz dla MAG), Title = „oring 20x3",
Description = „Oring 20x3 EPDM".

Dodatkowo biały render 300×300 (kamera przejściowa, bez osi XYZ) do
`<katalog>\\miniatury\\<plik>.png` i lista `<katalog>\\oringi_modele.csv`
(symbol;plik;png;material) — z niej `indeks_oringi_zasiew.py` przypisuje
modele w MAG, także w firmie.

⚠️ Istniejących plików NIE nadpisujemy (pomijamy z informacją).
"""
import argparse
import csv
import os
import re
import shutil
import sys
import time

KATALOG = r"B:\Znormalizowane\Oringi"
CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oringi_wymiarowka.csv")

#: Materiał z CSV → nazwa materiału w Inventorze usera (kolor gumy).
MATERIAL = {"EPDM": "EPDM", "NBR": "NBR-", "VITON": "VITON", "FKM": "VITON",
            "FPM": "VITON", "VMQ": "SILIKON", "VQM": "SILIKON", "SILIKON": "SILIKON"}
MATERIAL_DOMYSLNY = "EPDM"

# Stałe z RxInventor.tlb (2013) — sprawdzone, nie zgadywane.
K_JOIN = 20481                 # PartFeatureOperationEnum.kJoinOperation
K_KIERUNEK = 20993             # kPositiveExtentDirection
K_OKRAG = 5124                 # CurveTypeEnum.kCircleCurve
K_IZO = 10759                  # kIsoTopRightViewOrientation
K_PART = 12290                 # kPartDocumentObject


def liczba(s):
    return float(str(s).replace(",", "."))


def material_z(w):
    m = (w.get("Material") or "").strip().upper()
    if m in MATERIAL:
        return MATERIAL[m], m
    tekst = (w["Symbol"] + " " + w.get("Nazwa", "")).upper()
    for k in ("EPDM", "NBR", "VITON", "FKM", "FPM", "VMQ", "VQM", "SILIKON"):
        if k in tekst:
            return MATERIAL[k], k + " (z symbolu)"
    return MATERIAL_DOMYSLNY, "brak — domyślnie " + MATERIAL_DOMYSLNY


def nazwa_pliku(symbol):
    return re.sub(r'[\\/:*?"<>|]', "x", symbol.strip()) + ".ipt"


def zbuduj(app, szablon, plik, idm, gr, material, symbol, png):
    """Jeden model oringu. Zwraca opis albo rzuca wyjątek."""
    shutil.copyfile(szablon, plik)
    doc = app.Documents.Open(plik, False)
    try:
        cd = doc.ComponentDefinition
        tg = app.TransientGeometry
        cm_id, cm_gr = idm / 10.0, gr / 10.0          # Inventor liczy w cm
        szkic = cd.Sketches.Add(cd.WorkPlanes.Item(3))
        srodek = tg.CreatePoint2d(0.0, 0.0)
        szkic.SketchCircles.AddByCenterRadius(srodek, (cm_id + 2 * cm_gr) / 2.0)
        szkic.SketchCircles.AddByCenterRadius(srodek, cm_id / 2.0)
        prof = szkic.Profiles.AddForSolid()
        dfn = cd.Features.ExtrudeFeatures.CreateExtrudeDefinition(prof, K_JOIN)
        dfn.SetDistanceExtent(cm_gr, K_KIERUNEK)
        cd.Features.ExtrudeFeatures.Add(dfn)

        krawedzie = app.TransientObjects.CreateEdgeCollection()
        for e in cd.SurfaceBodies.Item(1).Edges:
            if e.GeometryType == K_OKRAG:
                krawedzie.Add(e)
        try:
            fd = cd.Features.FilletFeatures.CreateFilletDefinition()
            fd.AddConstantRadiusEdgeSet(krawedzie, cm_gr * 0.4)
            cd.Features.FilletFeatures.Add(fd)
        except Exception:
            cd.Features.FilletFeatures.AddSimple(krawedzie, cm_gr * 0.4)

        mat = None
        for i in range(1, doc.Materials.Count + 1):
            if doc.Materials.Item(i).Name.lower() == material.lower():
                mat = doc.Materials.Item(i)
                break
        if mat is None:
            raise RuntimeError("w Inventorze nie ma materiału %s" % material)
        cd.Material = mat

        wym = "%sx%s" % (("%g" % idm).replace(".", ","), ("%g" % gr).replace(".", ","))
        doc.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value = symbol
        doc.PropertySets.Item("Design Tracking Properties").Item("Description").Value = \
            "Oring %s %s" % (wym, material.rstrip("-"))
        doc.PropertySets.Item("Inventor Summary Information").Item("Title").Value = "oring " + wym
        doc.Update()
        doc.Save()

        # Biały render — jak tryb „miniatura" w oknie MAG.
        cam = app.TransientObjects.CreateCamera()
        cam.SceneObject = cd
        cam.ViewOrientationType = K_IZO
        cam.Fit()
        cam.ApplyWithoutTransition()
        bialy = app.TransientObjects.CreateColor(255, 255, 255, 1)
        osie = app.DisplayOptions.Show3DIndicator
        app.DisplayOptions.Show3DIndicator = False
        try:
            cam.SaveAsBitmap(png, 300, 300, bialy, bialy)
        finally:
            app.DisplayOptions.Show3DIndicator = osie
    finally:
        doc.Close(True)
    # Zapis kopii szablonu zostawia w OldVersions „<plik>.0001.ipt" (pusty
    # szablon) — w bibliotece to śmieć. Kasujemy TYLKO kopie tego pliku.
    import glob
    baza = os.path.splitext(os.path.basename(plik))[0]
    for stary in glob.glob(os.path.join(os.path.dirname(plik), "OldVersions", glob.escape(baza) + ".*.ipt")):
        try:
            os.remove(stary)
        except OSError:
            pass


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zapisz", action="store_true", help="tworzy pliki (bez tego suchy przebieg)")
    ap.add_argument("--katalog", default=KATALOG)
    ap.add_argument("--csv", default=CSV)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    wiersze = list(csv.DictReader(open(a.csv, encoding="utf-8-sig"), delimiter=";"))
    plan, zle = [], []
    for w in wiersze:
        try:
            idm, gr = liczba(w["Srednica wewn. [mm]"]), liczba(w["Przekroj [mm]"])
        except ValueError:
            zle.append(w["Symbol"])
            continue
        if idm <= 0 or gr <= 0:
            zle.append(w["Symbol"])
            continue
        mat, skad = material_z(w)
        plan.append((w["Symbol"].strip(), idm, gr, mat, skad))
    if a.limit:
        plan = plan[:a.limit]
    nazwy = [nazwa_pliku(p[0]).lower() for p in plan]
    if len(set(nazwy)) != len(nazwy):
        print("⛔ Dwie kartoteki dają tę samą nazwę pliku — przerwane.")
        return 1

    print("1. %s: %d kartotek, do modelu %d, bez wymiaru %d %s"
          % (os.path.basename(a.csv), len(wiersze), len(plan), len(zle), zle[:5]))
    print("   materiały:", {m: sum(1 for p in plan if p[3] == m) for m in sorted({p[3] for p in plan})})
    for p in plan:
        if "(z symbolu)" in p[4] or "brak" in p[4]:
            print("   materiał %-22s %-8s  (%s)" % (p[0], p[3], p[4]))
    istnieja = [p for p in plan if os.path.exists(os.path.join(a.katalog, nazwa_pliku(p[0])))]
    print("   już są w %s (pomijam, nie nadpisuję): %d" % (a.katalog, len(istnieja)))
    if not a.zapisz:
        print("\nSUCHY PRZEBIEG — nic nie utworzono. Realnie: --zapisz")
        return 0

    import win32com.client
    app = win32com.client.GetObject(Class="Inventor.Application")
    szablon = app.FileManager.GetTemplateFile(K_PART)
    print("\n2. Inventor %s, szablon: %s" % (app.SoftwareVersion.DisplayVersion, szablon))
    os.makedirs(os.path.join(a.katalog, "miniatury"), exist_ok=True)

    lista = os.path.join(a.katalog, "oringi_modele.csv")
    zrobione = {}
    if os.path.exists(lista):
        for w in csv.DictReader(open(lista, encoding="utf-8-sig"), delimiter=";"):
            zrobione[w["symbol"]] = w
    nowe, bledy, t0 = 0, [], time.time()
    for i, (sym, idm, gr, mat, skad) in enumerate(plan, 1):
        plik = os.path.join(a.katalog, nazwa_pliku(sym))
        png = os.path.join(a.katalog, "miniatury", nazwa_pliku(sym)[:-4] + ".png")
        if os.path.exists(plik):
            # Istniejący model (np. z przerwanego przebiegu) też idzie na listę.
            zrobione.setdefault(sym, {"symbol": sym, "plik": plik,
                                      "png": png if os.path.exists(png) else "", "material": mat})
            continue
        try:
            zbuduj(app, szablon, plik, idm, gr, mat, sym, png)
            zrobione[sym] = {"symbol": sym, "plik": plik, "png": png if os.path.exists(png) else "",
                             "material": mat}
            nowe += 1
        except Exception as e:
            bledy.append("%s: %s" % (sym, str(e)[:100]))
            if os.path.exists(plik):
                try:
                    os.remove(plik)            # niedokończony model nie zostaje
                except OSError:
                    pass
        if i % 20 == 0 or i == len(plan):
            print("   %d/%d  nowe %d, błędy %d  (%.0f s)" % (i, len(plan), nowe, len(bledy), time.time() - t0))
    with open(lista, "w", encoding="utf-8-sig", newline="") as f:
        z = csv.DictWriter(f, ["symbol", "plik", "png", "material"], delimiter=";")
        z.writeheader()
        for w in sorted(zrobione.values(), key=lambda x: x["symbol"]):
            z.writerow(w)
    print("\n3. UTWORZONE: %d, błędy: %d, lista: %s" % (nowe, len(bledy), lista))
    for b in bledy[:20]:
        print("   ⛔", b)
    return 1 if bledy else 0


if __name__ == "__main__":
    sys.exit(main())
