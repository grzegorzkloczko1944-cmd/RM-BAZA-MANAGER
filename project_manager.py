"""
============================================================================
PROJECT MANAGER - Zarządzanie projektami dla RM_BAZA v10 DISTRIBUTED
============================================================================
Funkcje do zarządzania projektami w master.sqlite:
- Tworzenie nowych projektów
- Edycja projektów (nazwa, ścieżka)
- Aktywacja/dezaktywacja projektów
- Usuwanie projektów
============================================================================
"""

import sqlite3
from pathlib import Path
from typing import Optional, Tuple, List
import re


def norm(s) -> str:
    """Normalizacja tekstu: usuń nadmiarowe spacje"""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).replace("\u00A0", " ")).strip()


def colnames(con: sqlite3.Connection, table: str) -> set:
    """Zwraca zbiór nazw kolumn w tabeli (lowercase)."""
    try:
        cur = con.execute(f"PRAGMA table_info({table})")
        return {str(r[1]).lower() for r in cur.fetchall()}
    except Exception:
        return set()


def pick_col(cols: set, candidates: list) -> Optional[str]:
    """Wybiera pierwszą pasującą kolumnę z listy kandydatów."""
    for c in candidates:
        if c.lower() in cols:
            return c
    return None


# ============================================================================
# PROJEKTY - Podstawowe operacje
# ============================================================================

def ensure_projects_active_column(con: sqlite3.Connection) -> None:
    """Zapewnia, że tabela projects ma kolumnę is_active (backward compatible)."""
    cols = colnames(con, "projects")
    active_col = pick_col(cols, ["is_active", "active", "enabled"])
    
    if active_col:
        # Normalizuj NULLy -> 1
        try:
            con.execute(f"UPDATE projects SET {active_col}=1 WHERE {active_col} IS NULL;")
        except Exception:
            pass
        return
    
    # Dodaj kolumnę
    try:
        con.execute("ALTER TABLE projects ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;")
    except Exception:
        return
    
    try:
        con.execute("UPDATE projects SET is_active=1 WHERE is_active IS NULL;")
    except Exception:
        pass


def ensure_project_type_column(con: sqlite3.Connection) -> None:
    """Zapewnia, że tabela projects ma kolumnę project_type (backward compatible)."""
    cols = colnames(con, "projects")
    type_col = pick_col(cols, ["project_type", "type"])
    
    if type_col:
        # Normalizuj NULLy -> 'MACHINE'
        try:
            con.execute(f"UPDATE projects SET {type_col}='MACHINE' WHERE {type_col} IS NULL OR {type_col}='';")
        except Exception:
            pass
        return
    
    # Dodaj kolumnę
    try:
        con.execute("ALTER TABLE projects ADD COLUMN project_type TEXT NOT NULL DEFAULT 'MACHINE';")
    except Exception:
        return
    
    try:
        con.execute("UPDATE projects SET project_type='MACHINE' WHERE project_type IS NULL OR project_type='';")
    except Exception:
        pass


def ensure_projects_stats_columns(con: sqlite3.Connection) -> None:
    """Zapewnia, że tabela projects ma kolumny dla statystyk (backward compatible).
    
    Dodaje kolumny:
    - started_at TEXT - data rozpoczęcia prac nad projektem
    - expected_delivery TEXT - planowany termin odbioru
    - completed_at TEXT - data faktycznego zakończenia projektu
    - designer TEXT - konstruktor/osoba przypisana do projektu
    - status TEXT - szczegółowy stan projektu (NOWY, W_REALIZACJI, etc.)
    
    UWAGA: Kolumna 'active' pozostaje bez zmian dla kompatybilności wstecznej!
    """
    cols = colnames(con, "projects")
    
    # started_at - kiedy rozpoczęto pracę
    if "started_at" not in cols:
        try:
            con.execute("ALTER TABLE projects ADD COLUMN started_at TEXT;")
            print("✅ Dodano kolumnę: started_at")
        except Exception as e:
            print(f"⚠️  Błąd dodawania started_at: {e}")
    
    # expected_delivery - planowany termin odbioru
    if "expected_delivery" not in cols:
        try:
            con.execute("ALTER TABLE projects ADD COLUMN expected_delivery TEXT;")
            print("✅ Dodano kolumnę: expected_delivery")
        except Exception as e:
            print(f"⚠️  Błąd dodawania expected_delivery: {e}")
    
    # completed_at - data faktycznego zakończenia
    if "completed_at" not in cols:
        try:
            con.execute("ALTER TABLE projects ADD COLUMN completed_at TEXT;")
            print("✅ Dodano kolumnę: completed_at")
        except Exception as e:
            print(f"⚠️  Błąd dodawania completed_at: {e}")
    
    # montaz - Data montażu (dawniej 'sat' - Site Acceptance Test)
    # Dla kompatybilności wstecznej sprawdź obie nazwy
    if "montaz" not in cols and "sat" not in cols:
        try:
            con.execute("ALTER TABLE projects ADD COLUMN montaz TEXT;")
            print("✅ Dodano kolumnę: montaz")
        except sqlite3.OperationalError as e:
            print(f"⚠️  Błąd dodawania montaz: {e}")
    
    # fat - Factory Acceptance Test
    if "fat" not in cols:
        try:
            con.execute("ALTER TABLE projects ADD COLUMN fat TEXT;")
            print("✅ Dodano kolumnę: fat")
        except Exception as e:
            print(f"⚠️  Błąd dodawania fat: {e}")
    
    # designer - konstruktor przypisany
    if "designer" not in cols:
        try:
            con.execute("ALTER TABLE projects ADD COLUMN designer TEXT;")
            print("✅ Dodano kolumnę: designer")
        except Exception as e:
            print(f"⚠️  Błąd dodawania designer: {e}")
    
    # status - szczegółowy stan projektu
    if "status" not in cols:
        try:
            con.execute("ALTER TABLE projects ADD COLUMN status TEXT NOT NULL DEFAULT 'PROJEKT';")
            print("✅ Dodano kolumnę: status (default='PROJEKT')")
        except Exception as e:
            print(f"⚠️  Błąd dodawania status: {e}")
    
    # received_percent - procent odebranych elementów (dla RM_MANAGER)
    if "received_percent" not in cols:
        try:
            con.execute("ALTER TABLE projects ADD COLUMN received_percent TEXT;")
            print("✅ Dodano kolumnę: received_percent")
        except Exception as e:
            print(f"⚠️  Błąd dodawania received_percent: {e}")
    
    # Normalizuj wartości NULL dla status
    try:
        con.execute("UPDATE projects SET status='PROJEKT' WHERE status IS NULL OR status='';")
    except Exception as e:
        print(f"⚠️  Błąd normalizacji status: {e}")


