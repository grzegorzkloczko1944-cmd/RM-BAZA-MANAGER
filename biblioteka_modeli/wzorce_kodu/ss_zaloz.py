# -*- coding: utf-8 -*-
"""Zakłada wersje nierdzewne zespołów w oprawach: G:\\...\\SS <symbol>\\ (model + części), materiał '304', iProperties jak w Subiekcie, miniatura natywna (białe tło) + PNG 600x600.
Praca na kopii w katalogu roboczym; na wyjście trafia gotowy katalog.
    python ss_zaloz.py --cel <katalog_wyjsciowy> [--nazwy A B ...]     # bez --nazwy: cała lista ss_lista.json
Bez --cel: G:\\Mój dysk\\SUBIEKT\\Łożyska w oprawach (PNG do ...\\miniatury)."""
import json, os, re, shutil, sys, time, ctypes, ctypes.wintypes as wt, win32com.client
sys.stdout.reconfigure(encoding="utf-8")
G = r"G:\Mój dysk\SUBIEKT\Łożyska w oprawach"
args = sys.argv[1:]
CEL = args[args.index("--cel") + 1] if "--cel" in args else G
nazwy = args[args.index("--nazwy") + 1:] if "--nazwy" in args else None
WORK = os.path.abspath("ss_work")
MAT = "304"                      # materiał „304" z InventorMaterialLibrary (wybór usera: wszędzie 304)
kMaterialAppearance = 100614
lista = [x for x in json.load(open("ss_lista.json", encoding="utf-8")) if not nazwy or x[0] in nazwy]
os.makedirs(os.path.join(CEL, "miniatury"), exist_ok=True)
os.makedirs(WORK, exist_ok=True)

inv = win32com.client.DispatchEx("Inventor.Application")     # OSOBNA instancja — sesja usera nietknięta
_t = time.time()
while not inv.Ready and time.time() - _t < 240:
    time.sleep(1)
inv.SilentOperation = True                                     # żadnych pytań o zapis/aktualizację
inv.Visible = "--widoczny" in sys.argv
app = win32com.client.Dispatch("Inventor.ApprenticeServer")
BIALY = inv.TransientObjects.CreateColor(255, 255, 255)
u32 = ctypes.windll.user32
_pid = wt.DWORD(); u32.GetWindowThreadProcessId(wt.HWND(inv.MainFrameHWND), ctypes.byref(_pid))
opcje = (inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight,
         inv.ColorSchemes.EnablePrehighlight, inv.ActiveColorScheme.Name)


def wal(symbol):
    """Średnica wałka [mm] z końcówki symbolu: ..201 -> 12, 202 -> 15, 203 -> 17, potem 5 x numer (204 -> 20 ... 212 -> 60)."""
    nn = int(re.search(r"(\d{2})$", symbol).group(1))
    return {0: 10, 1: 12, 2: 15, 3: 17}.get(nn, 5 * nn)


def wlasc(doc, symbol):
    nowy = "SS " + symbol
    doc.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value = nowy
    doc.PropertySets.Item("Design Tracking Properties").Item("Description").Value = "Zespół łożyskowy nierdzewny"
    doc.PropertySets.Item("Inventor Summary Information").Item("Title").Value = nowy


def na_stal(pdoc):
    """Materiał 304 + zdjęcie WSZYSTKICH nadpisań wyglądu (ściany/cechy/bryły) -> wygląd z materiału (Metal-045)."""
    cd = pdoc.ComponentDefinition
    try:
        mat = pdoc.Materials.Item(MAT)
    except Exception:                                      # starszy plik: dociągnij materiał z biblioteki
        inv.AssetLibraries.Item("InventorMaterialLibrary").MaterialAssets.Item(MAT).CopyTo(pdoc, True)
        mat = pdoc.Materials.Item(MAT)
    cd.Material = mat
    cd.ClearAppearanceOverrides()
    try:
        pdoc.AppearanceSourceType = kMaterialAppearance        # „Jak materiał" — kolor z materiału 304
    except Exception:
        pass
    return 1


def refs_poza(plik, kat):
    d = app.Open(plik)
    try:
        return [d.ReferencedFileDescriptors.Item(i).FullFileName for i in range(1, d.ReferencedFileDescriptors.Count + 1)
                if not d.ReferencedFileDescriptors.Item(i).FullFileName.lower().startswith(kat.lower())]
    finally:
        d.Close()


