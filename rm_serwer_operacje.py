# -*- coding: utf-8 -*-
"""Nazwane operacje na master.sqlite — JEDYNE miejsce, gdzie żyje SQL mastera.

⚠️ KLIENT NIGDY NIE WYSYŁA SQL. Wysyła nazwę operacji + parametry; treść
zapytania istnieje wyłącznie tutaj. Bez tego każdy w LAN mógłby wykonać
`DROP TABLE` — serwer słucha na sieci, nie na 127.0.0.1 jak most Subiekta
(PLAN_RM_SERWER.md §3, §7).

Moduł jest wspólny dla obu trybów przełącznika (§2a):
  • tryb „serwer" — woła go rm_serwer po stronie maszyny `nic`,
  • tryb „legacy"  — woła go klient bezpośrednio na swoim master_con.
Ta sama mapa operacja → SQL, inne miejsce wykonania. Dzięki temu tryb legacy
nie jest osobną implementacją, którą trzeba utrzymywać równolegle.

DOPISYWANIE OPERACJI
Nowa operacja = wpis w ODCZYT albo ZAPIS poniżej. Nic więcej — ani serwer,
ani klient nie wymagają zmian. Nazwy trzymamy w konwencji `rzecz-czynność`
(`supplier-add`, `settings-set`), bo po nich filtruje się log serwera.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════
# ODCZYTY — idempotentne, bez request_id, bez wpisu do _server_request_log
# ═══════════════════════════════════════════════════════════════════════
#
# Każdy wpis: nazwa → (SQL, [nazwy parametrów w kolejności]).
# Parametry są nazwane, żeby wywołanie z klienta było czytelne i odporne
# na pomyłkę kolejności: master_read("supplier-get", {"supplier_id": 7}).

ODCZYT = {
    # ── blokady projektow RM_BAZA (dawniej pliki project_<id>.lock) ──────
    #
    # ⚠️ Bez prefiksu `rmm-` — i to jest cala roznica. Routing serwera
    # (`_polaczenie`) kieruje te operacje do mastera RM_BAZA, a blizniacze
    # `rmm-lock-*` do rm_manager.sqlite. Dwa programy, dwie bazy, dwie
    # niezalezne tabele o tej samej nazwie: user RM_BAZA nigdy nie czeka
    # na projekt dlatego, ze ktos otworzyl projekt o tym samym numerze
    # w RM_MANAGER (numery pokrywaja sie w 81 przypadkach).
    "lock-po-projekcie": (
        "SELECT project_id, lock_id, uzytkownik, komputer, locked_at, last_heartbeat"
        "  FROM project_locks WHERE project_id = ?",
        ["project_id"],
    ),
    "locki-wszystkie": (
        "SELECT project_id, lock_id, uzytkownik, komputer, locked_at, last_heartbeat"
        "  FROM project_locks ORDER BY project_id",
        [],
    ),
    # ── master RM_BAZA: to, co klient czytal wprost z pliku ──────────────
    #
    # Selektor projektow i lista dostawcow — dwa zapytania wolane przy KAZDYM
    # starcie RM_BAZA. Dopoki szly przez `master_con`, plik `master.sqlite`
    # musial lezec na `Y:`, a program mial dwa zrodla prawdy naraz: wlasny
    # plik i baze serwera, ktore rozjezdzaly sie po kazdym zapisie.
    "projekty-do-selektora": (
        "SELECT project_id, name, active,"
        "       COALESCE(project_type, 'MACHINE') AS project_type"
        "  FROM projects ORDER BY name",
        [],
    ),
    "projekty-statusy-tekstowe": (
        "SELECT project_id, COALESCE(status, '') AS status FROM projects",
        [],
    ),
    "suppliers-aktywni-id-nazwa": (
        "SELECT supplier_id, name FROM suppliers"
        " WHERE is_active = 1 ORDER BY name",
        [],
    ),
    "suppliers-list": (
        "SELECT * FROM suppliers ORDER BY name COLLATE NOCASE",
        [],
    ),
    "supplier-get": (
        "SELECT * FROM suppliers WHERE supplier_id = ?",
        ["supplier_id"],
    ),
    # Sprawdzenie duplikatu przed dodaniem — po nazwie, bo to ona jest
    # dla użytkownika identyfikatorem firmy.
    "supplier-po-nazwie": (
        "SELECT supplier_id, name FROM suppliers WHERE name = ? COLLATE NOCASE",
        ["name"],
    ),
    # `is_active` jest potrzebne oknu zarządzania użytkownikami (kolumna
    # „Aktywny"). Dokładanie kolumny do SELECT-a jest bezpieczne: wołający
    # czytają wiersz po nazwach.
    "users-list": (
        "SELECT id, username, display_name, role, is_active FROM users"
        " ORDER BY username COLLATE NOCASE",
        [],
    ),
    "settings-get": (
        "SELECT value FROM settings WHERE key = ?",
        ["key"],
    ),
    "settings-all": (
        "SELECT key, value, updated_at FROM settings",
        [],
    ),
    "projects-list": (
        "SELECT * FROM projects ORDER BY project_id DESC",
        [],
    ),
    "project-get": (
        "SELECT * FROM projects WHERE project_id = ?",
        ["project_id"],
    ),
    "project-name": (
        "SELECT name FROM projects WHERE project_id = ?",
        ["project_id"],
    ),
    "user-audit-list": (
        "SELECT * FROM user_changes_log ORDER BY change_id DESC LIMIT ?",
        ["limit"],
    ),
    # Cały dziennik od początku — po nim odtwarza się stan użytkowników
    # (SNAPSHOT/ADD dodaje, DELETE usuwa), więc kolejność MUSI być rosnąca.
    # Pełny dziennik do okna „Historia zmian użytkowników" — wszystkie
    # kolumny, od najnowszych.
    "user-audit-pelny": (
        "SELECT change_id, action, user_id, username, display_name, role,"
        "       changed_by, timestamp, details"
        "  FROM user_changes_log ORDER BY change_id DESC",
        [],
    ),
    "user-audit-historia": (
        "SELECT action, user_id, username, display_name, role"
        " FROM user_changes_log ORDER BY change_id ASC",
        [],
    ),
    "sessions-list": (
        "SELECT * FROM client_sessions ORDER BY ended_at IS NOT NULL, last_seen DESC",
        [],
    ),
    # ── użytkownicy ───────────────────────────────────────────────────
    # Jeden użytkownik po id — uprawnienia sprawdzane przy każdej akcji.
    "user-po-id": (
        "SELECT id, username, display_name, role FROM users WHERE id = ?",
        ["id"],
    ),
    "users-aktywni": (
        "SELECT id, username, display_name, role FROM users"
        " WHERE is_active = 1 ORDER BY username",
        [],
    ),
    "user-nazwa-po-loginie": (
        "SELECT display_name FROM users WHERE username = ?",
        ["username"],
    ),
    "user-nazwa-po-id": (
        "SELECT display_name FROM users WHERE id = ?",
        ["id"],
    ),
    "user-hash": (
        "SELECT password_hash FROM users WHERE id = ?",
        ["id"],
    ),

    # ── projekty: status i priorytet (używa RM_MANAGER) ───────────────
    # ⚠️ `project_status` to CO INNEGO niż `status`: pierwsze to stan procesu
    # w RM_MANAGER (NEW/ACCEPTED/IN_PROGRESS/PAUSED/DONE), drugie to nazwa
    # etapu wpisywana przez `project-status-sync`. Obie kolumny są w tej
    # samej tabeli i łatwo je pomylić.
    "project-status": (
        "SELECT project_status FROM projects WHERE project_id = ?",
        ["project_id"],
    ),
    "projects-statusy": (
        "SELECT project_id, project_status FROM projects",
        [],
    ),
    # Do logiki „write once" w sync_to_master: montaz/sat wpisujemy RAZ,
    # kolejne synchronizacje go nie nadpisują.
    "project-daty": (
        "SELECT montaz, sat, fat, completed_at, designer, status"
        "  FROM projects WHERE project_id = ?",
        ["project_id"],
    ),
    "project-priorytet": (
        "SELECT priority FROM projects WHERE project_id = ?",
        ["project_id"],
    ),
    "projects-priorytety": (
        "SELECT project_id, priority FROM projects",
        [],
    ),
    # Logowanie do RM_MANAGER kontem z RM_BAZA — stąd password_hash.
    "users-do-logowania": (
        "SELECT id, username, display_name, role, password_hash FROM users"
        " WHERE is_active = 1 ORDER BY username",
        [],
    ),

    # ── projekty ──────────────────────────────────────────────────────
    "projects-id-nazwa": (
        "SELECT project_id, name FROM projects",
        [],
    ),
    "project-aktywny": (
        "SELECT active FROM projects WHERE project_id = ?",
        ["project_id"],
    ),

    # ── dostawcy ──────────────────────────────────────────────────────
    "suppliers-z-nip": (
        "SELECT supplier_id, name, nip FROM suppliers"
        " WHERE nip IS NOT NULL AND nip != ''",
        [],
    ),
    "supplier-nazwa": (
        "SELECT name FROM suppliers WHERE supplier_id = ?",
        ["supplier_id"],
    ),
    # Dostawca po nazwie z BOM-u. ⚠️ Poprzednio pytało o `id` i
    # `name_normalized` — tabela nie ma ANI JEDNEJ z tych kolumn (jest
    # `supplier_id` i `name`), więc każde wywołanie rzucało wyjątkiem,
    # cicho zjadanym przez `except: pass` u wołającego. Efekt: importowana
    # pozycja NIGDY nie dostawała dostawcy.
    #
    # `norm()` po stronie klienta zwija białe znaki; tutaj dokładamy TRIM
    # i NOCASE, bo nazwy w BOM-ie różnią się wielkością liter.
    "supplier-po-normalizacji": (
        "SELECT supplier_id AS id FROM suppliers"
        " WHERE TRIM(name) = TRIM(?) COLLATE NOCASE",
        ["name_normalized"],
    ),

    # Kolumny tabeli suppliers — klient używa ich do zbudowania widoku
    # (nazwy kolumn różnią się między instalacjami, patrz ALIASY_DOSTAWCY).
    # Zwraca po jednym wierszu na kolumnę, jak PRAGMA table_info.
    "suppliers-kolumny": (
        "SELECT name FROM pragma_table_info('suppliers')",
        [],
    ),
    # Tagi wszystkich kooperantów naraz — do listy dostawców z etykietami.
    "rfq-tagi-wszystkich": (
        "SELECT st.supplier_id, t.label FROM rfq_supplier_tags st"
        "  JOIN rfq_tags t ON t.id = st.tag_id"
        " ORDER BY t.sort_order, t.label",
        [],
    ),

    # ── wyniki zapytań ofertowych (portal RM_RFQ; tabele w masterze) ──
    # Kolumny wypisane jawnie, nie SELECT * — przy zmianie schematu portalu
    # chcemy błędu tutaj, a nie cicho innego kształtu wiersza u wołającego.
    "rfq-wyniki": (
        "SELECT drawing_number, invitations_sent, suppliers_count,"
        "       offers_count, min_price, supplier_name, price,"
        "       rfq_status, response_deadline, declined_count,"
        "       files_updated_at, docs_notified_at"
        "  FROM rfq_results ORDER BY COALESCE(rfq_id, 0) ASC",
        [],
    ),
    # Pełny wiersz wyceny detalu — ten sam detal bywa w kilku zapytaniach
    # naraz, stąd ORDER BY rfq_id DESC: pierwszy wiersz to najnowsze RFQ,
    # reszta idzie do sekcji „Ten detal w innych zapytaniach".
    "rfq-wycena-detalu": (
        "SELECT drawing_number, item_name, project_number, rfq_code, rfq_title,"
        "       rfq_status, invitations_sent, suppliers_count, offers_count,"
        "       min_price, supplier_name, price, currency, lead_time_days,"
        "       offer_notes, decided_at, synced_at, rfq_id,"
        "       viewers_count, seen_item_count, last_viewed_at,"
        "       rfq_item_id, files_updated_at, docs_notified_at"
        "  FROM rfq_results WHERE drawing_number = ?"
        " ORDER BY COALESCE(rfq_id, 0) DESC",
        ["drawing_number"],
    ),
    # Aktywność kooperantów przy detalu. Kolumny odmowy (has_declined,
    # decline_*) dochodzą dopiero przy pierwszym cyklu agenta po aktualizacji
    # portalu — stąd wariant „stary" poniżej, wołany gdy ten rzuci błędem.
    "rfq-aktywnosc-detalu": (
        "SELECT supplier_name, email_sent_at, last_viewed_at, view_count,"
        "       seen_this_item, has_offer, COALESCE(is_winner, 0) AS is_winner,"
        "       win_price, offer_price, offer_currency, offer_lead_time,"
        "       COALESCE(has_declined, 0) AS has_declined, decline_label,"
        "       decline_notes, offer_notes"
        "  FROM rfq_activity WHERE drawing_number = ?"
        " ORDER BY COALESCE(is_winner, 0) DESC, supplier_name",
        ["drawing_number"],
    ),
    "rfq-aktywnosc-detalu-stara": (
        "SELECT supplier_name, email_sent_at, last_viewed_at, view_count,"
        "       seen_this_item, has_offer, COALESCE(is_winner, 0) AS is_winner,"
        "       win_price, offer_price, offer_currency, offer_lead_time"
        "  FROM rfq_activity WHERE drawing_number = ?"
        " ORDER BY COALESCE(is_winner, 0) DESC, supplier_name",
        ["drawing_number"],
    ),
    "rfq-id-po-rysunku": (
        "SELECT rfq_id FROM rfq_results WHERE drawing_number = ?",
        ["drawing_number"],
    ),

    # ── tagi kooperantów (portal RM_RFQ; tabele leżą w masterze) ──────
    "rfq-tagi-dostawcy": (
        "SELECT tag_id FROM rfq_supplier_tags WHERE supplier_id = ?",
        ["supplier_id"],
    ),

    # ══ KALKULATORY ═════════════════════════════════════════════════
    "materialy-cennik": (
        "SELECT material, density, price_per_kg FROM material_prices"
        " ORDER BY material",
        [],
    ),
    # Dostawcy „RMPAK" — kalkulator liczy im robociznę zamiast ceny z oferty.
    "suppliers-po-nazwie-like": (
        "SELECT supplier_id FROM suppliers WHERE name LIKE ?",
        ["wzorzec"],
    ),

# ══ RM_MANAGER — odczyty ═══
    "rmm-line-projects-po-line-id": (
        "SELECT project_id FROM line_projects WHERE line_id = ?",
        ['line_id'],
    ),
    "rmm-payment-milestones-po-project-id-percentage": (
        "SELECT payment_date FROM payment_milestones WHERE project_id = ?"
        " AND percentage = ?",
        ['project_id', 'percentage'],
    ),
    # ⚠️ Generator uciął dwa zapytania poniżej do samego SELECT-a (WHERE był
    # w drugim literale stringa) — zwracały CAŁĄ tabelę. Tu wersje pełne.
    # Definicje etapów z GŁÓWNEJ bazy RM_MANAGER (tabela o tej samej nazwie
    # jest też w bazach projektowych — ta operacja dotyczy słownika).
    "rmm-stage-definitions-lista": (
        "SELECT code, display_name FROM stage_definitions ORDER BY id",
        [],
    ),
    # ── blokady projektów (dawniej pliki project_<id>.lock w LOCKS) ──────
    # ── sesje uzytkownikow (dawniej pliki JSON w SESSIONS\) ──────────────
    #
    # Pilnuja czego innego niz blokady projektow: jeden user = jedno
    # zalogowanie, zeby ta sama osoba nie pracowala z dwoch komputerow naraz.
    # Byly plikami, bo heartbeat co 30 s robil UPDATE na bazie przez SMB
    # i blokowal ja wszystkim. Serwer kolejkuje zapisy, wiec ten powod znikl.
    "rmm-sesje-uzytkownika": (
        "SELECT session_id, user_id, username, hostname, pid, app_name,"
        "       login_at, last_heartbeat, client_info"
        "  FROM active_sessions WHERE user_id = ?"
        " ORDER BY login_at DESC",
        ["user_id"],
    ),
    "rmm-sesje-wszystkie": (
        "SELECT session_id, user_id, username, hostname, pid, app_name,"
        "       login_at, last_heartbeat, client_info"
        "  FROM active_sessions ORDER BY login_at DESC",
        [],
    ),
    "rmm-sesja-po-id": (
        "SELECT session_id, user_id, username, hostname, pid, app_name,"
        "       login_at, last_heartbeat, client_info"
        "  FROM active_sessions WHERE session_id = ?",
        ["session_id"],
    ),
    "rmm-lock-po-projekcie": (
        "SELECT project_id, lock_id, uzytkownik, komputer, locked_at, last_heartbeat"
        "  FROM project_locks WHERE project_id = ?",
        ["project_id"],
    ),
    "rmm-locki-wszystkie": (
        "SELECT project_id, lock_id, uzytkownik, komputer, locked_at, last_heartbeat"
        "  FROM project_locks ORDER BY project_id",
        [],
    ),
    "rmm-payment-milestones-wszystkie": (
        "SELECT project_id, percentage, payment_date, payment_type"
        "  FROM payment_milestones ORDER BY project_id, percentage",
        [],
    ),
    # Dla asystenta AI (rm_ai_optimizer): przeglądy „wszystkich" bez filtra.
    "rmm-plc-unlock-codes-wszystkie": (
        "SELECT id, project_id, code_type, description, is_used, used_at,"
        " used_by, sent_at, sent_by, sent_via, expiry_date, created_at, created_by"
        " FROM plc_unlock_codes ORDER BY project_id, id",
        [],
    ),
    "rmm-line-projects-wszystkie": (
        "SELECT line_id, project_id FROM line_projects ORDER BY line_id, project_id",
        [],
    ),
    "rmm-production-lines-lista": (
        "SELECT id, name, description, parallel_stages_csv"
        " FROM production_lines ORDER BY name COLLATE NOCASE",
        [],
    ),
    "rmm-feature-users-po-feature": (
        "SELECT username FROM rm_feature_user_permissions"
        " WHERE feature = ? ORDER BY username",
        ["feature"],
    ),
    "rmm-service-trip-po-id-pelny": (
        "SELECT * FROM service_trips WHERE id = ?",
        ["id"],
    ),
    "rmm-nieobecnosc-po-id": (
        "SELECT id, employee_id, status, reason, date_from, date_to"
        " FROM employee_availability WHERE id = ?",
        ["id"],
    ),
    "rmm-carryover-po-employee-year": (
        "SELECT days FROM employee_carryover_override"
        " WHERE employee_id = ? AND year = ?",
        ["employee_id", "year"],
    ),
    "rmm-employee-vacation-base-po-employee-id": (
        "SELECT days FROM employee_vacation_base WHERE employee_id = ?",
        ['employee_id'],
    ),
    "rmm-employee-vacation-quota-po-employee-id-year": (
        "SELECT days FROM employee_vacation_quota WHERE employee_id = ?"
        " AND year = ?",
        ['employee_id', 'year'],
    ),
    "rmm-rm-user-permissions": (
        "SELECT COUNT(*) FROM rm_user_permissions",
        [],
    ),
    "rmm-resource-constraints": (
        "SELECT COUNT(*) FROM resource_constraints",
        [],
    ),
    "rmm-priority-weights": (
        "SELECT COUNT(*) FROM priority_weights",
        [],
    ),
    "rmm-line-projects-po-project-id": (
        "SELECT pl.id, pl.name, pl.description, pl.parallel_stages_csv"
        " FROM line_projects lp JOIN production_lines pl ON pl.id ="
        " lp.line_id WHERE lp.project_id = ?",
        ['project_id'],
    ),
    "rmm-project-file-tracking-po-project-id": (
        "SELECT project_name, file_path, file_birth_time,"
        " verification_status FROM project_file_tracking WHERE project_id ="
        " ?",
        ['project_id'],
    ),
    "rmm-project-file-tracking-po-project-id-2": (
        "SELECT project_name FROM project_file_tracking WHERE project_id ="
        " ?",
        ['project_id'],
    ),
    "rmm-sync-log": (
        "SELECT sync_date FROM sync_log ORDER BY id DESC LIMIT 1",
        [],
    ),
    "rmm-project-file-tracking-po-verification-status": (
        "SELECT project_id FROM project_file_tracking WHERE"
        " verification_status = 'OK'",
        [],
    ),
    "rmm-rm-user-permissions-po-role": (
        "SELECT * FROM rm_user_permissions WHERE role = ?",
        ['role'],
    ),
    "rmm-rm-user-permissions-2": (
        "SELECT * FROM rm_user_permissions ORDER BY role",
        [],
    ),
    "rmm-audit-log-po-employee-id": (
        "SELECT * FROM audit_log WHERE employee_id = ? ORDER BY changed_at"
        " DESC, id DESC LIMIT ?",
        ['employee_id', 'p1'],
    ),
    "rmm-audit-log": (
        "SELECT * FROM audit_log ORDER BY changed_at DESC, id DESC LIMIT ?",
        ['p1'],
    ),
    "rmm-employees-po-id": (
        "SELECT * FROM employees WHERE id = ?",
        ['id'],
    ),
    "rmm-employees-po-user-login": (
        "SELECT * FROM employees WHERE user_login = ? COLLATE NOCASE LIMIT"
        " 1",
        ['user_login'],
    ),
    "rmm-priority-weights-2": (
        "SELECT level, weight FROM priority_weights",
        [],
    ),
    "rmm-employees-po-id-2": (
        "SELECT id FROM employees WHERE id = ?",
        ['id'],
    ),
    "rmm-employees-po-id-3": (
        "SELECT id, name FROM employees WHERE id = ?",
        ['id'],
    ),
    "rmm-payment-milestones-po-project-id-payment-type": (
        "SELECT percentage, payment_date FROM payment_milestones WHERE"
        " project_id = ? AND payment_type = 'UMORZONY'",
        ['project_id'],
    ),
    "rmm-payment-milestones-po-project-id": (
        "SELECT id, project_id, percentage, payment_date, payment_type,"
        " created_by, created_at, modified_by, modified_at FROM"
        " payment_milestones WHERE project_id = ? ORDER BY id",
        ['project_id'],
    ),
    "rmm-payment-history-po-project-id": (
        "SELECT id, project_id, percentage, payment_date, action,"
        " changed_by, changed_at, old_date FROM payment_history WHERE"
        " project_id = ? ORDER BY changed_at DESC",
        ['project_id'],
    ),
    "rmm-payment-notification-config-po-id": (
        "SELECT id, trigger_percentage, email_recipients, smtp_server,"
        " smtp_port, smtp_user, smtp_password, enabled FROM"
        " payment_notification_config WHERE id = 1",
        [],
    ),
    "rmm-in-app-notifications-po-is-read": (
        "SELECT id, project_id, project_name, notification_type, message,"
        " created_at, created_by FROM in_app_notifications WHERE is_read ="
        " 0 ORDER BY created_at DESC",
        [],
    ),
    "rmm-payment-notifications-sent-po-project-id": (
        "SELECT id, project_id, project_name, percentage, payment_date,"
        " recipients, sent_at, sent_by, email_status, error_message FROM"
        " payment_notifications_sent WHERE project_id = ? ORDER BY sent_at"
        " DESC",
        ['project_id'],
    ),
    "rmm-payment-notifications-sent": (
        "SELECT id, project_id, project_name, percentage, payment_date,"
        " recipients, sent_at, sent_by, email_status, error_message FROM"
        " payment_notifications_sent ORDER BY sent_at DESC LIMIT 100",
        [],
    ),
    "rmm-plc-unlock-codes-po-project-id": (
        "SELECT id, project_id, code_type, unlock_code, description,"
        " created_by, created_at, modified_by, modified_at, is_used,"
        " used_at, used_by, notes, sent_at, sent_by, sent_via, expiry_date"
        " FROM plc_unlock_codes WHERE project_id = ? ORDER BY CASE"
        " code_type WHEN 'TEMPORARY' THEN 1 WHEN 'EXTENDED' THEN 2 WHEN"
        " 'PERMANENT' THEN 3 END, created_at",
        ['project_id'],
    ),
    "rmm-plc-global-recipients-po-setting-key": (
        "SELECT recipients_json FROM plc_global_recipients WHERE"
        " setting_key='default_recipients'",
        [],
    ),
    "rmm-plc-global-recipients-po-setting-key-2": (
        "SELECT recipients_json FROM plc_global_recipients WHERE"
        " setting_key = 'default_recipients'",
        [],
    ),
    "rmm-plc-global-recipients-po-setting-key-3": (
        "SELECT recipients_json FROM plc_global_recipients WHERE"
        " setting_key = 'payment_status_recipients'",
        [],
    ),
    "rmm-plc-unlock-codes-po-project-id-2": (
        "SELECT code_type, is_used, COUNT(*) as count FROM"
        " plc_unlock_codes WHERE project_id = ? GROUP BY code_type, is_used",
        ['project_id'],
    ),
    "rmm-payment-milestones-po-project-id-2": (
        "SELECT COALESCE(SUM(percentage), 0) as total FROM"
        " payment_milestones WHERE project_id = ?",
        ['project_id'],
    ),
    "rmm-plc-authorized-senders": (
        "SELECT COUNT(*) as cnt FROM plc_authorized_senders WHERE"
        " TRIM(LOWER(username)) = TRIM(LOWER(?))",
        ['p1'],
    ),
    "rmm-plc-authorized-senders-2": (
        "SELECT username, added_by, added_at, notes FROM"
        " plc_authorized_senders ORDER BY added_at DESC",
        [],
    ),
    "rmm-absence-exclusion-groups": (
        "SELECT * FROM absence_exclusion_groups ORDER BY name",
        [],
    ),
    "rmm-absence-exclusion-members": (
        "SELECT m.employee_id, e.name AS employee_name FROM"
        " absence_exclusion_members m JOIN employees e ON e.id ="
        " m.employee_id WHERE m.group_id = ? ORDER BY e.name",
        ['group_id'],
    ),
    "rmm-absence-exclusion-groups-po-employee-id": (
        "SELECT DISTINCT g.id, g.name FROM absence_exclusion_groups g JOIN"
        " absence_exclusion_members m ON m.group_id = g.id WHERE"
        " m.employee_id = ?",
        ['employee_id'],
    ),
    "rmm-absence-exclusion-members-2": (
        "SELECT m.employee_id FROM absence_exclusion_members m WHERE"
        " m.group_id = ? AND m.employee_id != ?",
        ['group_id', 'p1'],
    ),
    "rmm-employee-availability-po-employee-id-date-from": (
        "SELECT id, date_from, date_to, reason, status FROM"
        " employee_availability WHERE employee_id = ? AND date_from <= ?"
        " AND date_to >= ? AND UPPER(COALESCE(status,'ZATWIERDZONY')) !="
        " 'ODRZUCONY' ORDER BY date_from",
        ['employee_id', 'p1', 'p2'],
    ),
    "rmm-service-trips-po-id": (
        "SELECT date_from, date_to, status FROM service_trips WHERE id = ?",
        ['id'],
    ),
    "rmm-employee-availability-po-employee-id-date-from-2": (
        "SELECT date_from, date_to, reason FROM employee_availability"
        " WHERE employee_id = ? AND id != ? AND"
        " UPPER(COALESCE(status,'ZATWIERDZONY')) = 'ZATWIERDZONY' AND"
        " date_from <= ? AND date_to >= ? ORDER BY date_from LIMIT 1",
        ['employee_id', 'p1', 'p2', 'p3'],
    ),
    "rmm-company-calendar-po-date-date": (
        "SELECT date, day_type FROM company_calendar WHERE date >= ? AND"
        " date <= ?",
        ['p1', 'p2'],
    ),
    "rmm-optimization-runs": (
        "SELECT * FROM optimization_runs ORDER BY created_at DESC LIMIT ?",
        ['p1'],
    ),
    "rmm-project-file-tracking-po-project-id-3": (
        "SELECT COUNT(*) FROM project_file_tracking WHERE project_id = ?",
        ['project_id'],
    ),
    "rmm-employees-po-id-4": (
        "SELECT master_max_parallel FROM employees WHERE id=?",
        ['id'],
    ),
    "rmm-in-app-notifications": (
        "SELECT id, project_name, message, created_at, created_by, is_read"
        " FROM in_app_notifications ORDER BY created_at DESC LIMIT 100",
        [],
    ),
    "rmm-project-file-tracking": (
        "SELECT project_id, project_name FROM project_file_tracking ORDER"
        " BY project_id",
        [],
    ),
    "rmm-employees": (
        "SELECT id, name FROM employees",
        [],
    ),

    # ══ RM_MANAGER — zapytania wcześniej sklejane dynamicznie ═══════
    #
    # Klient budował te SQL-e z f-stringów (`WHERE id IN ({placeholders})`,
    # `SELECT * FROM t {where}`). Tutaj listy jadą jako JEDEN parametr —
    # tablica JSON rozpakowana przez `json_each` — a filtrowanie, którego
    # nie da się tak wyrazić, robi wołający na zwróconych wierszach.
    # Tabele mają od 3 do 151 wierszy, więc pełny odczyt jest tani.
    "rmm-employees-po-idach": (
        "SELECT id, name, category FROM employees"
        " WHERE id IN (SELECT value FROM json_each(?))"
        " ORDER BY category, name",
        ["idy_json"],
    ),
    "rmm-employees-po-idach-konstrukcja": (
        "SELECT id, name, category FROM employees"
        " WHERE id IN (SELECT value FROM json_each(?))"
        "   AND category = 'Konstrukcja' ORDER BY name",
        ["idy_json"],
    ),
    "rmm-employees-wszystkie": (
        "SELECT * FROM employees ORDER BY category, name",
        [],
    ),
    "rmm-transports-wszystkie": (
        "SELECT * FROM transports ORDER BY name",
        [],
    ),
    "rmm-resource-constraints-wszystkie": (
        "SELECT * FROM resource_constraints"
        " ORDER BY constraint_type, category, stage_code",
        [],
    ),
    "rmm-company-calendar-wszystkie": (
        "SELECT * FROM company_calendar ORDER BY date",
        [],
    ),
    # Nieobecności z nazwiskiem pracownika — złączenie po stronie serwera,
    # żeby klient nie musiał łączyć dwóch list w pamięci.
    "rmm-nieobecnosci-z-nazwiskami": (
        "SELECT ea.*, e.name AS employee_name,"
        "       e.category AS employee_category"
        " FROM employee_availability ea"
        " JOIN employees e ON e.id = ea.employee_id"
        " ORDER BY ea.date_from DESC",
        [],
    ),
    "rmm-wyjazdy-z-nazwiskami": (
        "SELECT st.*, e.name AS employee_name,"
        "       e.category AS employee_category"
        " FROM service_trips st"
        " LEFT JOIN employees e ON e.id = st.employee_id"
        " ORDER BY st.date_from DESC",
        [],
    ),

    # ══ STATUSY PROJEKTÓW ═══════════════════════════════════════════
    # Projekt ma KILKA statusów naraz — `project_statuses` to zbiór, nie
    # jedno pole. Kolejność po `set_at`, bo pierwszy nadany jest głównym.
    "statusy-projektu": (
        "SELECT status FROM project_statuses WHERE project_id = ?"
        " ORDER BY set_at ASC",
        ["project_id"],
    ),
    "status-historia": (
        "SELECT id, old_status, new_status, changed_at, changed_by, notes"
        " FROM project_status_history WHERE project_id = ?"
        " ORDER BY changed_at DESC",
        ["project_id"],
    ),
    # Rosnąco — liczenie czasu spędzonego w statusie wymaga kolejności od
    # najstarszego.
    "status-historia-rosnaco": (
        "SELECT old_status, new_status, changed_at"
        " FROM project_status_history WHERE project_id = ?"
        " ORDER BY changed_at ASC",
        ["project_id"],
    ),
    "status-zmiany": (
        "SELECT id, status, action, changed_at, changed_by, notes"
        " FROM project_status_changes WHERE project_id = ?"
        " ORDER BY changed_at DESC",
        ["project_id"],
    ),
    "status-zmiany-jednego": (
        "SELECT id, status, action, changed_at, changed_by, notes"
        " FROM project_status_changes"
        " WHERE project_id = ? AND status = ? ORDER BY changed_at DESC",
        ["project_id", "status"],
    ),
    "status-lista-uzytych": (
        "SELECT DISTINCT status FROM project_status_changes"
        " WHERE project_id = ?",
        ["project_id"],
    ),

    # ══ PORTAL RFQ — synchronizator (rm_sync_agent) ═════════════════
    # Agent chodzi w sieci firmowej: czyta mastera (przez serwer) i pliki
    # z V:\, wysyła ich treść do portalu po HTTPS. Pliki to etap 3 —
    # tutaj idą WYŁĄCZNIE metadane.
    "rfq-ustawienie": (
        "SELECT value FROM settings WHERE key = ?",
        ["key"],
    ),
    "rfq-tagi": (
        "SELECT id, name, label, sort_order FROM rfq_tags"
        " ORDER BY sort_order, label",
        [],
    ),
    "rfq-tag-nastepny-numer": (
        "SELECT COALESCE(MAX(sort_order), 0) + 1 AS nastepny FROM rfq_tags",
        [],
    ),
    "rfq-tagi-dostawcow": (
        "SELECT supplier_id, tag_id FROM rfq_supplier_tags",
        [],
    ),
    # DISTINCT rfq_id — po tym iteruje all_stale_drawings() licząc badge
    # „do podmiany".
    "rfq-pushed-rfq-id": (
        "SELECT DISTINCT rfq_id FROM rfq_pushed_files",
        [],
    ),
    "rfq-pushed-nazwy": (
        "SELECT filename FROM rfq_pushed_files"
        " WHERE rfq_id = ? AND drawing_number = ?",
        ["rfq_id", "drawing_number"],
    ),
    "rfq-pushed-sciezki": (
        "SELECT path FROM rfq_pushed_files"
        " WHERE rfq_id = ? AND drawing_number = ?",
        ["rfq_id", "drawing_number"],
    ),
    "rfq-pushed-odciski": (
        "SELECT path, filename, drawing_number, size, mtime_ns, sha1"
        " FROM rfq_pushed_files WHERE rfq_id = ?",
        ["rfq_id"],
    ),
    # Pozycje z ZALEGŁYM powiadomieniem: dokumentację podmieniono, ale
    # kooperanci nie wiedzą o tej wersji. Do tabelki „Do powiadomienia".
    "rfq-do-powiadomienia": (
        "SELECT rfq_id, drawing_number, item_name, rfq_code, files_updated_at"
        " FROM rfq_results"
        " WHERE files_updated_at IS NOT NULL"
        "   AND (docs_notified_at IS NULL OR docs_notified_at < files_updated_at)"
        " ORDER BY rfq_code, drawing_number",
        [],
    ),
    "rfq-wynikow-ile": (
        "SELECT COUNT(*) AS n FROM rfq_results",
        [],
    ),

    # ══ MAPOWANIA SUBIEKTA ══════════════════════════════════════════
    # ⚠️ Te operacje dotyczą OSOBNEGO PLIKU `subiekt_mapowania.sqlite`,
    # nie mastera. Serwer trzyma do niego drugie połączenie — patrz
    # `rm_serwer.Serwer.polacz`. Prefiks `map-` mówi, której bazy dotyczą.
    #
    # Numer rysunku jest kluczem głównym i jest znormalizowany (TRIM +
    # wielkie litery) PO STRONIE WOŁAJĄCEGO — `subiekt_mapowania._key()`.
    # Serwer nie normalizuje, żeby nie było dwóch różnych reguł.
    "map-get": (
        "SELECT * FROM mapowania WHERE numer_rysunku = ?",
        ["numer_rysunku"],
    ),
    "map-sposob": (
        "SELECT sposob FROM mapowania WHERE numer_rysunku = ?",
        ["numer_rysunku"],
    ),
    "map-po-sposobie": (
        "SELECT numer_rysunku FROM mapowania WHERE sposob = ?",
        ["sposob"],
    ),
    "map-statystyki": (
        "SELECT sposob, COUNT(*) AS n FROM mapowania GROUP BY sposob",
        [],
    ),
    "map-wszystkie": (
        "SELECT * FROM mapowania",
        [],
    ),
    "map-alias": (
        "SELECT nowy_symbol, nowy_id FROM aliasy_scalen"
        " WHERE stary_symbol = ? COLLATE NOCASE ORDER BY kiedy DESC LIMIT 1",
        ["stary_symbol"],
    ),
    "map-dostawcy-nie-firmy": (
        "SELECT supplier_id FROM dostawcy_decyzje WHERE decyzja = 'nie_firma'",
        [],
    ),

    # Stan zamówień ZD odkładany przez wysyłkę — nakładany przy przejęciu locka.
    # ══ WYSYŁKA ZD — dziennik i odłożone zamówienia (subiekt_wyslij_zd) ═══
    "zd-wyslane-terminy": (
        "SELECT numer_zd, termin FROM zd_wyslane ORDER BY id",
        [],
    ),
    "zd-wyslane-historia": (
        "SELECT dokument_id, MAX(kiedy) AS kiedy, COUNT(*) AS ile FROM zd_wyslane"
        " WHERE dokument_id IS NOT NULL GROUP BY dokument_id",
        [],
    ),
    "zd-wyslane-mapa": (
        "SELECT numer_zd, MAX(kiedy) AS kiedy FROM zd_wyslane"
        " WHERE dokument_id IS NOT NULL GROUP BY numer_zd",
        [],
    ),
    "zd-zamowione-ile": (
        "SELECT COUNT(*) AS n FROM zd_zamowione_pozycje WHERE project_id = ?",
        ["project_id"],
    ),
    "zd-cofniete-ile": (
        "SELECT COUNT(*) AS n FROM zd_cofniete_pozycje WHERE project_id = ?",
        ["project_id"],
    ),
    "zd-zamowione-list": (
        "SELECT item_id, termin, kiedy, supplier_id FROM zd_zamowione_pozycje"
        " WHERE project_id = ?",
        ["project_id"],
    ),
    "schowek-nowe-list": (
        "SELECT symbol, nazwa, kto, kiedy FROM schowek_nowe_pozycje"
        " WHERE project_id = ? ORDER BY id",
        ["project_id"],
    ),
    "schowek-nowe-ile": (
        "SELECT COUNT(*) AS n FROM schowek_nowe_pozycje WHERE project_id = ?",
        ["project_id"],
    ),
    "zd-cofniete-list": (
        "SELECT item_id, termin FROM zd_cofniete_pozycje WHERE project_id = ?",
        ["project_id"],
    ),
}


# ═══════════════════════════════════════════════════════════════════════
# ZAPISY — wymagają request_id, trafiają do _server_request_log
# ═══════════════════════════════════════════════════════════════════════

ZAPIS = {
    # ── blokady projektow RM_BAZA ────────────────────────────────────────
    #
    # Blizniaki `rmm-lock-*`, ale bez prefiksu: routing kieruje je do mastera
    # RM_BAZA, a tamte do rm_manager.sqlite. Dwie niezalezne tabele — patrz
    # komentarz przy `lock-po-projekcie` w ODCZYT.
    #
    # Warunek w `ON CONFLICT ... WHERE` jest tu calym mechanizmem wyscigu:
    # nadpisz wiersz TYLKO gdy blokada jest moja albo porzucona (bicie serca
    # starsze niz `granica`). Przy dwoch stacjach naraz serwer wykonuje
    # poleceniapo kolei, wiec drugi dostaje `rowcount = 0` i wie, ze przegral.
    # Sprawdzanie „czy wolny", a potem osobny zapis, dawalo dwoch zwyciezcow.
    "lock-przejmij": (
        "INSERT INTO project_locks"
        " (project_id, lock_id, uzytkownik, komputer, locked_at, last_heartbeat)"
        " VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(project_id) DO UPDATE SET"
        "   lock_id = excluded.lock_id, uzytkownik = excluded.uzytkownik,"
        "   komputer = excluded.komputer, locked_at = excluded.locked_at,"
        "   last_heartbeat = excluded.last_heartbeat"
        " WHERE (project_locks.uzytkownik = excluded.uzytkownik"
        "        AND project_locks.komputer = excluded.komputer)"
        "    OR project_locks.last_heartbeat IS NULL"
        "    OR project_locks.last_heartbeat < ?",
        ["project_id", "lock_id", "uzytkownik", "komputer", "locked_at",
         "last_heartbeat", "granica"],
    ),
    # Przejecie na sile: bez patrzenia na wlasciciela ani wiek.
    "lock-przejmij-sila": (
        "INSERT INTO project_locks"
        " (project_id, lock_id, uzytkownik, komputer, locked_at, last_heartbeat)"
        " VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(project_id) DO UPDATE SET"
        "   lock_id = excluded.lock_id, uzytkownik = excluded.uzytkownik,"
        "   komputer = excluded.komputer, locked_at = excluded.locked_at,"
        "   last_heartbeat = excluded.last_heartbeat",
        ["project_id", "lock_id", "uzytkownik", "komputer", "locked_at", "last_heartbeat"],
    ),
    "lock-zwolnij": (
        "DELETE FROM project_locks WHERE project_id = ?",
        ["project_id"],
    ),
    "lock-zwolnij-moj": (
        "DELETE FROM project_locks"
        " WHERE project_id = ? AND uzytkownik = ? AND komputer = ?",
        ["project_id", "uzytkownik", "komputer"],
    ),
    "lock-zwolnij-moje-poza": (
        "DELETE FROM project_locks"
        " WHERE uzytkownik = ? AND komputer = ?"
        "   AND project_id NOT IN (SELECT value FROM json_each(?))",
        ["uzytkownik", "komputer", "idy_json"],
    ),
    "lock-zwolnij-komputer": (
        "DELETE FROM project_locks WHERE komputer = ?",
        ["komputer"],
    ),
    "lock-bicie-serca": (
        "UPDATE project_locks SET last_heartbeat = ?"
        " WHERE project_id = ? AND uzytkownik = ? AND komputer = ?",
        ["last_heartbeat", "project_id", "uzytkownik", "komputer"],
    ),
    "lock-przepisz-uzytkownika": (
        "UPDATE project_locks SET uzytkownik = ?, last_heartbeat = ?"
        " WHERE komputer = ? AND uzytkownik = ?",
        ["nowy", "last_heartbeat", "komputer", "stary"],
    ),
    "locki-usun-przeterminowane": (
        "DELETE FROM project_locks"
        " WHERE last_heartbeat IS NULL OR last_heartbeat < ?",
        ["granica"],
    ),
    # ── ustawienia ────────────────────────────────────────────────────
    # UPSERT zamiast SELECT-potem-INSERT-albo-UPDATE: dziś klient robi to
    # w trzech krokach (RM_BAZA_v15…py:20026), co przy dwóch stanowiskach
    # naraz potrafi wstawić duplikat. Serwer ma jedno połączenie, ale
    # UPSERT i tak jest krótszy i szczelniejszy.
    "settings-set": (
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
        " updated_at = excluded.updated_at",
        ["key", "value", "updated_at"],
    ),

    # ── dostawcy ──────────────────────────────────────────────────────
    # ⚠️ suppliers NIE MA stałego schematu. Zależnie od historii instalacji
    # kolumny nazywają się `contact` albo `contact_info`, `phone` albo
    # `phone_default`, `description` / `notes` (na produkcji 11.09.2026:
    # contact_info, phone_default, email_default, notes). Dlatego dzisiejszy
    # kod buduje INSERT dynamicznie z wykrytych kolumn (RM_BAZA…py:22636).
    #
    # Serwer robi to samo, ale RAZ przy starcie — patrz `zbuduj_operacje_dostawcow`.
    # Tu zostają tylko operacje niezależne od aliasów.
    "supplier-delete": (
        "DELETE FROM suppliers WHERE supplier_id = ?",
        ["supplier_id"],
    ),
    "supplier-set-active": (
        "UPDATE suppliers SET is_active = ? WHERE supplier_id = ?",
        ["is_active", "supplier_id"],
    ),

    # ── użytkownicy + dziennik zmian ──────────────────────────────────
    "user-add": (
        "INSERT INTO users (username, display_name, role) VALUES (?, ?, ?)",
        ["username", "display_name", "role"],
    ),
    "user-edit": (
        "UPDATE users SET username = ?, display_name = ?, role = ? WHERE id = ?",
        ["username", "display_name", "role", "id"],
    ),
    "user-delete": (
        "DELETE FROM users WHERE id = ?",
        ["id"],
    ),
    "user-audit-add": (
        "INSERT INTO user_changes_log"
        " (action, user_id, username, display_name, role, changed_by, timestamp, details)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ["action", "user_id", "username", "display_name", "role",
         "changed_by", "timestamp", "details"],
    ),

    # ── projekty (nagłówek w masterze; zawartość siedzi w plikach) ─────
    # Używa tego RM_MANAGER.sync_to_master — jeden z dwóch zewnętrznych
    # pisarzy do mastera (§10 planu).
    # RM_MANAGER.sync_to_master. COALESCE(?, kolumna): NULL w parametrze
    # znaczy „nie ruszaj tego pola" — dzięki temu jedna operacja zastępuje
    # dynamicznie budowany UPDATE z listą zmienionych kolumn, a logika
    # WRITE ONCE dla montażu zostaje po stronie wołającego.
    "project-status-sync": (
        "UPDATE projects SET"
        "   status       = COALESCE(?, status),"
        "   designer     = COALESCE(?, designer),"
        "   montaz       = COALESCE(?, montaz),"
        "   fat          = COALESCE(?, fat),"
        "   completed_at = COALESCE(?, completed_at)"
        " WHERE project_id = ?",
        ["status", "designer", "montaz", "fat", "completed_at", "project_id"],
    ),
    # ⚠️ `status` i `project_status` to DWIE RÓŻNE kolumny w `projects`:
    # `status` to faza projektu (PROJEKT/MONTAZ/…), `project_status` to
    # osobne pole używane przez RM_MANAGER. Nie mylić — operacja poniżej
    # (`project-status-set`) pisze do tego drugiego.
    "project-status-zmien": (
        "UPDATE projects SET status = ?, status_changed_at = ?"
        " WHERE project_id = ?",
        ["status", "status_changed_at", "project_id"],
    ),
    # Sam znacznik czasu, bez ruszania `status` — używa go tryb
    # wielostatusowy, gdzie stan trzyma `project_statuses`, a w `projects`
    # aktualizujemy tylko „kiedy ostatnio coś się zmieniło".
    "project-status-znacznik": (
        "UPDATE projects SET status_changed_at = ? WHERE project_id = ?",
        ["status_changed_at", "project_id"],
    ),
    # Data zakończenia tylko gdy jeszcze pusta — COALESCE chroni pierwotną.
    "project-zakonczony": (
        "UPDATE projects SET completed_at = COALESCE(completed_at, ?)"
        " WHERE project_id = ?",
        ["completed_at", "project_id"],
    ),
    "project-status-set": (
        "UPDATE projects SET project_status = ? WHERE project_id = ?",
        ["project_status", "project_id"],
    ),
    "project-priorytet-set": (
        "UPDATE projects SET priority = ? WHERE project_id = ?",
        ["priority", "project_id"],
    ),
    # ── Projekty: dodanie / edycja / usunięcie ────────────────────────
    # Schemat `projects` jest ustalony (migracje serwera), więc operacje są
    # statyczne — inaczej niż przy dostawcach, gdzie nazwy kolumn różnią się
    # między instalacjami.
    # `project_id` przekazywany jawnie albo NULL. NULL = SQLite nadaje
    # kolejny numer sam (kolumna jest INTEGER PRIMARY KEY), a wołający
    # odczytuje go z `lastrowid` w odpowiedzi.
    "project-add": (
        "INSERT INTO projects"
        " (project_id, name, path, project_type, active, designer, status,"
        "  created_at)"
        " VALUES (?, ?, ?, COALESCE(?, 'MACHINE'), 1, ?,"
        "         COALESCE(?, 'PROJEKT'), datetime('now','localtime'))",
        ["project_id", "name", "path", "project_type", "designer", "status"],
    ),
    # ⚠️ COALESCE(?, kolumna): NULL znaczy „nie ruszaj tego pola".
    # Bez tego edycja samej nazwy wyczyściłaby projektantowi resztę danych.
    "project-edit": (
        "UPDATE projects SET"
        "   name              = COALESCE(?, name),"
        "   path              = COALESCE(?, path),"
        "   designer          = COALESCE(?, designer),"
        "   montaz            = COALESCE(?, montaz),"
        "   sat               = COALESCE(?, sat),"
        "   fat               = COALESCE(?, fat),"
        "   completed_at      = COALESCE(?, completed_at),"
        "   expected_delivery = COALESCE(?, expected_delivery),"
        "   received_percent  = COALESCE(?, received_percent)"
        " WHERE project_id = ?",
        ["name", "path", "designer", "montaz", "sat", "fat", "completed_at",
         "expected_delivery", "received_percent", "project_id"],
    ),
    "project-delete": (
        "DELETE FROM projects WHERE project_id = ?",
        ["project_id"],
    ),
    "project-set-active": (
        "UPDATE projects SET active = ? WHERE project_id = ?",
        ["active", "project_id"],
    ),
    "project-received-percent": (
        "UPDATE projects SET received_percent = ? WHERE project_id = ?",
        ["received_percent", "project_id"],
    ),

    # ── sesje klientów (bramka wersji) ────────────────────────────────
    "session-heartbeat": (
        "INSERT INTO client_sessions"
        " (host, username, role, exe_path, exe_size, exe_mtime, build_id, pid,"
        "  started_at, last_seen, ended_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)"
        " ON CONFLICT(host) DO UPDATE SET"
        "   username = excluded.username, role = excluded.role,"
        "   exe_path = excluded.exe_path, exe_size = excluded.exe_size,"
        "   exe_mtime = excluded.exe_mtime, build_id = excluded.build_id,"
        "   pid = excluded.pid,"
        "   started_at = CASE WHEN client_sessions.pid = excluded.pid"
        "                     THEN client_sessions.started_at"
        "                     ELSE excluded.started_at END,"
        "   last_seen = excluded.last_seen, ended_at = NULL",
        ["host", "username", "role", "exe_path", "exe_size", "exe_mtime",
         "build_id", "pid", "started_at", "last_seen"],
    ),
    "session-close": (
        "UPDATE client_sessions SET ended_at = ?, last_seen = ?"
        " WHERE host = ? AND pid = ?",
        ["ended_at", "last_seen", "host", "pid"],
    ),

    # ══ PORTAL RFQ — synchronizator (rm_sync_agent) ═════════════════
    # ══ KALKULATORY ═════════════════════════════════════════════════
    "material-zapisz": (
        "INSERT INTO material_prices (material, density, price_per_kg, updated_at)"
        " VALUES (?, ?, ?, ?)"
        " ON CONFLICT(material) DO UPDATE SET"
        "   density      = excluded.density,"
        "   price_per_kg = excluded.price_per_kg,"
        "   updated_at   = excluded.updated_at",
        ["material", "density", "price_per_kg", "updated_at"],
    ),

# ══ RM_MANAGER — zapisy ═══
    "rmm-plc-global-recipients-dodaj": (
        "INSERT OR IGNORE INTO plc_global_recipients (setting_key,"
        " recipients_json) VALUES ('default_recipients', '[]')",
        [],
    ),
    "rmm-line-projects-usun-po-line-id": (
        "DELETE FROM line_projects WHERE line_id = ?",
        ['line_id'],
    ),
    "rmm-payment-history-dodaj": (
        "INSERT INTO payment_history (project_id, percentage,"
        " payment_date, action, changed_by, old_date, changed_at) VALUES"
        " (?, ?, ?, 'MODIFIED', ?, ?, CURRENT_TIMESTAMP)",
        ['project_id', 'percentage', 'payment_date', 'changed_by', 'old_date'],
    ),
    "rmm-in-app-notifications-zmien-po-id": (
        "UPDATE in_app_notifications SET is_read = 1, read_at ="
        " CURRENT_TIMESTAMP, read_by = ? WHERE id = ?",
        ['read_by', 'id'],
    ),
    "rmm-rm-user-permissions-dodaj": (
        "INSERT INTO rm_user_permissions (role, can_start_stage,"
        " can_end_stage, can_edit_dates, can_sync_master,"
        " can_critical_path, can_manage_permissions) VALUES (?, ?, ?, ?, ?,"
        " ?, ?)",
        ['role', 'can_start_stage', 'can_end_stage', 'can_edit_dates', 'can_sync_master', 'can_critical_path', 'can_manage_permissions'],
    ),
    "rmm-rm-user-permissions-zmien-po-role-ADM": (
        "UPDATE rm_user_permissions SET can_manage_permissions = 1,"
        " updated_at = CURRENT_TIMESTAMP WHERE role = 'ADMIN' AND"
        " can_manage_permissions = 0",
        [],
    ),
    "rmm-payment-notification-config-dodaj": (
        "INSERT OR IGNORE INTO payment_notification_config (id,"
        " trigger_percentage, email_recipients, enabled) VALUES (1, 100,"
        " '[]', 1)",
        [],
    ),
    "rmm-resource-constraints-dodaj": (
        "INSERT INTO resource_constraints (constraint_type, category,"
        " stage_code, max_parallel, description) VALUES (?, ?, ?, ?, ?)",
        ['constraint_type', 'category', 'stage_code', 'max_parallel', 'description'],
    ),
    "rmm-employee-availability-zmien-po-status": (
        "UPDATE employee_availability SET status = 'ZATWIERDZONY' WHERE"
        " status = 'OCZEKUJE'",
        [],
    ),
    "rmm-priority-weights-dodaj": (
        "INSERT INTO priority_weights (level, label, weight) VALUES (?, ?,"
        " ?)",
        ['level', 'label', 'weight'],
    ),
    "rmm-production-lines-dodaj": (
        "INSERT INTO production_lines (name, description,"
        " parallel_stages_csv, created_by, updated_by) VALUES (?, ?, ?, ?,"
        " ?)",
        ['name', 'description', 'parallel_stages_csv', 'created_by', 'updated_by'],
    ),
    "rmm-production-lines-zmien-po-id": (
        "UPDATE production_lines SET name = ?, description = ?,"
        " parallel_stages_csv = ?, updated_at = CURRENT_TIMESTAMP,"
        " updated_by = ? WHERE id = ?",
        ['name', 'description', 'parallel_stages_csv', 'updated_by', 'id'],
    ),
    "rmm-line-projects-usun-po-project-id": (
        "DELETE FROM line_projects WHERE project_id = ?",
        ['project_id'],
    ),
    "rmm-line-projects-dodaj": (
        "INSERT INTO line_projects (line_id, project_id) VALUES (?, ?)",
        ['line_id', 'project_id'],
    ),
    "rmm-production-lines-usun-po-id": (
        "DELETE FROM production_lines WHERE id = ?",
        ['id'],
    ),
    "rmm-project-file-tracking-dodaj": (
        "INSERT OR REPLACE INTO project_file_tracking (project_id,"
        " project_name, file_path, file_birth_time, last_verified_at,"
        " verification_status) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)",
        ['project_id', 'project_name', 'file_path', 'file_birth_time', 'verification_status'],
    ),
    "rmm-project-file-tracking-zmien-po-project-id": (
        "UPDATE project_file_tracking SET verification_status = 'MISSING',"
        " last_verified_at = CURRENT_TIMESTAMP WHERE project_id = ?",
        ['project_id'],
    ),
    "rmm-project-file-tracking-zmien-po-project-id-2": (
        "UPDATE project_file_tracking SET verification_status ="
        " 'BIRTH_MISMATCH', last_verified_at = CURRENT_TIMESTAMP WHERE"
        " project_id = ?",
        ['project_id'],
    ),
    "rmm-project-file-tracking-zmien-po-project-id-3": (
        "UPDATE project_file_tracking SET verification_status = 'OK',"
        " last_verified_at = CURRENT_TIMESTAMP WHERE project_id = ?",
        ['project_id'],
    ),
    "rmm-project-file-tracking-usun-po-project-id": (
        "DELETE FROM project_file_tracking WHERE project_id = ?",
        ['project_id'],
    ),
    "rmm-sync-log-dodaj": (
        "INSERT INTO sync_log (sync_date, sync_timestamp, projects_synced,"
        " user, notes) VALUES (?, ?, ?, ?, ?)",
        ['sync_date', 'sync_timestamp', 'projects_synced', 'user', 'notes'],
    ),
    "rmm-rm-user-permissions-dodaj-2": (
        "INSERT INTO rm_user_permissions (role, can_start_stage,"
        " can_end_stage, can_edit_dates, can_sync_master,"
        " can_critical_path, can_manage_permissions, updated_at) VALUES (?,"
        " ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(role) DO UPDATE"
        " SET can_start_stage = excluded.can_start_stage, can_end_stage ="
        " excluded.can_end_stage, can_edit_dates = excluded.can_edit_dates,"
        " can_sync_master = excluded.can_sync_master, can_critical_path ="
        " excluded.can_critical_path, can_manage_permissions ="
        " excluded.can_manage_permissions, updated_at = CURRENT_TIMESTAMP",
        ['role', 'can_start_stage', 'can_end_stage', 'can_edit_dates', 'can_sync_master', 'can_critical_path', 'can_manage_permissions'],
    ),
    "rmm-rm-feature-user-permissions-usun-po-feature": (
        "DELETE FROM rm_feature_user_permissions WHERE feature = ?",
        ['feature'],
    ),
    "rmm-rm-feature-user-permissions-dodaj": (
        "INSERT INTO rm_feature_user_permissions (feature, username)"
        " VALUES (?, ?)",
        ['feature', 'username'],
    ),
    "rmm-audit-log-dodaj": (
        "INSERT INTO audit_log (employee_id, entity_type, entity_id,"
        " action, field, old_value, new_value, note, changed_by) VALUES (?,"
        " ?, ?, ?, ?, ?, ?, ?, ?)",
        ['employee_id', 'entity_type', 'entity_id', 'action', 'field', 'old_value', 'new_value', 'note', 'changed_by'],
    ),
    "rmm-employees-zmien-po-id": (
        "UPDATE employees SET name = ?, category = ?, description = ?,"
        " contact_info = ?, phone = ?, email = ?, podmiot = ?, user_login ="
        " ?, is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        ['name', 'category', 'description', 'contact_info', 'phone', 'email', 'podmiot', 'user_login', 'is_active', 'id'],
    ),
    "rmm-employees-dodaj": (
        "INSERT INTO employees (name, category, description, contact_info,"
        " phone, email, podmiot, user_login, is_active) VALUES (?, ?, ?, ?,"
        " ?, ?, ?, ?, ?)",
        ['name', 'category', 'description', 'contact_info', 'phone', 'email', 'podmiot', 'user_login', 'is_active'],
    ),
    "rmm-employees-usun-po-id": (
        "DELETE FROM employees WHERE id = ?",
        ['id'],
    ),
    "rmm-employees-zmien-po-id-2": (
        "UPDATE employees SET master_max_parallel = ?, updated_at ="
        " CURRENT_TIMESTAMP WHERE id = ?",
        ['master_max_parallel', 'id'],
    ),
    "rmm-priority-weights-dodaj-2": (
        "INSERT INTO priority_weights (level, label, weight) VALUES (?, ?,"
        " ?) ON CONFLICT(level) DO UPDATE SET weight = excluded.weight,"
        " label = excluded.label",
        ['level', 'label', 'weight'],
    ),
    "rmm-transports-zmien-po-id": (
        "UPDATE transports SET name = ?, description = ?, contact_info ="
        " ?, is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        ['name', 'description', 'contact_info', 'is_active', 'id'],
    ),
    "rmm-transports-dodaj": (
        "INSERT INTO transports (name, description, contact_info,"
        " is_active) VALUES (?, ?, ?, ?)",
        ['name', 'description', 'contact_info', 'is_active'],
    ),
    "rmm-transports-usun-po-id": (
        "DELETE FROM transports WHERE id = ?",
        ['id'],
    ),
    "rmm-payment-milestones-dodaj": (
        "INSERT INTO payment_milestones (project_id, percentage,"
        " payment_date, created_by, created_at, payment_type) VALUES (?, ?,"
        " ?, ?, CURRENT_TIMESTAMP, ?)",
        ['project_id', 'percentage', 'payment_date', 'created_by', 'payment_type'],
    ),
    "rmm-payment-history-dodaj-2": (
        "INSERT INTO payment_history (project_id, percentage,"
        " payment_date, action, changed_by, changed_at) VALUES (?, ?, ?,"
        " 'ADDED', ?, CURRENT_TIMESTAMP)",
        ['project_id', 'percentage', 'payment_date', 'changed_by'],
    ),
    "rmm-payment-milestones-zmien-po-project-id-percentage": (
        "UPDATE payment_milestones SET payment_date = ?, modified_by = ?,"
        " modified_at = CURRENT_TIMESTAMP WHERE project_id = ? AND"
        " percentage = ?",
        ['payment_date', 'modified_by', 'project_id', 'percentage'],
    ),
    "rmm-payment-milestones-zmien-po-project-id-payment-type": (
        "UPDATE payment_milestones SET payment_type = 'PŁATNOŚĆ',"
        " modified_by = ?, modified_at = CURRENT_TIMESTAMP WHERE project_id"
        " = ? AND payment_type = 'UMORZONY'",
        ['modified_by', 'project_id'],
    ),
    "rmm-payment-milestones-usun-po-project-id-percentage": (
        "DELETE FROM payment_milestones WHERE project_id = ? AND"
        " percentage = ?",
        ['project_id', 'percentage'],
    ),
    "rmm-payment-history-dodaj-3": (
        "INSERT INTO payment_history (project_id, percentage,"
        " payment_date, action, changed_by, old_date, changed_at) VALUES"
        " (?, ?, NULL, 'DELETED', ?, ?, CURRENT_TIMESTAMP)",
        ['project_id', 'percentage', 'changed_by', 'old_date'],
    ),
    "rmm-in-app-notifications-dodaj": (
        "INSERT INTO in_app_notifications (project_id, project_name,"
        " notification_type, message, created_by, created_at, is_read)"
        " VALUES (?, ?, 'PAYMENT', ?, ?, CURRENT_TIMESTAMP, 0)",
        ['project_id', 'project_name', 'message', 'created_by'],
    ),
    "rmm-payment-notifications-sent-dodaj": (
        "INSERT INTO payment_notifications_sent (project_id, project_name,"
        " percentage, payment_date, recipients, sent_by, email_status,"
        " error_message, sent_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?,"
        " CURRENT_TIMESTAMP)",
        ['project_id', 'project_name', 'percentage', 'payment_date', 'recipients', 'sent_by', 'email_status', 'error_message'],
    ),
    "rmm-plc-unlock-codes-dodaj": (
        "INSERT INTO plc_unlock_codes (project_id, code_type, unlock_code,"
        " description, created_by, created_at, is_used, expiry_date) VALUES"
        " (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 0, ?)",
        ['project_id', 'code_type', 'unlock_code', 'description', 'created_by', 'expiry_date'],
    ),
    "rmm-plc-unlock-codes-usun-po-id": (
        "DELETE FROM plc_unlock_codes WHERE id = ?",
        ['id'],
    ),
    "rmm-plc-global-recipients-dodaj-2": (
        "INSERT INTO plc_global_recipients (setting_key, recipients_json,"
        " updated_at) VALUES ('default_recipients', ?, CURRENT_TIMESTAMP)"
        " ON CONFLICT(setting_key) DO UPDATE SET recipients_json ="
        " excluded.recipients_json, updated_at = CURRENT_TIMESTAMP",
        ['recipients_json'],
    ),
    "rmm-plc-global-recipients-dodaj-3": (
        "INSERT INTO plc_global_recipients (setting_key, recipients_json,"
        " updated_at) VALUES ('payment_status_recipients', ?,"
        " CURRENT_TIMESTAMP) ON CONFLICT(setting_key) DO UPDATE SET"
        " recipients_json = excluded.recipients_json, updated_at ="
        " CURRENT_TIMESTAMP",
        ['recipients_json'],
    ),
    "rmm-plc-unlock-codes-zmien-po-id": (
        "UPDATE plc_unlock_codes SET is_used = 1, used_at ="
        " CURRENT_TIMESTAMP, used_by = ?, notes = ? WHERE id = ?",
        ['used_by', 'notes', 'id'],
    ),
    "rmm-plc-authorized-senders-dodaj": (
        "INSERT OR IGNORE INTO plc_authorized_senders (username, added_by,"
        " notes) VALUES (?, ?, ?)",
        ['username', 'added_by', 'notes'],
    ),
    "rmm-plc-authorized-senders-usun-po-username": (
        "DELETE FROM plc_authorized_senders WHERE username = ?",
        ['username'],
    ),
    "rmm-plc-unlock-codes-zmien-po-id-2": (
        "UPDATE plc_unlock_codes SET sent_at = CURRENT_TIMESTAMP, sent_by"
        " = ?, sent_via = 'EMAIL', is_used = 1, used_at = CURRENT_TIMESTAMP"
        " WHERE id = ?",
        ['sent_by', 'id'],
    ),
    "rmm-plc-unlock-codes-zmien-po-id-3": (
        "UPDATE plc_unlock_codes SET sent_at = CURRENT_TIMESTAMP, sent_by"
        " = ?, sent_via = 'SMS', is_used = 1, used_at = CURRENT_TIMESTAMP"
        " WHERE id = ?",
        ['sent_by', 'id'],
    ),
    "rmm-resource-constraints-zmien-po-id": (
        "UPDATE resource_constraints SET constraint_type = ?, category ="
        " ?, stage_code = ?, max_parallel = ?, description = ?, is_active ="
        " ?, modified_at = CURRENT_TIMESTAMP, modified_by = ? WHERE id = ?",
        ['constraint_type', 'category', 'stage_code', 'max_parallel', 'description', 'is_active', 'modified_by', 'id'],
    ),
    "rmm-resource-constraints-dodaj-2": (
        "INSERT INTO resource_constraints (constraint_type, category,"
        " stage_code, max_parallel, description, is_active, created_by)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        ['constraint_type', 'category', 'stage_code', 'max_parallel', 'description', 'is_active', 'created_by'],
    ),
    "rmm-resource-constraints-usun-po-id": (
        "DELETE FROM resource_constraints WHERE id = ?",
        ['id'],
    ),
    "rmm-absence-exclusion-groups-zmien-po-id": (
        "UPDATE absence_exclusion_groups SET name = ? WHERE id = ?",
        ['name', 'id'],
    ),
    "rmm-absence-exclusion-members-usun": (
        "DELETE FROM absence_exclusion_members WHERE group_id = ?",
        ['group_id'],
    ),
    "rmm-absence-exclusion-groups-dodaj": (
        "INSERT INTO absence_exclusion_groups (name, created_by) VALUES"
        " (?, ?)",
        ['name', 'created_by'],
    ),
    "rmm-absence-exclusion-members-dodaj": (
        "INSERT OR IGNORE INTO absence_exclusion_members (group_id,"
        " employee_id) VALUES (?, ?)",
        ['group_id', 'employee_id'],
    ),
    "rmm-absence-exclusion-groups-usun-po-id": (
        "DELETE FROM absence_exclusion_groups WHERE id = ?",
        ['id'],
    ),
    "rmm-employee-availability-zmien-po-id": (
        "UPDATE employee_availability SET employee_id = ?, date_from = ?,"
        " date_to = ?, reason = ?, notes = ?, time_from = ?, time_to = ?,"
        " days_override = ? WHERE id = ?",
        ['employee_id', 'date_from', 'date_to', 'reason', 'notes', 'time_from', 'time_to', 'days_override', 'id'],
    ),
    "rmm-employee-availability-zmien-po-id-2": (
        "UPDATE employee_availability SET status = ? WHERE id = ?",
        ['status', 'id'],
    ),
    "rmm-employee-availability-dodaj": (
        "INSERT INTO employee_availability (employee_id, date_from,"
        " date_to, reason, notes, created_by, time_from, time_to,"
        " days_override, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ['employee_id', 'date_from', 'date_to', 'reason', 'notes', 'created_by', 'time_from', 'time_to', 'days_override', 'status'],
    ),
    "rmm-employee-availability-usun-po-id": (
        "DELETE FROM employee_availability WHERE id = ?",
        ['id'],
    ),
    "rmm-service-trips-dodaj": (
        "INSERT INTO service_trips (employee_id, project_id,"
        " client_or_place, trip_type, date_from, date_to, status, note,"
        " created_by, working_days) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ['employee_id', 'project_id', 'client_or_place', 'trip_type', 'date_from', 'date_to', 'status', 'note', 'created_by', 'working_days'],
    ),
    "rmm-service-trips-usun-po-id": (
        "DELETE FROM service_trips WHERE id = ?",
        ['id'],
    ),
    "rmm-employee-vacation-base-dodaj": (
        "INSERT INTO employee_vacation_base (employee_id, days,"
        " updated_by) VALUES (?, ?, ?) ON CONFLICT(employee_id) DO UPDATE"
        " SET days = excluded.days, updated_at = CURRENT_TIMESTAMP,"
        " updated_by = excluded.updated_by",
        ['employee_id', 'days', 'updated_by'],
    ),
    "rmm-employee-vacation-quota-dodaj": (
        "INSERT INTO employee_vacation_quota (employee_id, year, days,"
        " updated_by) VALUES (?, ?, ?, ?) ON CONFLICT(employee_id, year) DO"
        " UPDATE SET days = excluded.days, updated_at = CURRENT_TIMESTAMP,"
        " updated_by = excluded.updated_by",
        ['employee_id', 'year', 'days', 'updated_by'],
    ),
    "rmm-employee-vacation-quota-usun-po-employee-id-year": (
        "DELETE FROM employee_vacation_quota WHERE employee_id = ? AND"
        " year = ?",
        ['employee_id', 'year'],
    ),
    "rmm-employee-carryover-override-usun-po-employee-id-year": (
        "DELETE FROM employee_carryover_override WHERE employee_id = ? AND"
        " year = ?",
        ['employee_id', 'year'],
    ),
    "rmm-employee-carryover-override-dodaj": (
        "INSERT INTO employee_carryover_override (employee_id, year, days,"
        " updated_by) VALUES (?, ?, ?, ?) ON CONFLICT(employee_id, year) DO"
        " UPDATE SET days = excluded.days, updated_at = CURRENT_TIMESTAMP,"
        " updated_by = excluded.updated_by",
        ['employee_id', 'year', 'days', 'updated_by'],
    ),
    "rmm-company-calendar-dodaj": (
        "INSERT OR REPLACE INTO company_calendar (date, day_type,"
        " description, created_by) VALUES (?, ?, ?, ?)",
        ['date', 'day_type', 'description', 'created_by'],
    ),
    "rmm-company-calendar-usun-po-date": (
        "DELETE FROM company_calendar WHERE date = ?",
        ['date'],
    ),
    "rmm-optimization-runs-dodaj": (
        "INSERT INTO optimization_runs (run_mode, project_ids_json,"
        " date_range_start, date_range_end, constraints_snapshot,"
        " result_json, score_before, score_after, solver_status,"
        " solver_time_ms, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
        " ?)",
        ['run_mode', 'project_ids_json', 'date_range_start', 'date_range_end', 'constraints_snapshot', 'result_json', 'score_before', 'score_after', 'solver_status', 'solver_time_ms', 'created_by'],
    ),
    "rmm-optimization-runs-zmien-po-id": (
        "UPDATE optimization_runs SET applied = 1, applied_at ="
        " CURRENT_TIMESTAMP, applied_by = ? WHERE id = ?",
        ['applied_by', 'id'],
    ),
    "rmm-project-file-tracking-usun": (
        "DELETE FROM project_file_tracking",
        [],
    ),

    # ── blokady projektów: przejęcie, zwolnienie, bicie serca ────────────
    # Przejęcie warunkowe: nadpisze wiersz TYLKO gdy blokada jest moja albo
    # porzucona (bicie serca starsze niż `granica`). Warunek i zapis muszą być
    # jednym poleceniem — przy sprawdzaniu osobno dwie stacje potrafią obie
    # uznać, że wygrały. Klient rozpoznaje przegraną po `rowcount = 0`.
    # ── sesje uzytkownikow ───────────────────────────────────────────────
    #
    # Wyscig rozstrzyga indeks UNIQUE(user_id, hostname, app_name): drugie
    # logowanie tego samego usera z TEGO SAMEGO komputera nadpisuje wiersz
    # (to normalne — restart programu), a z INNEGO tworzy osobny, ktory
    # klient widzi i odrzuca. Pliki JSON dawaly tu okno kilku ms, w ktorym
    # powstawaly dwie sesje naraz.
    # ⚠️ Warunek `WHERE NOT EXISTS` jest CALYM mechanizmem wyscigu i musi
    # zostac w JEDNYM poleceniu.
    #
    # Sprawdzenie „czy user ma zywa sesje gdzie indziej", a potem osobny
    # INSERT, przepuszczalo obu proszacych: serwer wykonuje polecenia
    # pojedynczo, ale miedzy dwa polecenia jednego klienta wchodzi polecenie
    # drugiego. Zmierzone — dwie maszyny logowaly sie jednoczesnie i OBIE
    # dostawaly „ok" (12.09.2026). Tutaj serwer sam sprawdza i zapisuje bez
    # przerwy, a przegrany dostaje `rowcount = 0`.
    #
    # `hostname <> ?` w podzapytaniu: wlasny komputer nie blokuje sam siebie,
    # bo ponowne uruchomienie programu ma nadpisac wlasny wiersz (UPSERT).
    "rmm-sesja-zaloz": (
        "INSERT INTO active_sessions"
        " (session_id, user_id, username, hostname, pid, app_name,"
        "  login_at, last_heartbeat, client_info)"
        " SELECT ?,?,?,?,?,?,?,?,?"
        "  WHERE NOT EXISTS ("
        "    SELECT 1 FROM active_sessions"
        "     WHERE user_id = ? AND app_name = ? AND hostname <> ?"
        "       AND last_heartbeat >= ?)"
        " ON CONFLICT(user_id, hostname, app_name) DO UPDATE SET"
        "   session_id = excluded.session_id, pid = excluded.pid,"
        "   login_at = excluded.login_at,"
        "   last_heartbeat = excluded.last_heartbeat,"
        "   client_info = excluded.client_info",
        ["session_id", "user_id", "username", "hostname", "pid", "app_name",
         "login_at", "last_heartbeat", "client_info",
         "user_id2", "app_name2", "hostname2", "granica"],
    ),
    "rmm-sesja-bicie-serca": (
        "UPDATE active_sessions SET last_heartbeat = ? WHERE session_id = ?",
        ["last_heartbeat", "session_id"],
    ),
    "rmm-sesja-usun": (
        "DELETE FROM active_sessions WHERE session_id = ?",
        ["session_id"],
    ),
    "rmm-sesje-usun-uzytkownika-poza": (
        "DELETE FROM active_sessions"
        " WHERE user_id = ? AND session_id <> ?",
        ["user_id", "session_id"],
    ),
    "rmm-sesje-usun-komputer": (
        "DELETE FROM active_sessions WHERE hostname = ?",
        ["hostname"],
    ),
    "rmm-sesje-usun-przeterminowane": (
        "DELETE FROM active_sessions"
        " WHERE last_heartbeat IS NULL OR last_heartbeat < ?",
        ["granica"],
    ),
    "rmm-lock-przejmij": (
        "INSERT INTO project_locks"
        " (project_id, lock_id, uzytkownik, komputer, locked_at, last_heartbeat)"
        " VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(project_id) DO UPDATE SET"
        "   lock_id = excluded.lock_id, uzytkownik = excluded.uzytkownik,"
        "   komputer = excluded.komputer, locked_at = excluded.locked_at,"
        "   last_heartbeat = excluded.last_heartbeat"
        " WHERE (project_locks.uzytkownik = excluded.uzytkownik"
        "        AND project_locks.komputer = excluded.komputer)"
        "    OR project_locks.last_heartbeat IS NULL"
        "    OR project_locks.last_heartbeat < ?",
        ["project_id", "lock_id", "uzytkownik", "komputer", "locked_at",
         "last_heartbeat", "granica"],
    ),
    # Przejęcie na siłę: bez patrzenia na właściciela ani wiek.
    "rmm-lock-przejmij-sila": (
        "INSERT INTO project_locks"
        " (project_id, lock_id, uzytkownik, komputer, locked_at, last_heartbeat)"
        " VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(project_id) DO UPDATE SET"
        "   lock_id = excluded.lock_id, uzytkownik = excluded.uzytkownik,"
        "   komputer = excluded.komputer, locked_at = excluded.locked_at,"
        "   last_heartbeat = excluded.last_heartbeat",
        ["project_id", "lock_id", "uzytkownik", "komputer", "locked_at", "last_heartbeat"],
    ),
    "rmm-lock-zwolnij": (
        "DELETE FROM project_locks WHERE project_id = ?",
        ["project_id"],
    ),
    "rmm-lock-zwolnij-moj": (
        "DELETE FROM project_locks"
        " WHERE project_id = ? AND uzytkownik = ? AND komputer = ?",
        ["project_id", "uzytkownik", "komputer"],
    ),
    "rmm-lock-zwolnij-moje-poza": (
        "DELETE FROM project_locks"
        " WHERE uzytkownik = ? AND komputer = ?"
        "   AND project_id NOT IN (SELECT value FROM json_each(?))",
        ["uzytkownik", "komputer", "idy_json"],
    ),
    "rmm-lock-zwolnij-komputer": (
        "DELETE FROM project_locks WHERE komputer = ?",
        ["komputer"],
    ),
    "rmm-lock-bicie-serca": (
        "UPDATE project_locks SET last_heartbeat = ?"
        " WHERE project_id = ? AND uzytkownik = ? AND komputer = ?",
        ["last_heartbeat", "project_id", "uzytkownik", "komputer"],
    ),
    "rmm-lock-przepisz-uzytkownika": (
        "UPDATE project_locks SET uzytkownik = ?, last_heartbeat = ?"
        " WHERE komputer = ? AND uzytkownik = ?",
        ["nowy", "last_heartbeat", "komputer", "stary"],
    ),
    "rmm-locki-usun-przeterminowane": (
        "DELETE FROM project_locks"
        " WHERE last_heartbeat IS NULL OR last_heartbeat < ?",
        ["granica"],
    ),
    # ── definicje etapów: uzupełnianie ze STAGE_DEFINITIONS w kodzie ──────
    "rmm-stage-definition-dodaj": (
        "INSERT OR IGNORE INTO stage_definitions"
        " (code, display_name, color, is_milestone) VALUES (?, ?, ?, ?)",
        ["code", "display_name", "color", "is_milestone"],
    ),
    "rmm-stage-definition-zmien": (
        "UPDATE stage_definitions SET display_name = ?, color = ?, is_milestone = ?"
        " WHERE code = ?",
        ["display_name", "color", "is_milestone", "code"],
    ),
    # ══ RM_MANAGER — zapisy wcześniej sklejane dynamicznie ══════════
    #
    # ⚠️ COALESCE(?, kolumna): NULL znaczy „nie ruszaj tego pola".
    # Klient budował `SET` tylko ze zmienionych kolumn; tutaj przekazuje
    # komplet, a NULL-e zostawiają wartości nietknięte. Bez tego edycja
    # samego telefonu wyczyściłaby pracownikowi resztę danych.
    #
    # Wyjazdy serwisowe CELOWO nie mają wersji z COALESCE: `working_days`
    # musi dać się ustawić na NULL (gdy wyjazd przestaje być ZREALIZOWANY),
    # a COALESCE by to zignorował — patrz `rmm-service-trip-nadpisz`.
    "rmm-employee-zmien": (
        "UPDATE employees SET"
        "   name                = COALESCE(?, name),"
        "   category            = COALESCE(?, category),"
        "   description         = COALESCE(?, description),"
        "   contact_info        = COALESCE(?, contact_info),"
        "   is_active           = COALESCE(?, is_active),"
        "   phone               = COALESCE(?, phone),"
        "   email               = COALESCE(?, email),"
        "   master_max_parallel = COALESCE(?, master_max_parallel),"
        "   podmiot             = COALESCE(?, podmiot),"
        "   user_login          = COALESCE(?, user_login),"
        "   updated_at          = datetime('now','localtime')"
        " WHERE id = ?",
        ["name", "category", "description", "contact_info", "is_active",
         "phone", "email", "master_max_parallel", "podmiot", "user_login",
         "id"],
    ),
    # Decyzja o wniosku urlopowym. `decided_by` bywa świadomie czyszczone
    # (cofnięcie decyzji), więc NIE przez COALESCE — pusta wartość ma
    # tu znaczyć „wyczyść", nie „zostaw".
    # Edycja kodu PLC: klient przekazuje tylko zmienione pola (żadne nie
    # jest czyszczone do NULL), więc COALESCE jest tu właściwe.
    "rmm-plc-code-zmien": (
        "UPDATE plc_unlock_codes SET"
        "   unlock_code = COALESCE(?, unlock_code),"
        "   description = COALESCE(?, description),"
        "   modified_by = ?, modified_at = CURRENT_TIMESTAMP"
        " WHERE id = ?",
        ["unlock_code", "description", "modified_by", "id"],
    ),
    # Konfiguracja powiadomień o płatnościach — zmiana wybranych pól.
    # COALESCE jest tu właściwe: żadnego z tych pól nie czyści się do NULL
    # (klient przekazuje tylko to, co user zmienił w oknie ustawień).
    "rmm-payment-notification-config-zmien": (
        "UPDATE payment_notification_config SET"
        "   email_recipients   = COALESCE(?, email_recipients),"
        "   smtp_server        = COALESCE(?, smtp_server),"
        "   smtp_port          = COALESCE(?, smtp_port),"
        "   smtp_user          = COALESCE(?, smtp_user),"
        "   smtp_password      = COALESCE(?, smtp_password),"
        "   enabled            = COALESCE(?, enabled),"
        "   trigger_percentage = COALESCE(?, trigger_percentage),"
        "   modified_at        = CURRENT_TIMESTAMP"
        " WHERE id = 1",
        ["email_recipients", "smtp_server", "smtp_port", "smtp_user",
         "smtp_password", "enabled", "trigger_percentage"],
    ),
    # Pełne nadpisanie wyjazdu — klient scala zmienione pola z aktualnym
    # wierszem i przysyła komplet. NULL tutaj ZNACZY NULL.
    "rmm-service-trip-nadpisz": (
        "UPDATE service_trips SET"
        "   employee_id = ?, project_id = ?, client_or_place = ?, trip_type = ?,"
        "   date_from = ?, date_to = ?, status = ?, note = ?, working_days = ?"
        " WHERE id = ?",
        ["employee_id", "project_id", "client_or_place", "trip_type",
         "date_from", "date_to", "status", "note", "working_days", "id"],
    ),
    "rmm-nieobecnosc-decyzja": (
        "UPDATE employee_availability SET"
        "   status = ?, decided_by = ?, decided_at = ?, decision_note = ?"
        " WHERE id = ?",
        ["status", "decided_by", "decided_at", "decision_note", "id"],
    ),

    # ══ STATUSY PROJEKTÓW ═══════════════════════════════════════════
    # Zestaw statusów podmienia się w całości: DELETE + INSERT-y jednym
    # batchem (jedna transakcja), inaczej zerwane połączenie zostawiłoby
    # projekt bez żadnego statusu.
    "statusy-wyczysc": (
        "DELETE FROM project_statuses WHERE project_id = ?",
        ["project_id"],
    ),
    "status-dodaj": (
        "INSERT INTO project_statuses (project_id, status, set_at, set_by)"
        " VALUES (?, ?, ?, ?)",
        ["project_id", "status", "set_at", "set_by"],
    ),
    # Dziennik pojedynczych zdarzeń: ADDED / REMOVED.
    "status-zmiana-zapisz": (
        "INSERT INTO project_status_changes"
        " (project_id, status, action, changed_at, changed_by, notes)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ["project_id", "status", "action", "changed_at", "changed_by", "notes"],
    ),
    # Dziennik przejść stary→nowy. `old_status` bywa NULL (pierwszy wpis).
    "status-historia-zapisz": (
        "INSERT INTO project_status_history"
        " (project_id, old_status, new_status, changed_at, changed_by, notes)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ["project_id", "old_status", "new_status", "changed_at",
         "changed_by", "notes"],
    ),

    "rfq-ustawienie-zapisz": (
        "INSERT INTO settings (key, value, updated_at)"
        " VALUES (?, ?, datetime('now','localtime'))"
        " ON CONFLICT(key) DO UPDATE SET"
        "   value = excluded.value, updated_at = excluded.updated_at",
        ["key", "value"],
    ),

    # ── Tagi kooperantów (RM_BAZA jest właścicielem) ──────────────────
    # Nadpisanie przypisań firmy: DELETE + INSERT-y lecą jednym batchem,
    # czyli w jednej transakcji — inaczej zerwanie połączenia między nimi
    # zostawiłoby kooperanta bez żadnego tagu.
    "rfq-tagi-dostawcy-czysc": (
        "DELETE FROM rfq_supplier_tags WHERE supplier_id = ?",
        ["supplier_id"],
    ),
    "rfq-tag-przypisz": (
        "INSERT OR IGNORE INTO rfq_supplier_tags (supplier_id, tag_id)"
        " VALUES (?, ?)",
        ["supplier_id", "tag_id"],
    ),
    "rfq-tag-usun": (
        "DELETE FROM rfq_tags WHERE id = ?",
        ["tag_id"],
    ),
    "rfq-tag-usun-przypisania": (
        "DELETE FROM rfq_supplier_tags WHERE tag_id = ?",
        ["tag_id"],
    ),
    "rfq-tag-dodaj": (
        "INSERT OR IGNORE INTO rfq_tags (name, label, sort_order)"
        " VALUES (?, ?, ?)",
        ["name", "label", "sort_order"],
    ),

    # ── Odciski wysłanych plików ──────────────────────────────────────
    # Para DELETE+INSERT leci jednym batchem (jedna transakcja): przy
    # ponownej wysyłce z innym zestawem plików stare, odpięte pliki nie
    # mają wisieć jako „zmienione".
    "rfq-pushed-czysc-pozycje": (
        "DELETE FROM rfq_pushed_files"
        " WHERE rfq_id = ? AND drawing_number = ?",
        ["rfq_id", "drawing_number"],
    ),
    "rfq-pushed-dodaj": (
        "INSERT OR REPLACE INTO rfq_pushed_files"
        " (rfq_id, drawing_number, path, filename, size, mtime_ns, sha1)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        ["rfq_id", "drawing_number", "path", "filename", "size",
         "mtime_ns", "sha1"],
    ),
    "rfq-pushed-odswiez-odcisk": (
        "UPDATE rfq_pushed_files SET size = ?, mtime_ns = ? WHERE path = ?",
        ["size", "mtime_ns", "path"],
    ),

    # Stan pozycji RFQ z portalu. Jedna pozycja = jeden wiersz; zawiera
    # też nierozstrzygnięte (liczniki zaproszeń/ofert), bo kolumna WYCENA
    # pokazuje stany pośrednie: „WYSŁANO · 4" → „1/4 OFERT · 96 zł".
    "rfq-wynik-zapisz": (
        "INSERT INTO rfq_results"
        " (rfq_item_id, drawing_number, item_name, revision, quantity, material, project_number, rfq_id, rfq_code, rfq_title, rfq_status, suppliers_count, offers_count, declined_count, min_price, invitations_sent, viewers_count, seen_item_count, last_viewed_at, response_deadline, files_updated_at, docs_notified_at, supplier_id, supplier_name, price, currency, lead_time_days, offer_notes, decided_at, synced_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now','localtime'))"
        " ON CONFLICT(rfq_item_id) DO UPDATE SET"
        " drawing_number = excluded.drawing_number, item_name = excluded.item_name, revision = excluded.revision, quantity = excluded.quantity, material = excluded.material, project_number = excluded.project_number, rfq_id = excluded.rfq_id, rfq_code = excluded.rfq_code, rfq_title = excluded.rfq_title, rfq_status = excluded.rfq_status, suppliers_count = excluded.suppliers_count, offers_count = excluded.offers_count, declined_count = excluded.declined_count, min_price = excluded.min_price, invitations_sent = excluded.invitations_sent, viewers_count = excluded.viewers_count, seen_item_count = excluded.seen_item_count, last_viewed_at = excluded.last_viewed_at, response_deadline = excluded.response_deadline, files_updated_at = excluded.files_updated_at, docs_notified_at = excluded.docs_notified_at, supplier_id = excluded.supplier_id, supplier_name = excluded.supplier_name, price = excluded.price, currency = excluded.currency, lead_time_days = excluded.lead_time_days, offer_notes = excluded.offer_notes, decided_at = excluded.decided_at,"
        " synced_at = excluded.synced_at",
        ['rfq_item_id', 'drawing_number', 'item_name', 'revision', 'quantity', 'material', 'project_number', 'rfq_id', 'rfq_code', 'rfq_title', 'rfq_status', 'suppliers_count', 'offers_count', 'declined_count', 'min_price', 'invitations_sent', 'viewers_count', 'seen_item_count', 'last_viewed_at', 'response_deadline', 'files_updated_at', 'docs_notified_at', 'supplier_id', 'supplier_name', 'price', 'currency', 'lead_time_days', 'offer_notes', 'decided_at'],
    ),

    # Aktywność kooperanta na pozycji. Klucz złożony: jedna para
    # (pozycja, kooperant) = jeden wiersz.
    "rfq-aktywnosc-zapisz": (
        "INSERT INTO rfq_activity"
        " (rfq_item_id, supplier_name, drawing_number, item_name, email_sent_at, first_viewed_at, last_viewed_at, view_count, seen_this_item, has_offer, is_winner, win_price, offer_price, offer_currency, offer_lead_time, has_declined, decline_reason, decline_label, decline_notes, declined_at, offer_notes, offer_submitted_at, synced_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now','localtime'))"
        " ON CONFLICT(rfq_item_id, supplier_name) DO UPDATE SET"
        " drawing_number = excluded.drawing_number, item_name = excluded.item_name, email_sent_at = excluded.email_sent_at, first_viewed_at = excluded.first_viewed_at, last_viewed_at = excluded.last_viewed_at, view_count = excluded.view_count, seen_this_item = excluded.seen_this_item, has_offer = excluded.has_offer, is_winner = excluded.is_winner, win_price = excluded.win_price, offer_price = excluded.offer_price, offer_currency = excluded.offer_currency, offer_lead_time = excluded.offer_lead_time, has_declined = excluded.has_declined, decline_reason = excluded.decline_reason, decline_label = excluded.decline_label, decline_notes = excluded.decline_notes, declined_at = excluded.declined_at, offer_notes = excluded.offer_notes, offer_submitted_at = excluded.offer_submitted_at,"
        " synced_at = excluded.synced_at",
        ['rfq_item_id', 'supplier_name', 'drawing_number', 'item_name', 'email_sent_at', 'first_viewed_at', 'last_viewed_at', 'view_count', 'seen_this_item', 'has_offer', 'is_winner', 'win_price', 'offer_price', 'offer_currency', 'offer_lead_time', 'has_declined', 'decline_reason', 'decline_label', 'decline_notes', 'declined_at', 'offer_notes', 'offer_submitted_at'],
    ),

    # ── Wyniki ofert i aktywność ──────────────────────────────────────
    "rfq-wynik-usun": (
        "DELETE FROM rfq_results WHERE rfq_item_id = ?",
        ["rfq_item_id"],
    ),
    "rfq-wyniki-wyczysc": (
        "DELETE FROM rfq_results",
        [],
    ),
    "rfq-aktywnosc-wyczysc": (
        "DELETE FROM rfq_activity",
        [],
    ),

    # ── Reconcile: skasuj to, czego nie ma już w portalu ──────────────
    # ⚠️ Lista żywych identyfikatorów jedzie jako JEDEN parametr —
    # tablica JSON rozpakowana przez json_each. Bez tego trzeba by skleić
    # `NOT IN (?,?,?…)` po stronie klienta, czyli wpuścić SQL z sieci.
    # Pusta lista = nic nie kasujemy (wołający sam pilnuje, by nie
    # wyczyścić tabeli po nieudanym pobraniu z portalu).
    "rfq-wyniki-reconcile": (
        "DELETE FROM rfq_results"
        " WHERE rfq_item_id NOT IN (SELECT value FROM json_each(?))",
        ["zywe_json"],
    ),
    "rfq-aktywnosc-reconcile": (
        "DELETE FROM rfq_activity"
        " WHERE rfq_item_id NOT IN (SELECT value FROM json_each(?))",
        ["zywe_json"],
    ),
    # Odciski są kluczowane po rfq_id (nie rfq_item_id) — stąd osobno.
    "rfq-pushed-reconcile": (
        "DELETE FROM rfq_pushed_files"
        " WHERE rfq_id NOT IN (SELECT value FROM json_each(?))",
        ["zywe_json"],
    ),

    # ══ MAPOWANIA SUBIEKTA (osobny plik — patrz odczyty) ════════════
    # UPSERT po numerze rysunku. COALESCE przy id/nazwie: dopasowanie
    # „luźne" nie zna Id kartoteki, więc nie może skasować tego, co wpisało
    # wcześniejsze dopasowanie dokładne.
    "map-put": (
        "INSERT INTO mapowania"
        " (numer_rysunku, symbol_subiekt, id_subiekt, nazwa_subiekt, sposob,"
        "  kto, kiedy, uwagi)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(numer_rysunku) DO UPDATE SET"
        "   symbol_subiekt = excluded.symbol_subiekt,"
        "   id_subiekt     = COALESCE(excluded.id_subiekt, mapowania.id_subiekt),"
        "   nazwa_subiekt  = COALESCE(excluded.nazwa_subiekt, mapowania.nazwa_subiekt),"
        "   sposob         = excluded.sposob,"
        "   kto            = excluded.kto,"
        "   kiedy          = excluded.kiedy,"
        "   uwagi          = COALESCE(excluded.uwagi, mapowania.uwagi)",
        ["numer_rysunku", "symbol_subiekt", "id_subiekt", "nazwa_subiekt",
         "sposob", "kto", "kiedy", "uwagi"],
    ),
    "map-delete": (
        "DELETE FROM mapowania WHERE numer_rysunku = ?",
        ["numer_rysunku"],
    ),
    "map-alias-dodaj": (
        "INSERT INTO aliasy_scalen"
        " (stary_symbol, stary_id, nowy_symbol, nowy_id, kto, kiedy)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ["stary_symbol", "stary_id", "nowy_symbol", "nowy_id", "kto", "kiedy"],
    ),
    "map-dostawca-decyzja": (
        "INSERT INTO dostawcy_decyzje (supplier_id, nazwa, decyzja, kto, kiedy)"
        " VALUES (?, ?, ?, ?, ?)",
        ["supplier_id", "nazwa", "decyzja", "kto", "kiedy"],
    ),
    "map-dostawca-decyzja-usun": (
        "DELETE FROM dostawcy_decyzje WHERE supplier_id = ?",
        ["supplier_id"],
    ),

    # ── „Zamówiono" odłożone przez wysyłkę ZD ─────────────────────────
    "zd-wyslane-dodaj": (
        "INSERT INTO zd_wyslane (numer_zd, dokument_id, adresat, nadawca,"
        " zalacznikow, termin, tryb, kiedy) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ["numer_zd", "dokument_id", "adresat", "nadawca", "zalacznikow",
         "termin", "tryb", "kiedy"],
    ),
    # Lista id jako tablica JSON (json_each) — zero sklejania `IN (?,?,…)`.
    "zd-wyslane-usun-po-dokumentach": (
        "DELETE FROM zd_wyslane"
        " WHERE dokument_id IN (SELECT value FROM json_each(?))",
        ["idy_json"],
    ),
    "zd-zamowione-dodaj": (
        "INSERT OR REPLACE INTO zd_zamowione_pozycje"
        " (project_id, item_id, termin, numer_zd, kiedy, supplier_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ["project_id", "item_id", "termin", "numer_zd", "kiedy", "supplier_id"],
    ),
    "zd-zamowione-usun-po-numerach": (
        "DELETE FROM zd_zamowione_pozycje"
        " WHERE numer_zd IN (SELECT value FROM json_each(?))",
        ["numery_json"],
    ),
    # Wygaszanie wpisów starszych niż DNI_WAZNOSCI_ZAMOWIEN (projekt nigdy
    # nie przejęty) — granicę liczy klient.
    "zd-zamowione-wygas": (
        "DELETE FROM zd_zamowione_pozycje WHERE kiedy < ?",
        ["granica"],
    ),
    # Poczekalnia nowych pozycji ze schowka montażowego — wiersze, których
    # nie dało się zapisać wprost do projektu, bo lock trzymał ktoś inny.
    # Nakłada je arkusz przy „Przejmij Lock" (SCHOWEK_RW_ALGORYTM.md §4.4).
    "schowek-nowe-dodaj": (
        "INSERT INTO schowek_nowe_pozycje"
        " (project_id, symbol, nazwa, kto, kiedy) VALUES (?, ?, ?, ?, ?)",
        ["project_id", "symbol", "nazwa", "kto", "kiedy"],
    ),
    # Granica `do_kiedy` jest OBOWIĄZKOWA przy sprzątaniu: master jest
    # wspólny, więc między nałożeniem a wgraniem kopii ktoś mógł dołożyć
    # swój wpis. Kasowanie „wszystkiego dla project_id" zabrałoby cudzy
    # świeży wiersz — ten sam błąd złapano przy ZD 08.09.2026.
    "schowek-nowe-usun": (
        "DELETE FROM schowek_nowe_pozycje WHERE project_id = ?"
        " AND (? IS NULL OR kiedy <= ?)",
        ["project_id", "do_kiedy", "do_kiedy"],
    ),
    "zd-cofniete-dodaj": (
        "INSERT OR REPLACE INTO zd_cofniete_pozycje"
        " (project_id, item_id, numer_zd, termin, kiedy) VALUES (?, ?, ?, ?, ?)",
        ["project_id", "item_id", "numer_zd", "termin", "kiedy"],
    ),
    "zd-cofniete-usun-pozycja": (
        "DELETE FROM zd_cofniete_pozycje WHERE project_id = ? AND item_id = ?",
        ["project_id", "item_id"],
    ),
    # NIP dostawcy — dopisywany z Subiekta przy scalaniu kartotek.
    "supplier-nip-set": (
        "UPDATE suppliers SET nip = ? WHERE supplier_id = ?",
        ["nip", "supplier_id"],
    ),
    "zd-zamowione-usun": (
        "DELETE FROM zd_zamowione_pozycje WHERE project_id = ?"
        " AND (? IS NULL OR kiedy <= ?)",
        ["project_id", "do_kiedy", "do_kiedy"],
    ),
    "zd-cofniete-usun": (
        "DELETE FROM zd_cofniete_pozycje WHERE project_id = ?"
        " AND (? IS NULL OR kiedy <= ?)",
        ["project_id", "do_kiedy", "do_kiedy"],
    ),
}


# ═══════════════════════════════════════════════════════════════════════
# MIGRACJE — wykonywane przez SERWER przy starcie, raz
# ═══════════════════════════════════════════════════════════════════════
#
# Dziś robi to każdy klient osobno (27 PRAGMA + ALTER/CREATE), stąd w logach
# „Nie udało się dodać kolumny 'subiekt_symbol': attempt to write a readonly
# database" — klient bez prawa zapisu próbował migrować cudzą bazę.
# Po zmianie schemat zmienia wyłącznie właściciel pliku.
#
# Kolejność ma znaczenie: CREATE TABLE przed ALTER-ami tej tabeli.

MIGRACJE = [
    ("""CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            contact     TEXT,
            phone       TEXT,
            email       TEXT,
            description TEXT,
            is_active   INTEGER DEFAULT 1
        )""", None),
    ("""CREATE TABLE IF NOT EXISTS settings (
            key        TEXT PRIMARY KEY,
            value      TEXT,
            updated_at TEXT
        )""", None),
    ("""CREATE TABLE IF NOT EXISTS user_changes_log (
            change_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            action       TEXT NOT NULL,
            user_id      INTEGER,
            username     TEXT,
            display_name TEXT,
            role         TEXT,
            changed_by   TEXT,
            timestamp    TEXT NOT NULL,
            details      TEXT
        )""", None),
    # ── Wysyłka ZD do Subiekta: dziennik + odłożone „Zamówiono"/cofnięcia ──
    # Wcześniej tworzył je klient (`subiekt_wyslij_zd._zapewnij_*`) przy
    # każdym zapisie. Schemat zgodny z produkcją.
    ("""CREATE TABLE IF NOT EXISTS zd_wyslane (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            numer_zd          TEXT NOT NULL,
            adresat           TEXT,
            nadawca           TEXT,
            zalacznikow       INTEGER,
            termin            TEXT,
            tryb              TEXT,
            kiedy             TEXT NOT NULL,
            dokument_usuniety TEXT,
            dokument_id       INTEGER
        )""", None),
    ("ALTER TABLE zd_wyslane ADD COLUMN dokument_id INTEGER", ("zd_wyslane", "dokument_id")),
    ("ALTER TABLE zd_wyslane ADD COLUMN dokument_usuniety TEXT", ("zd_wyslane", "dokument_usuniety")),
    ("CREATE INDEX IF NOT EXISTS idx_zd_wyslane_nr ON zd_wyslane(numer_zd)", None),
    ("CREATE INDEX IF NOT EXISTS idx_zd_wyslane_docid ON zd_wyslane(dokument_id)", None),
    ("""CREATE TABLE IF NOT EXISTS zd_zamowione_pozycje (
            project_id  INTEGER NOT NULL,
            item_id     INTEGER NOT NULL,
            termin      TEXT,
            numer_zd    TEXT,
            kiedy       TEXT NOT NULL,
            supplier_id INTEGER,
            PRIMARY KEY (project_id, item_id)
        )""", None),
    ("ALTER TABLE zd_zamowione_pozycje ADD COLUMN supplier_id INTEGER",
     ("zd_zamowione_pozycje", "supplier_id")),
    # Poczekalnia nowych pozycji ze schowka montażowego (§4.4 algorytmu).
    #
    # ⚠️ Klucz to `id`, a NIE (project_id, symbol) jak przy ZD: ten sam
    # symbol może zostać odłożony kilka razy, zanim ktokolwiek przejmie
    # lock. Nakładanie i tak sprawdza duplikat w BOM-ie, więc powtórki są
    # nieszkodliwe — a klucz złożony gubiłby wpisy po cichu.
    ("""CREATE TABLE IF NOT EXISTS schowek_nowe_pozycje (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL,
            symbol      TEXT    NOT NULL,
            nazwa       TEXT,
            kto         TEXT,
            kiedy       TEXT    NOT NULL
        )""", None),
    ("CREATE INDEX IF NOT EXISTS idx_schowek_nowe_proj "
     "ON schowek_nowe_pozycje(project_id)", None),
    ("""CREATE TABLE IF NOT EXISTS zd_cofniete_pozycje (
            project_id INTEGER NOT NULL,
            item_id    INTEGER NOT NULL,
            numer_zd   TEXT,
            termin     TEXT,
            kiedy      TEXT NOT NULL,
            PRIMARY KEY (project_id, item_id)
        )""", None),
    ("ALTER TABLE zd_cofniete_pozycje ADD COLUMN termin TEXT", ("zd_cofniete_pozycje", "termin")),

    # Dziennik idempotencji — patrz §3. W MASTERZE, nie w osobnym pliku:
    # jedna baza, jeden journal, jedna transakcja z operacją.
    ("""CREATE TABLE IF NOT EXISTS _server_request_log (
            request_id  TEXT PRIMARY KEY,
            operation   TEXT NOT NULL,
            kto         TEXT,
            result_json TEXT,
            created_at  TEXT NOT NULL
        )""", None),
    ("CREATE INDEX IF NOT EXISTS idx_server_request_log_czas"
     " ON _server_request_log(created_at)", None),

    # ALTER-y: (SQL, (tabela, kolumna)) — wykonywane tylko gdy kolumny brak.
    ("ALTER TABLE projects ADD COLUMN project_type TEXT NOT NULL DEFAULT 'MACHINE'",
     ("projects", "project_type")),
    ("ALTER TABLE projects ADD COLUMN designer TEXT", ("projects", "designer")),
    ("ALTER TABLE projects ADD COLUMN completed_at TEXT", ("projects", "completed_at")),
    ("ALTER TABLE projects ADD COLUMN status TEXT DEFAULT 'W_REALIZACJI'",
     ("projects", "status")),
    ("ALTER TABLE projects ADD COLUMN received_percent TEXT",
     ("projects", "received_percent")),
    ("ALTER TABLE projects ADD COLUMN montaz TEXT", ("projects", "montaz")),
    ("ALTER TABLE projects ADD COLUMN fat TEXT", ("projects", "fat")),
    ("ALTER TABLE suppliers ADD COLUMN nip TEXT", ("suppliers", "nip")),
    # Kolumny, które dokładał sobie sam RM_MANAGER przy pierwszym zapisie
    # (ALTER w set_project_status / set_project_priority). Teraz robi to
    # migracja — klient nie zmienia schematu.
    ("ALTER TABLE projects ADD COLUMN project_status TEXT DEFAULT 'NEW'",
     ("projects", "project_status")),
    ("ALTER TABLE projects ADD COLUMN priority INTEGER", ("projects", "priority")),
    # Blokady projektow RM_BAZA — ODDZIELNE od blokad RM_MANAGER.
    #
    # ⚠️ Ta sama nazwa tabeli co w rm_manager.sqlite, ale to INNY PLIK i
    # nie ma miedzy nimi zadnego zwiazku. Tak ma byc: numery projektow
    # obu programow pokrywaja sie w 81 przypadkach (RM_BAZA 1..2611,
    # RM_MANAGER 1..90), wiec jedna wspolna tabela kazalaby userowi
    # RM_BAZA czekac na projekt 22 dlatego, ze ktos inny otworzyl zupelnie
    # inny projekt 22 w RM_MANAGER. Rozdziela je routing serwera:
    # operacje `lock-*` (bez prefiksu) ida tutaj, `rmm-lock-*` do RM_MANAGER.
    ("CREATE TABLE IF NOT EXISTS project_locks ( project_id INTEGER PRIMARY KEY,"
     " lock_id TEXT NOT NULL, uzytkownik TEXT NOT NULL, komputer TEXT NOT NULL,"
     " locked_at TEXT NOT NULL, last_heartbeat TEXT NOT NULL )", None),
]


# ═══════════════════════════════════════════════════════════════════════
# OPERACJE ZALEŻNE OD SCHEMATU — budowane RAZ, przy starcie serwera
# ═══════════════════════════════════════════════════════════════════════
#
# `suppliers` nie ma jednego schematu: na jednej instalacji kolumna nazywa się
# `contact`, na innej `contact_info`; `description` bywa `notes`. Dzisiejszy
# klient radzi sobie, budując INSERT w locie przy każdym dodaniu dostawcy
# (RM_BAZA…py:22636) — serwer robi to samo, ale JEDEN RAZ, bo schemat nie
# zmienia się w trakcie pracy.
#
# Aliasy w kolejności preferencji — pierwszy istniejący wygrywa.
ALIASY_DOSTAWCY = {
    "contact":     ["contact", "contact_info"],
    "phone":       ["phone", "phone_default"],
    "email":       ["email", "email_default"],
    "description": ["description", "desc", "opis", "note", "notes"],
    "nip":         ["nip"],
}


def zbuduj_operacje_dostawcow(con):
    """Dokłada `supplier-add` i `supplier-edit` pod FAKTYCZNY schemat tabeli.

    Wołane raz, po migracjach. Zwraca mapę pole→kolumna, żeby było widać
    w logu, co serwer wykrył — przy diagnozie „czemu nie zapisał telefonu"
    to pierwsza rzecz do sprawdzenia.
    """
    try:
        kolumny = {r[1] for r in con.execute("PRAGMA table_info(suppliers)")}
    except sqlite3.Error:
        return {}
    if not kolumny:
        return {}

    mapa = {}
    for pole, kandydaci in ALIASY_DOSTAWCY.items():
        trafiony = next((k for k in kandydaci if k in kolumny), None)
        if trafiony:
            mapa[pole] = trafiony

    # name jest obowiązkowe — bez niego tabela nie jest tabelą dostawców.
    if "name" not in kolumny:
        return {}

    pola = ["name"] + [p for p in ALIASY_DOSTAWCY if p in mapa]
    kol = ["name"] + [mapa[p] for p in ALIASY_DOSTAWCY if p in mapa]

    aktywna = "is_active" in kolumny
    ZAPIS["supplier-add"] = (
        "INSERT INTO suppliers (%s%s) VALUES (%s%s)" % (
            ", ".join(kol), ", is_active" if aktywna else "",
            ", ".join(["?"] * len(kol)), ", 1" if aktywna else ""),
        pola,
    )
    ZAPIS["supplier-edit"] = (
        "UPDATE suppliers SET %s WHERE supplier_id = ?" % (
            ", ".join("%s = ?" % c for c in kol)),
        pola + ["supplier_id"],
    )
    return mapa


# ═══════════════════════════════════════════════════════════════════════
# SCHEMAT RM_MANAGER  (rm_manager.sqlite)
# ═══════════════════════════════════════════════════════════════════════
#
# Wygenerowane z PRODUKCYJNEJ bazy (sqlite_master), nie przepisane
# ręcznie — przy 30 tabelach i 31 indeksach pomyłka w jednej kolumnie
# byłaby nie do wychwycenia okiem.
#
# ⚠️ To OSOBNY PLIK, nie master RM_BAZA. Serwer trzyma do niego trzecie
# połączenie; operacje mają prefiks `rmm-`.

MIGRACJE_RM_MANAGER = [
    # ⚠️ Dziennik idempotencji MUSI być w KAŻDEJ bazie, do której serwer
    # pisze — transakcja SQLite nie obejmuje dwóch plików. Gdyby wpis
    # dziennika szedł do mastera, a operacja tutaj, zerwane połączenie
    # mogłoby zostawić jedno bez drugiego i ponowienie zdublowałoby zapis.
    ("""CREATE TABLE IF NOT EXISTS _server_request_log (
            request_id  TEXT PRIMARY KEY,
            operation   TEXT NOT NULL,
            kto         TEXT,
            result_json TEXT,
            created_at  TEXT NOT NULL
        )""", None),
    ("CREATE INDEX IF NOT EXISTS idx_server_request_log_czas"
     " ON _server_request_log(created_at)", None),

    ("CREATE TABLE IF NOT EXISTS absence_exclusion_groups ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " name TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
     " created_by TEXT )", None),
    ("CREATE TABLE IF NOT EXISTS absence_exclusion_members ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " group_id INTEGER NOT NULL, employee_id INTEGER NOT NULL,"
     " FOREIGN KEY (group_id) REFERENCES absence_exclusion_groups(id) ON DELETE CASCADE,"
     " FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,"
     " UNIQUE (group_id, employee_id) )", None),
    # ⚠️ BEZ klucza obcego do `users`: ta tabela leży w MASTERZE RM_BAZA,
    # a `active_sessions` w bazie RM_MANAGER — to dwa osobne pliki, więc
    # SQLite nie ma jak tego sprawdzić. Przy `PRAGMA foreign_keys=ON` (serwer
    # go włącza, bo schemat używa ON DELETE CASCADE gdzie indziej) każdy zapis
    # kończył się „no such table: main.users". Schemat był tu od początku,
    # ale nikt z tej tabeli nie korzystał, więc błąd nie miał okazji wyjść.
    ("CREATE TABLE IF NOT EXISTS active_sessions ( session_id TEXT PRIMARY KEY,"
     " user_id INTEGER NOT NULL, username TEXT NOT NULL,"
     " hostname TEXT NOT NULL, pid INTEGER NOT NULL,"
     " app_name TEXT NOT NULL DEFAULT 'rm_manager',"
     " login_at DATETIME NOT NULL, last_heartbeat DATETIME NOT NULL,"
     " client_info TEXT )", None),
    ("CREATE TABLE IF NOT EXISTS audit_log ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " employee_id INTEGER, entity_type TEXT NOT NULL, entity_id INTEGER,"
     " action TEXT NOT NULL, field TEXT, old_value TEXT, new_value TEXT,"
     " note TEXT, changed_by TEXT,"
     " changed_at DATETIME DEFAULT CURRENT_TIMESTAMP )", None),
    ("CREATE TABLE IF NOT EXISTS company_calendar ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " date DATE NOT NULL UNIQUE,"
     " day_type TEXT NOT NULL CHECK (day_type IN ( 'HOLIDAY',"
     " 'COMPANY_DAY_OFF', 'SATURDAY_WORK' )), description TEXT,"
     " created_at DATETIME DEFAULT CURRENT_TIMESTAMP, created_by TEXT )", None),
    ("CREATE TABLE IF NOT EXISTS employee_availability ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " employee_id INTEGER NOT NULL, date_from DATE NOT NULL,"
     " date_to DATE NOT NULL, reason TEXT NOT NULL, notes TEXT,"
     " created_at DATETIME DEFAULT CURRENT_TIMESTAMP, created_by TEXT,"
     " time_from TEXT, time_to TEXT, days_override REAL,"
     " status TEXT NOT NULL DEFAULT 'OCZEKUJE', decided_by TEXT,"
     " decided_at DATETIME, decision_note TEXT,"
     " FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,"
     " CHECK (date_to >= date_from) )", None),
    ("CREATE TABLE IF NOT EXISTS employee_carryover_override ( employee_id INTEGER NOT NULL,"
     " year INTEGER NOT NULL, days REAL NOT NULL,"
     " updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_by TEXT,"
     " PRIMARY KEY (employee_id, year),"
     " FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE )", None),
    ("CREATE TABLE IF NOT EXISTS employee_vacation_base ( employee_id INTEGER PRIMARY KEY,"
     " days REAL NOT NULL DEFAULT 26,"
     " updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_by TEXT,"
     " FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE )", None),
    ("CREATE TABLE IF NOT EXISTS employee_vacation_quota ( employee_id INTEGER NOT NULL,"
     " year INTEGER NOT NULL, days REAL NOT NULL DEFAULT 26,"
     " updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_by TEXT,"
     " carryover_override REAL, PRIMARY KEY (employee_id, year),"
     " FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE )", None),
    ("CREATE TABLE IF NOT EXISTS employees ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " name TEXT NOT NULL, category TEXT NOT NULL, description TEXT,"
     " contact_info TEXT, is_active INTEGER NOT NULL DEFAULT 1,"
     " created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
     " updated_at DATETIME DEFAULT CURRENT_TIMESTAMP , phone TEXT, email TEXT,"
     " master_max_parallel INTEGER NOT NULL DEFAULT 1, podmiot TEXT,"
     " user_login TEXT)", None),
    ("CREATE TABLE IF NOT EXISTS in_app_notifications ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " project_id INTEGER NOT NULL, project_name TEXT,"
     " notification_type TEXT NOT NULL, message TEXT NOT NULL,"
     " created_at DATETIME DEFAULT CURRENT_TIMESTAMP, created_by TEXT,"
     " is_read INTEGER NOT NULL DEFAULT 0, read_at DATETIME, read_by TEXT )", None),
    ("CREATE TABLE IF NOT EXISTS line_projects ( line_id INTEGER NOT NULL,"
     " project_id INTEGER NOT NULL UNIQUE, PRIMARY KEY (line_id, project_id),"
     " FOREIGN KEY (line_id) REFERENCES production_lines(id) ON DELETE CASCADE )", None),
    ("CREATE TABLE IF NOT EXISTS optimization_runs ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " run_mode TEXT NOT NULL CHECK (run_mode IN ('fit_projects',"
     " 'optimize_all')), project_ids_json TEXT NOT NULL,"
     " date_range_start DATE, date_range_end DATE, constraints_snapshot TEXT,"
     " result_json TEXT, score_before REAL, score_after REAL,"
     " solver_status TEXT, solver_time_ms INTEGER,"
     " applied INTEGER NOT NULL DEFAULT 0, applied_at DATETIME,"
     " applied_by TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
     " created_by TEXT )", None),
    ("CREATE TABLE IF NOT EXISTS payment_history ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " project_id INTEGER NOT NULL, percentage INTEGER NOT NULL,"
     " payment_date DATE, action TEXT NOT NULL CHECK (action IN ('ADDED',"
     " 'MODIFIED', 'DELETED')), changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
     " changed_by TEXT NOT NULL, old_date DATE )", None),
    ("CREATE TABLE IF NOT EXISTS \"payment_milestones\" ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " project_id INTEGER NOT NULL,"
     " percentage INTEGER NOT NULL CHECK (percentage > 0 AND percentage <= 100),"
     " payment_date DATE, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
     " created_by TEXT, modified_at DATETIME, modified_by TEXT,"
     " payment_type TEXT NOT NULL DEFAULT 'PŁATNOŚĆ' )", None),
    ("CREATE TABLE IF NOT EXISTS payment_notification_config ( id INTEGER PRIMARY KEY CHECK (id = 1),"
     " trigger_percentage INTEGER NOT NULL DEFAULT 100,"
     " email_recipients TEXT NOT NULL, smtp_server TEXT,"
     " smtp_port INTEGER DEFAULT 587, smtp_user TEXT, smtp_password TEXT,"
     " enabled INTEGER NOT NULL DEFAULT 1,"
     " created_at DATETIME DEFAULT CURRENT_TIMESTAMP, modified_at DATETIME )", None),
    ("CREATE TABLE IF NOT EXISTS payment_notifications_sent ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " project_id INTEGER NOT NULL, project_name TEXT,"
     " percentage INTEGER NOT NULL, payment_date DATE,"
     " recipients TEXT NOT NULL, sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
     " sent_by TEXT, email_status TEXT CHECK (email_status IN ('SUCCESS',"
     " 'FAILED', 'PENDING')), error_message TEXT )", None),
    ("CREATE TABLE IF NOT EXISTS plc_authorized_senders ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " username TEXT NOT NULL UNIQUE, added_by TEXT,"
     " added_at DATETIME DEFAULT CURRENT_TIMESTAMP, notes TEXT )", None),
    ("CREATE TABLE IF NOT EXISTS plc_global_recipients ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " setting_key TEXT NOT NULL UNIQUE, recipients_json TEXT NOT NULL,"
     " updated_by TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP )", None),
    ("CREATE TABLE IF NOT EXISTS plc_unlock_codes ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " project_id INTEGER NOT NULL,"
     " code_type TEXT NOT NULL CHECK (code_type IN ('TEMPORARY', 'EXTENDED',"
     " 'PERMANENT')), unlock_code TEXT NOT NULL, description TEXT,"
     " created_at DATETIME DEFAULT CURRENT_TIMESTAMP, created_by TEXT,"
     " modified_at DATETIME, modified_by TEXT,"
     " is_used INTEGER NOT NULL DEFAULT 0, used_at DATETIME, used_by TEXT,"
     " notes TEXT , default_recipients TEXT, sent_at DATETIME, sent_by TEXT,"
     " sent_via TEXT, expiry_date DATETIME)", None),
    ("CREATE TABLE IF NOT EXISTS priority_weights ( level INTEGER PRIMARY KEY,"
     " label TEXT NOT NULL, weight INTEGER NOT NULL DEFAULT 1 )", None),
    ("CREATE TABLE IF NOT EXISTS production_lines ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " name TEXT NOT NULL UNIQUE, description TEXT,"
     " parallel_stages_csv TEXT NOT NULL DEFAULT '',"
     " created_at DATETIME DEFAULT CURRENT_TIMESTAMP, created_by TEXT,"
     " updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_by TEXT )", None),
    ("CREATE TABLE IF NOT EXISTS project_file_tracking ( project_id INTEGER PRIMARY KEY,"
     " project_name TEXT, file_path TEXT NOT NULL,"
     " file_birth_time REAL NOT NULL,"
     " last_verified_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
     " verification_status TEXT DEFAULT 'OK',"
     " CHECK (verification_status IN ('OK', 'MISSING', 'BIRTH_MISMATCH')) )", None),
    ("CREATE TABLE IF NOT EXISTS resource_constraints ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " constraint_type TEXT NOT NULL CHECK (constraint_type IN ( 'exclusive_person',"
     " 'max_concurrent_category', 'max_concurrent_stage' )), category TEXT,"
     " stage_code TEXT, max_parallel INTEGER NOT NULL DEFAULT 1,"
     " is_active INTEGER NOT NULL DEFAULT 1, description TEXT,"
     " created_at DATETIME DEFAULT CURRENT_TIMESTAMP, created_by TEXT,"
     " modified_at DATETIME, modified_by TEXT )", None),
    ("CREATE TABLE IF NOT EXISTS rm_feature_user_permissions ( feature TEXT NOT NULL,"
     " username TEXT NOT NULL, granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
     " PRIMARY KEY (feature, username) )", None),
    ("CREATE TABLE IF NOT EXISTS rm_user_permissions ( role TEXT PRIMARY KEY,"
     " can_start_stage INTEGER NOT NULL DEFAULT 0,"
     " can_end_stage INTEGER NOT NULL DEFAULT 0,"
     " can_edit_dates INTEGER NOT NULL DEFAULT 0,"
     " can_sync_master INTEGER NOT NULL DEFAULT 0,"
     " can_critical_path INTEGER NOT NULL DEFAULT 0,"
     " can_manage_permissions INTEGER NOT NULL DEFAULT 0,"
     " updated_at DATETIME DEFAULT CURRENT_TIMESTAMP )", None),
    ("CREATE TABLE IF NOT EXISTS service_trips ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " employee_id INTEGER NOT NULL, project_id INTEGER, client_or_place TEXT,"
     " trip_type TEXT NOT NULL DEFAULT 'INNE', date_from DATE NOT NULL,"
     " date_to DATE NOT NULL,"
     " status TEXT NOT NULL DEFAULT 'PLANOWANY' CHECK (status IN ( 'PLANOWANY',"
     " 'POTWIERDZONY', 'ZREALIZOWANY' )), note TEXT,"
     " created_at DATETIME DEFAULT CURRENT_TIMESTAMP, created_by TEXT,"
     " working_days REAL,"
     " FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,"
     " CHECK (date_to >= date_from) )", None),
    ("CREATE TABLE IF NOT EXISTS project_locks ( project_id INTEGER PRIMARY KEY,"
     " lock_id TEXT NOT NULL, uzytkownik TEXT NOT NULL, komputer TEXT NOT NULL,"
     " locked_at TEXT NOT NULL, last_heartbeat TEXT NOT NULL )", None),
    ("CREATE TABLE IF NOT EXISTS stage_definitions ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " code TEXT UNIQUE NOT NULL, display_name TEXT, color TEXT,"
     " is_milestone INTEGER DEFAULT 0 )", None),
    ("CREATE TABLE IF NOT EXISTS sync_log ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " sync_date TEXT NOT NULL, sync_timestamp TEXT NOT NULL,"
     " projects_synced INTEGER DEFAULT 0, user TEXT, notes TEXT )", None),
    ("CREATE TABLE IF NOT EXISTS transports ( id INTEGER PRIMARY KEY AUTOINCREMENT,"
     " name TEXT NOT NULL, description TEXT, contact_info TEXT,"
     " is_active INTEGER NOT NULL DEFAULT 1,"
     " created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
     " updated_at DATETIME DEFAULT CURRENT_TIMESTAMP )", None),

    # ── indeksy ──────────────────────────────────────────────────────
    ("CREATE INDEX IF NOT EXISTS idx_abs_excl_members_emp ON absence_exclusion_members(employee_id)", None),
    ("CREATE INDEX IF NOT EXISTS idx_abs_excl_members_group ON absence_exclusion_members(group_id)", None),
    ("CREATE INDEX IF NOT EXISTS idx_active_sessions_heartbeat ON active_sessions(last_heartbeat)", None),
    ("CREATE INDEX IF NOT EXISTS idx_active_sessions_user ON active_sessions(user_id)", None),
    ("CREATE UNIQUE INDEX IF NOT EXISTS idx_active_sessions_user_host_app ON active_sessions(user_id,"
     " hostname, app_name)", None),
    ("CREATE INDEX IF NOT EXISTS idx_audit_changed_at ON audit_log(changed_at)", None),
    ("CREATE INDEX IF NOT EXISTS idx_audit_employee ON audit_log(employee_id)", None),
    ("CREATE INDEX IF NOT EXISTS idx_company_calendar_date ON company_calendar(date)", None),
    ("CREATE INDEX IF NOT EXISTS idx_emp_avail_dates ON employee_availability(date_from,"
     " date_to)", None),
    ("CREATE INDEX IF NOT EXISTS idx_emp_avail_employee ON employee_availability(employee_id)", None),
    ("CREATE INDEX IF NOT EXISTS idx_emp_avail_status ON employee_availability(status)", None),
    ("CREATE INDEX IF NOT EXISTS idx_employees_active ON employees(is_active)", None),
    ("CREATE INDEX IF NOT EXISTS idx_employees_category ON employees(category)", None),
    ("CREATE INDEX IF NOT EXISTS idx_file_tracking_status ON project_file_tracking(verification_status)", None),
    ("CREATE INDEX IF NOT EXISTS idx_in_app_notifications_project ON in_app_notifications(project_id)", None),
    ("CREATE INDEX IF NOT EXISTS idx_in_app_notifications_read ON in_app_notifications(is_read)", None),
    ("CREATE INDEX IF NOT EXISTS idx_line_projects_line ON line_projects(line_id)", None),
    ("CREATE INDEX IF NOT EXISTS idx_notifications_project ON payment_notifications_sent(project_id)", None),
    ("CREATE INDEX IF NOT EXISTS idx_notifications_status ON payment_notifications_sent(email_status)", None),
    ("CREATE INDEX IF NOT EXISTS idx_opt_runs_mode ON optimization_runs(run_mode)", None),
    ("CREATE INDEX IF NOT EXISTS idx_payment_history_project ON payment_history(project_id)", None),
    ("CREATE INDEX IF NOT EXISTS idx_payment_project ON payment_milestones(project_id)", None),
    ("CREATE INDEX IF NOT EXISTS idx_plc_codes_project ON plc_unlock_codes(project_id)", None),
    ("CREATE INDEX IF NOT EXISTS idx_plc_codes_type ON plc_unlock_codes(code_type)", None),
    ("CREATE INDEX IF NOT EXISTS idx_plc_senders_username ON plc_authorized_senders(username)", None),
    ("CREATE INDEX IF NOT EXISTS idx_res_constraints_active ON resource_constraints(is_active)", None),
    ("CREATE INDEX IF NOT EXISTS idx_res_constraints_type ON resource_constraints(constraint_type)", None),
    ("CREATE INDEX IF NOT EXISTS idx_service_trips_dates ON service_trips(date_from,"
     " date_to)", None),
    ("CREATE INDEX IF NOT EXISTS idx_service_trips_employee ON service_trips(employee_id)", None),
    ("CREATE INDEX IF NOT EXISTS idx_sync_log_date ON sync_log(sync_date)", None),
    ("CREATE INDEX IF NOT EXISTS idx_transports_active ON transports(is_active)", None),
]

# ═══════════════════════════════════════════════════════════════════════
# MIGRACJE DRUGIEJ BAZY — subiekt_mapowania.sqlite
# ═══════════════════════════════════════════════════════════════════════
#
# Osobny plik obok mastera. Schemat ten sam co w `subiekt_mapowania.py` —
# gdy tam coś dojdzie, dopisać i tutaj, bo to właściciel pliku zakłada
# tabele, nie klient.

# ═══════════════════════════════════════════════════════════════════════
# SCHEMAT PORTALU RFQ
# ═══════════════════════════════════════════════════════════════════════
#
# W agencie (`rm_sync_agent`) były to `PRAGMA table_info` + `ALTER TABLE`
# rozsiane po `_ensure_*_table()`, wołane przy KAŻDYM połączeniu. Schemat
# jest sprawą serwera, więc migracje idą tutaj — agent tylko woła operacje.
#
# Produkcyjna baza te tabele już ma; to jest dla świeżej bazy i dla kolumn
# dokładanych później.

MIGRACJE_RFQ = [
    # Cennik materiałów kalkulatora (gęstość + cena za kg). Wcześniej
    # tabelę tworzył `material_calculator._ensure_material_table`.
    ("""CREATE TABLE IF NOT EXISTS material_prices (
            material     TEXT PRIMARY KEY,
            density      REAL NOT NULL,
            price_per_kg REAL NOT NULL DEFAULT 0,
            updated_at   TEXT
        )""", None),

    # ── Statusy projektów ─────────────────────────────────────────────
    # Projekt może mieć KILKA statusów naraz (`project_statuses`), stąd
    # klucz złożony. Obok dwa dzienniki: `project_status_changes` notuje
    # dodanie/zdjęcie pojedynczego statusu, `project_status_history` —
    # przejścia stary→nowy. Schemat zgodny z produkcją.
    #
    # Wcześniej tworzył je klient (`project_manager.ensure_*_table`) na
    # bazie leżącej na dysku sieciowym.
    ("""CREATE TABLE IF NOT EXISTS project_statuses (
            project_id INTEGER NOT NULL,
            status     TEXT NOT NULL,
            set_at     TEXT NOT NULL DEFAULT (datetime('now')),
            set_by     TEXT,
            PRIMARY KEY (project_id, status),
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
        )""", None),
    ("CREATE INDEX IF NOT EXISTS idx_project_statuses_project"
     " ON project_statuses(project_id)", None),
    ("CREATE INDEX IF NOT EXISTS idx_project_statuses_status"
     " ON project_statuses(status)", None),

    ("""CREATE TABLE IF NOT EXISTS project_status_changes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            status     TEXT NOT NULL,
            action     TEXT NOT NULL CHECK(action IN ('ADDED', 'REMOVED')),
            changed_at TEXT NOT NULL DEFAULT (datetime('now')),
            changed_by TEXT,
            notes      TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
        )""", None),
    ("CREATE INDEX IF NOT EXISTS idx_status_changes_project"
     " ON project_status_changes(project_id, changed_at DESC)", None),
    ("CREATE INDEX IF NOT EXISTS idx_status_changes_status"
     " ON project_status_changes(status, changed_at DESC)", None),
    ("CREATE INDEX IF NOT EXISTS idx_status_changes_project_status"
     " ON project_status_changes(project_id, status, changed_at DESC)", None),

    ("""CREATE TABLE IF NOT EXISTS project_status_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_at TEXT NOT NULL DEFAULT (datetime('now')),
            changed_by TEXT,
            notes      TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
        )""", None),
    ("CREATE INDEX IF NOT EXISTS idx_status_history_project"
     " ON project_status_history(project_id, changed_at DESC)", None),

    # Tagi kooperantów dla portalu RM_RFQ: słownik + przypisania.
    # RM_BAZA jest właścicielem, RM_SYNC_AGENT wypycha je do portalu.
    # Wcześniej tworzył je klient własnym połączeniem do pliku.
    ("""CREATE TABLE IF NOT EXISTS rfq_tags (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL UNIQUE,
            label      TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0
        )""", None),
    ("""CREATE TABLE IF NOT EXISTS rfq_supplier_tags (
            supplier_id INTEGER NOT NULL,
            tag_id      INTEGER NOT NULL,
            PRIMARY KEY (supplier_id, tag_id)
        )""", None),
    ("CREATE INDEX IF NOT EXISTS idx_rfq_supplier_tags_sup"
     " ON rfq_supplier_tags(supplier_id)", None),

    # Sesje klientów: kto jest zalogowany i na jakim buildzie .exe.
    # Wcześniej tę tabelę tworzył `client_version._SESSIONS_DDL` po stronie
    # klienta — teraz schemat jest wyłącznie sprawą serwera.
    ("""CREATE TABLE IF NOT EXISTS client_sessions (
            host        TEXT PRIMARY KEY,
            username    TEXT,
            role        TEXT,
            exe_path    TEXT,
            exe_size    INTEGER,
            exe_mtime   TEXT,
            build_id    TEXT,
            pid         INTEGER,
            started_at  TEXT NOT NULL,
            last_seen   TEXT NOT NULL,
            ended_at    TEXT
        )""", None),

    ("""CREATE TABLE IF NOT EXISTS rfq_pushed_files (
            rfq_id          INTEGER NOT NULL,
            drawing_number  TEXT    NOT NULL,
            path            TEXT    NOT NULL,   -- ścieżka źródłowa na V:\\
            filename        TEXT    NOT NULL,
            size            INTEGER,
            mtime_ns        INTEGER,            -- st_mtime_ns w chwili wysyłki
            sha1            TEXT,               -- sha1 treści wysłanej do portalu
            pushed_at       TEXT DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (rfq_id, path)
        )""", None),
    # Stare bazy miały `mtime` zamiast `mtime_ns`. Wartości NIE konwertujemy:
    # NULL wymusi przeliczenie sha1 przy pierwszym sprawdzeniu (bezpiecznie),
    # a udana wysyłka zapisze bieżącą wartość.
    ("ALTER TABLE rfq_pushed_files ADD COLUMN mtime_ns INTEGER",
     ("rfq_pushed_files", "mtime_ns")),
    ("CREATE INDEX IF NOT EXISTS idx_rfq_pushed_drawing"
     " ON rfq_pushed_files(rfq_id, drawing_number)", None),

    ("""CREATE TABLE IF NOT EXISTS rfq_results (
            rfq_item_id      INTEGER PRIMARY KEY,
            drawing_number   TEXT NOT NULL,
            item_name        TEXT,
            revision         INTEGER,
            quantity         INTEGER,
            material         TEXT,
            project_number   TEXT,
            rfq_id           INTEGER,
            rfq_code         TEXT,
            rfq_title        TEXT,
            rfq_status       TEXT,
            suppliers_count  INTEGER,
            offers_count     INTEGER,
            declined_count   INTEGER,
            min_price        REAL,
            invitations_sent INTEGER,
            response_deadline TEXT,
            files_updated_at TEXT,
            docs_notified_at TEXT,
            viewers_count    INTEGER,
            seen_item_count  INTEGER,
            last_viewed_at   TEXT,
            supplier_id      INTEGER,   -- poniżej: dane zwycięzcy (NULL gdy brak)
            supplier_name    TEXT,
            price            REAL,
            currency         TEXT,
            lead_time_days   INTEGER,
            offer_notes      TEXT,
            decided_at       TEXT,
            synced_at        TEXT DEFAULT (datetime('now','localtime'))
        )""", None),
    ("CREATE INDEX IF NOT EXISTS idx_rfq_results_drawing"
     " ON rfq_results(drawing_number)", None),
    ("ALTER TABLE rfq_results ADD COLUMN rfq_id INTEGER", ("rfq_results", "rfq_id")),
    ("ALTER TABLE rfq_results ADD COLUMN rfq_status TEXT", ("rfq_results", "rfq_status")),
    ("ALTER TABLE rfq_results ADD COLUMN suppliers_count INTEGER", ("rfq_results", "suppliers_count")),
    ("ALTER TABLE rfq_results ADD COLUMN offers_count INTEGER", ("rfq_results", "offers_count")),
    ("ALTER TABLE rfq_results ADD COLUMN min_price REAL", ("rfq_results", "min_price")),
    ("ALTER TABLE rfq_results ADD COLUMN invitations_sent INTEGER", ("rfq_results", "invitations_sent")),
    ("ALTER TABLE rfq_results ADD COLUMN viewers_count INTEGER", ("rfq_results", "viewers_count")),
    ("ALTER TABLE rfq_results ADD COLUMN seen_item_count INTEGER", ("rfq_results", "seen_item_count")),
    ("ALTER TABLE rfq_results ADD COLUMN last_viewed_at TEXT", ("rfq_results", "last_viewed_at")),
    ("ALTER TABLE rfq_results ADD COLUMN response_deadline TEXT", ("rfq_results", "response_deadline")),
    ("ALTER TABLE rfq_results ADD COLUMN declined_count INTEGER", ("rfq_results", "declined_count")),
    ("ALTER TABLE rfq_results ADD COLUMN files_updated_at TEXT", ("rfq_results", "files_updated_at")),
    ("ALTER TABLE rfq_results ADD COLUMN docs_notified_at TEXT", ("rfq_results", "docs_notified_at")),

    ("""CREATE TABLE IF NOT EXISTS rfq_activity (
            rfq_item_id     INTEGER NOT NULL,
            supplier_name   TEXT    NOT NULL,
            drawing_number  TEXT,
            item_name       TEXT,
            email_sent_at   TEXT,      -- NULL = zaproszenia nie wysłano
            first_viewed_at TEXT,
            last_viewed_at  TEXT,
            view_count      INTEGER,   -- 0 = nie zajrzał
            seen_this_item  INTEGER,   -- 1 = wszedł po dodaniu tej pozycji
            has_offer       INTEGER,
            is_winner       INTEGER,
            win_price       REAL,
            offer_price     REAL,      -- cena złożonej oferty (przed wyborem)
            offer_currency  TEXT,
            offer_lead_time INTEGER,
            -- Zastrzeżenia zmieniające sens ceny („bez obróbki cieplnej").
            -- Bez nich user widział samą kwotę.
            offer_notes     TEXT,
            offer_submitted_at TEXT,
            -- ODMOWA: bez tego „brak oferty" i „odmowa" wyglądały w RM_BAZA
            -- identycznie („—"), a to różnica między „czekamy" a „szukaj dalej".
            has_declined    INTEGER,
            decline_reason  TEXT,      -- kod z listy zamkniętej (brak_mocy…)
            decline_label   TEXT,      -- gotowa etykieta PL z portalu
            decline_notes   TEXT,
            declined_at     TEXT,
            synced_at       TEXT DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (rfq_item_id, supplier_name)
        )""", None),
    ("CREATE INDEX IF NOT EXISTS idx_rfq_activity_drawing"
     " ON rfq_activity(drawing_number)", None),
]


MIGRACJE_MAPOWANIA = [
    """CREATE TABLE IF NOT EXISTS mapowania (
           numer_rysunku   TEXT PRIMARY KEY,
           symbol_subiekt  TEXT NOT NULL,
           id_subiekt      INTEGER,
           nazwa_subiekt   TEXT,
           sposob          TEXT NOT NULL,
           kto             TEXT,
           kiedy           TEXT NOT NULL,
           uwagi           TEXT
       )""",
    "CREATE INDEX IF NOT EXISTS idx_map_sposob ON mapowania(sposob)",
    "CREATE INDEX IF NOT EXISTS idx_map_symbol ON mapowania(symbol_subiekt)",
    """CREATE TABLE IF NOT EXISTS aliasy_scalen (
           id            INTEGER PRIMARY KEY AUTOINCREMENT,
           stary_symbol  TEXT NOT NULL,
           stary_id      INTEGER,
           nowy_symbol   TEXT NOT NULL,
           nowy_id       INTEGER,
           kto           TEXT,
           kiedy         TEXT NOT NULL
       )""",
    "CREATE INDEX IF NOT EXISTS idx_alias_nowy ON aliasy_scalen(nowy_symbol)",
    """CREATE TABLE IF NOT EXISTS dostawcy_decyzje (
           supplier_id INTEGER PRIMARY KEY,
           nazwa       TEXT,
           decyzja     TEXT NOT NULL,
           kto         TEXT,
           kiedy       TEXT NOT NULL
       )""",
    # Dziennik idempotencji — MUSI być w tej samej bazie co operacja, bo
    # zapis i wpis do dziennika idą JEDNĄ transakcją (§3). Transakcja SQLite
    # nie rozciąga się na dwa pliki.
    """CREATE TABLE IF NOT EXISTS _server_request_log (
           request_id  TEXT PRIMARY KEY,
           operation   TEXT NOT NULL,
           kto         TEXT,
           result_json TEXT,
           created_at  TEXT NOT NULL
       )""",
    "CREATE INDEX IF NOT EXISTS idx_server_request_log_czas"
    " ON _server_request_log(created_at)",
    """CREATE TABLE IF NOT EXISTS odrzucone_dopasowania (
           numer_rysunku  TEXT NOT NULL,
           symbol_subiekt TEXT NOT NULL,
           kto            TEXT,
           kiedy          TEXT NOT NULL,
           PRIMARY KEY (numer_rysunku, symbol_subiekt)
       )""",
]


class BladOperacji(Exception):
    """Operacja nieznana albo wywołana ze złymi parametrami.

    Osobny wyjątek, bo to NIE jest awaria serwera — to błąd wywołania.
    Serwer odpowiada `ok: false`, nie zrywa połączenia.
    """


def _parametry(nazwa, definicja, params):
    """Słownik parametrów → krotka w kolejności wymaganej przez SQL."""
    _, nazwy = definicja
    params = params or {}
    brakuje = [n for n in nazwy if n not in params]
    if brakuje:
        raise BladOperacji(
            "operacja %r: brakuje parametrów %s" % (nazwa, ", ".join(brakuje)))
    return tuple(params[n] for n in nazwy)


def wykonaj_odczyt(con, nazwa, params=None):
    """Odczyt z mastera. Zwraca listę słowników (JSON-owalnych)."""
    definicja = ODCZYT.get(nazwa)
    if definicja is None:
        raise BladOperacji("nieznana operacja odczytu: %r" % (nazwa,))
    sql, _ = definicja
    stary = con.row_factory
    try:
        con.row_factory = sqlite3.Row
        kur = con.execute(sql, _parametry(nazwa, definicja, params))
        return [dict(w) for w in kur.fetchall()]
    finally:
        con.row_factory = stary


def wykonaj_zapis(con, nazwa, params=None):
    """Pojedynczy zapis. BEZ commitu — transakcją steruje wołający.

    Commit należy do wołającego, bo zapis i wpis do `_server_request_log`
    muszą być JEDNĄ transakcją (§3). Gdyby commitować tutaj, wróciłaby
    dziura: operacja zapisana, dziennik nie — i ponowienie po zerwanym TCP
    zrobiłoby ją drugi raz.
    """
    definicja = ZAPIS.get(nazwa)
    if definicja is None:
        raise BladOperacji("nieznana operacja zapisu: %r" % (nazwa,))
    sql, _ = definicja
    kur = con.execute(sql, _parametry(nazwa, definicja, params))
    return {"rowcount": kur.rowcount, "lastrowid": kur.lastrowid}


def zastosuj_migracje(con):
    """Schemat mastera do bieżącej wersji. Wykonuje TYLKO właściciel pliku.

    Idempotentne: CREATE TABLE IF NOT EXISTS, a ALTER-y poprzedzone
    sprawdzeniem kolumny. Zwraca listę tego, co faktycznie dołożono.
    """
    zrobione = []
    for sql, warunek in MIGRACJE + MIGRACJE_RFQ:
        if warunek is not None:
            tabela, kolumna = warunek
            try:
                kolumny = {r[1] for r in con.execute(
                    "PRAGMA table_info(%s)" % tabela)}
            except sqlite3.Error:
                continue                 # tabeli nie ma — nie ma czego migrować
            if not kolumny or kolumna in kolumny:
                continue
        try:
            con.execute(sql)
            zrobione.append(sql.split("\n")[0].strip()[:70])
        except sqlite3.OperationalError as e:
            # „duplicate column" przy wyścigu dwóch startów — nieszkodliwe.
            if "duplicate column" not in str(e).lower():
                raise
    if zrobione:
        con.commit()
    return zrobione


def wyczysc_dziennik(con, starsze_niz_h=24):
    """Kasuje wpisy `_server_request_log` starsze niż N godzin (§3)."""
    granica = datetime.now().timestamp() - starsze_niz_h * 3600
    iso = datetime.fromtimestamp(granica).isoformat(timespec="seconds")
    kur = con.execute("DELETE FROM _server_request_log WHERE created_at < ?", (iso,))
    con.commit()
    return kur.rowcount


def znane_operacje():
    """Nazwy wszystkich operacji — do diagnostyki i testów zgodności."""
    return {"odczyt": sorted(ODCZYT), "zapis": sorted(ZAPIS)}


# ═══════════════════════════════════════════════════════════════════════
# SCHEMAT ARCHIWUM FAKTUR KSeF  (FV_KSEF.sqlite)
# ═══════════════════════════════════════════════════════════════════════
#
# ⚠️ OSOBNY PLIK, czwarta baza serwera. Operacje maja prefiks `ksef-`.
#
# Kolumna `xml` trzyma TRESC faktury, nie tylko sciezke do pliku. Dzieki temu
# archiwum to JEDEN plik: nie ma katalogu z XML-ami, ktory trzeba osobno
# udostepniac, kopiowac i backupowac. Faktura wazy ~4 KB, wiec baza jest dla
# niej naturalnym miejscem. `plik` zostaje — niesie oryginalna nazwe, pod
# ktora XML trafil z KSeF (12.09.2026).

MIGRACJE_KSEF = [
    """CREATE TABLE IF NOT EXISTS faktury (
           ksef_number      TEXT PRIMARY KEY,
           numer_faktury    TEXT,
           sprzedawca_nip   TEXT,
           sprzedawca       TEXT,
           data_wystawienia TEXT,
           wartosc_netto    REAL,
           pozycji          INTEGER,
           plik             TEXT,
           pobrano          TEXT,
           xml              TEXT
       )""",
    """CREATE TABLE IF NOT EXISTS pozycje (
           ksef_number   TEXT,
           nr_wiersza    INTEGER,
           nazwa         TEXT,
           jednostka     TEXT,
           ilosc         REAL,
           cena_netto    REAL,
           wartosc_netto REAL,
           PRIMARY KEY (ksef_number, nr_wiersza)
       )""",
    "CREATE INDEX IF NOT EXISTS idx_poz_nazwa ON pozycje(nazwa)",
    "CREATE INDEX IF NOT EXISTS idx_fakt_nip  ON faktury(sprzedawca_nip)",
    "CREATE INDEX IF NOT EXISTS idx_fakt_data ON faktury(data_wystawienia)",
]

# ── operacje archiwum KSeF ──────────────────────────────────────────────
#
# LOWER_PL rejestruje serwer (`rm_serwer._uprosc_pl`) — wbudowane LOWER()
# w SQLite dziala tylko na ASCII, wiec „Ciete" zostawaloby „cIete".

ODCZYT.update({
    "ksef-faktury": (
        "SELECT ksef_number, numer_faktury, sprzedawca_nip, sprzedawca,"
        "       data_wystawienia, wartosc_netto, pozycji"
        "  FROM faktury ORDER BY data_wystawienia DESC, numer_faktury DESC",
        [],
    ),
    "ksef-faktury-szukaj": (
        "SELECT ksef_number, numer_faktury, sprzedawca_nip, sprzedawca,"
        "       data_wystawienia, wartosc_netto, pozycji"
        "  FROM faktury"
        " WHERE LOWER_PL(numer_faktury) LIKE ? OR LOWER_PL(sprzedawca) LIKE ?"
        "    OR sprzedawca_nip LIKE ?"
        "    OR ksef_number IN (SELECT ksef_number FROM pozycje"
        "                       WHERE LOWER_PL(nazwa) LIKE ?)"
        " ORDER BY data_wystawienia DESC, numer_faktury DESC",
        ["wzor", "wzor2", "nip", "wzor3"],
    ),
    "ksef-pozycje": (
        "SELECT nr_wiersza, nazwa, jednostka, ilosc, cena_netto, wartosc_netto"
        "  FROM pozycje WHERE ksef_number = ? ORDER BY nr_wiersza",
        ["ksef_number"],
    ),
    "ksef-xml": (
        "SELECT xml, plik FROM faktury WHERE ksef_number = ?",
        ["ksef_number"],
    ),
    "ksef-numery": (
        "SELECT ksef_number FROM faktury",
        [],
    ),
    "ksef-zna": (
        "SELECT 1 FROM faktury WHERE ksef_number = ?",
        ["ksef_number"],
    ),
    "ksef-dostawcy": (
        "SELECT DISTINCT sprzedawca_nip, sprzedawca FROM faktury"
        " WHERE sprzedawca_nip <> '' ORDER BY sprzedawca",
        [],
    ),
    "ksef-podsumowanie": (
        "SELECT COUNT(*) AS faktur, COALESCE(SUM(wartosc_netto), 0) AS wartosc,"
        "       MIN(data_wystawienia) AS od, MAX(data_wystawienia) AS do,"
        "       (SELECT COUNT(*) FROM pozycje) AS pozycji"
        "  FROM faktury",
        [],
    ),
})

ZAPIS.update({
    "ksef-faktura-zapisz": (
        "INSERT OR REPLACE INTO faktury"
        " (ksef_number, numer_faktury, sprzedawca_nip, sprzedawca,"
        "  data_wystawienia, wartosc_netto, pozycji, plik, pobrano, xml)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        ["ksef_number", "numer_faktury", "sprzedawca_nip", "sprzedawca",
         "data_wystawienia", "wartosc_netto", "pozycji", "plik", "pobrano", "xml"],
    ),
    "ksef-pozycje-usun": (
        "DELETE FROM pozycje WHERE ksef_number = ?",
        ["ksef_number"],
    ),
    "ksef-pozycja-zapisz": (
        "INSERT OR REPLACE INTO pozycje"
        " (ksef_number, nr_wiersza, nazwa, jednostka, ilosc, cena_netto, wartosc_netto)"
        " VALUES (?,?,?,?,?,?,?)",
        ["ksef_number", "nr_wiersza", "nazwa", "jednostka", "ilosc",
         "cena_netto", "wartosc_netto"],
    ),
})
