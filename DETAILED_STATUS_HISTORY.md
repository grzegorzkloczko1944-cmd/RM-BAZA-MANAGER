# Szczegółowa Historia Statusów - Dokumentacja

## 📊 Przegląd

System został rozszerzony o **szczegółowe śledzenie historii każdego statusu osobno**. Każde dodanie lub usunięcie statusu jest zapisywane jako osobny wpis w bazie danych.

## 🆕 Nowa tabela: `project_status_changes`

```sql
CREATE TABLE project_status_changes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id     INTEGER NOT NULL,
    status         TEXT NOT NULL,
    action         TEXT NOT NULL CHECK(action IN ('ADDED', 'REMOVED')),
    changed_at     TEXT NOT NULL,
    changed_by     TEXT,
    notes          TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
)
```

### Przykładowe dane:

```
id | project_id | status    | action  | changed_at          | changed_by | notes
---|------------|-----------|---------|---------------------|------------|----------------------
1  | 1          | PRZYJETY  | ADDED   | 2026-03-26 10:00:00 | admin      | Status PRZYJETY dodany
2  | 1          | PROJEKT   | ADDED   | 2026-03-26 10:00:00 | admin      | Status PROJEKT dodany
3  | 1          | MONTAZ    | ADDED   | 2026-03-26 14:30:00 | admin      | Status MONTAZ dodany
4  | 1          | PROJEKT   | REMOVED | 2026-03-27 09:00:00 | admin      | Status PROJEKT usunięty
5  | 1          | ODBIORY   | ADDED   | 2026-03-28 15:00:00 | admin      | Status ODBIORY dodany
```

## 🔧 Migracja

### Krok 1: Upewnij się że masz bazową migrację

```bash
# Jeśli jeszcze nie uruchomiłeś:
python migrate_multi_status.py
```

### Krok 2: Uruchom migrację szczegółowej historii

```bash
python migrate_detailed_status_history.py
```

Skrypt automatycznie:
- Znajdzie bazę danych z pliku config
- Sprawdzi czy wymagana tabela `project_statuses` istnieje
- Utworzy tabelę `project_status_changes`
- Utworzy 3 indeksy dla szybkiego wyszukiwania

## 📈 Możliwości analizy

### 1. Pełna historia projektu

```python
from project_manager import get_status_detailed_history

# Pobierz wszystkie zmiany dla projektu
history = get_status_detailed_history(con, project_id=1)

for record in history:
    id, status, action, changed_at, changed_by, notes = record
    print(f"{changed_at}: {action} {status} by {changed_by}")
```

**Wynik:**
```
2026-03-28 15:00:00: ADDED ODBIORY by admin
2026-03-27 09:00:00: REMOVED PROJEKT by admin
2026-03-26 14:30:00: ADDED MONTAZ by admin
2026-03-26 10:00:00: ADDED PROJEKT by admin
2026-03-26 10:00:00: ADDED PRZYJETY by admin
```

### 2. Historia konkretnego statusu

```python
# Tylko zmiany statusu MONTAZ
history = get_status_detailed_history(con, project_id=1, status="MONTAZ")
```

### 3. Linia czasu (timeline)

```python
from project_manager import get_status_timeline

timeline = get_status_timeline(con, project_id=1)

# Zwraca:
{
    "MONTAZ": [
        {"action": "ADDED", "changed_at": "2026-03-26 14:30", "changed_by": "admin"},
        {"action": "REMOVED", "changed_at": "2026-03-27 16:00", "changed_by": "john"}
    ],
    "ODBIORY": [
        {"action": "ADDED", "changed_at": "2026-03-28 15:00", "changed_by": "admin"}
    ]
}
```

### 4. Czas spędzony w statusie

```python
from project_manager import get_status_duration, get_all_statuses_duration

# Ile dni w statusie MONTAZ?
days = get_status_duration(con, project_id=1, status="MONTAZ")
print(f"Projekt spędził {days:.1f} dni w statusie MONTAZ")

# Wszystkie statusy naraz
durations = get_all_statuses_duration(con, project_id=1)
# Zwraca: {"MONTAZ": 3.5, "PROJEKT": 1.2, "ODBIORY": 0.8, ...}
```

### 5. Czy status jest obecnie aktywny?

```python
from project_manager import is_status_currently_active

if is_status_currently_active(con, project_id=1, status="MONTAZ"):
    print("Projekt jest obecnie w fazie montażu")
```

