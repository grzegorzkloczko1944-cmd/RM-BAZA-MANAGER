---
name: project_aktualizacja_bom_zmiana_numeru
description: Aktualizacja BOM dopasowuje takze po src_drawing_no - bez tego zmiana numeru w arkuszu tworzyla duble
metadata:
  type: project
---

# Aktualizacja BOM a reczna zmiana numeru rysunku

Zgloszone 02.10.2026, projekt 2637 (baza `project_75.sqlite`): user poprawil
w arkuszu `HGH15SO` -> `HGH15SOK` i `HGW15SO` -> `HGW15SOK`, potem zrobil
„Aktualizacja BOM". Nazwy sie NIE zmienily, za to doszly DWA NOWE wiersze —
duble (5 pozycji -> 7).

## Przyczyna

`menu_aktualizuj_bom` budowala slownik istniejacych pozycji po kluczu
`COALESCE(NULLIF(work_drawing_no,''), src_drawing_no)` — czyli po nazwie
**AKTUALNIE widocznej w arkuszu**.

Reczna edycja numeru zapisuje sie do `work_drawing_no`, a `src_drawing_no`
trzyma oryginal z importu. Po zmianie wiersz stal w slowniku pod `HGH15SOK`,
a plik XLSX nadal mial `HGH15SO` — pod ta nazwa nie bylo juz nic, wiec
aktualizacja uznala to za NOWA pozycje i dopisala obok.

⚠️ To nie byl przypadek brzegowy: **kazda** zmiana numeru rysunku w arkuszu
rozjezdzala nastepna aktualizacje BOM.

## Naprawa (dwie czesci, obie konieczne)

**1. Klucz zapasowy** — `src_drawing_no` dopisany jako alias w
`existing_items`, obok klucza glownego. Stary numer z pliku trafia wtedy we
wlasciwy wiersz i user dostaje dialog porownania zamiast dubla. Alias NIE
nadpisuje klucza glownego: gdy pod stara nazwa stoi pozycja, ktora NAPRAWDE
tak sie teraz nazywa, zostaje ona.

**2. Reczna nazwa wygrywa z plikiem** (`_auto_accept_conflict`) — dla pola
`drawing_no` bierzemy `current_val`, nie `new_val`. Bez tego punkt 1 zalatwilby
duble, ale kazdy import COFALBY poprawke usera i poprawialby on ja w kolko.
Decyzja uzytkownika z 02.10.2026: „zachowaj moja nazwe". Reszta kolumn
(ilosci, material, opis) idzie z pliku jak dotad.

## Narzedzie do juz powstalych dubli

`narzedzia_duble_po_zmianie_numeru.py <nr_projektu> [--zapisz]`

Suchy przebieg domyslnie. Szuka par: wiersz z `work_drawing_no != src_drawing_no`
plus wiersz dopisany pod tym `src_`. Ostrzega, gdy dubel ma juz ZAMOWIONO,
DOSTARCZONO albo UWAGI — wtedy kasowanie nie jest bezobslugowe.

⚠️ Czyta baze NA SERWERZE. Gdy projekt jest przejety lockiem, zmiany siedza
w kopii lokalnej (`C:/RMPAK_CLIENT/project_<id>.sqlite`) i narzedzie ich NIE
WIDZI — 02.10.2026 raport dla 75 wyszedl pusty wlasnie dlatego, ze duble
nie byly jeszcze zapisane na serwer. Najpierw zwolnij lock.

Powiazane: [[project_zapis_do_bazy_projektu]]

## SPROSTOWANIE: duble w 2637 pochodzily z ZK, nie z aktualizacji BOM

Pierwsza diagnoza byla NIEPELNA. Wiersze-duble (id 2655, 2656) mialy
`is_manual=1` i `notes='z zamowienia ZK'` — utworzyla je
`_dopisz_pozycje_z_zk`, nie import z pliku.

Mechanizm (uwaga uzytkownika: „dla Subiekta nic sie nie zmienilo, to dalej
ten sam detal"):

1. User zmienia w arkuszu `HGH15SO` -> `HGH15SOK` (zapis do `work_drawing_no`)
2. **`subiekt_symbol` zostaje STARY** — zmiana nazwy w arkuszu go NIE rusza
3. W Subiekcie na ZK/ZD/RW figuruje juz `HGH15SOK`
4. `_zapisz_ilosci_z_subiekta` dopasowuje po kluczu `subiekt_symbol or numer`
   — w arkuszu widzi `HGH15SO`, na ZK jest `HGH15SOK`, NIE TRAFIA
5. `_dopisz_pozycje_z_zk` uznaje `HGH15SOK` za pozycje z ZK bez wiersza
   w arkuszu i dopisuje NOWY wiersz

⚠️ Duble z tego zrodla maja `work_drawing_no` I `src_drawing_no` PUSTE —
nazwa siedzi wylacznie w `subiekt_symbol`. Zapytania szukajace po numerze
rysunku ich NIE WIDZA (02.10.2026 pierwsze trzy proby wyszly puste).

## Co z tego wynika dla naprawy

Klucz zapasowy w aktualizacji BOM musi obejmowac **`subiekt_symbol`**, nie
tylko `src_drawing_no`: w projekcie 75 az **70 z 331** wierszy ma
`src_drawing_no` puste (pozycje dopisane wprost z kartoteki — wozki Hiwin,
lozyska, pasy). Dla nich `subiekt_symbol` to jedyny slad starej nazwy.

## Naprawa danych w 2637 (02.10.2026)

Scalenie, nie kasowanie — oryginaly maja Opis, Typ, dostawce ORION i powiazanie
z BOM-em, duble mialy tylko ilosc:

    id=2649 : work_drawing_no I subiekt_symbol -> HGH15SOK, usuniete id=2655
    id=2601 : work_drawing_no I subiekt_symbol -> HGW15SOK, usuniete id=2656

⚠️ Pierwsze podejscie ustawilo TYLKO `subiekt_symbol`, a `work_drawing_no`
zostawilo stare — arkusz dalej pokazywal HGH15SO, choc w Subiekcie detal
nazywa sie HGH15SOK. Uzytkownik: „odwrotnie mialo byc, SOK zostaje".
Przy scalaniu po zmianie nazwy poprawiaj OBA pola — widoczny numer i symbol.

Ilosci sie zgadzaly (5=5, 2=2), `delivered_qty` byly zerowe. Kopia zapasowa:
`project_75_przed_scaleniem_20261002_1519.sqlite` na udziale.

⚠️ W Subiekcie istnieja OBIE kartoteki (`HGH15SO` i `HGH15SOK`, obie
„dopasowanie=dokladne"), ale na dokumentach (ZD 6/09, ZD 43/09, RW 145/09,
RW 9/10) wystepuje WYLACZNIE wersja SOK. Stara kartoteka zostala osierocona.

## ZASADA NA PRZYSZLOSC

Zmiana numeru rysunku w arkuszu NIE zmienia `subiekt_symbol`. Gdy detal ma
w Subiekcie inna nazwe, trzeba poprawic OBA pola — inaczej kazdy „Przelicz"
z ZK dopisze dubla. Rozwazyc, czy edycja numeru nie powinna proponowac
aktualizacji `subiekt_symbol` razem z nim.
