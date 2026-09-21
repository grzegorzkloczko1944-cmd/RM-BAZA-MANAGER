---
name: feedback-nic-po-cichu
description: ŻADNA zmiana danych nie może przejść po cichu — zawsze okno PRZED (co się zmieni) i raport PO (co zmieniono i na jaką wartość)
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 42739f9a-ed55-4c6c-a06d-d2bf1b97a8bf
  modified: 2026-09-08T20:04:44.700Z
---

Każda operacja zmieniająca dane (Subiekt, RM_BAZA, dowolny zapis) MUSI mieć:
1. **Okno PRZED zapisem** — jawnie wypisane, co dokładnie zostanie zmienione, na czym i z jakiej wartości na jaką.
2. **Raport PO zapisie** — co faktycznie zostało zmienione i na jaką wartość / na co.

Nie wystarczy pokazać liczby zbiorczej ani statusu typu "bez zmian" wyliczonego z niepełnego porównania. Jeśli kod porównuje tylko część danych (np. sam symbol, bez ilości), to raport jest **kłamliwy** — user widzi "bez zmian", a dane się zmieniają.

**Why:** Użytkownik zgłosił to wielokrotnie (06.09, 07.09, 08.09.2026 i ponownie po incydencie z "dodaj BOM" + zmianą ilości na ZK, gdzie okno pokazało "25 BEZ ZMIAN / dopisze 0 poz." mimo realnej zmiany ilości). Zapis idzie na BAZĘ PRODUKCYJNĄ i części zmian (kartoteki) nie da się łatwo cofnąć. User musi wiedzieć, co robi, ZANIM to zrobi — "USER nawet nie wie co zrobił" to stan niedopuszczalny.

**How to apply:** Przy każdej nowej funkcji zapisu i przy każdej poprawce istniejącej: sprawdź, czy porównanie stanu przed/po obejmuje WSZYSTKIE pola, które faktycznie się zapisują (nie tylko klucz/symbol). Jeżeli jakaś kategoria zmian nie ma reprezentacji w oknie potwierdzenia (brak kafelka, brak wiersza w tabeli) — to jest błąd do naprawienia, nawet jeśli sama operacja działa poprawnie. Wzorzec do naśladowania: obsługa kompletów w `Projekt.cs` (porównanie par symbol+ilość, status `do-aktualizacji`, `OpiszRoznice()`) oraz raport po zapisie w Edytorze kartotek (kolorowanie wg wagi zmiany). Patrz też [[project-zk-ilosci-nie-porownywane]].
