---
name: project_subiekt_zerowanie_magazynu
description: Jak wyzerowac stany magazynu w Subiekcie - nie ma trybu "zeruj", sklada sie z magazyn + rw
metadata:
  type: project
---

**Nie ma trybu "wyzeruj stany"** i nie moze byc - stan w Subiekcie to wynik
dokumentow, nie pole do nadpisania. Zerowanie sklada sie z dwoch trybow mostu:

1. `magazyn --tylko-niezerowe` - lista kartotek ze stanem
2. przerobienie na plan RW: `{"pozycje":[{"symbol":..,"ilosc":..}],"uwagi":..,"magazyn":"MAG"}`
3. `rw --plan=... ` sucho, potem `--zapisz`

RW zdejmuje stan, a **kartoteki, indeksy, historie i komplety zostawia**.

Wykonane 07.09.2026 na MAG (przed uruchomieniem magazynu nr 2): 787 kartotek,
11996 szt. -> zero. Dokumenty RW 4..9/09/2026.

**Co sie sprawdzilo w praktyce:**

- **Brak ceny ewidencyjnej NIE blokuje RW.** 767 z 787 pozycji mialo
  `CenaEwidencyjna: 0.0` i Subiekt przyjal kazda - mimo ze komentarz w
  `Rw.cs` wymienia to jako czesta przyczyne odmowy.
- **Komplety schodza jako komplety**, nie rozbijaja sie na skladniki.
  43 komplety poszly osobnym RW bez problemu.
- **Partie po 200 pozycji** w jednym dokumencie dzialaja. Warto dzielic,
  zeby jedna felerna pozycja nie wywalila calosci.
- Kartoteka z **otwartym ZD** pokazuje sie dalej w `--tylko-niezerowe`,
  nawet gdy ma stan 0.0 - to nie jest stan, tylko zamowienie.
- Jedna pozycja nie zeszla przez spacje w symbolu - patrz
  [[project_subiekt_symbol_spacja]].

**Pulapka na pozniej:** RW nie rusza dokumentow, wiec **otwarte ZD
przetrwaly zerowanie**. Przyjecie z takiego ZD pojdzie na magazyn wskazany
na dokumencie (czyli stary MAG), nie na nowy - sprawdzic przed pierwsza
dostawa.

Tryb `dokumenty` czyta tylko ZK/ZD/RW/WZ - **nie widzi PZ ani FZ**, wiec
"brak dokumentow z ta pozycja" z tego trybu nie znaczy, ze kartoteka nie ma
historii zakupu. Od tego jest `stan` (`OstatniaCenaZakupu`/`DataOstatniegoZakupu`).
