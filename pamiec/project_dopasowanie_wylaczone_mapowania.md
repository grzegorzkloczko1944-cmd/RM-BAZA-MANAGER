---
name: project_dopasowanie_wylaczone_mapowania
description: "Czytanie globalnych mapowań w oknie Dopasowanie WYŁĄCZONE (24.09.2026) — odwracalne jedną linią; scalanie ilości na ZK zostaje żywe"
metadata:
  type: project
---

**Okno „Dopasowanie kartotek" nie czyta globalnych mapowań — od 24.09.2026,
decyzja użytkownika.** Commit `de7ddba`.

`przygotuj_pozycje()` widzi **pustą tabelę mapowań**: każda pozycja trafia do
okna jako „do decyzji" / „brak kartoteki", nic nie jest podpowiadane z tego,
co zapisano wcześniej. Dane w tabeli **są nietknięte** — to odcięcie odczytu
w jednym miejscu.

Miejsce: `subiekt_dopasowanie.py` ~215.

```python
mapowania = {}
# mapowania = subiekt_mapowania.get_many(kody) or {}
```

**POWRÓT:** skasować `mapowania = {}` i odkomentować linię niżej.

## ⚠️ NIE rozszerzać na subiekt_projekt.py

Scalanie ilości na ZK (`subiekt_projekt.py` ~946) korzysta z **tej samej
tabeli**, ale robi co innego: skleja wiersze BOM-u wskazujące JEDNĄ kartotekę.
Most ustawia ilość **WPROST, nie dodaje** — bez scalania druga pozycja
nadpisuje pierwszą i na dokumencie zostaje mniejsza liczba.

**7 + 1 dawało 1 zamiast 8** (projekt 2627, 15.09.2026).

To zostaje ŻYWE. Ostrzeżenie jest też w komentarzu przy samym wyłączeniu.

## Co się NIE zmienia

- **Arkusz RM_BAZA** czyta `subiekt_symbol` z tabeli `items`, nie z mapowań.
- **Zapis** mapowań („Zapisz decyzje") nadal działa — odkłada się do tabeli,
  tylko okno tego nie czyta z powrotem.
- Praktyczny skutek: raz dopasowana pozycja **wraca jako „do decyzji"** przy
  następnym otwarciu okna. Przy porządkowaniu całego BOM-u to klikanie
  wszystkiego od zera.

Narzędzie „Dopasuj kartotekę Subiekta…" z PPM w arkuszu również **nie pisze**
do mapowań — ta sama decyzja, ten sam dzień
([[project_dopasuj_kartoteke_wiersza]]).

Powiązane: [[project_dopasowanie_podpowiedzi]], [[project_jedno_zrodlo_prawdy_ilosci]].
