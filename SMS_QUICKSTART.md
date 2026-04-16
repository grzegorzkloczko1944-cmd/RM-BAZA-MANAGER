# SMS QUICKSTART - Powiadomienia SMS w RM_MANAGER

## 📱 Co to jest?

System powiadomień SMS automatycznie wysyła wiadomości do **pracowników przypisanych do etapu** o zmianach statusu:
- ✅ **Etap ROZPOCZĘTY** - SMS do pracowników przy starcie etapu
- ✅ **Etap ZAKOŃCZONY** - SMS do pracowników przy zakończeniu etapu
- ✅ **Test SMS** - możliwość wysłania testowej wiadomości

**Przykład SMS:**
```
Projekt: ABC-123 | MONTAŻ: ROZPOCZĘTY | 14.04.2026 10:30
```

**Kto dostaje SMS?**
- Pracownicy z listy **Listy → Pracownicy** przypisani do etapu (przycisk 👥 Przypisz)
- Muszą mieć wypełniony numer telefonu w formacie: `48123456789`

---

## 🚀 SETUP - Konfiguracja (5 minut)

### KROK 1: Załóż konto SMSAPI.pl

1. Wejdź na: **https://www.smsapi.pl/**
2. Kliknij **"Załóż konto"** (darmowa rejestracja)
3. Potwierdź email i zaloguj się
4. **Doładuj konto:**
   - Min. **10 PLN** (wystarczy na ~100-160 SMS)
   - BLIK / Przelew / Karta
   - Punkty **NIE WYGASAJĄ**

### KROK 2: Wygeneruj token OAuth

1. Panel SMSAPI → **Ustawienia** → **Dostępy** → **OAuth**
2. Kliknij **"Wygeneruj token"**
3. Nadaj nazwę: `RM_MANAGER`
4. Uprawnienia: **SMS** (zaznacz)
5. **Skopiuj token** (długi ciąg znaków) - NIE UDOSTĘPNIAJ NIKOMU!

### KROK 3: Dodaj numery telefonów pracowników

**Ważne:** Kolumna `phone` **już istnieje** w tabeli `employees` - nie potrzeba migracji!

**Dodaj numery telefonu:**
1. Uruchom **RM_MANAGER**
2. Menu → **Listy** → **👷 Pracownicy...**
3. Wybierz pracownika → kliknij **✏️ Edytuj**
4. W polu **Telefon** wpisz: **48123456789** (bez `+`, bez spacji, bez `-`)
5. Kliknij **💾 Zapisz**
6. Powtórz dla wszystkich pracowników, którzy mają dostawać SMS

**Przypisanie pracowników do etapów:**
1. Wybierz projekt w RM_MANAGER
2. Przy etapie (np. MONTAŻ) kliknij **👥 Przypisz**
3. Zaznacz pracowników
4. Zapisz

**Tylko przypisani pracownicy z wypełnionym `phone` dostaną SMS!**

### KROK 4: Skonfiguruj RM_MANAGER

1. Uruchom **RM_MANAGER**
2. Menu → **Narzędzia** → **📱 Konfiguracja SMS...**
3. Wypełnij:
   - ✅ **SMS włączony** (zaznacz)
   - **Token OAuth:** (wklej token z SMSAPI)
   - **Nazwa nadawcy:** `RM_MANAGER` (lub inna, wymaga rejestracji w SMSAPI, 10 PLN/msc)
   - **Kod kraju:** `48` (dla Polski)
4. Kliknij **💾 Zapisz**

### KROK 5: Test wysyłki

1. Menu → **Narzędzia** → **📱 Wyślij SMS testowy...**
2. Podaj **swój numer** (np. `48123456789`)
3. Wpisz treść: `Test SMS z RM_MANAGER`
4. Kliknij **📱 Wyślij**
5. Sprawdź telefon - SMS powinien przyjść w ciągu 10-30 sekund

**Jeśli SMS nie przyszedł:**
- Sprawdź token OAuth (czy dobrze skopiowany)
- Sprawdź saldo w SMSAPI (min. 1 punkt)
- Sprawdź numer telefonu (czy prawidłowy format)
- Zobacz konsole Python - błędy są tam wypisywane

---

## 📚 UŻYTKOWANIE

### Automatyczne powiadomienia

SMS wysyłany jest **automatycznie** gdy:
1. Klikniesz **ROZPOCZNIJ** etap
2. Klikniesz **ZAKOŃCZ** etap

**Kto dostaje SMS?**
- **Pracownicy przypisani do etapu** (przycisk 👥 Przypisz przy etapie)
- Z wypełnionym polem `phone` w **Listy → Pracownicy**
- Jeśli NIE ma przypisanych pracowników → **NIE wysyła SMS**

**Przypisanie pracowników:**
1. Wybierz projekt
2. Przy etapie (np. MONTAŻ) kliknij **👥 Przypisz**
3. Zaznacz pracowników (np. Jan Kowalski, Anna Nowak)
4. Kliknij **💾 Zapisz**
5. Teraz ci pracownicy dostaną SMS przy START/END tego etapu

**Format SMS:**
```
Projekt: Przenośnik ABC-2026-045 | ELEKTROMONTAŻ: ROZPOCZĘTY | 14.04.2026 15:22
```

### Wyłączanie SMS

**Tymczasowo:**
- Menu → Narzędzia → Konfiguracja SMS → **Odznacz "SMS włączony"**

**Na stałe:**
- W `manager_sync_config.json` ustaw: `"sms_enabled": false`

---

## 💰 KOSZTY

