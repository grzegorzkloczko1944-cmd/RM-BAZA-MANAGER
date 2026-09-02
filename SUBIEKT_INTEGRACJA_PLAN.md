# Integracja RM_BAZA ↔ Subiekt nexo PRO — plan

> **Status:** projekt, nic jeszcze nie zaimplementowane (stan 02.09.2026).
> Droga integracji: **Sfera dla nexo (nexo SDK)** — patrz sekcja 2.
> Warunki spełnione: Subiekt nexo **PRO** ✅, aktywny abonament ✅.
> SDK pobrane (`C:\iLogic\Subiekt_nexo_PRO_dokumentacja\SDK`), dokumentacja czytelna
> narzędziem (sekcja 9), **skrypt rozpoznawczy NexoRecon zbudowany i przetestowany**
> (sekcja 11) i **uruchomiony na żywej bazie** — wyniki i wnioski w sekcji 12.
> Następny krok to decyzja procesowa (ZD czy lista?) i dopiero potem zapis.
>
> ⚠️ **Historia błędów tego dokumentu — czytaj, zanim coś tu przepiszesz:**
> wersja z 31.08 zakładała Subiekt **GT** (Sfera COM/32-bit) — zły produkt.
> Wersja z 01.09 „poprawiła" to na REST API, twierdząc, że *„Sfera dla nexo nie
> istnieje"* — **nieprawda**, i ta poprawka kosztowała dwa ślepe tropy
> (szukanie kluczy API, aktywacja InsERT mobile). Sfera **istnieje w dwóch
> odmianach**: GT (COM) i nexo (.NET/SDK). Ta druga jest wprost wymieniona
> przez InsERT jako cecha wersji PRO i to jest właściwa droga.

## 1. Po co to — docelowy obieg (doprecyzowane 02.09.2026)

Dziś RM_BAZA prowadzi projekty i BOM-y, a magazyn żyje osobno w Subiekcie.
Skutek: zamówienia do dostawców powstają ręcznie, a informacja „co już mamy,
a co trzeba dokupić" wymaga ręcznego porównania dwóch systemów.

```
RM_BAZA: lista detali z projektu
        │
        ├─(1) MAPOWANIE: dla każdej pozycji sprawdź symbol w Subiekcie
        │       ├─ jest kartoteka  → użyj jej (id towaru do dalszych kroków)
        │       └─ brak kartoteki  → ZAŁÓŻ na żądanie (symbol=nr rysunku,
        │                            nazwa z BOM) — tylko dla tej pozycji,
        │                            nie hurtem; patrz sekcja 4
        │
        ├─(2) ZAMÓWIENIE / WYDANIE — Subiekt decyduje z magazynu:
        │       co wydać od ręki (WZ/RW), co zamówić u dostawcy
        │       ⚠️ forma zamówienia (ZD czy „lista + FZ jak dziś") to
        │       DECYZJA PROCESOWA, świadomie otwarta — patrz sekcja 12.1
        │
        └─(3) WYDANIE Z MAGAZYNU → RM_BAZA
                Subiekt potwierdza wydanie → RM_BAZA dostaje sygnał
                „dostarczono" na pozycji projektu.
```

Trzy operacje, różny profil ryzyka:

1. **Mapowanie (odczyt)** — dla listy numerów z RM_BAZA sprawdzić symbol
   w Subiekcie z normalizacją (TRIM + bez wielkości liter, sekcja 12.2 —
   rozpoznanie znalazło 16 takich przypadków). Zero ryzyka, czysty odczyt.
2. **Zakładanie brakujących kartotek (zapis, wąski zakres)** — TYLKO gdy
   symbol ma kształt poprawnego numeru rysunku (regex z sekcji 12.2).
   Pozycje o innym kształcie (rozpoznanie znalazło m.in. `Przygotowanie
   powietrza`, `Elektrozawór 5/3` wpisane w pole numeru) **NIE dostają
   kartoteki automatycznie** — trafiają na listę do ręcznego sprawdzenia,
   żeby nie zaśmiecić Subiekta. Decyzja użytkownika 02.09.2026.
3. **Wydanie z magazynu → RM_BAZA (odczyt zwrotny)** — jeszcze nierozpoznane
   technicznie, do zbadania w SDK razem z krokiem 2 (jaki dokument realnie
   potwierdza wydanie, skoro PZ/WZ/RW wygasły na rzecz FZ/FS — sekcja 12.1).
   **Decyzja 02.09.2026: DWA osobne sygnały, nie jeden.** „Wydano z magazynu"
   (mieli na stanie, WZ/RW albo ich następca) i „przyszło od dostawcy" (FZ)
   to różna informacja dla planowania — RM_BAZA ma widzieć, skąd pozycja
   się wzięła, nie tylko że jest gotowa. Do zbadania: jaki dokument/status
   w Subiekcie odpowiada każdemu z tych dwóch przypadków przy obecnym
   sposobie prowadzenia magazynu (sekcja 12.1).

⚠️ Krok (2) „zamówienie i wydanie" pozostaje decyzją procesową firmy, nie
techniczną — zapisane świadomie jako otwarte, nie jako zaległość.

## 2. Czym się łączyć — SFERA dla nexo (nexo SDK)

> ⚠️ **KOREKTA 02.09.2026 — poprzednia wersja tej sekcji była BŁĘDNA.**
> Twierdziła, że „Sfera należy do linii GT i dla nexo nie istnieje", i kierowała
> integrację na REST API (InsERT API). **Sfera dla nexo istnieje** i jest wprost
> wymieniona przez InsERT jako cecha wersji PRO. Skutki błędu i dlaczego REST API
> odpada — na końcu sekcji.

