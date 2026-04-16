#!/usr/bin/env python3
"""
Test konfiguracji JSON dla RM_MANAGER
Sprawdza czy ścieżki są wczytywane poprawnie
"""

import json
import os
import sys

# Ścieżka do config (jak w rm_manager_gui.py)
CONFIG_FILE_PATH = r"C:\RMPAK_CLIENT\manager_sync_config.json"
# Dla cross-platform testing
if sys.platform != 'win32':
    CONFIG_FILE_PATH = "./manager_sync_config.json"

print("=" * 80)
print("TEST KONFIGURACJI JSON - RM_MANAGER")
print("=" * 80)
print()

# Test 1: Sprawdź czy plik istnieje
print(f"📂 Sprawdzam plik: {CONFIG_FILE_PATH}")
if os.path.exists(CONFIG_FILE_PATH):
    print(f"✅ Plik istnieje")
else:
    print(f"❌ Plik NIE istnieje - GUI utworzy go automatycznie przy starcie")
    print()
    print("💡 Aby przetestować, skopiuj manager_sync_config.json do:")
    if sys.platform == 'win32':
        print("   C:\\RMPAK_CLIENT\\manager_sync_config.json")
    else:
        print("   ./manager_sync_config.json (katalog roboczy)")
    sys.exit(1)

print()

# Test 2: Wczytaj JSON
print("📖 Wczytuję konfigurację...")
try:
    with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    print("✅ JSON poprawnie wczytany")
except json.JSONDecodeError as e:
    print(f"❌ BŁĄD składni JSON: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ BŁĄD wczytywania: {e}")
    sys.exit(1)

print()

# Test 3: Sprawdź strukturę
print("🔍 Sprawdzam strukturę...")
required_keys = ['master_db_path', 'rm_db_path']
for key in required_keys:
    if key in config:
        value = config[key]
        print(f"✅ {key}: {value}")
    else:
        print(f"❌ Brak klucza: {key}")

print()

# Test 4: Sprawdź ścieżki
print("🔍 Sprawdzam czy pliki istnieją...")
master_path = config.get('master_db_path', '')
rm_path = config.get('rm_db_path', '')

# Master DB
if master_path:
    if os.path.exists(master_path):
        print(f"✅ master.sqlite: {master_path}")
        # Sprawdź rozmiar
        size = os.path.getsize(master_path)
        print(f"   Rozmiar: {size:,} bajtów ({size / 1024:.1f} KB)")
    else:
        print(f"⚠️ master.sqlite NIE istnieje: {master_path}")
        print(f"   GUI zapyta o lokalizację przy starcie")
else:
    print(f"❌ Brak ścieżki master_db_path")

print()

# RM Manager DB
if rm_path:
    if os.path.exists(rm_path):
        print(f"✅ rm_manager.sqlite: {rm_path}")
        size = os.path.getsize(rm_path)
        print(f"   Rozmiar: {size:,} bajtów ({size / 1024:.1f} KB)")
    else:
        print(f"⚠️ rm_manager.sqlite NIE istnieje: {rm_path}")
        print(f"   Zostanie utworzony automatycznie przez GUI")
else:
    print(f"❌ Brak ścieżki rm_db_path")

print()

# Test 5: Testowe połączenie z master.sqlite
if master_path and os.path.exists(master_path):
    print("🔌 Testuję połączenie z master.sqlite...")
    try:
        import sqlite3
        con = sqlite3.connect(master_path, timeout=5.0)
        cursor = con.execute("SELECT COUNT(*) FROM projects WHERE COALESCE(is_active, 1) = 1")
        count = cursor.fetchone()[0]
        con.close()
        print(f"✅ Połączenie OK - znaleziono {count} aktywnych projektów")
    except sqlite3.Error as e:
        print(f"❌ BŁĄD połączenia: {e}")
    except Exception as e:
        print(f"⚠️ Problem: {e}")

print()
print("=" * 80)
print("TEST ZAKOŃCZONY")
print("=" * 80)
print()

# Podsumowanie
print("📋 PODSUMOWANIE:")
print()
if os.path.exists(master_path):
    print("✅ Wszystko gotowe do uruchomienia GUI!")
    print()
    print("   Następny krok:")
    print("   python rm_manager_gui.py")
else:
    print("⚠️ Skonfiguruj ścieżkę do master.sqlite:")
    print()
    print("   Opcja 1: Edytuj JSON ręcznie")
    print("   Opcja 2: Uruchom GUI i wybierz plik")
    print()
    print("   python rm_manager_gui.py")
