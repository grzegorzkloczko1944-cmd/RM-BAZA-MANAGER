# -*- coding: utf-8 -*-
"""Dopisuje własność użytkownika 'Wymiar' (Ø d1 × Ø d2 × b mm) do tulei IGUS; miniatura natywna odświeżona w trybie białym."""
import ctypes, ctypes.wintypes as wt, os, sys, time, win32com.client
sys.stdout.reconfigure(encoding="utf-8")
S = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, S)
from igus_opis import wymiar
E = r"V:\! HASIOK\IGUS"
todo = []
for d in sorted(os.listdir(E)):
    p = os.path.join(E, d)
    if not os.path.isdir(p) or d.startswith("_"): continue
    w = wymiar(d)
    if not w: continue
    fl = os.listdir(p)
    main = [f for f in fl if f.lower() in (d.lower() + ".iam", d.lower() + ".ipt")]
    if main: todo.append((d, os.path.join(p, sorted(main)[0]), w))
print("tulei z wymiarem:", len(todo), flush=True)
inv = win32com.client.DispatchEx("Inventor.Application")
t = time.time()
while not inv.Ready and time.time() - t < 240: time.sleep(1)
inv.SilentOperation = True; inv.Visible = True
pid = wt.DWORD(); ctypes.windll.user32.GetWindowThreadProcessId(wt.HWND(inv.MainFrameHWND), ctypes.byref(pid))
opcje = (inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight, inv.ColorSchemes.EnablePrehighlight, inv.ActiveColorScheme.Name)
ok = 0
try:
    inv.DisplayOptions.Show3DIndicator = False; inv.GeneralOptions.EnablePrehighlight = False; inv.ColorSchemes.EnablePrehighlight = False
    inv.ColorSchemes.Item("Prezentacja").Activate()
    for sym, mp, w in todo:
        try:
            d = inv.Documents.Open(mp, True)
            ps = d.PropertySets.Item("Inventor User Defined Properties")
            try: ps.Item("Wymiar").Value = w
            except Exception: ps.Add(w, "Wymiar")
            d.SelectSet.Clear(); cam = inv.ActiveView.Camera; cam.ViewOrientationType = 10759
            cam.Apply(); cam.Fit(); cam.Apply(); inv.ActiveView.Update(); time.sleep(0.8); inv.ActiveView.Update()
            d.SetThumbnailSaveOption(79875, ""); d.Dirty = True; d.Save(); d.Close(True)
            ok += 1; print("OK %s | %s" % (sym, w), flush=True)
        except Exception as e:
            print("BŁĄD %s: %s" % (sym, str(e)[:100]), flush=True)
            try: inv.Documents.CloseAll()
            except Exception: pass
finally:
    inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight = opcje[0], opcje[1]
    inv.ColorSchemes.EnablePrehighlight = opcje[2]; inv.ColorSchemes.Item(opcje[3]).Activate()
    try: inv.Quit()
    except Exception: pass
    time.sleep(3); os.system("taskkill /F /PID %d >nul 2>&1" % pid.value)
print("KONIEC wymiarów: OK=%d z %d" % (ok, len(todo)), flush=True)
