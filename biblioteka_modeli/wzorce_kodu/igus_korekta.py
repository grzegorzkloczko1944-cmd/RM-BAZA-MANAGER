# -*- coding: utf-8 -*-
"""Korekta struktury katalogu IGUS (bez Inventora, nic nie kasuje):
 1) PRT: błędne pozycje -> IGUS_stare_v1\\_poprawione_PRT, nowe pełne złożenia z kodem wykonania
 2) zagnieżdżone złożenia PRT-01-200-TO-* -> IGUS\\_zagniezdzone (cały rekurencyjny zestaw plików)
 3) duble indeksu (…-N po dwóch liczbach) -> IGUS\\_duble_indeks, a gdy brak bazy: baza z oryginałów z _stare
"""
import os, re, sys, json, shutil, collections
import win32com.client
sys.stdout.reconfigure(encoding="utf-8")
S = os.path.dirname(os.path.abspath(__file__))
H = r"V:\! HASIOK"; E = os.path.join(H, "IGUS"); OLD = os.path.join(H, "IGUS_stare_v1")
app = win32com.client.Dispatch("Inventor.ApprenticeServer")
def refs(p):
    try:
        d = app.Open(p)
        try: return [fd.FullFileName for fd in d.ReferencedFileDescriptors]
        finally: d.Close()
    except Exception: return None
def tree(p, seen=None):
    seen = seen if seen is not None else []
    for r in refs(p) or []:
        if r not in seen:
            seen.append(r)
            if r.lower().endswith(".iam"): tree(r, seen)
    return seen
def mv(src, dstdir):
    os.makedirs(dstdir, exist_ok=True)
    dst = os.path.join(dstdir, os.path.basename(src))
    if os.path.exists(dst): dst += "_" + str(len(os.listdir(dstdir)))
    shutil.move(src, dst); return dst
def kopia(files, d):
    os.makedirs(d, exist_ok=True)
    for f in files: shutil.copy2(f, os.path.join(d, os.path.basename(f)))

# 1) PRT
wyb = json.load(open(os.path.join(S, "igus_prt_wybor.json"), encoding="utf-8"))
for bad in ("PRT-01-100", "PRT-01-150", "PRT-01-200", "PRT-01-300"):
    p = os.path.join(E, bad)
    if os.path.isdir(p): print("PRT stary ->", mv(p, os.path.join(OLD, "_poprawione_PRT")))
for sym, v in wyb.items():
    if not v: continue
    d = os.path.join(E, sym)
    if os.path.isdir(d): continue
    files = [v["iam"]] + v["skladowe"]
    if len({os.path.basename(f).lower() for f in files}) != len(files): print("kolizja nazw PRT", sym); continue
    kopia(files, d); print("PRT nowy:", sym, len(files), "plików")
# 2) zagnieżdżone
for sym, iam in (("PRT-01-200-TO-AT10", None), ("PRT-01-200-TO-HTD8M", None)):
    pass
import csv
dump = os.path.join(S, "zrzut_modeli.csv")
for sym, rx in (("PRT-01-200-TO-AT10", r"PRT[_-]01[_-]200[_-]TO[_-]AT10"), ("PRT-01-200-TO-HTD8M", r"PRT[_-]01[_-]200[_-]TO[_-]HTD8M")):
    d = os.path.join(E, "_zagniezdzone", sym)
    if os.path.isdir(d): continue
    cands = [os.path.join(r["folder"], r["plik"]) for r in csv.DictReader(open(dump, encoding="utf-8-sig"), delimiter=";") if r["ext"] == ".iam" and re.search(rx, r["plik"], re.I) and not re.search(r"Library|Workspace", r["folder"], re.I)]
    cands.sort(key=lambda p: (0 if p.upper().startswith("C:") else 1, len(p)))
    if not cands: print("brak IAM dla", sym); continue
    top = cands[0]; allf = [top] + tree(top)
    names = [os.path.basename(f).lower() for f in allf]
    if len(set(names)) != len(names) or any(not os.path.exists(f) for f in allf): print("zagnieżdżone: kolizja/brak", sym, len(allf)); continue
    kopia(allf, d); print("zagnieżdżone:", sym, len(allf), "plików z", top)
# 3) duble indeksu
FAM = re.compile(r"^(NW|RJUM|FJUM|QJFM)-(\d{2})-(\d{2,3})-(\d)$")
WJNOISE = re.compile(r"^(WJ[A-Z0-9]*)-(\d{2})-(\d{2})((?:-?\d+|-?[a-z]+\d*|-[A-Z])+)$")          # dopiski Inventora: -2, -3, 1, jj, -Z …
dirs = [x for x in os.listdir(E) if os.path.isdir(os.path.join(E, x)) and not x.startswith("_")]
for x in sorted(dirs):
    m = WJNOISE.match(x) or FAM.match(x)
    if not m: continue
    base = "%s-%s-%s" % m.groups()[:3]
    full = os.path.join(E, x)
    if base in dirs or os.path.isdir(os.path.join(E, base)):
        print("duble indeksu:", x, "->", mv(full, os.path.join(E, "_duble_indeks")))
    else:
        st = os.path.join(full, "_stare")
        files = [os.path.join(st, f) for f in os.listdir(st)] if os.path.isdir(st) else []
        nd = os.path.join(E, base)
        if files and not os.path.isdir(nd):
            kopia(files, nd); print("baza z oryginałów:", base, "(z", x + ")")
            mv(full, os.path.join(E, "_duble_indeks")); dirs.append(base)
        else: print("pozostawiono:", x)
print("KONIEC KOREKTY STRUKTURY")
