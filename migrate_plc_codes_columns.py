#!/usr/bin/env python3
"""
Migracja: Dodaj nowe kolumny do plc_unlock_codes i utwórz tabelę plc_authorized_senders

Data: 2026-04-15
Autor: System
"""

import sqlite3
import sys


def migrate_plc_codes(db_path: str) -> dict:
    """Dodaj nowe kolumny do tabeli plc_unlock_codes i utwórz plc_authorized_senders.
    
    Args:
        db_path: Ścieżka do rm_manager.sqlite
    
    Returns:
        Dict ze statystykami migracji
    """
    con = sqlite3.connect(db_path, timeout=30.0)
    con.row_factory = sqlite3.Row
    
    stats = {
        'columns_added': 0,
        'tables_created': 0,
        'errors': []
    }
    
    try:
        # Sprawdź czy tabela plc_unlock_codes istnieje
        cursor = con.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='plc_unlock_codes'
        """)
        
        if not cursor.fetchone():
            stats['errors'].append("Tabela plc_unlock_codes nie istnieje")
            return stats
        
        # Sprawdź jakie kolumny już istnieją
        cursor = con.execute("PRAGMA table_info(plc_unlock_codes)")
        existing_columns = {row['name'] for row in cursor.fetchall()}
        
        print(f"📋 Istniejące kolumny: {existing_columns}")
        
        # Dodaj nowe kolumny jeśli nie istnieją
        new_columns = [
            ('sent_at', 'DATETIME'),
            ('sent_by', 'TEXT'),
            ('sent_via', 'TEXT'),
            ('expiry_date', 'DATETIME')
        ]
        
        for col_name, col_type in new_columns:
            if col_name not in existing_columns:
                try:
                    print(f"➕ Dodaję kolumnę: {col_name} {col_type}")
                    con.execute(f"ALTER TABLE plc_unlock_codes ADD COLUMN {col_name} {col_type}")
                    stats['columns_added'] += 1
                except Exception as e:
                    stats['errors'].append(f"Błąd dodawania {col_name}: {e}")
                    print(f"❌ Błąd: {e}")
            else:
                print(f"✅ Kolumna {col_name} już istnieje")
        
        # Utwórz tabelę plc_authorized_senders jeśli nie istnieje
        cursor = con.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='plc_authorized_senders'
        """)
        
        if not cursor.fetchone():
            print("📦 Tworzę tabelę plc_authorized_senders...")
            con.execute("""
                CREATE TABLE plc_authorized_senders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    added_by TEXT,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_plc_senders_username ON plc_authorized_senders(username)")
            stats['tables_created'] += 1
            print("✅ Tabela utworzona")
        else:
            print("✅ Tabela plc_authorized_senders już istnieje")
        
        con.commit()
        print(f"\n✅ Migracja zakończona:")
        print(f"   Dodano kolumn: {stats['columns_added']}")
        print(f"   Utworzono tabel: {stats['tables_created']}")
        
        if stats['errors']:
            print(f"\n⚠️  Błędy: {len(stats['errors'])}")
            for err in stats['errors']:
                print(f"   - {err}")
        
    except Exception as e:
        stats['errors'].append(f"Błąd główny: {e}")
        print(f"❌ Błąd główny: {e}")
        con.rollback()
    
    finally:
        con.close()
    
    return stats


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrate_plc_codes_columns.py <rm_manager.sqlite>")
        print("\nPrzykład:")
        print("  python migrate_plc_codes_columns.py Y:/RM_MANAGER/rm_manager.sqlite")
        sys.exit(1)
    
    db_path = sys.argv[1]
    print(f"🔧 Migracja bazydanych: {db_path}\n")
    
    migrate_plc_codes(db_path)
    
    print("\n✅ Gotowe!")
