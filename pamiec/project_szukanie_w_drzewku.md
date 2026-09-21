---
name: project_szukanie_w_drzewku
description: "Szukanie w oknie Projekt/Aktualizacja rozwija gałęzie z trafieniami, nie filtruje drzewka"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5f190e79-13f0-43ff-a820-54ac4e6eb565
  modified: 2026-09-10T21:00:28.593Z
---

Okno „Projekt / Aktualizacja w Subiekcie" ma pole **Szukaj** (pasek Widok, obok filtra typu) — `subiekt_projekt._szukaj_w_drzewku()`. Szuka po numerze rysunku i nazwie, na żywo; Enter/F3 skacze do kolejnego trafienia, Escape i 🗑️ czyszczą.

**Why:** Szukanie **nie filtruje** drzewka — rozwija tylko gałęzie z trafieniami, reszta zostaje zwinięta. Decyzja użytkownika z 2026-09-10: w tym oknie połowa informacji to kontekst (w którym złożeniu pozycja siedzi, czy rodzic ma kartotekę), więc ukrycie niepasujących pozycji zabierałoby to, po czym się decyduje, co zaznaczyć do zapisu.

Podświetlenie robi **zaznaczenie drzewa**, nie tag koloru — tagi niosą tu znaczenie (`istnieje` / `nowy` / `blad` / `komplet-pusty`) i nadpisanie ich kolorem wyszukiwania skasowałoby informację.

**How to apply:** Po każdej przebudowie drzewa (`_fill_tree`) trzeba wołać `_odswiez_szukanie()` — węzły dostają nowe iid, więc zapamiętane trafienia wskazywałyby na nieistniejące wiersze. Jest to podpięte w obu wyjściach `_fill_tree` (drzewo i płaska lista).

Powiązane: [[project_uwagi_tytul_dokumentow]]