**Właściwy kanał: Sfera dla Subiekta nexo**, czyli warstwa programistyczna
opisana w **nexo SDK**. To dokładnie ta funkcja, za którą płaci się za wersję
**PRO** — zwykły Subiekt nexo jej nie ma. Cytat ze strony produktowej InsERT
(`subiekt_nexo_pro/opis.html`):

> „Sfera dla Subiekta nexo – możliwość tworzenia własnych rozwiązań
> (szczegółowy opis i dokumentacja techniczna w nexo SDK)"

⚠️ **Sfera dla nexo ≠ Sfera dla GT.** Ta sama nazwa, dwa różne mechanizmy:
GT to COM i 32-bit, nexo to .NET/SDK. Materiały o „Sferze" z sieci dotyczą
najczęściej GT — nie stosują się tutaj.

**Stan warunków wejścia (potwierdzone przez użytkownika 02.09.2026):**

| warunek | stan |
|---|---|
| Subiekt nexo **PRO** (nie zwykły nexo) | ✅ zainstalowany |
| aktywny abonament na nexo PRO | ✅ jest |
| **nexo SDK** (dokumentacja techniczna Sfery) | ⬜ do pobrania z e-Pomocy InsERT |

Nic poza tym nie jest potrzebne: **żadnego klucza API, portalu deweloperskiego
ani dokupowania czegokolwiek.**

**Zasada zostaje ta sama co dla GT, zmienia się tylko narzędzie: odczyt
najprostszą dostępną drogą, zapis wyłącznie przez Sferę.**

| operacja | kierunek | narzędzie | dlaczego |
|---|---|---|---|
| kartoteki towarów, ceny, stany | Subiekt → RM_BAZA | **Sfera / nexo SDK (odczyt)** | oficjalne, udokumentowane, bez ograniczeń bitowości |
| kontrahenci (dostawcy) | Subiekt → RM_BAZA | **Sfera / nexo SDK (odczyt)** | jw. |
| dokumenty RW / WZ / PZ | Subiekt → RM_BAZA | **Sfera / nexo SDK (odczyt)** | jw. |
| **tworzenie kartoteki towaru** | RM_BAZA → Subiekt | **Sfera / nexo SDK (zapis)** | patrz niżej |
| **zamówienia do dostawców** | RM_BAZA → Subiekt | **Sfera / nexo SDK (zapis)** | patrz niżej |

**Dlaczego zapis TYLKO przez API.** Dokument w Subiekcie to nie jeden wiersz
w tabeli — numeracja, stany magazynowe, rozrachunki i powiązania siedzą
w wielu tabelach, a część logiki jest w aplikacji, nie w bazie. Nawet gdyby
dało się dobrać bezpośrednio do bazy nexo, ręczny zapis dałby dokument, który
wygląda poprawnie do pierwszego remanentu — dokładnie ten sam problem, który
przy GT wykluczał ręczny `INSERT`. Poprawnie zapisuje się przez Sferę —
i przy GT, i przy nexo (choć to dwa różne mechanizmy o tej samej nazwie).

To samo dotyczy kartotek towarów — to nie jest jeden rekord (grupy, jednostki
miary, stawki VAT, cenniki, powiązania).

**Czego NIE robimy:** bezpośredniego SQL do bazy nexo (jak przy GT).
Sfera jest wspieranym kanałem integracji — struktura bazy nexo nie jest
publicznym kontraktem i może się zmienić między wersjami bez ostrzeżenia,
inaczej niż w GT, gdzie odczyt SQL był utrwaloną, powszechnie stosowaną
praktyką. Dotyczy to obu kierunków: **także odczytu.**

**Skąd wziąć nexo SDK — bezpośredni link (sprawdzony 02.09.2026):**

```
https://ftp.insert.com.pl/pub/demo/InsERT_nexo/nexoSDK.exe
```

466 MB, **archiwum samorozpakowujące 7-Zip** — nie instalator. Rozpakowuje się
bez instalowania czegokolwiek: `nexoSDK.exe -o"<katalog>" -y`. Pobranie nie
wymaga logowania. Pobrana wersja: **`nexoSDK_61.1.0.9431`** — zgadza się
z pakietem nexo zainstalowanym u użytkownika (sekcja 8).

📁 **SDK jest już rozpakowane i leży tutaj — pracujemy na tej kopii:**

```
C:\iLogic\Subiekt_nexo_PRO_dokumentacja\SDK
```

1198 MB, 1573 pliki, wersja `61.1.0.9431`. Pliki `.chm`/`.pdf` **odblokowane**
(`Unblock-File`) — bez tego Windows blokuje dokumentację pobraną z internetu
i `.chm` otwiera się z pustymi stronami.

⚠️ **NIE commitować do repo** (1,2 GB, ~650 plików w samym `Bin`). Reguły są już
w `.gitignore` (`nexoSDK*.exe`, `nexoSDK_*/`, `sdk/`, `*.chm`). SDK celowo leży
**poza repo**, na `C:\iLogic` — tak jak reszta materiałów pomocniczych.

**Co jest w środku — mapa, od czego zacząć:**

