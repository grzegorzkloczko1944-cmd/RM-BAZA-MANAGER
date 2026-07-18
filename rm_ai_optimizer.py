"""rm_ai_optimizer.py — AI Agent do analizy i optymalizacji harmonogramu.

Warstwa interpretacji nad rm_optimizer.py (OR-Tools CP-SAT).
Używa Claude API (tool use) do:
  - analizy stanu projektów (read-only)
  - wykrywania konfliktów i opóźnień
  - rekomendacji zmian (z potwierdzeniem użytkownika)

Kolejność wdrożenia (zgodnie z AI_OPTIMIZER_CONCEPT.md):
  1. Analiza stanu (read-only) — ten moduł, Krok 1
  2. Optymalizacja z AI jako "kierownikiem" — Krok 2 (TODO)
"""

from __future__ import annotations

import json
import sqlite3
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import anthropic

try:
    from rm_lock_manager import RMLockManager
    _LOCK_MANAGER_AVAILABLE = True
except ImportError:
    _LOCK_MANAGER_AVAILABLE = False

# ---------------------------------------------------------------------------
# Stałe
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

# Domyślna lokalizacja pliku reguł — obok tego modułu
_DEFAULT_RULES_FILE = Path(__file__).parent / "ai_rules.txt"


def load_rules(rules_file: Optional[str] = None) -> str:
    """Wczytaj reguły z pliku tekstowego.

    Linie zaczynające się od # są komentarzami i są pomijane.
    Zwraca pusty string jeśli plik nie istnieje.
    """
    path = Path(rules_file) if rules_file else _DEFAULT_RULES_FILE
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        content = "\n".join(l for l in lines if not l.strip().startswith("#"))
        return content.strip()
    except Exception:
        return ""

SYSTEM_PROMPT = """Jesteś asystentem kierownika produkcji w firmie stolarskiej/produkcyjnej.
Masz dostęp do harmonogramu projektów zapisanego w bazie SQLite.
Odpowiadasz po polsku, zwięźle i konkretnie — jak doświadczony kierownik.

Twoje narzędzia pozwalają Ci odczytać:
- listę aktywnych projektów z datami i priorytetami
- stan etapów każdego projektu (plan vs rzeczywistość)
- opóźnienia i konflikty
- obciążenie pracowników

Umiesz też RYSOWAĆ WYKRESY graficzne narzędziem render_chart (Gantt / słupki).
Gdy użytkownik prosi o wykres, oś czasu lub graficzne obciążenie — użyj render_chart.
Wykres pojawi się automatycznie w oknie czatu. NIGDY nie mów, że nie umiesz rysować.

Twoje narzędzia pozwalają Ci też MODYFIKOWAĆ dane:
- assign_worker   — przypisz pracownika do etapu projektu
- remove_worker   — zdejmij pracownika z etapu
- set_stage_dates — ustaw daty planowane etapu

ZASADA ZATWIERDZANIA:
1. Gdy użytkownik poprosi o zmianę — najpierw wywołaj propose_changes() z listą zmian.
2. Pokaż użytkownikowi co zamierzasz zmienić i zapytaj o potwierdzenie.
3. Dopiero gdy użytkownik napisze "zatwierdź", "tak", "zrób", "ok" lub podobnie —
   wywołaj commit_changes() żeby zapisać do bazy.
4. Jeśli użytkownik napisze "anuluj" lub "nie" — wywołaj cancel_changes().

Nigdy nie wywołuj assign_worker/remove_worker/set_stage_dates bezpośrednio bez
wcześniejszego propose_changes() i potwierdzenia użytkownika.

Format dat: YYYY-MM-DD. Dzisiaj: {today}.
"""

# ---------------------------------------------------------------------------
# Narzędzia (tools) — definicje dla Claude API
# ---------------------------------------------------------------------------