def fetch_projects(
    con: sqlite3.Connection, 
    only_active: bool = False, 
    include_active: bool = False,
    project_type: Optional[str] = None
) -> List[Tuple]:
    """
    Pobiera listę projektów z master DB.
    
    Args:
        con: Połączenie do master.sqlite
        only_active: Jeśli True, zwraca tylko aktywne projekty
        include_active: Jeśli True, dodaje flagę is_active do wyniku
        project_type: Filtr typu projektu ('MACHINE', 'WAREHOUSE', lub None dla wszystkich)
    
    Returns:
        Lista tupli: (id, name, root_path) lub (id, name, root_path, is_active) lub (id, name, root_path, is_active, project_type)
    """
    # Zapewnij tabelę historii statusów (automatyczne tworzenie przy pierwszym użyciu)
    ensure_project_status_history_table(con)
    
    cols = colnames(con, "projects")
    pk = pick_col(cols, ["id", "project_id"])
    if pk is None:
        raise RuntimeError(f"Nieznany klucz w projects. Kolumny: {sorted(cols)}")
    
    name_col = pick_col(cols, ["name", "project_name"])
    if name_col is None:
        raise RuntimeError(f"Nieznana kolumna nazwy projektu. Kolumny: {sorted(cols)}")
    
    path_col = pick_col(cols, ["root_path", "path"])
    active_col = pick_col(cols, ["is_active", "active", "enabled"])
    type_col = pick_col(cols, ["project_type", "type"])
    
    # Zapewnij kolumnę project_type
    if not type_col:
        ensure_project_type_column(con)
        cols = colnames(con, "projects")
        type_col = pick_col(cols, ["project_type", "type"])
    
    # Zapewnij kolumny dla statystyk
    ensure_projects_stats_columns(con)
    
    # Buduj SELECT
    select_cols = [pk, name_col]
    if path_col:
        select_cols.append(path_col)
    
    if include_active:
        if not active_col:
            ensure_projects_active_column(con)
            cols = colnames(con, "projects")
            active_col = pick_col(cols, ["is_active", "active", "enabled"])
        if active_col:
            select_cols.append(active_col)
    
    # Zawsze dodaj type_col do SELECT
    if type_col:
        select_cols.append(type_col)
    
    # WHERE clause
    where_clauses = []
    if only_active:
        if not active_col:
            ensure_projects_active_column(con)
            cols = colnames(con, "projects")
            active_col = pick_col(cols, ["is_active", "active", "enabled"])
        if active_col:
            where_clauses.append(f"COALESCE({active_col},1)=1")
    
    if project_type and type_col:
        where_clauses.append(f"{type_col}='{project_type}'")
    
    where = ""
    if where_clauses:
        where = f" WHERE {' AND '.join(where_clauses)} "
    
    sql = f"SELECT {', '.join(select_cols)} FROM projects{where} ORDER BY {name_col} COLLATE NOCASE, {pk}"
    rows = con.execute(sql).fetchall()
    
    # Parsuj wyniki
    out = []
    for r in rows:
        pid = int(r[0])
        pname = str(r[1]) if r[1] is not None else ""
        idx = 2
        
        ppath = ""
        if path_col:
            if len(r) > idx and r[idx] is not None:
                ppath = str(r[idx])
            idx += 1
        
        is_act = 1
        if include_active:
            if active_col and len(r) > idx and r[idx] is not None:
                try:
                    is_act = 1 if int(r[idx]) else 0
                except Exception:
                    is_act = 1
            idx += 1
        
        ptype = "MACHINE"
        if type_col and len(r) > idx and r[idx] is not None:
            ptype = str(r[idx])
        
        if include_active:
            out.append((pid, pname, ppath, is_act, ptype))
        else:
            out.append((pid, pname, ppath, ptype))
    
    return out


