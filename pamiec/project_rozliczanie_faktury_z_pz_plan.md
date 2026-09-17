---
name: project_rozliczanie_faktury_z_pz_plan
description: PLAN (nie kod) rozliczania faktury KSeF względem PZ — pięć szczebli kojarzenia (WZ, nr zamówienia, ZD, symbol+ilość, człowiek), statusy per linia, gdzie zapisać; uzgodnione 18.09.2026, do wznowienia
metadata:
  type: project
---

**Punkt wznowienia.** Rozmowa z 18.09.2026 po północy, tuż po wdrożeniu
okna przyjęcia dostawy ([[project_przyjecie_dostawy_pz]]). To ostatni
niezrobiony punkt planu z [[project_obieg_przyjec_dostawa_pz]]. Kodu jeszcze
NIE MA — poniżej jest projekt uzgodniony z użytkownikiem, pytanie „budować?"
zostało otwarte na jutro.

## Co już leży po obu stronach (nic nie trzeba dorabiać w danych)

| faktura KSeF (archiwum `FV_KSEF`) | PZ w Subiekcie (tryb `pz`) | DOSTAWA (master) |
|---|---|---|
| per pozycja: `dodatkowe["Numer wydania"]` = WZ, symbol dostawcy, ilość, cena; nagłówek: lista `<WZ>` | `NumerZewnetrzny` = WZ dostawcy (wpisuje okno przyjęcia), pozycje: symbol kartoteki, ilość, cena, `Realizuje` = ZD | `nr_wz_dostawcy`, `nr_zamowienia`, `identyfikator_wlasny`, pozycje, `pz_numer`/`pz_id` |
| symbol dostawcy → kartoteka: **powiązania w Subiekcie** (`DaneAsortymentuDlaPodmiotu`, [[project_symbole_dostawcy_w_sferze]]) — okno faktur już je czyta | | |

Faktura QUAY `RVQ/05195/26` ma 11 numerów WZ, każda pozycja wie, z którego
wydania jest. PZ z okna przyjęcia nosi ten sam numer w `NumerZewnetrzny`.
**Klucz łączący istnieje po obu stronach.**

## Algorytm — kolejność z notatki o obiegu, od najpewniejszego

1. **Po WZ** — pozycje faktury grupowane po `Numer wydania`; dla każdego WZ
   szukamy PZ z tym `NumerZewnetrzny` (i DOSTAWY z `nr_wz_dostawcy`). PEWNE.
2. **Po numerze zamówienia** — `Numer zamówienia` z faktury vs
   `dostawy.nr_zamowienia` (gdy dostawca drukuje, a magazynier wpisał).
3. **Przez ZD** — najmocniejszy szczebel, NIE wymaga numeru od dostawcy:
   pozycja faktury → kartoteka (powiązanie symbolu) → pozycja ZD tego
   dostawcy → PZ, które ją zrealizowało. Tę relację **Subiekt trzyma sam**
   (`Realizuje` na PZ, sprawdzone w teście: `PZ 1/MASTER/2026 →
   ZD 2/CENTRALA/2026`). Działa dla wszystkiego zamówionego przez ZD.
4. **Dostawca + symbol + ilość** — wśród nierozliczonych PZ tego dostawcy;
   trafienie TYLKO gdy pasuje dokładnie jedno PZ. Dwa → człowiek.
5. **Człowiek** — okno pokazuje kandydatów (nierozliczone PZ dostawcy
   z datą, pozycjami, ilościami); wybór zapisuje się jak decyzja o kartotece.

⚠️ Krok 4 nigdy nie zapisuje trwałego powiązania sam — ta sama zasada co
przy normalizacji symboli (kandydat ≠ decyzja).

## Statusy per linia faktury (wynik kontroli)

| status | znaczenie |
|---|---|
| ✔ ZGODNA | ilość i cena zgadzają się z PZ |
| ⚠ ILOŚĆ | na PZ inna ilość — zafakturowano więcej/mniej niż przyjęto |
| ⚠ CENA | inna cena niż na PZ/ZD — do sprawdzenia przed FZ |
| ✘ BRAK NA PZ | zafakturowane, **nigdy nie przyjęte** — przypadek `FZ 24/09/2026` (53 poz., 0 na stanie) |
| ✘ NADWYŻKA | na PZ jest, na fakturze nie ma — czekać na drugą fakturę albo pomyłka dostawcy |

