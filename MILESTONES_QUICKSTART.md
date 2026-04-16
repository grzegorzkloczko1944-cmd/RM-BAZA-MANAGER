# MILESTONES vs STAGES - Przewodnik szybki start

## 🎯 Czym są Milestones?

**MILESTONE** = zdarzenie instant (bez czasu trwania)
- ✅ **PRZYJĘTY** - moment przyjęcia projektu (trigger)
- ✅ **ZAKOŃCZONY** - moment zakończenia projektu

**STAGE** = etap z czasem trwania (od...do)
- PROJEKT, KOMPLETACJA, MONTAŻ, ELEKTROMONTAŻ, URUCHOMIENIE, ODBIORY, POPRAWKI, WSTRZYMANY

---

## 🔥 Kluczowe różnice

### MILESTONE (PRZYJĘTY, ZAKOŃCZONY)
```
❌ NIE MA czasu trwania
❌ NIE MA START / END
✅ Tylko data zdarzenia: 01-03-2026 14:30 ✔
```

**W GUI:**
- Checkbox + pole daty
- Brak przycisków START/END
- Timeline: punkt (nie przedział)

**W kodzie:**
```python
# Ustaw milestone
rmm.set_milestone(db_path, project_id, 'PRZYJETY', user='Jan Kowalski')

# Sprawdź czy ustawiony
if rmm.is_milestone_set(db_path, project_id, 'PRZYJETY'):
    print("Projekt przyjęty!")

# Pobierz info
info = rmm.get_milestone(db_path, project_id, 'PRZYJETY')
# {'timestamp': '2026-03-31 14:30', 'user': 'Jan Kowalski', 'notes': None}
```

---

### STAGE (PROJEKT, MONTAŻ, ...)
```
✅ MA czas trwania
✅ MA START i END
✅ Przedział: 01-03-2026 → 15-03-2026
```

**W GUI:**
- Przyciski START / KONIEC
- Timeline: przedział z czasem trwania

**W kodzie:**
```python
# Start etapu
rmm.start_stage(db_path, project_id, 'PROJEKT', started_by='Jan Kowalski')

# Koniec etapu
rmm.end_stage(db_path, project_id, 'PROJEKT', ended_by='Jan Kowalski')
```

---

## 🧠 Walidacja: PRZYJĘTY blokuje start PROJEKT

**ZASADA:** Projekt musi być przyjęty zanim jakikolwiek etap się rozpocznie.

```python
# ❌ Próba startu bez PRZYJĘTY
rmm.start_stage(db_path, project_id, 'PROJEKT')
# ValueError: Nie można rozpocząć PROJEKT: Projekt nie został przyjęty. 
#            Ustaw milestone PRZYJĘTY najpierw.

# ✅ Poprawna kolejność
rmm.set_milestone(db_path, project_id, 'PRZYJETY', user='Admin')
rmm.start_stage(db_path, project_id, 'PROJEKT', started_by='Jan')
```

---

## 🔧 Migracja starych danych

Stare projekty mogły mieć PRZYJĘTY i ZAKOŃCZONY jako etapy z czasem trwania.

### Automatyczna migracja

```python
import rm_manager as rmm

# Konwertuj wszystkie PRZYJĘTY/ZAKOŃCZONY na instant
result = rmm.migrate_milestones_to_instant(project_db_path)
print(f"Zaktualizowano: {result['periods_updated']} okresów")
```

### Z GUI

1. Menu: **Narzędzia** → **🔄 Migruj milestones na instant**
2. Potwierdź operację
3. Gotowe! PRZYJĘTY i ZAKOŃCZONY są teraz instant

---

## 📊 W bazie danych

### Tabela `stage_definitions`

```sql
CREATE TABLE stage_definitions (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE,
    display_name TEXT,
    color TEXT,
    is_milestone INTEGER DEFAULT 0  -- 🔥 NOWA KOLUMNA
);

-- Milestones
INSERT INTO stage_definitions VALUES (1, 'PRZYJETY', 'Przyjęty', '#3498db', 1);
INSERT INTO stage_definitions VALUES (10, 'ZAKONCZONY', 'Zakończony', '#2c3e50', 1);

-- Stages
INSERT INTO stage_definitions VALUES (2, 'PROJEKT', 'Projekt', '#9b59b6', 0);
```

### Tabela `stage_actual_periods`

