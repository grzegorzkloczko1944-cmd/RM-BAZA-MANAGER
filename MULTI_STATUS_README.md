# Multi-Status System - Dokumentacja

## 📋 Przegląd

System został rozszerzony o możliwość przypisywania **wielu statusów jednocześnie** do projektów.

## 🆕 Nowe statusy (10 opcji)

1. **PRZYJETY** - Przyjęty do realizacji
2. **PROJEKT** - Faza projektowania
3. **KOMPLETACJA** - Kompletacja materiałów
4. **MONTAZ** - Montaż
5. **AUTOMATYKA** - Prace nad automatyką
6. **URUCHOMIENIE** - Uruchomienie
7. **ODBIORY** - Odbiory
8. **POPRAWKI** - Poprawki
9. **WSTRZYMANY** - Wstrzymany
10. **ZAKONCZONY** - Zakończony

## 🔧 Jak używać

### 1. Migracja bazy danych

Uruchom skrypt migracji aby utworzyć nową tabelę:

**Opcja A: Auto-detect ścieżki z pliku config (ZALECANE)**
```bash
python migrate_multi_status.py
```
Skrypt automatycznie znajdzie ścieżkę do bazy z pliku konfiguracyjnego aplikacji (`C:/RMPAK_CLIENT/sync_config.json`).

**Opcja B: Podaj ścieżkę ręcznie**
```bash
python migrate_multi_status.py "Z:/RM_BAZA/master.sqlite"
```

**Częste błędy:**

❌ **Błąd:** "Podano katalog zamiast pliku"
```bash
# ŹLE - to katalog
python migrate_multi_status.py "Z:/RM_BAZA"

# DOBRZE - pełna ścieżka do pliku
python migrate_multi_status.py "Z:/RM_BAZA/master.sqlite"
```

❌ **Błąd:** "Plik nie istnieje"
- Sprawdź czy litera dysku jest poprawna (Y:, Z:, itp.)
- Sprawdź czy folder RM_BAZA istnieje
- Sprawdź czy plik nazywa się dokładnie `master.sqlite`

### 2. Tworzenie nowego projektu

Nowe projekty automatycznie dostają status **PRZYJETY**.

### 3. Edycja statusów projektu

W oknie listy projektów:
1. Kliknij **"✏️ Edytuj"**
2. W sekcji **"Statusy"** zaznacz checkboxami odpowiednie statusy
3. Możesz zaznaczyć **wiele statusów jednocześnie**
4. Kliknij **"✔ Zapisz"**

### 4. Wyświetlanie statusów

W liście projektów statusy są wyświetlane jako:
- `PROJEKT, MONTAZ, AUTOMATYKA` (wiele statusów)
- `PRZYJETY` (jeden status)
- `(brak)` (brak statusów)

## 🗄️ Struktura bazy danych

### Nowa tabela: `project_statuses`

```sql
CREATE TABLE project_statuses (
    project_id     INTEGER NOT NULL,
    status         TEXT NOT NULL,
    set_at         TEXT NOT NULL DEFAULT (datetime('now')),
    set_by         TEXT,
    PRIMARY KEY (project_id, status),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
)
```

**Relacja:** Many-to-Many (wiele statusów dla jednego projektu)

### Indeksy

- `idx_project_statuses_project` - szybkie wyszukiwanie po project_id
- `idx_project_statuses_status` - wyszukiwanie projektów po statusie

## 🔄 Backward Compatibility

- **Stara kolumna `projects.status`** pozostaje w bazie (nie jest usuwana)
- Stare dane w tej kolumnie są **IGNOROWANE**
- Historia zmian (`project_status_history`) nadal działa
- Istniejące projekty **nie mają** ustawionych statusów w nowym systemie
  - Edytuj projekty ręcznie aby ustawić statusy

## 📝 API (dla programistów)

### Pobieranie statusów

```python
from project_manager import get_project_statuses

# Pobierz listę statusów
statuses = get_project_statuses(con, project_id=5)
# Zwraca: ['PROJEKT', 'MONTAZ', 'AUTOMATYKA']

# Format do wyświetlenia
status_str = ", ".join(statuses) if statuses else "(brak)"
```

### Ustawianie statusów

```python
from project_manager import set_project_statuses

# Ustaw statusy (zastępuje wszystkie poprzednie)
set_project_statuses(
    con, 
    project_id=5,
    statuses=['PROJEKT', 'MONTAZ'],
    set_by='jan.kowalski'
)
```

### Dodawanie/usuwanie pojedynczego statusu

```python
from project_manager import add_project_status, remove_project_status

# Dodaj status (nie usuwa innych)
add_project_status(con, project_id=5, status='AUTOMATYKA', set_by='jan.kowalski')

# Usuń status (pozostałe zostają)
remove_project_status(con, project_id=5, status='MONTAZ', set_by='jan.kowalski')
```

## ⚠️ Ważne uwagi

1. **Automatyczne ustawienie `completed_at`**
   - Gdy status `ZAKONCZONY` jest zaznaczony, `completed_at` jest automatycznie ustawiane na bieżącą datę

2. **Historia zmian**
   - Każda zmiana statusów jest zapisywana w `project_status_history`
   - Format: `"PROJEKT, MONTAZ" -> "PROJEKT, AUTOMATYKA, URUCHOMIENIE"`

3. **Brak statusów**
   - Projekt może nie mieć żadnego statusu (wyświetlane jako `(brak)`)
   - To normalne dla starych projektów przed migracją

## 🚀 Przykłady użycia

### Scenariusz 1: Projekt w realizacji

Zaznacz statusy:
- ✅ PROJEKT
- ✅ KOMPLETACJA  
- ✅ MONTAZ

### Scenariusz 2: Projekt z problemami

Zaznacz statusy:
- ✅ MONTAZ
- ✅ WSTRZYMANY
- ✅ ODBIORY

### Scenariusz 3: Projekt zakończony

Zaznacz statusy:
- ✅ ODBIORY
- ✅ ZAKONCZONY

**Uwaga:** Data odbioru zostanie automatycznie uzupełniona!

## 📊 Monitorowanie

Możesz łatwo sprawdzić ile projektów ma dany status:

```sql
-- Projekty z statusem MONTAZ
SELECT DISTINCT p.project_id, p.name
FROM projects p
JOIN project_statuses ps ON p.project_id = ps.project_id
WHERE ps.status = 'MONTAZ';

-- Ile projektów jest w każdym statusie
SELECT status, COUNT(*) as count
FROM project_statuses
GROUP BY status
ORDER BY count DESC;
```

## 🐛 Troubleshooting

### Problem: "Brak statusów" dla wszystkich projektów

**Rozwiązanie:** Uruchom migrację:
```bash
python migrate_multi_status.py
```

### Problem: Checkboxy nie wyświetlają się

**Rozwiązanie:** 
1. Sprawdź czy zaimportowałeś `PROJECT_STATUSES_NEW` w `RM_BAZA_v15_MAG_STATS_ORG.py`
2. Zrestartuj aplikację

### Problem: Błąd zapisu statusów

**Rozwiązanie:**
1. Sprawdź czy połączenie jest READ-WRITE (nie READ-ONLY)
2. Sprawdź czy użytkownik ma uprawnienia (ADMIN/USER$$)

---

**Data wdrożenia:** 2026-03-26  
**Wersja:** 1.0  
**Autor:** System BOM v15
