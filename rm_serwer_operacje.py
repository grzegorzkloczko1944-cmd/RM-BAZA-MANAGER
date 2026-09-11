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
    "project-status-sync": (
        "UPDATE projects SET status = ?, designer = ?, montaz = ?, fat = ?,"
        " completed_at = ? WHERE project_id = ?",
        ["status", "designer", "montaz", "fat", "completed_at", "project_id"],
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
