# -*- coding: utf-8 -*-
"""Pipeline biblioteki modeli 3D: jedna komenda na krok, definicja rodziny w rodziny/<nazwa>.json.

    python biblioteka.py oringi stan                 # RAPORT (tylko odczyt): modele <-> kartoteki Subiekta
    python biblioteka.py oringi buduj [--zapisz]     # brakujace/niezgodne modele z SYMBOLU (wymiary z nazwy)
    python biblioteka.py oringi sieroty [--zapisz]   # modele bez kartoteki: lista / kasowanie
    python biblioteka.py oringi opisy [--zapisz]     # Opis kartoteki = 'Oring'
    python biblioteka.py oringi indeks [--zapisz]    # zasiew MAG (indeks_oringi_zasiew.py)
    python biblioteka.py oringi zdjecia [--zapisz]   # miniatury -> zdjecia kartotek (tylko bez zdjecia)
    python biblioteka.py wozki_hiwin plan            # co by skopiowano (szuka w B:, C:/Projekty, V:)
    python biblioteka.py wozki_hiwin kopiuj [--zapisz]

Kazdy krok bez --zapisz to SUCHY PRZEBIEG. Opis, pulapki i zasady: README.md.
"""
import argparse
import base64
import collections
import csv
import importlib.util
import json
import os
import re
import shutil
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def rodzina(nazwa):
    with open(os.path.join(HERE, "rodziny", nazwa + ".json"), encoding="utf-8") as f:
        return json.load(f)


# ───────────────────────── wspólne: Subiekt ─────────────────────────

def _bridge():
    import subiekt_bridge
    return subiekt_bridge


def kartoteki(prefiks):
    """{symbol: pozycja} z zywego Subiekta (tryb 'magazyn', nie kopia MAG — ta bywa nieaktualna)."""
    r = _bridge().call("magazyn", {"tylko_niezerowe": False}, timeout=280, write=False)
    return {x["Symbol"]: x for x in r["pozycje"] if x["Symbol"].upper().startswith(prefiks.upper())}


def ma_zdjecie(symbol):
    """True/False albo None gdy nie ma kartoteki (most nie ma pola 'istnieje' — czytamy kroki)."""
    st = _bridge().call("zdjecie", {"plan": {"akcja": "lista", "symbol": symbol}, "zapisz": False},
                        timeout=120, write=False)
    if any(k.get("Status") == "blad" for k in st.get("kroki", [])):
        return None
    return bool(st.get("zdjecia"))


def apprentice_pn(pliki):
    """{plik: Part Number} — Apprentice, tylko odczyt (nie rusza sesji uzytkownika)."""
    import win32com.client
    a = win32com.client.Dispatch("Inventor.ApprenticeServer")
    wynik = {}
    for p in pliki:
        d = a.Open(os.path.normpath(p))
        try:
            wynik[p] = d.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value
        finally:
            d.Close()
    return wynik


def _osobny_inventor():
    """Nowa instancja Inventora (sesja uzytkownika nietknieta) + funkcja sprzatajaca."""
    import ctypes
    import ctypes.wintypes as wt
    import win32com.client
    app = win32com.client.DispatchEx("Inventor.Application")
    t = time.time()
    while not app.Ready and time.time() - t < 240:
        time.sleep(1)
    app.SilentOperation = True
    pid = wt.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(wt.HWND(app.MainFrameHWND), ctypes.byref(pid))

    def zamknij():
        try:
            app.Quit()
        except Exception:
            pass
        time.sleep(3)
        os.system("taskkill /F /PID %d >nul 2>&1" % pid.value)
    return app, zamknij


# ───────────────────────── O-ringi ─────────────────────────

WZ_ORING = re.compile(r"^OR-(\d+(?:[.,]\d+)?)X(\d+(?:[.,]\d+)?)\s+(\S+)", re.I)


def _modele_oringow(c):
    return sorted(f[:-4] for f in os.listdir(c["katalog_modeli"]) if f.lower().endswith(".ipt"))


