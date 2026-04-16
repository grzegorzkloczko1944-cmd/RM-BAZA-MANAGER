# File Integrity Tracking - System śledzenia integralności plików

## 📋 PRZEGLĄD

System śledzenia integralności plików zapewnia ochronę przed sytuacją, gdy RM_BAZA usuwa projekt, a RM_MANAGER zachowuje "osierocone" dane bez odpowiadającego im pliku projektu.

## 🎯 PROBLEM

**Scenariusz:**
1. Projekt 123 istnieje w `Y:/RM_BAZA/projekt_123/data.sqlite`
2. RM_MANAGER śledzi etapy projektu 123 w `Y:/RM_MANAGER/rm_manager.sqlite`
3. Użytkownik usuwa projekt 123 w RM_BAZA (skasowanie folderu `projekt_123/`)
4. **ZAGROŻENIE:** RM_MANAGER nadal pokazuje dane projektu 123, ale nie można ich zsynchronizować

## ✅ ROZWIĄZANIE

### Inteligentne fingerprinting plików (v2 - 2026-04-14)
System używa **weryfikacji przez zawartość**, nie tylko metadata:

**Poziom 1: Birth time** (szybkie sprawdzenie)
- **Ścieżka pliku**: `{master_db_dir}/projekt_{id}/data.sqlite`
- **Czas utworzenia (birth_time)**: Timestamp utworzenia pliku
- **Tolerancja**: ±1 sekunda

**Poziom 2: Zawartość bazy** (przy rozbieżności)
- Sprawdza `project_id` w tabeli `projects` wewnątrz SQLite
- **Jeśli project_id zgadza się** → plik OK, auto-update birth_time
  - ✅ Rozwiązuje problem backup/synchronizacji (nowy birth_time, ta sama baza)
- **Jeśli project_id różny** → prawdziwe ostrzeżenie
  - ❌ Plik został podmieniony na inny projekt!

### Weryfikacja przy każdym dostępie
Gdy użytkownik wybiera projekt w GUI:
1. Sprawdź czy plik istnieje
2. Sprawdź czy `birth_time` się zgadza (±1s)
3. **NOWE**: Jeśli birth_time różny → sprawdź `project_id` w bazie
   - Ten sam project_id → **silent update**, praca kontynuowana
   - Inny project_id → **READ-ONLY mode**

### Tryb READ-ONLY
Gdy plik nieprawidłowy:
- ✅ Można przeglądać dane RM_MANAGER (zachowane w bazie)
- ❌ Blokada przycisków START/END
- 🚨 Czerwony banner ostrzegawczy na górze okna
- 💾 **Dane RM_MANAGER są bezpieczne** - nie zostają usunięte

### Przywrócenie
Gdy użytkownik przywróci plik projektu:
1. Menu: **Narzędzia → Resetuj śledzenie pliku projektu**
2. System rejestruje nowy plik
3. Tryb READ-ONLY zostaje wyłączony
4. Normalna praca wznowiona

---

## 🗄️ ARCHITEKTURA

### 1. Tabela `project_file_tracking`

```sql
CREATE TABLE project_file_tracking (
    project_id INTEGER PRIMARY KEY,
    project_name TEXT,
    file_path TEXT NOT NULL,                  -- Ścieżka do data.sqlite
    file_birth_time REAL NOT NULL,            -- Timestamp utworzenia
    last_verified_at DATETIME,                -- Ostatnia weryfikacja
    verification_status TEXT DEFAULT 'OK',    -- OK | MISSING | CONTENT_MISMATCH
    CHECK (verification_status IN ('OK', 'MISSING', 'CONTENT_MISMATCH'))
);
```

### 2. Funkcje backendowe (`rm_manager.py`)

#### `get_file_birth_time(filepath: str) -> float`
Pobiera czas utworzenia pliku.
- **Windows**: `st_ctime` (creation time)
- **Linux/macOS**: `st_birthtime` lub `st_mtime` jako fallback

