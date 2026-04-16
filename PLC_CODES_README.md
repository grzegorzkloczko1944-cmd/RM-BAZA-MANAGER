# System kodów odblokowujących PLC - Dokumentacja (v2 - 2026-04-15)

## Przegląd

System zarządzania kodami odblokowującymi PLC zintegrowany z RM_MANAGER. Umożliwia programistom wprowadzanie kodów po zakończeniu programowania, a następnie kontrolowane przekazywanie ich klientowi **przez email lub SMS**.

## Lokalizacja

Zakładka **"💳 Płatności"** → Sekcja **"Kody odblokowujące PLC"** (dolna część)

## Typy kodów

System obsługuje 3 typy kodów:

| Typ | Opis | Zastosowanie | Ważność |
|-----|------|-------------|---------|
| **TEMPORARY** | Tymczasowy | Testowe odblokowanie na czas rozruchu | **14 dni od utworzenia** |
| **EXTENDED** | Rozszerzony | Przedłużona licencja czasowa | Określona indywidualnie |
| **PERMANENT** | Stały | Pełna licencja bez ograniczeń czasowych | Bez limitu |

### ⏱️ Data ważności kodów TEMPORARY

- **Kolumna "Ważny do"** w treeview pokazuje datę wygaśnięcia
- **Obliczana automatycznie:** data utworzenia (created_at) + 14 dni
- **Zapisywana w bazie** przy dodawaniu kodu
- Wyświetlana tylko dla kodów TEMPORARY
- Dla innych typów: `---`
- **Przykład:** Kod utworzony 2026-04-15 → Ważny do: 2026-04-29

## Workflow

### 1. Programista wprowadza kody (po zakończeniu programowania)

```
Etap: PROGRAMOWANIE zakończony
    ↓
Programista → Zakładka "💳 Płatności" → Sekcja "Kody PLC"
    ↓
Kliknij "➕ Dodaj kod"
    ↓
Wybór typu: TEMPORARY / EXTENDED / PERMANENT
Wprowadź kod: np. "ABC-12345-XYZ-789"
Opis (opcjonalnie): "Kod testowy na 30 dni"
    ↓
✅ Zapisz
```

**Kody są przechowywane** w `rm_manager.sqlite` (tabela `plc_unlock_codes`) i **czekają na przekazanie klientowi**.

### 2. Księgowość wprowadza 100% płatność

```
Zakładka "💳 Płatności" → Sekcja "Transze płatności"
    ↓
Kliknij "➕ Dodaj transzę"
    ↓
Procent: 100%
Data płatności: [wybierz datę]
    ↓
✅ Zapisz
    ↓
🔔 Automatyczne powiadomienia email + in-app
```

### 3. Przekazanie kodów klientowi (NOWE! 📤)

#### Metoda A: Ręczne oznaczenie jako użyty

```
Zakładka "💳 Płatności" → Sekcja "Kody PLC"
    ↓
Wybierz kod do przekazania
    ↓
Kliknij "✅ Oznacz jako użyty"
    ↓
Wprowadź notatkę (opcjonalnie): "Przesłano klientowi email 2026-04-14"
    ↓
✅ Oznacz
```

#### Metoda B: **Automatyczne wysłanie (EMAIL/SMS)** 🚀

```
Zakładka "💳 Płatności" → Sekcja "Kody PLC"
    ↓
Wybierz kod do przekazania
    ↓
Kliknij "📤 UŻYJ (wyślij)"
    ↓
System sprawdzi:
  ✓ Czy masz uprawnienia do wysyłki (lista ADMIN)
  ⚠️  Jeśli PERMANENT i płatność < 100% → PODWÓJNE POTWIERDZENIE
    ↓
Wybierz metodę: 📧 Email / 📱 SMS / 📧+📱 Oba
Wprowadź dane odbiorcy (email/telefon)
    ↓
✅ Wyślij → Kod wysłany automatycznie!
```

