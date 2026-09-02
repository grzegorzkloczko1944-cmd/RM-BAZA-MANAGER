# Integracja RM_BAZA ↔ Subiekt nexo PRO — plan

> **Status:** integracja produkcyjna jeszcze niezaimplementowana (stan 02.09.2026); rozpoznanie Sfery i NexoRecon już działa na żywej bazie.
> Droga integracji z Subiektem: **RM_BAZA → Sfera dla nexo (nexo SDK)** — patrz sekcja 2.
> **Granica architektury na teraz:** RM_RFQ **nie łączy się bezpośrednio z Subiektem i nie wysyła zamówień do dostawców**.
> RM_BAZA przekazuje do RM_RFQ pozycje do ofertowania, kooperanci odpowiadają przez RM_RFQ,
> a po zakończeniu RFQ **RM_RFQ zwraca wynik ofertowania do RM_BAZA**. Dopiero RM_BAZA,
> uwzględniając wynik RFQ, tworzy i wysyła właściwe zamówienie do dostawcy oraz wykonuje
> mapowanie kartotek i ewentualny zapis do Subiekta.
> Warunki spełnione: Subiekt nexo **PRO** ✅, aktywny abonament ✅.
> SDK pobrane (`C:\iLogic\Subiekt_nexo_PRO_dokumentacja\SDK`), dokumentacja czytelna
> narzędziem (sekcja 9), **skrypt rozpoznawczy NexoRecon zbudowany i przetestowany**
> (sekcja 11) i **uruchomiony na żywej bazie** — wyniki i wnioski w sekcji 12.
> Proces od strony usera zaprojektowany — sekcja 13 (wzorowany na oknie
> „Wyślij do RFQ"). Otwarte: decyzja procesowa (ZD czy lista?) oraz **jak
> zabezpieczyć stan magazynowy przed dwoma projektami rezerwującymi te same
> sztuki naraz** (sekcja 5, `zadysponowane = 0` — firma dziś nie rezerwuje).
>
> ⚠️ **Historia błędów tego dokumentu — czytaj, zanim coś tu przepiszesz:**
> wersja z 31.08 zakładała Subiekt **GT** (Sfera COM/32-bit) — zły produkt.
> Wersja z 01.09 „poprawiła" to na REST API, twierdząc, że *„Sfera dla nexo nie
> istnieje"* — **nieprawda**, i ta poprawka kosztowała dwa ślepe tropy
> (szukanie kluczy API, aktywacja InsERT mobile). Sfera **istnieje w dwóch
> odmianach**: GT (COM) i nexo (.NET/SDK). Ta druga jest wprost wymieniona
> przez InsERT jako cecha wersji PRO i to jest właściwa droga.

## 1. Po co to — docelowy obieg (doprecyzowane 02.09.2026, routing RM_RFQ → RM_BAZA)

Dziś RM_BAZA prowadzi projekty i BOM-y, RM_RFQ obsługuje zapytania ofertowe,
a magazyn żyje osobno w Subiekcie. Docelowo te trzy elementy mają się połączyć,
ale **RM_BAZA pozostaje jedyną bramą do Subiekta**.

```
RM_BAZA: lista detali z projektu / BOM
        │
        ├─(1) SPRAWDŹ SUBIEKT: mapowanie symbolu + aktualny stan magazynu
        │       ├─ jest kartoteka  → użyj jej
        │       └─ brak kartoteki  → oznacz „do założenia" (kartoteka powstaje
        │                            dopiero przy realnym zamówieniu; sekcja 4)
        │
        ├─(2) ROZLICZ POTRZEBĘ:
        │       potrzeba / dostępne / ze stanu / do kupienia
        │
        ├─(3A) ZE STANU
        │       └─ RM_BAZA → Subiekt: rezerwacja/zadysponowanie albo wydanie
        │          (dokładny mechanizm do rozstrzygnięcia; patrz sekcja 5)
        │
        └─(3B) DO KUPIENIA
                ├─ z RFQ:
                │    RM_BAZA → RM_RFQ: pozycje do wyceny
                │    RM_RFQ → kooperanci: zapytania ofertowe
                │    kooperanci → RM_RFQ: oferty / terminy / odmowy
                │    RM_RFQ → RM_BAZA: wynik RFQ
                │
                └─ bez RFQ:
                     RM_BAZA: dostawca + ilość + termin + cena opcjonalna

                RM_BAZA, uwzględniając wynik RFQ albo dane bezpośrednie,
                tworzy i wysyła właściwe ZAMÓWIENIE do dostawcy
                              │
                              └─ RM_BAZA → Subiekt przez Sferę
                                 (kartoteka na żądanie + opcjonalnie ZD)

Subiekt → RM_BAZA:
    • stan magazynowy — odczyt na żywo / cache ze znacznikiem czasu,
    • przyjęcie od dostawcy — FZ,
    • wydanie ze stanu — dokument/status magazynowy do rozpoznania.
```

**Ważna granica odpowiedzialności:**

* **RM_RFQ** zna RFQ, zaproszenia, odpowiedzi kooperantów, oferty, ceny/terminy
  oraz wynik/rozstrzygnięcie ofertowania. **Nie tworzy i nie wysyła właściwego
  zamówienia do dostawcy**, nie zna Sfery, nie zakłada kartotek i nie tworzy
  dokumentów w Subiekcie.
* **RM_BAZA** scala BOM/projekt z wynikiem z RM_RFQ, na tej podstawie tworzy
  i wysyła właściwe zamówienie do dostawcy, zna mapowanie na kartoteki Subiekta
  i jako jedyna warstwa woła most C#/Sferę.
* **Subiekt** pozostaje źródłem prawdy o stanie magazynu i dokumentach
  magazynowo-handlowych.

Operacje mają różny profil ryzyka:

1. **Mapowanie i stan (odczyt)** — dla listy numerów z RM_BAZA sprawdzić symbol
   w Subiekcie z normalizacją (TRIM + bez wielkości liter, sekcja 12.2 —
   rozpoznanie znalazło 16 takich przypadków). Zero ryzyka, czysty odczyt.
2. **Zakładanie brakujących kartotek (zapis, wąski zakres)** — dopiero gdy
   pozycja naprawdę idzie do zamówienia i TYLKO gdy symbol ma kształt poprawnego
   numeru rysunku (regex z sekcji 12.2). Pozycje o innym kształcie
   (`Przygotowanie powietrza`, `Elektrozawór 5/3` itd.) nie dostają kartoteki
   automatycznie.
3. **Zamówienie** — właściwe zamówienie zawsze tworzy i wysyła **RM_BAZA**.
   Jeśli potrzebna była wycena, RM_RFQ zwraca do RM_BAZA **wynik RFQ**
   (kooperant/oferta/cena/termin), a RM_BAZA uwzględnia ten wynik przy tworzeniu
   zamówienia. Przy zakupie bez RFQ RM_BAZA tworzy zamówienie bezpośrednio.
   Forma w Subiekcie (ZD czy bez ZD i dopiero FZ przy dostawie) pozostaje
   decyzją procesową firmy — sekcja 12.1.
4. **Sygnał zwrotny Subiekt → RM_BAZA** — rozróżniamy co najmniej:
   „wydano ze stanu", „zamówiono u dostawcy" oraz „przyszło od dostawcy".
   FZ oznacza **przyjęcie od dostawcy**, nie samo złożenie zamówienia.

⚠️ Forma dokumentu zamówienia w Subiekcie (ZD czy obecny proces bez ZD) pozostaje
decyzją procesową firmy, nie techniczną. Pełny przepływ zakupowy jest taki:
**RM_BAZA → RM_RFQ → kooperanci → RM_RFQ → RM_BAZA → zamówienie do dostawcy**.
Integracja z Subiektem zawsze idzie osobnym kanałem **RM_BAZA ↔ Subiekt**;
nigdy RM_RFQ → Subiekt bezpośrednio.

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

**Kto wywołuje Sferę:** wyłącznie **RM_BAZA / most C# uruchamiany przez RM_BAZA**.
RM_RFQ komunikuje się z RM_BAZA swoim dotychczasowym mechanizmem synchronizacji
i zwraca **wynik ofertowania** do RM_BAZA; nie wysyła zamówienia do dostawcy,
nie dostaje połączenia ani danych logowania do Subiekta.

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
| **nexo SDK** (dokumentacja techniczna Sfery) | ✅ pobrane, rozpakowane i użyte do NexoRecon |

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

Poza tabelą Sfery istnieje osobny kanał aplikacyjny:
**RM_RFQ → RM_BAZA** — zwrot wyniku/rozstrzygnięcia ofertowania. To nie jest
integracja z Subiektem ani wysłanie zamówienia. Dopiero RM_BAZA na podstawie
tych danych tworzy właściwe zamówienie i wykonuje operacje z tabeli wyżej.

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
Czyli z Pythona **nie** przez `win32com` (to droga GT/COM). **Rozstrzygnięte
02.09.2026: most w C# (.NET 8, x64) uruchamiany jako osobny proces, NIE
`pythonnet`** — uzasadnienie (mieszany C++/CLI, `ijwhost.dll`, 554 zależności)
i stan (NexoRecon zbudowany i działa na żywej bazie) w sekcji 11.

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
- [ ] **Jak zabezpieczamy stan magazynowy dla projektu?** — **DO ROZSTRZYGNIĘCIA.**
      Rozpoznanie pokazało `zadysponowane = 0`, czyli firma nie używa dziś
      rezerwacji. Sam odczyt „dostępne 10 szt." nie wystarcza: dwa projekty mogą
      równocześnie uznać te same 10 szt. za swoje. Przy zatwierdzeniu zapotrzebowania
      trzeba więc albo zadysponować/rezerwować ilość w Subiekcie, albo od razu
      wykonać właściwe wydanie na projekt. Nie tworzyć osobnej „rezerwacji" tylko
      w RM_BAZA, bo wtedy przestałby obowiązywać Subiekt jako źródło prawdy.
- [x] **Dostęp do integracji** — **rozstrzygnięte 02.09.2026: Sfera, w cenie
      posiadanej licencji.** Warunki wejścia spełnione: Subiekt nexo **PRO**
      zainstalowany ✅, abonament aktywny ✅, **nexo SDK pobrane, rozpakowane
      i użyte do NexoRecon** ✅ — warunek spełniony, nic nie zostaje do pobrania.
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

**Stan 02.09.2026: uruchomione na żywej bazie, odczyt działa** — patrz sekcja 11
(NexoRecon) i sekcja 12 (wyniki rozpoznania na `Nexo_RM PRODUKCJA`). Następny
krok: komendy produkcyjne (`stan`, `--json`) i test zapisu na kopii bazy —
sekcja 12.3.

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
załadowania pakietu nexo/Sfery — dotyczy pakietu `Nexo-61.1.0.9431` lokalnie
na stacji klienckiej, nie serwera; naprawia się zwykle przez „Napraw instalację"
w Launcherze. Nie zmienia to architektury integracji: właściwym kanałem jest
**Sfera dla nexo (.NET/SDK)**, wywoływana przez most C# opisany w sekcji 11.

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
(build → ijwhost → Sfera → sieć → SQL) działa. Na tym etapie brakowało jeszcze
poprawnych danych logowania; późniejsze uruchomienie na żywej bazie zakończyło
się sukcesem — patrz niżej.

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
* **„Przyszło od dostawcy" = FZ**, nie PZ. Menedżer:
  `sfera.DokumentyZakupu()` (`IDokumentyZakupu`), filtr po statusie ze skutkiem
  przyjęcia (`StatusDokumentu.SkutekMagazynowyPrzyjecia`).
* **Źródło prawdy o stanie = Subiekt.** Stany są żywe (FZ/FS je ruszają), więc
  RM_BAZA może je odpytywać bez utrzymywania drugiej, niezależnej wersji stanu.
* **ZD nadal jest decyzją procesową.** Firma nigdy go nie używała, więc jego
  wprowadzenie byłoby zmianą procesu. Jeśli zostanie przyjęte, ZD tworzy
  **RM_BAZA przez Sferę** — zarówno dla zamówień bezpośrednich, jak i dla
  zamówień utworzonych przez RM_BAZA na podstawie wyniku RFQ. RM_RFQ nie tworzy ZD.
* Bez ZD stan „zamówione u dostawcy" istnieje w RM_BAZA na podstawie właściwego
  zamówienia utworzonego i wysłanego przez RM_BAZA, a **FZ dopiero potwierdza,
  że towar faktycznie przyszedł**.
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

1. **Decyzja procesowa** (właściciel: firma): ZD w Subiekcie czy zachowanie
   obecnego procesu bez ZD. Ta decyzja nie zmienia podziału odpowiedzialności:
   **RM_BAZA wysyła pozycje do RFQ → RM_RFQ zbiera odpowiedzi → wynik wraca
   do RM_BAZA → RM_BAZA tworzy i wysyła zamówienie do dostawcy**, a z Subiektem
   komunikuje się wyłącznie RM_BAZA.
2. Most rozszerzyć o tryb `--json` (wyjście maszynowe dla Pythona) i komendy:
   `stan <symbol...>`, `kartoteka-utworz`, a jeśli zapadnie decyzja o ZD —
   `zd-utworz`. Każdą komendę testować osobno na **kopii bazy** (sekcja 6),
   nie na produkcji.
3. Zdefiniować kontrakt **RM_RFQ → RM_BAZA dla wyniku ofertowania**, nie dla
   zamówienia. Co najmniej: `rfq_id`, `rfq_item_id`, `offer_id`, `supplier_id`,
   `drawing_number`, `quantity`, zaoferowana cena (opcjonalna), waluta,
   `lead_time_days` / zaoferowany termin oraz status rozstrzygnięcia.
   Po odebraniu wyniku **RM_BAZA tworzy własne zamówienie**, nadaje `order_number`,
   zapisuje `order_date`, wylicza `pickup_date` i dopiero potem wykonuje mapowanie
   do kartoteki Subiekta.
4. `IZamowieniaDoDostawcow.UtworzNaPodstawieZapotrzebowania` — sprawdzić
   w SDK, czy pasuje do dokumentu budowanego przez RM_BAZA z **własnego zamówienia**
   (utworzonego na podstawie wyniku RFQ albo bezpośrednio bez RFQ).
5. Kartoteka na żądanie: `WypelnijNaPodstawieSzablonu(DaneDomyslne.Towar)`
   + `Symbol` = numer rysunku + `Nazwa` z BOM + jednostka `szt`.

## 13. Proces od strony użytkownika RM_BAZA (zaprojektowane 02.09.2026)

Wzorowane na istniejącym oknie **„Wyślij do RFQ"** (`_open_rfq_send_dialog`,
`RM_BAZA_v15_MAG_STATS_ORG.py:24440`) — ten sam kształt: zaznaczenie w arkuszu,
okno modalne z listą i checkboxami, wysyłka. Nie wymyślamy nowego wzorca UX,
tylko powielamy sprawdzony. Decyzje 02.09.2026: **cały BOM projektu na raz**
(nie filtrowanie z góry), **jedno okno, dwie sekcje** (nie osobne kroki).