def create_project(
    con: sqlite3.Connection, 
    name: str, 
    root_path: Optional[str] = None, 
    project_type: str = "MACHINE",
    designer: Optional[str] = None,
    status: str = "PROJEKT"
) -> int:
    """
    Tworzy nowy projekt w master DB.
    
    Args:
        con: Połączenie do master.sqlite
        name: Nazwa projektu
        root_path: Opcjonalna ścieżka do katalogu projektu
        project_type: Typ projektu ('MACHINE' lub 'WAREHOUSE')
        designer: Konstruktor przypisany do projektu
        status: Status projektu (PROJEKT, W_REALIZACJI, WSTRZYMANY, ZAKOŃCZONY)
    
    Returns:
        ID nowo utworzonego projektu
    
    Note:
        Data utworzenia (created_at) jest automatycznie ustawiana przez bazę danych
    """
    name = norm(name)
    if not name:
        raise ValueError("Pusta nazwa projektu")
    
    # Zapewnij kolumnę project_type
    ensure_project_type_column(con)
    
    # Zapewnij kolumny dla statystyk
    ensure_projects_stats_columns(con)
    
    cols = colnames(con, "projects")
    pk = pick_col(cols, ["id", "project_id"])
    name_col = pick_col(cols, ["name", "project_name"])
    path_col = pick_col(cols, ["root_path", "path"])
    type_col = pick_col(cols, ["project_type", "type"])
    
    if pk is None or name_col is None:
        raise RuntimeError(f"Nieznany schemat projects. Kolumny: {sorted(cols)}")
    
    # Buduj INSERT
    fields = [name_col]
    params = [name]
    
    if path_col:
        fields.append(path_col)
        params.append(norm(root_path) if root_path else None)
    
    # Dodaj is_active=1
    active_col = pick_col(cols, ["is_active", "active", "enabled"])
    if active_col:
        fields.append(active_col)
        params.append(1)
    
    # Dodaj project_type
    if type_col:
        fields.append(type_col)
        params.append(project_type if project_type in ("MACHINE", "WAREHOUSE") else "MACHINE")
    
    # Dodaj designer (jeśli kolumna istnieje)
    if 'designer' in cols and designer:
        fields.append('designer')
        params.append(norm(designer))
    
    # Dodaj status (jeśli kolumna istnieje)
    if 'status' in cols:
        fields.append('status')
        params.append(status if status else 'PROJEKT')
    
    sql = f"INSERT INTO projects({', '.join(fields)}) VALUES ({', '.join(['?']*len(fields))})"
    cur = con.execute(sql, params)
    project_id = int(cur.lastrowid)
    
    # Zapewnij tabelę historii statusów i dodaj wpis początkowy
    ensure_project_status_history_table(con)
    try:
        from datetime import datetime
        now = datetime.now().isoformat()
        con.execute("""
            INSERT INTO project_status_history 
            (project_id, old_status, new_status, changed_at, notes)
            VALUES (?, NULL, ?, ?, 'Utworzenie projektu')
        """, (project_id, status if status else 'PROJEKT', now))
        con.commit()
    except Exception:
        # Jeśli nie można dodać do historii, nie blokuj tworzenia projektu
        pass
    
    return project_id


def update_project(
    con: sqlite3.Connection, 
    project_id: int, 
    name: Optional[str] = None, 
    root_path: Optional[str] = None,
    designer: Optional[str] = None,
    montaz: Optional[str] = None,
    fat: Optional[str] = None,
    completed_at: Optional[str] = None,
    status: Optional[str] = None
) -> None:
    """
    Aktualizuje dane projektu.
    
    Args:
        con: Połączenie do master.sqlite
        project_id: ID projektu do aktualizacji
        name: Nowa nazwa (opcjonalnie)
        root_path: Nowa ścieżka (opcjonalnie)
        designer: Konstruktor (opcjonalnie)
        montaz: Data montażu ISO (opcjonalnie)
        fat: Data FAT ISO (opcjonalnie)
        completed_at: Data zakończenia ISO (opcjonalnie)
        status: Status projektu (opcjonalnie) - automatycznie zapisuje historię zmian
    
    Note:
        Data utworzenia (created_at) jest ustawiana automatycznie tylko przy tworzeniu projektu
        Zmiana statusu automatycznie zapisuje się w project_status_history
    """
    cols = colnames(con, "projects")
    pk = pick_col(cols, ["id", "project_id"])
    if pk is None:
        raise RuntimeError(f"Nieznany klucz w projects. Kolumny: {sorted(cols)}")
    
    name_col = pick_col(cols, ["name", "project_name"])
    if name_col is None:
        raise RuntimeError(f"Nieznana kolumna nazwy projektu. Kolumny: {sorted(cols)}")
    
    path_col = pick_col(cols, ["root_path", "path"])
    
    sets = []
    params = []
    
    if name is not None:
        nm = norm(name)
        if not nm:
            raise RuntimeError("Nazwa projektu nie może być pusta.")
        sets.append(f"{name_col}=?")
        params.append(nm)
    
    if root_path is not None and path_col is not None:
        rp = norm(root_path)
        sets.append(f"{path_col}=?")
        params.append(rp if rp else None)
    
    # Nowe pola dla statystyk
    if designer is not None and 'designer' in cols:
        sets.append("designer=?")
        params.append(norm(designer) if designer else None)
    
    # Sprawdź obie nazwy kolumny dla kompatybilności wstecznej
    if montaz is not None:
        if 'montaz' in cols:
            sets.append("montaz=?")
            params.append(montaz)
        elif 'sat' in cols:
            sets.append("sat=?")
            params.append(montaz)
    
    if fat is not None and 'fat' in cols:
        sets.append("fat=?")
        params.append(fat)
    
    if completed_at is not None and 'completed_at' in cols:
        sets.append("completed_at=?")
        params.append(completed_at)
    
    # SPECJALNA OBSŁUGA STATUSU: zapisz w historii jeśli się zmienił
    if status is not None and 'status' in cols:
        # Pobierz aktualny status
        cur = con.execute(f"SELECT status FROM projects WHERE {pk}=?", (int(project_id),))
        row = cur.fetchone()
        old_status = row[0] if row else None
        
        # Jeśli status się zmienił, zapisz w historii
        if old_status != status:
            # Użyj funkcji change_project_status która obsłuży historię
            change_project_status(con, int(project_id), status, notes="Zmiana przez GUI")
            # Funkcja change_project_status już zapisze status, więc nie dodajemy do sets
        else:
            # Status się nie zmienił, ale może chcemy go ustawić przy tworzeniu
            sets.append("status=?")
            params.append(status)
    
    if not sets:
        return
    
    params.append(int(project_id))
    sql = f"UPDATE projects SET {', '.join(sets)} WHERE {pk}=?"
    con.execute(sql, params)