#### `verify_project_file_content(file_path: str, expected_project_id: int) -> bool`
**NOWA FUNKCJA (v2)** - Weryfikuje zawartość bazy SQLite.
```python
# Otwiera bazę w trybie read-only
# Sprawdza: SELECT project_id FROM projects LIMIT 1
# Porównuje z expected_project_id
# Returns: True jeśli ten sam projekt, False jeśli podmieniony
```

#### `register_project_file(rm_db_path, project_id, project_name, master_db_path)`
**LAZY INIT** - Rejestruje plik przy pierwszym dostępie.
```python
# Struktura ścieżki (POPRAWNA od v2.1 - 2026-04-14)
base_dir = projects_path or os.path.dirname(master_db_path)  # Y:/RM_BAZA
file_path = os.path.join(base_dir, f"projekt_{project_id}", "data.sqlite")  
# Y:/RM_BAZA/projekt_123/data.sqlite ← POPRAWNIE!
```

#### `migrate_file_tracking_paths(rm_db_path, projects_base_path)`
**AUTO-MIGRACJA (v2.1)** - Naprawia stare ścieżki w bazie.
```python
# Uruchamiana automatycznie przy starcie GUI
# Konwertuje: project_123.sqlite → projekt_123/data.sqlite
# Aktualizuje birth_time dla nowych ścieżek
```

#### `verify_project_file(rm_db_path, project_id) -> (bool, str, str)`
Weryfikuje integralność pliku (v2 - inteligentna weryfikacja).

**Algorytm:**
1. Sprawdź istnienie pliku → `MISSING` jeśli brak
2. Sprawdź birth_time (±1s)
   - **OK** → zwróć `(True, 'OK', ...)`
   - **Różny** → przejdź do kroku 3
3. **Weryfikuj zawartość** (`verify_project_file_content`)
   - **project_id OK** → auto-update birth_time, zwróć `(True, 'OK', ...)`
   - **project_id błędny** → zwróć `(False, 'CONTENT_MISMATCH', ...)`

**Zwraca:**
- `(True, 'OK', message)` - Plik prawidłowy (lub zaktualizowany po sync)
- `(False, 'MISSING', message)` - Plik nie istnieje
- `(False, 'CONTENT_MISMATCH', message)` - Plik podmieniony (inny project_id)
- `(False, 'BIRTH_MISMATCH', message)` - Plik został zmieniony (inny czas utworzenia)
- `(False, 'NOT_REGISTERED', message)` - Projekt nie jest jeszcze zarejestrowany

**Mechanizm:**
```python
current_birth = get_file_birth_time(file_path)

if current_birth == 0.0:
    return (False, 'MISSING', 'Plik nie istnieje')

if abs(current_birth - registered_birth) > 1.0:  # Tolerancja ±1s
    return (False, 'BIRTH_MISMATCH', 'Plik zmieniony')

return (True, 'OK', 'Plik prawidłowy')
```

#### `reset_project_tracking(rm_db_path, project_id, master_db_path)`
Resetuje śledzenie - usuwa stary wpis i rejestruje plik na nowo.

### 3. Integracja GUI (`rm_manager_gui.py`)

#### Zmienne stanu
```python
self.read_only_mode = False              # Tryb tylko do odczytu
self.file_verification_message = ""      # Komunikat o błędzie
```

#### Warning banner
```python
# Czerwona ramka ostrzegawcza (ukryta domyślnie)
self.warning_frame = tk.Frame(self.root, bg="#e74c3c")
self.warning_label = tk.Label(
    self.warning_frame,
    text="⚠️ PLIK PROJEKTU NIE ISTNIEJE - Tryb tylko do odczytu",
    bg="#e74c3c", fg="white", font=("Arial", 11, "bold")
)
```

#### Workflow wyboru projektu
```python
def on_project_selected(self, event):
    self.selected_project_id = self.projects[idx]
    
    # Lazy init projektu w RM_MANAGER
    self.ensure_project_initialized()
    
    # WERYFIKACJA PLIKU
    self.verify_project_file_integrity()  # ← KLUCZOWE
    
    # Załaduj dane
    self.load_project_stages()
    self.refresh_timeline()
```

