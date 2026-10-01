"""python pozycja.py <katalog_pozycji_obecny> <SYMBOL> <NAZWA> <OPIS>
IPT: Part Number=SYMBOL, Title=NAZWA, Description=OPIS; natywna miniatura (białe tło) + PNG 600x600.
Praca na kopii; na G: trafia plik <SYMBOL>.ipt w katalogu <NAZWA>, stare w _stare, PNG w miniatury jako <NAZWA>.png."""
import ctypes, ctypes.wintypes as wt, os, shutil, sys, time, win32com.client
sys.stdout.reconfigure(encoding="utf-8")
S = os.path.dirname(os.path.abspath(__file__))
E = r"G:\Mój dysk\SUBIEKT\Elesa"
KAT, SYM, NAZWA, OPIS = sys.argv[1:5]
folder = os.path.join(E, KAT)
ipts = [f for f in os.listdir(folder) if f.lower().endswith(".ipt")]
assert len(ipts) == 1, ipts
W = os.path.join(S, "poz_work"); shutil.rmtree(W, ignore_errors=True); os.makedirs(W)
wip = os.path.join(W, SYM + ".ipt"); png_tmp = os.path.join(W, SYM + ".png")
shutil.copy2(os.path.join(folder, ipts[0]), wip)

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
    d = inv.Documents.Open(wip, True)
    d.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value = SYM
    d.PropertySets.Item("Design Tracking Properties").Item("Description").Value = OPIS
    d.PropertySets.Item("Inventor Summary Information").Item("Title").Value = NAZWA
    d.SelectSet.Clear()
    cam = inv.ActiveView.Camera
    cam.ViewOrientationType = 10759
    cam.Apply(); cam.Fit(); cam.Apply()
    inv.ActiveView.Update(); time.sleep(1.0); inv.ActiveView.Update()
    d.SetThumbnailSaveOption(79875, "")
    d.Dirty = True; d.Save(); d.Close(True)
    d2 = inv.Documents.Open(wip, True)
    d2.SelectSet.Clear()
    cam = inv.ActiveView.Camera
    cam.ViewOrientationType = 10759
    cam.Apply(); cam.Fit(); cam.Apply(); d2.SelectSet.Clear()
    cam.SaveAsBitmap(png_tmp, 600, 600, BIALY, BIALY)
    d2.Close(True)
finally:
    inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight = opcje[0], opcje[1]
    inv.ColorSchemes.EnablePrehighlight = opcje[2]
    inv.ColorSchemes.Item(opcje[3]).Activate()
    try: inv.Quit()
    except Exception: pass
    time.sleep(3)
    os.system("taskkill /F /PID %d >nul 2>&1" % pid.value)
    h = os.path.join(os.path.expanduser("~"), "Documents", "Inventor", SYM + ".htm")
    if os.path.exists(h):
        try: os.remove(h)
        except Exception: pass

a = win32com.client.Dispatch("Inventor.ApprenticeServer")
dd = a.Open(wip)
pn = dd.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value
op = dd.PropertySets.Item("Design Tracking Properties").Item("Description").Value
ti = dd.PropertySets.Item("Inventor Summary Information").Item("Title").Value
ver = dd.SoftwareVersionSaved.DisplayVersion
dd.Close()
assert (pn, op, ti) == (SYM, OPIS, NAZWA), (pn, op, ti)
assert os.path.getsize(png_tmp) > 1000
# wstawienie na G:
stare = os.path.join(folder, "_stare"); os.makedirs(stare, exist_ok=True)
for f in os.listdir(folder):
    p = os.path.join(folder, f)
    if os.path.isfile(p): shutil.move(p, os.path.join(stare, f))
mini = os.path.join(E, "miniatury"); os.makedirs(mini, exist_ok=True)
oldpng = os.path.join(mini, NAZWA + ".png")
if os.path.exists(oldpng): shutil.move(oldpng, os.path.join(stare, NAZWA + ".png"))
shutil.copy2(wip, os.path.join(folder, SYM + ".ipt"))
shutil.copy2(png_tmp, os.path.join(mini, NAZWA + ".png"))
if KAT != NAZWA: os.rename(folder, os.path.join(E, NAZWA))
print("OK | PN=%s | Title=%s | Opis=%s | wersja=%s" % (pn, ti, op, ver))