def set_project_active(con: sqlite3.Connection, project_id: int, is_active: int) -> None:
    """
    Ustawia status aktywności projektu.
    
    Args:
        con: Połączenie do master.sqlite
        project_id: ID projektu
        is_active: 1 = aktywny, 0 = nieaktywny
    """
    cols = colnames(con, "projects")
    pk = pick_col(cols, ["id", "project_id"])
    if pk is None:
        raise RuntimeError(f"Nieznany klucz w projects. Kolumny: {sorted(cols)}")
    
    active_col = pick_col(cols, ["is_active", "active", "enabled"])
    if not active_col:
        ensure_projects_active_column(con)
        cols = colnames(con, "projects")
        active_col = pick_col(cols, ["is_active", "active", "enabled"])
    
    # Zapewnij kolumny dla statystyk
    ensure_projects_stats_columns(con)
    
    if not active_col:
        raise RuntimeError("Nie można znaleźć/dodać kolumny aktywności projektu.")
    
    con.execute(
        f"UPDATE projects SET {active_col}=? WHERE {pk}=?", 
        (1 if int(is_active) else 0, int(project_id))
    )


def delete_project(con: sqlite3.Connection, project_id: int) -> None:
    """
    Usuwa projekt z master DB.
    
    UWAGA: W architekturze distributed to usuwa tylko rekord w master.sqlite.
    Plik project_X.sqlite NIE jest automatycznie usuwany - wymaga osobnej obsługi.
    
    Args:
        con: Połączenie do master.sqlite
        project_id: ID projektu do usunięcia
    """
    cols = colnames(con, "projects")
    pk = pick_col(cols, ["id", "project_id"])
    if pk is None:
        raise RuntimeError(f"Nieznany klucz w projects. Kolumny: {sorted(cols)}")
    
    con.execute(f"DELETE FROM projects WHERE {pk}=?", (int(project_id),))


# ============================================================================
# UTILITY - Dodatkowe pomocnicze funkcje
# ============================================================================

def get_project_info(con: sqlite3.Connection, project_id: int) -> Optional[Tuple[int, str, str, str]]:
    """
    Pobiera informacje o pojedynczym projekcie.
    
    Returns:
        (id, name, root_path, project_type) lub None jeśli projekt nie istnieje
    """
    # Zapewnij kolumnę project_type
    ensure_project_type_column(con)
    
    cols = colnames(con, "projects")
    pk = pick_col(cols, ["id", "project_id"])
    name_col = pick_col(cols, ["name", "project_name"])
    path_col = pick_col(cols, ["root_path", "path"])
    type_col = pick_col(cols, ["project_type", "type"])
    
    if pk is None or name_col is None:
        raise RuntimeError(f"Nieznany schemat projects. Kolumny: {sorted(cols)}")
    
    select_cols = [pk, name_col]
    if path_col:
        select_cols.append(path_col)
    if type_col:
        select_cols.append(type_col)
    
    sql = f"SELECT {', '.join(select_cols)} FROM projects WHERE {pk}=?"
    row = con.execute(sql, (int(project_id),)).fetchone()
    
    if not row:
        return None
    
    pid = int(row[0])
    pname = str(row[1]) if row[1] is not None else ""
    idx = 2
    ppath = str(row[idx]) if len(row) > idx and row[idx] is not None else ""
    idx += 1
    ptype = str(row[idx]) if len(row) > idx and row[idx] is not None else "MACHINE"
    
    return (pid, pname, ppath, ptype)


def project_exists(con: sqlite3.Connection, project_id: int) -> bool:
    """Sprawdza czy projekt o danym ID istnieje."""
    return get_project_info(con, project_id) is not None


def get_project_db_path(projects_dir: Path, project_id: int, project_type: str = "MACHINE") -> Path:
    """
    Zwraca ścieżkę do pliku bazy danych projektu.
    
    Używa katalogów DOKŁADNIE jak podane w config (projects_dir / projects_mag_dir).
    NIE dodaje żadnych podkatalogów — ścieżka z configu wskazuje bezpośrednio
    na katalog z plikami .sqlite.
    
    Args:
        projects_dir: Katalog z bazami projektów (dokładnie jak w config):
                      - Dla MACHINE: np. Y:/RM_BAZA/projects
                      - Dla WAREHOUSE: np. Y:/RM_BAZA/projects_MAG
        project_id: ID projektu
        project_type: Typ projektu ('MACHINE' lub 'WAREHOUSE')
    
    Returns:
        Ścieżka do pliku: projects_dir/project_X.sqlite lub projects_dir/project_MAG_X.sqlite
    """
    if project_type == "WAREHOUSE":
        filename = f"project_MAG_{project_id}.sqlite"
    else:
        filename = f"project_{project_id}.sqlite"
    
    return projects_dir / filename


# ============================================================================
# ZARZĄDZANIE STATUSAMI I HISTORIĄ
# ============================================================================

# ============================================================================
# MULTI-STATUS SYSTEM - Wiele statusów równocześnie
# ============================================================================

# NOWA LISTA STATUSÓW (multi-select)
PROJECT_STATUSES_NEW = [
    "PRZYJETY",       # Przyjęty do realizacji
    "PROJEKT",        # Faza projektowania
    "KOMPLETACJA",    # Kompletacja materiałów
    "MONTAZ",         # Montaż
    "AUTOMATYKA",     # Prace nad automatyką
    "URUCHOMIENIE",   # Uruchomienie
    "ODBIORY",        # Odbiory
    "POPRAWKI",       # Poprawki
    "WSTRZYMANY",     # Wstrzymany
    "ZAKONCZONY"      # Zakończony
]

