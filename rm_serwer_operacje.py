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
    "users-list": (
        "SELECT id, username, display_name, role FROM users ORDER BY username COLLATE NOCASE",
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
    "supplier-po-normalizacji": (
        "SELECT id FROM suppliers WHERE name_normalized = ?",
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
    "rfq-tagi": (
        "SELECT id, name, label FROM rfq_tags ORDER BY sort_order, label",
        [],
    ),
    "rfq-tagi-dostawcy": (
        "SELECT tag_id FROM rfq_supplier_tags WHERE supplier_id = ?",
        ["supplier_id"],
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
    "zd-zamowione-list": (
        "SELECT item_id, termin, kiedy, supplier_id FROM zd_zamowione_pozycje"
        " WHERE project_id = ?",
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
    "project-status-set": (
        "UPDATE projects SET project_status = ? WHERE project_id = ?",
        ["project_status", "project_id"],
    ),
    "project-priorytet-set": (
        "UPDATE projects SET priority = ? WHERE project_id = ?",
        ["priority", "project_id"],
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
# MIGRACJE DRUGIEJ BAZY — subiekt_mapowania.sqlite
# ═══════════════════════════════════════════════════════════════════════
#
# Osobny plik obok mastera. Schemat ten sam co w `subiekt_mapowania.py` —
# gdy tam coś dojdzie, dopisać i tutaj, bo to właściciel pliku zakłada
# tabele, nie klient.

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
    for sql, warunek in MIGRACJE:
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
