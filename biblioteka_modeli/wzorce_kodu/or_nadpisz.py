import sys, os, csv, time, shutil, importlib.util, ctypes, ctypes.wintypes as wt, win32com.client
sys.stdout.reconfigure(encoding="utf-8")
GEN = "C:/RMPAK_CLIENT/Repozytoria/RM-BAZA-MANAGER/katalog_oringow/"
sp = importlib.util.spec_from_file_location("gen", GEN + "generuj_modele.py"); gen = importlib.util.module_from_spec(sp); sp.loader.exec_module(gen)
B = "B:/Znormalizowane/Oringi"
W = os.path.abspath("or_work"); shutil.rmtree(W, ignore_errors=True); os.makedirs(W + "/miniatury")
rows = list(csv.DictReader(open(GEN + "oringi_do_nadpisania.csv", encoding="utf-8-sig"), delimiter=";"))
app = win32com.client.DispatchEx("Inventor.Application")
t = time.time()
while not app.Ready and time.time() - t < 240: time.sleep(1)
app.SilentOperation = True
pid = wt.DWORD(); ctypes.windll.user32.GetWindowThreadProcessId(wt.HWND(app.MainFrameHWND), ctypes.byref(pid))
ok, bl = [], []
try:
    szablon = app.FileManager.GetTemplateFile(gen.K_PART)
    print("Inventor", app.SoftwareVersion.DisplayVersion, "szablon", szablon, flush=True)
    for w in rows:
        sym = w["Symbol"]; idm, gr = gen.liczba(w["Srednica wewn. [mm]"]), gen.liczba(w["Przekroj [mm]"])
        mat, _ = gen.material_z(w)
        plik = W + "/" + gen.nazwa_pliku(sym); png = W + "/miniatury/" + gen.nazwa_pliku(sym)[:-4] + ".png"
        try:
            gen.zbuduj(app, szablon, os.path.normpath(plik), idm, gr, mat, sym, os.path.normpath(png)); ok.append((sym, mat))
        except Exception as e:
            bl.append((sym, str(e)[:120]))
finally:
    try: app.Quit()
    except Exception: pass
    time.sleep(3); os.system("taskkill /F /PID %d >nul 2>&1" % pid.value)
print("zbudowane:", len(ok), "błędy:", bl, flush=True)
