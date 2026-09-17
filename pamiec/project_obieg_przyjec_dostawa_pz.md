---
name: project_obieg_przyjec_dostawa_pz
description: Obieg przyjęć towaru — DOSTAWA → PZ → kontrola FZ; decyzje projektowe i pomiary z 17.09.2026
metadata:
  type: project
---

Ustalenia architektoniczne przyjęte 17.09.2026, po pomiarze PZ na produkcji.
**To są decyzje, nie kod** — kodu jeszcze nie ma, powstaje etapami niżej.

## Pomiar, który wszystko ustawił

Tryb `NexoRecon.exe pz` (tylko odczyt, 80 dokumentów, 2023-06 … 2026-09-15):

| | |
|---|---|
| pozycje PZ z asortymentem | **350 / 350 = 100%** |
| pozycje FZ z asortymentem | 203 / 269 = 75% |
| PZ z `NumeryDokumentowRealizowanych` | 2 / 80 |
| magazyny | MASTER 45, Magazyn podstawowy 35 |

**Wniosek, mocniejszy niż wcześniej zakładano:** FZ z pozycją bez kartoteki nie
znaczy „towar przyjęty jako luźny tekst", tylko **towar NIE trafił na stan**.
Subiekt nie tworzy PZ dla pozycji, której nie potrafi zidentyfikować — nie wie,
co przyjąć. Dowód: `FZ 24/09/2026` QUAY, 53 pozycje, 0 dopasowanych — faktura
zaksięgowana, koszt poniesiony, **stanu magazynowego brak**.

## ⚠️ Subiekt trzyma relacje dokumentów SAM — nie dublować

Odczytane z `DokumentPZ`:

```
Dokument_DokumentPowiazany_Id = 100055
DokumentZrodlowyId            = 100055      → DokumentDZ (faktura)
DokumentyRealizowane / DokumentyRealizujace / DokumentyPowiazane  (kolekcje)
NumerKSeFDokumentu
```

Nie budować w RM_BAZA alternatywnej sieci FZ↔PZ↔ZD. Jedna FZ może realizować
kilka PZ — stąd kolekcje, nie pojedyncze pola.

## Kierunek przepływu — faktura KONTROLUJE, nie tworzy

```
ZD → paczka + (WZ | nr zamówienia | własny ID) → DOSTAWA → PZ → produkcja ma stan
                                                                      ↓
                                    ... kilka dni później ...
                                                                      ↓
                        XML KSeF → grupowanie → kontrola: ilość, symbol, cena,
                                                braki, nadwyżki → FZ
```

⚠️ **Data PZ pochodzi z momentu fizycznego przyjęcia**, nie z rekonstrukcji po
dacie faktury. Numer WZ z XML mówi, DO KTÓREJ dostawy należy pozycja — ale nie
KIEDY przyszła.

⚠️ **WZ nie może być wymagane.** Faktura QUAY ma 12 numerów WZ, ale wielu
dostawców ich nie podaje. Logika to `DOSTAWA → PZ`, gdzie WZ jest tylko jednym
z możliwych identyfikatorów.

## Model danych — trzy warstwy

⚠️ **Bez `zd_id` w dostawie.** Relacja jest wiele-do-wielu w obie strony: jedno
ZD przychodzi w trzech paczkach, jedna paczka miewa pozycje z kilku ZD.

```
dostawy              id, supplier_id, data_przyjecia, identyfikator_wlasny,
                     nr_wz_dostawcy NULL, nr_zamowienia NULL, pz_id NULL,
                     status, zrodlo_przyjecia

dostawy_pozycje      id, dostawa_id, asortyment_id, symbol_dostawcy,
                     ilosc, jednostka

dostawa_zd_pozycje   dostawa_pozycja_id, zd_pozycja_id, ilosc
                     ← osobna tabela, bo 100 szt. z ZD może przyjść 40+35+25
```

**DOSTAWA to nie dublowanie `DokumentyRealizowane`.** Subiekt opisuje relacje
dokumentów księgowo-magazynowych; DOSTAWA opisuje **zdarzenie operacyjne**:
kto odebrał, ile paczek, przyjęto 8 z 10, 2 brak. PZ jest dopiero WYNIKIEM tego
zdarzenia — stąd `pz_id` jako wskazanie wyniku, i nic więcej.

## Mapowania symboli dostawców — OSOBNA tabela

Istniejąca `mapowania` ma `numer_rysunku TEXT PRIMARY KEY` — klucz
jednowymiarowy, pod WŁASNE rysunki. Nie zmieści pary (dostawca, symbol),
a zmiana klucza głównego przy 863 wpisach to niepotrzebne ryzyko.

```
mapowania_dostawcow   supplier_id, symbol_dostawcy, asortyment_id,
                      kto, kiedy, uwagi
                      PRIMARY KEY (supplier_id, symbol_dostawcy)
```

