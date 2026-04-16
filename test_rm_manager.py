#!/usr/bin/env python3
"""
====================================================================
TEST - RM_MANAGER System
====================================================================
Demonstracja pełnej funkcjonalności systemu RM_MANAGER:
1. Inicjalizacja bazy
2. Utworzenie projektu z gratem zależności
3. Symulacja pracy (start/end etapów)
4. Multi-period tracking (powroty)
5. Forecast calculation (topological sort)
6. Critical path
7. Sync z MASTER.SQLITE (opcjonalnie)
====================================================================
"""

import os
import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Sprawdź czy rm_manager.py istnieje w tym samym katalogu
script_dir = os.path.dirname(os.path.abspath(__file__))
rm_manager_path = os.path.join(script_dir, "rm_manager.py")

if not os.path.exists(rm_manager_path):
    print("❌ BŁĄD: Nie znaleziono rm_manager.py!")
    print(f"   Szukano w: {script_dir}")
    print("\n📋 Wymagane pliki w tym samym katalogu:")
    print("   - rm_manager.py")
    print("   - test_rm_manager.py (ten plik)")
    print("\n💡 Upewnij się, że skopiowałeś wszystkie pliki:")
    print("   - rm_manager.py (1089 linii)")
    print("   - rm_database_manager.py (447 linii - opcjonalny dla testów)")
    print("   - rm_lock_manager.py (188 linii - opcjonalny dla testów)")
    sys.exit(1)

# Dodaj katalog skryptu do PYTHONPATH jeśli jeszcze nie ma
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

try:
    import rm_manager as rmm
except ImportError as e:
    print("❌ BŁĄD: Nie można zaimportować rm_manager!")
    print(f"   {e}")
    print(f"\n📂 Katalog skryptu: {script_dir}")
    print(f"📂 Python path: {sys.path[:3]}")
    print("\n💡 Sprawdź czy rm_manager.py jest poprawny i nie ma błędów składniowych.")
    sys.exit(1)


