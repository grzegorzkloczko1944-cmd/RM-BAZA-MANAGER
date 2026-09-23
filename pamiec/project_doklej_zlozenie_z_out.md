---
name: project_doklej_zlozenie_z_out
description: "WDROZONE 23.09.2026: pozycja menu „Doklej zlozenie z OUT…" — dokleja biblioteczne poddrzewo; korzen NIE sumowany, skladniki sumowane, modul w formacie MODUL(ilosc) jak Import modul"
metadata:
  node_type: memory
  type: project
---

**Ustalone 23.09.2026 na zywych danych (projekt 2637 + elewatory EWTR-820).
Kodu NIE MA — ponizej gotowa specyfikacja.**

## Po co

Doklejenie bibliotecznego poddrzewa z osobnego `*_OUT.xlsx` w miejsce
pustego zlozenia. Zadna z 4 istniejacych funkcji tego nie robi poprawnie —
kazda ma inna wade (pomiary nizej).

## Dlaczego istniejace nie wystarczaja — POMIAR

Test na 2637 + `EWTR-820.00ZZ Elewator L_OUT.xlsx`:

| funkcja | korzen `EWTR-820.00ZZ` | czesc wspolna `011-100.67` |
|---|---|---|
| Import BOM | ⛔ KASUJE caly projekt | — |
| Aktualizuj BOM | ✅ zostaje 1 | ⛔ 5 zamiast 10 (bierze z pliku) |
| **Dodaj BOM** | ⛔ 1+1 = **2** | ✅ 5+5 = 10 |
| Import modul | (nie testowane) | sumuje + modul z iloscia |

**Sedno problemu:** korzen elewatora jest ZARAZEM pozycja w BOM-ie projektu
(jako puste zlozenie) I pierwszym wierszem w OUT-cie biblioteki. Kazda
funkcja sumujaca liczy go podwojnie.

