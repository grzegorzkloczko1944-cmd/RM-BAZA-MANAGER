# Kody PLC - Quick Start (5 minut) - v2 (2026-04-15)

⚡ **Szybki start** dla systemu kodów odblokowujących PLC w RM_MANAGER

---

## 🎯 Cel

**Programista wprowadza kody** po zakończeniu programowania → **Księgowość wprowadza 100% płatność** → **Kody są przekazywane klientowi AUTOMATYCZNIE (email/SMS)** 🚀

---

## 📝 Krok 1: Dodaj kod (Programista)

1. Otwórz **RM_MANAGER**
2. Wybierz projekt z listy
3. Przejdź do zakładki **"💳 Płatności"**
4. Przewiń w dół do sekcji **"Kody odblokowujące PLC"**
5. Kliknij **"➕ Dodaj kod"**
6. Wypełnij formularz:
   - **Typ kodu:** TEMPORARY / EXTENDED / PERMANENT
   - **Kod:** np. `ABC-12345-XYZ-789`
   - **Opis:** np. "Kod testowy na 30 dni" (opcjonalnie)
7. Kliknij **"✅ Zapisz"**

✅ **Kod jest zapisany** i czeka na przekazanie klientowi

---

## 💰 Krok 2: Wprowadź 100% płatność (Księgowość)

1. Przejdź do sekcji **"Transze płatności"** (górna część zakładki)
2. Kliknij **"➕ Dodaj transzę"**
3. Ustaw:
   - **Procent:** 100%
   - **Data płatności:** [dzisiejsza data]
4. Kliknij **"✅ Zapisz"**

🔔 **System automatycznie wysyła powiadomienia** email + in-app

---

## 📤 Krok 3: Przekaż kod klientowi (NOWE! 2 metody)

### Metoda A: Ręczne oznaczenie jako użyty (tradycyjna)

1. Osoba odpowiedzialna otrzymuje powiadomienie
2. Przejdź do sekcji **"Kody PLC"**
3. **Wybierz kod** z listy (kliknij na wiersz)
4. Kliknij **"✅ Oznacz jako użyty"**
5. Wprowadź notatkę (opcjonalnie): np. "Przesłano email 2026-04-14"
6. Kliknij **"✅ Oznacz"**

✅ **Kod oznaczony jako użyty** → widoczne w kolumnie "Użyty": ✅ TAK

### Metoda B: 🚀 Automatyczna wysyłka (EMAIL/SMS) - REKOMENDOWANA!

1. Osoba odpowiedzialna otrzymuje powiadomienie
2. Przejdź do sekcji **"Kody PLC"**
3. **Wybierz kod** z listy (kliknij na wiersz)
4. Kliknij **"📤 UŻYJ (wyślij)"**
5. System sprawdzi:
   - ✅ Czy masz uprawnienia do wysyłki (lista ADMIN)
   - ⚠️ Jeśli PERMANENT i płatność < 100% → **PODWÓJNE POTWIERDZENIE**
6. Wybierz metodę wysyłki:
   - 📧 **Email**
   - 📱 **SMS**
   - 📧+📱 **Oba**
7. Wprowadź dane odbiorcy:
   - Email: `klient@firma.pl` (można wiele: `email1@pl, email2@pl`)
   - Telefon: `48123456789` lub `123456789`
8. Kliknij **"📤 Wyślij"**

✅ **Kod wysłany automatycznie!** Klient otrzymuje email/SMS z kodem

---

## 🔐 Krok 0 (jednorazowo): Dodaj użytkowników uprawnionych

**Tylko wybrani użytkownicy mogą wysyłać kody przez system.**

1. Otwórz **RM_MANAGER**
2. Menu → **Narzędzia** → **🔐 Zarządzaj uprawnieniami wysyłki kodów PLC...**
3. Kliknij **"➕ Dodaj użytkownika"**
4. Wprowadź **nazwę użytkownika** (np. `Jan Kowalski`)
5. Notatki (opcjonalnie): np. "Kierownik działu serwisu"
6. Kliknij **"✅ Dodaj"**

✅ **Użytkownik może teraz wysyłać kody**

**Usuwanie użytkownika:**
1. Wybierz użytkownika z listy
2. Kliknij **"🗑️ Usuń"**
3. Potwierdź

---

## 🔧 Operacje dodatkowe

### Edytuj kod

1. Wybierz kod z listy (lub double-click)
2. Kliknij **"✏️ Edytuj"**
3. Zmień kod lub opis
4. Kliknij **"✅ Zapisz"**

