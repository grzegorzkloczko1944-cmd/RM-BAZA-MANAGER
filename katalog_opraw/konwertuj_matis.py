# -*- coding: utf-8 -*-
"""Łożyska w oprawach (UCP, UCF, UCFL, UCPA, BPFT) — STEP z matis.sk → Inventor.

    python katalog_opraw/konwertuj_matis.py              # suchy przebieg — NIC nie tworzy
    python katalog_opraw/konwertuj_matis.py --zapisz     # tworzy modele w B:\\Znormalizowane\\Łożyska w oprawach

Źródło (29.09.2026, link od usera): https://www.matis.sk/sk/info/cad —
katalog „Strojní_součásti/Ložisková_tělesa", oprawy ISB/ASKUBAL, bezpośrednie
linki bez logowania. Pobrane (88 plików, 72 MB, z przerwą 1 s) do
`<katalog>\\_STEP_matis\\<TYP>\\`. Portale (TraceParts, PARTcommunity) odpadły:
ręczne klikanie każdego rozmiaru + blokady po kilku pobraniach.

JAK: STEP otwierany w Inventorze z `SilentOperation = True` (bez niego import
wyskakuje z oknem „Import danych wymiany" u usera), potem SaveAs:
  * `ucf204-ISB.stp`      → jedna część (wiele brył)  → `UCF204.ipt`
  * `ucp204-ISB_asm.stp`  → złożenie oprawa+wkładka   → `UCP204\\UCP204.iam`
                            + `UCP204\\UCP204 - P204.ipt`, `UCP204 - UC204.ipt`
Import zostawia raport `<nazwa>.htm` w folderze roboczym Inventora
(u usera OneDrive\\Dokumenty\\Inventor) — kasujemy te, które powstały teraz.
iProperties modelu głównego: Part Number = Title = SYMBOL (klucz dla MAG;
nazwę i opis z Subiekta wpisze „Przypisz 3D" w MAG albo zasiew).
Biały render 300×300 → `miniatury\\<SYMBOL>.png`, lista
`lozyska_oprawy_modele.csv` (symbol;plik;png;material) dla
`indeks_oringi_zasiew.py --lista lozyska_oprawy_modele.csv`.

Oprawy blaszane BPP/BPF/BPFL (numery katalogowe 6252…/6264…/6265…) POMIJANE —
nie wiadomo, pod jakim symbolem są w Subiekcie.
⚠️ Istniejących plików NIE nadpisujemy.
"""
import argparse
import csv
import glob
import os
import re
import sys
import time

KATALOG = r"B:\Znormalizowane\Łożyska w oprawach"
TYPY = ("UCP", "UCF", "UCFL", "UCPA", "BPFT")
K_ASM = 12291
K_IZO = 10759


def symbol_z_pliku(nazwa):
    """ucp204-ISB_asm.stp → UCP204; ASKUBAL UCPA 202.stp → UCPA202; bpft-sb202 → BPFT202."""
    b = os.path.splitext(nazwa)[0]
    m = re.search(r"(ucfl|ucpa|ucf|ucp)\s*-?\s*(\d{3})", b, re.I)
    if m:
        return (m.group(1) + m.group(2)).upper()
    m = re.search(r"bpft-?sb?(\d{3})", b, re.I)
    if m:
        return "BPFT" + m.group(1)
    return None


def D(o):
    from win32com.client import dynamic
    return dynamic.Dispatch(o._oleobj_ if hasattr(o, "_oleobj_") else o)


def sprzatnij_raporty(folder, baza, przed):
    for p in glob.glob(os.path.join(folder, glob.escape(baza) + "*.htm")):
        if p not in przed:
            try:
                os.remove(p)
            except OSError:
                pass


def render(app, doc, png):
    cam = D(D(app.TransientObjects).CreateCamera())
    cam.SceneObject = D(doc).ComponentDefinition
    cam.ViewOrientationType = K_IZO
    cam.Fit()
    cam.ApplyWithoutTransition()
    bialy = D(app.TransientObjects).CreateColor(255, 255, 255, 1)
    dop = D(app.DisplayOptions)
    osie = dop.Show3DIndicator
    dop.Show3DIndicator = False
    try:
        cam.SaveAsBitmap(png, 300, 300, bialy, bialy)
    finally:
        dop.Show3DIndicator = osie


