---
name: project_wydane_do_arkusza_symbol
description: Dopasowanie wydan do arkusza musi uwzgledniac subiekt_symbol - pozycje handlowe nie maja numeru rysunku
metadata:
  type: project
---

# `delivered_qty` z Subiekta: dopasowanie TAKZE po `subiekt_symbol`

Zgloszone 02.10.2026: ZP196 mial w oknie wydania 17 pozycji wydanych,
a w arkuszu tylko 9 wypelnionych "Ilosci dostarczonych". Synchronizacja
`subiekt_wydane_do_arkusza.odswiez()` raportowala **0 zmian**.

## Przyczyna

`_mapa_bom()` budowala klucze wylacznie z `work_drawing_no` i
`src_drawing_no`. Pozycje handlowe dopisane z kartoteki Subiekta
(lozyska SKF, pasy T5, silnik, Elesa) **NIE MAJA numeru rysunku** —
oba pola sa `NULL`, a jedynym identyfikatorem jest `subiekt_symbol`.
Nie dopasowywaly sie do niczego i ich `delivered_qty` zostawalo puste,
choc Subiekt mial je wydane na RW 83/91/104 z 09.2026.

W ZP196 bylo takich pozycji 7 z 31 wierszy arkusza (id 59-65).

## Naprawa

`subiekt_symbol` jako TRZECI kandydat klucza, po `work_` i `src_` —
ostatni, zeby nie ruszac pierwszenstwa numeru rysunku tam, gdzie numer
istnieje. Efekt: 0 zmian -> 7 zmian.

⚠️ To ta sama lekcja, ktora `_zapisz_ilosci_z_subiekta` (ilosci z ZK)
mial juz wczesniej: "Klucz: najpierw symbol, pod ktorym pozycja poszla
do Subiekta". Modul wydan jej nie mial — teraz oba sa spojne.

## Kiedy synchronizacja w ogole leci

TYLKO pod lockiem, w trzech miejscach (`RM_BAZA_v15_MAG_STATS_ORG.py`):
  * "Przejmij Lock"  -> `_odswiez_wydane_z_subiekta(cicho=True)`
  * "Wymus"          -> to samo
  * przycisk "⬇ Dostarczone" -> na zadanie

Projekt w READ-ONLY nie zsynchronizuje sie nigdy — to zasada, nie blad.
Gdy arkusz "nie nadaza za Subiektem", NAJPIERW sprawdz, czy user ma lock.

## Czego ta synchronizacja NIE robi

**Nie dopisuje wierszy.** Symbol, ktorego nie ma w arkuszu, jest pomijany
(`if not trafienie: continue`). W ZP196 zostaly tak 3 pozycje kupione
na ZD z pominieciem BOM-u (`27 T5/19`, `27 T5/32`, `419817`) — arkusz ma
31 wierszy, Subiekt 34 pozycje. Dopisywanie wierszy to osobna decyzja
uzytkownika, NIE rob tego automatem.

Powiazane: [[project_wydanie_poza_bom_i_zd]]
