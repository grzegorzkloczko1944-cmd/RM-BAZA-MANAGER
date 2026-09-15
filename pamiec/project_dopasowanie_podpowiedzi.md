---
name: project_dopasowanie_podpowiedzi
description: "Okno Dopasowanie kartotek: zakładka Podpowiedzi (fuzzy DO WYBORU, nigdy automat) + przepisywanie pozycji BOM na symbol i nazwę z Subiekta"
metadata:
  type: project
---

**Okno „Dopasowanie kartotek Subiekta" — rozbudowa 15.09.2026.**

## Dwa tory dopasowania

**Tor 1 — reguła jeden-do-jednego** (zakładki Do decyzji / Dopasowane /
Brak kartoteki). Klucz: `norm_kod()` z `subiekt_scalanie.py` — usuwa
`[spacja - _ . /]`, wielkie litery, potem porównanie DOSŁOWNE.
Kolejność: zapamiętane mapowanie → symbol → nazwa → kilku kandydatów → brak.
⚠️ `norm_kod` **NIE rusza ogonków**: `Lozysko` ≠ `Łożysko`.

**Tor 2 — zakładka „Podpowiedzi"** (nowa). Wchodzi TYLKO tam, gdzie tor 1
nic nie znalazł. Porównuje **każde pole z każdym** — nazwa i kod po stronie
RM_BAZA × nazwa i symbol po stronie Subiekta, 4 kombinacje, wygrywa
najlepszy wynik. Kolumna „Skąd": `N→N`, `N→S`, `S→N`, `S→S`
(N=nazwa, S=symbol, RM_BAZA→Subiekt).

Kod: `subiekt_dopasowanie.podpowiedzi()`, próg `PROG_PODPOWIEDZI = 0.70`,
`TOP_PODPOWIEDZI = 5`. Podobieństwo z `subiekt_podobne.podobienstwo()`
(SequenceMatcher po normalizacji, która ogonki JUŻ sprowadza).

**Wynik na projekcie 89:** 30 z 46 pozycji „brak kartoteki" dostaje
propozycję; z przełącznikiem „tylko po nazwie" — 22.

⚠️ **Porównanie WSZYSTKICH pól dało wyraźnie więcej niż same nazwy.**
`Korpus zaworu` = 1.00 (N→N), `3304` → `3304 RS 20x52x22,2` (N→S),
`19247_DSNU-25-80-PPV-A` → `19249_DSNU-25-125-PPV-A` = 0.91 (S→S).

⚠️ **`S→S` bywa czystym szumem** — numery rysunku z jednej rodziny projektów
są podobne z natury: `ZP179-100.01X` („Stolik pośredni") → `ZP196-000.10`
(„Oś rolki") = 0.76. Stąd przełącznik **„podpowiadaj tylko po nazwie"**,
który wycina `S→S` i `S→N`.

## ⛔ Podpowiedź NIGDY nie przypina sama

Pomiar 04.09.2026 (`subiekt_podobne.py`, nagłówek pliku): **389 par RÓŻNYCH
detali** przekroczyło próg — „Płyta zewnętrzna" vs „Płyta wewnętrzna" = 0.933,
„Korek 14mm" vs „Korek 64mm" = 0.889. Prawdziwe trafienia dają 1.000,
fałszywe siedzą tuż pod nimi i **żaden próg ich nie rozdziela**.
Zatwierdzone błędne skojarzenie idzie do GLOBALNYCH mapowań i po cichu
działa we wszystkich przyszłych projektach.

## Przepisywanie pozycji BOM (nowe)

`D.wpisz_numery_do_bom(project_id, {nazwa: {symbol, nazwa}})` — wołane przy
„Zapisz decyzje" dla pozycji BEZ numeru rysunku:

```
przed:  numer = (pusto)     nazwa = „6004 RS"
po:     numer = „6004RS"    nazwa = „6004RS INOX"
```

**Po co:** żeby przy NASTĘPNYM projekcie ta sama pozycja trafiła od razu
regułą jeden-do-jednego. Sprawdzone: po przepisaniu stan = „dokładny symbol"
(zielony, bez pytania), niezależnie od tego, czy nazwa jest stara czy nowa —
trafienie idzie po symbolu.

**Trzy blokady w SQL** (przetestowane na kopii bazy projektu 89):
- ⛔ `NOT (is_manual=1 AND subiekt_symbol<>'' AND notes LIKE 'półprodukt%'/'z zamówienia ZK')`
  — **CO PRZYSZŁO Z SUBIEKTA, NIE WRACA DO SUBIEKTA**. Ten sam warunek,
  którym rozpoznaje je `subiekt_projekt.read_project_items`. Te wiersze są
  rozpoznawane PO BRAKU NUMERU — wpisanie im numeru zdjęłoby ochronę i most
  założyłby DRUGĄ kartotekę (awaria z 14.09.2026).
- ⛔ `ordered_flag = 0` — pozycja na ZK/ZD należy do dokumentu.
- ⛔ wszystkie trzy kolumny numeru puste — nie nadpisujemy cudzej wartości.

Każde pominięcie wraca do okna **z powodem**. Nazwę nadpisujemy tylko
w `work_name` (roboczej); `src_name` z importu zostaje nietknięta.

## Pułapki interfejsu (naprawione tego samego dnia)

- ⚠️ **Szerokości kolumn liczyć PO tym, jak Tk nada oknu rozmiary.** Liczone
  w `__init__` opierają się na `winfo_width() == 1` i tabela startuje ścięta.
  Stąd `after(120, self._dopasuj_kolumny)` + przeliczanie po `<Configure>`
  okna i po ruchu suwaka `PanedWindow`.
- ⚠️ **`_rozciagnij` musi działać w OBIE strony.** Pierwsza wersja tylko
  dodawała nadmiar — gdy suma szerokości bazowych przekraczała panel,
  kolumny zostawały ucięte mimo miejsca w oknie.
- ⚠️ **Sumy szerokości bazowych muszą mieścić się w `minsize` panelu.**
- ⚠️ **`transient()` odbiera oknu przyciski − i □ w Windows** (zostaje samo ×)
  i trzyma je nad rodzicem. Okno zamówień rozwiązało to tak samo —
  `subiekt_zamowienia.py` ~1016.
- Etykiety „Skąd" muszą być krótkie (`S→S`), bo `symbol ~ symbol` się nie
  mieści i ucina do `symbol ~ sy…`.
- Stan i cena kandydata: `subiekt_stany.query_stock()` (~0,1 s przez żywy
  most), cache na czas okna. Katalog z `wczytaj_katalog_subiekta()` ma tylko
  `id/symbol/nazwa` — stanów tam nie ma.

Powiązane: [[project_subiekt_edytor_kartotek]], [[project_subiekt_scalanie_kartotek]].
