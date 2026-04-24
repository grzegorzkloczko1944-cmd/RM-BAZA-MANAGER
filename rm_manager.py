"""
============================================================================
RM_MANAGER - Zaawansowane zarządzanie procesami projektów
============================================================================
Zgodnie z RM_MANAGER_SPEC.md:
- Multi-period tracking (etapy mogą wracać wielokrotnie)
- Pauzy automatyczne
- Dependency graph (FS/SS)
- Automatic forecasting (topological sort)
- Critical path analysis
- Synchronizacja z MASTER.SQLITE (OPCJONALNA)

Architektura - CENTRALNA BAZA:
Y:/RM_MANAGER/
├─ rm_manager.sqlite              ← JEDNA baza dla WSZYSTKICH projektów
│  ├─ stage_definitions
│  ├─ project_stages
│  ├─ stage_schedule
│  ├─ stage_actual_periods       ← multi-period!
│  ├─ stage_dependencies         ← graf FS/SS
│  └─ stage_events
└─ LOCKS/
   └─ project_X.lock              ← heartbeat locks

RM_MANAGER ↔ RM_BAZA:
- RM_MANAGER działa autonomicznie
- sync_to_master() OPCJONALNA (tylko do wyświetlania w RM_BAZA)
- Oba systemy niezależne
============================================================================
"""

import os
import glob
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from collections import deque
import time as _time


# ============================================================================
# SMB-SAFE CONNECTION LAYER (NAS/LAN)
# ============================================================================
# Każde połączenie RM_MANAGER do SQLite na NAS MUSI przechodzić przez tę warstwę.
# Ustawia PRAGMAs krytyczne dla poprawnej pracy przez SMB:
#   - journal_mode=DELETE  (WAL nie działa przez SMB!)
#   - busy_timeout=5000    (5s wait zamiast natychmiastowego SQLITE_BUSY)
#   - synchronous=NORMAL   (kompromis wydajność/bezpieczeństwo)
#   - locking_mode=NORMAL  (zwalniaj lock po transakcji)
# ============================================================================

def _open_rm_connection(db_path: str, row_factory: bool = True,
                        uri: bool = False) -> sqlite3.Connection:
    """Otwórz SMB-safe połączenie do dowolnej bazy RM_MANAGER na NAS.

    Stosowane dla:
    - rm_manager.sqlite (master RM_MANAGER)
    - rm_manager_project_*.sqlite (per-projekt)
    - master.sqlite (shared RM_BAZA) - docelowo osobna warstwa (etap 5)

    Args:
        db_path: Ścieżka do bazy (lub URI jeśli uri=True)
        row_factory: Ustawić sqlite3.Row (domyślnie True)
        uri: Otworzyć jako URI (np. 'file:path?mode=ro')

    Returns:
        sqlite3.Connection z ustawionymi PRAGMAs i row_factory
    """
    con = sqlite3.connect(db_path, timeout=10.0, uri=uri)
    if row_factory:
        con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=DELETE")
    con.execute("PRAGMA busy_timeout=5000")
    con.execute("PRAGMA locking_mode=NORMAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA cache_size=-2000")
    con.execute("PRAGMA temp_store=MEMORY")
    # Weryfikuj journal_mode - WAL na SMB powoduje korupcję
    actual_mode = con.execute("PRAGMA journal_mode").fetchone()[0]
    if actual_mode.upper() != "DELETE":
        print(f"🔴 OSTRZEŻENIE: journal_mode={actual_mode} zamiast DELETE dla {db_path}!")
        print(f"   WAL mode NIE DZIAŁA przez SMB - ryzyko korupcji danych!")
    return con


def _rm_safe_commit(con: sqlite3.Connection, max_retries: int = 3,
                    retry_delay: float = 0.5) -> None:
    """Commit z retry na 'database is locked' (typowe na NAS/SMB).

    busy_timeout=5000 w _open_rm_connection obsługuje większość przypadków,
    ale przy dużym obciążeniu (10 użytkowników) commit może nadal dostać BUSY.
    Retry daje dodatkową warstwę bezpieczeństwa.
    """
    for attempt in range(max_retries):
        try:
            con.commit()
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                wait = retry_delay * (attempt + 1)
                print(f"⚠️ Database locked przy commit "
                      f"(próba {attempt + 1}/{max_retries}), retry za {wait:.1f}s...")
                _time.sleep(wait)
                continue
            raise


# ============================================================================
# Per-projekt architecture helpers
# ============================================================================

def get_project_db_path(rm_manager_dir: str, project_id: int) -> str:
    """Zwraca ścieżkę do per-projekt bazy RM_MANAGER.

    Konwencja: rm_manager_project_{project_id}.sqlite
    Analogicznie do project_{project_id}.sqlite w RM_BAZA.
    """
    return os.path.join(rm_manager_dir, f"rm_manager_project_{project_id}.sqlite")


# ============================================================================
# Helper functions
# ============================================================================

