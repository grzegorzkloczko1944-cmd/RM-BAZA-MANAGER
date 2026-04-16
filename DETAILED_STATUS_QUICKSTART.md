# 📋 Quick Start - Szczegółowa Historia Statusów

## ✅ Wymagania

Przed uruchomieniem migracji szczegółowej historii, upewnij się że:

1. ✅ Uruchomiłeś już `migrate_multi_status.py` (system multi-statusów)
2. ✅ Masz zamknięte połączenia do bazy danych

## 🚀 Instalacja

```bash
# Uruchom migrację
python migrate_detailed_status_history.py
```

**To wszystko!** System automatycznie:
- Znajdzie bazę danych z pliku config
- Utworzy tabelę `project_status_changes`
- Doda 3 indeksy
- Gotowe do użycia

## 📊 Co się zmienia?

### Przed migracją
```
Historia zapisywała cały zestaw statusów:
old_status: "MONTAZ, PROJEKT"
new_status: "MONTAZ, ODBIORY, PROJEKT"
```

### Po migracji
```
Historia zapisuje każdą zmianę osobno:
2026-03-26 14:30 | ODBIORY | ADDED   | admin
2026-03-27 09:00 | MONTAZ  | REMOVED | admin
```

## 🎯 Nowe możliwości

```python
from project_manager import (
    get_status_detailed_history,    # Historia dla projektu
    get_status_timeline,             # Linia czasu statusów
    get_status_duration,             # Ile dni w danym statusie
    get_all_statuses_duration,       # Czasy wszystkich statusów
    is_status_currently_active       # Czy status jest aktywny
)

# Przykład: Ile dni projekt był w montażu?
days = get_status_duration(con, project_id=1, status="MONTAZ")
print(f"Montaż trwał {days:.1f} dni")

# Przykład: Pełna historia projektu
history = get_status_detailed_history(con, project_id=1)
for _, status, action, changed_at, changed_by, _ in history:
    print(f"{changed_at}: {action} {status} by {changed_by}")
```

## ⚠️ Ważne

- Historia zaczyna się **od momentu migracji**
- Przeszłe zmiany (przed migracją) **NIE są śledzone szczegółowo**
- GUI **nie wymaga żadnych zmian** - wszystko działa automatycznie
- Stary system historii (`project_status_history`) **nadal działa**

## 📚 Dokumentacja

Pełna dokumentacja z przykładami: [DETAILED_STATUS_HISTORY.md](DETAILED_STATUS_HISTORY.md)

## 🆘 Troubleshooting

### Błąd: "Tabela project_statuses nie istnieje"
```bash
# Najpierw uruchom podstawową migrację:
python migrate_multi_status.py

# Potem szczegółową historię:
python migrate_detailed_status_history.py
```

### Błąd: "Nie znaleziono pliku config"
```bash
# Podaj ścieżkę ręcznie:
python migrate_detailed_status_history.py "Y:/RM_BAZA/master.sqlite"
```

### Migracja już wykonana
```
⚠️  Tabela project_status_changes już istnieje - migracja nie jest potrzebna
```
To normalne - migrację uruchamia się tylko raz!

## 🎉 Gotowe!

Od teraz każda zmiana statusu jest śledzona szczegółowo. Żadnych zmian w GUI nie trzeba robić - wszystko działa automatycznie w tle! 🚀
