import os, re, csv, sys, time
S = os.path.dirname(os.path.abspath(__file__))
ROOTS = sys.argv[1:] or ["B:\\", "C:\\Projekty", "V:\\"]
EXT = (".ipt", ".iam", ".stp", ".step")
SKIPDIR = ("oldversions", "@recycle", "$recycle.bin", "stp_work", "ref_work", "ref_work2", "ref_work3")
KNOWN = [os.path.normcase(x) for x in (r"B:\Elementy handlowe\Elesa-Ganter", r"G:\Mój dysk\SUBIEKT\Elesa")]
KOD = re.compile(r"(elesa|ganter|(^|[\s_\-(])GN[\s._\-]?\d{3}|(^|[\s_\-])(ERX|ERM|CT\.\d|CQ[_/ ]|BMS\.|VCL|VLP|CFSW|EBP|EBS|LRX|MRX|VBTP|VC\.|CS\.|CSP|CSM|HBT|LVP|IUR|MFB|PMC|MR\.|VBT|VTT|CFM|CFMS|GN)\b)", re.I)
OPIS = re.compile(r"(indexing plunger|spring plunger|ball (joint|lever|knob)|adjustable handle|clamping (lever|bolt|knob|handle)|cabinet (u )?handle|hand ?wheel|revolving handle|fixed handle|tubular handle|lobe knob|wing (nut|screw)|star knob|three[- ]lobe|two[- ]way (clamp|connector)|connector clamp|tube clamp|toggle (latch|clamp)|latch|hinge|shaft collar|retaining ring|levelling (foot|feet)|leveling (foot|feet)|vibration (mount|damper)|anti[- ]vibration|universal joint|digital position|position indicator|"
                  r"Andr[uü]ckschraube|Klemmhebel|Rastbolzen|Kugelgelenk|Handrad|Sterngriff|Scharnier|Spannhebel|Stellgriff|Verschluss|Schwenkgriff)", re.I)
rows = []
t0 = time.time()
for ROOT in ROOTS:
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d.lower() not in SKIPDIR]
        nr = os.path.normcase(root)
        if any(nr.startswith(k) for k in KNOWN):
            dirs[:] = []; continue
        inpath = bool(re.search(r"elesa|ganter", root, re.I))
        for f in files:
            if not f.lower().endswith(EXT): continue
            tr = "folder" if inpath else ("kod" if KOD.search(f) else ("opis" if OPIS.search(f) else ""))
            if not tr: continue
            p = os.path.join(root, f)
            try: sz = os.path.getsize(p)
            except OSError: sz = -1
            rows.append((root, f, os.path.splitext(f)[1].lower(), sz, tr))
    print(ROOT, "gotowe, trafień łącznie:", len(rows), "czas", int(time.time() - t0), "s", flush=True)
out = os.path.join(S, "szukaj2.csv")
with open(out, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh, delimiter=";"); w.writerow(["folder", "plik", "ext", "rozmiar", "trafienie"]); w.writerows(rows)
