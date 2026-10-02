---
name: project_wydanie_kolumna_rw
description: Kolumna RW w oknie wydania - numer dokumentu przy pozycji, klik otwiera przeglad dokumentow na tym RW
metadata:
  type: project
---

# Okno wydania: kolumna „RW" z klikalnym numerem dokumentu

Dodane 02.10.2026 na prosbe uzytkownika: przy kazdej wydanej pozycji ma stac
numer RW, a klik ma otworzyc „Dokumenty w Subiekcie" ustawione na tym RW.

## Most (`WydanieStan.cs`)

Tryb `wydanie-stan` zwraca w kazdej pozycji nowe pole **`rw`** — liste
numerow RW, ktore ten symbol wydaly. Zbierane w `Zbierz()` przy okazji
sumowania ilosci, wiec BEZ dodatkowego zapytania (opcjonalny parametr
`numery`, wypelniany tylko dla RW).

Lista, nie pojedynczy numer: ten sam symbol moze wyjsc kilkoma RW przy
wydaniach czesciowych, a na jednym RW moze stac w kilku wierszach — stad
`Contains` przed dodaniem.

## Okno (`subiekt_wydanie_gui.py`)

* Kolumna `rw` na koncu, 86 px, wyrownana do lewej.
* `_bez_roku()` obcina rok: „RW 87/09/2026" -> „RW 87/09". Pelny numer sie
  nie miescil. Obcinamy TYLKO 4-cyfrowy ostatni czlon — inne ksztalty
  zostawiamy w calosci.
* Kilka RW -> „RW 87/09 +1", a klik pyta okienkiem, ktory otworzyc.
  Zgadywanie „pierwszy z brzegu" trafialoby w zly dokument.
* Klik obsluzony przez `<Button-1>` + `identify_column`, TYLKO na kolumnie
  `rw`; `<Double-1>` ma wyjatek na te kolumne, inaczej dwuklik w numer
  otwieralby „Popraw ilosc" tuz po otwarciu dokumentow.
* `_wiersz_planu()` szuka pozycji **po symbolu, nie po indeksie wiersza** —
  lista jest filtrowana i sortowana, wiec numeracja na ekranie nie odpowiada
  indeksom w `self.plan`.
* Kursor „reka" nad klikalnym numerem (`<Motion>`), inaczej nikt nie zgadnie,
  ze to link.

⚠️ SZEROKOSCI: budzet tabeli to ~820 px (patrz komentarz nad `KOL_PLAN`).
Dwie nowe kolumny („Do wyd." 54 + „RW" 86) zmusily do zwezenia pozostalych;
suma wynosi 818. Przy dokladaniu kolejnej kolumny NIE przekraczaj budzetu —
historia dwoch nieudanych prob jest w komentarzu.

## Przeglad dokumentow (`subiekt_dokumenty_gui.py`)

`DokumentyWindow(parent, szukaj=None)` i `open_window(parent, szukaj=None)`.
Numer trafia do wyszukiwarki (ktora i tak filtruje po numerze dokumentu),
a `_zaznacz_zadany()` po pierwszym wypelnieniu listy zaznacza wiersz,
przewija do niego i wola `_on_wybor_dokumentu()`, zeby dolna tabela pokazala
pozycje. Dziala JEDNORAZOWO — `_do_zaznaczenia` jest czyszczone, inaczej
kazde „Odswiez" przeskakiwaloby kursorem.

Okno wydania wola z `try/except TypeError` i awaryjnie ustawia `search_var`
recznie — stanowisko z nieodswiezonym modulem nadal zadziala.

Powiazane: [[project_wydanie_poza_bom_i_zd]]

## Prawa tabela przegladu dokumentow uciekala poza okno (02.10.2026)

Po otwarciu dokumentow klikiem z okna wydania widac bylo, ze panel pozycji
(prawa strona) jest szerszy niz miejsce, ktore dostaje: „Cena netto"
i „Wartosc" wychodzily poza krawedz.

Przyczyna: `KOL_POZ` sumowalo sie do **1090 px**, a panel siedzi
w `PanedWindow` z waga **3 z 8** — dostaje ~460 px przy oknie 1250 px
i ~700 px przy zmaksymalizowanym FullHD. Nie miescil sie NIGDY, tylko
nikt nie patrzyl na te kolumny, dopoki klik z okna wydania nie zaczal
otwierac dokumentow wprost na pozycjach.

Naprawione: `KOL_POZ` 1090 -> **690 px**, najwiecej oddal „Opis"
(260 -> 90; w tych dokumentach jest prawie zawsze pusty). Tryb „Wszystkie
pozycje" (9 kolumn, osobna lista szerokosci w `_pokaz_wszystkie_pozycje`)
miał ten sam problem: 1060 -> **780 px**.

⚠️ PULAPKA: `podepnij_szerokosci` przywraca szerokosci z
`C:\RMPAK_CLIENT\subiekt_kolumny.json` i NADPISUJE domyslne z kodu.
Zabezpieczenie dziala tylko wtedy, gdy zmienila sie LICZBA kolumn —
samo zwezenie w kodzie nie wystarczy, bo zapis ma te sama dlugosc.
Po zmianie szerokosci w kodzie trzeba skasowac wpis z JSON-a, inaczej
poprawka nie bedzie widoczna na stanowisku, ktore juz raz otworzylo okno.

Tu akurat zapis `dokumenty_pozycje` mial 6 wartosci przy 7 kolumnach
(kolumna „Opis" doszla 15.09.2026), wiec zostal odrzucony sam — ale
na to NIE MOZNA liczyc. Wpis skasowany recznie; kopia zapasowa:
`subiekt_kolumny.json.bak_02102026`. Wpis `dokumenty` (lewa tabela,
1279 px) zostal PRZYWROCONY — tam uklad byl dobry i to ustawienie
uzytkownika.