def get_timestamp_now() -> str:
    """Zwraca timestamp bez sekund: YYYY-MM-DD HH:MM"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ============================================================================
# STAGE DEFINITIONS - 10 statusów projektu
# ============================================================================

# Format: (code, display_name, color, is_milestone)
# is_milestone=1: zdarzenie instant (bez czasu trwania)
# is_milestone=0: etap z czasem trwania
STAGE_DEFINITIONS = [
    ('PRZYJETY', 'Przyjęty', '#3498db', 1),        # MILESTONE - trigger projektu
    ('PROJEKT', 'Projekt', '#9b59b6', 0),
    ('ELEKTROPROJEKT', 'Elektroprojekt', '#8e44ad', 0),  # Projekt elektryczny
    ('KOMPLETACJA', 'Kompletacja', '#e67e22', 0),
    ('MONTAZ', 'Montaż', '#e74c3c', 0),
    ('ELEKTROMONTAZ', 'Elektromontaż', '#f39c12', 0),
    ('TRANSPORT', 'Transport', '#16a085', 1),      # MILESTONE informacyjny
    ('URUCHOMIENIE', 'Uruchomienie', '#1abc9c', 0),
    ('URUCHOMIENIE_U_KLIENTA', 'SAT', '#17a589', 1),  # MILESTONE informacyjny
    ('FAT', 'FAT', '#27ae60', 1),                  # MILESTONE informacyjny
    ('ODBIORY', 'Odbiory', '#27ae60', 0),
    ('ODBIOR_1', 'Odbiór 1', '#229954', 1),        # MILESTONE informacyjny
    ('ODBIOR_2', 'Odbiór 2', '#1e8449', 1),        # MILESTONE informacyjny
    ('ODBIOR_3', 'Odbiór 3', '#196f3d', 1),        # MILESTONE informacyjny
    ('POPRAWKI', 'Poprawki', '#95a5a6', 0),
    # 🚫 WSTRZYMANY usunięty - to nie etap, to overlay/pauza!
    ('ZAKONCZONY', 'Zapłacony', '#2c3e50', 1),     # MILESTONE - zakończenie projektu
]

# Priorytety statusów (do determine_display_status)
STAGE_PRIORITY = {
    # 🚫 WSTRZYMANY usunięty - pauza nie jest etapem!
    'ZAKONCZONY': 90,
    'POPRAWKI': 80,
    'ODBIORY': 70,
    'URUCHOMIENIE': 60,
    'ELEKTROMONTAZ': 50,
    'MONTAZ': 40,
    'KOMPLETACJA': 30,
    'ELEKTROPROJEKT': 25,
    'PROJEKT': 20,
    'PRZYJETY': 10,
}

# Domyślne zależności między etapami (automatyczny workflow)
# Format: (from_stage, to_stage, dependency_type, lag_days)
# FS = Finish-to-Start (następny czeka na zakończenie poprzedniego)
# SS = Start-to-Start (następny może zacząć gdy poprzedni się zaczął)
DEFAULT_DEPENDENCIES = [
    # 🔵 START PROJEKTU - PRZYJĘTY jako trigger
    ('PRZYJETY',      'PROJEKT',       'FS', 0),  # Projekt może zacząć po przyjęciu
    
    # 🔵 SEKWENCJA GŁÓWNA
    ('PROJEKT',       'KOMPLETACJA',   'FS', 0),  # Kompletacja po projekcie
    ('KOMPLETACJA',   'MONTAZ',        'FS', 0),  # Montaż po kompletacji
    
    # 🔵 ELEKTROPROJEKT → ELEKTROMONTAŻ (niezależny start, blokuje elektromontaż)
    ('ELEKTROPROJEKT', 'ELEKTROMONTAZ', 'FS', 0),  # Elektromontaż czeka na elektroprojekt
    
    # 🔵 RÓWNOLEGŁOŚĆ - ELEKTROMONTAŻ i MONTAŻ mogą iść równolegle
    ('MONTAZ',        'ELEKTROMONTAZ', 'SS', 0),  # Elektromontaż może zacząć gdy montaż się zaczął
    
    # 🔵 URUCHOMIENIE tylko po montażu (elektromontaż i uruchomienie są niezależne)
    ('MONTAZ',        'URUCHOMIENIE',  'FS', 0),  # Uruchomienie po montażu
    
    # 🔵 KOŃCÓWKA
    ('URUCHOMIENIE',  'ODBIORY',       'FS', 0),  # Odbiory po uruchomieniu
    ('ODBIORY',       'POPRAWKI',      'FS', 0),  # Poprawki po odbiorach (jeśli są)
]

# Zależności które zostały usunięte z DEFAULT_DEPENDENCIES i muszą być wyczyszczone
# z istniejących projektów podczas migracji.
# Format: (predecessor, successor) — usuń KAŻDY rekord z tą parą, niezależnie od typu.
DEPRECATED_DEPENDENCIES = [
    ('ELEKTROMONTAZ', 'URUCHOMIENIE'),  # 2026-04-22: usunięto — etapy są teraz w pełni niezależne
]


def remove_deprecated_dependencies_for_project(rm_db_path: str, project_id: int) -> int:
    """Usuwa z bazy projektu zależności które zostały wycofane z DEFAULT_DEPENDENCIES.

    Bezpieczne: usuwa tylko pary z DEPRECATED_DEPENDENCIES, nic innego nie zmienia.

    Args:
        rm_db_path: Ścieżka do bazy per-projekt
        project_id: ID projektu

    Returns:
        Liczba usuniętych wpisów
    """
    con = _open_rm_connection(rm_db_path)
    removed = 0
    for pred, succ in DEPRECATED_DEPENDENCIES:
        cursor = con.execute("""
            DELETE FROM stage_dependencies
            WHERE project_id = ? AND predecessor_stage_code = ? AND successor_stage_code = ?
        """, (project_id, pred, succ))
        removed += cursor.rowcount
    con.commit()
    con.close()
    if removed > 0:
        print(f"🧹 Projekt {project_id}: usunięto {removed} wycofanych zależności")
    return removed


# ============================================================================
# PROJECT STATUS - State Machine (kontrola globalnego stanu projektu)
# ============================================================================

# Stany projektu (globalny status w master.sqlite)
class ProjectStatus:
    NEW = 'NEW'                    # Projekt utworzony, nie przyjęty
    ACCEPTED = 'ACCEPTED'          # PRZYJĘTY kliknięty - gotowy do pracy
    IN_PROGRESS = 'IN_PROGRESS'    # Co najmniej jeden etap aktywny
    PAUSED = 'PAUSED'              # Projekt wstrzymany (pauza overlay przez project_pauses)
    DONE = 'DONE'                  # Projekt zakończony (ZAKOŃCZONY ustawiony)

# Dozwolone przejścia stanów (state machine)
ALLOWED_TRANSITIONS = {
    ProjectStatus.NEW: [ProjectStatus.ACCEPTED],
    ProjectStatus.ACCEPTED: [ProjectStatus.IN_PROGRESS, ProjectStatus.DONE],  # DONE tylko jeśli żadne etapy
    ProjectStatus.IN_PROGRESS: [ProjectStatus.PAUSED, ProjectStatus.DONE],
    ProjectStatus.PAUSED: [ProjectStatus.IN_PROGRESS],
    ProjectStatus.DONE: [ProjectStatus.IN_PROGRESS, ProjectStatus.ACCEPTED],  # Wznowienie zakończonego projektu
}

# Event types (dla project_events)
class EventType:
    PRZYJETY = 'PRZYJETY'
    ZAKONCZONY = 'ZAKONCZONY'
    WSTRZYMANY = 'WSTRZYMANY'
    WZNOWIONY = 'WZNOWIONY'


# ============================================================================
# HELPERS - State Management
# ============================================================================

def is_project_editable(status: str) -> bool:
    """Sprawdź czy projekt jest edytowalny (nie zakończony)
    
    Args:
        status: ProjectStatus (NEW, ACCEPTED, IN_PROGRESS, PAUSED, DONE)
        
    Returns:
        True jeśli można edytować, False jeśli projekt zakończony
    """
    return status != ProjectStatus.DONE


# ============================================================================
# Inicjalizacja bazy danych
# ============================================================================

# Domyślne uprawnienia per rola (używane przy inicjalizacji tabeli)
DEFAULT_ROLE_PERMISSIONS = [
    # role,       start, end, edit_dates, sync, critical_path, manage_permissions
    ('ADMIN',     1,     1,   1,          1,    1,             1),
    ('USER$$',    1,     1,   1,          1,    1,             0),
    ('USER$',     1,     1,   1,          0,    1,             0),
    ('USER',      1,     1,   0,          0,    0,             0),
    ('GUEST',     0,     0,   0,          0,    0,             0),
]


def ensure_rm_master_tables(master_db_path: str):
    """Tworzy tabele w rm_manager.sqlite (MASTER RM_MANAGER):
    - stage_definitions       (słownik etapów)
    - project_file_tracking   (integralność plików RM_BAZA)
    - rm_user_permissions     (uprawnienia per kategoria użytkownika)
    """
    Path(master_db_path).parent.mkdir(parents=True, exist_ok=True)
    con = _open_rm_connection(master_db_path)

    con.execute("""
        CREATE TABLE IF NOT EXISTS stage_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            display_name TEXT,
            color TEXT,
            is_milestone INTEGER DEFAULT 0
        )
    """)
    # Dodaj kolumnę is_milestone jeśli brak (upgrade starej bazy)
    try:
        con.execute("ALTER TABLE stage_definitions ADD COLUMN is_milestone INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # kolumna już istnieje
    count = con.execute("SELECT COUNT(*) FROM stage_definitions").fetchone()[0]
    if count == 0:
        con.executemany("""
            INSERT INTO stage_definitions (code, display_name, color, is_milestone) VALUES (?, ?, ?, ?)
        """, STAGE_DEFINITIONS)
        print(f"✅ Master: wstawiono {len(STAGE_DEFINITIONS)} definicji etapów")

    con.execute("""
        CREATE TABLE IF NOT EXISTS project_file_tracking (
            project_id INTEGER PRIMARY KEY,
            project_name TEXT,
            file_path TEXT NOT NULL,
            file_birth_time REAL NOT NULL,
            last_verified_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            verification_status TEXT DEFAULT 'OK',
            CHECK (verification_status IN ('OK', 'MISSING', 'BIRTH_MISMATCH'))
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_file_tracking_status ON project_file_tracking(verification_status)")

    # Tabela uprawnień per rola (kategoria użytkownika)
    con.execute("""
        CREATE TABLE IF NOT EXISTS rm_user_permissions (
            role                TEXT PRIMARY KEY,
            can_start_stage     INTEGER NOT NULL DEFAULT 0,
            can_end_stage       INTEGER NOT NULL DEFAULT 0,
            can_edit_dates      INTEGER NOT NULL DEFAULT 0,
            can_sync_master     INTEGER NOT NULL DEFAULT 0,
            can_critical_path   INTEGER NOT NULL DEFAULT 0,
            can_manage_permissions INTEGER NOT NULL DEFAULT 0,
            updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Wstaw domyślne uprawnienia jeśli tabela pusta
    existing = con.execute("SELECT COUNT(*) FROM rm_user_permissions").fetchone()[0]
    if existing == 0:
        con.executemany("""
            INSERT INTO rm_user_permissions
                (role, can_start_stage, can_end_stage, can_edit_dates,
                 can_sync_master, can_critical_path, can_manage_permissions)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, DEFAULT_ROLE_PERMISSIONS)
        print(f"✅ Master: wstawiono domyślne uprawnienia dla {len(DEFAULT_ROLE_PERMISSIONS)} ról")

    # SAFETY: ADMIN musi ZAWSZE mieć can_manage_permissions = 1
    # (naprawa po bugfix z pustymi uprawnieniami)
    con.execute("""
        UPDATE rm_user_permissions
        SET can_manage_permissions = 1, updated_at = CURRENT_TIMESTAMP
        WHERE role = 'ADMIN' AND can_manage_permissions = 0
    """)
    if con.total_changes:
        print("🔧 Naprawiono uprawnienia ADMIN (can_manage_permissions)")

    # Tabela synchronizacji z RM_BAZA (tracking)
    con.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_date           TEXT NOT NULL,
            sync_timestamp      TEXT NOT NULL,
            projects_synced     INTEGER DEFAULT 0,
            user                TEXT,
            notes               TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_sync_log_date ON sync_log(sync_date)")

    # ============================================================================
    # SYSTEM PŁATNOŚCI (2026-04-13)
    # ============================================================================
    # Transze płatności (np. 30%, 70%, 100%) z datami
    con.execute("""
        CREATE TABLE IF NOT EXISTS payment_milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            percentage INTEGER NOT NULL CHECK (percentage > 0 AND percentage <= 100),
            payment_date DATE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            modified_at DATETIME,
            modified_by TEXT,
            UNIQUE(project_id, percentage)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_payment_project ON payment_milestones(project_id)")
    # Migracja: dodaj kolumnę payment_type jeśli nie istnieje (upgrade starej bazy)
    try:
        con.execute("ALTER TABLE payment_milestones ADD COLUMN payment_type TEXT NOT NULL DEFAULT 'PŁATNOŚĆ'")
    except sqlite3.OperationalError:
        pass  # kolumna już istnieje

    # Historia zmian płatności (audit log)
    con.execute("""
        CREATE TABLE IF NOT EXISTS payment_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            percentage INTEGER NOT NULL,
            payment_date DATE,
            action TEXT NOT NULL CHECK (action IN ('ADDED', 'MODIFIED', 'DELETED')),
            changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            changed_by TEXT NOT NULL,
            old_date DATE
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_payment_history_project ON payment_history(project_id)")

    # Konfiguracja powiadomień email (lista odbiorców, trigger percentage)
    con.execute("""
        CREATE TABLE IF NOT EXISTS payment_notification_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            trigger_percentage INTEGER NOT NULL DEFAULT 100,
            email_recipients TEXT NOT NULL,
            smtp_server TEXT,
            smtp_port INTEGER DEFAULT 587,
            smtp_user TEXT,
            smtp_password TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            modified_at DATETIME
        )
    """)
    # Wstaw domyślną konfigurację (pusta lista odbiorców)
    con.execute("""
        INSERT OR IGNORE INTO payment_notification_config
            (id, trigger_percentage, email_recipients, enabled)
        VALUES (1, 100, '[]', 1)
    """)

    # Log wysłanych powiadomień email
    con.execute("""
        CREATE TABLE IF NOT EXISTS payment_notifications_sent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            project_name TEXT,
            percentage INTEGER NOT NULL,
            payment_date DATE,
            recipients TEXT NOT NULL,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            sent_by TEXT,
            email_status TEXT CHECK (email_status IN ('SUCCESS', 'FAILED', 'PENDING')),
            error_message TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_notifications_project ON payment_notifications_sent(project_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_notifications_status ON payment_notifications_sent(email_status)")

    # In-app notifications (powiadomienia w aplikacji)
    con.execute("""
        CREATE TABLE IF NOT EXISTS in_app_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            project_name TEXT,
            notification_type TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            is_read INTEGER NOT NULL DEFAULT 0,
            read_at DATETIME,
            read_by TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_in_app_notifications_read ON in_app_notifications(is_read)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_in_app_notifications_project ON in_app_notifications(project_id)")

    # ============================================================================
    # KODY PLC - Kody odblokowujące maszyny (2026-04-14)
    # ============================================================================
    # 3 rodzaje kodów: chwilowy, dłuższy, permanentny
    con.execute("""
        CREATE TABLE IF NOT EXISTS plc_unlock_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            code_type TEXT NOT NULL CHECK (code_type IN ('TEMPORARY', 'EXTENDED', 'PERMANENT')),
            unlock_code TEXT NOT NULL,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            modified_at DATETIME,
            modified_by TEXT,
            is_used INTEGER NOT NULL DEFAULT 0,
            used_at DATETIME,
            used_by TEXT,
            notes TEXT,
            sent_at DATETIME,
            sent_by TEXT,
            sent_via TEXT,
            expiry_date DATETIME
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_plc_codes_project ON plc_unlock_codes(project_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_plc_codes_type ON plc_unlock_codes(code_type)")
    
    # Dodaj kolumnę default_recipients jeśli nie istnieje (lista ID pracowników jako JSON)
    try:
        con.execute("ALTER TABLE plc_unlock_codes ADD COLUMN default_recipients TEXT")
    except sqlite3.OperationalError:
        pass  # kolumna już istnieje
    
    # Tabela uprawnień do wysyłki kodów PLC
    con.execute("""
        CREATE TABLE IF NOT EXISTS plc_authorized_senders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            added_by TEXT,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_plc_senders_username ON plc_authorized_senders(username)")

    # Globalna tabela odbiorców kodów PLC (wspólna dla wszystkich projektów)
    con.execute("""
        CREATE TABLE IF NOT EXISTS plc_global_recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_key TEXT NOT NULL UNIQUE,
            recipients_json TEXT NOT NULL,
            updated_by TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Domyślny rekord dla globalnych odbiorców
    con.execute("""
        INSERT OR IGNORE INTO plc_global_recipients (setting_key, recipients_json)
        VALUES ('default_recipients', '[]')
    """)

    # ============================================================================
    # OPTYMALIZATOR PRODUKCJI (2026-04-19)
    # ============================================================================
    # Ograniczenia zasobów — reguły biznesowe typu "konstruktor pracuje nad 1 projektem"
    con.execute("""
        CREATE TABLE IF NOT EXISTS resource_constraints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            constraint_type TEXT NOT NULL CHECK (constraint_type IN (
                'exclusive_person',
                'max_concurrent_category',
                'max_concurrent_stage'
            )),
            category TEXT,
            stage_code TEXT,
            max_parallel INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            modified_at DATETIME,
            modified_by TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_res_constraints_type ON resource_constraints(constraint_type)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_res_constraints_active ON resource_constraints(is_active)")

    # Dostępność pracowników — urlopy, L4, delegacje
    con.execute("""
        CREATE TABLE IF NOT EXISTS employee_availability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            date_from DATE NOT NULL,
            date_to DATE NOT NULL,
            reason TEXT NOT NULL CHECK (reason IN (
                'URLOP', 'L4', 'DELEGACJA', 'SZKOLENIE', 'INNE'
            )),
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
            CHECK (date_to >= date_from)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_emp_avail_employee ON employee_availability(employee_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_emp_avail_dates ON employee_availability(date_from, date_to)")

    # Dni wolne / kalendarz firmy
    con.execute("""
        CREATE TABLE IF NOT EXISTS company_calendar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL UNIQUE,
            day_type TEXT NOT NULL CHECK (day_type IN (
                'HOLIDAY', 'COMPANY_DAY_OFF', 'SATURDAY_WORK'
            )),
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_company_calendar_date ON company_calendar(date)")

    # Wyniki optymalizacji — historia uruchomień
    con.execute("""
        CREATE TABLE IF NOT EXISTS optimization_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_mode TEXT NOT NULL CHECK (run_mode IN ('fit_projects', 'optimize_all')),
            project_ids_json TEXT NOT NULL,
            date_range_start DATE,
            date_range_end DATE,
            constraints_snapshot TEXT,
            result_json TEXT,
            score_before REAL,
            score_after REAL,
            solver_status TEXT,
            solver_time_ms INTEGER,
            applied INTEGER NOT NULL DEFAULT 0,
            applied_at DATETIME,
            applied_by TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_opt_runs_mode ON optimization_runs(run_mode)")

    # Domyślne ograniczenia zasobów (jeśli tabela pusta)
    existing_constraints = con.execute("SELECT COUNT(*) FROM resource_constraints").fetchone()[0]
    if existing_constraints == 0:
        _default_constraints = [
            ('exclusive_person', 'Konstrukcja', None, 1,
             'Konstruktor pracuje nad jednym projektem jednocześnie'),
            ('exclusive_person', 'Serwis', 'URUCHOMIENIE', 1,
             'Serwisant nie może uruchamiać dwóch maszyn jednocześnie'),
            ('exclusive_person', 'Serwis', 'ODBIORY', 1,
             'Serwisant nie może prowadzić dwóch odbiorów jednocześnie'),
            ('exclusive_person', 'Montaż', None, 1,
             'Monter nie może montować dwóch maszyn jednocześnie'),
            ('exclusive_person', 'Elektromontaż', None, 1,
             'Elektromonter nie może montować dwóch maszyn jednocześnie'),
        ]
        con.executemany("""
            INSERT INTO resource_constraints
                (constraint_type, category, stage_code, max_parallel, description)
            VALUES (?, ?, ?, ?, ?)
        """, _default_constraints)
        print(f"✅ Master: wstawiono {len(_default_constraints)} domyślnych ograniczeń zasobów")

    # ============================================================================
    # SESJE UŻYTKOWNIKÓW - tracking aktywnych logowań (2026-04-24)
    # ============================================================================
    # Tabela aktywnych sesji - sprawdzanie czy użytkownik jest już zalogowany
    con.execute("""
        CREATE TABLE IF NOT EXISTS active_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            hostname TEXT NOT NULL,
            pid INTEGER NOT NULL,
            app_name TEXT NOT NULL DEFAULT 'rm_manager',
            login_at DATETIME NOT NULL,
            last_heartbeat DATETIME NOT NULL,
            client_info TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_active_sessions_user ON active_sessions(user_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_active_sessions_heartbeat ON active_sessions(last_heartbeat)")
    # UNIQUE constraint - DEFENSE IN DEPTH: drugi mechanizm chroniący przed
    # 2 sesjami tego samego usera na 1 komputerze (oprócz transakcji w register_user_session).
    # NOTE: nie blokuje 2 komputerów dla 1 usera - to obsługuje logika "force/cancel".
    con.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_active_sessions_user_host_app
        ON active_sessions(user_id, hostname, app_name)
    """)

    con.commit()
    con.close()
    print(f"✅ RM_MANAGER master baza zainicjalizowana: {master_db_path}")
    ensure_list_tables(master_db_path)


# Kategorie pracowników (stała lista)
EMPLOYEE_CATEGORIES = [
    'Elektromontaż',
    'Konstrukcja',
    'Elektroprojekt',
    'Logistyka',
    'Magazyn',
    'Montaż',
    'Programowanie',
    'Serwis',
    'Sprzedaż',
]

# Mapowanie etap → preferowana kategoria pracownika
STAGE_TO_PREFERRED_CATEGORY = {
    'PROJEKT':        ['Konstrukcja'],
    'ELEKTROPROJEKT': ['Elektroprojekt'],
    'KOMPLETACJA':    ['Logistyka', 'Magazyn'],
    'MONTAZ':         ['Montaż'],
    'ELEKTROMONTAZ':  ['Elektromontaż'],
    'URUCHOMIENIE':   ['Serwis'],
    'ODBIORY':        ['Serwis'],
    'POPRAWKI':       ['Serwis'],
    # PRZYJETY, ZAKONCZONY = milestones, zazwyczaj nie przypisujemy pracowników
}


def ensure_list_tables(master_db_path: str):
    """Tworzy tabele list zasobów w rm_manager.sqlite:
    - employees   (pracownicy z kategorią)
    - transports  (transport)
    Wywoływana ze ensure_rm_master_tables i osobno przy aktualizacji bazy.
    """
    con = _open_rm_connection(master_db_path)

    con.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            category     TEXT NOT NULL,
            description  TEXT,
            contact_info TEXT,
            is_active    INTEGER NOT NULL DEFAULT 1,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_employees_category ON employees(category)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_employees_active   ON employees(is_active)")

    con.execute("""
        CREATE TABLE IF NOT EXISTS transports (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            description  TEXT,
            contact_info TEXT,
            is_active    INTEGER NOT NULL DEFAULT 1,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_transports_active ON transports(is_active)")

    # Dodaj kolumnę phone jeśli nie istnieje (dla funkcji SMS)
    try:
        con.execute("ALTER TABLE employees ADD COLUMN phone TEXT")
    except sqlite3.OperationalError:
        pass  # kolumna już istnieje
    
    # Dodaj kolumnę email jeśli nie istnieje (osobne pole dla maila)
    try:
        con.execute("ALTER TABLE employees ADD COLUMN email TEXT")
    except sqlite3.OperationalError:
        pass  # kolumna już istnieje

    con.commit()
    con.close()
    print(f"✅ Tabele list (employees, transports) gotowe: {master_db_path}")


# ============================================================================
# Zarządzanie sesjami użytkowników (session tracking)
# ============================================================================

# Ile minut bez heartbeat = sesja uznana za martwą
DEFAULT_STALE_SESSION_MINUTES = 10


def _is_db_readonly(con: sqlite3.Connection) -> bool:
    """Sprawdź czy baza jest otwarta w trybie read-only.
    
    Wykrywa: pragma query_only=1, mode=ro w URI, brak praw zapisu.
    """
    try:
        cur = con.execute("PRAGMA query_only")
        row = cur.fetchone()
        if row and row[0] == 1:
            return True
    except Exception:
        pass
    
    # Test "miękki" - próba na temp table (rollback od razu)
    try:
        con.execute("BEGIN")
        con.execute("CREATE TEMP TABLE __ro_check__ (x INTEGER)")
        con.execute("DROP TABLE __ro_check__")
        con.rollback()
        return False
    except sqlite3.OperationalError as e:
        try:
            con.rollback()
        except Exception:
            pass
        if "readonly" in str(e).lower() or "read-only" in str(e).lower():
            return True
        return False
    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        return False


def register_user_session(master_db_path: str, user_id: int, username: str, 
                         hostname: str, pid: int, app_name: str = 'rm_manager',
                         client_info: str = None,
                         stale_minutes: int = DEFAULT_STALE_SESSION_MINUTES,
                         force: bool = False):
    """
    Atomowo zarejestruj nową sesję użytkownika w bazie.
    
    Algorytm (transakcja BEGIN IMMEDIATE - blokuje DB):
    1. Cleanup starych sesji tego usera (heartbeat > stale_minutes)
    2. Sprawdź czy są jeszcze AKTYWNE sesje na innych komputerach
    3a. Jeśli SĄ + force=False: zwróć (None, "active_session_exists", existing_session)
    3b. Jeśli SĄ + force=True: usuń je
    4. INSERT nowej sesji
    
    To eliminuje TOCTOU race - dwa równoczesne logowania nie utworzą 2 sesji.
    
    Args:
        master_db_path: Ścieżka do rm_manager.sqlite
        user_id: ID użytkownika
        username: Login użytkownika
        hostname: Nazwa komputera
        pid: PID procesu aplikacji
        app_name: Nazwa aplikacji
        client_info: Dodatkowe info (opcjonalne)
        stale_minutes: Po ilu min bez heartbeat sesja uznana za martwą
        force: Jeśli True - wymuś (usuń aktywne sesje na innych komputerach)
    
    Returns:
        Tuple (session_id, status, existing_session):
        - ("uuid...", "ok", None)                 - sesja zarejestrowana
        - ("uuid...", "readonly", None)           - DB ro, sesja nie zapisana (zwrócono fake id)
        - (None, "active_session_exists", dict)   - inny komputer, force=False
        - (None, "error", error_msg_str)          - inny błąd
    """
    import uuid
    import socket
    from datetime import datetime, timedelta
    
    if hostname is None:
        hostname = socket.gethostname()
    
    session_id = str(uuid.uuid4())
    now = datetime.now()
    now_iso = now.isoformat()
    cutoff_iso = (now - timedelta(minutes=stale_minutes)).isoformat()
    
    try:
        con = _open_rm_connection(master_db_path)
    except Exception as e:
        print(f"⚠️ Nie można otworzyć DB do rejestracji sesji: {e}")
        return (None, "error", str(e))
    
    # Sprawdź czy DB jest writable
    if _is_db_readonly(con):
        con.close()
        print(f"ℹ️  Master DB read-only - sesja NIE zapisana (tryb GUEST/backup view)")
        # Zwróć fake session_id żeby kod GUI nie crashował przy dalszej obsłudze
        return (session_id, "readonly", None)
    
    try:
        # ATOMOWA TRANSAKCJA - BEGIN IMMEDIATE blokuje DB do zapisu (eliminuje TOCTOU)
        con.execute("BEGIN IMMEDIATE")
        
        # Krok 1: Usuń stare martwe sesje tego usera (zwolnij miejsce)
        con.execute("""
            DELETE FROM active_sessions
            WHERE user_id = ? AND last_heartbeat < ?
        """, (user_id, cutoff_iso))
        
        # Krok 2: Sprawdź AKTYWNE sesje na innych komputerach
        active_others = con.execute("""
            SELECT session_id, user_id, username, hostname, pid, app_name,
                   login_at, last_heartbeat, client_info
            FROM active_sessions
            WHERE user_id = ? AND last_heartbeat >= ? AND hostname != ?
            ORDER BY login_at DESC
            LIMIT 1
        """, (user_id, cutoff_iso, hostname)).fetchone()
        
        if active_others and not force:
            # Inny komputer ma aktywną sesję - odmów
            con.rollback()
            con.close()
            existing = dict(active_others)
            print(f"⚠️  Logowanie odrzucone - {username} aktywny na {existing['hostname']}")
            return (None, "active_session_exists", existing)
        
        # Krok 3: Jeśli force=True - usuń sesje na innych komputerach
        if active_others and force:
            con.execute("""
                DELETE FROM active_sessions
                WHERE user_id = ? AND hostname != ?
            """, (user_id, hostname))
            print(f"⚡ Force-login: usunięto sesję {username}@{active_others['hostname']}")
        
        # Krok 4: Usuń ewentualne stare sesje na TYM komputerze (np. po crashu)
        con.execute("""
            DELETE FROM active_sessions
            WHERE user_id = ? AND hostname = ?
        """, (user_id, hostname))
        
        # Krok 5: INSERT nowej sesji
        con.execute("""
            INSERT INTO active_sessions 
                (session_id, user_id, username, hostname, pid, app_name, login_at, last_heartbeat, client_info)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, user_id, username, hostname, pid, app_name, now_iso, now_iso, client_info))
        
        _rm_safe_commit(con)
        con.close()
        
        print(f"✅ Zarejestrowano sesję: {username}@{hostname} (session_id: {session_id[:8]}...)")
        return (session_id, "ok", None)
    
    except sqlite3.OperationalError as e:
        try:
            con.rollback()
        except Exception:
            pass
        try:
            con.close()
        except Exception:
            pass
        if "readonly" in str(e).lower() or "read-only" in str(e).lower():
            print(f"ℹ️  DB read-only przy rejestracji sesji - pomijam")
            return (session_id, "readonly", None)
        print(f"⚠️ Błąd rejestracji sesji: {e}")
        return (None, "error", str(e))
    except Exception as e:
        try:
            con.rollback()
        except Exception:
            pass
        try:
            con.close()
        except Exception:
            pass
        print(f"⚠️ Błąd rejestracji sesji: {e}")
        return (None, "error", str(e))


def get_active_user_sessions(master_db_path: str, user_id: int, 
                            stale_minutes: int = DEFAULT_STALE_SESSION_MINUTES) -> List[Dict]:
    """
    Pobierz aktywne sesje użytkownika (heartbeat nie starszy niż stale_minutes).
    
    Funkcja read-only - działa nawet na DB ro.
    
    Returns:
        Lista słowników z danymi sesji (puste gdy brak/błąd)
    """
    from datetime import datetime, timedelta
    
    try:
        con = _open_rm_connection(master_db_path)
    except Exception as e:
        print(f"⚠️ Nie można otworzyć DB: {e}")
        return []
    
    try:
        cutoff = (datetime.now() - timedelta(minutes=stale_minutes)).isoformat()
        rows = con.execute("""
            SELECT session_id, user_id, username, hostname, pid, app_name, 
                   login_at, last_heartbeat, client_info
            FROM active_sessions
            WHERE user_id = ? AND last_heartbeat >= ?
            ORDER BY login_at DESC
        """, (user_id, cutoff)).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError as e:
        try:
            con.close()
        except Exception:
            pass
        # Tabela może nie istnieć (stara baza) - graceful fallback
        if "no such table" in str(e).lower():
            return []
        print(f"⚠️ Błąd pobierania sesji: {e}")
        return []
    except Exception as e:
        try:
            con.close()
        except Exception:
            pass
        print(f"⚠️ Błąd pobierania sesji: {e}")
        return []


def update_session_heartbeat(master_db_path: str, session_id: str) -> bool:
    """
    Odśwież heartbeat sesji (wywołuj co ~30 s).
    
    Cicha funkcja - bez logów dla normalnych przypadków read-only.
    
    Returns:
        bool: True jeśli udało się zaktualizować
    """
    from datetime import datetime
    
    if not session_id:
        return False
    
    try:
        con = _open_rm_connection(master_db_path)
    except Exception:
        return False
    
    try:
        if _is_db_readonly(con):
            con.close()
            return False  # Cicho - to normalna sytuacja w trybie GUEST
        
        con.execute("""
            UPDATE active_sessions
            SET last_heartbeat = ?
            WHERE session_id = ?
        """, (datetime.now().isoformat(), session_id))
        updated = con.total_changes > 0
        _rm_safe_commit(con)
        con.close()
        return updated
    except sqlite3.OperationalError as e:
        try:
            con.close()
        except Exception:
            pass
        if "readonly" in str(e).lower() or "no such table" in str(e).lower():
            return False  # Cicho
        print(f"⚠️ Błąd heartbeat sesji: {e}")
        return False
    except Exception as e:
        try:
            con.close()
        except Exception:
            pass
        print(f"⚠️ Błąd heartbeat sesji: {e}")
        return False


def cleanup_user_session(master_db_path: str, session_id: str):
    """
    Usuń sesję użytkownika (przy wylogowaniu/zamknięciu aplikacji).
    """
    if not session_id:
        return
    
    try:
        con = _open_rm_connection(master_db_path)
    except Exception:
        return
    
    try:
        if _is_db_readonly(con):
            con.close()
            return
        
        con.execute("DELETE FROM active_sessions WHERE session_id = ?", (session_id,))
        _rm_safe_commit(con)
        con.close()
        print(f"🧹 Usunięto sesję: {session_id[:8]}...")
    except sqlite3.OperationalError as e:
        try:
            con.close()
        except Exception:
            pass
        if "readonly" not in str(e).lower() and "no such table" not in str(e).lower():
            print(f"⚠️ Błąd usuwania sesji: {e}")
    except Exception as e:
        try:
            con.close()
        except Exception:
            pass
        print(f"⚠️ Błąd usuwania sesji: {e}")


def cleanup_stale_sessions(master_db_path: str,
                          stale_minutes: int = DEFAULT_STALE_SESSION_MINUTES) -> int:
    """
    Usuń nieaktywne sesje (heartbeat starszy niż stale_minutes).
    
    Returns:
        int: Liczba usuniętych sesji (0 gdy brak/error/readonly)
    """
    from datetime import datetime, timedelta
    
    try:
        con = _open_rm_connection(master_db_path)
    except Exception:
        return 0
    
    try:
        if _is_db_readonly(con):
            con.close()
            return 0
        
        cutoff = (datetime.now() - timedelta(minutes=stale_minutes)).isoformat()
        
        # Pobierz sesje do usunięcia (dla logu)
        to_delete = con.execute("""
            SELECT username, hostname, session_id
            FROM active_sessions
            WHERE last_heartbeat < ?
        """, (cutoff,)).fetchall()
        
        if not to_delete:
            con.close()
            return 0
        
        con.execute("DELETE FROM active_sessions WHERE last_heartbeat < ?", (cutoff,))
        deleted = con.total_changes
        _rm_safe_commit(con)
        con.close()
        
        if deleted > 0:
            print(f"🧹 Usunięto {deleted} nieaktywnych sesji:")
            for row in to_delete:
                print(f"   • {row[0]}@{row[1]} (ID: {row[2][:8]}...)")
        return deleted
    except sqlite3.OperationalError as e:
        try:
            con.close()
        except Exception:
            pass
        if "readonly" not in str(e).lower() and "no such table" not in str(e).lower():
            print(f"⚠️ Błąd cleanup stale sessions: {e}")
        return 0
    except Exception as e:
        try:
            con.close()
        except Exception:
            pass
        print(f"⚠️ Błąd cleanup stale sessions: {e}")
        return 0


def cleanup_hostname_sessions(master_db_path: str, hostname: str) -> int:
    """
    Usuń WSZYSTKIE sesje z danego komputera (przy starcie aplikacji po crashu).
    
    Returns:
        int: Liczba usuniętych sesji
    """
    try:
        con = _open_rm_connection(master_db_path)
    except Exception:
        return 0
    
    try:
        if _is_db_readonly(con):
            con.close()
            return 0
        
        to_delete = con.execute("""
            SELECT username, session_id
            FROM active_sessions
            WHERE hostname = ?
        """, (hostname,)).fetchall()
        
        if not to_delete:
            con.close()
            return 0
        
        con.execute("DELETE FROM active_sessions WHERE hostname = ?", (hostname,))
        deleted = con.total_changes
        _rm_safe_commit(con)
        con.close()
        
        if deleted > 0:
            print(f"🧹 Startup cleanup: usunięto {deleted} osieroconych sesji z {hostname}:")
            for row in to_delete:
                print(f"   • {row[0]} (ID: {row[1][:8]}...)")
        return deleted
    except sqlite3.OperationalError as e:
        try:
            con.close()
        except Exception:
            pass
        if "readonly" not in str(e).lower() and "no such table" not in str(e).lower():
            print(f"⚠️ Błąd cleanup hostname sessions: {e}")
        return 0
    except Exception as e:
        try:
            con.close()
        except Exception:
            pass
        print(f"⚠️ Błąd cleanup hostname sessions: {e}")
        return 0


def update_stage_definitions(master_db_path: str):
    """Aktualizuje definicje etapów w rm_manager.sqlite - dodaje brakujące.
    
    Przydatne po dodaniu nowych etapów do STAGE_DEFINITIONS w kodzie.
    Używa INSERT OR IGNORE - bezpieczne dla istniejących danych.
    
    Returns:
        int: Liczba dodanych etapów
    """
    con = _open_rm_connection(master_db_path)
    
    # Upewnij się, że tabela istnieje
    con.execute("""
        CREATE TABLE IF NOT EXISTS stage_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            display_name TEXT,
            color TEXT,
            is_milestone INTEGER DEFAULT 0
        )
    """)
    
    # Dodaj kolumnę is_milestone jeśli nie istnieje (dla starych baz)
    try:
        con.execute("ALTER TABLE stage_definitions ADD COLUMN is_milestone INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Kolumna już istnieje
    
    # Sprawdź które etapy już istnieją
    existing = {row['code'] for row in con.execute("SELECT code FROM stage_definitions")}
    
    added = 0
    updated = 0
    for code, display_name, color, is_milestone in STAGE_DEFINITIONS:
        if code not in existing:
            con.execute("""
                INSERT INTO stage_definitions (code, display_name, color, is_milestone)
                VALUES (?, ?, ?, ?)
            """, (code, display_name, color, is_milestone))
            added += 1
            print(f"  ➕ Dodano etap: {code} ({display_name})")
        else:
            # Aktualizuj display_name, color i is_milestone dla istniejących etapów
            con.execute("""
                UPDATE stage_definitions
                SET display_name = ?, color = ?, is_milestone = ?
                WHERE code = ?
            """, (display_name, color, is_milestone, code))
            updated += 1
            print(f"  🔄 Zaktualizowano etap: {code} ({display_name})")
    
    con.commit()
    con.close()
    
    if added > 0 or updated > 0:
        print(f"✅ Zaktualizowano definicje etapów: +{added} nowych, ~{updated} zaktualizowanych")
    else:
        print("✅ Definicje etapów aktualne - brak zmian")
    
    return added


def _migrate_assigned_staff_json_to_table(con: sqlite3.Connection):
    """Migracja: przenieś dane z JSON project_stages.assigned_staff → stage_staff_assignments.
    
    Wywoływane z ensure_project_tables(). Bezpieczne — nie nadpisuje istniejących wpisów.
    Używa planned_start/planned_end z stage_schedule (template dates).
    """
    import json

    # Sprawdź czy tabela docelowa istnieje (powinna — wywołane po CREATE TABLE)
    try:
        con.execute("SELECT 1 FROM stage_staff_assignments LIMIT 1")
    except sqlite3.OperationalError:
        return  # Tabela jeszcze nie istnieje

    # Pobierz etapy z JSON assigned_staff
    rows = con.execute("""
        SELECT ps.id AS ps_id, ps.stage_code, ps.assigned_staff,
               ss.template_start, ss.template_end
        FROM project_stages ps
        LEFT JOIN stage_schedule ss ON ss.project_stage_id = ps.id
        WHERE ps.assigned_staff IS NOT NULL AND ps.assigned_staff != '' AND ps.assigned_staff != '[]'
    """).fetchall()

    migrated = 0
    for row in rows:
        try:
            staff_list = json.loads(row['assigned_staff'])
        except (json.JSONDecodeError, TypeError):
            continue

        for staff in staff_list:
            if not isinstance(staff, dict):
                continue
            emp_id = staff.get('employee_id')
            if not emp_id:
                continue

            # Sprawdź czy już nie istnieje w nowej tabeli
            exists = con.execute("""
                SELECT 1 FROM stage_staff_assignments
                WHERE project_stage_id = ? AND employee_id = ?
            """, (row['ps_id'], emp_id)).fetchone()

            if exists:
                continue

            try:
                con.execute("""
                    INSERT INTO stage_staff_assignments
                        (project_stage_id, employee_id, planned_start, planned_end,
                         assigned_at, assigned_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    row['ps_id'],
                    emp_id,
                    row['template_start'],   # planned_start = template_start etapu
                    row['template_end'],     # planned_end = template_end etapu
                    staff.get('assigned_at'),
                    staff.get('assigned_by'),
                ))
                migrated += 1
            except sqlite3.IntegrityError:
                pass  # duplikat — pomijamy

    if migrated > 0:
        print(f"    ↳ Migracja: przeniesiono {migrated} przypisań pracowników do stage_staff_assignments")


def ensure_project_tables(project_db_path: str):
    """Tworzy tabele w rm_manager_project_X.sqlite (PER-PROJEKT):
    - stage_definitions  (kopia – dla niezależności JOINów w jednej bazie)
    - project_stages
    - stage_schedule
    - stage_actual_periods
    - stage_dependencies
    - stage_events
    """
    Path(project_db_path).parent.mkdir(parents=True, exist_ok=True)
    con = _open_rm_connection(project_db_path)

    # Kopia stage_definitions (żeby JOIN działał bez ATTACH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS stage_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            display_name TEXT,
            color TEXT,
            is_milestone INTEGER DEFAULT 0
        )
    """)
    
    # Dodaj kolumnę is_milestone jeśli nie istnieje (dla starych baz)
    try:
        con.execute("ALTER TABLE stage_definitions ADD COLUMN is_milestone INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Kolumna już istnieje
    
    count = con.execute("SELECT COUNT(*) FROM stage_definitions").fetchone()[0]
    if count == 0:
        con.executemany("""
            INSERT INTO stage_definitions (code, display_name, color, is_milestone) VALUES (?, ?, ?, ?)
        """, STAGE_DEFINITIONS)
    else:
        # Aktualizuj istniejące + DODAJ brakujące etapy
        for code, display_name, color, is_milestone in STAGE_DEFINITIONS:
            existing = con.execute("SELECT id FROM stage_definitions WHERE code = ?", (code,)).fetchone()
            if existing:
                con.execute("""
                    UPDATE stage_definitions 
                    SET is_milestone = ?, display_name = ?, color = ?
                    WHERE code = ?
                """, (is_milestone, display_name, color, code))
            else:
                con.execute("""
                    INSERT INTO stage_definitions (code, display_name, color, is_milestone)
                    VALUES (?, ?, ?, ?)
                """, (code, display_name, color, is_milestone))

    # project_stages
    con.execute("""
        CREATE TABLE IF NOT EXISTS project_stages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            stage_code TEXT NOT NULL,
            sequence INTEGER,
            assigned_staff TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id, stage_code)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_project_stages_project ON project_stages(project_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_project_stages_code ON project_stages(stage_code)")
    
    # Dodaj kolumnę assigned_staff jeśli nie istnieje (dla starych baz)
    try:
        con.execute("ALTER TABLE project_stages ADD COLUMN assigned_staff TEXT")
    except sqlite3.OperationalError:
        pass  # Kolumna już istnieje

    # stage_schedule
    con.execute("""
        CREATE TABLE IF NOT EXISTS stage_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_stage_id INTEGER NOT NULL,
            template_start DATE,
            template_end DATE,
            notes TEXT,
            transport_id INTEGER,
            employee_id INTEGER,
            FOREIGN KEY (project_stage_id) REFERENCES project_stages(id) ON DELETE CASCADE
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_stage_schedule_stage ON stage_schedule(project_stage_id)")

    # Migracja: dodaj transport_id jeśli nie istnieje (istniejące bazy)
    try:
        con.execute("ALTER TABLE stage_schedule ADD COLUMN transport_id INTEGER")
    except sqlite3.OperationalError:
        pass  # kolumna już istnieje
    
    # Migracja: dodaj employee_id jeśli nie istnieje (istniejące bazy)
    try:
        con.execute("ALTER TABLE stage_schedule ADD COLUMN employee_id INTEGER")
    except sqlite3.OperationalError:
        pass  # kolumna już istnieje

    # stage_actual_periods
    con.execute("""
        CREATE TABLE IF NOT EXISTS stage_actual_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_stage_id INTEGER NOT NULL,
            started_at DATETIME NOT NULL,
            ended_at DATETIME,
            started_by TEXT,
            ended_by TEXT,
            notes TEXT,
            assigned_staff TEXT,
            FOREIGN KEY (project_stage_id) REFERENCES project_stages(id) ON DELETE CASCADE
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_actual_periods_stage ON stage_actual_periods(project_stage_id, started_at)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_actual_periods_active ON stage_actual_periods(project_stage_id, ended_at)")
    
    # Dodaj kolumnę assigned_staff jeśli nie istnieje (dla starych baz)
    try:
        con.execute("ALTER TABLE stage_actual_periods ADD COLUMN assigned_staff TEXT")
    except sqlite3.OperationalError:
        pass  # Kolumna już istnieje

    # stage_dependencies
    con.execute("""
        CREATE TABLE IF NOT EXISTS stage_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            predecessor_stage_code TEXT NOT NULL,
            successor_stage_code TEXT NOT NULL,
            dependency_type TEXT NOT NULL,
            lag_days INTEGER DEFAULT 0,
            CHECK (dependency_type IN ('FS', 'SS'))
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_dependencies_project ON stage_dependencies(project_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_dependencies_pred ON stage_dependencies(predecessor_stage_code)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_dependencies_succ ON stage_dependencies(successor_stage_code)")
    
    # UNIQUE constraint na kombinację project_id + predecessor + successor + type
    # Najpierw deduplikacja istniejących wpisów, potem tworzenie indeksu
    try:
        con.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_dependencies_unique 
            ON stage_dependencies(project_id, predecessor_stage_code, successor_stage_code, dependency_type)
        """)
    except sqlite3.IntegrityError:
        # Duplikaty istnieją — usuwamy je, potem tworzymy indeks
        try:
            con.execute("""
                DELETE FROM stage_dependencies
                WHERE id NOT IN (
                    SELECT MIN(id) FROM stage_dependencies
                    GROUP BY project_id, predecessor_stage_code, successor_stage_code, dependency_type
                )
            """)
            con.commit()
            con.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_dependencies_unique 
                ON stage_dependencies(project_id, predecessor_stage_code, successor_stage_code, dependency_type)
            """)
            print("✅ Deduplikacja stage_dependencies + UNIQUE index utworzony")
        except Exception as e:
            print(f"⚠️  Nie udało się deduplikować stage_dependencies: {e}")

    # project_events - eventy projektu (PRZYJĘTY, ZAKOŃCZONY, WSTRZYMANY, WZNOWIONY)
    con.execute("""
        CREATE TABLE IF NOT EXISTS project_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            user TEXT,
            notes TEXT,
            CHECK (event_type IN ('PRZYJETY', 'ZAKONCZONY', 'WSTRZYMANY', 'WZNOWIONY'))
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_project_events_project ON project_events(project_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_project_events_type ON project_events(event_type)")
    # UNIQUE constraint dla jednorazowych eventów
    con.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_project_events_unique 
        ON project_events(project_id, event_type) 
        WHERE event_type IN ('PRZYJETY', 'ZAKONCZONY')
    """)

    # 🚀 project_pauses - NOWA ARCHITEKTURA: pauzy jako overlay na etapach!
    # 📚 KONCEPCJA: WSTRZYMANY nie jest etapem - to pauza nałożona na aktywne etapy
    con.execute("""
        CREATE TABLE IF NOT EXISTS project_pauses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            start_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            end_at DATETIME,  -- NULL = aktywna pauza
            reason TEXT,
            user TEXT,
            notes TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_project_pauses_project ON project_pauses(project_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_project_pauses_active ON project_pauses(project_id, end_at)")
    # UNIQUE constraint dla aktywnej pauzy (tylko jedna na raz)
    con.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_project_pauses_active_unique
        ON project_pauses(project_id) 
        WHERE end_at IS NULL
    """)

    # stage_events
    con.execute("""
        CREATE TABLE IF NOT EXISTS stage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_stage_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            event_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            description TEXT,
            created_by TEXT,
            FOREIGN KEY (project_stage_id) REFERENCES project_stages(id) ON DELETE CASCADE
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_stage_events_stage ON stage_events(project_stage_id)")

    # ============================================================================
    # SYSTEM NOTATEK - tematy, notatki, alarmy
    # ============================================================================
    
    # stage_topics - tematy notatek dla etapów
    con.execute("""
        CREATE TABLE IF NOT EXISTS stage_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            stage_code TEXT NOT NULL,
            topic_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            priority TEXT DEFAULT 'MEDIUM',
            color TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            CHECK (priority IN ('HIGH', 'MEDIUM', 'LOW')),
            UNIQUE(project_id, stage_code, topic_number)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_stage_topics_project_stage ON stage_topics(project_id, stage_code)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_stage_topics_priority ON stage_topics(priority)")
    
    # stage_notes - notatki w ramach tematów
    con.execute("""
        CREATE TABLE IF NOT EXISTS stage_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            note_text TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            FOREIGN KEY (topic_id) REFERENCES stage_topics(id) ON DELETE CASCADE
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_stage_notes_topic ON stage_notes(topic_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_stage_notes_created ON stage_notes(created_at)")
    # Migracja: dodaj sort_order jeśli nie istnieje (istniejące bazy)
    try:
        con.execute("ALTER TABLE stage_notes ADD COLUMN sort_order INTEGER DEFAULT 0")
        # Ustaw sort_order = id dla istniejących rekordów
        con.execute("UPDATE stage_notes SET sort_order = id WHERE sort_order = 0 OR sort_order IS NULL")
        con.commit()
    except Exception:
        pass  # kolumna już istnieje
    
    # stage_note_attachments - załączniki do notatek (JPG, PDF, CSV, XLSX, etc.)
    con.execute("""
        CREATE TABLE IF NOT EXISTS stage_note_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_data BLOB NOT NULL,
            file_size INTEGER NOT NULL,
            mime_type TEXT,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            uploaded_by TEXT,
            FOREIGN KEY (note_id) REFERENCES stage_notes(id) ON DELETE CASCADE
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_note_attachments_note ON stage_note_attachments(note_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_note_attachments_uploaded ON stage_note_attachments(uploaded_at)")
    
    # stage_attachments - załączniki bezpośrednio do etapów (Karta maszyny, Protokoły)
    con.execute("""
        CREATE TABLE IF NOT EXISTS stage_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_stage_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_data BLOB NOT NULL,
            file_size INTEGER NOT NULL,
            mime_type TEXT,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            uploaded_by TEXT,
            FOREIGN KEY (project_stage_id) REFERENCES project_stages(id) ON DELETE CASCADE
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_stage_attachments_stage ON stage_attachments(project_stage_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_stage_attachments_uploaded ON stage_attachments(uploaded_at)")
    
    # stage_alarms - system powiadomień
    con.execute("""
        CREATE TABLE IF NOT EXISTS stage_alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            alarm_datetime DATETIME NOT NULL,
            message TEXT,
            assigned_to TEXT DEFAULT 'ALL',
            is_active INTEGER DEFAULT 1,
            acknowledged_at DATETIME,
            acknowledged_by TEXT,
            snoozed_until DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            CHECK (target_type IN ('TOPIC', 'NOTE'))
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_stage_alarms_target ON stage_alarms(target_type, target_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_stage_alarms_datetime ON stage_alarms(alarm_datetime)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_stage_alarms_active ON stage_alarms(is_active, alarm_datetime)")
    # Migracja: dodaj kolumny assigned_to i snoozed_until jeśli nie istnieją
    try:
        con.execute("ALTER TABLE stage_alarms ADD COLUMN assigned_to TEXT DEFAULT 'ALL'")
        con.commit()
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE stage_alarms ADD COLUMN snoozed_until DATETIME")
        con.commit()
    except Exception:
        pass

    # ============================================================================
    # STAGE STAFF ASSIGNMENTS — przypisania pracowników z datami (2026-04-19)
    # ============================================================================
    # Zastępuje JSON w project_stages.assigned_staff
    # Pracownik przypisany na czas aktywności (planned_start..planned_end)
    con.execute("""
        CREATE TABLE IF NOT EXISTS stage_staff_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_stage_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            planned_start DATE,
            planned_end DATE,
            actual_start DATETIME,
            actual_end DATETIME,
            role TEXT,
            assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            assigned_by TEXT,
            FOREIGN KEY (project_stage_id) REFERENCES project_stages(id) ON DELETE CASCADE,
            UNIQUE(project_stage_id, employee_id)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_ssa_stage ON stage_staff_assignments(project_stage_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_ssa_employee ON stage_staff_assignments(employee_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_ssa_dates ON stage_staff_assignments(planned_start, planned_end)")

    # Migracja: przenieś istniejące dane z JSON assigned_staff → nowa tabela
    _migrate_assigned_staff_json_to_table(con)

    con.commit()
    con.close()
    print(f"✅ RM_MANAGER per-projekt baza zainicjalizowana: {project_db_path}")


def update_project_stage_definitions(project_db_path: str):
    """Aktualizuje definicje etapów w per-project bazie - dodaje brakujące.
    
    Używane po dodaniu nowych etapów do STAGE_DEFINITIONS w kodzie.
    Bezpieczne: INSERT OR IGNORE.
    
    Returns:
        int: Liczba dodanych etapów
    """
    con = _open_rm_connection(project_db_path)
    
    # Upewnij się, że tabela istnieje
    con.execute("""
        CREATE TABLE IF NOT EXISTS stage_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            display_name TEXT,
            color TEXT,
            is_milestone INTEGER DEFAULT 0
        )
    """)
    
    # Dodaj kolumnę is_milestone jeśli nie istnieje (dla starych baz)
    try:
        con.execute("ALTER TABLE stage_definitions ADD COLUMN is_milestone INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Kolumna już istnieje
    
    # Sprawdź które etapy już istnieją
    existing = {row['code'] for row in con.execute("SELECT code FROM stage_definitions")}
    
    added = 0
    updated = 0
    for code, display_name, color, is_milestone in STAGE_DEFINITIONS:
        if code not in existing:
            con.execute("""
                INSERT INTO stage_definitions (code, display_name, color, is_milestone)
                VALUES (?, ?, ?, ?)
            """, (code, display_name, color, is_milestone))
            added += 1
        else:
            # Aktualizuj display_name, color i is_milestone dla istniejących etapów
            con.execute("""
                UPDATE stage_definitions
                SET display_name = ?, color = ?, is_milestone = ?
                WHERE code = ?
            """, (display_name, color, is_milestone, code))
            updated += 1
    
    con.commit()
    con.close()
    
    return added + updated


# ============================================================================
# DEPRECATED: Usunięte - błędna architektura (wszystko w jednej bazie)
# ============================================================================
# def ensure_rm_manager_tables(rm_db_path: str):
#     """🚫 DEPRECATED - używaj ensure_project_tables() dla każdego projektu osobno!
#     
#     Stara funkcja tworzyła wszystkie tabele projektowe w jednej centralnej bazie,
#     co powodowało problemy z lockami (użytkownicy blokowali się nawzajem).
#     
#     ✅ POPRAWNA ARCHITEKTURA:
#     - rm_manager.sqlite            ← master (stage_definitions, employees, tracking)
#     - rm_manager_project_1.sqlite  ← projekt 1 (project_stages, periods, etc.)
#     - rm_manager_project_2.sqlite  ← projekt 2 (project_stages, periods, etc.)
#     - ...
#     
#     Użyj:
#     - ensure_rm_master_tables() dla rm_manager.sqlite
#     - ensure_project_tables() dla każdego rm_manager_project_X.sqlite
#     """
#     raise NotImplementedError(
#         "🚫 ensure_rm_manager_tables() jest DEPRECATED!\n\n"
#         "Użyj zamiast tego:\n"
#         "  - ensure_rm_master_tables(master_path)  # dla rm_manager.sqlite\n"
#         "  - ensure_project_tables(project_path)   # dla rm_manager_project_X.sqlite\n\n"
#         "Powód: Per-projekt bazy zapewniają izolację i działanie locków."
#     )


# ============================================================================
# MIGRACJA: Centralna baza → Per-projekt bazy
# ============================================================================

def migrate_central_to_per_project(rm_manager_dir: str, rm_master_db_path: str = None) -> Dict:
    """Migruje dane z centralnej rm_manager.sqlite do per-projekt baz.
    
    STARA ARCHITEKTURA (centralna):
        rm_manager.sqlite zawiera project_stages, stage_actual_periods, 
        stage_schedule, stage_dependencies, stage_events, project_events, 
        project_pauses dla WSZYSTKICH projektów.
    
    NOWA ARCHITEKTURA (per-projekt):
        rm_manager_project_{id}.sqlite - osobna baza per projekt
        rm_manager.sqlite - tylko master (employees, permissions, tracking)
    
    Args:
        rm_manager_dir: Katalog RM_MANAGER (np. Y:/RM_MANAGER/rm_manager/)
        rm_master_db_path: Ścieżka do rm_manager.sqlite (domyślnie: rm_manager_dir/rm_manager.sqlite)
    
    Returns:
        Dict z podsumowaniem:
        {
            'projects_migrated': int,
            'projects_skipped': int,
            'errors': list,
            'details': {project_id: {'stages': N, 'periods': N, ...}}
        }
    """
    if rm_master_db_path is None:
        rm_master_db_path = os.path.join(rm_manager_dir, 'rm_manager.sqlite')
    
    if not os.path.exists(rm_master_db_path):
        return {
            'projects_migrated': 0,
            'projects_skipped': 0,
            'errors': ['Brak pliku rm_manager.sqlite'],
            'details': {}
        }
    
    result = {
        'projects_migrated': 0,
        'projects_skipped': 0,
        'errors': [],
        'details': {}
    }
    
    con = _open_rm_connection(rm_master_db_path)
    
    # Sprawdź czy centralna baza ma tabele projektowe (stara architektura)
    tables = [row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    
    if 'project_stages' not in tables:
        con.close()
        return {
            'projects_migrated': 0,
            'projects_skipped': 0,
            'errors': ['Brak tabeli project_stages w centralnej bazie - nic do migracji.'],
            'details': {}
        }
    
    # Pobierz unikalne project_id z centralnej bazy
    try:
        project_ids = [row['project_id'] for row in con.execute(
            "SELECT DISTINCT project_id FROM project_stages ORDER BY project_id"
        ).fetchall()]
    except Exception as e:
        con.close()
        return {
            'projects_migrated': 0,
            'projects_skipped': 0,
            'errors': [f'Błąd odczytu project_stages: {e}'],
            'details': {}
        }
    
    if not project_ids:
        con.close()
        return {
            'projects_migrated': 0,
            'projects_skipped': 0,
            'errors': ['Brak projektów w centralnej bazie.'],
            'details': {}
        }
    
    print(f"📦 Znaleziono {len(project_ids)} projektów do migracji: {project_ids}")
    
    for project_id in project_ids:
        project_db_path = get_project_db_path(rm_manager_dir, project_id)
        
        # Sprawdź czy per-projekt baza już istnieje I ma dane
        if os.path.exists(project_db_path):
            try:
                pcon = _open_rm_connection(project_db_path)
                count = pcon.execute(
                    "SELECT COUNT(*) FROM project_stages WHERE project_id = ?",
                    (project_id,)
                ).fetchone()[0]
                pcon.close()
                
                if count > 0:
                    print(f"   ⏭️  Projekt {project_id}: per-projekt baza już istnieje ({count} etapów) - POMIJAM")
                    result['projects_skipped'] += 1
                    continue
            except Exception:
                pass  # Baza uszkodzona lub nie ma tabel - migrujemy
        
        # Inicjalizuj per-projekt bazę (tabele)
        ensure_project_tables(project_db_path)
        
        detail = {'stages': 0, 'periods': 0, 'schedules': 0, 'dependencies': 0, 
                  'events': 0, 'project_events': 0, 'pauses': 0}
        
        try:
            pcon = _open_rm_connection(project_db_path)
            
            # --- 1. project_stages ---
            stages = con.execute("""
                SELECT * FROM project_stages WHERE project_id = ?
            """, (project_id,)).fetchall()
            
            old_to_new_stage_id = {}  # mapping starego ID → nowego ID
            
            for s in stages:
                # Sprawdź kolumny dostępne w starej bazie
                assigned_staff = None
                try:
                    assigned_staff = s['assigned_staff']
                except (IndexError, KeyError):
                    pass
                
                pcon.execute("""
                    INSERT OR IGNORE INTO project_stages 
                    (project_id, stage_code, sequence, assigned_staff)
                    VALUES (?, ?, ?, ?)
                """, (s['project_id'], s['stage_code'], s['sequence'], assigned_staff))
                
                # Pobierz nowe ID
                new_row = pcon.execute("""
                    SELECT id FROM project_stages 
                    WHERE project_id = ? AND stage_code = ?
                """, (project_id, s['stage_code'])).fetchone()
                
                if new_row:
                    old_to_new_stage_id[s['id']] = new_row['id']
                    detail['stages'] += 1
            
            # --- 2. stage_schedule ---
            if 'stage_schedule' in tables:
                for old_id, new_id in old_to_new_stage_id.items():
                    schedules = con.execute("""
                        SELECT * FROM stage_schedule WHERE project_stage_id = ?
                    """, (old_id,)).fetchall()
                    
                    for sch in schedules:
                        pcon.execute("""
                            INSERT OR REPLACE INTO stage_schedule 
                            (project_stage_id, template_start, template_end, notes)
                            VALUES (?, ?, ?, ?)
                        """, (new_id, sch['template_start'], sch['template_end'], sch['notes']))
                        detail['schedules'] += 1
            
            # --- 3. stage_actual_periods ---
            if 'stage_actual_periods' in tables:
                for old_id, new_id in old_to_new_stage_id.items():
                    periods = con.execute("""
                        SELECT * FROM stage_actual_periods WHERE project_stage_id = ?
                    """, (old_id,)).fetchall()
                    
                    for p in periods:
                        assigned_staff = None
                        try:
                            assigned_staff = p['assigned_staff']
                        except (IndexError, KeyError):
                            pass
                        
                        pcon.execute("""
                            INSERT INTO stage_actual_periods 
                            (project_stage_id, started_at, ended_at, started_by, ended_by, notes, assigned_staff)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (new_id, p['started_at'], p['ended_at'], 
                              p['started_by'], p['ended_by'], p['notes'], assigned_staff))
                        detail['periods'] += 1
            
            # --- 4. stage_dependencies ---
            if 'stage_dependencies' in tables:
                deps = con.execute("""
                    SELECT * FROM stage_dependencies WHERE project_id = ?
                """, (project_id,)).fetchall()
                
                for d in deps:
                    pcon.execute("""
                        INSERT OR IGNORE INTO stage_dependencies 
                        (project_id, predecessor_stage_code, successor_stage_code, 
                         dependency_type, lag_days)
                        VALUES (?, ?, ?, ?, ?)
                    """, (project_id, d['predecessor_stage_code'], d['successor_stage_code'],
                          d['dependency_type'], d['lag_days']))
                    detail['dependencies'] += 1
            
            # --- 5. stage_events ---
            if 'stage_events' in tables:
                for old_id, new_id in old_to_new_stage_id.items():
                    events = con.execute("""
                        SELECT * FROM stage_events WHERE project_stage_id = ?
                    """, (old_id,)).fetchall()
                    
                    for ev in events:
                        pcon.execute("""
                            INSERT INTO stage_events 
                            (project_stage_id, event_type, event_date, description, created_by)
                            VALUES (?, ?, ?, ?, ?)
                        """, (new_id, ev['event_type'], ev['event_date'], 
                              ev['description'], ev['created_by']))
                        detail['events'] += 1
            
            # --- 6. project_events ---
            if 'project_events' in tables:
                p_events = con.execute("""
                    SELECT * FROM project_events WHERE project_id = ?
                """, (project_id,)).fetchall()
                
                for pe in p_events:
                    pcon.execute("""
                        INSERT OR IGNORE INTO project_events 
                        (project_id, event_type, timestamp, user, notes)
                        VALUES (?, ?, ?, ?, ?)
                    """, (project_id, pe['event_type'], pe['timestamp'], 
                          pe['user'], pe['notes']))
                    detail['project_events'] += 1
            
            # --- 7. project_pauses ---
            if 'project_pauses' in tables:
                pauses = con.execute("""
                    SELECT * FROM project_pauses WHERE project_id = ?
                """, (project_id,)).fetchall()
                
                for pa in pauses:
                    pcon.execute("""
                        INSERT INTO project_pauses 
                        (project_id, start_at, end_at, reason, user, notes)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (project_id, pa['start_at'], pa['end_at'], 
                          pa['reason'], pa['user'], pa['notes']))
                    detail['pauses'] += 1
            
            pcon.commit()
            pcon.close()
            
            result['projects_migrated'] += 1
            result['details'][project_id] = detail
            
            total_records = sum(detail.values())
            print(f"   ✅ Projekt {project_id}: {total_records} rekordów "
                  f"({detail['stages']} etapów, {detail['periods']} okresów, "
                  f"{detail['schedules']} szablonów, {detail['dependencies']} zależności)")
        
        except Exception as e:
            result['errors'].append(f"Projekt {project_id}: {e}")
            print(f"   ❌ Projekt {project_id}: BŁĄD - {e}")
    
    con.close()
    
    print(f"\n📊 PODSUMOWANIE MIGRACJI:")
    print(f"   ✅ Zmigrowano: {result['projects_migrated']} projektów")
    print(f"   ⏭️  Pominięto: {result['projects_skipped']} projektów (już istnieją)")
    if result['errors']:
        print(f"   ❌ Błędy: {len(result['errors'])}")
        for err in result['errors']:
            print(f"      - {err}")
    
    return result


def cleanup_central_project_tables(rm_master_db_path: str, dry_run: bool = True) -> Dict:
    """Usuwa tabele projektowe z centralnej rm_manager.sqlite.
    
    Tabele projektowe (project_stages, stage_actual_periods, itp.) powinny
    być TYLKO w per-projekt bazach (rm_manager_project_X.sqlite).
    Ich obecność w centralnej bazie to relikt starej architektury.
    
    Args:
        rm_master_db_path: Ścieżka do rm_manager.sqlite
        dry_run: True = tylko pokaż co by usunął, False = usuwaj
    
    Returns:
        Dict z listą usuniętych tabel i statystykami
    """
    con = _open_rm_connection(rm_master_db_path)
    
    # Tabele projektowe które powinny być TYLKO w per-projekt bazach
    project_tables = [
        'project_stages', 'stage_schedule', 'stage_actual_periods',
        'stage_dependencies', 'stage_events', 'project_events', 'project_pauses'
    ]
    
    existing = [row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    
    tables_to_remove = [t for t in project_tables if t in existing]
    
    # Zbierz statystyki (ile rekordów w każdej tabeli)
    table_stats = {}
    for table in tables_to_remove:
        try:
            count = con.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            table_stats[table] = count
        except Exception:
            table_stats[table] = '?'
    
    result = {
        'tables_found': tables_to_remove,
        'table_stats': table_stats,
        'tables_removed': [],
        'dry_run': dry_run
    }
    
    if dry_run:
        print(f"🔍 DRY RUN - tabele do usunięcia z centralnej bazy:")
        for t in tables_to_remove:
            print(f"   • {t}: {table_stats.get(t, '?')} rekordów")
    else:
        for table in tables_to_remove:
            con.execute(f"DROP TABLE IF EXISTS [{table}]")
            result['tables_removed'].append(table)
            print(f"   🗑️  Usunięto tabelę: {table} ({table_stats.get(table, '?')} rekordów)")
        con.execute("VACUUM")
        con.commit()
        print(f"✅ Usunięto {len(result['tables_removed'])} tabel projektowych z centralnej bazy")
    
    con.close()
    return result


def migrate_notes_system_to_projects(rm_projects_dir: str) -> Dict:
    """Migracja: dodaj tabele systemu notatek do istniejących per-projekt baz.
    
    Dodaje tabele stage_topics, stage_notes, stage_alarms do wszystkich
    istniejących per-projekt baz które ich nie mają.
    
    Args:
        rm_projects_dir: Katalog z per-projekt bazami (np. Y:/RM_MANAGER/RM_MANAGER_projects/)
    
    Returns:
        Dict z podsumowaniem:
        {
            'projects_updated': int,
            'projects_skipped': int,
            'errors': list,
            'details': {project_id: 'status'}
        }
    """
    result = {
        'projects_updated': 0,
        'projects_skipped': 0,
        'errors': [],
        'details': {}
    }
    
    if not os.path.exists(rm_projects_dir):
        result['errors'].append(f"Katalog nie istnieje: {rm_projects_dir}")
        return result
    
    # Znajdź wszystkie per-projekt bazy
    pattern = os.path.join(rm_projects_dir, "rm_manager_project_*.sqlite")
    project_dbs = glob.glob(pattern)
    
    if not project_dbs:
        result['errors'].append(f"Nie znaleziono żadnych projektów w: {rm_projects_dir}")
        return result
    
    print(f"📝 Znaleziono {len(project_dbs)} projektów do aktualizacji")
    
    for project_db_path in sorted(project_dbs):
        # Wyciągnij project_id z nazwy pliku
        basename = os.path.basename(project_db_path)
        try:
            project_id = int(basename.replace('rm_manager_project_', '').replace('.sqlite', ''))
        except ValueError:
            result['errors'].append(f"Nie można wyciągnąć project_id z: {basename}")
            continue
        
        try:
            con = _open_rm_connection(project_db_path)
            
            # Sprawdź czy tabele notatek już istnieją
            existing_tables = [row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            
            notes_tables = ['stage_topics', 'stage_notes', 'stage_alarms']
            has_all_tables = all(t in existing_tables for t in notes_tables)
            
            if has_all_tables:
                # Sprawdź czy stage_topics ma wszystkie kolumny
                columns = [row[1] for row in con.execute("PRAGMA table_info(stage_topics)")]
                required_columns = ['id', 'project_id', 'stage_code', 'topic_number', 'title', 
                                   'priority', 'color', 'created_at', 'updated_at', 'created_by']
                
                if all(col in columns for col in required_columns):
                    con.close()
                    result['projects_skipped'] += 1
                    result['details'][project_id] = 'already_has_notes_tables'
                    print(f"   ✅ Projekt {project_id}: tabele notatek już istnieją - POMIJAM")
                    continue
            
            # Dodaj tabele notatek
            print(f"   🔧 Projekt {project_id}: dodawanie tabel notatek...")
            
            # stage_topics
            con.execute("""
                CREATE TABLE IF NOT EXISTS stage_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    stage_code TEXT NOT NULL,
                    topic_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    priority TEXT DEFAULT 'MEDIUM',
                    color TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT,
                    CHECK (priority IN ('HIGH', 'MEDIUM', 'LOW')),
                    UNIQUE(project_id, stage_code, topic_number)
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_stage_topics_project_stage ON stage_topics(project_id, stage_code)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_stage_topics_priority ON stage_topics(priority)")
            
            # stage_notes
            con.execute("""
                CREATE TABLE IF NOT EXISTS stage_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id INTEGER NOT NULL,
                    note_text TEXT NOT NULL,
                    sort_order INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT,
                    FOREIGN KEY (topic_id) REFERENCES stage_topics(id) ON DELETE CASCADE
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_stage_notes_topic ON stage_notes(topic_id)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_stage_notes_created ON stage_notes(created_at)")
            # Migracja sort_order
            try:
                con.execute("ALTER TABLE stage_notes ADD COLUMN sort_order INTEGER DEFAULT 0")
                con.execute("UPDATE stage_notes SET sort_order = id WHERE sort_order = 0 OR sort_order IS NULL")
                con.commit()
            except Exception:
                pass
            
            # stage_alarms
            con.execute("""
                CREATE TABLE IF NOT EXISTS stage_alarms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id INTEGER NOT NULL,
                    alarm_datetime DATETIME NOT NULL,
                    message TEXT,
                    assigned_to TEXT DEFAULT 'ALL',
                    is_active INTEGER DEFAULT 1,
                    acknowledged_at DATETIME,
                    acknowledged_by TEXT,
                    snoozed_until DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT,
                    CHECK (target_type IN ('TOPIC', 'NOTE'))
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_stage_alarms_target ON stage_alarms(target_type, target_id)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_stage_alarms_datetime ON stage_alarms(alarm_datetime)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_stage_alarms_active ON stage_alarms(is_active, alarm_datetime)")
            # Migracja: dodaj kolumny assigned_to i snoozed_until jeśli nie istnieją
            try:
                con.execute("ALTER TABLE stage_alarms ADD COLUMN assigned_to TEXT DEFAULT 'ALL'")
                con.commit()
            except Exception:
                pass
            try:
                con.execute("ALTER TABLE stage_alarms ADD COLUMN snoozed_until DATETIME")
                con.commit()
            except Exception:
                pass
            
            con.commit()
            con.close()
            
            result['projects_updated'] += 1
            result['details'][project_id] = 'updated'
            print(f"   ✅ Projekt {project_id}: zaktualizowano")
            
        except Exception as e:
            error_msg = f"Projekt {project_id}: {str(e)}"
            result['errors'].append(error_msg)
            result['details'][project_id] = f'error: {str(e)}'
            print(f"   ❌ {error_msg}")
            continue
    
    print(f"\n✅ Migr acja zakończona:")
    print(f"   • Zaktualizowano: {result['projects_updated']} projektów")
    print(f"   • Pominięto: {result['projects_skipped']} projektów")
    print(f"   • Błędy: {len(result['errors'])}")
    
    return result


# ============================================================================
# File Integrity Tracking (śledzenie integralności plików RM_BAZA)
# ============================================================================

def get_file_birth_time(filepath: str) -> float:
    """Pobiera czas utworzenia pliku (creation time)
    
    Returns:
        float: Timestamp utworzenia pliku
    """
    import os
    import platform
    
    if not os.path.exists(filepath):
        return 0.0
    
    stat_info = os.stat(filepath)
    
    # Windows: st_ctime to creation time
    # Linux/Unix: st_ctime to change time, więc używamy st_mtime jako fallback
    if platform.system() == 'Windows':
        return stat_info.st_ctime
    else:
        # Na Linux najlepiej użyć st_birthtime jeśli dostępne (macOS), inaczej st_mtime
        return getattr(stat_info, 'st_birthtime', stat_info.st_mtime)


def register_project_file(rm_db_path: str, project_id: int, project_name: str, master_db_path: str, projects_path: str = None):
    """Rejestruje plik projektu przy pierwszym dostępie (lazy init)
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite
        project_id: ID projektu
        project_name: Nazwa projektu
        master_db_path: Ścieżka do master.sqlite (RM_BAZA)
        projects_path: Folder projektów (jeśli None - używa katalogu master.sqlite)
    """
    import os
    
    # Konstruuj ścieżkę: {projects_path}/project_{id}.sqlite
    base_dir = projects_path if projects_path else os.path.dirname(master_db_path)
    file_path = os.path.join(base_dir, f"project_{project_id}.sqlite")
    
    birth_time = get_file_birth_time(file_path)
    
    if birth_time == 0.0:
        print(f"⚠️ OSTRZEŻENIE: Plik projektu nie istnieje: {file_path}")
        status = 'MISSING'
    else:
        status = 'OK'
        print(f"✅ Zarejestrowano plik projektu {project_id}: {file_path} (birth: {birth_time})")
    
    con = _open_rm_connection(rm_db_path)
    con.execute("""
        INSERT OR REPLACE INTO project_file_tracking 
        (project_id, project_name, file_path, file_birth_time, last_verified_at, verification_status)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
    """, (project_id, project_name, file_path, birth_time, status))
    con.commit()
    con.close()


def verify_project_file(rm_db_path: str, project_id: int, projects_path: str = None) -> tuple:
    """Weryfikuje integralność pliku projektu
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite
        project_id: ID projektu
        projects_path: Folder projektów (lokalny config). Jeśli podany - konstruuje ścieżkę w locie
    
    Returns:
        tuple: (is_valid: bool, status: str, message: str)
            - (True, 'OK', 'Plik prawidłowy')
            - (False, 'MISSING', 'Plik projektu nie istnieje')
            - (False, 'BIRTH_MISMATCH', 'Plik został zmieniony (inny czas utworzenia)')
            - (False, 'NOT_REGISTERED', 'Projekt nie jest jeszcze zarejestrowany')
    """
    con = _open_rm_connection(rm_db_path)
    
    # Pobierz zarejestrowane dane
    row = con.execute("""
        SELECT project_name, file_path, file_birth_time, verification_status
        FROM project_file_tracking
        WHERE project_id = ?
    """, (project_id,)).fetchone()
    
    if not row:
        con.close()
        return (False, 'NOT_REGISTERED', 'Projekt nie jest jeszcze zarejestrowany w systemie śledzenia')
    
    # Konstruuj ścieżkę z lokalnego config (nie z bazy - litera dysku może być inna!)
    import os
    if projects_path:
        file_path = os.path.join(projects_path, f"project_{project_id}.sqlite")
    else:
        file_path = row['file_path']
    registered_birth = row['file_birth_time']
    
    # Sprawdź czy plik istnieje
    current_birth = get_file_birth_time(file_path)
    
    if current_birth == 0.0:
        # Plik nie istnieje
        con.execute("""
            UPDATE project_file_tracking
            SET verification_status = 'MISSING', last_verified_at = CURRENT_TIMESTAMP
            WHERE project_id = ?
        """, (project_id,))
        con.commit()
        con.close()
        return (False, 'MISSING', f'Plik projektu nie istnieje: {file_path}')
    
    # Sprawdź czy czas utworzenia się zgadza (tolerancja ±1 sekunda)
    if abs(current_birth - registered_birth) > 1.0:
        con.execute("""
            UPDATE project_file_tracking
            SET verification_status = 'BIRTH_MISMATCH', last_verified_at = CURRENT_TIMESTAMP
            WHERE project_id = ?
        """, (project_id,))
        con.commit()
        con.close()
        return (False, 'BIRTH_MISMATCH', 
                f'Plik projektu został zmieniony (inny czas utworzenia).\n'
                f'Zarejestrowany: {registered_birth}, Obecny: {current_birth}')
    
    # Wszystko OK
    con.execute("""
        UPDATE project_file_tracking
        SET verification_status = 'OK', last_verified_at = CURRENT_TIMESTAMP
        WHERE project_id = ?
    """, (project_id,))
    con.commit()
    con.close()
    
    return (True, 'OK', 'Plik projektu prawidłowy')


def reset_project_tracking(rm_db_path: str, project_id: int, master_db_path: str, projects_path: str = None):
    """Resetuje śledzenie pliku projektu (ponowna rejestracja)
    
    Używane gdy użytkownik przywróci plik lub chce zarejestrować nowy plik.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite
        project_id: ID projektu
        master_db_path: Ścieżka do master.sqlite
        projects_path: Folder projektów
    """
    import os
    
    con = _open_rm_connection(rm_db_path)
    
    # Pobierz nazwę projektu
    row = con.execute("""
        SELECT project_name FROM project_file_tracking WHERE project_id = ?
    """, (project_id,)).fetchone()
    
    project_name = row['project_name'] if row else f"Projekt_{project_id}"
    con.close()
    
    # Usuń stary wpis i zarejestruj ponownie
    con = _open_rm_connection(rm_db_path)
    con.execute("DELETE FROM project_file_tracking WHERE project_id = ?", (project_id,))
    con.commit()
    con.close()
    
    register_project_file(rm_db_path, project_id, project_name, master_db_path, projects_path=projects_path)
    print(f"✅ Zresetowano śledzenie dla projektu {project_id}")


# ============================================================================
# Inicjalizacja projektu
# ============================================================================

def sync_project_stages_with_definitions(project_db_path: str, project_id: int) -> int:
    """Synchronizuj project_stages z STAGE_DEFINITIONS - dodaj brakujące etapy.
    Napraw również brakujące stage_schedule dla istniejących stages.
    
    Returns:
        Liczba dodanych etapów
    """
    con = _open_rm_connection(project_db_path)
    
    try:
        # Pobierz wszystkie stage_code z stage_definitions
        all_stage_codes = {row['code'] for row in con.execute("SELECT code FROM stage_definitions")}
        
        # Pobierz istniejące stage_code dla projektu
        existing = {row['stage_code'] for row in con.execute(
            "SELECT stage_code FROM project_stages WHERE project_id = ?", (project_id,)
        )}
        
        # Etapy do dodania
        missing = all_stage_codes - existing
        
        # Najpierw dodaj nowe etapy
        added = 0
        if missing:
            # Pobierz max sequence
            cursor = con.execute(
                "SELECT MAX(sequence) as max_seq FROM project_stages WHERE project_id = ?",
                (project_id,)
            )
            row = cursor.fetchone()
            next_seq = (row['max_seq'] or 0) + 1 if row else 1
            
            for stage_code in sorted(missing):  # sorted dla deterministycznego kolejności
                # INSERT project_stages
                cur = con.execute("""
                    INSERT INTO project_stages (project_id, stage_code, sequence)
                    VALUES (?, ?, ?)
                """, (project_id, stage_code, next_seq))
                ps_id = cur.lastrowid
                
                # INSERT stage_schedule (pusty wpis)
                con.execute("""
                    INSERT INTO stage_schedule (project_stage_id)
                    VALUES (?)
                """, (ps_id,))
                
                next_seq += 1
                added += 1
        
        # Napraw brakujące stage_schedule dla ISTNIEJĄCYCH project_stages
        schedules_fixed = 0
        for ps_row in con.execute("""
            SELECT id FROM project_stages WHERE project_id = ?
        """, (project_id,)):
            ps_id = ps_row['id']
            existing_sched = con.execute(
                "SELECT id FROM stage_schedule WHERE project_stage_id = ?",
                (ps_id,)
            ).fetchone()
            if not existing_sched:
                con.execute(
                    "INSERT INTO stage_schedule (project_stage_id) VALUES (?)",
                    (ps_id,)
                )
                schedules_fixed += 1
        
        con.commit()
        
        if added > 0 or schedules_fixed > 0:
            print(f"✅ Projekt {project_id}: dodano {added} etapów/milestones, naprawiono {schedules_fixed} stage_schedule")
        
        return added
        
    except Exception as e:
        con.rollback()
        print(f"❌ Błąd sync_project_stages: {e}")
        raise
    finally:
        con.close()


def init_project(rm_db_path: str, project_id: int, stages_config: List[Dict], dependencies_config: List[Dict] = None):
    """Inicjalizuje nowy projekt w RM_MANAGER
    
    Args:
        project_id: ID projektu
        stages_config: [
            {"code": "PROJEKT", "template_start": "2026-01-01", "template_end": "2026-01-05", "sequence": 1},
            {"code": "MONTAZ", "template_start": "2026-01-05", "template_end": "2026-01-15", "sequence": 2},
        ]
        dependencies_config: [
            {"from": "PROJEKT", "to": "KOMPLETACJA", "type": "FS", "lag": 0},
            {"from": "MONTAZ", "to": "ELEKTROMONTAZ", "type": "SS", "lag": 2},
        ]
    """
    con = _open_rm_connection(rm_db_path)
    
    try:
        # 1. Utwórz project_stages
        for stage in stages_config:
            # Sprawdź czy stage_code istnieje w stage_definitions
            cursor = con.execute("SELECT id FROM stage_definitions WHERE code = ?", (stage['code'],))
            if not cursor.fetchone():
                raise ValueError(f"Nieznany stage_code: {stage['code']}")
            
            # INSERT lub IGNORE jeśli już istnieje
            con.execute("""
                INSERT OR IGNORE INTO project_stages (project_id, stage_code, sequence)
                VALUES (?, ?, ?)
            """, (project_id, stage['code'], stage.get('sequence', 0)))
        
        # 2. Jeśli są template dates - dodaj do stage_schedule
        for stage in stages_config:
            if 'template_start' in stage and 'template_end' in stage:
                # Pobierz project_stage_id
                cursor = con.execute("""
                    SELECT id FROM project_stages
                    WHERE project_id = ? AND stage_code = ?
                """, (project_id, stage['code']))
                row = cursor.fetchone()
                if row:
                    project_stage_id = row[0]
                    
                    # INSERT lub UPDATE schedule
                    con.execute("""
                        INSERT OR REPLACE INTO stage_schedule 
                        (project_stage_id, template_start, template_end, notes)
                        VALUES (?, ?, ?, ?)
                    """, (project_stage_id, stage['template_start'], stage['template_end'], stage.get('notes')))
        
        # 3. Dodaj dependencies
        if dependencies_config:
            for dep in dependencies_config:
                con.execute("""
                    INSERT OR IGNORE INTO stage_dependencies 
                    (project_id, predecessor_stage_code, successor_stage_code, dependency_type, lag_days)
                    VALUES (?, ?, ?, ?, ?)
                """, (project_id, dep['from'], dep['to'], dep['type'], dep.get('lag', 0)))
        
        con.commit()
        print(f"✅ Projekt {project_id} zainicjalizowany: {len(stages_config)} etapów, {len(dependencies_config or [])} zależności")
        
    except Exception as e:
        con.rollback()
        print(f"❌ Błąd init_project: {e}")
        raise
    finally:
        con.close()


# ============================================================================
# Operacje na etapach: START/END
# ============================================================================

# UWAGA: can_start_stage() przeniesione niżej (po MILESTONE functions) - L1625+ 
# Nowa wersja obsługuje state machine validation

def is_stage_started(rm_db_path: str, project_id: int, stage_code: str) -> bool:
    """🔍 Sprawdź czy etap został rozpoczęty (ma przynajmniej jeden okres)
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt
        project_id: ID projektu
        stage_code: Kod etapu
        
    Returns:
        True jeśli etap został kiedykolwiek rozpoczęty
    """
    con = _open_rm_connection(rm_db_path)
    
    cursor = con.execute("""
        SELECT COUNT(*) as cnt
        FROM stage_actual_periods sap
        JOIN project_stages ps ON sap.project_stage_id = ps.id
        WHERE ps.project_id = ? AND ps.stage_code = ?
    """, (project_id, stage_code))
    
    count = cursor.fetchone()[0]
    con.close()
    
    return count > 0


def is_stage_finished(rm_db_path: str, project_id: int, stage_code: str) -> bool:
    """🔍 Sprawdź czy etap został zakończony (wszystkie okresy zamknięte)
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt
        project_id: ID projektu
        stage_code: Kod etapu
        
    Returns:
        True jeśli etap został rozpoczęty I wszystkie okresy są zamknięte (ended_at != NULL)
        ⚠️  Dla milestones: True jeśli milestone został ustawiony (ended_at nie ma znaczenia)
    """
    con = _open_rm_connection(rm_db_path)
    
    # Sprawdź czy to milestone
    cursor = con.execute("""
        SELECT sd.is_milestone
        FROM project_stages ps
        JOIN stage_definitions sd ON ps.stage_code = sd.code
        WHERE ps.project_id = ? AND ps.stage_code = ?
    """, (project_id, stage_code))
    row = cursor.fetchone()
    
    if not row:
        con.close()
        return False
    
    is_milestone_flag = row['is_milestone']
    
    if is_milestone_flag:
        # 🔵 MILESTONE: "zakończony" = został ustawiony (ma period)
        # Milestones nie mają ended_at bo to instant event
        cursor = con.execute("""
            SELECT COUNT(*) as total
            FROM stage_actual_periods sap
            JOIN project_stages ps ON sap.project_stage_id = ps.id
            WHERE ps.project_id = ? AND ps.stage_code = ?
        """, (project_id, stage_code))
        total = cursor.fetchone()['total']
        con.close()
        return total > 0
    else:
        # 🔵 REGULARNY ETAP: zakończony = ma okresy I wszystkie zamknięte (ended_at != NULL)
        cursor = con.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN sap.ended_at IS NULL THEN 1 ELSE 0 END) as active
            FROM stage_actual_periods sap
            JOIN project_stages ps ON sap.project_stage_id = ps.id
            WHERE ps.project_id = ? AND ps.stage_code = ?
        """, (project_id, stage_code))
        
        row = cursor.fetchone()
        con.close()
        
        total = row['total']
        active = row['active']
        
        # Zakończony = ma okresy I żaden nie jest aktywny
        return total > 0 and active == 0


def start_stage(rm_db_path: str, project_id: int, stage_code: str, started_by: str = None, notes: str = None, master_db_path: str = None) -> int:
    """Rozpocznij etap (utwórz nowy okres)
    
    ⚠️  Dla milestones (PRZYJĘTY, ZAKOŃCZONY) użyj set_milestone() zamiast start_stage()!
    ⚠️  STATE MACHINE: Waliduje status projektu i aktualizuje na IN_PROGRESS
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt
        project_id: ID projektu
        stage_code: Kod etapu
        started_by: Użytkownik rozpoczynający etap
        notes: Notatki
        master_db_path: Ścieżka do master.sqlite (dla update statusu projektu)
    
    Returns:
        ID nowego okresu w stage_actual_periods
    """
    # Sprawdź czy to milestone - jeśli tak, ostrzeż
    if is_milestone(rm_db_path, stage_code):
        raise ValueError(f"⚠️  {stage_code} jest milestone! Użyj set_milestone() zamiast start_stage().")
    
    # 🛡️ BACKEND GUARD: Walidacja statusu projektu
    if master_db_path:
        current_status = get_project_status(master_db_path, project_id)
        
        if current_status == ProjectStatus.NEW:
            raise ValueError(f"🚫 Projekt nieprzyjęty (status: NEW)!\nKliknij PRZYJĘTY przed startowaniem etapów.")
        
        if current_status == ProjectStatus.DONE:
            raise ValueError(f"🚫 Projekt zakończony (status: DONE)!\nNie można rozpocząć etapu w zakończonym projekcie.")
        
        if current_status == ProjectStatus.PAUSED:
            raise ValueError(f"🚫 Projekt wstrzymany (status: PAUSED)!\nKliknij WZNÓW przed startowaniem nowych etapów.")
    
    # 🚀 NOWE SPRAWDZENIE: Dodatkowa ochrona przez project_pauses
    if is_project_paused(rm_db_path, project_id):
        raise ValueError(f"🚫 Projekt ma aktywną pauzę!\nUżyj resume_project() przed startowaniem etapów.")
    
    con = _open_rm_connection(rm_db_path)
    
    try:
        # Walidacja zależności
        can_start, reason = can_start_stage(rm_db_path, project_id, stage_code, master_db_path)
        if not can_start:
            raise ValueError(f"Nie można rozpocząć {stage_code}: {reason}")
        
        # Znajdź project_stage_id
        cursor = con.execute("""
            SELECT id FROM project_stages 
            WHERE project_id = ? AND stage_code = ?
        """, (project_id, stage_code))
        row = cursor.fetchone()
        
        if not row:
            raise ValueError(f"Etap {stage_code} nie istnieje dla projektu {project_id}. Użyj init_project() najpierw.")
        
        project_stage_id = row[0]
        
        # 🛡️ BACKEND GUARD: Sprawdź czy etap już trwa
        cursor = con.execute("""
            SELECT id FROM stage_actual_periods
            WHERE project_stage_id = ? AND ended_at IS NULL
        """, (project_stage_id,))
        
        if cursor.fetchone():
            raise ValueError(f"🚫 Etap {stage_code} już trwa! Nie można rozpocząć drugiej instancji.")
        
        # Utwórz nowy okres
        now = get_timestamp_now()
        cursor = con.execute("""
            INSERT INTO stage_actual_periods 
            (project_stage_id, started_at, started_by, notes)
            VALUES (?, ?, ?, ?)
        """, (project_stage_id, now, started_by, notes))
        
        period_id = cursor.lastrowid
        con.commit()
        con.close()
        
        # ── Aktualizuj status projektu ────────────────────────────────────
        if master_db_path:
            try:
                current_status = get_project_status(master_db_path, project_id)
                
                # � NOWA LOGIKA: Start etapu → IN_PROGRESS (bez specjalnej obsługi WSTRZYMANY)
                if current_status in [ProjectStatus.ACCEPTED, None]:
                    set_project_status(master_db_path, project_id, ProjectStatus.IN_PROGRESS)
                    
            except Exception as e:
                print(f"⚠️  Nie można zaktualizować statusu projektu: {e}")
        
        print(f"✅ START: {stage_code} (project={project_id}, period_id={period_id})")
        return period_id
        
    except Exception as e:
        con.close()
        raise


def end_stage(rm_db_path: str, project_id: int, stage_code: str, ended_by: str = None, notes: str = None, master_db_path: str = None):
    """Zakończ etap (zamknij aktywny okres)
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt
        project_id: ID projektu
        stage_code: Kod etapu
        ended_by: Użytkownik kończący etap
        notes: Notatki
        master_db_path: Opcjonalna ścieżka do master.sqlite (dla auto-update statusu projektu)
    
    ⚠️  Dla milestones (PRZYJĘTY, ZAKOŃCZONY) użyj set_milestone() (nie ma END dla milestone)!
    """
    # Sprawdź czy to milestone - jeśli tak, ostrzeż
    if is_milestone(rm_db_path, stage_code):
        raise ValueError(f"⚠️  {stage_code} jest milestone! Milestones nie mają END - użyj set_milestone().")
    
    con = _open_rm_connection(rm_db_path)
    
    try:
        # Znajdź project_stage_id
        cursor = con.execute("""
            SELECT id FROM project_stages 
            WHERE project_id = ? AND stage_code = ?
        """, (project_id, stage_code))
        row = cursor.fetchone()
        
        if not row:
            raise ValueError(f"Etap {stage_code} nie istnieje")
        
        project_stage_id = row[0]
        
        # Znajdź aktywny okres
        cursor = con.execute("""
            SELECT id FROM stage_actual_periods
            WHERE project_stage_id = ? AND ended_at IS NULL
        """, (project_stage_id,))
        row = cursor.fetchone()
        
        if not row:
            raise ValueError(f"Etap {stage_code} nie jest aktywny!")
        
        period_id = row[0]
        
        # Zaktualizuj
        now = get_timestamp_now()
        con.execute("""
            UPDATE stage_actual_periods
            SET ended_at = ?, ended_by = ?, 
                notes = CASE 
                    WHEN notes IS NULL THEN ?
                    WHEN ? IS NULL THEN notes
                    ELSE notes || ' | ' || ?
                END
            WHERE id = ?
        """, (now, ended_by, notes, notes, notes, period_id))
        
        con.commit()
        print(f"✅ END: {stage_code} (project={project_id}, period_id={period_id})")
        
    finally:
        con.close()
    
    # 🔄 AUTO-UPDATE: Aktualizuj status projektu (uproszczona logika bez WSTRZYMANY)
    if master_db_path:
        update_project_status_after_stage_end(rm_db_path, master_db_path, project_id, stage_code)


def update_project_status_after_stage_end(rm_db_path: str, master_db_path: str, project_id: int, stage_code: str = None):
    """🔄 AUTO-UPDATE: Automatycznie aktualizuj status projektu po zakończeniu etapu
    
    🚀 NOWA LOGIKA: Uproszczona bez specjalnej obsługi WSTRZYMANY 
    - Pauzy obsługiwane przez pause_project()/resume_project()
    - Etapy = normalna praca nad projektem
    
    Logika:
        - Jeśli są aktywne etapy (nie-milestones) → IN_PROGRESS
        - Jeśli brak aktywnych etapów + status był IN_PROGRESS → zostaw IN_PROGRESS (user musi kliknąć ZAKOŃCZONY)
        - Jeśli status PAUSED → nie zmieniaj (pauza trwa)
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt
        master_db_path: Ścieżka do master.sqlite
        project_id: ID projektu
        stage_code: Kod zakończonego etapu (obecnie nieużywane)
    """
    if not master_db_path:
        return
    
    try:
        current_status = get_project_status(master_db_path, project_id)
        
        # Nie rób nic jeśli PAUSED, DONE, lub NEW - niech user sam steruje
        if current_status in [ProjectStatus.PAUSED, ProjectStatus.DONE, ProjectStatus.NEW]:
            return
        
        # Sprawdź czy są aktywne etapy (nie-milestones)  
        con = _open_rm_connection(rm_db_path)
        cursor = con.execute("""
            SELECT COUNT(*) as active_count
            FROM stage_actual_periods sap
            JOIN project_stages ps ON sap.project_stage_id = ps.id
            JOIN stage_definitions sd ON ps.stage_code = sd.code
            WHERE ps.project_id = ? AND sap.ended_at IS NULL
              AND sd.is_milestone = 0
        """, (project_id,))
        active_count = cursor.fetchone()[0]
        con.close()
        
        # Jeśli są aktywne → upewnij się że IN_PROGRESS
        if active_count > 0:
            if current_status != ProjectStatus.IN_PROGRESS:
                set_project_status(master_db_path, project_id, ProjectStatus.IN_PROGRESS)
        # Jeśli brak aktywnych → zostaw jak jest (user musi kliknąć ZAKOŃCZONY)
        
    except Exception as e:
        print(f"⚠️  Nie można auto-update statusu: {e}")


def get_active_stages(rm_db_path: str, project_id: int) -> List[Dict]:
    """Pobierz aktywne etapy (ended_at = NULL)
    
    📚 WSTRZYMANY jest filtrowany — pauzy obsługiwane przez project_pauses (overlay).
    
    Returns:
        [{'stage_code': 'MONTAZ', 'started_at': '...', 'period_id': 123}, ...]
    """
    con = _open_rm_connection(rm_db_path)
    
    cursor = con.execute("""
        SELECT sap.id as period_id, ps.stage_code, sap.started_at, sap.started_by, sap.notes
        FROM stage_actual_periods sap
        JOIN project_stages ps ON sap.project_stage_id = ps.id
        JOIN stage_definitions sd ON ps.stage_code = sd.code  -- 🚀 INNER JOIN filtruje nieistniejące etapy
        WHERE ps.project_id = ? AND sap.ended_at IS NULL
              AND ps.stage_code != 'WSTRZYMANY'
        ORDER BY sap.started_at
    """, (project_id,))
    
    rows = cursor.fetchall()
    con.close()
    
    return [dict(row) for row in rows]


def get_stage_periods(rm_db_path: str, project_id: int, stage_code: str) -> List[Dict]:
    """Zwraca wszystkie okresy dla danego etapu (historia powrotów)"""
    con = _open_rm_connection(rm_db_path)
    
    cursor = con.execute("""
        SELECT sap.id, sap.started_at, sap.ended_at, sap.started_by, sap.ended_by, sap.notes
        FROM stage_actual_periods sap
        JOIN project_stages ps ON sap.project_stage_id = ps.id
        WHERE ps.project_id = ? AND ps.stage_code = ?
        ORDER BY sap.started_at
    """, (project_id, stage_code))
    
    rows = cursor.fetchall()
    con.close()
    
    return [dict(row) for row in rows]


# ============================================================================  
# PROJECT PAUSES - System pauz jako overlay (nie etap!)
# ============================================================================

def is_project_paused(rm_db_path: str, project_id: int) -> bool:
    """Sprawdź czy projekt jest aktualnie wstrzymany (ma aktywną pauzę)
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt 
        project_id: ID projektu
        
    Returns:
        True jeśli projekt ma aktywną pauzę (end_at IS NULL)
    """
    con = _open_rm_connection(rm_db_path)
    cursor = con.execute("""
        SELECT id FROM project_pauses
        WHERE project_id = ? AND end_at IS NULL
    """, (project_id,))
    
    result = cursor.fetchone() is not None
    con.close()
    return result


def pause_project(rm_db_path: str, project_id: int, reason: str = None, 
                  paused_by: str = None, notes: str = None, 
                  master_db_path: str = None) -> int:
    """🛑 WSTRZYMAJ projekt (pauza overlay na aktywnych etapach)
    
    📚 ARCHITEKTURA: Pauza NIE jest etapem - to overlay na timeline!
    - Aktywne etapy pozostają aktywne
    - Status projektu → PAUSED  
    - Timeline pokazuje pauzę jako nakładkę
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt
        project_id: ID projektu
        reason: Powód wstrzymania
        paused_by: Użytkownik wstrzymujący
        notes: Dodatkowe notatki
        master_db_path: Ścieżka do master.sqlite (dla update statusu)
        
    Returns:
        ID utworzonej pauzy
        
    Raises:
        ValueError: Jeśli projekt już jest wstrzymany
    """
    # Sprawdź czy już wstrzymany
    if is_project_paused(rm_db_path, project_id):
        raise ValueError(f"🚫 Projekt {project_id} już jest wstrzymany!")
    
    # Sprawdź status projektu - nie można wstrzymać NEW lub ACCEPTED bez aktywnych etapów
    if master_db_path:
        current_status = get_project_status(master_db_path, project_id)
        if current_status in (ProjectStatus.NEW,):
            raise ValueError(f"🚫 Projekt nie został jeszcze przyjęty! (status: {current_status})")
        if current_status == ProjectStatus.DONE:
            raise ValueError(f"🚫 Projekt jest zakończony! (status: {current_status})")
    
    con = _open_rm_connection(rm_db_path)
    try:
        now = get_timestamp_now()
        cursor = con.execute("""
            INSERT INTO project_pauses (project_id, start_at, reason, user, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (project_id, now, reason, paused_by, notes))
        
        pause_id = cursor.lastrowid
        con.commit()
        
        # Event do project_events
        con.execute("""
            INSERT INTO project_events (project_id, event_type, user, notes)
            VALUES (?, 'WSTRZYMANY', ?, ?)
        """, (project_id, paused_by, f"Powód: {reason}" if reason else notes))
        con.commit()
        
        print(f"⏸️  WSTRZYMANIE: Projekt {project_id} (pause_id={pause_id})")
        
    except Exception as e:
        con.rollback()
        raise
    finally:
        con.close()
    
    # Aktualizuj status w master.sqlite
    if master_db_path:
        try:
            set_project_status(master_db_path, project_id, ProjectStatus.PAUSED)
        except Exception as e:
            print(f"⚠️  Nie można zaktualizować statusu: {e}")
    
    return pause_id


def resume_project(rm_db_path: str, project_id: int, resumed_by: str = None, 
                   notes: str = None, master_db_path: str = None) -> int:
    """▶️ WZNÓW projekt (zakończ aktywną pauzę)
    
    📚 ARCHITEKTURA: Kończy pauzę overlay, przywraca normalny przepływ
    - Aktywne etapy pozostają aktywne
    - Status projektu → IN_PROGRESS lub ACCEPTED
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt
        project_id: ID projektu
        resumed_by: Użytkownik wznawiający
        notes: Notatki
        master_db_path: Ścieżka do master.sqlite
        
    Returns:
        ID zakończonej pauzy
        
    Raises:
        ValueError: Jeśli projekt nie jest wstrzymany
    """
    if not is_project_paused(rm_db_path, project_id):
        raise ValueError(f"🚫 Projekt {project_id} nie jest wstrzymany!")
    
    con = _open_rm_connection(rm_db_path)
    try:
        now = get_timestamp_now()
        
        # Znajdź aktywną pauzę
        cursor = con.execute("""
            SELECT id FROM project_pauses
            WHERE project_id = ? AND end_at IS NULL
        """, (project_id,))
        
        pause_row = cursor.fetchone()
        if not pause_row:
            raise ValueError(f"Brak aktywnej pauzy dla projektu {project_id}")
        
        pause_id = pause_row[0]
        
        # Zakończ pauzę
        con.execute("""
            UPDATE project_pauses 
            SET end_at = ?, notes = COALESCE(notes || ' | ', '') || ?
            WHERE id = ?
        """, (now, f"Wznowiono przez {resumed_by}" if resumed_by else "Wznowiono", pause_id))
        
        # Event do project_events
        con.execute("""
            INSERT INTO project_events (project_id, event_type, user, notes)
            VALUES (?, 'WZNOWIONY', ?, ?)
        """, (project_id, resumed_by, notes))
        
        con.commit()
        print(f"▶️  WZNOWIENIE: Projekt {project_id} (pause_id={pause_id})")
        
    except Exception as e:
        con.rollback()
        raise
    finally:
        con.close()
    
    # Aktualizuj status w master.sqlite (PAUSED → IN_PROGRESS lub ACCEPTED)
    if master_db_path:
        try:
            # Sprawdź czy są aktywne etapy (nie-milestones)
            active_stages = get_active_stages(rm_db_path, project_id)
            active_non_milestones = [s for s in active_stages if not is_milestone(rm_db_path, s['stage_code'])]
            
            if active_non_milestones:
                new_status = ProjectStatus.IN_PROGRESS
            else:
                new_status = ProjectStatus.ACCEPTED
                
            set_project_status(master_db_path, project_id, new_status)
            print(f"📊 STATUS: PAUSED → {new_status}")
            
        except Exception as e:
            print(f"⚠️  Nie można zaktualizować statusu: {e}")
    
    return pause_id


def get_project_pauses(rm_db_path: str, project_id: int) -> list:
    """Pobierz historię pauz projektu
    
    Returns:
        Lista słowników z danymi pauz (start_at, end_at, reason, user, etc.)
    """
    con = _open_rm_connection(rm_db_path)
    
    cursor = con.execute("""
        SELECT * FROM project_pauses
        WHERE project_id = ?
        ORDER BY start_at DESC
    """, (project_id,))
    
    rows = cursor.fetchall()
    con.close()
    
    return [dict(row) for row in rows]


def cleanup_orphaned_wstrzymany(rm_db_path: str, project_id: int) -> int:
    """Zamknij osierocone okresy WSTRZYMANY w stage_actual_periods.
    
    📚 MIGRACJA: Stary GUI używał start_stage('WSTRZYMANY') / end_stage('WSTRZYMANY').
    Nowa architektura używa project_pauses (overlay). Ta funkcja czyści stare rekordy.
    
    Returns:
        Liczba zamkniętych okresów
    """
    con = _open_rm_connection(rm_db_path)
    try:
        now = get_timestamp_now()
        cursor = con.execute("""
            UPDATE stage_actual_periods
            SET ended_at = ?, notes = COALESCE(notes || ' | ', '') || 'Auto-zamknięty (migracja na project_pauses)'
            WHERE project_stage_id IN (
                SELECT ps.id FROM project_stages ps
                WHERE ps.project_id = ? AND ps.stage_code = 'WSTRZYMANY'
            )
            AND ended_at IS NULL
        """, (now, project_id))
        
        count = cursor.rowcount
        con.commit()
        
        if count > 0:
            print(f"🧹 Zamknięto {count} osieroconych okresów WSTRZYMANY dla projektu {project_id}")
        
        return count
    finally:
        con.close()


# ============================================================================
# PROJECT STATUS - State Machine (kontrola stanu projektu w master.sqlite)
# ============================================================================

def get_project_status(master_db_path: str, project_id: int) -> str:
    """Pobierz aktualny status projektu z master.sqlite
    
    Returns:
        Status projektu (NEW, ACCEPTED, IN_PROGRESS, PAUSED, DONE)
        Jeśli brak kolumny project_status w master, zwraca None
    """
    con = _open_rm_connection(master_db_path)
    
    try:
        cursor = con.execute("""
            SELECT project_status FROM projects WHERE project_id = ?
        """, (project_id,))
        row = cursor.fetchone()
        con.close()
        
        if row and row['project_status']:
            return row['project_status']
        else:
            # Domyślny status jeśli nie ustawiony
            return ProjectStatus.NEW
            
    except sqlite3.OperationalError:
        # Kolumna project_status nie istnieje (stary schemat)
        con.close()
        return None


def set_project_status(master_db_path: str, project_id: int, new_status: str):
    """Ustaw status projektu w master.sqlite
    
    Args:
        master_db_path: Ścieżka do master.sqlite
        project_id: ID projektu
        new_status: Nowy status (NEW, ACCEPTED, IN_PROGRESS, PAUSED, DONE)
    """
    # Walidacja: czy nowy status jest poprawny
    valid_statuses = [ProjectStatus.NEW, ProjectStatus.ACCEPTED, ProjectStatus.IN_PROGRESS, 
                     ProjectStatus.PAUSED, ProjectStatus.DONE]
    if new_status not in valid_statuses:
        raise ValueError(f"Nieprawidłowy status: {new_status}")
    
    con = _open_rm_connection(master_db_path)
    
    try:
        # Dodaj kolumnę project_status jeśli nie istnieje
        try:
            con.execute("ALTER TABLE projects ADD COLUMN project_status TEXT DEFAULT 'NEW'")
        except sqlite3.OperationalError:
            pass  # Kolumna już istnieje
        
        # Update status
        con.execute("""
            UPDATE projects 
            SET project_status = ?
            WHERE project_id = ?
        """, (new_status, project_id))
        
        con.commit()
        print(f"✅ Status projektu {project_id}: {new_status}")
        
    finally:
        con.close()


def can_transition_to(current_status: str, new_status: str) -> tuple:
    """Sprawdź czy przejście do nowego statusu jest dozwolone
    
    Returns:
        (allowed: bool, reason: str)
    """
    if current_status not in ALLOWED_TRANSITIONS:
        return (False, f"Nieznany status początkowy: {current_status}")
    
    allowed = ALLOWED_TRANSITIONS[current_status]
    
    if new_status in allowed:
        return (True, "OK")
    else:
        return (False, f"Niedozwolone przejście: {current_status} → {new_status}")


def transition_project_status(master_db_path: str, project_id: int, new_status: str, 
                              force: bool = False) -> tuple:
    """Przejdź do nowego statusu z walidacją state machine
    
    Args:
        master_db_path: Ścieżka do master.sqlite
        project_id: ID projektu
        new_status: Docelowy status
        force: Czy pominąć walidację przejść (tylko ADMIN)
        
    Returns:
        (success: bool, message: str)
    """
    current_status = get_project_status(master_db_path, project_id)
    
    if current_status is None:
        # Stary schemat bez project_status - inicjalizuj
        set_project_status(master_db_path, project_id, ProjectStatus.NEW)
        current_status = ProjectStatus.NEW
    
    # Walidacja przejścia (pomiń jeśli force=True)
    if not force:
        allowed, reason = can_transition_to(current_status, new_status)
        if not allowed:
            return (False, reason)
    
    # Wykonaj przejście
    try:
        set_project_status(master_db_path, project_id, new_status)
        return (True, f"Przejście {current_status} → {new_status}")
    except Exception as e:
        return (False, f"Błąd przejścia statusu: {e}")


def record_project_event(rm_db_path: str, project_id: int, event_type: str, 
                         user: str = None, notes: str = None, timestamp: str = None):
    """Zapisz event projektu do tabeli project_events
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt
        project_id: ID projektu
        event_type: Typ eventu (PRZYJETY, ZAKONCZONY, WSTRZYMANY, WZNOWIONY)
        user: Użytkownik wykonujący event
        notes: Notatki
        timestamp: Opcjonalny timestamp (domyślnie NOW)
    """
    con = _open_rm_connection(rm_db_path)
    
    try:
        ts = timestamp or get_timestamp_now()
        
        con.execute("""
            INSERT INTO project_events (project_id, event_type, timestamp, user, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (project_id, event_type, ts, user, notes))
        
        con.commit()
        print(f"✅ EVENT: {event_type} @ {ts} (project={project_id}, user={user})")
        
    finally:
        con.close()


def get_project_event(rm_db_path: str, project_id: int, event_type: str) -> dict:
    """Pobierz event projektu
    
    Returns:
        {'timestamp': '...', 'user': '...', 'notes': '...'} lub None
    """
    con = _open_rm_connection(rm_db_path)
    
    cursor = con.execute("""
        SELECT timestamp, user, notes
        FROM project_events
        WHERE project_id = ? AND event_type = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (project_id, event_type))
    
    row = cursor.fetchone()
    con.close()
    
    return dict(row) if row else None


def event_exists(rm_db_path: str, project_id: int, event_type: str) -> bool:
    """Sprawdź czy event został już zapisany"""
    return get_project_event(rm_db_path, project_id, event_type) is not None


# ============================================================================
# MILESTONE functions - dla "zdarzeń instant" (PRZYJĘTY, ZAKOŃCZONY)
# ============================================================================

def is_milestone(rm_db_path: str, stage_code: str) -> bool:
    """Sprawdź czy etap to milestone (zdarzenie instant bez czasu trwania)"""
    con = _open_rm_connection(rm_db_path)
    
    cursor = con.execute("""
        SELECT is_milestone FROM stage_definitions WHERE code = ?
    """, (stage_code,))
    row = cursor.fetchone()
    con.close()
    
    return bool(row and row['is_milestone'])


def set_milestone(rm_db_path: str, project_id: int, stage_code: str, user: str = None, notes: str = None, 
                  timestamp: str = None, master_db_path: str = None) -> int:
    """Ustaw milestone (zdarzenie instant: start = end = now)
    
    ⚠️  STATE MACHINE: Waliduje status projektu przed ustawieniem milestone
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt
        project_id: ID projektu
        stage_code: Kod milestone (np. 'PRZYJETY', 'ZAKONCZONY')
        user: Użytkownik ustawiający milestone
        notes: Notatki
        timestamp: Opcjonalny timestamp (domyślnie now)
        master_db_path: Ścieżka do master.sqlite (dla update statusu projektu)
        
    Returns:
        period_id: ID utworzonego rekordu w stage_actual_periods
    """
    print(f"\n🎯 SET_MILESTONE BACKEND: project={project_id}, stage={stage_code}")
    print(f"   rm_db_path: {rm_db_path}")
    print(f"   user: {user}")
    print(f"   master_db_path: {master_db_path}")
    print(f"   Plik RM istnieje: {os.path.exists(rm_db_path)}")
    print(f"   Master istnieje: {os.path.exists(master_db_path) if master_db_path else 'N/A'}")
    
    # Sprawdź czy to rzeczywiście milestone
    is_ms = is_milestone(rm_db_path, stage_code)
    print(f"   is_milestone({stage_code}): {is_ms}")
    
    if not is_ms:
        error_msg = f"⚠️  {stage_code} nie jest milestone! Użyj start_stage() zamiast set_milestone()."
        print(f"   ❌ {error_msg}")
        raise ValueError(error_msg)
    
    # ── STATE MACHINE: Walidacja statusu projektu ──────────────────────────
    if master_db_path:
        print(f"   🔍 Sprawdzam status projektu w master.sqlite...")
        current_status = get_project_status(master_db_path, project_id)
        print(f"   Status aktualny: {current_status}")
        
        if current_status is None:
            # Stary schemat - inicjalizuj
            print(f"   🔄 Inicjalizuję status na NEW...")
            set_project_status(master_db_path, project_id, ProjectStatus.NEW)
            current_status = ProjectStatus.NEW
            print(f"   Status po inicjalizacji: {current_status}")
        
        # 🛡️ BACKEND GUARD: Walidacja dla PRZYJĘTY
        if stage_code == 'PRZYJETY':
            print(f"   🛡️ Walidacja PRZYJĘTY: current_status={current_status}")
            if current_status != ProjectStatus.NEW:
                error_msg = f"🚫 Projekt już przyjęty! (status: {current_status})\nNie można ustawić PRZYJĘTY ponownie."
                print(f"   ❌ {error_msg}")
                raise ValueError(error_msg)
        
        # 🛡️ BACKEND GUARD: Walidacja dla ZAKOŃCZONY
        if stage_code == 'ZAKONCZONY':
            print(f"   🛡️ Walidacja ZAKOŃCZONY: current_status={current_status}")
            if current_status == ProjectStatus.DONE:
                error_msg = f"🚫 Projekt już zakończony! (status: {current_status})\nNie można ustawić ZAKOŃCZONY ponownie."
                print(f"   ❌ {error_msg}")
                raise ValueError(error_msg)
            if current_status != ProjectStatus.IN_PROGRESS:
                error_msg = f"🚫 Projekt nie był w realizacji! (status: {current_status})\nMusi być przynajmniej jeden etap rozpoczęty."
                print(f"   ❌ {error_msg}")
                raise ValueError(error_msg)
    else:
        print(f"   ⚠️ Brak master_db_path - pomijam walidację statusu")
    
    # 🔒 ATOMOWA TRANSAKCJA: Sprawdź aktywne etapy + zapisz milestone + update status (zapobiega race condition)
    print(f"   🔒 Rozpoczynam transakcję SQLite...")
    con = _open_rm_connection(rm_db_path)
    
    try:
        # BEGIN TRANSACTION (implicit - SQLite auto-begins on first statement)
        print(f"   📊 Sprawdzam strukturę bazy...")
        
        # 🛡️ BACKEND GUARD: Sprawdź czy są aktywne etapy (TYLKO dla ZAKOŃCZONY, w TEJ SAMEJ transakcji!)
        if stage_code == 'ZAKONCZONY':
            print(f"   🔍 Sprawdzam aktywne etapy dla ZAKOŃCZONY...")
            cursor = con.execute("""
                SELECT COUNT(*) as active_count
                FROM stage_actual_periods sap
                JOIN project_stages ps ON sap.project_stage_id = ps.id
                JOIN stage_definitions sd ON ps.stage_code = sd.code
                WHERE ps.project_id = ? AND sap.ended_at IS NULL
                  AND sd.is_milestone = 0
            """, (project_id,))
            active_count = cursor.fetchone()[0]
            print(f"   Aktywnych etapów: {active_count}")
            
            if active_count > 0:
                error_msg = f"🚫 Są aktywne etapy ({active_count})!\nNie można zakończyć projektu. Najpierw zakończ wszystkie etapy."
                print(f"   ❌ {error_msg}")
                raise ValueError(error_msg)
        
        # Znajdź project_stage_id
        print(f"   🔍 Szukam project_stage dla {stage_code}...")
        cursor = con.execute("""
            SELECT id FROM project_stages 
            WHERE project_id = ? AND stage_code = ?
        """, (project_id, stage_code))
        row = cursor.fetchone()
        
        if not row:
            error_msg = f"Milestone {stage_code} nie istnieje dla projektu {project_id}. Użyj init_project() najpierw."
            print(f"   ❌ {error_msg}")
            raise ValueError(error_msg)
        
        project_stage_id = row[0]
        print(f"   ✅ Znalazłem project_stage_id: {project_stage_id}")
        
        # Double-check: sprawdź czy już ustawiony w stage_actual_periods
        print(f"   🔍 Sprawdzam czy milestone już istnieje...")
        cursor = con.execute("""
            SELECT id FROM stage_actual_periods
            WHERE project_stage_id = ?
        """, (project_stage_id,))
        
        existing = cursor.fetchone()
        print(f"   Istniejący rekord: {existing['id'] if existing else 'brak'}")
        
        if existing and stage_code in ('PRZYJETY', 'ZAKONCZONY'):
            error_msg = f"🚫 Milestone {stage_code} już ustawiony w bazie!"
            print(f"   ❌ {error_msg}")
            raise ValueError(error_msg)
        
        # Utwórz rekord (start = end = now)
        now = timestamp or get_timestamp_now()
        print(f"   💾 Tworzę rekord milestone z timestampem: {now}")
        
        cursor = con.execute("""
            INSERT INTO stage_actual_periods 
            (project_stage_id, started_at, ended_at, started_by, ended_by, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (project_stage_id, now, now, user, user, notes))
        
        period_id = cursor.lastrowid
        print(f"   ✅ Utworzony period_id: {period_id}")
        
        # ── Zapisz event do project_events (W TEJ SAMEJ TRANSAKCJI!) ────────
        if stage_code in ('PRZYJETY', 'ZAKONCZONY'):
            print(f"   📝 Zapisuję event do project_events...")
            con.execute("""
                INSERT INTO project_events (project_id, event_type, timestamp, user, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (project_id, stage_code, now, user, notes))
            print(f"   ✅ Event zapisany")
        
        # COMMIT atomowo (milestone + event razem)
        print(f"   💾 COMMIT transakcji...")
        con.commit()
        con.close()
        print(f"   ✅ Transakcja zakończona pomyślnie")
        
        # ── Aktualizuj status projektu w master.sqlite ──────────────────
        if master_db_path:
            print(f"   🔄 Aktualizuję status projektu w master.sqlite...")
            try:
                if stage_code == 'PRZYJETY':
                    # NEW → ACCEPTED
                    print(f"   📊 NEW → ACCEPTED")
                    set_project_status(master_db_path, project_id, ProjectStatus.ACCEPTED)
                    
                elif stage_code == 'ZAKONCZONY':
                    # IN_PROGRESS/ACCEPTED → DONE
                    print(f"   📊 IN_PROGRESS/ACCEPTED → DONE")
                    set_project_status(master_db_path, project_id, ProjectStatus.DONE)
                
                print(f"   ✅ Status zaktualizowany w master.sqlite")
                    
            except Exception as e:
                print(f"   ⚠️  Nie można zaktualizować statusu projektu: {e}")
        
        print(f"✅ MILESTONE SET: {stage_code} @ {now} (project={project_id}, period_id={period_id})")
        return period_id
        
    except Exception as e:
        print(f"   🔥 Błąd w transakcji SQL: {e}")
        import traceback
        traceback.print_exc()
        con.close()
        raise


def is_milestone_set(rm_db_path: str, project_id: int, stage_code: str) -> bool:
    """Sprawdź czy milestone został ustawiony"""
    con = _open_rm_connection(rm_db_path)
    
    cursor = con.execute("""
        SELECT sap.id
        FROM stage_actual_periods sap
        JOIN project_stages ps ON sap.project_stage_id = ps.id
        WHERE ps.project_id = ? AND ps.stage_code = ?
        LIMIT 1
    """, (project_id, stage_code))
    
    result = cursor.fetchone() is not None
    con.close()
    
    return result


def get_milestone(rm_db_path: str, project_id: int, stage_code: str) -> dict:
    """Pobierz informacje o milestone
    
    Returns:
        {'timestamp': '...', 'user': '...', 'notes': '...'} lub None
    """
    con = _open_rm_connection(rm_db_path)
    
    cursor = con.execute("""
        SELECT sap.started_at as timestamp, sap.started_by as user, sap.notes
        FROM stage_actual_periods sap
        JOIN project_stages ps ON sap.project_stage_id = ps.id
        WHERE ps.project_id = ? AND ps.stage_code = ?
        LIMIT 1
    """, (project_id, stage_code))
    
    row = cursor.fetchone()
    con.close()
    
    return dict(row) if row else None


def unset_milestone(rm_db_path: str, project_id: int, stage_code: str, master_db_path: str = None):
    """Usuń milestone (cofnij ustawienie)
    
    ⚠️  STATE MACHINE: Cofa status projektu (DONE → IN_PROGRESS, ACCEPTED → NEW)
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt
        project_id: ID projektu
        stage_code: Kod milestone (PRZYJETY, ZAKONCZONY)
        master_db_path: Ścieżka do master.sqlite (dla update statusu projektu)
    """
    if not is_milestone(rm_db_path, stage_code):
        raise ValueError(f"⚠️  {stage_code} nie jest milestone!")
    
    con = _open_rm_connection(rm_db_path)
    
    try:
        # Znajdź project_stage_id
        cursor = con.execute("""
            SELECT id FROM project_stages 
            WHERE project_id = ? AND stage_code = ?
        """, (project_id, stage_code))
        row = cursor.fetchone()
        
        if not row:
            raise ValueError(f"Milestone {stage_code} nie istnieje dla projektu {project_id}")
        
        project_stage_id = row[0]
        
        # 🔧 PRE-CHECK: Sprawdź aktywne etapy PRZED usunięciem (dla ZAKOŃCZONY)
        if stage_code == 'ZAKONCZONY':
            cursor = con.execute("""
                SELECT COUNT(*) as active_count
                FROM stage_actual_periods sap
                JOIN project_stages ps ON sap.project_stage_id = ps.id
                JOIN stage_definitions sd ON ps.stage_code = sd.code
                WHERE ps.project_id = ? AND sap.ended_at IS NULL
                  AND sd.is_milestone = 0 AND ps.stage_code != 'WSTRZYMANY'
            """, (project_id,))
            active_count_before = cursor.fetchone()[0]
        else:
            active_count_before = 0
        
        # Usuń wszystkie okresy dla tego milestone
        con.execute("""
            DELETE FROM stage_actual_periods
            WHERE project_stage_id = ?
        """, (project_stage_id,))
        
        # Usuń event z project_events
        con.execute("""
            DELETE FROM project_events
            WHERE project_id = ? AND event_type = ?
        """, (project_id, stage_code))
        
        con.commit()
        con.close()
        
        # ── Aktualizuj status projektu ─────────────────────────────────────
        if master_db_path:
            try:
                if stage_code == 'PRZYJETY':
                    # ACCEPTED → NEW
                    set_project_status(master_db_path, project_id, ProjectStatus.NEW)
                    
                elif stage_code == 'ZAKONCZONY':
                    # DONE → IN_PROGRESS (lub ACCEPTED jeśli żadne etapy były aktywne przed usunięciem)
                    if active_count_before > 0:
                        set_project_status(master_db_path, project_id, ProjectStatus.IN_PROGRESS)
                    else:
                        set_project_status(master_db_path, project_id, ProjectStatus.ACCEPTED)
                        
            except Exception as e:
                print(f"⚠️  Nie można zaktualizować statusu projektu: {e}")
        
        print(f"✅ MILESTONE UNSET: {stage_code} (project={project_id})")
        
    except Exception as e:
        con.close()
        raise


def can_start_stage(rm_db_path: str, project_id: int, stage_code: str, master_db_path: str = None) -> tuple:
    """Sprawdź czy etap może się rozpocząć (walidacja status + dependencies + PRZYJĘTY)
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt
        project_id: ID projektu
        stage_code: Kod etapu
        master_db_path: Opcjonalna ścieżka do master.sqlite (dla walidacji statusu)
    
    Returns:
        (can_start: bool, reason: str)
    """
    # ── STATE MACHINE: Walidacja statusu projektu ──────────────────────────
    if master_db_path:
        current_status = get_project_status(master_db_path, project_id)
        
        if current_status is None:
            # Stary schemat - brak kolumny project_status w master.sqlite
            # Fallback: sprawdź milestone
            if stage_code != 'PRZYJETY' and not is_milestone_set(rm_db_path, project_id, 'PRZYJETY'):
                return (False, "🚫 Projekt nie został przyjęty. Ustaw milestone PRZYJĘTY najpierw.")
        elif current_status == ProjectStatus.NEW:
            return (False, "🚫 Projekt nie przyjęty! Ustaw milestone PRZYJĘTY najpierw.")
        elif current_status == ProjectStatus.DONE:
            return (False, "🚫 Projekt już zakończony! Nie można rozpoczynać nowych etapów.")
        elif current_status == ProjectStatus.PAUSED:
            return (False, "🚫 Projekt wstrzymany! Wznów projekt przed rozpoczęciem etapu.")
    else:
        # Brak master_db_path - fallback do starej logiki
        if stage_code != 'PRZYJETY' and not is_milestone_set(rm_db_path, project_id, 'PRZYJETY'):
            return (False, "🚫 Projekt nie został przyjęty. Ustaw milestone PRZYJĘTY najpierw.")
    
    # Sprawdź czy etap już trwa
    active_stages = get_active_stages(rm_db_path, project_id)
    active_codes = [s['stage_code'] for s in active_stages]
    
    if stage_code in active_codes:
        return (False, f"🚫 Etap {stage_code} już trwa!")
    
    # 🔥 WALIDACJA ZALEŻNOŚCI (GRAF FS/SS)
    con = _open_rm_connection(rm_db_path)
    
    try:
        # Pobierz wszystkie zależności dla tego etapu (gdzie jest successorem)
        cursor = con.execute("""
            SELECT predecessor_stage_code, dependency_type, lag_days
            FROM stage_dependencies
            WHERE project_id = ? AND successor_stage_code = ?
        """, (project_id, stage_code))
        
        dependencies = cursor.fetchall()
        con.close()
        
        # Jeśli brak zależności - można uruchomić
        if not dependencies:
            return (True, "OK")
        
        # Sprawdź każdą zależność
        blocking_reasons = []
        
        for dep in dependencies:
            pred_code = dep['predecessor_stage_code']
            dep_type = dep['dependency_type']
            lag_days = dep['lag_days'] or 0
            
            if dep_type == 'FS':
                # 🔵 Finish-to-Start: poprzednik musi być zakończony
                if not is_stage_finished(rm_db_path, project_id, pred_code):
                    if not is_stage_started(rm_db_path, project_id, pred_code):
                        blocking_reasons.append(f"• {pred_code} (FS) - etap nie został rozpoczęty")
                    else:
                        blocking_reasons.append(f"• {pred_code} (FS) - etap nie został zakończony")
            
            elif dep_type == 'SS':
                # 🔵 Start-to-Start: poprzednik musi być rozpoczęty
                if not is_stage_started(rm_db_path, project_id, pred_code):
                    blocking_reasons.append(f"• {pred_code} (SS) - etap nie został rozpoczęty")
        
        # Zwróć wynik
        if blocking_reasons:
            # Deduplikacja komunikatów (na wypadek duplikatów w stage_dependencies)
            unique_reasons = list(dict.fromkeys(blocking_reasons))
            message = f"Nie można uruchomić etapu {stage_code}\n\nNiespełnione zależności:\n" + "\n".join(unique_reasons)
            return (False, message)
        
        return (True, "OK")
        
    except Exception as e:
        if con:
            con.close()
        return (False, f"Błąd sprawdzania zależności: {e}")


# ============================================================================
# GŁÓWNA FUNKCJA: Forecast (topological sort + graph analysis)
# ============================================================================

def recalculate_forecast(rm_db_path: str, project_id: int) -> Dict:
    """**SERCE SYSTEMU** - przelicza timeline całego projektu
    
    Algorytm:
        1. Pobiera graf zależności
        2. Topological sort (prawidłowa kolejność obliczeń)
        3. Dla każdego etapu:
           - Sprawdza zależności (FS/SS + lag)
           - Oblicza earliest_start
           - Oblicza forecast_end
        4. Uwzględnia rzeczywiste okresy
    
    Returns:
        {
            "PROJEKT": {
                "template_start": "2026-01-01",
                "template_end": "2026-01-05",
                "forecast_start": "2026-01-01",
                "forecast_end": "2026-01-07",
                "actual_periods": [...],
                "variance_days": +2,
                "is_active": False
            },
            ...
        }
    """
    con = _open_rm_connection(rm_db_path)
    
    # 1. Pobierz etapy projektu (tylko te które istnieją w stage_definitions)
    #    WSTRZYMANY to pauza/overlay - nie etap timeline
    cursor = con.execute("""
        SELECT ps.stage_code, ss.template_start, ss.template_end
        FROM project_stages ps
        LEFT JOIN stage_schedule ss ON ss.project_stage_id = ps.id
        JOIN stage_definitions sd ON ps.stage_code = sd.code
        WHERE ps.project_id = ? AND ps.stage_code != 'WSTRZYMANY'
        ORDER BY ps.sequence
    """, (project_id,))
    stages = {row['stage_code']: dict(row) for row in cursor.fetchall()}
    
    # 2. Pobierz zależności
    cursor = con.execute("""
        SELECT predecessor_stage_code, successor_stage_code, dependency_type, lag_days
        FROM stage_dependencies
        WHERE project_id = ?
    """, (project_id,))
    dependencies = [dict(row) for row in cursor.fetchall()]
    
    # 3. Pobierz rzeczywiste okresy
    cursor = con.execute("""
        SELECT ps.stage_code, sap.started_at, sap.ended_at
        FROM stage_actual_periods sap
        JOIN project_stages ps ON sap.project_stage_id = ps.id
        WHERE ps.project_id = ?
        ORDER BY sap.started_at
    """, (project_id,))
    actuals_rows = cursor.fetchall()
    
    # Grupuj po stage_code
    actuals = {}
    for row in actuals_rows:
        code = row['stage_code']
        if code not in actuals:
            actuals[code] = []
        actuals[code].append({
            'started_at': row['started_at'],
            'ended_at': row['ended_at']
        })
    
    con.close()
    
    # 4. Topological sort
    stage_order = _topological_sort(list(stages.keys()), dependencies)
    
    # 5. Oblicz forecast dla każdego etapu
    forecast = {}
    
    for stage_code in stage_order:
        template = stages.get(stage_code, {})
        periods = actuals.get(stage_code, [])
        
        # A. Jeśli etap się zakończył - użyj actual
        if periods and all(p['ended_at'] for p in periods):
            first_start = min(p['started_at'] for p in periods)
            last_end = max(p['ended_at'] for p in periods)
            
            forecast[stage_code] = {
                "template_start": template.get('template_start'),
                "template_end": template.get('template_end'),
                "forecast_start": first_start,
                "forecast_end": last_end,
                "actual_periods": periods,
                "is_active": False,
                "is_actual": True
            }
            continue
        
        # B. Jeśli etap trwa - użyj actual_start + template_duration
        if periods and any(p['ended_at'] is None for p in periods):
            active_period = next(p for p in periods if p['ended_at'] is None)
            
            # Oblicz duration z template
            if template.get('template_start') and template.get('template_end'):
                t_start = datetime.fromisoformat(template['template_start'])
                t_end = datetime.fromisoformat(template['template_end'])
                duration_days = (t_end - t_start).days
            else:
                duration_days = 5  # default
            
            start_dt = datetime.fromisoformat(active_period['started_at'])
            end_dt = start_dt + timedelta(days=duration_days)
            
            forecast[stage_code] = {
                "template_start": template.get('template_start'),
                "template_end": template.get('template_end'),
                "forecast_start": active_period['started_at'],
                "forecast_end": end_dt.isoformat(),
                "actual_periods": periods,
                "is_active": True,
                "is_actual": False
            }
            continue
        
        # C. Etap jeszcze nie rozpoczęty - oblicz forecast
        
        # ⭕ OPCJONALNE ETAPY: brak template_start i brak actuals → forecast = None
        # Etap nie jest zaplanowany przez użytkownika — nie pojawia się na wykresach.
        if not template.get('template_start') and not periods:
            forecast[stage_code] = {
                "template_start": None,
                "template_end": None,
                "forecast_start": None,
                "forecast_end": None,
                "actual_periods": periods,
                "is_active": False,
                "is_actual": False,
                "variance_days": 0
            }
            continue
        
        # Znajdź ograniczenia z zależności
        constraints = []
        
        for dep in dependencies:
            if dep['successor_stage_code'] != stage_code:
                continue
            
            pred_code = dep['predecessor_stage_code']
            pred = forecast.get(pred_code)
            if not pred:
                continue
            # Porzed poprzednik bez forecastu (opcjonalny, nieaktywowany) — pomiń
            if not pred.get('forecast_end') or not pred.get('forecast_start'):
                continue
            
            if dep['dependency_type'] == 'FS':
                # Finish-to-Start
                pred_end = datetime.fromisoformat(pred['forecast_end'])
                constraint = pred_end + timedelta(days=dep['lag_days'])
            elif dep['dependency_type'] == 'SS':
                # Start-to-Start
                pred_start = datetime.fromisoformat(pred['forecast_start'])
                constraint = pred_start + timedelta(days=dep['lag_days'])
            else:
                continue
            
            constraints.append(constraint)
        
        # Earliest start = max(template_start, wszystkie constraints)
        candidates = []
        if template.get('template_start'):
            candidates.append(datetime.fromisoformat(template['template_start']))
        if constraints:
            candidates.extend(constraints)
        
        if candidates:
            forecast_start = max(candidates)
        else:
            forecast_start = datetime.now()
        
        # Oblicz duration
        if template.get('template_start') and template.get('template_end'):
            t_start = datetime.fromisoformat(template['template_start'])
            t_end = datetime.fromisoformat(template['template_end'])
            duration_days = (t_end - t_start).days
        else:
            duration_days = 5
        
        forecast_end = forecast_start + timedelta(days=duration_days)
        
        forecast[stage_code] = {
            "template_start": template.get('template_start'),
            "template_end": template.get('template_end'),
            "forecast_start": forecast_start.date().isoformat() if hasattr(forecast_start, 'date') else forecast_start,
            "forecast_end": forecast_end.date().isoformat() if hasattr(forecast_end, 'date') else forecast_end,
            "actual_periods": periods,
            "is_active": False,
            "is_actual": False
        }
    
    # 6. Oblicz variance
    for stage_code, fc in forecast.items():
        if fc.get('template_start') and fc.get('template_end'):
            t_start = datetime.fromisoformat(fc['template_start'])
            t_end = datetime.fromisoformat(fc['template_end'])
            
            f_start = fc['forecast_start']
            f_end = fc['forecast_end']
            
            # Convert to datetime if string
            if isinstance(f_start, str):
                f_start = datetime.fromisoformat(f_start)
            if isinstance(f_end, str):
                f_end = datetime.fromisoformat(f_end)
            
            template_duration = (t_end - t_start).days
            forecast_duration = (f_end - f_start).days if hasattr(f_end, '__sub__') else template_duration
            
            fc['variance_days'] = forecast_duration - template_duration
        else:
            fc['variance_days'] = 0
    
    return forecast


def _topological_sort(stages: List[str], dependencies: List[Dict]) -> List[str]:
    """Topological sort etapów (dla prawidłowej kolejności obliczeń)"""
    # Build adjacency list
    graph = {stage: [] for stage in stages}
    in_degree = {stage: 0 for stage in stages}
    
    for dep in dependencies:
        pred = dep['predecessor_stage_code']
        succ = dep['successor_stage_code']
        if pred in graph and succ in graph:
            graph[pred].append(succ)
            in_degree[succ] += 1
    
    # Kahn's algorithm
    queue = deque([stage for stage in stages if in_degree[stage] == 0])
    result = []
    
    while queue:
        stage = queue.popleft()
        result.append(stage)
        
        for neighbor in graph[stage]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    
    # Jeśli cykl - zwróć stages w oryginalnej kolejności
    if len(result) != len(stages):
        print("⚠️  Wykryto cykl w zależnościach - używam sequential order")
        return stages
    
    return result


# ============================================================================
# Critical path analysis
# ============================================================================

def calculate_critical_path(rm_db_path: str, project_id: int) -> List[str]:
    """Identyfikuje ścieżkę krytyczną algorytmem CPM.
    
    Algorytm:
        1. Forward pass  → ES (Earliest Start), EF (Earliest Finish)
        2. Backward pass → LF (Latest Finish),  LS (Latest Start)
        3. Float = LS - ES
        4. Critical path = etapy z float = 0
    
    Returns:
        Lista kodów etapów na ścieżce krytycznej (w kolejności topologicznej)
    """
    forecast = recalculate_forecast(rm_db_path, project_id)

    con = _open_rm_connection(rm_db_path)
    deps = [dict(r) for r in con.execute("""
        SELECT predecessor_stage_code, successor_stage_code, dependency_type, lag_days
        FROM stage_dependencies WHERE project_id = ?
    """, (project_id,)).fetchall()]
    con.close()

    stages = list(forecast.keys())
    if not stages:
        return []

    # Czas trwania każdego etapu w dniach (z prognozy)
    durations = {}
    for code, fc in forecast.items():
        try:
            s = str(fc.get('forecast_start') or '')[:10]
            e = str(fc.get('forecast_end') or '')[:10]
            d = (datetime.fromisoformat(e) - datetime.fromisoformat(s)).days if s and e else 1
            durations[code] = max(d, 1)
        except Exception:
            durations[code] = 1

    order = _topological_sort(stages, deps)

    # ── FORWARD PASS ──────────────────────────
    ES = {s: 0 for s in stages}   # Earliest Start
    for stage in order:
        ef = ES[stage] + durations.get(stage, 1)   # Earliest Finish
        for dep in deps:
            if dep['predecessor_stage_code'] != stage:
                continue
            succ = dep['successor_stage_code']
            if succ not in ES:
                continue
            lag = dep.get('lag_days') or 0
            if dep['dependency_type'] == 'FS':
                ES[succ] = max(ES[succ], ef + lag)
            elif dep['dependency_type'] == 'SS':
                ES[succ] = max(ES[succ], ES[stage] + lag)

    EF = {s: ES[s] + durations.get(s, 1) for s in stages}
    project_end = max(EF.values())

    # ── BACKWARD PASS ───────────────────────
    LF = {s: project_end for s in stages}  # Latest Finish
    for stage in reversed(order):
        ls = LF[stage] - durations.get(stage, 1)   # Latest Start
        for dep in deps:
            if dep['successor_stage_code'] != stage:
                continue
            pred = dep['predecessor_stage_code']
            if pred not in LF:
                continue
            lag = dep.get('lag_days') or 0
            if dep['dependency_type'] == 'FS':
                # LF[pred] <= LS[succ] - lag
                LF[pred] = min(LF[pred], ls - lag)
            elif dep['dependency_type'] == 'SS':
                # LS[pred] <= LS[succ] - lag  ⇒  LF[pred] <= LS[succ] - lag + dur[pred]
                LF[pred] = min(LF[pred], ls - lag + durations.get(pred, 1))

    LS = {s: LF[s] - durations.get(s, 1) for s in stages}  # Latest Start

    # ── FLOAT → Ścieżka krytyczna (float == 0) ──────
    critical = [s for s in order if (LS[s] - ES[s]) <= 0]
    return critical if critical else order


def get_critical_path_details(rm_db_path: str, project_id: int) -> List[Dict]:
    """Zwraca szczegóły CPM: ES, EF, LS, LF, float dla każdego etapu."""
    forecast = recalculate_forecast(rm_db_path, project_id)

    con = _open_rm_connection(rm_db_path)
    deps = [dict(r) for r in con.execute("""
        SELECT predecessor_stage_code, successor_stage_code, dependency_type, lag_days
        FROM stage_dependencies WHERE project_id = ?
    """, (project_id,)).fetchall()]
    con.close()

    stages = list(forecast.keys())
    if not stages:
        return []

    durations = {}
    for code, fc in forecast.items():
        try:
            s = str(fc.get('forecast_start') or '')[:10]
            e = str(fc.get('forecast_end') or '')[:10]
            d = (datetime.fromisoformat(e) - datetime.fromisoformat(s)).days if s and e else 1
            durations[code] = max(d, 1)
        except Exception:
            durations[code] = 1

    order = _topological_sort(stages, deps)

    ES = {s: 0 for s in stages}
    for stage in order:
        ef = ES[stage] + durations.get(stage, 1)
        for dep in deps:
            if dep['predecessor_stage_code'] != stage:
                continue
            succ = dep['successor_stage_code']
            if succ not in ES:
                continue
            lag = dep.get('lag_days') or 0
            if dep['dependency_type'] == 'FS':
                ES[succ] = max(ES[succ], ef + lag)
            elif dep['dependency_type'] == 'SS':
                ES[succ] = max(ES[succ], ES[stage] + lag)

    EF = {s: ES[s] + durations.get(s, 1) for s in stages}
    project_end = max(EF.values())

    LF = {s: project_end for s in stages}
    for stage in reversed(order):
        ls = LF[stage] - durations.get(stage, 1)
        for dep in deps:
            if dep['successor_stage_code'] != stage:
                continue
            pred = dep['predecessor_stage_code']
            if pred not in LF:
                continue
            lag = dep.get('lag_days') or 0
            if dep['dependency_type'] == 'FS':
                LF[pred] = min(LF[pred], ls - lag)
            elif dep['dependency_type'] == 'SS':
                LF[pred] = min(LF[pred], ls - lag + durations.get(pred, 1))

    LS = {s: LF[s] - durations.get(s, 1) for s in stages}

    result = []
    for stage in order:
        total_float = LS[stage] - ES[stage]
        result.append({
            'stage_code': stage,
            'duration': durations.get(stage, 1),
            'ES': ES[stage],
            'EF': EF[stage],
            'LS': LS[stage],
            'LF': LF[stage],
            'total_float': total_float,
            'is_critical': total_float <= 0,
        })
    return result


# ============================================================================
# Migracja / korekta danych
# ============================================================================

# Kanoniczy zestaw etapów z właściwymi numerami sekwencji
CANONICAL_STAGES = [
    ('PRZYJETY',      1),
    ('PROJEKT',       2),
    ('ELEKTROPROJEKT', 3),
    ('KOMPLETACJA',   4),
    ('MONTAZ',        5),
    ('ELEKTROMONTAZ', 6),
    ('URUCHOMIENIE',  7),
    ('ODBIORY',       8),
    ('POPRAWKI',      9),
    ('WSTRZYMANY',   10),
    ('ZAKONCZONY',   11),
]


def ensure_default_dependencies_for_project(rm_db_path: str, project_id: int) -> int:
    """🔗 Dodaje domyślne zależności workflow dla projektu
    
    Bezpieczne: używa INSERT OR IGNORE, nie nadpisuje istniejących dependency.
    Można wywołać wielokrotnie - doda tylko te które brakują.
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt
        project_id: ID projektu
        
    Returns:
        Liczba dodanych zależności
    """
    con = _open_rm_connection(rm_db_path)
    
    added = 0
    for from_stage, to_stage, dep_type, lag in DEFAULT_DEPENDENCIES:
        cursor = con.execute("""
            INSERT OR IGNORE INTO stage_dependencies 
            (project_id, predecessor_stage_code, successor_stage_code, dependency_type, lag_days)
            VALUES (?, ?, ?, ?, ?)
        """, (project_id, from_stage, to_stage, dep_type, lag))
        
        if cursor.rowcount > 0:
            added += 1
    
    con.commit()
    con.close()
    
    if added > 0:
        print(f"✅ Projekt {project_id}: dodano {added} domyślnych zależności workflow")
    
    return added


def ensure_all_stages_for_all_projects(rm_db_path: str) -> dict:
    """Dodaje brakujące etapy do WSZYSTKICH projektów w rm_manager.sqlite.

    Bezpieczne: używa INSERT OR IGNORE, nie rusza istniejących danych.
    Tworzy też puste wpisy w stage_schedule dla nowych etapów.

    Returns:
        {'projects_updated': int, 'stages_added': int}
    """
    con = _open_rm_connection(rm_db_path)

    project_ids = [r[0] for r in con.execute(
        "SELECT DISTINCT project_id FROM project_stages"
    ).fetchall()]

    stages_added = 0
    schedules_added = 0
    for pid in project_ids:
        for code, seq in CANONICAL_STAGES:
            cur = con.execute(
                "INSERT OR IGNORE INTO project_stages (project_id, stage_code, sequence) VALUES (?, ?, ?)",
                (pid, code, seq)
            )
            if cur.rowcount > 0:
                stages_added += 1
                # Pobierz ID nowo dodanego project_stage
                ps_id = con.execute(
                    "SELECT id FROM project_stages WHERE project_id = ? AND stage_code = ?",
                    (pid, code)
                ).fetchone()[0]
                # Dodaj pusty wpis w stage_schedule
                con.execute(
                    "INSERT OR IGNORE INTO stage_schedule (project_stage_id) VALUES (?)",
                    (ps_id,)
                )
                schedules_added += 1
            else:
                # Etap już istnieje - upewnij się że ma stage_schedule
                ps_row = con.execute(
                    "SELECT id FROM project_stages WHERE project_id = ? AND stage_code = ?",
                    (pid, code)
                ).fetchone()
                if ps_row:
                    existing_sched = con.execute(
                        "SELECT id FROM stage_schedule WHERE project_stage_id = ?",
                        (ps_row[0],)
                    ).fetchone()
                    if not existing_sched:
                        con.execute(
                            "INSERT INTO stage_schedule (project_stage_id) VALUES (?)",
                            (ps_row[0],)
                        )
                        schedules_added += 1

    con.commit()
    con.close()
    print(f"✅ ensure_all_stages: {len(project_ids)} projektów, dodano {stages_added} etapów, {schedules_added} schedule")
    return {'projects_updated': len(project_ids), 'stages_added': stages_added}


def migrate_milestones_to_instant(rm_db_path: str) -> dict:
    """Migracja: zmienia PRZYJĘTY i ZAKOŃCZONY na instant (ended_at = started_at).
    
    OPCJA C: minimalna zmiana dla istniejących projektów gdzie PRZYJĘTY/ZAKOŃCZONY
    były traktowane jako etapy z czasem trwania.
    
    Po migracji:
    - PRZYJĘTY: started_at = ended_at (instant)
    - ZAKOŃCZONY: started_at = ended_at (instant)
    
    Returns:
        {'periods_updated': int, 'projects_affected': int}
    """
    con = _open_rm_connection(rm_db_path)
    
    # Znajdź wszystkie okresy dla milestones które mają ended_at != started_at
    cursor = con.execute("""
        SELECT sap.id, sap.started_at, ps.project_id, ps.stage_code
        FROM stage_actual_periods sap
        JOIN project_stages ps ON sap.project_stage_id = ps.id
        WHERE ps.stage_code IN ('PRZYJETY', 'ZAKONCZONY')
          AND (sap.ended_at IS NULL OR sap.ended_at != sap.started_at)
    """)
    
    periods = cursor.fetchall()
    project_ids = set()
    
    for period in periods:
        period_id = period['id']
        started_at = period['started_at']
        project_id = period['project_id']
        stage_code = period['stage_code']
        
        # Ustaw ended_at = started_at (instant)
        con.execute("""
            UPDATE stage_actual_periods
            SET ended_at = ?
            WHERE id = ?
        """, (started_at, period_id))
        
        project_ids.add(project_id)
        print(f"  🔄 {stage_code} (projekt {project_id}): ustawiono jako instant @ {started_at}")
    
    con.commit()
    con.close()
    
    print(f"✅ migrate_milestones: {len(periods)} okresów, {len(project_ids)} projektów")
    return {'periods_updated': len(periods), 'projects_affected': len(project_ids)}


def fix_stage_sequence_for_all_projects(rm_db_path: str) -> dict:
    """Aktualizuje sequence dla WSZYSTKICH istniejących etapów zgodnie z CANONICAL_STAGES.
    
    Bezpieczne: aktualizuje tylko kolumnę sequence, nie rusza innych danych.
    
    Returns:
        {'projects_updated': int, 'stages_updated': int}
    """
    con = _open_rm_connection(rm_db_path)
    
    # Pobierz wszystkie unikalne project_id
    project_ids = [r[0] for r in con.execute(
        "SELECT DISTINCT project_id FROM project_stages"
    ).fetchall()]
    
    # Stwórz mapę code -> sequence z CANONICAL_STAGES
    canonical_seq_map = {code: seq for code, seq in CANONICAL_STAGES}
    
    stages_updated = 0
    for pid in project_ids:
        print(f"  📋 Projekt {pid}:")
        # Pokaż przed aktualizacją
        before = con.execute("""
            SELECT stage_code, sequence 
            FROM project_stages 
            WHERE project_id = ? 
            ORDER BY sequence
        """, (pid,)).fetchall()
        print(f"      PRZED: {[(r['stage_code'], r['sequence']) for r in before]}")
        
        # Aktualizuj
        for code, seq in CANONICAL_STAGES:
            cur = con.execute("""
                UPDATE project_stages 
                SET sequence = ? 
                WHERE project_id = ? AND stage_code = ?
            """, (seq, pid, code))
            if cur.rowcount > 0:
                stages_updated += 1
        
        # Pokaż po aktualizacji
        after = con.execute("""
            SELECT stage_code, sequence 
            FROM project_stages 
            WHERE project_id = ? 
            ORDER BY sequence
        """, (pid,)).fetchall()
        print(f"      PO:    {[(r['stage_code'], r['sequence']) for r in after]}")
    
    con.commit()
    con.close()
    print(f"✅ fix_stage_sequence: {len(project_ids)} projektów, zaktualizowano {stages_updated} etapów")
    return {'projects_updated': len(project_ids), 'stages_updated': stages_updated}


# ============================================================================
# Synchronizacja z MASTER.SQLITE (dla RM_BAZA)
# ============================================================================

def determine_display_status(rm_db_path: str, project_id: int) -> str:
    """Określ jaki status pokazać w RM_BAZA (uproszczony)
    
    🚀 NOWA LOGIKA: Sprawdza pauzy przez project_pauses, nie aktywne etapy
    
    Logika:
        - Jeśli ma aktywną pauzę → WSTRZYMANY
        - Inne aktywne → najwyższy priorytet
        - Brak aktywnych → ostatni zakończony
    """
    # 🚀 Sprawdź czy projekt jest w pauzie (overlay)
    if is_project_paused(rm_db_path, project_id):
        return 'WSTRZYMANY'
    
    active = get_active_stages(rm_db_path, project_id)
    
    if not active:
        # Brak aktywnych - ostatni zakończony
        con = _open_rm_connection(rm_db_path)
        
        cursor = con.execute("""
            SELECT ps.stage_code
            FROM stage_actual_periods sap
            JOIN project_stages ps ON sap.project_stage_id = ps.id
            WHERE ps.project_id = ? AND sap.ended_at IS NOT NULL
            ORDER BY sap.ended_at DESC
            LIMIT 1
        """, (project_id,))
        
        row = cursor.fetchone()
        con.close()
        
        return row[0] if row else 'PRZYJETY'
    
    # 🚀 Zwróć etap z najwyższym priorytetem (bez sprawdzania WSTRZYMANY w active)
    active_sorted = sorted(active, key=lambda x: STAGE_PRIORITY.get(x['stage_code'], 0), reverse=True)
    return active_sorted[0]['stage_code']


def get_stage_display_name(stage_code: str) -> str:
    """Mapuj kod etapu na polską nazwę wyświetlaną
    
    Args:
        stage_code: Kod etapu (np. 'MONTAZ')
        
    Returns:
        Display name (np. 'Montaż')
    """
    for code, display_name, _, _ in STAGE_DEFINITIONS:
        if code == stage_code:
            return display_name
    return stage_code  # Fallback


def get_first_montaz_date(rm_db_path: str, project_id: int) -> str:
    """Pobierz planowaną datę MONTAŻ z szablonu dla synchronizacji z RM_BAZA
    
    UWAGA: Zwraca TYLKO datę z szablonu (template_start), nie rzeczywistą datę rozpoczęcia!
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt
        project_id: ID projektu
        
    Returns:
        Data w formacie YYYY-MM-DD z szablonu lub None jeśli brak szablonu
    """
    con = _open_rm_connection(rm_db_path)
    
    # Pobierz planowaną datę z szablonu
    cursor = con.execute("""
        SELECT ss.template_start
        FROM stage_schedule ss
        JOIN project_stages ps ON ss.project_stage_id = ps.id
        WHERE ps.project_id = ? AND ps.stage_code = 'MONTAZ'
        LIMIT 1
    """, (project_id,))
    
    row = cursor.fetchone()
    con.close()
    
    if row and row['template_start']:
        template_date = row['template_start']
        if len(template_date) >= 10:
            return template_date[:10]
        return template_date
    
    return None


def sync_to_master(rm_db_path: str, master_db_path: str, project_id: int):
    """Synchronizuj dane z RM_MANAGER → MASTER.SQLITE (RM_BAZA)
    
    🔄 NOWA WERSJA (2026-04-12):
    Synchronizuje 5 kolumn do master.sqlite dla wyświetlania w RM_BAZA:
    
    1. status TEXT - status projektu:
       - "Zakończony" (ZAKOŃCZONY milestone)
       - "Wstrzymany" (WSTRZYMANY aktywny)
       - Nazwa etapu (najdalszy aktywny etap: "Projekt", "Montaż", etc.)
       - "Przyjęty" (PRZYJĘTY milestone, brak aktywnych)
       - "Nowy" (projekt nie przyjęty)
    
    2. designer TEXT - konstruktor (pracownik przypisany do etapu PROJEKT)
       - Pobierany z stage_schedule.employee_id (etap PROJEKT)
    
    3. montaz TEXT (lub sat) - pierwsza data rozpoczęcia MONTAŻ (YYYY-MM-DD)
       - WRITE ONCE: raz wpisany, nigdy nie nadpisuj
       - Dla pracowników produkcyjnych (kiedy zaczyna się montaż)
    
    4. fat TEXT - data milestone FAT (YYYY-MM-DD)
       - Czytana z stage_schedule.template_start
    
    5. completed_at TEXT - data milestone TRANSPORT (YYYY-MM-DD)
       - Czytana z stage_schedule.template_start
    
    Args:
        rm_db_path: Ścieżka do bazy per-projekt RM_MANAGER
        master_db_path: Ścieżka do master.sqlite (współdzielony z RM_BAZA)
        project_id: ID projektu
    """
    master_path = Path(master_db_path)
    if not master_path.exists():
        print(f"⚠️  master.sqlite nie istnieje: {master_path}")
        return
    
    # 1. Określ status - priorytet:
    #    1. ZAKOŃCZONY (milestone) -> "Zakończony"
    #    2. WSTRZYMANY (aktywny) -> "Wstrzymany"
    #    3. Inne aktywne etapy (najwyższy priorytet) -> nazwa etapu
    #    4. PRZYJĘTY (milestone, brak aktywnych) -> "Przyjęty"
    #    5. NULL (projekt nie przyjęty)
    
    status_text = None
    
    # Sprawdź ZAKOŃCZONY (najwyższy priorytet)
    if is_milestone_set(rm_db_path, project_id, 'ZAKONCZONY'):
        status_text = "Zakończony"
    
    else:
        # Sprawdź aktywne etapy
        active_stages = get_active_stages(rm_db_path, project_id)
        
        if active_stages:
            # Sprawdź czy WSTRZYMANY jest aktywny (drugi priorytet)
            wstrzymany_active = any(s['stage_code'] == 'WSTRZYMANY' for s in active_stages)
            
            if wstrzymany_active:
                status_text = "Wstrzymany"
            else:
                # Najdalszy aktywny etap (poza WSTRZYMANY)
                non_wstrzymany = [s for s in active_stages if s['stage_code'] != 'WSTRZYMANY']
                if non_wstrzymany:
                    active_sorted = sorted(non_wstrzymany, 
                                         key=lambda x: STAGE_PRIORITY.get(x['stage_code'], 0), 
                                         reverse=True)
                    top_stage_code = active_sorted[0]['stage_code']
                    status_text = get_stage_display_name(top_stage_code)
        
        else:
            # Brak aktywnych etapów - sprawdź czy PRZYJĘTY
            if is_milestone_set(rm_db_path, project_id, 'PRZYJETY'):
                status_text = "Przyjęty"
            else:
                # Projekt nie przyjęty - nowy projekt
                status_text = "Nowy"
    
    # 2. Montaż - pierwsza data rozpoczęcia (WRITE ONCE)
    montaz_date = get_first_montaz_date(rm_db_path, project_id)
    
    # 2b. Konstruktor - pracownik przypisany do etapu PROJEKT (pierwsza osoba)
    designer_name = None
    try:
        # Czytaj z assigned_staff (JSON w project_stages)
        assigned_staff = get_stage_assigned_staff(rm_db_path, 
                                                   Path(rm_db_path).parent.parent / "rm_manager.sqlite",
                                                   project_id, 'PROJEKT')
        if assigned_staff and len(assigned_staff) > 0:
            # Weź pierwszego pracownika z listy
            designer_name = assigned_staff[0]['employee_name']
    except Exception as e:
        print(f"⚠️  Błąd pobierania konstruktora: {e}")
    
    # 3. FAT - czytaj z stage_schedule (template_start)
    fat_date = None
    con_peek = _open_rm_connection(rm_db_path)
    
    cursor = con_peek.execute("""
        SELECT ss.template_start
        FROM stage_schedule ss
        JOIN project_stages ps ON ss.project_stage_id = ps.id
        WHERE ps.project_id = ? AND ps.stage_code = 'FAT'
    """, (project_id,))
    row = cursor.fetchone()
    if row and row['template_start']:
        fat_date = row['template_start'][:10]  # YYYY-MM-DD
    
    # 4. Transport/Odbiór - czytaj z stage_schedule (template_start)
    completed_date = None
    cursor = con_peek.execute("""
        SELECT ss.template_start
        FROM stage_schedule ss
        JOIN project_stages ps ON ss.project_stage_id = ps.id
        WHERE ps.project_id = ? AND ps.stage_code = 'TRANSPORT'
    """, (project_id,))
    row = cursor.fetchone()
    if row and row['template_start']:
        completed_date = row['template_start'][:10]  # YYYY-MM-DD
    
    con_peek.close()
    
    # Połączenie z master.sqlite
    con = _open_rm_connection(str(master_path))
    
    try:
        # Sprawdź obecne wartości (dla WRITE ONCE logic)
        # Najpierw sprawdź które kolumny istnieją
        cursor = con.execute("PRAGMA table_info(projects)")
        columns = {col[1] for col in cursor.fetchall()}
        
        existing_montaz = None
        if 'montaz' in columns:
            cursor = con.execute("SELECT montaz FROM projects WHERE project_id = ?", (project_id,))
            row = cursor.fetchone()
            if row:
                existing_montaz = row['montaz']
        elif 'sat' in columns:
            cursor = con.execute("SELECT sat FROM projects WHERE project_id = ?", (project_id,))
            row = cursor.fetchone()
            if row:
                existing_montaz = row['sat']
        
        # BUILD UPDATE dynamically (tylko kolumny które istnieją)
        updates = []
        params = []
        
        # Status - zawsze aktualizuj (jeśli jest wartość)
        if status_text:
            updates.append("status = ?")
            params.append(status_text)
        
        # Montaż - WRITE ONCE (tylko jeśli puste)
        if montaz_date and not existing_montaz:
            # Kolumny już sprawdzone powyżej
            if 'montaz' in columns:
                updates.append("montaz = ?")
                params.append(montaz_date)
            elif 'sat' in columns:
                updates.append("sat = ?")
                params.append(montaz_date)
        
        # Konstruktor (designer) - nadpisuj zawsze (może się zmienić)
        if designer_name and 'designer' in columns:
            updates.append("designer = ?")
            params.append(designer_name)
        
        # FAT - nadpisuj zawsze (może się zmienić)
        if fat_date:
            updates.append("fat = ?")
            params.append(fat_date)
        
        # Odbiór (completed_at) - nadpisuj zawsze
        if completed_date:
            updates.append("completed_at = ?")
            params.append(completed_date)
        
        # Wykonaj UPDATE jeśli są zmiany
        if updates:
            params.append(project_id)
            sql = f"UPDATE projects SET {', '.join(updates)} WHERE project_id = ?"
            con.execute(sql, params)
            con.commit()
            
            print(f"✅ SYNC → master.sqlite (projekt {project_id}):")
            print(f"   • status: {status_text}")
            print(f"   • designer: {designer_name}")
            print(f"   • montaz: {montaz_date} (existing: {existing_montaz})")
            print(f"   • fat: {fat_date}")
            print(f"   • completed_at: {completed_date}")
        else:
            print(f"ℹ️  SYNC: Brak zmian dla projektu {project_id}")
        
    except Exception as e:
        con.rollback()
        print(f"❌ Błąd sync_to_master (projekt {project_id}): {e}")
        import traceback
        traceback.print_exc()
    finally:
        con.close()


def get_last_sync_date(rm_master_db_path: str) -> str:
    """Pobierz datę ostatniej synchronizacji
    
    Args:
        rm_master_db_path: Ścieżka do rm_manager.sqlite (MASTER)
        
    Returns:
        Data w formacie YYYY-MM-DD lub None jeśli nigdy nie synchronizowano
    """
    con = _open_rm_connection(rm_master_db_path)
    
    cursor = con.execute("""
        SELECT sync_date
        FROM sync_log
        ORDER BY id DESC
        LIMIT 1
    """)
    
    row = cursor.fetchone()
    con.close()
    
    return row['sync_date'] if row else None


def should_sync_today(rm_master_db_path: str) -> bool:
    """Sprawdź czy dzisiejsza synchronizacja jest potrzebna
    
    Args:
        rm_master_db_path: Ścieżka do rm_manager.sqlite (MASTER)
        
    Returns:
        True jeśli nie było synchronizacji dzisiaj
    """
    last_sync = get_last_sync_date(rm_master_db_path)
    today = datetime.now().strftime("%Y-%m-%d")
    
    return last_sync != today


def record_sync(rm_master_db_path: str, projects_synced: int, user: str = None, notes: str = None):
    """Zapisz wpis o synchronizacji w sync_log
    
    Args:
        rm_master_db_path: Ścieżka do rm_manager.sqlite (MASTER)
        projects_synced: Liczba zsynchronizowanych projektów
        user: Użytkownik który uruchomił sync (opcjonalnie)
        notes: Notatki (opcjonalnie)
    """
    con = _open_rm_connection(rm_master_db_path)
    
    now = datetime.now()
    sync_date = now.strftime("%Y-%m-%d")
    sync_timestamp = now.strftime("%Y-%m-%d %H:%M")
    
    con.execute("""
        INSERT INTO sync_log (sync_date, sync_timestamp, projects_synced, user, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (sync_date, sync_timestamp, projects_synced, user, notes))
    
    con.commit()
    con.close()
    
    print(f"📝 Zapisano sync_log: {sync_date} {sync_timestamp}, projektów: {projects_synced}")


def sync_all_projects(rm_master_db_path: str, rm_projects_dir: str, master_db_path: str, user: str = None, lock_manager=None):
    """Synchronizuj wszystkie projekty z RM_MANAGER → master.sqlite
    
    ⚠️  UWAGA WSPÓŁBIEŻNOŚĆ: Synchronizuje tylko projekty które NIE są zlockowane przez innych.
    Projekty z lockiem są pomijane aby uniknąć nadpisania danych edytowanych przez innych użytkowników.
    
    Args:
        rm_master_db_path: Ścieżka do rm_manager.sqlite (MASTER)
        rm_projects_dir: Ścieżka do katalogu z bazami projektów (RM_MANAGER_projects)
        master_db_path: Ścieżka do master.sqlite (współdzielony z RM_BAZA)
        user: Użytkownik który uruchomił sync (opcjonalnie)
        lock_manager: Opcjonalny LockManager do sprawdzania locków (aby uniknąć race conditions)
        
    Returns:
        int: Liczba zsynchronizowanych projektów
    """
    # Pobierz wszystkie projekty z RM_MANAGER
    con = _open_rm_connection(rm_master_db_path)
    
    # Pobierz listę projektów z project_file_tracking (tylko poprawne)
    cursor = con.execute("""
        SELECT project_id
        FROM project_file_tracking
        WHERE verification_status = 'OK'
    """)
    project_ids = [row['project_id'] for row in cursor.fetchall()]
    con.close()
    
    if not project_ids:
        print("⚠️  Brak projektów do synchronizacji (project_file_tracking puste lub wszystkie niezweryfikowane)")
        return 0
    
    # Synchronizuj każdy projekt
    synced_count = 0
    skipped_locked = 0
    for project_id in project_ids:
        try:
            # Sprawdź czy projekt jest zlockowany przez innego użytkownika
            if lock_manager:
                lock_info = lock_manager.get_project_lock_owner(project_id)
                if lock_info and lock_info.get('user') != user:
                    # Projekt edytowany przez innego użytkownika - pomiń
                    print(f"⏭️  Pominięto projekt {project_id}: zlockowany przez {lock_info.get('user')}")
                    skipped_locked += 1
                    continue
            
            # Ścieżka do per-project database (używamy rm_projects_dir z GUI)
            rm_project_db = str(Path(rm_projects_dir) / f"rm_manager_project_{project_id}.sqlite")
            
            if not Path(rm_project_db).exists():
                print(f"⚠️  Pominięto projekt {project_id}: baza nie istnieje ({rm_project_db})")
                continue
            
            sync_to_master(rm_project_db, master_db_path, project_id)
            synced_count += 1
            
        except Exception as e:
            print(f"⚠️  Błąd sync projektu {project_id}: {e}")
            import traceback
            traceback.print_exc()
    
    # Zapisz wpis do sync_log
    notes = f"Auto-sync: {synced_count} OK, {skipped_locked} zlockowanych"
    record_sync(rm_master_db_path, synced_count, user, notes=notes)
    
    print(f"✅ SYNC ALL: {synced_count}/{len(project_ids)} projektów zaktualizowanych, {skipped_locked} pominiętych (lock)")
    return synced_count


# ============================================================================
# Analiza i statystyki
# ============================================================================

def get_stage_variance(rm_db_path: str, project_id: int, stage_code: str) -> Dict:
    """Oblicza odchylenie dla etapu"""
    forecast = recalculate_forecast(rm_db_path, project_id)
    stage_fc = forecast.get(stage_code, {})
    
    return {
        "variance_days": stage_fc.get('variance_days', 0),
        "variance_percent": 0,  # TODO: calculate
        "template_start": stage_fc.get('template_start'),
        "template_end": stage_fc.get('template_end'),
        "forecast_start": stage_fc.get('forecast_start'),
        "forecast_end": stage_fc.get('forecast_end'),
    }


def get_project_status_summary(rm_db_path: str, project_id: int) -> Dict:
    """Generuje podsumowanie dla dashboard"""
    forecast = recalculate_forecast(rm_db_path, project_id)
    active = get_active_stages(rm_db_path, project_id)
    
    # Oblicz overall variance
    total_variance = sum(fc.get('variance_days', 0) for fc in forecast.values())
    
    # Status
    if total_variance > 10:
        status = "DELAYED"
    elif total_variance > 5:
        status = "AT_RISK"
    else:
        status = "ON_TRACK"
    
    # Completion forecast
    completion_dates = [fc['forecast_end'] for fc in forecast.values() if fc.get('forecast_end')]
    completion_forecast = max(completion_dates) if completion_dates else None
    
    # Pause info
    paused = is_project_paused(rm_db_path, project_id)
    pauses = get_project_pauses(rm_db_path, project_id)
    
    return {
        "status": status,
        "overall_variance_days": total_variance,
        "completion_forecast": completion_forecast,
        "active_stages": [s['stage_code'] for s in active],
        "critical_path_status": "UNKNOWN",
        "is_paused": paused,
        "pauses": pauses,
    }


def get_stage_timeline(rm_db_path: str, project_id: int) -> List[Dict]:
    """Zwraca kompletny timeline dla GUI (wizualizacja Gantt)"""
    forecast = recalculate_forecast(rm_db_path, project_id)
    
    timeline = []
    for stage_code, fc in forecast.items():
        timeline.append({
            "stage_code": stage_code,
            "template_start": fc.get('template_start'),
            "template_end": fc.get('template_end'),
            "forecast_start": fc.get('forecast_start'),
            "forecast_end": fc.get('forecast_end'),
            "actual_periods": fc.get('actual_periods', []),
            "variance_days": fc.get('variance_days', 0),
            "is_active": fc.get('is_active', False),
            "is_critical_path": False  # TODO: calculate
        })
    
    return timeline


# ============================================================================
# Zdarzenia (opcjonalnie)
# ============================================================================

def add_stage_event(rm_db_path: str, project_id: int, stage_code: str, 
                   event_type: str, description: str, created_by: str = None):
    """Dodaje zdarzenie do etapu"""
    con = _open_rm_connection(rm_db_path)
    
    try:
        # Znajdź project_stage_id
        cursor = con.execute("""
            SELECT id FROM project_stages
            WHERE project_id = ? AND stage_code = ?
        """, (project_id, stage_code))
        row = cursor.fetchone()
        
        if not row:
            raise ValueError(f"Etap {stage_code} nie istnieje")
        
        project_stage_id = row[0]
        
        con.execute("""
            INSERT INTO stage_events 
            (project_stage_id, event_type, description, created_by)
            VALUES (?, ?, ?, ?)
        """, (project_stage_id, event_type, description, created_by))
        
        con.commit()
        print(f"✅ Event: {event_type} dla {stage_code}")
        
    finally:
        con.close()


def get_stage_events(rm_db_path: str, project_id: int, stage_code: str = None) -> List[Dict]:
    """Zwraca historię zdarzeń"""
    con = _open_rm_connection(rm_db_path)
    
    if stage_code:
        cursor = con.execute("""
            SELECT se.*, ps.stage_code
            FROM stage_events se
            JOIN project_stages ps ON se.project_stage_id = ps.id
            WHERE ps.project_id = ? AND ps.stage_code = ?
            ORDER BY se.event_date DESC
        """, (project_id, stage_code))
    else:
        cursor = con.execute("""
            SELECT se.*, ps.stage_code
            FROM stage_events se
            JOIN project_stages ps ON se.project_stage_id = ps.id
            WHERE ps.project_id = ?
            ORDER BY se.event_date DESC
        """, (project_id,))
    
    rows = cursor.fetchall()
    con.close()
    
    return [dict(row) for row in rows]


# ===========================================================================
# Użytkownicy – odczyt z master RM_BAZA + uprawnienia RM_MANAGER
# ===========================================================================

def get_users_from_baza(master_baza_path: str) -> List[Dict]:
    """Pobierz aktywnych użytkowników z master.sqlite RM_BAZA (read-only).
    Zwraca listę słowników: id, username, display_name, role, password_hash.
    """
    if not Path(master_baza_path).exists():
        return []
    try:
        con = _open_rm_connection(f"file:{master_baza_path}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT id, username, display_name, role, password_hash "
            "FROM users WHERE is_active = 1 ORDER BY username"
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"⚠️  get_users_from_baza: {e}")
        return []


def get_user_permissions(rm_master_db_path: str, role: str) -> Dict:
    """Pobierz uprawnienia dla danej roli z rm_manager.sqlite.
    Zwraca dict: {can_start_stage: bool, can_end_stage: bool, ...}
    Fallback: GUEST (wszystko False) gdy rola nieznana lub plik niedostępny.
    """
    fallback = {
        'can_start_stage': False,
        'can_end_stage': False,
        'can_edit_dates': False,
        'can_sync_master': False,
        'can_critical_path': False,
        'can_manage_permissions': False,
    }
    try:
        if not Path(rm_master_db_path).exists():
            return fallback
        con = _open_rm_connection(rm_master_db_path)
        row = con.execute(
            "SELECT * FROM rm_user_permissions WHERE role = ?", (role,)
        ).fetchone()
        con.close()
        if row:
            result = {k: bool(row[k]) for k in fallback}
            # SAFETY: ADMIN zawsze ma can_manage_permissions
            if role == 'ADMIN':
                result['can_manage_permissions'] = True
            return result
        # Brak wiersza dla roli – ADMIN dostaje pełne uprawnienia
        if role == 'ADMIN':
            return {k: True for k in fallback}
        return fallback
    except Exception as e:
        print(f"⚠️  get_user_permissions: {e}")
        # SAFETY: nawet przy błędzie ADMIN nie traci dostępu
        if role == 'ADMIN':
            return {k: True for k in fallback}
        return fallback


def get_all_role_permissions(rm_master_db_path: str) -> List[Dict]:
    """Pobierz uprawnienia wszystkich ról (dla dialogu edycji).
    Zwraca listę słowników posortowaną po roli.
    """
    try:
        if not Path(rm_master_db_path).exists():
            return []
        con = _open_rm_connection(rm_master_db_path)
        rows = con.execute(
            "SELECT * FROM rm_user_permissions ORDER BY role"
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"⚠️  get_all_role_permissions: {e}")
        return []


def set_role_permissions(rm_master_db_path: str, role: str, permissions: Dict):
    """Zapisz / zaktualizuj uprawnienia roli w rm_manager.sqlite.
    permissions = {can_start_stage: bool, can_end_stage: bool, ...}
    """
    con = _open_rm_connection(rm_master_db_path)
    try:
        con.execute("""
            INSERT INTO rm_user_permissions
                (role, can_start_stage, can_end_stage, can_edit_dates,
                 can_sync_master, can_critical_path, can_manage_permissions, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(role) DO UPDATE SET
                can_start_stage     = excluded.can_start_stage,
                can_end_stage       = excluded.can_end_stage,
                can_edit_dates      = excluded.can_edit_dates,
                can_sync_master     = excluded.can_sync_master,
                can_critical_path   = excluded.can_critical_path,
                can_manage_permissions = excluded.can_manage_permissions,
                updated_at          = CURRENT_TIMESTAMP
        """, (
            role,
            int(bool(permissions.get('can_start_stage', False))),
            int(bool(permissions.get('can_end_stage', False))),
            int(bool(permissions.get('can_edit_dates', False))),
            int(bool(permissions.get('can_sync_master', False))),
            int(bool(permissions.get('can_critical_path', False))),
            int(bool(permissions.get('can_manage_permissions', False))),
        ))
        con.commit()
    finally:
        con.close()


# ===========================================================================
# Listy zasobów – Pracownicy i Transport
# ===========================================================================

def get_employees(rm_master_db_path: str, category: str = None, active_only: bool = False) -> List[Dict]:
    """Pobierz pracowników z rm_manager.sqlite.
    category=None → wszystkie kategorie.
    active_only=True → tylko is_active=1.
    """
    ensure_list_tables(rm_master_db_path)
    con = _open_rm_connection(rm_master_db_path)
    clauses, params = [], []
    if category:
        clauses.append("category = ?")
        params.append(category)
    if active_only:
        clauses.append("is_active = 1")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = con.execute(
        f"SELECT * FROM employees {where} ORDER BY category, name", params
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def save_employee(rm_master_db_path: str, data: Dict) -> int:
    """Dodaj lub aktualizuj pracownika.
    data musi zawierać: name, category.
    Opcjonalne: description, contact_info, phone, email, is_active, id (gdy update).
    Zwraca id rekordu.
    """
    ensure_list_tables(rm_master_db_path)
    con = _open_rm_connection(rm_master_db_path)
    try:
        if data.get('id'):
            con.execute("""
                UPDATE employees SET
                    name         = ?,
                    category     = ?,
                    description  = ?,
                    contact_info = ?,
                    phone        = ?,
                    email        = ?,
                    is_active    = ?,
                    updated_at   = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                data['name'], data['category'],
                data.get('description', ''), data.get('contact_info', ''),
                data.get('phone', ''), data.get('email', ''),
                int(bool(data.get('is_active', True))),
                data['id']
            ))
            row_id = data['id']
        else:
            cur = con.execute("""
                INSERT INTO employees (name, category, description, contact_info, phone, email, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                data['name'], data['category'],
                data.get('description', ''), data.get('contact_info', ''),
                data.get('phone', ''), data.get('email', ''),
                int(bool(data.get('is_active', True))),
            ))
            row_id = cur.lastrowid
        con.commit()
        return row_id
    finally:
        con.close()


def delete_employee(rm_master_db_path: str, employee_id: int):
    """Usuń pracownika z bazy (fizycznie)."""
    con = _open_rm_connection(rm_master_db_path)
    try:
        con.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
        con.commit()
    finally:
        con.close()


def get_transports(rm_master_db_path: str, active_only: bool = False) -> List[Dict]:
    """Pobierz pozycje z listy transport."""
    ensure_list_tables(rm_master_db_path)
    con = _open_rm_connection(rm_master_db_path)
    where = "WHERE is_active = 1" if active_only else ""
    rows = con.execute(
        f"SELECT * FROM transports {where} ORDER BY name", ()
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def save_transport(rm_master_db_path: str, data: Dict) -> int:
    """Dodaj lub aktualizuj pozycję transportu.
    data musi zawierać: name.
    Opcjonalne: description, contact_info, is_active, id (gdy update).
    """
    ensure_list_tables(rm_master_db_path)
    con = _open_rm_connection(rm_master_db_path)
    try:
        if data.get('id'):
            con.execute("""
                UPDATE transports SET
                    name         = ?,
                    description  = ?,
                    contact_info = ?,
                    is_active    = ?,
                    updated_at   = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                data['name'],
                data.get('description', ''), data.get('contact_info', ''),
                int(bool(data.get('is_active', True))),
                data['id']
            ))
            row_id = data['id']
        else:
            cur = con.execute("""
                INSERT INTO transports (name, description, contact_info, is_active)
                VALUES (?, ?, ?, ?)
            """, (
                data['name'],
                data.get('description', ''), data.get('contact_info', ''),
                int(bool(data.get('is_active', True))),
            ))
            row_id = cur.lastrowid
        con.commit()
        return row_id
    finally:
        con.close()


def delete_transport(rm_master_db_path: str, transport_id: int):
    """Usuń pozycję transportu z bazy (fizycznie)."""
    con = _open_rm_connection(rm_master_db_path)
    try:
        con.execute("DELETE FROM transports WHERE id = ?", (transport_id,))
        con.commit()
    finally:
        con.close()


def get_stage_transport_id(project_db_path: str, project_id: int, stage_code: str) -> int:
    """Pobierz ID firmy transportowej przypisanej do milestone TRANSPORT."""
    con = _open_rm_connection(project_db_path)
    try:
        row = con.execute("""
            SELECT ss.transport_id
            FROM stage_schedule ss
            JOIN project_stages ps ON ss.project_stage_id = ps.id
            WHERE ps.project_id = ? AND ps.stage_code = ?
        """, (project_id, stage_code)).fetchone()
        return row['transport_id'] if row and row['transport_id'] else None
    finally:
        con.close()


def set_stage_transport_id(project_db_path: str, project_id: int, stage_code: str, transport_id: int):
    """Ustaw firmę transportową dla milestone TRANSPORT.
    
    Args:
        transport_id: ID firmy transportowej (None = clear selection)
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    try:
        # Pobierz project_stage_id
        ps_row = con.execute("""
            SELECT id FROM project_stages
            WHERE project_id = ? AND stage_code = ?
        """, (project_id, stage_code)).fetchone()
        
        if not ps_row:
            raise ValueError(f"Nie znaleziono stage {stage_code} dla projektu {project_id}")
        
        ps_id = ps_row[0]
        
        # Sprawdź czy istnieje stage_schedule
        existing = con.execute(
            "SELECT id FROM stage_schedule WHERE project_stage_id = ?",
            (ps_id,)
        ).fetchone()
        
        if existing:
            # UPDATE
            con.execute("""
                UPDATE stage_schedule
                SET transport_id = ?
                WHERE project_stage_id = ?
            """, (transport_id, ps_id))
        else:
            # INSERT
            con.execute("""
                INSERT INTO stage_schedule (project_stage_id, transport_id)
                VALUES (?, ?)
            """, (ps_id, transport_id))
        
        con.commit()
    finally:
        con.close()


def get_stage_employee_id(project_db_path: str, project_id: int, stage_code: str) -> int:
    """Pobierz ID pracownika przypisanego do milestone URUCHOMIENIE_U_KLIENTA."""
    con = _open_rm_connection(project_db_path)
    try:
        row = con.execute("""
            SELECT ss.employee_id
            FROM stage_schedule ss
            JOIN project_stages ps ON ss.project_stage_id = ps.id
            WHERE ps.project_id = ? AND ps.stage_code = ?
        """, (project_id, stage_code)).fetchone()
        return row['employee_id'] if row and row['employee_id'] else None
    finally:
        con.close()


def set_stage_employee_id(project_db_path: str, project_id: int, stage_code: str, employee_id: int):
    """Ustaw pracownika dla milestone URUCHOMIENIE_U_KLIENTA.
    
    Args:
        employee_id: ID pracownika (None = clear selection)
    """
    con = _open_rm_connection(project_db_path)
    try:
        # Pobierz project_stage_id
        ps_row = con.execute("""
            SELECT id FROM project_stages
            WHERE project_id = ? AND stage_code = ?
        """, (project_id, stage_code)).fetchone()
        
        if not ps_row:
            raise ValueError(f"Nie znaleziono stage {stage_code} dla projektu {project_id}")
        
        ps_id = ps_row[0]
        
        # Sprawdź czy istnieje stage_schedule
        existing = con.execute(
            "SELECT id FROM stage_schedule WHERE project_stage_id = ?",
            (ps_id,)
        ).fetchone()
        
        if existing:
            # UPDATE
            con.execute("""
                UPDATE stage_schedule
                SET employee_id = ?
                WHERE project_stage_id = ?
            """, (employee_id, ps_id))
        else:
            # INSERT
            con.execute("""
                INSERT INTO stage_schedule (project_stage_id, employee_id)
                VALUES (?, ?)
            """, (ps_id, employee_id))
        
        con.commit()
    finally:
        con.close()


# ============================================================================
# STAGE STAFF ASSIGNMENTS - Przypisania pracowników do etapów
# ============================================================================

def add_staff_to_stage(project_db_path: str, rm_master_db_path: str,
                       project_id: int, stage_code: str, employee_id: int,
                       assigned_by: str = None) -> bool:
    """Przypisz pracownika do etapu (faza planowania).
    
    Zapisuje w JSON kolumnie assigned_staff w project_stages:
    [{"employee_id": 1, "assigned_at": "2026-04-09 14:30", "assigned_by": "admin"}]
    
    NOWA ARCHITEKTURA: przypisania w project_stages (nie stage_actual_periods)
    - Można planować pracowników PRZED rozpoczęciem etapu
    - Nie wymaga aktywnego okresu
    
    Args:
        project_db_path: Ścieżka do bazy per-projekt
        rm_master_db_path: Ścieżka do master (dla sprawdzenia czy employee istnieje)
        project_id: ID projektu
        stage_code: Kod etapu (np. 'MONTAZ')
        employee_id: ID pracownika z tabeli employees
        assigned_by: Nazwa użytkownika który przypisał
    
    Returns:
        True jeśli udało się przypisać
    """
    import json
    
    # Sprawdź czy pracownik istnieje
    con_master = _open_rm_connection(rm_master_db_path)
    employee = con_master.execute("SELECT id FROM employees WHERE id = ?", (employee_id,)).fetchone()
    con_master.close()
    
    if not employee:
        raise ValueError(f"Pracownik ID={employee_id} nie istnieje w bazie employees")
    
    con = _open_rm_connection(project_db_path)
    
    try:
        # Znajdź project_stage
        row = con.execute("""
            SELECT id, assigned_staff
            FROM project_stages
            WHERE project_id = ? AND stage_code = ?
        """, (project_id, stage_code)).fetchone()
        
        if not row:
            raise ValueError(f"Etap {stage_code} nie istnieje dla projektu {project_id}")
        
        stage_id = row['id']
        assigned_staff_json = row['assigned_staff'] or '[]'
        
        # Parse JSON
        try:
            assigned_staff = json.loads(assigned_staff_json)
        except (json.JSONDecodeError, TypeError):
            assigned_staff = []
        
        # Sprawdź czy już nie jest przypisany
        if any(s['employee_id'] == employee_id for s in assigned_staff):
            return True  # Już przypisany
        
        # Dodaj nowy wpis
        assigned_staff.append({
            'employee_id': employee_id,
            'assigned_at': get_timestamp_now(),
            'assigned_by': assigned_by or 'System'
        })
        
        # Zapisz z powrotem
        con.execute("""
            UPDATE project_stages
            SET assigned_staff = ?
            WHERE id = ?
        """, (json.dumps(assigned_staff), stage_id))

        # Sync: wstaw też do stage_staff_assignments (jeśli tabela istnieje)
        try:
            # Pobierz daty template dla planned_start/planned_end
            ss_row = con.execute("""
                SELECT template_start, template_end
                FROM stage_schedule WHERE project_stage_id = ?
            """, (stage_id,)).fetchone()
            p_start = ss_row['template_start'] if ss_row else None
            p_end = ss_row['template_end'] if ss_row else None

            existing = con.execute("""
                SELECT id FROM stage_staff_assignments
                WHERE project_stage_id = ? AND employee_id = ?
            """, (stage_id, employee_id)).fetchone()
            if not existing:
                con.execute("""
                    INSERT INTO stage_staff_assignments
                        (project_stage_id, employee_id, planned_start, planned_end,
                         assigned_by)
                    VALUES (?, ?, ?, ?, ?)
                """, (stage_id, employee_id, p_start, p_end,
                      assigned_by or 'System'))
        except sqlite3.OperationalError:
            pass  # stara baza bez tabeli
        
        con.commit()
        return True
        
    finally:
        con.close()


def remove_staff_from_stage(project_db_path: str, project_id: int,
                           stage_code: str, employee_id: int) -> bool:
    """Usuń pracownika z etapu.
    
    Args:
        project_db_path: Ścieżka do bazy per-projekt
        project_id: ID projektu
        stage_code: Kod etapu
        employee_id: ID pracownika do usunięcia
    
    Returns:
        True jeśli usunięto, False jeśli nie znaleziono
    """
    import json
    
    con = _open_rm_connection(project_db_path)
    
    try:
        row = con.execute("""
            SELECT id, assigned_staff
            FROM project_stages
            WHERE project_id = ? AND stage_code = ?
        """, (project_id, stage_code)).fetchone()
        
        if not row:
            return False
        
        stage_id = row['id']
        assigned_staff_json = row['assigned_staff'] or '[]'
        
        try:
            assigned_staff = json.loads(assigned_staff_json)
        except (json.JSONDecodeError, TypeError):
            assigned_staff = []
        
        # Usuń pracownika (int cast na wypadek mieszanych typów w JSON)
        assigned_staff = [s for s in assigned_staff
                          if int(s.get('employee_id', -1)) != int(employee_id)]
        
        con.execute("""
            UPDATE project_stages
            SET assigned_staff = ?
            WHERE id = ?
        """, (json.dumps(assigned_staff), stage_id))

        # Sync: usuń też z stage_staff_assignments (jeśli tabela istnieje)
        try:
            con.execute("""
                DELETE FROM stage_staff_assignments
                WHERE project_stage_id = ? AND employee_id = ?
            """, (stage_id, employee_id))
        except sqlite3.OperationalError:
            pass  # stara baza bez tabeli
        
        con.commit()
        return True
        
    finally:
        con.close()


def get_stage_assigned_staff(project_db_path: str, rm_master_db_path: str,
                            project_id: int, stage_code: str) -> List[Dict]:
    """Pobierz listę pracowników przypisanych do etapu.

    Merguje oba źródła: JSON (project_stages.assigned_staff) + tabela
    (stage_staff_assignments).  Dzięki temu wpisy istniejące tylko w tabeli
    (np. po starym usunięciu z JSON bez sync) również zostają zwrócone i mogą
    być usunięte z poziomu dialogu.

    Returns:
        Lista dict z kluczami:
        - employee_id
        - employee_name
        - category
        - assigned_at
        - assigned_by
    """
    import json

    con = _open_rm_connection(project_db_path)

    # Zbierz employee_ids z obu źródeł
    json_staff = []   # [{employee_id, assigned_at, assigned_by}, ...]
    table_eids = set()

    try:
        row = con.execute("""
            SELECT id, assigned_staff
            FROM project_stages
            WHERE project_id = ? AND stage_code = ?
        """, (project_id, stage_code)).fetchone()

        if row:
            stage_id = row['id']
            try:
                json_staff = json.loads(row['assigned_staff'] or '[]')
            except (json.JSONDecodeError, TypeError):
                json_staff = []

            # Zbierz z tabeli stage_staff_assignments
            try:
                ssa_rows = con.execute("""
                    SELECT employee_id, assigned_by
                    FROM stage_staff_assignments
                    WHERE project_stage_id = ?
                """, (stage_id,)).fetchall()
                table_eids = {r['employee_id'] for r in ssa_rows}
            except Exception:
                pass  # stara baza bez tabeli
    finally:
        con.close()

    # Zbierz unikalne employee_ids (JSON + tabela)
    json_eid_set = set()
    for s in json_staff:
        if isinstance(s, dict) and 'employee_id' in s:
            json_eid_set.add(s['employee_id'])

    all_eids = json_eid_set | table_eids
    if not all_eids:
        return []

    # Pobierz szczegóły pracowników z master
    con_master = _open_rm_connection(rm_master_db_path)

    try:
        placeholders = ','.join('?' * len(all_eids))
        employees = con_master.execute(f"""
            SELECT id, name, category
            FROM employees
            WHERE id IN ({placeholders})
        """, list(all_eids)).fetchall()

        employee_map = {e['id']: {'name': e['name'], 'category': e['category']}
                        for e in employees}

        # Buduj wynik — priorytet danych z JSON (ma assigned_at), dopełnienie z tabeli
        result = []
        seen = set()

        # Najpierw wpisy z JSON (zachowaj kolejność)
        for staff in json_staff:
            if not isinstance(staff, dict) or 'employee_id' not in staff:
                continue
            emp_id = staff['employee_id']
            if emp_id in employee_map and emp_id not in seen:
                seen.add(emp_id)
                result.append({
                    'employee_id': emp_id,
                    'employee_name': employee_map[emp_id]['name'],
                    'category': employee_map[emp_id]['category'],
                    'assigned_at': staff.get('assigned_at'),
                    'assigned_by': staff.get('assigned_by')
                })

        # Dopełnij wpisami z tabeli, których nie było w JSON
        for eid in sorted(table_eids - seen):
            if eid in employee_map:
                result.append({
                    'employee_id': eid,
                    'employee_name': employee_map[eid]['name'],
                    'category': employee_map[eid]['category'],
                    'assigned_at': None,
                    'assigned_by': None
                })

        return result

    finally:
        con_master.close()


# ============================================================================
# STAGE STAFF ASSIGNMENTS — nowa architektura z datami (2026-04-19)
# ============================================================================

def add_staff_assignment(project_db_path: str, rm_master_db_path: str,
                         project_id: int, stage_code: str, employee_id: int,
                         planned_start: str = None, planned_end: str = None,
                         role: str = None, assigned_by: str = None) -> int:
    """Przypisz pracownika do etapu z określonym zakresem dat.
    
    Zapisuje w tabeli stage_staff_assignments (nowa architektura).
    Jednocześnie aktualizuje JSON w project_stages.assigned_staff (compat).
    
    Args:
        planned_start: Data rozpoczęcia pracy (ISO). None = template_start etapu.
        planned_end: Data zakończenia pracy (ISO). None = template_end etapu.
        role: Opcjonalna rola ('lead', 'support', itp.)
    
    Returns:
        ID przypisania
    """
    import json

    # Walidacja pracownika
    con_master = _open_rm_connection(rm_master_db_path)
    employee = con_master.execute("SELECT id, name FROM employees WHERE id = ?", (employee_id,)).fetchone()
    con_master.close()
    if not employee:
        raise ValueError(f"Pracownik ID={employee_id} nie istnieje")

    con = _open_rm_connection(project_db_path)
    try:
        # Znajdź project_stage i daty template
        row = con.execute("""
            SELECT ps.id AS ps_id, ps.assigned_staff,
                   ss.template_start, ss.template_end
            FROM project_stages ps
            LEFT JOIN stage_schedule ss ON ss.project_stage_id = ps.id
            WHERE ps.project_id = ? AND ps.stage_code = ?
        """, (project_id, stage_code)).fetchone()

        if not row:
            raise ValueError(f"Etap {stage_code} nie istnieje dla projektu {project_id}")

        ps_id = row['ps_id']
        p_start = planned_start or row['template_start']
        p_end = planned_end or row['template_end']

        # Wstaw do nowej tabeli
        try:
            cursor = con.execute("""
                INSERT INTO stage_staff_assignments
                    (project_stage_id, employee_id, planned_start, planned_end,
                     role, assigned_by)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (ps_id, employee_id, p_start, p_end, role, assigned_by or 'System'))
            assignment_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            # Już przypisany — zaktualizuj daty
            con.execute("""
                UPDATE stage_staff_assignments
                SET planned_start = ?, planned_end = ?, role = ?,
                    assigned_by = ?, assigned_at = CURRENT_TIMESTAMP
                WHERE project_stage_id = ? AND employee_id = ?
            """, (p_start, p_end, role, assigned_by, ps_id, employee_id))
            r = con.execute("""
                SELECT id FROM stage_staff_assignments
                WHERE project_stage_id = ? AND employee_id = ?
            """, (ps_id, employee_id)).fetchone()
            assignment_id = r['id'] if r else 0

        # Compat: zaktualizuj JSON w project_stages.assigned_staff
        try:
            staff_json = json.loads(row['assigned_staff'] or '[]')
        except (json.JSONDecodeError, TypeError):
            staff_json = []

        if not any(s.get('employee_id') == employee_id for s in staff_json):
            staff_json.append({
                'employee_id': employee_id,
                'assigned_at': get_timestamp_now(),
                'assigned_by': assigned_by or 'System',
            })
            con.execute("UPDATE project_stages SET assigned_staff = ? WHERE id = ?",
                        (json.dumps(staff_json), ps_id))

        _rm_safe_commit(con)
        return assignment_id

    finally:
        con.close()


def update_staff_assignment_dates(project_db_path: str, assignment_id: int,
                                  planned_start: str = None, planned_end: str = None):
    """Zaktualizuj daty przypisania pracownika."""
    con = _open_rm_connection(project_db_path)
    try:
        sets, params = [], []
        if planned_start is not None:
            sets.append("planned_start = ?")
            params.append(planned_start)
        if planned_end is not None:
            sets.append("planned_end = ?")
            params.append(planned_end)
        if not sets:
            return
        params.append(assignment_id)
        con.execute(f"UPDATE stage_staff_assignments SET {', '.join(sets)} WHERE id = ?", params)
        _rm_safe_commit(con)
    finally:
        con.close()


def remove_staff_assignment(project_db_path: str, project_id: int,
                            stage_code: str, employee_id: int) -> bool:
    """Usuń przypisanie pracownika (nowa tabela + compat JSON)."""
    import json

    con = _open_rm_connection(project_db_path)
    try:
        row = con.execute("""
            SELECT ps.id AS ps_id, ps.assigned_staff
            FROM project_stages ps
            WHERE ps.project_id = ? AND ps.stage_code = ?
        """, (project_id, stage_code)).fetchone()
        if not row:
            return False

        ps_id = row['ps_id']

        # Nowa tabela
        con.execute("""
            DELETE FROM stage_staff_assignments
            WHERE project_stage_id = ? AND employee_id = ?
        """, (ps_id, employee_id))

        # Compat JSON
        try:
            staff_json = json.loads(row['assigned_staff'] or '[]')
            staff_json = [s for s in staff_json if s.get('employee_id') != employee_id]
            con.execute("UPDATE project_stages SET assigned_staff = ? WHERE id = ?",
                        (json.dumps(staff_json), ps_id))
        except (json.JSONDecodeError, TypeError):
            pass

        _rm_safe_commit(con)
        return True
    finally:
        con.close()


def get_staff_assignments(project_db_path: str, rm_master_db_path: str,
                          project_id: int, stage_code: str = None) -> List[Dict]:
    """Pobierz przypisania pracowników z nowymi datami.
    
    Args:
        stage_code: None = wszystkie etapy projektu
    
    Returns:
        Lista dict: employee_id, employee_name, category, stage_code,
                    planned_start, planned_end, actual_start, actual_end, role
    """
    con = _open_rm_connection(project_db_path)
    try:
        if stage_code:
            rows = con.execute("""
                SELECT ssa.*, ps.stage_code
                FROM stage_staff_assignments ssa
                JOIN project_stages ps ON ssa.project_stage_id = ps.id
                WHERE ps.project_id = ? AND ps.stage_code = ?
                ORDER BY ssa.planned_start
            """, (project_id, stage_code)).fetchall()
        else:
            rows = con.execute("""
                SELECT ssa.*, ps.stage_code
                FROM stage_staff_assignments ssa
                JOIN project_stages ps ON ssa.project_stage_id = ps.id
                WHERE ps.project_id = ?
                ORDER BY ps.sequence, ssa.planned_start
            """, (project_id,)).fetchall()
    finally:
        con.close()

    if not rows:
        return []

    # Pobierz dane pracowników z master
    emp_ids = list({r['employee_id'] for r in rows})
    con_master = _open_rm_connection(rm_master_db_path)
    try:
        placeholders = ','.join('?' * len(emp_ids))
        emps = con_master.execute(f"""
            SELECT id, name, category FROM employees WHERE id IN ({placeholders})
        """, emp_ids).fetchall()
        emp_map = {e['id']: {'name': e['name'], 'category': e['category']} for e in emps}
    finally:
        con_master.close()

    result = []
    for r in rows:
        eid = r['employee_id']
        emp_info = emp_map.get(eid, {'name': f'ID={eid}', 'category': '?'})
        result.append({
            'id': r['id'],
            'employee_id': eid,
            'employee_name': emp_info['name'],
            'category': emp_info['category'],
            'stage_code': r['stage_code'],
            'planned_start': r['planned_start'],
            'planned_end': r['planned_end'],
            'actual_start': r['actual_start'],
            'actual_end': r['actual_end'],
            'role': r['role'],
            'assigned_at': r['assigned_at'],
            'assigned_by': r['assigned_by'],
        })

    return result


def get_employee_schedule(rm_master_db_path: str, rm_manager_dir: str,
                          employee_id: int, project_ids: List[int],
                          date_from: str = None, date_to: str = None) -> List[Dict]:
    """Pobierz harmonogram pracownika z wielu projektów.
    
    Zwraca listę okresów kiedy pracownik jest zaplanowany.
    Kluczowe dla optymalizatora — widzi obciążenie pracownika.
    
    Returns:
        Lista dict: project_id, stage_code, planned_start, planned_end, actual_start, actual_end
    """
    result = []
    for pid in project_ids:
        db_path = get_project_db_path(rm_manager_dir, pid)
        if not Path(db_path).exists():
            continue
        con = _open_rm_connection(db_path)
        try:
            clauses = ["ssa.employee_id = ?"]
            params = [employee_id]
            if date_from:
                clauses.append("(ssa.planned_end >= ? OR ssa.planned_end IS NULL)")
                params.append(date_from)
            if date_to:
                clauses.append("(ssa.planned_start <= ? OR ssa.planned_start IS NULL)")
                params.append(date_to)
            where = " AND ".join(clauses)

            rows = con.execute(f"""
                SELECT ps.project_id, ps.stage_code,
                       ssa.planned_start, ssa.planned_end,
                       ssa.actual_start, ssa.actual_end, ssa.role
                FROM stage_staff_assignments ssa
                JOIN project_stages ps ON ssa.project_stage_id = ps.id
                WHERE {where}
                ORDER BY ssa.planned_start
            """, params).fetchall()

            for r in rows:
                result.append({
                    'project_id': r['project_id'],
                    'stage_code': r['stage_code'],
                    'planned_start': r['planned_start'],
                    'planned_end': r['planned_end'],
                    'actual_start': r['actual_start'],
                    'actual_end': r['actual_end'],
                    'role': r['role'],
                })
        except sqlite3.OperationalError:
            pass  # Stara baza bez tabeli
        finally:
            con.close()

    return result


def start_staff_actual(project_db_path: str, project_id: int,
                       stage_code: str, employee_id: int,
                       started_by: str = None):
    """Oznacz faktyczny start pracy pracownika na etapie."""
    con = _open_rm_connection(project_db_path)
    try:
        con.execute("""
            UPDATE stage_staff_assignments
            SET actual_start = CURRENT_TIMESTAMP
            WHERE project_stage_id = (
                SELECT id FROM project_stages WHERE project_id = ? AND stage_code = ?
            ) AND employee_id = ? AND actual_start IS NULL
        """, (project_id, stage_code, employee_id))
        _rm_safe_commit(con)
    finally:
        con.close()


def end_staff_actual(project_db_path: str, project_id: int,
                     stage_code: str, employee_id: int,
                     ended_by: str = None):
    """Oznacz faktyczne zakończenie pracy pracownika na etapie."""
    con = _open_rm_connection(project_db_path)
    try:
        con.execute("""
            UPDATE stage_staff_assignments
            SET actual_end = CURRENT_TIMESTAMP
            WHERE project_stage_id = (
                SELECT id FROM project_stages WHERE project_id = ? AND stage_code = ?
            ) AND employee_id = ? AND actual_end IS NULL
        """, (project_id, stage_code, employee_id))
        _rm_safe_commit(con)
    finally:
        con.close()


def get_all_stage_staff_for_project(project_db_path: str, rm_master_db_path: str,
                                   project_id: int) -> Dict[str, List[Dict]]:
    """Pobierz przypisania pracowników dla wszystkich etapów projektu.
    
    Returns:
        Dict: {stage_code: [lista pracowników]}
    """
    import json
    
    con = _open_rm_connection(project_db_path)
    
    try:
        rows = con.execute("""
            SELECT stage_code, assigned_staff
            FROM project_stages
            WHERE project_id = ?
        """, (project_id,)).fetchall()
        
        result = {}
        for row in rows:
            stage_code = row['stage_code']
            if row['assigned_staff']:
                try:
                    assigned_staff = json.loads(row['assigned_staff'])
                    result[stage_code] = assigned_staff
                except (json.JSONDecodeError, TypeError):
                    result[stage_code] = []
            else:
                result[stage_code] = []
        
        return result
        
    finally:
        con.close()


def get_project_staff(project_db_path: str, rm_master_db_path: str,
                     project_id: int) -> List[Dict]:
    """Pobierz unikalną listę pracowników przypisanych do projektu (ze wszystkich etapów).
    
    Returns:
        Lista dict z kluczami:
        - employee_id
        - employee_name
        - category
    """
    import json
    
    con = _open_rm_connection(project_db_path)
    
    try:
        # Pobierz wszystkich pracowników ze wszystkich etapów
        rows = con.execute("""
            SELECT assigned_staff
            FROM project_stages
            WHERE project_id = ? AND assigned_staff IS NOT NULL AND assigned_staff != ''
        """, (project_id,)).fetchall()
        
        # Zbierz unikalne employee_id
        employee_ids = set()
        for row in rows:
            try:
                assigned = json.loads(row['assigned_staff'])
                for staff in assigned:
                    emp_id = staff.get('employee_id')
                    if emp_id:
                        employee_ids.add(emp_id)
            except (json.JSONDecodeError, TypeError):
                continue
        
    finally:
        con.close()
    
    if not employee_ids:
        return []
    
    # Upewnij się że tabela employees istnieje
    ensure_list_tables(rm_master_db_path)
    
    # Pobierz szczegóły z master DB (tylko kategoria "Konstrukcja")
    con_master = _open_rm_connection(rm_master_db_path)
    
    try:
        placeholders = ','.join('?' * len(employee_ids))
        employees = con_master.execute(f"""
            SELECT id, name, category
            FROM employees
            WHERE id IN ({placeholders})
              AND category = 'Konstrukcja'
            ORDER BY name
        """, list(employee_ids)).fetchall()
        
        return [
            {
                'employee_id': e['id'],
                'employee_name': e['name'],
                'category': e['category']
            }
            for e in employees
        ]
        
    finally:
        con_master.close()


# ============================================================================
# SYSTEM NOTATEK - Tematy, notatki, alarmy
# ============================================================================

def create_topic(project_db_path: str, project_id: int, stage_code: str,
                title: str, priority: str = 'MEDIUM', color: str = None,
                created_by: str = None) -> int:
    """Utwórz nowy temat notatek dla etapu.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        project_id: ID projektu
        stage_code: Kod etapu (np. 'PROJEKT', 'MONTAZ')
        title: Tytuł tematu
        priority: Priorytet ('HIGH', 'MEDIUM', 'LOW')
        color: Kolor tematu (opcjonalnie)
        created_by: Kto utworzył
    
    Returns:
        int: ID utworzonego tematu
    """
    con = _open_rm_connection(project_db_path)
    
    try:
        # Znajdź następny topic_number dla tego etapu
        row = con.execute("""
            SELECT COALESCE(MAX(topic_number), 0) + 1 as next_num
            FROM stage_topics
            WHERE project_id = ? AND stage_code = ?
        """, (project_id, stage_code)).fetchone()
        
        topic_number = row['next_num']
        
        cursor = con.execute("""
            INSERT INTO stage_topics 
            (project_id, stage_code, topic_number, title, priority, color, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (project_id, stage_code, topic_number, title, priority, color, created_by))
        
        con.commit()
        return cursor.lastrowid
        
    finally:
        con.close()


def get_topics(project_db_path: str, project_id: int, stage_code: str = None) -> List[Dict]:
    """Pobierz tematy dla projektu/etapu.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        project_id: ID projektu
        stage_code: Kod etapu (None = wszystkie etapy)
    
    Returns:
        List[Dict]: Lista tematów posortowana po priorytecie i numerze
    """
    con = _open_rm_connection(project_db_path)
    
    try:
        if stage_code:
            rows = con.execute("""
                SELECT t.*, COUNT(n.id) AS note_count
                FROM stage_topics t
                LEFT JOIN stage_notes n ON n.topic_id = t.id
                WHERE t.project_id = ? AND t.stage_code = ?
                GROUP BY t.id
                ORDER BY t.topic_number
            """, (project_id, stage_code)).fetchall()
        else:
            rows = con.execute("""
                SELECT t.*, COUNT(n.id) AS note_count
                FROM stage_topics t
                LEFT JOIN stage_notes n ON n.topic_id = t.id
                WHERE t.project_id = ?
                GROUP BY t.id
                ORDER BY t.stage_code, t.topic_number
            """, (project_id,)).fetchall()
        
        return [dict(r) for r in rows]
        
    finally:
        con.close()


def update_topic(project_db_path: str, topic_id: int,
                title: str = None, priority: str = None, color: str = None) -> bool:
    """Zaktualizuj temat.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        topic_id: ID tematu
        title: Nowy tytuł (None = bez zmiany)
        priority: Nowy priorytet (None = bez zmiany)
        color: Nowy kolor (None = bez zmiany)
    
    Returns:
        bool: True jeśli zaktualizowano
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    
    try:
        updates = []
        params = []
        
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        
        if priority is not None:
            updates.append("priority = ?")
            params.append(priority)
        
        if color is not None:
            updates.append("color = ?")
            params.append(color)
        
        if not updates:
            return False
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(topic_id)
        
        con.execute(f"""
            UPDATE stage_topics
            SET {', '.join(updates)}
            WHERE id = ?
        """, params)
        
        con.commit()
        return con.total_changes > 0
        
    finally:
        con.close()


def delete_topic(project_db_path: str, topic_id: int) -> bool:
    """Usuń temat (kaskadowo usuwa notatki i alarmy).
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        topic_id: ID tematu
    
    Returns:
        bool: True jeśli usunięto
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    
    try:
        con.execute("DELETE FROM stage_topics WHERE id = ?", (topic_id,))
        con.commit()
        return con.total_changes > 0
        
    finally:
        con.close()


def reorder_topics(project_db_path: str, project_id: int, stage_code: str,
                  new_order: List[int]) -> bool:
    """Zmień kolejność tematów (aktualizuj topic_number).
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        project_id: ID projektu
        stage_code: Kod etapu
        new_order: Lista topic_id w nowej kolejności
    
    Returns:
        bool: True jeśli zaktualizowano
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    
    try:
        # Tymczasowe ujemne wartości (unikniecie UNIQUE constraint)
        for idx, topic_id in enumerate(new_order, start=1):
            con.execute("""
                UPDATE stage_topics
                SET topic_number = ?
                WHERE id = ? AND project_id = ? AND stage_code = ?
            """, (-(idx), topic_id, project_id, stage_code))
        for idx, topic_id in enumerate(new_order, start=1):
            con.execute("""
                UPDATE stage_topics
                SET topic_number = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND project_id = ? AND stage_code = ?
            """, (idx, topic_id, project_id, stage_code))
        
        con.commit()
        return True
        
    finally:
        con.close()


def move_topic(project_db_path: str, project_id: int, stage_code: str,
              topic_id: int, direction: str) -> bool:
    """Przesuń temat w kolejności (up/down/top/bottom).
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        project_id: ID projektu
        stage_code: Kod etapu
        topic_id: ID tematu
        direction: 'up', 'down', 'top', 'bottom'
    
    Returns:
        bool: True jeśli przesunięto
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    
    try:
        rows = con.execute(
            "SELECT id FROM stage_topics WHERE project_id = ? AND stage_code = ? ORDER BY topic_number",
            (project_id, stage_code)
        ).fetchall()
        
        ids = [r[0] for r in rows]
        if topic_id not in ids:
            return False
        
        idx = ids.index(topic_id)
        
        if direction == 'up' and idx > 0:
            ids[idx], ids[idx - 1] = ids[idx - 1], ids[idx]
        elif direction == 'down' and idx < len(ids) - 1:
            ids[idx], ids[idx + 1] = ids[idx + 1], ids[idx]
        elif direction == 'top' and idx > 0:
            ids.insert(0, ids.pop(idx))
        elif direction == 'bottom' and idx < len(ids) - 1:
            ids.append(ids.pop(idx))
        else:
            return False
        
        for new_num, tid in enumerate(ids, 1):
            con.execute(
                "UPDATE stage_topics SET topic_number = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (-(new_num), tid)
            )
        for new_num, tid in enumerate(ids, 1):
            con.execute(
                "UPDATE stage_topics SET topic_number = ? WHERE id = ?",
                (new_num, tid)
            )
        
        con.commit()
        return True
        
    finally:
        con.close()


def add_note(project_db_path: str, topic_id: int, note_text: str,
            created_by: str = None) -> int:
    """Dodaj notatkę do tematu.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        topic_id: ID tematu
        note_text: Treść notatki
        created_by: Kto utworzył
    
    Returns:
        int: ID utworzonej notatki
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    
    try:
        # sort_order = max + 1 (nowa notatka na końcu)
        row = con.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM stage_notes WHERE topic_id = ?",
            (topic_id,)
        ).fetchone()
        next_order = row[0]
        
        cursor = con.execute("""
            INSERT INTO stage_notes (topic_id, note_text, sort_order, created_by)
            VALUES (?, ?, ?, ?)
        """, (topic_id, note_text, next_order, created_by))
        
        con.commit()
        return cursor.lastrowid
        
    finally:
        con.close()


def get_notes(project_db_path: str, topic_id: int) -> List[Dict]:
    """Pobierz notatki dla tematu.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        topic_id: ID tematu
    
    Returns:
        List[Dict]: Lista notatek posortowana po dacie utworzenia
    """
    con = _open_rm_connection(project_db_path)
    
    try:
        rows = con.execute("""
            SELECT * FROM stage_notes
            WHERE topic_id = ?
            ORDER BY sort_order, created_at
        """, (topic_id,)).fetchall()
        
        return [dict(r) for r in rows]
        
    finally:
        con.close()


def update_note(project_db_path: str, note_id: int, note_text: str) -> bool:
    """Zaktualizuj notatkę.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        note_id: ID notatki
        note_text: Nowa treść
    
    Returns:
        bool: True jeśli zaktualizowano
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    
    try:
        con.execute("""
            UPDATE stage_notes
            SET note_text = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (note_text, note_id))
        
        con.commit()
        return con.total_changes > 0
        
    finally:
        con.close()


def delete_note(project_db_path: str, note_id: int) -> bool:
    """Usuń notatkę.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        note_id: ID notatki
    
    Returns:
        bool: True jeśli usunięto
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    
    try:
        con.execute("DELETE FROM stage_notes WHERE id = ?", (note_id,))
        con.commit()
        return con.total_changes > 0
        
    finally:
        con.close()


def move_note(project_db_path: str, topic_id: int, note_id: int, direction: str) -> bool:
    """Przesuń notatkę w kolejności (up/down/top/bottom).
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        topic_id: ID tematu
        note_id: ID notatki
        direction: 'up', 'down', 'top', 'bottom'
    
    Returns:
        bool: True jeśli przesunięto
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    
    try:
        # Pobierz wszystkie notatki tematu w kolejności
        rows = con.execute(
            "SELECT id, sort_order FROM stage_notes WHERE topic_id = ? ORDER BY sort_order, created_at",
            (topic_id,)
        ).fetchall()
        
        ids = [r[0] for r in rows]
        if note_id not in ids:
            return False
        
        idx = ids.index(note_id)
        
        if direction == 'up' and idx > 0:
            ids[idx], ids[idx - 1] = ids[idx - 1], ids[idx]
        elif direction == 'down' and idx < len(ids) - 1:
            ids[idx], ids[idx + 1] = ids[idx + 1], ids[idx]
        elif direction == 'top' and idx > 0:
            ids.insert(0, ids.pop(idx))
        elif direction == 'bottom' and idx < len(ids) - 1:
            ids.append(ids.pop(idx))
        else:
            return False
        
        # Przenumeruj sort_order
        for new_order, nid in enumerate(ids, 1):
            con.execute("UPDATE stage_notes SET sort_order = ? WHERE id = ?", (new_order, nid))
        
        con.commit()
        return True
        
    finally:
        con.close()


# ═══════════════════════════════════════════════════════════════════════════
# STAGE NOTE ATTACHMENTS - załączniki do notatek
# ═══════════════════════════════════════════════════════════════════════════

def add_attachment(project_db_path: str, note_id: int, file_path: str, 
                   uploaded_by: str = None) -> int:
    """Dodaj załącznik do notatki.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        note_id: ID notatki
        file_path: Ścieżka do pliku (JPG/PDF/CSV/XLSX/etc.)
        uploaded_by: Kto dodał
    
    Returns:
        int: ID utworzonego załącznika
    """
    import os
    import mimetypes
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Plik nie istnieje: {file_path}")
    
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    mime_type = mimetypes.guess_type(file_path)[0]
    
    # Czytaj plik binarnie
    with open(file_path, 'rb') as f:
        file_data = f.read()
    
    con = _open_rm_connection(project_db_path, row_factory=False)
    try:
        cursor = con.execute("""
            INSERT INTO stage_note_attachments 
            (note_id, filename, file_data, file_size, mime_type, uploaded_by)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (note_id, filename, file_data, file_size, mime_type, uploaded_by))
        
        con.commit()
        return cursor.lastrowid
    finally:
        con.close()


def get_attachments(project_db_path: str, note_id: int) -> List[Dict]:
    """Pobierz załączniki dla notatki (bez BLOB - tylko metadane).
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        note_id: ID notatki
    
    Returns:
        List[Dict]: Lista załączników (id, filename, file_size, mime_type, uploaded_at, uploaded_by)
    """
    con = _open_rm_connection(project_db_path)
    
    try:
        rows = con.execute("""
            SELECT id, note_id, filename, file_size, mime_type, uploaded_at, uploaded_by
            FROM stage_note_attachments
            WHERE note_id = ?
            ORDER BY uploaded_at
        """, (note_id,)).fetchall()
        
        return [dict(r) for r in rows]
    finally:
        con.close()


def get_attachment_data(project_db_path: str, attachment_id: int) -> dict:
    """Pobierz dane załącznika notatki.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        attachment_id: ID załącznika
    
    Returns:
        dict: Dane załącznika {'filename': str, 'file_content': bytes}
    """
    con = _open_rm_connection(project_db_path)
    
    try:
        row = con.execute(
            "SELECT filename, file_data FROM stage_note_attachments WHERE id = ?",
            (attachment_id,)
        ).fetchone()
        
        if not row:
            raise ValueError(f"Załącznik {attachment_id} nie istnieje")
        
        return {
            'filename': row['filename'],
            'file_content': row['file_data']
        }
    finally:
        con.close()


def delete_attachment(project_db_path: str, attachment_id: int) -> bool:
    """Usuń załącznik.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        attachment_id: ID załącznika
    
    Returns:
        bool: True jeśli usunięto
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    
    try:
        con.execute("DELETE FROM stage_note_attachments WHERE id = ?", (attachment_id,))
        con.commit()
        return con.total_changes > 0
    finally:
        con.close()


def save_attachment_to_temp(project_db_path: str, attachment_id: int) -> str:
    """Zapisz załącznik do pliku tymczasowego i zwróć ścieżkę.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        attachment_id: ID załącznika
    
    Returns:
        str: Ścieżka do pliku tymczasowego
    """
    import tempfile
    
    con = _open_rm_connection(project_db_path)
    
    try:
        row = con.execute("""
            SELECT filename, file_data 
            FROM stage_note_attachments 
            WHERE id = ?
        """, (attachment_id,)).fetchone()
        
        if not row:
            raise ValueError(f"Załącznik {attachment_id} nie istnieje")
        
        filename = row['filename']
        file_data = row['file_data']
        
        # Utwórz plik tymczasowy z zachowaniem rozszerzenia
        import os
        _, ext = os.path.splitext(filename)
        fd, temp_path = tempfile.mkstemp(suffix=ext, prefix="rm_attachment_")
        
        # Zapisz dane
        with os.fdopen(fd, 'wb') as f:
            f.write(file_data)
        
        return temp_path
    finally:
        con.close()


# ═══════════════════════════════════════════════════════════════════════════
# STAGE ATTACHMENTS - załączniki bezpośrednio do etapów (Karta maszyny, Protokoły)
# ═══════════════════════════════════════════════════════════════════════════

def add_stage_attachment(project_db_path: str, project_id: int, stage_code: str,
                         file_path: str, uploaded_by: str = None) -> int:
    """Dodaj załącznik bezpośrednio do etapu (milestone).
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        project_id: ID projektu
        stage_code: Kod etapu (np. PRZYJETY, ODBIOR_1)
        file_path: Ścieżka do pliku
        uploaded_by: Kto dodał
    
    Returns:
        int: ID utworzonego załącznika
    """
    import os
    import mimetypes
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Plik nie istnieje: {file_path}")
    
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    mime_type = mimetypes.guess_type(file_path)[0]
    
    # Czytaj plik binarnie
    with open(file_path, 'rb') as f:
        file_data = f.read()
    
    con = _open_rm_connection(project_db_path, row_factory=False)
    try:
        # Pobierz project_stage_id
        ps_row = con.execute("""
            SELECT id FROM project_stages
            WHERE project_id = ? AND stage_code = ?
        """, (project_id, stage_code)).fetchone()
        
        if not ps_row:
            raise ValueError(f"Nie znaleziono etapu {stage_code} dla projektu {project_id}")
        
        project_stage_id = ps_row[0]
        
        cursor = con.execute("""
            INSERT INTO stage_attachments 
            (project_stage_id, filename, file_data, file_size, mime_type, uploaded_by)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (project_stage_id, filename, file_data, file_size, mime_type, uploaded_by))
        
        con.commit()
        return cursor.lastrowid
    finally:
        con.close()


def get_stage_attachments(project_db_path: str, project_id: int, stage_code: str) -> List[Dict]:
    """Pobierz załączniki dla etapu (bez BLOB - tylko metadane).
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        project_id: ID projektu
        stage_code: Kod etapu
    
    Returns:
        List[Dict]: Lista załączników
    """
    con = _open_rm_connection(project_db_path)
    
    try:
        rows = con.execute("""
            SELECT sa.id, sa.project_stage_id, sa.filename, sa.file_size, 
                   sa.mime_type, sa.uploaded_at, sa.uploaded_by
            FROM stage_attachments sa
            JOIN project_stages ps ON sa.project_stage_id = ps.id
            WHERE ps.project_id = ? AND ps.stage_code = ?
            ORDER BY sa.uploaded_at
        """, (project_id, stage_code)).fetchall()
        
        return [dict(r) for r in rows]
    finally:
        con.close()


def get_stage_attachment_data(project_db_path: str, attachment_id: int) -> dict:
    """Pobierz dane załącznika etapu.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        attachment_id: ID załącznika
    
    Returns:
        dict: Dane załącznika {'filename': str, 'file_content': bytes}
    """
    con = _open_rm_connection(project_db_path)
    
    try:
        row = con.execute(
            "SELECT filename, file_data FROM stage_attachments WHERE id = ?",
            (attachment_id,)
        ).fetchone()
        
        if not row:
            raise ValueError(f"Załącznik etapu {attachment_id} nie istnieje")
        
        return {
            'filename': row['filename'],
            'file_content': row['file_data']
        }
    finally:
        con.close()


def delete_stage_attachment(project_db_path: str, attachment_id: int) -> bool:
    """Usuń załącznik etapu.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        attachment_id: ID załącznika
    
    Returns:
        bool: True jeśli usunięto
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    
    try:
        con.execute("DELETE FROM stage_attachments WHERE id = ?", (attachment_id,))
        con.commit()
        return con.total_changes > 0
    finally:
        con.close()


def save_stage_attachment_to_temp(project_db_path: str, attachment_id: int) -> str:
    """Zapisz załącznik etapu do pliku tymczasowego i zwróć ścieżkę.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        attachment_id: ID załącznika
    
    Returns:
        str: Ścieżka do pliku tymczasowego
    """
    import tempfile
    import os
    
    con = _open_rm_connection(project_db_path)
    
    try:
        row = con.execute("""
            SELECT filename, file_data 
            FROM stage_attachments 
            WHERE id = ?
        """, (attachment_id,)).fetchone()
        
        if not row:
            raise ValueError(f"Załącznik {attachment_id} nie istnieje")
        
        filename = row['filename']
        file_data = row['file_data']
        
        # Utwórz plik tymczasowy z zachowaniem rozszerzenia
        _, ext = os.path.splitext(filename)
        fd, temp_path = tempfile.mkstemp(suffix=ext, prefix="rm_stage_attachment_")
        
        # Zapisz dane
        with os.fdopen(fd, 'wb') as f:
            f.write(file_data)
        
        return temp_path
    finally:
        con.close()


def create_alarm(project_db_path: str, project_id: int, target_type: str,
                target_id: int, alarm_datetime: str, message: str = None,
                created_by: str = None, assigned_to: str = 'ALL') -> int:
    """Utwórz alarm/powiadomienie.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        project_id: ID projektu
        target_type: 'TOPIC' lub 'NOTE'
        target_id: ID tematu lub notatki
        alarm_datetime: Data i czas alarmu (format ISO)
        message: Treść powiadomienia
        created_by: Kto utworzył
        assigned_to: Adresaci ('ALL' lub lista nazw oddzielona przecinkami)
    
    Returns:
        int: ID utworzonego alarmu
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    
    try:
        cursor = con.execute("""
            INSERT INTO stage_alarms 
            (project_id, target_type, target_id, alarm_datetime, message, created_by, assigned_to)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (project_id, target_type, target_id, alarm_datetime, message, created_by,
              assigned_to or 'ALL'))
        
        con.commit()
        return cursor.lastrowid
        
    finally:
        con.close()


def get_all_alarms_with_snoozed(project_db_path: str, project_id: int = None,
                                before_datetime: str = None, for_user: str = None) -> List[Dict]:
    """Pobierz WSZYSTKIE alarmy łącznie z odłożonymi (wzbogacone o nazwę tematu/notatki).
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        project_id: ID projektu (None = wszystkie)
        before_datetime: Pobierz alarmy przed tą datą (None = wszystkie)
        for_user: Filtruj alarmy dla danego użytkownika (None = wszystkie)
    
    Returns:
        List[Dict]: Lista wszystkich alarmów posortowana po dacie,
                    wzbogacona o topic_title, stage_code, note_text, is_snoozed
    """
    con = _open_rm_connection(project_db_path)
    
    try:
        query = "SELECT * FROM stage_alarms WHERE is_active = 1"
        params = []
        
        if project_id is not None:
            query += " AND project_id = ?"
            params.append(project_id)
        
        if before_datetime:
            query += " AND alarm_datetime <= ?"
            params.append(before_datetime)
        
        # NIE filtrujemy snoozed_until - pokazujemy wszystkie alarmy
        query += " ORDER BY alarm_datetime"
        
        rows = con.execute(query, params).fetchall()
        result = []
        current_time = before_datetime or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for r in rows:
            alarm = dict(r)
            # Filtruj po użytkowniku
            assigned = alarm.get('assigned_to', 'ALL') or 'ALL'
            if for_user and assigned != 'ALL':
                assigned_list = [u.strip() for u in assigned.split(',')]
                if for_user not in assigned_list:
                    continue
            
            # Dodaj flagę czy alarm jest odłożony
            snoozed_until = alarm.get('snoozed_until')
            alarm['is_snoozed'] = bool(snoozed_until and snoozed_until > current_time)
            
            # Wzbogać o dane tematu/notatki
            if alarm['target_type'] == 'TOPIC':
                topic = con.execute(
                    "SELECT title, stage_code FROM stage_topics WHERE id = ?",
                    (alarm['target_id'],)
                ).fetchone()
                if topic:
                    alarm['topic_title'] = topic['title']
                    alarm['stage_code'] = topic['stage_code']
                else:
                    alarm['topic_title'] = '(usunięty temat)'
                    alarm['stage_code'] = ''
                alarm['note_text'] = None
            elif alarm['target_type'] == 'NOTE':
                note = con.execute(
                    "SELECT n.note_text, n.topic_id, t.title AS topic_title, t.stage_code "
                    "FROM stage_notes n LEFT JOIN stage_topics t ON n.topic_id = t.id "
                    "WHERE n.id = ?",
                    (alarm['target_id'],)
                ).fetchone()
                if note:
                    alarm['note_text'] = note['note_text'][:100]
                    alarm['topic_title'] = note['topic_title'] or '(usunięty temat)'
                    alarm['stage_code'] = note['stage_code'] or ''
                    alarm['topic_id'] = note['topic_id']
                else:
                    alarm['note_text'] = '(usunięta notatka)'
                    alarm['topic_title'] = ''
                    alarm['stage_code'] = ''
            
            result.append(alarm)
        
        return result
        
    finally:
        con.close()


def get_alarms_for_target(project_db_path: str, target_type: str, target_id: int,
                         include_snoozed: bool = True) -> List[Dict]:
    """Pobierz wszystkie alarmy dla konkretnego tematu/notatki.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        target_type: 'TOPIC' lub 'NOTE'
        target_id: ID tematu lub notatki
        include_snoozed: Czy uwzględnić odłożone alarmy
    
    Returns:
        List[Dict]: Lista alarmów posortowana po dacie
    """
    try:
        con = _open_rm_connection(project_db_path)
        
        # Sprawdź czy tabela stage_alarms istnieje
        table_check = con.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='stage_alarms'
        """).fetchone()
        
        if not table_check:
            return []  # Tabela nie istnieje, zwróć pustą listę
        
        query = """
            SELECT * FROM stage_alarms 
            WHERE is_active = 1 AND target_type = ? AND target_id = ?
        """
        params = [target_type, target_id]
        
        if not include_snoozed:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            query += " AND (snoozed_until IS NULL OR snoozed_until <= ?)"
            params.append(current_time)
        
        query += " ORDER BY alarm_datetime"
        
        rows = con.execute(query, params).fetchall()
        result = []
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for r in rows:
            alarm = dict(r)
            # Dodaj flagę czy alarm jest odłożony
            snoozed_until = alarm.get('snoozed_until')
            alarm['is_snoozed'] = bool(snoozed_until and snoozed_until > current_time)
            result.append(alarm)
        
        return result
    
    except Exception as e:
        print(f"⚠️ get_alarms_for_target error: {e}")
        return []
        
    finally:
        try:
            con.close()
        except:
            pass


def get_active_alarms(project_db_path: str, project_id: int = None,
                     before_datetime: str = None, for_user: str = None) -> List[Dict]:
    """Pobierz aktywne alarmy (wzbogacone o nazwę tematu/notatki).
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        project_id: ID projektu (None = wszystkie)
        before_datetime: Pobierz alarmy przed tą datą (None = wszystkie)
        for_user: Filtruj alarmy dla danego użytkownika (None = wszystkie)
    
    Returns:
        List[Dict]: Lista aktywnych alarmów posortowana po dacie,
                    wzbogacona o topic_title, stage_code, note_text
    """
    con = _open_rm_connection(project_db_path)
    
    try:
        # Sprawdź czy tabela stage_alarms istnieje (może nie być w starszych bazach)
        table_check = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stage_alarms'"
        ).fetchone()
        
        if not table_check:
            # Tabela nie istnieje - zwróć pustą listę (starsza baza projektu)
            return []
        
        query = "SELECT * FROM stage_alarms WHERE is_active = 1"
        params = []
        
        if project_id is not None:
            query += " AND project_id = ?"
            params.append(project_id)
        
        if before_datetime:
            query += " AND alarm_datetime <= ?"
            params.append(before_datetime)
        
        # Filtruj snoozed_until
        query += " AND (snoozed_until IS NULL OR snoozed_until <= ?)"
        params.append(before_datetime or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        query += " ORDER BY alarm_datetime"
        
        rows = con.execute(query, params).fetchall()
        result = []
        for r in rows:
            alarm = dict(r)
            # Filtruj po użytkowniku
            assigned = alarm.get('assigned_to', 'ALL') or 'ALL'
            if for_user and assigned != 'ALL':
                assigned_list = [u.strip() for u in assigned.split(',')]
                if for_user not in assigned_list:
                    continue
            
            # Wzbogać o dane tematu/notatki
            if alarm['target_type'] == 'TOPIC':
                topic = con.execute(
                    "SELECT title, stage_code FROM stage_topics WHERE id = ?",
                    (alarm['target_id'],)
                ).fetchone()
                if topic:
                    alarm['topic_title'] = topic['title']
                    alarm['stage_code'] = topic['stage_code']
                else:
                    alarm['topic_title'] = '(usunięty temat)'
                    alarm['stage_code'] = ''
                alarm['note_text'] = None
            elif alarm['target_type'] == 'NOTE':
                note = con.execute(
                    "SELECT n.note_text, n.topic_id, t.title AS topic_title, t.stage_code "
                    "FROM stage_notes n LEFT JOIN stage_topics t ON n.topic_id = t.id "
                    "WHERE n.id = ?",
                    (alarm['target_id'],)
                ).fetchone()
                if note:
                    alarm['note_text'] = note['note_text'][:100]
                    alarm['topic_title'] = note['topic_title'] or '(usunięty temat)'
                    alarm['stage_code'] = note['stage_code'] or ''
                    alarm['topic_id'] = note['topic_id']
                else:
                    alarm['note_text'] = '(usunięta notatka)'
                    alarm['topic_title'] = ''
                    alarm['stage_code'] = ''
            
            result.append(alarm)
        
        return result
        
    finally:
        con.close()


def acknowledge_alarm(project_db_path: str, alarm_id: int,
                     acknowledged_by: str = None) -> bool:
    """Potwierdź alarm (wyłącz powiadomienie).
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        alarm_id: ID alarmu
        acknowledged_by: Kto potwierdził
    
    Returns:
        bool: True jeśli zaktualizowano
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    
    try:
        con.execute("""
            UPDATE stage_alarms
            SET is_active = 0,
                acknowledged_at = CURRENT_TIMESTAMP,
                acknowledged_by = ?
            WHERE id = ?
        """, (acknowledged_by, alarm_id))
        
        con.commit()
        return con.total_changes > 0
        
    finally:
        con.close()


def delete_alarm(project_db_path: str, alarm_id: int) -> bool:
    """Usuń alarm.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        alarm_id: ID alarmu
    
    Returns:
        bool: True jeśli usunięto
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    
    try:
        con.execute("DELETE FROM stage_alarms WHERE id = ?", (alarm_id,))
        con.commit()
        return con.total_changes > 0
        
    finally:
        con.close()


def snooze_alarm(project_db_path: str, alarm_id: int, snooze_until: str) -> bool:
    """Odłóż alarm na później (Powiadom później).
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        alarm_id: ID alarmu
        snooze_until: Data/czas kiedy alarm ma się ponownie pojawić (ISO format)
    
    Returns:
        bool: True jeśli zaktualizowano
    """
    con = _open_rm_connection(project_db_path, row_factory=False)
    
    try:
        con.execute("""
            UPDATE stage_alarms
            SET snoozed_until = ?
            WHERE id = ? AND is_active = 1
        """, (snooze_until, alarm_id))
        
        con.commit()
        return con.total_changes > 0
        
    finally:
        con.close()


def get_topic_stats(project_db_path: str, project_id: int, stage_code: str = None) -> Dict:
    """Pobierz statystyki notatek.
    
    Args:
        project_db_path: Ścieżka do per-projekt bazy
        project_id: ID projektu
        stage_code: Kod etapu (None = wszystkie etapy)
    
    Returns:
        Dict: Statystyki (total_topics, total_notes, active_alarms)
    """
    con = _open_rm_connection(project_db_path)
    
    try:
        # Liczba tematów
        if stage_code:
            topics_query = """
                SELECT COUNT(*) as cnt FROM stage_topics
                WHERE project_id = ? AND stage_code = ?
            """
            params_topics = (project_id, stage_code)
        else:
            topics_query = """
                SELECT COUNT(*) as cnt FROM stage_topics
                WHERE project_id = ?
            """
            params_topics = (project_id,)
        
        total_topics = con.execute(topics_query, params_topics).fetchone()['cnt']
        
        # Liczba notatek
        if stage_code:
            notes_query = """
                SELECT COUNT(*) as cnt FROM stage_notes
                WHERE topic_id IN (
                    SELECT id FROM stage_topics
                    WHERE project_id = ? AND stage_code = ?
                )
            """
            params_notes = (project_id, stage_code)
        else:
            notes_query = """
                SELECT COUNT(*) as cnt FROM stage_notes
                WHERE topic_id IN (
                    SELECT id FROM stage_topics WHERE project_id = ?
                )
            """
            params_notes = (project_id,)
        
        total_notes = con.execute(notes_query, params_notes).fetchone()['cnt']
        
        # Aktywne alarmy
        if stage_code:
            alarms_query = """
                SELECT COUNT(*) as cnt FROM stage_alarms
                WHERE is_active = 1 AND project_id = ?
                  AND (
                      (target_type = 'TOPIC' AND target_id IN (
                          SELECT id FROM stage_topics WHERE project_id = ? AND stage_code = ?
                      ))
                      OR
                      (target_type = 'NOTE' AND target_id IN (
                          SELECT n.id FROM stage_notes n
                          JOIN stage_topics t ON n.topic_id = t.id
                          WHERE t.project_id = ? AND t.stage_code = ?
                      ))
                  )
            """
            params_alarms = (project_id, project_id, stage_code, project_id, stage_code)
        else:
            alarms_query = """
                SELECT COUNT(*) as cnt FROM stage_alarms
                WHERE is_active = 1 AND project_id = ?
            """
            params_alarms = (project_id,)
        
        active_alarms = con.execute(alarms_query, params_alarms).fetchone()['cnt']
        
        return {
            'total_topics': total_topics,
            'total_notes': total_notes,
            'active_alarms': active_alarms
        }
        
    finally:
        con.close()


# ============================================================================
# MAINTENANCE - Czyszczenie duplikatów
# ============================================================================

def cleanup_duplicate_dependencies(project_db_path: str, project_id: int = None) -> int:
    """Usuń duplikaty z tabeli stage_dependencies.
    
    Duplikaty mogą powstać jeśli ta sama zależność została dodana kilka razy
    (przed dodaniem UNIQUE INDEX). Funkcja pozostawia tylko jedną kopię każdej
    unikalnej zależności (project_id, predecessor, successor, type).
    
    Args:
        project_db_path: Ścieżka do bazy per-projekt
        project_id: Opcjonalnie - czyść tylko dla konkretnego projektu
    
    Returns:
        Liczba usuniętych duplikatów
    """
    con = _open_rm_connection(project_db_path)
    
    try:
        # Usuń duplikaty - zachowaj tylko najstarszy wpis (min id) dla każdej kombinacji
        if project_id:
            removed = con.execute("""
                DELETE FROM stage_dependencies
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM stage_dependencies
                    WHERE project_id = ?
                    GROUP BY project_id, predecessor_stage_code, successor_stage_code, dependency_type
                ) AND project_id = ?
            """, (project_id, project_id))
        else:
            removed = con.execute("""
                DELETE FROM stage_dependencies
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM stage_dependencies
                    GROUP BY project_id, predecessor_stage_code, successor_stage_code, dependency_type
                )
            """)
        
        count = removed.rowcount
        con.commit()
        return count
        
    finally:
        con.close()


# ============================================================================
# PAYMENT SYSTEM - Płatności (2026-04-13)
# ============================================================================

def add_payment_milestone(rm_db_path: str, project_id: int, percentage: int, 
                          payment_date: str, user: str = None, check_trigger: bool = True,
                          master_db_path: str = None, payment_type: str = 'PŁATNOŚĆ') -> int:
    """Dodaj transzę płatności dla projektu.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        project_id: ID projektu
        percentage: Procent płatności (1-100)
        payment_date: Data płatności (YYYY-MM-DD)
        user: Kto dodał
        check_trigger: Czy sprawdzić trigger 100% (domyślnie True)
        master_db_path: Ścieżka do master.sqlite (opcjonalnie, do pobierania nazwy projektu)
        payment_type: Typ transzy: 'PŁATNOŚĆ' lub 'UMORZONY'
    
    Returns:
        ID dodanej transzy
        
    Raises:
        sqlite3.IntegrityError: Jeśli transza już istnieje
    """
    if not (1 <= percentage <= 100):
        raise ValueError(f"Procent musi być w zakresie 1-100, otrzymano: {percentage}")
    if payment_type not in ('PŁATNOŚĆ', 'UMORZONY'):
        payment_type = 'PŁATNOŚĆ'
    
    con = _open_rm_connection(rm_db_path)
    try:
        cursor = con.execute("""
            INSERT INTO payment_milestones (project_id, percentage, payment_date, created_by, created_at, payment_type)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        """, (project_id, percentage, payment_date, user, payment_type))
        
        milestone_id = cursor.lastrowid
        
        # Historia
        con.execute("""
            INSERT INTO payment_history (project_id, percentage, payment_date, action, changed_by, changed_at)
            VALUES (?, ?, ?, 'ADDED', ?, CURRENT_TIMESTAMP)
        """, (project_id, percentage, payment_date, user))
        
        _rm_safe_commit(con)
        
        # Sprawdź trigger dla 100%
        if check_trigger and percentage == 100:
            trigger_payment_notifications(rm_db_path, project_id, percentage, payment_date, user, master_db_path)
        
        return milestone_id
        
    finally:
        con.close()


def update_payment_milestone(rm_db_path: str, project_id: int, percentage: int, 
                              new_date: str, user: str = None, check_trigger: bool = True,
                              master_db_path: str = None):
    """Zaktualizuj datę istniejącej transzy płatności.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        project_id: ID projektu
        percentage: Procent transzy do zmiany
        new_date: Nowa data (YYYY-MM-DD)
        user: Kto zmienił
        check_trigger: Czy sprawdzić trigger 100% (jeśli zmieniono datę 100%)
        master_db_path: Ścieżka do master.sqlite (opcjonalnie)
    """
    con = _open_rm_connection(rm_db_path)
    try:
        # Pobierz starą datę
        row = con.execute("""
            SELECT payment_date FROM payment_milestones
            WHERE project_id = ? AND percentage = ?
        """, (project_id, percentage)).fetchone()
        
        if not row:
            raise ValueError(f"Nie znaleziono transzy {percentage}% dla projektu {project_id}")
        
        old_date = row['payment_date']
        
        # Zmień datę
        con.execute("""
            UPDATE payment_milestones
            SET payment_date = ?, modified_by = ?, modified_at = CURRENT_TIMESTAMP
            WHERE project_id = ? AND percentage = ?
        """, (new_date, user, project_id, percentage))
        
        # Historia
        con.execute("""
            INSERT INTO payment_history (project_id, percentage, payment_date, action, changed_by, old_date, changed_at)
            VALUES (?, ?, ?, 'MODIFIED', ?, ?, CURRENT_TIMESTAMP)
        """, (project_id, percentage, new_date, user, old_date))
        
        _rm_safe_commit(con)
        
        # Jeśli zmieniono datę 100%, może to wymagać ponownego powiadomienia
        if check_trigger and percentage == 100:
            trigger_payment_notifications(rm_db_path, project_id, percentage, new_date, user, master_db_path)
        
    finally:
        con.close()


def delete_payment_milestone(rm_db_path: str, project_id: int, percentage: int, user: str = None):
    """Usuń transzę płatności.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        project_id: ID projektu
        percentage: Procent transzy do usunięcia
        user: Kto usunął
    """
    con = _open_rm_connection(rm_db_path)
    try:
        # Pobierz datę przed usunięciem
        row = con.execute("""
            SELECT payment_date FROM payment_milestones
            WHERE project_id = ? AND percentage = ?
        """, (project_id, percentage)).fetchone()
        
        if not row:
            return  # Już usunięta
        
        payment_date = row['payment_date']
        
        # Usuń transzę
        con.execute("""
            DELETE FROM payment_milestones
            WHERE project_id = ? AND percentage = ?
        """, (project_id, percentage))
        
        # Historia
        con.execute("""
            INSERT INTO payment_history (project_id, percentage, payment_date, action, changed_by, old_date, changed_at)
            VALUES (?, ?, NULL, 'DELETED', ?, ?, CURRENT_TIMESTAMP)
        """, (project_id, percentage, user, payment_date))
        
        _rm_safe_commit(con)
        
    finally:
        con.close()


def get_payment_milestones(rm_db_path: str, project_id: int) -> List[Dict]:
    """Pobierz wszystkie transze płatności dla projektu.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        project_id: ID projektu
    
    Returns:
        Lista słowników z kluczami: id, percentage, payment_date, created_by, created_at, modified_by, modified_at
    """
    con = _open_rm_connection(rm_db_path)
    try:
        rows = con.execute("""
            SELECT id, project_id, percentage, payment_date, payment_type,
                   created_by, created_at, modified_by, modified_at
            FROM payment_milestones
            WHERE project_id = ?
            ORDER BY percentage
        """, (project_id,)).fetchall()
        
        return [dict(row) for row in rows]
        
    finally:
        con.close()


def get_payment_history(rm_db_path: str, project_id: int) -> List[Dict]:
    """Pobierz historię zmian płatności dla projektu.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        project_id: ID projektu
    
    Returns:
        Lista słowników: id, percentage, payment_date, action, changed_by, changed_at, old_date
    """
    con = _open_rm_connection(rm_db_path)
    try:
        rows = con.execute("""
            SELECT id, project_id, percentage, payment_date, action, 
                   changed_by, changed_at, old_date
            FROM payment_history
            WHERE project_id = ?
            ORDER BY changed_at DESC
        """, (project_id,)).fetchall()
        
        return [dict(row) for row in rows]
        
    finally:
        con.close()


def get_payment_notification_config(rm_db_path: str) -> Dict:
    """Pobierz konfigurację powiadomień email.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
    
    Returns:
        Dict z kluczami: id, trigger_percentage, email_recipients (lista), 
                         smtp_server, smtp_port, smtp_user, smtp_password, enabled
    """
    con = _open_rm_connection(rm_db_path)
    try:
        row = con.execute("""
            SELECT id, trigger_percentage, email_recipients, 
                   smtp_server, smtp_port, smtp_user, smtp_password, enabled
            FROM payment_notification_config
            WHERE id = 1
        """).fetchone()
        
        if not row:
            return None
        
        result = dict(row)
        # Parse JSON email list
        import json
        result['email_recipients'] = json.loads(result['email_recipients'] or '[]')
        return result
        
    finally:
        con.close()


def update_payment_notification_config(rm_db_path: str, recipients: List[str] = None, 
                                        smtp_server: str = None, smtp_port: int = None,
                                        smtp_user: str = None, smtp_password: str = None,
                                        enabled: bool = None, trigger_percentage: int = None):
    """Zaktualizuj konfigurację powiadomień email.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        recipients: Lista adresów email (opcjonalnie)
        smtp_server: Adres serwera SMTP (opcjonalnie)
        smtp_port: Port SMTP (opcjonalnie)
        smtp_user: Użytkownik SMTP (opcjonalnie)
        smtp_password: Hasło SMTP (opcjonalnie)
        enabled: Czy powiadomienia włączone (opcjonalnie)
        trigger_percentage: Procent triggerujący powiadomienie (opcjonalnie)
    """
    import json
    con = _open_rm_connection(rm_db_path)
    
    try:
        updates = []
        params = []
        
        if recipients is not None:
            updates.append("email_recipients = ?")
            params.append(json.dumps(recipients))
        
        if smtp_server is not None:
            updates.append("smtp_server = ?")
            params.append(smtp_server)
        
        if smtp_port is not None:
            updates.append("smtp_port = ?")
            params.append(smtp_port)
        
        if smtp_user is not None:
            updates.append("smtp_user = ?")
            params.append(smtp_user)
        
        if smtp_password is not None:
            updates.append("smtp_password = ?")
            params.append(smtp_password)
        
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if enabled else 0)
        
        if trigger_percentage is not None:
            updates.append("trigger_percentage = ?")
            params.append(trigger_percentage)
        
        if not updates:
            return  # Nic do zmiany
        
        updates.append("modified_at = CURRENT_TIMESTAMP")
        query = f"UPDATE payment_notification_config SET {', '.join(updates)} WHERE id = 1"
        
        con.execute(query, params)
        _rm_safe_commit(con)
        
    finally:
        con.close()


def trigger_payment_notifications(rm_db_path: str, project_id: int, percentage: int, 
                                   payment_date: str, user: str = None, master_db_path: str = None):
    """Wyślij powiadomienia o płatności (email + in-app).
    
    Wywoływane automatycznie gdy transza osiągnie trigger_percentage (domyślnie 100%).
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        project_id: ID projektu
        percentage: Procent transzy
        payment_date: Data płatności
        user: Kto zmienił
        master_db_path: Ścieżka do master.sqlite (opcjonalnie, do pobrania nazwy projektu)
    """
    config = get_payment_notification_config(rm_db_path)
    
    if not config or not config['enabled']:
        print(f"⚠️ Powiadomienia wyłączone - skipuję dla projektu {project_id}")
        return
    
    if percentage < config['trigger_percentage']:
        print(f"⚠️ Procent {percentage}% < trigger {config['trigger_percentage']}% - skipuję")
        return
    
    # Pobierz nazwę projektu z master.sqlite
    project_name = f"Projekt {project_id}"  # Fallback
    if master_db_path:
        try:
            con = _open_rm_connection(master_db_path)
            # Sprawdź czy kolumna to 'name' czy 'nazwa'
            cursor = con.execute("PRAGMA table_info(projects)")
            columns = [row[1] for row in cursor.fetchall()]
            name_col = 'name' if 'name' in columns else 'nazwa'
            id_col = 'project_id' if 'project_id' in columns else 'id'
            
            row = con.execute(f"SELECT {name_col} FROM projects WHERE {id_col} = ?", (project_id,)).fetchone()
            if row and row[name_col]:
                project_name = row[name_col]
            con.close()
        except Exception as e:
            print(f"⚠️ Nie można pobrać nazwy projektu: {e}")
    
    recipients = config['email_recipients']
    
    # 1. Powiadomienie in-app (zawsze)
    _create_in_app_notification(rm_db_path, project_id, project_name, percentage, 
                                  payment_date, user)
    
    # 2. Email (jeśli są odbiorcy)
    if recipients:
        _send_payment_email(rm_db_path, project_id, project_name, percentage, 
                            payment_date, recipients, config, user)
    else:
        print(f"⚠️ Brak odbiorców email - skipuję wysyłkę dla projektu {project_id}")


def _create_in_app_notification(rm_db_path: str, project_id: int, project_name: str, 
                                  percentage: int, payment_date: str, user: str = None):
    """Utwórz powiadomienie in-app."""
    import json
    con = _open_rm_connection(rm_db_path)
    
    try:
        message = f"Projekt '{project_name}' osiągnął {percentage}% płatności (data: {payment_date})"
        
        con.execute("""
            INSERT INTO in_app_notifications 
                (project_id, project_name, notification_type, message, created_by, created_at, is_read)
            VALUES (?, ?, 'PAYMENT', ?, ?, CURRENT_TIMESTAMP, 0)
        """, (project_id, project_name, message, user))
        
        _rm_safe_commit(con)
        print(f"✅ Utworzono powiadomienie in-app: {message}")
        
    finally:
        con.close()


def _send_payment_email(rm_db_path: str, project_id: int, project_name: str, 
                        percentage: int, payment_date: str, recipients: List[str], 
                        config: Dict, user: str = None):
    """Wyślij powiadomienie email o płatności."""
    import json
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    # Treść email
    subject = f"[RM_MANAGER] Płatność {percentage}% - {project_name}"
    body = f"""
Witaj,

Projekt: {project_name} (ID: {project_id})
Płatność: {percentage}%
Data płatności: {payment_date}
Wpisane przez: {user or 'System'}

Możesz teraz przystąpić do przekazania kodów zabezpieczeń do PLC.

---
Wiadomość automatyczna z systemu RM_MANAGER
"""
    
    email_status = 'PENDING'
    error_message = None
    
    con = _open_rm_connection(rm_db_path)
    
    try:
        # Wyślij email
        msg = MIMEMultipart()
        msg['From'] = config.get('smtp_user', 'RM_MANAGER')
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        if config.get('smtp_server') and config.get('smtp_user') and config.get('smtp_password'):
            try:
                server = smtplib.SMTP(config['smtp_server'], config.get('smtp_port', 587))
                server.starttls()
                server.login(config['smtp_user'], config['smtp_password'])
                server.send_message(msg)
                server.quit()
                
                email_status = 'SUCCESS'
                print(f"✅ Email wysłany do: {', '.join(recipients)}")
                
            except Exception as e:
                email_status = 'FAILED'
                error_message = str(e)
                print(f"❌ Błąd wysyłki email: {e}")
        else:
            email_status = 'FAILED'
            error_message = 'Brak konfiguracji SMTP (server/user/password)'
            print(f"⚠️ {error_message}")
        
        # Zapisz log wysyłki
        con.execute("""
            INSERT INTO payment_notifications_sent 
                (project_id, project_name, percentage, payment_date, recipients, 
                 sent_by, email_status, error_message, sent_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (project_id, project_name, percentage, payment_date, 
              json.dumps(recipients), user, email_status, error_message))
        
        _rm_safe_commit(con)
        
    finally:
        con.close()


def get_unread_notifications(rm_db_path: str) -> List[Dict]:
    """Pobierz nieprzeczytane powiadomienia in-app.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
    
    Returns:
        Lista powiadomień: id, project_id, project_name, notification_type, message, created_at
    """
    con = _open_rm_connection(rm_db_path)
    try:
        rows = con.execute("""
            SELECT id, project_id, project_name, notification_type, message, 
                   created_at, created_by
            FROM in_app_notifications
            WHERE is_read = 0
            ORDER BY created_at DESC
        """).fetchall()
        
        return [dict(row) for row in rows]
        
    finally:
        con.close()


def mark_notification_as_read(rm_db_path: str, notification_id: int, user: str = None):
    """Oznacz powiadomienie jako przeczytane.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        notification_id: ID powiadomienia
        user: Kto przeczytał
    """
    con = _open_rm_connection(rm_db_path)
    try:
        con.execute("""
            UPDATE in_app_notifications
            SET is_read = 1, read_at = CURRENT_TIMESTAMP, read_by = ?
            WHERE id = ?
        """, (user, notification_id))
        
        _rm_safe_commit(con)
        
    finally:
        con.close()


def get_payment_notifications_log(rm_db_path: str, project_id: int = None) -> List[Dict]:
    """Pobierz log wysłanych powiadomień email.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        project_id: Opcjonalnie - filtruj po projekcie
    
    Returns:
        Lista logów: id, project_id, project_name, percentage, payment_date, recipients, sent_at, email_status
    """
    con = _open_rm_connection(rm_db_path)
    try:
        if project_id:
            rows = con.execute("""
                SELECT id, project_id, project_name, percentage, payment_date, 
                       recipients, sent_at, sent_by, email_status, error_message
                FROM payment_notifications_sent
                WHERE project_id = ?
                ORDER BY sent_at DESC
            """, (project_id,)).fetchall()
        else:
            rows = con.execute("""
                SELECT id, project_id, project_name, percentage, payment_date, 
                       recipients, sent_at, sent_by, email_status, error_message
                FROM payment_notifications_sent
                ORDER BY sent_at DESC
                LIMIT 100
            """).fetchall()
        
        import json
        result = []
        for row in rows:
            d = dict(row)
            d['recipients'] = json.loads(d['recipients'] or '[]')
            result.append(d)
        
        return result
        
    finally:
        con.close()


# ============================================================================
# PLC UNLOCK CODES - Kody odblokowujące (2026-04-14)
# ============================================================================

def add_plc_code(rm_db_path: str, project_id: int, code_type: str, unlock_code: str,
                 description: str = None, user: str = None) -> int:
    """Dodaj kod odblokowujący PLC dla projektu.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        project_id: ID projektu
        code_type: Typ kodu: TEMPORARY, EXTENDED, PERMANENT
        unlock_code: Kod odblokowujący
        description: Opis kodu (opcjonalnie)
        user: Kto dodał
    
    Returns:
        ID dodanego kodu
        
    Raises:
        ValueError: Jeśli code_type nieprawidłowy
        
    Note:
        Dla TEMPORARY: expiry_date = created_at + 14 dni (automatycznie obliczane)
        Dla EXTENDED/PERMANENT: expiry_date = NULL
    """
    from datetime import datetime, timedelta
    
    valid_types = ['TEMPORARY', 'EXTENDED', 'PERMANENT']
    if code_type not in valid_types:
        raise ValueError(f"Nieprawidłowy typ kodu: {code_type}. Dozwolone: {valid_types}")
    
    con = _open_rm_connection(rm_db_path)
    try:
        # Oblicz expiry_date dla TEMPORARY (created_at + 14 dni)
        expiry_date = None
        if code_type == 'TEMPORARY':
            now = datetime.now()
            expiry_dt = now + timedelta(days=14)
            expiry_date = expiry_dt.strftime('%Y-%m-%d %H:%M:%S')
        
        cursor = con.execute("""
            INSERT INTO plc_unlock_codes 
                (project_id, code_type, unlock_code, description, created_by, created_at, is_used, expiry_date)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 0, ?)
        """, (project_id, code_type, unlock_code, description, user, expiry_date))
        
        code_id = cursor.lastrowid
        _rm_safe_commit(con)
        return code_id
        
    finally:
        con.close()


def update_plc_code(rm_db_path: str, code_id: int, unlock_code: str = None,
                    description: str = None, user: str = None):
    """Zaktualizuj kod PLC.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        code_id: ID kodu do zmiany
        unlock_code: Nowy kod (opcjonalnie)
        description: Nowy opis (opcjonalnie)
        user: Kto zmienił
    """
    con = _open_rm_connection(rm_db_path)
    try:
        updates = []
        params = []
        
        if unlock_code is not None:
            updates.append("unlock_code = ?")
            params.append(unlock_code)
        
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        
        if not updates:
            return  # Nic do zmiany
        
        updates.append("modified_by = ?")
        params.append(user)
        updates.append("modified_at = CURRENT_TIMESTAMP")
        
        params.append(code_id)
        query = f"UPDATE plc_unlock_codes SET {', '.join(updates)} WHERE id = ?"
        
        con.execute(query, params)
        _rm_safe_commit(con)
        
    finally:
        con.close()


def delete_plc_code(rm_db_path: str, code_id: int):
    """Usuń kod PLC.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        code_id: ID kodu do usunięcia
    """
    con = _open_rm_connection(rm_db_path)
    try:
        con.execute("DELETE FROM plc_unlock_codes WHERE id = ?", (code_id,))
        _rm_safe_commit(con)
    finally:
        con.close()


def get_plc_codes(rm_db_path: str, project_id: int) -> List[Dict]:
    """Pobierz wszystkie kody PLC dla projektu.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        project_id: ID projektu
    
    Returns:
        Lista słowników: id, code_type, unlock_code, description, created_by, 
                        created_at, modified_by, modified_at, is_used, used_at, used_by, notes,
                        sent_at, sent_by, sent_via, expiry_date
    """
    con = _open_rm_connection(rm_db_path)
    try:
        rows = con.execute("""
            SELECT id, project_id, code_type, unlock_code, description,
                   created_by, created_at, modified_by, modified_at,
                   is_used, used_at, used_by, notes,
                   sent_at, sent_by, sent_via, expiry_date
            FROM plc_unlock_codes
            WHERE project_id = ?
            ORDER BY 
                CASE code_type
                    WHEN 'TEMPORARY' THEN 1
                    WHEN 'EXTENDED' THEN 2
                    WHEN 'PERMANENT' THEN 3
                END,
                created_at
        """, (project_id,)).fetchall()
        
        return [dict(row) for row in rows]
        
    finally:
        con.close()


def save_plc_code_recipients(rm_db_path: str, code_id: int, recipient_ids: List[int]):
    """Zapisz listę odbiorców - GLOBALNA dla wszystkich projektów w RM_MANAGER."""
    import json
    
    print(f"\n💾 SAVE GLOBAL RECIPIENTS: db={rm_db_path}")
    print(f"   recipient_ids={recipient_ids}")
    
    con = _open_rm_connection(rm_db_path)
    try:
        # Upewnij się że tabela istnieje
        con.execute("""
            CREATE TABLE IF NOT EXISTS plc_global_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key TEXT NOT NULL UNIQUE,
                recipients_json TEXT NOT NULL,
                updated_by TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        recipients_json = json.dumps(recipient_ids) if recipient_ids else '[]'
        print(f"   recipients_json={recipients_json}")
        
        # UPSERT - INSERT jeśli nie ma, UPDATE jeśli jest
        con.execute("""
            INSERT INTO plc_global_recipients (setting_key, recipients_json, updated_at)
            VALUES ('default_recipients', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(setting_key) DO UPDATE SET
                recipients_json = excluded.recipients_json,
                updated_at = CURRENT_TIMESTAMP
        """, (recipients_json,))
        con.commit()
        
        # Weryfikacja zapisu
        verify = con.execute("SELECT recipients_json FROM plc_global_recipients WHERE setting_key='default_recipients'").fetchone()
        print(f"   ✅ WERYFIKACJA po zapisie: {verify['recipients_json'] if verify else 'BRAK REKORDU!'}")
    except Exception as e:
        print(f"   ❌ BŁĄD SAVE: {e}")
        import traceback
        traceback.print_exc()
    finally:
        con.close()


def get_plc_code_recipients(rm_db_path: str, code_id: int) -> List[int]:
    """Pobierz listę odbiorców - GLOBALNA dla wszystkich projektów w RM_MANAGER."""
    import json
    
    print(f"\n📚 GET GLOBAL RECIPIENTS: db={rm_db_path}")
    
    con = _open_rm_connection(rm_db_path)
    try:
        # Sprawdź czy tabela istnieje
        table_exists = con.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='plc_global_recipients'
        """).fetchone()
        
        print(f"   tabela plc_global_recipients istnieje: {bool(table_exists)}")
        
        if not table_exists:
            # Tabela nie istnieje - utwórz ją
            print(f"   ⚠️ Tworzę tabelę plc_global_recipients...")
            con.execute("""
                CREATE TABLE IF NOT EXISTS plc_global_recipients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    setting_key TEXT NOT NULL UNIQUE,
                    recipients_json TEXT NOT NULL,
                    updated_by TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                INSERT OR IGNORE INTO plc_global_recipients (setting_key, recipients_json)
                VALUES ('default_recipients', '[]')
            """)
            con.commit()
            print(f"   ✅ Tabela utworzona, zwracam []")
            return []
        
        # Pobierz z globalnej tabeli
        row = con.execute("""
            SELECT recipients_json
            FROM plc_global_recipients
            WHERE setting_key = 'default_recipients'
        """).fetchone()
        
        print(f"   row={dict(row) if row else None}")
        
        if row and row['recipients_json']:
            try:
                result = json.loads(row['recipients_json'])
                print(f"   ✅ Zwracam {len(result)} odbiorców: {result}")
                return result if result else []
            except (json.JSONDecodeError, TypeError) as e:
                print(f"   ❌ Błąd JSON: {e}")
                return []
        
        print(f"   ⚠️ Brak rekordu lub pusty recipients_json")
        return []
        
    except Exception as e:
        print(f"   ❌ BŁĄD GET: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        con.close()


def mark_plc_code_as_used(rm_db_path: str, code_id: int, user: str = None, notes: str = None):
    """Oznacz kod PLC jako użyty (przekazany klientowi).
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        code_id: ID kodu
        user: Kto użył
        notes: Notatki (opcjonalnie)
    """
    con = _open_rm_connection(rm_db_path)
    try:
        con.execute("""
            UPDATE plc_unlock_codes
            SET is_used = 1, used_at = CURRENT_TIMESTAMP, used_by = ?, notes = ?
            WHERE id = ?
        """, (user, notes, code_id))
        
        _rm_safe_commit(con)
        
    finally:
        con.close()


def get_plc_codes_summary(rm_db_path: str, project_id: int) -> Dict:
    """Pobierz podsumowanie kodów PLC dla projektu.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        project_id: ID projektu
    
    Returns:
        Dict z liczbą kodów per typ i statusem użycia
    """
    con = _open_rm_connection(rm_db_path)
    try:
        rows = con.execute("""
            SELECT code_type, is_used, COUNT(*) as count
            FROM plc_unlock_codes
            WHERE project_id = ?
            GROUP BY code_type, is_used
        """, (project_id,)).fetchall()
        
        summary = {
            'TEMPORARY': {'total': 0, 'used': 0, 'unused': 0},
            'EXTENDED': {'total': 0, 'used': 0, 'unused': 0},
            'PERMANENT': {'total': 0, 'used': 0, 'unused': 0}
        }
        
        for row in rows:
            code_type = row['code_type']
            is_used = row['is_used']
            count = row['count']
            
            summary[code_type]['total'] += count
            if is_used:
                summary[code_type]['used'] += count
            else:
                summary[code_type]['unused'] += count
        
        return summary
        
    finally:
        con.close()


def calculate_code_expiry_date(created_at: str, code_type: str) -> str:
    """Oblicz datę wygaśnięcia kodu TEMPORARY (utworzenie + 14 dni).
    
    DEPRECATED: Ta funkcja jest już nieużywana. 
    Data wygaśnięcia jest teraz obliczana automatycznie przy dodawaniu kodu (add_plc_code)
    i zapisywana w kolumnie expiry_date.
    
    Args:
        created_at: Data utworzenia kodu (ISO format: YYYY-MM-DD HH:MM:SS)
        code_type: Typ kodu
    
    Returns:
        Data wygaśnięcia (ISO format) lub None jeśli nie TEMPORARY
    """
    if code_type != 'TEMPORARY' or not created_at:
        return None
    
    from datetime import datetime, timedelta
    
    try:
        # Parse data utworzenia
        created_date = datetime.fromisoformat(created_at.replace(' ', 'T'))
        # Dodaj 14 dni
        expiry = created_date + timedelta(days=14)
        return expiry.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return None


def get_payment_total_percentage(rm_db_path: str, project_id: int) -> float:
    """Oblicz łączny procent płatności dla projektu.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        project_id: ID projektu
    
    Returns:
        Suma procentów płatności (0-100+)
    """
    con = _open_rm_connection(rm_db_path)
    try:
        row = con.execute("""
            SELECT COALESCE(SUM(percentage), 0) as total
            FROM payment_milestones
            WHERE project_id = ?
        """, (project_id,)).fetchone()
        
        return row['total'] if row else 0.0
        
    finally:
        con.close()


def is_user_authorized_for_plc_sending(rm_db_path: str, username: str) -> bool:
    """Sprawdź czy użytkownik ma uprawnienia do wysyłki kodów PLC.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        username: Nazwa użytkownika
    
    Returns:
        True jeśli uprawniony
    """
    con = _open_rm_connection(rm_db_path)
    try:
        row = con.execute("""
            SELECT COUNT(*) as cnt
            FROM plc_authorized_senders
            WHERE username = ?
        """, (username,)).fetchone()
        
        return row['cnt'] > 0 if row else False
        
    finally:
        con.close()


def add_plc_authorized_sender(rm_db_path: str, username: str, added_by: str = None, notes: str = None):
    """Dodaj użytkownika do listy uprawnionych do wysyłki kodów.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        username: Nazwa użytkownika
        added_by: Kto dodał
        notes: Notatki (opcjonalnie)
    """
    con = _open_rm_connection(rm_db_path)
    try:
        con.execute("""
            INSERT OR IGNORE INTO plc_authorized_senders (username, added_by, notes)
            VALUES (?, ?, ?)
        """, (username, added_by, notes))
        
        _rm_safe_commit(con)
        
    finally:
        con.close()


def remove_plc_authorized_sender(rm_db_path: str, username: str):
    """Usuń użytkownika z listy uprawnionych.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        username: Nazwa użytkownika
    """
    con = _open_rm_connection(rm_db_path)
    try:
        con.execute("DELETE FROM plc_authorized_senders WHERE username = ?", (username,))
        _rm_safe_commit(con)
        
    finally:
        con.close()


def get_plc_authorized_senders(rm_db_path: str) -> List[Dict]:
    """Pobierz listę użytkowników uprawnionych do wysyłki kodów.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
    
    Returns:
        Lista słowników: username, added_by, added_at, notes
    """
    con = _open_rm_connection(rm_db_path)
    try:
        rows = con.execute("""
            SELECT username, added_by, added_at, notes
            FROM plc_authorized_senders
            ORDER BY added_at DESC
        """).fetchall()
        
        return [dict(row) for row in rows]
        
    finally:
        con.close()


def send_plc_code_email(rm_db_path: str, code_id: int, recipient_emails: List[str], 
                        subject: str, message: str, user: str = None, role: str = None) -> bool:
    """Wyślij kod PLC przez email.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        code_id: ID kodu do wysłania
        recipient_emails: Lista adresów email odbiorców
        subject: Temat wiadomości email
        message: Treść wiadomości
        user: Kto wysyła
        role: Rola użytkownika (ADMIN ma automatyczne uprawnienia)
    
    Returns:
        True jeśli wysłano pomyślnie
    
    Raises:
        ValueError: Jeśli użytkownik nie ma uprawnień lub brak konfiguracji email
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from datetime import datetime
    
    # Sprawdź uprawnienia (ADMIN ma zawsze dostęp)
    if user and role != 'ADMIN' and not is_user_authorized_for_plc_sending(rm_db_path, user):
        raise ValueError(f"Użytkownik {user} nie ma uprawnień do wysyłki kodów PLC")
    
    # Pobierz konfigurację email
    email_config = get_payment_notification_config(rm_db_path)
    if not email_config or not email_config.get('enabled'):
        raise ValueError("Wysyłka email nie jest skonfigurowana lub wyłączona")
    
    # Wyślij email
    try:
        msg = MIMEMultipart()
        msg['From'] = email_config.get('smtp_user', 'RM_MANAGER')
        msg['To'] = ', '.join(recipient_emails)
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain', 'utf-8'))
        
        if email_config.get('smtp_server') and email_config.get('smtp_user') and email_config.get('smtp_password'):
            smtp_port = email_config.get('smtp_port', 587)
            print(f"📧 Łączenie z SMTP: {email_config['smtp_server']}:{smtp_port}")
            
            if smtp_port == 465:
                # Port 465 = SSL (SMTP_SSL)
                server = smtplib.SMTP_SSL(email_config['smtp_server'], smtp_port, timeout=30)
            else:
                # Port 587 = STARTTLS
                server = smtplib.SMTP(email_config['smtp_server'], smtp_port, timeout=30)
                print("📧 SMTP połączony, starttls...")
                server.starttls()
            
            print("📧 TLS OK, logowanie...")
            server.login(email_config['smtp_user'], email_config['smtp_password'])
            print("📧 Zalogowano, wysyłanie...")
            server.send_message(msg)
            print("📧 Wysłano, zamykanie...")
            server.quit()
            
            print(f"✅ Email wysłany do: {', '.join(recipient_emails)}")
        else:
            raise ValueError('Brak konfiguracji SMTP (server/user/password)')
        
        # Zaktualizuj informację o wysłaniu i oznacz jako użyty
        con = _open_rm_connection(rm_db_path)
        try:
            con.execute("""
                UPDATE plc_unlock_codes
                SET sent_at = CURRENT_TIMESTAMP, sent_by = ?, sent_via = 'EMAIL',
                    is_used = 1, used_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (user, code_id))
            _rm_safe_commit(con)
        finally:
            con.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Błąd wysyłki email: {e}")
        raise


def send_plc_code_sms(rm_db_path: str, code_id: int, phone_numbers: List[str], 
                      message: str, user: str = None, role: str = None,
                      sms_config: dict = None) -> bool:
    """Wyślij kod PLC przez SMS.
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite (master)
        code_id: ID kodu do wysłania
        phone_numbers: Lista numerów telefonów odbiorców (format: 48123456789)
        message: Treść SMS
        user: Kto wysyła
        role: Rola użytkownika (ADMIN ma automatyczne uprawnienia)
        sms_config: Konfiguracja SMS (dict z sms_enabled, sms_api_token)
    
    Returns:
        True jeśli wysłano pomyślnie
    
    Raises:
        ValueError: Jeśli użytkownik nie ma uprawnień lub brak konfiguracji SMS
    """
    import json
    import os
    
    # Sprawdź uprawnienia (ADMIN ma zawsze dostęp)
    if user and role != 'ADMIN' and not is_user_authorized_for_plc_sending(rm_db_path, user):
        raise ValueError(f"Użytkownik {user} nie ma uprawnień do wysyłki kodów PLC")
    
    # Pobierz konfigurację SMS
    config = sms_config or {}
    if not config:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(script_dir, 'manager_sync_config.json')
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
    
    sms_enabled = config.get('sms_enabled', False)
    sms_token = config.get('sms_api_token', '')
    
    if not sms_enabled:
        raise ValueError("Wysyłka SMS jest wyłączona w konfiguracji")
    
    if not sms_token:
        raise ValueError("Brak tokenu API dla SMS (sms_api_token w manager_sync_config.json)")
    
    # Wyślij SMS do wszystkich odbiorców
    success_count = 0
    last_error = None
    for phone in phone_numbers:
        try:
            if _send_sms_smsapi(phone, message, sms_token):
                success_count += 1
        except Exception as e:
            last_error = e
            print(f"❌ Błąd wysyłki SMS do {phone}: {e}")
    
    if success_count == 0:
        raise ValueError(f"Nie wysłano żadnego SMS: {last_error}")
    
    # Zaktualizuj informację o wysłaniu i oznacz jako użyty
    con = _open_rm_connection(rm_db_path)
    try:
        con.execute("""
            UPDATE plc_unlock_codes
            SET sent_at = CURRENT_TIMESTAMP, sent_by = ?, sent_via = 'SMS',
                is_used = 1, used_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (user, code_id))
        _rm_safe_commit(con)
    finally:
        con.close()
    
    print(f"✅ Wysłano SMS do {success_count}/{len(phone_numbers)} odbiorców")
    return True


def _send_sms_smsapi(phone: str, message: str, token: str) -> bool:
    """Wyślij SMS przez SMSAPI.pl (wbudowane, bez zależności od sms_sender.py).
    
    Args:
        phone: Numer telefonu (np. '48123456789' lub '123456789')
        message: Treść SMS
        token: Token OAuth z panelu SMSAPI.pl
    
    Returns:
        True jeśli wysłano, False przy błędzie
    """
    import requests
    
    # Normalizuj numer (dodaj 48 jeśli brak)
    if not phone.startswith('48') and not phone.startswith('+'):
        phone = '48' + phone
    phone = phone.replace('+', '')
    
    print(f"📱 Wysyłanie SMS do: +{phone}")
    print(f"💬 Treść ({len(message)} znaków): {message[:100]}")
    
    url = 'https://api.smsapi.pl/sms.do'
    headers = {'Authorization': f'Bearer {token}'}
    data = {
        'to': phone,
        'message': message,
        'format': 'json',
        'encoding': 'utf-8',  # Obsługa polskich znaków (ĄĆĘŁŃÓŚŹŻąćęłńóśźż)
        'normalize': '1'       # Automatyczna normalizacja znaków specjalnych
    }
    
    resp = requests.post(url, headers=headers, data=data, timeout=30)
    result = resp.json()
    
    if 'error' in result:
        error_msg = result.get('message', result.get('error', 'Nieznany błąd'))
        print(f"❌ SMSAPI błąd: {error_msg}")
        raise ValueError(f"SMSAPI: {error_msg}")
    
    print(f"✅ SMS wysłany!")
    return True


def send_custom_sms(rm_db_path: str, project_id: int, message: str, 
                    config: dict, phone_number: str) -> dict:
    """Wyślij niestandardowy SMS (test SMS z menu Narzędzia).
    
    Args:
        rm_db_path: Ścieżka do rm_manager.sqlite
        project_id: ID projektu
        message: Treść SMS
        config: Konfiguracja z manager_sync_config.json
        phone_number: Numer telefonu odbiorcy
    
    Returns:
        Dict z kluczami: success (int), message (str), errors (list)
    """
    sms_enabled = config.get('sms_enabled', False)
    sms_token = config.get('sms_api_token', '')
    
    if not sms_enabled:
        return {'success': 0, 'message': 'SMS wyłączony w konfiguracji', 'errors': []}
    
    if not sms_token:
        return {'success': 0, 'message': 'Brak tokenu SMSAPI', 'errors': []}
    
    try:
        if _send_sms_smsapi(phone_number, message, sms_token):
            return {'success': 1, 'message': f'SMS wysłany do {phone_number}', 'errors': []}
        else:
            return {'success': 0, 'message': 'Wysyłka nie powiodła się', 'errors': ['Zwrócono False']}
    except Exception as e:
        return {'success': 0, 'message': str(e), 'errors': [str(e)]}


# ============================================================================
# OPTYMALIZATOR PRODUKCJI — CRUD ograniczeń zasobów (2026-04-19)
# ============================================================================

def get_resource_constraints(rm_master_db_path: str, active_only: bool = True) -> List[Dict]:
    """Pobierz ograniczenia zasobów."""
    ensure_rm_master_tables(rm_master_db_path)
    con = _open_rm_connection(rm_master_db_path)
    try:
        where = "WHERE is_active = 1" if active_only else ""
        rows = con.execute(f"""
            SELECT * FROM resource_constraints {where}
            ORDER BY constraint_type, category, stage_code
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def save_resource_constraint(rm_master_db_path: str, data: Dict, user: str = None) -> int:
    """Dodaj lub zaktualizuj ograniczenie zasobu.
    
    data keys: id (opt), constraint_type, category, stage_code, max_parallel, description, is_active
    """
    con = _open_rm_connection(rm_master_db_path)
    try:
        if data.get('id'):
            con.execute("""
                UPDATE resource_constraints
                SET constraint_type = ?, category = ?, stage_code = ?,
                    max_parallel = ?, description = ?, is_active = ?,
                    modified_at = CURRENT_TIMESTAMP, modified_by = ?
                WHERE id = ?
            """, (data['constraint_type'], data.get('category'),
                  data.get('stage_code'), data.get('max_parallel', 1),
                  data.get('description'), data.get('is_active', 1),
                  user, data['id']))
            _rm_safe_commit(con)
            return data['id']
        else:
            cursor = con.execute("""
                INSERT INTO resource_constraints
                    (constraint_type, category, stage_code, max_parallel,
                     description, is_active, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (data['constraint_type'], data.get('category'),
                  data.get('stage_code'), data.get('max_parallel', 1),
                  data.get('description'), data.get('is_active', 1),
                  user))
            _rm_safe_commit(con)
            return cursor.lastrowid
    finally:
        con.close()


def delete_resource_constraint(rm_master_db_path: str, constraint_id: int):
    """Usuń ograniczenie zasobu."""
    con = _open_rm_connection(rm_master_db_path)
    try:
        con.execute("DELETE FROM resource_constraints WHERE id = ?", (constraint_id,))
        _rm_safe_commit(con)
    finally:
        con.close()


# ============================================================================
# OPTYMALIZATOR — dostępność pracowników
# ============================================================================

def get_employee_availability(rm_master_db_path: str, employee_id: int = None,
                              date_from: str = None, date_to: str = None) -> List[Dict]:
    """Pobierz okresy niedostępności pracowników.
    
    Filtruje po employee_id i/lub po zakresie dat (overlap).
    """
    con = _open_rm_connection(rm_master_db_path)
    try:
        clauses, params = [], []
        if employee_id is not None:
            clauses.append("ea.employee_id = ?")
            params.append(employee_id)
        if date_from:
            clauses.append("ea.date_to >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("ea.date_from <= ?")
            params.append(date_to)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = con.execute(f"""
            SELECT ea.*, e.name AS employee_name, e.category AS employee_category
            FROM employee_availability ea
            JOIN employees e ON ea.employee_id = e.id
            {where}
            ORDER BY ea.date_from
        """, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def save_employee_availability(rm_master_db_path: str, data: Dict, user: str = None) -> int:
    """Dodaj lub zaktualizuj okres niedostępności.
    
    data keys: id (opt), employee_id, date_from, date_to, reason, notes
    """
    con = _open_rm_connection(rm_master_db_path)
    try:
        if data.get('id'):
            con.execute("""
                UPDATE employee_availability
                SET employee_id = ?, date_from = ?, date_to = ?, reason = ?, notes = ?
                WHERE id = ?
            """, (data['employee_id'], data['date_from'], data['date_to'],
                  data['reason'], data.get('notes'), data['id']))
            _rm_safe_commit(con)
            return data['id']
        else:
            cursor = con.execute("""
                INSERT INTO employee_availability
                    (employee_id, date_from, date_to, reason, notes, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (data['employee_id'], data['date_from'], data['date_to'],
                  data['reason'], data.get('notes'), user))
            _rm_safe_commit(con)
            return cursor.lastrowid
    finally:
        con.close()


def delete_employee_availability(rm_master_db_path: str, avail_id: int):
    """Usuń okres niedostępności."""
    con = _open_rm_connection(rm_master_db_path)
    try:
        con.execute("DELETE FROM employee_availability WHERE id = ?", (avail_id,))
        _rm_safe_commit(con)
    finally:
        con.close()


# ============================================================================
# OPTYMALIZATOR — kalendarz firmowy
# ============================================================================

def get_company_calendar(rm_master_db_path: str, date_from: str = None,
                         date_to: str = None) -> List[Dict]:
    """Pobierz dni firmowe (wolne, święta, soboty pracujące)."""
    con = _open_rm_connection(rm_master_db_path)
    try:
        clauses, params = [], []
        if date_from:
            clauses.append("date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("date <= ?")
            params.append(date_to)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = con.execute(f"""
            SELECT * FROM company_calendar {where} ORDER BY date
        """, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def save_company_calendar_day(rm_master_db_path: str, date: str, day_type: str,
                              description: str = None, user: str = None) -> int:
    """Dodaj lub nadpisz dzień w kalendarzu firmowym."""
    con = _open_rm_connection(rm_master_db_path)
    try:
        cursor = con.execute("""
            INSERT OR REPLACE INTO company_calendar (date, day_type, description, created_by)
            VALUES (?, ?, ?, ?)
        """, (date, day_type, description, user))
        _rm_safe_commit(con)
        return cursor.lastrowid
    finally:
        con.close()


def delete_company_calendar_day(rm_master_db_path: str, date: str):
    """Usuń dzień z kalendarza firmowego."""
    con = _open_rm_connection(rm_master_db_path)
    try:
        con.execute("DELETE FROM company_calendar WHERE date = ?", (date,))
        _rm_safe_commit(con)
    finally:
        con.close()


def get_working_days(rm_master_db_path: str, date_from: str, date_to: str) -> List[str]:
    """Zwróć listę dni roboczych w podanym przedziale.
    
    Uwzględnia:
    - Weekendy (sob/ndz = wolne, chyba że SATURDAY_WORK)
    - Święta i dni wolne z company_calendar
    """
    cal_entries = {}
    con = _open_rm_connection(rm_master_db_path)
    try:
        rows = con.execute("""
            SELECT date, day_type FROM company_calendar
            WHERE date >= ? AND date <= ?
        """, (date_from, date_to)).fetchall()
        for r in rows:
            cal_entries[r['date']] = r['day_type']
    finally:
        con.close()

    start = datetime.fromisoformat(date_from).date() if isinstance(date_from, str) else date_from
    end = datetime.fromisoformat(date_to).date() if isinstance(date_to, str) else date_to

    working = []
    current = start
    while current <= end:
        iso = current.isoformat()
        wd = current.weekday()  # 0=Mon .. 6=Sun

        if iso in cal_entries:
            ct = cal_entries[iso]
            if ct == 'SATURDAY_WORK':
                working.append(iso)
            # HOLIDAY / COMPANY_DAY_OFF → wolne
        elif wd < 5:
            # Pon-Pt → roboczy
            working.append(iso)
        # Sob/Ndz bez wpisu → wolne

        current += timedelta(days=1)

    return working


def save_optimization_run(rm_master_db_path: str, data: Dict, user: str = None) -> int:
    """Zapisz wynik optymalizacji."""
    import json
    con = _open_rm_connection(rm_master_db_path)
    try:
        cursor = con.execute("""
            INSERT INTO optimization_runs
                (run_mode, project_ids_json, date_range_start, date_range_end,
                 constraints_snapshot, result_json, score_before, score_after,
                 solver_status, solver_time_ms, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['run_mode'],
            json.dumps(data['project_ids']),
            data.get('date_range_start'),
            data.get('date_range_end'),
            json.dumps(data.get('constraints_snapshot', {})),
            json.dumps(data.get('result', {})),
            data.get('score_before'),
            data.get('score_after'),
            data.get('solver_status'),
            data.get('solver_time_ms'),
            user
        ))
        _rm_safe_commit(con)
        return cursor.lastrowid
    finally:
        con.close()


def mark_optimization_applied(rm_master_db_path: str, run_id: int, user: str = None):
    """Oznacz zapis optymalizacji jako zastosowany."""
    con = _open_rm_connection(rm_master_db_path)
    try:
        con.execute("""
            UPDATE optimization_runs
            SET applied = 1, applied_at = CURRENT_TIMESTAMP, applied_by = ?
            WHERE id = ?
        """, (user, run_id))
        _rm_safe_commit(con)
    finally:
        con.close()


def get_optimization_runs(rm_master_db_path: str, limit: int = 20) -> List[Dict]:
    """Pobierz historię optymalizacji."""
    con = _open_rm_connection(rm_master_db_path)
    try:
        rows = con.execute("""
            SELECT * FROM optimization_runs
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


# ============================================================================
# OPTYMALIZATOR — pobieranie danych wielu projektów (dla solvera)
# ============================================================================


def sync_staff_json_to_table(rm_manager_dir: str, project_ids: List[int]) -> Dict:
    """Jednorazowa migracja: synchronizuj assigned_staff JSON → stage_staff_assignments.

    Dla każdego etapu: jeśli pracownik jest w JSON ale nie w tabeli, dodaj wpis.
    Nie usuwa nadmiarowych wpisów z tabeli.

    Returns:
        {'synced': int, 'skipped': int, 'errors': list}
    """
    import json as _json

    synced = 0
    skipped = 0
    errors = []

    for pid in project_ids:
        db_path = get_project_db_path(rm_manager_dir, pid)
        if not Path(db_path).exists():
            continue

        con = _open_rm_connection(db_path)
        try:
            # Sprawdź czy obie tabele istnieją
            has_ps = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='project_stages'"
            ).fetchone()
            has_ssa = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='stage_staff_assignments'"
            ).fetchone()
            if not has_ps or not has_ssa:
                skipped += 1
                continue

            rows = con.execute("""
                SELECT ps.id AS ps_id, ps.stage_code, ps.assigned_staff,
                       ss.template_start, ss.template_end
                FROM project_stages ps
                LEFT JOIN stage_schedule ss ON ss.project_stage_id = ps.id
                WHERE ps.project_id = ?
            """, (pid,)).fetchall()

            for row in rows:
                try:
                    staff_json = _json.loads(row['assigned_staff'] or '[]')
                except (_json.JSONDecodeError, TypeError):
                    continue

                for entry in staff_json:
                    if not isinstance(entry, dict) or 'employee_id' not in entry:
                        continue
                    eid = entry['employee_id']
                    # Sprawdź czy już jest w tabeli
                    existing = con.execute("""
                        SELECT id FROM stage_staff_assignments
                        WHERE project_stage_id = ? AND employee_id = ?
                    """, (row['ps_id'], eid)).fetchone()
                    if existing:
                        continue
                    # Wstaw
                    con.execute("""
                        INSERT INTO stage_staff_assignments
                            (project_stage_id, employee_id, planned_start, planned_end,
                             assigned_by)
                        VALUES (?, ?, ?, ?, ?)
                    """, (row['ps_id'], eid,
                          row['template_start'], row['template_end'],
                          'migration'))
                    synced += 1

            _rm_safe_commit(con)
        except Exception as e:
            errors.append(f"pid={pid}: {e}")
        finally:
            con.close()

    return {'synced': synced, 'skipped': skipped, 'errors': errors}


def get_projects_scheduling_data(rm_manager_dir: str, rm_master_db_path: str,
                                 project_ids: List[int]) -> Dict:
    """Pobierz wszystkie dane potrzebne do optymalizacji dla podanych projektów.
    
    Returns:
        {
            'projects': {
                pid: {
                    'stages': {stage_code: {template_start, template_end, duration_days, is_actual, is_active}},
                    'dependencies': [(pred, succ, type, lag)],
                    'staff': {stage_code: [employee_id, ...]},
                    'forecast': {stage_code: {forecast_start, forecast_end, ...}},
                }
            },
            'employees': {eid: {name, category, is_active}},
            'constraints': [...],
            'availability': [...],
            'calendar': [...]
        }
    """
    import json

    employees_list = get_employees(rm_master_db_path, active_only=False)
    employees = {e['id']: e for e in employees_list}

    constraints = get_resource_constraints(rm_master_db_path, active_only=True)
    availability = get_employee_availability(rm_master_db_path)
    calendar = get_company_calendar(rm_master_db_path)

    projects = {}
    for pid in project_ids:
        db_path = get_project_db_path(rm_manager_dir, pid)
        print(f"⚡ scheduling_data: pid={pid}, db_path={db_path}, exists={Path(db_path).exists()}")
        if not Path(db_path).exists():
            continue

        con = _open_rm_connection(db_path)
        try:
            # Sprawdź czy tabela project_stages istnieje
            tbl_check = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='project_stages'"
            ).fetchone()
            if not tbl_check:
                print(f"⚡ scheduling_data: pid={pid} — brak tabeli project_stages, pomijam")
                continue

            rows = con.execute("""
                SELECT ps.stage_code, ps.assigned_staff, ps.sequence,
                       ss.template_start, ss.template_end
                FROM project_stages ps
                LEFT JOIN stage_schedule ss ON ss.project_stage_id = ps.id
                JOIN stage_definitions sd ON ps.stage_code = sd.code
                WHERE ps.project_id = ? AND ps.stage_code != 'WSTRZYMANY'
                ORDER BY ps.sequence
            """, (pid,)).fetchall()

            stages = {}
            staff_map = {}
            staff_dates = {}  # {stage_code: [{employee_id, planned_start, planned_end}]}
            for row in rows:
                sc = row['stage_code']
                t_start = row['template_start']
                t_end = row['template_end']

                duration = 5
                if t_start and t_end:
                    try:
                        d0 = datetime.fromisoformat(t_start)
                        d1 = datetime.fromisoformat(t_end)
                        duration = max(1, (d1 - d0).days)
                    except (ValueError, TypeError):
                        pass

                stages[sc] = {
                    'template_start': t_start,
                    'template_end': t_end,
                    'duration_days': duration,
                    'sequence': row['sequence'],
                }

            # Przypisania z nowej tabeli (z datami)
            try:
                ssa_rows = con.execute("""
                    SELECT ps.stage_code, ssa.employee_id,
                           ssa.planned_start, ssa.planned_end
                    FROM stage_staff_assignments ssa
                    JOIN project_stages ps ON ssa.project_stage_id = ps.id
                    WHERE ps.project_id = ?
                """, (pid,)).fetchall()
                for sr in ssa_rows:
                    sc = sr['stage_code']
                    if sc not in staff_map:
                        staff_map[sc] = []
                        staff_dates[sc] = []
                    staff_map[sc].append(sr['employee_id'])
                    staff_dates[sc].append({
                        'employee_id': sr['employee_id'],
                        'planned_start': sr['planned_start'],
                        'planned_end': sr['planned_end'],
                    })
            except sqlite3.OperationalError:
                pass  # Stara baza bez tabeli

            # Fallback per-etap: jeśli etap nie ma wpisów w nowej tabeli, czytaj z JSON
            for row in rows:
                sc = row['stage_code']
                if sc not in staff_map or not staff_map[sc]:
                    assigned = []
                    try:
                        staff_json = json.loads(row['assigned_staff'] or '[]')
                        assigned = [s['employee_id'] for s in staff_json
                                    if isinstance(s, dict) and 'employee_id' in s]
                    except (json.JSONDecodeError, TypeError):
                        pass
                    if assigned:
                        staff_map[sc] = assigned

            deps_rows = con.execute("""
                SELECT predecessor_stage_code, successor_stage_code,
                       dependency_type, lag_days
                FROM stage_dependencies WHERE project_id = ?
            """, (pid,)).fetchall()
            dependencies = [(r['predecessor_stage_code'], r['successor_stage_code'],
                             r['dependency_type'], r['lag_days'])
                            for r in deps_rows]

            actuals_rows = con.execute("""
                SELECT ps.stage_code, sap.started_at, sap.ended_at
                FROM stage_actual_periods sap
                JOIN project_stages ps ON sap.project_stage_id = ps.id
                WHERE ps.project_id = ?
            """, (pid,)).fetchall()

            for ar in actuals_rows:
                sc = ar['stage_code']
                if sc in stages:
                    if ar['ended_at']:
                        # Zakończony okres — ustaw is_actual TYLKO gdy etap
                        # nie jest już oznaczony jako aktywny (przerywane etapy)
                        if not stages[sc].get('is_active'):
                            stages[sc]['is_actual'] = True
                            stages[sc]['actual_start'] = ar['started_at']
                            stages[sc]['actual_end'] = ar['ended_at']
                    elif ar['started_at'] and not ar['ended_at']:
                        # Aktywny okres — ZAWSZE wygrywa nad zakończonym
                        stages[sc]['is_active'] = True
                        stages[sc]['actual_start'] = ar['started_at']
                        stages[sc].pop('is_actual', None)
                        stages[sc].pop('actual_end', None)

        finally:
            con.close()

        try:
            forecast = recalculate_forecast(db_path, pid)
        except Exception:
            forecast = {}

        projects[pid] = {
            'stages': stages,
            'dependencies': dependencies,
            'staff': staff_map,
            'staff_dates': staff_dates,
            'forecast': forecast,
        }

    return {
        'projects': projects,
        'employees': employees,
        'constraints': constraints,
        'availability': availability,
        'calendar': calendar,
    }


def apply_optimization_result(rm_manager_dir: str, project_id: int,
                              stage_dates: Dict[str, Tuple[str, str]]):
    """Zastosuj wynik optymalizacji — nadpisz template_start/template_end
    + aktualizuj planned_start/planned_end w stage_staff_assignments.
    
    stage_dates: {stage_code: (new_start_iso, new_end_iso)}
    """
    db_path = get_project_db_path(rm_manager_dir, project_id)
    con = _open_rm_connection(db_path)
    try:
        for stage_code, (new_start, new_end) in stage_dates.items():
            row = con.execute("""
                SELECT ps.id AS ps_id, ss.id AS ss_id
                FROM project_stages ps
                LEFT JOIN stage_schedule ss ON ss.project_stage_id = ps.id
                WHERE ps.project_id = ? AND ps.stage_code = ?
            """, (project_id, stage_code)).fetchone()

            if not row:
                continue

            if row['ss_id']:
                con.execute("""
                    UPDATE stage_schedule SET template_start = ?, template_end = ?
                    WHERE id = ?
                """, (new_start, new_end, row['ss_id']))
            else:
                con.execute("""
                    INSERT INTO stage_schedule (project_stage_id, template_start, template_end)
                    VALUES (?, ?, ?)
                """, (row['ps_id'], new_start, new_end))

            # Zaktualizuj daty przypisań pracowników
            try:
                con.execute("""
                    UPDATE stage_staff_assignments
                    SET planned_start = ?, planned_end = ?
                    WHERE project_stage_id = ?
                      AND actual_start IS NULL
                """, (new_start, new_end, row['ps_id']))
            except sqlite3.OperationalError:
                pass  # stara baza bez tabeli

        _rm_safe_commit(con)
    finally:
        con.close()


def snapshot_before_optimization(rm_manager_dir: str, project_id: int,
                                  stage_codes: list) -> Dict:
    """Zapisz snapshot dat template i staff przed optymalizacją (do cofania).

    Returns:
        {'stage_code': {'template_start', 'template_end',
                        'staff': [{'id', 'planned_start', 'planned_end'}]}}
    """
    db_path = get_project_db_path(rm_manager_dir, project_id)
    con = _open_rm_connection(db_path)
    snapshot = {}
    try:
        for sc in stage_codes:
            row = con.execute("""
                SELECT ps.id AS ps_id, ss.template_start, ss.template_end
                FROM project_stages ps
                LEFT JOIN stage_schedule ss ON ss.project_stage_id = ps.id
                WHERE ps.project_id = ? AND ps.stage_code = ?
            """, (project_id, sc)).fetchone()
            if not row:
                continue
            entry = {
                'template_start': row['template_start'],
                'template_end': row['template_end'],
                'staff': [],
            }
            try:
                staff_rows = con.execute("""
                    SELECT id, planned_start, planned_end
                    FROM stage_staff_assignments
                    WHERE project_stage_id = ? AND actual_start IS NULL
                """, (row['ps_id'],)).fetchall()
                entry['staff'] = [{'id': r['id'],
                                   'planned_start': r['planned_start'],
                                   'planned_end': r['planned_end']} for r in staff_rows]
            except sqlite3.OperationalError:
                pass
            snapshot[sc] = entry
    finally:
        con.close()
    return snapshot


def restore_optimization_snapshot(rm_manager_dir: str, project_id: int,
                                   snapshot: Dict):
    """Przywróć daty sprzed optymalizacji z snapshotu.

    snapshot: {stage_code: {'template_start', 'template_end',
                            'staff': [{'id', 'planned_start', 'planned_end'}]}}
    """
    db_path = get_project_db_path(rm_manager_dir, project_id)
    con = _open_rm_connection(db_path)
    try:
        for sc, entry in snapshot.items():
            row = con.execute("""
                SELECT ps.id AS ps_id, ss.id AS ss_id
                FROM project_stages ps
                LEFT JOIN stage_schedule ss ON ss.project_stage_id = ps.id
                WHERE ps.project_id = ? AND ps.stage_code = ?
            """, (project_id, sc)).fetchone()
            if not row:
                continue
            if row['ss_id']:
                con.execute("""
                    UPDATE stage_schedule SET template_start = ?, template_end = ?
                    WHERE id = ?
                """, (entry['template_start'], entry['template_end'], row['ss_id']))
            for sa in entry.get('staff', []):
                try:
                    con.execute("""
                        UPDATE stage_staff_assignments
                        SET planned_start = ?, planned_end = ?
                        WHERE id = ?
                    """, (sa['planned_start'], sa['planned_end'], sa['id']))
                except sqlite3.OperationalError:
                    pass
        _rm_safe_commit(con)
    finally:
        con.close()

