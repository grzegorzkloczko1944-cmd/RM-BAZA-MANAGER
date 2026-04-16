# 🔧 POPRAWKA: "no such column" - rm_manager_gui.py

## ❌ Problem
Użytkownik zgłosił błąd: **"no such column"** przy ładowaniu projektów w RM_MANAGER GUI.

## 🔍 Analiza
Zapytania SQL w `rm_manager_gui.py` używały nazw kolumn z **testowego schematu**, które różniły się od **produkcyjnego schematu** (`schema_full_master_SQLITE.txt`):

### Błędne zapytania (przed poprawką):
```sql
-- load_projects()
SELECT 
    COALESCE(project_id, id) as pid,        ❌ 'id' nie istnieje
    name,
    COALESCE(is_active, 1) as is_active     ❌ 'is_active' nie istnieje
FROM projects
WHERE COALESCE(is_active, 1) = 1

-- get_project_dates_from_master()
SELECT started_at, expected_delivery, completed_at
FROM projects
WHERE id = ? OR project_id = ?              ❌ 'id' nie istnieje
```

### Schemat produkcyjny (schema_full_master_SQLITE.txt):
```sql
CREATE TABLE projects (
    project_id INTEGER PRIMARY KEY,      -- PRIMARY KEY (NIE 'id')
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,   -- 'active' (NIE 'is_active')
    project_type TEXT NOT NULL,
    status TEXT NOT NULL,
    ...
)
```

## ✅ Rozwiązanie

### 1. Poprawione zapytania SQL w rm_manager_gui.py:

**load_projects():**
```sql
SELECT 
    project_id as pid,                   ✅ używa project_id
    name,
    COALESCE(active, 1) as active        ✅ używa active
FROM projects
WHERE COALESCE(active, 1) = 1
ORDER BY name COLLATE NOCASE
```

**get_project_dates_from_master():**
```sql
SELECT started_at, expected_delivery, completed_at
FROM projects
WHERE project_id = ?                     ✅ tylko project_id
```

### 2. Poprawiony test_rm_gui.py:

**CREATE TABLE (zgodny z produkcją):**
```sql
CREATE TABLE projects (
    project_id INTEGER PRIMARY KEY,      ✅ PRIMARY KEY
    name TEXT NOT NULL,
    path TEXT,
    active INTEGER NOT NULL DEFAULT 1,   ✅ active (nie is_active)
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    project_type TEXT NOT NULL DEFAULT 'MACHINE',
    started_at TEXT,
    expected_delivery TEXT,
    completed_at TEXT,
    designer TEXT,
    status TEXT NOT NULL DEFAULT 'W_REALIZACJI',
    status_changed_at TEXT,
    sat TEXT,
    fat TEXT
)
```

**INSERT (używa 'active' zamiast 'is_active'):**
```sql
INSERT INTO projects (project_id, name, project_type, designer, status, started_at, active)
VALUES (100, '100 - Linia produkcyjna A', 'MACHINE', 'Jan Kowalski', 'PROJEKT', '2026-04-01', 1)
```

### 3. Utworzono narzędzie weryfikacyjne: verify_schema.py

Sprawdza:
- ✅ Zgodność CREATE TABLE z produkcyjnym schematem
- ✅ Poprawność zapytań SQL (load_projects, get_project_dates)
- ✅ Działanie INSERT z prawidłowymi nazwami kolumn

## 📝 Zaktualizowana dokumentacja

### RM_MANAGER_GUI_README.md
Dodano sekcję "WAŻNE - Wymagania dotyczące master.sqlite":
- Wyjaśnienie różnic w schemacie
- Odniesienie do `schema_full_master_SQLITE.txt`
- Link do `verify_schema.py`

### INSTALACJA_RM_MANAGER.md
Dodano sekcję troubleshooting:
- Problem: "no such column: is_active" lub "no such column: id"
- Rozwiązanie krok po kroku
- Przykład prawidłowego schematu

### MANAGER_CONFIG_README.md (bez zmian)
- Plik konfiguracyjny JSON działa poprawnie

## 🧪 Weryfikacja

Uruchom test:
```bash
python verify_schema.py
```

Oczekiwany wynik:
```
✅ Schemat testu zgodny z produkcją
✅ load_projects() - OK
✅ get_project_dates_from_master() - OK
✅ INSERT - OK
✅ Wszystkie zapytania SQL są zgodne ze schematem produkcyjnym!
```

## 📋 Podsumowanie zmian

### Zmienione pliki:
1. ✅ `rm_manager_gui.py` - 2 zapytania SQL poprawione
2. ✅ `test_rm_gui.py` - CREATE TABLE i 3x INSERT poprawione
3. ✅ `RM_MANAGER_GUI_README.md` - dodano wymagania schematu
4. ✅ `INSTALACJA_RM_MANAGER.md` - dodano troubleshooting

### Utworzone pliki:
5. ✅ `verify_schema.py` - narzędzie weryfikacyjne

### Zaktualizowane:
6. ✅ `/memories/bom-project.md` - dodano sekcję o schemacie

## ✨ Rezultat

**RM_MANAGER GUI jest teraz zgodny ze schematem produkcyjnym master.sqlite!**

Użytkownik może:
1. Uruchomić `python rm_manager_gui.py` z prawdziwą bazą produkcyjną
2. Uruchomić `python test_rm_gui.py` do testów (baza zgodna z produkcją)
3. Uruchomić `python verify_schema.py` do weryfikacji

**Błąd "no such column" nie powinien już występować!** ✅
