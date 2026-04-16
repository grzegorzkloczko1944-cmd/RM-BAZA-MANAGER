# RM_MANAGER - Konfiguracja

## 📋 Plik konfiguracyjny: `manager_sync_config.json`

### Lokalizacja (na sztywno):
```
C:\RMPAK_CLIENT\manager_sync_config.json
```

### Struktura pliku:

```json
{
    "master_db_path": "Y:/RM_BAZA/master.sqlite",
    "rm_db_path": "rm_manager.sqlite",
    "_comment": "RM_MANAGER configuration file - edit paths as needed"
}
```

---

## ⚙️ Parametry

### `master_db_path`
**Ścieżka do wspólnego master.sqlite (RM_BAZA)**

- **Środowisko produkcyjne:** `"Y:/RM_BAZA/master.sqlite"`
- **Środowisko testowe:** `"C:/test/master.sqlite"`
- **WAŻNE:** Musi wskazywać na ten sam plik co RM_BAZA GUI!

### `rm_db_path`
**Ścieżka do rm_manager.sqlite (zarządzanie procesem)**

- **Domyślnie:** `"rm_manager.sqlite"` (katalog roboczy)
- **Centralna lokalizacja:** `"C:/RM_MANAGER/rm_manager.sqlite"`
- **Sieciowa:** `"Y:/RM_MANAGER/rm_manager.sqlite"`

---

## 🔧 Jak zmienić konfigurację?

### Opcja 1 - Przez GUI (zalecana):
1. Uruchom `rm_manager_gui.py`
2. Menu → **Plik** → **Konfiguracja ścieżek...**
3. Wybierz plik `master.sqlite`
4. Gotowe! Ścieżka zapisana w JSON

### Opcja 2 - Ręczna edycja:
1. Otwórz w Notatniku: `C:\RMPAK_CLIENT\manager_sync_config.json`
2. Zmień wartość `master_db_path`
3. Zapisz plik (Ctrl+S)
4. Uruchom GUI ponownie

---

## 📚 Przykłady konfiguracji

### Środowisko produkcyjne (sieć LAN):
```json
{
    "master_db_path": "Y:/RM_BAZA/master.sqlite",
    "rm_db_path": "rm_manager.sqlite"
}
```
- Master na serwerze (Y:)
- RM_MANAGER lokalnie (katalog roboczy)

### Środowisko testowe (lokalne):
```json
{
    "master_db_path": "C:/test_data/master.sqlite",
    "rm_db_path": "C:/test_data/rm_manager.sqlite"
}
```
- Wszystko lokalnie w `C:/test_data/`

### Środowisko developerskie:
```json
{
    "master_db_path": "./master.sqlite",
    "rm_db_path": "./rm_manager.sqlite"
}
```
- Ścieżki relatywne (katalog roboczy)

---

## ❓ FAQ

### Pytanie: Co się stanie jeśli plik nie istnieje?
**Odpowiedź:** GUI utworzy go automatycznie przy pierwszym uruchomieniu z domyślnymi wartościami:
- `master_db_path`: `"master.sqlite"`
- `rm_db_path`: `"rm_manager.sqlite"`

### Pytanie: Czy mogę zmienić lokalizację pliku JSON?
**Odpowiedź:** Tak, ale wymaga edycji kodu. W pliku `rm_manager_gui.py`, linia ~30:
```python
CONFIG_FILE_PATH = r"C:\RMPAK_CLIENT\manager_sync_config.json"
```
Zmień na swoją ścieżkę, np.:
```python
CONFIG_FILE_PATH = r"D:\Moje_Dokumenty\rm_config.json"
```

### Pytanie: Co jeśli nie mam uprawnień do `C:\RMPAK_CLIENT`?
**Odpowiedź:** 
1. **Opcja A:** Uruchom terminal jako Administrator i utwórz katalog:
   ```cmd
   mkdir C:\RMPAK_CLIENT
   ```
2. **Opcja B:** Zmień ścieżkę w kodzie (patrz pytanie powyżej)

### Pytanie: Jak sprawdzić czy ścieżka jest prawidłowa?
**Odpowiedź:** 
1. Otwórz Eksplorator Windows
2. Wklej ścieżkę z JSON do paska adresu (np. `Y:/RM_BAZA/`)
3. Jeśli widzisz plik `master.sqlite` - ścieżka OK ✅

### Pytanie: Czy każdy użytkownik musi mieć swój plik JSON?
**Odpowiedź:** 
- **Zazwyczaj NIE** - wszyscy używają tej samej konfiguracji:
  - `C:\RMPAK_CLIENT\manager_sync_config.json` → `Y:/RM_BAZA/master.sqlite`
- **Wyjątek:** Testerzy mogą mieć własne pliki z innymi ścieżkami

---

## 🚨 Rozwiązywanie problemów

### Problem: "Nie znaleziono bazy RM_BAZA"
**Przyczyna:** `master_db_path` wskazuje na nieistniejący plik

**Rozwiązanie:**
1. Sprawdź czy plik istnieje: otwórz Eksplorator → wklej ścieżkę
2. Jeśli NIE - popraw ścieżkę w JSON lub użyj GUI:
   - Menu → Plik → Konfiguracja ścieżek...
3. Jeśli TAK - sprawdź uprawnienia do pliku

### Problem: Plik JSON nie ładuje się
**Przyczyna:** Błąd składni JSON (brak przecinka, cudzysłowu, nawiasu)

**Rozwiązanie:**
1. Otwórz plik w edytorze tekstowym
2. Sprawdź czy struktura jest prawidłowa (patrz przykład na górze)
3. Usuń plik - GUI utworzy nowy przy starcie
4. Lub skopiuj przykład z dokumentacji

### Problem: GUI pokazuje domyślną ścieżkę zamiast z JSON
**Przyczyna:** Plik JSON nie znajduje się w `C:\RMPAK_CLIENT\`

**Rozwiązanie:**
1. Sprawdź czy katalog `C:\RMPAK_CLIENT\` istnieje
2. Sprawdź czy plik nazywa się DOKŁADNIE `manager_sync_config.json`
3. Konsola Python pokaże komunikaty: "✅ Konfiguracja wczytana z: ..."

---

## 📝 Notatki

1. **Używaj slash (/) zamiast backslash (\\)** w ścieżkach Windows:
   - ✅ DOBRE: `"Y:/RM_BAZA/master.sqlite"`
   - ❌ ZŁE: `"Y:\\RM_BAZA\\master.sqlite"` (wymaga podwójnych backslash)

2. **Ścieżki relatywne:** działają względem katalogu roboczego (gdzie uruchomiono skrypt)

3. **Sieciowe dyski:** sprawdź literę dysku (Y:, Z:, etc.) w Eksploratorze Windows

4. **Plik zostanie utworzony automatycznie** jeśli nie istnieje - nie musisz go tworzyć ręcznie!

---

## 📞 Wsparcie

W razie problemów sprawdź konsolę Python - zawiera szczegółowe komunikaty:
```
✅ Konfiguracja wczytana z: C:\RMPAK_CLIENT\manager_sync_config.json
   master_db_path: Y:/RM_BAZA/master.sqlite
   rm_db_path: rm_manager.sqlite
```

Lub:
```
⚠️ Brak pliku konfiguracyjnego: C:\RMPAK_CLIENT\manager_sync_config.json
   Użyto domyślnych ścieżek
✅ Konfiguracja zapisana: C:\RMPAK_CLIENT\manager_sync_config.json
```
