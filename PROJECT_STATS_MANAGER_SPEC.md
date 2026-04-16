# RM_MANAGER - Specyfikacja zarządzania statusami (Advanced)

## Cel
Zaawansowane zarządzanie cyklami statusów projektów z obsługą:
- **Multi-period tracking** - statusy mogą wracać wielokrotnie (PROJEKT: 01-05, 12-14, 18-19)
- **Pauzy** - automatyczne wykrywanie przerw w pracy
- **Dependency graph** - zależności w standardzie PM (FS, SS)
- **Automatic forecasting** - przeliczanie całego timeline na podstawie rzeczywistości
- **Topological sort** - prawidłowa kolejność obliczeń w grafie
- **Critical path analysis** - identyfikacja kluczowych ścieżek projektu

---

## Architektura (2 systemy)

### System 1: RM_BAZA - WIZUALIZACJA (read-only dla użytkowników)

**MASTER.SQLITE** (centralna, LAN):
```
projects
├─ project_id, name, designer
├─ status (TEXT) - uproszczony status dla wizualizacji
└─ "PROJEKT", "MONTAŻ", "URUCHOMIENIE" - dla użytkowników RM_BAZA

project_statuses (multi-status z checkboxami)
├─ project_id, status
└─ do kompatybilności wstecznej
```

**RM_BAZA_v15_MAG_STATS_ORG.py** - GUI tylko do ODCZYTU statusu:
```
✓ Pokazuje aktualny status projektu
✓ Checkboxy (read-only)
✗ NIE zarządza procesem
✗ NIE zmienia etapów
```

---

### System 2: RM_MANAGER - WŁAŚCIWE ZARZĄDZANIE

**RM_MANAGER.SQLITE** (centralna baza procesów):
```
stage_definitions     → definicje etapów (PROJEKT, MONTAZ, ...)
project_stages        → instancje etapów dla projektów
stage_schedule        → template (plan - "jak miało być")
stage_actual_periods  → rzeczywistość (WIELE okresów, powroty, pauzy)
stage_dependencies    → graf zależności (FS/SS)
stage_events          → zdarzenia (opcjonalnie)
```

**Lub per-project (jeśli wolisz rozproszoną):**
```
PROJEKT_X/PROCESS.SQLITE
└─ te same tabele, ale tylko dla jednego projektu
```

**rm_manager.py** - GUI do zarządzania procesami:
```
✓ START/END etapów
✓ Zarządzanie zależnościami
✓ Recalculate forecast
✓ Analiza critical path
✓ Aktualizuje status w MASTER.SQLITE dla RM_BAZA
```

---

### Przepływ danych

```
RM_MANAGER GUI (zarządzanie):
  User: [START MONTAŻ]
    ↓
  1. INSERT INTO stage_actual_periods (started_at = NOW)
    ↓
  2. recalculate_forecast(project_id)
    ↓
  3. determine_display_status() → "MONTAŻ"
    ↓
  4. UPDATE master.sqlite:
       SET status = 'MONTAŻ'
       WHERE project_id = 123
    ↓
  5. UPDATE project_statuses:
       ADD 'MONTAZ' (dla checkboxów)
    ↓
RM_BAZA GUI (wizualizacja):
  Pokazuje: status = "MONTAŻ" ✓
  Checkboxy: [x] MONTAŻ
```

**Kluczowa zasada:**
```
RM_MANAGER = source of truth (szczegóły)
         ↓
    sync status
         ↓
RM_BAZA = display only (uproszczony widok)
```

---

### Poziom aplikacji

**project_manager.py** (operacje na MASTER - tylko SYNC):
```
- sync_status_from_rm_manager(project_id, status)  → aktualizuje MASTER z RM_MANAGER
- get_project_status(project_id)                   → odczyt dla RM_BAZA
- get_project_statuses(project_id)                 → multi-status dla checkboxów
```

**rm_manager.py** (operacje na RM_MANAGER.SQLITE):
```
Inicjalizacja:
- init_project_schedule()           → inicjalizacja struktury projektu
- set_stage_dependency()            → definicja zależności (FS/SS)

Operacje:
- start_stage(project_id, stage)    → rozpoczęcie etapu (nowy okres)
- end_stage(project_id, stage)      → zakończenie etapu (zamknięcie okresu)
- get_active_stages(project_id)     → które etapy obecnie trwają

Analiza:
- recalculate_forecast(project_id)  → GŁÓWNA FUNKCJA - przelicza cały timeline
- get_stage_timeline(project_id)    → kompletny widok dla GUI
- determine_display_status()        → określa jaki status pokazać w RM_BAZA
- get_project_status_summary()      → "opóźniony o X dni", "on track"

Sync:
- sync_to_master(project_id)        → aktualizuje MASTER.SQLITE
```

---

## Schemat baz danych

### PROJECT_X/DATA.SQLITE

#### 1. STAGE_DEFINITIONS (słownik etapów - globalny)
```sql
CREATE TABLE stage_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    display_name TEXT,
    color TEXT
);
```

**Wypełnienie dla typowego projektu:**
```
INSERT INTO stage_definitions (code, display_name) VALUES
  ('PRZYJETY', 'Przyjęty'),
  ('PROJEKT', 'Projekt'),
  ('KOMPLETACJA', 'Kompletacja'),
  ('MONTAZ', 'Montaż'),
  ('AUTOMATYKA', 'Automatyka'),
  ('URUCHOMIENIE', 'Uruchomienie'),
  ('ODBIORY', 'Odbiory'),
  ('POPRAWKI', 'Poprawki'),
  ('WSTRZYMANY', 'Wstrzymany'),
  ('ZAKONCZONY', 'Zakończony');
```

#### 2. PROJECT_STAGES (instancje etapów dla projektu)
```sql
CREATE TABLE project_stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    stage_id INTEGER NOT NULL,
    sequence INTEGER,
    FOREIGN KEY (stage_id) REFERENCES stage_definitions(id)
);

CREATE INDEX idx_project_stages_project ON project_stages(project_id);
```

**Przykład:**
```
Dla project_id=123:
| id  | project_id | stage_id | sequence |
|-----|------------|----------|----------|
| 1   | 123        | 2        | 1        | -- PROJEKT
| 2   | 123        | 3        | 2        | -- KOMPLETACJA
| 3   | 123        | 4        | 3        | -- MONTAZ
| 4   | 123        | 5        | 3        | -- AUTOMATYKA (równoległy)
| 5   | 123        | 6        | 4        | -- URUCHOMIENIE
```

#### 3. STAGE_SCHEDULE (template - "jak miało być")
```sql
CREATE TABLE stage_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_stage_id INTEGER NOT NULL,
    template_start DATE NOT NULL,
    template_end DATE NOT NULL,
    notes TEXT,
    FOREIGN KEY (project_stage_id) REFERENCES project_stages(id) ON DELETE CASCADE
);

CREATE INDEX idx_stage_schedule_stage ON stage_schedule(project_stage_id);
```

**Przykład:**
```
| id | project_stage_id | template_start | template_end |
|----|------------------|----------------|--------------|
| 1  | 1 (PROJEKT)      | 2026-01-01     | 2026-01-05   |
| 2  | 2 (KOMPLETACJA)  | 2026-01-05     | 2026-01-10   |
| 3  | 3 (MONTAZ)       | 2026-01-10     | 2026-01-20   |
| 4  | 4 (AUTOMATYKA)   | 2026-01-12     | 2026-01-18   |
| 5  | 5 (URUCHOMIENIE) | 2026-01-20     | 2026-01-25   |
```

#### 4. STAGE_ACTUAL_PERIODS (rzeczywistość - KLUCZ, wiele okresów!)
```sql
CREATE TABLE stage_actual_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_stage_id INTEGER NOT NULL,
    started_at DATETIME NOT NULL,
    ended_at DATETIME,                    -- NULL = etap trwa
    started_by TEXT,
    ended_by TEXT,
    notes TEXT,
    FOREIGN KEY (project_stage_id) REFERENCES project_stages(id) ON DELETE CASCADE
);

CREATE INDEX idx_actual_periods_stage ON stage_actual_periods(project_stage_id, started_at);
CREATE INDEX idx_actual_periods_active ON stage_actual_periods(project_stage_id, ended_at);
```

**Przykład (PROJEKT wraca kilka razy!):**
```
| id | project_stage_id | started_at          | ended_at            |
|----|------------------|---------------------|---------------------|
| 1  | 1 (PROJEKT)      | 2026-01-01 08:00    | 2026-01-05 17:00    | -- 1. okres
| 2  | 2 (KOMPLETACJA)  | 2026-01-06 08:00    | 2026-01-11 12:00    |
| 3  | 1 (PROJEKT)      | 2026-01-12 09:00    | 2026-01-14 16:00    | -- PROJEKT wraca!
| 4  | 3 (MONTAZ)       | 2026-01-15 08:00    | NULL                | -- trwa
| 5  | 4 (AUTOMATYKA)   | 2026-01-15 10:00    | NULL                | -- równolegle
| 6  | 1 (PROJEKT)      | 2026-01-18 08:00    | 2026-01-19 15:00    | -- 3. okres!

Wykrywanie:
- PROJEKT trwał 3 razy: 01-05, 12-14, 18-19
- MONTAZ obecnie trwa (ended_at = NULL)
- AUTOMATYKA równocześnie z MONTAZEM
- Pauzy automatyczne (koniec okresu = pauza)
```

#### 5. STAGE_DEPENDENCIES (graf zależności - standard PM)
```sql
CREATE TABLE stage_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    predecessor_stage_id INTEGER NOT NULL,
    successor_stage_id INTEGER NOT NULL,
    dependency_type TEXT NOT NULL,        -- 'FS' lub 'SS'
    lag_days INTEGER DEFAULT 0,           -- opóźnienie (może być ujemne)
    FOREIGN KEY (predecessor_stage_id) REFERENCES project_stages(id) ON DELETE CASCADE,
    FOREIGN KEY (successor_stage_id) REFERENCES project_stages(id) ON DELETE CASCADE,
    CHECK (dependency_type IN ('FS', 'SS'))
);

CREATE INDEX idx_dependencies_project ON stage_dependencies(project_id);
CREATE INDEX idx_dependencies_pred ON stage_dependencies(predecessor_stage_id);
CREATE INDEX idx_dependencies_succ ON stage_dependencies(successor_stage_id);
```

