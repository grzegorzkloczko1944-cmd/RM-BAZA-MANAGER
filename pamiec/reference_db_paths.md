---
name: reference-db-paths
description: Ścieżki do pliku master.sqlite i folderu projektów RM_BAZA
metadata: 
  node_type: memory
  type: reference
  originSessionId: 98e71cec-ffbe-4aab-8fa8-5ae9adfc245c
---

Ścieżki NIE są zaszyte w kodzie — czytane z `C:/RMPAK_CLIENT/sync_config.json` (klucz `paths`). Aktualny stan (2026-07-21):

- Baza master: `Y:/RM_BAZA/master.sqlite`
- Projekty (folder): `Y:/RM_BAZA/projects` → pliki `project_{id}.sqlite`
- Locki projektów: `Y:/RM_BAZA/locks/project_{id}.lock` (JSON: user, computer, locked_at, last_heartbeat) — sprawdzaj przed zapisem do bazy projektu, patrz [[project-rmpak-calc-qty-bug]]

Projekt po nazwie: `master.sqlite` tabela `projects(project_id, name, ...)`. Pozycje w project db: tabela `items`, kolumny ilości: `src_qty` (=Ilość BOM), `work_qty`, `order_qty`, `delivered_qty`.
