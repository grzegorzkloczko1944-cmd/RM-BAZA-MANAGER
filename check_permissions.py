#!/usr/bin/env python3
"""
Weryfikacja uprawnień użytkowników w rm_manager.sqlite
"""
import sqlite3
import os
import sys

# Domyślna ścieżka
DEFAULT_RM_MANAGER_DB = r"C:\RMPAK_CLIENT\RM_MANAGER\rm_manager\rm_manager.sqlite"

def check_permissions(db_path):
    """Sprawdź jakie uprawnienia są w bazie"""
    if not os.path.exists(db_path):
        print(f"❌ Baza nie istnieje: {db_path}")
        return False
    
    try:
        con = sqlite3.connect(db_path, timeout=10.0)
        con.row_factory = sqlite3.Row
        
        # Sprawdź czy tabela istnieje
        cursor = con.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='rm_user_permissions'
        """)
        if not cursor.fetchone():
            print(f"❌ Tabela rm_user_permissions nie istnieje w bazie!")
            con.close()
            return False
        
        # Pobierz wszystkie uprawnienia
        cursor = con.execute("""
            SELECT * FROM rm_user_permissions ORDER BY role
        """)
        rows = cursor.fetchall()
        con.close()
        
        if not rows:
            print(f"⚠️  BRAK UPRAWNIEŃ W BAZIE!")
            print(f"   Tabela rm_user_permissions jest pusta.")
            return False
        
        # Wyświetl uprawnienia
        print(f"\n📊 Uprawnienia w bazie: {db_path}\n")
        print(f"{'Rola':<10} | Start | End | Edit | Sync | Crit | Manage")
        print("-" * 70)
        
        for row in rows:
            print(f"{row['role']:<10} | "
                  f"{'✓' if row['can_start_stage'] else '✗':^5} | "
                  f"{'✓' if row['can_end_stage'] else '✗':^3} | "
                  f"{'✓' if row['can_edit_dates'] else '✗':^4} | "
                  f"{'✓' if row['can_sync_master'] else '✗':^4} | "
                  f"{'✓' if row['can_critical_path'] else '✗':^4} | "
                  f"{'✓' if row['can_manage_permissions'] else '✗':^6}")
        
        print("\n")
        
        # Sprawdź czy ADMIN ma wszystkie uprawnienia
        cursor = con.execute("SELECT * FROM rm_user_permissions WHERE role = 'ADMIN'")
        con = sqlite3.connect(db_path, timeout=10.0)
        con.row_factory = sqlite3.Row
        admin_row = con.execute("SELECT * FROM rm_user_permissions WHERE role = 'ADMIN'").fetchone()
        con.close()
        
        if admin_row:
            missing = []
            for perm in ['can_start_stage', 'can_end_stage', 'can_edit_dates', 
                        'can_sync_master', 'can_critical_path', 'can_manage_permissions']:
                if not admin_row[perm]:
                    missing.append(perm)
            
            if missing:
                print(f"⚠️  ADMIN ma brakujące uprawnienia: {', '.join(missing)}")
                return False
            else:
                print(f"✅ ADMIN ma wszystkie uprawnienia")
                return True
        else:
            print(f"❌ Brak roli ADMIN w bazie!")
            return False
            
    except Exception as e:
        print(f"❌ Błąd: {e}")
        return False


def fix_permissions(db_path):
    """Napraw uprawnienia - wstaw domyślne"""
    DEFAULT_ROLE_PERMISSIONS = [
        # role,       start, end, edit_dates, sync, critical_path, manage_permissions
        ('ADMIN',     1,     1,   1,          1,    1,             1),
        ('USER$$',    1,     1,   1,          1,    1,             0),
        ('USER$',     1,     1,   1,          0,    1,             0),
        ('USER',      1,     1,   0,          0,    0,             0),
        ('GUEST',     0,     0,   0,          0,    0,             0),
    ]
    
    try:
        con = sqlite3.connect(db_path, timeout=10.0)
        
        # Usuń stare uprawnienia
        con.execute("DELETE FROM rm_user_permissions")
        
        # Wstaw nowe
        con.executemany("""
            INSERT INTO rm_user_permissions
                (role, can_start_stage, can_end_stage, can_edit_dates,
                 can_sync_master, can_critical_path, can_manage_permissions)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, DEFAULT_ROLE_PERMISSIONS)
        
        con.commit()
        con.close()
        
        print(f"✅ Uprawnienia zostały naprawione!")
        return True
        
    except Exception as e:
        print(f"❌ Błąd naprawiania uprawnień: {e}")
        return False


if __name__ == "__main__":
    # Użyj podanej ścieżki lub domyślnej
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RM_MANAGER_DB
    
    print(f"🔍 Sprawdzam uprawnienia w: {db_path}\n")
    
    result = check_permissions(db_path)
    
    if not result:
        print(f"\n⚠️  Wykryto problem!")
        response = input(f"\nCzy naprawić uprawnienia? (tak/nie): ").strip().lower()
        if response in ['tak', 't', 'y', 'yes']:
            if fix_permissions(db_path):
                print(f"\n✅ Uprawnienia naprawione. Sprawdzam ponownie...\n")
                check_permissions(db_path)
