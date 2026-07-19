"""stats_status.py — agregacja statystyk statusow projektow.

Ile projektow w jakim etapie, opoznienia plan vs realizacja (stage_schedule
vs stage_actual_periods z per-projektowych baz RM_MANAGER_projects).
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List

from db import RMStatsDB

# Kolejnosc statusow zgodna z nomenklatura RM_MANAGER (kolumna projects.status
# w master.sqlite, wypelniana przez GUI RM_MANAGER - patrz checkboxy
# "Statusy" w oknie edycji projektu: Przyjety/Projekt/Kompletacja/Montaz/
# Automatyka/Uruchomienie/Odbiory/Poprawki/Wstrzymany/Zakonczony).
# project_status (NEW/IN_PROGRESS/ACCEPTED/DONE) to osobny, zgrubny status
# techniczny - nieuzywany tutaj do etykiet, bo nie odpowiada nomenklaturze
# znanej userom RM_MANAGER. Dane w bazie maja niespojna wielkosc liter
# (np. "PROJEKT" caps, "Nowy" zamiast "Przyjety" dla nowych projektow) -
# normalizujemy do Capitalized zgodnie ze slownikiem GUI.
STATUS_ORDER = [
    'Nowy', 'Przyjety', 'Projekt', 'Elektroprojekt', 'Kompletacja', 'Montaz',
    'Automatyka', 'Elektromontaz', 'Uruchomienie', 'Odbiory', 'Poprawki',
    'Wstrzymany', 'Zakonczony',
]

_STATUS_NORMALIZE = {s.lower(): s for s in STATUS_ORDER}


def _normalize_status(raw_status: str) -> str:
    if not raw_status:
        return 'Nieznany'
    return _STATUS_NORMALIZE.get(raw_status.strip().lower(), raw_status.strip())


def _status_sort_key(status: str):
    try:
        return STATUS_ORDER.index(status)
    except ValueError:
        return len(STATUS_ORDER)


def _parse_date(value: str):
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _project_delays(db: RMStatsDB, pid: int, today: date, current_status: str) -> List[Dict]:
    stage_data = db.project_stage_status(pid)
    stages = stage_data.get('stages', [])

    # Etapy WCZESNIEJSZE w kolejce niz biezacy status projektu (np. PRZYJETY
    # gdy projekt jest juz w Montazu) sa pomijane - RM_MANAGER czesto nie
    # zamyka formalnie starych etapow (brak actual_end), mimo ze projekt
    # faktycznie dawno przeszedl dalej. Bez tego kazdy taki "zapomniany"
    # wpis wygladal jak trwajace opoznienie fazy, ktora juz minela.
    current_idx = _status_sort_key(current_status)

    project_delays = []
    for stage in stages:
        stage_status = _normalize_status(stage.get('stage_code'))
        if _status_sort_key(stage_status) < current_idx:
            continue

        planned_end = _parse_date(stage.get('planned_end'))
        actual_end = _parse_date(stage.get('actual_end'))
        actual_start = _parse_date(stage.get('actual_start'))

        if planned_end and not actual_end:
            # etap nieskonczony a termin planowany juz minal
            if planned_end < today:
                project_delays.append({
                    'stage_code': stage['stage_code'],
                    'planned_end': stage.get('planned_end'),
                    'overrun_days': (today - planned_end).days,
                    'in_progress': bool(actual_start),
                })
        elif planned_end and actual_end and actual_end > planned_end:
            # etap skonczony, ale po terminie
            project_delays.append({
                'stage_code': stage['stage_code'],
                'planned_end': stage.get('planned_end'),
                'actual_end': stage.get('actual_end'),
                'overrun_days': (actual_end - planned_end).days,
                'in_progress': False,
            })
    return project_delays


# Statusy koncowe - projekt juz sie nie zmienia, wiec etapy z minionym
# planned_end i brakiem actual_end (dane historyczne, czesto niekompletne
# w starszych wpisach RM_MANAGER) nie sa realnym, biezacym opoznieniem.
# Bez tego wykluczenia kazdy dawno zakonczony projekt z choc jednym
# nieuzupelnionym actual_end wygladal jak aktywnie opozniony.
#
# projects.status (checkboxy) i project_status (NEW/IN_PROGRESS/ACCEPTED/DONE)
# to dwa niezalezne pola w RM_MANAGER i potrafia sie rozjezdzac (np. status
# checkbox wciaz "Przyjety" mimo ze project_status juz DONE) - traktujemy
# projekt jako zakonczony gdy KTOREKOLWIEK z nich to potwierdza, zeby oba
# widoki (Status projektow / Podsumowanie) byly spojne.
_FINAL_STATUSES = {'Zakonczony', 'Wstrzymany'}

# "Nowy" to projekt oczekujacy na decyzje usera o formalnym przyjeciu -
# praca (i sensowny harmonogram) zaczyna sie dopiero od etapu PRZYJETY.
# Miniety termin PRZYJETY przy statusie Nowy to nie opoznienie realizacji,
# tylko po prostu "wciaz w kolejce, user jeszcze nie zdecydowal" - nie
# powinno straszyc czerwienia tak samo jak faktyczne poslizgi w toku pracy.
_NOT_STARTED_STATUSES = {'Nowy'}


def build_status_overview(db: RMStatsDB) -> Dict:
    projects = db.list_projects(only_active=True)
    today = date.today()

    by_status: Dict[str, int] = {}
    delayed_projects: List[Dict] = []
    all_projects: List[Dict] = []
    on_time_count = 0
    in_progress_count = 0

    for proj in projects:
        status = _normalize_status(proj.get('status'))
        # project_status='DONE' jest priorytetowy nad checkboxem status - RM_MANAGER
        # potrafi zostawic stary status-checkbox (np. "Przyjety") mimo ze projekt
        # zostal juz oznaczony jako zakonczony (spojne z _project_status_label()
        # w stats_project_summary.py).
        if proj.get('project_status') == 'DONE':
            status = 'Zakonczony'
        by_status[status] = by_status.get(status, 0) + 1

        pid = proj['project_id']
        skip_delays = status in _FINAL_STATUSES or status in _NOT_STARTED_STATUSES
        project_delays = [] if skip_delays else _project_delays(db, pid, today, status)

        row = {
            'project_id': pid,
            'name': proj.get('name'),
            'priority': proj.get('priority'),
            'status': status,
            'is_delayed': bool(project_delays),
            'delays': project_delays,
        }
        all_projects.append(row)

        if status not in _FINAL_STATUSES:
            in_progress_count += 1

        if project_delays:
            delayed_projects.append(row)
        else:
            on_time_count += 1

    delayed_projects.sort(key=lambda p: max(d['overrun_days'] for d in p['delays']), reverse=True)
    all_projects.sort(key=lambda p: (not p['is_delayed'], p.get('priority') or 99, p.get('name') or ''))
    by_status = dict(sorted(by_status.items(), key=lambda kv: _status_sort_key(kv[0])))

    return {
        # total_active = wszystkie nie-zarchiwizowane w bazie (flaga active),
        # w tym Zakonczony/Wstrzymany - "active" w RM_MANAGER znaczy tylko
        # "widoczny/nie ukryty", nie "w toku realizacji".
        'total_active': len(projects),
        # in_progress_count = realnie w realizacji (bez Zakonczony/Wstrzymany) -
        # to pokazuje karta "Aktywne projekty" w UI, zeby nie sugerowac ze
        # zakonczone prace nadal "trwaja".
        'in_progress_count': in_progress_count,
        'by_status': by_status,
        'on_time_count': on_time_count,
        'delayed_count': len(delayed_projects),
        'delayed_projects': delayed_projects,
        'all_projects': all_projects,
        'today': today.isoformat(),
    }
