"""db.py — adapter dostępu do baz dla modułów statystyk (stats_status.py,
stats_project_summary.py) wewnątrz RM_MANAGER.

Odpowiednik db.py z RM_STATS (klasa RMStatsDB), ale ścieżki baz bierze z
konfiguracji RM_MANAGERa zamiast z osobnego config.json. Dzięki temu moduły
stats_*.py są IDENTYCZNE w obu projektach (importują `from db import RMStatsDB`),
a jedyna różnica — skąd wziąć ścieżki — jest schowana tutaj. Ułatwia to
migrację poprawek: kopiujesz stats_*.py między RM_STATS a RM_MANAGER bez zmian.

Read-only: połączenia otwierane w trybie mode=ro, nigdy nie zapisujemy do
żywych baz.

Zawiera tylko metody używane przez oba widoki (Podsumowanie, Status projektów):
list_projects, project_stage_status, project_forecast_inputs, payment_milestones.
Pełny db.py z RM_STATS ma więcej metod (materiały, pracownicy, urlopy) — dołóż
gdy zajdzie potrzeba przeniesienia kolejnych widoków.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional


def open_ro(path: str) -> sqlite3.Connection:
    uri = Path(path).as_posix()
    con = sqlite3.connect(f'file:{uri}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


class RMStatsDB:
    """Read-only dostęp do baz RM_BAZA/RM_MANAGER dla widoków statystyk.

    Tworzona z jawnych ścieżek (z konfiguracji RM_MANAGERa):
        master_db_path        — master.sqlite (RM_BAZA): tabela projects
        rm_master_db_path     — rm_manager.sqlite: płatności, pracownicy
        rm_manager_projects_dir — katalog rm_manager_project_<id>.sqlite
        projects_path         — katalog project_<id>.sqlite (RM_BAZA Machines/BOM),
                                opcjonalny — potrzebny do completion_percent()
    """

    def __init__(self, master_db_path: str, rm_master_db_path: str,
                 rm_manager_projects_dir: str, projects_path: str = None):
        self.master_db_path = master_db_path
        self.rm_master_db_path = rm_master_db_path
        self.rm_manager_projects_dir = Path(rm_manager_projects_dir)
        self.projects_path = Path(projects_path) if projects_path else None

    # ------------------------------------------------------------------
    # Ścieżki do baz per-projekt
    # ------------------------------------------------------------------

    def project_events_db_path(self, project_id: int) -> Optional[Path]:
        p = self.rm_manager_projects_dir / f'rm_manager_project_{project_id}.sqlite'
        return p if p.exists() else None

    def mag_db_path(self, project_id: int) -> Optional[Path]:
        """Baza Machines (BOM/items) — RM_BAZA/projects/project_<id>.sqlite."""
        if not self.projects_path:
            return None
        p = self.projects_path / f'project_{project_id}.sqlite'
        return p if p.exists() else None

    def completion_percent(self, project_id: int) -> Optional[Dict]:
        """Stopień kompletacji BOM — liczony na żywo z tabeli items.

        Procent = odebrane / (wszystkie − ZZ):
        - "wszystkie" = items nie-ukryte (is_hidden=0)
        - "ZZ" = pozycje których numer rysunku kończy się na "ZZ" (złożenia do
          montażu, wyłączone z mianownika)
        - "odebrane" = delivered_qty >= COALESCE(order_qty, work_qty, src_qty)
        Zwraca None gdy brak bazy Machines dla projektu."""
        db_path = self.mag_db_path(project_id)
        if not db_path:
            return None
        con = open_ro(str(db_path))
        try:
            total_rows = con.execute(
                'SELECT COUNT(*) FROM items WHERE project_id = ? AND COALESCE(is_hidden, 0) = 0',
                (project_id,),
            ).fetchone()[0]

            if total_rows == 0:
                return {'percent': 0, 'total_rows': 0, 'valid_count': 0, 'delivered_count': 0}

            zz_count = con.execute(
                """SELECT COUNT(*) FROM items
                WHERE project_id = ? AND COALESCE(is_hidden, 0) = 0
                AND UPPER(TRIM(COALESCE(NULLIF(work_drawing_no,''), src_drawing_no, ''))) LIKE '%ZZ'""",
                (project_id,),
            ).fetchone()[0]

            delivered_count = con.execute(
                """SELECT COUNT(*) FROM items
                WHERE project_id = ? AND COALESCE(is_hidden, 0) = 0
                AND UPPER(TRIM(COALESCE(NULLIF(work_drawing_no,''), src_drawing_no, ''))) NOT LIKE '%ZZ'
                AND delivered_qty IS NOT NULL
                AND COALESCE(order_qty, work_qty, src_qty) IS NOT NULL
                AND CAST(delivered_qty AS REAL) >= CAST(COALESCE(order_qty, work_qty, src_qty) AS REAL)""",
                (project_id,),
            ).fetchone()[0]

            valid_count = total_rows - zz_count
            percent = round((delivered_count / valid_count) * 100) if valid_count > 0 else 0

            return {
                'percent': percent,
                'total_rows': total_rows,
                'valid_count': valid_count,
                'delivered_count': delivered_count,
            }
        except sqlite3.OperationalError:
            return None
        finally:
            con.close()

    # ------------------------------------------------------------------
    # Projekty (master.sqlite)
    # ------------------------------------------------------------------

    def list_projects(self, only_active: bool = True) -> List[Dict]:
        con = open_ro(self.master_db_path)
        try:
            cols = {r[1] for r in con.execute('PRAGMA table_info(projects)')}
            wanted = ['project_id', 'name', 'active', 'project_status', 'status',
                      'project_type', 'priority', 'designer', 'expected_delivery',
                      'received_percent']
            sel = [c for c in wanted if c in cols]
            rows = con.execute(
                f'SELECT {", ".join(sel)} FROM projects ORDER BY '
                + ('priority, name' if 'priority' in cols else 'name')
            ).fetchall()
            result = [dict(r) for r in rows]
            if only_active and 'active' in cols:
                result = [r for r in result if r.get('active')]
            if 'project_type' in cols:
                result = [r for r in result if r.get('project_type') != 'WAREHOUSE']
            return result
        finally:
            con.close()

    # ------------------------------------------------------------------
    # Etapy / opóźnienia (per-projekt)
    # ------------------------------------------------------------------

    def project_stage_status(self, project_id: int) -> Dict:
        """Lista etapów z planem (stage_schedule) i realizacją (stage_actual_periods)."""
        db_path = self.project_events_db_path(project_id)
        if not db_path:
            return {'error': 'brak bazy etapów', 'stages': []}

        con = open_ro(str(db_path))
        try:
            try:
                stage_rows = con.execute(
                    'SELECT id, stage_code, sequence FROM project_stages '
                    'WHERE project_id = ? ORDER BY sequence', (project_id,)
                ).fetchall()
            except sqlite3.OperationalError as e:
                return {'error': str(e), 'stages': []}

            schedule = {
                r['project_stage_id']: dict(r)
                for r in con.execute(
                    'SELECT project_stage_id, template_start, template_end FROM stage_schedule'
                ).fetchall()
            }
            actuals = {}
            for r in con.execute(
                'SELECT project_stage_id, started_at, ended_at FROM stage_actual_periods'
            ).fetchall():
                # jeśli etap ma wiele okresów, bierzemy pierwszy start / ostatni koniec
                sid = r['project_stage_id']
                cur = actuals.get(sid)
                if cur is None:
                    actuals[sid] = dict(r)
                else:
                    if r['started_at'] and (not cur['started_at'] or r['started_at'] < cur['started_at']):
                        cur['started_at'] = r['started_at']
                    if r['ended_at'] and (not cur['ended_at'] or r['ended_at'] > cur['ended_at']):
                        cur['ended_at'] = r['ended_at']

            stages = []
            for r in stage_rows:
                sid = r['id']
                sched = schedule.get(sid, {})
                actual = actuals.get(sid, {})
                stages.append({
                    'stage_code': r['stage_code'],
                    'sequence': r['sequence'],
                    'planned_start': sched.get('template_start'),
                    'planned_end': sched.get('template_end'),
                    'actual_start': actual.get('started_at'),
                    'actual_end': actual.get('ended_at'),
                })
            return {'stages': stages}
        finally:
            con.close()

    def project_forecast_inputs(self, project_id: int) -> Dict:
        """Dane surowe do recalculate_forecast()/CPM: etapy z template dat,
        zależności, rzeczywiste okresy, flagi is_milestone. Pomija WSTRZYMANY."""
        empty = {'error': None, 'stages': {}, 'dependencies': [], 'actuals': {},
                 'is_milestone': {}, 'is_paused': False}
        db_path = self.project_events_db_path(project_id)
        if not db_path:
            empty['error'] = 'brak bazy etapów'
            return empty

        con = open_ro(str(db_path))
        try:
            try:
                stage_rows = con.execute("""
                    SELECT ps.stage_code, ss.template_start, ss.template_end
                    FROM project_stages ps
                    LEFT JOIN stage_schedule ss ON ss.project_stage_id = ps.id
                    JOIN stage_definitions sd ON ps.stage_code = sd.code
                    WHERE ps.project_id = ? AND ps.stage_code != 'WSTRZYMANY'
                    ORDER BY ps.sequence
                """, (project_id,)).fetchall()
            except sqlite3.OperationalError as e:
                empty['error'] = str(e)
                return empty

            stages = {r['stage_code']: dict(r) for r in stage_rows}

            dependencies = [dict(r) for r in con.execute("""
                SELECT predecessor_stage_code, successor_stage_code, dependency_type, lag_days
                FROM stage_dependencies WHERE project_id = ?
            """, (project_id,)).fetchall()]

            actual_rows = con.execute("""
                SELECT ps.stage_code, sap.started_at, sap.ended_at
                FROM stage_actual_periods sap
                JOIN project_stages ps ON sap.project_stage_id = ps.id
                WHERE ps.project_id = ?
                ORDER BY sap.started_at
            """, (project_id,)).fetchall()
            actuals: Dict[str, List[Dict]] = {}
            for r in actual_rows:
                actuals.setdefault(r['stage_code'], []).append({
                    'started_at': r['started_at'], 'ended_at': r['ended_at'],
                })

            is_milestone = {r['code']: bool(r['is_milestone'])
                            for r in con.execute('SELECT code, is_milestone FROM stage_definitions').fetchall()}

            try:
                paused = con.execute(
                    "SELECT id FROM project_pauses WHERE project_id = ? AND end_at IS NULL",
                    (project_id,)).fetchone() is not None
            except sqlite3.OperationalError:
                paused = False

            return {'error': None, 'stages': stages, 'dependencies': dependencies,
                    'actuals': actuals, 'is_milestone': is_milestone, 'is_paused': paused}
        finally:
            con.close()

    # ------------------------------------------------------------------
    # Płatności (rm_manager.sqlite)
    # ------------------------------------------------------------------

    def payment_milestones(self, project_id: Optional[int] = None) -> List[Dict]:
        con = open_ro(self.rm_master_db_path)
        try:
            sql = 'SELECT project_id, percentage, payment_date, payment_type FROM payment_milestones'
            params = ()
            if project_id is not None:
                sql += ' WHERE project_id = ?'
                params = (project_id,)
            return [dict(r) for r in con.execute(sql, params).fetchall()]
        finally:
            con.close()
