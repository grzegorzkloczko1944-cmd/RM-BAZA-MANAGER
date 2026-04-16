#!/usr/bin/env python3
"""
Test RM_MANAGER GUI - Integracja z RM_BAZA
Tworzy przykładowe projekty w master.sqlite i uruchamia GUI
"""

import os
import sys
import sqlite3

# Import modułów
import rm_manager as rmm
import rm_manager_gui

# ============================================================================
# Przygotowanie danych testowych
# ============================================================================

def setup_test_data():
    """Utwórz przykładowe projekty dla GUI"""
    
    rm_db_path = "rm_manager.sqlite"
    master_db_path = "master.sqlite"
    
    # Usuń stare bazy jeśli istnieją
    for db in [rm_db_path, master_db_path]:
        if os.path.exists(db):
            print(f"🗑️  Usuwam starą bazę: {db}")
            os.remove(db)
    
    print("\n" + "=" * 70)
    print("PRZYGOTOWANIE DANYCH TESTOWYCH - RM_MANAGER + RM_BAZA")
    print("=" * 70)
    
    # 1. Inicjalizacja RM_MANAGER
    print("\n1️⃣  Inicjalizacja RM_MANAGER...")
    # Master baza (globalne tabele)
    rmm.ensure_rm_master_tables(rm_db_path)
    # Per-projekt bazy utworzymy później dla każdego projektu
    
    # 2. Inicjalizacja MASTER (RM_BAZA)
    print("\n2️⃣  Inicjalizacja master.sqlite (RM_BAZA)...")
    master_con = sqlite3.connect(master_db_path)
    master_con.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            project_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            path TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            project_type TEXT NOT NULL DEFAULT 'MACHINE',
            started_at TEXT,
            expected_delivery TEXT,
            completed_at TEXT,
            designer TEXT,
            status TEXT NOT NULL DEFAULT 'W_REALIZACJI',
            status_changed_at TEXT,
            sat TEXT,
            fat TEXT
        )
    """)
    
    # Tabela project_statuses (multi-status checkboxy)
    master_con.execute("""
        CREATE TABLE IF NOT EXISTS project_statuses (
            project_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 0,
            changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            changed_by TEXT,
            PRIMARY KEY (project_id, status)
        )
    """)
    
    master_con.commit()
    
    # 3. Tworzenie projektów w MASTER
    print("\n3️⃣  Tworzenie projektów w master.sqlite...")
    
    # Projekt 100
    print("   📦 Projekt 100 - Linia produkcyjna A")
    master_con.execute("""
        INSERT INTO projects (project_id, name, project_type, designer, status, started_at, active)
        VALUES (100, '100 - Linia produkcyjna A', 'MACHINE', 'Jan Kowalski', 'PROJEKT', '2026-04-01', 1)
    """)
    
    # Projekt 200
    print("   📦 Projekt 200 - Linia produkcyjna B")
    master_con.execute("""
        INSERT INTO projects (project_id, name, project_type, designer, status, started_at, active)
        VALUES (200, '200 - Linia produkcyjna B', 'MACHINE', 'Maria Nowak', 'KOMPLETACJA', '2026-04-10', 1)
    """)
    
    # Projekt 300
    print("   📦 Projekt 300 - Magazyn automatyczny")
    master_con.execute("""
        INSERT INTO projects (project_id, name, project_type, designer, status, started_at, active)
        VALUES (300, '300 - Magazyn automatyczny', 'WAREHOUSE', 'Piotr Wiśniewski', 'URUCHOMIENIE', '2026-03-01', 1)
    """)
    
    master_con.commit()
    master_con.close()
    
    print("\n✅ Projekty utworzone w master.sqlite")
    print("\n💡 GUI automatycznie zainicjalizuje projekty w RM_MANAGER przy pierwszym otwarciu")
    
    print("\n" + "=" * 70)
    print("✅ DANE TESTOWE UTWORZONE")
    print("=" * 70)
    print("\nProjekty w master.sqlite:")
    print("  100 - Linia produkcyjna A (PROJEKT)")
    print("  200 - Linia produkcyjna B (KOMPLETACJA)")
    print("  300 - Magazyn automatyczny (URUCHOMIENIE)")
    print("\n💡 RM_MANAGER automatycznie zainicjalizuje projekty przy pierwszym otwarciu")
    print("💾 Bazy: master.sqlite + rm_manager.sqlite")
    print("\n")


# ============================================================================
# Main
# ============================================================================

def main():
    print("=" * 70)
    print("TEST RM_MANAGER GUI")
    print("=" * 70)
    
    # Setup
    setup_test_data()
    
    # Uruchom GUI
    print("🚀 Uruchamiam GUI...\n")
    
    try:
        rm_manager_gui.main()
    except KeyboardInterrupt:
        print("\n\n👋 Zamykam GUI...")
    except Exception as e:
        print(f"\n❌ Błąd GUI: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