| plik / katalog | co to |
|---|---|
| **`InsERT.nexo.Sfera.chm`** | ⭐ **główna dokumentacja Sfery** — tu zaczynamy |
| `Dokumentacja_bazy_danych_nexo.htm` | struktura bazy (4,4 MB) — do rozumienia pól, NIE do SQL-a (patrz wyżej) |
| `InsERT.nexo.Schematy.chm` | schematy danych |
| `Przyklady/OperacjeSferyczne` | ⭐ podstawowe operacje przez Sferę |
| `Przyklady/PrzykladyKartoteki` | ⭐ kartoteki towarów — sekcja 4 („kartoteka na żądanie") |
| `Przyklady/PrzykladyRealizacjiDokumentow` | ⭐ dokumenty magazynowe (RW/WZ/PZ) |
| `Przyklady/nexoZapytanie` | odczyt danych |
| `Przyklady/SferaZdarzeniowa` | reakcja na zdarzenia w nexo |
| `Bin/` | 647 plików — biblioteki nexo do referencji |
| `ZmianyAPI_61.0.4_61.1.0.txt` | zmiany API między wersjami |

**Sfera nexo to .NET, potwierdzone:** `Bin/` to biblioteki .NET (WPF, pakiety
NuGet — `WersjePakietowNuget.txt`), a w `Narzedzia/` jest `SferaDotnetUpgrade.exe`.
Czyli z Pythona **nie** przez `win32com` (to droga GT/COM), tylko przez
`pythonnet` (`clr`) albo mały most w C#. Do rozstrzygnięcia na `InsERT.nexo.Sfera.chm`
— patrz sekcja 6.

**Dlaczego NIE REST API (InsERT API) — ślepy zaułek, sprawdzone 02.09.2026.**
Poprzednia wersja planu kierowała tam całą integrację. Powody odrzucenia:
* artykuł e-Pomocy InsERT o portalu deweloperskim (nr 10590) wymienia jako
  wspierane produkty **Gestor nexo, InsERT nexo, Subiekt 123** — **Subiekta
  nexo PRO tam nie ma**;
* w „Moje produkty" na koncie InsERT kafelek „InsERT API" **się nie pojawia**,
  mimo roli Administratora (potwierdzone: kreator InsERT mobile, który tej roli
  wymaga, przeszedł poprawnie);
* Sfera jest już opłacona w ramach PRO — REST API oznaczałoby szukanie
  (i prawdopodobnie dokupywanie) drugiej drogi do tego samego celu.

⚠️ **InsERT mobile to nie to samo co InsERT API.** Uruchomiony przy okazji
serwer e-usług obsługuje synchronizację aplikacji mobilnej — z integracją
RM_BAZA nie ma nic wspólnego. Nie szukać tam kluczy ani endpointów.

⚠️ **Easy Nexo Integrator / „Bridge"** (NT.NET, ~900 zł, własne REST API nad
nexo) — rozwiązanie trzeciej firmy, **odrzucone**: Sfera daje to samo w cenie
posiadanej już licencji PRO.

## 3. Faktury: NIE przez Subiekta

RM_BAZA ma **własnego klienta KSeF** gadającego wprost z API Ministerstwa —
[`ksef_api_client.py`](ksef_api_client.py) (`authenticate_with_token`,
`query_purchase_invoices`, `download_invoice_xml`) +
[`ksef_invoice_parser.py`](ksef_invoice_parser.py).

**Nie dublować tego przez Subiekta.** Czytanie faktur z Subiekta byłoby krokiem
wstecz: XML z KSeF ma pełną treść (pozycje, stawki, załączniki), a Subiekt trzyma
to, co sam zmapował na swój model. Dochodzi też zależność — faktura pojawiłaby się
w RM_BAZA dopiero, gdy ktoś zaimportuje ją w Subiekcie.

⚠️ Klient KSeF domyślnie celuje w **środowisko testowe**
(`BASE_URL_TEST = api-test.ksef.mf.gov.pl`). Do prawdziwych faktur trzeba
`BASE_URL_PRODUCTION` i token produkcyjny.

**Kiedy Subiekt jednak ma sens przy fakturach:** gdy potrzebne jest to, co Subiekt
do faktury dorobił — powiązanie z zamówieniem, dekretacja, rozrachunki, status
płatności. Tego w XML z KSeF nie ma, bo powstaje dopiero w systemie handlowym.

**KSeF ≠ Subiekt — to różne dane, nie duplikat:**

| źródło | co wie | czego nie wie |
|---|---|---|
| KSeF (faktura) | ile zapłacono za konkretną dostawę, kiedy, komu | ile jest **teraz** na magazynie |
| Subiekt | stan magazynowy, cena bieżąca, kartoteka | — |

Faktura to zdarzenie z przeszłości; stan magazynu to obraz na dziś. Z samych
faktur nie policzy się stanu (brak wydań, korekt, remanentów).

## 4. Kartoteki towarów — reguła „na żądanie"

**Problem:** detali jednorazowych jest dużo, ale część się powtarza — i nie da się
z góry przewidzieć, które wrócą.

**Reguła: kartotekę zakłada dopiero ZAMÓWIENIE, nie pozycja w BOM.**

```
pozycja idzie do zamówienia
   └─► RM_BAZA sprawdza po symbolu, czy kartoteka istnieje
         ├─ istnieje  → używa istniejącej (buduje się historia cen)
         └─ brak      → zakłada nową (przez Sferę)
```

Dlaczego tak:
* Subiekt nie puchnie od detali, które nigdy nie wrócą,
* pozycje powtarzalne **same się wyłaniają** — drugie zamówienie na ten sam numer
  trafia w istniejącą kartotekę i buduje historię cen,
* nie trzeba niczego przewidywać z góry: decyduje to, co faktycznie zamówiono.

**Warunek konieczny: symbol musi być STABILNY** — ten sam detal zawsze daje ten sam
symbol. Patrz sekcja 5.

**Na później (nie na start):** detal bez ruchu przez rok → oznaczyć w Subiekcie jako
nieaktywny. Kartoteka zostaje dla historii, ale nie zaśmieca list wyboru.

## 5. DO ROZSTRZYGNIĘCIA PRZED KODEM

To nie są pytania techniczne — to decyzje o tym, jak ma działać firma.
Lepiej podjąć je teraz niż po pierwszym imporcie.

