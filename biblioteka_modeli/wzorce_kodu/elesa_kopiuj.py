import os, re, csv, json, shutil
import win32com.client
S = os.path.dirname(os.path.abspath(__file__))
DEST = r"G:\Mój dysk\SUBIEKT\Elesa"
K = json.load(open(os.path.join(S, "kand2.json"), encoding="utf-8"))
LW = "Łączniki do profili aluminiowych lub stalowych"
ELU = "Elementy ustalające"; PRZ = "Przeguby, sprzęgła, przekładnie"; DZ = "Dźwignie zaciskowe"; EM = "Elementy maszyn"
UCH = "Uchwyty przemysłowe"; WS = "Wskaźniki"; ZAM = "Zamki"; WIB = "Wibroizolatory i sprężyny"; ES = "Elementy sterujące"; KR = "Koła ręczne, korby"
DOC = "Dociskacze, napinacze, zapięcia"; ZAW = "Zawiasy i akcesoria"
F = {  # rodzina -> (co to, do czego, typ); "?" = do uzupełnienia z katalogu
 "113": ("Trzpień montażowy z blokadą kulkową (ball lock pin)", "Szybkie, rozłączne mocowanie i pozycjonowanie elementów", ELU),
 "131": ("Łącznik zaciskowy do rur", "Łączenie rur/prętów pod kątem — ramy, osłony", LW),
 "132": ("Łącznik zaciskowy do rur", "Łączenie rur/prętów pod kątem — ramy, osłony", LW),
 "133": ("Łącznik zaciskowy do rur (różne średnice)", "Łączenie rur o różnych średnicach", LW),
 "134": ("Łącznik zaciskowy do rur", "Łączenie rur/prętów — ramy, osłony", LW),
 "135": ("Łącznik zaciskowy do rur", "Łączenie rur/prętów — ramy, osłony", LW),
 "136": ("Łącznik zaciskowy do rur/profili", "Łączenie rur/prętów — ramy, osłony", LW),
 "141": ("Łącznik zaciskowy do rur", "Łączenie rur/prętów", LW),
 "146": ("Łącznik zaciskowy do rur z płytą", "Mocowanie rury do płaskiej powierzchni", LW),
 "147": ("Łącznik zaciskowy do rur z płytą boczną", "Mocowanie rury do płaskiej powierzchni", LW),
 "163": ("Łącznik zaciskowy do rur", "Łączenie rur/prętów", LW),
 "164": ("Łącznik zaciskowy do rur", "Łączenie rur/prętów", LW),
 "165": ("Łącznik zaciskowy do rur", "Łączenie rur/prętów", LW),
 "193": ("Łącznik zaciskowy do rur", "Łączenie rur/prętów", LW),
 "194": ("Łącznik zaciskowy do rur", "Łączenie rur/prętów", LW),
 "241": ("Łącznik zaciskowy do rur", "Łączenie rur/prętów", LW),
 "273": ("Łącznik zaciskowy do rur", "Łączenie rur/prętów", LW),
 "274": ("Łącznik zaciskowy do rur", "Łączenie rur/prętów", LW),
 "275": ("Łącznik zaciskowy do rur", "Łączenie rur/prętów", LW),
 "471": ("Korba kątowa (cranked handle)", "Ręczne napędzanie / regulacja", KR),
 "473": ("Łącznik z podstawą do rur", "Mocowanie rury do powierzchni", LW),
 "474": ("Zacisk dwukierunkowy do rur", "Łączenie rur pod kątem", LW),
 "509": ("Jednostka kulowa (ball transfer unit)", "Swobodne toczenie przedmiotów po stole/rolkowisku", EM),
 "565": ("Uchwyt U do szaf", "Uchwyt do drzwi i pokryw maszyn", UCH),
 "612": ("Sworzeń ustalający z mechanizmem krzywkowym (cam action indexing plunger)", "Ustalanie położenia z blokadą w pozycji", ELU),
 "613": ("Sworzeń ustalający", "Ustalanie położenia elementów", ELU),
 "614": ("Zatrzask kulkowy (sworzeń sprężynujący z kulką)", "Zapadka pozycjonująca, lekkie blokowanie elementów", ELU),
 "615": ("Sworzeń sprężynujący (spring plunger)", "Zapadka/pozycjonowanie, docisk sprężynujący", ELU),
 "648": ("Przegub kulowy", "Przegubowe łączenie cięgien i dźwigni", PRZ),
 "705": ("Pierścień osadczy / tuleja zaciskowa", "Ustalanie elementów na wałku", EM),
 "706": ("Pierścień osadczy rozcięty (shaft collar)", "Ustalanie elementów na wałku", EM),
 "707": ("Pierścień osadczy rozcięty (shaft collar)", "Ustalanie elementów na wałku", EM),
 "708": ("Śruba dociskowa (clamping bolt)", "Docisk i blokada położenia", DOC),
 "711": ("Linijka / wskaźnik położenia", "Odczyt położenia przy regulacji", WS),
 "751": ("Przegub widełkowy (fork joint)", "Przegubowe łączenie cięgien", PRZ),
 "817": ("Sworzeń ustalający (indexing plunger)", "Ustalanie położenia z blokadą", ELU),
 "822": ("Sworzeń ustalający (indexing plunger)", "Ustalanie położenia z blokadą", ELU),
 "927": ("Dźwignia mimośrodowa zaciskowa", "Szybkie zaciskanie/luzowanie elementów", DZ),
 "ERX": ("Rękojeść nastawna", "Ręczne dokręcanie/luzowanie i regulacja położenia", DZ),
 "EBP": ("Uchwyt mostkowy (bridge handle)", "Uchwyt do przenoszenia/otwierania osłon", UCH),
 "CFM": ("Zawias", "Zawieszanie drzwi i osłon", ZAW),
 "DVM": ("Zderzak gumowy / amortyzator", "Tłumienie drgań i uderzeń", WIB),
 "ANPS": ("Pierścień osadczy rozłączny (split set collar)", "Ustalanie elementów na wałku", EM),
}
def info(sym):
    m = re.match(r"GN (\d+)", sym)
    k = m.group(1) if m else re.match(r"[A-Z]+", sym).group(0)
    return F.get(k, ("(do uzupełnienia z katalogu Elesa-Ganter)", "(do uzupełnienia)", "(do zaszeregowania)"))