def test_basic_workflow():
    """Test podstawowego workflow"""
    
    print("=" * 80)
    print("TEST RM_MANAGER - Podstawowy workflow")
    print("=" * 80)
    
    # 1. Setup - użyj katalogu skryptu dla cross-platform compatibility
    script_dir = os.path.dirname(os.path.abspath(__file__))
    master_db_path = os.path.join(script_dir, "test_rm_master.sqlite")
    project_db_path = os.path.join(script_dir, "test_rm_project_12345.sqlite")
    
    # Usuń stare bazy
    for path in [master_db_path, project_db_path]:
        if os.path.exists(path):
            os.remove(path)
            print(f"   🗑️  Usunięto starą bazę: {os.path.basename(path)}")
    
    print("\n1️⃣  Inicjalizacja baz...")
    # Master baza (globalne tabele)
    rmm.ensure_rm_master_tables(master_db_path)
    # Per-projekt baza (tabele projektu)
    rmm.ensure_project_tables(project_db_path)
    db_path = project_db_path  # Użyj per-projekt bazy dla kompatybilności
    
    # 2. Utwórz projekt
    print("\n2️⃣  Tworzenie projektu 12345...")
    
    stages_config = [
        {"code": "PRZYJETY", "template_start": "2026-01-01", "template_end": "2026-01-02", "sequence": 1},
        {"code": "PROJEKT", "template_start": "2026-01-02", "template_end": "2026-01-10", "sequence": 2},
        {"code": "AUTOMATYKA_PROJEKT", "template_start": "2026-01-10", "template_end": "2026-01-15", "sequence": 3},
        {"code": "KOMPLETACJA", "template_start": "2026-01-10", "template_end": "2026-01-15", "sequence": 4},
        {"code": "MONTAZ", "template_start": "2026-01-15", "template_end": "2026-01-25", "sequence": 5},
        {"code": "AUTOMATYKA_ELEKTROMONTAZ", "template_start": "2026-01-20", "template_end": "2026-01-28", "sequence": 6},
        {"code": "AUTOMATYKA_PROGRAMOWANIE", "template_start": "2026-01-20", "template_end": "2026-01-28", "sequence": 7},
        {"code": "URUCHOMIENIE", "template_start": "2026-01-28", "template_end": "2026-02-05", "sequence": 8},
        {"code": "ODBIORY", "template_start": "2026-02-05", "template_end": "2026-02-10", "sequence": 9},
    ]
    
    dependencies_config = [
        {"from": "PRZYJETY", "to": "PROJEKT", "type": "FS", "lag": 0},
        {"from": "PROJEKT", "to": "AUTOMATYKA_PROJEKT", "type": "FS", "lag": 0},
        {"from": "PROJEKT", "to": "KOMPLETACJA", "type": "FS", "lag": 0},
        {"from": "KOMPLETACJA", "to": "MONTAZ", "type": "FS", "lag": 0},
        {"from": "MONTAZ", "to": "AUTOMATYKA_ELEKTROMONTAZ", "type": "SS", "lag": 5},  # SS z opóźnieniem 5 dni
        {"from": "MONTAZ", "to": "AUTOMATYKA_PROGRAMOWANIE", "type": "SS", "lag": 5},
        {"from": "AUTOMATYKA_ELEKTROMONTAZ", "to": "URUCHOMIENIE", "type": "FS", "lag": 0},
        {"from": "AUTOMATYKA_PROGRAMOWANIE", "to": "URUCHOMIENIE", "type": "FS", "lag": 0},
        {"from": "URUCHOMIENIE", "to": "ODBIORY", "type": "FS", "lag": 0},
    ]
    
    rmm.init_project(db_path, 12345, stages_config, dependencies_config)
    
    # 3. Rozpocznij etapy
    print("\n3️⃣  Symulacja pracy nad projektem...")
    
    print("\n   🟢 START: PRZYJETY")
    rmm.start_stage(db_path, 12345, "PRZYJETY", started_by="Jan Kowalski")
    
    print("   🟢 START: PROJEKT")
    rmm.start_stage(db_path, 12345, "PROJEKT", started_by="Maria Nowak")
    
    # Sprawdź aktywne
    active = rmm.get_active_stages(db_path, 12345)
    print(f"\n   📊 Aktywne etapy: {[s['stage_code'] for s in active]}")
    
    # Zakończ PRZYJETY
    print("\n   🔴 END: PRZYJETY")
    rmm.end_stage(db_path, 12345, "PRZYJETY", ended_by="Jan Kowalski", notes="Kontrakt podpisany")
    
    active = rmm.get_active_stages(db_path, 12345)
    print(f"   📊 Aktywne etapy: {[s['stage_code'] for s in active]}")
    
    # 4. Forecast
    print("\n4️⃣  Obliczanie forecast...")
    forecast = rmm.recalculate_forecast(db_path, 12345)
    
    print("\n   📅 Timeline:")
    for code, fc in forecast.items():
        status_icon = "🟢" if fc['is_active'] else "⏺️"
        actual_icon = "✔️" if fc['is_actual'] else "📋"
        variance = fc.get('variance_days', 0)
        variance_str = f"+{variance}" if variance > 0 else str(variance)
        
        print(f"   {status_icon} {actual_icon} {code:15} | "
              f"Template: {fc.get('template_start', 'N/A')} → {fc.get('template_end', 'N/A')} | "
              f"Forecast: {fc.get('forecast_start', 'N/A')} → {fc.get('forecast_end', 'N/A')} | "
              f"Variance: {variance_str} dni")
    
    # 5. Zakończ PROJEKT
    print("\n   🔴 END: PROJEKT")
    rmm.end_stage(db_path, 12345, "PROJEKT", ended_by="Maria Nowak")
    
    # 6. Rozpocznij KOMPLETACJA i MONTAZ
    print("   🟢 START: KOMPLETACJA")
    rmm.start_stage(db_path, 12345, "KOMPLETACJA", started_by="Piotr Wiśniewski")
    
    print("   🟢 START: MONTAZ")
    rmm.start_stage(db_path, 12345, "MONTAZ", started_by="Adam Lewandowski")
    
    # 7. Zakończ i uruchom ponownie (MULTI-PERIOD!)
    print("\n5️⃣  Test multi-period (powroty)...")
    
    print("   🔴 END: MONTAZ (pierwsza próba)")
    rmm.end_stage(db_path, 12345, "MONTAZ", ended_by="Adam Lewandowski", notes="Wykryto problem")
    
    print("   🟢 START: MONTAZ (powrót!)")
    rmm.start_stage(db_path, 12345, "MONTAZ", started_by="Adam Lewandowski", notes="Poprawki po testach")
    
    periods = rmm.get_stage_periods(db_path, 12345, "MONTAZ")
    print(f"\n   📜 Historia MONTAZ: {len(periods)} okresów")
    for i, period in enumerate(periods, 1):
        status = "TRWA" if period['ended_at'] is None else "ZAKOŃCZONY"
        print(f"      #{i}: {period['started_at']} → {period['ended_at'] or 'TRWA'} ({status})")
    
    # 8. Status display
    print("\n6️⃣  Status dla RM_BAZA...")
    display_status = rmm.determine_display_status(db_path, 12345)
    print(f"   📺 Display status: {display_status}")
    
    active = rmm.get_active_stages(db_path, 12345)
    print(f"   📊 Aktywne: {[s['stage_code'] for s in active]}")
    
    # 9. Critical path
    print("\n7️⃣  Critical path analysis...")
    critical = rmm.calculate_critical_path(db_path, 12345)
    print(f"   🔥 Critical path: {critical}")
    
    # 10. Project summary
    print("\n8️⃣  Project summary...")
    summary = rmm.get_project_status_summary(db_path, 12345)
    print(f"   📊 Status: {summary['status']}")
    print(f"   📉 Variance: {summary['overall_variance_days']} dni")
    print(f"   📅 Completion forecast: {summary['completion_forecast']}")
    print(f"   🟢 Active: {summary['active_stages']}")
    
    # 11. Timeline dla GUI
    print("\n9️⃣  Timeline (dla Gantt chart)...")
    timeline = rmm.get_stage_timeline(db_path, 12345)
    print(f"   📊 {len(timeline)} etapów w timeline")
    
    print("\n" + "=" * 80)
    print("✅ TEST ZAKOŃCZONY")
    print("=" * 80)
    print(f"\n💾 Baza testowa: {db_path}")
    print("   Możesz sprawdzić dane przez sqlite3:")
    print(f"   $ sqlite3 \"{db_path}\"")
    print("   sqlite> SELECT * FROM stage_actual_periods;")
    
    return db_path  # Zwróć ścieżkę dla kolejnych testów


