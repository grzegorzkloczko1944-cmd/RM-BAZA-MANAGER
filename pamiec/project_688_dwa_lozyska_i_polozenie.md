---
name: project_688_dwa_lozyska_i_polozenie
description: 688 wystepuje w DWOCH wersjach (8x16x5 EZO i 8x16x4 = 618/8) - rozdzielone na osobne kartoteki, katalog i modele 3D; przy okazji kolumna Polozenie w Edytorze kartotek i pola R/P
metadata:
  type: project
---

# 688: dwa różne łożyska pod jednym oznaczeniem (03.10.2026)

## Sedno

`688` występuje **w obu wersjach i obie są w obrocie**:

| | wymiary | co to |
|---|---|---|
| **688** (EZO) | 8×16×**5** | wersja uszczelniona ZZ/2RS — tę mamy na magazynie (70 szt.) |
| **618/8** (alias 688) | 8×16×**4** | wersja otwarta, norma ISO/Timken |

Katalog łożysk miał tylko `618/8` z aliasem `688` i uwagą **„B dla wersji
otwartej; ZZ/2RS bywa szersze"** — coworker przewidział ten przypadek już
28.09 ([[project_lozyska_katalog_28_09]]), gdzie zresztą „poprawił"
`688 ZZ` z 8x16x5 na 8x16x4 „wg katalogu Timken". To nie był jego błąd:
wtedy nie było wiadomo, że mamy obie wersje.

⚠️ Sprawdzone: rozjazd dotyczy **wyłącznie 688**. Pozostałe 69 aliasów
(683–687, 689…) zgadza się z normą — skrypt porównujący nazwę kartoteki
z katalogiem znalazł 4 rozjazdy, wszystkie na 688.

## Co zrobiono

**Kartoteki** — rozdzielone na dwa towary:
* `688 ZZ`, `688 2RS`, `SS 688 ZZ`, `SS 688 2RS`, `SS 688.ZZ` → nazwy `8x16x5`
* NOWE: `618/8 ZZ`, `618/8 2RS`, `SS 618/8 ZZ`, `SS 618/8 2RS` → `8x16x4`,
  nazwa z aliasem: „618/8 ZZ 8x16x4 (alias 688)". Bez dopisku „Łożysko
  Kulkowe Zwykłe" — to samo stoi w kolumnie Opis (uwaga usera).

**Katalog łożysk** — `688` jako 294. wpis, B=5, źródło „EZO (wersja ZZ/2RS)".
Alias `688` ZDJĘTY z `618/8`, żeby jeden symbol nie miał dwóch źródeł wymiarów.

⚠️ `lozyska_kulkowe.json` jest GENEROWANY z PDF-ów producentów przez
`zbuduj_katalog.py`, który nadpisuje cały plik. Dlatego wpis dodany w DWÓCH
miejscach: sekcja `WLASNE` w skrypcie (scalana po wczytaniu PDF-ów) i sam
JSON. Bez tego pierwsza przebudowa katalogu skasowałaby wpis.