⚠️ Korzen MUSI zostac w BOM-ie — `build_plan` zaklada komplet iterujac po
`items` po typie Z/ZZ ([subiekt_projekt.py:1114](../subiekt_projekt.py#L1114)).
Usuniecie korzenia = brak kompletu w Subiekcie, skladniki wisza luzem.
**Nie kombinowac z wycinaniem wiersza z pliku OUT.**

## Co ma robic (decyzje usera)

1. **Osobna pozycja w menu Plik: „Doklej zlozenie z OUT…"** — nie checkbox
   w „Dodaj BOM" (decyzja 23.09.2026).
2. **Korzen (`len(sciezka)==1`) → NIE sumowac** ilosci; zostawic wartosc
   z BOM-u projektu.
3. **Skladniki (`len(sciezka)>1`) → sumowac** (jak Dodaj BOM).
4. **Modul w formacie `MODUL(ilosc)`**, po przecinku przy wielu —
   jak „Import modul": `100(5), 820(5)`.

## Z czego zlozyc (NIE pisac od zera)

| element | zrodlo |
|---|---|
| szkielet automatu bez dialogow | `menu_dodaj_bom` ([RM_BAZA…:19725](../RM_BAZA_v15_MAG_STATS_ORG.py#L19725)) |
| **przelacznik sumowania** | flaga `sum_quantities` w `new_data` ([linia 20063](../RM_BAZA_v15_MAG_STATS_ORG.py#L20063)) → `_auto_accept_conflict` czyta ja jako `sum_mode` ([18892](../RM_BAZA_v15_MAG_STATS_ORG.py#L18892)) |
| **modul z iloscia** | `concatenate_modul()` ([20596](../RM_BAZA_v15_MAG_STATS_ORG.py#L20596)) — format `MODUL(n)`, dopisywanie po przecinku; pole `modul_merged` w `new_data` ([20869](../RM_BAZA_v15_MAG_STATS_ORG.py#L20869)) |
| rozpoznanie korzenia | `find_assembly_tree_rows()` → korzen to jedyny wiersz `len(sciezka)==1` |
| mnoznik ilosci | `simpledialog.askinteger` w `menu_dodaj_bom` (~19747) |

**Klucz:** `sum_quantities` ustawiac **per wiersz** — `False` dla korzenia,
`True` dla reszty. Dzis obie funkcje ustawiaja ja globalnie dla calego pliku.
To jest CALA roznica; reszta mechanizmu juz dziala.

`modul_merged` ma pierwszenstwo w `_auto_accept_conflict` ([18910](../RM_BAZA_v15_MAG_STATS_ORG.py#L18910))
i ZAWSZE idzie do `work_modul` ([18982](../RM_BAZA_v15_MAG_STATS_ORG.py#L18982)).

## Obejscie HISTORYCZNE (bylo potrzebne zanim powstala funkcja)

„Dodaj BOM" dla obu plikow (mnoznik 1), potem **recznie poprawic ilosc
dwoch korzeni** `EWTR-820.00ZZ` i `EWTR-820.45ZZ` z 2 na 1.
To zmiana LICZBY, nie usuwanie pozycji — struktura kompletu idzie z drzewka
(`kids`), a `ilosci_z_drzewa` przelicza ilosci od nowa. Subiekt sie nie rozjedzie.

Wad: 2 poprawki (Dodaj BOM) vs 38 (Aktualizuj BOM — wszystkie czesci wspolne L∩P).


## Jak to zrobiono (stan po wdrozeniu)

**Menu Plik → „Doklej zlozenie z OUT…"** (miedzy „Dodaj BOM…" a „Import modul…").

| plik | co |
|---|---|
| `doklej_zlozenie.py` | `znajdz_korzen_drzewka()` — korzen to jedyny wiersz o `len(sciezka)==1` w „DRZEWKO TEKST"; `scal_moduly()` — format `100, 820(5)`, NIE dopisuje tego samego modulu dwa razy |
| `menu_doklej_zlozenie` | klon `menu_dodaj_bom`; jedyna roznica merytoryczna: `'sum_quantities': not jest_korzeniem` zamiast `True` |

⚠️ **Przy okazji naprawione:** menu wlaczalo sie po INDEKSACH liczbowych
(`entryconfig(3, …)`) — dolozenie pozycji w srodku przesunelo wszystkie
kolejne i „Import modul" zamienilby sie miejscami z „Aktualizuj ilosci".
Przepisane na wyszukiwanie po ETYKIECIE, wiec nastepna zmiana menu tez
sie nie rozjedzie.

**Plik bez arkusza „DRZEWKO TEKST"** → funkcja odmawia z wyjasnieniem,
zamiast po cichu zsumowac korzen (bez korzenia nie wiadomo, czego nie sumowac).

### Test na kopii project_72 (przed wdrozeniem)

| pozycja | przed | po | ocena |
|---|---|---|---|
| `EWTR-820.00ZZ` (korzen L) | 1 | **1** | nie zsumowany |
| `EWTR-820.45ZZ` (korzen P) | 1 | **1** | nie zsumowany |
| `011-100.67` (czesc wspolna) | 5 | **10** | zsumowana 5+5 |
| pozycji razem | 277 | 352 | +75 |
| duplikaty numerow | — | BRAK | |

Drugi plik pokazal obie sciezki naraz: 16 nowych + 38 zsumowanych + 1 korzen pominiety.

## Uwagi

- Modul nowych pozycji wchodzi dzis jako `820` z kolumny „Katalog" pliku.
  Nowa funkcja ma dawac `100(n), 820(n)` — moduł wezla w projekcie + biblioteczny.
- Format wielomodulowy JEST juz uzywany w 2637: `200,500` i `200,400`.
- Zmiana dotyka RM_BAZA na produkcji — testowac na M-OLD
  ([[project_srodowisko_domowe_m_old]]).

Patrz [[project_drugi_out_uzupelnia_drzewo]] (mechanizm sklejania drzewek,
pomiary korzeni), [[project_subiekt_zk_komplety]], [[feedback_nic_po_cichu]].