def oringi_stan(c, a):
    kart = kartoteki(c["prefiks_symbolu"])
    kart = {s: x for s, x in kart.items() if s not in c.get("pomijaj_symbole", [])}
    pliki = _modele_oringow(c)
    lk, lp = {s.lower(): s for s in kart}, {p.lower(): p for p in pliki}
    brak = sorted(s for s in kart if s.lower() not in lp)
    sieroty = sorted(p for p in pliki if p.lower() not in lk)
    sciezki = {p: os.path.join(c["katalog_modeli"], p + ".ipt") for p in pliki}
    pn = apprentice_pn(list(sciezki.values()))
    zle_pn = sorted(p for p in pliki if pn[sciezki[p]].lower() != p.lower())
    zly_opis = sorted(s for s, x in kart.items() if (x.get("Opis") or "") != c["opis_subiekta"])
    bez_polozenia = sorted(s for s, x in kart.items() if not x.get("Polozenie"))
    print("kartotek %s: %d | modeli: %d" % (c["prefiks_symbolu"], len(kart), len(pliki)))
    print("kartoteki BEZ modelu (%d): %s" % (len(brak), brak))
    print("modele BEZ kartoteki — sieroty (%d): %s" % (len(sieroty), sieroty))
    print("Part Number != nazwa pliku (%d): %s" % (len(zle_pn), zle_pn))
    print("Opis != '%s' (%d): %s" % (c["opis_subiekta"], len(zly_opis), zly_opis))
    print("bez polozenia w PoleWlasne1 (%d): %s" % (len(bez_polozenia), bez_polozenia))
    print("→ kroki: buduj (brak + --niezgodne), sieroty, opisy, indeks, zdjecia")


def _material_oringu(c, token):
    return c["material"].get(token.upper().rstrip("-"), c["material_domyslny"])


def oringi_buduj(c, a):
    kart = {s: x for s, x in kartoteki(c["prefiks_symbolu"]).items() if s not in c.get("pomijaj_symbole", [])}
    pliki = set(p.lower() for p in _modele_oringow(c))
    cele = set(a.symbole or [])
    if not cele:
        cele = {s for s in kart if s.lower() not in pliki}
        if a.niezgodne:
            sc = {p: os.path.join(c["katalog_modeli"], p + ".ipt") for p in _modele_oringow(c)}
            pn = apprentice_pn(list(sc.values()))
            cele |= {p for p in sc if pn[sc[p]].lower() != p.lower() and p in kart}
    plan = []
    for s in sorted(cele):
        m = WZ_ORING.match(s)
        if not m:
            print("  ⛔ symbol nie pasuje do wzorca OR-<D>X<przekroj> <MATERIAL>: %s (pomijam)" % s)
            continue
        plan.append((s, float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", ".")),
                     _material_oringu(c, m.group(3))))
    print("do zbudowania: %d" % len(plan))
    for p in plan:
        print("  %-24s Ø%g × %g  materiał %s" % p)
    if not a.zapisz or not plan:
        return
    spec = importlib.util.spec_from_file_location("gen", os.path.join(ROOT, "katalog_oringow", "generuj_modele.py"))
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    app, zamknij = _osobny_inventor()
    praca = os.path.join(HERE, "_praca_oringi")
    shutil.rmtree(praca, ignore_errors=True)
    os.makedirs(os.path.join(praca, "miniatury"))
    ok = []
    try:
        wersja = app.SoftwareVersion.DisplayVersion
        if c["inventor_wymagany"] not in wersja and not a.dopusc_inny_inventor:
            print("⛔ Inventor %s, biblioteka jest w formacie %s — zapis zmieniłby format plików. "
                  "Uruchom na maszynie z %s albo dodaj --dopusc-inny-inventor." % (wersja, c["inventor_wymagany"], c["inventor_wymagany"]))
            return
        szablon = app.FileManager.GetTemplateFile(gen.K_PART)
        for s, idm, gr, mat in plan:
            try:
                gen.zbuduj(app, szablon, os.path.normpath(os.path.join(praca, gen.nazwa_pliku(s))), idm, gr, mat, s,
                           os.path.normpath(os.path.join(praca, "miniatury", gen.nazwa_pliku(s)[:-4] + ".png")))
                ok.append((s, mat))
            except Exception as e:
                print("  ⛔ %s: %s" % (s, str(e)[:100]))
    finally:
        zamknij()
    os.makedirs(c["miniatury"], exist_ok=True)
    for s, mat in ok:
        shutil.copy2(os.path.join(praca, s + ".ipt"), os.path.join(c["katalog_modeli"], s + ".ipt"))
        shutil.copy2(os.path.join(praca, "miniatury", s + ".png"), os.path.join(c["miniatury"], s + ".png"))
    _csv_upsert(c, ok)
    shutil.rmtree(praca, ignore_errors=True)
    print("zbudowane i skopiowane: %d. Dalej: indeks, zdjecia, opisy." % len(ok))


