# Biblioteka modeli 3D — instrukcja DLA AGENTA

**Przeczytaj to w całości, zanim cokolwiek zrobisz.** Użytkownik nie chce
tłumaczyć za każdym razem, co i jak. Tu jest: co on robi, jakie ma zasady, jak
to wykonać krok po kroku i gdzie się wykłada. Kod w `wzorce_kodu/` to
**przykłady do adaptacji**, nie gotowe narzędzie (użytkownik: „skrypt zawsze
się wykrzaczy, tu jest za dużo zawiłości") — pisz własny jednorazowy skrypt
na bazie wzorca, sprawdzaj wynik. `biblioteka.py` obok to opcjonalny skrót, nie musisz go używać.

---

## 1. O co chodzi (cel użytkownika)

Firma (RMPAK) używa Subiekta nexo (kartoteki towarów), Inventora (modele 3D)
i własnego programu MAG/RM_BAZA (magazyn, wstawianie modelu do złożenia).
Użytkownik buduje **biblioteki modeli 3D elementów handlowych**, tak żeby:

* **każda kartoteka Subiekta miała dokładnie jeden model 3D** (i odwrotnie — bez sierot i dubli),
* model miał **właściwe iProperties, natywną miniaturę na białym tle i PNG**,
* MAG widział model (indeks) i kartoteka miała **zdjęcie** w Subiekcie,
* opis/położenie w Subiekcie były uporządkowane.

Rodziny zrobione do tej pory: **O-ringi**, **łożyska w oprawach**, **wózki Hiwin** (samo znalezienie i kopia).
Kolejne będą podobne — ten sam schemat: *znajdź/zrób model → nazwij pod Subiekta → miniatury → indeks MAG → zdjęcia/opisy w Subiekcie*.

## 2. Zasady bezwzględne

1. **Najpierw suchy przebieg i liczby, potem zapis.** Pokaż użytkownikowi co i ile zrobisz.
   Zapis do Subiekta/kasowanie/nadpisanie robisz, gdy użytkownik **w tej rozmowie** powiedział
   „wgrywaj / nadpisuj / kasuj / zrób". Zgoda z poprzedniej partii **nie** przechodzi na następną.
2. **Nie kasuj plików ani niczego w Subiekcie bez wyraźnego polecenia.** Zamiast kasować — przenieś do `_stare\` i zapytaj.
3. **Nigdy nie wpisuj haseł** (użytkownik podaje je czasem w czacie — nie używaj, nie zapisuj; logowanie robi on sam).
4. **Nie dotykaj sesji Inventora użytkownika** (pytania „Zapisz?" psują mu pracę). Zawsze **osobna instancja** (patrz 4.1).
5. **Tylko istniejące na rynku warianty.** Nie zakładaj modeli „na zapas" (np. nierdzewnych wersji, których nikt nie sprzedaje). Wątpliwość → zapytaj albo pomiń.
6. **Nie commituj i nie pushuj** bez wyraźnej zgody. Nie modyfikuj plików sync/hooków/.claude bez pytania.
7. **Pisz po polsku, krótko, z liczbami.** Raport końcowy: co zrobione (liczby), co NIE zrobione, co wymaga decyzji. Nie twierdź „sprawdzone", jeśli nie sprawdzałeś.
8. Format plików Inventora: patrz 4.2 — **zapis w 2015 jest zawsze dozwolony** (decyzja użytkownika 01.10.2026); w raporcie podawaj wersję plików.
9. **ZASIEWANE ZAWSZE IDĄ Z MINIATURĄ DO SUBIEKTA (zasada usera 08.10.2026, wszystkie katalogi: O-ringi, łożyska, tuleje, HIWIN, IGUS, ELESA, kolejne).** Zdjęcie kartoteki w Subiekcie = PNG z `miniatury\` biblioteki; to część zasiewu, NIE wymaga osobnej zgody. Robi to `indeks_oringi_zasiew.py --zapisz` (moduł `zdjecia_do_subiekta.py`; tylko kartotekom bez zdjęcia; `--bez-zdjec` wyłącza) albo osobno `python zdjecia_do_subiekta.py --katalog … --lista … --zapisz`. Zasiew bez zdjęć = partia niedokończona. Kolejność: pliki w B: → natywne miniatury w plikach → kartoteki → sync kopii → zasiew MAG → **zdjęcia** → oceny Rekomendowane (ADMIN).

## 3. Nomenklatura (Subiekt ↔ Inventor)

| Pole | Wartość |
|---|---|
| Symbol kartoteki Subiekta | klucz; = nazwa pliku modelu |
| **Part Number** (Design Tracking) | = symbol |
| **Title** (Inventor Summary Information) | = symbol (łożyska) / „oring 20x3" (O-ringi, tak robi generator) |
| **Description** (Design Tracking) | łożyska: „Zespół łożyskowy" / „Zespół łożyskowy nierdzewny" (SS); O-ringi: „Oring 20x3 EPDM" |
| Opis w Subiekcie | łożyska j.w.; **O-ringi: „Oring"** |
| Położenie (regał/półka) | **PoleWlasne1** w Subiekcie, format `R22/P5`. **NIE w Opisie.** |
| Średnica wałka (łożyska) | **NIE w nazwie** — pójdzie do Subiekta jako wymiar przy mapowaniu |

Symbol Subiekta użyty w dokumentach **nie da się zmienić** (most odmawia). Takie kartoteki-„widma"
zostają bez modelu; model robimy dla kanonicznej kartoteki.

## 4. Narzędzia i jak ich używać

### 4.1 Inventor (COM, Python + pywin32)

* **Osobna instancja:** `app = win32com.client.DispatchEx("Inventor.Application")`; czekaj na `app.Ready`;
  `app.SilentOperation = True` (bez okien „Czy zapisać?"); `app.Visible = True` (potrzebne do natywnych miniatur).
  PID okna: `GetWindowThreadProcessId(app.MainFrameHWND)`. Na końcu **`app.Quit()` + `taskkill /F /PID <pid>`** — tylko własny PID.
  NIGDY `GetActiveObject`/`GetObject` (to sesja użytkownika). Wzorzec: `wzorce_kodu/konwertuj_stp.py`, `dodaj_iam.py`.
* **Odczyt bez ryzyka:** `Dispatch("Inventor.ApprenticeServer")` — iProperties, geometria, referencje. **Nie zapisuje.** Wzorzec: `wzorce_kodu/pn.py`.
* **Tło miniatur:** natywna miniatura bierze tło z aktywnego schematu kolorów. Na czas pracy: `ColorSchemes.Item("Prezentacja").Activate()`
  (białe), potem przywróć poprzedni. Wyłącz `DisplayOptions.Show3DIndicator`, `GeneralOptions.EnablePrehighlight`
  **i** `ColorSchemes.EnablePrehighlight` (inaczej czerwone podświetlenie na PNG); po pracy przywróć.
* **Miniatura natywna (w pliku):** widoczny dokument, `SelectSet.Clear()`, kamera izometria `ViewOrientationType = 10759`,
  `cam.Apply(); cam.Fit(); cam.Apply(); ActiveView.Update(); sleep(1); ActiveView.Update()`,
  `doc.SetThumbnailSaveOption(79875, "")` (kActiveWindowOnSave), `doc.Dirty = True`, zapis. Ukryty Inventor daje poszarpane miniatury.
* **PNG do `miniatury\`:** `cam.SaveAsBitmap(png, 600, 600, biały, biały)` — łożyska 600×600, O-ringi 300×300 (kamera przejściowa
  `TransientObjects.CreateCamera()`, `cam.SceneObject = cd` — **bez `Set`**, właściwość Let). Rób PNG w **osobnym otwarciu** pliku.
* **Zapis na dysk sieciowy G:/B:** pracuj na **kopii w katalogu roboczym**, na miejsce kopiuj tylko plik główny
  (Inventor zostawia `OldVersions\`, a na G: nie chcemy śmieci). Po zapisie sprawdź Apprentice’em, że referencje IAM
  wskazują na własny katalog (`ReferencedFileDescriptors`).
* **Wygląd/kolor:** kolor to **Wygląd** (Appearance), nie materiał. `PartComponentDefinition.ClearAppearanceOverrides()`,
  `PartDocument.AppearanceSourceType = 100614` (kolor z materiału), materiał z biblioteki
  (`MaterialAssets.Item("304").CopyTo(doc, True)` gdy go nie ma w dokumencie). Dla IAM także `AssemblyComponentDefinition.ClearAppearanceOverrides()`.
* **STEP → IPT:** `Documents.Open(step, False)`; jeśli wyszło złożenie (12291) — zapisz części osobno przed IAM, potem nowy IPT
  z szablonu i `DerivedAssemblyComponents.CreateDefinition(iam)`, `DeriveStyle = 80643` (jako wiele brył), `.Add(def).BreakLinkToFile()`.
  Jeśli STEP dał od razu część — zapisz i otwórz ponownie **widocznie**. Wzorzec: `konwertuj_stp.py`.
* **Rysowanie od zera** (gdy brak modelu): `wzorce_kodu/rysuj_ucfl_mini.py` — pułapki: enumeracje bierz z typelib (nie zgaduj),
  płaszczyzny robocze ukrywaj, kształty nakładające się rysuj w **osobnych szkicach**, trapezy łącz punktami (`EndSketchPoint`),
  linia osi obrotu jako **zwykła** (nie konstrukcyjna) jeśli zamyka profil.
* Okna modalne (VBA, Bitdefender) blokują COM — jeśli zawiesza się, sprawdź czy nie ma okna u użytkownika.
* **Okno „Microsoft Visual Basic for Applications — błąd ładowania ‘Module7’, kontynuować?”** pojawia się przy KAŻDYM starcie nowej instancji Inventora
  (projekt VBA użytkownika). **Nie każ użytkownikowi klikać „Tak”** — przed seryjną pracą uruchom w tle `wzorce_kodu\watchdog_vba.py <PID_sesji_użytkownika> ...`
  (PID-y istniejących Inventor.exe użytkownika, sprawdź `Get-Process Inventor` PRZED startem). Watchdog klika „Tak” tylko w oknach procesów Inventor.exe spoza listy chronionych.
  Zatrzymaj go po zakończeniu pracy (TaskStop). Przyczyny (Module7) nie naprawiaj bez pytania.

### 4.2 Wersje Inventora (WAŻNE)

* Biblioteka O-ringów `B:\Znormalizowane\Oringi` i większość starych modeli jest w formacie **2013**.
* Komputer **Mongo (firma) ma tylko Inventora 2015** → zapis tu przeprowadza plik na **2015**, którego 2013 nie otworzy.
* Sprawdź: `ApprenticeServerDocument.SoftwareVersionSaved.DisplayVersion` (co jest w pliku) i `app.SoftwareVersion.DisplayVersion` (czym zapisujesz).
* Zasada (decyzja użytkownika 01.10.2026): **pliki mogą być w formacie 2015** — dla wszystkich bibliotek (O-ringi, łożyska,
  Elesa-Ganter i kolejne). **Nie pytaj** o zgodę na 2015; tylko podaj wersję w raporcie. Łożyska w oprawach na G: już są w 2015.
* Szablon pliku (`GetTemplateFile`) pochodzi z **aktywnego projektu** użytkownika — sprawdź, że są w nim materiały gum
  (EPDM, `NBR-` z myślnikiem, VITON, SILIKON) i że szablon nie jest specyficzny dla jednego projektu.

### 4.3 Subiekt (przez „most") — `subiekt_bridge`

```python
import sys; sys.path.insert(0, r"C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER")
import subiekt_bridge
subiekt_bridge.call(TRYB, {"plan": {...}, "zapisz": True/False}, timeout=120, write=True/False)
```
Działa na komputerze firmowym (Mongo). `zapisz: False` = suchy przebieg (most opisuje co zmieni).

| Cel | Tryb i plan |
|---|---|
| Odczyt kartotek + Opis + Położenie | `"magazyn"`, args `{"tylko_niezerowe": False}` → `["pozycje"]` z `Symbol, Nazwa, Opis, Polozenie, Rodzaj, Dostepne…` (**żywy Subiekt**) |
| Zmiana Opisu/Nazwy | `"kartoteka-edytuj"`, `{"plan": {"pozycje": [{"symbol": S, "opis": "Oring"}]}, "zapisz": True}` (nigdy nie rusza symbolu) |
| Położenie | `"pola-wlasne"`, `{"plan": {"pole": "PoleWlasne1", "pozycje": [{"symbol": S, "wartosc": "R6/P3"}]}, "zapisz": True}` |
| Zdjęcia | `"zdjecie"`, `{"plan": {"akcja": "lista"/"dodaj"/"usun", "symbol": S, ...}}`; dodaj: `nazwa`, `typ:"png"`, `dane_b64` |
| Usunięcie kartoteki | `"kartoteka-usun"` (Subiekt odmówi, gdy użyta) — tylko na polecenie |
| Zmiana symbolu | tryb `"symbole"` — most odmówi dla użytych w dokumentach |

* **Most `zdjecie` nie ma pola „istnieje"** — brak kartoteki to krok `{"Status": "blad", "Szczegoly": "nie ma takiej kartoteki"}`
  i pusta lista zdjęć (wygląda jak kartoteka bez zdjęcia!). Zawsze sprawdzaj `kroki`.
* **Zdjęć nie nadpisuj** — dodawaj tylko kartotekom bez zdjęcia (chyba że użytkownik kazał inaczej).
* Kopia Subiekta w MAG (`http://W2019S:5061/mag/szukaj?q=…&limit=…`, tylko odczyt) **bywa nieaktualna** (stare symbole) —
  do decyzji używaj żywego odczytu przez most.

### 4.4 MAG (indeks 3D)

* `python indeks_oringi_zasiew.py [--zapisz]` w `RM-BAZA-MANAGER` — z `<katalog>\oringi_modele.csv` (`symbol;plik;png;material`)
  wpisuje przypisania modeli (`zrodlo='reczny'`) + białe miniatury na **RM_SERWER 192.168.100.84:5060**.
  Dla innej rodziny: `--katalog <dir> --lista <plik.csv>` (tak robiono łożyska). **Zawsze najpierw bez `--zapisz`.**
* Zasiew dopiero **po** ustaleniu ostatecznych nazw plików (inaczej utrwali stare).

## 5. Przepisy

### 5.A Nowa partia O-ringów

1. Użytkownik zakłada/poprawia kartoteki `OR-<D>X<przekrój> <MATERIAŁ>` w Subiekcie (przecinek dziesiętny; materiał: EPDM, NBR, FPM/FKM/VITON, VMQ/SIL).
2. **Stan:** odczytaj kartoteki `OR-*` (magazyn), porównaj z `B:\Znormalizowane\Oringi\*.ipt` po symbolu; sprawdź Part Number modeli (Apprentice, `pn.py`).
   Raport: kartoteki bez modelu, sieroty, PN ≠ nazwa, Opis ≠ „Oring", brak położenia.
3. **Budowa** brakujących: `RM-BAZA-MANAGER\katalog_oringow\generuj_modele.py` (funkcja `zbuduj`) — metoda z makra TOOLS++ „funkcja 18":
   pierścień ID / OD=ID+2×przekrój na XY, wysokość = przekrój, zaokrąglenie 0,4×przekrój, Part Number = symbol,
   materiał = kolor gumy (EPDM→EPDM, NBR→`NBR-`, FKM/FPM/VITON→VITON, VMQ/VQM/SIL→SILIKON), biały render 300×300. Wzorzec użycia z osobnym Inventorem: `wzorce_kodu/or_nadpisz.py`.
   Buduj do katalogu roboczego, potem kopiuj do `B:` (nadpisanie za zgodą). Generator sam nie nadpisuje istniejących.
4. Zaktualizuj `oringi_modele.csv` (symbol;plik;png;material), posprzątaj `OldVersions\`.
5. Sieroty (modele bez kartoteki) i duble — **lista do zatwierdzenia**, kasowanie tylko na polecenie.
6. `indeks_oringi_zasiew.py --zapisz` → zdjęcia (`wzorce_kodu/or_zdjecia.py`, tylko kartotekom bez zdjęcia) → Opis „Oring" (kartoteka-edytuj) → położenie z Opisu (`Reg 6.3` → `R6/P3`) do PoleWlasne1, jeśli PoleWlasne1 puste.
7. Kartoteki-widma (użyte w dokumentach, np. `OR-13x1,5 EPDM 70`, `… S`/`… Silikon`) zostają bez modelu — nie rób dla nich pliku.

### 5.B Łożyska w oprawach — biblioteka `G:\Mój dysk\SUBIEKT\Łożyska w oprawach`

Układ: `<SYMBOL>\<SYMBOL>.ipt|.iam` (+ części IAM w tym katalogu), `miniatury\<SYMBOL>.png` (600×600),
`lozyska_oprawy_modele.csv` (`symbol;plik;png;material` — SS: materiał 304; sortowanie musi znać sufiks „ Mini"), `_uzupelnienie_oprawy.csv` (pochodzenie).
Zawartość: rodziny UCP, UCPA, UCF, UCFL, UCFC, UCFB, UCFH, UCT, KFL, KP, BP*, rozmiarówka 201–212 (UC — same wkładki — **nie**), wersje **SS** (nierdzewne, 304), UCFL201/202 Mini.

Nowe łożysko:
1. **Znajdź źródło** w kolejności: istniejące w `C:\Projekty`, `B:\`, `V:\` → plik od użytkownika → 3dfindit/sklep producenta
   (logowanie robi użytkownik, **nigdy nie wpisuj jego hasła**; blokady pobierania konta ASKUBAL — nie obchodź).
   **Reguła formatu: IPT > IAM > STEP; przy wielu IPT bierz największy plik.** Model IAM zastąp IPT, jeśli istnieje.
2. **STEP → IPT** (wzorzec `konwertuj_stp.py <stp> <SYMBOL> --tytul --opis`), IAM kopiuj z częściami (`dodaj_iam.py`) i **sprawdź referencje**.
3. **iProperties:** Part Number = Title = symbol; Description „Zespół łożyskowy" (SS: „…nierdzewny"); miniatura natywna biała; PNG 600×600.
   Wzorce: `napraw_tytuly.py`, `png_izolowany.py`.
4. **SS:** kopia wersji zwykłej, materiał 304 (kolor z materiału: `ClearAppearanceOverrides` + `AppearanceSourceType=100614`), symbol `SS <symbol>`. `ss_zaloz.py`.
   Zakładaj tylko warianty istniejące na rynku (NTN/Transdev SUC 204–212, SUCFB 204–210; miniaturowe SS-KP/SS-KFL pominięte świadomie).
5. Brak modelu i użytkownik poda wymiary → **rysuj od zera** (`rysuj_ucfl_mini.py`, jedna część, kilka brył: obudowa + wkładka + smarowniczka; kontroluj rozstaw otworów i gabaryt).
6. Dopisz do CSV, zrób indeks MAG (`--katalog … --lista lozyska_oprawy_modele.csv`), **zdjęcia do Subiekta — zawsze w ramach zasiewu, bez osobnej zgody** (reguła 9 w §2).
7. **Decyzje użytkownika (nie wracaj bez prośby):** pomijamy UCFH211/212, rozmiary >212, miniaturowe SS, UCFL201 Slim. Mapowanie do Subiekta odłożone (wymiar = średnica wałka).

### 5.C „Znajdź i skopiuj modele" (np. wózki Hiwin)

1. Szukaj po **nazwach plików** w `B:\`, `C:\Projekty`, `V:\` (`os.walk`, pomiń `OldVersions`); V: trwa ~3 min. Rozszerzenia modeli: `.ipt .iam .stp .step`.
2. Typ z nazwy regexem; **odrzuć** rysunki (`.idw/.dwf/.pdf`), szyny, `_MIR`, przeróbki z projektów.
3. Zapytaj/ustal zakres: użytkownik zwykle chce **oryginały producenta** (nazwy nadane przez producenta), nie tysiące wariantów z projektów.
   Wózki Hiwin 30.09.2026: 178 plików / 31 typów (HG/MGN), wzorzec `wzorce_kodu/hiw_orygin.py`; wyjściowo 1730 trafień → 554 różnych po rozmiarze.
4. Kopiuj do wskazanego katalogu w podfolderach per typ + `_zrodla.csv` (typ; plik; rozmiar; źródło). Nie ruszaj oryginałów. Nie nadpisuj tego, co użytkownik już przeniósł.
5. Wynik: podaj liczby i to, czego **nie** sprawdzałeś (geometria, serie spoza zakresu).

## 6. Pułapki (znane, kosztowały czas)

* **Heredoc/PowerShell zjada backslash** (`\\nic`, regexy `\d`, JSON) — pliki z regexami/UNC zapisuj narzędziem Write albo `json.dump`; Python widzi `/tmp` inaczej niż bash — używaj scratchpada.
* **Kopia Subiekta w MAG nieaktualna** — decyzje na żywym odczycie przez most.
* **Apprentice nie zapisuje**; zapis iProperties = pełny Inventor.
* **Ukryty Inventor = złe miniatury**; **czerwone PNG** = prehighlight/zaznaczenie.
* **Zaśmiecanie `Documents\Inventor`** przez Inventora (pliki `.htm`, `OldVersions`) — sprzątaj wąskimi wzorcami nazw i oknem czasu.
* **Nie kasuj masowo w katalogach użytkownika** — zabezpieczenia to blokują; kasuj po wyraźnym „kasuj" i po obejrzeniu listy.
* Zmiana symbolu kartoteki użytej w dokumentach niemożliwa (most odmówi) — sprawdzaj `NaDokumentach` zanim obiecasz zmianę.
* Bitdefender potrafi blokować Inventora/VBA i PyInstaller — jeśli COM „stoi", to często to.
* Kopia `.ipt` na G: (Google Drive) — bez `OldVersions`; pliki wewnątrz `G:` synchronizują się, nie dotykaj ich zbędnie.
* Klucz `PoleWlasne1` = położenie; `null` = „nie ruszaj", nie „wyczyść".

## 7. Definicja „zrobione" (checklista końcowa)

Dla każdej partii przed raportem sprawdź i podaj liczby:

- [ ] plik = symbol, Part Number = symbol (Apprentice, 0 rozbieżności),
- [ ] Description/Title zgodne z rodziną, kolor = materiał,
- [ ] natywna miniatura biała + PNG w `miniatury\`, wpis w CSV rodziny,
- [ ] brak sierot i dubli (albo lista do decyzji),
- [ ] indeks MAG zasiany (liczba przypisań),
- [ ] **zdjęcia w Subiekcie dla KAŻDEJ zasianej pozycji** (wysłane / miały już / bez kartoteki; audyt: lista zdjęć przez most = 100 %) — zasiew bez zdjęć to niedokończona partia,
- [ ] **oceny MAG: „Rekomendowane” z automatu** dla każdej pozycji **zasiewanej z biblioteki** (model w `B:\Znormalizowane\<katalog>`, zasiew MAG `reczny`, z miniaturą; nie dla modeli z automatycznego skanu/IDW) (autor **ADMIN**; `POST /mag/ocena/oznacz?ocena=rekomendowane&kto=ADMIN`, symbole w treści, ≤400 naraz, po `subiekt_kopia_sync.py`; nie nadpisuj Zastrzeżeń ani „do usunięcia”) — dotyczy też HIWIN, IGUS, ELESA i kolejnych katalogów (decyzja usera 08.10.2026),
- [ ] Opis/Położenie w Subiekcie poprawione (odczyt kontrolny po zapisie),
- [ ] wersja Inventora plików podana w raporcie,
- [ ] pamięć projektu zaktualizowana (`project_*` w katalogu memory + wpis w `MEMORY.md`).

## 8. Gdzie co leży

| Co | Gdzie |
|---|---|
| Ta instrukcja i wzorce kodu | `C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER\biblioteka_modeli\` (`README.md`, `wzorce_kodu\`) |
| Generator O-ringów, wymiarówka | `RM-BAZA-MANAGER\katalog_oringow\` (`generuj_modele.py`) |
| Zasiew MAG | `RM-BAZA-MANAGER\indeks_oringi_zasiew.py`, `indeks_modeli_3d.py` |
| Most Subiekta | `RM-BAZA-MANAGER\subiekt_bridge.py` (+ `MAGAZYN.md`: PoleWlasne1, tryby) |
| Modele O-ringów | `B:\Znormalizowane\Oringi\` (+ `miniatury\`, `oringi_modele.csv`) |
| Łożyska w oprawach | `G:\Mój dysk\SUBIEKT\Łożyska w oprawach\` |
| Wózki (kopia) | `G:\Mój dysk\SUBIEKT\Wózki\<TYP>\` |
| Pamięć użytkownika | `C:\Users\mongo\.claude\projects\C--RMPAK-CLIENT-Repozytoria-NOW\memory\` (`project_lozyska_w_oprawach_g`, `project-oringi-modele-b-stan`, `project_pipeline_biblioteka_modeli`) |
| Notatki nomenklatury MAG | `RM-BAZA-MANAGER\pamiec\` (`project_lozyska_w_oprawach`, `project_mag_wstaw_i_przypisz`, `project_oringi_*`) |

## 9. Elesa-Ganter — `V:\! HASIOK\Elesa` (ustalone 01.10.2026; przeniesione z G: 02.10.2026)

Skrypty wzorcowe mają w stałej ścieżkę `G:\Mój dysk\SUBIEKT\Elesa` — zmień `E` na `V:\! HASIOK\Elesa`. Strona wyboru dla zespołu: `WYBOR_Elesa-Ganter.html` w tym folderze (kod w `_narzedzia\strona_wybor\`), zaznaczenia zbierane z CSV w `wybory\`.

Kandydaci zebrani z B:, C:\Projekty, V: (nazwy plików: kody GN/ERX/EBP/CFM…), bez przeróbek projektowych (`_MIR` itp.);
pozycje występujące tylko w 1 projekcie → `_rzadkie\`. Skrypty wzorcowe: pozycja IPT i pozycja IAM (patrz niżej).

* **Układ:** `Elesa\<OZNACZENIE>\<SYMBOL>.ipt` (IAM: `<SYMBOL>.iam` + `<SYMBOL>-1.ipt`, `-2.ipt`…), `Elesa\miniatury\<OZNACZENIE>.png` (600×600, białe tło), stare pliki w `_stare\`.
* **iProperties:** Part Number = **KOD produktu producenta** (np. `234046-C1`; kod bazowy z tabeli + indeks koloru),
  Title (NAZWA) = **samo oznaczenie** (np. `ERX.30 p-M6x40-C1`, BEZ opisu), Description (OPIS) = co to jest (ze strony producenta, np. „Rękojeść nastawna”).
* **Typy bez kodu** (np. pozycje GN): Part Number = oznaczenie. **Sprawdź każdy TYP (rodzinę)** na elesa-ganter.pl, czy ma kolumnę „Kod”, zanim założysz PN.
  Źródła kodów: tabele w PDF producenta (`elesa.com/siteassets/PDF/PDF_EN/<seria>.pdf`) i JSON-LD na stronie serii elesa-ganter.pl (patrz niżej). Tabele wariantów na stronie ładują się dynamicznie — WebFetch ich nie widzi; w przeglądarce odrzucaj cookies.
* **Miniatura natywna** — biała tylko gdy w osobnej instancji aktywny schemat „Prezentacja”; kontrola z pliku: `IShellItemImageFactory` (tło piksela 255,255,255). Stary plik ze źródła bywa niebieski.
* **IAM ze zgodnymi nazwami składowych co w `C:\Projekty`** — referencje wracają do projektu mimo `ReplaceReference`.
  Naprawa: zapisz IPT pod nowymi nazwami (`<SYMBOL>-N.ipt`) i **zbuduj IAM od nowa** (przenieś Transformation, Grounded=True), potem sprawdź Apprentice’em, że referencje są lokalne.
**Zbieranie kandydatów (kolejność kroków, skrypty w `wzorce_kodu\`):**
1. `elesa_szukaj.py` — przeszukanie B:, C:\Projekty, V: po nazwach plików (kody GN/ERX/EBP/CFM… i nazwy opisowe EN/DE; V: trwa ok. 3 min) → CSV trafień.
2. `elesa_grupuj.py` — normalizacja do symbolu producenta, odrzucenie `_MIR`/workspace/Festo, wyłączenie składowych IAM, wybór reprezentanta (IPT > IAM z kompletem składowych > STEP; źródło B: > C: > V:, największy plik), odjęcie tego, co już w bibliotece.
3. `elesa_kopiuj.py` — kopia do `Elesa\<symbol>\` (IAM z wszystkimi składowymi), lista CSV (typ, co to, zastosowanie, format, wersja Inventora, źródło).
4. `elesa_czestosc.py` — w ilu różnych projektach występuje symbol; **pozycje z 1 projektu → `_rzadkie\`** (kryterium „bardzo rzadko” ustalił użytkownik; próg można zaostrzyć).
5. `elesa_porzadki.py` — składowe/duble/wątpliwe do podkatalogów pomocniczych; potem `elesa_batch.py` (tam też słownik OPIS w liczbie pojedynczej wg rodzin).
STEP bez IPT konwertuj `konwertuj_stp.py` (osobna instancja Inventora).
* Opisy rodzin „do uzupełnienia” — z nazw na stronie producenta; oznaczaj jako do weryfikacji.
* **Seryjne przetwarzanie** (wzorzec `elesa_batch.py`): sekwencyjnie, po każdej pozycji log do pliku; do 3 prób na pozycję (start Inventora bywa przejściowo nieudany
  z błędem „Wykonanie serwera nie powiodło się”); IAM zawsze przez przebudowę; składowe IAM, duble biblioteki i wątpliwe nazwy wcześniej do `_skladowe\`, `_juz_w_bibliotece\`, `_do_decyzji\`
  (nigdy kasowanie). Wolne pozycje bez opisu rodziny — pomijaj i raportuj.
* **Weryfikacja kodu/opisu na elesa-ganter.pl** (`elesa_typy_strona.py`): strona serii `/produkty/<dowolna-kategoria>/seria/<slug>` zawiera JSON-LD
  (`brand` = ELESA → ma kod w `sku`; `brand` = GANTER → brak kodu, tylko Oznaczenie; `mpn` = seria; `description` po polsku). **Zawsze sprawdź, że `mpn` zgadza się z rodziną** (dopasowanie slugów jest rozmyte).
  Mapę wszystkich serii (kategoria + typ po polsku) daje `static/sitemap/sitemap.B2BStorePOL.pl.catalog.products.xml.gz` (z robots.txt). Kody Elesa (np. ERX, CFM): tabele w PDF (`elesa.com/siteassets/PDF/PDF_EN|PDF_US/<seria>..pdf`, pary „kod-*” + oznaczenie).
  Wyszukiwarka sklepu (`SearchDisplay`) nie działa bez JS — nie używaj.

## 10. Strona HTML do podejmowania decyzji (lista pozycji z miniaturami i ptaszkami)

Użytkownik chce pokazać zespołowi listę pozycji (np. kandydatów do biblioteki) i zebrać decyzje „tak/nie” (ptaszek „Do biblioteki”).
Gotowy wzorzec z Elesa-Ganter (`wzorce_kodu\decyzje_*`; stan: 272 pozycje, 4 zakładki: Zrobione / Do decyzji / Już w bibliotece / Rzadkie).

**Kroki:**
1. **Miniatury i spis** — `decyzje_miniatury_lista.ps1` (PowerShell; plik zapisz z BOM UTF-8, inaczej polskie znaki w ścieżkach się psują): dla każdej pozycji
   bierze miniaturę natywną z Eksploratora (`IShellItemImageFactory`) i zapisuje `manifest.csv`. Pliki źródłowe z projektów często **nie mają** osadzonej miniatury (u Elesy 120 z 272).
2. **Brakujące miniatury** — `decyzje_render_brakujace.py`: osobna instancja Inventora (jak zwykle: watchdog okna VBA, PID-y użytkownika chronione, `app.Quit()` + `taskkill` własnego PID), otwiera plik BEZ zapisu
   (`Documents.Open`, `Close(True)`), schemat „Prezentacja”, izometria, `SaveAsBitmap` 300×300 białe tło. ~10 s na pozycję. STEP też się renderuje.
3. **Dane strony** — `decyzje_build_data.py`: scala metadane (kod, opis, format, wersja, projekt źródłowy, powód „do decyzji”) z miniaturami (JPEG 180 px, base64) w `items.json` (~1 MB na 270 pozycji).
4. **Strona** — szablon `decyzje_szablon.html` (zakładki z licznikami, wyszukiwarka, filtr, „zaznacz/odznacz widoczne”, karty z checkboxem, kto i kiedy zmienił). Dwie wersje:
   * **Artefakt claude.ai** (`Artifact` + `db`, `user`, `downloads`): wspólne zaznaczenia na żywo, ale odbiorcy muszą mieć dostęp do artefaktu — link jest prywatny, **udostępnienie robi użytkownik w menu „Udostępnij”**, uprawnienia współautora do zaznaczania. Przed pracą załaduj skille `artifact-design` i `artifact-capabilities`.
   * **Plik samodzielny do sieci** (`decyzje_build_lokalny.py` + `decyzje_patch_lokalny.js`): zwykły HTML na dysku sieciowym (np. `V:\! HASIOK\...`), działa dwuklikiem; zaznaczenia w `localStorage` przeglądarki, imię + „Zapisz mój wybór (CSV)” → plik do folderu `wybory\`; wspólne zestawienie scalasz z CSV. To wersja, gdy użytkownik mówi „musi być po sieci”.
5. Domyślnie zaznaczone tylko pozycje „zrobione” (propozycja); rozróżniaj „propozycja” od „decyzja” (zapis w bazie/CSV).

**Pułapki:** podgląd `file://` w panelu przeglądarki bywa zablokowany — skład JS sprawdź `node --check` na wyciągniętym skrypcie; łańcuchy z `\r\n`/`\uFEFF` wstawiane z heredoca bash/Python tracą backslashe —
fragmenty JS trzymaj w osobnych plikach (`patch_lokalny.js`) zapisanych narzędziem Write; dane JSON w `<script type="application/json">` zamieniaj `</` na `<\/`.

## 11. IGUS — `V:\! HASIOK\IGUS` (02.10.2026)

Tory jak w sekcji 9 (Elesa), ale kody IGUS parsuje się z nazw plików; **wcześniej zrób zrzut nazw wszystkich modeli** (`zrzut_modeli.py` → CSV, ~380 tys. plików z B:, C:\Projekty, V:) i iteruj regexami na CSV zamiast skanować dyski.

* **Co jest kodem IGUS:** tuleje iglidur `[litera][SM|FM|TM|PM|UM]-d1d2-b` (np. `PSM-4550-30`; **w nazwach plików bywają podkreślniki i końcówka `_1`** — ujednolicaj separatory), wózki drylin `WJ200UM/UME/QM-01-10`, szyny `WS/WSQ/WSX/TS`, `NW/TW/TK`, `PRT-01-150-TO-AT10`, łańcuchy `E2…`. Fałszywe rodziny (nie IGUS): `DFM/DSM/HGPM` (Festo), `MGPM` (SMC), `CFM` (Elesa), `NS`, `RS`.
* **Końcówki z Inventora** (`-2`, `-3`, `1`, `jj`, pojedyncza litera) to śmieci z ręcznej numeracji — **odcinaj do poprawnego symbolu** (`WJ200UM-01-101` → `WJ200UM-01-10`); zostają tylko wykonania (`-ES`, `-AL`) i dla PRT pełny kod (`-TO-AT10`, `-TO-HTD8M`) — to są **osobne pozycje**.
* **Wybór reprezentanta:** IPT > IAM, **ale** gdy IPT jest składową IAM o tym samym kodzie (np. PRT) bierz IAM (≥2 składowe, nazwa zgodna z symbolem). IAM-opakowania z 1 częścią i złożenia projektowe → IPT. Zagnieżdżone IAM (IAM w IAM) → osobny katalog, ręcznie.
* **Description** = nazwa produktu z igus.pl w skrócie (`igus_opis.py`): `oprawa stojakowa`; UME (litera E po UM/QM = „clearance infinitely adjustable”) → `oprawa stojakowa, kasowanie luzu`; `szyna pojedyncza`, `system prowadnicy liniowej`, `tuleja ślizgowa (z kołnierzem)`, `łożysko obrotowe (z uzębieniem AT10/HTD8M)`. QM nie ma regulacji luzu wg igus.com.
* **Tuleje:** wymiary z kodu → własność użytkownika `Wymiar` = `Ø d1 × Ø d2 × b mm` (`igus_wymiar.py`) do mapowania w Subiekcie.
* **Modele z sieci (igus-cad.com):** użytkownik loguje się sam w karcie przeglądarki aplikacji. Pobieranie sterowane przez DOM (ramki są same-origin): `window.frames[3]` = ccHandler; pole długości `ccAnswer9`, format `outputformat_3d`, przycisk `btCadDownload3D`, zamknięcie okna `btDownloadDlgClose`; **sprawdzaj, że „Numer zamówienia” kończy się na `-1000`, zanim klikniesz Pobierz** (zmiana długości bywa niezauważona). Adres `ArtNr=<pełny numer>` nie działa — otwieraj typ bazowy i ustawiaj długość polem. Centrum pobierania ma **limit 20 plików**.
  ZIP: link `BinaryFileRedirector.ashx?PATH=tmp/Zip/…` w ramce `…frames[11].frames[12]` pobiera się wprost z Pythona (bez cookies). Zrzuty ekranu w tej przeglądarce często przekraczają limit czasu — stąd DOM.
* **Szyny 1 m:** typ bazowy + długość 1000 → symbol `<kod> L1000` (STEP → IPT `konwertuj_stp.py`).
* Strona wyboru dla zespołu: jak w sekcji 10 (`igus_strona.py` → `WYBOR_IGUS.html`).
* **Wózki i szyny (zasada użytkownika):** jeśli w bibliotece jest wózek, musi być **cały** (komplet, nie same części) i obok **szyna 1 m (`<kod> L1000`)** do niego. Części składowe wózka (np. `TK-04-09-1…3`) nie są pozycją — zastąp je pełnym wózkiem z igus-cad.com (`TW-04-09`) i dołóż `TS-04-09 L1000`. Kojarzenie wózek → szyna wg katalogu IGUS: `WJ…` → `WS-NN`/`WSQ-NN`, `TW-xx-yy` → `TS-xx-yy`, `NW-…-80` → `NS-01-80` (do potwierdzenia). Kody, których nie ma w igus-cad.com (np. `TS-02-20`, `NS-02-80`), nieoficjalne — nie twórz dla nich pary. Skrypt wzorcowy: `wzorce_kodu/igus_stp2.py`.
