"""
============================================================================
MIGRACJA: Multi-Status System dla projektów
============================================================================
Skrypt do inicjalizacji nowego systemu wielokrotnych statusów.

Tworzy:
- Tabelę project_statuses (many-to-many)
- Indeksy dla szybkiego wyszukiwania

UWAGA: Stare dane w kolumnie projects.status są IGNOROWANE.
       Nowe projekty będą używały nowego systemu.
       Istniejące projekty nie mają żadnych statusów do czasu ręcznej edycji.

UŻYCIE:
    python migrate_multi_status.py                      # Auto-detect z config
    python migrate_multi_status.py <ścieżka_do_pliku>  # Własna ścieżka
    
PRZYKŁADY:
    python migrate_multi_status.py
    python migrate_multi_status.py "Y:/RM_BAZA/master.sqlite"
    python migrate_multi_status.py "Z:/RM_BAZA/master.sqlite"
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
    # Możliwe lokalizacje pliku config
    config_paths = [
        Path("C:/RMPAK_CLIENT/sync_config.json"),
        Path.home() / "RMPAK_CLIENT" / "sync_config.json",
        Path("sync_config.json"),  # Lokalnie w bieżącym katalogu
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
        except Exception as e:
            # Ignoruj błędy odczytu - spróbuj następnego pliku
            continue
    
    return None


def validate_database_path(path_str: str) -> tuple:
    """
    Waliduje ścieżkę do pliku bazy danych.
    
    Args:
        path_str: Ścieżka do sprawdzenia
    
    Returns:
        (bool, str): (is_valid, error_message)
    """
    if not path_str:
        return False, "Nie podano ścieżki do bazy danych!"
    
    path = Path(path_str)
    
    # Sprawdź czy to katalog zamiast pliku
    if path.exists() and path.is_dir():
        return False, f"Podano katalog zamiast pliku: {path_str}\n   Podaj pełną ścieżkę do pliku .sqlite, np:\n   {path}/master.sqlite"
    
    # Sprawdź czy ma rozszerzenie .sqlite
    if path.suffix.lower() not in ['.sqlite', '.db', '.sqlite3']:
        return False, f"Plik nie ma rozszerzenia .sqlite: {path_str}\n   Upewnij się że podałeś pełną ścieżkę do pliku bazy danych."
    
    # Sprawdź czy plik istnieje
    if not path.exists():
        # Pokaż możliwe katalogi
        parent = path.parent
        suggestions = []
        if parent.exists():
            suggestions.append(f"\n   📁 Katalog istnieje: {parent}")
            try:
                files = list(parent.glob("*.sqlite"))
                if files:
                    suggestions.append(f"   📄 Znalezione pliki .sqlite:")
                    for f in files[:5]:  # Max 5 plików
                        suggestions.append(f"      • {f.name}")
            except:
                pass
        
        error = f"Plik nie istnieje: {path_str}"
        if suggestions:
            error += "\n" + "\n".join(suggestions)
        
        return False, error
    
    # Sprawdź czy to faktycznie baza SQLite
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
        con.execute("SELECT name FROM sqlite_master LIMIT 1")
        con.close()
        return True, ""
    except sqlite3.DatabaseError:
        return False, f"Plik nie jest prawidłową bazą SQLite: {path_str}"
    except Exception as e:
        return False, f"Nie można otworzyć pliku: {path_str}\n   Błąd: {e}"



def migrate_multi_status(master_db_path: str):
    """
    Wykonaj migrację do nowego systemu multi-status.
    
    Args:
        master_db_path: Ścieżka do master.sqlite
    """
    print("=" * 80)
    print("MIGRACJA: Multi-Status System")
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
        print("   3. Przykład: python migrate_multi_status.py \"Z:/RM_BAZA/master.sqlite\"")
        return False
    
    db_path = Path(master_db_path)
    
    try:
        # Połącz z bazą
        con = sqlite3.connect(master_db_path, timeout=30.0)
        print(f"✅ Połączono z: {master_db_path}")
        print(f"   Rozmiar: {db_path.stat().st_size / 1024 / 1024:.2f} MB")
        
        # Sprawdź czy tabela już istnieje
        cur = con.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='project_statuses'
        """)
        
        if cur.fetchone():
            print("⚠️  Tabela project_statuses już istnieje - migracja nie jest potrzebna")
            
            # Pokaż ile statusów jest już w bazie
            cur = con.execute("SELECT COUNT(*) FROM project_statuses")
            count = cur.fetchone()[0]
            print(f"   Rekordów w project_statuses: {count}")
            
            con.close()
            return True
        
        print("\n📋 Tworzenie nowej struktury...")
        
        # Utwórz tabelę project_statuses (many-to-many)
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
        print("✅ Utworzono tabelę: project_statuses")
        
        # Indeks dla szybkiego wyszukiwania po project_id
        con.execute("""
            CREATE INDEX idx_project_statuses_project 
            ON project_statuses(project_id)
        """)
        print("✅ Utworzono indeks: idx_project_statuses_project")
        
        # Indeks dla wyszukiwania po statusie
        con.execute("""
            CREATE INDEX idx_project_statuses_status 
            ON project_statuses(status)
        """)
        print("✅ Utworzono indeks: idx_project_statuses_status")
        
        # Zmiana nazwy kolumny SAT → montaz
        print("\n📝 Zmiana nazwy kolumny SAT → montaz...")
        
        # Sprawdź czy kolumna 'sat' istnieje
        cur = con.execute("PRAGMA table_info(projects)")
        columns = {row[1].lower(): row[1] for row in cur.fetchall()}
        
        if 'sat' in columns:
            # SQLite nie obsługuje RENAME COLUMN bezpośrednio w starszych wersjach
            # Musimy użyć ALTER TABLE ... RENAME COLUMN (SQLite 3.25.0+)
            try:
                con.execute("ALTER TABLE projects RENAME COLUMN sat TO montaz;")
                print("✅ Zmieniono nazwę kolumny: sat → montaz")
            except sqlite3.OperationalError as e:
                # Jeśli RENAME COLUMN nie działa, użyj starszej metody
                if "no such column" not in str(e).lower():
                    print(f"⚠️  Nie można zmienić nazwy kolumny SAT: {e}")
                    print("   Prawdopodobnie starsza wersja SQLite")
                    print("   Kolumna pozostanie jako 'sat' (kod obsługuje obie nazwy)")
        elif 'montaz' in columns:
            print("✅ Kolumna 'montaz' już istnieje - pominięto")
        else:
            print("⚠️  Nie znaleziono kolumny 'sat' ani 'montaz' - pominięto")
        
        # Zatwierdź zmiany
        con.commit()
        print("\n✅ Migracja zakończona pomyślnie!")
        
        # Pokaż informacje
        print("\n" + "=" * 80)
        print("INFORMACJE")
        print("=" * 80)
        print()
        print("Nowy system statusów:")
        print("  1. PRZYJETY       - Przyjęty do realizacji")
        print("  2. PROJEKT        - Faza projektowania")
        print("  3. KOMPLETACJA    - Kompletacja materiałów")
        print("  4. MONTAZ         - Montaż")
        print("  5. AUTOMATYKA     - Prace nad automatyką")
        print("  6. URUCHOMIENIE   - Uruchomienie")
        print("  7. ODBIORY        - Odbiory")
        print("  8. POPRAWKI       - Poprawki")
        print("  9. WSTRZYMANY     - Wstrzymany")
        print(" 10. ZAKONCZONY     - Zakończony")
        print()
        print("⚠️  UWAGA:")
        print("   • Istniejące projekty NIE mają ustawionych statusów")
        print("   • Stara kolumna projects.status jest IGNOROWANA")
        print("   • Nowe projekty automatycznie dostaną status 'PRZYJETY'")
        print("   • Edytuj projekty ręcznie aby ustawić statusy")
        print()
        print("📝 Zmiany w strukturze:")
        print("   • Kolumna 'sat' → 'montaz' (jeśli istniała)")
        print("   • FAT pozostaje bez zmian")
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
    print("MIGRACJA: Multi-Status System dla projektów")
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
            print()
        else:
            # Użyj domyślnej ścieżki
            master_path = "Y:/RM_BAZA/master.sqlite"
            print("⚠️  Nie znaleziono pliku config")
            print(f"📌 Używam domyślnej ścieżki: {master_path}")
            print()
            print("💡 Wskazówka:")
            print("   Jeśli baza jest w innej lokalizacji, podaj ścieżkę:")
            print("   python migrate_multi_status.py \"Z:/RM_BAZA/master.sqlite\"")
            print()
    
    # Wykonaj migrację
    success = migrate_multi_status(master_path)
    
    if success:
        print("\n" + "=" * 80)
        print("🎉 Gotowe! System multi-status jest aktywny.")
        print("=" * 80)
        print()
        print("Następne kroki:")
        print("  1. Uruchom aplikację: RM_BAZA_v15_MAG_STATS_ORG.py")
        print("  2. Otwórz listę projektów (Menu → Projekty)")
        print("  3. Edytuj projekt i ustaw statusy używając checkboxów")
        print()
        sys.exit(0)
    else:
        print("\n" + "=" * 80)
        print("❌ Migracja nieudana!")
        print("=" * 80)
        sys.exit(1)
