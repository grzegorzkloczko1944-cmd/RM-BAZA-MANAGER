# -*- coding: utf-8 -*-
"""Strona HTML (plik lokalny) do wyboru pozycji IGUS: V:\\! HASIOK\\IGUS\\WYBOR_IGUS.html"""
import os, re, csv, json, io, base64, sys
from PIL import Image
sys.stdout.reconfigure(encoding="utf-8")
S = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, S)
from igus_opis import opis as opis_dla, wymiar as wymiar_dla
E = r"V:\! HASIOK\IGUS"
BS = chr(92)

def grupa(sym, poziom):
    s = sym.upper()
    if poziom == "wariant długości": return "warianty"
    if re.match(r"[A-Z]{1,2}(SM|FM|TM|PM|UM|UCM)-", s): return "tuleje"
    if s.startswith("PRT"): return "prt"
    if re.match(r"[ER]\d", s): return "lancuchy"
    if re.match(r"(WS|WSQ|WSX|TS|TK)-", s): return "szyny"
    if re.match(r"(WJ|WW|WK|NW|TW|WEKA)", s): return "wozki"
    return "inne"

def jpeg(path, size=180):
    im = Image.open(path).convert("RGB"); im.thumbnail((size, size))
    b = io.BytesIO(); im.save(b, "JPEG", quality=72, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()

rows = list(csv.DictReader(open(os.path.join(E, "lista_pozycji_final.csv"), encoding="utf-8-sig"), delimiter=";"))
proj = {}
for f in ("lista_pozycji.csv",):
    try:
        for r in csv.DictReader(open(os.path.join(E, f), encoding="utf-8-sig"), delimiter=";"): proj[r["symbol"]] = r.get("projektow", "")
    except Exception: pass
items = []
for r in rows:
    sym = r["symbol"]; g = grupa(sym, r["poziom"])
    png = os.path.join(E, "miniatury", sym + ".png")
    info = ""
    if "L1000" in sym: info = "Model 1000 mm pobrany z igus-cad.com (STEP)."
    items.append(dict(g=g, n=sym, kod=sym, opis=r["description"], wym=r.get("wymiar", ""), fmt=r["rodzaj"], ver=r["wersja_inventora"],
                      proj=("w %s proj." % proj[sym]) if proj.get(sym) else "", info=info, img=jpeg(png) if os.path.exists(png) else ""))
# do decyzji: zagnieżdżone złożenia PRT i duble / literówki (nie są pozycjami biblioteki)
for sub, pow_ in (("_zagniezdzone", "Złożenie zagnieżdżone: wymaga ręcznego dopracowania (IAM w IAM)."), ("_duble_indeks", "Dopisek z Inventora do poprawnego symbolu (nie osobna pozycja) lub literówka.")):
    d = os.path.join(E, sub)
    if not os.path.isdir(d): continue
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if not os.path.isdir(p): continue
        base = re.sub(r"\s*\(literówka\)$", "", name)
        png = os.path.join(E, "miniatury", base + ".png")
        items.append(dict(g="decyzje", n=name, kod="", opis=opis_dla(base) or "", wym="", fmt="", ver="", proj="", info=pow_, img=jpeg(png) if os.path.exists(png) else ""))
for i, it in enumerate(items, 1): it["id"] = "p%04d" % i
print({k: sum(1 for x in items if x["g"] == k) for k in sorted({x["g"] for x in items})}, "razem", len(items))

GR = """[
    {k:'tuleje', t:'Tuleje', d:'Tuleje i łożyska ślizgowe iglidur z wymiarami (Ø wewnętrzna × Ø zewnętrzna × długość) do mapowania w Subiekcie.', def:true},
    {k:'wozki', t:'Wózki i oprawy', d:'Wózki prowadnic drylin W/T/N: oprawy stojakowe (WJ200UM, QM), z kasowaniem luzu (UME), wózki WW, NW, TW.', def:true},
    {k:'szyny', t:'Szyny i prowadnice', d:'Szyny pojedyncze i systemy prowadnic liniowych (WS, WSQ, WSX, TS), także w wersji 1000 mm (L1000) pobranej od IGUS.', def:true},
    {k:'prt', t:'Łożyska PRT', d:'Łożyska obrotowe iglidur PRT: złożenia z 15 składowymi, wykonania z uzębieniem (AT10, HTD8M).', def:true},
    {k:'lancuchy', t:'Łańcuchy', d:'Prowadniki kablowe e-chain.', def:true},
    {k:'inne', t:'Pozostałe', d:'Pozostałe pozycje IGUS (łożyska liniowe drylin R, oprawy kołnierzowe i inne).', def:true},
    {k:'warianty', t:'Warianty długości', d:'Ten sam kod w innej długości lub z dopiskiem. Domyślnie nie trafiają do biblioteki.', def:false},
    {k:'decyzje', t:'Do decyzji', d:'Złożenia zagnieżdżone i dopiski z Inventora. To nie są osobne pozycje, ale możesz je zaznaczyć.', def:false}
  ]"""
t = open(os.path.join(S, "wybor_szablon.html"), encoding="utf-8").read()
patch = open(os.path.join(S, "patch_lokalny.js"), encoding="utf-8").read()
# tytuł, nagłówek, grupy, chip wymiaru
t = t.replace("<title>Wybór Elesa-Ganter</title>", "<title>Wybór IGUS (plik lokalny)</title>")
t = t.replace("Wybór Elesa-Ganter <small>modele 3D do biblioteki</small>", "Wybór IGUS <small>modele 3D do biblioteki</small>")
t = re.sub(r"var GROUPS = \[.*?\n  \];", "var GROUPS = " + GR.replace("\\", "\\\\") + ";", t, flags=re.S)
t = t.replace("var state = {tab:'zrobione'", "var state = {tab:'tuleje'")
t = t.replace("if(it.fmt) meta +=", "if(it.wym) meta += '<span class=\"chip\" title=\"Wymiar do mapowania\">'+esc(it.wym)+'</span>';\n    if(it.fmt) meta +=")
t = t.replace("(it.n+' '+it.kod+' '+it.opis+' '+it.proj)", "(it.n+' '+it.kod+' '+it.opis+' '+it.proj+' '+(it.wym||''))")
t = t.replace("wybor-elesa", "wybor-igus").replace("wybor_elesa_", "wybor_igus_")
patch = patch.replace("wybor-elesa", "wybor-igus").replace("wybor_elesa_", "wybor_igus_")
marker = "    renderAll();\n    try{ userCap = await claude.use('user'); }"
assert marker in t
t = t.replace(marker, "    renderAll();" + patch + "    try{ userCap = await claude.use('user'); }")
t = t.replace('<button class="btn" id="csv" type="button" hidden>Zapisz listę CSV</button>',
              '<input type="text" id="who" placeholder="Twoje imię" aria-label="Twoje imię" hidden style="font:inherit;background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:7px 10px;min-width:0;width:150px">\n      <button class="btn" id="csv" type="button" hidden>Zapisz mój wybór (CSV)</button>')
t = t.replace("var who = v.by ? (names[v.by] || 'ktoś') : 'ktoś';", "var who = v.by ? (names[v.by] || v.by) : 'ktoś';")
d = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
he = t.index("</style>") + len("</style>")
head, body = t[:he], t[he:]
out = '<!doctype html>\n<html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n' + head + '\n</head><body>' + body.replace("/*DATA*/", d) + '</body></html>'
open(os.path.join(E, "WYBOR_IGUS.html"), "w", encoding="utf-8").write(out)
js = re.findall(r"<script(?![^>]*application/json)[^>]*>(.*?)</script>", out, re.S)[-1]
open(os.path.join(S, "igus_check.js"), "w", encoding="utf-8").write(js)
os.makedirs(os.path.join(E, "wybory"), exist_ok=True)
print("MB: %.2f" % (len(out.encode('utf-8')) / 1e6))
