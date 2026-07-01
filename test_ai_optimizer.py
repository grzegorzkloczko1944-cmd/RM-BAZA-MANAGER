"""test_ai_optimizer.py — Test wszystkich tools AIOptimizerContext bez GUI i bez Claude API.

Uruchomienie:
    python test_ai_optimizer.py

Wymagania:
    - rm_ai_optimizer.py w tym samym katalogu
    - działające bazy SQLite (ścieżki z config.json lub domyślne)
"""

import json
import os
import sys

# Wczytaj ścieżki z config jeśli istnieje
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_MASTER_DB  = r"C:\RMPAK_CLIENT\RM_BAZY\RM_BAZA\master.sqlite"
DEFAULT_RM_DIR     = r"C:\RMPAK_CLIENT\RM_BAZY\RM_MANAGER\RM_MANAGER_projects"
DEFAULT_RM_MASTER  = r"C:\RMPAK_CLIENT\RM_BAZY\RM_MANAGER\rm_manager.sqlite"

master_db  = DEFAULT_MASTER_DB
rm_dir     = DEFAULT_RM_DIR
rm_master  = DEFAULT_RM_MASTER

if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        master_db = cfg.get("master_db_path", master_db)
        rm_dir    = cfg.get("rm_manager_dir", rm_dir)
        rm_master = cfg.get("rm_master_db_path", os.path.join(os.path.dirname(rm_dir), "rm_manager.sqlite"))
        print(f"[config] Wczytano z {CONFIG_FILE}")
    except Exception as e:
        print(f"[config] Błąd odczytu: {e}")

print(f"[config] master_db:  {master_db}  {'✅' if os.path.exists(master_db) else '❌ NIE ISTNIEJE'}")
print(f"[config] rm_dir:     {rm_dir}  {'✅' if os.path.exists(rm_dir) else '❌ NIE ISTNIEJE'}")
print(f"[config] rm_master:  {rm_master}  {'✅' if os.path.exists(rm_master) else '❌ NIE ISTNIEJE'}")
print()

import rm_ai_optimizer as ai

ctx = ai.AIOptimizerContext(
    master_db_path=master_db,
    rm_manager_dir=rm_dir,
    rm_master_db_path=rm_master,
)

# ---------------------------------------------------------------------------
PASS = 0
FAIL = 0

def test(name, fn, *args, **kwargs):
    global PASS, FAIL
    print(f"{'─'*60}")
    print(f"TEST: {name}")
    try:
        result = fn(*args, **kwargs)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:1200])
        PASS += 1
        print("  ✅ OK")
    except Exception as e:
        import traceback
        traceback.print_exc()
        FAIL += 1
        print(f"  ❌ BŁĄD: {e}")
    print()

# ---------------------------------------------------------------------------
# READ TOOLS
# ---------------------------------------------------------------------------

test("get_schedule_summary",
     ctx.get_schedule_summary)

result_list = {"projects": []}
try:
    result_list = ctx.get_projects_list(status_filter="active")
except Exception:
    pass

test("get_projects_list (active)",
     ctx.get_projects_list, status_filter="active")

test("get_projects_list (all)",
     ctx.get_projects_list, status_filter="all")

test("get_delays (min 1 dzień)",
     ctx.get_delays, min_delay_days=1)

test("get_worker_load (wszyscy)",
     ctx.get_worker_load)

# Pobierz projekt który ma etapy
projects = result_list.get("projects", [])
project_with_stages = None
for p in projects:
    try:
        r = ctx.get_project_stages(project_id=p["id"])
        if r.get("stages"):
            project_with_stages = p
            break
    except Exception:
        pass

if project_with_stages:
    test(f"get_project_stages (projekt id={project_with_stages['id']} {project_with_stages['name']})",
         ctx.get_project_stages, project_id=project_with_stages["id"])
else:
    print("⚠️  Żaden projekt nie ma etapów — pomijam test get_project_stages")

# ---------------------------------------------------------------------------
# WRITE TOOLS — tryb dry-run (propose → cancel)
# ---------------------------------------------------------------------------

import sqlite3
employee_id = None
emp_name = None
try:
    con = sqlite3.connect(rm_master)
    row = con.execute("SELECT id, name FROM employees WHERE is_active=1 LIMIT 1").fetchone()
    if row:
        employee_id, emp_name = row
        print(f"[test] Pracownik testowy: id={employee_id} name={emp_name}")
    con.close()
except Exception as e:
    print(f"⚠️  Nie można pobrać pracownika: {e}")

if project_with_stages and employee_id:
    pid = project_with_stages["id"]
    stage_code = None
    try:
        stages_result = ctx.get_project_stages(project_id=pid)
        stages = stages_result.get("stages", [])
        if stages:
            stage_code = stages[0]["stage_code"]
            print(f"[test] Projekt testowy: id={pid} {project_with_stages['name']}, etap: {stage_code}")
    except Exception:
        pass

    if stage_code:
        test("propose_changes (assign_worker dry-run)",
             ctx.propose_changes, changes=[{
                 "action": "assign_worker",
                 "project_id": pid,
                 "stage_code": stage_code,
                 "employee_id": employee_id,
                 "role": "support",
                 "description": f"[TEST DRY-RUN] Przypisz {emp_name} do {stage_code} proj {pid}",
             }])

        test("cancel_changes (dry-run — nic nie zapisano)",
             ctx.cancel_changes)

        # propose → commit → verify → cleanup
        print("─"*60)
        print("TEST: propose → commit → verify → cleanup")
        try:
            ctx.propose_changes(changes=[{
                "action": "assign_worker",
                "project_id": pid,
                "stage_code": stage_code,
                "employee_id": employee_id,
                "role": "support",
                "description": f"[TEST] assign {emp_name}",
            }])
            result_commit = ctx.commit_changes()
            print(f"  commit: {result_commit}")
            assert not result_commit.get("errors"), f"Błędy: {result_commit['errors']}"

            stages_after = ctx.get_project_stages(project_id=pid)
            stage_data = next((s for s in stages_after["stages"] if s["stage_code"] == stage_code), None)
            print(f"  workers po commit: {stage_data['workers'] if stage_data else '?'}")

            ctx.propose_changes(changes=[{
                "action": "remove_worker",
                "project_id": pid,
                "stage_code": stage_code,
                "employee_id": employee_id,
                "description": f"[TEST CLEANUP] usuń {emp_name}",
            }])
            result_cleanup = ctx.commit_changes()
            print(f"  cleanup: {result_cleanup}")

            PASS += 1
            print("  ✅ OK")
        except Exception as e:
            import traceback
            traceback.print_exc()
            FAIL += 1
            print(f"  ❌ BŁĄD: {e}")
        print()

    if stage_code:
        test("propose_changes (set_stage_dates dry-run)",
             ctx.propose_changes, changes=[{
                 "action": "set_stage_dates",
                 "project_id": pid,
                 "stage_code": stage_code,
                 "planned_start": "2099-01-01",
                 "planned_end": "2099-01-10",
                 "description": f"[TEST DRY-RUN] daty {stage_code} proj {pid}",
             }])
        test("cancel_changes (dry-run set_stage_dates)",
             ctx.cancel_changes)

# ---------------------------------------------------------------------------
print("="*60)
print(f"WYNIKI: ✅ {PASS} OK   ❌ {FAIL} BŁĘDÓW")
if FAIL:
    print("\n⚠️  Popraw błędy przed użyciem w aplikacji.")
    sys.exit(1)
else:
    print("\n🎉 Wszystkie testy przeszły.")
