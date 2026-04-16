#!/usr/bin/env python3
"""
Migracja: Zmiana stage_code z AUTOMATYKA na ELEKTROMONTAZ
"""

import sqlite3
import glob
import os
from pathlib import Path

def migrate_database(db_path: str) -> dict:
    """Migruje pojedynczą bazę danych"""
    changes = {
        'stage_definitions': 0,
        'project_stages': 0,
        'stage_dependencies_pred': 0,
        'stage_dependencies_succ': 0
    }
    
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        
        # 1. stage_definitions
        cur.execute("UPDATE stage_definitions SET code = 'ELEKTROMONTAZ' WHERE code = 'AUTOMATYKA'")
        changes['stage_definitions'] = cur.rowcount
        
        # 2. project_stages
        cur.execute("UPDATE project_stages SET stage_code = 'ELEKTROMONTAZ' WHERE stage_code = 'AUTOMATYKA'")
        changes['project_stages'] = cur.rowcount
        
        # 3. stage_dependencies - predecessor
        cur.execute("UPDATE stage_dependencies SET predecessor_stage_code = 'ELEKTROMONTAZ' WHERE predecessor_stage_code = 'AUTOMATYKA'")
        changes['stage_dependencies_pred'] = cur.rowcount
        
        # 4. stage_dependencies - successor
        cur.execute("UPDATE stage_dependencies SET successor_stage_code = 'ELEKTROMONTAZ' WHERE successor_stage_code = 'AUTOMATYKA'")
        changes['stage_dependencies_succ'] = cur.rowcount
        
        con.commit()
        con.close()
        
        return changes
        
    except Exception as e:
        print(f"  ❌ Błąd: {e}")
        return None


def main():
    """Migruje wszystkie bazy rm_manager"""
    
    print("=" * 80)
    print("MIGRACJA: AUTOMATYKA → ELEKTROMONTAZ")
    print("=" * 80)
    print()
    
    # Ścieżka do RM_MANAGER (możesz zmienić)
    rm_manager_dir = r"C:\RMPAK_CLIENT\RM_MANAGER\rm_manager"
    
    if not os.path.exists(rm_manager_dir):
        print(f"⚠️  Katalog {rm_manager_dir} nie istnieje!")
        print("📝 Edytuj skrypt i podaj prawidłową ścieżkę.")
        return
    
    # Znajdź wszystkie bazy
    pattern = os.path.join(rm_manager_dir, "rm_manager_project_*.sqlite")
    project_dbs = glob.glob(pattern)
    master_db = os.path.join(rm_manager_dir, "rm_manager.sqlite")
    
    all_dbs = []
    if os.path.exists(master_db):
        all_dbs.append(("MASTER", master_db))
    
    for pdb in project_dbs:
        project_id = os.path.basename(pdb).replace("rm_manager_project_", "").replace(".sqlite", "")
        all_dbs.append((f"PROJECT {project_id}", pdb))
    
    if not all_dbs:
        print("⚠️  Nie znaleziono żadnych baz danych!")
        return
    
    print(f"Znaleziono {len(all_dbs)} baz danych:\n")
    
    # Migruj
    total_changes = 0
    migrated = 0
    
    for db_name, db_path in all_dbs:
        print(f"📁 {db_name}: {os.path.basename(db_path)}")
        
        changes = migrate_database(db_path)
        
        if changes:
            total = sum(changes.values())
            if total > 0:
                print(f"  ✅ Zmieniono {total} rekordów:")
                for table, count in changes.items():
                    if count > 0:
                        print(f"     • {table}: {count}")
                migrated += 1
            else:
                print(f"  ℹ️  Brak zmian (już zaktualizowane)")
            total_changes += total
        
        print()
    
    # Podsumowanie
    print("=" * 80)
    print("PODSUMOWANIE:")
    print(f"  Przetworzono baz: {len(all_dbs)}")
    print(f"  Zmigrowano:       {migrated}")
    print(f"  Zmieniono rekordów: {total_changes}")
    print("=" * 80)
    print()
    print("✅ Migracja zakończona!")
    print()
    print("WAŻNE:")
    print("  1. Uruchom rm_manager_gui.py")
    print("  2. Wybierz projekt")
    print("  3. Menu: Narzędzia → Aktualizuj definicje etapów")
    print("  4. To zsynchronizuje nowe nazwy w całym systemie")


if __name__ == "__main__":
    main()
