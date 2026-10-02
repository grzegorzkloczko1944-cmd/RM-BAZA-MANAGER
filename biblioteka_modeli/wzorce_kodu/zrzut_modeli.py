import os, csv, time
S = os.path.dirname(os.path.abspath(__file__))
ROOTS = ["B:\\", "C:\\Projekty", "V:\\"]
EXT = (".ipt", ".iam", ".stp", ".step")
SKIP = ("oldversions", "@recycle", "$recycle.bin", "stp_work", "poz_work", "ref_work", "ref_work2", "ref_work3", "mini_work")
KNOWN = os.path.normcase(r"V:\! HASIOK")
t0 = time.time(); n = 0
with open(os.path.join(S, "zrzut_modeli.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh, delimiter=";"); w.writerow(["folder", "plik", "ext", "rozmiar"])
    for ROOT in ROOTS:
        for root, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d.lower() not in SKIP]
            if os.path.normcase(root).startswith(KNOWN): dirs[:] = []; continue
            for f in files:
                if f.lower().endswith(EXT):
                    try: sz = os.path.getsize(os.path.join(root, f))
                    except OSError: sz = -1
                    w.writerow([root, f, os.path.splitext(f)[1].lower(), sz]); n += 1
        print(ROOT, "gotowe, razem plików:", n, "czas", int(time.time() - t0), "s", flush=True)
