"""
Skrypt diagnostyczny - wypisuje strukturę bazy RM_MANAGER backup
"""
import sqlite3
import sys
from pathlib import Path

def diagnose_backup(db_path: str):
    """Wypisz pełną strukturę bazy backup"""
    
    if not Path(db_path).exists():
        print(f"❌ Plik nie istnieje: {db_path}")
        return
    
    print(f"\n{'='*80}")
    print(f"📂 DIAGNOSTYKA STRUKTURY BAZY: {db_path}")
    print(f"📏 Rozmiar: {Path(db_path).stat().st_size / 1024:.1f} KB")
    print(f"{'='*80}\n")
    
    con = sqlite3.connect(db_path, timeout=10.0)
    con.row_factory = sqlite3.Row
    
    try:
        # Lista tabel
        cursor = con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"📋 TABELE ({len(tables)}):")
        for table in tables:
            print(f"  • {table}")
        print()
        
        # Szczegóły każdej tabeli
        for table in tables:
            print(f"\n{'─'*80}")
            print(f"🔍 TABELA: {table}")
            print(f"{'─'*80}")
            
            # Kolumny
            cursor = con.execute(f"PRAGMA table_info({table})")
            cols = cursor.fetchall()
            
            print(f"\n  KOLUMNY ({len(cols)}):")
            for col in cols:
                pk = " [PK]" if col[5] else ""
                notnull = " NOT NULL" if col[3] else ""
                default = f" DEFAULT {col[4]}" if col[4] else ""
                print(f"    {col[1]:30s} {col[2]:15s}{pk}{notnull}{default}")
            
            # Indeksy
            cursor = con.execute(f"SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=?", (table,))
            indexes = cursor.fetchall()
            if indexes:
                print(f"\n  INDEKSY ({len(indexes)}):")
                for idx in indexes:
                    print(f"    • {idx[0]}")
            
            # Liczba rekordów
            cursor = con.execute(f"SELECT COUNT(*) as cnt FROM {table}")
            count = cursor.fetchone()[0]
            print(f"\n  📊 REKORDÓW: {count}")
            
            # Przykładowe dane (max 3 rekordy)
            if count > 0 and count < 1000:
                cursor = con.execute(f"SELECT * FROM {table} LIMIT 3")
                rows = cursor.fetchall()
                
                if rows:
                    print(f"\n  📄 PRZYKŁADOWE DANE (max 3 rekordy):")
                    for i, row in enumerate(rows, 1):
                        print(f"\n    Rekord #{i}:")
                        for key in row.keys():
                            value = row[key]
                            # Skróć długie wartości
                            if isinstance(value, str) and len(value) > 50:
                                value = value[:47] + "..."
                            print(f"      {key:25s} = {value}")
        
        print(f"\n\n{'='*80}")
        print(f"✅ DIAGNOSTYKA ZAKOŃCZONA")
        print(f"{'='*80}\n")
        
    finally:
        con.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Użycie: python diagnose_backup_structure.py <ścieżka_do_backupu>")
        print("\nPrzykład:")
        print("  python diagnose_backup_structure.py C:/RMPAK_CLIENT/RM_MANAGER/backups/projects/project_29/project_29_2026-04-12.sqlite")
        sys.exit(1)
    
    db_path = sys.argv[1]
    diagnose_backup(db_path)
