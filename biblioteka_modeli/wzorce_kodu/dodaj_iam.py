# -*- coding: utf-8 -*-
"""Dodaje istniejące złożenie (IAM + części w tym samym katalogu) do biblioteki: G:\\...\\<SYMBOL>\\<SYMBOL>.iam.
iProperties: Part Number = Nazwa = SYMBOL, Opis. Praca na kopii w OSOBNYM (widocznym) Inventorze, miniatura natywna (białe tło),
referencje sprawdzane przez Apprentice (muszą wskazywać na kopie).
    python dodaj_iam.py <źródło.iam> "<SYMBOL>" "<Opis>" """
import ctypes, ctypes.wintypes as wt, os, shutil, sys, time, win32com.client
sys.stdout.reconfigure(encoding="utf-8")
G = r"G:\Mój dysk\SUBIEKT\Łożyska w oprawach"
src, symbol, opis = os.path.normpath(sys.argv[1]), sys.argv[2], sys.argv[3]
kat_src = os.path.dirname(src)
app = win32com.client.Dispatch("Inventor.ApprenticeServer")


def refs(path):
    d = app.Open(path)
    try:
        return [d.ReferencedFileDescriptors.Item(i).FullFileName for i in range(1, d.ReferencedFileDescriptors.Count + 1)]
    finally:
        d.Close()


def poza(path, kat):
    return [r for r in refs(path) if not r.lower().startswith(kat.lower())]


rf = refs(src)
assert all(os.path.dirname(r).lower() == kat_src.lower() and os.path.exists(r) for r in rf), "części nie leżą obok złożenia"
w = os.path.abspath(os.path.join("iam_work", symbol)); shutil.rmtree(w, ignore_errors=True); os.makedirs(w)
shutil.copy2(src, os.path.join(w, symbol + ".iam"))
for r in rf:
    shutil.copy2(r, os.path.join(w, os.path.basename(r)))
cel = os.path.join(G, symbol)
assert not os.path.exists(cel), "katalog już istnieje: " + cel

inv = win32com.client.DispatchEx("Inventor.Application")
t = time.time()
while not inv.Ready and time.time() - t < 240: time.sleep(1)
inv.SilentOperation = True; inv.Visible = True
pid = wt.DWORD(); ctypes.windll.user32.GetWindowThreadProcessId(wt.HWND(inv.MainFrameHWND), ctypes.byref(pid))
o = (inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight, inv.ColorSchemes.EnablePrehighlight, inv.ActiveColorScheme.Name)
try:
    inv.DisplayOptions.Show3DIndicator = False; inv.GeneralOptions.EnablePrehighlight = False; inv.ColorSchemes.EnablePrehighlight = False
    inv.ColorSchemes.Item("Prezentacja").Activate()
    doc = inv.Documents.Open(os.path.join(w, symbol + ".iam"), True)
    obce = [d.FullFileName for d in doc.AllReferencedDocuments if not d.FullFileName.lower().startswith(w.lower())]
    assert not obce, "część poza katalogiem roboczym: %s" % obce[:1]
    doc.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value = symbol
    doc.PropertySets.Item("Design Tracking Properties").Item("Description").Value = opis
    doc.PropertySets.Item("Inventor Summary Information").Item("Title").Value = symbol
    doc.SelectSet.Clear()
    cam = inv.ActiveView.Camera; cam.ViewOrientationType = 10759
    cam.Apply(); cam.Fit(); cam.Apply(); inv.ActiveView.Update(); time.sleep(1.0); inv.ActiveView.Update()
    doc.SetThumbnailSaveOption(79875, ""); doc.Dirty = True
    doc.Save2(True)
    doc.Close(True)
finally:
    inv.DisplayOptions.Show3DIndicator, inv.GeneralOptions.EnablePrehighlight = o[0], o[1]
    inv.ColorSchemes.EnablePrehighlight = o[2]; inv.ColorSchemes.Item(o[3]).Activate()
    try: inv.Quit()
    except Exception: pass
    time.sleep(3); os.system("taskkill /F /PID %d >nul 2>&1" % pid.value)
z = poza(os.path.join(w, symbol + ".iam"), w)
assert not z, "po zapisie referencje poza katalogiem roboczym: %s" % z[:1]
os.makedirs(cel)
for f in os.listdir(w):
    if os.path.isfile(os.path.join(w, f)) and f.lower().endswith((".ipt", ".iam")):
        shutil.copy2(os.path.join(w, f), os.path.join(cel, f))
z = poza(os.path.join(cel, symbol + ".iam"), cel)
if z:
    shutil.rmtree(cel, ignore_errors=True)
    raise SystemExit("referencje po skopiowaniu wskazują poza katalog: %s" % z[:1])
shutil.rmtree(w, ignore_errors=True)
print("OK ->", os.path.join(cel, symbol + ".iam"), "|", sorted(os.listdir(cel)))
