---
name: project-subiekt-integracja-m-old
description: "Środowisko testowe integracji Subiekt nexo na domowym komputerze M-OLD — osobne od firmy, tylko kod współdzielony przez git"
metadata: 
  node_type: memory
  type: project
  originSessionId: e0ba9b4b-d4d7-4304-bc9f-6adc6046664a
  modified: 2026-09-03T21:16:10.655Z
---

Od 2026-09-03 użytkownik ma na domowym komputerze `M-OLD` zainstalowane
Subiekt nexo PRO demo (45 dni) do testów integracji RM_BAZA ↔ Subiekt,
niezależnie od firmowego środowiska (serwer `192.168.100.4`). Szczegóły
techniczne instalacji, wersje, napotkane błędy: `subiekt_sfera/INSTALACJA_DOMOWA_NOTATKI.md`
w repo RM-BAZA-MANAGER.

Kluczowe ustalenia:
- Lokalna instancja SQL: `.\INSERTNEXO` (SQL Server 2019 Express, tryb mieszany)
- Wersja InsERT nexo i nexo SDK zgodne: `61.1.0.9431`
- Dane (bazy `.sqlite`, `.nexo_sfera.json`) są **świadomie odseparowane**
  od firmy — M-OLD ma własną testową kopię, nie synchronizuje się z
  firmową bazą. Użytkownik wybrał to jawnie (nie chciał żywej synchronizacji).
- Kod (git, repo RM-BAZA-MANAGER) **jest wspólny** między firmą a M-OLD —
  ten sam branch `main`, ten sam commit history. Patrz [[feedback_git_pull_multi_maszyna]]
  za zasadę ostrożności przy pracy z dwóch maszyn na tym samym repo.

**Why:** Użytkownik chce testować most C# (`subiekt_sfera/NexoRecon`)
i logikę `subiekt_projekt.py` bez ryzyka dotknięcia produkcyjnej bazy
firmowej — stąd pełna separacja danych, ale wspólny kod (bo to ten sam
projekt, nie eksperymentalna gałąź).

**How to apply:** Gdy użytkownik wspomina pracę "w domu"/"na M-OLD" w
kontekście Subiekta, traktuj to jako osobne środowisko testowe z innym
configiem (`.\INSERTNEXO` zamiast `192.168.100.4`), ale tym samym kodem
co firma.
