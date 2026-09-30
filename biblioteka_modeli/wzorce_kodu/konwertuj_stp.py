# -*- coding: utf-8 -*-
"""STEP -> IPT (jedna część, wiele brył) w OSOBNYM Inventorze (sesja usera nietknięta), z natywną miniaturą
(białe tło) i PNG 600x600. Wynik: <cel>\\<symbol>\\<symbol>.ipt (+ kopia STEP), <cel>\\miniatury\\<symbol>.png
    python konwertuj_stp.py <plik.stp> <SYMBOL> --tytul "<Nazwa>" [--opis "<Opis>"] [--cel <katalog>]"""
import ctypes, ctypes.wintypes as wt, os, shutil, sys, time, win32com.client
sys.stdout.reconfigure(encoding="utf-8")
G = r"G:\Mój dysk\SUBIEKT\Łożyska w oprawach"
a = sys.argv[1:]
stp, symbol = a[0], a[1]
opt = lambda k, d="": a[a.index(k) + 1] if k in a else d
tytul, opis, CEL = opt("--tytul", symbol), opt("--opis"), opt("--cel", G)
WORK = os.path.abspath("stp_work"); wdir = os.path.join(WORK, symbol)
shutil.rmtree(wdir, ignore_errors=True); os.makedirs(wdir)
os.makedirs(os.path.join(CEL, "miniatury"), exist_ok=True)

inv = win32com.client.DispatchEx("Inventor.Application")
_t = time.time()
while not inv.Ready and time.time() - _t < 240: time.sleep(1)
inv.SilentOperation = True
inv.Visible = True
u32 = ctypes.windll.user32
pid = wt.DWORD(); u32.GetWindowThreadProcessId(wt.HWND(inv.MainFrameHWND), ctypes.byref(pid))
BIALY = inv.TransientObjects.CreateColor(255, 255, 255)
opcje = (inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight, inv.ColorSchemes.EnablePrehighlight,
         inv.ActiveColorScheme.Name)
try:
    inv.DisplayOptions.Show3DIndicator = False
    inv.GeneralOptions.EnablePrehighlight = False
    inv.ColorSchemes.EnablePrehighlight = False
    inv.ColorSchemes.Item("Prezentacja").Activate()
    shutil.copy2(stp, os.path.join(wdir, symbol + ".stp"))
    imp = inv.Documents.Open(os.path.join(wdir, symbol + ".stp"), False)
    if imp.DocumentType == 12291:
        docs = list(imp.AllReferencedDocuments)
        for d in [x for x in docs if x.DocumentType == 12290] + [x for x in docs if x.DocumentType == 12291]:
            d.SaveAs(os.path.join(wdir, os.path.splitext(d.DisplayName)[0] + (".ipt" if d.DocumentType == 12290 else ".iam")), False)
        iam = os.path.join(wdir, symbol + ".iam")
        imp.SaveAs(iam, False)
        fm = inv.FileManager
        czesc = inv.Documents.Add(12290, fm.GetTemplateFile(12290), True)
        komp = czesc.ComponentDefinition.ReferenceComponents.DerivedAssemblyComponents
        dfn = komp.CreateDefinition(iam)
        dfn.DeriveStyle = 80643
        komp.Add(dfn).BreakLinkToFile()
    else:                                                  # STEP dał od razu jedną część: zapis i otwarcie WIDOCZNE (potrzebny widok)
        ipt0 = os.path.join(wdir, symbol + ".ipt")
        imp.SaveAs(ipt0, False)
        imp.Close(True)
        imp = None
        czesc = inv.Documents.Open(ipt0, True)
    cd = czesc.ComponentDefinition
    rb = cd.RangeBox
    dims = sorted(round(abs(getattr(rb.MaxPoint, x) - getattr(rb.MinPoint, x)) * 10, 1) for x in "XYZ")
    print("bryły:", cd.SurfaceBodies.Count, "| gabaryt mm:", dims, flush=True)
    czesc.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value = symbol
    czesc.PropertySets.Item("Inventor Summary Information").Item("Title").Value = tytul
    if opis:
        czesc.PropertySets.Item("Design Tracking Properties").Item("Description").Value = opis
    czesc.SelectSet.Clear()
    cam = inv.ActiveView.Camera
    cam.ViewOrientationType = 10759
    cam.Apply(); cam.Fit(); cam.Apply()
    inv.ActiveView.Update(); time.sleep(1.0); inv.ActiveView.Update()
    czesc.SetThumbnailSaveOption(79875, "")
    wyj = os.path.join(CEL, symbol); os.makedirs(wyj, exist_ok=True)
    cel_ipt = os.path.join(wyj, symbol + ".ipt")
    czesc.SaveAs(cel_ipt, False)
    czesc.Close(True)
    if imp is not None:
        try: imp.Close(True)
        except Exception: pass
    # PNG z gotowego pliku
    d2 = inv.Documents.Open(cel_ipt, True)
    d2.SelectSet.Clear()
    cam = inv.ActiveView.Camera
    cam.ViewOrientationType = 10759
    cam.Apply(); cam.Fit(); cam.Apply(); d2.SelectSet.Clear()
    cam.SaveAsBitmap(os.path.join(CEL, "miniatury", symbol + ".png"), 600, 600, BIALY, BIALY)
    d2.Close(True)
    print("OK ->", cel_ipt, flush=True)
finally:
    inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight = opcje[0], opcje[1]
    inv.ColorSchemes.EnablePrehighlight = opcje[2]
    inv.ColorSchemes.Item(opcje[3]).Activate()
    try: inv.Quit()
    except Exception: pass
    time.sleep(3)
    os.system("taskkill /F /PID %d >nul 2>&1" % pid.value)
    for f in (os.path.join(os.path.expanduser("~"), "Documents", "Inventor", symbol + ".htm"),):
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass
