# 📅 RM_MANAGER - Edycja dat szablonu i prognozy

## ✨ Nowe funkcje (polonizacja + edycja dat)

### 1. **Pełna polonizacja GUI**

Wszystkie terminy angielskie zostały przetłumaczone na polski:

#### Terminy kluczowe:
- **TEMPLATE** → **Szablon** (planowane daty rozpoczęcia/zakończenia etapów)
- **FORECAST** → **Prognoza** (przewidywane daty bazujące na rzeczywistym postępie)
- **VARIANCE** → **Odchylenie** (różnica między planem a rzeczywistością)
- **TIMELINE** → **Oś czasu**
- **DASHBOARD** → **Podsumowanie**
- **START** → **ROZPOCZNIJ**
- **END** → **ZAKOŃCZ**
- **CRITICAL PATH** → **Ścieżka krytyczna**

#### Statusy projektu:
- **ON_TRACK** → **ZGODNIE Z PLANEM** 🟢
- **AT_RISK** → **ZAGROŻONY** 🟡
- **DELAYED** → **OPÓŹNIONY** 🔴

---

## 📝 Edycja dat szablonu i prognozy

### Gdzie znaleźć:
**Menu → Narzędzia → Edytuj daty szablonu i prognozy**

### Co można edytować:

1. **Szablon Start** - planowana data rozpoczęcia etapu
2. **Szablon Koniec** - planowana data zakończenia etapu
3. **Prognoza Start** - przewidywana data rozpoczęcia (obliczana automatycznie)
4. **Prognoza Koniec** - przewidywana data zakończenia (obliczana automatycznie)

### Jak używać:

1. **Wybierz projekt** z listy rozwijanej
2. **Menu → Narzędzia → Edytuj daty szablonu i prognozy**
3. **Edytuj daty** w tabeli:
   - Każdy wiersz = jeden etap projektu
   - Format: **YYYY-MM-DD** (np. 2026-04-15)
   - Można edytować **Szablon** i **Prognozę**
4. **Kliknij "💾 Zapisz"**
5. System automatycznie:
   - Zapisuje nowe daty do bazy
   - Przelicza prognozę dla wszystkich etapów
   - Uwzględnia zależności (dependency graph)
   - Aktualizuje ścieżkę krytyczną

### Format daty:
```
YYYY-MM-DD

Przykłady:
2026-04-15  ✅ PRAWIDŁOWY
2026-4-5    ❌ ZŁY (brak zer wiodących)
15.04.2026  ❌ ZŁY (niewłaściwy format)
2026/04/15  ❌ ZŁY (slash zamiast myślnika)
```

### Walidacja:
- System sprawdza poprawność formatu daty
- Jeśli format jest nieprawidłowy → komunikat błędu
- Daty są walidowane PRZED zapisem do bazy

---

## 🔄 Jak działa przeliczanie prognozy?

### Algorytm:

1. **Pobiera daty szablonu** (template_start, template_end)
2. **Sprawdza rzeczywiste okresy** (stage_actual_periods)
3. **Jeśli etap już trwał/trwa:**
   - Prognoza = rzeczywiste daty
   - Oblicza odchylenie (variance)
4. **Jeśli etap nierozpoczęty:**
   - Uwzględnia **zależności** (FS/SS + lag days)
   - Stosuje **topological sort** (algorytm Kahna)
   - Propaguje opóźnienia/przyspieszenia
5. **Aktualizuje ścieżkę krytyczną**

### Przykład:

```
Projekt: 100 - Linia produkcyjna A

SZABLON (plan):
PROJEKT:      2026-04-01 → 2026-04-15  (14 dni)
KOMPLETACJA:  2026-04-16 → 2026-04-26  (10 dni)
MONTAŻ:       2026-04-27 → 2026-05-18  (21 dni)

RZECZYWISTOŚĆ:
PROJEKT rozpoczęty: 2026-04-01
PROJEKT zakończony: 2026-04-18  (+3 dni opóźnienie! ⚠️)

PROGNOZA (po przeliczeniu):
KOMPLETACJA:  2026-04-19 → 2026-04-29  (+3 dni)  ← propagacja opóźnienia
MONTAŻ:       2026-04-30 → 2026-05-21  (+3 dni)  ← propagacja opóźnienia
```

**Cascading effect** - opóźnienie w jednym etapie propaguje się na kolejne!

---

## 🎯 Przypadki użycia

### 1. Zmiana harmonogramu projektu
**Sytuacja:** Klient przesunął termin dostawy o 2 tygodnie

