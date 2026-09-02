# Integracja RM_BAZA ↔ Subiekt nexo PRO — plan

> **Status:** projekt, nic jeszcze nie zaimplementowane (stan 31.08.2026,
> zaktualizowano 01.09.2026 — użytkownik ma **nexo PRO**, nie GT, patrz sekcja 2).
> Dokument powstał z rozmowy ustalającej zakres — zapisany, żeby nie zaczynać
> od zera. Przed pisaniem kodu przeczytaj sekcję 5 (do rozstrzygnięcia).
>
> ⚠️ Ten plik pierwotnie zakładał Subiekt **GT** (Sfera, COM, 32-bit). Program
> to **nexo PRO** — inny produkt InsERT, inna architektura integracji. Sekcja 2
> i 6 przepisane pod nexo; reszta (4, 5, cel biznesowy) nie zależy od wersji
> produktu i została bez zmian.

## 1. Po co to

Dziś RM_BAZA prowadzi projekty i BOM-y, a magazyn żyje osobno w Subiekcie GT.
Skutek: zamówienia do dostawców powstają ręcznie, a informacja „co już mamy,
a co trzeba dokupić" wymaga ręcznego porównania dwóch systemów.

Docelowy obieg:

```
RM_BAZA  ──(1) lista zamówień──►  SUBIEKT GT
                                     │
                                     ├─ (2) porównuje z magazynem:
                                     │      co wydać do montażu,
                                     │      co zamówić u dostawcy
                                     │
RM_BAZA  ◄──(3) co wydano / co przyszło──┘
```

1. **RM_BAZA → Subiekt** — lista zamówień (zapotrzebowanie z projektu).
2. **Subiekt** — sam liczy, co pokryje z magazynu, a co zamówić. Nic nie budujemy.
3. **Subiekt → RM_BAZA** — dokumenty magazynowe: wydania do montażu (RW/WZ)
   i przyjęcia od poddostawców (PZ).

## 2. Czym się łączyć — nexo PRO API, nie Sfera

**Program to Subiekt nexo PRO — inny produkt niż GT, ze zupełnie innym
mechanizmem integracji.** Sfera (COM, 32-bit) należy do linii GT i **dla nexo
nie istnieje**. Właściwym i jedynym oficjalnym kanałem jest **nexo PRO API**
(REST/HTTP), do którego dostęp jest już wykupiony (klucz API na koncie —
sprawdzone 01.09.2026).

**Zasada zostaje ta sama co dla GT, zmienia się tylko narzędzie: odczyt
najprostszą dostępną drogą, zapis wyłącznie przez oficjalne API.**

| operacja | kierunek | narzędzie | dlaczego |
|---|---|---|---|
| kartoteki towarów, ceny, stany | Subiekt → RM_BAZA | **nexo PRO API (GET)** | oficjalne, udokumentowane, bez ograniczeń bitowości |
| kontrahenci (dostawcy) | Subiekt → RM_BAZA | **nexo PRO API (GET)** | jw. |
| dokumenty RW / WZ / PZ | Subiekt → RM_BAZA | **nexo PRO API (GET)** | jw. |
| **tworzenie kartoteki towaru** | RM_BAZA → Subiekt | **nexo PRO API (POST)** | patrz niżej |
| **zamówienia do dostawców** | RM_BAZA → Subiekt | **nexo PRO API (POST)** | patrz niżej |

**Dlaczego zapis TYLKO przez API.** Dokument w Subiekcie to nie jeden wiersz
w tabeli — numeracja, stany magazynowe, rozrachunki i powiązania siedzą
w wielu tabelach, a część logiki jest w aplikacji, nie w bazie. Nawet gdyby
dało się dobrać bezpośrednio do bazy nexo, ręczny zapis dałby dokument, który
wygląda poprawnie do pierwszego remanentu — dokładnie ten sam problem, który
przy GT wykluczał ręczny `INSERT`. Różnica jest tylko w narzędziu, którym się
poprawnie zapisuje: przy GT to Sfera, przy nexo to REST API.

To samo dotyczy kartotek towarów — to nie jest jeden rekord (grupy, jednostki
miary, stawki VAT, cenniki, powiązania).

**Czego NIE robimy:** bezpośredniego SQL do bazy nexo (jak przy GT).
nexo PRO API jest projektowane jako *jedyny* wspierany kanał integracji —
struktura bazy nexo nie jest publicznym kontraktem i może się zmienić między
wersjami bez ostrzeżenia, inaczej niż w GT, gdzie odczyt SQL był
utrwaloną, powszechnie stosowaną praktyką.