# STARA LISTA (backward compatibility - nie używana w nowym systemie)
PROJECT_STATUSES = [
    "PROJEKT",        # Faza projektowania urządzenia
    "W_REALIZACJI",   # Projekt w trakcie realizacji
    "WSTRZYMANY",     # Projekt tymczasowo wstrzymany
    "ZAKOŃCZONY"      # Projekt zakończony
]


def ensure_project_statuses_table(con: sqlite3.Connection) -> None:
    """
    Zapewnia, że tabela project_statuses istnieje (NOWY SYSTEM MULTI-STATUS).
    
    Tworzy tabelę many-to-many do przechowywania wielu statusów dla jednego projektu.
    Tabela pozwala na przypisanie wielu statusów równocześnie.
    """
    try:
        cur = con.cursor()
        
        # Sprawdź czy tabela już istnieje
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='project_statuses'
        """)
        
        if cur.fetchone():
            # Tabela już istnieje
            return
        
        # Utwórz tabelę project_statuses (many-to-many)
        cur.execute("""
            CREATE TABLE project_statuses (
                project_id     INTEGER NOT NULL,
                status         TEXT NOT NULL,
                set_at         TEXT NOT NULL DEFAULT (datetime('now')),
                set_by         TEXT,
                PRIMARY KEY (project_id, status),
                FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
            )
        """)
        
        # Indeks dla szybkiego wyszukiwania
        cur.execute("""
            CREATE INDEX idx_project_statuses_project 
            ON project_statuses(project_id)
        """)
        
        # Indeks dla wyszukiwania po statusie
        cur.execute("""
            CREATE INDEX idx_project_statuses_status 
            ON project_statuses(status)
        """)
        
        con.commit()
        print("✅ Utworzono tabelę project_statuses (multi-status)")
        
    except Exception as e:
        print(f"⚠️  Błąd tworzenia tabeli project_statuses: {e}")


def ensure_project_status_changes_table(con: sqlite3.Connection) -> None:
    """
    Zapewnia, że tabela project_status_changes istnieje (SZCZEGÓŁOWA HISTORIA).
    
    Tworzy tabelę do śledzenia każdej zmiany statusu osobno - każde dodanie lub
    usunięcie statusu zapisywane jest jako osobny wpis.
    
    Struktura:
    - id: Unikalny identyfikator zmiany
    - project_id: ID projektu
    - status: Nazwa statusu (np. 'MONTAZ', 'ODBIORY')
    - action: 'ADDED' (dodano) lub 'REMOVED' (usunięto)
    - changed_at: Timestamp zmiany
    - changed_by: Kto wykonał zmianę
    - notes: Opcjonalne notatki
    """
    try:
        cur = con.cursor()
        
        # Sprawdź czy tabela już istnieje
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='project_status_changes'
        """)
        
        if cur.fetchone():
            # Tabela już istnieje
            return
        
        # Utwórz tabelę szczegółowej historii statusów
        cur.execute("""
            CREATE TABLE project_status_changes (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id     INTEGER NOT NULL,
                status         TEXT NOT NULL,
                action         TEXT NOT NULL CHECK(action IN ('ADDED', 'REMOVED')),
                changed_at     TEXT NOT NULL DEFAULT (datetime('now')),
                changed_by     TEXT,
                notes          TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
            )
        """)
        
        # Indeks dla szybkiego wyszukiwania po projekcie
        cur.execute("""
            CREATE INDEX idx_status_changes_project 
            ON project_status_changes(project_id, changed_at DESC)
        """)
        
        # Indeks dla wyszukiwania po statusie
        cur.execute("""
            CREATE INDEX idx_status_changes_status 
            ON project_status_changes(status, changed_at DESC)
        """)
        
        # Indeks dla wyszukiwania kombinacji projekt+status
        cur.execute("""
            CREATE INDEX idx_status_changes_project_status 
            ON project_status_changes(project_id, status, changed_at DESC)
        """)
        
        con.commit()
        print("✅ Utworzono tabelę project_status_changes (szczegółowa historia)")
        
    except Exception as e:
        print(f"⚠️  Błąd tworzenia tabeli project_status_changes: {e}")


