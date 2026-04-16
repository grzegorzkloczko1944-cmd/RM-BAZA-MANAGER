# 🚨 FILE TRACKING - Przewodnik Szybkiego Startu

## Co to jest?

System automatycznie sprawdza czy pliki projektów w RM_BAZA nadal istnieją i czy nie zostały podmienione.  
Chroni przed utratą synchronizacji gdy ktoś skasuje lub zastąpi projekt.

**NOWE (2026-04-14)**: Inteligentna weryfikacja automatycznie rozpoznaje backup/synchronizację! 🎯

---

## 🟢 Normalny widok

Gdy wszystko OK:
```
┌─────────────────────────────────────────────┐
│ PROJEKT: [123 - Mój projekt]  [🔄 Odśwież] │
└─────────────────────────────────────────────┘
│                                              │
│  [🟢 ROZPOCZNIJ]  [🔴 ZAKOŃCZ]              │
│                                              │
│  Status bar: 🟢 Projekt 123 - plik prawidłowy│
└──────────────────────────────────────────────┘
```

**Możesz:**
- ✅ Rozpoczynać/kończyć etapy
- ✅ Edytować daty
- ✅ Przeglądać timeline

---

## 🔄 Auto-naprawa po synchronizacji

**NOWA FUNKCJA:** Gdy inny użytkownik robi backup/synchronizację, system automatycznie wykrywa że to ten sam plik i aktualizuje śledzenie w tle.

**Co widać:**
- Żadnych ostrzeżeń! 🎉
- Praca kontynuowana normalnie
- W konsoli: `✅ Zawartość prawidłowa - aktualizuję birth_time`

**Jak to działa:**
1. System wykrywa zmianę czasu utworzenia pliku (backup)
2. Sprawdza zawartość bazy (project_id)
3. Jeśli ten sam projekt → automatyczny update
4. Jeśli inny plik → prawdziwe ostrzeżenie

---

## 🔴 Tryb READ-ONLY

Gdy plik projektu został **PODMIENIONY** (inny project_id):
```
┌─────────────────────────────────────────────┐
│ PROJEKT: [123 - Mój projekt]  [🔄 Odśwież] │
├═════════════════════════════════════════════┤
│ ⚠️ PLIK PROJEKTU PODMIENIONY - Tryb tylko  │
│    do odczytu    [🔄 Resetuj śledzenie]    │
└─────────────────────────────────────────────┘
│                                              │
│  [🔒 ZABLOKOWANE]  [🔒 ZABLOKOWANE]         │
│                                              │
│  Status bar: ⚠️ TRYB TYLKO DO ODCZYTU       │
└──────────────────────────────────────────────┘
```

**Możesz:**
- ✅ Przeglądać dane (są bezpieczne w RM_MANAGER!)
- ❌ Nie możesz rozpocząć/zakończyć etapów

---

## 🔧 Jak naprawić?

### Krok 1: Sprawdź plik
Plik projektu powinien być tutaj:
```
Y:/RM_BAZA/projekt_123/data.sqlite
```

### Krok 2: Jeśli plik zniknął lub został podmieniony
1. Skontaktuj się z administratorem
2. Poproś o sprawdzenie backupu
3. **NIE PANIKUJ** - Twoje dane w RM_MANAGER są bezpieczne!

### Krok 3: Po przywróceniu właściwego pliku
1. Menu: **Narzędzia**
2. Wybierz: **🔄 Resetuj śledzenie pliku projektu**
3. Potwierdź w oknie dialogowym
4. ✅ Gotowe! Tryb normalny przywrócony

---

## ❓ Najczęstsze pytania

### "Czerwony banner się pojawił - co się stało?"
Plik projektu został **podmieniony** na inny (różny project_id w bazie).  
To NIE jest efekt backup/synchronizacji - skontaktuj się z administratorem.

### "Inny użytkownik robi backup - czy dostanę ostrzeżenie?"
**NIE!** 🎯 System automatycznie rozpozna że to ten sam plik i zaktualizuje śledzenie w tle.  
Pracujesz normalnie bez żadnych przeszkód.

### "Przyciski są zablokowane"
To normalne w trybie READ-ONLY.  
Przywróć plik i użyj "Resetuj śledzenie".

### "Moje dane zniknęły?"
**NIE!** Dane w RM_MANAGER są bezpieczne.  
Możesz je przeglądać nawet w trybie READ-ONLY.

### "Jak wyłączyć ten mechanizm?"
Nie można. To zabezpieczenie przed utratą synchronizacji.

### "Administrator przywrócił plik - co teraz?"
Menu → Narzędzia → Resetuj śledzenie pliku projektu

---

## ⚡ Szybkie akcje

| Sytuacja | Akcja |
|----------|-------|
| 🔴 Banner ostrzegawczy | Sprawdź czy plik istnieje |
| 🔒 Przyciski zablokowane | Zobacz banner - przyczyna tam |
| ✅ Plik przywrócony | Resetuj śledzenie (menu) |
| 📞 Potrzebujesz pomocy | Skontaktuj się z adminem |

---

## 🎯 W skrócie

1. **System sprawdza pliki automatycznie** przy każdym wyborze projektu
2. **Jeśli coś nie tak → tryb READ-ONLY** (czerwony banner + blokada)
3. **Dane są bezpieczne** - nic nie zostaje usunięte
4. **Po naprawie → Resetuj śledzenie** i wracasz do normalnej pracy

**Aplikacja Cię chroni, nie blokuje!** 🛡️

