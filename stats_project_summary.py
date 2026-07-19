"""stats_project_summary.py — podsumowanie projektu ("Status/Odchylenie/CPM/
Platnosci"), port 1:1 z RM-BAZA-MANAGER/rm_manager.py:
  - recalculate_forecast() (linie ~4239-4472) - propagacja harmonogramu
    (topological sort + zaleznosci FS/SS+lag + actual periods)
  - calculate_critical_path()/get_critical_path_details() (~4513-4670) - CPM
    (forward/backward pass, ES/EF/LS/LF, total_float)
  - get_project_status_summary() (~5475-5507) - status ON_TRACK/AT_RISK/DELAYED
  - sekcja PLATNOSCI z rm_manager_gui.py (~9631-9677)

Czysto read-only - RM_STATS tylko odczytuje te same tabele i liczy identyczny
wynik jak GUI RM_MANAGER (zakladka "Podsumowanie" per projekt), zeby dac
przeglad zbiorczy po wszystkich projektach naraz.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from db import RMStatsDB

# Sub-milestone'y wchodzace w sklad ODBIORY - pomijane w liczniku "etapow bez
# rezerwy" i w progresie (tak jak _CHILD_MILESTONE_CODES w rm_manager_gui.py).
SUB_MILESTONES = {
    'ODBIORY': ['FAT', 'ODBIOR_1', 'ODBIOR_2', 'ODBIOR_3', 'TRANSPORT', 'URUCHOMIENIE_U_KLIENTA'],
}
CHILD_MILESTONE_CODES = {code for children in SUB_MILESTONES.values() for code in children}


def _topological_sort(stages: List[str], dependencies: List[Dict]) -> List[str]:
    graph = {s: [] for s in stages}
    in_degree = {s: 0 for s in stages}
    for dep in dependencies:
        pred, succ = dep['predecessor_stage_code'], dep['successor_stage_code']
        if pred in graph and succ in graph:
            graph[pred].append(succ)
            in_degree[succ] += 1

    queue = deque([s for s in stages if in_degree[s] == 0])
    result = []
    while queue:
        stage = queue.popleft()
        result.append(stage)
        for neighbor in graph[stage]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(stages):
        return stages  # cykl w zaleznosciach - fallback na oryginalna kolejnosc
    return result


def recalculate_forecast(inputs: Dict) -> Dict:
    """Port recalculate_forecast() - przelicza harmonogram etapow projektu na
    podstawie template dat, zaleznosci (FS/SS+lag) i rzeczywistych okresow."""
    stages = inputs['stages']
    dependencies = inputs['dependencies']
    actuals = inputs['actuals']

    stage_order = _topological_sort(list(stages.keys()), dependencies)
    forecast: Dict[str, Dict] = {}

    for stage_code in stage_order:
        template = stages.get(stage_code, {})
        periods = actuals.get(stage_code, [])

        # A. Etap zakonczony - uzyj actual
        if periods and all(p['ended_at'] for p in periods):
            first_start = min(p['started_at'] for p in periods)
            last_end = max(p['ended_at'] for p in periods)
            forecast[stage_code] = {
                'template_start': template.get('template_start'),
                'template_end': template.get('template_end'),
                'forecast_start': first_start,
                'forecast_end': last_end,
                'actual_periods': periods,
                'is_active': False,
                'is_actual': True,
            }
            continue

        # B. Etap trwa - actual_start + template_duration
        if periods and any(p['ended_at'] is None for p in periods):
            active_period = next(p for p in periods if p['ended_at'] is None)
            if template.get('template_start') and template.get('template_end'):
                t_start = datetime.fromisoformat(template['template_start'])
                t_end = datetime.fromisoformat(template['template_end'])
                duration_days = (t_end - t_start).days
            else:
                duration_days = 5
            start_dt = datetime.fromisoformat(active_period['started_at'])
            end_dt = start_dt + timedelta(days=duration_days)

            # Etap TRWA i jest juz opozniony: jesli przewidywany koniec wypada
            # w przeszlosci (minela data planowanego zakonczenia, a etap wciaz
            # otwarty), przesun forecast_end co najmniej na dzis. Bez tego etap
            # "w toku" nigdy nie sygnalizuje opoznienia, bo jego czas trwania
            # zawsze = template_duration (odchylenie = 0).
            now_dt = datetime.now()
            if end_dt < now_dt:
                end_dt = now_dt

            forecast[stage_code] = {
                'template_start': template.get('template_start'),
                'template_end': template.get('template_end'),
                'forecast_start': active_period['started_at'],
                'forecast_end': end_dt.isoformat(),
                'actual_periods': periods,
                'is_active': True,
                'is_actual': False,
            }
            continue

        # C. Etap nierozpoczety
        if not template.get('template_start') and not periods:
            forecast[stage_code] = {
                'template_start': None, 'template_end': None,
                'forecast_start': None, 'forecast_end': None,
                'actual_periods': periods, 'is_active': False, 'is_actual': False,
                'variance_days': 0,
            }
            continue

        constraints = []
        for dep in dependencies:
            if dep['successor_stage_code'] != stage_code:
                continue
            pred = forecast.get(dep['predecessor_stage_code'])
            if not pred or not pred.get('forecast_end') or not pred.get('forecast_start'):
                continue
            lag = dep.get('lag_days') or 0
            if dep['dependency_type'] == 'FS':
                constraints.append(datetime.fromisoformat(pred['forecast_end']) + timedelta(days=lag))
            elif dep['dependency_type'] == 'SS':
                constraints.append(datetime.fromisoformat(pred['forecast_start']) + timedelta(days=lag))

        candidates = []
        if template.get('template_start'):
            candidates.append(datetime.fromisoformat(template['template_start']))
        candidates.extend(constraints)
        forecast_start = max(candidates) if candidates else datetime.now()

        if template.get('template_start') and template.get('template_end'):
            t_start = datetime.fromisoformat(template['template_start'])
            t_end = datetime.fromisoformat(template['template_end'])
            duration_days = (t_end - t_start).days
        else:
            duration_days = 5
        forecast_end = forecast_start + timedelta(days=duration_days)

        forecast[stage_code] = {
            'template_start': template.get('template_start'),
            'template_end': template.get('template_end'),
            'forecast_start': forecast_start.date().isoformat(),
            'forecast_end': forecast_end.date().isoformat(),
            'actual_periods': periods,
            'is_active': False,
            'is_actual': False,
        }

    for stage_code, fc in forecast.items():
        if fc.get('template_start') and fc.get('template_end'):
            t_start = datetime.fromisoformat(fc['template_start'])
            t_end = datetime.fromisoformat(fc['template_end'])
            f_start = fc['forecast_start']
            f_end = fc['forecast_end']
            if isinstance(f_start, str):
                f_start = datetime.fromisoformat(f_start)
            if isinstance(f_end, str):
                f_end = datetime.fromisoformat(f_end)
            template_duration = (t_end - t_start).days
            forecast_duration = (f_end - f_start).days
            fc['variance_days'] = forecast_duration - template_duration
        else:
            fc.setdefault('variance_days', 0)

    return forecast


def get_critical_path_details(forecast: Dict, dependencies: List[Dict]) -> List[Dict]:
    """Port get_critical_path_details() - CPM forward/backward pass."""
    stages = list(forecast.keys())
    if not stages:
        return []

    durations = {}
    for code, fc in forecast.items():
        try:
            s = str(fc.get('forecast_start') or '')[:10]
            e = str(fc.get('forecast_end') or '')[:10]
            d = (datetime.fromisoformat(e) - datetime.fromisoformat(s)).days if s and e else 1
            durations[code] = max(d, 1)
        except Exception:
            durations[code] = 1

    order = _topological_sort(stages, dependencies)

    ES = {s: 0 for s in stages}
    for stage in order:
        ef = ES[stage] + durations.get(stage, 1)
        for dep in dependencies:
            if dep['predecessor_stage_code'] != stage:
                continue
            succ = dep['successor_stage_code']
            if succ not in ES:
                continue
            lag = dep.get('lag_days') or 0
            if dep['dependency_type'] == 'FS':
                ES[succ] = max(ES[succ], ef + lag)
            elif dep['dependency_type'] == 'SS':
                ES[succ] = max(ES[succ], ES[stage] + lag)

    EF = {s: ES[s] + durations.get(s, 1) for s in stages}
    project_end = max(EF.values())

    LF = {s: project_end for s in stages}
    for stage in reversed(order):
        ls = LF[stage] - durations.get(stage, 1)
        for dep in dependencies:
            if dep['successor_stage_code'] != stage:
                continue
            pred = dep['predecessor_stage_code']
            if pred not in LF:
                continue
            lag = dep.get('lag_days') or 0
            if dep['dependency_type'] == 'FS':
                LF[pred] = min(LF[pred], ls - lag)
            elif dep['dependency_type'] == 'SS':
                LF[pred] = min(LF[pred], ls - lag + durations.get(pred, 1))

    LS = {s: LF[s] - durations.get(s, 1) for s in stages}

    result = []
    for stage in order:
        total_float = LS[stage] - ES[stage]
        result.append({
            'stage_code': stage, 'duration': durations.get(stage, 1),
            'ES': ES[stage], 'EF': EF[stage], 'LS': LS[stage], 'LF': LF[stage],
            'total_float': total_float, 'is_critical': total_float <= 0,
        })
    return result


def _project_status_label(project_status_db: Optional[str], variance_status: str) -> Dict:
    """Port logiki etykiet z rm_manager_gui.py (status_icon/status_pl)."""
    if project_status_db == 'DONE':
        return {'code': 'DONE', 'label': 'ZAKONCZONY', 'icon': 'done'}
    mapping = {
        'DELAYED': {'code': 'DELAYED', 'label': 'OPOZNIONY', 'icon': 'delayed'},
        'AT_RISK': {'code': 'AT_RISK', 'label': 'ZAGROZONY', 'icon': 'at_risk'},
        'ON_TRACK': {'code': 'ON_TRACK', 'label': 'ZGODNIE Z PLANEM', 'icon': 'on_track'},
    }
    return mapping.get(variance_status, mapping['ON_TRACK'])


def build_project_summary(db: RMStatsDB, project: Dict) -> Dict:
    """Podsumowanie jednego projektu - odpowiednik zakladki Podsumowanie
    w RM_MANAGER GUI. `project` to wiersz z db.list_projects()."""
    pid = project['project_id']
    inputs = db.project_forecast_inputs(pid)
    if inputs.get('error'):
        return {
            'project_id': pid, 'name': project.get('name'), 'error': inputs['error'],
        }

    forecast = recalculate_forecast(inputs)

    # Odchylenie calosci = przewidywany koniec projektu vs. planowany koniec.
    # NIE suma odchylen czasow trwania etapow - bo wczesnie zamkniety etap
    # (duza rezerwa) maskowalby opoznienie etapu krytycznego, a etap "w toku"
    # ktory sie przeciaga w ogole nie wchodzilby do sumy (jego duration zawsze
    # = template_duration -> odchylenie 0). Port z rm_manager.py (naprawa
    # 2026-07-19: "Napraw status projektu: licz odchylenie wg daty
    # zakonczenia, nie sumy czasow trwania").
    def _to_dt(v):
        return datetime.fromisoformat(v) if isinstance(v, str) else v

    forecast_end_dates = [_to_dt(fc['forecast_end']) for fc in forecast.values() if fc.get('forecast_end')]
    template_end_dates = [_to_dt(fc['template_end']) for fc in forecast.values() if fc.get('template_end')]
    completion_forecast_dt = max(forecast_end_dates) if forecast_end_dates else None
    planned_end_dt = max(template_end_dates) if template_end_dates else None

    if completion_forecast_dt and planned_end_dt:
        total_variance = (completion_forecast_dt - planned_end_dt).days
    else:
        total_variance = 0

    if total_variance > 10:
        variance_status = 'DELAYED'
    elif total_variance > 5:
        variance_status = 'AT_RISK'
    else:
        variance_status = 'ON_TRACK'

    status_info = _project_status_label(project.get('project_status'), variance_status)

    completion_dates = [fc['forecast_end'] for fc in forecast.values() if fc.get('forecast_end')]
    completion_forecast = max(completion_dates) if completion_dates else None

    active_stages = [
        code for code, fc in forecast.items()
        if fc.get('is_active') and code not in CHILD_MILESTONE_CODES
    ]

    details = get_critical_path_details(forecast, inputs['dependencies'])
    relevant_details = [d for d in details if d['stage_code'] not in CHILD_MILESTONE_CODES]
    n_critical = sum(1 for d in relevant_details if d['is_critical'])

    milestones_payment = db.payment_milestones(project_id=pid)
    total_paid = sum(m['percentage'] for m in milestones_payment)
    has_umorzony = any(m.get('payment_type') == 'UMORZONY' for m in milestones_payment)
    count_platnosc = sum(1 for m in milestones_payment if m.get('payment_type') == 'PLATNOSC' or m.get('payment_type') == 'PŁATNOŚĆ')

    zakonczony_periods = inputs['actuals'].get('ZAKONCZONY', [])
    is_paid_milestone = any(p.get('started_at') for p in zakonczony_periods)
    is_paid = is_paid_milestone or total_paid >= 100 or has_umorzony

    return {
        'project_id': pid,
        'name': project.get('name'),
        'status_code': status_info['code'],
        'status_label': status_info['label'],
        'overall_variance_days': total_variance,
        'completion_forecast': (completion_forecast or '')[:10] or None,
        'active_stages': active_stages,
        'is_paused': inputs.get('is_paused', False),
        'stages_total': len(relevant_details),
        'stages_critical': n_critical,
        'is_linear_project': n_critical == len(relevant_details) if relevant_details else False,
        'payment_total_paid_pct': total_paid,
        'payment_is_paid': is_paid,
        'payment_is_paid_milestone': is_paid_milestone,
        'payment_has_umorzony': has_umorzony,
        'payment_transze_count': len(milestones_payment),
        'payment_transze_platnosc_count': count_platnosc,
    }


def build_projects_summary(db: RMStatsDB) -> Dict:
    projects = db.list_projects(only_active=True)
    summaries = [build_project_summary(db, p) for p in projects]
    summaries.sort(key=lambda s: (s.get('status_code') != 'DELAYED', s.get('status_code') != 'AT_RISK', s.get('name') or ''))
    return {'projects': summaries, 'count': len(summaries)}
