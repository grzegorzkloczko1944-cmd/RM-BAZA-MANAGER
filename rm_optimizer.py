"""
============================================================================
RM_OPTIMIZER — Optymalizator produkcji oparty na Google OR-Tools CP-SAT
============================================================================
Wymagania:
    pip install ortools

Dwa tryby:
    1. fit_projects  — wciśnij wybrane projekty w istniejący harmonogram
    2. optimize_all  — przeoptymalizuj całą produkcję w przedziale czasowym

Algorytm:
    - Zmienne decyzyjne: dzień startu każdego etapu (w dniach roboczych od epoch)
    - Ograniczenia:
        a) Zależności wewnątrz-projektowe (FS/SS + lag)
        b) Zasoby: exclusive_person (1 pracownik = max N projektów naraz)
        c) Zasoby: max_concurrent_category (cała kategoria = max N projektów naraz)
        d) Niedostępność pracowników (urlopy, L4)
        e) Zamrożone etapy (zakończone / aktywne — stałe daty)
    - Cel: minimize makespan (dzień zakończenia ostatniego etapu)

Zależność od rm_manager.py:
    - STAGE_TO_PREFERRED_CATEGORY
    - get_projects_scheduling_data()
    - get_working_days()
    - apply_optimization_result()
    - save_optimization_run()
============================================================================
"""

import time as _time
from datetime import datetime, timedelta, date as dt_date
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict

# OR-Tools import — graceful fallback
try:
    from ortools.sat.python import cp_model
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False
    print("⚠️  ortools niedostępny — pip install ortools")

# Import stałych z rm_manager (lazy — unikamy circular)
_STAGE_TO_PREFERRED_CATEGORY = None

def _get_stage_category_map():
    global _STAGE_TO_PREFERRED_CATEGORY
    if _STAGE_TO_PREFERRED_CATEGORY is None:
        from rm_manager import STAGE_TO_PREFERRED_CATEGORY
        _STAGE_TO_PREFERRED_CATEGORY = STAGE_TO_PREFERRED_CATEGORY
    return _STAGE_TO_PREFERRED_CATEGORY


# Etapy-milestones (bez czasu trwania, bez pracowników)
MILESTONE_STAGES = {
    'PRZYJETY', 'TRANSPORT', 'URUCHOMIENIE_U_KLIENTA', 'FAT',
    'ODBIOR_1', 'ODBIOR_2', 'ODBIOR_3', 'ZAKONCZONY',
}


# ============================================================================
# HELPER: Kalendarz dni roboczych
# ============================================================================

class WorkingDayCalendar:
    """Mapowanie między datami kalendarzowymi a numerami dni roboczych.
    
    Umożliwia solverowi operowanie na indeksach dni roboczych (0, 1, 2, ...),
    a potem konwersję wyników z powrotem na daty ISO.
    """

    def __init__(self, working_days: List[str]):
        """working_days: posortowana lista dat ISO ('2026-01-05', ...)"""
        self._days = sorted(working_days)
        self._date_to_idx = {d: i for i, d in enumerate(self._days)}
        self._idx_to_date = {i: d for i, d in enumerate(self._days)}

    @property
    def total_days(self) -> int:
        return len(self._days)

    def date_to_index(self, iso_date: str) -> Optional[int]:
        """Konwertuj datę ISO na index dnia roboczego.
        
        Jeśli data nie jest dniem roboczym, zwróć najbliższy następny dzień roboczy.
        """
        if iso_date in self._date_to_idx:
            return self._date_to_idx[iso_date]
        # Znajdź najbliższy dzień roboczy >= iso_date
        for i, d in enumerate(self._days):
            if d >= iso_date:
                return i
        # Poza zakresem — zwróć ostatni dzień
        return len(self._days) - 1 if self._days else 0

    def index_to_date(self, idx: int) -> str:
        """Konwertuj index dnia roboczego na datę ISO."""
        idx = max(0, min(idx, len(self._days) - 1))
        return self._idx_to_date.get(idx, self._days[-1] if self._days else '2026-01-01')

    def working_duration(self, start_idx: int, calendar_days: int) -> int:
        """Ile dni roboczych mieści się w 'calendar_days' dniach kalendarzowych
        licząc od start_idx?"""
        if start_idx >= len(self._days):
            return max(1, calendar_days)
        start_date = datetime.fromisoformat(self._days[start_idx]).date()
        end_date = start_date + timedelta(days=calendar_days)
        count = 0
        for d in self._days[start_idx:]:
            if datetime.fromisoformat(d).date() > end_date:
                break
            count += 1
        return max(1, count)

    def calendar_days_for_working(self, start_idx: int, working_days: int) -> int:
        """Ile dni kalendarzowych potrzeba na 'working_days' dni roboczych
        licząc od start_idx?"""
        end_idx = min(start_idx + working_days - 1, len(self._days) - 1)
        if start_idx >= len(self._days) or end_idx < 0:
            return working_days
        d0 = datetime.fromisoformat(self._days[start_idx]).date()
        d1 = datetime.fromisoformat(self._days[end_idx]).date()
        return (d1 - d0).days

    def is_employee_available(self, employee_id: int, day_idx: int,
                              unavailable_periods: List[Dict]) -> bool:
        """Sprawdź czy pracownik jest dostępny danego dnia roboczego."""
        if day_idx >= len(self._days):
            return True
        day_iso = self._days[day_idx]
        for period in unavailable_periods:
            if period['employee_id'] != employee_id:
                continue
            if period['date_from'] <= day_iso <= period['date_to']:
                return False
        return True


# ============================================================================
# GŁÓWNA KLASA: ProductionOptimizer
# ============================================================================