## 🔐 Uprawnienia do wysyłki kodów

**Tylko wybrani użytkownicy mogą wysyłać kody przez system.**

### Zarządzanie uprawnieniami (ADMIN)

```
Menu: Narzędzia → 🔐 Zarządzaj uprawnieniami wysyłki kodów PLC
    ↓
Dialog z listą uprawnionych użytkowników:
  - ➕ Dodaj użytkownika
  - 🗑️ Usuń użytkownika
  - 🔄 Odśwież listę
```

**Kto może zarządzać uprawnieniami?**
- Każdy użytkownik może DODAWAĆ innych do listy
- Tylko użytkownik na liście może WYSYŁAĆ kody

### Co się dzieje gdy użytkownik NIE MA uprawnień?

```
Kliknij "📤 UŻYJ (wyślij)"
    ↓
❌ BŁĄD: "Użytkownik 'Jan' nie ma uprawnień do wysyłki kodów PLC.
           Skontaktuj się z administratorem w celu uzyskania dostępu."
```

## ⚠️ Specjalne zasady dla kodów PERMANENT

**Jeśli płatność < 100%, system wymaga PODWÓJNEGO POTWIERDZENIA:**

```
OSTRZEŻENIE 1:
"UWAGA! Wysyłasz kod PERMANENT, a płatność wynosi tylko 50%!
 Czy na pewno chcesz kontynuować?"
    ↓ TAK
OSTRZEŻENIE 2:
"POTWIERDZENIE PONOWNE:
 Kod: ABC-12345
 Typ: PERMANENT
 Płatność: 50%
 
 CZY NA PEWNO WYSŁAĆ?"
    ↓ TAK
✅ Kod wysłany
```

**Dla kodów TEMPORARY i EXTENDED:** pojedyncze potwierdzenie (standardowe)

## 📧 Wysyłka przez Email

**Wymagania:**
- Konfiguracja SMTP w: `Narzędzia → 📧 Konfiguracja powiadomień płatności`
- Adres email odbiorcy (można podać wiele, oddzielonych przecinkami)

**Treść emaila:**
```
Temat: Kod odblokowujący PLC - Projekt ABC

Kod odblokowujący PLC dla projektu: Projekt ABC

Typ kodu: Tymczasowy (2 tygodnie)
Kod: ABC-12345-XYZ
Opis: Kod testowy

Data wysłania: 2026-04-15 10:30:00
Wysłał: Jan Kowalski

---
Wiadomość wygenerowana automatycznie przez RM_MANAGER
```

## 📱 Wysyłka przez SMS

**Wymagania:**
- Konfiguracja SMSAPI w: `Narzędzia → 📱 Konfiguracja SMS`
- Token OAuth z SMSAPI.pl
- Numer telefonu w formacie: `48123456789` lub `123456789`

**Treść SMS:**
```
Kod PLC (TEMP): ABC-12345-XYZ | Projekt: ABC
```

## 📦 Instalacja/Migracja (jednorazowo)

Przed pierwszym użyciem nowych funkcji (wysyłka email/SMS), wykonaj migrację bazy danych.

### Metoda A: Z GUI (REKOMENDOWANA) ✨

1. Otwórz **RM_MANAGER**
2. Menu → **Narzędzia** → **🔧 Migruj bazę kodów PLC (dodaj kolumny)**
3. Przeczytaj opis operacji
4. Kliknij **TAK** aby potwierdzić
5. Poczekaj na komunikat **"✅ Migracja zakończona!"**

**Co robi migracja:**
- ✅ Dodaje 4 nowe kolumny do `plc_unlock_codes`
- ✅ Tworzy tabelę `plc_authorized_senders`
- ✅ Bezpieczna (sprawdza czy już istnieją)
- ✅ Można powtórzyć bez straty danych

### Metoda B: Z konsoli (alternatywna)

```bash
python migrate_plc_codes_columns.py Y:/RM_MANAGER/rm_manager.sqlite
```