**Skąd wziąć specyfikację API (do zrobienia w firmie, na miejscu z dostępem
do konta InsERT):**
1. `konto.insert.com.pl` → zakładka „Aplikacje" → InsERT API → specyfikacja
   API dla poszczególnych produktów (endpointy, parametry, przykłady).
2. Osobno: „Szczegółowa Dokumentacja Techniczna" (SDK) do nexo — struktura
   danych i lista obiektów/metod programu, do pobrania z e-Pomocy technicznej
   InsERT. Przydatna jako uzupełnienie specyfikacji REST, gdy trzeba
   zrozumieć znaczenie pola, nie tylko jego nazwę w JSON.
3. **Uwaga na starsze materiały w sieci** — od 14.06.2024 InsERT wymaga
   nowego REST API zamiast wcześniejszych mechanizmów integracji; artykuły
   i posty z forum sprzed tej daty mogą opisywać nieaktualny sposób
   podłączenia.

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
- [ ] **Kto jest źródłem prawdy o stanie magazynu?** Powinien być Subiekt, a RM_BAZA
      tylko go odpytuje. RM_BAZA NIE MOŻE trzymać własnej wersji stanów — rozjadą
      się (por. `rfq_portal_url`, gdzie dwa źródła tej samej prawdy rozjechały się
      przy pierwszej zmianie).
- [x] **Dostęp do nexo PRO API** — klucz API już wykupiony i aktywny (potwierdzone
      01.09.2026), droga **oficjalna**: portal deweloperski InsERT przez
      `konto.insert.com.pl` → „Moje produkty" → InsERT API → subskrypcja →
      klucz kliencki + klucz prywatny (para kluczy, oba trzeba zachować przy
      generowaniu). NIE przez rozwiązanie trzeciej firmy (np. Easy Nexo
      Integrator/„Bridge" — osobna aplikacja z własnym REST API, inna droga,
      nie tę wybrano).
      Do zrobienia przed kodem: sprawdzić w portalu deweloperskim InsERT
      dokładny zakres uprawnień subskrypcji (czy obejmuje zapis dokumentów
      magazynowych i tworzenie kartotek, czy tylko odczyt — przy generowaniu
      klucza wybiera się „Read/Write") oraz limity zapytań (rate limit).

## 6. Pułapki techniczne (nexo PRO API)

**Cała ta sekcja pierwotnie opisywała pułapki Sfery (COM, 32-bit) — nie
dotyczą nexo i zostały usunięte.** nexo PRO API to zwykłe REST/HTTP: żadnego
problemu 32-bit vs 64-bit (jak przy `tkinterdnd2` czy `Inventor32bitHost.exe`),
żadnego pośredniczącego procesu-mostu, żadnego ryzyka blokady przez
Bitdefender na poziomie COM. RM_BAZA łączy się z API bezpośrednio, z tego
samego procesu, niezależnie od bitowości Pythona.

Do sprawdzenia realnie dotyczące nexo:

- **Autoryzacja** — jak dokładnie klucz API jest przekazywany (nagłówek,
  token OAuth, para klucz+sekret) i czy wymaga odnawiania (token z czasem
  wygaśnięcia vs klucz stały).
- **Format odpowiedzi i błędów** — JSON zwykle, ale trzeba sprawdzić strukturę
  błędów walidacji (np. przy tworzeniu kartoteki z brakującym polem), żeby
  komunikaty w RM_BAZA były czytelne, a nie surowym zrzutem odpowiedzi.
- **Limity zapytań (rate limiting)** — jeśli API ogranicza liczbę wywołań na
  minutę/godzinę, wpływa to na to, czy pobieranie stanów robić w pętli, czy
  wsadowo (batch endpoint, jeśli istnieje).
- **Środowisko testowe** — sprawdzić, czy nexo PRO API ma osobny adres/tryb
  testowy (analogicznie do `BASE_URL_TEST` w kliencie KSeF, sekcja 3), żeby
  pierwsze testy nie trafiały w prawdziwe dane magazynowe.

## 7. Pierwszy krok

**Skrypt rozpoznawczy, nie integracja.** Podłączyć się kluczem API (odczyt) do
nexo PRO i wypisać, co tam jest: struktura kartotek towarów, kontrahenci,
dokumenty magazynowe, cenniki — dokładnie jak dotąd, tylko przez wywołania
GET zamiast zapytań SQL.

Kilkanaście linijek, nic nie zmienia, a odpowiada na pytanie, czy mapowanie po
numerze rysunku jest w ogóle wykonalne (sekcja 5), i przy okazji pokazuje
realny kształt odpowiedzi API (pola, nazewnictwo) — potrzebny do zaplanowania
zapisu w kroku drugim.

Potrzebne: dokumentacja nexo PRO API (endpointy, autoryzacja) + klucz API
(już jest, patrz sekcja 5).