class ProductionOptimizer:
    """Optymalizator produkcji — wrapper na CP-SAT Solver."""

    def __init__(self, scheduling_data: Dict, calendar: WorkingDayCalendar):
        """
        Args:
            scheduling_data: wynik get_projects_scheduling_data()
            calendar: WorkingDayCalendar z listą dni roboczych
        """
        self.data = scheduling_data
        self.cal = calendar
        self.model = None
        self.solver = None

        # Zmienne decyzyjne — wypełniane w _build_model
        # {(project_id, stage_code): cp_model.IntVar}
        self._start_vars: Dict[Tuple[int, str], any] = {}
        self._end_vars: Dict[Tuple[int, str], any] = {}
        self._duration_vars: Dict[Tuple[int, str], int] = {}
        self._frozen_values: Dict[Tuple[int, str], Tuple[int, int]] = {}  # key → (start_idx, end_idx)
        self._target_keys: Set[Tuple[int, str]] = set()  # etapy faktycznie optymalizowalne (nie zamrożone)

        # Wynik
        self.result: Optional[Dict] = None

    def optimize(self, mode: str = 'fit_projects',
                 target_project_ids: List[int] = None,
                 frozen_project_ids: List[int] = None,
                 time_limit_seconds: int = 30,
                 ignore_staff: bool = False) -> Dict:
        """Uruchom optymalizację.
        
        Args:
            mode: 'fit_projects' lub 'optimize_all'
            target_project_ids: projekty do optymalizacji (tryb fit)
            frozen_project_ids: projekty zamrożone (tryb fit)
            time_limit_seconds: max czas solvera
            ignore_staff: jeśli True — pomijaj ograniczenia pracowników
                          (exclusive_person + availability)
            
        Returns:
            {
                'status': 'OPTIMAL' | 'FEASIBLE' | 'INFEASIBLE' | 'ERROR',
                'solver_time_ms': int,
                'score_before': float,  # makespan przed
                'score_after': float,   # makespan po
                'changes': {
                    project_id: {
                        stage_code: {
                            'old_start': str, 'old_end': str,
                            'new_start': str, 'new_end': str,
                        }
                    }
                },
                'message': str,
            }
        """
        if not ORTOOLS_AVAILABLE:
            return {
                'status': 'ERROR',
                'message': 'ortools niedostępny — uruchom: pip install ortools',
                'solver_time_ms': 0,
                'changes': {},
            }

        if not self.data.get('projects'):
            return {
                'status': 'ERROR',
                'message': 'Brak danych projektów do optymalizacji',
                'solver_time_ms': 0,
                'changes': {},
            }

        if self.cal.total_days < 2:
            return {
                'status': 'ERROR',
                'message': 'Za mało dni roboczych w kalendarzu',
                'solver_time_ms': 0,
                'changes': {},
            }

        all_pids = list(self.data['projects'].keys())

        if mode == 'fit_projects':
            target = set(target_project_ids or [])
            frozen = set(frozen_project_ids or []) | (set(all_pids) - target)
        else:
            # optimize_all — wszystko jest target
            target = set(all_pids)
            frozen = set()

        # Sprawdź przypisania pracowników do target projektów
        if not ignore_staff:
            missing_staff_projects = []
            for pid in target:
                if pid not in self.data['projects']:
                    continue
                pdata = self.data['projects'][pid]
                # Sprawdź czy choć 1 nie-milestone etap ma przypisanego pracownika
                non_milestone_staff = {
                    sc: emps for sc, emps in pdata.get('staff', {}).items()
                    if sc not in MILESTONE_STAGES
                }
                has_any_staff = any(len(emps) > 0 for emps in non_milestone_staff.values())
                counts = {sc: len(e) for sc, e in non_milestone_staff.items()}
                print(f"⚡ staff_check pid={pid}: "
                      f"staff_keys={list(non_milestone_staff.keys())}, "
                      f"has_any={has_any_staff}, "
                      f"counts={counts}")
                if not has_any_staff:
                    missing_staff_projects.append(pid)
            
            if missing_staff_projects:
                pids_str = ', '.join(str(p) for p in sorted(missing_staff_projects))
                return {
                    'status': 'ERROR',
                    'message': (
                        f"⚠️ Projekty bez przypisanych pracowników: {pids_str}\n\n"
                        f"W trybie z ograniczeniami pracowników, etapy muszą mieć "
                        f"przypisanych pracowników.\n\n"
                        f"Rozwiązania:\n"
                        f"  1. Przypisz pracowników do etapów projektu\n"
                        f"  2. Użyj trybu '🚫 Bez ograniczeń pracowników'"
                    ),
                    'solver_time_ms': 0,
                    'changes': {},
                }

        t0 = _time.time()
        try:
            self._build_model(target, frozen, ignore_staff=ignore_staff)

            # Jeśli 0 etapów target → nie ma sensu uruchamiać solvera
            if not self._target_keys:
                return {
                    'status': 'ERROR',
                    'message': (
                        '⚠️ Brak etapów do optymalizacji.\n\n'
                        'Wszystkie etapy wybranych projektów są już zakończone '
                        'lub aktywne (zamrożone). Solver nie ma czego przesunąć.\n\n'
                        'Wybierz projekt z zaplanowanymi (nierozpoczętymi) etapami.'
                    ),
                    'solver_time_ms': int((_time.time() - t0) * 1000),
                    'changes': {},
                }

            status_str = self._solve(time_limit_seconds)
            if status_str in ('OPTIMAL', 'FEASIBLE'):
                changes = self._extract_result(target)
                score_before = self._calc_makespan_before(target)
                score_after = self._calc_makespan_after(target)
            else:
                changes = {}
                score_before = self._calc_makespan_before(target)
                score_after = score_before
        except Exception as e:
            return {
                'status': 'ERROR',
                'message': f'Błąd solvera: {e}',
                'solver_time_ms': int((_time.time() - t0) * 1000),
                'changes': {},
            }

        elapsed_ms = int((_time.time() - t0) * 1000)

        return {
            'status': status_str,
            'solver_time_ms': elapsed_ms,
            'score_before': score_before,
            'score_after': score_after,
            'changes': changes,
            'message': self._status_message(status_str, changes, elapsed_ms),
        }

    # ================================================================
    # BUILD MODEL
    # ================================================================

    def _build_model(self, target_pids: Set[int], frozen_pids: Set[int],
                     ignore_staff: bool = False):
        """Zbuduj model CP-SAT."""
        self.model = cp_model.CpModel()
        horizon = self.cal.total_days

        projects = self.data['projects']
        constraints_list = self.data.get('constraints', [])
        availability_list = self.data.get('availability', [])
        employees = self.data.get('employees', {})

        # Dolna granica dla target stages = DZIŚ
        # Solver nie może planować etapów w przeszłości — inaczej szablony
        # rozjadą się z prognozą (forecast wie że "dziś" to dziś).
        today_iso = datetime.now().date().isoformat()
        today_idx = self.cal.date_to_index(today_iso)
        print(f"⚡ build_model: today={today_iso}, today_idx={today_idx}")

        # --- 1. Zmienne decyzyjne: start i end każdego etapu ---
        frozen_stages = 0
        target_stages = 0
        for pid, pdata in projects.items():
            for sc, sinfo in pdata['stages'].items():
                # Pomijaj milestones — nie mają czasu trwania
                if sc in MILESTONE_STAGES:
                    continue
                dur = self._stage_duration_working(pid, sc)
                key = (pid, sc)
                self._duration_vars[key] = dur

                # Zamrożone etapy (zakończone / aktywne / projekt zamrożony)
                is_frozen = (
                    pid in frozen_pids
                    or sinfo.get('is_actual')
                    or sinfo.get('is_active')
                )

                if is_frozen:
                    fixed_start = self._get_fixed_start(pid, sc)
                    if fixed_start == 0 and not self._has_any_date(pid, sc):
                        # Etap zamrożony BEZ jakichkolwiek dat — pomijamy go
                        # (fixed_start=0 to artefakt, nie prawdziwa data)
                        continue
                    fixed_end = min(fixed_start + dur, horizon - 1)
                    sv = self.model.NewConstant(fixed_start)
                    ev = self.model.NewConstant(fixed_end)
                    self._frozen_values[key] = (fixed_start, fixed_end)
                    frozen_stages += 1
                else:
                    # Target: nie wcześniej niż DZIŚ
                    sv = self.model.NewIntVar(today_idx, horizon - 1, f's_{pid}_{sc}')
                    ev = self.model.NewIntVar(today_idx, horizon - 1, f'e_{pid}_{sc}')
                    # end = start + duration
                    self.model.Add(ev == sv + dur)
                    self._target_keys.add(key)
                    target_stages += 1

                self._start_vars[key] = sv
                self._end_vars[key] = ev

        print(f"⚡ build_model: {target_stages} etapów target, {frozen_stages} zamrożonych, horizon={horizon}")

        if target_stages == 0:
            print("⚠️  UWAGA: 0 etapów target! Wszystkie etapy target-projektów są zamrożone "
                  "(is_actual/is_active). Solver nie ma czego optymalizować.")

        # --- 2. Ograniczenia zależności wewnątrz-projektowych ---
        dep_count = 0
        dep_skipped = 0
        dep_dedup = 0
        for pid, pdata in projects.items():
            # Deduplikacja: baza może mieć wielokrotne wpisy tych samych zależności
            seen_deps = set()
            for dep in pdata['dependencies']:
                # Wsteczna kompatybilność: stare krotki 4-elementowe (bez lag_percent)
                if len(dep) == 5:
                    pred, succ, dep_type, lag, lag_pct = dep
                else:
                    pred, succ, dep_type, lag = dep
                    lag_pct = 0
                dep_sig = (pred, succ, dep_type)
                if dep_sig in seen_deps:
                    dep_dedup += 1
                    continue
                seen_deps.add(dep_sig)

                pred_key = (pid, pred)
                succ_key = (pid, succ)
                if pred_key not in self._start_vars or succ_key not in self._start_vars:
                    continue

                # Pomiń zależności w których OBA etapy są zamrożone
                pred_frozen = (
                    pid in frozen_pids
                    or pdata['stages'].get(pred, {}).get('is_actual')
                    or pdata['stages'].get(pred, {}).get('is_active')
                )
                succ_frozen = (
                    pid in frozen_pids
                    or pdata['stages'].get(succ, {}).get('is_actual')
                    or pdata['stages'].get(succ, {}).get('is_active')
                )
                if pred_frozen and succ_frozen:
                    dep_skipped += 1
                    continue

                # SS lag — ZASADY 2026-04-29:
                #   • lag_days  : klasyczny SS lag (succ.start >= pred.start + lag_days)
                #   • lag_pct   : INTERPRETACJA „min(pred, succ)" (Propozycja A) —
                #                 lag_pct = % pracy poprzednika która musi minąć,
                #                 czyli MAX overlap = (100 - lag_pct)% × min(pred_dur, succ_dur).
                #                 Symetryczne: następnik nie wjeżdża głębiej niż X%
                #                 KRÓTSZEGO z dwóch etapów. Eliminuje patologie gdy
                #                 etapy mają drastycznie różne długości
                #                 (np. ELEKTROMONTAZ 10 wd vs URUCHOMIENIE 5 wd).
                # Dla FS lag_pct jest ignorowany.
                lag_working = max(0, lag)
                if dep_type == 'FS':
                    self.model.Add(
                        self._start_vars[succ_key] >= self._end_vars[pred_key] + lag_working
                    )
                    dep_count += 1
                elif dep_type == 'SS':
                    # Klasyczny SS lag (start succ ≥ start pred + lag_days)
                    self.model.Add(
                        self._start_vars[succ_key] >= self._start_vars[pred_key] + lag_working
                    )
                    # Limit overlap = floor((100 - lag_pct)% × min(pred_dur, succ_dur))
                    # FLOOR (zamiast ceil) — bardziej restrykcyjne, dla małych
                    # etapów nadaje 0 wd overlap, eliminując efekt weekendu
                    # (1 wd robocze = pt→pn = 3 dni kalendarzowe = wizualnie
                    # cały krótki pasek).
                    if lag_pct and 0 < int(lag_pct) <= 100:
                        pred_dur = int(self._duration_vars.get(pred_key, 1))
                        succ_dur = int(self._duration_vars.get(succ_key, 1))
                        min_dur = max(1, min(pred_dur, succ_dur))
                        max_overlap_pct = 100 - int(lag_pct)
                        # floor(min_dur * max_overlap_pct / 100)
                        max_overlap = (min_dur * max_overlap_pct) // 100
                        # succ.start ≥ pred.end − max_overlap
                        self.model.Add(
                            self._start_vars[succ_key]
                            >= self._end_vars[pred_key] - max_overlap
                        )
                    dep_count += 1

        print(f"⚡ build_model: {dep_count} zależności dodanych, {dep_skipped} pominiętych (frozen-frozen), {dep_dedup} zdeduplikowanych")

        # Debug: pokaż aktywne zależności target projektów
        for pid in target_pids:
            if pid not in projects:
                continue
            pdata = projects[pid]
            all_deps = pdata.get('dependencies', [])
            print(f"⚡ pid={pid}: {len(all_deps)} zależności w bazie, etapy w modelu: "
                  f"{[sc for sc in pdata['stages'] if (pid, sc) in self._start_vars]}")
            seen = set()
            for dep in all_deps:
                if len(dep) == 5:
                    pred, succ, dep_type, lag, lag_pct = dep
                else:
                    pred, succ, dep_type, lag = dep
                    lag_pct = 0
                sig = (pred, succ, dep_type)
                if sig in seen:
                    continue
                seen.add(sig)
                pred_key = (pid, pred)
                succ_key = (pid, succ)
                in_model = pred_key in self._start_vars and succ_key in self._start_vars
                status = "✅ ADDED" if in_model else f"⏭️ SKIP (pred_ok={pred_key in self._start_vars}, succ_ok={succ_key in self._start_vars})"
                lag_str = f"lag={lag}" + (f"+{lag_pct}%" if lag_pct else "")
                print(f"⚡   dep pid={pid}: {pred} --{dep_type}({lag_str})--> {succ}  {status}")

        # --- 3. Ograniczenia zasobów ---
        if ignore_staff:
            # Tryb bez pracowników: pomijamy exclusive_person, zostawiamy max_concurrent_*
            non_staff_constraints = [c for c in constraints_list
                                     if c['constraint_type'] != 'exclusive_person']
            print(f"⚡ ignore_staff=True: pomijam exclusive_person, zostało {len(non_staff_constraints)} ograniczeń")
            self._add_resource_constraints(non_staff_constraints, employees,
                                           target_pids, frozen_pids)
        else:
            self._add_resource_constraints(constraints_list, employees,
                                           target_pids, frozen_pids)

        # --- 4. Ograniczenia niedostępności pracowników ---
        if not ignore_staff:
            self._add_availability_constraints(availability_list, target_pids)
        else:
            print("⚡ ignore_staff=True: pomijam ograniczenia niedostępności pracowników")

        # --- 5. Reguła biznesowa: pracownik = max 1 projekt jednocześnie ---
        # Dotyczy WSZYSTKICH przypisanych pracowników (konstruktor, monter,
        # serwisant itp.). Jeśli pracownik jest przypisany do etapów w różnych
        # projektach, te etapy nie mogą się nakładać.
        # Działa ZAWSZE (niezależnie od ignore_staff) — to fizyczne ograniczenie.
        self._add_person_exclusivity_constraints(target_pids, frozen_pids)

        # --- 6. Cel: ważona suma końców projektów (priorytety) + makespan tiebreaker ---
        # Dla każdego projektu obliczamy max(end_vars jego etapów) = project_end_p.
        # Funkcja celu = Σ_p weight_p × project_end_p + makespan
        # gdzie weight_p pochodzi z mapy priorytetów (Turbo=100, Pilny=10, Normalny=1).
        # Dzięki temu projekty Turbo są pchane jak najwcześniej (mała wartość end_p
        # × duża waga = duży zysk z przesuwania w lewo).
        priority_weights = self.data.get('priority_weights', {1: 100, 2: 10, 3: 1})
        # Bezpieczne odzyskanie dla brakujących wartości
        def _w_for(prio):
            try:
                return max(1, int(priority_weights.get(int(prio), 1)))
            except Exception:
                return 1

        weighted_terms = []
        all_target_ends = []
        for pid in target_pids:
            if pid not in projects:
                continue
            pdata = projects[pid]
            prio = pdata.get('priority', 3)
            w = _w_for(prio)

            # Końce wszystkich etapów target tego projektu
            project_ends = []
            for sc in pdata['stages']:
                key = (pid, sc)
                if key in self._end_vars:
                    project_ends.append(self._end_vars[key])

            if not project_ends:
                continue

            all_target_ends.extend(project_ends)

            # project_end_p = max(end_vars)
            project_end_var = self.model.NewIntVar(
                0, self.cal.total_days, f'project_end_p{pid}'
            )
            self.model.AddMaxEquality(project_end_var, project_ends)
            weighted_terms.append(w * project_end_var)

            print(f"⚡ priorytet pid={pid}: {prio} (waga={w})")

        if weighted_terms:
            # makespan jako delikatny tiebreaker (waga 1) — zachęca solver do
            # nieprzeciągania harmonogramu nawet dla projektów Normalnych
            makespan = self.model.NewIntVar(0, self.cal.total_days, 'makespan')
            self.model.AddMaxEquality(makespan, all_target_ends)
            self.model.Minimize(sum(weighted_terms) + makespan)

    def _add_resource_constraints(self, constraints_list: List[Dict],
                                  employees: Dict,
                                  target_pids: Set[int],
                                  frozen_pids: Set[int]):
        """Dodaj ograniczenia zasobów — exclusive_person i max_concurrent.
        
        WAŻNE: Ograniczenia dotyczą tylko interwałów, w których co najmniej jeden
        jest z target (optymalizowalny). Zamrożone-vs-zamrożone pomijamy —
        ich dat nie da się zmienić, a jeśli już się nakładają, wymuszanie
        NoOverlap/Cumulative uczyniłoby model sprzecznym (INFEASIBLE).
        """
        STAGE_TO_PREFERRED_CATEGORY = _get_stage_category_map()

        projects = self.data['projects']

        # Mapuj employee_id → category
        emp_category = {eid: e.get('category', '') for eid, e in employees.items()}

        def _make_intervals_with_target_filter(stage_keys_list):
            """Buduj interwały, ale uwzględniaj je tylko gdy choć 1 jest target.
            
            Dla Cumulative: wrzucamy target + frozen (frozen jako stałe blokady).
            Dla NoOverlap: pary frozen-frozen pomijamy (optional intervals).
            Zwraca: (intervals, demands, has_any_target)
            """
            intervals = []
            demands = []
            has_target = False
            for pid, sc in stage_keys_list:
                key = (pid, sc)
                if key not in self._start_vars:
                    continue
                dur = self._duration_vars[key]
                is_target = key in self._target_keys
                if is_target:
                    has_target = True
                interval = self.model.NewIntervalVar(
                    self._start_vars[key], dur, self._end_vars[key],
                    f'rsrc_{pid}_{sc}'
                )
                intervals.append((interval, is_target, pid, sc))
                demands.append(1)
            return intervals, demands, has_target

        for constraint in constraints_list:
            ctype = constraint['constraint_type']
            cat = constraint.get('category')
            stage_filter = constraint.get('stage_code')
            max_par = constraint.get('max_parallel', 1)

            if ctype == 'exclusive_person':
                relevant_stage_codes = set()
                if stage_filter:
                    relevant_stage_codes.add(stage_filter)
                else:
                    for sc, cats in STAGE_TO_PREFERRED_CATEGORY.items():
                        if cat in cats:
                            relevant_stage_codes.add(sc)

                if not relevant_stage_codes:
                    continue

                emp_stages: Dict[int, List[Tuple[int, str]]] = defaultdict(list)
                for pid, pdata in projects.items():
                    for sc in relevant_stage_codes:
                        if sc not in pdata['stages']:
                            continue
                        assigned = pdata['staff'].get(sc, [])
                        for eid in assigned:
                            if emp_category.get(eid) == cat:
                                emp_stages[eid].append((pid, sc))

                for eid, stage_keys in emp_stages.items():
                    if len(stage_keys) <= max_par:
                        continue

                    # Filtruj: pomiń jeśli same frozen
                    has_any_target = any((pid, sc) in self._target_keys for pid, sc in stage_keys)
                    if not has_any_target:
                        continue

                    if max_par == 1:
                        # Sprawdź czy zamrożone interwały już się nakładają
                        frozen_keys = [(p, s) for p, s in stage_keys
                                       if (p, s) not in self._target_keys]
                        frozen_overlap = self._max_frozen_overlap(frozen_keys)

                        if frozen_overlap > max_par:
                            # Frozen nakładają się — globalny NoOverlap byłby sprzeczny.
                            # Strategia: (a) NoOverlap wśród targetów,
                            #            (b) każdy target omija każdy frozen pairwise.
                            target_here = [(p, s) for p, s in stage_keys
                                           if (p, s) in self._target_keys]
                            frozen_here = [(p, s) for p, s in stage_keys
                                           if (p, s) not in self._target_keys
                                           and (p, s) in self._frozen_values]
                            if len(target_here) > 1:
                                t_ivs = []
                                for p, s in target_here:
                                    k = (p, s)
                                    d = self._duration_vars.get(k, 1)
                                    t_ivs.append(self.model.NewIntervalVar(
                                        self._start_vars[k], d, self._end_vars[k],
                                        f'iv_{eid}_{p}_{s}'))
                                self.model.AddNoOverlap(t_ivs)
                            for p_t, s_t in target_here:
                                k_t = (p_t, s_t)
                                for p_f, s_f in frozen_here:
                                    f_s, f_e = self._frozen_values[(p_f, s_f)]
                                    b = self.model.NewBoolVar(
                                        f'xavd_{eid}_{p_t}_{s_t}_{p_f}')
                                    self.model.Add(
                                        self._end_vars[k_t] <= f_s
                                    ).OnlyEnforceIf(b)
                                    self.model.Add(
                                        self._start_vars[k_t] >= f_e
                                    ).OnlyEnforceIf(b.Not())
                            print(f"⚠️  exclusive_person(eid={eid}, cat={cat}): "
                                  f"frozen overlap={frozen_overlap}, "
                                  f"NoOverlap wśród {len(target_here)} targetów + "
                                  f"{len(frozen_here)} unikań frozen")
                        else:
                            # Normalnie: NoOverlap z frozen jako stałe blokady
                            intervals = []
                            for pid, sc in stage_keys:
                                key = (pid, sc)
                                if key not in self._start_vars:
                                    continue
                                dur = self._duration_vars.get(key, 1)
                                is_target = key in self._target_keys
                                if is_target:
                                    interval = self.model.NewIntervalVar(
                                        self._start_vars[key], dur, self._end_vars[key],
                                        f'iv_{eid}_{pid}_{sc}'
                                    )
                                else:
                                    pres = self.model.NewConstant(1)
                                    interval = self.model.NewOptionalIntervalVar(
                                        self._start_vars[key], dur, self._end_vars[key],
                                        pres, f'iv_{eid}_{pid}_{sc}'
                                    )
                                intervals.append((interval, is_target))
                            target_intervals = [iv for iv, is_t in intervals if is_t]
                            frozen_intervals = [iv for iv, is_t in intervals if not is_t]
                            all_relevant = target_intervals + frozen_intervals
                            if len(target_intervals) > 0 and len(all_relevant) > 1:
                                self.model.AddNoOverlap(all_relevant)
                    else:
                        intervals = []
                        demands = []
                        for pid, sc in stage_keys:
                            key = (pid, sc)
                            if key not in self._start_vars:
                                continue
                            dur = self._duration_vars.get(key, 1)
                            interval = self.model.NewIntervalVar(
                                self._start_vars[key], dur, self._end_vars[key],
                                f'iv_{eid}_{pid}_{sc}'
                            )
                            intervals.append(interval)
                            demands.append(1)
                        if intervals:
                            frozen_overlap = self._max_frozen_overlap(
                                [(p, s) for p, s in stage_keys if (p, s) not in self._target_keys])
                            if frozen_overlap <= max_par:
                                self.model.AddCumulative(intervals, demands, max_par)
                            else:
                                print(f"⚠️  Pomijam exclusive_person(eid={eid}, max={max_par}): "
                                      f"frozen overlap={frozen_overlap}")

            elif ctype == 'max_concurrent_category':
                relevant_stage_codes = set()
                if stage_filter:
                    relevant_stage_codes.add(stage_filter)
                else:
                    for sc, cats in STAGE_TO_PREFERRED_CATEGORY.items():
                        if cat in cats:
                            relevant_stage_codes.add(sc)

                # Zbierz wszystkie etapy tej kategorii
                all_stage_keys = []
                for pid, pdata in projects.items():
                    for sc in relevant_stage_codes:
                        if sc not in pdata['stages']:
                            continue
                        all_stage_keys.append((pid, sc))

                # Pomijamy jeśli same frozen — nie da się naprawić
                has_any_target = any((pid, sc) in self._target_keys for pid, sc in all_stage_keys)
                if not has_any_target:
                    continue

                # Cumulative: frozen interwały wliczamy jako stałe blokady,
                # ale tylko te które mają zmienne (nie odfiltrowane wcześniej)
                intervals = []
                demands = []
                for pid, sc in all_stage_keys:
                    key = (pid, sc)
                    if key not in self._start_vars:
                        continue
                    dur = self._duration_vars.get(key, 1)
                    interval = self.model.NewIntervalVar(
                        self._start_vars[key], dur, self._end_vars[key],
                        f'cat_iv_{cat}_{pid}_{sc}'
                    )
                    intervals.append(interval)
                    demands.append(1)
                if intervals:
                    # Sprawdź: frozen interwały nie mogą same przekraczać limitu
                    # (jeśli tak, pomijamy constraint bo jest nierozwiązywalny)
                    frozen_count_at_any_time = self._max_frozen_overlap(
                        [(pid, sc) for pid, sc in all_stage_keys if (pid, sc) not in self._target_keys])
                    if frozen_count_at_any_time <= max_par:
                        self.model.AddCumulative(intervals, demands, max_par)
                    else:
                        print(f"⚠️  Pomijam max_concurrent_category({cat}={max_par}): "
                              f"zamrożone etapy już mają {frozen_count_at_any_time} nakładających się")

            elif ctype == 'max_concurrent_stage':
                if not stage_filter:
                    continue

                all_stage_keys = []
                for pid, pdata in projects.items():
                    if stage_filter not in pdata['stages']:
                        continue
                    all_stage_keys.append((pid, stage_filter))

                has_any_target = any((pid, sc) in self._target_keys for pid, sc in all_stage_keys)
                if not has_any_target:
                    continue

                intervals = []
                demands = []
                for pid, sc in all_stage_keys:
                    key = (pid, sc)
                    if key not in self._start_vars:
                        continue
                    dur = self._duration_vars.get(key, 1)
                    interval = self.model.NewIntervalVar(
                        self._start_vars[key], dur, self._end_vars[key],
                        f'stg_iv_{stage_filter}_{pid}'
                    )
                    intervals.append(interval)
                    demands.append(1)
                if intervals:
                    frozen_count_at_any_time = self._max_frozen_overlap(
                        [(pid, sc) for pid, sc in all_stage_keys if (pid, sc) not in self._target_keys])
                    if frozen_count_at_any_time <= max_par:
                        self.model.AddCumulative(intervals, demands, max_par)
                    else:
                        print(f"⚠️  Pomijam max_concurrent_stage({stage_filter}={max_par}): "
                              f"zamrożone etapy już mają {frozen_count_at_any_time} nakładających się")

    def _add_person_exclusivity_constraints(self, target_pids: Set[int],
                                             frozen_pids: Set[int]):
        """Reguła biznesowa: master-pracownik = max N etapów jednocześnie.

        Działa ZAWSZE (niezależnie od ignore_staff) — to fizyczne ograniczenie.

        Zasady:
        - Z listy pracowników etapu bierzemy TYLKO pierwszego (master).
          Drugi i kolejni to slave/pomocnicy — nie blokują harmonogramu.
        - KOMPLETACJA jest wyjątkiem: logistyk może prowadzić wiele
          kompletacji równolegle.
        - Globalny limit per master = employees[eid]['master_max_parallel']
          (domyślnie 1). Liczy się sumarycznie po wszystkich projektach
          i typach etapów (poza MILESTONE i PARALLEL_STAGES).
        - LINIE PRODUKCYJNE: jeśli kilka projektów należy do tej samej linii,
          a etap jest w `parallel_stages` linii — etapy te traktujemy jako
          JEDNĄ czynność (kompozytowy interwał: start = min, end = max),
          bo serwisant uruchamia całą linię równolegle.
        """
        PARALLEL_STAGES = {'KOMPLETACJA'}  # etapy bez ograniczenia per-person

        projects = self.data['projects']
        employees = self.data.get('employees', {}) or {}

        # Mapowanie: pid -> (line_id, set(parallel_stages_for_line))
        # Tylko linie z >= 2 projektami w modelu mają sens (1 projekt = nic
        # nie zmienia). Optymalizator traktuje pids z linii jak grupę.
        production_lines = self.data.get('production_lines', []) or []
        pid_to_line: Dict[int, Tuple[int, Set[str]]] = {}
        for line in production_lines:
            line_id = int(line.get('id', 0))
            line_pids = [int(p) for p in line.get('project_ids', [])]
            line_pids_in_model = [p for p in line_pids if p in projects]
            if len(line_pids_in_model) < 2:
                continue
            parallel_set = set(line.get('parallel_stages', []) or [])
            if not parallel_set:
                continue
            for p in line_pids_in_model:
                pid_to_line[p] = (line_id, parallel_set)

        # Grupuj wg master_eid -> [(pid, sc), ...] (across all stages)
        emp_stage_map: Dict[int, List[Tuple[int, str]]] = defaultdict(list)

        for pid, pdata in projects.items():
            for sc, assigned in pdata['staff'].items():
                if sc in MILESTONE_STAGES or sc in PARALLEL_STAGES:
                    continue
                if not assigned:
                    continue
                key = (pid, sc)
                if key not in self._start_vars:
                    continue
                master_eid = assigned[0]  # pierwszy = master
                emp_stage_map[master_eid].append((pid, sc))

        constraints_added = 0
        skipped_frozen = 0
        skipped_all_frozen = 0
        line_groups_merged = 0

        def _build_interval_for_group(group_label: str, members: List[Tuple[int, str]]):
            """Zwróć IntervalVar reprezentujący jedną „czynność" mastera.

            Dla single member: zwykły IntervalVar po istniejących start/end.
            Dla wielu (kompozyt linii): start=min(starts), end=max(ends),
            size=end-start. Master jest uznany za zajętego przez cały rozstaw.
            """
            if len(members) == 1:
                p, s = members[0]
                k = (p, s)
                d = self._duration_vars.get(k, 1)
                return self.model.NewIntervalVar(
                    self._start_vars[k], d, self._end_vars[k], group_label
                )
            horizon = self.cal.total_days
            starts = [self._start_vars[(p, s)] for p, s in members]
            ends = [self._end_vars[(p, s)] for p, s in members]
            cs = self.model.NewIntVar(0, horizon, group_label + '_s')
            ce = self.model.NewIntVar(0, horizon, group_label + '_e')
            sz = self.model.NewIntVar(0, horizon, group_label + '_z')
            self.model.AddMinEquality(cs, starts)
            self.model.AddMaxEquality(ce, ends)
            self.model.Add(sz == ce - cs)
            return self.model.NewIntervalVar(cs, sz, ce, group_label)

        def _group_stage_keys(stage_keys: List[Tuple[int, str]]):
            """Podziel etapy mastera na grupy kompozytowe (per-linia, per-etap).

            Zwraca listę (group_id, members) gdzie:
            - dla etapów linii: group_id = ('LINE', line_id, sc), members > 1
            - dla pozostałych: group_id = ('SOLO', pid, sc), members = 1
            """
            groups: Dict[Tuple, List[Tuple[int, str]]] = defaultdict(list)
            for p, s in stage_keys:
                line_info = pid_to_line.get(p)
                if line_info and s in line_info[1]:
                    groups[('LINE', line_info[0], s)].append((p, s))
                else:
                    groups[('SOLO', p, s)].append((p, s))
            return list(groups.items())

        for eid, stage_keys in emp_stage_map.items():
            # Limit z bazy (domyślnie 1)
            emp_row = employees.get(eid) or employees.get(str(eid)) or {}
            try:
                max_parallel = int(emp_row.get('master_max_parallel', 1) or 1)
            except (TypeError, ValueError):
                max_parallel = 1
            if max_parallel < 1:
                max_parallel = 1

            if len(stage_keys) <= max_parallel:
                continue

            # Pomiń jeśli same frozen
            has_target = any((pid, sc) in self._target_keys for pid, sc in stage_keys)
            if not has_target:
                pids_in_group = sorted({p for p, _ in stage_keys})
                print(f"⚠️  person_excl(eid={eid}, max={max_parallel}): pomiń — WSZYSTKIE "
                      f"{len(stage_keys)} etapy zamrożone (is_actual/is_active) "
                      f"w projektach {pids_in_group}.")
                skipped_all_frozen += 1
                continue

            # Sprawdź frozen overlap (max liczba zamrożonych nakładających się jednocześnie)
            frozen_overlap = self._max_frozen_overlap(
                [(p, s) for p, s in stage_keys if (p, s) not in self._target_keys])

            if frozen_overlap > max_parallel:
                # Zamrożone same przekraczają limit — globalny Cumulative byłby sprzeczny.
                # Dla max_parallel=1 robimy strategię pairwise (NoOverlap targetów +
                # unikanie każdego frozen przez każdy target).
                # Dla max_parallel>1 — pomijamy z ostrzeżeniem.
                # UWAGA: w tej gałęzi grupowanie linii pomijamy — frozen
                # mają i tak stałe daty, a target-target traktujemy klasycznie.
                target_here = [(p, s) for p, s in stage_keys
                               if (p, s) in self._target_keys]
                frozen_here = [(p, s) for p, s in stage_keys
                               if (p, s) not in self._target_keys
                               and (p, s) in self._frozen_values]

                if max_parallel == 1 and target_here:
                    if len(target_here) > 1:
                        t_ivs = []
                        for p, s in target_here:
                            k = (p, s)
                            d = self._duration_vars.get(k, 1)
                            t_ivs.append(self.model.NewIntervalVar(
                                self._start_vars[k], d, self._end_vars[k],
                                f'pex_{eid}_{p}_{s}'))
                        self.model.AddNoOverlap(t_ivs)
                        constraints_added += 1

                    for p_t, s_t in target_here:
                        k_t = (p_t, s_t)
                        for p_f, s_f in frozen_here:
                            f_s, f_e = self._frozen_values[(p_f, s_f)]
                            b = self.model.NewBoolVar(
                                f'pavd_{eid}_{p_t}_{s_t}_{p_f}_{s_f}')
                            self.model.Add(
                                self._end_vars[k_t] <= f_s
                            ).OnlyEnforceIf(b)
                            self.model.Add(
                                self._start_vars[k_t] >= f_e
                            ).OnlyEnforceIf(b.Not())

                    print(f"⚠️  person_excl(eid={eid}, max=1): "
                          f"frozen overlap={frozen_overlap}, "
                          f"NoOverlap wśród {len(target_here)} targetów + "
                          f"{len(frozen_here)} unikań frozen")
                else:
                    print(f"⚠️  Pomijam person_excl(eid={eid}, max={max_parallel}): "
                          f"zamrożone etapy już mają {frozen_overlap} nakładających się")
                    skipped_frozen += 1
                continue

            # Standardowo: Cumulative z capacity = max_parallel.
            # Dla max_parallel=1 to równoważne NoOverlap.
            # Etapy linii grupujemy w 1 kompozytowy interwał (start=min, end=max).
            grouped = _group_stage_keys(stage_keys)
            intervals = []
            demands = []
            for gkey, members in grouped:
                if len(members) > 1:
                    line_groups_merged += 1
                    label = f'pex_line_{eid}_{gkey[1]}_{gkey[2]}'
                else:
                    p, s = members[0]
                    label = f'pex_{eid}_{p}_{s}'
                intervals.append(_build_interval_for_group(label, members))
                demands.append(1)

            if len(intervals) > 1:
                if max_parallel == 1:
                    self.model.AddNoOverlap(intervals)
                else:
                    self.model.AddCumulative(intervals, demands, max_parallel)
                constraints_added += 1

        print(f"⚡ person_exclusivity: {constraints_added} ograniczeń master-cap "
              f"({skipped_frozen} pominięte przez frozen, "
              f"{skipped_all_frozen} pominięte all-frozen, "
              f"{line_groups_merged} kompozytów linii)")

    def _add_availability_constraints(self, availability_list: List[Dict],
                                      target_pids: Set[int]):
        """Dodaj ograniczenia niedostępności pracowników.
        
        Jeśli pracownik jest niedostępny w określonym okresie,
        to żaden etap przypisany do niego nie może się w tym czasie odbywać.
        """
        projects = self.data['projects']

        # Grupuj unavailability po pracowniku
        emp_unavail: Dict[int, List[Dict]] = defaultdict(list)
        for av in availability_list:
            emp_unavail[av['employee_id']].append(av)

        for pid in target_pids:
            if pid not in projects:
                continue
            pdata = projects[pid]
            for sc, assigned_ids in pdata['staff'].items():
                key = (pid, sc)
                if key not in self._start_vars:
                    continue
                # Pomijaj zamrożone etapy (is_actual/is_active) — stałych dat nie zmienimy
                if key not in self._target_keys:
                    continue
                for eid in assigned_ids:
                    if eid not in emp_unavail:
                        continue
                    for period in emp_unavail[eid]:
                        ua_start = self.cal.date_to_index(period['date_from'])
                        ua_end = self.cal.date_to_index(period['date_to'])
                        if ua_start is None or ua_end is None:
                            continue
                        # Etap musi być PRZED unavailable lub PO nim
                        # before: end <= ua_start
                        # after:  start > ua_end
                        before = self.model.NewBoolVar(
                            f'bef_{pid}_{sc}_{eid}_{period["id"]}'
                        )
                        self.model.Add(
                            self._end_vars[key] <= ua_start
                        ).OnlyEnforceIf(before)
                        self.model.Add(
                            self._start_vars[key] > ua_end
                        ).OnlyEnforceIf(before.Not())

    # ================================================================
    # HELPER: Max overlap zamrożonych interwałów
    # ================================================================

    def _max_frozen_overlap(self, frozen_stage_keys: list) -> int:
        """Oblicz max liczbę zamrożonych interwałów nakładających się jednocześnie.
        
        Jeśli zamrożone etapy już przekraczają limit Cumulative, 
        constraint jest nierozwiązywalny i należy go pominąć.
        """
        if not frozen_stage_keys:
            return 0
        events = []  # (time, +1/-1)
        for pid, sc in frozen_stage_keys:
            key = (pid, sc)
            if key not in self._frozen_values:
                continue
            s, e = self._frozen_values[key]
            events.append((s, 1))
            events.append((e, -1))
        if not events:
            return 0
        events.sort(key=lambda x: (x[0], -x[1]))
        max_overlap = 0
        current = 0
        for _, delta in events:
            current += delta
            max_overlap = max(max_overlap, current)
        return max_overlap

    # ================================================================
    # HELPER: Czas trwania etapu w dniach roboczych
    # ================================================================

    def _stage_duration_working(self, pid: int, sc: str) -> int:
        """Oblicz czas trwania etapu w dniach roboczych.
        
        WAŻNE: duration_days z bazy to dni KALENDARZOWE (template_end - template_start).
        Przeliczamy na dni robocze używając kalendarza, by uniknąć narastania
        czasu trwania przy wielokrotnych optymalizacjach.
        """
        pdata = self.data['projects'].get(pid, {})
        sinfo = pdata.get('stages', {}).get(sc, {})

        # Jeśli etap zakończony — weź actual duration z kalendarza
        if sinfo.get('is_actual') and sinfo.get('actual_start') and sinfo.get('actual_end'):
            start_str = sinfo['actual_start'][:10]
            end_str = sinfo['actual_end'][:10]
            return self._count_working_days_between(start_str, end_str)

        # Przelicz z template dat (kalendarzowe → robocze)
        t_start = sinfo.get('template_start')
        t_end = sinfo.get('template_end')
        if t_start and t_end:
            return self._count_working_days_between(t_start[:10], t_end[:10])

        # Fallback: duration_days z bazy / domyślne 5
        cal_days = sinfo.get('duration_days', 5)
        return max(1, int(cal_days * 5 / 7))

    def _count_working_days_between(self, start_iso: str, end_iso: str) -> int:
        """Policz dni robocze między dwiema datami ISO (włącznie z końcami)."""
        start_idx = self.cal.date_to_index(start_iso)
        end_idx = self.cal.date_to_index(end_iso)
        if start_idx is not None and end_idx is not None:
            return max(1, end_idx - start_idx)
        # Fallback: przybliżenie 5/7
        try:
            d0 = datetime.fromisoformat(start_iso).date()
            d1 = datetime.fromisoformat(end_iso).date()
            cal_days = (d1 - d0).days
            return max(1, int(cal_days * 5 / 7))
        except (ValueError, TypeError):
            return 5

    def _has_any_date(self, pid: int, sc: str) -> bool:
        """Sprawdź czy etap ma jakąkolwiek datę (template/forecast/actual)."""
        pdata = self.data['projects'].get(pid, {})
        sinfo = pdata.get('stages', {}).get(sc, {})
        forecast = pdata.get('forecast', {}).get(sc, {})
        for field in ['actual_start', 'actual_end', 'forecast_start', 
                       'forecast_end', 'template_start', 'template_end']:
            val = sinfo.get(field) or forecast.get(field)
            if val:
                return True
        return False

    def _get_fixed_start(self, pid: int, sc: str) -> int:
        """Pobierz zamrożony start_index dla etapu (actual lub template)."""
        pdata = self.data['projects'].get(pid, {})
        sinfo = pdata.get('stages', {}).get(sc, {})
        forecast = pdata.get('forecast', {}).get(sc, {})

        # Prioritet: actual > forecast > template
        for field in ['actual_start', 'forecast_start', 'template_start']:
            val = sinfo.get(field) or forecast.get(field)
            if val:
                date_str = val[:10] if len(val) > 10 else val
                idx = self.cal.date_to_index(date_str)
                if idx is not None:
                    return idx

        return 0

    # ================================================================
    # SOLVE
    # ================================================================

    def _solve(self, time_limit_seconds: int) -> str:
        """Uruchom solver, zwróć status."""
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = time_limit_seconds
        self.solver.parameters.num_workers = 4  # paralelizm

        status = self.solver.Solve(self.model)

        status_map = {
            cp_model.OPTIMAL: 'OPTIMAL',
            cp_model.FEASIBLE: 'FEASIBLE',
            cp_model.INFEASIBLE: 'INFEASIBLE',
            cp_model.MODEL_INVALID: 'ERROR',
            cp_model.UNKNOWN: 'UNKNOWN',
        }
        return status_map.get(status, 'UNKNOWN')

    # ================================================================
    # EXTRACT RESULT
    # ================================================================

    def _extract_result(self, target_pids: Set[int]) -> Dict:
        """Wyciągnij nowe daty z rozwiązania solvera."""
        changes = {}
        projects = self.data['projects']

        for pid in target_pids:
            if pid not in projects:
                continue
            pdata = projects[pid]
            pid_changes = {}

            for sc, sinfo in pdata['stages'].items():
                key = (pid, sc)
                if key not in self._start_vars:
                    continue

                # Pomiń zamrożone (actual/active)
                if sinfo.get('is_actual') or sinfo.get('is_active'):
                    continue

                new_start_idx = self.solver.Value(self._start_vars[key])
                new_end_idx = self.solver.Value(self._end_vars[key])

                new_start_date = self.cal.index_to_date(new_start_idx)
                new_end_date = self.cal.index_to_date(new_end_idx)

                print(f"⚡ result pid={pid} {sc}: idx={new_start_idx}..{new_end_idx} → {new_start_date}..{new_end_date}")

                old_start = sinfo.get('template_start', '')
                old_end = sinfo.get('template_end', '')

                # Zapisz zmianę tylko jeśli daty się zmieniły
                if new_start_date != old_start or new_end_date != old_end:
                    pid_changes[sc] = {
                        'old_start': old_start,
                        'old_end': old_end,
                        'new_start': new_start_date,
                        'new_end': new_end_date,
                    }

            if pid_changes:
                changes[pid] = pid_changes

        return changes

    def _calc_makespan_before(self, target_pids: Set[int]) -> float:
        """Oblicz makespan (max end) PRZED optymalizacją (z forecast)."""
        max_end = 0
        projects = self.data['projects']
        for pid in target_pids:
            pdata = projects.get(pid, {})
            for sc, fc in pdata.get('forecast', {}).items():
                end = fc.get('forecast_end')
                if end:
                    idx = self.cal.date_to_index(str(end)[:10])
                    if idx is not None and idx > max_end:
                        max_end = idx
        return max_end

    def _calc_makespan_after(self, target_pids: Set[int]) -> float:
        """Oblicz makespan PO optymalizacji (z rozwiązania solvera)."""
        max_end = 0
        projects = self.data['projects']
        for pid in target_pids:
            if pid not in projects:
                continue
            for sc in projects[pid]['stages']:
                key = (pid, sc)
                if key in self._end_vars:
                    val = self.solver.Value(self._end_vars[key])
                    if val > max_end:
                        max_end = val
        return max_end

    def _status_message(self, status: str, changes: Dict, elapsed_ms: int) -> str:
        """Wygeneruj czytelny komunikat o wyniku."""
        if status == 'OPTIMAL':
            total = sum(len(v) for v in changes.values())
            return (f"✅ Znaleziono optymalne rozwiązanie w {elapsed_ms}ms. "
                    f"Zmieniono {total} etapów w {len(changes)} projektach.")
        elif status == 'FEASIBLE':
            total = sum(len(v) for v in changes.values())
            return (f"✅ Znaleziono dopuszczalne rozwiązanie w {elapsed_ms}ms "
                    f"(może nie być optymalne). "
                    f"Zmieniono {total} etapów w {len(changes)} projektach.")
        elif status == 'INFEASIBLE':
            return ("❌ Brak rozwiązania — ograniczenia są sprzeczne. "
                    "Sprawdź: za mało pracowników, za krótki horyzont, "
                    "lub niemożliwe do spełnienia zależności.")
        else:
            return f"⚠️ Solver zakończył ze statusem: {status} ({elapsed_ms}ms)"