**Rozwiązanie:**
1. Menu → Narzędzia → Edytuj daty
2. Przesuń daty wszystkich etapów o +14 dni
3. Zapisz → system przeliczy prognozę

### 2. Optymalizacja ścieżki krytycznej
**Sytuacja:** Montaż można skrócić o 5 dni dzięki dodatkowej ekipie

**Rozwiązanie:**
1. Edytuj: MONTAŻ Szablon Koniec: wcześniejsza data (-5 dni)
2. Zapisz → prognoza automatycznie dostosuje kolejne etapy
3. Sprawdź wpływ na ścieżkę krytyczną

### 3. Korekta po opóźnieniu
**Sytuacja:** PROJEKT zakończony z 7-dniowym opóźnieniem

**Rozwiązanie:**
1. System automatycznie oznaczy opóźnienie (⚠️ +7 dni)
2. Edytuj daty kolejnych etapów aby nadrobić czas
3. Lub zaakceptuj przesunięcie całego projektu

---

## 📊 Wizualizacja w GUI

### Zakładka "Oś czasu":
```
🟢 ✔️ PROJEKT
   Szablon:   2026-04-01 → 2026-04-15
   Prognoza:  2026-04-01 → 2026-04-18
   Odchylenie: +3 dni ⚠️
   Okresy:    1 okres(ów)
              #1: 2026-04-01 → 2026-04-18 (ZAKOŃCZONY)

⏺️  📋 KOMPLETACJA
   Szablon:   2026-04-16 → 2026-04-26
   Prognoza:  2026-04-19 → 2026-04-29
   Odchylenie: +3 dni ⚠️
```

### Zakładka "Podsumowanie":
```
Status projektu:        🟡 ZAGROŻONY

Odchylenie (całkowite): +3 dni ⚠️
Przewidywane zakończ.:  2026-06-25
Aktywne etapy:          KOMPLETACJA

ŚCIEŻKA KRYTYCZNA (5 kluczowych etapów):
1. PROJEKT
2. KOMPLETACJA
3. MONTAŻ
4. URUCHOMIENIE
5. ODBIORY
```

---

## ⚙️ Konfiguracja

### Zmiana domyślnych czasów trwania etapów:

W pliku `rm_manager_gui.py`, funkcja `auto_initialize_project()`:

```python
# Domyślne czasy trwania (w dniach)
duration_days = 7  # domyślnie

if stage_code == 'PROJEKT':
    duration_days = 14      # 2 tygodnie
elif stage_code == 'KOMPLETACJA':
    duration_days = 10      # 10 dni
elif stage_code == 'MONTAZ':
    duration_days = 21      # 3 tygodnie
elif stage_code == 'AUTOMATYKA':
    duration_days = 14      # 2 tygodnie
```

Możesz dostosować te wartości do swojej organizacji.

---

## 🔒 Ważne informacje

### Co NIE jest edytowalne:
- **Rzeczywiste okresy** (stage_actual_periods) - tylko przez START/END
- **Zależności** (stage_dependencies) - tylko przez kod/setup
- **Definicje etapów** (stage_definitions) - słownik globalny

### Co JEST edytowalne:
- ✅ Daty szablonu (template_start, template_end)
- ✅ System automatycznie przelicza prognozę

### System automatyczny:
- 🔄 Auto-sync z master.sqlite po każdej zmianie
- 🔄 Auto-recalculate prognozy po zapisie dat
- 🔄 Auto-update ścieżki krytycznej

---

## 🆘 Pomoc

### Problem: "Nieprawidłowy format daty"
**Rozwiązanie:** Użyj formatu YYYY-MM-DD (np. 2026-04-15)

### Problem: Prognoza się nie aktualizuje
**Rozwiązanie:** 
1. Zapisz daty (💾 Zapisz)
2. System automatycznie przelicza
3. Jeśli nadal nie działa: sprawdź zależności etapów

### Problem: Nie mogę edytować dat prognozy
**Rozwiązanie:** 
- Prognoza jest obliczana automatycznie (pola tylko informacyjne)
- Edytuj daty **szablonu** → prognoza się dostosuje

---

## 📚 Zobacz też:
- [RM_MANAGER_GUI_README.md](RM_MANAGER_GUI_README.md) - pełna dokumentacja
- [PROJECT_STATS_MANAGER_SPEC.md](PROJECT_STATS_MANAGER_SPEC.md) - specyfikacja techniczna
- [INSTALACJA_RM_MANAGER.md](INSTALACJA_RM_MANAGER.md) - instalacja i konfiguracja
