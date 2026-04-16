# 🚀 RM_MANAGER - Instalacja i Konfiguracja

## 📦 Co potrzebujesz?

**3 pliki:**
1. `rm_manager.py` - backend (logika)
2. `rm_manager_gui.py` - GUI (interfejs)
3. `manager_sync_config.json` - konfiguracja ścieżek

**Lokalizacja konfiguracji:** `C:\RMPAK_CLIENT\manager_sync_config.json`

---

## ⚡ Szybka instalacja (5 kroków)

### Krok 1: Utwórz katalog konfiguracyjny
```cmd
mkdir C:\RMPAK_CLIENT
```

### Krok 2: Skopiuj pliki RM_MANAGER
Skopiuj do dowolnego katalogu, np. `C:\RM_MANAGER\`:
- `rm_manager.py`
- `rm_manager_gui.py`

### Krok 3: Utwórz plik konfiguracyjny
Utwórz plik: `C:\RMPAK_CLIENT\manager_sync_config.json`

**Zawartość:**
```json
{
    "master_db_path": "Y:/RM_BAZA/master.sqlite",
    "rm_db_path": "rm_manager.sqlite",
    "_comment": "RM_MANAGER configuration file"
}
```

**WAŻNE:** Zmień `Y:/RM_BAZA/master.sqlite` na swoją ścieżkę do master.sqlite (ten sam co w RM_BAZA)!

**WYMAGANIA SCHEMATU:**  
RM_MANAGER wymaga, aby `master.sqlite` miał schemat zgodny z produkcją:
- Tabela `projects` z kolumną `project_id` (PRIMARY KEY) - NIE `id`
- Tabela `projects` z kolumną `active` - NIE `is_active`
- Zobacz: `schema_full_master_SQLITE.txt` dla pełnego schematu

Jeśli masz inny schemat, użyj `test_rm_gui.py` do utworzenia testowej bazy z prawidłowym schematem.

### Krok 4: Uruchom GUI
```cmd
cd C:\RM_MANAGER
python rm_manager_gui.py
```

### Krok 5: Sprawdź w konsoli
Powinieneś zobaczyć:
```
✅ Konfiguracja wczytana z: C:\RMPAK_CLIENT\manager_sync_config.json
   master_db_path: Y:/RM_BAZA/master.sqlite
   rm_db_path: rm_manager.sqlite
✅ Baza zainicjalizowana: rm_manager.sqlite
🟢 Załadowano X projektów z RM_BAZA
```

**Jeśli widzisz błąd "no such column":**  
→ Uruchom `python verify_schema.py` aby zweryfikować schemat  
→ Sprawdź czy master.sqlite używa kolumn `project_id` i `active` (patrz wyżej)

---

## 🔧 Konfiguracja ścieżki przez GUI (łatwiejsze)

Jeśli nie chcesz ręcznie edytować JSON:

1. **Uruchom GUI** (plik JSON zostanie utworzony automatycznie)
2. Pojawi się komunikat: "Nie znaleziono bazy RM_BAZA"
3. Kliknij **TAK** → wybierz plik `master.sqlite`
4. Ścieżka zostanie zapisana w JSON
5. Gotowe!

**Lub:** Menu → Plik → Konfiguracja ścieżek... → wybierz plik

---

## 📂 Przykładowa struktura katalogów

```
C:\
├─ RMPAK_CLIENT\
│  └─ manager_sync_config.json     ← Konfiguracja (TUTAJ!)
│
├─ RM_MANAGER\
│  ├─ rm_manager.py                ← Backend
│  ├─ rm_manager_gui.py            ← GUI
│  └─ rm_manager.sqlite            ← Baza (utworzy się automatycznie)
│
Y:\
└─ RM_BAZA\
   └─ master.sqlite                ← Wspólny master (RM_BAZA + RM_MANAGER)
