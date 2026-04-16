# 💳 System płatności i powiadomień - RM_MANAGER

## Cel systemu

Automatyzacja procedury powiadamiania o pełnej płatności (100%), która uruchamia proces przekazywania kodów zabezpieczeń do PLC (odblokowujących maszyny).

**Problem rozwiązany:**
- Obecnie informacje o płatnościach przekazywane są ustnie i emailem (nieoptymalnie)
- Brak centralnego składowania danych o transzach płatności
- Brak historii zmian

**Rozwiązanie:**
- System transz płatności (30%, 70%, 100%) z datami
- Automatyczne powiadomienia email + in-app przy 100% płatności
- Pełna historia zmian (kto, kiedy zmienił)

---

## 📊 Architektura

### Baza danych (rm_manager.sqlite)

**Tabele:**
- `payment_milestones` - transze płatności (procent + data)
- `payment_history` - audit log zmian
- `payment_notification_config` - konfiguracja powiadomień (odbiorcy, SMTP)
- `payment_notifications_sent` - log wysłanych emaili
- `in_app_notifications` - powiadomienia w aplikacji

---

## 🎯 Funkcjonalność

### 1. Zakładka "💳 Płatności"

**Lokalizacja:** Główne okno projektu → zakładka "💳 Płatności"

**Funkcje:**
- ➕ **Dodaj transzę** - dodanie nowej transzy (np. 30%, 70%, 100%)
- ✏️ **Edytuj datę** - zmiana daty istniejącej transzy
- 🗑️ **Usuń transzę** - usunięcie transzy
- 📜 **Historia zmian** - pełna historia operacji

**Treeview kolumny:**
- Procent (%) - wartość transzy
- Data płatności - data zapłaty
- Utworzył - kto dodał
- Ostatnia zmiana - kiedy ostatnio edytowano

### 2. Automatyczne powiadomienia

**Trigger:** Gdy transza osiągnie 100% (konfigurowalne)

**Rodzaje powiadomień:**
1. **Email** - automatyczny email do skonfigurowanych odbiorców
2. **In-app** - banner na górze aplikacji + lista powiadomień

**Banner powiadomień:**
- Pojawia się automatycznie po zalogowaniu (jeśli są nieprzeczytane)
- 🔔 "Masz X nowe powiadomienia o płatnościach!"
- Przyciski: "📋 Zobacz wszystkie" | "❌ Zamknij"

### 3. Konfiguracja powiadomień

**Lokalizacja:** Menu → Narzędzia → 💳 Konfiguracja powiadomień płatności...

**Opcje:**
- **Trigger (%)** - przy jakim procencie wysyłać powiadomienie (domyślnie 100%)
- **Powiadomienia włączone** - checkbox on/off
- **Odbiorcy email** - lista adresów email (➕ Dodaj | 🗑️ Usuń)
- **Konfiguracja SMTP:**
  - Serwer
  - Port (domyślnie 587)
  - Użytkownik
  - Hasło

---

## 📋 Instrukcja użytkowania

### Scenariusz 1: Księgowość wpisuje płatność 100%

1. **Księgowość** loguje się do RM_MANAGER (konto USER)
2. Wybiera projekt z listy
3. Przechodzi do zakładki "💳 Płatności"
4. Klika **➕ Dodaj transzę**
5. Wpisuje:
   - Procent: **100**
   - Data płatności: **2026-04-13** (lub wybiera z kalendarza)
6. Klika **💾 Zapisz**

**Co się dzieje automatycznie:**
- ✅ Transza zapisana w bazie
- ✅ Wpis w historii zmian
- ✅ Email wysłany do skonfigurowanych odbiorców
- ✅ Powiadomienie in-app utworzone

### Scenariusz 2: Pracownik otrzymuje powiadomienie

1. **Pracownik** loguje się do RM_MANAGER
2. **Banner** pojawia się na górze: 🔔 "Masz 1 nowe powiadomienie o płatnościach!"
3. Klika **📋 Zobacz wszystkie**
4. Widzi listę powiadomień:
   ```
   Projekt: Maszyna XYZ (ID: 123)
   Płatność: 100%
   Data płatności: 2026-04-13
   Wpisane przez: anna.kowalska
   ```
5. **Przystępuje do działania** - przekazuje kody PLC

### Scenariusz 3: Zmiana daty płatności

1. Wybierz projekt
2. Zakładka "💳 Płatności"
3. Zaznacz transzę (kliknij na wiersz)
4. Klika **✏️ Edytuj datę** (lub double-click)
5. Wpisuje nową datę
6. **💾 Zapisz**

**Historia zachowana:**
- Data poprzednia: 2026-04-10
- Data nowa: 2026-04-13
- Akcja: MODIFIED
- Kto zmienił: jan.nowak

---

## ⚙️ Konfiguracja (administrator)

### Pierwsze uruchomienie

**1. Skonfiguruj odbiorców email**

Menu → Narzędzia → 💳 Konfiguracja powiadomień płatności...

**Przykładowa lista:**
```
programista@firma.pl
serwis@firma.pl
montaz@firma.pl
```

