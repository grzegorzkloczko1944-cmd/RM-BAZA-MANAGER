import os, re, csv, shutil, collections, sys
import win32com.client
sys.stdout.reconfigure(encoding="utf-8")
S = os.path.dirname(os.path.abspath(__file__))
DEST = r"V:\! HASIOK\IGUS"
APPLY = "--zapisz" in sys.argv
EXC_DIR = re.compile(r"\\(Library|Libraries)\\|\\Workspaces?\\|\\OldVersions\\", re.I)

BEAR = re.compile(r"(?<![A-Za-z0-9])([A-Z]{1,2}(?:SM|FM|TM|PM|UM|UCM))[-_ ](\d{3,4})[-_ ](\d{2})(?![0-9])")
CHAIN = re.compile(r"(?:(\d+\.\d+)m )?(?<![A-Za-z0-9])([ER]\d[A-Z]?\.\d{2,3}\.\d{2,3}\.\d{2,3}\.\d)(?![0-9])")
RAILRX = (r"WSQ|WSX|WS|WJ[A-Z0-9]*|WJRM|WJUM|WJBMP|WWPV|WWPL|WWP|WWBCX|WWC|WWS|WW|WK|WEKA|TK|TS|TW|NW|RJ4JP|RJUM|FJUM|QJFM|SLW")
RAIL = re.compile(r"(?<![A-Za-z0-9])(%s)[-_ ]?(\d{2,4})(?:[-_ ](\d{1,4}))?(?:[-_ ](\d{1,4}))?" % RAILRX)
PRT = re.compile(r"(?<![A-Za-z0-9])(PRT)[-_ ](0\d)[-_ ](\d{2,3})(?:[-_ ](\d{1,3}))?")
JOINT = re.compile(r"(?<![A-Za-z0-9])((?:KBRM|KBM|KGLM|GLRM|GERM|EGLM|KSTM|KGHM|KARM)[-_ ]?\d{2,3}[A-Z0-9]*)")
SKIPNAME = re.compile(r"_MIR|\bmir\b|^(ZS|DS|ZS4R)[\s-]|\+ ", re.I)

def parse(fn):
    n = re.sub(r"\.(ipt|iam|stp|step)$", "", fn, flags=re.I)
    n0 = re.sub(r"^ibh_", "", n)
    if SKIPNAME.search(n0): return None
    m = BEAR.search(n0)
    if m: return ("Tuleja/łożysko ślizgowe iglidur", "%s-%s-%s" % m.groups(), "")
    m = CHAIN.search(n0)
    if m:
        if re.search(r"_\d+$", n0): return None                                       # składowe łańcucha
        L = ("L%d" % round(float(m.group(1)) * 1000)) if m.group(1) else ""
        return ("Łańcuch prowadzący (e-chain)", m.group(2), L)
    m = JOINT.search(n0)
    if m: return ("Przegub igubal", m.group(1).replace("_", "-").replace(" ", "-"), "")
    m = PRT.search(n0)
    if m:
        return ("Łożysko obrotowe drylin PRT", "PRT-%s-%s" % (m.group(2), m.group(3)), "")
    m = RAIL.search(n0)
    if m:
        pfx = m.group(1)
        parts = [m.group(2)] + [x for x in (m.group(3), m.group(4)) if x]
        base = pfx + "-" + "-".join(parts)
        rest = n0[m.end():]
        ml = re.match(r"^[,\s_]*[Ll]?(\d{2,4})(?!\d)", rest) if not re.search(r"UNGEBOHRT", rest, re.I) else None
        L = ("L" + ml.group(1)) if ml else ""
        grp = "Wózek drylin" if pfx.startswith("WJ") else ("Prowadnica/szyna drylin" if pfx != "PRT" else "Łożysko obrotowe drylin PRT")
        return (grp, base, L)
    return None

rows = list(csv.DictReader(open(os.path.join(S, "zrzut_modeli.csv"), encoding="utf-8-sig"), delimiter=";"))
cand = collections.defaultdict(list)            # (symbol) -> pliki   [A: kod]    ; (symbol L###) -> [B: kod + długość]
meta = {}
for r in rows:
    p = os.path.join(r["folder"], r["plik"])
    if EXC_DIR.search(p): continue
    pr = parse(r["plik"])
    if not pr: continue
    typ, base, L = pr
    proj = r["folder"].replace("/", "\\").split("\\")
    pn = (proj[2] if len(proj) > 2 else "C:\\Projekty") if r["folder"].upper().startswith("C:\\PROJEKTY") else (proj[0].upper() + "\\" + (proj[1] if len(proj) > 1 else ""))
    name_clean = re.sub(r"\.(ipt|iam|stp|step)$", "", r["plik"], flags=re.I)
    item = (p, r["ext"], int(r["rozmiar"]), pn, name_clean)
    cand[("A", base)].append(item); meta[("A", base)] = typ
    if L:
        cand[("B", base + " " + L)].append(item); meta[("B", base + " " + L)] = typ