wyniki, t0 = [], time.time()
try:
    inv.DisplayOptions.Show3DIndicator = False
    inv.GeneralOptions.EnablePrehighlight = False
    inv.ColorSchemes.EnablePrehighlight = False
    inv.ColorSchemes.Item("Prezentacja").Activate()
    for k, (sym, fam, size, glowny) in enumerate(lista, 1):
        nowy = "SS " + sym
        ext = os.path.splitext(glowny)[1].lower()
        doc, notatka = None, ""
        try:
            wdir = os.path.join(WORK, nowy); shutil.rmtree(wdir, ignore_errors=True); os.makedirs(wdir)
            zrodlo = os.path.dirname(glowny)
            for f in os.listdir(zrodlo):
                p = os.path.join(zrodlo, f)
                if os.path.isfile(p) and f.lower().endswith((".ipt", ".iam")):
                    shutil.copy2(p, os.path.join(wdir, nowy + ext if p == glowny else f))
            wglowny = os.path.join(wdir, nowy + ext)
            doc = inv.Documents.Open(wglowny, True)
            zmieniono = 0
            if ext == ".iam":
                poza = [d.FullFileName for d in doc.AllReferencedDocuments if not d.FullFileName.lower().startswith(wdir.lower())]
                if poza:
                    raise RuntimeError("część poza katalogiem roboczym: %s" % poza[0][-50:])
                for d in doc.AllReferencedDocuments:
                    if d.DocumentType == 12290:
                        zmieniono += na_stal(d)
                    elif d.DocumentType == 12291:
                        d.ComponentDefinition.ClearAppearanceOverrides()
                doc.ComponentDefinition.ClearAppearanceOverrides()
            else:
                zmieniono += na_stal(doc)
            wlasc(doc, sym)
            doc.SelectSet.Clear()
            cam = inv.ActiveView.Camera
            cam.ViewOrientationType = 10759
            cam.Apply(); cam.Fit(); cam.Apply()
            doc.SelectSet.Clear()
            inv.ActiveView.Update(); time.sleep(1.0)               # dokończ rysowanie przed miniaturą
            inv.ActiveView.Update()
            doc.SetThumbnailSaveOption(79875, "")
            doc.Dirty = True
            doc.Save2(True)
            doc.Close(True); doc = None
            if ext == ".iam":
                zle = refs_poza(wglowny, wdir)
                if zle:
                    raise RuntimeError("referencje po zapisie poza katalogiem: %s" % zle[0][-50:])
            wyj = os.path.join(CEL, nowy)
            os.makedirs(wyj, exist_ok=True)
            for f in os.listdir(wdir):
                p = os.path.join(wdir, f)
                if os.path.isfile(p) and f.lower().endswith((".ipt", ".iam")):
                    shutil.copy2(p, os.path.join(wyj, f))
            wyniki.append((nowy, "OK", "%s, zmian wyglądu: %d" % (ext, zmieniono)))
        except Exception as e:
            wyniki.append((nowy, "BŁĄD", str(e)[:120]))
        finally:
            if doc is not None:
                try: doc.Close(True)
                except Exception: pass
            shutil.rmtree(os.path.join(WORK, nowy), ignore_errors=True)
        print("%d/%d %s -> %s %s (%.0f s)" % (k, len(lista), nowy, wyniki[-1][1], wyniki[-1][2], time.time() - t0), flush=True)
    # przebieg 2: PNG 600x600 z GOTOWYCH plików (w jednym otwarciu ze zmianami łapie czerwone zaznaczenie)
    for sym, fam, size, glowny in lista:
        nowy = "SS " + sym
        gotowy = os.path.join(CEL, nowy, nowy + os.path.splitext(glowny)[1].lower())
        d2 = None
        try:
            d2 = inv.Documents.Open(gotowy, True)
            d2.SelectSet.Clear()
            cam = inv.ActiveView.Camera
            cam.ViewOrientationType = 10759
            cam.Apply(); cam.Fit(); cam.Apply()
            d2.SelectSet.Clear()
            cam.SaveAsBitmap(os.path.join(CEL, "miniatury", nowy + ".png"), 600, 600, BIALY, BIALY)
        except Exception as e:
            print("PNG błąd", nowy, str(e)[:80], flush=True)
        finally:
            if d2 is not None:
                try: d2.Close(True)
                except Exception: pass
finally:
    inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight = opcje[0], opcje[1]
    inv.ColorSchemes.EnablePrehighlight = opcje[2]
    inv.ColorSchemes.Item(opcje[3]).Activate()
    try:
        inv.Quit()
    except Exception:
        pass
    time.sleep(3)
    os.system('taskkill /F /PID %d >nul 2>&1' % _pid.value)   # tylko własny proces
print("KONIEC %.0f s | %s" % (time.time() - t0, {s: sum(1 for w in wyniki if w[1] == s) for s in {w[1] for w in wyniki}}))
