import os, re, csv, json, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
S = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(S, "grupuj.py"), encoding="utf-8").read()
ns = {}
exec(src[src.index("CODE ="):src.index("allrows = []")], {"re": re}, ns)   # tylko norm()
norm = ns["norm"]
rows = list(csv.DictReader(open(os.path.join(S, "szukaj2.csv"), encoding="utf-8-sig"), delimiter=";"))
def proj(folder):
    parts = folder.replace("/", "\\").split("\\")
    return (parts[0].upper() + "\\" + (parts[1] if len(parts) > 1 else "")).lower()
DEST = r"G:\Mój dysk\SUBIEKT\Elesa"
dirs = [d for d in os.listdir(DEST) if os.path.isdir(os.path.join(DEST, d)) and d not in ("miniatury", "_rzadkie")]
bysym = collections.defaultdict(set)
for r in rows:
    if r["trafienie"] == "opis": continue
    s = norm(r["plik"])
    if s: bysym[s.lower()].add(proj(r["folder"]))
def count(sym):
    k = sym.lower(); ps = set(bysym.get(k, ()))
    for kk, v in bysym.items():
        if kk.startswith(k) and re.fullmatch(r"([-_]\d+|_[a-z])", kk[len(k):] or "x"): ps |= v
    return len(ps)
res = {d: count(d) for d in dirs}
json.dump(res, open(os.path.join(S, "czestosc.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(sorted(collections.Counter(res.values()).items()))