#### Metoda weryfikacyjna
```python
def verify_project_file_integrity(self):
    # Sprawdź czy projekt zarejestrowany
    con = sqlite3.connect(self.rm_db_path)
    cursor = con.execute(
        "SELECT COUNT(*) FROM project_file_tracking WHERE project_id = ?",
        (self.selected_project_id,)
    )
    count = cursor.fetchone()[0]
    
    if count == 0:
        # Pierwszy dostęp - zarejestruj plik (LAZY INIT)
        rmm.register_project_file(
            self.rm_db_path, 
            self.selected_project_id, 
            project_name, 
            self.master_db_path
        )
    
    # Weryfikuj
    is_valid, status, message = rmm.verify_project_file(
        self.rm_db_path, 
        self.selected_project_id
    )
    
    if is_valid:
        self.read_only_mode = False
        self.hide_file_warning()
    else:
        self.read_only_mode = True
        self.show_file_warning(status, message)
```

#### Blokada edycji
```python
def start_stage(self, stage_code):
    if not self.selected_project_id:
        return
    
    # Sprawdź tryb READ-ONLY
    if self.read_only_mode:
        messagebox.showerror(
            "🔒 Tryb tylko do odczytu",
            f"Nie można rozpocząć etapu - plik projektu nieprawidłowy.\n\n"
            f"{self.file_verification_message}\n\n"
            f"Przywróć plik projektu i użyj 'Resetuj śledzenie'."
        )
        return
    
    # Kontynuuj normalnie...
```

---

## 🔄 SCENARIUSZE UŻYCIA

### ✅ Scenariusz 1: Normalny dostęp
1. Użytkownik wybiera projekt 123
2. Pierwszy dostęp → `register_project_file()` (lazy init)
3. Plik istnieje → `verification_status = 'OK'`
4. Tryb normalny - wszystkie funkcje działają

### ⚠️ Scenariusz 2: Usunięty plik
1. Admin usuwa `projekt_123/` w RM_BAZA
2. Użytkownik wybiera projekt 123 w RM_MANAGER
3. Weryfikacja: `current_birth = 0.0` (plik nie istnieje)
4. **Tryb READ-ONLY włączony**
   - Banner: "⚠️ PLIK PROJEKTU NIE ISTNIEJE - Tryb tylko do odczytu"
   - Przyciski START/END zablokowane
   - Dane RM_MANAGER nadal widoczne (timeline, podsumowanie, historia)

### 🔄 Scenariusz 3: Przywrócenie pliku
1. Admin przywraca backup `projekt_123/data.sqlite`
2. Użytkownik: **Narzędzia → Resetuj śledzenie pliku projektu**
3. System:
   - Usuwa stary wpis z `project_file_tracking`
   - Rejestruje nowy plik (nowy `file_birth_time`)
   - Weryfikacja → status 'OK'
4. **Tryb normalny przywrócony**

### 🔀 Scenariusz 4: Podmiana pliku
1. Admin zastępuje `data.sqlite` nowym plikiem (np. z innej bazy)
2. Użytkownik wybiera projekt
3. Weryfikacja: `abs(current_birth - registered_birth) > 1.0`
4. **Tryb READ-ONLY włączony**
   - Banner: "⚠️ PLIK PROJEKTU ZMIENIONY - Tryb tylko do odczytu"
   - Komunikat: "Zarejestrowany: 1735689234.5, Obecny: 1735812456.2"

---

## 🛠️ INSTRUKCJA DLA UŻYTKOWNIKA

### Gdy widzisz czerwony banner
**"⚠️ PLIK PROJEKTU NIE ISTNIEJE - Tryb tylko do odczytu"**

**Możliwe przyczyny:**
1. Projekt został usunięty w RM_BAZA
2. Zmieniono nazwę folderu projektu
3. Przeniesiono bazę master.sqlite bez przenoszenia folderów projektów