app = win32com.client.Dispatch("Inventor.ApprenticeServer")
out, problems = [], []
for sym, p, ext, sz, n in K:
    safe = re.sub(r'[<>:"/\\|?*]', "-", sym).strip(" .")
    dst = os.path.join(DEST, safe)
    if os.path.isdir(dst):
        continue
    files = [p]; ver = pn = ""
    if ext in (".ipt", ".iam"):
        try:
            d = app.Open(p)
            try:
                ver = d.SoftwareVersionSaved.DisplayVersion
                pn = d.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value
                if ext == ".iam":
                    files += [fd.FullFileName for fd in d.ReferencedFileDescriptors]
            finally: d.Close()
        except Exception as e:
            problems.append((sym, "odczyt: " + str(e)[:60])); continue
    names = [os.path.basename(f).lower() for f in files]
    if len(set(names)) != len(names) or any(not os.path.exists(f) for f in files):
        problems.append((sym, "kolizja/brak składowych")); continue
    os.makedirs(dst)
    for f in files: shutil.copy2(f, os.path.join(dst, os.path.basename(f)))
    flag = ""
    if ext == ".iam":
        d = app.Open(os.path.join(dst, os.path.basename(p)))
        try:
            if any(os.path.normcase(os.path.dirname(fd.FullFileName)) != os.path.normcase(dst) for fd in d.ReferencedFileDescriptors):
                flag = "IAM wskazuje składowe poza własnym katalogiem — wymaga przebudowy"
        finally: d.Close()
    co, dosl, typ = info(sym)
    out.append(dict(symbol=sym, typ=typ, co_to=co, zastosowanie=dosl, format=ext.lstrip(".").upper() if ext not in (".stp", ".step") else "STEP (brak IPT)",
                    liczba_plikow=len(files), pliki=" | ".join(os.path.basename(f) for f in files), wersja_inventora=ver,
                    part_number_w_pliku=pn, zrodlo=p, uwagi=flag))
print("skopiowano:", len(out), "problemy:", len(problems))
for x in problems: print("  PROBLEM", x)
print("IAM do przebudowy:", sum(1 for o in out if o["uwagi"]))
print("opis do uzupełnienia:", sum(1 for o in out if o["typ"].startswith("(do")))
with open(os.path.join(DEST, "lista_pozycji_2.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0].keys()), delimiter=";"); w.writeheader(); w.writerows(out)