⚠️ **Klucz na `supplier_id`, nie na NIP-ie.** NIP przychodzi z faktury i służy
do ZNALEZIENIA `supplier_id` (`suppliers-z-nip`); reszta systemu operuje na
własnym stabilnym ID. Dwóch dostawców używa tego samego oznaczenia dla różnych
rzeczy — dlatego symbol sam z siebie NIE jest kluczem globalnym.

## Kolejność dopasowania pozycji

```
1. ręczne zapamiętane mapowanie (supplier_id + symbol)  → pewne
2. dokładny symbol w kartotece                          → pewne
3. symbol po normalizacji, TYLKO gdy jednoznaczny       → KANDYDAT, nie zapis
4. BRAK → decyzja człowieka
```

⚠️ Krok 3 **proponuje, nigdy nie zapisuje** trwałego mapowania. Normalizacja
prędzej czy później zlepi dwa różne symbole, a błąd rozejdzie się po wszystkich
przyszłych fakturach tego dostawcy. Trwałe mapowanie = decyzja człowieka.

⚠️ **Bez fuzzy match po nazwie** — zmierzone i odrzucone, patrz
[[project_ksef_price_import]] i nagłówek `subiekt_podobne.py`: 389 par RÓŻNYCH
detali przekroczyło próg (`Płyta zewnętrzna` vs `Płyta wewnętrzna` = 0,933).

## ⚠️ NIE KAŻDA POZYCJA MA SYMBOL — trzy układy, ta sama schema FA(3)

Zmierzone na trzech fakturach 17.09.2026:

| dostawca | `<Indeks>` | `P_7` | identyfikator |
|---|---|---|---|
| **QUAY** | brak | czysty symbol `618/6 2Z` | całe `P_7` |
| **AMB PRODUKT** | **nie istnieje** | kod **+** nazwa: `013-100.30a Bok transportera 0,3mb` | kod wyłuskany regexem — **PROPOZYCJA** |
| **alu-frost** | jest, ale to **KATEGORIA** | `Detale cięte laserem - projekt 2630` | **BRAK** |

⚠️ **`<Indeks>` u alu-frost to nie symbol** — `Detale cięte laserem` powtarza się
w 3 z 4 wierszy, pozycje różnią się dopiero pełnym `P_7`. Taka linia może
odpowiadać **wielu detalom z kilku ZD**, więc faktura nie daje relacji 1:1.
Stąd status `POZYCJA_ZBIORCZA`: nie zakładamy kartoteki na siłę, nie blokujemy
rozliczenia, ale też nie udajemy, że jedna linia = jeden element magazynowy.

⚠️ Regex na kod rysunku (`_KOD_RYSUNKU`) jest celowo **wąski**: `człon-liczba
.liczba[literka]`. Szerszy rozbijał symbole QUAY (`618/4 2Z=684 2Z` → `618/4`
+ reszta), a to cały symbol, nie kod z nazwą.

Wynik: `mapowania_dostawcow` NIE MOŻE wymagać symbolu — musi być opcjonalny.
Pełne `P_7` zachowujemy zawsze jako `tekst_pozycji`.

Kolumny okna: **Identyfikator dostawcy | Nazwa / opis | Źródło**, gdzie źródło
to `INDEKS` / `SYMBOL` / `NAZWA` (wykryty) / `BRAK`.

## Ten sam rozdział istnieje po stronie BOM-u

`items` w bazie projektu ma numer rysunku i nazwę W OSOBNYCH kolumnach:
`src_drawing_no` / `work_drawing_no` / `norm_drawing_no` oraz `src_name` /
`work_name`. Zmierzone na `project_10`:

| klasa | pozycji bez numeru rysunku |
|---|---|
| ZNORMALIZOWANE (normalia) | **77 z 78** |
| STANDARD (detale własne) | 0 z 69 |
| X | 0 z 78 |

Normalia mają identyfikator **w nazwie** (`3304`, `170833 DFM-16-20-P-A-GF`,
`554225_ADNGF-20-30-P-A`), detale własne mają numer rysunku zawsze. Dopasowując
pozycję faktury do BOM-u: numer rysunku gdy jest, nazwa gdy pusty —
`class_effective` mówi, którego przypadku się spodziewać.

## ⚠️ TRZECI TYP: detal z NASZEGO rysunku

Obok towaru handlowego i pozycji opisowej jest trzeci typ, którego tożsamością
jest **numer rysunku RM**, a nie symbol dostawcy: `027-200.01 Korpus`,
`2602-100.41X Płyta zewnętrzna`. To Wasze elementy projektowe zlecone
kooperantowi, które wracają jako dostawa.

**Pomiar rozstrzygający (faktura AMB PRODUKT, 5 pozycji, 17.09.2026):**

