import os, re
S = os.path.dirname(os.path.abspath(__file__))
t = open(os.path.join(S, "wybor_szablon.html"), encoding="utf-8").read()
patch = open(os.path.join(S, "patch_lokalny.js"), encoding="utf-8").read()
t = t.replace("<title>Wybór Elesa-Ganter</title>", "<title>Wybór Elesa-Ganter (plik lokalny)</title>")
t = t.replace('<button class="btn" id="csv" type="button" hidden>Zapisz listę CSV</button>',
              '<input type="text" id="who" placeholder="Twoje imię" aria-label="Twoje imię" hidden style="font:inherit;background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:7px 10px;min-width:0;width:150px">\n      <button class="btn" id="csv" type="button" hidden>Zapisz mój wybór (CSV)</button>')
marker = "    renderAll();\n    try{ userCap = await claude.use('user'); }"
assert marker in t
t = t.replace(marker, "    renderAll();" + patch + "    try{ userCap = await claude.use('user'); }")
t = t.replace("var who = v.by ? (names[v.by] || 'ktoś') : 'ktoś';", "var who = v.by ? (names[v.by] || v.by) : 'ktoś';")
d = open(os.path.join(S, "items.json"), encoding="utf-8").read().replace("</", "<\\/")
# podział: <title>/<link>/<style> do <head>, reszta do <body>
head_end = t.index("</style>") + len("</style>")
head, body = t[:head_end], t[head_end:]
out = '<!doctype html>\n<html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n' + head + '\n</head><body>' + body.replace("/*DATA*/", d) + '</body></html>'
open(os.path.join(S, "wybor_elesa_ganter_lokalny.html"), "w", encoding="utf-8").write(out)
js = re.findall(r"<script(?![^>]*application/json)[^>]*>(.*?)</script>", out, re.S)[-1]
open(os.path.join(S, "lokalny_check.js"), "w", encoding="utf-8").write(js)
print("MB: %.2f" % (len(out.encode("utf-8")) / 1e6))
