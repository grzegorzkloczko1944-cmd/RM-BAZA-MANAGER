---
name: project-local-copy-rm-manager
description: RM_MANAGER pracuje na lokalnej kopii baz per-projekt; płatności i kody PLC MUSZĄ zostać bezpośrednio na Y:
metadata:
  type: project
---

RM_MANAGER (`rm_manager_gui.py` + `rm_manager.py`) używa lokalnej kopii baz **per-projekt** (`rm_manager_project_{id}.sqlite`) dla wydajności — punkt zaczepienia to `self.get_project_db_path()` w [rm_manager_gui.py:685], kopiowanie przy `_acquire_project_lock()`, sync z powrotem na Y: przy `_release_current_lock()`. Flaga `USE_LOCAL_COPY` pozwala wyłączyć mechanizm.

**Wyjątek (decyzja użytkownika 2026-08-06):** zakładki **płatności** i **kody PLC** muszą działać bezpośrednio na bazie sieciowej — dane mają być natychmiast widoczne dla innych użytkowników, nie mogą czekać na sync przy zwolnieniu locka.

**Why:** te dane są krytyczne operacyjnie i współdzielone między użytkownikami w czasie rzeczywistym; opóźnienie do końca sesji edycyjnej byłoby nieakceptowalne.

**How to apply:** wyjątek jest spełniony automatycznie, bo tabele `payment_milestones`, `payment_history`, `plc_unlock_codes`, `plc_authorized_senders`, `plc_global_recipients` żyją w **masterze** `rm_manager.sqlite` (`ensure_rm_master_tables()` w [rm_manager.py:366]), a nie w bazach per-projekt. Nigdy nie przenoś ich do baz per-projekt i nie obejmuj mastera lokalną kopią bez ponownej rozmowy z użytkownikiem.

Kontekst wydajnościowy: ~11 miejsc w GUI omija `get_project_db_path()` i skanuje `glob()` po Y: (alarmy, statystyki) — są read-only, więc powodują tylko chwilową nieświeżość, nie utratę danych. Wzorzec local-copy pochodzi z RM_BAZA: [database_manager.py:862-982]. Patrz [[reference-db-paths]].
