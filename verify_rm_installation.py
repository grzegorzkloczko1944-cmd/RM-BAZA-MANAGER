#!/usr/bin/env python3
"""
Weryfikacja instalacji RM_MANAGER
Sprawdza czy wszystkie wymagane pliki są dostępne
"""

import os
import sys
from pathlib import Path

def check_installation():
    """Sprawdź instalację RM_MANAGER"""
    
    print("=" * 70)
    print("RM_MANAGER - Weryfikacja instalacji")
    print("=" * 70)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"\n📂 Katalog: {script_dir}\n")
    
    # Wymagane pliki
    required_files = {
        "rm_manager.py": "Główny moduł (WYMAGANY)",
    }
    
    # Opcjonalne pliki
    optional_files = {
        "rm_database_manager.py": "SMB connection manager (dla produkcji)",
        "rm_lock_manager.py": "Heartbeat locks (dla produkcji)",
        "test_rm_manager.py": "Test demonstracyjny",
        "RM_MANAGER_DEPLOY.md": "Instrukcja wdrożenia",
    }
    
    all_ok = True
    
    # Sprawdź wymagane
    print("📋 Pliki WYMAGANE:")
    for filename, description in required_files.items():
        filepath = os.path.join(script_dir, filename)
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            print(f"   ✅ {filename:30} ({size:6} B) - {description}")
        else:
            print(f"   ❌ {filename:30} BRAK! - {description}")
            all_ok = False
    
    # Sprawdź opcjonalne
    print("\n📋 Pliki OPCJONALNE:")
    for filename, description in optional_files.items():
        filepath = os.path.join(script_dir, filename)
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            print(f"   ✅ {filename:30} ({size:6} B) - {description}")
        else:
            print(f"   ⚠️  {filename:30} brak - {description}")
    
    # Test importu
    print("\n🔬 Test importu modułów:")
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    
    try:
        import rm_manager
        print("   ✅ import rm_manager - OK")
        
        # Sprawdź kluczowe funkcje
        required_funcs = [
            'ensure_rm_manager_tables',
            'init_project',
            'start_stage',
            'end_stage',
            'get_active_stages',
            'recalculate_forecast',
            'determine_display_status',
            'sync_to_master',
        ]
        
        missing = [f for f in required_funcs if not hasattr(rm_manager, f)]
        if missing:
            print(f"   ⚠️  Brakujące funkcje: {missing}")
        else:
            print(f"   ✅ Wszystkie {len(required_funcs)} funkcji dostępne")
            
    except ImportError as e:
        print(f"   ❌ import rm_manager - BŁĄD: {e}")
        all_ok = False
    
    # Test Python
    print(f"\n🐍 Python:")
    print(f"   Wersja: {sys.version}")
    print(f"   Executable: {sys.executable}")
    
    # Test SQLite3
    try:
        import sqlite3
        print(f"   ✅ sqlite3: {sqlite3.sqlite_version}")
    except ImportError:
        print("   ❌ sqlite3: BRAK!")
        all_ok = False
    
    # Test uprawnień do zapisu
    print("\n📝 Test uprawnień do zapisu:")
    test_file = os.path.join(script_dir, ".test_write_permission")
    try:
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        print(f"   ✅ Można zapisywać w katalogu: {script_dir}")
    except Exception as e:
        print(f"   ❌ Brak uprawnień do zapisu: {e}")
        all_ok = False
    
    # Podsumowanie
    print("\n" + "=" * 70)
    if all_ok:
        print("✅ INSTALACJA OK - Możesz uruchomić test_rm_manager.py")
        print("\n▶️  python test_rm_manager.py")
    else:
        print("❌ INSTALACJA NIEKOMPLETNA")
        print("\n📖 Sprawdź instrukcję: RM_MANAGER_DEPLOY.md")
        print("\n📦 Wymagane pliki do skopiowania:")
        for filename in required_files.keys():
            filepath = os.path.join(script_dir, filename)
            if not os.path.exists(filepath):
                print(f"   - {filename}")
    print("=" * 70)
    
    return all_ok


if __name__ == "__main__":
    try:
        ok = check_installation()
        sys.exit(0 if ok else 1)
    except Exception as e:
        print(f"\n❌ BŁĄD: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