**Typy zależności (standard PM):**

**FS (Finish-to-Start)** - domyślny, sekwencyjny:
```
A: ████████
            B: ████████
            ↑ B czeka na koniec A

Warunek: start(B) ≥ end(A) + lag_days
```

**SS (Start-to-Start)** - równoległy:
```
A: ████████████
   B: ████████
   ↑ B może zacząć gdy A zacznie

Warunek: start(B) ≥ start(A) + lag_days
```

**Przykład (Twój graf projektu):**
```
Definicja:
PROJEKT → KOMPLETACJA (FS)
KOMPLETACJA → MONTAZ (FS)
MONTAZ → AUTOMATYKA (SS)       ← równolegle!
MONTAZ → URUCHOMIENIE (FS)
AUTOMATYKA → URUCHOMIENIE (FS)
URUCHOMIENIE → ODBIORY (FS)
ODBIORY → POPRAWKI (FS)

Tabela:
| id | predecessor    | successor      | type | lag |
|----|----------------|----------------|------|-----|
| 1  | 1 (PROJEKT)    | 2 (KOMPLET)    | FS   | 0   |
| 2  | 2 (KOMPLET)    | 3 (MONTAZ)     | FS   | 0   |
| 3  | 3 (MONTAZ)     | 4 (AUTOMATYKA) | SS   | 2   | -- po 2 dniach montażu
| 4  | 3 (MONTAZ)     | 5 (URUCHOM)    | FS   | 0   |
| 5  | 4 (AUTOMATYKA) | 5 (URUCHOM)    | FS   | 0   |
| 6  | 5 (URUCHOM)    | 6 (ODBIORY)    | FS   | 0   |
| 7  | 6 (ODBIORY)    | 7 (POPRAWKI)   | FS   | 0   |
```

#### 6. STAGE_EVENTS (zdarzenia - opcjonalnie)
```sql
CREATE TABLE stage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_stage_id INTEGER NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT (datetime('now')),
    event_type TEXT NOT NULL,
    description TEXT,
    assigned_to TEXT,
    FOREIGN KEY (project_stage_id) REFERENCES project_stages(id) ON DELETE CASCADE,
    CHECK (event_type IN ('START', 'END', 'PAUSE', 'RESUME', 'ISSUE', 'RESOLVED', 'NOTE', 'DELAY'))
);

CREATE INDEX idx_events_stage ON stage_events(project_stage_id, timestamp DESC);
```

**Przykład:**
```
| id | project_stage_id | timestamp           | event_type | description              |
|----|------------------|---------------------|------------|--------------------------|
| 1  | 3 (MONTAZ)       | 2026-01-15 08:00    | START      | Rozpoczęty montaż         |
| 2  | 3 (MONTAZ)       | 2026-01-16 14:30    | ISSUE      | Brakuje śrub M12          |
| 3  | 3 (MONTAZ)       | 2026-01-16 16:00    | DELAY      | Opóźnienie dostawy        |
| 4  | 3 (MONTAZ)       | 2026-01-17 09:00    | RESOLVED   | Części dostarczone        |
```

---

## Logika zarządzania statusami

### 1. Rozpoczęcie etapu (w RM_MANAGER GUI)

```
User w RM_MANAGER GUI:
  Klik: [START MONTAŻ]

Krok 1: rm_manager.start_stage(project_id, "MONTAZ")
        ↓
        INSERT INTO stage_actual_periods (
          project_stage_id = X,
          started_at = NOW,
          ended_at = NULL,
          started_by = 'user@example.com'
        )

Krok 2: rm_manager.recalculate_forecast(project_id)
        ↓
        Topological sort + obliczenia zależności
        ↓
        Zwraca: forecast dla wszystkich etapów

Krok 3: rm_manager.determine_display_status(project_id)
        ↓
        Logika: "jaki status pokazać w RM_BAZA?"
        ↓
        Zwraca: "MONTAŻ" (bo MONTAŻ jest aktywny)

Krok 4: rm_manager.sync_to_master(project_id, "MONTAŻ")
        ↓
        UPDATE master.projects
        SET status = 'MONTAŻ', updated_at = NOW
        WHERE project_id = 123
        ↓
        DELETE FROM master.project_statuses WHERE project_id = 123
        INSERT INTO master.project_statuses (project_id, status)
        VALUES (123, 'MONTAZ')

Krok 5: RM_BAZA GUI automatycznie odświeża widok
        ↓
        Pokazuje: status = "MONTAŻ" w kolumnie
        Checkboxy: [x] MONTAZ
```

### 2. Zakończenie etapu (w RM_MANAGER GUI)

```
User w RM_MANAGER GUI:
  Klik: [END MONTAŻ]

Krok 1: rm_manager.end_stage(project_id, "MONTAZ")
        ↓
        UPDATE stage_actual_periods
        SET ended_at = NOW,
            ended_by = 'user@example.com'
        WHERE project_stage_id = X 
          AND ended_at IS NULL

Krok 2: rm_manager.calculate_variance(project_id, "MONTAZ")
        ↓
        actual_duration = ended_at - started_at
        planned_duration = template_end - template_start
        variance = actual_duration - planned_duration
        ↓
        Zapisuje variance w analityce

Krok 3: rm_manager.recalculate_forecast(project_id)
        ↓
        Przelicza forecast dla pozostałych etapów
        ↓
        Uwzględnia opóźnienie/przyśpieszenie

Krok 4: rm_manager.determine_display_status(project_id)
        ↓
        Sprawdza: które etapy są teraz aktywne?
        ↓
        Np. jeśli AUTOMATYKA trwa: status = "AUTOMATYKA"
        Np. jeśli nic nie trwa: status = ostatni zakończony

Krok 5: sync_to_master(project_id, nowy_status)
        ↓
        Aktualizuje MASTER.SQLITE dla RM_BAZA
```

### 3. Równoległe etapy

```
Scenariusz: MONTAŻ i AUTOMATYKA trwają równocześnie

RM_MANAGER:
  stage_actual_periods:
    | project_stage_id | started_at  | ended_at |
    |------------------|-------------|----------|
    | 3 (MONTAZ)       | 01-10 08:00 | NULL     | ← trwa
    | 4 (AUTOMATYKA)   | 01-12 09:00 | NULL     | ← trwa

  determine_display_status():
    Logika: "co pokazać gdy 2 etapy trwają?"
    
    Opcja A: Główny etap (większy priorytet)
      → status = "MONTAŻ" (priorytet wyższy)
    
    Opcja B: Ostatnio rozpoczęty
      → status = "AUTOMATYKA"
    
    Opcja C: Multi-status string
      → status = "MONTAŻ+AUTOMATYKA"

RM_BAZA:
  Pokazuje wybrany status (np. "MONTAŻ")
  Checkboxy:
    [x] MONTAZ
    [x] AUTOMATYKA
```

### 4. Powrót do etapu (PROJEKT wraca kilka razy)

```
Timeline:
  01-05: PROJEKT (1. raz)
  06-11: KOMPLETACJA
  12-14: PROJEKT (2. raz) ← wraca!
  15-20: MONTAŻ

RM_MANAGER:
  stage_actual_periods dla PROJEKT:
    | id | started_at  | ended_at    |
    |----|-------------|-------------|
    | 1  | 01-01 08:00 | 01-05 17:00 | ← 1. okres
    | 2  | 01-12 09:00 | 01-14 16:00 | ← 2. okres (powrót!)

  Każdy okres = osobny rekord
  Pauzy = automatyczne (koniec okresu)

RM_BAZA:
  Podczas 1. okresu: status = "PROJEKT"
  Podczas KOMPLETACJI: status = "KOMPLETACJA"
  Podczas 2. okresu: status = "PROJEKT" (znowu)
  
  Historia w RM_BAZA:
    01-05: PROJEKT
    06-11: KOMPLETACJA
    12-14: PROJEKT ← widać powrót
    15-20: MONTAŻ
```

### 5. Cascading effect (automatyczny w forecast)

```
Scenariusz: PROJEKT opóźniony o 2 dni

RM_MANAGER:
  Template (plan):
    PROJEKT:      01-05
    KOMPLETACJA:  05-10
    MONTAZ:       10-20

  Rzeczywistość:
    PROJEKT: 01-07 (opóźnienie +2)

  recalculate_forecast():
    1. Topological sort etapów
    2. Dla każdego etapu:
       a) Pobierz zależności (FS/SS)
       b) Oblicz earliest_start:
          earliest_start = max(
            template_start,
            max(końce predecessorów)
          )
       c) forecast_start = earliest_start
       d) forecast_end = forecast_start + duration

    Wynik:
      PROJEKT:      01-07 (actual +2)
      KOMPLETACJA:  07-12 (przesunięta o +2)
      MONTAZ:       12-22 (przesunięta o +2)

  System NIE wymaga ręcznego przesuwania!
  Forecast liczy się automatycznie na podstawie grafu.

RM_BAZA:
  Widzi tylko aktualny status
  Nie wie o opóźnieniach (to w RM_MANAGER)
```

---

## Funkcje rm_manager.py

