# -*- coding: utf-8 -*-
"""Nazwa (Title) = SAMO Part Number (symbol) — bez średnicy wałka (wałek pójdzie do Subiekta przy mapowaniu).
Dotyczy: 74 SS + KFL08 + KP003..KP006. Praca na KOPII w katalogu roboczym (bez OldVersions na G:), odtworzenie
miniatury natywnej (osobny WIDOCZNY Inventor, białe tło), na G: wraca tylko plik modelu główny."""
import ctypes, ctypes.wintypes as wt, json, os, shutil, sys, time, win32com.client
sys.stdout.reconfigure(encoding="utf-8")
G = r"G:\Mój dysk\SUBIEKT\Łożyska w oprawach"
WORK = os.path.abspath("tyt_work")
nazwy = ["SS " + s for s, *_ in json.load(open("ss_lista.json", encoding="utf-8"))] + ["KFL08", "KP003", "KP004", "KP005", "KP006"]
if "--nazwy" in sys.argv:
    nazwy = sys.argv[sys.argv.index("--nazwy") + 1:]

inv = win32com.client.DispatchEx("Inventor.Application")
_t = time.time()
while not inv.Ready and time.time() - _t < 240: time.sleep(1)
inv.SilentOperation = True
inv.Visible = True
u32 = ctypes.windll.user32
pid = wt.DWORD(); u32.GetWindowThreadProcessId(wt.HWND(inv.MainFrameHWND), ctypes.byref(pid))
app = win32com.client.Dispatch("Inventor.ApprenticeServer")
opcje = (inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight, inv.ColorSchemes.EnablePrehighlight,
         inv.ActiveColorScheme.Name)
os.makedirs(WORK, exist_ok=True)
wyniki, t0 = [], time.time()
try:
    inv.DisplayOptions.Show3DIndicator = False
    inv.GeneralOptions.EnablePrehighlight = False
    inv.ColorSchemes.EnablePrehighlight = False
    inv.ColorSchemes.Item("Prezentacja").Activate()
    for k, n in enumerate(nazwy, 1):
        doc = None
        try:
            kat = os.path.join(G, n)
            glowny = next(os.path.join(kat, n + e) for e in (".ipt", ".iam") if os.path.exists(os.path.join(kat, n + e)))
            w = os.path.join(WORK, n); shutil.rmtree(w, ignore_errors=True); os.makedirs(w)
            for f in os.listdir(kat):
                p = os.path.join(kat, f)
                if os.path.isfile(p) and f.lower().endswith((".ipt", ".iam")):
                    shutil.copy2(p, os.path.join(w, f))
            wg = os.path.join(w, os.path.basename(glowny))
            doc = inv.Documents.Open(wg, True)
            pn = doc.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value
            if pn != n:
                raise RuntimeError("Part Number '%s' != '%s'" % (pn, n))
            doc.PropertySets.Item("Inventor Summary Information").Item("Title").Value = n
            doc.SelectSet.Clear()
            cam = inv.ActiveView.Camera
            cam.ViewOrientationType = 10759
            cam.Apply(); cam.Fit(); cam.Apply()
            inv.ActiveView.Update(); time.sleep(1.0); inv.ActiveView.Update()
            doc.SetThumbnailSaveOption(79875, "")
            doc.Dirty = True
            doc.Save2(True)
            doc.Close(True); doc = None
            shutil.copy2(wg, glowny)                    # tylko plik główny wraca na G:
            d2 = app.Open(glowny)
            try:
                t = d2.PropertySets.Item("Inventor Summary Information").Item("Title").Value
                p2 = d2.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value
                poza = [d2.ReferencedFileDescriptors.Item(i).FullFileName for i in range(1, d2.ReferencedFileDescriptors.Count + 1)
                        if not d2.ReferencedFileDescriptors.Item(i).FullFileName.lower().startswith(kat.lower())]
            finally:
                d2.Close()
            if t != n or p2 != n or poza:
                raise RuntimeError("kontrola po powrocie: title=%s pn=%s poza=%s" % (t, p2, poza[:1]))
            wyniki.append((n, "OK", ""))
        except Exception as e:
            wyniki.append((n, "BŁĄD", str(e)[:120]))
        finally:
            if doc is not None:
                try: doc.Close(True)
                except Exception: pass
            shutil.rmtree(os.path.join(WORK, n), ignore_errors=True)
        if wyniki[-1][1] != "OK" or k % 10 == 0:
            print("%d/%d %s -> %s %s (%.0f s)" % (k, len(nazwy), n, wyniki[-1][1], wyniki[-1][2], time.time() - t0), flush=True)
finally:
    inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight = opcje[0], opcje[1]
    inv.ColorSchemes.EnablePrehighlight = opcje[2]
    inv.ColorSchemes.Item(opcje[3]).Activate()
    try: inv.Quit()
    except Exception: pass
    time.sleep(3)
    os.system("taskkill /F /PID %d >nul 2>&1" % pid.value)
print("KONIEC %.0f s | %s" % (time.time() - t0, {s: sum(1 for w in wyniki if w[1] == s) for s in {w[1] for w in wyniki}}))
