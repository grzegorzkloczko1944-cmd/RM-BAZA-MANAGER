---
name: project-numer-rysunku-i-symbol
description: Definicja numeru rysunku RMPAK i reguła generowania symbolu kartoteki — jedno źródło dla wszystkich narzędzi
metadata: 
  node_type: memory
  type: project
  originSessionId: e0ba9b4b-d4d7-4304-bc9f-6adc6046664a
  modified: 2026-09-05T03:12:49.780Z
---

**Numer rysunku RMPAK ma ścisły format** (`RE_RMPAK_BASE` w
`NOW/RM_IMPORT/RM_IMPORT_V17_MOD.py`):

```
^[A-Za-z0-9]{2,8}-\d{3}\.\d{2}     + opcjonalny sufiks X/XX/Z/ZZ
```

Obowiązkowa jest część `.NN` po trzycyfrowym katalogu — to ona odróżnia
`2627-100.01` od kodu handlowego `A-8-10-10`. Prefiks obejmuje też `ZP`
(zlecenia produkcyjne, np. `ZP139-100.07`).

**Nie zgadywać z kształtu napisu.** Poprzednia reguła („ma myślnik i cyfrę")
brała za rysunki kody handlowe `A-8-10-10`, `DSNU-25-100-P`, `GS14 14-16`
i panel przeczesywał dla nich serwer, kończąc „nie znaleziono plików".
Sprawdzone na 24 realnych symbolach — format klasyfikuje wszystkie poprawnie.

**Klasa pozycji jest gorszym kryterium niż format.** Pomiar na wszystkich
projektach: 919 pozycji ZNORMALIZOWANE ma pole numeru puste co do jednej,
2357 produkowanych (STANDARD/X/XX/Z/ZZ) ma je wypełnione — ale 10 pozycji
z klasą produkcyjną ma tam śmieci (`rolka`, `zbiornik`, `.`, `200`, kody Festo).

**Symbol kartoteki dla pozycji BEZ numeru rysunku** liczy `symbol_z_nazwy`
z `subiekt_projekt.py` (max 13 znaków; przy kolizji `rozroznij_symbol`
zostawia wyróżniki z cyframi: DN40, M6, L2525). Ręczne zakładanie kartoteki
(przycisk „Generuj") MUSI używać tej samej reguły — inaczej kartoteka założona
ręcznie i ta sama pozycja idąca automatem z projektu rozjadą się w Subiekcie
na dwie różne kartoteki.

**Kolumna ZD/ZK w oknie zamówień pokazuje numer Z ILOŚCIĄ**
(`ZD 4/CENTRALA/2026 (8)`) i bywa zbiorcza. To zapis dla oka — do wysyłki,
usuwania i do portalu idzie czysty numer (`_numery_zd` w `subiekt_zamowienia`).

Zob. [[project-parser-rm-baza]], [[project-zd-portal-rfq]].