# ============================================================================
# PUBLICZNE API — uruchamiane z GUI
# ============================================================================

def run_optimization(rm_manager_dir: str, rm_master_db_path: str,
                     mode: str, target_project_ids: List[int],
                     frozen_project_ids: List[int] = None,
                     date_range: Tuple[str, str] = None,
                     time_limit_seconds: int = 30,
                     ignore_staff: bool = False,
                     master_db_path: str = None) -> Dict:
    """Główna funkcja — uruchom optymalizację.

    Args:
        rm_manager_dir: katalog RM_MANAGER (z bazami per-projekt)
        rm_master_db_path: ścieżka do rm_manager.sqlite
        mode: 'fit_projects' lub 'optimize_all'
        target_project_ids: projekty do optymalizacji
        frozen_project_ids: projekty zamrożone (None = reszta auto-frozen w trybie fit)
        date_range: (start_iso, end_iso) — zakres dat, None = auto (dziś + 365 dni)
        time_limit_seconds: max czas solvera
        ignore_staff: pomijaj ograniczenia pracowników (exclusive_person + availability)
        master_db_path: ścieżka do master.sqlite (potrzebne do priorytetów projektów)

    Returns:
        Dict z wynikiem (patrz ProductionOptimizer.optimize())
    """
    import rm_manager

    # 1. Ustal zakres dat
    if date_range:
        date_from, date_to = date_range
    else:
        today = datetime.now().date()
        date_from = (today - timedelta(days=30)).isoformat()  # trochę w przeszłość (zamrożone etapy)
        date_to = (today + timedelta(days=365)).isoformat()

    # 2. Pobierz dane
    all_pids = list(target_project_ids or [])
    if frozen_project_ids:
        all_pids = list(set(all_pids) | set(frozen_project_ids))

    print(f"⚡ run_optimization: rm_manager_dir={rm_manager_dir}")
    print(f"⚡ run_optimization: all_pids={all_pids}")

    # Auto-migracja zależności workflow: usuń wycofane (DEPRECATED) i upewnij
    # się że wszystkie default workflow są obecne (z aktualnym lag_percent).
    # Bez tego stare bazy projektów trzymają np. MONTAZ→ELEKTROMONTAZ z lag=0
    # zamiast 75% i nie mają ELEKTROMONTAZ→URUCHOMIENIE.
    for pid in all_pids:
        try:
            db_path = rm_manager.get_project_db_path(rm_manager_dir, pid)
            rm_manager.remove_deprecated_dependencies_for_project(db_path, pid)
            rm_manager.ensure_default_dependencies_for_project(db_path, pid)
        except Exception as e:
            print(f"⚠️  Auto-migracja zależności pid={pid} pominięta: {e}")

    data = rm_manager.get_projects_scheduling_data(
        rm_manager_dir, rm_master_db_path, all_pids,
        master_db_path=master_db_path,
    )

    print(f"⚡ run_optimization: projects loaded={list(data.get('projects', {}).keys())}")
    print(f"⚡ run_optimization: constraints={len(data.get('constraints', []))}")
    print(f"⚡ run_optimization: employees={len(data.get('employees', {}))}")

    # 3. Zbuduj kalendarz dni roboczych
    working_days = rm_manager.get_working_days(rm_master_db_path, date_from, date_to)
    if not working_days:
        return {
            'status': 'ERROR',
            'message': 'Brak dni roboczych w podanym zakresie',
            'solver_time_ms': 0,
            'changes': {},
        }
    calendar = WorkingDayCalendar(working_days)

    # 4. Optymalizuj
    optimizer = ProductionOptimizer(data, calendar)
    result = optimizer.optimize(
        mode=mode,
        target_project_ids=target_project_ids,
        frozen_project_ids=frozen_project_ids,
        time_limit_seconds=time_limit_seconds,
        ignore_staff=ignore_staff,
    )

    # 5. Zapisz przebieg
    try:
        rm_manager.save_optimization_run(rm_master_db_path, {
            'run_mode': mode,
            'project_ids': target_project_ids,
            'date_range_start': date_from,
            'date_range_end': date_to,
            'constraints_snapshot': data.get('constraints', []),
            'result': result.get('changes', {}),
            'score_before': result.get('score_before'),
            'score_after': result.get('score_after'),
            'solver_status': result.get('status'),
            'solver_time_ms': result.get('solver_time_ms'),
        })
    except Exception as e:
        print(f"⚠️ Nie udało się zapisać historii optymalizacji: {e}")

    return result