def _csv_odczyt(c):
    if not os.path.exists(c["lista_csv"]):
        return {}
    with open(c["lista_csv"], encoding="utf-8-sig", newline="") as f:
        return {r["symbol"]: r for r in csv.DictReader(f, delimiter=";")}


def _csv_zapis(c, wiersze):
    with open(c["lista_csv"], "w", encoding="utf-8-sig", newline="") as f:
        z = csv.DictWriter(f, ["symbol", "plik", "png", "material"], delimiter=";")
        z.writeheader()
        for k in sorted(wiersze):
            z.writerow(wiersze[k])


def _csv_upsert(c, wpisy):
    w = lambda x: x.replace("/", chr(92))
    wiersze = _csv_odczyt(c)
    for s, mat in wpisy:
        wiersze[s] = {"symbol": s, "plik": w(os.path.join(c["katalog_modeli"], s + ".ipt")),
                      "png": w(os.path.join(c["miniatury"], s + ".png")), "material": mat}
    _csv_zapis(c, wiersze)


def oringi_sieroty(c, a):
    kart = {s.lower() for s in kartoteki(c["prefiks_symbolu"])}
    sieroty = [p for p in _modele_oringow(c) if p.lower() not in kart]
    print("modele bez kartoteki: %d %s" % (len(sieroty), sieroty))
    if not a.zapisz:
        return
    for p in sieroty:
        for f in (os.path.join(c["katalog_modeli"], p + ".ipt"), os.path.join(c["miniatury"], p + ".png")):
            if os.path.exists(f):
                os.remove(f)
    _csv_zapis(c, {k: v for k, v in _csv_odczyt(c).items() if k not in sieroty})
    print("skasowane:", len(sieroty))


def oringi_opisy(c, a):
    kart = kartoteki(c["prefiks_symbolu"])
    do = sorted(s for s, x in kart.items() if (x.get("Opis") or "") != c["opis_subiekta"])
    print("Opis do poprawy: %d %s" % (len(do), do))
    if a.zapisz and do:
        r = _bridge().call("kartoteka-edytuj", {"plan": {"pozycje": [{"symbol": s, "opis": c["opis_subiekta"]} for s in do]},
                                                "zapisz": True}, timeout=300, write=True)
        print("zmienionych:", r.get("zmienionych"))


def oringi_indeks(c, a):
    import subprocess
    cmd = [sys.executable, os.path.join(ROOT, "indeks_oringi_zasiew.py")] + (["--zapisz"] if a.zapisz else [])
    subprocess.run(cmd, cwd=ROOT, check=False)


def oringi_zdjecia(c, a):
    wysl, maja, brak = 0, 0, []
    for f in sorted(os.listdir(c["miniatury"])):
        if not f.lower().endswith(".png"):
            continue
        s = f[:-4]
        z = ma_zdjecie(s)
        if z is None:
            brak.append(s)
        elif z:
            maja += 1
        else:
            if a.zapisz:
                dane = open(os.path.join(c["miniatury"], f), "rb").read()
                _bridge().call("zdjecie", {"plan": {"akcja": "dodaj", "symbol": s, "nazwa": s + ".png", "typ": "png",
                                                    "dane_b64": base64.b64encode(dane).decode("ascii")},
                                           "zapisz": True}, timeout=300, write=True)
            wysl += 1
    print("%s: %d | miały zdjęcie (pominięte): %d | bez kartoteki: %s" % ("WYSŁANE" if a.zapisz else "DO WYSŁANIA", wysl, maja, brak))


# ───────────────────────── Wózki Hiwin ─────────────────────────

