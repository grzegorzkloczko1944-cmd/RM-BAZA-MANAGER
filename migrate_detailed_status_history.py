"""
============================================================================
MIGRACJA: Szczegółowa historia statusów (Detailed Status Tracking)
============================================================================
Skrypt dodaje tabelę project_status_changes do śledzenia każdej zmiany
statusu osobno (dodanie/usunięcie).

WYMAGA: Już uruchomionej migracji migrate_multi_status.py

Tworzy:
- Tabelę project_status_changes z kolumnami:
  * id - unikalny identyfikator
  * project_id - do którego projektu
  * status - nazwa statusu
  * action - 'ADDED' lub 'REMOVED'
  * changed_at - kiedy
  * changed_by - kto
  * notes - opcjonalne notatki
- 3 indeksy dla szybkiego wyszukiwania

UŻYCIE:
    python migrate_detailed_status_history.py                      # Auto-detect z config
    python migrate_detailed_status_history.py <ścieżka_do_pliku>  # Własna ścieżka
    
PRZYKŁADY:
    python migrate_detailed_status_history.py
    python migrate_detailed_status_history.py "Y:/RM_BAZA/master.sqlite"
============================================================================
"""

import sqlite3
from pathlib import Path
import sys
import json


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
        return False, f"Podano katalog zamiast pliku: {path_str}"
    
    if path.suffix.lower() not in ['.sqlite', '.db', '.sqlite3']:
        return False, f"Plik nie ma rozszerzenia .sqlite: {path_str}"
    
    if not path.exists():
        return False, f"Plik nie istnieje: {path_str}"
    
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
        con.execute("SELECT name FROM sqlite_master LIMIT 1")
        con.close()
        return True, ""
    except Exception as e:
        return False, f"Nie można otworzyć pliku: {path_str}\n   Błąd: {e}"


def migrate_detailed_status_history(master_db_path: str):
    """
    Wykonaj migrację - dodaj tabelę szczegółowej historii statusów.
    
    Args:
        master_db_path: Ścieżka do master.sqlite
    """
    print("=" * 80)
    print("MIGRACJA: Szczegółowa Historia Statusów")
    print("=" * 80)
    print()
    
    # Waliduj ścieżkę
    is_valid, error_msg = validate_database_path(master_db_path)
    if not is_valid:
        print(f"❌ Błąd: {error_msg}")
        return False
    
    db_path = Path(master_db_path)
    
    try:
        # Połącz z bazą
        con = sqlite3.connect(master_db_path, timeout=30.0)
        print(f"✅ Połączono z: {master_db_path}")
        print(f"   Rozmiar: {db_path.stat().st_size / 1024 / 1024:.2f} MB")
        
        # Sprawdź czy tabela project_statuses istnieje (wymóg)
        cur = con.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='project_statuses'
        """)
        
        if not cur.fetchone():
            print()
            print("❌ BŁĄD: Tabela project_statuses nie istnieje!")
            print("   Najpierw uruchom: python migrate_multi_status.py")
            con.close()
            return False
        
        # Sprawdź czy tabela już istnieje
        cur = con.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='project_status_changes'
        """)
        
        if cur.fetchone():
            print()
            print("⚠️  Tabela project_status_changes już istnieje - migracja nie jest potrzebna")
            
            # Pokaż ile rekordów jest już w bazie
            cur = con.execute("SELECT COUNT(*) FROM project_status_changes")
            count = cur.fetchone()[0]
            print(f"   Rekordów w project_status_changes: {count}")
            
            con.close()
            return True
        
        print("\n📋 Tworzenie tabeli szczegółowej historii...")
        
        # Utwórz tabelę project_status_changes
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
        print("✅ Utworzono tabelę: project_status_changes")
        
        # Indeks dla szybkiego wyszukiwania po projekcie
        con.execute("""
            CREATE INDEX idx_status_changes_project 
            ON project_status_changes(project_id, changed_at DESC)
        """)
        print("✅ Utworzono indeks: idx_status_changes_project")
        
        # Indeks dla wyszukiwania po statusie
        con.execute("""
            CREATE INDEX idx_status_changes_status 
            ON project_status_changes(status, changed_at DESC)
        """)
        print("✅ Utworzono indeks: idx_status_changes_status")
        
        # Indeks dla wyszukiwania kombinacji projekt+status
        con.execute("""
            CREATE INDEX idx_status_changes_project_status 
            ON project_status_changes(project_id, status, changed_at DESC)
        """)
        print("✅ Utworzono indeks: idx_status_changes_project_status")
        
        # Zatwierdź zmiany
        con.commit()
        print("\n✅ Migracja zakończona pomyślnie!")
        
        # Pokaż informacje
        print("\n" + "=" * 80)
        print("INFORMACJE")
        print("=" * 80)
        print()
        print("📊 Nowa funkcjonalność:")
        print()
        print("Szczegółowa historia śledzi KAŻDĄ zmianę statusu:")
        print("  • Dodanie statusu (ADDED)")
        print("  • Usunięcie statusu (REMOVED)")
        print("  • Timestamp każdej zmiany")
        print("  • Kto wykonał zmianę")
        print()
        print("📈 Możliwości analizy:")
        print("  • Ile czasu projekt spędził w każdym statusie")
        print("  • Kiedy konkretnie status został dodany/usunięty")
        print("  • Pełna linia czasu zmian")
        print("  • Audyt kto i kiedy zmieniał statusy")
        print()
        print("⚠️  UWAGA:")
        print("  • Historia zaczyna się OD TEGO MOMENTU")
        print("  • Przeszłe zmiany (przed migracją) NIE są śledzone szczegółowo")
        print("  • Dla nowych zmian każde kliknięcie checkboxa będzie zapisane")
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
    print("MIGRACJA: Szczegółowa Historia Statusów")
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
            print('   python migrate_detailed_status_history.py "Y:/RM_BAZA/master.sqlite"')
            sys.exit(1)
    
    print()
    
    # Wykonaj migrację
    success = migrate_detailed_status_history(master_path)
    
    if success:
        print("\n🎉 Gotowe! Aplikacja będzie teraz śledziła szczegółową historię statusów.")
        sys.exit(0)
    else:
        print("\n❌ Migracja nie powiodła się.")
        sys.exit(1)
