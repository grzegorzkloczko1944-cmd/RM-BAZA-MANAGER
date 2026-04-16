# 🚀 Quick Start - Migracja Kompletna (Kombajn)

## ✨ Jeden skrypt - wszystkie funkcje

**migrate_full.py** to kompleksowy skrypt migracji, który wykonuje WSZYSTKIE zmiany w bazie danych w jednym przebiegu.

## 📦 Co robi?

### ✅ Dodaje kolumny do `projects`:
- `designer` - konstruktor/projektant
- `started_at` - data rozpoczęcia
- `expected_delivery` - planowany termin
- `completed_at` - data zakończenia
- `montaz` - data montażu (albo zmienia nazwę z `sat`)
- `fat` - Factory Acceptance Test
- `status` - status projektu
- `status_changed_at` - data ostatniej zmiany

### ✅ Zmienia nazwę kolumny:
- `sat` → `montaz`

### ✅ Tworzy tabele:
- `project_statuses` - system multi-status (wiele statusów naraz)
- `project_status_history` - historia zmian (kompatybilność)
- `project_status_changes` - szczegółowa historia (ADDED/REMOVED)

### ✅ Tworzy indeksy:
- 6 indeksów dla szybkiego wyszukiwania i analiz

## 🎯 Instalacja - TAK PROSTO!

```bash
# Uruchom skrypt
python migrate_full.py
```

**GOTOWE!** 🎉

Skrypt:
- ✅ Automatycznie znajdzie bazę danych z pliku config
- ✅ Sprawdzi co już istnieje
- ✅ Doda tylko to czego brakuje
- ✅ Można uruchamiać wielokrotnie bez szkody

## 🔄 Idempotentność

Skrypt jest **idempotentny** - możesz go uruchomić wielokrotnie:

**Pierwsze uruchomienie:**
```
✅ Dodano kolumnę: designer
✅ Dodano kolumnę: montaz
✅ Utworzono tabelę: project_statuses
... (wszystkie zmiany)
Wykonano: 15 zmian
```

**Drugie uruchomienie:**
```
ℹ️  Kolumna designer już istnieje - pominięto
ℹ️  Kolumna montaz już istnieje - pominięto
ℹ️  Tabela project_statuses już istnieje - pominięto
... (wszystkie sprawdzenia)
Baza danych jest już aktualna - nie wykonano żadnych zmian
```

**Bezpieczne!** Nie zepsuje istniejących danych.

## 📋 Szczegółowy output

Skrypt pokazuje dokładnie co robi:

```
================================================================================
MIGRACJA KOMPLETNA - System BOM
================================================================================

✅ Połączono z: Z:/RM_BAZA/master.sqlite
   Rozmiar: 15.34 MB

🔧 KROK 1: Sprawdzanie i dodawanie kolumn w tabeli projects...
--------------------------------------------------------------------------------
   ✅ Dodano kolumnę: designer - Konstruktor/projektant
   ℹ️  Kolumna started_at już istnieje - pominięto
   ✅ Dodano kolumnę: completed_at - Data faktycznego zakończenia
   ...

🔧 KROK 2: Zmiana nazwy kolumny sat → montaz...
--------------------------------------------------------------------------------
   ✅ Zmieniono nazwę kolumny: sat → montaz

🔧 KROK 3: Tworzenie tabeli project_statuses (multi-status)...
--------------------------------------------------------------------------------
   ✅ Utworzono tabelę: project_statuses
   ✅ Utworzono indeks: idx_project_statuses_project
   ...

🔧 KROK 4: Tworzenie tabeli project_status_history (historia)...
--------------------------------------------------------------------------------
   ✅ Utworzono tabelę: project_status_history
   ✅ Zainicjalizowano historię dla 23 projektów

🔧 KROK 5: Tworzenie tabeli project_status_changes (szczegółowa historia)...
--------------------------------------------------------------------------------
   ✅ Utworzono tabelę: project_status_changes
   ✅ Utworzono indeks: idx_status_changes_project
   ...

================================================================================
PODSUMOWANIE
================================================================================

✅ Migracja zakończona pomyślnie!
   Wykonano: 15 zmian(y)

📊 Struktura bazy danych:

Tabele:
  ✅ projects - rozszerzona o nowe kolumny
  ✅ project_statuses - multi-status system
  ✅ project_status_history - historia zmian (kompatybilność)
  ✅ project_status_changes - szczegółowa historia (ADDED/REMOVED)

📈 Nowe możliwości:
  • Wiele statusów jednocześnie (checkboxy)
  • Szczegółowa historia każdego statusu
  • Analiza czasu w statusach
  • Pełny audyt zmian

📊 Statystyki:
  • projects: 23 rekordów
  • project_statuses: 0 rekordów
  • project_status_history: 23 rekordów
  • project_status_changes: 0 rekordów

🎉 Gotowe! Aplikacja jest gotowa do użycia z nowymi funkcjami.
```

