# -*- coding: utf-8 -*-
"""PNG 600x600 z gotowego IPT/IAM w OSOBNYM Inventorze (białe tło, ISO). python png_izolowany.py SYMBOL [SYMBOL ...]"""
import ctypes, ctypes.wintypes as wt, os, sys, time, win32com.client
sys.stdout.reconfigure(encoding="utf-8")
G = r"G:\Mój dysk\SUBIEKT\Łożyska w oprawach"
inv = win32com.client.DispatchEx("Inventor.Application")
t = time.time()
while not inv.Ready and time.time() - t < 240: time.sleep(1)
inv.SilentOperation = True; inv.Visible = True
pid = wt.DWORD(); ctypes.windll.user32.GetWindowThreadProcessId(wt.HWND(inv.MainFrameHWND), ctypes.byref(pid))
BIALY = inv.TransientObjects.CreateColor(255, 255, 255)
o = (inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight, inv.ColorSchemes.EnablePrehighlight, inv.ActiveColorScheme.Name)
try:
    inv.DisplayOptions.Show3DIndicator = False; inv.GeneralOptions.EnablePrehighlight = False; inv.ColorSchemes.EnablePrehighlight = False
    inv.ColorSchemes.Item("Prezentacja").Activate()
    for n in sys.argv[1:]:
        f = next(os.path.join(G, n, n + e) for e in (".ipt", ".iam") if os.path.exists(os.path.join(G, n, n + e)))
        d = inv.Documents.Open(f, True)
        d.SelectSet.Clear()
        cam = inv.ActiveView.Camera; cam.ViewOrientationType = 10759
        cam.Apply(); cam.Fit(); cam.Apply(); inv.ActiveView.Update(); time.sleep(0.8); d.SelectSet.Clear()
        cam.SaveAsBitmap(os.path.join(G, "miniatury", n + ".png"), 600, 600, BIALY, BIALY)
        d.Close(True); print("PNG", n, flush=True)
finally:
    inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight = o[0], o[1]
    inv.ColorSchemes.EnablePrehighlight = o[2]; inv.ColorSchemes.Item(o[3]).Activate()
    try: inv.Quit()
    except Exception: pass
    time.sleep(3); os.system("taskkill /F /PID %d >nul 2>&1" % pid.value)