**2. Skonfiguruj SMTP (opcjonalnie)**

Jeśli chcesz automatyczne emaile:
- Serwer: `smtp.office365.com` (lub inny)
- Port: `587`
- Użytkownik: `powiadomienia@firma.pl`
- Hasło: `********`

**UWAGA:** Bez konfiguracji SMTP działają tylko powiadomienia in-app!

**3. Włącz powiadomienia**

- ☑ Powiadomienia włączone (checkbox)
- Trigger: **100** %
- **💾 Zapisz**

---

## 🔍 Historia i audyt

### Historia zmian płatności

**Dostęp:** Zakładka Płatności → 📜 Historia zmian

**Rejestrowane zdarzenia:**
- **ADDED** - dodanie nowej transzy
- **MODIFIED** - zmiana daty transzy
- **DELETED** - usunięcie transzy

**Kolumny:**
| Procent | Nowa data | Akcja | Kto | Kiedy | Stara data |
|---------|-----------|-------|-----|-------|------------|
| 100% | 2026-04-13 | ADDED | anna.k | 2026-04-13 10:30 | --- |
| 100% | 2026-04-14 | MODIFIED | jan.n | 2026-04-13 14:20 | 2026-04-13 |

### Log wysłanych emaili

**Backend:** `rmm.get_payment_notifications_log(rm_db_path, project_id)`

**Dane:**
- Projekt, procent, data płatności
- Lista odbiorców
- Data wysłania
- Status: SUCCESS | FAILED | PENDING
- Komunikat błędu (jeśli failed)

---

## 🚨 Troubleshooting

### Problem: 'RMManagerGUI' object has no attribute 'rm_manager_db'

**Przyczyna:** Błąd w kodzie - używano nieistniejącego atrybutu

**Fix:** Zaktualizowano kod do wersji najnowszej (2026-04-14)
- Poprawny atrybut: `self.rm_master_db_path` (ścieżka do rm_manager.sqlite)

### Problem: Email nie wysyła się

**Sprawdź:**
1. Menu → Konfiguracja powiadomień
2. Czy ☑ Powiadomienia włączone?
3. Czy są odbiorcy na liście?
4. Czy SMTP server/user/password wypełnione?
5. Konsola Python - czy jest błąd SMTP?

**Typowe błędy:**
- `Connection refused` - zły port lub server
- `Authentication failed` - złe hasło
- `Relay denied` - brak uprawnień konta

**Workaround:** Wyłącz email, używaj tylko in-app notifications

### Problem: Powiadomienia in-app nie pokazują się

**Sprawdź:**
1. Czy użytkownik ma konto?
2. Czy logowanie powiodło się?
3. Console Python: `check_unread_notifications()` wykonane?

**Fix:**
```python
# W konsoli Python (debug)
import rm_manager as rmm
notifications = rmm.get_unread_notifications("Y:/RM_MANAGER/rm_manager.sqlite")
print(notifications)
```

### Problem: Transza 100% nie triggeruje powiadomień

**Sprawdź:**
1. Konfiguracja → Trigger % = **100**
2. Powiadomienia włączone = **True**
3. Console Python:
```
✅ Utworzono powiadomienie in-app: Projekt...
✅ Email wysłany do: ...
```
lub
```
⚠️ Powiadomienia wyłączone - skipuję...
```

---

## 📦 Pliki projektu

**Backend:** `rm_manager.py`
- Funkcje: `add_payment_milestone()`, `update_payment_milestone()`, `delete_payment_milestone()`
- Funkcje: `trigger_payment_notifications()`, `_send_payment_email()`, `_create_in_app_notification()`
- Funkcje: `get_payment_milestones()`, `get_payment_history()`

**GUI:** `rm_manager_gui.py`
- Zakładka: Płatności (tab 5)
- Menu: Konfiguracja powiadomień płatności
- Banner: `notifications_banner`, funkcje: `check_unread_notifications()`, `show_all_notifications()`

**Baza:** `rm_manager.sqlite` (master)
- Tabele płatności (utworzone automatycznie przy pierwszym uruchomieniu)

---

## 🎓 Dodatkowe informacje

### Uprawnienia

**Kto może dodawać płatności?**
- Wszyscy użytkownicy z rolą **USER** lub wyżej
- GUEST - brak dostępu

**Uprawnienia email:**
- Tylko ADMIN może edytować konfigurację powiadomień

### Limity

- Maksymalnie **1 transza per procent** dla projektu (unique constraint)
- Procent: 1-100%
- Historia: brak limitu (audit trail)
- Powiadomienia: ostatnie 100 (limit w GUI)

### Bezpieczeństwo

- Hasło SMTP przechowywane w bazie (plaintext) - **tylko dla zaufanego środowiska!**
- Logowanie zmian - każda operacja zapisuje `changed_by`
- Lock system - projekt musi być locked aby edytować płatności (współdzielone z etapami)

---

## 📞 Kontakt

Pytania? Zgłoś issue w projekcie BOM lub skontaktuj się z administratorem systemu.

**Data utworzenia:** 2026-04-13
**Wersja:** 1.0
**System:** RM_MANAGER
