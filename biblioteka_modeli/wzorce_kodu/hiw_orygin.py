import re, os, sys, csv, shutil, collections
sys.stdout.reconfigure(encoding="utf-8")
rows=[]
for f in ("hiw_B.tsv","hiw_CProjekty.tsv","hiw_V.tsv"):
    for l in open(f,encoding="utf-8"):
        p,s=l.rstrip("\n").split("\t"); rows.append((p,int(s)))
V1=re.compile(r"^(hg[hwl]\d{2}(?:ca|ha|cc|hc)|mg[nw]0?\d{1,2}[ch])[ _]?1[ _]?r[ _]?\d+[ _]?z[0f][ _]?h[ _]?(?:m)?[ _]?(?:ss)?_?(?:file)?_?\d?$", re.I)
V2=re.compile(r"^(hg[hwl]\d{2}(?:ca|ha|cc|hc)|mg[nw]0?\d{1,2}[ch])(?:z0h|1r\d+z[0f]hm)_?(?:no_set_e1_[\d_]+_0|file)_?\d{0,2}$", re.I)
V3=re.compile(r"^(hg[hwl]\d{2}(?:ca|ha|cc|hc)|mg[nw]0?\d{1,2}[ch])[ _]?z[0f1][ _]?h[ _]?m?[ _]*wózek$", re.I)
V4=re.compile(r"^hiwin corporation-(hg[hwl])-(\d{2})-(ca|ha|cc|hc)(-default)?$", re.I)
res=collections.OrderedDict()
def typ(n):
    m=re.match(r"(hg[hwl]\d{2}(?:ca|ha|cc|hc)|mg[nw]0?\d{1,2}[ch])",n,re.I)
    if m: return re.sub(r"^(MG[NW])0(\d)",r"\1\2",m.group(1).upper())
    m=V4.match(n)
    return (m.group(1)+m.group(2)+m.group(3)).upper() if m else "INNE"
for p,s in sorted(rows,key=lambda x:(not x[0].startswith("B:"),x[0])):
    b,e=os.path.splitext(os.path.basename(p))
    if e.lower() not in (".ipt",".stp",".step"): continue
    if re.search(r"_mir$|rail|szyn",b,re.I): continue
    n=b.replace("_"," ") if False else b
    if not (V1.match(b) or V2.match(b) or V3.match(b) or V4.match(b) or ("Znormalizowane" in p and e.lower()==".stp")): continue
    k=(b.lower().replace("_"," "),e.lower(),s)
    if k in res: continue
    res[k]=(typ(b),p,s)
print("oryginałów:",len(res), collections.Counter(v[0] for v in res.values()))
if "--kopiuj" in sys.argv:
    D="G:/Mój dysk/SUBIEKT/Wózki"; out=[]; used=collections.defaultdict(set)
    for k,(t,p,s) in res.items():
        os.makedirs(D+"/"+t,exist_ok=True)
        n=os.path.basename(p)
        if n.lower() in used[t]:
            b,e=os.path.splitext(n); n="%s (%d)%s"%(b,len(used[t]),e)
        used[t].add(n.lower()); shutil.copy2(p,D+"/"+t+"/"+n); out.append((t,n,s,p))
    with open(D+"/_zrodla.csv","w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f,delimiter=";"); w.writerow(["typ","plik","rozmiar","zrodlo"]); w.writerows(out)
    print("skopiowane:",len(out))