TOOLS: List[Dict] = [
    {
        "name": "get_projects_list",
        "description": (
            "Pobierz listę projektów z master.sqlite. "
            "Zwraca ID, nazwę, priorytet, status, planowane daty zakończenia."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "description": "Filtr statusu: 'active', 'all', 'completed'. Domyślnie 'active'.",
                    "enum": ["active", "all", "completed"],
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_project_stages",
        "description": (
            "Pobierz szczegółowy stan etapów konkretnego projektu: "
            "daty planowane, rzeczywiste starty/końce, przypisanych pracowników, "
            "czy etap jest aktywny/zakończony/nie rozpoczęty."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "ID projektu z master.sqlite",
                }
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "get_delays",
        "description": (
            "Pobierz listę projektów/etapów z opóźnieniami. "
            "Porównuje daty planowane z rzeczywistymi startami i dzisiejszą datą. "
            "Zwraca projekty gdzie etapy powinny być już rozpoczęte lub zakończone a nie są."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "min_delay_days": {
                    "type": "integer",
                    "description": "Minimalna liczba dni opóźnienia do zgłoszenia (domyślnie 1).",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_worker_load",
        "description": (
            "Pobierz obciążenie pracowników: które etapy są do nich przypisane, "
            "w jakim okresie, czy etap jest aktywny. "
            "Pomaga wykryć przeciążonych pracowników i konflikty zasobów."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "worker_name": {
                    "type": "string",
                    "description": "Imię i nazwisko pracownika (opcjonalne — brak = wszyscy aktywni).",
                },
                "date_from": {
                    "type": "string",
                    "description": "Data początkowa zakresu YYYY-MM-DD (opcjonalna).",
                },
                "date_to": {
                    "type": "string",
                    "description": "Data końcowa zakresu YYYY-MM-DD (opcjonalna).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_schedule_summary",
        "description": (
            "Pobierz skrótowe podsumowanie harmonogramu: "
            "ile projektów aktywnych, ile z opóźnieniami, "
            "najbliższe terminy zakończenia, projekty VIP/priorytetowe."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "render_chart",
        "description": (
            "Narysuj wykres graficzny (PNG) i pokaż go użytkownikowi w oknie czatu. "
            "Używaj gdy użytkownik prosi o wykres, Gantt, oś czasu, obciążenie w formie graficznej. "
            "Typy: 'gantt' (oś czasu zadań — idealne dla obciążenia pracownika lub etapów projektu) "
            "oraz 'bar' (słupki — np. liczba przypisań na pracownika, opóźnienia w dniach). "
            "Dla 'gantt' każdy element to zadanie z datami start/end (YYYY-MM-DD) i etykietą. "
            "Dla 'bar' każdy element to słupek z etykietą i wartością liczbową. "
            "Po wywołaniu wykres pojawia się automatycznie w czacie — w odpowiedzi tekstowej "
            "krótko go skomentuj, NIE opisuj że nie umiesz rysować."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["gantt", "bar"],
                    "description": "Typ wykresu: 'gantt' (oś czasu) lub 'bar' (słupki).",
                },
                "title": {
                    "type": "string",
                    "description": "Tytuł wykresu (po polsku).",
                },
                "items": {
                    "type": "array",
                    "description": (
                        "Dane wykresu. Dla 'gantt': obiekty z 'label', 'start', 'end' "
                        "(daty YYYY-MM-DD) i opcjonalnie 'color' ('red'/'orange'/'green'/'blue' "
                        "— użyj 'red' dla opóźnionych). Dla 'bar': obiekty z 'label' i 'value'."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "Etykieta zadania/słupka."},
                            "start": {"type": "string", "description": "Data startu YYYY-MM-DD (gantt)."},
                            "end": {"type": "string", "description": "Data końca YYYY-MM-DD (gantt)."},
                            "value": {"type": "number", "description": "Wartość liczbowa (bar)."},
                            "color": {
                                "type": "string",
                                "description": "Kolor: red/orange/green/blue (opcjonalny).",
                            },
                        },
                        "required": ["label"],
                    },
                },
            },
            "required": ["chart_type", "title", "items"],
        },
    },
    {
        "name": "propose_changes",
        "description": (
            "Zaproponuj zmiany do zatwierdzenia przez użytkownika. "
            "Wywołaj PRZED każdą modyfikacją bazy. "
            "Zwraca sformatowaną listę zmian gotową do pokazania użytkownikowi."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "changes": {
                    "type": "array",
                    "description": "Lista zmian do zatwierdzenia.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["assign_worker", "remove_worker", "set_stage_dates"],
                                "description": "Typ operacji.",
                            },
                            "project_id": {"type": "integer"},
                            "stage_code": {"type": "string"},
                            "employee_id": {
                                "type": "integer",
                                "description": "ID pracownika (dla assign/remove).",
                            },
                            "role": {
                                "type": "string",
                                "description": "Rola pracownika: 'master' lub 'support'.",
                                "enum": ["master", "support"],
                            },
                            "planned_start": {
                                "type": "string",
                                "description": "Data startu YYYY-MM-DD (dla set_stage_dates).",
                            },
                            "planned_end": {
                                "type": "string",
                                "description": "Data końca YYYY-MM-DD (dla set_stage_dates).",
                            },
                            "description": {
                                "type": "string",
                                "description": "Opis zmiany po polsku dla użytkownika.",
                            },
                        },
                        "required": ["action", "project_id", "stage_code", "description"],
                    },
                }
            },
            "required": ["changes"],
        },
    },
    {
        "name": "commit_changes",
        "description": (
            "Zatwierdź i zapisz do bazy zmiany zaproponowane przez propose_changes(). "
            "Wywołaj TYLKO gdy użytkownik potwierdził zmiany słowami: "
            "'zatwierdź', 'tak', 'zrób', 'ok', 'wykonaj' lub podobnymi."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "cancel_changes",
        "description": (
            "Anuluj zaproponowane zmiany bez zapisywania. "
            "Wywołaj gdy użytkownik odrzucił zmiany."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

# ---------------------------------------------------------------------------
# Klasa kontekstu — ścieżki do baz
# ---------------------------------------------------------------------------


class AIOptimizerContext:
    """Przechowuje ścieżki do baz i eksponuje je narzędziom agenta."""

    def __init__(
        self,
        master_db_path: str,
        rm_manager_dir: str,
        rm_master_db_path: str,
        locks_dir: Optional[str] = None,
        current_user: str = "AI",
        rules_file: Optional[str] = None,
    ):
        self.master_db_path = master_db_path          # master.sqlite (projekty)
        self.rm_manager_dir = rm_manager_dir          # katalog z bazami per-projekt
        self.rm_master_db_path = rm_master_db_path    # rm_manager.sqlite (pracownicy)
        # ai_rules.txt — wspólny plik reguł dla wszystkich userów (konfigurowalny
        # w GUI: "Konfiguracja ścieżek" → "Plik kontekstu AI"). Gdy nie podano
        # jawnie, spadamy na rm_manager_dir/ai_rules.txt (dawny domyślny wzorzec).
        self.rules_file = rules_file or (str(Path(rm_manager_dir) / "ai_rules.txt") if rm_manager_dir else None)
        self.today = date.today().isoformat()
        # Bufor zmian czekających na zatwierdzenie przez użytkownika
        self._pending_changes: List[Dict] = []
        # Ścieżki do wykresów PNG wygenerowanych w bieżącej turze (GUI je odczytuje
        # po session.send() i osadza w oknie czatu). Czyszczone na starcie każdej tury.
        self.chart_paths: List[str] = []

        # Lock manager — opcjonalny, ale zalecany przy wielu użytkownikach
        self._lock_manager = None
        if _LOCK_MANAGER_AVAILABLE and locks_dir:
            try:
                self._lock_manager = RMLockManager(
                    locks_folder=Path(locks_dir),
                    stale_seconds=60,   # AI trzyma lock max 60s — krótko, bo nie ma heartbeatu
                )
                self._lock_manager.my_name = current_user
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pomocnicze
    # ------------------------------------------------------------------

    def _open(self, path: str) -> sqlite3.Connection:
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        return con

    def _project_db(self, project_id: int) -> Optional[str]:
        """Zwróć ścieżkę do bazy projektu lub None jeśli nie istnieje.

        RM_MANAGER używa konwencji: rm_manager_project_{pid}.sqlite.
        Szuka w rm_manager_dir oraz w podkatalogu RM_MANAGER_projects.
        """
        base = Path(self.rm_manager_dir)
        fname = f"rm_manager_project_{project_id}.sqlite"
        candidates = [
            base / fname,
            base / "RM_MANAGER_projects" / fname,
            base.parent / "RM_MANAGER_projects" / fname,
            base / str(project_id) / "rm_manager.sqlite",
            base / f"project_{project_id}" / "rm_manager.sqlite",
            base / f"{project_id}.sqlite",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        return None

    # ------------------------------------------------------------------
    # Implementacje narzędzi
    # ------------------------------------------------------------------

    def get_projects_list(self, status_filter: str = "active") -> Dict:
        con = self._open(self.master_db_path)
        try:
            # master.sqlite (RM_BAZA): tabela projects, klucz project_id, flaga active (0/1)
            try:
                rows = con.execute(
                    "SELECT project_id, name, active, priority, expected_delivery, project_status"
                    " FROM projects ORDER BY priority, name"
                ).fetchall()
            except sqlite3.OperationalError:
                rows = con.execute(
                    "SELECT project_id, name, active FROM projects ORDER BY name"
                ).fetchall()

            projects = []
            for r in rows:
                row_dict = dict(r)
                # active: 1 = aktywny, 0 = zakończony/archiwalny
                active_flag = row_dict.get("active", 1)
                if status_filter == "active" and not active_flag:
                    continue
                if status_filter == "completed" and active_flag:
                    continue
                # Ujednolicamy klucz do "id" żeby reszta kodu działała
                row_dict["id"] = row_dict["project_id"]
                projects.append(row_dict)

            return {"projects": projects, "count": len(projects)}
        finally:
            con.close()

    def get_project_stages(self, project_id: int) -> Dict:
        # Pobierz nazwę projektu z master
        project_name = f"Projekt {project_id}"
        try:
            con = self._open(self.master_db_path)
            try:
                row = con.execute(
                    "SELECT name FROM projects WHERE project_id = ?", (project_id,)
                ).fetchone()
                if row:
                    project_name = row["name"]
            finally:
                con.close()
        except Exception:
            pass

        db_path = self._project_db(project_id)
        if not db_path:
            return {"error": f"Brak bazy danych dla projektu {project_id}"}

        con = self._open(db_path)
        try:
            try:
                rows = con.execute("""
                    SELECT ps.stage_code, ps.sequence,
                           ss.template_start, ss.template_end,
                           ps.assigned_staff
                    FROM project_stages ps
                    LEFT JOIN stage_schedule ss ON ss.project_stage_id = ps.id
                    WHERE ps.project_id = ?
                    ORDER BY ps.sequence
                """, (project_id,)).fetchall()
            except sqlite3.OperationalError as e:
                # Baza projektu istnieje, ale jest niekompletna (brak tabel stage_*).
                # Nie wysadzaj całej analizy — zgłoś jako błąd, get_delays to pominie.
                return {"error": f"Baza projektu {project_id} niekompletna: {e}"}

            # Rzeczywiste okresy
            try:
                actuals = con.execute("""
                    SELECT ps.stage_code, sap.started_at, sap.ended_at
                    FROM stage_actual_periods sap
                    JOIN project_stages ps ON sap.project_stage_id = ps.id
                    WHERE ps.project_id = ?
                """, (project_id,)).fetchall()
                actuals_map: Dict[str, Dict] = {}
                for a in actuals:
                    sc = a["stage_code"]
                    if a["ended_at"]:
                        actuals_map[sc] = {"actual_start": a["started_at"], "actual_end": a["ended_at"], "status": "zakończony"}
                    elif a["started_at"]:
                        actuals_map[sc] = {"actual_start": a["started_at"], "actual_end": None, "status": "aktywny"}
            except sqlite3.OperationalError:
                actuals_map = {}

            # Pracownicy
            try:
                staff_rows = con.execute("""
                    SELECT ps.stage_code, ssa.employee_id,
                           ssa.planned_start, ssa.planned_end
                    FROM stage_staff_assignments ssa
                    JOIN project_stages ps ON ssa.project_stage_id = ps.id
                    WHERE ps.project_id = ?
                """, (project_id,)).fetchall()
                staff_map: Dict[str, List] = {}
                for sr in staff_rows:
                    sc = sr["stage_code"]
                    staff_map.setdefault(sc, []).append(sr["employee_id"])
            except sqlite3.OperationalError:
                staff_map = {}

            # Nazwy pracowników
            employee_names: Dict[int, str] = {}
            try:
                rm_con = self._open(self.rm_master_db_path)
                try:
                    emp_rows = rm_con.execute(
                        "SELECT id, name FROM employees"
                    ).fetchall()
                    for e in emp_rows:
                        employee_names[e["id"]] = e["name"]
                finally:
                    rm_con.close()
            except Exception:
                pass

            stages = []
            today = date.today()
            for r in rows:
                sc = r["stage_code"]
                actual = actuals_map.get(sc, {})
                staff_ids = staff_map.get(sc, [])
                staff_names = [employee_names.get(eid, f"ID:{eid}") for eid in staff_ids]

                planned_end = r["template_end"]
                status = actual.get("status", "nie rozpoczęty")

                delay_days = None
                if status == "nie rozpoczęty" and r["template_start"]:
                    try:
                        planned_start_date = date.fromisoformat(r["template_start"][:10])
                        if planned_start_date < today:
                            delay_days = (today - planned_start_date).days
                    except ValueError:
                        pass

                stages.append({
                    "stage_code": sc,
                    "sequence": r["sequence"],
                    "planned_start": r["template_start"],
                    "planned_end": r["template_end"],
                    "status": status,
                    "actual_start": actual.get("actual_start"),
                    "actual_end": actual.get("actual_end"),
                    "workers": staff_names,
                    "delay_days": delay_days,
                })

            return {
                "project_id": project_id,
                "project_name": project_name,
                "stages": stages,
            }
        finally:
            con.close()

    def get_delays(self, min_delay_days: int = 1) -> Dict:
        # Pobierz listę aktywnych projektów
        projects_result = self.get_projects_list(status_filter="active")
        delayed = []
        today = date.today()

        for proj in projects_result["projects"]:
            pid = proj["id"]
            stages_result = self.get_project_stages(pid)
            if "error" in stages_result:
                continue

            project_delays = []
            for stage in stages_result["stages"]:
                if stage["delay_days"] and stage["delay_days"] >= min_delay_days:
                    project_delays.append({
                        "stage_code": stage["stage_code"],
                        "planned_start": stage["planned_start"],
                        "delay_days": stage["delay_days"],
                        "workers": stage["workers"],
                    })
                # Etap aktywny który powinien być skończony
                if stage["status"] == "aktywny" and stage["planned_end"]:
                    try:
                        planned_end_date = date.fromisoformat(stage["planned_end"][:10])
                        if planned_end_date < today:
                            overrun = (today - planned_end_date).days
                            if overrun >= min_delay_days:
                                project_delays.append({
                                    "stage_code": stage["stage_code"],
                                    "issue": "przekroczenie planowanego końca etapu",
                                    "planned_end": stage["planned_end"],
                                    "overrun_days": overrun,
                                    "workers": stage["workers"],
                                })
                    except ValueError:
                        pass

            if project_delays:
                delayed.append({
                    "project_id": pid,
                    "project_name": proj.get("name", f"Projekt {pid}"),
                    "priority": proj.get("priority", 3),
                    "delays": project_delays,
                })

        delayed.sort(key=lambda x: x.get("priority", 3))
        return {
            "today": today.isoformat(),
            "delayed_projects": delayed,
            "count": len(delayed),
        }

    def get_worker_load(
        self,
        worker_name: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict:
        # Pobierz pracowników z rm_master_db
        try:
            rm_con = self._open(self.rm_master_db_path)
            try:
                emp_rows = rm_con.execute(
                    "SELECT id, name FROM employees WHERE is_active = 1"
                ).fetchall()
                employees = {
                    e["id"]: e["name"] for e in emp_rows
                }
            finally:
                rm_con.close()
        except Exception as ex:
            return {"error": f"Błąd odczytu pracowników: {ex}"}

        # Filtr po nazwisku
        target_ids = None
        if worker_name:
            wl = worker_name.lower()
            target_ids = {
                eid for eid, name in employees.items() if wl in name.lower()
            }
            if not target_ids:
                return {"error": f"Nie znaleziono pracownika: {worker_name}"}

        # Zbierz etapy z wszystkich projektów
        projects_result = self.get_projects_list(status_filter="active")
        worker_assignments: Dict[int, List] = {}

        for proj in projects_result["projects"]:
            pid = proj["id"]
            db_path = self._project_db(pid)
            if not db_path:
                continue

            con = self._open(db_path)
            try:
                try:
                    rows = con.execute("""
                        SELECT ps.stage_code, ssa.employee_id,
                               ssa.planned_start, ssa.planned_end
                        FROM stage_staff_assignments ssa
                        JOIN project_stages ps ON ssa.project_stage_id = ps.id
                        WHERE ps.project_id = ?
                    """, (pid,)).fetchall()
                except sqlite3.OperationalError:
                    continue

                for r in rows:
                    eid = r["employee_id"]
                    if target_ids and eid not in target_ids:
                        continue

                    # Filtr dat
                    ps = r["planned_start"]
                    pe = r["planned_end"]
                    if date_from and pe and pe[:10] < date_from:
                        continue
                    if date_to and ps and ps[:10] > date_to:
                        continue

                    worker_assignments.setdefault(eid, []).append({
                        "project_id": pid,
                        "project_name": proj.get("name", f"Projekt {pid}"),
                        "stage_code": r["stage_code"],
                        "planned_start": ps,
                        "planned_end": pe,
                    })
            finally:
                con.close()

        result = []
        for eid, assignments in worker_assignments.items():
            result.append({
                "employee_id": eid,
                "name": employees.get(eid, f"ID:{eid}"),
                "assignment_count": len(assignments),
                "assignments": assignments,
            })
        result.sort(key=lambda x: x["assignment_count"], reverse=True)

        return {
            "workers": result,
            "count": len(result),
            "date_from": date_from,
            "date_to": date_to,
        }

    def get_schedule_summary(self) -> Dict:
        today = date.today()
        projects_result = self.get_projects_list(status_filter="active")
        projects = projects_result["projects"]

        delayed_count = 0
        vip_projects = []
        ending_soon = []

        for proj in projects:
            pid = proj["id"]
            stages_result = self.get_project_stages(pid)
            if "error" in stages_result:
                continue

            has_delay = any(
                s["delay_days"] and s["delay_days"] > 0
                for s in stages_result["stages"]
            )
            if has_delay:
                delayed_count += 1

            if proj.get("priority", 3) == 1:
                vip_projects.append(proj.get("name", f"Projekt {pid}"))

            # Szukaj ostatniego etapu
            last_stage = None
            for s in reversed(stages_result["stages"]):
                if s["planned_end"]:
                    last_stage = s
                    break
            if last_stage and last_stage["planned_end"]:
                try:
                    end_date = date.fromisoformat(last_stage["planned_end"][:10])
                    days_left = (end_date - today).days
                    if 0 <= days_left <= 30:
                        ending_soon.append({
                            "project_name": proj.get("name", f"Projekt {pid}"),
                            "end_date": last_stage["planned_end"][:10],
                            "days_left": days_left,
                            "priority": proj.get("priority", 3),
                        })
                except ValueError:
                    pass

        ending_soon.sort(key=lambda x: x["days_left"])

        return {
            "today": today.isoformat(),
            "active_projects": len(projects),
            "delayed_projects": delayed_count,
            "vip_projects": vip_projects,
            "ending_within_30_days": ending_soon,
        }

    # ------------------------------------------------------------------
    # Narzędzia zapisu (write tools)
    # ------------------------------------------------------------------

    def propose_changes(self, changes: List[Dict]) -> Dict:
        """Buforuj zmiany i zwróć czytelny opis dla użytkownika."""
        self._pending_changes = changes
        lines = []
        for i, ch in enumerate(changes, 1):
            lines.append(f"{i}. {ch.get('description', str(ch))}")
        return {
            "status": "pending",
            "count": len(changes),
            "changes": lines,
            "message": "Czy zatwierdzić powyższe zmiany? Wpisz 'zatwierdź' lub 'anuluj'.",
        }

    def commit_changes(self) -> Dict:
        """Wykonaj wszystkie buforowane zmiany i zapisz do bazy.

        Dla każdego unikalnego projektu w zmianach:
        1. Acquire lock (jeśli lock manager dostępny)
        2. Wykonaj zapis
        3. Release lock
        Jeśli lock zajęty przez innego użytkownika — zwróć błąd bez zapisu.
        """
        if not self._pending_changes:
            return {"status": "error", "message": "Brak oczekujących zmian do zatwierdzenia."}

        # Zbierz unikalne project_id
        project_ids = list({ch["project_id"] for ch in self._pending_changes})

        # Acquire locki dla wszystkich projektów
        acquired: List[int] = []
        if self._lock_manager:
            for pid in project_ids:
                ok, _ = self._lock_manager.acquire_project_lock(pid)
                if ok:
                    acquired.append(pid)
                else:
                    # Nie udało się — zwolnij już przejęte i przerwij
                    for apid in acquired:
                        try:
                            self._lock_manager.release_project_lock(apid)
                        except Exception:
                            pass
                    owner = self._lock_manager.get_project_lock_owner(pid)
                    who = owner.get("user", "?") + "@" + owner.get("computer", "?") if owner else "inny użytkownik"
                    self._pending_changes = []
                    return {
                        "status": "locked",
                        "message": f"Projekt {pid} jest zablokowany przez {who}. Spróbuj za chwilę.",
                    }

        done = []
        errors = []
        try:
            for ch in self._pending_changes:
                try:
                    action = ch["action"]
                    pid = ch["project_id"]
                    stage = ch["stage_code"]
                    if action == "assign_worker":
                        self._assign_worker(pid, stage, ch["employee_id"], ch.get("role", "support"))
                        done.append(ch.get("description", action))
                    elif action == "remove_worker":
                        self._remove_worker(pid, stage, ch["employee_id"])
                        done.append(ch.get("description", action))
                    elif action == "set_stage_dates":
                        self._set_stage_dates(pid, stage, ch.get("planned_start"), ch.get("planned_end"))
                        done.append(ch.get("description", action))
                    else:
                        errors.append(f"Nieznana akcja: {action}")
                except Exception as ex:
                    errors.append(f"{ch.get('description', '?')}: {ex}")
        finally:
            # Zawsze zwolnij locki
            if self._lock_manager:
                for apid in acquired:
                    try:
                        self._lock_manager.release_project_lock(apid)
                    except Exception:
                        pass

        self._pending_changes = []
        return {
            "status": "done" if not errors else "partial",
            "saved": done,
            "errors": errors,
        }

    def cancel_changes(self) -> Dict:
        """Anuluj buforowane zmiany."""
        count = len(self._pending_changes)
        self._pending_changes = []
        return {"status": "cancelled", "message": f"Anulowano {count} zmian."}

    def _assign_worker(self, project_id: int, stage_code: str, employee_id: int, role: str) -> None:
        """Przypisz pracownika do etapu projektu.

        Zapisuje w obu miejscach:
        - stage_staff_assignments (nowy styl)
        - project_stages.assigned_staff JSON (legacy styl używany przez GUI)
        """
        db_path = self._project_db(project_id)
        if not db_path:
            raise ValueError(f"Brak bazy dla projektu {project_id}")
        con = sqlite3.connect(db_path)
        try:
            cur = con.cursor()
            row = cur.execute(
                "SELECT id, assigned_staff FROM project_stages WHERE project_id = ? AND stage_code = ?",
                (project_id, stage_code),
            ).fetchone()
            if not row:
                raise ValueError(f"Etap {stage_code} nie istnieje w projekcie {project_id}")
            ps_id, assigned_staff_json = row[0], row[1]

            # 1. stage_staff_assignments
            existing = cur.execute(
                "SELECT id FROM stage_staff_assignments WHERE project_stage_id = ? AND employee_id = ?",
                (ps_id, employee_id),
            ).fetchone()
            now = datetime.now().isoformat()
            if existing:
                cur.execute(
                    "UPDATE stage_staff_assignments SET role = ? WHERE id = ?",
                    (role, existing[0]),
                )
            else:
                cur.execute(
                    "INSERT INTO stage_staff_assignments (project_stage_id, employee_id, role, assigned_at)"
                    " VALUES (?, ?, ?, ?)",
                    (ps_id, employee_id, role, now),
                )

            # 2. project_stages.assigned_staff (JSON lista pracowników)
            try:
                staff_list = json.loads(assigned_staff_json) if assigned_staff_json else []
            except (json.JSONDecodeError, TypeError):
                staff_list = []
            # Usuń stary wpis tego pracownika jeśli istnieje, dodaj nowy
            staff_list = [e for e in staff_list if e.get("employee_id") != employee_id]
            staff_list.append({"employee_id": employee_id, "role": role, "assigned_at": now, "assigned_by": "AI"})
            cur.execute(
                "UPDATE project_stages SET assigned_staff = ? WHERE id = ?",
                (json.dumps(staff_list), ps_id),
            )
            con.commit()
        finally:
            con.close()

    def _remove_worker(self, project_id: int, stage_code: str, employee_id: int) -> None:
        """Zdejmij pracownika z etapu projektu.

        Usuwa z obu miejsc:
        - stage_staff_assignments
        - project_stages.assigned_staff JSON
        """
        db_path = self._project_db(project_id)
        if not db_path:
            raise ValueError(f"Brak bazy dla projektu {project_id}")
        con = sqlite3.connect(db_path)
        try:
            cur = con.cursor()
            row = cur.execute(
                "SELECT id, assigned_staff FROM project_stages WHERE project_id = ? AND stage_code = ?",
                (project_id, stage_code),
            ).fetchone()
            if not row:
                raise ValueError(f"Etap {stage_code} nie istnieje w projekcie {project_id}")
            ps_id, assigned_staff_json = row[0], row[1]

            # 1. stage_staff_assignments
            cur.execute(
                "DELETE FROM stage_staff_assignments WHERE project_stage_id = ? AND employee_id = ?",
                (ps_id, employee_id),
            )

            # 2. project_stages.assigned_staff JSON
            try:
                staff_list = json.loads(assigned_staff_json) if assigned_staff_json else []
            except (json.JSONDecodeError, TypeError):
                staff_list = []
            staff_list = [e for e in staff_list if e.get("employee_id") != employee_id]
            new_json = json.dumps(staff_list) if staff_list else None
            cur.execute(
                "UPDATE project_stages SET assigned_staff = ? WHERE id = ?",
                (new_json, ps_id),
            )
            con.commit()
        finally:
            con.close()

    def _set_stage_dates(
        self,
        project_id: int,
        stage_code: str,
        planned_start: Optional[str],
        planned_end: Optional[str],
    ) -> None:
        """Ustaw daty planowane etapu w stage_schedule."""
        db_path = self._project_db(project_id)
        if not db_path:
            raise ValueError(f"Brak bazy dla projektu {project_id}")
        con = sqlite3.connect(db_path)
        try:
            cur = con.cursor()
            row = cur.execute(
                "SELECT id FROM project_stages WHERE project_id = ? AND stage_code = ?",
                (project_id, stage_code),
            ).fetchone()
            if not row:
                raise ValueError(f"Etap {stage_code} nie istnieje w projekcie {project_id}")
            ps_id = row[0]

            existing = cur.execute(
                "SELECT id FROM stage_schedule WHERE project_stage_id = ?", (ps_id,)
            ).fetchone()
            if existing:
                cur.execute(
                    "UPDATE stage_schedule SET template_start = ?, template_end = ? WHERE project_stage_id = ?",
                    (planned_start, planned_end, ps_id),
                )
            else:
                cur.execute(
                    "INSERT INTO stage_schedule (project_stage_id, template_start, template_end) VALUES (?, ?, ?)",
                    (ps_id, planned_start, planned_end),
                )
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------------
    # Wykresy
    # ------------------------------------------------------------------

    def render_chart(self, chart_type: str, title: str, items: List[Dict]) -> Dict:
        """Narysuj wykres PNG (gantt/bar) i zapisz do pliku tymczasowego.

        Ścieżka trafia do self.chart_paths — GUI osadza obraz w oknie czatu.
        Zwraca zwięzły opis (do kontekstu agenta), nie samą grafikę.
        """
        if not items:
            return {"error": "Brak danych do wykresu (items puste)."}

        try:
            import tempfile
            import matplotlib
            matplotlib.use("Agg")  # backend bez GUI — bezpieczny w wątku roboczym
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
        except Exception as ex:
            return {"error": f"Brak biblioteki matplotlib: {ex}"}

        _COLORS = {
            "red": "#e74c3c", "orange": "#e67e22",
            "green": "#27ae60", "blue": "#3498db",
        }

        try:
            n = len(items)
            fig, ax = plt.subplots(figsize=(10, max(2.5, 0.5 * n + 1)), dpi=110)

            if chart_type == "gantt":
                labels = []
                for i, it in enumerate(items):
                    s = (it.get("start") or "")[:10]
                    e = (it.get("end") or "")[:10]
                    try:
                        d0 = datetime.strptime(s, "%Y-%m-%d")
                        d1 = datetime.strptime(e, "%Y-%m-%d")
                    except ValueError:
                        continue
                    if d1 < d0:
                        d0, d1 = d1, d0
                    width = max((d1 - d0).days, 1)
                    color = _COLORS.get((it.get("color") or "blue").lower(), "#3498db")
                    y = n - 1 - i  # pierwszy element na górze
                    ax.barh(y, width, left=mdates.date2num(d0), height=0.6,
                            color=color, edgecolor="white")
                    labels.append((y, it.get("label", "")))

                ax.set_yticks([y for y, _ in labels])
                ax.set_yticklabels([lbl for _, lbl in labels], fontsize=9)
                ax.xaxis_date()
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
                # Linia "dziś"
                try:
                    ax.axvline(mdates.date2num(datetime.strptime(self.today, "%Y-%m-%d")),
                               color="#c0392b", linestyle="--", linewidth=1, label="dziś")
                    ax.legend(loc="lower right", fontsize=8)
                except ValueError:
                    pass
                fig.autofmt_xdate(rotation=30)

            elif chart_type == "bar":
                labels = [it.get("label", "") for it in items]
                values = [float(it.get("value") or 0) for it in items]
                colors = [_COLORS.get((it.get("color") or "blue").lower(), "#3498db")
                          for it in items]
                ax.bar(range(n), values, color=colors, edgecolor="white")
                ax.set_xticks(range(n))
                ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
                for i, v in enumerate(values):
                    ax.text(i, v, f"{v:g}", ha="center", va="bottom", fontsize=8)
            else:
                plt.close(fig)
                return {"error": f"Nieznany typ wykresu: {chart_type}"}

            ax.set_title(title, fontsize=12, fontweight="bold")
            ax.grid(axis="x" if chart_type == "gantt" else "y", alpha=0.3)
            fig.tight_layout()

            fd, path = tempfile.mkstemp(prefix="rm_chart_", suffix=".png")
            import os as _os
            _os.close(fd)
            fig.savefig(path, dpi=110, bbox_inches="tight")
            plt.close(fig)

            self.chart_paths.append(path)
            return {
                "ok": True,
                "chart_type": chart_type,
                "title": title,
                "items_count": n,
                "note": "Wykres wygenerowany i pokazany użytkownikowi w oknie czatu.",
            }
        except Exception as ex:
            return {"error": f"Błąd rysowania wykresu: {ex}", "traceback": traceback.format_exc()}

    # ------------------------------------------------------------------
    # Dispatcher narzędzi
    # ------------------------------------------------------------------

    def execute_tool(self, tool_name: str, tool_input: Dict) -> str:
        try:
            if tool_name == "get_projects_list":
                result = self.get_projects_list(**tool_input)
            elif tool_name == "get_project_stages":
                result = self.get_project_stages(**tool_input)
            elif tool_name == "get_delays":
                result = self.get_delays(**tool_input)
            elif tool_name == "get_worker_load":
                result = self.get_worker_load(**tool_input)
            elif tool_name == "get_schedule_summary":
                result = self.get_schedule_summary(**tool_input)
            elif tool_name == "render_chart":
                result = self.render_chart(**tool_input)
            elif tool_name == "propose_changes":
                result = self.propose_changes(**tool_input)
            elif tool_name == "commit_changes":
                result = self.commit_changes()
            elif tool_name == "cancel_changes":
                result = self.cancel_changes()
            else:
                result = {"error": f"Nieznane narzędzie: {tool_name}"}
        except Exception as ex:
            result = {"error": str(ex), "traceback": traceback.format_exc()}

        return json.dumps(result, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Pętla agentowa
# ---------------------------------------------------------------------------


def run_ai_agent(
    user_message: str,
    context: AIOptimizerContext,
    history: List[Dict],
    on_thinking: Optional[Callable[[str], None]] = None,
) -> str:
    """Uruchom jedną turę agenta Claude.

    Args:
        user_message: Wiadomość od użytkownika.
        context: Kontekst z ścieżkami do baz.
        history: Historia wiadomości (modyfikowana in-place, dodawana nowa tura).
        on_thinking: Callback wywoływany gdy agent używa narzędzia — do pokazania
                     użytkownikowi że coś się dzieje ("Czytam harmonogram...").

    Returns:
        Odpowiedź agenta jako tekst.
    """
    client = anthropic.Anthropic()

    rules = load_rules(getattr(context, 'rules_file', None))
    rules_section = f"\n\nREGUŁY FIRMOWE:\n{rules}" if rules else ""
    system = SYSTEM_PROMPT.format(today=context.today) + rules_section

    # Nowa tura — wyzeruj wykresy z poprzedniej odpowiedzi
    context.chart_paths = []

    history.append({"role": "user", "content": user_message})

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=TOOLS,
            messages=history,
        )

        # Zbierz tekst i wywołania narzędzi z odpowiedzi
        assistant_content = response.content
        history.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason == "end_turn":
            # Wyodrębnij tekst odpowiedzi
            text_parts = [
                block.text for block in assistant_content
                if hasattr(block, "text")
            ]
            return "\n".join(text_parts)

        if response.stop_reason == "tool_use":
            # Wykonaj narzędzia i wróć z wynikami
            tool_results = []
            for block in assistant_content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input

                if on_thinking:
                    label = {
                        "get_projects_list": "Czytam listę projektów...",
                        "get_project_stages": f"Czytam etapy projektu {tool_input.get('project_id', '')}...",
                        "get_delays": "Szukam opóźnień...",
                        "get_worker_load": "Sprawdzam obciążenie pracowników...",
                        "get_schedule_summary": "Przygotowuję podsumowanie...",
                        "render_chart": "Rysuję wykres...",
                        "propose_changes": "Przygotowuję propozycję zmian...",
                        "commit_changes": "Zapisuję zmiany do bazy...",
                        "cancel_changes": "Anuluję zmiany...",
                    }.get(tool_name, f"Wywołuję {tool_name}...")
                    on_thinking(label)

                result_str = context.execute_tool(tool_name, tool_input)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })

            history.append({"role": "user", "content": tool_results})
            # Kontynuuj pętlę — agent oceni wyniki i odpowie lub wywoła kolejne narzędzia
            continue

        # Nieoczekiwany stop_reason
        break

    return "(brak odpowiedzi)"


# ---------------------------------------------------------------------------
# Sesja czatu — wrapper z historią
# ---------------------------------------------------------------------------


class AIChatSession:
    """Sesja czatu z AI — przechowuje historię rozmowy."""

    def __init__(self, context: AIOptimizerContext):
        self.context = context
        self.history: List[Dict] = []

    def send(
        self,
        message: str,
        on_thinking: Optional[Callable[[str], None]] = None,
    ) -> str:
        return run_ai_agent(message, self.context, self.history, on_thinking)

    def reset(self) -> None:
        self.history.clear()
