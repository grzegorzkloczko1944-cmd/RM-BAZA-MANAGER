import os, re, sys, subprocess, time, csv, json
S = os.path.dirname(os.path.abspath(__file__))
E = r"G:\Mój dysk\SUBIEKT\Elesa"
SKIP = {"ERX.30 p-M6x40-C1", "ERX.44 p-M5x16-C2", "GN 113.4-6-30"}
KODY = {"ERX.44 p-M8x16-C1": "234159-C1", "ERX.63 p-M8x30-C1": "234346-C1", "ERX.30 p-M6x16-C6": "234021-C6", "CFM.40 CH-5": "425512"}
# rodzina -> OPIS (liczba pojedyncza, wg nazw typów ze strony producenta elesa-ganter.pl)
OPIS = [
 (r"^ERX", "Rękojeść nastawna"), (r"^CFM", "Zawias"), (r"^EBP", "Uchwyt"), (r"^DVM", "Wibroizolator"), (r"^ANPS", "Pierścień osadczy rozcięty dwuczęściowy"),
 (r"^GN 111\.8", "Linka zabezpieczająca"), (r"^GN 113\.[34]", "Trzpień montażowy z blokadą kulkową"),
 (r"^GN 13[134]|^GN 474-", "Łącznik dwukierunkowy"), (r"^GN 136", "Zawias metalowy"),
 (r"^GN 14[67]", "Łącznik z płytą boczną"), (r"^GN 16[35]", "Łącznik z płytą czołową"), (r"^GN 164", "Pierścień skalowy"),
 (r"^GN 194", "Łącznik teowy"), (r"^GN 274", "Łącznik obrotowy"), (r"^GN 300", "Dźwignia nastawna"), (r"^GN 302\.2", "Dźwignia nastawna płaska"),
 (r"^GN 350\.3", "Podkładka wahliwa"), (r"^GN (413|608|613|617|717)", "Trzpień ustalający"), (r"^GN 425\.3", "Uchwyt pałąkowy"),
 (r"^GN 431", "Śruba motylkowa"), (r"^GN 473", "Łącznik z podstawą"), (r"^GN 474\.1", "Łącznik równoległy"),
 (r"^GN 612\.9", "Trzpień ustalający z dźwignią"), (r"^GN 61[45]\.?[01]?-", "Zatrzask"), (r"^GN 615\.2", "Zatrzask kulkowy z tworzywa"),
 (r"^GN 648", "Przegub kulowy"), (r"^GN 705", "Pierścień osadczy"), (r"^GN 706\.2", "Pierścień osadczy rozcięty"),
 (r"^GN 707\.2", "Pierścień osadczy dwuczęściowy"), (r"^GN 708\.1", "Śruba dociskowa"), (r"^GN 711", "Linijka"),
 (r"^GN 751", "Przegub widełkowy"), (r"^GN 817", "Trzpień ustalający"), (r"^GN 822", "Trzpień ustalający mini"),
 (r"^GN 841", "Napinacz suwakowy"), (r"^GN 851\.1", "Zapięcie"), (r"^GN 913\.3", "Wkręt dociskowy"), (r"^GN 924", "Koło ręczne wieloramienne"),
]
def opis_dla(n):
    for rx, o in OPIS:
        if re.search(rx, n): return o
    return None
def czysty(n): return re.sub(r"-\((deactivated|closed)[^)]*\)$", "", n)
dirs = sorted(d for d in os.listdir(E) if os.path.isdir(os.path.join(E, d)) and not d.startswith("_") and d != "miniatury")
log = open(os.path.join(S, "batch_log.txt"), "a", encoding="utf-8"); wyn = []
def L(s):
    print(s, flush=True); log.write(s + "\n"); log.flush()
for d in dirs:
    if d in SKIP: continue
    nazwa = czysty(d); sym = KODY.get(nazwa, nazwa); op = opis_dla(nazwa)
    fl = [f for f in os.listdir(os.path.join(E, d)) if os.path.isfile(os.path.join(E, d, f))]
    iam = [f for f in fl if f.lower().endswith(".iam")]; ipt = [f for f in fl if f.lower().endswith(".ipt")]
    if op is None: L("POMINIĘTO (brak opisu rodziny): " + d); wyn.append((d, sym, nazwa, "", "brak opisu")); continue
    if iam and len(iam) == 1: script = "pozycja_iam.py"
    elif len(ipt) == 1 and not iam: script = "pozycja.py"
    else: L("POMINIĘTO (układ plików %s): %s" % (fl, d)); wyn.append((d, sym, nazwa, op, "układ plików")); continue
    ok = False
    for proba in range(3):
        r = subprocess.run([sys.executable, os.path.join(S, script), d, sym, nazwa, op], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        if r.returncode == 0: ok = True; break
        L("  próba %d nieudana (%s): %s" % (proba + 1, d, (r.stderr or r.stdout).strip().splitlines()[-1][:160] if (r.stderr or r.stdout).strip() else ""))
        time.sleep(10)
    L(("OK  " if ok else "BŁĄD ") + d + " -> " + sym + " | " + op + (" | " + r.stdout.strip().splitlines()[-1][:160] if ok and r.stdout.strip() else ""))
    wyn.append((d, sym, nazwa, op, "OK" if ok else "BŁĄD"))
with open(os.path.join(S, "batch_wynik.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh, delimiter=";"); w.writerow(["katalog_przed", "symbol", "nazwa", "opis", "status"]); w.writerows(wyn)
L("KONIEC: %d pozycji, OK=%d" % (len(wyn), sum(1 for x in wyn if x[4] == "OK")))