### Inicjalizacja bazy danych
```python
def ensure_rm_manager_tables(rm_db_path):
    """Tworzy wszystkie tabele w RM_MANAGER.SQLITE jeśli nie istnieją
    
    Tworzy:
    - stage_definitions
    - project_stages
    - stage_schedule
    - stage_actual_periods
    - stage_dependencies
    - stage_events
    """
    pass

def init_project(rm_db_path, project_id, stages_config, dependencies_config):
    """Inicjalizuje nowy projekt w RM_MANAGER
    
    Args:
        project_id: ID projektu z MASTER.SQLITE
        stages_config: [
            {"code": "PROJEKT", "template_start": "2026-01-01", "template_end": "2026-01-05"},
            {"code": "MONTAZ", "template_start": "2026-01-05", "template_end": "2026-01-15"},
            ...
        ]
        dependencies_config: [
            {"from": "PROJEKT", "to": "KOMPLETACJA", "type": "FS", "lag": 0},
            {"from": "MONTAZ", "to": "AUTOMATYKA", "type": "SS", "lag": 2},
            ...
        ]
    """
    pass
```

### Operacje na etapach (START/END)
```python
def start_stage(rm_db_path, project_id, stage_code, started_by=None, notes=None):
    """Rozpoczyna nowy okres dla etapu (multi-period support!)
    
    Args:
        stage_code: 'PROJEKT', 'MONTAZ', etc.
        
    Returns:
        period_id: ID nowego rekordu w stage_actual_periods
    
    Uwaga: Można uruchomić ten sam etap kilka razy (powroty)
    """
    # INSERT INTO stage_actual_periods (started_at=NOW, ended_at=NULL)
    pass

def end_stage(rm_db_path, project_id, stage_code, ended_by=None, notes=None):
    """Kończy bieżący okres dla etapu
    
    Zamyka ostatni otwarty okres (ended_at=NULL)
    """
    # UPDATE stage_actual_periods SET ended_at=NOW WHERE ended_at IS NULL
    pass

def get_active_stages(rm_db_path, project_id):
    """Zwraca listę etapów które obecnie trwają
    
    Returns:
        [{"stage_code": "MONTAZ", "started_at": "2026-01-15 08:00", "period_id": 123}, ...]
    """
    # SELECT FROM stage_actual_periods WHERE ended_at IS NULL
    pass

def get_stage_periods(rm_db_path, project_id, stage_code):
    """Zwraca wszystkie okresy dla danego etapu (historia powrotów)
    
    Returns:
        [
            {"started_at": "2026-01-01 08:00", "ended_at": "2026-01-05 17:00"},
            {"started_at": "2026-01-12 09:00", "ended_at": "2026-01-14 16:00"},  # powrót
            ...
        ]
    """
    pass
```

### GŁÓWNA FUNKCJA: Forecast (topological sort + graph analysis)
```python
def recalculate_forecast(rm_db_path, project_id):
    """**SERCE SYSTEMU** - przelicza timeline całego projektu
    
    Algorytm:
        1. Pobiera graf zależności
        2. Topological sort (prawidłowa kolejność obliczeń)
        3. Dla każdego etapu:
           - Sprawdza zależności (FS/SS + lag)
           - Oblicza earliest_start na podstawie predecessorów
           - Oblicza forecast_end = earliest_start + duration
        4. Uwzględnia rzeczywiste okresy (stage_actual_periods)
    
    Returns:
        {
            "PROJEKT": {
                "template_start": "2026-01-01",
                "template_end": "2026-01-05",
                "forecast_start": "2026-01-01",
                "forecast_end": "2026-01-07",  # opóźniony o 2 dni
                "actual_periods": [{"started": ..., "ended": ...}],
                "variance_days": +2,
                "is_active": False
            },
            "MONTAZ": {
                ...
                "forecast_start": "2026-01-07",  # automatycznie przesunięty!
                ...
            }
        }
    
    Uwaga: 
        - Automatyczny cascading effect
        - Nie wymaga ręcznego przesuwania dat
        - Reaguje na rzeczywiste opóźnienia
    """
    pass

def calculate_critical_path(rm_db_path, project_id):
    """Identyfikuje critical path - ścieżkę krytyczną projektu
    
    Returns:
        ["PROJEKT", "KOMPLETACJA", "MONTAZ", "URUCHOMIENIE", "ODBIORY"]
    """
    pass
```

### Sync z MASTER.SQLITE (dla RM_BAZA)
```python
def determine_display_status(rm_db_path, project_id):
    """Określa jaki status pokazać w RM_BAZA (uproszczony)
    
    Logika:
        - Jeśli 1 etap aktywny → jego nazwa
        - Jeśli wiele aktywnych → etap z najwyższym priorytetem
        - Jeśli żaden nieaktywny → ostatnio zakończony
    
    Returns:
        "MONTAZ"  # string do wyświetlenia w RM_BAZA
    """
    pass

def sync_to_master(rm_db_path, master_db_path, project_id):
    """Synchronizuje status z RM_MANAGER do MASTER.SQLITE
    
    1. Wywołuje determine_display_status()
    2. UPDATE master.projects SET status = ...
    3. UPDATE master.project_statuses (dla checkboxów)
    """
    pass

def sync_all_projects(rm_db_path, master_db_path):
    """Sync wszystkich projektów (batch operation)"""
    pass
```

### Analiza i statystyki
```python
def get_stage_variance(rm_db_path, project_id, stage_code):
    """Oblicza odchylenie dla etapu
    
    Returns:
        {
            "variance_days": +2,  # opóźnienie
            "variance_percent": 40.0,  # 40% dłużej niż plan
            "planned_duration": 5,
            "actual_duration": 7
        }
    """
    pass

def get_project_status_summary(rm_db_path, project_id):
    """Generuje podsumowanie dla dashboard
    
    Returns:
        {
            "status": "ON_TRACK" | "AT_RISK" | "DELAYED",
            "overall_variance_days": -3,
            "completion_forecast": "2026-02-15",
            "active_stages": ["MONTAZ", "AUTOMATYKA"],
            "critical_path_status": "DELAYED"
        }
    """
    pass

def get_stage_timeline(rm_db_path, project_id):
    """Zwraca kompletny timeline dla GUI (wizualizacja Gantt)
    
    Returns:
        [
            {
                "stage_code": "PROJEKT",
                "template_start": "2026-01-01",
                "template_end": "2026-01-05",
                "forecast_start": "2026-01-01",
                "forecast_end": "2026-01-07",
                "actual_periods": [
                    {"started": "2026-01-01 08:00", "ended": "2026-01-05 17:00"},
                    {"started": "2026-01-12 09:00", "ended": "2026-01-14 16:00"}  # powrót!
                ],
                "dependencies": [
                    {"to": "KOMPLETACJA", "type": "FS"}
                ],
                "variance_days": +2,
                "is_active": False,
                "is_critical_path": True
            },
            ...
        ]
    """
    pass
```

### Zdarzenia (opcjonalnie)
```python
def add_stage_event(rm_db_path, project_id, stage_code, event_type, description, assigned_to=None):
    """Dodaje zdarzenie do etapu
    
    event_type: START, END, PAUSE, RESUME, ISSUE, RESOLVED, NOTE, DELAY
    """
    # INSERT INTO stage_events
    pass

def get_stage_events(rm_db_path, project_id, stage_code=None):
    """Zwraca historię zdarzeń
    
    Args:
        stage_code: jeśli None, zwraca wszystkie zdarzenia projektu
    """
    pass
```

---

## Integracja z GUI

### RM_MANAGER GUI - zarządzanie procesami

```python
import rm_manager
from datetime import datetime

# Przy START etapu:
def on_start_stage_clicked(project_id, stage_code):
    """Obsługa przycisku [START MONTAŻ]"""
    
    # 1. Rozpocznij etap
    period_id = rm_manager.start_stage(
        rm_db_path="C:/RM_MANAGER/rm_manager.sqlite",
        project_id=project_id,
        stage_code=stage_code,
        started_by=current_user,
        notes="Rozpoczęcie montażu"
    )
    
    # 2. Przelicz forecast
    forecast = rm_manager.recalculate_forecast(rm_db_path, project_id)
    
    # 3. Sync do MASTER dla RM_BAZA
    rm_manager.sync_to_master(
        rm_db_path=rm_db_path,
        master_db_path="Y:/RM_BAZA/master.sqlite",
        project_id=project_id
    )
    
    # 4. Odśwież widok
    refresh_timeline_view(forecast)
    show_notification(f"Rozpoczęto {stage_code}")


# Przy END etapu:
def on_end_stage_clicked(project_id, stage_code):
    """Obsługa przycisku [END MONTAŻ]"""
    
    # 1. Zakończ etap
    rm_manager.end_stage(
        rm_db_path=rm_db_path,
        project_id=project_id,
        stage_code=stage_code,
        ended_by=current_user
    )
    
    # 2. Oblicz variance
    variance = rm_manager.get_stage_variance(rm_db_path, project_id, stage_code)
    
    # 3. Przelicz forecast (dla pozostałych etapów)
    forecast = rm_manager.recalculate_forecast(rm_db_path, project_id)
    
    # 4. Sync do MASTER
    rm_manager.sync_to_master(rm_db_path, master_db_path, project_id)
    
    # 5. Pokaż wynik
    if variance["variance_days"] > 0:
        show_warning(f"Opóźnienie: {variance['variance_days']} dni")
    else:
        show_success(f"Na czas! ({variance['variance_days']} dni)")
    
    refresh_timeline_view(forecast)


# Wyświetlenie timeline (Gantt chart):
def show_timeline(project_id):
    """Wizualizacja timeline projektu"""
    
    timeline = rm_manager.get_stage_timeline(rm_db_path, project_id)
    
    for stage in timeline:
        print(f"{stage['stage_code']:15} ", end="")
        
        # Template (szary)
        print(f"Plan: {stage['template_start']} - {stage['template_end']} ", end="")
        
        # Forecast (żółty jeśli opóźniony)
        color = "red" if stage['variance_days'] > 0 else "green"
        print(f"Forecast: {stage['forecast_start']} - {stage['forecast_end']} ", end="")
        
        # Actual periods (zielony)
        if stage['actual_periods']:
            print(f"Actual: {len(stage['actual_periods'])} okresów")
            for period in stage['actual_periods']:
                print(f"  • {period['started']} - {period['ended']}")
        
        # Czy trwa
        if stage['is_active']:
            print("  ▶ TRWA TERAZ")


# Dashboard - podsumowanie:
def show_dashboard(project_id):
    """Pokaż podsumowanie projektu"""
    
    summary = rm_manager.get_project_status_summary(rm_db_path, project_id)
    
    print(f"Status: {summary['status']}")
    print(f"Opóźnienie ogólne: {summary['overall_variance_days']} dni")
    print(f"Przewidywane zakończenie: {summary['completion_forecast']}")
    print(f"Aktywne etapy: {', '.join(summary['active_stages'])}")
    
    if summary['status'] == 'DELAYED':
        print("⚠️ PROJEKT OPÓŹNIONY!")
    elif summary['status'] == 'AT_RISK':
        print("⚡ PROJEKT ZAGROŻONY")
    else:
        print("✅ PROJEKT ON TRACK")
```

