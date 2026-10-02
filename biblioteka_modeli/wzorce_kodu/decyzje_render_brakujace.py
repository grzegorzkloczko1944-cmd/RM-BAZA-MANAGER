import ctypes, ctypes.wintypes as wt, os, sys, time, csv, shutil, win32com.client
sys.stdout.reconfigure(encoding="utf-8")
S = os.path.dirname(os.path.abspath(__file__)); T = os.path.join(S, "thumbs")
E = r"G:\Mój dysk\SUBIEKT\Elesa"
BAZA = {"zrobione": E, "do_decyzji": E + r"\_do_decyzji", "w_bibliotece": E + r"\_juz_w_bibliotece", "rzadkie": E + r"\_rzadkie"}
rows = list(csv.DictReader(open(os.path.join(T, "manifest.csv"), encoding="utf-8-sig"), delimiter=";"))
todo = [r for r in rows if not r["png"] and r["ext"] in (".ipt", ".iam", ".stp", ".step")]
print("do wyrenderowania:", len(todo), flush=True)
inv = win32com.client.DispatchEx("Inventor.Application")
t = time.time()
while not inv.Ready and time.time() - t < 240: time.sleep(1)
inv.SilentOperation = True; inv.Visible = True
pid = wt.DWORD(); ctypes.windll.user32.GetWindowThreadProcessId(wt.HWND(inv.MainFrameHWND), ctypes.byref(pid))
BIALY = inv.TransientObjects.CreateColor(255, 255, 255)
opcje = (inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight, inv.ColorSchemes.EnablePrehighlight, inv.ActiveColorScheme.Name)
ok = 0; blad = []
try:
    inv.DisplayOptions.Show3DIndicator = False
    inv.GeneralOptions.EnablePrehighlight = False
    inv.ColorSchemes.EnablePrehighlight = False
    inv.ColorSchemes.Item("Prezentacja").Activate()
    for i, r in enumerate(todo, 1):
        p = os.path.join(BAZA[r["grupa"]], r["nazwa"], r["plik"])
        out = os.path.join(T, "%s__%s.png" % (r["grupa"], r["nr"]))
        try:
            d = inv.Documents.Open(p, True)
            d.SelectSet.Clear()
            cam = inv.ActiveView.Camera
            cam.ViewOrientationType = 10759
            cam.Apply(); cam.Fit(); cam.Apply(); d.SelectSet.Clear()
            cam.SaveAsBitmap(out, 300, 300, BIALY, BIALY)
            d.Close(True)
            ok += 1
            print("OK %d/%d %s" % (i, len(todo), r["nazwa"]), flush=True)
        except Exception as e:
            blad.append(r["nazwa"]); print("BŁĄD %d/%d %s: %s" % (i, len(todo), r["nazwa"], str(e)[:80]), flush=True)
            try: inv.Documents.CloseAll()
            except Exception: pass
finally:
    inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight = opcje[0], opcje[1]
    inv.ColorSchemes.EnablePrehighlight = opcje[2]
    inv.ColorSchemes.Item(opcje[3]).Activate()
    try: inv.Quit()
    except Exception: pass
    time.sleep(3)
    os.system("taskkill /F /PID %d >nul 2>&1" % pid.value)
print("KONIEC: OK=%d, błędy=%d" % (ok, len(blad)), blad, flush=True)