- [x] **Co jest symbolem kartoteki?** Numer rysunku RM_BAZA — **rozstrzygnięte
      02.09.2026**: numery rysunków są niepowtarzalne, zmiana konstrukcyjna
      zawsze dostaje nowy numer, nigdy nie nadpisuje starego pod tym samym
      symbolem. Ryzyko z pierwotnego pytania (numer zostaje, geometria się
      zmienia) nie występuje w praktyce firmy. Numer rysunku = symbol
      kartoteki, bez dodatkowego wersjonowania/rewizji.
- [x] **Czy sufiks X/XX wchodzi w symbol?** — **rozstrzygnięte 02.09.2026**:
      sufiks jest integralną częścią numeru rysunku, więc wchodzi w symbol
      automatycznie, bez dodatkowej logiki — laser i frez na tym samym detalu
      mają różne numery, więc dostają różne kartoteki.
- [x] **Materiały (blacha, profile)** mają kartoteki w Subiekcie, ale nie mają
      numerów rysunków — **rozstrzygnięte 02.09.2026**: materiały nie wchodzą
      w zakres tej integracji, nie mapujemy ich.
- [x] **Kto jest źródłem prawdy o stanie magazynu?** — **Subiekt, potwierdzone
      02.09.2026** (stany żywe, ruszane przez FZ/FS — sekcja 12.1). Powinien być Subiekt, a RM_BAZA
      tylko go odpytuje. RM_BAZA NIE MOŻE trzymać własnej wersji stanów — rozjadą
      się (por. `rfq_portal_url`, gdzie dwa źródła tej samej prawdy rozjechały się
      przy pierwszej zmianie).
- [x] **Dostęp do integracji** — **rozstrzygnięte 02.09.2026: Sfera, w cenie
      posiadanej licencji.** Warunki wejścia spełnione: Subiekt nexo **PRO**
      zainstalowany ✅, abonament aktywny ✅. Zostaje pobrać **nexo SDK**
      z e-Pomocy InsERT (za darmo dla PRO z abonamentem).
      Nie trzeba: klucza API, portalu deweloperskiego, dokupowania.
      Szczegóły i dlaczego REST API odpada — sekcja 2.

## 6. Pułapki techniczne (Sfera dla nexo)

⚠️ Ta sekcja była pisana dwa razy pod błędne założenia — najpierw pod Sferę GT
(COM, 32-bit), potem pod REST API. **Sfera dla nexo to trzecia, właściwa
rzecz** i jej pułapki trzeba dopiero rozpoznać na SDK. Do sprawdzenia:

- **Czym to się wywołuje z Pythona — ROZSTRZYGNIĘTE 02.09.2026: most w C# (.NET 8, x64)
  uruchamiany jako proces**, nie `pythonnet`. Uzasadnienie i stan w sekcji 11.
- **Bitowość — ROZSTRZYGNIĘTE:** nexo ≥57 to wyłącznie **64-bit** (.NET 8). Python
  RM_BAZA jest 64-bit, most też — brak konfliktu.
- **Licencja przy starcie.** Sfera zwykle zajmuje licencję/sesję programu —
  sprawdzić, czy skrypt w tle nie zablokuje stanowiska pracownikowi.
- **Uprawnienia użytkownika nexo**, na którym loguje się Sfera — musi mieć
  prawo do zapisu dokumentów i zakładania kartotek.
- **Tryb testowy.** Czy da się podpiąć do kopii bazy (`Nexo_RM PRODUKCJA` —
  sekcja 8), żeby pierwsze zapisy nie poszły w produkcję.
- **Format błędów walidacji** — żeby komunikaty w RM_BAZA były czytelne,
  a nie surowym zrzutem wyjątku .NET.

## 7. Pierwszy krok

**Skrypt rozpoznawczy, nie integracja.** Podłączyć się Sferą do nexo w trybie
odczytu i wypisać, co tam jest: kartoteki towarów, kontrahenci, dokumenty
magazynowe, cenniki.

Cel podwójny: (1) potwierdzić, że mapowanie po numerze rysunku jest wykonalne
(sekcja 5), (2) zobaczyć realny kształt obiektów Sfery — potrzebny do
zaplanowania zapisu w kroku drugim.

Nic nie zapisuje, więc jest bezpieczny na produkcyjnej bazie.

**Stan 02.09.2026: ZBUDOWANY i przetestowany** — patrz sekcja 11 (NexoRecon).
Do uruchomienia na żywo brakuje tylko haseł (SQL `sa` + użytkownik nexo).

## 8. Infrastruktura — gdzie faktycznie siedzi baza (ustalone 02.09.2026)

Nie do integracji (patrz sekcja 2 — zapis/odczyt tylko przez API, nie SQL),
ale przydatne jako kontekst przy diagnozowaniu problemów ze startem programu
czy przy rozmowach ze wsparciem InsERT.

**Serwer SQL:** `192.168.100.4` — SQL Server 2022 Express (RTM-CU23), na
**Linuksie (Debian 12, kontener)**, nie na W2019S (`192.168.100.84`, tamten
serwer trzyma RM_STATS/RM_PRINT/RM_DWF/RM_RFQ — to inna maszyna).

**Bazy na tej instancji:**
| baza | rola |
|---|---|
| `Nexo_RM PRODUKCJA` | firma produkcyjna (główna) |
| `Nexo_RMPAK SPZOO` | druga firma |
| `InsERT_Launcher` | baza dystrybucyjna (aktualizacje pakietów, wersje) |

Login SQL: `sa` (SQL Server authentication, nie Windows).