### Krok 1 — start: zaznaczenie w arkuszu

User zaznacza wiersze BOM-u (albo całe zaznaczenie, jak dziś przy RFQ) →
PPM → **„Sprawdź w Subiekcie"**. Lista ~300 pozycji, ale można wywołać też
dla mniejszego zaznaczenia — mechanizm ten sam niezależnie od liczby.

### Krok 2 — okno: mapowanie w tle, dwie sekcje na wyniku

Okno otwiera się od razu (jak przy RFQ — `dlg = tk.Toplevel(self)`), a
zapytanie do Subiekta (`NexoRecon.exe stan --symbols-file=...`) leci w
**osobnym wątku**, żeby GUI się nie zamroziło — ten sam wzorzec co
`_start_rfq_freshness_thread` przy sprawdzaniu świeżości rysunków RFQ.
Podczas ładowania: spinner/pasek postępu (jak „Szukam plików… X/Y” w oknie
wysyłki RFQ).

Po powrocie wyniku — **jedno okno, dwie sekcje**, bez osobnych kroków do
potwierdzania:

```
┌─ Sprawdzenie w Subiekcie — projekt 2627 (300 pozycji) ──────┐
│                                                                │
│ ✅ MAJĄ KARTOTEKĘ (287)                          [zwiń/rozwiń] │
│   ☑ 013-100.22X  Tuleja   potrzeba 20 | dostępne 12 | kupić 8 │
│   ☑ 013-100.20X  Płyta    potrzeba  5 | dostępne 20 | kupić 0 │
│   ...                                                          │
│                                                                │
│ ⚠️ BRAK KARTOTEKI — do założenia (11)                          │
│   ☑ 2609-450.42   Tuleja formatów X       (nowa pozycja)      │
│   ...                                                          │
│                                                                │
│ 🔴 NIE DA SIĘ DOPASOWAĆ (2)          [pokaż listę / pomiń]    │
│   „Przygotowanie powietrza” — brak kształtu numeru rysunku    │
│                                                                │
│ [Odznacz wszystkie] [Szukaj podobnych w Subiekcie] [Dalej →] │
└────────────────────────────────────────────────────────────┘
```