**Co możesz zrobić:**
1. ✅ Przeglądać dane w RM_MANAGER (są bezpieczne)
2. ❌ Nie możesz rozpocząć/zakończyć etapów

**Rozwiązanie:**
1. Skontaktuj się z administratorem - sprawdź czy plik projektu istnieje
2. Jeśli plik został przywrócony:
   - Menu: **Narzędzia → 🔄 Resetuj śledzenie pliku projektu**
   - Potwierdź resetowanie
   - System zarejestruje plik na nowo

### Menu "Resetuj śledzenie pliku projektu"
**Kiedy użyć:**
- Po przywróceniu usuniętego pliku
- Po naprawie struktury katalogów
- Po migracji bazy z backupu

**Ostrzeżenie:**
Używaj tylko gdy **na pewno** plik projektu istnieje w lokalizacji:
```
{master_db_dir}/projekt_{id}/data.sqlite
```

---

## 🔧 KONFIGURACJA TECHNICZNA

### Lokalizacja baz
Domyślnie (można zmienić w menu Plik → Konfiguracja ścieżek):
```json
{
    "master_db_path": "Y:/RM_BAZA/master.sqlite",
    "rm_db_path": "Y:/RM_MANAGER/rm_manager.sqlite"
}
```

### Struktura katalogów
```
Y:/RM_BAZA/
├─ master.sqlite              ← Wspólny master
├─ projekt_123/
│   └─ data.sqlite            ← Śledzone przez RM_MANAGER
├─ projekt_124/
│   └─ data.sqlite

Y:/RM_MANAGER/
└─ rm_manager.sqlite          ← Tabela project_file_tracking tutaj
```

### Tolerancja czasu utworzenia
```python
if abs(current_birth - registered_birth) > 1.0:  # ±1 sekunda
    return (False, 'BIRTH_MISMATCH', ...)
```

**Dlaczego ±1s?**
- System plików może zaokrąglać timestampy
- Różnice między FAT32/NTFS/ext4
- Kopiowanie plików zachowuje mtime ale nie zawsze ctime

---

## 📊 MONITORING

### Status weryfikacji w bazie
```sql
-- Sprawdź status wszystkich projektów
SELECT 
    project_id, 
    project_name, 
    verification_status,
    datetime(last_verified_at) AS last_check
FROM project_file_tracking
WHERE verification_status != 'OK';
```

### Historia weryfikacji
- `last_verified_at` aktualizowane przy każdym wywołaniu `verify_project_file()`
- Można dodać tabelę audit log jeśli potrzeba szczegółowej historii

### Statystyki
```sql
-- Ile projektów w każdym statusie
SELECT 
    verification_status, 
    COUNT(*) as count
FROM project_file_tracking
GROUP BY verification_status;
```

---

## 🚀 WDROŻENIE

### 1. Aktualizacja bazy
Po uruchomieniu aplikacji automatycznie:
```python
rmm.ensure_rm_manager_tables(rm_db_path)
```
→ Tworzy tabelę `project_file_tracking` jeśli nie istnieje

### 2. Migracja istniejących projektów
**Automatyczna (lazy init):**
- Przy pierwszym wyborze projektu → `register_project_file()`
- Żadnej ręcznej migracji nie trzeba!

**Ręczna (opcjonalnie):**
```python
# Zarejestruj wszystkie projekty z góry
for project_id in all_projects:
    rmm.register_project_file(rm_db_path, project_id, name, master_db_path)
```

### 3. Brak wpływu na istniejące dane
- Tabela niezależna od `project_stages`, `stage_actual_periods` itp.
- Dane RM_MANAGER **NIE SĄ USUWANE** gdy plik zniknie
- Tylko tryb READ-ONLY zostaje włączony

---

## 🧪 TESTY

### Test 1: Normalny dostęp
```bash
1. Uruchom RM_MANAGER GUI
2. Wybierz projekt (np. 123)
3. Sprawdź brak banneru ostrzegawczego
4. Przyciski START/END działają
✅ PASS gdy tryb normalny
```