**Znaleziony i celowo NIEnaprawiony problem — konflikt collation:**
instancja SQL Server ma collation `SQL_Latin1_General_CP1_CI_AS` (stąd
dziedziczy je `tempdb`), a wszystkie 3 bazy InsERT mają `Polish_CI_AS`.
Powoduje to błędy `Cannot resolve the collation conflict between
"Polish_CI_AS" and "SQL_Latin1_General_CP1_CI_AS"` przy niektórych operacjach
InsLaunchera (zaobserwowane przy starcie/sprawdzaniu aktualizacji pakietów —
program mimo to uruchomił się poprawnie). Naprawa źródłowa (ujednolicenie
collation instancji) wymaga `rebuild master` — ryzykowne na produkcyjnym
serwerze, **świadomie odłożone**, do zgłoszenia raczej do wsparcia InsERT niż
do samodzielnej naprawy. Nie wpływa na plan integracji przez API (sekcja 2) —
API nie widzi tempdb ani collation na tym poziomie.

Osobny, drobny objaw z tego samego uruchomienia: InsLauncher zgłosił brak
pliku `Windows.dll` wymaganego przez `Microsoft.Data.Sqlite` przy próbie
załadowania Sfery — dotyczy pakietu `Nexo-61.1.0.9431` lokalnie na stacji
klienckiej, nie serwera; naprawia się zwykle przez "Napraw instalację"
w Launcherze. Nieistotne dla integracji API (Sfera to mechanizm GT, patrz
sekcja 2 — nexo PRO w ogóle jej nie używa do integracji zewnętrznej).

## 9. System czytania dokumentacji Sfery (zrobione 02.09.2026)

