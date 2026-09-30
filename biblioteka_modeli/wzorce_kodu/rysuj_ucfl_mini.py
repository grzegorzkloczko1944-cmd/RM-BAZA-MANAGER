# -*- coding: utf-8 -*-
"""Rysuje UCFL MINI od zera (jedna część, 5 brył: obudowa, pierścień zewn., pierścień wewn., koszyk, smarownica).
Wymiary [mm]: d wałek, E rozstaw otworów, L długość, H średnica bossa, A grubość obudowy, B szerokość pierścienia wewn.,
otwory mocujące Ø12. Gniazdo wkładki Ø40 (jak w FL203/UC20x). Osobny Inventor; miniatura natywna; PNG osobno.
    python rysuj_ucfl_mini.py <SYMBOL> --d 12 --E 76 --L 97.5 --H 56 --A 25.4 --B 31 [--cel <katalog>]"""
import ctypes, ctypes.wintypes as wt, math, os, shutil, sys, time, pythoncom, win32com.client
sys.stdout.reconfigure(encoding="utf-8")
G = r"G:\Mój dysk\SUBIEKT\Łożyska w oprawach"
a = sys.argv[1:]
symbol = a[0]
p = lambda k, d: float(a[a.index(k) + 1]) if k in a else d
d_, E_, L_, H_, A_, B_ = p("--d", 12), p("--E", 76), p("--L", 97.5), p("--H", 56), p("--A", 25.4), p("--B", 31)
CEL = a[a.index("--cel") + 1] if "--cel" in a else G
OD_SEAT = 40.0                                   # gniazdo/kulista średnica zewnętrzna wkładki (jak UC20x)
HOLE_D = 12.0
cm = lambda mm: mm / 10.0

tl = pythoncom.LoadRegTypeLib('{D98A091D-3A0F-4C3E-B36E-61F62068D488}', 1, 0, 0)
ENUM = {}
for i in range(tl.GetTypeInfoCount()):
    ti = tl.GetTypeInfo(i); at = ti.GetTypeAttr()
    for j in range(at.cVars):
        v = ti.GetVarDesc(j)
        if v.varkind == pythoncom.VAR_CONST: ENUM[ti.GetNames(v.memid)[0]] = v.value
kJoin, kCut, kNew = ENUM["kJoinOperation"], ENUM["kCutOperation"], ENUM["kNewBodyOperation"]
kPos, kSym = ENUM["kPositiveExtentDirection"], ENUM["kSymmetricExtentDirection"]

