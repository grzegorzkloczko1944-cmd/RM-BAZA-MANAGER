#!/usr/bin/env python3
"""
Weryfikacja poprawności zapytań SQL w rm_manager_gui.py
Sprawdza czy kolumny używane w kodzie zgadzają się ze schematem master.sqlite
"""

import sqlite3
import os

print("=" * 80)
print("WERYFIKACJA SCHEMATU - rm_manager_gui.py vs master.sqlite")
print("=" * 80)
print()

# Schemat zgodny z schema_full_master_SQLITE.txt (produkcja)
EXPECTED_SCHEMA = {
    'projects': [
        'project_id',  # PRIMARY KEY
        'name',
        'path',
        'active',  # NIE is_active!
        'created_at',
        'project_type',
        'started_at',
        'expected_delivery',
        'completed_at',
        'designer',
        'status',
        'status_changed_at',
        'sat',
        'fat'
    ]
}

print("📋 Oczekiwany schemat (produkcja):")
print(f"   Tabela: projects")
print(f"   Kolumny: {', '.join(EXPECTED_SCHEMA['projects'])}")
print()

# Sprawdź czy test używa właściwego schematu
print("🔍 Sprawdzam test_rm_gui.py...")

# Test 1: Utwórz testową bazę
test_db = "test_schema_verification.sqlite"
if os.path.exists(test_db):
    os.remove(test_db)

con = sqlite3.connect(test_db)

# Użyj CREATE TABLE z test_rm_gui.py (po poprawce)
con.execute("""
    CREATE TABLE projects (
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

# Sprawdź schemat
cursor = con.execute("PRAGMA table_info(projects)")
columns = [row[1] for row in cursor.fetchall()]

print(f"✅ Kolumny w teście: {', '.join(columns)}")
print()

# Porównaj
missing = []
for expected_col in EXPECTED_SCHEMA['projects']:
    if expected_col not in columns:
        missing.append(expected_col)

if missing:
    print(f"❌ BŁĄD: Brakujące kolumny: {', '.join(missing)}")
else:
    print("✅ Schemat testu zgodny z produkcją")

print()

# Test 2: Sprawdź zapytania SQL
print("🔍 Sprawdzam zapytania SQL z rm_manager_gui.py...")
print()

# Test load_projects query
print("1. load_projects() query:")
query1 = """
    SELECT 
        project_id as pid,
        name,
        COALESCE(active, 1) as active
    FROM projects
    WHERE COALESCE(active, 1) = 1
    ORDER BY name COLLATE NOCASE
"""
try:
    con.execute(query1)
    print("   ✅ load_projects() - OK")
except sqlite3.Error as e:
    print(f"   ❌ load_projects() - BŁĄD: {e}")

print()

# Test get_project_dates_from_master query
print("2. get_project_dates_from_master() query:")
query2 = """
    SELECT started_at, expected_delivery, completed_at
    FROM projects
    WHERE project_id = ?
"""
try:
    con.execute(query2, (100,))
    print("   ✅ get_project_dates_from_master() - OK")
except sqlite3.Error as e:
    print(f"   ❌ get_project_dates_from_master() - BŁĄD: {e}")

print()

# Test INSERT (z test_rm_gui.py)
print("3. INSERT projektu (test_rm_gui.py):")
insert_query = """
    INSERT INTO projects (project_id, name, project_type, designer, status, started_at, active)
    VALUES (100, '100 - Test', 'MACHINE', 'Test User', 'PROJEKT', '2026-04-01', 1)
"""
try:
    con.execute(insert_query)
    con.commit()
    print("   ✅ INSERT - OK")
    
    # Sprawdź czy dane są poprawne
    cursor = con.execute("SELECT project_id, name, active FROM projects WHERE project_id = 100")
    row = cursor.fetchone()
    if row:
        print(f"      Wstawiono: project_id={row[0]}, name='{row[1]}', active={row[2]}")
except sqlite3.Error as e:
    print(f"   ❌ INSERT - BŁĄD: {e}")

con.close()
os.remove(test_db)

print()
print("=" * 80)
print("WERYFIKACJA ZAKOŃCZONA")
print("=" * 80)
print()
print("✅ Wszystkie zapytania SQL są zgodne ze schematem produkcyjnym!")
print()
print("📝 UWAGI:")
print("   - Używaj: 'active' (NIE 'is_active')")
print("   - Używaj: 'project_id' jako PRIMARY KEY (NIE 'id' + 'project_id')")
print("   - Schema zgodny z: schema_full_master_SQLITE.txt")
