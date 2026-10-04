---
name: project_urlopy_saldo_godzin
description: Urlopy — część dnia (pół dnia, kilka godzin) NIE schodzi z puli, tylko wisi na SALDZIE GODZIN; zdejmuje je odpracowanie albo po 8 h dzień urlopu; kalendarz zespołu: kratka do połowy (04.10.2026)
metadata:
  type: project
---

Decyzje usera 04.10.2026 (RM_MANAGER → Kadry → Urlopy):
- „pracownicy biorą pół dnia urlopu lub kilka godzin, potem dobierają innego
  dnia lub odpracowują"
- **godziny nie liczą się do żadnych urlopów** — wiszą „w powietrzu"; dopiero
  gdy nazbiera się cały dzień, kadrowa wydaje na ten dzień urlop
- odpracowanie odejmuje z salda; rozliczane **w dowolnym terminie** (bez
  terminu, bez czerwonego „po terminie")
- kalendarz zespołu: nieobecność od godziny w górę (krótsza niż cały dzień)
  → kratka świeci się **do połowy**

## Model

- Typ nieobecności **`GODZINY`** („Godziny (saldo)", `counts_as_vacation=False`)
  w `employee_availability`, wymaga godzin od–do (jednodniowy).
- Tabela **`employee_godziny_rozliczenia`** (serwer, MIGRACJE_RM_MANAGER):
  `rodzaj` = `ODPRACOWANIE` (dowolne h) | `URLOP` (8 h = 1 dzień z puli
  w roku `date`). Osobna tabela, NIE wpis w availability — to nie
  nieobecność (kalendarz/optymalizator/konflikty by ją źle czytały).
- Saldo = Σ h wpisów GODZINY (bez ODRZUCONY; OCZEKUJE się liczy) −
  Σ rozliczeń. Cała historia, nie rok. `get_saldo_godzin()` — dwa odczyty
  dla całego zespołu; `_urlop_z_godzin()` dolicza dni „URLOP" do
  wykorzystanego urlopu (także zaległego z ub. roku).
- Operacje serwera: `rmm-godziny-rozliczenia-wszystkie`,
  `rmm-godziny-rozliczenie-dodaj`, `rmm-godziny-rozliczenie-usun-po-id`.
  Stary serwer → `get_godziny_rozliczenia` zwraca [] (nie wyjątek).

## GUI

- Formularz nieobecności: przyciski **½ rano / ½ po południu**
  (`DZIEN_PRACY_OD/DO`, `POL_DNIA_GODZ` = 07:00/15:00/11:00 — założone,
  NIE z konfiguracji). Godziny przy typie urlopowym → pytanie i zapis jako
  GODZINY (część dnia nigdy nie schodzi z puli).
- Rozliczenie: kolumny **🟢 Z godzin** i **Saldo godz.**, „Pozostało"
  w dniach + godzinach (`fmt_dni_godz`), pomarańczowy wiersz przy saldzie
  ≥ 8 h, przycisk **⏱ Saldo godzin** → `_vacation_saldo_godzin`
  (godziny wzięte | rozliczenia, Odpracowanie, Rozlicz 8 h dniem urlopu —
  aktywny od 8 h, Usuń rozliczenie). CSV z nowymi kolumnami.
- Kalendarz zespołu: komórka `(code, st, czesc)`; część dnia = kolor w dolnej
  połowie kratki, dymek „Część dnia: 07:00–11:00 (4 h)"; przy tym samym
  statusie cały dzień wygrywa z częścią.

## Otwarte

- **Optymalizator** blokuje pracownikowi CAŁY dzień przy każdej
  nieobecności, także godzinowej (solver liczy w dniach). User 04.10.2026:
  **„zostawić tak"** — świadoma decyzja, nie zmieniać bez pytania.
- Blokada nakładania nie pozwala na dwa wpisy tego samego dnia (np. ½ rano
  GODZINY + delegacja po południu).
- ~~`get_vacation_report` pyta serwer per pracownik~~ — NAPRAWIONE 04.10
  („strasznie długo się ładuje kartoteka pracownika", „za dużo czyta się
  szeregowo"): raport w pakiecie — 7 odczytów zamiast 218, 3 s → 0,1 s,
  wynik IDENTYCZNY ze starą wersją na 2025/2026/2027 (porównane JSON-em).
  Nowe operacje: `rmm-employee-vacation-base-wszystkie`,
  `rmm-employee-vacation-quota-wszystkie`, `rmm-carryover-wszystkie`; stary
  serwer → `_get_vacation_report_seryjnie`. Karta pracownika woła raport
  z `employee_id`. `dni_nieobecnosci_hurtem()` (jeden odczyt kalendarza)
  zamiast `_count_absence_days` w pętli: karta → Nieobecności, Historia
  pracownika, karta urlopowa PDF, eksport Excel (23 wpisy: 0,54 s → 0,004 s).
  ⚠️ Pułapka testu: `_count_absence_days(..., rm_master_db_path=None)` liczy
  dni KALENDARZOWE — okno zawsze podaje ścieżkę, więc porównywać z niepustą.
- Formularz nieobecności dalej liczy dni przy każdym znaku (2 zapytania na
  klawisz) — nie ruszane.
- **Otwieranie okna Kadry (04.10, „długo się ładuje")**: zakładki budowane
  LENIWIE (`vacation_dialog`: kalendarz od razu, reszta przy pierwszym
  wejściu; obsługa zmiany zakładki podpinana `after_idle`, bo pierwsze
  zdarzenie po otwarciu ładowało kalendarz drugi raz). Kalendarz: nieobecności
  i kalendarz firmy czytane RAZ na odświeżenie (`cal['avail_all']`,
  `cal['kal']`, kasowane w `_full_reset`) zamiast per rysowany miesiąc
  (4 miesiące na start = 8 zapytań + każdy scroll). Pula urlopu:
  `get_pule_urlopowe()` — 2 odczyty zamiast 4 na osobę (~2 s → 0,03 s,
  wynik identyczny 2025–2027). `dni_robocze_lista()` = get_working_days
  w pamięci (zgodne na 5 zakresach, w tym przełom roku).
- PDF zestawienie/karta urlopowa — bez nowych kolumn.

Powiązane: [[project_urlopy_block]], [[project_kadry_module]], [[project_urlopy_dni_robocze]].
