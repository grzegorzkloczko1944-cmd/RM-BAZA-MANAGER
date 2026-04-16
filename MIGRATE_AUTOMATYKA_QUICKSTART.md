# MIGRACJA: AUTOMATYKA → ELEKTROMONTAŻ

## Zmiana stage_code

**Dlaczego?** Zmiana nazwy etapu z `AUTOMATYKA` na `ELEKTROMONTAZ` (kodowanie bez polskich znaków).

---

## KROK 1: Backup

```bash
# Zrób kopię bezpieczeństwa PRZED migracją!
cd C:\RMPAK_CLIENT\RM_MANAGER\rm_manager
mkdir backup_przed_migracja
copy *.sqlite backup_przed_migracja\
```

---

## KROK 2: Uruchom skrypt migracji

```bash
python migrate_automatyka_to_elektromontaz.py
```

### Co robi skrypt:
- Zmienia `stage_code` z `AUTOMATYKA` → `ELEKTROMONTAZ` w:
  * `stage_definitions`
  * `project_stages`
  * `stage_dependencies` (predecessor i successor)

### Output:
```
================================================================================
MIGRACJA: AUTOMATYKA → ELEKTROMONTAZ
================================================================================

Znaleziono 5 baz danych:

📁 MASTER: rm_manager.sqlite
  ✅ Zmieniono 3 rekordów:
     • stage_definitions: 1
     • stage_dependencies_pred: 1
     • stage_dependencies_succ: 1

📁 PROJECT 6: rm_manager_project_6.sqlite
  ✅ Zmieniono 2 rekordów:
     • project_stages: 1
     • stage_dependencies_pred: 1

...

================================================================================
PODSUMOWANIE:
  Przetworzono baz: 5
  Zmigrowano:       5
  Zmieniono rekordów: 12
================================================================================

✅ Migracja zakończona!
```

---

## KROK 3: Aktualizuj definicje w GUI

1. **Uruchom RM_MANAGER GUI:**
   ```bash
   python rm_manager_gui.py
   ```

2. **Wybierz projekt**

3. **Menu → Narzędzia → 🔄 Aktualizuj definicje etapów**
   - To zaktualizuje `display_name` i `color` dla wszystkich etapów
   - Zsynchronizuje zmiany w całym systemie

---

## KROK 4: Weryfikacja

### Sprawdź Dashboard:
```
Etap             Status         Plan start    Plan koniec
────────────────────────────────────────────────────────
PROJEKT          ● TRWA         01-04-2026    06-04-2026
ELEKTROMONTAZ    ○ Oczekuje     15-04-2026    20-04-2026  ← ZMIENIONE!
URUCHOMIENIE     ○ Oczekuje     20-04-2026    23-04-2026
```

### Sprawdź Timeline:
- Etap powinien się nazywać **"Elektromontaż"**
- Zależności:
  * `MONTAZ → ELEKTROMONTAZ (SS, lag 3)`
  * `ELEKTROMONTAZ → URUCHOMIENIE (FS)`

---

## Co jeśli coś pójdzie nie tak?

### Przywróć backup:
```bash
cd C:\RMPAK_CLIENT\RM_MANAGER\rm_manager
copy backup_przed_migracja\*.sqlite .
```

### Uruchom ponownie:
```bash
python migrate_automatyka_to_elektromontaz.py
```

---

## FAQ

**Q: Czy mogę uruchomić skrypt kilka razy?**  
A: Tak, jest bezpieczny. Jeśli struktura już jest zaktualizowana, pokaże "Brak zmian".

**Q: Czy muszę zamknąć RM_MANAGER GUI przed migracją?**  
A: TAK! Zamknij wszystkie instancje GUI przed uruchomieniem skryptu.

**Q: Co z RM_BAZA?**  
A: RM_BAZA używa tylko `display_name` z master.sqlite, więc automatycznie zobaczy "Elektromontaż".

**Q: Czy walidacja zależności działa po migracji?**  
A: TAK! System sprawdza `stage_code`, które zostało zaktualizowane.

---

## Zmienione pliki

### W kodzie (już zaktualizowane):
- `rm_manager.py`:
  * `STAGE_DEFINITIONS`: ('ELEKTROMONTAZ', 'Elektromontaż', '#f39c12')
  * `STAGE_PRIORITY`: 'ELEKTROMONTAZ': 50
  * `CANONICAL_STAGES`: ('ELEKTROMONTAZ', 5)
  
- `rm_manager_gui.py`:
  * `DEFAULT_STAGE_SEQUENCE`: 'ELEKTROMONTAZ'
  * `DEFAULT_DEPENDENCIES`: 'MONTAZ' → 'ELEKTROMONTAZ' (SS)

### W bazach (migrowane skryptem):
- `rm_manager.sqlite`
- `rm_manager_project_*.sqlite`

---

## Kontakt przy problemach

Jeśli napotkasz błędy:
1. **Zachowaj backup!**
2. Skopiuj komunikat błędu
3. Sprawdź czy wszystkie GUI są zamknięte
4. Spróbuj ponownie

✅ Po migracji system działa identycznie, tylko z nową nazwą etapu!
