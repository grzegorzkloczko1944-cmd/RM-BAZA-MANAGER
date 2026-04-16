# RM_MANAGER GUI - Quick Start

## ✅ Co zostało zaimplementowane:

### 1. **Backend** (logika biznesowa)
- [rm_manager.py](rm_manager.py) - 1089 linii
  - Multi-period tracking
  - Dependency graph (FS/SS)
  - Topological sort + forecasting
  - Critical path analysis
  - Sync z master.sqlite

### 2. **GUI** (Tkinter - styl RM_BAZA)
- [rm_manager_gui.py](rm_manager_gui.py) - 750+ linii
  - **Integracja z RM_BAZA** - czyta projekty z master.sqlite
  - **Lazy initialization** - auto-init projektów przy pierwszym otwarciu
  - **Auto-sync** - synchronizacja statusów z RM_BAZA po każdej zmianie
  - Project selector
  - Stage buttons (START/END)
  - Timeline visualization
  - Dashboard (variance, forecast, critical path)
  - Historia okresów
  - Menu (Sync, Critical Path)
  - **Kolory RM_BAZA theme** (#2c3e50, #27ae60, #e74c3c, etc.)

### 3. **Testy**
- [test_rm_manager.py](test_rm_manager.py) - test backend
- [test_rm_gui.py](test_rm_gui.py) - test GUI z przykładowymi danymi

## 🚀 Szybki start

### 0. **WAŻNE** - Konfiguracja ścieżek (plik JSON)

RM_MANAGER używa pliku konfiguracyjnego JSON do przechowywania ścieżek do baz danych:

**Lokalizacja (na sztywno):**
```
C:\RMPAK_CLIENT\manager_sync_config.json
```

**Struktura pliku:**
```json
{
    "master_db_path": "Y:/RM_BAZA/master.sqlite",
    "rm_db_path": "rm_manager.sqlite",
    "_comment": "RM_MANAGER configuration file - edit paths as needed"
}
```

**Jak skonfigurować:**
1. Przy pierwszym uruchomieniu GUI - jeśli brak pliku, zostanie utworzony z domyślnymi wartościami
2. W GUI: Menu → **Plik** → **Konfiguracja ścieżek...** → wybierz master.sqlite
3. Ścieżka zostanie zapisana w JSON i będzie używana przy kolejnych uruchomieniach
4. Można też edytować plik JSON ręcznie (zmienić `master_db_path`)

**Przykład:**
- Sieciowy master: `"master_db_path": "Y:/RM_BAZA/master.sqlite"`
- Lokalny test: `"master_db_path": "C:/test/master.sqlite"`

**WAŻNE - Wymagania dotyczące master.sqlite:**

RM_MANAGER wymaga, aby tabela `projects` w master.sqlite miała następujący schemat:
```sql
CREATE TABLE projects (
    project_id INTEGER PRIMARY KEY,      -- NIE 'id'!
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,   -- NIE 'is_active'!
    project_type TEXT,
    status TEXT,
    designer TEXT,
    started_at TEXT,
    expected_delivery TEXT,
    completed_at TEXT,
    -- ... inne kolumny ...
)
```

**Kluczowe różnice vs stary schemat:**
- ✅ Używaj: `project_id` (PRIMARY KEY) - NIE `id` + osobne `project_id`
- ✅ Używaj: `active` - NIE `is_active`
- ✅ Schema zgodny z: `schema_full_master_SQLITE.txt` (produkcja)

Jeśli masz stary schemat - uruchom odpowiednią migrację lub użyj `test_rm_gui.py` do utworzenia testowej bazy.

---

### 1. Test GUI (z przykładowymi projektami w master.sqlite):
```bash
python test_rm_gui.py
```
Utworzy:
- **master.sqlite** (RM_BAZA) - 3 projekty z PRAWIDŁOWYM schematem
- **rm_manager.sqlite** (RM_MANAGER) - automatycznie zainicjalizowane przy pierwszym otwarciu
- **Projekt 100** - Linia A (PROJEKT)
- **Projekt 200** - Linia B (KOMPLETACJA)
- **Projekt 300** - Magazyn (URUCHOMIENIE)

### 2. Uruchomienie GUI (z istniejącym master.sqlite):
```bash
python rm_manager_gui.py
```
**UWAGA:** Przy pierwszym uruchomieniu sprawdzi plik `C:\RMPAK_CLIENT\manager_sync_config.json`:
- Jeśli istnieje - wczyta ścieżki z JSON
- Jeśli brak - utworzy plik z domyślnymi wartościami i zapyta o konfigurację

**Weryfikacja schematu:** Uruchom `python verify_schema.py` aby sprawdzić zgodność zapytań SQL

### 3. Test backend (bez GUI):
```bash
python test_rm_manager.py
```

## 🔗 Integracja z RM_BAZA

### Współdzielony master.sqlite
RM_MANAGER i RM_BAZA używają **tej samej** bazy master.sqlite:

```
Y:/RM_BAZA/
├─ master.sqlite              ← Wspólny dla obu systemów!
│  ├─ projects               ← Lista projektów
│  └─ project_statuses       ← Multi-status checkboxy
│
├─ projekt_123/
│  └─ data.sqlite            ← Dane BOM (tylko RM_BAZA)
```

```
Y:/RM_MANAGER/
└─ rm_manager.sqlite          ← Zarządzanie procesem (wszystkie projekty)
```

### Przepływ danych:
1. **RM_BAZA** tworzy projekt w master.sqlite
2. **RM_MANAGER** otwiera projekt → **lazy init** w rm_manager.sqlite
3. Użytkownik START/END etapów → **auto-sync** do master.sqlite
4. **RM_BAZA** wyświetla aktualny status (read-only)

## 📂 Struktura plików

```
C:/RMPAK_CLIENT/
├─ manager_sync_config.json   ← Konfiguracja (ścieżki do baz) - **WYMAGANY**
│
RM_MANAGER/
├─ rm_manager.py              ← Backend (logika biznesowa) - **WYMAGANY**
├─ rm_manager_gui.py          ← GUI (Tkinter) - **WYMAGANY**
├─ rm_manager.sqlite          ← Baza danych (utworzy się automatycznie)
│
├─ test_rm_manager.py         ← Test backend (opcjonalny)
├─ test_rm_gui.py             ← Test GUI (opcjonalny)
│
└─ RM_MANAGER_GUI_README.md  ← Dokumentacja
```

**MINIMALNA INSTALACJA (3 pliki):**
1. `rm_manager.py` - backend
2. `rm_manager_gui.py` - GUI
3. `C:\RMPAK_CLIENT\manager_sync_config.json` - konfiguracja ścieżek

**UWAGA:** `rm_database_manager.py` i `rm_lock_manager.py` NIE są potrzebne!  
RM_MANAGER działa na jednej centralnej bazie (bez per-project locków).

**UWAGA 2:** `project_manager.py` NIE jest wymagany!  
GUI używa bezpośredniego SQL do master.sqlite.

## 🎯 Jak używać GUI

### 1. Wybór projektu
- Lista rozwijana na górze
- Automatyczne ładowanie etapów

### 2. Zarządzanie etapami (lewy panel)
```
┌── Montaż ──────┐
│ ● TRWA         │  ← Status indicator
│                │
│ 🟢 START       │  ← Rozpocznij (disabled gdy trwa)
│ 🔴 END         │  ← Zakończ (enabled gdy trwa)
└────────────────┘
```

### 3. Timeline (prawy panel - zakładka "Timeline")
- Porównanie Template vs Forecast
- Variance (opóźnienia/przyspieszenia)
- Multi-period history (powroty etapów)

### 4. Dashboard (zakładka)
- Status projektu: 🟢 ON_TRACK / 🟡 AT_RISK / 🔴 DELAYED
- Overall variance
- Completion forecast
- Critical Path (5 najważniejszych etapów)

### 5. Historia (zakładka)
- Tabela wszystkich okresów
- Start/End timestamps
- Duration

## 🔧 Konfiguracja

Edytuj na górze `rm_manager_gui.py`:

```python
# Ścieżki do baz danych
RM_DB_PATH = "rm_manager.sqlite"           # Lokalna test baza
# RM_DB_PATH = "Y:/RM_MANAGER/rm_manager.sqlite"  # Produkcja (SMB)

MASTER_DB_PATH = "master.sqlite"           # Lokalna test baza
# MASTER_DB_PATH = "Y:/RM_BAZA/master.sqlite"    # Produkcja (RM_BAZA - WSPÓLNY!)

# Użytkownik
CURRENT_USER = os.environ.get('USERNAME', 'System')

# Default stage configuration (auto-init)
DEFAULT_STAGE_SEQUENCE = [
    'PRZYJETY', 'PROJEKT', 'KOMPLETACJA', 'MONTAZ', 
    'AUTOMATYKA', 'URUCHOMIENIE', 'ODBIORY', 'POPRAWKI'
]

# Default dependencies (workflow)
DEFAULT_DEPENDENCIES = [
    {'from': 'PRZYJETY', 'to': 'PROJEKT', 'type': 'FS', 'lag': 0},
    {'from': 'PROJEKT', 'to': 'KOMPLETACJA', 'type': 'FS', 'lag': 0},
    # ... więcej ...
]
```

## 📊 Przykładowy workflow

1. **Uruchom GUI test:**
   ```bash
   python test_rm_gui.py
   ```

2. **Wybierz projekt 100** z listy (automatycznie zainicjalizowany)

3. **Rozpocznij etap PROJEKT:**
   - Kliknij 🟢 START PROJEKT
   - Status zmienia się na "● TRWA"
   - Auto-sync do master.sqlite

4. **Zakończ etap PROJEKT:**
   - Kliknij 🔴 END PROJEKT
   - Pojawi się komunikat z variance
   - Auto-sync do master.sqlite

5. **Zobacz Timeline:**
   - Zakładka "Timeline"
   - Sprawdź forecast dla kolejnych etapów
   - Multi-period history

6. **Dashboard:**
   - Zakładka "Dashboard"
   - Status projektu: 🟢 ON_TRACK / 🟡 AT_RISK / 🔴 DELAYED
   - Variance, critical path

7. **Historia:**
   - Zakładka "Historia"
   - Wszystkie okresy (zakończone i aktywne)

## 🔄 Lazy Initialization

Przy pierwszym otwarciu projektu z master.sqlite:

1. GUI sprawdza czy projekt istnieje w rm_manager.sqlite
2. Jeśli NIE → **auto-init** z domyślną konfiguracją:
   - 8 etapów (PRZYJETY → POPRAWKI)
   - Dependency graph (FS/SS)
   - Template dates (szacowania z started_at)
3. Projekty gotowe do użycia!

## 🔄 Sync z RM_BAZA

Menu → **Narzędzia** → **Sync z RM_BAZA**

Aktualizuje `master.sqlite`:
- `projects.status` = najważniejszy aktywny etap

## ⚙️ Konfiguracja - Szczegóły

### Plik konfiguracyjny JSON

**Lokalizacja:** `C:\RMPAK_CLIENT\manager_sync_config.json` (na sztywno w kodzie)

**Zawartość:**
```json
{
    "master_db_path": "Y:/RM_BAZA/master.sqlite",
    "rm_db_path": "rm_manager.sqlite",
    "_comment": "RM_MANAGER configuration file - edit paths as needed"
}
```

**Parametry:**
- `master_db_path` - ścieżka do wspólnego master.sqlite (RM_BAZA)
  - Może być sieciowa: `Y:/RM_BAZA/master.sqlite`
  - Może być lokalna: `C:/RM_BAZA/master.sqlite`
  - **WAŻNE:** Ta sama baza co RM_BAZA GUI!
  
- `rm_db_path` - ścieżka do rm_manager.sqlite
  - Domyślnie: `rm_manager.sqlite` (katalog roboczy)
  - Można zmienić na: `C:/RM_MANAGER/rm_manager.sqlite`

### Jak zmienić konfigurację:

**Opcja 1 - Przez GUI:**
1. Menu → **Plik** → **Konfiguracja ścieżek...**
2. Wybierz plik master.sqlite
3. Ścieżka zostanie zapisana w JSON

**Opcja 2 - Ręczna edycja:**
1. Otwórz w Notatniku: `C:\RMPAK_CLIENT\manager_sync_config.json`
2. Zmień `master_db_path` na swoją ścieżkę
3. Zapisz plik
4. Uruchom GUI ponownie

**Przykłady konfiguracji:**

*Środowisko produkcyjne (sieć):*
```json
{
    "master_db_path": "Y:/RM_BAZA/master.sqlite",
    "rm_db_path": "rm_manager.sqlite"
}
```

*Środowisko testowe (lokalne):*
```json
{
    "master_db_path": "C:/test/master.sqlite",
    "rm_db_path": "C:/test/rm_manager.sqlite"
}
```

### Rozwiązywanie problemów:

**Problem:** "Nie znaleziono bazy RM_BAZA"
- **Rozwiązanie:** Sprawdź czy `master_db_path` w JSON wskazuje na prawidłowy plik
- Użyj Menu → Plik → Konfiguracja ścieżek... i wybierz plik ponownie

**Problem:** Plik JSON nie istnieje
- **Rozwiązanie:** GUI utworzy go automatycznie przy pierwszym uruchomieniu
- Lub skopiuj `manager_sync_config.json` z katalogu projektu do `C:\RMPAK_CLIENT\`

**Problem:** Nie mam uprawnień do `C:\RMPAK_CLIENT\`
- **Rozwiązanie:** Zmień stałą `CONFIG_FILE_PATH` w pliku `rm_manager_gui.py` (linia ~30)
- Lub uruchom jako administrator i utwórz katalog `C:\RMPAK_CLIENT\`
- `project_statuses` = checkboxy dla RM_BAZA

## ⚠️ Multi-period tracking (powroty)

Etapy mogą wracać wielokrotnie! Przykład:

1. START MONTAZ
2. END MONTAZ (problem wykryty)
3. START MONTAZ (powrót - poprawki)
4. END MONTAZ (OK)

Historia pokaże 2 okresy dla MONTAZ!

## 🎨 Kolory statusów

- **🟢** - Etap trwa
- **⏺️** - Etap nieaktywny
- **✔️** - Zakończony (actual)
- **📋** - Planowany (forecast)
- **✅** - On time / ahead
- **⚠️** - Opóźniony

## 📚 Dokumentacja

- [PROJECT_STATS_MANAGER_SPEC.md](PROJECT_STATS_MANAGER_SPEC.md) - Specyfikacja kompletna
- [RM_MANAGER_DEPLOY.md](RM_MANAGER_DEPLOY.md) - Instrukcja wdrożenia

## 🐛 Troubleshooting

### Problem: "No module named 'rm_manager'"
**Rozwiązanie:** Upewnij się że `rm_manager.py` jest w tym samym katalogu

### Problem: "unable to open database file"
**Rozwiązanie:** Sprawdź uprawnienia do zapisu w katalogu

### Problem: Lista projektów pusta
**Rozwiązanie:** Uruchom `test_rm_gui.py` aby utworzyć przykładowe projekty

### Problem: GUI się nie uruchamia na Windows
**Rozwiązanie:** Tkinter powinno być zainstalowane z Pythonem. Sprawdź:
```bash
python -m tkinter
```

## 🚀 Produkcja

Dla wdrożenia produkcyjnego zmień ścieżki na SMB:

```python
# W rm_manager_gui.py:
RM_DB_PATH = "Y:/RM_MANAGER/rm_manager.sqlite"
MASTER_DB_PATH = "Y:/RM_BAZA/master.sqlite"  # WSPÓLNY!
```

### Architektura produkcyjna:

```
Y:/RM_BAZA/                     ← Istniejący system (read-only dla użytkowników)
├─ master.sqlite                ← WSPÓLNY dla obu systemów
├─ projekt_123/
│  └─ data.sqlite              ← Dane BOM
└─ locks/

Y:/RM_MANAGER/                  ← Nowy system (zarządzanie procesem)
└─ rm_manager.sqlite            ← Jedna baza dla wszystkich projektów
```

### Workflow:
1. **RM_BAZA** - użytkownicy przeglądają projekty (read-only)
2. **RM_MANAGER** - manager zarządza procesem (START/END etapów)
3. Auto-sync → statusy widoczne w obu systemach

**UWAGA:** Nie używaj `rm_database_manager.py` i `rm_lock_manager.py` - RM_MANAGER ma jedną centralną bazę!

## 🎉 Gotowe!

System RM_MANAGER jest **w pełni funkcjonalny i zintegrowany z RM_BAZA**:
- ✅ Backend z multi-period tracking
- ✅ GUI (Tkinter w stylu RM_BAZA)
- ✅ **Integracja z master.sqlite** (współdzielony)
- ✅ **Lazy initialization** (auto-init projektów)
- ✅ **Auto-sync** (synchronizacja po każdej zmianie)
- ✅ Timeline visualization
- ✅ Critical path analysis
- ✅ Dashboard (variance, forecast)
- ✅ Testy

**Możesz zacząć używać!** 🚀

## 🔗 Jak to działa razem:

```
UŻYTKOWNIK RM_BAZA                    MANAGER RM_MANAGER
     │                                      │
     ├─ Przegląd projektów                 │
     │  (read-only)                        │
     │                                      │
     │                              ┌───────┴────────┐
     │                              │ Wybiera projekt│
     │                              │ (lazy init!)   │
     │                              └───────┬────────┘
     │                                      │
     │                              ┌───────┴────────┐
     │                              │ START/END etap │
     │                              └───────┬────────┘
     │                                      │
     │                              ┌───────┴────────┐
     │                              │   Auto-sync    │
     │                              └───────┬────────┘
     │                                      │
     ├─ Widzi nowy status ◄────────────────┘
     │  (master.sqlite)
```

**Source of truth:** RM_MANAGER → sync → RM_BAZA (display)
