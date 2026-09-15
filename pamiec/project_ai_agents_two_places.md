---
name: project-ai-agents-two-places
description: Dwaj niezależni asystenci AI (RM_MANAGER i RM_STATS) mają osobne zestawy narzędzi nad tymi samymi bazami — zmiana uprawnień/narzędzi w jednym nie propaguje się do drugiego
metadata: 
  node_type: memory
  type: project
  originSessionId: 5eced48e-9049-41f8-8c1b-531e4d668f2e
  modified: 2026-08-19T13:02:27.607Z
---

W projekcie działają **dwa niezależne agenty AI** nad pokrywającymi się danymi:

1. **RM_MANAGER** — `rm_ai_optimizer.py`. Narzędzia zdefiniowane w liście `TOOLS`,
   wpięte w `AIOptimizerContext.execute_tool()`. Reguły biznesowe (co wolno,
   jak interpretować dane) w osobnym pliku `Y:\RM_MANAGER\ai_rules.txt`
   (NIE w repo — edytowany bezpośrednio na dysku, wczytywany przy każdym
   otwarciu okna AI Chat, komentarze `#`).
2. **RM_STATS** (w RM_BAZA_v15_MAG_STATS_ORG.py) — osobny agent, osobny zestaw
   narzędzi, czyta te same bazy (`rm_manager.sqlite`, `master.sqlite`).

**Why:** 2026-08-19 user zgłosił, że RM_MANAGER-owy asystent odmawiał podania
transz płatności ("nie mam dostępu do danych finansowych"), a RM_STATS-owy
na to samo pytanie odpowiadał poprawnie z tabeli `payment_milestones`. Powód:
`rm_ai_optimizer.py` miał 5 narzędzi (get_projects_list, get_project_stages,
get_delays, get_worker_load, get_schedule_summary) — żadne nie czytało
`payment_milestones`, mimo że tabela i gotowe API (`get_payment_milestones()`
w rm_manager.py) już istniały. To nie był konflikt logiki, tylko luka w
wyposażeniu jednego z dwóch agentów.

**How to apply:** Przy każdej prośbie "dodaj AI możliwość odpowiadania o X" /
"AI nie widzi Y" / zmianie zachowania asystenta — sprawdź OBA miejsca:
- czy `rm_ai_optimizer.py` (TOOLS + execute_tool + SYSTEM_PROMPT) ma narzędzie
- czy `ai_rules.txt` na Y: wspomina o tym temacie (reguła, nie tylko kod)
- czy odpowiadający agent w RM_STATS ma analogiczne narzędzie / musi być
  zsynchronizowany logicznie (np. ta sama interpretacja pola w bazie)

**ZASADA UPRAWNIEŃ (ustalona 2026-08-19, user wprost):** agent AI NIE MOŻE być
furtką omijającą "Uprawnienia kategorii użytkowników" z GUI. Dane wrażliwe —
transze płatności (`payment_milestones`) i kody PLC (`plc_codes`) — muszą
przechodzić przez `rmm.has_feature_permission(rm_master_db_path, feature,
username, role)`, tę samą funkcję co okna (wzorzec: `_check_feature_permission`
w rm_manager_gui.py). ADMIN zawsze przechodzi, pusta lista uprawnionych =
brak ograniczeń, błąd odczytu = fail-open (jak w GUI). Dotyczy też każdej
przyszłej funkcji zapisu/modyfikacji finansów przez AI. W `AIOptimizerContext`
służą do tego pola `current_user` + `current_user_role` (GUI je przekazuje).
Wartości samych kodów PLC nigdy nie są zwracane agentowi — tylko ich stan.

Dodanie narzędzia w jednym miejscu NIE propaguje się do drugiego — to
świadomie osobne implementacje, nie wspólna warstwa. Jeśli user zgłasza że
"jeden mówi co innego niż drugi", to zwykle nie bug w logice, tylko brakujące
narzędzie/regułę w jednym z nich — zweryfikuj przez grep nazwy tabeli/pola w
obu plikach zamiast zakładać rozjazd interpretacji.