| numer rysunku | BOM-y projektów | kartoteka Subiekta |
|---|---|---|
| `013-100.30a` | 25, 48, 54 | BRAK |
| `013-100.30B` | 9, 10, 21, 25, 29, 65 | BRAK |
| `013-100.30c` | 25, 50, 73 | BRAK |
| `ROTO-100.01` | 29, 48, 50, 54, 65 | BRAK |
| `DUO-100.06` | 73 | BRAK |
| **razem** | **5 / 5** | **0 / 5** |

Dla takiej pozycji szukanie w kartotece jest **z definicji bezowocne** — stąd
numer rysunku IDZIE PRZED symbolem katalogowym w hierarchii. Odwrotnie niż
QUAY: tam symbole są w kartotece (11/55), ale w BOM-ach ich nie ma.

⚠️ **Ten sam rysunek występuje w WIELU projektach** (`013-100.30B` w sześciu),
więc systemu nie da się zmusić do wskazania ZD — wybiera człowiek.

⚠️ **Numery rysunku porównujemy Z ZACHOWANIEM WIELKOŚCI LITER.**
`013-100.30a` i `013-100.30B` to RÓŻNE detale; normalizacja do wielkich liter
by je zlepiła.

**Bez nowej tabeli:** `mapowania` (klucz `numer_rysunku`) jest dokładnie do
tego; `mapowania_dostawcow` do cudzych symboli; `dostawa_zd_pozycje` do
powiązania z ZD. Semantyka rozdziela się sama.

**Pytanie w oknie brzmi „czym to jest", nie „załóż kartotekę":**
towar handlowy / usługa / pozycja zbiorcza / detal z naszego rysunku.

Kolumny okna: `Lp. | Identyfikator | Typ | Numer rysunku | Nazwa/opis | Ilość |
JM | Kartoteka | ZD | Status`.

## Cztery statusy pozycji

```
✓ KARTOTEKA        → konkretny asortyment Subiekta
✓ NOWA_KARTOTEKA   → utworzona teraz
— USLUGA           → nie bierze udziału w PZ
◫ POZYCJA_ZBIORCZA → jedna linia = wiele detali (alu-frost); nie na PZ
📐 RYSUNEK_RM      → nasz detal; wiąże się z ZD, kartoteka opcjonalna
! BRAK_DECYZJI     → blokuje utworzenie PZ
```

```python
can_create_pz = all(p.status in ("KARTOTEKA", "NOWA_KARTOTEKA",
                                 "USLUGA", "POZYCJA_ZBIORCZA")
                    for p in pozycje)
# do PZ ida tylko KARTOTEKA i NOWA_KARTOTEKA
```

Warunkiem nie jest „100% pozycji ma kartoteki", tylko **100% pozycji
magazynowych**. `OBSLUGA` z faktury QUAY ma być usługą, a nie towarem
magazynowym założonym po to, żeby licznik pokazał 55/55.

## Kojarzenie faktury z przyjęciami

```
1. numer WZ
2. numer zamówienia
3. ZD + dostawca + symbol + ilość
4. nierozliczone przyjęcia tego dostawcy
5. decyzja człowieka
```

⚠️ **Bez automatu przy `dostawca + symbol + ilość`, gdy pasuje więcej niż jedna
dostawa** — to idzie do okna rozliczenia.

## ⚠️ Naprawa historii to OSOBNY tryb

Kolumna `zrodlo_przyjecia`: `NORMALNE` / `REKONSTRUKCJA_HISTORYCZNA`.

Faktura QUAY posłuży jednorazowo do odtworzenia 53 pozycji z `FZ 24/09/2026`,
które nigdy nie weszły na stan. Oznaczenie jest po to, żeby za rok nikt nie
zobaczył kodu tworzącego PZ z XML faktury i nie uznał, że TAK MA DZIAŁAĆ
standardowy proces. **Faktura nie jest źródłem informacji, że dostawa nastąpiła.**

## Kolejność prac

1. **kartoteki + `mapowania_dostawcow`** — kolumna „Kartoteka" w pozycjach
   faktury, przycisk zbiorczego zakładania, trzy decyzje na pozycję
   (utwórz / wskaż istniejącą / oznacz jako usługę)
2. ekran przyjęcia DOSTAWY
3. powiązanie pozycji z ZD
4. generowanie PZ
5. rozliczanie faktury względem istniejących PZ

Etap 4 bez 1 i 2 stworzy dokumenty z pustymi pozycjami albo przypisane do
przypadkowego asortymentu — zafałszowanych stanów magazynowych nie sprząta się
łatwo.

**FZ zostaje poza RM_BAZA.** RM_BAZA: zapotrzebowanie → ZD → kartoteka →
przyjęcie → PZ. Subiekt/księgowość: faktura → FZ → rozliczenie istniejących
dokumentów.

Patrz [[project_ksef_archiwum_kolumny]], [[project_rfq_zamowienia_subiekt]],
[[project_mapowania_subiekta_stan_14_09]].
