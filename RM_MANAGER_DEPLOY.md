# RM_MANAGER - Instrukcja wdrożenia

## 📦 Wymagane pliki

Skopiuj następujące pliki do katalogu `C:\RMPAK_CLIENT\RM_MANAGER\`:

### 1. Główny moduł (WYMAGANY):
```
rm_manager.py          (1089 linii) - główna logika biznesowa
rm_manager_gui.py      (650+ linii) - interfejs GUI (Tkinter)
```

### 2. Infrastruktura (OPCJONALNE - dla produkcji z SMB):
```
rm_database_manager.py (447 linii)  - SMB connection manager
rm_lock_manager.py     (188 linii)  - heartbeat locks
```

### 3. Testy:
```
test_rm_manager.py     (290+ linii) - test backend (bez GUI)
test_rm_gui.py         (150+ linii) - test GUI z przykładowymi danymi
```

## 🚀 Szybki start

### Minimalna instalacja (tylko test lokalny):
```
C:\RMPAK_CLIENT\RM_MANAGER\
├─ rm_manager.py
└─ test_rm_manager.py
```

### Pełna instalacja (produkcja):
```
C:\RMPAK_CLIENT\RM_MANAGER\
├─ rm_manager.py
├─ rm_database_manager.py
├─ rm_lock_manager.py
├─ test_rm_manager.py
└─ rm_manager.sqlite          (utworzy się automatycznie)
```

## ▶️ Uruchomienie

### Test backend (bez GUI):
1. Otwórz CMD lub PowerShell
2. Przejdź do katalogu:
   ```
   cd C:\RMPAK_CLIENT\RM_MANAGER
   ```
3. Uruchom test:
   ```
   python test_rm_manager.py
   ```

### Test GUI (z przykładowymi danymi):
1. Przejdź do katalogu:
   ```
   cd C:\RMPAK_CLIENT\RM_MANAGER
   ```
2. Uruchom GUI test:
   ```
   python test_rm_gui.py
   ```
   Utworzy 3 przykładowe projekty i uruchomi GUI

### Uruchomienie GUI (produkcja):
```
python rm_manager_gui.py
```

## 🖥️ GUI - Interfejs użytkownika

### Główne okno RM_MANAGER GUI:

```
┌────────────────────────────────────────────────────────────────────┐
│ RM_MANAGER - Zarządzanie procesami projektów              [_ □ X] │
├────────────────────────────────────────────────────────────────────┤
│ Plik  Widok  Narzędzia                                            │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Projekt: [Projekt 100 ▼]  🔄 Odśwież                            │
│                                                                    │
├──────────────────────┬─────────────────────────────────────────────┤
│ ETAPY PROJEKTU       │ 📅 Timeline | 📊 Dashboard | 📜 Historia   │
│                      │                                             │
│ ┌──── Projekt ─────┐ │ ┌──────────────────────────────────────┐  │
│ │ ● TRWA           │ │ │ TIMELINE - Projekt 100               │  │
│ │                  │ │ │                                      │  │
│ │ 🔴 START PROJEKT │ │ │ 🟢 📋 PROJEKT                        │  │
│ │ 🟢 END PROJEKT   │ │ │    Template:  2026-04-02 → 2026-04-15│  │
│ └──────────────────┘ │ │    Forecast:  2026-04-02 → 2026-04-15│  │
│                      │ │    Variance:  0 dni ✅                │  │
│ ┌── Kompletacja ──┐ │ │                                      │  │
│ │ ○ Nieaktywny    │ │ │ ⏺️  📋 KOMPLETACJA                    │  │
│ │                  │ │ │    Template:  2026-04-15 → 2026-04-22│  │
│ │ 🟢 START         │ │ │    Forecast:  2026-04-15 → 2026-04-22│  │
│ │ 🔴 END           │ │ │    Variance:  0 dni ✅                │  │
│ └──────────────────┘ │ │                                      │  │
│                      │ │ [więcej etapów...]                   │  │
│ ┌──── Montaż ─────┐ │ │                                      │  │
│ │ ○ Nieaktywny    │ │ └──────────────────────────────────────┘  │
│ │ ...              │ │                                            │
│                      │                                            │
├──────────────────────┴─────────────────────────────────────────────┤
│ Gotowy                                                             │
└────────────────────────────────────────────────────────────────────┘
```

### Funkcje GUI:

#### 1. **Project Selector**
- Wybór projektu z listy
- Autocomplete
- Szybkie przełączanie między projektami

#### 2. **Stage Buttons** (lewy panel)
- 🟢 **START** - rozpocznij etap
- 🔴 **END** - zakończ etap
- Status indicator: ● TRWA / ○ Nieaktywny
- Automatyczne włączanie/wyłączanie buttonów

#### 3. **Timeline Tab** (prawy panel)
- Forecast dla każdego etapu
- Template vs Forecast comparison
- Variance (opóźnienie/przyspieszenie)
- Multi-period history (powroty etapów)

#### 4. **Dashboard Tab**
- Status projektu (🟢 ON_TRACK / 🟡 AT_RISK / 🔴 DELAYED)
- Overall variance
- Completion forecast
- Aktywne etapy
- **Critical Path** - 5 kluczowych etapów

#### 5. **Historia Tab**
- Tabela wszystkich okresów
- Start/End timestamps
- Duration
- Status (Aktywny/Zakończony)

#### 6. **Menu**
- **Plik**: Nowy projekt, Import/Export
- **Widok**: Odśwież, Sortowanie
- **Narzędzia**: 
  - Sync z RM_BAZA (master.sqlite)
  - Critical Path Analysis
  - Export do Excel

## ✅ Oczekiwany wynik testu

```
================================================================================
TEST RM_MANAGER - Podstawowy workflow
================================================================================