V_ORYG = [
    r"^{t}[ _]?1[ _]?r[ _]?\d+[ _]?z[0f][ _]?h[ _]?(?:m)?[ _]?(?:ss)?_?(?:file)?_?\d?$",
    r"^{t}(?:z0h|1r\d+z[0f]hm)_?(?:no_set_e1_[\d_]+_0|file)_?\d{{0,2}}$",
    r"^{t}[ _]?z[0f1][ _]?h[ _]?m?[ _]*wózek$",
]


V_HIWIN_CORP = re.compile(r"^hiwin corporation-(hg[hwl])-(\d{2})-(ca|ha|cc|hc)(-default)?$", re.I)


def _szukaj_wozkow(c):
    t = re.compile(c["typy_regex"], re.I)
    odrz = re.compile(c["odrzuc_regex"], re.I)
    orig = [re.compile(p.format(t=c["typy_regex"]), re.I) for p in V_ORYG] + [V_HIWIN_CORP]
    ext = tuple(c["rozszerzenia_modeli"])
    znalezione = collections.OrderedDict()
    for korzen in c["przeszukaj"]:
        for d, ds, fs in os.walk(korzen):
            ds[:] = [x for x in ds if x.lower() not in ("oldversions", "$recycle.bin", "system volume information")]
            for f in fs:
                b, e = os.path.splitext(f)
                if e.lower() not in ext or odrz.search(b):
                    continue
                p = os.path.join(d, f)
                ok = any(o.match(b) for o in orig) or ("Znormalizowane" in p and e.lower() == ".stp" and t.search(b))
                if not ok:
                    continue
                m = t.search(b.replace("_", " "))
                typ = re.sub(r"^(MG[NW])0(\d)", r"\1\2", m.group(1).upper()) if m else "INNE"
                k = (b.lower().replace("_", " "), e.lower(), os.path.getsize(p))
                znalezione.setdefault(k, (typ, p, k[2]))
    return list(znalezione.values())


def wozki_plan(c, a):
    lista = _szukaj_wozkow(c)
    print("oryginałów (bez duplikatów po nazwie i rozmiarze): %d" % len(lista))
    print(dict(collections.Counter(x[0] for x in lista)))
    return lista


def wozki_kopiuj(c, a):
    lista = wozki_plan(c, a)
    if not a.zapisz:
        return
    cel = c["cel"]
    uzyte, out = collections.defaultdict(set), []
    for typ, p, s in lista:
        os.makedirs(os.path.join(cel, typ), exist_ok=True)
        n = os.path.basename(p)
        if n.lower() in uzyte[typ]:
            b, e = os.path.splitext(n)
            n = "%s (%d)%s" % (b, len(uzyte[typ]), e)
        uzyte[typ].add(n.lower())
        shutil.copy2(p, os.path.join(cel, typ, n))
        out.append((typ, n, s, p))
    with open(os.path.join(cel, "_zrodla.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["typ", "plik", "rozmiar", "zrodlo"])
        w.writerows(out)
    print("skopiowane:", len(out))


# ───────────────────────── CLI ─────────────────────────

KROKI = {
    "oringi": {"stan": oringi_stan, "buduj": oringi_buduj, "sieroty": oringi_sieroty, "opisy": oringi_opisy,
               "indeks": oringi_indeks, "zdjecia": oringi_zdjecia},
    "wozki_hiwin": {"plan": wozki_plan, "kopiuj": wozki_kopiuj},
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rodzina", choices=sorted(KROKI))
    ap.add_argument("krok")
    ap.add_argument("--zapisz", action="store_true", help="realny zapis (domyślnie suchy przebieg)")
    ap.add_argument("--symbole", nargs="*", help="buduj: tylko te symbole")
    ap.add_argument("--niezgodne", action="store_true", help="buduj: także modele z Part Number != nazwa pliku")
    ap.add_argument("--dopusc-inny-inventor", action="store_true", help="buduj mimo innej wersji Inventora niż w bibliotece")
    a = ap.parse_args()
    if a.krok not in KROKI[a.rodzina]:
        sys.exit("Kroki dla %s: %s" % (a.rodzina, ", ".join(KROKI[a.rodzina])))
    c = rodzina(a.rodzina)
    KROKI[a.rodzina][a.krok](c, a)


if __name__ == "__main__":
    main()