## 🛠️ Ręczna ścieżka

Jeśli nie ma pliku config:

```bash
python migrate_full.py "Y:/RM_BAZA/master.sqlite"
```

## ⚠️ Po migracji

1. **Przeładuj aplikację** (zamknij i uruchom ponownie)
2. **Statusy istniejących projektów** - będą puste, trzeba ustawić ręcznie
3. **Nowe projekty** - automatycznie dostaną status "PRZYJETY"
4. **Historia** - zaczyna się od teraz (stare zmiany nie są śledzone)

## 🆚 vs Osobne skrypty

| Funkcja | migrate_full.py | migrate_multi_status.py + migrate_detailed... |
|---------|----------------|-----------------------------------------------|
| Dodaje kolumny | ✅ TAK | ⚠️ Częściowo (tylko niektóre) |
| Zmienia sat → montaz | ✅ TAK | ✅ TAK (tylko multi_status) |
| Tworzy project_statuses | ✅ TAK | ✅ TAK (tylko multi_status) |
| Tworzy project_status_changes | ✅ TAK | ✅ TAK (tylko detailed) |
| Inicjalizuje historię | ✅ TAK | ❌ NIE |
| Wszystko w jednym | ✅ TAK | ❌ NIE - trzeba uruchomić 2× |

## 💡 Rekomendacja

**Używaj `migrate_full.py`** - to najprostsza i najbezpieczniejsza opcja!

### Kiedy użyć osobnych skryptów?

Tylko jeśli:
- Chcesz etapowo wdrażać zmiany
- Masz specyficzne wymagania
- Testujesz poszczególne funkcje osobno

### W normalnym użyciu:

```bash
# Po prostu:
python migrate_full.py

# I tyle! 🎉
```

## 🔍 Weryfikacja

Po migracji sprawdź czy wszystko działa:

```python
# W Python:
import sqlite3

con = sqlite3.connect("Y:/RM_BAZA/master.sqlite")

# Sprawdź kolumny
cur = con.execute("PRAGMA table_info(projects)")
for row in cur:
    print(row[1])  # Nazwy kolumn

# Sprawdź tabele
cur = con.execute("""
    SELECT name FROM sqlite_master 
    WHERE type='table' AND name LIKE 'project_%'
    ORDER BY name
""")
for row in cur:
    print(row[0])

con.close()
```

Powinieneś zobaczyć:
```
# Kolumny:
id
name
designer
montaz
fat
status
completed_at
...

# Tabele:
project_status_changes
project_status_history
project_statuses
```

## 🆘 Troubleshooting

### Błąd: "Nie znaleziono pliku config"
```bash
python migrate_full.py "Z:/RM_BAZA/master.sqlite"
```

### Błąd: "Nie można otworzyć pliku"
- Sprawdź czy ścieżka jest poprawna
- Sprawdź czy plik istnieje
- Zamknij aplikację przed migracją

### Migracja się zatrzymała
- Sprawdź czy aplikacja nie ma otwartego połączenia z bazą
- Zamknij wszystkie okna aplikacji
- Uruchom skrypt ponownie (jest bezpieczny)

## ✅ Gotowe!

Po uruchomieniu `migrate_full.py` masz:
- ✅ Wszystkie kolumny
- ✅ System multi-status
- ✅ Szczegółową historię
- ✅ Wszystkie indeksy
- ✅ Gotową bazę danych

**Jeden skrypt - pełna funkcjonalność!** 🚀