## 🔍 Jak to działa?

### Automatyczne zapisywanie

Gdy edytujesz projekt w GUI i zmieniasz checkboxy statusów:

**Przed zapisem:**
- Projekt ma statusy: `["PROJEKT", "MONTAZ"]`

**Po zapisie:**
- Projekt ma statusy: `["PROJEKT", "MONTAZ", "ODBIORY"]`

**System automatycznie zapisze:**
```sql
INSERT INTO project_status_changes 
(project_id, status, action, changed_at, changed_by)
VALUES 
(1, 'ODBIORY', 'ADDED', '2026-03-26 14:30', 'admin')
```

**Jeśli odznaczysz checkbox:**
- Odznaczenie `MONTAZ`

**System zapisze:**
```sql
INSERT INTO project_status_changes 
(project_id, status, action, changed_at, changed_by)
VALUES 
(1, 'MONTAZ', 'REMOVED', '2026-03-26 14:35', 'admin')
```

## 📊 Przykłady użycia

### Raport czasu w statusach

```python
from project_manager import get_all_statuses_duration

durations = get_all_statuses_duration(con, project_id=1)

print("Raport czasu projektu w statusach:")
print("=" * 50)
for status, days in sorted(durations.items(), key=lambda x: -x[1]):
    print(f"{status:15} {days:6.1f} dni")
```

### Audyt zmian

```python
from project_manager import get_status_detailed_history

print("Historia zmian statusów:")
print("=" * 80)

history = get_status_detailed_history(con, project_id=1)
for record in history:
    _, status, action, changed_at, changed_by, notes = record
    symbol = "✅" if action == "ADDED" else "❌"
    print(f"{changed_at} {symbol} {status:15} by {changed_by:12} - {notes}")
```

### Wykryj problemy

```python
# Projekt wstrzymany ponad 7 dni?
if is_status_currently_active(con, project_id=1, status="WSTRZYMANY"):
    days = get_status_duration(con, project_id=1, status="WSTRZYMANY")
    if days > 7:
        print(f"⚠️  UWAGA: Projekt wstrzymany już {days:.0f} dni!")
```

## ⚠️ Ważne uwagi

### Historia zaczyna się od migracji

- **Stare dane:** Przed uruchomieniem migracji = brak szczegółowej historii
- **Nowe dane:** Od momentu migracji = pełna szczegółowa historia
- **Backward compatibility:** Stary system historii (`project_status_history`) nadal działa

### Wydajność

- 3 indeksy zapewniają szybkie zapytania
- Historia rośnie z każdą zmianą (nie z każdym zapisem projektu)
- Przykład: 100 projektów × 20 zmian = 2000 rekordów (niewiele)

### Usuwanie danych

```sql
-- Usuń historię dla konkretnego projektu
DELETE FROM project_status_changes WHERE project_id = 123;

-- Usuń historię starszą niż 1 rok
DELETE FROM project_status_changes 
WHERE changed_at < datetime('now', '-1 year');
```

## 🎯 Różnice: Stary vs Nowy system

### Stary system (`project_status_history`)

```
old_status: "MONTAZ, PROJEKT"
new_status: "MONTAZ, ODBIORY, PROJEKT"
```
- ❌ Nie wiadomo który status został dodany
- ❌ Nie można obliczyć czasu w konkretnym statusie
- ✅ Widać cały zestaw statusów w danym momencie

### Nowy system (`project_status_changes`)

```
status: "ODBIORY", action: "ADDED", changed_at: "2026-03-26 14:30"
status: "MONTAZ", action: "REMOVED", changed_at: "2026-03-27 09:00"
```
- ✅ Dokładnie wiadomo co się zmieniło
- ✅ Można obliczyć czas w każdym statusie
- ✅ Pełny audyt kto i kiedy
- ✅ Możliwość analizy i raportowania

## 🔄 Integracja z GUI

Żadnych zmian w GUI nie trzeba robić! System działa automaticznie w tle:

1. Użytkownik edytuje projekt
2. Zmienia checkboxy statusów
3. Klika "Zapisz"
4. `set_project_statuses()` automatycznie:
   - Porównuje stare i nowe statusy
   - Dodaje wpisy ADDED dla nowych statusów
   - Dodaje wpisy REMOVED dla usuniętych statusów
   - Zapisuje wszystko w `project_status_changes`

**Zero zmian w interface - wszystko działa automatycznie!** 🎉