print("grupy A (kod):", sum(1 for k in cand if k[0] == "A"), "| grupy B (kod+długość):", sum(1 for k in cand if k[0] == "B"))

app = win32com.client.Dispatch("Inventor.ApprenticeServer")
refmap = {}
def refs(p):
    if p in refmap: return refmap[p]
    try:
        d = app.Open(p)
        try: v = [fd.FullFileName for fd in d.ReferencedFileDescriptors]
        finally: d.Close()
    except Exception: v = None
    refmap[p] = v; return v
PRI = lambda p: 0 if p.upper().startswith("B:") else (1 if p.upper().startswith("C:") else 2)
def exactness(name, key):                       # im bliżej samego kodu, tym lepiej
    k = re.sub(r"[-_ ]", "", key.split(" ")[0]).lower(); n = re.sub(r"[-_ ]", "", name).lower()
    return 0 if n == k else (1 if n.startswith(k) else 2)
chosen = []
for key, lst in sorted(cand.items()):
    tier, sym = key
    projekty = {x[3] for x in lst}
    pick = None
    for ext in (".ipt", ".iam", ".stp", ".step"):
        c = [x for x in lst if x[1] == ext]
        c.sort(key=lambda x: (exactness(x[4], sym), PRI(x[0]), len(x[4]), -x[2]))
        for x in c[:6]:
            if ext == ".iam":
                rf = refs(x[0])
                if not rf or any(not os.path.exists(y) for y in rf): continue
            pick = x; break
        if pick: break
    if pick: chosen.append((tier, sym, meta[key], pick, len(projekty)))
# składowe złożeń nie są osobnymi pozycjami
comp = set()
for tier, sym, typ, x, npr in chosen:
    if x[1] == ".iam":
        for y in refs(x[0]) or []: comp.add(os.path.normcase(y))
print("WS- przed usunięciem składowych:", sum(1 for c in chosen if c[1].startswith("WS-")), "| grup WS- w cand:", sum(1 for k in cand if k[1].startswith("WS-")))
chosen = [c for c in chosen if os.path.normcase(c[3][0]) not in comp]
print("WS- po usunięciu składowych:", sum(1 for c in chosen if c[1].startswith("WS-")))
# B tylko jeśli różni się od A
print("wybrano:", collections.Counter(c[0] for c in chosen), "| formaty:", collections.Counter(c[3][1] for c in chosen))
print("typy:", collections.Counter(c[2] for c in chosen if c[0] == "A"))
out = []; problemy = []
for tier, sym, typ, x, npr in chosen:
    safe = re.sub(r'[<>:"/\\|?*]', "-", sym).strip(" .")
    d = os.path.join(DEST, safe) if tier == "A" else os.path.join(DEST, "_warianty_dlugosci", safe)
    p, ext = x[0], x[1]
    files = [p] + ((refs(p) or []) if ext == ".iam" else [])
    names = [os.path.basename(f).lower() for f in files]
    if len(set(names)) != len(names) or any(not os.path.exists(f) for f in files): problemy.append((sym, "kolizja/brak składowych")); continue
    if APPLY and not os.path.isdir(d):
        os.makedirs(d)
        for f in files: shutil.copy2(f, os.path.join(d, os.path.basename(f)))
    out.append(dict(poziom="katalogowe (kod)" if tier == "A" else "wariant długości", symbol=sym, typ=typ, format=ext.lstrip(".").upper(), liczba_plikow=len(files), projektow=npr, pliki=" | ".join(os.path.basename(f) for f in files), zrodlo=p))
_p = collections.defaultdict(list)
for o in out:
    _p[re.match(r"[A-Z]+[0-9]*[A-Z]*", o["symbol"]).group(0)].append(o["symbol"])
for k, v in sorted(_p.items(), key=lambda x: -len(x[1])):
    print("  %-8s %3d  %s" % (k, len(v), v[:3]))
print("do skopiowania:", len(out), "problemy:", problemy[:5], "| w jednym projekcie:", sum(1 for o in out if o["projektow"] == 1))
if APPLY:
    with open(os.path.join(DEST, "lista_pozycji.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()), delimiter=";"); w.writeheader(); w.writerows(out)
    print("skopiowano do", DEST)
