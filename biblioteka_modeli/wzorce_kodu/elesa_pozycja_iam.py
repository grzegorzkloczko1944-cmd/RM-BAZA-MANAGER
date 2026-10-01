"""python pozycja_iam.py <katalog_obecny> <SYMBOL> <NAZWA> <OPIS>
IAM + jego IPT: przebudowa z lokalnymi referencjami (IPT zapisane pod nazwami <SYMBOL>-1.ipt ...),
iProperties, natywna miniatura (białe tło), PNG 600x600. Na G:: <NAZWA>\\<SYMBOL>.iam + IPT, stare w _stare, PNG w miniatury\\<NAZWA>.png"""
import ctypes, ctypes.wintypes as wt, os, shutil, sys, time, win32com.client
sys.stdout.reconfigure(encoding="utf-8")
S = os.path.dirname(os.path.abspath(__file__))
E = r"G:\Mój dysk\SUBIEKT\Elesa"
KAT, SYM, NAZWA, OPIS = sys.argv[1:5]
folder = os.path.join(E, KAT)
fl = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
iams = [f for f in fl if f.lower().endswith(".iam")]; assert len(iams) == 1, iams
W = os.path.join(S, "poz_work"); shutil.rmtree(W, ignore_errors=True); os.makedirs(W)
tmp = os.path.join(W, "src"); os.makedirs(tmp)
for f in fl: shutil.copy2(os.path.join(folder, f), tmp)
out = os.path.join(W, "out"); os.makedirs(out)

inv = win32com.client.DispatchEx("Inventor.Application")
t = time.time()
while not inv.Ready and time.time() - t < 240: time.sleep(1)
inv.SilentOperation = True; inv.Visible = True
pid = wt.DWORD(); ctypes.windll.user32.GetWindowThreadProcessId(wt.HWND(inv.MainFrameHWND), ctypes.byref(pid))
BIALY = inv.TransientObjects.CreateColor(255, 255, 255)
opcje = (inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight, inv.ColorSchemes.EnablePrehighlight, inv.ActiveColorScheme.Name)
try:
    inv.DisplayOptions.Show3DIndicator = False
    inv.GeneralOptions.EnablePrehighlight = False
    inv.ColorSchemes.EnablePrehighlight = False
    inv.ColorSchemes.Item("Prezentacja").Activate()
    old = inv.Documents.Open(os.path.join(tmp, iams[0]), False)
    occs = list(old.ComponentDefinition.Occurrences)
    print("wiązania:", old.ComponentDefinition.Constraints.Count, "| składowe:", len(occs))
    order = [os.path.basename(o.ReferencedDocumentDescriptor.FullDocumentName) for o in occs]
    mats = [o.Transformation for o in occs]
    # unikalne IPT w kolejności
    uniq = []
    for b in order:
        if b not in uniq: uniq.append(b)
    old.Close(True); inv.Documents.CloseAll()
    names = {}
    for i, b in enumerate(uniq, 1):
        d = inv.Documents.Open(os.path.join(tmp, b), False)
        nn = os.path.join(out, "%s-%d.ipt" % (SYM, i))
        d.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value = "%s-%d" % (SYM, i)
        d.SaveAs(nn, False); d.Close(True); names[b] = nn
    inv.Documents.CloseAll()
    new = inv.Documents.Add(12291, inv.FileManager.GetTemplateFile(12291), True)
    for b, m in zip(order, mats):
        occ = new.ComponentDefinition.Occurrences.Add(names[b], m); occ.Grounded = True
    new.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value = SYM
    new.PropertySets.Item("Design Tracking Properties").Item("Description").Value = OPIS
    new.PropertySets.Item("Inventor Summary Information").Item("Title").Value = NAZWA
    new.SelectSet.Clear()
    cam = inv.ActiveView.Camera
    cam.ViewOrientationType = 10759
    cam.Apply(); cam.Fit(); cam.Apply()
    inv.ActiveView.Update(); time.sleep(1.0); inv.ActiveView.Update()
    new.SetThumbnailSaveOption(79875, "")
    iam = os.path.join(out, SYM + ".iam")
    new.SaveAs(iam, False); new.Close(True)
    d2 = inv.Documents.Open(iam, True)
    d2.SelectSet.Clear()
    cam = inv.ActiveView.Camera
    cam.ViewOrientationType = 10759
    cam.Apply(); cam.Fit(); cam.Apply(); d2.SelectSet.Clear()
    png = os.path.join(out, NAZWA + ".png")
    cam.SaveAsBitmap(png, 600, 600, BIALY, BIALY)
    d2.Close(True)
finally:
    inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight = opcje[0], opcje[1]
    inv.ColorSchemes.EnablePrehighlight = opcje[2]
    inv.ColorSchemes.Item(opcje[3]).Activate()
    try: inv.Quit()
    except Exception: pass
    time.sleep(3)
    os.system("taskkill /F /PID %d >nul 2>&1" % pid.value)

a = win32com.client.Dispatch("Inventor.ApprenticeServer")
dd = a.Open(iam)
assert dd.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value == SYM
assert dd.PropertySets.Item("Design Tracking Properties").Item("Description").Value == OPIS
assert dd.PropertySets.Item("Inventor Summary Information").Item("Title").Value == NAZWA
ver = dd.SoftwareVersionSaved.DisplayVersion
rf = [fd.FullFileName for fd in dd.ReferencedFileDescriptors]; dd.Close()
assert rf and all(os.path.normcase(os.path.dirname(x)) == os.path.normcase(out) and os.path.exists(x) for x in rf), rf
assert os.path.getsize(png) > 1000
# na G:
stare = os.path.join(folder, "_stare"); os.makedirs(stare, exist_ok=True)
for f in fl: shutil.move(os.path.join(folder, f), os.path.join(stare, f))
for f in os.listdir(out):
    if f.lower().endswith((".iam", ".ipt")): shutil.copy2(os.path.join(out, f), os.path.join(folder, f))
mini = os.path.join(E, "miniatury"); os.makedirs(mini, exist_ok=True)
op = os.path.join(mini, NAZWA + ".png")
if os.path.exists(op): shutil.move(op, os.path.join(stare, NAZWA + ".png"))
shutil.copy2(png, op)
if KAT != NAZWA: os.rename(folder, os.path.join(E, NAZWA))
print("OK | IAM PN=%s | Title=%s | Opis=%s | wersja=%s | składowe: %s" % (SYM, NAZWA, OPIS, ver, [os.path.basename(x) for x in rf]))