def ensure_project_status_history_table(con: sqlite3.Connection) -> None:
    """
    Zapewnia, że tabela project_status_history istnieje wraz z potrzebnymi kolumnami.
    Tworzy automatycznie przy pierwszym użyciu - gotowe do instalacji w działającym systemie.
    
    Tworzy:
    - Tabelę project_status_history do śledzenia zmian statusów
    - Indeks dla szybkiego wyszukiwania
    - Kolumnę status_changed_at w tabeli projects
    - Inicjalizuje historię dla istniejących projektów
    """
    from datetime import datetime
    
    try:
        cur = con.cursor()
        
        # Sprawdź czy tabela już istnieje
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='project_status_history'
        """)
        
        if cur.fetchone():
            # Tabela już istnieje, nie rób nic
            return
        
        # Utwórz tabelę historii statusów
        cur.execute("""
            CREATE TABLE project_status_history (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id     INTEGER NOT NULL,
                old_status     TEXT,
                new_status     TEXT NOT NULL,
                changed_at     TEXT NOT NULL DEFAULT (datetime('now')),
                changed_by     TEXT,
                notes          TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
            )
        """)
        
        # Indeks dla szybkiego wyszukiwania
        cur.execute("""
            CREATE INDEX idx_status_history_project 
            ON project_status_history(project_id, changed_at DESC)
        """)
        
        # Dodaj kolumnę status_changed_at do projects (jeśli nie istnieje)
        cols = colnames(con, "projects")
        if "status_changed_at" not in cols:
            try:
                cur.execute("""
                    ALTER TABLE projects 
                    ADD COLUMN status_changed_at TEXT
                """)
            except sqlite3.OperationalError:
                pass  # Kolumna już istnieje
        
        # Inicjalizuj historię dla istniejących projektów
        cur.execute("""
            SELECT project_id, status, created_at
            FROM projects
        """)
        projects = cur.fetchall()
        
        for proj_id, status, created_at in projects:
            # Dodaj wpis historii
            cur.execute("""
                INSERT INTO project_status_history 
                (project_id, old_status, new_status, changed_at, notes)
                VALUES (?, NULL, ?, ?, 'Automatyczna inicjalizacja historii')
            """, (proj_id, status or 'PROJEKT', created_at or datetime.now().isoformat()))
            
            # Ustaw status_changed_at
            cur.execute("""
                UPDATE projects 
                SET status_changed_at = ?
                WHERE project_id = ?
            """, (created_at or datetime.now().isoformat(), proj_id))
        
        con.commit()
        
    except Exception as e:
        # Błąd nie jest krytyczny, system może działać bez historii
        print(f"⚠️  Błąd tworzenia tabeli historii: {e}")


def change_project_status(
    con: sqlite3.Connection,
    project_id: int,
    new_status: str,
    changed_by: Optional[str] = None,
    notes: Optional[str] = None
) -> bool:
    """
    Zmienia status projektu i zapisuje w historii.
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
        new_status: Nowy status (musi być z PROJECT_STATUSES)
        changed_by: Kto zmienił status (opcjonalne)
        notes: Notatki do zmiany (opcjonalne)
    
    Returns:
        True jeśli zmiana się powiodła
    """
    from datetime import datetime
    
    # Zapewnij tabelę historii statusów (automatyczne tworzenie przy pierwszym użyciu)
    ensure_project_status_history_table(con)
    
    # Walidacja statusu
    if new_status not in PROJECT_STATUSES:
        print(f"❌ Nieprawidłowy status: {new_status}")
        print(f"   Dozwolone: {', '.join(PROJECT_STATUSES)}")
        return False
    
    # Wykryj nazwę kolumny klucza głównego (może być 'id' lub 'project_id')
    cols = colnames(con, "projects")
    pk = pick_col(cols, ["id", "project_id"])
    if pk is None:
        print(f"❌ Nie znaleziono klucza głównego w tabeli projects")
        return False
    
    try:
        # Pobierz aktualny status (używając wykrytej nazwy kolumny)
        cur = con.execute(
            f"SELECT status FROM projects WHERE {pk}=?",
            (project_id,)
        )
        row = cur.fetchone()
        if not row:
            print(f"❌ Nie znaleziono projektu {project_id}")
            return False
        
        old_status = row[0]
        
        # Jeśli status się nie zmienił, nie rób nic
        if old_status == new_status:
            return True
        
        now = datetime.now().isoformat()
        
        # Zapisz w historii
        con.execute("""
            INSERT INTO project_status_history 
            (project_id, old_status, new_status, changed_at, changed_by, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (project_id, old_status, new_status, now, changed_by, notes))
        
        # Zaktualizuj status w projects (używając wykrytej nazwy kolumny)
        con.execute(f"""
            UPDATE projects 
            SET status = ?, status_changed_at = ?
            WHERE {pk} = ?
        """, (new_status, now, project_id))
        
        # Jeśli status to ZAKOŃCZONY, ustaw completed_at (jeśli nie jest już ustawiony)
        if new_status == "ZAKOŃCZONY":
            con.execute(f"""
                UPDATE projects 
                SET completed_at = COALESCE(completed_at, ?)
                WHERE {pk} = ?
            """, (now, project_id))
        
        con.commit()
        return True
        
    except Exception as e:
        print(f"❌ Błąd zmiany statusu: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_project_status_history(
    con: sqlite3.Connection,
    project_id: int
) -> list:
    """
    Pobiera historię zmian statusów projektu.
    
    Returns:
        Lista tuple: (id, old_status, new_status, changed_at, changed_by, notes)
    """
    # Zapewnij tabelę historii statusów (automatyczne tworzenie przy pierwszym użyciu)
    ensure_project_status_history_table(con)
    
    try:
        cur = con.execute("""
            SELECT id, old_status, new_status, changed_at, changed_by, notes
            FROM project_status_history
            WHERE project_id = ?
            ORDER BY changed_at DESC
        """, (project_id,))
        return cur.fetchall()
    except Exception as e:
        print(f"❌ Błąd pobierania historii: {e}")
        return []


def get_project_time_in_status(
    con: sqlite3.Connection,
    project_id: int,
    status: str
) -> float:
    """
    Oblicza łączny czas (w dniach) spędzony w danym statusie.
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
        status: Status do sprawdzenia
    
    Returns:
        Liczba dni w tym statusie
    """
    from datetime import datetime
    
    # Zapewnij tabelę historii statusów (automatyczne tworzenie przy pierwszym użyciu)
    ensure_project_status_history_table(con)
    
    try:
        # Pobierz wszystkie zmiany statusu
        cur = con.execute("""
            SELECT old_status, new_status, changed_at
            FROM project_status_history
            WHERE project_id = ?
            ORDER BY changed_at ASC
        """, (project_id,))
        
        history = cur.fetchall()
        if not history:
            return 0.0
        
        total_days = 0.0
        current_status = None
        status_start = None
        
        for old_stat, new_stat, changed_at in history:
            # Parsuj datę
            try:
                change_time = datetime.fromisoformat(changed_at)
            except:
                continue
            
            # Jeśli wchodzimy w interesujący nas status
            if new_stat == status:
                status_start = change_time
                current_status = status
            
            # Jeśli wychodzimy z interesującego nas statusu
            elif current_status == status and status_start:
                delta = (change_time - status_start).total_seconds()
                total_days += delta / 86400.0  # sekund na dzień
                status_start = None
                current_status = new_stat
            else:
                current_status = new_stat
        
        # Jeśli nadal jesteśmy w tym statusie
        if current_status == status and status_start:
            now = datetime.now()
            delta = (now - status_start).total_seconds()
            total_days += delta / 86400.0
        
        return total_days
        
    except Exception as e:
        print(f"❌ Błąd obliczania czasu: {e}")
        return 0.0