### RM_BAZA GUI - tylko wyświetlanie (read-only)

```python
# RM_BAZA_v15_MAG_STATS_ORG.py
# Nie zmienia się - tylko pokazuje status z MASTER.SQLITE

def refresh_project_list():
    """Odświeża listę projektów"""
    
    con = sqlite3.connect("Y:/RM_BAZA/master.sqlite")
    
    cur = con.execute("""
        SELECT project_id, name, status, updated_at
        FROM projects
        ORDER BY updated_at DESC
    """)
    
    for row in cur.fetchall():
        tree.insert('', 'end', values=row)
    
    # Status jest aktualizowany przez RM_MANAGER.sync_to_master()
    # RM_BAZA tylko wyświetla
```

---

## Przykład użycia - kompletny flow

```python
import rm_manager
from datetime import datetime

rm_db = "C:/RM_MANAGER/rm_manager.sqlite"
master_db = "Y:/RM_BAZA/master.sqlite"

# =========================================================================
# KROK 1: Inicjalizacja nowego projektu
# =========================================================================

project_id = 123  # ID z MASTER.SQLITE

# Definicja etapów i szablonu
stages = [
    {"code": "PROJEKT", "template_start": "2026-01-01", "template_end": "2026-01-05"},
    {"code": "KOMPLETACJA", "template_start": "2026-01-05", "template_end": "2026-01-10"},
    {"code": "MONTAZ", "template_start": "2026-01-10", "template_end": "2026-01-20"},
    {"code": "AUTOMATYKA", "template_start": "2026-01-12", "template_end": "2026-01-18"},
    {"code": "URUCHOMIENIE", "template_start": "2026-01-20", "template_end": "2026-01-25"},
]

# Definicja zależności (graf)
dependencies = [
    {"from": "PROJEKT", "to": "KOMPLETACJA", "type": "FS", "lag": 0},
    {"from": "KOMPLETACJA", "to": "MONTAZ", "type": "FS", "lag": 0},
    {"from": "MONTAZ", "to": "AUTOMATYKA", "type": "SS", "lag": 2},  # po 2 dniach montażu
    {"from": "MONTAZ", "to": "URUCHOMIENIE", "type": "FS", "lag": 0},
    {"from": "AUTOMATYKA", "to": "URUCHOMIENIE", "type": "FS", "lag": 0},
]

# Inicjalizacja
rm_manager.init_project(rm_db, project_id, stages, dependencies)
print("✅ Projekt zainicjalizowany w RM_MANAGER")


# =========================================================================
# KROK 2: Start pierwszego etapu (PROJEKT)
# =========================================================================

rm_manager.start_stage(rm_db, project_id, "PROJEKT", started_by="jan.kowalski")
print("✅ PROJEKT rozpoczęty")

# Sync do MASTER
rm_manager.sync_to_master(rm_db, master_db, project_id)
print("✅ Status zsynchronizowany do RM_BAZA")


# =========================================================================
# KROK 3: Zakończenie PROJEKTU (z opóźnieniem!)
# =========================================================================

# Zakładamy, że PROJEKT trwał 7 dni zamiast 5 (opóźnienie +2 dni)
rm_manager.end_stage(rm_db, project_id, "PROJEKT", ended_by="jan.kowalski")

# Sprawdź variance
variance = rm_manager.get_stage_variance(rm_db, project_id, "PROJEKT")
print(f"⚠️ PROJEKT variance: {variance['variance_days']} dni")

# Przelicz forecast (cascading effect!)
forecast = rm_manager.recalculate_forecast(rm_db, project_id)

print("📊 Forecast po opóźnieniu PROJEKTU:")
for stage_code, data in forecast.items():
    print(f"  {stage_code}: {data['forecast_start']} - {data['forecast_end']}")
    
# Wynik:
#   PROJEKT: 2026-01-01 - 2026-01-07 (actual)
#   KOMPLETACJA: 2026-01-07 - 2026-01-12 (przesunięta o +2!)
#   MONTAZ: 2026-01-12 - 2026-01-22 (przesunięta o +2!)
#   AUTOMATYKA: 2026-01-14 - 2026-01-20 (SS lag=2)
#   URUCHOMIENIE: 2026-01-22 - 2026-01-27 (czeka na oba)

# Sync do MASTER
rm_manager.sync_to_master(rm_db, master_db, project_id)


# =========================================================================
# KROK 4: Równoległe etapy (MONTAZ + AUTOMATYKA)
# =========================================================================

# Start MONTAŻU
rm_manager.start_stage(rm_db, project_id, "MONTAZ")
print("✅ MONTAŻ rozpoczęty")

# Po 2 dniach start AUTOMATYKI (SS lag=2)
rm_manager.start_stage(rm_db, project_id, "AUTOMATYKA")
print("✅ AUTOMATYKA rozpoczęta równolegle")

# Sprawdź aktywne etapy
active = rm_manager.get_active_stages(rm_db, project_id)
print(f"▶ Obecnie trwa: {[s['stage_code'] for s in active]}")
# Wynik: ['MONTAZ', 'AUTOMATYKA']

# Sync
rm_manager.sync_to_master(rm_db, master_db, project_id)


# =========================================================================
# KROK 5: PROJEKT wraca (multi-period!)
# =========================================================================

# Załóżmy, że podczas montażu trzeba wrócić do projektu
rm_manager.start_stage(rm_db, project_id, "PROJEKT", notes="Poprawki w projekcie")
print("✅ PROJEKT powrócił (2. okres)")

# ... po kilku dniach
rm_manager.end_stage(rm_db, project_id, "PROJEKT")
print("✅ PROJEKT zakończony (2. raz)")

# Sprawdź historię PROJEKTU
periods = rm_manager.get_stage_periods(rm_db, project_id, "PROJEKT")
print(f"📅 PROJEKT trwał {len(periods)} razy:")
for i, period in enumerate(periods, 1):
    print(f"  {i}. {period['started_at']} - {period['ended_at']}")


# =========================================================================
# KROK 6: Timeline i dashboard
# =========================================================================

# Pełny timeline
timeline = rm_manager.get_stage_timeline(rm_db, project_id)

print("\n📊 TIMELINE PROJEKTU:")
print("=" * 80)
for stage in timeline:
    status_icon = "▶" if stage['is_active'] else "✓"
    critical = "⚠" if stage['is_critical_path'] else " "
    
    print(f"{critical} {status_icon} {stage['stage_code']:15} "
          f"Plan: {stage['template_start']} - {stage['template_end']} | "
          f"Forecast: {stage['forecast_start']} - {stage['forecast_end']} | "
          f"Variance: {stage['variance_days']:+3d} dni")

# Dashboard
summary = rm_manager.get_project_status_summary(rm_db, project_id)
print("\n" + "=" * 80)
print(f"STATUS PROJEKTU: {summary['status']}")
print(f"Ogólne opóźnienie: {summary['overall_variance_days']} dni")
print(f"Przewidywane zakończenie: {summary['completion_forecast']}")
print(f"Aktywne etapy: {', '.join(summary['active_stages']) or 'brak'}")
print("=" * 80)


# =========================================================================
# KROK 7: Critical path analysis
# =========================================================================

critical_path = rm_manager.calculate_critical_path(rm_db, project_id)
print(f"\n🔴 Critical Path: {' → '.join(critical_path)}")
# Wynik: PROJEKT → KOMPLETACJA → MONTAZ → URUCHOMIENIE
# (AUTOMATYKA nie jest na critical path bo trwa równolegle)
```

---

## Algorytm recalculate_forecast() (szczegóły)

```python
def recalculate_forecast(rm_db_path, project_id):
    """Implementacja z topological sort"""
    
    # 1. Pobierz dane
    stages = get_project_stages(rm_db_path, project_id)
    schedule = get_stage_schedule(rm_db_path, project_id)
    actuals = get_stage_actual_periods(rm_db_path, project_id)
    deps = get_stage_dependencies(rm_db_path, project_id)
    
    # 2. Topological sort (prawidłowa kolejność obliczeń)
    order = topological_sort(stages, deps)
    
    # 3. Dla każdego etapu w kolejności
    forecast = {}
    
    for stage_id in order:
        stage = stages[stage_id]
        sched = schedule[stage_id]
        periods = actuals.get(stage_id, [])
        
        # A. Jeśli etap już się zakończył - użyj actual
        if periods and all(p['ended_at'] for p in periods):
            last_end = max(p['ended_at'] for p in periods)
            forecast[stage_id] = {
                "forecast_start": periods[0]['started_at'],
                "forecast_end": last_end,
                "is_actual": True
            }
            continue
        
        # B. Jeśli etap trwa - użyj actual_start + template_duration
        if periods and any(p['ended_at'] is None for p in periods):
            active_period = next(p for p in periods if p['ended_at'] is None)
            duration = (sched['template_end'] - sched['template_start']).days
            forecast[stage_id] = {
                "forecast_start": active_period['started_at'],
                "forecast_end": active_period['started_at'] + timedelta(days=duration),
                "is_actual": True  # częściowo
            }
            continue
        
        # C. Etap jeszcze nie rozpoczęty - oblicz forecast
        # Znajdź ograniczenia z zależności
        constraints = []
        
        for dep in deps:
            if dep['successor_stage_id'] != stage_id:
                continue
            
            pred = forecast.get(dep['predecessor_stage_id'])
            if not pred:
                continue
            
            if dep['dependency_type'] == 'FS':
                # Finish-to-Start
                constraint = pred['forecast_end'] + timedelta(days=dep['lag_days'])
            elif dep['dependency_type'] == 'SS':
                # Start-to-Start
                constraint = pred['forecast_start'] + timedelta(days=dep['lag_days'])
            
            constraints.append(constraint)
        
        # Earliest start = max(template_start, wszystkie constraints)
        candidates = [sched['template_start']]
        if constraints:
            candidates.extend(constraints)
        
        forecast_start = max(candidates)
        duration = (sched['template_end'] - sched['template_start']).days
        forecast_end = forecast_start + timedelta(days=duration)
        
        forecast[stage_id] = {
            "forecast_start": forecast_start,
            "forecast_end": forecast_end,
            "is_actual": False
        }
    
    return forecast
```