---

## Operacje CRUD

### Dodawanie kodu

**Przycisk:** ➕ Dodaj kod

**Dialog:**
- **Typ kodu:** Wybór z listy (TEMPORARY, EXTENDED, PERMANENT)
- **Kod:** Pole tekstowe (wymagane)
- **Opis:** Pole tekstowe (opcjonalne)

**Akcja:** Kod jest zapisywany z flagą `is_used = 0` (nieużyty)

### Edycja kodu

**Przycisk:** ✏️ Edytuj

**Wymogi:**
- Wybierz kod z listy (single-selection)
- Double-click na treeview = edycja

**Dialog:**
- **Kod:** Pole tekstowe (można zmienić)
- **Opis:** Pole tekstowe (można zmienić)

**Uwaga:** Typ kodu NIE JEST EDYTOWALNY (tylko kod i opis)

### Usuwanie kodu

**Przycisk:** 🗑️ Usuń

**Wymogi:**
- Wybierz kod z listy
- Potwierdzenie dialogiem

**Akcja:** Kod jest permanentnie usuwany z bazy danych

### Oznaczanie jako użyty

**Przycisk:** ✅ Oznacz jako użyty

**Wymogi:**
- Wybierz kod z listy
- Kod musi być nieużyty (`is_used = 0`)

**Dialog:**
- **Notatka:** Pole tekstowe (opcjonalne) - np. "Przesłano email 2026-04-14"

**Akcja:** 
- `is_used = 1`
- `used_at = CURRENT_TIMESTAMP`
- `used_by = [current_user]`
- `notes = [wprowadzona notatka]`

## Kolumny w treeview

| Kolumna | Opis | Przykład |
|---------|------|----------|
| **Typ** | Typ kodu | TEMPORARY |
| **Kod** | Kod odblokowujący | ABC-12345-XYZ-789 |
| **Opis** | Opis wprowadzony przez użytkownika | Kod testowy na 30 dni |
| **Użyty** | Status użycia | ✅ TAK / ❌ NIE |
| **Data użycia** | Kiedy oznaczono jako użyty | 2026-04-14 10:23:45 |
| **Utworzył** | Kto dodał kod | jan.kowalski |

## Sortowanie

Kody są automatycznie sortowane według:
1. **Typ kodu** (TEMPORARY → EXTENDED → PERMANENT)
2. **Data utworzenia** (najstarsze najpierw)

## Baza danych

### Tabela: `plc_unlock_codes` (rm_manager.sqlite)

```sql
CREATE TABLE plc_unlock_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    code_type TEXT NOT NULL CHECK (code_type IN ('TEMPORARY', 'EXTENDED', 'PERMANENT')),
    unlock_code TEXT NOT NULL,
    description TEXT,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_by TEXT,
    modified_at TIMESTAMP,
    is_used INTEGER DEFAULT 0,
    used_at TIMESTAMP,
    used_by TEXT,
    notes TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
```

## API (backend - rm_manager.py)

### `add_plc_code(rm_db_path, project_id, code_type, unlock_code, description, user)`

Dodaj nowy kod PLC.

**Parametry:**
- `rm_db_path` - ścieżka do `rm_manager.sqlite`
- `project_id` - ID projektu
- `code_type` - typ: `'TEMPORARY'`, `'EXTENDED'`, `'PERMANENT'`
- `unlock_code` - kod odblokowujący (string)
- `description` - opis (opcjonalny)
- `user` - login użytkownika

**Zwraca:** ID dodanego kodu (int)

**Rzuca:** `ValueError` jeśli `code_type` nieprawidłowy

---

### `update_plc_code(rm_db_path, code_id, unlock_code, description, user)`

Zaktualizuj kod PLC (tylko kod i opis).

**Parametry:**
- `rm_db_path` - ścieżka do `rm_manager.sqlite`
- `code_id` - ID kodu do zmiany
- `unlock_code` - nowy kod (opcjonalny)
- `description` - nowy opis (opcjonalny)
- `user` - login użytkownika