### Usuń kod

1. Wybierz kod z listy
2. Kliknij **"🗑️ Usuń"**
3. Potwierdź dialogiem

---

## 📊 Typy kodów i kolumna "Ważny do"

| Typ | Symbol | Zastosowanie | Ważny do |
|-----|--------|-------------|----------|
| TEMPORARY | ⏱️ | Testowe odblokowanie (czasowe) | **📅 Data utworzenia + 14 dni** |
| EXTENDED | 📅 | Przedłużona licencja | `---` |
| PERMANENT | 🔓 | Pełna licencja (bez limitu) | `---` |

**Przykład:**
- **Data utworzenia:** 2026-04-15 10:30
- **Ważny do:** 2026-04-29 10:30 (automatycznie obliczone)

---

## ⚠️ Specjalne zasady dla PERMANENT

**Jeśli płatność < 100%, system wymaga PODWÓJNEGO POTWIERDZENIA:**

```
Ostrzeżenie 1:
"UWAGA! Wysyłasz kod PERMANENT, a płatność wynosi tylko 50%!
 Czy na pewno chcesz kontynuować?"

Ostrzeżenie 2:
"POTWIERDZENIE PONOWNE:
 Kod: ABC-12345
 Typ: PERMANENT
 Płatność: 50%
 
 CZY NA PEWNO WYSŁAĆ?"
```

✅ Chroni przed przypadkowym wysłaniem kodu permanentnego przy niepełnej płatności

---

## ❓ FAQ

**P: Czy mogę zmienić typ kodu po utworzeniu?**  
O: NIE. Typ kodu jest NIEZMIENIALNY. Musisz usunąć i dodać ponownie z nowym typem.

**P: Co się stanie jeśli oznaczyłem kod jako użyty przez pomyłkę?**  
O: Nie ma automatycznego "cofnięcia". Skontaktuj się z administratorem bazy danych.

**P: Czy kody są automatycznie wysyłane w powiadomieniach email o 100% płatności?**  
O: NIE. Musisz ręcznie użyć przycisku "📤 UŻYJ (wyślij)" aby wysłać kod.

**P: Kto może dodawać/edytować/usuwać kody?**  
O: Każdy zalogowany użytkownik (brak specjalnych uprawnień wymaganych).

**P: Kto może WYSYŁAĆ kody przez email/SMS?**  
O: Tylko użytkownicy na liście uprawnień (zarządzane przez ADMINA w: Narzędzia → Zarządzaj uprawnieniami).

**P: Co się stanie jeśli nie mam uprawnień do wysyłki?**  
O: System pokaże błąd: "Użytkownik 'Jan' nie ma uprawnień do wysyłki kodów PLC. Skontaktuj się z administratorem."

**P: Jak wyświetlić "Ważny do" dla kodu TEMPORARY?**  
O: Kolumna "Ważny do" pokazuje datę automatycznie gdy kod zostanie oznaczony jako użyty.

**P: Czy mogę wysłać kod na wiele adresów email naraz?**  
O: TAK! Oddziel adresy przecinkami: `email1@pl, email2@pl, email3@pl`

**P: Czy system loguje kto i kiedy wysłał kod?**  
O: TAK. Dane wysyłki są zapisywane (kiedy, kto, jak: email/SMS).

---

## 🚀 Migracja (jednorazowo - przed pierwszym użyciem)

**Przed użyciem nowych funkcji, uruchom migrację (2 metody):**

### Metoda A: Z GUI (REKOMENDOWANA) ✨
```
RM_MANAGER → Narzędzia → 🔧 Migruj bazę kodów PLC (dodaj kolumny)
    → Przeczytaj opis → Potwierdź → ✅ Gotowe!
```

### Metoda B: Z konsoli (alternatywna)
```bash
python migrate_plc_codes_columns.py Y:/RM_MANAGER/rm_manager.sqlite
```

✅ Dodaje nowe kolumny i tabele do bazy danych

---

## 📚 Dokumentacja pełna

Zobacz: **PLC_CODES_README.md** - kompletna dokumentacja techniczna

---

## 🐛 Problemy?

W razie błędów sprawdź:
1. Czy projekt jest WYBRANY z listy?
2. Czy jesteś ZALOGOWANY?
3. Czy istnieje plik `rm_manager.sqlite`?

---

**Zakończono:** 2026-04-14  
**Wersja:** 1.0  
**Autor:** RM_MANAGER System