---

## Podsumowanie

### Przepływ danych
```
RM_MANAGER GUI:
  User: [START MONTAŻ]
    ↓
  rm_manager.start_stage() → INSERT stage_actual_periods
    ↓
  rm_manager.recalculate_forecast() → Topological sort + graph analysis
    ↓
  rm_manager.determine_display_status() → "MONTAŻ"
    ↓
  rm_manager.sync_to_master() → UPDATE master.sqlite
    ↓
RM_BAZA GUI:
  Pokazuje: "MONTAŻ" ✓
```

### Architektura - 2 systemy
```
RM_MANAGER.SQLITE (source of truth)
├─ stage_actual_periods (multi-period, powroty, pauzy)
├─ stage_dependencies (graf FS/SS)
├─ recalculate_forecast() (topological sort)
└─ sync_to_master() → aktualizuje MASTER

MASTER.SQLITE (display layer)
├─ projects.status (uproszczony status)
├─ project_statuses (multi-status dla checkboxów)
└─ odczyt przez RM_BAZA (read-only)
```

### Kluczowe cechy

**✅ Multi-period tracking**
- Etapy mogą wracać wielokrotnie (PROJEKT: 01-05, 12-14, 18-19)
- Każdy okres = osobny rekord w `stage_actual_periods`
- Pauzy = automatyczne (koniec okresu)

**✅ Dependency graph (standard PM)**
- **FS** (Finish-to-Start) - sekwencyjny: `start(B) ≥ end(A)`
- **SS** (Start-to-Start) - równoległy: `start(B) ≥ start(A)`
- **lag_days** - opóźnienie między etapami (może być ujemne)

**✅ Automatic forecasting**
- Topological sort zapewnia prawidłową kolejność obliczeń
- Cascading effect AUTOMATYCZNY - nie wymaga ręcznego przesuwania
- System reaguje na rzeczywiste opóźnienia/przyśpieszenia

**✅ Critical path analysis**
- Identyfikacja ścieżki krytycznej projektu
- Śledzenie które etapy wpływają na całkowity czas projektu
- Slack time - margines opóźnień dla etapów niekrytycznych

**✅ Rozdzielenie systemów**
- RM_MANAGER = zarządzanie procesem (właściwe operacje)
- RM_BAZA = wizualizacja (read-only dla użytkowników)
- Sync jednokierunkowy: RM_MANAGER → MASTER.SQLITE
- Brak blokowania MASTER.SQLITE przez ciężkie operacje

**✅ Analiza i statystyki**
- Variance tracking (plan vs actual)
- Project status summary ("ON_TRACK", "AT_RISK", "DELAYED")
- Timeline visualization (Gantt chart)
- Event history (opcjonalnie)

### Różnice vs stara architektura

| Aspekt | Stara SPEC | Nowa architektura (RM_MANAGER) |
|--------|------------|--------------------------------|
| **Okresy** | status_stats: 1 start + 1 end | stage_actual_periods: wiele rekordów |
| **Powroty** | Trudne do obsługi | Naturalne (multi-period) |
| **Pauzy** | Brak wsparcia | Automatyczne (ended_at != NULL) |
| **Zależności** | DEPENDS_ON, PARALLEL_OF | FS, SS (standard PM) |
| **Cascading** | check_cascading + apply | recalculate_forecast (topological) |
| **Forecast** | Ręczne przesuwanie | Automatyczne przeliczanie |
| **GUI** | Jeden system | Dwa: RM_MANAGER + RM_BAZA |

### Pożyteczne wskaźniki

- **Variance**: `+3 dni` = opóźnienie, `-1` = przyśpieszenie
- **Critical path**: etapy wpływające na całą długość projektu
- **Slack time**: margines na opóźnienia dla etapów niekrytycznych
- **Impact radius**: ile etapów zmieni się przy opóźnieniu jednego
- **Forecast accuracy**: porównanie forecast vs actual w czasie

### Następne kroki

1. **Implementacja rm_manager.py** - funkcje opisane w spec
2. **Migracja danych** - skrypt do przeniesienia istniejących projektów
3. **RM_MANAGER GUI** - interfejs do zarządzania procesami
4. **Integracja** - połączenie RM_MANAGER ↔ MASTER.SQLITE
5. **Testy** - scenariusze testowe (powroty, równoległość, opóźnienia)

---

## INFRASTRUKTURA TECHNICZNA - System połączeń LAN

> **WAŻNE:** RM_MANAGER KOPIUJE 1:1 sprawdzone mechanizmy z RM_BAZA
> - System działa od 2 miesięcy
> - 5 użytkowników jednocześnie
> - Środowisko LAN przez SMB
> - Obsługa sleep/wake, timeouts, reconnects

### Architektura połączeń

```
RM_MANAGER
├─ rm_manager.sqlite (Y:/RM_MANAGER/)           → centralna baza, LAN, READ-WRITE
├─ RM_MANAGER_PROJECTS/
│   ├─ rm_manager_project_123.sqlite            → per-project, LAN, READ-WRITE
│   ├─ rm_manager_project_124.sqlite
│   └─ rm_manager_project_125.sqlite
└─ LOCKS/
    ├─ project_123.lock                         → JSON heartbeat lock
    ├─ project_124.lock
    └─ project_125.lock

MASTER.SQLITE (Y:/RM_BAZA/master.sqlite)        → sync target, READ-WRITE (tylko sync)
```

### Klasa RMDatabaseManager (wzorowana na DatabaseManager)

