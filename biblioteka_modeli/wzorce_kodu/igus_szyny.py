# -*- coding: utf-8 -*-
"""Szyny i prowadnice IGUS 1000 mm (STEP z igus-cad.com) -> IPT, symbol '<kod> L1000'."""
import os, re, sys, subprocess, time, shutil, glob
sys.stdout.reconfigure(encoding="utf-8")
S = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, S)
from igus_opis import opis
E = r"V:\! HASIOK\IGUS"
KONW = r"C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER\biblioteka_modeli\wzorce_kodu\konwertuj_stp.py"
src = os.path.join(E, "do_konwersji")
dirs = [os.path.join(src, d) for d in os.listdir(src) if d.startswith("stp_szyny")]
zad = []
for dd in dirs:
    for f in sorted(os.listdir(dd)):
        m = re.match(r"^((?:WSQ|WSX|WS|TS)(?:_\d{2,3}){1,3})_1000_\d+\.stp$", f, re.I)
        if not m: continue                      # pomija WJ200…, pliki 200 mm i inne
        zad.append(((m.group(1).replace("_", "-") + " L1000"), os.path.join(dd, f)))
seen = {}
for sym, p in zad: seen.setdefault(sym, p)
zad = list(seen.items())
print("do konwersji:", len(zad), [z[0] for z in zad], flush=True)
os.chdir(S)
for sym, stp in zad:
    ipt = os.path.join(E, sym, sym + ".ipt")
    if os.path.exists(ipt): print("już jest:", sym, flush=True); continue
    op = opis(sym) or ""
    ok = False
    for proba in range(3):
        r = subprocess.run([sys.executable, KONW, stp, sym, "--tytul", sym, "--opis", op, "--cel", E], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        if r.returncode == 0 and os.path.exists(ipt): ok = True; break
        print("  próba %d nieudana (%s): %s" % (proba + 1, sym, ((r.stderr or r.stdout).strip().splitlines() or [""])[-1][:140]), flush=True); time.sleep(10)
    if ok:
        st = os.path.join(E, sym, "_stare"); os.makedirs(st, exist_ok=True); shutil.copy2(stp, os.path.join(st, os.path.basename(stp)))
        print("OK  %s | opis: %s" % (sym, op), flush=True)
    else: print("BŁĄD", sym, flush=True)
print("KONIEC SZYNY", flush=True)
