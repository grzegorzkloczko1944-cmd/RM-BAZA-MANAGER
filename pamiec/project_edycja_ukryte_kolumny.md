---
name: project_edycja_ukryte_kolumny
description: Edycja komórki z ukrytymi kolumnami trafiała w złe pole (ODEBRANE -> Uwagi) — sztywne `col >= 16 -> +1` zamienione na _kolumna_danych
metadata:
  type: project
---

# Edycja w arkuszu a ukryte kolumny (05.10.2026)

**Objaw:** „w ODEBRANE nic nie mogę wpisać". Wpis znikał po odświeżeniu.

**Przyczyna:** `on_cell_edited` przeliczał kolumnę widoku na kolumnę danych
sztywno (`if col >= 16: col += 1`), czyli zakładał, że ukryta jest tylko
DWF_BIB. User miał w menu „🧱 Kolumny" ukryte także ALARM (14) i Moduł (18).
Skutki:
* ODEBRANE (widok 15) → zapis do **Uwag**,
* Uwagi (widok 14) → zapis do **ALARM**,
* każda edytowalna kolumna za ukrytą przesunięta o jedną w lewo.

Ten sam schemat siedział w `on_restore_to_bom` i w dymku kolumn BOM
(`on_sheet_left_click`). Wszystkie trzy przeszły na `self._kolumna_danych(col)`
(`sheet.data_c`), z którego obsługa kliknięć korzystała już od 10.09.

**Zasada:** indeks z `get_currently_selected()` / `identify_column` to
indeks WIDOKU. Zawsze przepuszczać go przez `_kolumna_danych`, nigdy przez
stałe przesunięcie. `get_cell_data(row, col)` bierze indeks DANYCH.

**Do sprawdzenia:** w projektach edytowanych z ukrytymi kolumnami w Uwagach
lub ALARM-ie mogły wylądować wpisy przeznaczone dla sąsiedniej kolumny.

Powiązane: [[project_odebrane_notatka_ilosc]]
