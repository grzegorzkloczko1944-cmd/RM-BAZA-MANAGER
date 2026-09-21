---
name: project-zk-ilosci-nie-porownywane
description: "ZK — rozjazd ilości BOM vs dokument; most raportuje różnice, ale ich NIE zapisuje (decyzja o właścicielu ilości odroczona)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 42739f9a-ed55-4c6c-a06d-d2bf1b97a8bf
  modified: 2026-09-08T20:41:05.362Z
---

**Stan: warstwa informacyjna NAPRAWIONA (2026-09-08), decyzja projektowa ODROCZONA.**

Pierwotny błąd: `Projekt.cs` budował `naZk` jako `HashSet<string>` samych symbolów, więc 4 i 10 były dla mostu tym samym stanem. Zmiana ilości nie pojawiała się ani w dry-run, ani w raporcie, a zapis i tak jej nie przenosił (pozycja o istniejącym symbolu była pomijana przez `continue`).

**Co zrobiono:**
- `CzytajPozycjeZk()` zwraca `{symbol → ilość}` (parametr typu `PozycjaDokumentu`, sumuje powtórzony symbol).
- Nowy rodzaj kroku `"zk-poz"` ze statusami `roznica-ilosci` (dry-run) i `roznica-ilosci-pominieta` (po zapisie); opis `BOM: X — na ZK: Y (różnica ±Z)`.
- Okno: czerwony kafelek "RÓŻNICA ILOŚCI" (pierwszy w pasku), wiersze na czerwonym tle u góry tabeli, ostrzeżenie w opisie ZK, wzmianka w pasku statusu po "Przelicz", sekcja w raporcie po zapisie + `showwarning` zamiast `showinfo`. Kafelek "BEZ ZMIAN" przemianowany na "SKŁAD BEZ ZMIAN" (dotyczy wyłącznie kompletów, mylił się z ogólnym stanem).

**Czego NIE zrobiono (świadomie):** most **nie nadpisuje ani nie dodaje** ilości na istniejącym ZK — tylko informuje o rozjeździe.

**Why:** Nie jest rozstrzygnięte, kto jest właścicielem ilości na wystawionym dokumencie. User: "SUBIEKT jest ważniejszy bo jest księgowy. RM_BAZA wprowadza dane na starcie a potem już trzeba w subiekcie prowadzić zmiany a RM_BAZA już tylko czyta" — model "przekazania własności w czasie". Nie rozstrzyga on jednak, co robić przy dosypaniu NOWEGO zakresu do projektu (przypadek "dodaj BOM" z Transporterka). Pełna analiza w repo: `ANALIZA_ZK_DWA_ZRODLA_PRAWDY.md` — user konsultuje ją z kimś z zewnątrz.

**How to apply:** Zanim zmienisz logikę zapisu ilości na ZK — sprawdź, czy zapadła decyzja z tego dokumentu (wariant 6a: dopisywać tylko nowe symbole / 6b: osobny dokument na każdą partię). NIE traktuj braku zapisu ilości jako buga do naprawienia — to celowe zawieszenie. Zgodne z [[feedback-nic-po-cichu]]. Po zmianach w moście: `dotnet build` i wdrożenie do `C:\iLogic\Subiekt\MOST`.