def test_sync_to_master(rm_db_path: str):
    """Test synchronizacji z master.sqlite (opcjonalny)"""
    
    print("\n" + "=" * 80)
    print("TEST SYNC - RM_MANAGER → MASTER.SQLITE")
    print("=" * 80)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    master_db = os.path.join(script_dir, "test_master.sqlite")
    
    # Utwórz dummy master.sqlite
    if os.path.exists(master_db):
        os.remove(master_db)
    
    con = sqlite3.connect(master_db)
    con.execute("""
        CREATE TABLE projects (
            project_id INTEGER PRIMARY KEY,
            project_number TEXT,
            status TEXT,
            updated_at DATETIME
        )
    """)
    con.execute("""
        CREATE TABLE project_statuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            status TEXT
        )
    """)
    con.execute("INSERT INTO projects (project_id, project_number, status) VALUES (12345, 'P-12345', 'PRZYJETY')")
    con.commit()
    con.close()
    
    print("\n1️⃣  Master.sqlite utworzony")
    
    # Sync
    print("\n2️⃣  Synchronizacja...")
    rmm.sync_to_master(rm_db_path, master_db, 12345)
    
    # Sprawdź wynik
    print("\n3️⃣  Sprawdzenie master.sqlite...")
    con = sqlite3.connect(master_db)
    con.row_factory = sqlite3.Row
    
    cursor = con.execute("SELECT * FROM projects WHERE project_id = 12345")
    project = dict(cursor.fetchone())
    print(f"   projects.status = {project['status']}")
    
    cursor = con.execute("SELECT status FROM project_statuses WHERE project_id = 12345")
    statuses = [row['status'] for row in cursor.fetchall()]
    print(f"   project_statuses = {statuses}")
    
    con.close()
    
    print("\n✅ SYNC TEST ZAKOŃCZONY")


def test_events(rm_db_path: str):
    """Test zdarzeń"""
    
    print("\n" + "=" * 80)
    print("TEST EVENTS - Historia zdarzeń")
    print("=" * 80)
    
    print("\n1️⃣  Dodawanie zdarzeń...")
    rmm.add_stage_event(rm_db_path, 12345, "MONTAZ", "DELAY", "Brak materiałów z Chin", created_by="Adam")
    rmm.add_stage_event(rm_db_path, 12345, "MONTAZ", "INFO", "Materiały dotarły", created_by="Adam")
    rmm.add_stage_event(rm_db_path, 12345, "KOMPLETACJA", "ISSUE", "Błąd w dokumentacji", created_by="Piotr")
    
    print("\n2️⃣  Historia MONTAZ...")
    events = rmm.get_stage_events(rm_db_path, 12345, "MONTAZ")
    for event in events:
        print(f"   [{event['event_date']}] {event['event_type']}: {event['description']} (by {event['created_by']})")
    
    print("\n3️⃣  Wszystkie zdarzenia projektu 12345...")
    all_events = rmm.get_stage_events(rm_db_path, 12345)
    print(f"   📊 Łącznie: {len(all_events)} zdarzeń")
    
    print("\n✅ EVENTS TEST ZAKOŃCZONY")


if __name__ == "__main__":
    # Test 1: Podstawowy workflow
    db_path = test_basic_workflow()
    
    # Test 2: Synchronizacja (opcjonalnie)
    test_sync_to_master(db_path)
    
    # Test 3: Zdarzenia
    test_events(db_path)
    
    print("\n" + "🎉" * 40)
    print("WSZYSTKIE TESTY ZAKOŃCZONE")
    print("🎉" * 40)
    print(f"\n💾 Pliki testowe w katalogu: {os.path.dirname(os.path.abspath(__file__))}")
    print("   - test_rm_manager.sqlite")
    print("   - test_master.sqlite")
