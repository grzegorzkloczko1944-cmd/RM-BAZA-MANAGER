"""stats_status.py — agregacja statystyk statusow projektow.

Ile projektow w jakim etapie, opoznienia plan vs realizacja (stage_schedule
vs stage_actual_periods z per-projektowych baz RM_MANAGER_projects).
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List

from db import RMStatsDB, project_sort_key
from stats_project_summary import build_project_summary, recalculate_forecast

# Kolejnosc statusow zgodna z nomenklatura RM_MANAGER (kolumna projects.status
# w master.sqlite, wypelniana przez GUI RM_MANAGER - patrz checkboxy
# "Statusy" w oknie edycji projektu: Przyjety/Projekt/Kompletacja/Montaz/
# Automatyka/Uruchomienie/Odbiory/Poprawki/Wstrzymany/Zakonczony).
# project_status (NEW/IN_PROGRESS/ACCEPTED/DONE) to osobny, zgrubny status
# techniczny - nieuzywany tutaj do etykiet, bo nie odpowiada nomenklaturze
# znanej userom RM_MANAGER. Dane w bazie maja niespojna wielkosc liter
# (np. "PROJEKT" caps, "Nowy" zamiast "Przyjety" dla nowych projektow) -
# normalizujemy do Capitalized zgodnie ze slownikiem GUI.
#
# WAZNE: musi byc z polskimi znakami DOKLADNIE jak w bazie (sprawdzone przez
# SELECT DISTINCT status FROM projects) - "Przyjety" bez "e" NIE pasuje do
# "Przyjęty" z bazy nawet po .lower(), przez co _normalize_status po cichu
# nie normalizowal (zwracal string 1:1 z bazy), a taki string nie byl w
# STATUS_ORDER wiec _status_sort_key dawal mu najgorszy mozliwy indeks -
# to psulo caly filtr "etapy wczesniejsze niz biezacy status" dla KAZDEGO
# projektu ze statusem Przyjety/Zakonczony/Montaz/Elektromontaz (2026-07-19).
STATUS_ORDER = [
    'Nowy', 'Przyjęty', 'Projekt', 'Elektroprojekt', 'Kompletacja', 'Montaż',
    'Automatyka', 'Elektromontaż', 'Uruchomienie', 'Odbiory', 'Poprawki',
    'Wstrzymany', 'Zakończony',
]

_PL_TO_ASCII = str.maketrans('ąćęłńóśźż', 'acelnoszz')


def _ascii_fold(s: str) -> str:
    return s.translate(_PL_TO_ASCII)


# Dwie niezalezne wielkosci liter - projects.status w master.sqlite ma polskie
# znaki ("Przyjęty"), a stage_code w project_stages (rm_manager_project_<id>.
# sqlite) jest bez ogonkow, caps ("PRZYJETY") - _normalize_status musi
# rozpoznac OBA warianty i zmapowac na ta sama kanoniczna wartosc z STATUS_ORDER,
# inaczej porownanie miedzy nimi (np. w _project_delays) zawsze zawodzi.
_STATUS_NORMALIZE = {}
for _s in STATUS_ORDER:
    _STATUS_NORMALIZE[_s.lower()] = _s
    _STATUS_NORMALIZE[_ascii_fold(_s.lower())] = _s


def _normalize_status(raw_status: str) -> str:
    if not raw_status:
        return 'Nieznany'
    key = raw_status.strip().lower()
    return _STATUS_NORMALIZE.get(key) or _STATUS_NORMALIZE.get(_ascii_fold(key), raw_status.strip())


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


def _project_delays(
    db: RMStatsDB, pid: int, today: date, current_status: str, forecast: Dict | None = None,
) -> List[Dict]:
    """`forecast` (z recalculate_forecast, patrz stats_project_summary.py) -
    gdy podany, overrun_days liczy sie wzgledem forecast_end (przeliczona
    prognoza z uwzglednieniem zaleznosci/opoznien poprzednich etapow), TA SAMA
    miara co "Odchylenie" w RM_MANAGER/zakladka Podsumowanie. Bez tego liczylo
    sie naiwnie (dzisiaj - planned_end z surowego szablonu bazowego) - dawalo
    zupelnie inna (i myląco wieksza) liczbe niz RM_MANAGER dla etapow po
    poslizgu wczesniejszych faz, bo nie uwzgledniało przesuniecia w lancuchu
    zaleznosci (np. Uruchomienie z planem sprzed 70 dni, ale realny poczatek
    przesuniety przez opoznienia Kompletacji/Montazu - naprawione 2026-08-26)."""
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
        # PRZYJETY nie ma twardego terminu - to decyzja usera kiedy przyjac
        # projekt do realizacji, nie zadanie z deadline'em. Nawet gdy formalnie
        # zamkniete po zaplanowanej dacie, to nie jest opoznienie realizacji.
        # TRANSPORT nie jest etapem z czasem trwania - to punktowe zdarzenie
        # (wyslano/odebrano), nie ma sensu liczyc go jako "opozniony etap".
        stage_code = stage.get('stage_code')
        if stage_code in ('PRZYJETY', 'TRANSPORT'):
            continue

        stage_status = _normalize_status(stage_code)
        if _status_sort_key(stage_status) < current_idx:
            continue

        actual_end = _parse_date(stage.get('actual_end'))
        actual_start = _parse_date(stage.get('actual_start'))

        # Preferujemy forecast_end (CPM/prognoza, spojna z RM_MANAGER) - fallback
        # na surowy planned_end tylko gdy forecast niedostepny (np. blad danych).
        fc = (forecast or {}).get(stage_code)
        if fc and fc.get('forecast_end'):
            reference_end = _parse_date(fc['forecast_end'])
            reference_end_raw = fc['forecast_end']
        else:
            reference_end = _parse_date(stage.get('planned_end'))
            reference_end_raw = stage.get('planned_end')

        # Tylko etapy WCIAZ OTWARTE z minietym terminem licza sie jako
        # opoznienie - to realny, biezacy problem wymagajacy akcji teraz.
        # Etap juz zamkniety po terminie (nawet jesli zakonczyl sie pozniej
        # niz planowano) to zamknieta historia, nie wplywa juz na nic - lista
        # ma pokazywac co trzeba dogonic TERAZ, nie kronike przeszlosci.
        if reference_end and not actual_end and reference_end < today:
            project_delays.append({
                'stage_code': stage_code,
                'planned_end': reference_end_raw,
                'overrun_days': (today - reference_end).days,
                'in_progress': bool(actual_start),
            })
    return project_delays


# Milestone'y informacyjne w ramach etapu ODBIORY - w oryginalnym RM_MANAGER
# (patrz STAGE_DEFINITIONS, is_milestone=1) sa CELOWO poza grafem CPM: to
# checkboxy/znaczniki bez wlasnego czasu trwania, nie osobne fazy harmonogramu.
# Dlatego NIE licza sie do "opoznienia projektu" (CPM) - ale przeterminowany,
# nieodhaczony milestone to wciaz realny sygnal ("zapomniano potwierdzic FAT"),
# wiec dostaje wlasna, osobna kategorie zamiast byc calkowicie niewidoczny.
# TRANSPORT pominiety - to punktowe zdarzenie bez sensownego "terminu"
# do przekroczenia (nie ma deadline'u wymagajacego akcji, tylko fakt do
# odnotowania kiedys).
_ODBIORY_MILESTONE_CODES = ('FAT', 'ODBIOR_1', 'ODBIOR_2', 'ODBIOR_3', 'URUCHOMIENIE_U_KLIENTA')


def _overdue_milestones(db: RMStatsDB, pid: int, today: date) -> List[Dict]:
    stage_data = db.project_stage_status(pid)
    stages = stage_data.get('stages', [])

    overdue = []
    for stage in stages:
        if stage.get('stage_code') not in _ODBIORY_MILESTONE_CODES:
            continue
        planned_end = _parse_date(stage.get('planned_end'))
        actual_end = _parse_date(stage.get('actual_end'))
        if planned_end and not actual_end and planned_end < today:
            overdue.append({
                'stage_code': stage['stage_code'],
                'planned_end': stage.get('planned_end'),
                'overrun_days': (today - planned_end).days,
            })
    return overdue


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
_FINAL_STATUSES = {'Zakończony', 'Wstrzymany'}

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
    overdue_milestone_projects: List[Dict] = []
    on_time_count = 0
    in_progress_count = 0

    for proj in projects:
        status = _normalize_status(proj.get('status'))
        # project_status='DONE' jest priorytetowy nad checkboxem status - RM_MANAGER
        # potrafi zostawic stary status-checkbox (np. "Przyjety") mimo ze projekt
        # zostal juz oznaczony jako zakonczony (spojne z _project_status_label()
        # w stats_project_summary.py).
        if proj.get('project_status') == 'DONE':
            status = 'Zakończony'
        by_status[status] = by_status.get(status, 0) + 1

        pid = proj['project_id']
        skip_delays = status in _FINAL_STATUSES or status in _NOT_STARTED_STATUSES
        # 'delays' = surowa lista etapow z minietym terminem - przydatna do
        # zobaczenia CO konkretnie sie slizga, ale pojedynczy spozniony etap
        # niekoniecznie zagraza calemu projektowi (moze miec bufor gdzie indziej,
        # nie byc na sciezce krytycznej). Do KLASYFIKACJI projektu jako
        # "opozniony" uzywamy wiec CPM/forecast (overall_variance_days) -
        # tej samej miary co zakladka Podsumowanie, zeby obie byly spojne.
        # Overrun_days per etap liczymy TEZ wzgledem forecast (nie surowego
        # planu bazowego) - inaczej etap po poslizgu wczesniejszych faz
        # pokazywal myląco duzy overrun niezgodny z Odchyleniem w RM_MANAGER
        # (patrz docstring _project_delays).
        stage_forecast = None
        if not skip_delays:
            try:
                forecast_inputs = db.project_forecast_inputs(pid)
                if not forecast_inputs.get('error'):
                    stage_forecast = recalculate_forecast(forecast_inputs)
            except Exception:
                stage_forecast = None
        project_delays = [] if skip_delays else _project_delays(db, pid, today, status, stage_forecast)

        # is_paused pochodzi z tabeli project_pauses (otwarty wpis) i jest
        # NIEZALEZNE od statusu tekstowego 'Wstrzymany' - projekt moze byc w
        # pauzie majac status np. 'Przyjety'. Taki projekt tez nie jest realnym
        # alarmem, wiec traktujemy pauze jak skip_delays (is_delayed=False).
        is_paused = False
        underlying_variance = 0
        if skip_delays:
            is_delayed = False
        else:
            summary = build_project_summary(db, proj)
            is_paused = bool(summary.get('is_paused'))
            underlying_variance = summary.get('overall_variance_days', 0)
            is_delayed = (
                not summary.get('error')
                and not is_paused
                and underlying_variance > 5
            )

        # Przeterminowane milestone'y odbiorowe (FAT/ODBIOR_x/SAT) - osobna
        # kategoria, celowo NIEwliczana do is_delayed (patrz komentarz przy
        # _overdue_milestones) - to inny rodzaj sygnalu niz "harmonogram sie
        # slizga", nie miesza sie z klasyfikacja CPM.
        milestones = [] if skip_delays else _overdue_milestones(db, pid, today)
        if milestones:
            overdue_milestone_projects.append({
                'project_id': pid,
                'name': proj.get('name'),
                'status': status,
                'milestones': milestones,
            })

        row = {
            'project_id': pid,
            'name': proj.get('name'),
            'priority': proj.get('priority'),
            'status': status,
            'is_delayed': is_delayed,
            # Pauza (project_pauses) + pierwotne odchylenie, zeby UI pokazalo
            # "WSTRZYMANY (opoznienie +Xd)" zamiast czerwonego OPOZNIONY.
            'is_paused': is_paused,
            'underlying_variance_days': underlying_variance,
            'delays': project_delays,
            # Poprawki to normalny, zaplanowany etap (ma wlasny budzet czasu
            # w harmonogramie) - CPM slusznie NIE traktuje go jako opoznienie
            # dopoki miesci sie w oknie. Ale sam fakt bycia w tej fazie to
            # dodatkowy sygnal "wymaga uwagi" (cos wymagalo poprawy po
            # pierwszym odbiorze) - niezalezny od klasyfikacji is_delayed.
            'needs_attention': status == 'Poprawki',
            # Karta maszyny (stage_attachments, etap PRZYJETY) - ta sama
            # funkcja co przycisk "Karta maszyny" w Osi czasu RM_MANAGER.
            'has_machine_card': bool(db.stage_attachments(pid, 'PRZYJETY')),
        }
        all_projects.append(row)

        if status not in _FINAL_STATUSES:
            in_progress_count += 1

        if is_delayed:
            delayed_projects.append(row)
        elif status not in _FINAL_STATUSES:
            # on_time_count ma sumowac sie z delayed_count do in_progress_count
            # (obie karty licza tylko projekty w toku) - zakonczony/wstrzymany
            # projekt nie jest ani "na czas" ani "opozniony", po prostu juz go
            # nie ma w tej puli (analogicznie do karty "Aktywne projekty").
            on_time_count += 1

    # Sortuj wg najwiekszego overrun_days w liscie etapow, jesli jest -
    # is_delayed pochodzi teraz z CPM i moze byc True bez zadnego wpisu w
    # 'delays' (np. opoznienie wynika z zaleznosci miedzy etapami, nie z
    # pojedynczego przekroczonego terminu), wiec max() na pustej liscie
    # bylby bledem - takie przypadki ladujemy na koniec (0).
    delayed_projects.sort(
        key=lambda p: max((d['overrun_days'] for d in p['delays']), default=0), reverse=True,
    )
    all_projects.sort(key=lambda p: (not p['is_delayed'], p.get('priority') or 99, p.get('name') or ''))
    by_status = dict(sorted(by_status.items(), key=lambda kv: _status_sort_key(kv[0])))
    overdue_milestone_projects.sort(
        key=lambda p: max(m['overrun_days'] for m in p['milestones']), reverse=True,
    )

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
        # Przeterminowane milestone'y odbiorowe (FAT/ODBIOR_x/SAT) - osobna
        # kategoria niezalezna od CPM/is_delayed, patrz _overdue_milestones.
        'overdue_milestone_count': len(overdue_milestone_projects),
        'overdue_milestone_projects': overdue_milestone_projects,
        'today': today.isoformat(),
    }


def build_project_list(db: RMStatsDB) -> Dict:
    """Zakladka "Lista projektow" - wszystkie projekty w kolejnosci jak
    lista rozwijana PROJEKT: w RM_MANAGER (project_sort_key, NIE
    priorytet/opoznienia jak w Status projektow), z kolumnami: Karta
    maszyny, Notatki i zalaczniki, Aktualny etap, Stan (zielony/czerwony/
    ostrzezenie). Reuzywa te same dane co build_status_overview (all_projects
    juz ma wszystkie potrzebne pola), tylko re-sortuje."""
    overview = build_status_overview(db)
    rows = list(overview['all_projects'])
    rows.sort(key=lambda p: project_sort_key(p.get('name')))

    overdue_milestones_by_pid = {
        p['project_id']: len(p['milestones']) for p in overview['overdue_milestone_projects']
    }

    for row in rows:
        pid = row['project_id']
        # has_notes = to samo co pokazuje modal "Wszystkie notatki i
        # zalaczniki" (bez etapu PRZYJETY - to osobna kolumna Karta maszyny):
        # czy jest jakikolwiek temat z notatkami, lub zalacznik innego etapu.
        topics = db.stage_topics(pid)
        has_any_note = any(t.get('notes') for t in topics)
        other_attachments = [a for a in db.stage_attachments(pid) if a.get('stage_code') != 'PRZYJETY']
        row['has_notes'] = has_any_note or bool(other_attachments)
        # Przeterminowane odbiory FAT/SAT - osobny sygnal ostrzegawczy,
        # niezalezny od is_delayed/needs_attention (patrz _overdue_milestones).
        row['overdue_milestones_count'] = overdue_milestones_by_pid.get(pid, 0)

    return {
        'rows': rows,
        'today': overview['today'],
    }
