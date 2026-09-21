---
name: project_tksheet_indeksy_kolumn
description: tksheet - indeks WIDOKU vs indeks DANYCH przy ukrytych kolumnach, dwa bledy tej samej rodziny
metadata:
  type: project
---

W arkuszu głównym RM_BAZA kolumny mają **stałe indeksy w danych** (`WYCENA_COL=19`, `SUBIEKT_COL=20`, `CASTING_COL=21`), ale tksheet operuje na indeksach **widoku** — a te przesuwają się przy każdej ukrytej kolumnie. DWF_BIB (16) jest ukryta zawsze, menu „🧱 Kolumny" pozwala ukryć dowolne inne.

**Dwa błędy tej samej rodziny, oba 2026-09-10:**

1. **Znikała kolumna WYCENA** (`13909e1`) — `hide_columns()` ma domyślnie `data_indexes=False`, czyli liczy w widoku. Po ukryciu DWF_BIB kolejne `hide_columns(19)` trafiało obok. Naprawa: `data_indexes=True` + reset do pełnego stanu (`show_columns` na całym zakresie) przed ukrywaniem.

2. **Klik w WYCENA nie otwierał RFQ** (`e21b527`) — obsługa kliku miała sztywne `if col >= 16: col += 1`, zakładające jedną ukrytą kolumnę. Przy trzech ukrytych klik w WYCENA liczył się jako 17 (SUBIEKT). Naprawa: metoda `_kolumna_danych()` używająca `sheet.data_c()`.

**Zasada:** nigdy nie licz przesunięcia ręcznie. Do konwersji widok→dane służy `sheet.data_c(c)`, do ukrywania `hide_columns(..., data_indexes=True)`. `show_columns()` nie ma tego parametru — zawsze bierze indeksy danych.

**How to apply:** przy każdym nowym kodzie reagującym na kliknięcie w kolumnę arkusza użyć `self._kolumna_danych(col)`. Jeśli coś „działa tylko gdy wszystkie kolumny widoczne" — to jest ten błąd.
