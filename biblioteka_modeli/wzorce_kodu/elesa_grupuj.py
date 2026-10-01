import os, re, csv, json, collections
import win32com.client
S = os.path.dirname(os.path.abspath(__file__))
rows = list(csv.DictReader(open(os.path.join(S, "szukaj2.csv"), encoding="utf-8-sig"), delimiter=";"))
LIB = r"B:\Elementy handlowe\Elesa-Ganter"
G = r"G:\Mój dysk\SUBIEKT\Elesa"
EXCL = re.compile(r"ERM-|MS\d-LFR|wire gn|blacha ramy|licznika|Ucho licznika|DD51_FR|ARNO|Digital_position|Noniusz", re.I)
EXC_DIR = re.compile(r"\\(Library|Libraries)\\|\\Workspaces?\\", re.I)
CODE = re.compile(r"(?:^|[\s_\-(])((?:GN|ERX|EBP-L|EBP|CFM-TR|CFM|DVM|ANPS|VCT|VBT|LRX|MRX|CQ|CT|BMS\.L|BMS|VCL|VLP|CFSW|EBS|HBT|LVP|IUR|MFB|PMC|VC|CS|CSP|CSM|MR)[\s._\-]?\d?[^\s]*)", re.I)

def norm(fn):
    n = re.sub(r"\.(ipt|iam|stp|step)$", "", fn, flags=re.I)
    n = re.sub(r"\(deactivated\)|__closed__\d+_\d+|__deactivated|_MIR\d*|\s*\(\d\)", "", n, flags=re.I)
    m = re.search(r"(?:^|[\s_\-(])(GN)[\s_]?(\d{3})(?:[._](\d))?[\s_\-]+(.+)$", n, re.I)
    if m:
        fam = m.group(2) + ("." + m.group(3) if m.group(3) else "")
        rest = re.sub(r"[_ ]+", "-", m.group(4)).strip("-")
        return "GN " + fam + "-" + rest
    m = re.search(r"(?:^|[\s_\-(])((?:ERX|EBP-L|EBP|CFM-TR|CFM|DVM|ANPS)[\s._\-]?[\w.\-]+(?:\s[\w.\-]+)?)$", n)
    if m:
        return m.group(1).replace("_", ".").strip()
    return None

allrows = []
for r in rows:
    p = os.path.join(r["folder"], r["plik"])
    if r["trafienie"] == "opis" or EXCL.search(r["plik"]) or EXC_DIR.search(p) or re.search(r"_MIR|\bmir\b", r["plik"], re.I):
        continue
    s = norm(r["plik"])
    if not s: continue
    allrows.append((s, p, r["ext"], int(r["rozmiar"])))
print("plików z symbolem:", len(allrows))

# biblioteka + już dołożone
have = set()
for base in (LIB, G):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d.lower() not in ("oldversions", "_stare", "miniatury")]
        for f in files:
            if f.lower().endswith((".ipt", ".iam", ".stp", ".step")):
                s = norm(f) or re.sub(r"\.(ipt|iam|stp)$", "", f)
                have.add(s.lower())
                have.add(re.sub(r"\s[A-ZŁŚŻ][a-ząćęłńóśźż ]+$", "", s).lower())
a = win32com.client.Dispatch("Inventor.ApprenticeServer")
groups = collections.defaultdict(list)
for s, p, e, sz in allrows: groups[s].append((p, e, sz))
refmap = {}
def refs(p):
    if p in refmap: return refmap[p]
    try:
        d = a.Open(p)
        try: v = [fd.FullFileName for fd in d.ReferencedFileDescriptors]
        finally: d.Close()
    except Exception:
        v = None
    refmap[p] = v; return v
comp = set()
for s, lst in groups.items():
    for p, e, sz in lst:
        if e == ".iam":
            for x in refs(p) or []: comp.add(os.path.normcase(x))
out = []
PRI = lambda p: 0 if p.upper().startswith("B:") else (1 if p.upper().startswith("C:") else 2)
for s, lst in sorted(groups.items()):
    if s.lower() in have: continue
    lst = [x for x in lst if os.path.normcase(x[0]) not in comp]
    if not lst: continue
    pick = None
    for e in (".ipt", ".iam", ".stp", ".step"):
        c = [x for x in lst if x[1] == e]
        if e == ".iam":
            c = [x for x in c if refs(x[0]) and all(os.path.exists(y) for y in refs(x[0]))]
        if c:
            pick = sorted(c, key=lambda x: (PRI(x[0]), -x[2]))[0]; break
    if pick:
        out.append((s, pick[0], pick[1], pick[2], len(lst)))
json.dump(out, open(os.path.join(S, "kand2.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print("nowych kandydatów:", len(out), "| w bibliotece/już dołożone:", len(groups) - len(out))
fam = collections.Counter(re.match(r"(GN \d+(?:\.\d)?|[A-Z\-]+)", s).group(1) for s, *_ in out)
print(sorted(fam.items(), key=lambda x: x[0]))
print(collections.Counter(e for _, _, e, *_ in out))