### Test 2: Usunięcie pliku
```bash
1. Wybierz projekt 123 (załaduj normalnie)
2. Zamknij GUI
3. Usuń folder Y:/RM_BAZA/projekt_123/
4. Uruchom GUI, wybierz projekt 123
5. Sprawdź czerwony banner: "PLIK PROJEKTU NIE ISTNIEJE"
6. Spróbuj kliknąć START → komunikat błędu
✅ PASS gdy READ-ONLY włączony
```

### Test 3: Przywrócenie
```bash
1. Kontynuuj Test 2
2. Przywróć folder projekt_123/ z backupu
3. Menu: Narzędzia → Resetuj śledzenie pliku projektu
4. Potwierdź
5. Banner znika, przyciski START/END działają
✅ PASS gdy tryb normalny przywrócony
```

### Test 4: Podmiana pliku
```bash
1. Załaduj projekt 123
2. Zamknij GUI
3. Zastąp data.sqlite nowym plikiem (touch, cp, itp.)
4. Uruchom GUI, wybierz projekt 123
5. Sprawdź banner: "PLIK PROJEKTU ZMIENIONY"
✅ PASS gdy READ-ONLY włączony
```

---

## ❓ FAQ

### Q: Co się stanie z danymi RM_MANAGER gdy plik zniknie?
**A:** Dane **NIE SĄ USUWANE**. Tryb READ-ONLY tylko blokuje edycję. Możesz przeglądać timeline, podsumowanie, historię.

### Q: Czy mogę wyłączyć śledzenie?
**A:** Nie. To mechanizm bezpieczeństwa - wyłączenie powodowałoby ryzyko desynchronizacji.

### Q: Co gdy przywrócę plik z backupu sprzed tygodnia?
**A:** System wykryje zmianę `birth_time` → tryb READ-ONLY. Użyj "Resetuj śledzenie" aby zaakceptować stary plik.

### Q: Czy to działa na Linux/macOS?
**A:** Tak. Funkcja `get_file_birth_time()` obsługuje Windows (`st_ctime`), macOS (`st_birthtime`), Linux (`st_mtime` jako fallback).

### Q: Skąd aplikacja wie gdzie jest plik projektu?
**A:** Z master_db_path: `{dirname(master_db_path)}/projekt_{id}/data.sqlite`

---

## 📝 CHANGELOG

### v2.1 (2026-04-14) - FIX: Błędne ścieżki + auto-migracja
**Problem odkryty:** Błędna konstrukówka ścieżki pliku → 100% fałszywych alarmów
- BŁĄD: `Y:/RM_BAZA/project_123.sqlite`
- POPRAWNIE: `Y:/RM_BAZA/projekt_123/data.sqlite`

**Zmiany:**
- ✅ Naprawiono `register_project_file()` - poprawna ścieżka z folderem `projekt_X/data.sqlite`
- ✅ Dodano `migrate_file_tracking_paths()` - automatyczna migracja starych wpisów
- ✅ GUI wywołuje migrację w `init_database()` przy starcie

**Rezultat:**
- Banner ostrzegawczy **NIE POJAWIA SIĘ** po synchronizacji/backup (inteligentna weryfikacja działa)
- Migracja automatycznie naprawia stare błędne wpisy
- Logi: `✅ Zaktualizowano X ścieżek plików projektu`

### v2.0 (2026-04-14) - Inteligentna weryfikacja przez zawartość
**Problem:** Backup/synchronizacja zmienia `birth_time` → fałszywe alarmyy

**Zmiany:**
- ✅ Dodano `verify_project_file_content()` - sprawdza `project_id` w tabeli `projects`
- ✅ Auto-update `birth_time` gdy zawartość OK (ten sam project_id)
- ✅ READ-ONLY tylko przy prawdziwej podmianie (inny project_id)
- ✅ Nowy status: `CONTENT_MISMATCH`

### v1.0 (2025-01-02) - Podstawowe śledzenie
- ✅ Tabela `project_file_tracking` (project_id, file_path, file_birth_time)
- ✅ Weryfikacja `birth_time` (±1s tolerancja)
- ✅ Tryb READ-ONLY przy błędach (`MISSING`, `BIRTH_MISMATCH`)
- ✅ Menu "Resetuj śledzenie pliku projektu"

