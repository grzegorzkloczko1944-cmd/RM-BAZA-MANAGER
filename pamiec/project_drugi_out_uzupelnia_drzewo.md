---
name: project_drugi_out_uzupelnia_drzewo
description: "DO ZROBIENIA W DOMU: doklejanie drugiego pliku OUT w miejsce pustego zlozenia bibliotecznego; ilosci sie mnoza przez krotnosc wezla"
metadata:
  node_type: memory
  type: project
---

**Zadanie zglosozne 23.09.2026, do zrobienia W DOMU (M-OLD).** Kodu NIE MA —
ponizej ustalenia i rozpoznanie, zeby nie zaczynac od zera.

## Problem

Projekt ma juz zaciagniety jeden plik `*_OUT.xlsx`. Jeden z jego podzespolow
to zlozenie **z biblioteki** — w pierwszym OUT jest PUSTE (lisc bez skladu),
bo jego rozwiniecie siedzi w **drugim, zupelnie innym pliku OUT**.

Cel: drugim OUT-em **uzupelnic drzewo** — wkleic jego zawartosc jako
poddrzewo pod pustym wezlem.

> „ilosci sie mnoza. Po prostu tym OUT uzupelniam drzewo."

Czyli gdy pusty wezel wystepuje w pierwszym drzewku 3×, skladniki z drugiego
OUT wchodza w ilosciach ×3.

## Co JUZ DZIALA (nie pisac od nowa)

| co | gdzie |
|---|---|
| czytanie drzewka z OUT | `import_bom.find_assembly_tree_rows()` — arkusz **„DRZEWKO TEKST"**, kolumny `Poziom`, `Nr rysunku`, `Nazwa`, `Ilość lokalna`, `Ilość całkowita`, `Typ`, `Ścieżka` |
| hierarchia | pole `sciezka` = lista segmentow od korzenia, rozdzielana `>` — zagniezdzenie wynika z DLUGOSCI sciezki, nie trzeba go liczyc |
| szukanie zlozenia detalu | `import_bom.find_assembly_for_drawing()` → zwraca `row`, `all_rows`, `parent_drawing_no` |
| okno drzewka w RM_BAZA | `RM_BAZA_v15_MAG_STATS_ORG.py` ok. 16321 (`ttk.Treeview`) |
| drzewko w edytorze kartotek | `subiekt_edytor_gui.py` ok. 3373 |
| **rozpoznanie pustych zlozen** | `subiekt_projekt.build_plan` → `bib_bez_skladu` → okno „⛔ Decyzje"; etykieta `[biblioteka B:\]` vs `[projekt — brak w *_OUT.xlsx]` |

`find_assembly_tree_rows` czyta DOWOLNY plik OUT — drugi obsluzy tak samo
jak pierwszy. Nowy parser NIE jest potrzebny.

## Plan (uzgodniony kierunek)

Dzis okno „⛔ Decyzje" ([[project_subiekt_puste_zlozenia_decyzje]]) daje dla
takiego zlozenia DWA wyjscia: „zaloz bez skladu" / „pomin". Dolozyc **trzecie:
wskaz plik OUT z rozwinieciem**.

Po wskazaniu:
1. `find_assembly_tree_rows(drugi_out)` — wiersze poddrzewa;
2. **przedluzyc sciezki** o sciezke wezla-rodzica z pierwszego drzewka
   (inaczej hierarchia sie nie sklei);
3. **pomnozyc ilosci** przez krotnosc wezla w drzewie nadrzednym;
4. dalej bez zmian — komplety w Subiekcie ida istniejaca droga
   ([[project_subiekt_zk_komplety]]).

To jedna opcja w istniejacym oknie + funkcja sklejajaca dwa zestawy wierszy.
NIE osobny modul.

## ⚠️ Do rozstrzygniecia na miejscu (pytania bez odpowiedzi)

- **Po czym poznac, ze drugi OUT pasuje do tego wezla?** Hipoteza: korzen
  drugiego drzewka ma TEN SAM `Nr rysunku` co pusty wezel. Sprawdzic na
  prawdziwym pliku i ostrzegac, gdy sie nie zgadza.
- **Czy zapamietywac wybor pliku?** Dzis decyzje zyja tylko w pamieci okna
  (`_bib_decyzje`) i gina po zamknieciu. Biblioteczny zespol wroci w kolejnym
  projekcie — warto zapisac powiazanie `numer rysunku → plik OUT`.
- **Ktora ilosc mnozyc** — `ilosc_lokalna` czy `ilosc_calkowita`? Obie sa
  w wierszu; ustalic, zeby nie policzyc podwojnie.

## Na start w domu

Potrzebny **prawdziwy drugi plik OUT** + numer rysunku pustego zlozenia,
zeby sprawdzic zalozenie o pokrywajacych sie korzeniach.

Patrz [[project_subiekt_puste_zlozenia_decyzje]], [[project_subiekt_zk_komplety]],
[[project_srodowisko_domowe_m_old]].