**Uwaga:** Typ kodu NIE MOŻE być zmieniony po utworzeniu

---

### `delete_plc_code(rm_db_path, code_id)`

Usuń kod PLC.

**Parametry:**
- `rm_db_path` - ścieżka do `rm_manager.sqlite`
- `code_id` - ID kodu do usunięcia

---

### `get_plc_codes(rm_db_path, project_id)`

Pobierz wszystkie kody dla projektu.

**Zwraca:** Lista słowników:
```python
[
    {
        'id': 1,
        'project_id': 123,
        'code_type': 'TEMPORARY',
        'unlock_code': 'ABC-12345',
        'description': 'Kod testowy',
        'created_by': 'jan.kowalski',
        'created_at': '2026-04-14 10:00:00',
        'modified_by': None,
        'modified_at': None,
        'is_used': 0,
        'used_at': None,
        'used_by': None,
        'notes': None
    },
    ...
]
```

---

### `mark_plc_code_as_used(rm_db_path, code_id, user, notes)`

Oznacz kod jako użyty (przekazany klientowi).

**Parametry:**
- `rm_db_path` - ścieżka do `rm_manager.sqlite`
- `code_id` - ID kodu
- `user` - kto użył
- `notes` - notatki (opcjonalne)

**Akcja:** Ustawia `is_used = 1`, `used_at = CURRENT_TIMESTAMP`

---

### `get_plc_codes_summary(rm_db_path, project_id)`

Pobierz podsumowanie kodów dla projektu.

**Zwraca:** Słownik z liczbami:
```python
{
    'TEMPORARY': {'total': 2, 'used': 1, 'unused': 1},
    'EXTENDED': {'total': 1, 'used': 0, 'unused': 1},
    'PERMANENT': {'total': 1, 'used': 1, 'unused': 0}
}
```

## Uprawnienia

**Wymagane uprawnienia:**
- Dodawanie/edycja/usuwanie kodów: **Brak specjalnych uprawnień** (każdy zalogowany użytkownik)
- Oznaczanie jako użyty: **Brak specjalnych uprawnień**

**Uwaga:** W przyszłości można dodać dedykowane uprawnienia `can_manage_plc_codes` w tabeli `rm_user_permissions`.

## Integracja z powiadomieniami płatności

Po osiągnięciu 100% płatności:
1. System wysyła automatyczne powiadomienia (email + in-app)
2. Odbiorca powiadomienia przechodzi do zakładki "💳 Płatności"
3. W sekcji "Kody PLC" widzi wszystkie dostępne kody
4. Przekazuje kody klientowi
5. Oznacza każdy kod jako "użyty" po przekazaniu

## Historia zmian

| Data | Wersja | Zmiany |
|------|--------|--------|
| 2026-04-14 | 1.0 | Pierwsza implementacja systemu kodów PLC |

## Znane ograniczenia

1. **Typ kodu nie jest edytowalny** po utworzeniu (trzeby usunąć i dodać ponownie)
2. **Brak historii zmian** dla kodów PLC (podobnie jak payment_history)
3. **Brak automatycznego wysyłania kodów** w powiadomieniach email (TODO future)

## TODO (przyszłe rozszerzenia)

- [ ] Historia zmian kodów PLC (tabela `plc_codes_history`)
- [ ] Automatyczne dołączanie kodów do powiadomień email o 100% płatności
- [ ] Uprawnienia `can_manage_plc_codes` w `rm_user_permissions`
- [ ] Export kodów do CSV/PDF
- [ ] Wygaśnięcie czasowe dla kodów TEMPORARY i EXTENDED
- [ ] Walidacja formatu kodu (regex pattern)

## Kontakt

W razie pytań lub problemów:
- **Dokumentacja techniczna:** PAYMENT_SYSTEM_README.md
- **Quick start:** PAYMENT_QUICKSTART.md
