# Projekty RM_BAZA w Subiekcie — wydania i zapotrzebowanie

> **Status:** ustalenia z rozmowy 03.09.2026, nic jeszcze nie zaimplementowane.
> Dokument uzupełnia [`SUBIEKT_INTEGRACJA_PLAN.md`](SUBIEKT_INTEGRACJA_PLAN.md)
> (tam: kanał integracji, API Sfery, most NexoRecon, wyniki rozpoznania).
> Tu: **jak powiązać pozycje Subiekta z projektami RM_BAZA i wydawać na projekt.**

## 1. Problem

RM_BAZA prowadzi projekty i BOM-y. Subiekt prowadzi magazyn i **nie ma pojęcia
„projekt"** — sprawdzone w SDK: nie istnieje encja `Projekt` ani `Zlecenie`
(są tylko zlecenia produkcyjne ZPM/ZPR — montowanie kompletów, 0 sztuk w bazie).

Pytanie brzmi: jak wydać oring z magazynu „na projekt 2222" tak, żeby dało się
potem powiedzieć, co poszło na który projekt.

**Trudność, która wywraca proste rozwiązania:** elementy handlowe (oringi, śruby,
łożyska) przewijają się przez **wiele projektów naraz**. Kartoteka `OR-26X2 FKM`
należy do wszystkich projektów jednocześnie — to po prostu *ten oring*.

## 2. Rozważone i odrzucone

### 2.1 Uwagi na dokumencie — działa, ale nie skaluje

Stan faktyczny (03.09.2026): pole `Dokumenty.Uwagi` jest wypełnione w **628
dokumentach**, w tym **8 faktur sprzedaży ma sam numer projektu** (`2115`,
`2328`, `2341`, `2401`, `2457`, `2460`, `2509`, `2550`). Dzisiejsze
`RW 1/09/2026` ma w Uwagach `2453`.

Czyli sposób jest już w użyciu — ale:

* **Uwagi są na dokumencie, nie na pozycji** → jedno RW = jeden projekt.
  Wydanie oringów na trzy projekty wymaga trzech dokumentów albo wpisu
  `2222/2453/2601`, przy którym **ginie informacja, ile sztuk poszło gdzie**.
* To wolny tekst — nikt nie pilnuje formatu (`2453` vs `proj. 2453` vs
  `2453 Ceramizator`), więc filtrowanie z czasem zawodzi.

Szukanie po Uwagach **działa**: w Subiekcie przez filtrowanie F8 (opisane
w `SDK/F8_filtrowanie_przy_pomocy_wyrazen.pdf`), kolumnę „Uwagi" na liście
i widoki robocze (cecha PRO); z RM_BAZA zwykłym `LIKE` po `Dokumenty.Uwagi`.

**Werdykt:** dobre na doraźne oznaczanie detali robionych pod jeden projekt.
Nie nadaje się do elementów handlowych dzielonych między projekty.

### 2.2 Pole własne na pozycji dokumentu — poprawne, ale to tylko etykieta

Tabela `PozycjeDokumentu_PolaWlasnePozycjaDokumentu_Adv2` **istnieje i jest
pusta** — miejsce wolne. Pola własne **zaawansowane w wersji 2**; ⚠️ ważne:
wersja 2 **nie wymaga** podmiany `InsERT.Moria.ModelDanych.dll` na tę
z `Deployments\...\Binaries` (tego wymaga dopiero wersja 1) — most działa bez zmian.

Rozwiązuje granulację (1 pozycja = 1 projekt), ale:

* wymaga konfiguracji w Subiekcie (Konfiguracja → Pola własne),
* ktoś musi je **wypełniać** — Subiekt sam nic z niego nie liczy,
* to nadal notatka: brak pilnowania ilości, brak realizacji, brak zapotrzebowania.

Proste pola własne (`PolaWlasne1..8`) są **tylko dla `Asortyment` i `Podmiot`** —
nie dla pozycji dokumentu. Na kartotece numer projektu i tak nie ma sensu
(ten sam detal w wielu projektach), ale te 8 pól to dobre miejsce na
**symbol dostawcy** (patrz sekcja 5).

### 2.3 Słownik własny z listą projektów — odrzucone na teraz

Pole własne może być referencją do **słownika własnego** (`ISlownikiWlasne`,
`PozycjaSlownikaWlasnego` z `Id`/`Wartosc`/`Aktywna`) — wtedy w Subiekcie jest
**lista rozwijana**, nie wpisywanie z palca. Zamknięte projekty oznacza się
`Aktywna = false`: znikają z listy, zostają w historii.

**Koszt:** drugie źródło prawdy o tym, jakie projekty istnieją, plus
synchronizacja RM_BAZA → Subiekt. Plan ostrzega przed tym wprost (sekcja 5,
przypadek `rfq_portal_url`). Wracamy do tego, jeśli okaże się, że wpisywanie
ręczne faktycznie się rozjeżdża.

### 2.4 Kategorie dokumentów — nie

23 kategorie (`Zakup`, `Wydanie`, `Montaż`…). Jedna etykieta na cały dokument,
płaska lista — przy dziesiątkach projektów zrobi się śmietnik.

## 3. ROZWIĄZANIE: ZK (zamówienie od klienta) jako „lista projektu"

