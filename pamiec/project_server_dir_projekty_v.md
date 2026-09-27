---
name: project_server_dir_projekty_v
description: „Serwer projekty" (server_dir) = korzeń folderów projektów z DWF; projekty leżą WPROST w V:\ — na M-OLD stało V:/SERVER_PROJEKTY i miniatury DWF szły tylko z biblioteki
metadata:
  type: project
---

`paths.server_dir` w `C:\RMPAK_CLIENT\sync_config.json` (RM_BAZA: Ustawienia →
Konfiguracja ścieżek → „Serwer projekty") to korzeń folderów projektów:
`get_assembly_tree_root()` → `_find_dwf_in_project` → miniatury DWF w arkuszu,
zdjęcia kartotek przy zasiewie, wyszukiwarka plików, RFQ.

**Projekty leżą bezpośrednio w `V:\`** (`V:\2637 Feniks Z 25L`) — user,
28.09.2026. Na M-OLD było `V:/SERVER_PROJEKTY` (nie istnieje) → zasiew 2637
wysłał miniatury tylko dla pozycji z biblioteki B: (74 z 348), reszta
„bez rysunku" po cichu. Poprawione na `V:/` (kopia:
`sync_config.json.przed_server_dir_20260928.bak`). Po poprawce 194 rysunki
z folderu projektu + 74 z biblioteki.

⚠ Najpierw sprawdź, czy folder istnieje (`ls V:\`), zanim uznasz, że
„rysunków nie ma na maszynie" — 28.09 agent przeoczył go, patrząc tylko na
początek listingu, i wysnuł błędny wniosek.

Powiązane: [[project_mag_wdrozenie_firma_todo]], [[project_srodowisko_domowe_m_old]]