Serwer wczytuje katalog **przy starcie** z `C:\Apps\RM_SERWER\katalog_lozysk\`
(NIE z repo na serwerze) — po wgraniu konieczny `Restart-Service RM_SERWER`.
Log potwierdza: „katalog łożysk: 294 pozycji".

**Modele 3D i miniatury** — procedurą coworkera:
1. Rendery w Inventorze przez COM (wzorzec
   `biblioteka_modeli/wzorce_kodu/decyzje_render_brakujace.py`): schemat
   „Prezentacja", `ViewOrientationType = 10759`, `SaveAsBitmap(600, 600,
   BIALY, BIALY)`, przywrócenie opcji w `finally`. 5 plików, 0 błędów.
2. `indeks_modeli_3d.odswiez_miniatury()` → „zapisano 1" (porównuje mtime).
3. Zdjęcia do Subiekta — 9 wysłanych, **4 nadpisane** przy 688 (stary render
   4 mm przedstawiał już inne łożysko). Zgoda usera, bo
   [[feedback_nadpisywanie_pytaj]] wymaga jej za każdym razem.
4. `subiekt_kopia_sync.py --miniatury-od-nowa` (~18 min, 2876 miniatur) —
   zwykła synchronizacja NIE dociąga ZMIENIONYCH zdjęć, tylko nowe kartoteki.

⚠️ `subiekt_lozyska_zdjecia.py` nie nadawał się dla 618/8: wyprowadza symbol
z NAZWY PLIKU, a „618/8" ma ukośnik, którego w nazwie pliku być nie może
(`618-8 ZZ 8x16x4.png` → symbol „618-8 ZZ" ≠ „618/8 ZZ"). Użyty jednorazowy
skrypt z JAWNYM mapowaniem plik→symbol.

## AKTUALIZACJA 03.10.2026 wieczorem: 618/8 USUNIETE CALKOWICIE

Decyzja uzytkownika: **zostaje wylacznie 688 = 8x16x5**. Wersja otwarta
8x16x4 nie jest w obrocie, a dublowanie oznaczenia tylko mylilo.

Usuniete:
* 4 kartoteki `618/8 ZZ`, `618/8 2RS`, `SS 618/8 ZZ`, `SS 618/8 2RS`
  (`kartoteka-usun`; byly nieuzywane — 0 dokumentow, 0 kompletow);
* wpis `618/8` z katalogu lozysk (294 -> 293) + alias;
* 4 powiazania modeli 3D (`/mag/model3d/usun`);
* 4 rendery `618-8*.png` z `C:\iLogic\LOZYSKA\miniatury`;
* 4 pliki `.ipt` 8x16x4 z `B:\...\gotowe` i 4 miniatury z `B:\...\miniatury`.

⚠️ `zbuduj_katalog.py` ma teraz `POMIJAJ = {"618/8"}` — bez tego wpis
WROCILBY przy pierwszej przebudowie katalogu, bo w PDF-ach Timkena jest
norma. Lista dziala tez na aliasach.

⚠️ ZOSTALY cztery stare rendery `688*8x16x4.png` w `C:\iLogic\LOZYSKAminiatury` (to INNY katalog niz `B:\...\miniatury`). Stamtad czyta
`subiekt_lozyska_zdjecia.py`, wiec jego uruchomienie wgraloby stare zdjecia
4 mm pod symbole 688. Do usuniecia przy okazji.

Stan koncowy: na `B:` tylko `688 ZZ 8x16x5.ipt`, w katalogu jeden wpis
`688` = 8x16x5, w MAG zero kartotek z 8x16x4.

## Czego NIE zrobiono

* `SS 688.ZZ` ma puste `Wymiary` — kropka w symbolu nie pasuje do wzorca
  dopasowania w katalogu. To ten sam towar co `SS 688 ZZ` (stany 30 i 0) —
  duplikat do scalenia albo usunięcia.
* Model `688 ZZ 8x16x5.ipt` przypięty TAKŻE do wariantów 2RS — geometria ta
  sama, różni się uszczelnienie (decyzja usera: „do wszystkich pięciu").
* Pliki modeli 4 mm nazywają się nadal „688…", choć należą do 618/8.

## Mój błąd w tej sesji — do zapamiętania

Zanim user podał EZO, „poprawiłem" cztery kartoteki z `8x16x4` na `8x16x5`,
biorąc za wzorzec JEDNĄ kartotekę (`SS 688.ZZ`). Nie sprawdziłem wcześniej
modeli 3D ani szeregu 685–689, choć były pod ręką i pokazywały `4`. To była
zmiana danych produkcyjnych oparta na założeniu — **pytać PRZED zapisem,
nie po**. Skończyło się dobrze tylko dlatego, że oba warianty istnieją.

Powiązane: [[project_lozyska_katalog_28_09]] [[project_regal_z_opisu_migracja]]
