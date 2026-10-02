# -*- coding: utf-8 -*-
"""Wózek TW-04-09 (pełny, zastępuje części TK-04-09) i szyny 1000 mm do wózków drylin T/N: STEP -> IPT."""
import os, sys, subprocess, time, shutil
sys.stdout.reconfigure(encoding="utf-8")
S = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, S)
from igus_opis import opis
E = r"V:\! HASIOK\IGUS"
KONW = r"C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER\biblioteka_modeli\wzorce_kodu\konwertuj_stp.py"
W = os.path.join(E, "do_konwersji", "stp_wozki")
ZAD = [("TW-04-09", "TW_04_09_27.stp"), ("TS-04-09 L1000", "TS_04_09_1000_28.stp"), ("TS-01-15 L1000", "TS_01_15_1000_29.stp"), ("NS-01-80 L1000", "NS_01_80_1000_30.stp")]
# części TK-04-09 (składowe wózka) -> do _duble_indeks (zastąpione pełnym wózkiem TW-04-09)
tk = os.path.join(E, "TK-04-09")
if os.path.isdir(tk):
    dst = os.path.join(E, "_duble_indeks"); os.makedirs(dst, exist_ok=True)
    shutil.move(tk, os.path.join(dst, "TK-04-09 (części wózka, zastąpione TW-04-09)")); print("TK-04-09 -> _duble_indeks", flush=True)
os.chdir(S)
for sym, f in ZAD:
    stp = os.path.join(W, f); ipt = os.path.join(E, sym, sym + ".ipt")
    if not os.path.exists(stp): print("BRAK STEP", sym, flush=True); continue
    if os.path.exists(ipt): print("już jest", sym, flush=True); continue
    op = opis(sym) or ""; ok = False
    for p in range(3):
        r = subprocess.run([sys.executable, KONW, stp, sym, "--tytul", sym, "--opis", op, "--cel", E], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        if r.returncode == 0 and os.path.exists(ipt): ok = True; break
        print("  próba %d nieudana (%s)" % (p + 1, sym), flush=True); time.sleep(10)
    if ok:
        st = os.path.join(E, sym, "_stare"); os.makedirs(st, exist_ok=True); shutil.copy2(stp, os.path.join(st, f)); print("OK  %s | opis: %s" % (sym, op), flush=True)
    else: print("BŁĄD", sym, flush=True)
print("KONIEC STP2", flush=True)