def apply_optimization(rm_manager_dir: str, rm_master_db_path: str,
                       changes: Dict, run_id: int = None,
                       user: str = None) -> Dict:
    """Zastosuj wynik optymalizacji — nadpisz template daty w bazach projektów.
    
    Args:
        changes: wynik z optimize() — {pid: {stage_code: {new_start, new_end, ...}}}
        run_id: ID rekordu optimization_runs (jeśli mamy)
        user: kto stosuje
    
    Returns:
        {'applied_projects': int, 'applied_stages': int, 'errors': list,
         'snapshots': {pid: snapshot_dict}}
    """
    import rm_manager

    applied_projects = 0
    applied_stages = 0
    errors = []
    snapshots = {}

    for pid, stage_changes in changes.items():
        pid = int(pid)
        stage_dates = {}
        for sc, info in stage_changes.items():
            stage_dates[sc] = (info['new_start'], info['new_end'])

        try:
            # Snapshot przed zmianą — do cofania
            snapshots[pid] = rm_manager.snapshot_before_optimization(
                rm_manager_dir, pid, list(stage_dates.keys()))

            rm_manager.apply_optimization_result(rm_manager_dir, pid, stage_dates)
            # Przelicz prognozę po zmianie szablonów — synchronizacja template ↔ forecast
            try:
                db_path = rm_manager.get_project_db_path(rm_manager_dir, pid)
                rm_manager.recalculate_forecast(db_path, pid)
            except Exception as fe:
                print(f"⚠️ Nie udało się przeliczyć prognozy pid={pid}: {fe}")
            applied_projects += 1
            applied_stages += len(stage_dates)
        except Exception as e:
            errors.append(f"Projekt {pid}: {e}")

    # Oznacz run jako zastosowany
    if run_id:
        try:
            rm_manager.mark_optimization_applied(rm_master_db_path, run_id, user)
        except Exception:
            pass

    return {
        'applied_projects': applied_projects,
        'applied_stages': applied_stages,
        'errors': errors,
        'snapshots': snapshots,
    }


def undo_optimization(rm_manager_dir: str, snapshots: Dict) -> Dict:
    """Cofnij optymalizację — przywróć daty sprzed zastosowania.

    Args:
        snapshots: {pid: {stage_code: {template_start, template_end, staff: [...]}}}

    Returns:
        {'restored_projects': int, 'errors': list}
    """
    import rm_manager

    restored = 0
    errors = []
    for pid, snapshot in snapshots.items():
        pid = int(pid)
        try:
            rm_manager.restore_optimization_snapshot(rm_manager_dir, pid, snapshot)
            try:
                db_path = rm_manager.get_project_db_path(rm_manager_dir, pid)
                rm_manager.recalculate_forecast(db_path, pid)
            except Exception:
                pass
            restored += 1
        except Exception as e:
            errors.append(f"Projekt {pid}: {e}")
    return {'restored_projects': restored, 'errors': errors}


def check_ortools_available() -> bool:
    """Sprawdź czy OR-Tools jest zainstalowany."""
    return ORTOOLS_AVAILABLE
