import os, re, csv, json, base64, io
from PIL import Image
S = os.path.dirname(os.path.abspath(__file__)); T = os.path.join(S, "thumbs")
E = r"G:\Mój dysk\SUBIEKT\Elesa"
src = open(os.path.join(S, "batch.py"), encoding="utf-8").read()
ns = {"re": re}
exec(src[src.index("OPIS = ["):src.index("def czysty")], ns)
opis_dla = ns["opis_dla"]
man = list(csv.DictReader(open(os.path.join(T, "manifest.csv"), encoding="utf-8-sig"), delimiter=";"))
final = {r["katalog_oznaczenie"]: r for r in csv.DictReader(open(os.path.join(E, "lista_pozycji_final.csv"), encoding="utf-8-sig"), delimiter=";")}
zr = {}
for f in ("lista_pozycji.csv", "lista_pozycji_2.csv"):
    for r in csv.DictReader(open(os.path.join(E, f), encoding="utf-8-sig"), delimiter=";"): zr[r["symbol"]] = r
def projekt(path):
    if not path: return ""
    p = path.replace("/", "\\").split("\\")
    if path[:2].upper() in ("B:", "V:") : return p[0] + "\\" + (p[1] if len(p) > 1 else "")
    if path.upper().startswith("C:\\PROJEKTY"): return p[2] if len(p) > 2 else ""
    return p[0] + "\\" + (p[1] if len(p) > 1 else "")
POWOD_DECYZJI = {
 "GN 113.4-6-20-Trzpień": "Nazwa z dopiskiem „Trzpień” — niepewne, czy to osobny wariant GN 113.4-6-20.",
 "GN 924-125-K12-R-SW-elcomp": "Dopisek „elcomp” w nazwie — oznaczenie niezgodne z katalogiem.",
}
def jpeg(path, size=180):
    im = Image.open(path).convert("RGB")
    im.thumbnail((size, size))
    b = io.BytesIO(); im.save(b, "JPEG", quality=72, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
items = []
for m in man:
    g, nr, nazwa = m["grupa"], m["nr"], m["nazwa"]
    if g == "zrobione":
        f = final.get(nazwa, {})
        img = os.path.join(E, "miniatury", nazwa + ".png")
        it = dict(g=g, n=nazwa, kod=f.get("part_number", ""), opis=f.get("description", ""), fmt=f.get("rodzaj", ""), ver=f.get("wersja_inventora", ""), proj="", info="")
    else:
        img = os.path.join(T, "%s__%s.png" % (g, nr))
        z = zr.get(nazwa) or zr.get(re.sub(r"-\((deactivated|closed)[^)]*\)$", "", nazwa)) or {}
        opis = opis_dla(nazwa) or ""
        info = ""
        if g == "do_decyzji":
            info = POWOD_DECYZJI.get(nazwa, "Seria GN 724.x: oznaczenie w nazwie nie zgadza się jednoznacznie z serią na stronie producenta (strona ma GN 7241/7243/7247).")
        if g == "w_bibliotece": info = "Ten model jest już w bibliotece Elesa-Ganter na B:."
        it = dict(g=g, n=nazwa, kod="", opis=opis, fmt=(m["ext"] or "").lstrip(".").upper() or "?", ver="", proj=projekt(z.get("zrodlo", "")), info=info)
    it["img"] = jpeg(img) if os.path.exists(img) else ""
    items.append(it)
for i, it in enumerate(items, 1): it["id"] = "p%04d" % i
json.dump(items, open(os.path.join(S, "items.json"), "w", encoding="utf-8"), ensure_ascii=False)
import collections
print(collections.Counter(i["g"] for i in items), "bez obrazka:", sum(1 for i in items if not i["img"]), "rozmiar MB: %.2f" % (os.path.getsize(os.path.join(S, "items.json")) / 1e6))
