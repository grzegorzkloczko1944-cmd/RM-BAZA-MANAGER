import os, re, shutil, json, sys
E = r"G:\Mój dysk\SUBIEKT\Elesa"
LIB = r"B:\Elementy handlowe\Elesa-Ganter"
APPLY = "--zapisz" in sys.argv
lib = set()
for r, d, fs in os.walk(LIB):
    d[:] = [x for x in d if x.lower() != "oldversions"]
    for f in fs:
        if f.lower().endswith((".ipt", ".iam", ".stp")): lib.add(os.path.splitext(f)[0].lower())
def in_lib(p):
    p = p.lower()
    return any(n == p or n.startswith(p + " ") for n in lib)
dirs = [d for d in os.listdir(E) if os.path.isdir(os.path.join(E, d)) and not d.startswith("_") and d != "miniatury"]
gotowe = {d for d in dirs if os.path.isdir(os.path.join(E, d, "_stare"))}
skladowe, dub, watpliwe = [], [], []
for d in sorted(dirs):
    if d in gotowe: continue
    base = re.sub(r"-\d$", "", d)
    if base != d and base in dirs: skladowe.append(d); continue
    if d.startswith("CFM-TR-G-B.60-SH-6 ."): skladowe.append(d); continue
    if in_lib(d) or in_lib(re.sub(r"-\(.*\)$", "", d)): dub.append(d); continue
    if re.match(r"GN 724\.", d) or "Trzpień" in d or "elcomp" in d or d.endswith("-1") or d.endswith("-Gubek"): watpliwe.append(d)
print("składowe:", skladowe); print("duble biblioteki:", dub); print("wątpliwe:", watpliwe)
if APPLY:
    for name, lst in (("_skladowe", skladowe), ("_juz_w_bibliotece", dub), ("_do_decyzji", watpliwe)):
        os.makedirs(os.path.join(E, name), exist_ok=True)
        for d in lst: shutil.move(os.path.join(E, d), os.path.join(E, name, d))
    print("przeniesiono")