Faktura KONTROLUJE przyjęcie, nie tworzy go — kierunek z notatki o obiegu.

## Gdy towar przyszedł BEZ WZ (pytanie użytkownika 18.09.2026)

WZ wypada z łańcucha, reszta ogniw zostaje — dlatego w oknie przyjęcia WZ
nie jest wymagane. Magazynier wpisuje nr zamówienia albo własny identyfikator
(np. `QUAY 18.09 paczka 2`); PZ i tak powstaje.

| sytuacja | jak się rozliczy |
|---|---|
| towar zamówiony przez ZD, bez WZ | **automatycznie** przez ZD (krok 3) |
| spoza ZD, bez WZ, jedna otwarta dostawa dostawcy | automatycznie po symbolu i ilości (krok 4) |
| spoza ZD, bez WZ, kilka otwartych dostaw | ręcznie — okno podpowiada kandydatów |

Brak WZ boli tylko w jednym przypadku: towar spoza zamówienia od dostawcy,
który przysyła paczki często. Tam własny identyfikator przy przyjęciu pozwala
człowiekowi wybrać w pięć sekund zamiast zgadywać.

## Gdzie to widać i co się zapisuje

* okno **Faktury z KSeF**: nowa zakładka „Rozliczenie z PZ" (pozycje faktury
  + kolumny PZ / ilość na PZ / cena na PZ / status), liczniki jak przy
  kartotekach, odznaka faktury **„Rozliczona"** — teraz z realnym
  znaczeniem (w makiecie była, celowo jej dotąd nie użyliśmy)
* okno **Przyjęcie dostawy**, historia: kolumna „Faktura" przy rozliczonych
* zapis: powiązanie faktura↔PZ i wynik kontroli w archiwum faktur
  (`pozycje.rozliczenie` JSON — jak `decyzja`) + `dostawy.ksef_number`.
  Żadnej nowej sieci relacji poza tym, co Subiekt trzyma sam.

**FZ zostaje poza RM_BAZA** (ustalenie z notatki o obiegu). Księgowość
księguje FZ w Subiekcie „na podstawie PZ"; nasze rozliczenie mówi jej PRZED
tym, czy faktura się zgadza i które PZ realizuje.

## Otwarta decyzja (na jutro)

Sfera ma na PZ `IPrzyjecieZewnetrzne.ZmienStatusFakturowania`. Dwie drogi:

* **(rekomendowane na start) tylko RM_BAZA** — kontrola i widoczność bez
  ingerencji w to, co robi księgowość;
* **także Subiekt** — po rozliczeniu oznaczać PZ jako zafakturowane, żeby
  widać to było i tam. Dołożyć, gdy rozliczenie zobaczy się na żywo.

Użytkownik nie odpowiedział jeszcze „budować?" — rozmowa przerwana na
zapisaniu planu.

## Dane do testu (demo M-OLD, stan na 18.09.2026 00:30)

* faktura QUAY `RVQ/05195/26` w archiwum (55 poz., 11 WZ, 18 z kartoteką)
* `PZ 1/MASTER/2026`: `NumerZewnetrzny = WZ/TEST/01`, realizuje ZD 2,
  pozycje `2602-100.42X` ×3 i `688 ZZ` ×2 (cena 4,30) — DOSTAWA nr 1
* `688 ZZ` jest na fakturze QUAY jako `688 2Z-8x16x5` (lp 5, 212 szt.,
  WZ/01579/26, cena 4,30) i ma powiązanie symbolu w Subiekcie — dobry
  przypadek na krok 4 (symbol pasuje, ilość NIE: 2 vs 212 → ⚠ ILOŚĆ)
* do pełnego testu kroku 1 trzeba przyjąć dostawę z WZ = `WZ/01579/26`
  (numer z faktury), nie `WZ/TEST/01`

Patrz [[project_ksef_okno_faktur_wdrozone]], [[project_przyjecie_dostawy_pz]],
[[project_obieg_przyjec_dostawa_pz]].