CHM InsERT to 82 192 strony HTML — nie da się tego czytać "z ręki". Zbudowany
zestaw narzędzi (poza repo, w `C:\iLogic\Subiekt_nexo_PRO_dokumentacja\CHM\`):

| co | gdzie |
|---|---|
| CHM zdekompilowany do HTML | `C:\iLogic\Subiekt_nexo_PRO_dokumentacja\CHM\sfera\html\*.htm` (+ `schematy\`) |
| indeks tematów (breadcrumb → plik) | `C:\iLogic\Subiekt_nexo_PRO_dokumentacja\CHM\sfera_index.tsv` (81 984 wpisy) |
| budowanie indeksu z `.hhc` | `C:\iLogic\Subiekt_nexo_PRO_dokumentacja\CHM\tools\build_index.py` |
| **czytnik** | `C:\iLogic\Subiekt_nexo_PRO_dokumentacja\CHM\tools\doc.py` |

```
python doc.py tree [glebokosc]      # zarys struktury
python doc.py find <fraza>          # szukaj tematu, pokazuje plik .htm
python doc.py read "<temat|plik>"   # strona jako czysty tekst (kod C# zachowany)
```

**Pułapki, które kosztowały czas — nie powtarzać:**
* `hh.exe -decompile` **milczy i nic nie robi, gdy ścieżka ma spacje** (nawet
  w cudzysłowach). Kopiować CHM do `C:\iLogic\Subiekt_nexo_PRO_dokumentacja\CHM\Sfera.chm` i dopiero wtedy
  dekompilować. Nie sandbox, nie uprawnienia — spacje.
* `.hhc` jest w **cp1250**, a `Name` i `Local` są w **osobnych liniach**.
* W bibliotece klas są **dwie** rodziny encji o tych samych nazwach:
  `InsERT.Moria.Archiwa.*` (w `InsERT.Moria.API`) i `InsERT.Moria.ModelDanych.*`.
  Sfera pracuje na **ModelDanych** — przy sprawdzaniu pola zawsze zawężać do
  `InsERT.Moria.ModelDanych >` w breadcrumbie, inaczej trafia się np. na
  `Archiwa.Dokument.DataWystawienia`, którego w ModelDanych **nie ma**
  (tam jest `DataWprowadzenia` / `DataWydaniaWystawienia`).
* `doc.py read "<fraza>"` bierze **pierwsze** dopasowanie — dla encji podawać pełny
  breadcrumb od `InsERT.Moria.ModelDanych > `.

## 10. Ściąga API Sfery (z dokumentacji, wersja 61.1.0.9431)

**Start i logowanie** (`using InsERT.Moria.Sfera; using InsERT.Mox.Product;`):
```csharp
var dane  = DanePolaczenia.Jawne("192.168.100.4", "Nexo_RM PRODUKCJA", false, "sa", haslo); // lub (serwer, baza, true) = Windows auth
var sfera = new MenedzerPolaczen().Polacz(dane, ProductId.Subiekt);   // TYLKO Subiekt — każdy produkt = osobna licencja PRO
if (!sfera.ZalogujOperatora(loginNexo, hasloNexo)) throw ...;           // login = pole "Login" w Konfiguracja → Użytkownicy
```
Alternatywa do wdrożenia: `DanePolaczenia.Odbierz()` (parametry ze stdin od InsLaunchera).

**Menedżery** — `sfera.PodajObiektTypu<IAsortymenty>()` albo skróty (extension w `InsERT.Moria.Sfera`):
`sfera.Asortymenty()`, `sfera.Podmioty()`, `sfera.Magazyny()`, `sfera.JednostkiMiar()`,
`sfera.ZamowieniaDoDostawcow()` (ZD), `sfera.PrzyjeciaZewnetrzne()` (PZ),
`sfera.WydaniaZewnetrzne()` (WZ), `sfera.RozchodyWewnetrzne()` (RW), `sfera.Konfiguracje()`,
`sfera.StatusyDokumentow()`, `sfera.SzablonyAsortymentu()`.

**Odczyt:** `manager.Dane.Wszystkie()` → IQueryable (LINQ), `Dane.Pierwszy(x => ...)`,
`Asortymenty().Dane.WyszukajPoSymbolu("...")`, `Podmioty().Dane.WszystkieFirmy()`.

**Zapis:** `using (var bo = manager.Utworz()) { bo.Dane.X = ...; if (!bo.Zapisz()) bo.WypiszBledy(); }`;
edycja istniejącego: `manager.Znajdz(encja)`. Nowa kartoteka: **najpierw**
`bo.WypelnijNaPodstawieSzablonu(sfera.SzablonyAsortymentu().DaneDomyslne.Towar)`,
inaczej brak domyślnej jednostki miary (FAQ SDK). Dokument: `Utworz(konfiguracja)`,
np. `sfera.Konfiguracje().DaneDomyslne.ZamowienieOdKlienta`; pozycje `dok.Pozycje.Dodaj(asortyment, ilosc, jm)`.
**ZD ma dedykowaną metodę:** `IZamowieniaDoDostawcow.UtworzNaPodstawieZapotrzebowania(...)` — do zbadania w kroku 2.

**Encje (ModelDanych) istotne dla nas:**
* `Asortyment`: `Symbol`, `Nazwa`, `Rodzaj` (→ `RodzajAsortymentu.Nazwa`), `Grupa`,
  `CenaEwidencyjna`, `StanyMagazynowe` (kolekcja), `StanyWMagazynachUproszczone`.
* `StanMagazynowy`: `Magazyn`, `Asortyment`, `IloscDostepna`, `IloscZadysponowana`,
  `IloscZarezerwowanaIlosciowo`, `IloscZarezerwowanaDostawowo`. **Brak menedżera** —
  dostęp przez `Magazyn.StanyMagazynowe` / `Asortyment.StanyMagazynowe`.
* `Podmiot`: `NazwaSkrocona`, `NIP`, `Telefon`, `Kontrahent` (bool), `Aktywny`, `Firma`, `Osoba`.
* `Dokument`: `NumerWewnetrzny.PelnaSygnatura` (typ `Sygnatura`), `DataWprowadzenia`,
  `DataWydaniaWystawienia` (DateTime?), `Podmiot`, `Magazyn`, `Pozycje`, `StatusDokumentu`.
* `PozycjaDokumentu`: `AsortymentAktualny`, `Ilosc`, `JednostkaMiaryAs`
  (⚠️ `JednostkaMiaryAsortymentu.Symbol` to **metoda**, nie właściwość).

**Bezpośredni SQL** jest przez Sferę oficjalnie dostępny do **odczytu**
(`sfera.PodajPolaczenie()`, schema `ModelDanychContainer`), do zapisu InsERT
odradza wprost — zgodne z sekcją 2.

## 11. NexoRecon — skrypt rozpoznawczy: ZBUDOWANY i przetestowany (02.09.2026)

**Decyzja architektoniczna:** most w **C# (.NET 8, x64)** wywoływany z Pythona jako
proces, a nie `pythonnet`. Powody: Sfera to .NET 8 wyłącznie 64-bit;
`InsERT.Moria.Security.Core.dll` to mieszany C++/CLI wymagający `ijwhost.dll`
obok; build kopiuje 554 zależności — ładowanie tego przez pythonnet to proszenie się
o kłopoty, a gotowy przepis (`SferaConsoleApp.targets`) jest w SDK.

| | |
|---|---|
| projekt | `subiekt_sfera/NexoRecon/` (csproj + Program.cs, ~10 KB — **to** jest w repo) |
| build | `dotnet build -c Release` w katalogu projektu (dotnet SDK 10, runtime .NET 8.0.14 — jest) |
| wyjście | `subiekt_sfera/NexoRecon/bin/Release/NexoRecon.exe` + 554 pliki, 549 MB — **poza gitem** |
| konfig | `C:\RMPAK_CLIENT\.nexo_sfera.json` (wzór `subiekt_sfera/nexo_sfera.example.json`) — **poza gitem** |
| użycie | `NexoRecon.exe [konfig.json] [--symbol=NR-RYS ...] [--limit=20]` |

Robi wyłącznie odczyt: magazyny, kartoteki (liczba, rodzaje, kształt symboli,
próbki), stany per magazyn, kontrahenci, ostatnie ZD/PZ/WZ/RW z pozycjami,
oraz sprawdzenie konkretnych symboli (`--symbol=`) z ich stanami.

**Test dymny przeszedł:** z celowo błędnym hasłem SQL program załadował Sferę
61.1.0.9431 (= wersja bazy), potwierdził proces 64-bit, dotarł do
`192.168.100.4` i dostał `Login failed for user 'sa'`. Cały łańcuch
(build → ijwhost → Sfera → sieć → SQL) działa. **Brakuje tylko danych logowania.**

**Uruchomiony na żywo 02.09.2026 — działa; wyniki w sekcji 12.** Dwie literówki
w hasłach (O↔0) kosztowały godzinę — przy `Login failed` najpierw goły test SQL
(`SqlConnectionStringBuilder`), on rozdziela hasło od Sfery.

**Konfig (poza repo) wymaga:**
1. hasło SQL `sa` do `192.168.100.4` (albo `sqlWindowsAuth: true`, jeśli konto
   Windows ma dostęp — na Linuksowym SQL Serverze raczej nie);
2. login + hasło **użytkownika nexo** (Konfiguracja → Użytkownicy → pole *Login*),
   najlepiej z uprawnieniami do Subiekta; do odczytu wystarczy zwykły.

Ryzyka do sprawdzenia przy pierwszym realnym uruchomieniu (FAQ SDK): licencja PRO
Subiekta **na tej bazie** (`InvalidOperationException: Licencja zabrania...`),
oczekujące aktualizacje bazy (uruchomić Subiekta), pola własne zaawansowane v1
(wtedy `InsERT.Moria.ModelDanych.dll` z `%LOCALAPPDATA%\InsERT\Deployments\Nexo\RM PRODUKCJA...\Binaries` zamiast z SDK).

## 12. Wyniki pierwszego rozpoznania na żywej bazie (02.09.2026)

`NexoRecon.exe` uruchomiony na `Nexo_RM PRODUKCJA` jako operator `GKI` — 9 s,
wyłącznie odczyt. Liczby poniżej to stan na 02.09.2026.

### 12.1 Która baza żyje i jak prowadzony jest magazyn

| | `Nexo_RM PRODUKCJA` | `Nexo_RMPAK SPZOO` |
|---|---|---|
| kartotek asortymentu | **2745** (2599 towar, 83 usługa, 63 komplet) | 185 |
| dokumentów 2026 | **1699** (FZ 1408, FS 263, KFZ/KFS) | 436 (FL, ZK, FZ, WZ, PW, FS) |
| magazyny | `MAG` (podstawowy), `KOSZT` (pusty) | — |
| stany > 0 | 795 pozycji, zadysponowane = 0 (rezerwacje nieużywane) | — |
| użytkownik GKI | ✅ jest | ❌ **brak** (tylko `GDziedzic`, `Szef`) |

**Magazyn w RM PRODUKCJA jest prowadzony na bieżąco, ale bezpośrednio przez
faktury:** FZ 2026 mają status *„Przyjęty towar i odebrane usługi"*, FS *„Wydany
towar i wykonane usługi"*. Osobne dokumenty magazynowe wygasły: PZ ostatni
11.2023, WZ 09.2024, RW 07.2023, PW 06.2024. **ZD (zamówienia do dostawców):
0 sztuk w obu bazach — nigdy nie używane.**

Konsekwencje dla planu:
* **Sekcja 1, strzałka (3) „Subiekt → RM_BAZA: co przyszło"** = **FZ**, nie PZ.
  Menedżer: `sfera.DokumentyZakupu()` (`IDokumentyZakupu`), filtr po statusie
  ze skutkiem przyjęcia (`StatusDokumentu.SkutekMagazynowyPrzyjecia`).
* **Sekcja 5 „źródło prawdy o stanie" — potwierdzone: Subiekt.** Stany są żywe
  (FZ/FS je ruszają), więc RM_BAZA może je odpytywać bez własnej kopii.
* **Sekcja 1, strzałka (1) „RM_BAZA → ZD"** wprowadza typ dokumentu, którego
  firma **nigdy nie używała**. To zmiana procesu, nie tylko integracja — do
  decyzji, czy zamówienia mają powstawać jako ZD w Subiekcie, czy RM_BAZA ma
  tylko przygotowywać listę, a zakup dalej idzie „FZ przy dostawie".
* `SPZOO` jest poza zasięgiem Sfery na koncie GKI — jeśli ma być objęta,
  potrzebne konto w tej bazie (decyzja organizacyjna).

### 12.2 Symbole kartotek vs numery rysunków RM_BAZA

Porównanie pełnych zbiorów: 2744 symbole Subiekta vs **4425 unikalnych
numerów rysunków** z 79 projektów na `Y:\RM_BAZA\projects` (`work_drawing_no`
> `norm_drawing_no` > `src_drawing_no`).

| | |
|---|---|
| numerów RM_BAZA **z kartoteką** w Subiekcie | **135** (119 dokładnie + 16 po normalizacji spacji/wielkości) — **3 %** |
| numerów RM_BAZA **bez kartoteki** | 4290 |
| symboli Subiekta o kształcie numeru rysunku (`NNN-NNN.NN[X]`, `NNNN-NNN.NN[X]`, `AAnnn-nnn.nn`) | **891 z 2744** |

**Oba systemy używają tego samego formatu numeru** (`013-100.22X`,
`2559-666.02X`, `ZP159-100.05X`) — mapowanie 1:1 po symbolu jest wykonalne
i sensowne, sufiks X/XX wchodzi w symbol (zgodnie z sekcją 5).

**Części powtarzalne istnieją i NIE mają kartotek** — dokładnie przypadek,
dla którego jest reguła „kartoteka na żądanie" (sekcja 4): `013-100.22X`
w 15 projektach, `013-100.20X` w 12, `027-100.00Z` w 11, `EWTR-820.*` w 6–8.
Przy pierwszym zamówieniu przez RM_BAZA dostaną kartotekę i od tej pory
zbudują historię cen.

**Jakość danych do ogarnięcia przed zapisem (obie strony):**
* Subiekt: 16 dopasowań tylko po normalizacji — np. `'8025354 '` (spacja na
  końcu), `'624 ZZ'` vs `624ZZ`, `011-100.39A` vs `011-100.39a`. Przy szukaniu
  kartoteki porównywać `TRIM` + bez rozróżniania wielkości; przy zakładaniu —
  zapisywać numer dokładnie jak w RM_BAZA.
* Subiekt: 9 symboli 1-znakowych, 90 dwucyfrowych (`10`, `28`…), 1 kartoteka
  z pustą nazwą — śmieci historyczne, nie dotykać, ale nie mapować.
* RM_BAZA: w polu numeru rysunku bywają nazwy (`Przygotowanie powietrza`
  w 3 projektach, `Elektrozawór 5/3`, `Obejma`) — takie pozycje nie mogą
  dostać kartoteki po „numerze"; filtr kształtu numeru przed wysyłką.
* `cenaEwid=0` na sprawdzanych kartotekach — ceny ewidencyjne nieprowadzone;
  historia cen będzie się budować dopiero z FZ/ZD tworzonych przez integrację.

**Skalowanie — czy 8 s z rozpoznania to problem, gdy Subiekt urośnie? Nie.**
Te 8 s to tryb rozpoznawczy (`Asortymenty().Dane.Wszystkie()` — ściąga
i grupuje CAŁĄ tabelę, `Program.cs`), używany jednorazowo do zwiedzenia bazy.
Docelowy tryb produkcyjny to **`stan`** (`Stan.cs`, patrz sekcja 11): dla listy
symboli z RM_BAZA robi punktowe `WyszukajPoSymbolu(s)` — wyszukanie po indeksie,
nie przegląd tabeli. Koszt zależy od **liczby symboli, które podajemy**
(rozmiar projektu w RM_BAZA, dziś ~300), praktycznie NIE od tego, ile kartotek
ma Subiekt. Różnica między 3 tys. a 30 tys. pozycji w Subiekcie będzie
niezauważalna, bo i tak pytamy punktowo o konkretne numery.

⚠️ Jedyne miejsce, gdzie skalowanie zależy od TEGO, co piszemy, nie od
Subiekta: zakładanie kartotek (krok 2 zapisu) rób pojedynczo, symbol po
symbolu, z potwierdzeniem — nie masową pętlą bez limitu w jednej transakcji.

**⚠️ NIEZMIERZONE — do sprawdzenia w firmie, zanim zacznie się optymalizować:**
tryb `stan` z pełną listą ~300 symboli projektu jeszcze nie był uruchomiony
(rozpoznanie w sekcji 12 użyło trybu ogólnego, nie `stan`). Szacunek z rozmowy
(300 × pojedyncze `WyszukajPoSymbolu`) to rząd **15–30 s** — ale to zgadywanie,
nie pomiar, i dotyczy INNEJ operacji niż 8 s rozpoznania (punktowe szukanie
300 numerów ≠ przegląd całej tabeli 2745 kartotek — nie są bezpośrednio
porównywalne, mimo że 15–30 s "brzmi" na więcej niż 8 s).

Zmierzyć realnie:
```
NexoRecon.exe stan --symbols-file=lista_300.txt --out=wynik.json
```
Dopiero jeśli realny czas okaże się za wolny przy codziennym użyciu (nie sam
fakt, że jest dłuższy niż 8 s) — sprawdzić w SDK, czy Sfera ma odpowiednik
zapytania wsadowego (`symbol IN (...)` na całej liście naraz) zamiast pętli
300 pojedynczych wywołań. To ścięłoby narzut mnożony przez 300 do jednego
zapytania. Nie komplikować kodu z góry bez pomiaru.

**⚠️ NIEUSTALONE — częstotliwość użycia i cache (pytanie zadane 02.09.2026,
świadomie odłożone „do ustalenia w firmie", nie rozstrzygnięte na wyrost).**
Czas 15–30 s ma sens tylko w kontekście tego, JAK CZĘSTO RM_BAZA będzie o to
pytać:
* raz przy otwarciu projektu → 15–30 s jednorazowo jest do przyjęcia bez cache,
* przy każdym otwarciu okna „stan magazynowy” / „wyślij do Subiekta” → 15–30 s
  za każdym razem jest zbyt wolne, cache staje się koniecznością.

**Jeśli cache — to NIE jeden mechanizm dla wszystkiego.** Zastrzeżenie
użytkownika: *„cache trzymać może nieaktualne dane”* — realne ryzyko przy
stanach magazynowych (user widzi „15 szt. dostępne”, klika zamówienie, a ktoś
inny w międzyczasie je wydał). Dwa rodzaje danych mają różny profil starzenia
się, więc prawdopodobnie różną politykę cache:
* **mapowanie symbol → istnieje/nie istnieje kartoteka** — zmienia się rzadko
  (tylko gdy ktoś świadomie zakłada nową), bezpieczny kandydat do dłuższego
  cache;
* **stan magazynowy (ilość dostępna)** — zmienia się przy każdej fakturze,
  ryzykowny do cache'owania bez jawnego znacznika wieku.

Do rozstrzygnięcia w firmie, PO zmierzeniu realnego czasu i zobaczeniu, jak
często dane faktycznie się zmieniają w praktyce: czy w ogóle cache'ować stany,
a jeśli tak — jak pokazać userowi wiek danych (np. „stan z 14:32” + przycisk
Odśwież), żeby nie działał na liczbach, którym nie może ufać.

**Utarty wzorzec z integracji ERP — punkt wyjścia do dyskusji, nie gotowa
decyzja:** rozdział nie po TYPIE danych, tylko po TYPIE operacji.
* **Przeglądanie/planowanie** → cache normalny, zawsze ze znacznikiem czasu
  odczytu i przyciskiem odśwież. User widzi „stan z 14:32” i sam ocenia,
  czy ufać liczbie — jak saldo w aplikacji bankowej.
* **Operacja ze skutkiem (zamówienie, rezerwacja, zapis)** → „weryfikacja na
  końcu”: user działa na cache'owanym widoku, ale w momencie kliknięcia
  „zamów”/„zapisz” system pyta Subiekta na ŻYWO o tę JEDNĄ pozycję, tuż przed
  zapisem. Jeśli stan się nie zgadza z tym, co user widział — komunikat
  „stan się zmienił, sprawdź ponownie”, nigdy cichy zapis na starych danych.

To eliminuje ryzyko zapisu na nieaktualnych danych bez wymogu, żeby całe
przeglądanie było wolne (przeglądanie nie ma nieodwracalnego skutku, zapis ma).

### 12.3 Co dalej (krok 2 — zapis)

1. **Decyzja procesowa** (właściciel: firma): ZD w Subiekcie czy tylko lista?
2. Most rozszerzyć o tryb `--json` (wyjście maszynowe dla Pythona) i komendy:
   `stan <symbol...>`, `kartoteka-utworz`, `zd-utworz` — każda osobno testowana
   na **kopii bazy** (sekcja 6: tryb testowy), nie na produkcji.
3. `IZamowieniaDoDostawcow.UtworzNaPodstawieZapotrzebowania` — sprawdzić
   w SDK, czy pasuje do „listy zamówień z projektu" (może oszczędzić ręcznego
   budowania pozycji).
4. Kartoteka na żądanie: `WypelnijNaPodstawieSzablonu(DaneDomyslne.Towar)`
   + `Symbol` = numer rysunku + `Nazwa` z BOM + jednostka `szt`.
