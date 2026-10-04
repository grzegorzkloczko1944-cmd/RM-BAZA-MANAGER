---
name: project_rm_manager_czytanie_w_pakiecie
description: RM_MANAGER — przegląd odczytów „w pakiecie" 04.10.2026 (Kadry, lista projektów, Multi-projekt, oś czasu): co było seryjne, co zastąpione zbiorczym odczytem, zmierzone i porównane; skaner AST do szukania pytań serwera w pętlach; co zostało
metadata:
  type: project
---

User 04.10.2026: „Kadry długo się ładują", „Multi projekt też się długo
odpala", „czytanie w RM_MANAGER jest bardzo nieoptymalne". Zasada z CLAUDE.md:
odczyt hurtem, nie pętla z pytaniem na wiersz.

## Jak szukać (powtarzalne)

Skaner AST (jednorazowy skrypt): zbiera funkcje `rm_manager.py`, które
pośrednio wołają `rmm_read/rmm_exec/rmm_batch/master_read`, i zgłasza ich
wywołania WEWNĄTRZ pętli/comprehension w `rm_manager_gui.py`. 04.10: 77
trafień w 47 funkcjach. ⚠️ Fałszywe alarmy: `for x in rmm.get_employees(...)`
(iterator liczony raz) — trzeba obejrzeć każde. Potem MIERZYĆ: licznik
podpięty pod `rm_klient.master_read` + czas, i porównać wynik starej i nowej
ścieżki (JSON / pole po polu) na żywych danych.

## Naprawione (wszystko porównane: 0 różnic)

| miejsce | było | jest |
|---|---|---|
| Kadry → Rozliczenie, karta pracownika | 218 zapytań, ~3 s | 7, 0,1 s |
| Kadry → Pula urlopu | 4 zapytania/osobę, ~2 s | 2, 0,03 s |
| Kadry → kalendarz zespołu | nieobecności + dni robocze per rysowany miesiąc | raz na odświeżenie |
| Kadry → otwarcie okna | 7 zakładek budowanych od razu, kalendarz 2× | leniwie, kalendarz 1× |
| Lista projektów (`projects_list_dialog.reload`) | 5–6 zapytań/projekt | statusy, status procesu, locki, transze zbiorczo przed pętlą |
| Multi-projekt → selektor projektów | status per projekt, 62× = 1,6 s | `get_all_project_statuses` raz |
| Multi-projekt → wykres | transze per zakończony projekt | zbiorczo przy pierwszej potrzebie |
| Oś czasu (`refresh_timeline`) | pracownicy etapu per wiersz (~25 otwarć pliku + 25 zapytań), transze do 3× | `get_stage_assigned_staff_wszystkie` raz, transze raz |
| Ikona statusu na wykresach | `get_project_status` per projekt | bufor 5 s z `get_all_project_statuses` |

Nowe operacje serwera: `rmm-employee-vacation-base-wszystkie`,
`rmm-employee-vacation-quota-wszystkie`, `rmm-carryover-wszystkie`,
`statusy-projektow-wszystkie` (+ już istniejące `projects-statusy`,
`rmm-payment-milestones-wszystkie`, `rmm-locki-wszystkie`). Każde miejsce ma
fallback do starej ścieżki, gdy serwer nie zna operacji („nieznana operacja")
— nowa RM_MANAGER działa ze starym serwerem, tylko wolniej.

`get_stage_assigned_staff_wszystkie(pdb, pid)` — 899 etapów w 62 projektach
identycznie jak wersja per etap; lokalnie 3,1 s → 0,6 s, na udziale więcej.

## Druga runda (04.10, „poprawiaj")

| miejsce | było | jest |
|---|---|---|
| **Plan serwisantów** (`_collect_service_stages`) | 531 otwarć baz projektów + 60 zapytań, 1,6 s lokalnie (w firmie przez sieć — „długie sekundy") | 64 otwarcia, 0 zapytań, 0,11 s; 63 wpisy planu IDENTYCZNE |
| Selektor Multi-projekt | 5 otwarć bazy na projekt (pauza ×2, prognoza, aktywne etapy, pauzy) | `podsumowanie_projektu_lekkie` — 1 otwarcie; ocena terminów wspólna `_ocena_terminow` |
| Starszy Gantt multi-projekt | 4 otwarcia na projekt | 1 (`_get_stage_timeline_with_con` + `get_stage_assigned_staff_wszystkie(con=)` + SAT na tym samym połączeniu) |
| `refresh_timeline` | blok DEBUG otwierał bazę i drukował przy każdym odświeżeniu | usunięty |

Nowe w `rm_manager.py`: `id_pracownikow_etapow(con, pid)` — same numery, bez
serwera (plan i tak przecina z listą serwisantów; różnica wobec wersji
z nazwiskami tylko gdy lista serwisantów pusta — numer nieistniejącego
pracownika nie zostałby odsiany). `get_stage_assigned_staff_wszystkie`
przyjmuje opcjonalne `con`. ⚠️ Porównując prognozy: `forecast_end` liczone od
„teraz" różni się o mikrosekundy między wywołaniami — to nie różnica.

## Zostało

- `send_plc_code`, `send_payment_status` — jeden projekt / kilka maszyn
  linii, zysk znikomy, świadomie nie ruszane.
- Formularz nieobecności liczy dni przy każdym znaku.

Powiązane: [[project_urlopy_saldo_godzin]], [[project_zapotrzebowanie_szybkie]].
