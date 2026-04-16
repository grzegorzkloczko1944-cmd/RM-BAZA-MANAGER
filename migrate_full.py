"""
============================================================================
MIGRACJA KOMPLETNA - Wszystkie zmiany w jednym skrypcie
============================================================================
Kompleksowy skrypt migracji dla systemu BOM:

1. Dodanie kolumn do tabeli projects:
   - designer (konstruktor)
   - started_at, expected_delivery, completed_at
   - sat/montaz (data montażu)
   - fat (Factory Acceptance Test)
   - status, status_changed_at

2. Zmiana nazwy kolumny: sat → montaz

3. System multi-status:
   - Tabela project_statuses (many-to-many)
   - Indeksy dla szybkiego wyszukiwania

4. Szczegółowa historia statusów:
   - Tabela project_status_changes (tracking ADDED/REMOVED)
   - Indeksy dla analiz

5. Historia zmian statusów (kompatybilność):
   - Tabela project_status_history
   - Inicjalizacja dla istniejących projektów

UŻYCIE:
    python migrate_full.py                      # Auto-detect z config
    python migrate_full.py <ścieżka_do_pliku>  # Własna ścieżka
    
PRZYKŁADY:
    python migrate_full.py
    python migrate_full.py "Y:/RM_BAZA/master.sqlite"
    python migrate_full.py "Z:/FoldeR/master.sqlite"

UWAGA: 
- Skrypt jest idempotentny - można uruchamiać wielokrotnie bez szkody
- Sprawdza czy każda zmiana już istnieje przed jej wykonaniem
- Bezpieczny dla działającej bazy danych
============================================================================
"""

import sqlite3
from pathlib import Path
import sys
import json
from datetime import datetime


def get_master_path_from_config():
    """
    Próbuje odczytać ścieżkę do master.sqlite z pliku konfiguracyjnego aplikacji.
    
    Returns:
        str lub None: Ścieżka do master.sqlite lub None jeśli nie znaleziono
    """
    config_paths = [
        Path("C:/RMPAK_CLIENT/sync_config.json"),
        Path.home() / "RMPAK_CLIENT" / "sync_config.json",
        Path("sync_config.json"),
    ]
    
    for config_path in config_paths:
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    master_path = config.get("paths", {}).get("master")
                    if master_path:
                        print(f"📋 Znaleziono config: {config_path}")
                        print(f"   Ścieżka z configu: {master_path}")
                        return master_path
        except Exception:
            continue
    
    return None


def validate_database_path(path_str: str) -> tuple:
    """
    Waliduje ścieżkę do pliku bazy danych.
    
    Returns:
        (bool, str): (is_valid, error_message)
    """
    if not path_str:
        return False, "Nie podano ścieżki do bazy danych!"
    
    path = Path(path_str)
    
    if path.exists() and path.is_dir():
        return False, f"Podano katalog zamiast pliku: {path_str}\n   Podaj pełną ścieżkę do pliku .sqlite"
    
    if path.suffix.lower() not in ['.sqlite', '.db', '.sqlite3']:
        return False, f"Plik nie ma rozszerzenia .sqlite: {path_str}"
    
    if not path.exists():
        parent = path.parent
        suggestions = []
        if parent.exists():
            suggestions.append(f"\n   📁 Katalog istnieje: {parent}")
            try:
                files = list(parent.glob("*.sqlite"))
                if files:
                    suggestions.append(f"   📄 Znalezione pliki .sqlite:")
                    for f in files[:5]:
                        suggestions.append(f"      • {f.name}")
            except:
                pass
        
        error = f"Plik nie istnieje: {path_str}"
        if suggestions:
            error += "\n" + "\n".join(suggestions)
        
        return False, error
    
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
        con.execute("SELECT name FROM sqlite_master LIMIT 1")
        con.close()
        return True, ""
    except Exception as e:
        return False, f"Nie można otworzyć pliku: {path_str}\n   Błąd: {e}"


def get_existing_columns(con: sqlite3.Connection, table: str) -> dict:
    """
    Pobiera listę istniejących kolumn w tabeli.
    
    Returns:
        Dict: {nazwa_kolumny_lowercase: oryginalna_nazwa_kolumny}
    """
    try:
        cur = con.execute(f"PRAGMA table_info({table})")
        return {row[1].lower(): row[1] for row in cur.fetchall()}
    except:
        return {}


def table_exists(con: sqlite3.Connection, table_name: str) -> bool:
    """Sprawdza czy tabela istnieje."""
    try:
        cur = con.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name=?
        """, (table_name,))
        return cur.fetchone() is not None
    except:
        return False


def index_exists(con: sqlite3.Connection, index_name: str) -> bool:
    """Sprawdza czy indeks istnieje."""
    try:
        cur = con.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name=?
        """, (index_name,))
        return cur.fetchone() is not None
    except:
        return False