„Szukaj podobnych w Subiekcie” działa na zaznaczeniu (patrz krok 2b niżej) —
przydatne zwłaszcza dla pozycji z sekcji „nie da się dopasować” i „brak
kartoteki”, zanim klikniesz „Dalej” i założysz coś, co już istnieje pod inną
nazwą.

Dla pozycji z kartoteką wynik powinien od razu policzyć cztery wartości:
**potrzeba**, **dostępne**, **ze stanu** i **kupić**. To nie jest jeszcze
rezerwacja — to plan. Przed operacją ze skutkiem RM_BAZA ponownie sprawdza
stan na żywo, a po zatwierdzeniu musi go zabezpieczyć w Subiekcie zgodnie
z decyzją z sekcji 5 (rezerwacja/zadysponowanie albo wydanie).

* **„MAJĄ KARTOTEKĘ”** — czysty odczyt, checkbox zaznaczony domyślnie:
  te pozycje idą dalej do zamówienia/wydania bez zmian w Subiekcie.
* **„BRAK KARTOTEKI”** — checkbox zaznaczony domyślnie, ale zaznaczenie tu
  oznacza tylko „weź tę pozycję dalej", **nie zakłada niczego w Subiekcie**.
  Klik w „Dalej” niczego nie zapisuje — pozycja zostaje oznaczona jako
  „do założenia" i idzie do kroku 3 (RFQ / zamówienie bezpośrednie). Kartoteka
  powstaje dopiero, gdy pozycja faktycznie trafi do zamówienia — po powrocie
  z RFQ albo przy „Zamów bez RFQ" (zgodnie z regułą „na żądanie" z sekcji 4;
  zapis wtedy i tak leci pojedynczo, symbol po symbolu, patrz sekcja 12.2).