```sql
-- MILESTONE: started_at = ended_at (instant)
INSERT INTO stage_actual_periods (project_stage_id, started_at, ended_at)
VALUES (1, '2026-03-31 14:30', '2026-03-31 14:30');  -- PRZYJĘTY

-- STAGE: started_at != ended_at (okres)
INSERT INTO stage_actual_periods (project_stage_id, started_at, ended_at)
VALUES (2, '2026-03-31 15:00', NULL);  -- PROJEKT (trwa)
```

---

## 🚀 API Reference

### Funkcje dla Milestones

```python
# Sprawdź czy to milestone
rmm.is_milestone(db_path, 'PRZYJETY')  # → True
rmm.is_milestone(db_path, 'PROJEKT')   # → False

# Ustaw milestone
period_id = rmm.set_milestone(
    db_path, 
    project_id, 
    'PRZYJETY', 
    user='Jan Kowalski',
    notes='Umowa podpisana',
    timestamp='2026-03-31 14:30'  # opcjonalnie (domyślnie NOW)
)

# Sprawdź czy ustawiony
rmm.is_milestone_set(db_path, project_id, 'PRZYJETY')  # → True/False

# Pobierz info
info = rmm.get_milestone(db_path, project_id, 'PRZYJETY')
# → {'timestamp': '...', 'user': '...', 'notes': '...'}

# Usuń milestone (cofnij)
rmm.unset_milestone(db_path, project_id, 'PRZYJETY')
```

### Funkcje dla Stages

```python
# Walidacja przed startem
can_start, reason = rmm.can_start_stage(db_path, project_id, 'PROJEKT')
if not can_start:
    print(f"Nie można: {reason}")

# Start etapu
period_id = rmm.start_stage(
    db_path, 
    project_id, 
    'PROJEKT',
    started_by='Jan Kowalski',
    notes='Rozpoczęto projektowanie'
)

# Koniec etapu
rmm.end_stage(
    db_path, 
    project_id, 
    'PROJEKT',
    ended_by='Jan Kowalski',
    notes='Dokumentacja gotowa'
)

# Aktywne etapy
active = rmm.get_active_stages(db_path, project_id)
# → [{'stage_code': 'MONTAZ', 'started_at': '...', ...}]
```

---

## ⚠️ Błędy i walidacja

```python
# ❌ Próba użycia start_stage() dla milestone
rmm.start_stage(db_path, project_id, 'PRZYJETY')
# ValueError: ⚠️  PRZYJETY jest milestone! Użyj set_milestone() zamiast start_stage().

# ❌ Próba użycia end_stage() dla milestone
rmm.end_stage(db_path, project_id, 'PRZYJETY')
# ValueError: ⚠️  PRZYJETY jest milestone! Milestones nie mają END.

# ❌ Start projektu bez PRZYJĘTY
rmm.start_stage(db_path, project_id, 'PROJEKT')
# ValueError: Nie można rozpocząć PROJEKT: Projekt nie został przyjęty.

# ❌ Podwójne ustawienie milestone
rmm.set_milestone(db_path, project_id, 'PRZYJETY', user='Admin')
rmm.set_milestone(db_path, project_id, 'PRZYJETY', user='User')
# ValueError: Milestone PRZYJETY już ustawiony!
```

---

## 🎨 W Timeline (oś czasu)

### Milestone
```
PRZYJĘTY: 01-03-2026 14:30 ✔
```
- Punkt na osi czasu
- Bez przedziału
- Ikona ✔

### Stage
```
PROJEKT:  01-03-2026 15:00 → 15-03-2026 18:00
          |────────────────────────────────|
          14 dni
```
- Przedział z czasem trwania
- Ikona 🟢 (aktywny) / ⏺️ (zakończony)

---

## 🔄 Upgrade do OPCJA A (przyszłość)

Obecnie: **OPCJA C** (flaga `is_milestone` w `stage_definitions`)

W przyszłości (jeśli potrzeba):
- Osobna tabela `project_milestones`
- Więcej typów eventów (REVIEW, APPROVAL, etc.)
- Lepsza analityka historii
- Notifications / alerts

**Migracja będzie automatyczna** - obecna struktura jest kompatybilna w przód.

---

## 📚 Zobacz też

- `RM_MANAGER_SPEC.md` - pełna specyfikacja systemu
- `FILE_INTEGRITY_TRACKING.md` - śledzenie plików projektów
- `MULTI_STATUS_README.md` - multi-status checkboxy
