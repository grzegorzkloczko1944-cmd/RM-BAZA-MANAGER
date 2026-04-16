# 💳 PAYMENT QUICKSTART - RM_MANAGER

## ⚡ Start w 5 minut

### 1. Konfiguracja (raz, administrator)

```
Menu → Narzędzia → 💳 Konfiguracja powiadomień płatności...

☑ Powiadomienia włączone
Trigger: 100%

Odbiorcy email:
  ➕ programista@firma.pl
  ➕ serwis@firma.pl
  ➕ montaz@firma.pl

💾 Zapisz
```

### 2. Dodanie płatności 100% (księgowość)

```
1. Wybierz projekt z listy
2. Zakładka 💳 Płatności
3. ➕ Dodaj transzę
4. Procent: 100
   Data: 2026-04-13
5. 💾 Zapisz
```

**Automatycznie:**
- ✅ Email wysłany do 3 osób
- ✅ Banner w aplikacji dla wszystkich użytkowników

### 3. Odczyt powiadomienia (pracownik)

```
1. Zaloguj się do RM_MANAGER
2. 🔔 Banner: "Masz 1 nowe powiadomienie!"
3. 📋 Zobacz wszystkie
4. Przeczytaj → przystąp do działania (kody PLC)
```

---

## 📋 Częste użycia

### Dodanie transzy 30%
```
Płatności → ➕ Dodaj
Procent: 30
Data: 2026-03-10
Zapisz
```
(Nie wywołuje powiadomień - trigger=100%)

### Zmiana daty 100%
```
Płatności → zaznacz wiersz 100%
✏️ Edytuj datę
Nowa data: 2026-04-14
Zapisz
```
(Wywołuje ponowne powiadomienia!)

### Historia
```
Płatności → 📜 Historia zmian
```

---

## ⚙️ SMTP (opcjonalne)

Jeśli chcesz emaile:
```
Konfiguracja powiadomień:

Serwer: smtp.office365.com
Port: 587
Użytkownik: powiadomienia@firma.pl
Hasło: ********
```

**Bez SMTP:** Tylko in-app notifications (wystarczające!)

---

## 🚨 Błędy

### Email nie idzie
- Sprawdź SMTP server/hasło
- Lub: wyłącz email, używaj tylko in-app

### Banner nie pokazuje się
- Przeloguj użytkownika
- Sprawdź: Konfiguracja → ☑ Powiadomienia włączone

---

**Pełna dokumentacja:** [PAYMENT_SYSTEM_README.md](PAYMENT_SYSTEM_README.md)
