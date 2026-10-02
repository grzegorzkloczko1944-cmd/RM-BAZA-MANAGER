# -*- coding: utf-8 -*-
"""STEP -> IPT dla pozycji IGUS: nowe modele pobrane z igus-cad.com oraz pozycje, które miały tylko STEP."""
import os, sys, subprocess, time, shutil, glob
sys.stdout.reconfigure(encoding="utf-8")
S = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, S)
from igus_opis import opis
E = r"V:\! HASIOK\IGUS"
KONW = r"C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER\biblioteka_modeli\wzorce_kodu\konwertuj_stp.py"
ZADANIA = [   # (symbol, plik STEP)
    ("WJ200UME-01-16", os.path.join(E, "do_konwersji", "stp", "WJ200UME_01_16_1.stp")),
    ("WJ200UME-01-25", os.path.join(E, "do_konwersji", "stp", "WJ200UME_01_25_2.stp")),
    ("WJ200UM-01-06", os.path.join(E, "do_konwersji", "stp", "WJ200UM_01_06_3.stp")),
    ("WJ200UME-01-06", os.path.join(E, "do_konwersji", "stp", "WJ200UME_01_06_4.stp")),
]
for sym in ("RJUM-01-60", "WS-20-80-200", "WWC-06-30-06"):
    found = glob.glob(os.path.join(E, sym, "*.stp")) + glob.glob(os.path.join(E, "_warianty_dlugosci", sym, "*.stp"))
    if found: ZADANIA.append((sym, found[0]))
os.chdir(S)
for sym, stp in ZADANIA:
    if not os.path.exists(stp): print("BRAK STEP:", sym, stp, flush=True); continue
    op = opis(sym) or ""
    ipt = os.path.join(E, sym, sym + ".ipt")
    if os.path.exists(ipt): print("już jest IPT:", sym, flush=True); continue
    ok = False
    for proba in range(3):
        r = subprocess.run([sys.executable, KONW, stp, sym, "--tytul", sym, "--opis", op, "--cel", E], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        if r.returncode == 0 and os.path.exists(ipt): ok = True; break
        print("  próba %d nieudana (%s): %s" % (proba + 1, sym, ((r.stderr or r.stdout).strip().splitlines() or [""])[-1][:140]), flush=True)
        time.sleep(10)
    if ok:
        st = os.path.join(E, sym, "_stare"); os.makedirs(st, exist_ok=True)
        if os.path.dirname(stp) != os.path.join(E, "do_konwersji", "stp"):    # STEP leżał w katalogu pozycji -> do _stare
            shutil.move(stp, os.path.join(st, os.path.basename(stp)))
        else:
            shutil.copy2(stp, os.path.join(st, os.path.basename(stp)))
        print("OK  %s | opis: %s" % (sym, op), flush=True)
    else: print("BŁĄD", sym, flush=True)
print("KONIEC STEP", flush=True)