* **„NIE DA SIĘ DOPASOWAĆ”** — pozycje bez kształtu numeru rysunku (regex
  z sekcji 12.2). Odznaczone i wyszarzone: NIE wchodzą automatycznie do
  zapisu (decyzja użytkownika 02.09.2026, patrz sekcja 1 pkt 2). User widzi
  listę i może je pominąć albo poprawić numer w RM_BAZA i spróbować ponownie
  — ale kliknięcie „Dalej” nigdy nie zakłada kartoteki dla tej grupy po cichu.

### Krok 2b — szukanie po podobnej nazwie (na żądanie, przycisk na zaznaczeniu)

**Decyzje 02.09.2026.** Problem: część detali może już mieć kartotekę
w Subiekcie pod **innym symbolem albo bez symbolu-numeru** (np. założona
ręcznie kiedyś, zanim istniała reguła „symbol = numer rysunku") — dopasowanie
1:1 po symbolu (krok 2) tego nie wyłapie i pchnie prosto do „załóż nową”,
tworząc duplikat kartoteki dla tego samego fizycznego detalu.

**SDK nie ma zapytania „podobna nazwa” po stronie Sfery** — jest tylko
`WyszukajPoSymbolu` (dokładne trafienie) i `Wszystkie()` (pełna lista,
patrz sekcja 10/`Program.cs:110`). Dopasowanie fuzzy musi więc działać
**lokalnie**, na ściągniętej liście asortymentu, nie jako kolejne zapytanie
do bazy — stąd oddzielenie od kroku 2 (który jest szybkim odczytem
punktowym) i osobny przycisk, nie automat.

* **Jeden wspólny przycisk pod listą** (nie osobny przy każdym wierszu) —
  **„Szukaj podobnych w Subiekcie”**, działa na zaznaczeniu: jedna zaznaczona
  pozycja albo wiele naraz, tak samo jak checkboxy w reszcie okna sterują
  „Załóż zaznaczone”. Dostępne dla KAŻDEJ sekcji (nie tylko „brak kartoteki”)
  — user sam decyduje, kiedy sprawdzić duplikat pod inną nazwą/symbolem;
  nie zaśmieca domyślnego widoku okna, bo trzeba go świadomie kliknąć.
  Dla wielu zaznaczonych pozycji naraz: wynik pokazuje się per pozycja
  (każda dostaje własną listę top-N kandydatów), jedno przejście przez listę
  asortymentu w pamięci starcza dla całego zaznaczenia — nie trzeba ściągać
  jej ponownie za każdym razem.
* **Algorytm:** dopasowanie tekstowe (fuzzy match) pola `Nazwa` — np. część
  wspólna słów / odległość Levenshteina — na liście asortymentu ściągniętej
  raz do pamięci (koszt ~8 s, jak w rozpoznaniu sekcji 12, ale JEDNORAZOWO
  na sesję okna, nie per pozycja). Top-N (3–5) najbardziej podobnych do
  wyboru, plus zawsze opcja „żadna z tych, załóż nową”.
* **Wynik wyboru:** jeśli user wskaże istniejącą kartotekę — pozycja
  przechodzi z „brak kartoteki” do „ma kartotekę” z tym symbolem (jak trafienie
  w kroku 2), zamiast zakładać nową.

**Zapamiętanie skojarzenia — gdzie i jak (rozstrzygnięte 02.09.2026, częściowo).**

⚠️ **Nie nadpisywać nazwy/opisu detalu w RM_BAZA danymi z Subiekta.** Pytanie
padło w rozmowie — odrzucone, bo łamie kierunek prawdy z sekcji 1/12.1: dane
konstrukcyjne (nazwa, opis z BOM) mają źródło prawdy w RM_BAZA, tak samo jak
Subiekt jest źródłem prawdy TYLKO dla stanów magazynowych. Nadpisanie
odwróciłoby to tam, gdzie nie powinno być odwrócone.

Zamiast tego: **globalna tabela mapowań w warstwie RM_BAZA** (nie w SQLite
konkretnego projektu i nie w kolumnie BOM). To metadana integracji, która ma
działać między projektami: jeśli `013-100.22X` został raz ręcznie połączony
z kartoteką Subiekta, następny projekt powinien znać to skojarzenie od razu.
Kolumny co najmniej: numer rysunku, ID/symbol Subiekta, sposób trafienia
(automat po symbolu / ręczny wybór fuzzy), kto i kiedy wybrał. Konkretne
miejsce przechowywania (np. centralna baza RM_BAZA albo osobny plik integracji)
do ustalenia, ale **nie per projekt**. Krok 2 sprawdza najpierw tę tabelę,
dopiero potem `WyszukajPoSymbolu`.

**Dlaczego to nie zwalnia kroku 2, tylko go przyspiesza (pytanie z rozmowy:
"czy SQLite da taką samą prędkość jak SQL Subiekta?").** Błędne porównanie —
to dwie różne operacje w łańcuchu, nie konkurenci. Krok 2 dla każdego numeru
najpierw sprawdza tabelę mapowań (`SELECT ... WHERE numer_rysunku = ?` na
lokalnym pliku, z indeksem: mikrosekundy, zero sieci) i **tylko przy braku
trafienia** leci do Sfery/SQL Subiekta przez sieć (to jest ten wolniejszy,
mierzony krok — sekcja 12.2 wyżej, 15–30 s dla 300 wywołań). Im więcej
trafień w tabeli mapowań, tym mniej zapytań sieciowych do Subiekta w ogóle —
lokalna baza działa jak warstwa filtrująca przed kosztowną operacją, nie jak
jej zamiennik. Nie trzeba więc, żeby ona "dogoniła" prędkość Sfery — role
w łańcuchu są różne.

⚠️ **Problem zgłoszony w rozmowie, jeszcze nierozwiązany: sama tabela w bazie
nie wystarczy — user patrzący na arkusz BOM musi WIDZIEĆ, że pozycja została
dopasowana, i to jak.** Trzy stany do rozróżnienia wizualnie (analogicznie do
kolumny WYCENA z integracji RFQ, która ma różne kolory/prefiksy dla różnych
stanów): dopasowanie automatyczne po symbolu (pewne) vs dopasowanie ręczne
przez fuzzy match (decyzja człowieka, mogła być pomyłka, może wymagać
weryfikacji) vs brak dopasowania. **Konkretny wygląd (kolumna w arkuszu?
kolor? klik pokazujący szczegóły?) świadomie NIEZAPROJEKTOWANY — do ustalenia
w firmie**, patrząc na realny arkusz, nie w ciemno.

⚠️ **Szczegóły algorytmu dopasowania (próg podobieństwa, biblioteka)
NIEUSTALONE** — do dobrania w firmie, mając pod ręką realne przykłady nazw
z obu systemów (dziś widziane różnice to głównie normalizacja pisowni,
patrz sekcja 12.2, nie parafrazy nazw — trzeba sprawdzić, czy fuzzy match
w ogóle jest tu problemem wartym rozwiązania, czy normalizacja wystarczy).

### Krok 3 — co zrobić z ilością „KUPIĆ"

Po policzeniu `kupić > 0` użytkownik ma dwie ścieżki. **RM_RFQ służy wyłącznie
do zebrania i rozstrzygnięcia ofert. Właściwe zamówienie do dostawcy zawsze
tworzy i wysyła RM_BAZA.**

```
KUPIĆ > 0
   │
   ├─► 4A. ZAMÓW BEZ RFQ
   │      RM_BAZA: wybór dostawcy + ilość + termin
   │      cena: znana / uzgodniona / nieznana („wg faktury")
   │      │
   │      └──────────────────────────────────────┐
   │                                             │
   └─► 4B. WYŚLIJ DO RFQ                        │
          RM_BAZA → RM_RFQ:                     │
          pozycje + ilości + dokumentacja       │
                    │                            │
                    ▼                            │
          RM_RFQ → KOOPERANCI: zapytania        │
                    │                            │
                    ▼                            │
          KOOPERANCI → RM_RFQ:                  │
          oferty / ceny / terminy / odmowy      │
                    │                            │
                    ▼                            │
          RM_RFQ → RM_BAZA: WYNIK RFQ           │
          (wybrana oferta / dostawca /           │
           cena / termin / odniesienie do oferty)
                    │                            │
                    └──────────────────────┐     │
                                           ▼     ▼
                         10. UTWORZENIE I WYSŁANIE
                             ZAMÓWIENIA W RM_BAZA
```

**4B jest wyłącznie akcją „wyślij pozycje do ofertowania w RM_RFQ".**
RM_RFQ wysyła zapytania do kooperantów, odbiera ich odpowiedzi i po zakończeniu
procesu zwraca **wynik RFQ do RM_BAZA**. Wynik nie wraca do 4B i RM_RFQ nie wysyła
właściwego zamówienia do dostawcy.

**Twarda zasada architektoniczna:**
* **RM_RFQ kończy swoją odpowiedzialność na zwrocie wyniku ofertowania do RM_BAZA.**
* **RM_BAZA jest systemem, który tworzy, numeruje i wysyła właściwe zamówienie
  do dostawcy** — zarówno po RFQ, jak i bez RFQ.
* RM_RFQ nie wywołuje Sfery, nie mapuje kartotek i nie zna modelu dokumentów Subiekta.

Dopiero we wspólnym kroku **10. Utworzenie i wysłanie zamówienia w RM_BAZA**
RM_BAZA:
1. scala projekt/BOM z wynikiem RFQ albo z danymi zakupu bezpośredniego,
2. ustala finalnego dostawcę i warunki handlowe,
3. tworzy właściwe zamówienie w RM_BAZA i nadaje mu `order_number`,
4. zapisuje `order_date` i wylicza/zapisuje `pickup_date`,
5. **wysyła zamówienie do dostawcy**,
6. rozwiązuje mapowanie `drawing_number → kartoteka Subiekta`,
7. zakłada brakującą kartotekę na żądanie, jeśli spełnia reguły,
8. **jeśli firma zdecyduje się na ZD** — tworzy ZD przez Sferę,
9. jeśli ZD nie będzie używane — stan „zamówiono u dostawcy" pozostaje w RM_BAZA,
   a FZ później potwierdza fizyczne przyjęcie.

**Dopiero z kroku 10 mogą wychodzić operacje zapisu RM_BAZA → Subiekt.**
Sam zwrot wyniku z RM_RFQ jest tylko przepływem danych ofertowych do RM_BAZA.

Dzięki temu później można zmienić sposób obsługi Subiekta albo sposób generowania
zamówień bez ruszania mechanizmu ofertowania RM_RFQ.

### Krok 4 — sygnały zwrotne i stany w RM_BAZA

Nie sprowadzać wszystkiego do jednego „dostarczono”. W praktyce potrzebne są
co najmniej trzy różne stany:

| Stan | Źródło | Znaczenie w RM_BAZA |
|---|---|---|
| **wydano ze stanu** | Subiekt: rezerwacja/wydanie (dokładny dokument do ustalenia) | ilość zabezpieczona z własnego magazynu |
| **zamówiono u dostawcy** | **RM_BAZA** — właściwe zamówienie utworzone i wysłane na podstawie wyniku RFQ albo bez RFQ; opcjonalnie potwierdzone ZD | istnieje zobowiązanie/zamówienie, towar jeszcze nie przyszedł |
| **przyszło od dostawcy** | **FZ** ze skutkiem magazynowym przyjęcia | dostawa faktycznie weszła na magazyn |

Wizualnie warto użyć tego samego wzorca co kolumna **WYCENA**: krótki prefiks,
kolor oraz klik pokazujący szczegóły (numer zamówienia, kooperant, data
zamówienia, termin odbioru, data przyjęcia).

Mechanizm odświeżania — do zaprojektowania razem z decyzją o cache
(sekcja 12.2): ręczny „Sprawdź dostawy” per projekt albo odpytywanie przy
otwarciu projektu. Dla operacji ze skutkiem nadal obowiązuje weryfikacja
aktualnego stanu w Subiekcie tuż przed zapisem.