def konwertuj(app, stp, symbol, katalog, png):
    """Zwraca ścieżkę głównego pliku (.ipt/.iam)."""
    doc = D(app.Documents.Open(stp, False))
    try:
        if doc.DocumentType == K_ASM:
            folder = os.path.join(katalog, symbol)
            os.makedirs(folder, exist_ok=True)
            robocze = os.path.dirname(doc.FullFileName)
            # WSZYSTKIE poziomy: wkładka bywa podzłożeniem (UC203_ASM.iam z własnymi
            # częściami) — zapis jako .ipt dawał E_INVALIDARG. Najpierw części,
            # potem podzłożenia, każde z właściwym rozszerzeniem.
            ard = D(doc.AllReferencedDocuments)
            wszystkie = [D(ard.Item(i)) for i in range(1, ard.Count + 1)]
            for c in sorted(wszystkie, key=lambda x: x.DocumentType != 12290):
                nazwa = os.path.splitext(c.DisplayName.split(":")[0])[0]
                ext = ".iam" if c.DocumentType == K_ASM else ".ipt"
                c.SaveAs(os.path.join(folder, "%s - %s%s" % (symbol, nazwa, ext)), False)
            cel = os.path.join(folder, symbol + ".iam")
        else:
            robocze = os.path.dirname(doc.FullFileName)
            cel = os.path.join(katalog, symbol + ".ipt")
        ps = D(doc.PropertySets)
        D(D(ps.Item("Design Tracking Properties")).Item("Part Number")).Value = symbol
        D(D(ps.Item("Inventor Summary Information")).Item("Title")).Value = symbol
        doc.SaveAs(cel, False)
        render(app, doc, png)
        # Natywna miniatura w pliku (Eksplorator, MAG): dokument niewidoczny nie
        # ma okna, więc Inventor nie ma z czego jej zrobić — wstawiamy biały
        # render (kImportFromFile = 79877, sprawdzone 29.09.2026) i zapis.
        if os.path.exists(png):
            doc.SetThumbnailSaveOption(79877, png)
            doc.Save()
        return cel, robocze
    finally:
        doc.Close(True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zapisz", action="store_true")
    ap.add_argument("--katalog", default=KATALOG)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--zrodlo", help=r"folder ze STEP (domyślnie <katalog>\_STEP_matis)")
    # tryb wewnętrzny: jeden plik w osobnym Inventorze (woła go rodzic)
    ap.add_argument("--jeden", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--stp", help=argparse.SUPPRESS)
    ap.add_argument("--symbol", help=argparse.SUPPRESS)
    ap.add_argument("--znacznik", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.jeden:
        return tryb_jeden(a)

    zrodlo = a.zrodlo or os.path.join(a.katalog, "_STEP_matis")
    plan, bez = [], []
    for typ in TYPY:
        for stp in sorted(glob.glob(os.path.join(zrodlo, typ, "*.stp"))):
            sym = symbol_z_pliku(os.path.basename(stp))
            (plan.append((sym, stp)) if sym else bez.append(stp))
    syms = [p[0] for p in plan]
    dubel = sorted({s for s in syms if syms.count(s) > 1})
    if a.limit:
        plan = plan[:a.limit]
    print("1. %s: do konwersji %d, bez symbolu %d, dublujące się symbole %s"
          % (zrodlo, len(plan), len(bez), dubel))
    for typ in TYPY:
        s = [p[0] for p in plan if re.match(typ + r"\d", p[0])]
        if s:
            print("   %-5s %2d  %s … %s" % (typ, len(s), s[0], s[-1]))
    istnieje = lambda sym: (os.path.exists(os.path.join(a.katalog, sym + ".ipt")) or
                            os.path.exists(os.path.join(a.katalog, sym, sym + ".iam")))
    print("   już są (pomijam): %d" % sum(1 for s, _ in plan if istnieje(s)))
    if not a.zapisz:
        print("\nSUCHY PRZEBIEG — nic nie utworzono. Realnie: --zapisz")
        return 0

    os.makedirs(os.path.join(a.katalog, "miniatury"), exist_ok=True)
    lista = os.path.join(a.katalog, "lozyska_oprawy_modele.csv")
    zrobione = {}
    if os.path.exists(lista):
        for w in csv.DictReader(open(lista, encoding="utf-8-sig"), delimiter=";"):
            zrobione[w["symbol"]] = w
    nowe, bledy, t0 = 0, [], time.time()
    for i, (sym, stp) in enumerate(plan, 1):
        png = os.path.join(a.katalog, "miniatury", sym + ".png")
        if istnieje(sym):
            plik = os.path.join(a.katalog, sym + ".ipt")
            if not os.path.exists(plik):
                plik = os.path.join(a.katalog, sym, sym + ".iam")
            zrobione.setdefault(sym, {"symbol": sym, "plik": plik,
                                      "png": png if os.path.exists(png) else "", "material": ""})
            continue
        wynik, blad = jeden_w_osobnym_procesie(stp, sym, a.katalog, png)
        if not wynik:                    # druga próba — w nowym, świeżym procesie
            usun_resztki(sym, a.katalog)
            wynik, blad = jeden_w_osobnym_procesie(stp, sym, a.katalog, png)
        if wynik:
            zrobione[sym] = {"symbol": sym, "plik": wynik,
                             "png": png if os.path.exists(png) else "", "material": ""}
            nowe += 1
        else:
            bledy.append("%s: %s" % (sym, blad))
            usun_resztki(sym, a.katalog)
        print("   %d/%d  %-8s %s  (%.0f s)" % (i, len(plan), sym, "OK" if wynik else "BŁĄD " + blad[:60],
                                            time.time() - t0), flush=True)
        # Lista na bieżąco — przerwany przebieg nie gubi zrobionych.
        zapisz_liste(lista, zrobione)
    zapisz_liste(lista, zrobione)
    print("\n2. UTWORZONE: %d, błędy: %d, lista: %s" % (nowe, len(bledy), lista))
    for b in bledy[:30]:
        print("   ⛔", b)
    return 1 if bledy else 0


def zapisz_liste(lista, zrobione):
    with open(lista, "w", encoding="utf-8-sig", newline="") as f:
        z = csv.DictWriter(f, ["symbol", "plik", "png", "material"], delimiter=";")
        z.writeheader()
        for w in sorted(zrobione.values(), key=lambda x: x["symbol"]):
            z.writerow(w)


def usun_resztki(sym, katalog):
    """Po nieudanej konwersji: niedokończone pliki TEGO symbolu (nic innego)."""
    import shutil
    for p in (os.path.join(katalog, sym + ".ipt"), os.path.join(katalog, "miniatury", sym + ".png")):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
    folder = os.path.join(katalog, sym)
    if os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)


# ── jeden plik = jeden świeży, UKRYTY Inventor (29.09.2026) ────────────────────
#
# Import tych STEP wywracał Inventora 2013 usera po kilku plikach (proces
# padał: „Serwer RPC jest niedostępny"). Dlatego NIGDY na sesji usera:
# DispatchEx → osobny proces, po jednym pliku Quit. Rodzic pilnuje czasu
# i przy awarii/zawieszeniu ubija WYŁĄCZNIE PID zapisany przez dziecko.

LIMIT_S = 300


def jeden_w_osobnym_procesie(stp, sym, katalog, png):
    """(ścieżka_modelu, None) albo (None, opis błędu)."""
    import json
    import subprocess
    import tempfile
    znacznik = os.path.join(tempfile.gettempdir(), "konwertuj_matis_%s.json" % sym)
    if os.path.exists(znacznik):
        os.remove(znacznik)
    cmd = [sys.executable, os.path.abspath(__file__), "--jeden", "--stp", stp, "--symbol", sym,
           "--katalog", katalog, "--znacznik", znacznik]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=LIMIT_S)
        wyj = (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        wyj = "zawieszony > %d s" % LIMIT_S
    stan = {}
    if os.path.exists(znacznik):
        try:
            stan = json.load(open(znacznik, encoding="utf-8"))
        except ValueError:
            stan = {}
        os.remove(znacznik)
    zabij_moj_inventor(stan.get("pid"))
    if stan.get("plik") and os.path.exists(stan["plik"]):
        return stan["plik"], None
    ost = [l for l in wyj.strip().splitlines() if l.strip()]
    return None, (stan.get("blad") or (ost[-1] if ost else "brak odpowiedzi"))[:150]


def zabij_moj_inventor(pid):
    """Ubija proces Inventora, który uruchomiło dziecko — jeśli jeszcze żyje."""
    if not pid:
        return
    import subprocess
    time.sleep(2)                        # po Quit proces kończy się chwilę
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


def tryb_jeden(a):
    """Dziecko: jeden STEP → Inventor, w SWOIM ukrytym Inventorze."""
    import json
    import pythoncom
    import win32process
    from win32com.client import DispatchEx, dynamic
    stan = {"pid": None}

    def zapisz_stan():
        json.dump(stan, open(a.znacznik, "w", encoding="utf-8"))

    pythoncom.CoInitialize()
    app = dynamic.Dispatch(DispatchEx("Inventor.Application")._oleobj_)
    stan["pid"] = win32process.GetWindowThreadProcessId(app.MainFrameHWND)[1]
    zapisz_stan()                        # PID od razu — rodzic ubije go przy awarii
    raporty = [os.path.join(os.path.expanduser("~"), "OneDrive", "Dokumenty", "Inventor"),
               os.path.join(os.path.expanduser("~"), "Documents", "Inventor")]
    przed = set()
    for r in raporty:
        przed |= set(glob.glob(os.path.join(r, "*.htm")))
    try:
        # Świeży Inventor bywa jeszcze w trakcie startu — praca od razu
        # kończyła się „Zdalne wywołanie procedury nie powiodło się".
        t0 = time.time()
        while time.time() - t0 < 90:
            try:
                if app.Ready:
                    break
            except Exception:
                pass
            time.sleep(1)
        time.sleep(2)
        app.Visible = False
        app.SilentOperation = True
        os.makedirs(os.path.join(a.katalog, "miniatury"), exist_ok=True)
        png = os.path.join(a.katalog, "miniatury", a.symbol + ".png")
        cel, _ = konwertuj(app, a.stp, a.symbol, a.katalog, png)
        stan["plik"] = cel
    except Exception as e:
        stan["blad"] = str(e)[:150]
    finally:
        zapisz_stan()
        baza = os.path.splitext(os.path.basename(a.stp))[0]
        for r in raporty:
            if os.path.isdir(r):
                sprzatnij_raporty(r, baza, przed)
        try:
            app.Quit()
        except Exception:
            pass
    return 0 if stan.get("plik") else 1


if __name__ == "__main__":
    sys.exit(main())
