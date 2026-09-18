---
name: project_most_faktury_braki
description: "Tryb `faktury` w moscie: pole NumerKSeF KLAMIE (trzyma numery zamowien), brak kwoty faktury i numeru KSeF — lista brakow do jednej przebudowy"
metadata:
  node_type: memory
  type: project
---

Ustalone 18.09.2026 przy dokladaniu przelacznika zrodel w oknie faktur
([[project_ksef_okno_zrodla_przelacznik]]). Tryb `faktury` (`Faktury.cs`,
czyta `sfera.DokumentyZakupu()`) ma trzy braki — **poprawic je JEDNYM
przebiegiem**, razem z nowym trybem `efaktury`
([[project_sfera_kolejka_efaktur]]), zeby nie budowac mostu dwa razy.

⛔ **PULAPKA: pole `NumerKSeF` w rekordzie `Fak` NIE ZAWIERA numeru KSeF.**
Rekord ma je na 6. pozycji, a konstruktor wstawia tam
`d.NumeryDokumentowRealizowanych` — czyli numery ZAMOWIEN realizowanych przez
te fakture. Filtrowanie listy po tym polu pokazywalo 3 faktury zamiast 120
(przeszly tylko te realizujace ZD). Nazwa pola jest mylaca — **zmienic na
`NumeryRealizowanych`**, a numer KSeF dolozyc osobno.

**Czego rekord `Fak` NIE MA, a przydaje sie w oknie:**

| brak | skutek dzis | skad wziac |
|---|---|---|
| kwota faktury | kolumna „Netto" pokazuje 0,00 dla KAZDEJ FZ | `DokumentZakupu.Wartosc` (potwierdzone w dokumentacji SDK, `CHM/sfera/html/74E2F3D3.htm`) |
| prawdziwy numer KSeF | nie da sie zestawic FZ z archiwum `FV_KSEF` | ⚠️ `DokumentZakupu` **nie ma** pola KSeF (sprawdzone: brak `NumerKSeF`/`KSeF`); isc przez `DokumentElektroniczny.DokumentPowiazanyId` → FZ |
| nazwa pozycji BEZ kartoteki (uslugi, transport) | pozycja pokazuje sama cene, pusty Identyfikator i Nazwa | `p.Opis` wraca PUSTY; znalezc wlasciwe pole nazwy na pozycji FZ |
| jednostka miary pozycji | kolumna „J.m." pusta | `PozFak` ma tylko Symbol/Nazwy/Ilosc/Cena |

⚠️ **Symbol i nazwa pozycji NIE zawsze sa puste** - wbrew komentarzowi
„0 z 305" w `Faktury.cs`. Pozycje Z KARTOTEKA maja jedno i drugie (widziane
18.09.2026: FZ 139/09/2026 poz. 1 `SSH812-K400`, „Lancuch SSH812-K4").
Pusto jest dla pozycji BEZ kartoteki - uslug i kosztow transportu: tam
`AsortymentAktualnyId` = 0, wiec symbol i nazwa kartoteki nie maja skad przyjsc,
a `p.Opis` (jedyne zrodlo nazwy takiej pozycji) wraca pusty. Ilosc i cena sa
zawsze, bo ida wprost z pozycji. **To brak w MOSCIE, nie w GUI.**

**How to apply:**
- Kolumny arkusza pozycji budowac PO NAZWACH (`{k: i for i, (k,_,_) in
  enumerate(KOL_POZYCJE)}`), nie po zgadnietych indeksach — pomylka o jedna
  pozycje wsadza cene w kolumne WZ i nikt tego nie zauwaza. Kolejnosc:
  `lp, ident, typ, nazwa, ilosc, jm, cena, wz, kartoteka, symbol_kart,
  nazwa_kart, opis_kart, projekty, status`.
- ⚠️ Most ma **JEDNA kolejke** (`BlockingCollection` w `ServerHost.cs`) —
  zadania ida po kolei. Okno faktur pyta przy starcie o `katalog` (CALA
  kartoteka, BEZ limitu), `symbole-dostawcy` i `kontrahenci`; dolozenie
  czwartego zapytania z limitem 500 zawieszalo pasek na minuty. Limit 120
  wystarcza. Przy nowych zapytaniach pamietac o tym korku.