```python
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

class RMDatabaseManager:
    """Zarządza połączeniami do rm_manager.sqlite + project databases
    
    KOPIUJE SPRAWDZONE MECHANIZMY z RM_BAZA:
    - PRE-TOUCH warm-up (budzenie SMB przed sqlite.connect)
    - Retry loop dla zimnego startu (3 próby z progresywnym opóźnieniem)
    - is_file_accessible() z timeoutem (sprawdza dostępność w 2-5s)
    - ensure_alive() - automatyczny reconnect po sleep/wake
    - Thread-safe reconnect lock
    - Heartbeat detection (database locked = martwe połączenie)
    """
    
    def __init__(self, rm_base_dir: str):
        r"""
        Args:
            rm_base_dir: Y:\RM_MANAGER (root folder)
        """
        self.rm_base_dir = Path(rm_base_dir)
        self.rm_main_db = self.rm_base_dir / "rm_manager.sqlite"
        self.rm_projects_dir = self.rm_base_dir / "RM_MANAGER_PROJECTS"
        self.locks_dir = self.rm_base_dir / "LOCKS"
        
        # Połączenia
        self.main_con: Optional[sqlite3.Connection] = None
        self.project_con: Optional[sqlite3.Connection] = None
        self.current_project_id: Optional[int] = None
        
        # Thread-safe reconnect
        self._reconnect_lock = threading.Lock()
        
        # Network status
        self._network_available = True
        
        # Utwórz foldery
        self.rm_projects_dir.mkdir(parents=True, exist_ok=True)
        self.locks_dir.mkdir(parents=True, exist_ok=True)
    
    # ========================================================================
    # PRE-TOUCH - Warm-up dysku sieciowego (KLUCZOWY mechanizm!)
    # ========================================================================
    
    def _warm_up_remote_file(self, db_path: Path, label: str, cold_start: bool = False) -> None:
        """Wymuś szybki odczyt pliku, żeby obudzić SMB/połączenie sieciowe.
        
        **DLACZEGO TO JEST KRYTYCZNE:**
        - sqlite3.connect() przez SMB może wisieć 30-60s na timeout
        - Odczyt 16KB PRZED connect() budzi cache dysku w <1s
        - Retry loop dla zimnego startu (dysk sieciowy uśpiony)
        
        Args:
            db_path: Ścieżka do pliku bazy
            label: Etykieta do logów
            cold_start: Czy to zimny start (pierwsze połączenie) - więcej retry
        """
        print(f"🧊 WARM-UP {label} START: {time.strftime('%H:%M:%S')} (cold_start={cold_start})")
        warm_start = time.time()
        
        # Retry loop dla zimnego startu (dysk sieciowy może być uśpiony)
        max_attempts = 3 if cold_start else 1
        
        for attempt in range(max_attempts):
            try:
                if not db_path.exists():
                    if attempt < max_attempts - 1:
                        print(f"  ⚠️  WARM-UP próba {attempt+1}/{max_attempts}: brak pliku (czekam 0.5s...)")
                        time.sleep(0.5)
                        continue
                    else:
                        print(f"  ❌ WARM-UP: brak pliku {db_path} po {max_attempts} próbach")
                        return
            except Exception as e:
                if attempt < max_attempts - 1:
                    print(f"  ⚠️  WARM-UP próba {attempt+1}/{max_attempts}: exists() failed: {e} (czekam 0.5s...)")
                    time.sleep(0.5)
                    continue
                else:
                    print(f"  ❌ WARM-UP: exists() failed po {max_attempts} próbach: {e}")
                    return
            
            # Plik istnieje - spróbuj odczytać
            try:
                with db_path.open("rb") as f:
                    # Zimny start: odczytaj 16KB (obudzi cache dysku sieciowego)
                    # Normalny: 1KB wystarczy
                    chunk_size = 16384 if cold_start else 1024
                    data = f.read(chunk_size)
                    print(f"  ✅ WARM-UP odczytano {len(data)} bajtów")
                    break  # Sukces!
            except Exception as e:
                if attempt < max_attempts - 1:
                    print(f"  ⚠️  WARM-UP próba {attempt+1}/{max_attempts}: read failed: {e} (czekam 0.5s...)")
                    time.sleep(0.5)
                    continue
                else:
                    print(f"  ❌ WARM-UP: read failed po {max_attempts} próbach: {e}")
                    return
        
        warm_time = time.time() - warm_start
        print(f"🧊 WARM-UP {label} END: {warm_time:.3f}s")
    
    # ========================================================================
    # is_file_accessible - Szybki test dostępności (z timeoutem)
    # ========================================================================
    
    def is_file_accessible(self, path: Path, timeout_s: float = 2.0) -> bool:
        """Szybki test dostępności pliku (w osobnym wątku z timeoutem).
        
        **DLACZEGO TO JEST KRYTYCZNE:**
        - path.exists() przez SMB może wisieć 30s
        - Thread z timeoutem = odpowiedź w <2s
        - Unika martwych connected() wywołań
        
        Returns:
            True jeśli plik jest dostępny, False jeśli nie (timeout lub błąd)
        """
        result = [False]
        
        def _check():
            try:
                if path.exists():
                    # Spróbuj odczytać 1 bajt
                    with path.open('rb') as f:
                        f.read(1)
                    result[0] = True
            except Exception:
                result[0] = False
        
        t = threading.Thread(target=_check, daemon=True)
        t.start()
        t.join(timeout=timeout_s)
        
        if t.is_alive():
            # Timeout - plik niedostępny (dysk sieciowy nie odpowiada)
            print(f"⚠️  is_file_accessible: TIMEOUT ({timeout_s}s) dla {path}")
            self._network_available = False
            return False
        
        self._network_available = result[0]
        return result[0]
    
    # ========================================================================
    # connect_main - Połączenie z rm_manager.sqlite (z retry dla zimnego startu)
    # ========================================================================
    
    def connect_main(self) -> bool:
        """Otwórz rm_manager.sqlite (READ-WRITE)
        
        **RETRY LOOP dla ZIMNEGO STARTU:**
        - Pierwsze połączenie po uruchomieniu = zimny start
        - 3 próby z progresywnym opóźnieniem (2s, 4s)
        - Każda próba: pre-check + warm-up + connect
        
        Returns:
            True jeśli połączenie udane, False jeśli baza nie istnieje
        """
        # Sprawdź czy już mamy połączenie
        if self.main_con:
            try:
                self.main_con.execute("SELECT 1").fetchone()
                print(f"✅ RM Main już połączone - używam istniejącego")
                return True
            except:
                # Połączenie martwe, zamknij
                try:
                    self.main_con.close()
                except:
                    pass
                self.main_con = None
        
        # PRE-TOUCH: Obudź dysk sieciowy PRZED sqlite.connect()
        print(f"🔍 PRE-TOUCH rm_manager.sqlite START: {time.strftime('%H:%M:%S')}")
        pre_start = time.time()
        
        # Wykryj zimny start (pierwsza próba połączenia)
        cold_start = not hasattr(self, '_first_connect_main_done')
        if cold_start:
            print(f"  ❄️  ZIMNY START wykryty - użyję agresywniejszego warm-up")
        
        # Retry loop dla zimnego startu
        max_attempts = 3 if cold_start else 1
        last_error = None
        
        for attempt in range(max_attempts):
            if attempt > 0:
                wait_time = 2 * attempt  # Progresywne opóźnienie: 2s, 4s
                print(f"  🔄 Próba {attempt+1}/{max_attempts} po {wait_time}s opóźnienia...")
                time.sleep(wait_time)
            
            try:
                # Szybki pre-check z timeoutem (5s cold / 3s normal)
                precheck_timeout = 5.0 if cold_start else 3.0
                if not self.is_file_accessible(self.rm_main_db, timeout_s=precheck_timeout):
                    if attempt < max_attempts - 1:
                        print(f"  ⚠️  Próba {attempt+1}/{max_attempts}: rm_manager.sqlite niedostępny (timeout {precheck_timeout}s)")
                        continue
                    else:
                        print(f"  ❌ rm_manager.sqlite niedostępny po {max_attempts} próbach (timeout {precheck_timeout}s każda)")
                        return False
                
                # Plik dostępny - warm-up
                self._warm_up_remote_file(self.rm_main_db, "rm_manager.sqlite", cold_start=cold_start)
                
                pre_time = time.time() - pre_start
                print(f"🔍 PRE-TOUCH rm_manager.sqlite END: {pre_time:.3f}s")
                
                # SQLite connect
                print(f"🔌 SQLITE CONNECT rm_manager.sqlite START: {time.strftime('%H:%M:%S')}")
                connect_start = time.time()
                
                # Timeout: 15s dla zimnego startu, 5s normalnie
                timeout_s = 15.0 if cold_start else 5.0
                print(f"  ⏱️  Timeout ustawiony na: {timeout_s}s")
                
                self.main_con = sqlite3.connect(
                    str(self.rm_main_db),
                    timeout=timeout_s,
                    check_same_thread=False,
                    isolation_level='DEFERRED'
                )
                self.main_con.row_factory = sqlite3.Row
                
                # Optymalizacje wydajności + SMB-safe settings
                self.main_con.execute("PRAGMA cache_size=-32000")  # 32MB cache
                self.main_con.execute("PRAGMA temp_store=MEMORY")
                self.main_con.execute("PRAGMA journal_mode=DELETE")  # WAL NIE DZIAŁA przez SMB!
                self.main_con.execute("PRAGMA busy_timeout=5000")
                self.main_con.execute("PRAGMA locking_mode=NORMAL")
                self.main_con.execute("PRAGMA synchronous=NORMAL")
                
                # Test połączenia
                try:
                    test_result = self.main_con.execute("SELECT 1").fetchone()
                    if not test_result:
                        raise sqlite3.OperationalError("Test query zwrócił NULL")
                except Exception as test_err:
                    if attempt < max_attempts - 1:
                        print(f"  ⚠️  Próba {attempt+1}/{max_attempts}: Test query failed: {test_err}")
                        try:
                            self.main_con.close()
                        except:
                            pass
                        self.main_con = None
                        continue
                    else:
                        raise
                
                connect_time = time.time() - connect_start
                print(f"🔌 SQLITE CONNECT rm_manager.sqlite END: {connect_time:.3f}s")
                print(f"✅ RM Main: {self.rm_main_db} - TOTAL: {pre_time + connect_time:.3f}s")
                
                # Oznacz że pierwszy connect się udał
                self._first_connect_main_done = True
                
                return True
                
            except Exception as e:
                last_error = e
                if attempt < max_attempts - 1:
                    print(f"  ⚠️  Próba {attempt+1}/{max_attempts}: Błąd łączenia: {e}")
                    try:
                        if self.main_con:
                            self.main_con.close()
                            self.main_con = None
                    except:
                        pass
                    continue
                else:
                    print(f"❌ Błąd łączenia z rm_manager.sqlite po {max_attempts} próbach: {e}")
                    import traceback
                    traceback.print_exc()
                    return False
        
        print(f"❌ Nie udało się połączyć z rm_manager.sqlite po {max_attempts} próbach")
        if last_error:
            print(f"  Ostatni błąd: {last_error}")
        return False
    
    # ========================================================================
    # ensure_main_alive - Sprawdź żywotność + auto-reconnect
    # ========================================================================
    
    def ensure_main_alive(self) -> bool:
        """Sprawdź czy połączenie z rm_manager.sqlite jest żywe. Reconnect jeśli nie.
        
        **SCENARIUSZE:**
        - Po sleep/wake komputera: połączenie SMB martwe
        - "database is locked" = martwe połączenie
        - Timeout SMB po dłuższej bezczynności
        
        Returns:
            True jeśli połączenie OK, False jeśli nie udało się przywrócić
        """
        # Jeśli nie ma połączenia, połącz
        if not self.main_con:
            print("🔄 RM Main: brak połączenia, łączę...")
            return self.connect_main()
        
        # Szybki pre-check: czy plik na dysku sieciowym jest w ogóle dostępny?
        if not self.is_file_accessible(self.rm_main_db, timeout_s=2.0):
            print(f"⚠️  RM Main: plik niedostępny (dysk sieciowy?) - nie próbuję reconnect")
            return False
        
        # Test żywotności - SELECT z tabelą (dotyka pliku na dysku)
        try:
            self.main_con.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
            return True
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            err_msg = str(e).lower()
            
            # "database is locked" po sleep/wake — wymuś pełny reconnect
            if "locked" in err_msg:
                print(f"⚠️  RM Main: database locked (sleep/wake?), wymuszam reconnect...")
            else:
                print(f"⚠️  RM Main: połączenie martwe ({e}), reconnect...")
            
            # Zamknij martwe połączenie
            try:
                self.main_con.close()
            except:
                pass
            self.main_con = None
            
            # Próba ponownego połączenia
            try:
                time.sleep(0.05)
                return self.connect_main()
            except Exception as reconnect_err:
                print(f"❌ RM Main reconnect failed: {reconnect_err}")
                return False
    
    # ========================================================================
    # _reconnect_after_locked - Thread-safe reconnect (po sleep/wake)
    # ========================================================================
    
    def _reconnect_after_locked(self, db_type: str, connect_func) -> bool:
        """Zamknij martwe/zablokowane połączenie i połącz ponownie.
        
        **THREAD-SAFE:**
        - Używa locka żeby uniknąć podwójnego reconnect
        - Race condition po sleep/wake (wiele wątków wykrywa błąd jednocześnie)
        
        Args:
            db_type: "main" lub "project"
            connect_func: funkcja do reconnect (connect_main lub connect_project)
        
        Returns:
            True jeśli reconnect się udał
        """
        # Zapobiegnij podwójnemu reconnect (race condition po sleep/wake)
        if not self._reconnect_lock.acquire(blocking=False):
            # Inny wątek już robi reconnect — poczekaj aż skończy
            print(f"⏳ RECONNECT {db_type}: inny wątek już reconnectuje — czekam...")
            self._reconnect_lock.acquire()  # Czekaj na zakończenie
            self._reconnect_lock.release()
            
            # Sprawdź czy połączenie działa (inny wątek już je naprawił)
            con = self.main_con if db_type == "main" else self.project_con
            if con:
                try:
                    con.execute("SELECT 1").fetchone()
                    print(f"✅ RECONNECT {db_type}: połączenie już naprawione przez inny wątek")
                    return True
                except:
                    pass  # Wciąż martwe — spróbuj sam
        
        try:
            print(f"🔄 RECONNECT {db_type} po 'database is locked' (sleep/wake?)...")
            
            # Zamknij martwe połączenie
            con = self.main_con if db_type == "main" else self.project_con
            try:
                if con:
                    con.close()
            except:
                pass
            
            if db_type == "main":
                self.main_con = None
            else:
                self.project_con = None
            
            time.sleep(0.2)  # Krótka pauza żeby SMB zdążył się odbudować
            return connect_func()
        finally:
            try:
                self._reconnect_lock.release()
            except RuntimeError:
                pass  # Już zwolniony
    
    # ========================================================================
    # open_project - Otwórz per-project database
    # ========================================================================
    
    def open_project(self, project_id: int) -> bool:
        """Otwórz bazę projektu (rm_manager_project_XXX.sqlite)
        
        Args:
            project_id: ID projektu
        
        Returns:
            True jeśli połączenie udane
        """
        # Jeśli ten sam projekt już otwarty
        if (self.project_con is not None and 
            self.current_project_id == project_id):
            try:
                self.project_con.execute("SELECT 1").fetchone()
                print(f"✅ Projekt {project_id} już otwarty - używam istniejącego")
                return True
            except:
                # Połączenie martwe
                pass
        
        # Zamknij poprzednie połączenie
        if self.project_con:
            try:
                self.project_con.close()
            except:
                pass
            self.project_con = None
        
        # Ścieżka do bazy projektu
        project_db = self.rm_projects_dir / f"rm_manager_project_{project_id}.sqlite"
        
        # PRE-TOUCH
        print(f"🔍 PRE-TOUCH project {project_id} START: {time.strftime('%H:%M:%S')}")
        pre_start = time.time()
        
        # Pre-check
        if not self.is_file_accessible(project_db, timeout_s=3.0):
            print(f"⚠️  Projekt {project_id}: plik niedostępny")
            return False
        
        # Warm-up
        self._warm_up_remote_file(project_db, f"project_{project_id}", cold_start=False)
        
        pre_time = time.time() - pre_start
        print(f"🔍 PRE-TOUCH project {project_id} END: {pre_time:.3f}s")
        
        # Connect
        try:
            print(f"🔌 SQLITE CONNECT project {project_id} START")
            connect_start = time.time()
            
            self.project_con = sqlite3.connect(
                str(project_db),
                timeout=5.0,
                check_same_thread=False,
                isolation_level='DEFERRED'
            )
            self.project_con.row_factory = sqlite3.Row
            
            # SMB-safe settings
            self.project_con.execute("PRAGMA cache_size=-32000")
            self.project_con.execute("PRAGMA temp_store=MEMORY")
            self.project_con.execute("PRAGMA journal_mode=DELETE")
            self.project_con.execute("PRAGMA busy_timeout=5000")
            self.project_con.execute("PRAGMA locking_mode=NORMAL")
            self.project_con.execute("PRAGMA synchronous=NORMAL")
            
            # Test
            self.project_con.execute("SELECT 1").fetchone()
            
            self.current_project_id = project_id
            
            connect_time = time.time() - connect_start
            print(f"🔌 SQLITE CONNECT project {project_id} END: {connect_time:.3f}s")
            print(f"✅ Project {project_id}: {project_db}")
            
            return True
            
        except Exception as e:
            print(f"❌ Błąd łączenia z projektem {project_id}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # ========================================================================
    # ensure_project_alive - Auto-reconnect dla projektu
    # ========================================================================
    
    def ensure_project_alive(self) -> bool:
        """Sprawdź czy połączenie z projektem jest żywe. Reconnect jeśli nie."""
        if not self.project_con or not self.current_project_id:
            return False
        
        # Pre-check pliku
        project_db = self.rm_projects_dir / f"rm_manager_project_{self.current_project_id}.sqlite"
        if not self.is_file_accessible(project_db, timeout_s=2.0):
            print(f"⚠️  Project: plik niedostępny - nie próbuję reconnect")
            return False
        
        # Test żywotności
        try:
            self.project_con.execute("SELECT 1").fetchone()
            return True
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            print(f"⚠️  Project: połączenie martwe ({e}), reconnect...")
            
            try:
                self.project_con.close()
            except:
                pass
            self.project_con = None
            
            # Re-open
            try:
                time.sleep(0.05)
                return self.open_project(self.current_project_id)
            except Exception as reconnect_err:
                print(f"❌ Project reconnect failed: {reconnect_err}")
                return False
```

