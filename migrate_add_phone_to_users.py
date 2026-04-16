#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migracja: Dodaj pole 'phone' do tabeli employees w rm_manager.sqlite
Potrzebne dla funkcji SMS (SMSAPI.pl)
Odbiorcy SMS = pracownicy z listy pracowników, nie użytkownicy systemu!
"""

import sqlite3
import sys
import os

def add_phone_column(rm_db_path: str):
    """Dodaj kolumnę phone do tabeli employees jeśli nie istnieje."""
    
    if not os.path.exists(rm_db_path):
        print(f"❌ Błąd: Nie znaleziono bazy {rm_db_path}")
        return False
    
    con = sqlite3.connect(rm_db_path, timeout=10.0)
    con.row_factory = sqlite3.Row
    
    try:
        # Sprawdź czy kolumna już istnieje
        cursor = con.execute("PRAGMA table_info(employees)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'phone' in columns:
            print("✅ Kolumna 'phone' już istnieje w tabeli employees")
            return True
        
        # Dodaj kolumnę
        print("📝 Dodaję kolumnę 'phone' do tabeli employees...")
        con.execute("""
            ALTER TABLE employees
            ADD COLUMN phone TEXT
        """)
        
        con.commit()
        print("✅ Kolumna 'phone' dodana pomyślnie!")
        
        # Weryfikacja
        cursor = con.execute("PRAGMA table_info(employees)")
        columns_after = [row[1] for row in cursor.fetchall()]
        
        if 'phone' in columns_after:
            print("✅ Weryfikacja OK - kolumna istnieje")
            return True
        else:
            print("❌ Weryfikacja FAILED - kolumna nie została dodana")
            return False
        
    except Exception as e:
        print(f"❌ Błąd migracji: {e}")
        con.rollback()
        return False
    finally:
        con.close()


def main():
    print("=" * 70)
    print("  Migracja: Dodaj pole 'phone' do tabeli employees")
    print("=" * 70)
    
    # Domyślna ścieżka
    default_path = "Y:/RM_MANAGER/rm_manager.sqlite"
    
    if len(sys.argv) > 1:
        rm_db_path = sys.argv[1]
    else:
        rm_db_path = input(f"\nŚcieżka do rm_manager.sqlite [{default_path}]: ").strip()
        if not rm_db_path:
            rm_db_path = default_path
    
    print(f"\n📂 Baza: {rm_db_path}")
    
    if not os.path.exists(rm_db_path):
        print(f"\n❌ Plik nie istnieje: {rm_db_path}")
        sys.exit(1)
    
    # Backup (opcjonalnie)
    response = input("\n⚠️  Wykonać backup przed migracją? [T/n]: ").strip().lower()
    if response != 'n':
        import shutil
        from datetime import datetime
        backup_path = rm_db_path + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"📋 Tworzę backup: {backup_path}")
        try:
            shutil.copy2(rm_db_path, backup_path)
            print("✅ Backup utworzony")
        except Exception as e:
            print(f"❌ Błąd backupu: {e}")
            if input("Kontynuować mimo błędu? [t/N]: ").strip().lower() != 't':
                sys.exit(1)
    
    # Migracja
    print("\n🚀 Uruchamiam migrację...")
    success = add_phone_column(rm_db_path)
    
    if success:
        print("\n" + "=" * 70)
        print("  ✅ MIGRACJA ZAKOŃCZONA POMYŚLNIE")
        print("=" * 70)
        print("\nKolumna 'phone' została dodana do tabeli employees.")
        print("Możesz teraz używać funkcji SMS w RM_MANAGER.")
        print("\nAby dodać numer telefonu pracownika:")
        print("1. Uruchom RM_MANAGER")
        print("2. Menu → Listy → Pracownicy")
        print("3. Edytuj pracownika i dodaj telefon w formacie: 48123456789 (bez '+' i spacji)")
    else:
        print("\n" + "=" * 70)
        print("  ❌ MIGRACJA NIE POWIODŁA SIĘ")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Anulowano przez użytkownika.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Nieoczekiwany błąd: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
