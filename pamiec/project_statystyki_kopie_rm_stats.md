---
name: project_statystyki_kopie_rm_stats
description: stats_status.py i stats_project_summary.py w RM-BAZA-MANAGER to KOPIE z NOW/RM_STATS — mają być identyczne; różni się tylko db.py (łącznik przez RM_SERWER). Zsynchronizowane 10.10.2026 po 2,5 mies. rozjazdu
metadata:
  type: project
---

`stats_status.py` i `stats_project_summary.py` (okna RM_MANAGER „Podsumowanie” i
„Status projektów”) to **kopie 1:1** z `NOW/RM_STATS/`. Różnić się ma tylko `db.py`:
w RM-BAZA-MANAGER to łącznik (`RMStatsDB`) czytający master przez RM_SERWER (`_rmm()`),
w RM_STATS pełny dostęp do plików. Zamysł zapisany w nagłówku `db.py`.

**Rozjazd 19.07 → 10.10.2026:** poprawki szły tylko do RM_STATS. RM_MANAGER nie miał:
opóźnień etapów liczonych od PROGNOZY (fix 26.08 — wcześniej zawyżone dni dla etapów po
poślizgu), pauzy (`is_paused` — wstrzymany pokazywany jako czerwony OPÓŹNIONY), karty maszyny.
10.10 skopiowane wersje z NOW; do łącznika dopisane 1:1 z RM_STATS/db.py: `project_sort_key`,
`stage_attachments`, `stage_topics`. Funkcji osi czasu (`build_project_timeline`:
pracownicy, urlopy) RM_MANAGER nie woła — łącznik ich nie ma (dopisać, gdy będzie potrzeba).

Sprawdzone na danych domowych: 63 projekty, ocena „opóźniony” bez zmian, 16 projektów z mniejszą
listą opóźnionych etapów (np. 2608: Elektromontaż +57 / Uruchomienie +115 znikają, FAT +43 zostaje).
Status projektów ~1,0 s (było 0,44 s) — `stage_attachments` otwiera plik każdego z 63 projektów.

**Why:** dwie kopie tego samego kodu rozjeżdżają się po cichu, a RM_MANAGER pokazywał inne liczby
niż RM_STATS.

**How to apply:** poprawka w `stats_*.py` → od razu do OBU repo (skopiować plik); w RM-BAZA
ewentualnie dopisać brakującą metodę do łącznika `db.py`. Inne kopie między repo:
`dwf_thumb.py` (świadomie: inna ścieżka cache, reszta identyczna). `RM_Tray_Organizer`
usunięty z RM-BAZA-MANAGER 10.10 — żyje tylko w NOW.