---

## Lock Manager dla RM_MANAGER

```python
import json
import socket
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Set

class RMLockManager:
    """System locków dla RM_MANAGER - KOPIUJE lock_manager_v2.py z RM_BAZA
    
    LOCK = PLIK JSON w katalogu LOCKS/
    - Nazwa: project_X.lock
    - Zawartość: {"user": "M-old", "computer": "DESKTOP-ABC", "locked_at": "...", "last_heartbeat": "..."}
    
    HEARTBEAT SYSTEM:
    ✅ Lock odświeżany co 2 minuty (last_heartbeat)
    ✅ Locki starsze niż 5 minut automatycznie przejmowane
    ✅ Proste i niezawodne
    """
    
    def __init__(self, locks_folder: Path, stale_seconds: int = 300):
        """
        Args:
            locks_folder: Path do folderu LOCKS/
            stale_seconds: Po ilu sekundach lock uznawany za przeterminowany (default: 300 = 5 min)
        """
        self.my_name = socket.gethostname()  # Domyślnie hostname, można zmienić przez update_user_name()
        self.my_computer = socket.gethostname()
        self.locks_folder = locks_folder
        self.stale_lock_seconds = stale_seconds
        
        self.locks_folder.mkdir(parents=True, exist_ok=True)
        
        # Aktywne locki (project_id -> lock_id)
        self._my_locks: Dict[int, str] = {}
        
        print(f"🔧 RMLockManager: folder locks = {self.locks_folder}")
        print(f"💻 Mój komputer: {self.my_computer}")
        print(f"⏱️  Heartbeat timeout: {self.stale_lock_seconds}s")
    
    def update_user_name(self, new_name: str):
        """Zaktualizuj nazwę użytkownika (po zalogowaniu)"""
        old_name = self.my_name
        self.my_name = new_name
        print(f"🔄 RMLockManager: zmieniono nazwę użytkownika {old_name} -> {new_name}")
    
    def _lock_age_seconds(self, owner: Optional[Dict]) -> Optional[float]:
        """Zwróć wiek HEARTBEAT w sekundach (None jeśli brak daty lub błąd)."""
        if not owner:
            return None
        # Sprawdź last_heartbeat (priorytet) lub locked_at (fallback)
        heartbeat = owner.get('last_heartbeat') or owner.get('locked_at')
        if not heartbeat:
            return None
        try:
            lock_dt = datetime.fromisoformat(str(heartbeat))
            return (datetime.now() - lock_dt).total_seconds()
        except Exception:
            return None
    
    def acquire_project_lock(self, project_id: int, force: bool = False) -> Tuple[bool, Optional[str]]:
        """Przejmij lock projektu
        
        Args:
            project_id: ID projektu
            force: Czy wymusić przejęcie (ignoruj czy owner online)
        
        Returns:
            Tuple[bool, Optional[str]]: (success, lock_id)
        """
        lock_file = self.locks_folder / f"project_{project_id}.lock"
        
        # Jeśli lock NIE istnieje - od razu przejmij
        if not lock_file.exists():
            print(f"🔓 Lock project {project_id}: wolny - przejmuję")
            return self._create_lock_file(project_id, lock_file)
        
        # Lock istnieje - sprawdź czy to mój
        owner = self.get_project_lock_owner(project_id)
        if owner:
            owner_user = owner.get('user', 'Unknown')
            owner_comp = owner.get('computer', 'Unknown')
            if owner_comp == self.my_computer and owner_user == self.my_name:
                print(f"✅ Lock project {project_id}: już mój")
                lock_id = owner.get('lock_id', str(uuid.uuid4()))
                self._my_locks[project_id] = lock_id
                return (True, lock_id)
        
        # Lock zajęty przez kogoś innego - sprawdź HEARTBEAT
        owner_user = owner.get('user', 'Unknown') if owner else 'Unknown'
        owner_comp = owner.get('computer', 'Unknown') if owner else 'Unknown'
        
        if not force:
            # Sprawdź wiek heartbeat
            lock_age = self._lock_age_seconds(owner)
            
            if lock_age is None:
                # Brak timestampa - przejmij lock
                print(f"🔓 Lock project {project_id}: brak heartbeat - przejmuję")
                return self._create_lock_file(project_id, lock_file)
            
            if lock_age < self.stale_lock_seconds:
                # Heartbeat świeży - lock aktywny
                print(
                    f"🔴 Lock project {project_id}: zajęty przez {owner_user}@{owner_comp} "
                    f"(heartbeat {int(lock_age)}s temu)"
                )
                return (False, None)
            
            # Heartbeat przeterminowany - przejmij lock
            print(
                f"🔓 Lock project {project_id}: heartbeat przeterminowany "
                f"({int(lock_age)}s, limit {self.stale_lock_seconds}s) - przejmuję"
            )
            return self._create_lock_file(project_id, lock_file)
        else:
            # Force = przejmij bez sprawdzania heartbeat
            print(f"⚡ Lock project {project_id}: wymuszam przejęcie (force=True)")
            return self._create_lock_file(project_id, lock_file)
    
    def _create_lock_file(self, project_id: int, lock_file: Path) -> Tuple[bool, Optional[str]]:
        """Utwórz plik lock"""
        lock_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        lock_data = {
            "lock_id": lock_id,
            "user": self.my_name,
            "computer": self.my_computer,
            "locked_at": now,
            "last_heartbeat": now
        }
        
        try:
            with open(lock_file, 'w', encoding='utf-8') as f:
                json.dump(lock_data, f, indent=2)
            
            self._my_locks[project_id] = lock_id
            print(f"✅ Lock project {project_id} przejęty: {self.my_name}@{self.my_computer} (lock_id: {lock_id[:8]}...)")
            return (True, lock_id)
        
        except Exception as e:
            print(f"❌ Błąd przejmowania locka project {project_id}: {e}")
            return (False, None)
    
    def release_project_lock(self, project_id: int):
        """Zwolnij lock projektu"""
        lock_file = self.locks_folder / f"project_{project_id}.lock"
        
        try:
            if lock_file.exists():
                lock_file.unlink()
            
            if project_id in self._my_locks:
                del self._my_locks[project_id]
            
            print(f"🔓 Lock project {project_id} zwolniony")
        
        except Exception as e:
            print(f"⚠️ Błąd zwalniania locka project {project_id}: {e}")
    
    def refresh_heartbeat(self, project_id: int) -> bool:
        """Odśwież heartbeat dla locka projektu (wywołuj co ~2 minuty)
        
        Returns:
            True jeśli udało się odświeżyć, False jeśli lock nie istnieje lub błąd
        """
        lock_file = self.locks_folder / f"project_{project_id}.lock"
        
        if not lock_file.exists():
            print(f"⚠️  Lock project {project_id}: plik nie istnieje - nie można odświeżyć")
            return False
        
        try:
            # Odczytaj lock
            with open(lock_file, 'r', encoding='utf-8') as f:
                lock_data = json.load(f)
            
            # Sprawdź czy to mój lock
            if lock_data.get('computer') != self.my_computer or lock_data.get('user') != self.my_name:
                print(f"⚠️  Lock project {project_id}: nie mój lock - nie odświeżam")
                return False
            
            # Odśwież heartbeat
            lock_data['last_heartbeat'] = datetime.now().isoformat()
            
            # Zapisz z powrotem
            with open(lock_file, 'w', encoding='utf-8') as f:
                json.dump(lock_data, f, indent=2)
            
            print(f"💓 Lock project {project_id}: heartbeat odświeżony")
            return True
        
        except Exception as e:
            print(f"❌ Błąd odświeżania heartbeat project {project_id}: {e}")
            return False
    
    def have_project_lock(self, project_id: int) -> bool:
        """Sprawdź czy mam lock dla projektu"""
        return project_id in self._my_locks
    
    def get_my_locked_projects(self) -> Set[int]:
        """Zwróć set ID projektów które mam zablokowane"""
        return set(self._my_locks.keys())
    
    def get_project_lock_owner(self, project_id: int) -> Optional[Dict]:
        """Pobierz info o właścicielu locka projektu
        
        Returns:
            Dict z {"user", "computer", "locked_at", "last_heartbeat"} lub None
        """
        lock_file = self.locks_folder / f"project_{project_id}.lock"
        
        if not lock_file.exists():
            return None
        
        try:
            with open(lock_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Błąd odczytu locka: {e}")
            return None
    
    def release_all_my_locks(self):
        """Zwolnij wszystkie moje locki (przy zamykaniu aplikacji)"""
        project_ids = list(self._my_locks.keys())
        for project_id in project_ids:
            self.release_project_lock(project_id)
```

