---
name: project-projekt-aktualizacja-potwierdzone
description: Potwierdzone na żywo działanie okna Projekt/Aktualizacja w Subiekcie — dołożenie pozycji do BOM i Przelicz
metadata: 
  node_type: memory
  type: project
  originSessionId: 42739f9a-ed55-4c6c-a06d-d2bf1b97a8bf
  modified: 2026-09-08T19:41:41.783Z
---

Dołożenie nowej pozycji (np. `5000.100.01`) do arkusza projektu w RM_BAZA, a następnie kliknięcie "Przelicz" w oknie "Projekt / Aktualizacja w Subiekcie" (`subiekt_projekt.py`, `SubiektProjektWindow`), poprawnie podchwytuje ją i pokazuje w planie jako nową pozycję do założenia ("dokładkę").

**Why:** Użytkownik potwierdził na żywych danych (2026-09-08+), że mechanizm `build_plan`/`read_project_items` + odświeżenie planu działa zgodnie z oczekiwaniem dla zwykłego przypadku "dodaj pozycję do BOM → przelicz → pojawia się w planie jako nowa".

**How to apply:** Traktować ten przepływ (edycja BOM w arkuszu RM_BAZA → Przelicz w oknie Aktualizacji) jako zweryfikowany i bezpieczny — nie trzeba go podważać ani sugerować obejść przy tego typu prostym dodaniu pojedynczej pozycji. Odróżnić od NIEDOKOŃCZONEJ ścieżki CSV spoza RM_BAZA (patrz dokumentacja `SUBIEKT_ZMIANY_2026-09-08.md` sekcja 3) — tamta nie ma tego poziomu potwierdzenia na żywym zapisie.