**Zamiast oznaczać pozycje etykietą, importujemy listę pozycji projektu jako
dokument ZK.** Subiekt traktuje ZK jako obiekt biznesowy i sam liczy realizację.

```
RM_BAZA: BOM projektu 2222
      │  eksport listy pozycji
      ▼
Subiekt: ZK „projekt 2222"  (pozycje + ilości)
      │
      ├─ co da się wydać teraz      → ZestawieniePozycjiGotowychDoWydania()
      ├─ czego brakuje              → ZapotrzebowanieNaAsortyment()
      ├─ RW/WZ jednym kliknięciem   → WypelnijNaPodstawieZK(...)
      ├─ ile już wydano             → IloscDoRealizacji, StanRealizacjiZamowienia
      └─ braki → zamówienie do dostawcy (zbiorcze przetwarzanie ZK na ZD)
```

**Dlaczego to bije poprzednie warianty:**

| | Uwagi | pole własne | **ZK** |
|---|---|---|---|
| jeden detal w wielu projektach | ✗ | ✓ | **✓** |
| Subiekt pilnuje, ile wydano | ✗ | ✗ | **✓** |
| wydanie jednym kliknięciem | ✗ | ✗ | **✓** |
| widać braki do zamówienia | ✗ | ✗ | **✓** |
| wymaga konfiguracji w Subiekcie | ✗ | ✓ | **✗** |

Uwagi i pole własne to **etykieta**, którą trzeba samemu obsłużyć.
ZK to **mechanizm** — nic nie budujemy, korzystamy z gotowego.

**Metody potwierdzone w API** (`IZamowieniaOdKlientow`, wersja 61.1.0.9431):
`UtworzZamowienieOdKlienta`, `ZapotrzebowanieNaAsortyment`,
`ZestawieniePozycjiGotowychDoWydania`; realizacja przez
`WypelnijNaPodstawieZK(zamowienia[], zrodlo, ParametryGrupowania…)`
z `MetodaGrupowaniaPozycji` (`BezKonsolidacji` /
`KonsolidacjaWJednostceMiaryICenie` / `KonsolidacjaBezWzgleduNaJednostkeMiary`).
Przykłady: `SDK\Przyklady\PrzykladyRealizacjiDokumentow` oraz rozdział
„Realizacje dokumentów" w `InsERT.nexo.Sfera.chm`.

**Numer projektu** wchodzi w `Tytul` albo `Uwagi` **na ZK** — i to wystarcza,
bo dalej wszystko wisi na zamówieniu, nie na pojedynczych pozycjach.

## 4. DO ROZSTRZYGNIĘCIA PRZED KODEM

- [ ] **Podmiot na ZK.** ZK to „zamówienie *od klienta*", wymaga podmiotu.
      Projekty to produkcja własna. Dwa wyjścia: **RMPAK** (własna firma — tak
      już robiliście, historyczne RW mają podmiot „RMPAK SPÓŁKA Z O.O.")
      albo **klient końcowy**, gdy projekt jest dla konkretnego odbiorcy.
- [ ] **Czy wracacie do wystawiania RW.** Ostatnie RW przed dzisiejszym:
      lipiec 2023. Bez wydań magazynowych nie da się śledzić, co poszło na
      projekt — całe to rozwiązanie zakłada, że RW są wystawiane.
      ⚠️ Dzisiejsze `RW 1/09/2026` (uwagi `2453`) **nie ma ani jednej pozycji** —
      sam nagłówek. Do wyjaśnienia, czy to test, czy dokument w trakcie.
- [ ] **Kopia bazy do testów.** To pierwszy **zapis** do Subiekta. Kopia:
      archiwizacja podmiotu → odtworzenie jako np. „RM PRODUKCJA TEST".
      Na produkcji dopiero po sprawdzeniu na kopii.
- [ ] **Co z pozycjami bez kartoteki.** Z 4425 numerów rysunków RM_BAZA
      kartotekę ma **135 (3 %)** — patrz plan, sekcja 12.2. ZK nie powstanie na
      nieistniejącej kartotece, więc albo zakładamy kartoteki przy eksporcie
      („kartoteka na żądanie", plan sekcja 4), albo ZK obejmuje tylko to,
      co już istnieje.

## 5. Na marginesie: symbole dostawców (osobny temat, ten sam mechanizm)

Przy imporcie faktur zakupowych Subiekt dopasowuje pozycje do kartotek m.in.
po **symbolu, jakim posługuje się dostawca** (`WyszukajPoSymboluDostawcy`,
`SymboleDlaPodmiotu`). Wypełnienie tego raz dla powtarzalnych dostawców
znacząco podnosi skuteczność automatycznego importu e-Faktur
(Subiekt ma go wbudowanego — `ObslugaImportuEFaktur`,
`WypelnijNaPodstawieDokumentuElektronicznego`, `WyszukajNiezafakturowanePrzyjecia`,
`WyszukajAsortyment`). **Nie trzeba tego pisać w RM_BAZA.**

## 6. Następny krok

**Suchy przebieg** (bez zapisu): bierze BOM projektu, dopasowuje pozycje do
kartotek Subiekta i pokazuje, jakie ZK by powstało — ile pozycji, które mają
kartotekę, których brakuje, jakie ilości. Dopiero po obejrzeniu tego —
zapis, i to najpierw na kopii bazy.