inv = win32com.client.DispatchEx("Inventor.Application")
t = time.time()
while not inv.Ready and time.time() - t < 240: time.sleep(1)
inv.SilentOperation = True; inv.Visible = True
pid = wt.DWORD(); ctypes.windll.user32.GetWindowThreadProcessId(wt.HWND(inv.MainFrameHWND), ctypes.byref(pid))
TG = inv.TransientGeometry
P = lambda x, y: TG.CreatePoint2d(cm(x), cm(y))
BIALY = inv.TransientObjects.CreateColor(255, 255, 255)
o = (inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight, inv.ColorSchemes.EnablePrehighlight, inv.ActiveColorScheme.Name)
try:
    inv.DisplayOptions.Show3DIndicator = False; inv.GeneralOptions.EnablePrehighlight = False; inv.ColorSchemes.EnablePrehighlight = False
    inv.ColorSchemes.Item("Prezentacja").Activate()
    doc = inv.Documents.Add(12290, inv.FileManager.GetTemplateFile(12290), True)
    cd = doc.ComponentDefinition
    YZ, XZ, XY = cd.WorkPlanes.Item(1), cd.WorkPlanes.Item(2), cd.WorkPlanes.Item(3)
    Rb, Rs, Rh = H_ / 2, OD_SEAT / 2, HOLE_D / 2
    Rl = (L_ - E_) / 2; cx = E_ / 2                      # promień oczka i położenie środka oczka
    ca = (Rb - Rl) / cx; sa = math.sqrt(1 - ca * ca)      # styczne zewnętrzne boss <-> oczko
    P1 = (Rb * ca, Rb * sa); P2 = (cx + Rl * ca, Rl * sa)

    def plane_z(z_mm):
        wp = cd.WorkPlanes.AddByPlaneAndOffset(XY, cm(z_mm)); wp.Visible = False
        return wp

    def extrude(sk, dist_mm, op, direction=kPos):
        sk.Visible = False
        pr = sk.Profiles.AddForSolid()
        df = cd.Features.ExtrudeFeatures.CreateExtrudeDefinition(pr, op)
        df.SetDistanceExtent(cm(dist_mm), direction)
        return cd.Features.ExtrudeFeatures.Add(df)

    # --- OBUDOWA: płyta kołnierza (hull boss + 2 oczka) i boss
    z0 = -A_ / 2
    plate_t = 10.0
    wz = plane_z(z0)
    sk = cd.Sketches.Add(wz); sk.SketchCircles.AddByCenterRadius(P(0, 0), cm(Rb)); extrude(sk, plate_t, kNew)
    for sg in (-1, 1):
        sk = cd.Sketches.Add(wz); sk.SketchCircles.AddByCenterRadius(P(sg * cx, 0), cm(Rl)); extrude(sk, plate_t, kJoin)
        pts = [P(sg * P1[0], P1[1]), P(sg * P2[0], P2[1]), P(sg * P2[0], -P2[1]), P(sg * P1[0], -P1[1])]
        sk = cd.Sketches.Add(wz)
        l = [sk.SketchLines.AddByTwoPoints(pts[0], pts[1])]
        l.append(sk.SketchLines.AddByTwoPoints(l[0].EndSketchPoint, pts[2]))
        l.append(sk.SketchLines.AddByTwoPoints(l[1].EndSketchPoint, pts[3]))
        l.append(sk.SketchLines.AddByTwoPoints(l[2].EndSketchPoint, l[0].StartSketchPoint))
        extrude(sk, plate_t, kJoin)
    sk = cd.Sketches.Add(wz); sk.SketchCircles.AddByCenterRadius(P(0, 0), cm(Rb))
    extrude(sk, A_, kJoin)
    sk = cd.Sketches.Add(wz); sk.Visible = False           # gniazdo Ø40 (przelotowe) i otwory mocujące
    sk.SketchCircles.AddByCenterRadius(P(0, 0), cm(Rs))
    for s in (-1, 1): sk.SketchCircles.AddByCenterRadius(P(s * cx, 0), cm(Rh))
    pr = sk.Profiles.AddForSolid()
    # przecięcie: profil = obszary kół; wycinamy przelotowo
    df = cd.Features.ExtrudeFeatures.CreateExtrudeDefinition(pr, kCut)
    df.SetThroughAllExtent(kPos)
    cd.Features.ExtrudeFeatures.Add(df)
    cd.SurfaceBodies.Item(1).Name = "Obudowa"

    # --- WKŁADKA: 3 bryły obrotowe (szkic na XZ: x = promień, y = oś)
    def rev(rysuj, nazwa):
        sk = cd.Sketches.Add(XZ); sk.Visible = False
        rysuj(sk)
        ax = sk.SketchLines.AddByTwoPoints(P(0, -25), P(0, 25)); ax.Construction = True
        pr = sk.Profiles.AddForSolid()
        f = cd.Features.RevolveFeatures.AddFull(pr, ax, kNew)
        f.SurfaceBodies.Item(1).Name = nazwa

    wo = 19.0                                            # szerokość pierścienia zewnętrznego
    zo = wo / 2; ro = math.sqrt(Rs * Rs - zo * zo); ri_o = 15.0

    def zewn(sk):
        l1 = sk.SketchLines.AddByTwoPoints(P(ri_o, -zo), P(ro, -zo))
        ar = sk.SketchArcs.AddByThreePoints(l1.EndSketchPoint, P(Rs, 0), P(ro, zo))
        l2 = sk.SketchLines.AddByTwoPoints(ar.EndSketchPoint, P(ri_o, zo))
        sk.SketchLines.AddByTwoPoints(l2.EndSketchPoint, l1.StartSketchPoint)
    rev(zewn, "Pierscien zewnetrzny")
    rev(lambda sk: sk.SketchLines.AddAsTwoPointRectangle(P(d_ / 2, -B_ / 2), P(13.0, B_ / 2)), "Pierscien wewnetrzny")
    rev(lambda sk: sk.SketchLines.AddAsTwoPointRectangle(P(13.0, -7.0), P(ri_o, 7.0)), "Koszyk")

    # --- SMARONICZKA na bossie (+Y): szyjka Ø6 i łebek Ø8
    def plane_y(y_mm):
        wp = cd.WorkPlanes.AddByPlaneAndOffset(XZ, cm(y_mm))
        if wp.Plane.RootPoint.Y * 10 * (1 if y_mm >= 0 else -1) < 0:
            wp.Delete(); wp = cd.WorkPlanes.AddByPlaneAndOffset(XZ, -cm(y_mm))
        wp.Visible = False
        return wp
    # otwór w bossie pod smarownicę (Ø6, od gniazda do zewnątrz), potem smarownica jako jedna bryła obrotowa
    wp = plane_y(Rs)
    sk = cd.Sketches.Add(wp); sk.Visible = False; sk.SketchCircles.AddByCenterRadius(P(0, 0), cm(3.0))
    pr = sk.Profiles.AddForSolid()
    df = cd.Features.ExtrudeFeatures.CreateExtrudeDefinition(pr, kCut)
    df.SetDistanceExtent(cm(Rb - Rs), kPos)
    cd.Features.ExtrudeFeatures.Add(df)
    sk = cd.Sketches.Add(XY); sk.Visible = False
    pts = [P(0, Rs), P(3.0, Rs), P(3.0, Rb), P(4.0, Rb), P(4.0, Rb + 6.0), P(0, Rb + 6.0)]
    l = [sk.SketchLines.AddByTwoPoints(pts[0], pts[1])]
    for i in range(2, 6): l.append(sk.SketchLines.AddByTwoPoints(l[-1].EndSketchPoint, pts[i]))
    l.append(sk.SketchLines.AddByTwoPoints(l[-1].EndSketchPoint, l[0].StartSketchPoint))
    ax = l[-1]                                          # linia na osi Y (x = 0) tworzy zamknięcie profilu i jest osią
    pr = sk.Profiles.AddForSolid()
    f = cd.Features.RevolveFeatures.AddFull(pr, ax, kNew)
    f.SurfaceBodies.Item(1).Name = "Smarownica"
    # kontrola
    n = cd.SurfaceBodies.Count
    rb = cd.RangeBox
    dims = sorted(round(abs(getattr(rb.MaxPoint, k) - getattr(rb.MinPoint, k)) * 10, 1) for k in "XYZ")
    for b in cd.SurfaceBodies:
        r = b.RangeBox
        print("  %-22s X[%7.1f %7.1f] Y[%7.1f %7.1f] Z[%7.1f %7.1f]" % ((b.Name,) + tuple(round(v * 10, 1) for v in (r.MinPoint.X, r.MaxPoint.X, r.MinPoint.Y, r.MaxPoint.Y, r.MinPoint.Z, r.MaxPoint.Z))), flush=True)
    print("bryły:", n, [b.Name for b in cd.SurfaceBodies], "| gabaryt mm:", dims, "| rozstaw/otw:", E_, HOLE_D, flush=True)
    doc.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value = symbol
    doc.PropertySets.Item("Inventor Summary Information").Item("Title").Value = symbol
    doc.PropertySets.Item("Design Tracking Properties").Item("Description").Value = "Zespół łożyskowy"
    doc.SelectSet.Clear()
    cam = inv.ActiveView.Camera; cam.ViewOrientationType = 10759
    cam.Apply(); cam.Fit(); cam.Apply(); inv.ActiveView.Update(); time.sleep(1.0); inv.ActiveView.Update()
    doc.SetThumbnailSaveOption(79875, "")
    wyj = os.path.join(CEL, symbol); os.makedirs(wyj, exist_ok=True)
    doc.SaveAs(os.path.join(wyj, symbol + ".ipt"), False)
    os.makedirs(os.path.join(CEL, "miniatury"), exist_ok=True)
    doc.SelectSet.Clear()
    cam = inv.ActiveView.Camera; cam.ViewOrientationType = 10759
    cam.Apply(); cam.Fit(); cam.Apply(); inv.ActiveView.Update(); time.sleep(0.8); doc.SelectSet.Clear()
    cam.SaveAsBitmap(os.path.join(CEL, "miniatury", symbol + ".png"), 600, 600, BIALY, BIALY)
    doc.Close(True)
    print("OK ->", os.path.join(wyj, symbol + ".ipt"), flush=True)
finally:
    inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight = o[0], o[1]
    inv.ColorSchemes.EnablePrehighlight = o[2]; inv.ColorSchemes.Item(o[3]).Activate()
    try: inv.Quit()
    except Exception: pass
    time.sleep(3); os.system("taskkill /F /PID %d >nul 2>&1" % pid.value)
