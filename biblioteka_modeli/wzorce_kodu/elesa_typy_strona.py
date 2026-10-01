import urllib.request, re, ssl, json, os, html, time
S = os.path.dirname(os.path.abspath(__file__))
ctx = ssl.create_default_context()
def get(u):
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(r, timeout=40, context=ctx).read().decode("utf-8", "ignore")
def serie(slug):
    h = get("https://www.elesa-ganter.pl/produkty/elementy-ustalajace/seria/" + slug)
    for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
        try: j = json.loads(b)
        except Exception: continue
        if j.get("@type") == "Product":
            offs = j.get("offers", {})
            offs = offs.get("offers", []) if isinstance(offs, dict) else offs
            return dict(slug=slug, mpn=j.get("mpn"), name=j.get("name"), desc=j.get("description"), brand=(j.get("brand") or {}).get("name"),
                        offers=[(o.get("name"), o.get("sku")) for o in offs])
    return None
FAM = """CFM CFM-TR ERX EBP DVM ANPS GN111.8 GN113.3 GN113.4 GN131 GN133 GN134 GN136 GN146 GN147 GN163 GN164 GN165 GN194 GN274 GN300 GN300.6 GN302.2 GN350.3 GN413 GN425.3 GN431 GN473 GN474 GN474.1 GN608 GN612.9 GN613 GN614 GN615 GN615.1 GN615.2 GN617 GN648.1 GN648.2 GN648.6 GN705 GN706.2 GN707.2 GN708.1 GN711 GN717 GN724.2 GN724.3 GN724.6 GN751 GN817 GN817.1 GN817.4 GN822 GN822.6 GN822.7 GN841 GN851.1 GN913.3 GN924""".split()
res = {}
for f in FAM:
    if f.startswith("GN"):
        base = f[2:]; slugs = ["gn-" + base.replace(".", "-")]
    else:
        slugs = [f.lower()]
    got = None
    for s in slugs:
        try: d = serie(s)
        except Exception as e: d = None
        if d: got = d; break
        time.sleep(0.3)
    ok = bool(got and got["mpn"] and re.sub(r"\s", "", got["mpn"]).upper() == re.sub(r"\s", "", f).upper()) if f.startswith("GN") else bool(got)
    res[f] = dict(ok=ok, **(got or {}))
    time.sleep(0.3)
json.dump(res, open(os.path.join(S, "typy2.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for f, d in res.items():
    print(("OK  " if d["ok"] else "??  ") + f, "|", d.get("brand"), "|", d.get("mpn"), "|", html.unescape(d.get("desc") or d.get("name") or ""))