def migrate_full(master_db_path: str):
    """
    Wykonaj pełną migrację bazy danych.
    
    Args:
        master_db_path: Ścieżka do master.sqlite
    """
    print("=" * 80)
    print("MIGRACJA KOMPLETNA - System BOM")
    print("=" * 80)
    print()
    
    # Waliduj ścieżkę
    is_valid, error_msg = validate_database_path(master_db_path)
    if not is_valid:
        print(f"❌ Błąd: {error_msg}")
        print()
        print("💡 Pomoc:")
        print("   1. Sprawdź czy plik master.sqlite istnieje")
        print("   2. Podaj PEŁNĄ ścieżkę do PLIKU (nie katalogu)")
        print("   3. Przykład: python migrate_full.py \"Z:/RM_BAZA/master.sqlite\"")
        return False
    
    db_path = Path(master_db_path)
    
    try:
        # Połącz z bazą
        con = sqlite3.connect(master_db_path, timeout=30.0)
        print(f"✅ Połączono z: {master_db_path}")
        print(f"   Rozmiar: {db_path.stat().st_size / 1024 / 1024:.2f} MB")
        print()
        
        changes_made = 0
        
        # ===================================================================
        # KROK 1: Dodanie/modyfikacja kolumn w tabeli projects
        # ===================================================================
        print("🔧 KROK 1: Sprawdzanie i dodawanie kolumn w tabeli projects...")
        print("-" * 80)
        
        columns = get_existing_columns(con, "projects")
        
        # Lista kolumn do dodania/sprawdzenia
        columns_to_add = [
            ("designer", "TEXT", "Konstruktor/projektant"),
            ("started_at", "TEXT", "Data rozpoczęcia prac"),
            ("expected_delivery", "TEXT", "Planowany termin odbioru"),
            ("completed_at", "TEXT", "Data faktycznego zakończenia"),
            ("fat", "TEXT", "Factory Acceptance Test (data)"),
            ("status", "TEXT NOT NULL DEFAULT 'PROJEKT'", "Status projektu"),
            ("status_changed_at", "TEXT", "Data ostatniej zmiany statusu"),
        ]
        
        # Sprawdź montaz/sat
        if "montaz" not in columns and "sat" not in columns:
            columns_to_add.insert(4, ("montaz", "TEXT", "Data montażu (dawniej SAT)"))
        
        for col_name, col_type, description in columns_to_add:
            if col_name not in columns:
                try:
                    con.execute(f"ALTER TABLE projects ADD COLUMN {col_name} {col_type};")
                    print(f"   ✅ Dodano kolumnę: {col_name} - {description}")
                    changes_made += 1
                except sqlite3.OperationalError as e:
                    print(f"   ⚠️  Kolumna {col_name} już istnieje lub błąd: {e}")
            else:
                print(f"   ℹ️  Kolumna {col_name} już istnieje - pominięto")
        
        # Normalizacja wartości NULL dla status
        try:
            con.execute("UPDATE projects SET status='PROJEKT' WHERE status IS NULL OR status='';")
            con.commit()
        except:
            pass
        
        print()
        
        # ===================================================================
        # KROK 2: Zmiana nazwy kolumny sat → montaz
        # ===================================================================
        print("🔧 KROK 2: Zmiana nazwy kolumny sat → montaz...")
        print("-" * 80)
        
        columns = get_existing_columns(con, "projects")
        
        if 'sat' in columns:
            try:
                con.execute("ALTER TABLE projects RENAME COLUMN sat TO montaz;")
                print("   ✅ Zmieniono nazwę kolumny: sat → montaz")
                changes_made += 1
            except sqlite3.OperationalError as e:
                if "no such column" not in str(e).lower():
                    print(f"   ⚠️  Nie można zmienić nazwy kolumny SAT: {e}")
                    print("      Prawdopodobnie starsza wersja SQLite")
                    print("      Kolumna pozostanie jako 'sat' (kod obsługuje obie nazwy)")
        elif 'montaz' in columns:
            print("   ℹ️  Kolumna 'montaz' już istnieje - pominięto")
        else:
            print("   ⚠️  Nie znaleziono kolumny 'sat' ani 'montaz'")
        
        print()
        
        # ===================================================================
        # KROK 3: Tabela project_statuses (multi-status)
        # ===================================================================
        print("🔧 KROK 3: Tworzenie tabeli project_statuses (multi-status)...")
        print("-" * 80)
        
        if not table_exists(con, "project_statuses"):
            con.execute("""
                CREATE TABLE project_statuses (
                    project_id     INTEGER NOT NULL,
                    status         TEXT NOT NULL,
                    set_at         TEXT NOT NULL DEFAULT (datetime('now')),
                    set_by         TEXT,
                    PRIMARY KEY (project_id, status),
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                )
            """)
            print("   ✅ Utworzono tabelę: project_statuses")
            changes_made += 1
            
            # Indeksy
            if not index_exists(con, "idx_project_statuses_project"):
                con.execute("""
                    CREATE INDEX idx_project_statuses_project 
                    ON project_statuses(project_id)
                """)
                print("   ✅ Utworzono indeks: idx_project_statuses_project")
                changes_made += 1
            
            if not index_exists(con, "idx_project_statuses_status"):
                con.execute("""
                    CREATE INDEX idx_project_statuses_status 
                    ON project_statuses(status)
                """)
                print("   ✅ Utworzono indeks: idx_project_statuses_status")
                changes_made += 1
        else:
            print("   ℹ️  Tabela project_statuses już istnieje - pominięto")
            
            # Sprawdź indeksy
            if not index_exists(con, "idx_project_statuses_project"):
                con.execute("""
                    CREATE INDEX idx_project_statuses_project 
                    ON project_statuses(project_id)
                """)
                print("   ✅ Utworzono brakujący indeks: idx_project_statuses_project")
                changes_made += 1
            
            if not index_exists(con, "idx_project_statuses_status"):
                con.execute("""
                    CREATE INDEX idx_project_statuses_status 
                    ON project_statuses(status)
                """)
                print("   ✅ Utworzono brakujący indeks: idx_project_statuses_status")
                changes_made += 1
        
        print()
        
        # ===================================================================
        # KROK 4: Tabela project_status_history (kompatybilność)
        # ===================================================================
        print("🔧 KROK 4: Tworzenie tabeli project_status_history (historia)...")
        print("-" * 80)
        
        if not table_exists(con, "project_status_history"):
            con.execute("""
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
            print("   ✅ Utworzono tabelę: project_status_history")
            changes_made += 1
            
            # Indeks
            if not index_exists(con, "idx_status_history_project"):
                con.execute("""
                    CREATE INDEX idx_status_history_project 
                    ON project_status_history(project_id, changed_at DESC)
                """)
                print("   ✅ Utworzono indeks: idx_status_history_project")
                changes_made += 1
            
            # Inicjalizuj historię dla istniejących projektów
            try:
                # Znajdź nazwę kolumny klucza głównego
                pk_name = "id"
                for col in get_existing_columns(con, "projects").values():
                    if col.lower() in ["id", "project_id"]:
                        pk_name = col
                        break
                
                cur = con.execute(f"""
                    SELECT {pk_name}, status, created_at
                    FROM projects
                """)
                projects = cur.fetchall()
                
                init_count = 0
                for proj_id, status, created_at in projects:
                    # Sprawdź czy już jest wpis historii
                    cur = con.execute("""
                        SELECT COUNT(*) FROM project_status_history 
                        WHERE project_id = ?
                    """, (proj_id,))
                    
                    if cur.fetchone()[0] == 0:
                        con.execute("""
                            INSERT INTO project_status_history 
                            (project_id, old_status, new_status, changed_at, notes)
                            VALUES (?, NULL, ?, ?, 'Automatyczna inicjalizacja historii')
                        """, (proj_id, status or 'PROJEKT', created_at or datetime.now().isoformat()))
                        init_count += 1
                
                if init_count > 0:
                    print(f"   ✅ Zainicjalizowano historię dla {init_count} projektów")
                    changes_made += 1
                    
            except Exception as e:
                print(f"   ⚠️  Błąd inicjalizacji historii: {e}")
        else:
            print("   ℹ️  Tabela project_status_history już istnieje - pominięto")
            
            # Sprawdź indeks
            if not index_exists(con, "idx_status_history_project"):
                con.execute("""
                    CREATE INDEX idx_status_history_project 
                    ON project_status_history(project_id, changed_at DESC)
                """)
                print("   ✅ Utworzono brakujący indeks: idx_status_history_project")
                changes_made += 1
        
        print()
        
        # ===================================================================
        # KROK 5: Tabela project_status_changes (szczegółowa historia)
        # ===================================================================
        print("🔧 KROK 5: Tworzenie tabeli project_status_changes (szczegółowa historia)...")
        print("-" * 80)
        
        if not table_exists(con, "project_status_changes"):
            con.execute("""
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
            print("   ✅ Utworzono tabelę: project_status_changes")
            changes_made += 1
            
            # Indeksy
            indexes = [
                ("idx_status_changes_project", "project_id, changed_at DESC"),
                ("idx_status_changes_status", "status, changed_at DESC"),
                ("idx_status_changes_project_status", "project_id, status, changed_at DESC"),
            ]
            
            for idx_name, idx_cols in indexes:
                if not index_exists(con, idx_name):
                    con.execute(f"""
                        CREATE INDEX {idx_name} 
                        ON project_status_changes({idx_cols})
                    """)
                    print(f"   ✅ Utworzono indeks: {idx_name}")
                    changes_made += 1
        else:
            print("   ℹ️  Tabela project_status_changes już istnieje - pominięto")
            
            # Sprawdź indeksy
            indexes = [
                ("idx_status_changes_project", "project_id, changed_at DESC"),
                ("idx_status_changes_status", "status, changed_at DESC"),
                ("idx_status_changes_project_status", "project_id, status, changed_at DESC"),
            ]
            
            for idx_name, idx_cols in indexes:
                if not index_exists(con, idx_name):
                    con.execute(f"""
                        CREATE INDEX {idx_name} 
                        ON project_status_changes({idx_cols})
                    """)
                    print(f"   ✅ Utworzono brakujący indeks: {idx_name}")
                    changes_made += 1
        
        print()
        
        # Zatwierdź wszystkie zmiany
        con.commit()
        
        # ===================================================================
        # PODSUMOWANIE
        # ===================================================================
        print("=" * 80)
        print("PODSUMOWANIE")
        print("=" * 80)
        print()
        
        if changes_made > 0:
            print(f"✅ Migracja zakończona pomyślnie!")
            print(f"   Wykonano: {changes_made} zmian(y)")
        else:
            print("ℹ️  Baza danych jest już aktualna - nie wykonano żadnych zmian")
        
        print()
        print("📊 Struktura bazy danych:")
        print()
        print("Tabele:")
        print("  ✅ projects - rozszerzona o nowe kolumny")
        print("  ✅ project_statuses - multi-status system")
        print("  ✅ project_status_history - historia zmian (kompatybilność)")
        print("  ✅ project_status_changes - szczegółowa historia (ADDED/REMOVED)")
        print()
        print("Kolumny w projects:")
        cols = get_existing_columns(con, "projects")
        key_cols = ["designer", "montaz", "sat", "fat", "status", "completed_at"]
        for col in key_cols:
            if col in cols:
                print(f"  ✅ {cols[col]}")
        print()
        print("📈 Nowe możliwości:")
        print("  • Wiele statusów jednocześnie (checkboxy)")
        print("  • Szczegółowa historia każdego statusu")
        print("  • Analiza czasu w statusach")
        print("  • Pełny audyt zmian")
        print()
        print("⚠️  UWAGA:")
        print("  • Istniejące projekty NIE mają ustawionych statusów w project_statuses")
        print("  • Nowe projekty automatycznie dostaną status 'PRZYJETY'")
        print("  • Szczegółowa historia działa od teraz - przeszłe zmiany nie są śledzone")
        print("  • Edytuj projekty w GUI aby ustawić statusy")
        print()
        
        # Statystyki
        stats = []
        for table in ["projects", "project_statuses", "project_status_history", "project_status_changes"]:
            if table_exists(con, table):
                cur = con.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                stats.append(f"{table}: {count} rekordów")
        
        if stats:
            print("📊 Statystyki:")
            for stat in stats:
                print(f"  • {stat}")
            print()
        
        con.close()
        return True
        
    except Exception as e:
        print(f"\n❌ Błąd migracji: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 80)
    print("MIGRACJA KOMPLETNA - System BOM")
    print("=" * 80)
    print()
    
    master_path = None
    
    # Sprawdź czy podano ścieżkę jako argument
    if len(sys.argv) > 1:
        master_path = sys.argv[1]
        print(f"📌 Użyto ścieżki z argumentu: {master_path}")
        print()
    else:
        # Spróbuj odczytać z pliku config
        print("🔍 Szukam pliku konfiguracyjnego aplikacji...")
        config_path = get_master_path_from_config()
        
        if config_path:
            master_path = config_path
            print("✅ Znaleziono ścieżkę do bazy danych")
        else:
            print("⚠️  Nie znaleziono pliku konfiguracyjnego")
            print()
            print("💡 Podaj ścieżkę jako argument:")
            print('   python migrate_full.py "Y:/RM_BAZA/master.sqlite"')
            sys.exit(1)
    
    print()
    
    # Wykonaj migrację
    success = migrate_full(master_path)
    
    if success:
        print("🎉 Gotowe! Aplikacja jest gotowa do użycia z nowymi funkcjami.")
        sys.exit(0)
    else:
        print("❌ Migracja nie powiodła się.")
        sys.exit(1)
