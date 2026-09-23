---
name: project_todo_ostrzezenie_kolizja_rodzica_out
description: "ZROBIONE 24.09.2026: read_tree ostrzega, gdy dwa pliki OUT podaja rozny sklad tego samego rodzica — dopisac wykrywanie rozjazdu i ostrzezenie do warn (~15 linii)"
metadata:
  node_type: memory
  type: project
---

**✅ ZROBIONE 24.09.2026** (wariant minimalny — wykryj i ostrzez).
Ponizej opis problemu i co dokladnie zaimplementowano.
Nie pilne: dzisiejsze dane (projekt 2637 + dwa OUT-y elewatorow) kolizji
NIE MAJA. Uderzy, gdy biblioteka dostanie zagniezdzone zlozenia.

## Co jest zle

`read_tree` ([subiekt_projekt.py:508-536](../subiekt_projekt.py#L508-L536))
skleja wszystkie `*_OUT.xlsx` z folderu projektu w jedno `kids`. Gdy DWA
pliki opisuja sklad TEGO SAMEGO rodzica, linia 532:

```python
if not any(c[0].upper() == child.upper() for c in kids[parent]):
    kids[parent].append((child, qty))
```

**pierwszy wpis wygrywa, drugi jest pomijany BEZ SLOWA.** Efekt:

- rozne ilosci tego samego dziecka → zostaje ta z pliku czytanego wczesniej;
- rozne sklady → HYBRYDA: suma obu list, czyli sklad, ktorego NIE MA
  w zadnym pliku.

O zwyciezcy decyduje **nazwa pliku** — `find_out_files` robi `sorted(glob())`,
kolejnosc alfabetyczna. Zmiana nazwy pliku zmienia wynik i nikt tego nie widzi.

⚠️ Uwaga: to dotyczy kolizji na RODZICU. Ten sam numer jako DZIECKO
w roznych rodzicach jest POPRAWNY i ma sie sumowac (`ilosci_z_drzewa`) —
nie ruszac, patrz [[project_drugi_out_uzupelnia_drzewo]].

## Co zrobic (wariant minimalny — REKOMENDOWANY)

**Wykryc i ostrzec, nie naprawiac.** Zachowanie sklejania zostaje bez zmian;
dokladamy tylko sygnal.

W petli jest juz `zrodla` (ile rodzicow wniosl kazdy plik). Dolozyc slownik
`skad = {RODZIC: nazwa_pliku}` i przy probie dopisania do rodzica
obsadzonego z INNEGO pliku porownac sklady:

- zgodne (ten sam zestaw dzieci i ilosci) → **cisza**, to normalne
  (ten sam zespol wystepuje w obu OUT-ach);
- rozjazd → komunikat do `warn`: numer rodzica, oba pliki, na czym polega
  roznica (inna ilosc / dziecko tylko w jednym).

`warn` wraca z `read_tree` i trafia do okna PRZED zapisem — user zobaczy
i zdecyduje ([[feedback_nic_po_cichu]]).

**Koszt:** ~15 linii. **Ryzyko regresji: zerowe** — dane bez kolizji
przechodza identycznie.


## Jak zaimplementowano (24.09.2026)

W `read_tree` doszly dwa slowniki: `skad = {RODZIC: nazwa pliku}` i lista
`rozjazdy`. Przy dopisywaniu dziecka do rodzica obsadzonego juz z INNEGO
pliku sprawdzany jest sklad:

- dziecko, ktorego tamten plik nie znal → „jest w X, ale nie ma go w Y";
- to samo dziecko w INNEJ ilosci → „X podaje 5, Y podaje 99 — zostaje 5"
  (jawnie mowimy, ktora wartosc wygrala).

Zgodne sklady → cisza. Rozjazd → komunikat leci do `warn` (widoczny
w oknie PRZED zapisem) i pelna lista do konsoli; w oknie pierwsze 5 pozycji
plus „… i N wiecej".

### Test

| przypadek | wynik |
|---|---|
| prawdziwy projekt 2637 (4 pliki OUT) | `warn = None` — zero falszywych alarmow |
| sztuczna kolizja (kopia OUT-a, ilosc 5 → 99) | wykryta, z nazwami plikow i zwyciezca |

## Warianty odrzucone (nie wracac)

| pomysl | dlaczego nie |
|---|---|
| zostawic jak jest (milczace scalanie) | daje sklad, ktorego nie ma w zadnym pliku |
| sortowac po DACIE zamiast nazwy | ta sama cichosc, tylko inny arbitralny zwyciezca |
| priorytet: plik projektu > biblioteczny | sensowne (projekt jest wlascicielem struktury), ale `kids` nie niesie „skad plik" → wieksza przebudowa. Wariant NA POZNIEJ, gdy ostrzezenia zaczna byc czeste |

## Jak przetestowac

Nie ma dzis danych z kolizja. Zrobic sztuczna: skopiowac OUT elewatora,
zmienic w kopii ilosc jednego skladnika i wlozyc oba do folderu projektu —
bez fixu przejdzie po cichu, z fixem ma wyskoczyc ostrzezenie.

Patrz [[project_drugi_out_uzupelnia_drzewo]] (mechanizm sklejania, pomiary
na 2637), [[project_subiekt_puste_zlozenia_decyzje]].