| Pakiet punktów | Cena | Koszt 1 SMS | SMS/pakiet |
|----------------|------|-------------|------------|
| 100 pkt        | 10 PLN | **0.10 PLN** | 100 SMS |
| 500 pkt        | 45 PLN | **0.09 PLN** | 500 SMS |
| 1000 pkt       | 80 PLN | **0.08 PLN** | 1000 SMS |
| 5000 pkt       | 350 PLN | **0.07 PLN** | 5000 SMS |

**Długie SMS (>160 znaków):** koszują więcej punktów (2 SMS = 2 pkt, 3 SMS = 3 pkt)

**Przykładowe koszty miesięczne:**
- **Mały zespół (5 osób, 50 SMS/msc):** ~5 PLN
- **Średni zespół (20 osób, 200 SMS/msc):** ~18 PLN
- **Duży zespół (50 osób, 500 SMS/msc):** ~40 PLN

**Bez opłat miesięcznych!** Punkty nie wygasają.

---

## 🛠️ TROUBLESHOOTING

### ❌ "SMS wyłączony w konfiguracji"
→ Włącz SMS: Menu → Narzędzia → Konfiguracja SMS → Zaznacz "SMS włączony"

### ❌ "Brak tokenu SMSAPI"
→ Dodaj token: Menu → Narzędzia → Konfiguracja SMS → Token OAuth

### ❌ "Brak biblioteki smsapi-client"
```bash
pip install smsapi-client
```

### ❌ "Brak numerów telefonów"
→ Pracownicy przypisani do etapu nie mają wypełnionego pola `phone`
→ Dodaj telefony: Menu → Listy → Pracownicy → Edytuj

### ❌ "Brak przypisanych pracowników"
→ Nie przypisałeś pracowników do etapu
→ Przypisz: wybierz projekt → przycisk 👥 przy etapie → zaznacz pracowników

### ❌ "Invalid token" / "Unauthorized"
→ Token nieprawidłowy - wygeneruj nowy w SMSAPI.pl

### ❌ "Insufficient funds"
→ Brak punktów w SMSAPI - doładuj konto

### ❌ SMS nie dochodzi
1. Sprawdź saldo w SMSAPI (Panel → Pulpit)
2. Sprawdź logi wysyłki (Panel → SMS → Historia)
3. Sprawdź czy numer jest prawidłowy (48 + 9 cyfr)
4. Sprawdź czy telefon ma zasięg

---

## 📋 ARCHITEKTURA

### Gdzie są dane?

**Pracownicy:**
- `Y:/RM_MANAGER/rm_manager.sqlite` → tabela `employees` (kolumna `phone`)
- Edycja: Menu → Listy → Pracownicy

**Przypisania do etapów:**
- `Y:/RM_MANAGER/rm_manager_project_X.sqlite` → tabela `project_stages` (kolumna `assigned_staff`)
- Format: JSON lista pracowników `[{"id": 1, "name": "Jan Kowalski"}, ...]`
- Edycja: Przycisk 👥 Przypisz przy etapie

**Konfiguracja SMS:**
- `C:\RMPAK_CLIENT\manager_sync_config.json` → klucze `sms_*`
- Edycja: Menu → Narzędzia → Konfiguracja SMS

---

## 📋 PLIKI KONFIGURACYJNE

### manager_sync_config.json

```json
{
    "master_db_path": "Y:/RM_BAZA/master.sqlite",
    "rm_db_path": "rm_manager.sqlite",
    
    "sms_enabled": true,
    "sms_api_token": "TWÓJ_TOKEN_OAUTH_Z_SMSAPI",
    "sms_sender_name": "RM_MANAGER",
    "sms_default_country_code": "48"
}
```

**Gdzie przechowywany:** `C:\RMPAK_CLIENT\manager_sync_config.json`

---

## 🔒 BEZPIECZEŃSTWO

⚠️ **WAŻNE:**
- **Nie udostępniaj tokenu OAuth** nikomu
- Token OAuth = hasło dostępu do wysyłki SMS
- Trzymaj `manager_sync_config.json` w bezpiecznym miejscu
- Jeśli token wycieknie → **Natychmiast usuń go w SMSAPI** i wygeneruj nowy

---

## ℹ️ FAQ

**Q: Czy mogę zmienić treść SMS?**  
A: Tak, edytuj funkcję `send_stage_change_sms()` w `rm_manager.py`

**Q: Czy mogę wysłać SMS do konkretnych osób?**  
A: Tak - przypisz tylko tych pracowników do etapu (przycisk 👥)

**Q: Co jeśli nie przypisałem pracowników do etapu?**  
A: SMS nie zostanie wysłany (brak odbiorców)

**Q: Czy mogę użyć innej bramki SMS?**  
A: Tak, ale wymaga zmiany kodu (np. Twilio, SerwerSMS.pl)

**Q: Czy działa bez internetu?**  
A: NIE - SMS wymaga połączenia z API SMSAPI.pl

**Q: Ile czasu zajmuje dostarczenie SMS?**  
A: Zwykle 10-30 sekund, max. 2 minuty

**Q: Czy pracownik może być przypisany do wielu etapów?**  
A: Tak! Dostanie SMS przy każdym etapie, do którego jest przypisany

---

## 📞 POMOC

- **SMSAPI pomoc:** https://www.smsapi.pl/kontakt
- **Dokumentacja API:** https://docs.smsapi.pl/
- **Issues:** Zgłoś problem w repozytorium

---

**Wersja:** 1.0 (14.04.2026)  
**Ostatnia aktualizacja:** Dodanie modułu SMS do RM_MANAGER
