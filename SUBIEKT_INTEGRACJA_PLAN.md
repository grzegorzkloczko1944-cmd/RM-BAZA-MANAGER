# Integracja RM_BAZA ↔ Subiekt GT — plan

> **Status:** projekt, nic jeszcze nie zaimplementowane (stan 31.08.2026).
> Dokument powstał z rozmowy ustalającej zakres — zapisany, żeby nie zaczynać
> od zera. Przed pisaniem kodu przeczytaj sekcję 5 (do rozstrzygnięcia).

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

## 2. Czym się łączyć — Sfera czy SQL

**Zasada: odczyt po SQL, zapis przez Sferę.**

| operacja | kierunek | narzędzie | dlaczego |
|---|---|---|---|
| kartoteki towarów, ceny, stany | Subiekt → RM_BAZA | **SQL read-only** | szybkie, bez licencji, nic nie psuje |
| kontrahenci (dostawcy) | Subiekt → RM_BAZA | **SQL read-only** | jw. |
| dokumenty RW / WZ / PZ | Subiekt → RM_BAZA | **SQL read-only** | jw. |
| **tworzenie kartoteki towaru** | RM_BAZA → Subiekt | **SFERA (COM)** | patrz niżej |
| **zamówienia do dostawców** | RM_BAZA → Subiekt | **SFERA (COM)** | patrz niżej |

**Dlaczego zapis TYLKO przez Sferę.** Dokument w Subiekcie to nie jeden wiersz
w tabeli — numeracja, stany magazynowe, rozrachunki i powiązania siedzą
w kilkunastu tabelach, a część logiki jest w aplikacji, nie w bazie. Ręczny
`INSERT` da dokument, który wygląda poprawnie do pierwszego remanentu.
Insert nie wspiera takich modyfikacji: przy problemie zostajemy sami.

To samo dotyczy kartotek towarów — to nie jest jeden rekord (grupy, jednostki
miary, stawki VAT, cenniki, powiązania).

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

- [ ] **Co jest symbolem kartoteki?** Numer rysunku RM_BAZA to naturalny kandydat,
      ale: czy `2602-100.41X` po zmianie konstrukcyjnej to nadal ten sam towar?
      Jeśli zmieniła się geometria, a numer został — dostawca dostanie zamówienie
      na coś innego niż poprzednio.
- [ ] **Czy sufiks X/XX wchodzi w symbol?** Ten sam detal cięty laserem i frezowany
      to dla magazynu dwie różne rzeczy.
- [ ] **Materiały (blacha, profile)** mają kartoteki w Subiekcie, ale nie mają
      numerów rysunków — jak je mapować?
- [ ] **Kto jest źródłem prawdy o stanie magazynu?** Powinien być Subiekt, a RM_BAZA
      tylko go odpytuje. RM_BAZA NIE MOŻE trzymać własnej wersji stanów — rozjadą
      się (por. `rfq_portal_url`, gdzie dwa źródła tej samej prawdy rozjechały się
      przy pierwszej zmianie).
- [ ] **Licencja Sfery** — jest płatna, per stanowisko, dokupowana do Subiekta GT.
      Bez niej zapis odpada i zostaje sam odczyt. **Sprawdzić PRZED planowaniem.**

## 6. Pułapki techniczne (znane z tego środowiska)

⚠️ **Sfera jest 32-bitowa i wymaga zainstalowanego Subiekta na maszynie.**
Jeśli RM_BAZA chodzi na 64-bitowym Pythonie, wołanie COM wprost SIĘ NIE UDA —
to ten sam problem co `tkinterdnd2` (win-x86 vs win-x64) i `Inventor32bitHost.exe`.

**Rozwiązanie:** osobny proces-most w 32-bit, zamiast wołania COM z RM_BAZA —
analogicznie do `RM_SYNC_AGENT`, który pośredniczy między RM_BAZA a portalem RM_RFQ.

⚠️ **Bitdefender potrafi blokować operacje COM** (patrz historia z
`Inventor32bitHost.exe`). Przy pierwszych testach sprawdzić to, zanim zacznie się
szukać błędu w kodzie.

⚠️ Python dogada się ze Sferą przez **`pywin32`** — ta sama biblioteka, której
używa `RM_Transfer_Project_FULL.py` do Inventora. Technologia nie jest nowa
w tym środowisku.

## 7. Pierwszy krok

**Skrypt rozpoznawczy, nie integracja.** Podłączyć się read-only do bazy Subiekta
i wypisać, co tam jest: struktura kartotek towarów, kontrahenci, dokumenty
magazynowe, cenniki.

Kilkanaście linijek, nic nie zmienia, a odpowiada na pytanie, czy mapowanie po
numerze rysunku jest w ogóle wykonalne (sekcja 5). Dopiero po tym decyzja
o Sferze i zapisie.

Potrzebne: nazwa serwera SQL i bazy (zwykle `.\INSERTGT`, baza typu `Firma_XXX`).