def get_all_project_times(
    con: sqlite3.Connection,
    project_id: int
) -> dict:
    """
    Oblicza czas spędzony w każdym statusie.
    
    Returns:
        Dict: {status: days}
    """
    times = {}
    for status in PROJECT_STATUSES:
        times[status] = get_project_time_in_status(con, project_id, status)
    return times


# ============================================================================
# MULTI-STATUS SYSTEM - Funkcje zarządzania wieloma statusami
# ============================================================================

def get_project_statuses(con: sqlite3.Connection, project_id: int) -> list:
    """
    Pobiera listę aktywnych statusów dla projektu (NOWY SYSTEM).
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
    
    Returns:
        Lista statusów: ['PROJEKT', 'MONTAZ', ...]
    """
    # Zapewnij tabelę
    ensure_project_statuses_table(con)
    
    try:
        cur = con.execute("""
            SELECT status
            FROM project_statuses
            WHERE project_id = ?
            ORDER BY set_at ASC
        """, (project_id,))
        return [row[0] for row in cur.fetchall()]
    except Exception as e:
        print(f"❌ Błąd pobierania statusów: {e}")
        return []


def set_project_statuses(
    con: sqlite3.Connection,
    project_id: int,
    statuses: list,
    set_by: Optional[str] = None
) -> bool:
    """
    Ustawia statusy projektu (NOWY SYSTEM - multi-select).
    
    Zastępuje wszystkie poprzednie statusy nowymi.
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
        statuses: Lista statusów do ustawienia ['PROJEKT', 'MONTAZ', ...]
        set_by: Kto ustawił (login użytkownika)
    
    Returns:
        True jeśli sukces
    """
    from datetime import datetime
    
    # Zapewnij tabelę
    ensure_project_statuses_table(con)
    
    # Walidacja statusów
    for status in statuses:
        if status not in PROJECT_STATUSES_NEW:
            print(f"❌ Nieprawidłowy status: {status}")
            print(f"   Dozwolone: {', '.join(PROJECT_STATUSES_NEW)}")
            return False
    
    try:
        now = datetime.now().isoformat()
        
        # Pobierz stare statusy
        old_statuses = get_project_statuses(con, project_id)
        old_statuses_set = set(old_statuses)
        new_statuses_set = set(statuses)
        
        # Oblicz różnice
        added_statuses = new_statuses_set - old_statuses_set
        removed_statuses = old_statuses_set - new_statuses_set
        
        # Zapewnij tabelę szczegółowej historii
        ensure_project_status_changes_table(con)
        
        # Zapisz szczegółową historię - każdy dodany status
        for status in added_statuses:
            con.execute("""
                INSERT INTO project_status_changes 
                (project_id, status, action, changed_at, changed_by, notes)
                VALUES (?, ?, 'ADDED', ?, ?, ?)
            """, (project_id, status, now, set_by, f"Status {status} dodany"))
        
        # Zapisz szczegółową historię - każdy usunięty status
        for status in removed_statuses:
            con.execute("""
                INSERT INTO project_status_changes 
                (project_id, status, action, changed_at, changed_by, notes)
                VALUES (?, ?, 'REMOVED', ?, ?, ?)
            """, (project_id, status, now, set_by, f"Status {status} usunięty"))
        
        # Usuń wszystkie obecne statusy
        con.execute("""
            DELETE FROM project_statuses
            WHERE project_id = ?
        """, (project_id,))
        
        # Dodaj nowe statusy
        for status in statuses:
            con.execute("""
                INSERT INTO project_statuses (project_id, status, set_at, set_by)
                VALUES (?, ?, ?, ?)
            """, (project_id, status, now, set_by))
        
        # Zapisz zmianę w historii (stary system - dla kompatybilności)
        old_status_str = ", ".join(sorted(old_statuses)) if old_statuses else None
        new_status_str = ", ".join(sorted(statuses)) if statuses else None
        
        if old_status_str != new_status_str:
            ensure_project_status_history_table(con)
            con.execute("""
                INSERT INTO project_status_history 
                (project_id, old_status, new_status, changed_at, changed_by, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (project_id, old_status_str, new_status_str, now, set_by, "Multi-status update"))
        
        # Zaktualizuj status_changed_at w projects
        cols = colnames(con, "projects")
        pk = pick_col(cols, ["id", "project_id"])
        if "status_changed_at" in cols and pk:
            con.execute(f"""
                UPDATE projects 
                SET status_changed_at = ?
                WHERE {pk} = ?
            """, (now, project_id))
        
        # Jeśli ZAKONCZONY jest w statusach, ustaw completed_at
        if "ZAKONCZONY" in statuses:
            cols = colnames(con, "projects")
            pk = pick_col(cols, ["id", "project_id"])
            if "completed_at" in cols and pk:
                con.execute(f"""
                    UPDATE projects 
                    SET completed_at = COALESCE(completed_at, ?)
                    WHERE {pk} = ?
                """, (now, project_id))
        
        con.commit()
        return True
        
    except Exception as e:
        print(f"❌ Błąd ustawiania statusów: {e}")
        import traceback
        traceback.print_exc()
        return False


def add_project_status(
    con: sqlite3.Connection,
    project_id: int,
    status: str,
    set_by: Optional[str] = None
) -> bool:
    """
    Dodaje pojedynczy status do projektu (nie usuwając innych).
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
        status: Status do dodania
        set_by: Kto dodał
    
    Returns:
        True jeśli sukces
    """
    statuses = get_project_statuses(con, project_id)
    if status not in statuses:
        statuses.append(status)
        return set_project_statuses(con, project_id, statuses, set_by)
    return True


def remove_project_status(
    con: sqlite3.Connection,
    project_id: int,
    status: str,
    set_by: Optional[str] = None
) -> bool:
    """
    Usuwa pojedynczy status z projektu.
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
        status: Status do usunięcia
        set_by: Kto usunął
    
    Returns:
        True jeśli sukces
    """
    statuses = get_project_statuses(con, project_id)
    if status in statuses:
        statuses.remove(status)
        return set_project_statuses(con, project_id, statuses, set_by)
    return True


def get_project_statuses_display(con: sqlite3.Connection, project_id: int) -> str:
    """
    Pobiera statusy projektu jako string do wyświetlenia.
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
    
    Returns:
        String: "PROJEKT, MONTAZ, AUTOMATYKA" lub "(brak)"
    """
    statuses = get_project_statuses(con, project_id)
    if not statuses:
        return "(brak)"
    return ", ".join(statuses)


# ============================================================================
# SZCZEGÓŁOWA HISTORIA STATUSÓW - Tracking każdej zmiany osobno
# ============================================================================

def get_status_detailed_history(
    con: sqlite3.Connection,
    project_id: int,
    status: Optional[str] = None
) -> list:
    """
    Pobiera szczegółową historię zmian statusów dla projektu.
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
        status: Opcjonalnie - filtruj po konkretnym statusie
    
    Returns:
        Lista tuple: (id, status, action, changed_at, changed_by, notes)
        Posortowana od najnowszych
    """
    ensure_project_status_changes_table(con)
    
    try:
        if status:
            cur = con.execute("""
                SELECT id, status, action, changed_at, changed_by, notes
                FROM project_status_changes
                WHERE project_id = ? AND status = ?
                ORDER BY changed_at DESC
            """, (project_id, status))
        else:
            cur = con.execute("""
                SELECT id, status, action, changed_at, changed_by, notes
                FROM project_status_changes
                WHERE project_id = ?
                ORDER BY changed_at DESC
            """, (project_id,))
        
        return cur.fetchall()
    except Exception as e:
        print(f"❌ Błąd pobierania szczegółowej historii: {e}")
        return []


def get_status_timeline(
    con: sqlite3.Connection,
    project_id: int
) -> dict:
    """
    Pobiera pełną linię czasu statusów dla projektu.
    
    Zwraca słownik gdzie klucz to status, wartość to lista zmian:
    {
        "MONTAZ": [
            {"action": "ADDED", "changed_at": "2026-03-26 10:00", "changed_by": "admin"},
            {"action": "REMOVED", "changed_at": "2026-03-27 14:00", "changed_by": "admin"}
        ],
        "ODBIORY": [...]
    }
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
    
    Returns:
        Dict z historią każdego statusu
    """
    history = get_status_detailed_history(con, project_id)
    
    timeline = {}
    for row in history:
        _, status, action, changed_at, changed_by, notes = row
        
        if status not in timeline:
            timeline[status] = []
        
        timeline[status].append({
            "action": action,
            "changed_at": changed_at,
            "changed_by": changed_by,
            "notes": notes
        })
    
    return timeline


def get_status_duration(
    con: sqlite3.Connection,
    project_id: int,
    status: str
) -> float:
    """
    Oblicza łączny czas (w dniach) spędzony w danym statusie.
    
    Analizuje pary ADDED/REMOVED aby obliczyć rzeczywisty czas.
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
        status: Nazwa statusu
    
    Returns:
        Liczba dni (float)
    """
    from datetime import datetime
    
    history = get_status_detailed_history(con, project_id, status)
    
    if not history:
        return 0.0
    
    total_seconds = 0.0
    added_at = None
    
    # Iteruj od najstarszych do najnowszych (odwróć listę)
    for row in reversed(history):
        _, _, action, changed_at, _, _ = row
        
        try:
            timestamp = datetime.fromisoformat(changed_at)
        except:
            continue
        
        if action == "ADDED":
            added_at = timestamp
        elif action == "REMOVED" and added_at is not None:
            delta = (timestamp - added_at).total_seconds()
            total_seconds += delta
            added_at = None
    
    # Jeśli status jest nadal aktywny (ADDED bez REMOVED)
    if added_at is not None:
        now = datetime.now()
        delta = (now - added_at).total_seconds()
        total_seconds += delta
    
    return total_seconds / 86400.0  # Konwertuj na dni


def get_all_statuses_duration(
    con: sqlite3.Connection,
    project_id: int
) -> dict:
    """
    Oblicza czas spędzony w każdym statusie.
    
    Returns:
        Dict: {status_name: days}
    """
    durations = {}
    
    # Pobierz wszystkie unikalne statusy dla tego projektu
    ensure_project_status_changes_table(con)
    
    try:
        cur = con.execute("""
            SELECT DISTINCT status
            FROM project_status_changes
            WHERE project_id = ?
        """, (project_id,))
        
        statuses = [row[0] for row in cur.fetchall()]
        
        for status in statuses:
            durations[status] = get_status_duration(con, project_id, status)
        
        return durations
    
    except Exception as e:
        print(f"❌ Błąd obliczania czasów: {e}")
        return {}


def is_status_currently_active(
    con: sqlite3.Connection,
    project_id: int,
    status: str
) -> bool:
    """
    Sprawdza czy dany status jest obecnie aktywny dla projektu.
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
        status: Nazwa statusu
    
    Returns:
        True jeśli status jest aktywny
    """
    current_statuses = get_project_statuses(con, project_id)
    return status in current_statuses