1️⃣  Inicjalizacja bazy...
✅ Utworzono 10 definicji etapów
✅ RM_MANAGER centralna baza zainicjalizowana: C:\RMPAK_CLIENT\RM_MANAGER\test_rm_manager.sqlite

2️⃣  Tworzenie projektu 12345...
✅ Projekt 12345 zainicjalizowany: 7 etapów, 6 zależności

3️⃣  Symulacja pracy nad projektem...
   🟢 START: PRZYJETY
✅ START: PRZYJETY (project=12345, period_id=1)
   ...

✅ TEST ZAKOŃCZONY
🎉 WSZYSTKIE TESTY ZAKOŃCZONE

💾 Pliki testowe w katalogu: C:\RMPAK_CLIENT\RM_MANAGER
   - test_rm_manager.sqlite
   - test_master.sqlite
```

**Uwaga:** Bazy testowe są tworzone w tym samym katalogu co skrypt (cross-platform compatibility).

## ❌ Typowe problemy

### Problem 1: ModuleNotFoundError: No module named 'rm_manager'
**Przyczyna:** Brak pliku `rm_manager.py` w katalogu  
**Rozwiązanie:** Skopiuj `rm_manager.py` do katalogu z testem

### Problem 2: ImportError podczas importu rm_manager
**Przyczyna:** Błąd składniowy w `rm_manager.py`  
**Rozwiązanie:** Sprawdź czy plik został skopiowany kompletnie (1089 linii)

### Problem 3: sqlite3.OperationalError: unable to open database file
**Przyczyna:** Ścieżka `/tmp/` nie istnieje w Windows  
**Rozwiązanie:** ✅ NAPRAWIONE - test używa katalogu lokalnego (cross-platform)

## 📚 Struktura produkcyjna

Dla prawdziwego środowiska (LAN/SMB):

```
Y:/RM_MANAGER/                      ← katalog sieciowy (SMB)
├─ rm_manager.sqlite                ← CENTRALNA BAZA (wszystkie projekty!)
├─ LOCKS/
│  ├─ project_12345.lock
│  └─ project_12346.lock
└─ BACKUPS/                         ← opcjonalnie
    └─ rm_manager_YYYYMMDD.sqlite
```

## 🔧 Konfiguracja dla produkcji

W kodzie aplikacji użyj:

```python
import rm_manager as rmm

# Ścieżka do centralnej bazy (SMB)
RM_DB_PATH = "Y:/RM_MANAGER/rm_manager.sqlite"

# Inicjalizacja (uruchom raz)
rmm.ensure_rm_manager_tables(RM_DB_PATH)

# Użycie
rmm.init_project(RM_DB_PATH, project_id, stages_config, dependencies_config)
rmm.start_stage(RM_DB_PATH, project_id, "MONTAZ", started_by="Jan Kowalski")
rmm.end_stage(RM_DB_PATH, project_id, "MONTAZ", ended_by="Jan Kowalski")

# Forecast
forecast = rmm.recalculate_forecast(RM_DB_PATH, project_id)

# Sync z RM_BAZA (opcjonalnie)
rmm.sync_to_master(RM_DB_PATH, "Y:/RM_BAZA/master.sqlite", project_id)
```

## 📊 Integracja z istniejącym master.sqlite

RM_MANAGER może współpracować z RM_BAZA:

```python
# RM_MANAGER autonomiczny
rm_db = "Y:/RM_MANAGER/rm_manager.sqlite"

# RM_BAZA master (współdzielony)
master_db = "Y:/RM_BAZA/master.sqlite"

# Sync do RM_BAZA (opcjonalnie - tylko display status)
rmm.sync_to_master(rm_db, master_db, project_id)
```

## 🆘 Pomoc

Jeśli test się nie uruchamia:

1. Sprawdź czy Python zainstalowany: `python --version`
2. Sprawdź czy pliki w katalogu: `dir C:\RMPAK_CLIENT\RM_MANAGER`
3. Sprawdź uprawnienia do zapisu
4. Uruchom z verbose: `python -v test_rm_manager.py`

## 📖 Dokumentacja

Kompletna specyfikacja: `PROJECT_STATS_MANAGER_SPEC.md`