```

---

## ✅ Weryfikacja instalacji

### Test 1: Sprawdź plik JSON
```cmd
notepad C:\RMPAK_CLIENT\manager_sync_config.json
```
Powinieneś zobaczyć:
```json
{
    "master_db_path": "Y:/RM_BAZA/master.sqlite",
    "rm_db_path": "rm_manager.sqlite",
    "_comment": "..."
}
```

### Test 2: Sprawdź master.sqlite
Otwórz Eksplorator Windows → wklej ścieżkę z JSON (np. `Y:/RM_BAZA/`)  
Czy widzisz plik `master.sqlite`? 
- ✅ TAK → OK
- ❌ NIE → popraw ścieżkę w JSON

### Test 3: Uruchom GUI
```cmd
python rm_manager_gui.py
```
Sprawdź konsolę:
- ✅ "Konfiguracja wczytana" → OK
- ✅ "Załadowano X projektów" → OK
- ❌ "Brak master.sqlite" → popraw ścieżkę
- ❌ "Błąd ładowania" → sprawdź uprawnienia

---

## 🔄 Zmiana ścieżki (dla administratora)

### Gdy zmienia się lokalizacja master.sqlite:

**Opcja 1 - GUI:**
1. Menu → Plik → Konfiguracja ścieżek...
2. Wybierz nowy plik master.sqlite
3. Gotowe!

**Opcja 2 - Edycja JSON:**
1. Otwórz: `C:\RMPAK_CLIENT\manager_sync_config.json`
2. Zmień `master_db_path` na nową ścieżkę
3. Zapisz
4. Uruchom GUI ponownie

**Przykład:** zmiana z Y: na Z:
```json
{
    "master_db_path": "Z:/RM_BAZA_NEW/master.sqlite",
    "rm_db_path": "rm_manager.sqlite"
}
```

---

## 🌐 Instalacja sieciowa (dla zespołu)

### Dla wielu użytkowników:

**Krok 1:** Admin tworzy plik JSON na każdym komputerze:
```cmd
mkdir C:\RMPAK_CLIENT
notepad C:\RMPAK_CLIENT\manager_sync_config.json
```
Zawierający:
```json
{
    "master_db_path": "Y:/RM_BAZA/master.sqlite",
    "rm_db_path": "rm_manager.sqlite"
}
```

**Krok 2:** Skopiuj `rm_manager.py` i `rm_manager_gui.py` na każdy komputer

**Krok 3:** Każdy użytkownik uruchamia GUI:
```cmd
python rm_manager_gui.py
```

**UWAGA:** Wszyscy używają **tego samego master.sqlite** (Y:/RM_BAZA/)  
Każdy ma **własny rm_manager.sqlite** (lokalny)

---

## 🚨 Rozwiązywanie problemów

### Problem: "Nie mam katalogu C:\RMPAK_CLIENT"
**Rozwiązanie:**
```cmd
mkdir C:\RMPAK_CLIENT
```
Lub uruchom Wiersz polecenia jako Administrator

### Problem: "Nie mogę zapisać pliku JSON"
**Przyczyna:** Brak uprawnień do C:\RMPAK_CLIENT\  
**Rozwiązanie:**
1. Uruchom cmd jako Administrator
2. Lub zmień lokalizację (patrz: MANAGER_CONFIG_README.md)

### Problem: "GUI nie widzi projektów"
**Przyczyna:** Nieprawidłowa ścieżka do master.sqlite  
**Rozwiązanie:**
1. Sprawdź w Eksploratorze: czy plik istnieje?
2. Menu → Plik → Konfiguracja ścieżek... → wybierz ponownie
3. Sprawdź konsolę Python - komunikaty błędów

### Problem: "ModuleNotFoundError: No module named 'rm_manager'"
**Przyczyna:** Uruchomiłeś GUI z innego katalogu  
**Rozwiązanie:**
```cmd
cd C:\RM_MANAGER
python rm_manager_gui.py
```
Lub skopiuj `rm_manager.py` do katalogu roboczego

### Problem: "no such column: is_active" lub "no such column: id"
**Przyczyna:** Schemat master.sqlite nie jest zgodny z oczekiwanym  
**Rozwiązanie:**

1. **Sprawdź schemat:** Uruchom `python verify_schema.py`
2. **Popraw master.sqlite:**
   - Tabela `projects` musi mieć kolumnę `project_id` (PRIMARY KEY) - NIE osobne `id`
   - Tabela `projects` musi mieć kolumnę `active` - NIE `is_active`
3. **Testowa baza:** Użyj `python test_rm_gui.py` aby utworzyć bazę z prawidłowym schematem
4. **Migracja:** Jeśli masz dane produkcyjne, uruchom skrypt migracji

**Schemat produkcyjny (wymagany):**
```sql
CREATE TABLE projects (
    project_id INTEGER PRIMARY KEY,      -- NIE 'id'!
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,   -- NIE 'is_active'!
    ...
)
```

Zobacz: `schema_full_master_SQLITE.txt` dla pełnego schematu

---

## 📚 Dodatkowe informacje

- **Pełna dokumentacja:** [RM_MANAGER_GUI_README.md](RM_MANAGER_GUI_README.md)
- **Konfiguracja JSON:** [MANAGER_CONFIG_README.md](MANAGER_CONFIG_README.md)
- **Specyfikacja techniczna:** [PROJECT_STATS_MANAGER_SPEC.md](PROJECT_STATS_MANAGER_SPEC.md)
- **Weryfikacja schematu:** `python verify_schema.py`

---

## ✨ Gotowe!

Po instalacji możesz:
- ✅ Przeglądać projekty z RM_BAZA
- ✅ START/END etapów
- ✅ Monitorować timeline i forecast
- ✅ Analizować critical path
- ✅ Auto-sync z master.sqlite

**Pierwsze uruchomienie:** wybierz projekt → zostanie automatycznie zainicjalizowany  
**Kolejne użycie:** wszystko załadowane, gotowe do pracy!