---

## Integracja - Kompletny przykład z lockami i reconnect

```python
import rm_manager
from rm_database_manager import RMDatabaseManager
from rm_lock_manager import RMLockManager
import time
import threading

# Inicjalizacja
rm_base = Path("Y:/RM_MANAGER")
db_mgr = RMDatabaseManager(rm_base_dir=str(rm_base))
lock_mgr = RMLockManager(locks_folder=rm_base / "LOCKS", stale_seconds=300)

# Połącz główną bazę
if not db_mgr.connect_main():
    print("❌ Nie można połączyć z rm_manager.sqlite")
    exit(1)

# HEARTBEAT THREAD - odświeża locki co 2 minuty
def heartbeat_thread():
    """Wątek w tle: odświeża locki co 2 minuty"""
    while True:
        time.sleep(120)  # 2 minuty
        
        locked_projects = lock_mgr.get_my_locked_projects()
        for project_id in locked_projects:
            lock_mgr.refresh_heartbeat(project_id)

# Uruchom heartbeat w tle
heartbeat_daemon = threading.Thread(target=heartbeat_thread, daemon=True)
heartbeat_daemon.start()

# WORKFLOW: Edycja projektu z lockiem
project_id = 123

# 1. Sprawdź połączenie (auto-reconnect po sleep/wake)
if not db_mgr.ensure_main_alive():
    print("❌ Baza główna niedostępna")
    exit(1)

# 2. Spróbuj przejąć lock
success, lock_id = lock_mgr.acquire_project_lock(project_id, force=False)
if not success:
    print("❌ Projekt zajęty przez innego użytkownika")
    exit(1)

print(f"✅ Lock przejęty: {lock_id}")

# 3. Otwórz bazę projektu
if not db_mgr.open_project(project_id):
    print("❌ Nie można otworzyć bazy projektu")
    lock_mgr.release_project_lock(project_id)
    exit(1)

# 4. Wykonaj operacje (z retry po sleep/wake)
try:
    # Sprawdź żywotność przed każdą operacją
    if not db_mgr.ensure_project_alive():
        print("⚠️  Połączenie z projektem martwe - reconnect...")
        if not db_mgr.ensure_project_alive():
            raise Exception("Nie można przywrócić połączenia")
    
    # START etapu
    rm_manager.start_stage(
        db_mgr.project_con,
        project_id=project_id,
        stage_code="MONTAZ",
        started_by="jan.kowalski"
    )
    
    # Recalculate forecast
    forecast = rm_manager.recalculate_forecast(db_mgr.project_con, project_id)
    
    # Sync do MASTER (z retry)
    master_con = sqlite3.connect("Y:/RM_BAZA/master.sqlite", timeout=5.0)
    try:
        rm_manager.sync_to_master(
            rm_con=db_mgr.project_con,
            master_con=master_con,
            project_id=project_id
        )
    finally:
        master_con.close()
    
    print("✅ Operacje zakończone pomyślnie")

finally:
    # 5. Zawsze zwolnij lock
    lock_mgr.release_project_lock(project_id)
    print("🔓 Lock zwolniony")
```

---

## Podsumowanie mechanizmów technicznych

### ✅ PRE-TOUCH warm-up
```python
# Odczytaj 16KB PRZED sqlite.connect()
# Budzi cache dysku SMB w <1s
# Unika 30-60s timeoutów
self._warm_up_remote_file(db_path, "label", cold_start=True)
```

### ✅ Retry loop (zimny start)
```python
# 3 próby z progresywnym opóźnieniem (2s, 4s)
# Pierwsza próba po uruchomieniu = zimny start
# Każda próba: pre-check + warm-up + connect
for attempt in range(3):
    if self.is_file_accessible(db_path, timeout_s=5.0):
        self._warm_up_remote_file(...)
        con = sqlite3.connect(...)
        break
    time.sleep(2 * attempt)
```

### ✅ is_file_accessible (z timeoutem)
```python
# Thread z timeoutem 2-5s
# Sprawdza path.exists() + odczyt 1 bajta
# Unika 30s hang na martwy SMB
if not self.is_file_accessible(db_path, timeout_s=2.0):
    return False  # Dysk sieciowy nie odpowiada
```

### ✅ ensure_alive (auto-reconnect)
```python
# Wywołuj PRZED każdą operacją na bazie
# Wykrywa martwe połączenie (sleep/wake)
# Automatyczny reconnect
if not db_mgr.ensure_main_alive():
    print("❌ Nie można przywrócić połączenia")
```

### ✅ Thread-safe reconnect lock
```python
# Zapobiega podwójnemu reconnect (race condition)
# Po sleep/wake wiele wątków wykrywa błąd jednocześnie
# Lock: tylko jeden wątek reconnectuje, reszta czeka
if not self._reconnect_lock.acquire(blocking=False):
    self._reconnect_lock.acquire()  # Czekaj na inny wątek
    # Sprawdź czy już naprawiony
```

### ✅ Heartbeat system (locki)
```python
# Odświeżaj lock co 2 minuty
# Locki starsze niż 5 minut = przeterminowane
# Automatyczne przejmowanie przeterminowanych
lock_mgr.refresh_heartbeat(project_id)  # Co 2 min w wątku
```

### ✅ SMB-safe PRAGMA
```python
# journal_mode=DELETE (WAL NIE DZIAŁA przez SMB!)
# busy_timeout=5000 (5s na lock)
# locking_mode=NORMAL (nie exclusive)
# synchronous=NORMAL (nie FULL - wolne przez SMB)
con.execute("PRAGMA journal_mode=DELETE")
con.execute("PRAGMA busy_timeout=5000")
```

### ✅ Obsługa błędów "database is locked"
```python
# Po sleep/wake: połączenie SMB martwe
# SQLite rzuca "database is locked"
# Wymuś pełny reconnect (nie retry query!)
if "locked" in str(e).lower():
    self._reconnect_after_locked("main", self.connect_main)
```

---

**WSZYSTKIE mechanizmy testowane przez 2 miesiące, 5 użytkowników, środowisko LAN! 🚀**
