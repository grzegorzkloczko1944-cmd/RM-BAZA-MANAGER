---
name: project_znormalia_model_3d_z_zlozen
description: Mapowanie znormaliów na modele 3D bierze się ze złożeń (OUT + IAM), nie z nazw plików — zmierzone 66%; Part Number jest kluczem dla detali RMPAK
metadata:
  type: project
---

# Znormalia → model 3D: źródłem są złożenia, nie nazwy plików

Pomiar 27.09.2026 na `B:\!BIBLIOTEKA` (23 złożenia, 124 pozycje, 15 s).
Narzędzie: `pomiar_modele_znormalia.py` w repo, powtarzalne przez `--root`.

## Co jest kluczem

**Detale RMPAK — `Part Number` w modelu.** Numer rysunku stoi wprost
w iProperty „Design Tracking Properties":

```
Oś kół pozycjonera.ipt      PN=PL-300.06
Koło pod łańcuch 06-B2.ipt  PN=PL-300.05
```

Zero heurystyki, mapowanie pewne.

**Znormalia — `PN` PUSTE.** Nazwę (`688ZZ`) nadaje się w tabelce IDW, a nie
w modelu, więc w IAM-ie jej nie ma. Dlatego tylko one wymagają dopasowania
po kodzie katalogowym i ilości.

## Łańcuch danych

```
model 3D → IDW (tabelka — TU user poprawia nazwy) → CSV → importer → OUT.xlsx
```

OUT stoi **poniżej** edycji użytkownika, więc niesie już poprawione nazwy.
Zestawiamy dwa źródła tego samego złożenia:

| źródło | wie | nie wie |
|---|---|---|
| `OUT.xlsx` / `ELEMENTY ZNORMALIZOWANE` | nazwa z tabelki + ilość | pliku modelu |
| IAM przez `ApprenticeServer` | plik modelu + liczba wystąpień | nazwy z tabelki |

Ilości się zgadzają — w `PL-300.30ZZ` OUT mówi `6004ZZ`×1, `608ZZ`×10,
`688ZZ`×4 i dokładnie tyle wystąpień jest w IAM-ie.

## Wynik

| | pozycji | |
|---|---|---|
| pewne (automat) | 82 | **66%** |
| niepewne (człowiek) | 42 | 34% |

46 unikalnych symboli, **1 konflikt** (`6004ZZ` → różne modele w różnych
złożeniach).

## ⛔ Ślepe uliczki — nie powtarzać

**Kolumna „Pliki 3D" w OUT to NIE ścieżka.** Trzyma flagę `STP` („istnieje
eksport STEP"). `import_bom.py:369` ją czyta i nic z nią nie robi; w
`C:\iLogic` nie ma kodu, który wpisywałby tam ścieżkę.

**Dopasowanie „nazwa pliku = symbol kartoteki" dało 14 z 723 (2%).**
Porzucone — brakujących modeli nie ma pod ŻADNĄ nazwą, to nie był problem
nazewnictwa. Pełny opis: `PLAN_MAG.md`, sekcja 5a.

**Samo dopasowanie po ilości daje 28%.** Wszystko o ilości 1 wpada do jednego
worka kandydatów. Trzeba łączyć ilość z kodem katalogowym.

## ⚠️ Pułapka: sufiks uszczelnienia

`ZZ` / `2RS` / `2Z` to **typ uszczelnienia łożyska, nie część kodu**. Bez ich
obcięcia `6004ZZ` nie trafia w `6004 2Z Łożysko….ipt`. Ta jedna poprawka
podniosła wynik **z 52% na 66%** — największy pojedynczy zysk w całym
pomiarze.

## Czego automat nie ruszy

34% to pozycje, gdzie nazwa w tabelce nie ma nic wspólnego z nazwą modelu.
Żadna heurystyka tego nie złapie i nie ma sensu próbować:

```
SP-1,2/10,6/30 Sprężyna 1,2x10,6x30  →  sprężyna klawiszy wewn.ipt
Silnik 86BYG-118 8,5Nm               →  silnik Sanyo Denki 8,5Nm.ipt
Pasek T5/260 szer. 16mm              →  Pasek obrotnicy t5-260.ipt
```

To robota dla człowieka — ale **42 pozycje, nie 723**.

## Otwarte

* **Pomiar na całej `B:`** — zmierzono tylko `!BIBLIOTEKA`. Przed budowaniem
  narzędzia dla współpracownika trzeba znać prawdziwą skalę.
* **Czytanie tabelki wprost z IDW** — dałoby kolejność pozycji jako dodatkowy
  klucz; może podnieść 66%.

Plan makra: `PLAN_MAG.md` (sekcja 5a).

Powiązane: [[project_numer_rysunku_i_symbol]],
[[project_normalia_po_klasie]], [[project_symbole_ze_spacja]]