---

## 🔧 TROUBLESHOOTING

### Problem: "Banner pojawia się i znika cyklicznie"
**Przyczyna:** Błędna ścieżka w bazie (stary format `project_X.sqlite`)

**Rozwiązanie (automatyczne - v2.1):**
1. Uruchom ponownie RM_MANAGER GUI
2. Sprawdź logi:
   ```
   🔄 Sprawdzam ścieżki w file tracking...
   ✅ Zaktualizowano X ścieżek plików projektu
   ```
3. ✅ Problem rozwiązany automatycznie!

**Rozwiązanie (manualne):**
Jeśli auto-migracja nie zadziałała:
1. Menu > Narzędzia > Resetuj śledzenie pliku projektu
2. Potwierdź w oknie dialogowym
3. ✅ Plik zarejestrowany z poprawną ścieżką

### Problem: "Weryfikacja zawartości nie widać w logach"
**Objawy:** Brak logów typu:
```
🔍 Birth time różny (Δ=X.Xs) - weryfikuję zawartość...
✅ Zawartość prawidłowa - aktualizuję birth_time
```

**Przyczyny:**
1. **Birth_time w tolerancji (±1s)** → weryfikacja zawartości nie jest potrzebna
2. **Projekt nie zarejestrowany** → sprawdź czy jest w `project_file_tracking`

**Diagnostyka:**
```sql
-- Sprawdź rejestrację projektu
SELECT * FROM project_file_tracking WHERE project_id = 123;

-- Sprawdź status
SELECT verification_status, last_verified_at 
FROM project_file_tracking 
WHERE project_id = 123;
```

### Problem: "READ-ONLY mimo że plik istnieje"
**Przyczyny:**
1. **Błędna ścieżka w bazie** → użyj auto-migracji (v2.1) lub resetuj tracking
2. **Plik podmieniony** (inny `project_id` w bazie)
3. **Uprawnienia pliku** → sprawdź czy aplikacja może otworzyć bazę SQLite

**Rozwiązanie:**
1. Sprawdź komunikat w bannerze (MISSING vs CONTENT_MISMATCH)
2. Jeśli MISSING → sprawdź ścieżkę: `{master_db_dir}/projekt_{id}/data.sqlite`
3. Jeśli CONTENT_MISMATCH → prawdopodobnie podmieniony plik, sprawdź backup
4. Menu > Resetuj śledzenie (jeśli plik prawidłowy)

### Q: Co jeśli zmienię ścieżkę master_db_path w konfiguracji?
**A:** Stare ścieżki w `project_file_tracking` będą nieprawidłowe. Użyj "Resetuj śledzenie" dla każdego projektu aby zaktualizować.

---

## 📝 CHANGELOG

### v1.0 (2025-01-02)
- ✅ Tabela `project_file_tracking`
- ✅ Funkcje: `get_file_birth_time()`, `register_project_file()`, `verify_project_file()`, `reset_project_tracking()`
- ✅ GUI: Warning banner, READ-ONLY mode, menu "Resetuj śledzenie"
- ✅ Lazy init rejestracji przy pierwszym dostępie
- ✅ Weryfikacja przy każdym wyborze projektu
- ✅ Blokada START/END w trybie READ-ONLY

---

## 🎓 PODSUMOWANIE

**File Integrity Tracking** to eleganckie rozwiązanie problemu osieroconych danych:
- 🟢 **Lazy init** - brak ręcznej migracji
- 🟢 **Non-invasive** - nie usuwa żadnych danych
- 🟢 **User-friendly** - jasny komunikat + przycisk resetowania
- 🟢 **Cross-platform** - Windows/Linux/macOS
- 🟢 **Automatic** - działa w tle bez uwagi użytkownika

**Kluczowa filozofia:**
> Lepiej zachować dane i zablokować edycję, niż pozwolić na desynchronizację.

