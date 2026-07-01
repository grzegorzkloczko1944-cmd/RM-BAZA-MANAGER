# AI Optimizer — koncepcja integracji Claude API z RM_MANAGER

## Problem z obecnym solverem

OR-Tools CP-SAT minimalizuje `makespan` (czas do zakończenia ostatniego etapu).
To cel matematyczny, nie biznesowy. Solver nie rozumie:
- że projekt VIP ma wyższy priorytet
- że etap musi skończyć się przed konkretnym terminem umownym
- że lepiej opóźnić projekt B żeby projekt A dotrzymał terminu

## Koncepcja: Agentic AI

Nie zamiennik OR-Tools — warstwa interpretacji, konfiguracji i autonomicznego działania.

```
RM_MANAGER GUI
     ↓
AI Agent (Claude API)
     ├── tool: read_schedule()     → czyta harmonogram z SQLite
     ├── tool: read_constraints()  → zasoby, pracownicy, niedostępność
     ├── tool: analyze_conflicts() → wykrywa konflikty
     ├── tool: propose_changes()   → proponuje zmiany dat
     ├── tool: apply_changes()     → zapisuje do bazy  ← kluczowe
     └── tool: explain_decision()  → tłumaczy co i dlaczego
```

## Co AI robi lepiej niż OR-Tools

1. **Wyjaśnienie wyniku** — tłumaczy słownie dlaczego projekt X jest opóźniony i co go blokuje
2. **Miękkie priorytety** — user opisuje słownie "ten projekt jest pilny bo kary umowne" → AI zamienia na wagi
3. **Wykrywanie konfliktów** — "te 3 projekty jednocześnie wymagają tego samego pracownika"
4. **Rekomendacje** — "żeby dotrzymać terminu X musisz albo A albo B"
5. **Autonomiczne zmiany w bazie** — agent sam zapisuje daty po zatwierdzeniu przez użytkownika

## Kluczowa różnica

- OR-Tools: czarna skrzynka, wynik matematyczny
- AI Agent: rozumuje krok po kroku, tłumaczy decyzje, pyta gdy niejednoznaczność

## Do ustalenia przed implementacją

1. Tryb działania: autonomiczny (sam zapisuje) vs z potwierdzeniem (proponuje → user zatwierdza)
2. Klucz API Anthropica
3. Czy `apply_optimization_result()` w `rm_manager.py` nadaje się jako tool dla agenta (obsługuje zapis dat do SQLite)

## Pliki

- `rm_manager_gui.py` — 30 914 linii, GUI Tkinter
- `rm_optimizer.py` — 1 498 linii, OR-Tools CP-SAT solver
- `rm_manager.py` — logika biznesowa, `apply_optimization_result()`, `get_projects_scheduling_data()`
- baza: `master.sqlite` (SQLite), tabele: `stage_schedule`, `project_stages`, `stage_actual_periods`

## Stack techniczny (planowany)

- Claude API (model: claude-sonnet-4-6 lub nowszy)
- Tool use (function calling) — agent wywołuje funkcje Python które operują na SQLite
- System prompt: opis algorytmu optymalizacji, reguły biznesowe, struktura bazy
- Nowy moduł: `rm_ai_optimizer.py`
- Opcjonalnie: Whisper API (OpenAI) — wejście głosowe zamiast pisania (~0.006$/min)

## Architektura: AI jako "kierownik", OR-Tools jako "pracownik"

AI nie buduje modelu OR-Tools bezpośrednio — wywołuje gotowe funkcje Python
które ustawiają parametry solvera. Bezpieczniejsze, łatwiejsze do debugowania.

```
użytkownik (chat / mikrofon)
     ↓
Claude API
     ↓
wywołuje funkcje-narzędzia (tools)
     ↓
OR-Tools CP-SAT solver
     ↓
zapis do master.sqlite
```

Pętla iteracyjna:
1. AI czyta bazę → identyfikuje konflikty
2. AI ustawia parametry → odpala solver
3. Solver zwraca wynik → AI ocenia biznesowo
4. Jeśli nie OK → AI modyfikuje parametry → ponownie od 2
5. Gdy OK → pokazuje propozycję użytkownikowi → po zatwierdzeniu zapisuje

## API między AI a solverem — co trzeba dopisać w Pythonie

Obecne wejścia solvera są zaprojektowane pod GUI (klikanie). Dla AI potrzeba
bardziej granularnych funkcji:

### Już istnieje (prawdopodobnie):
- priorytety projektów (wagi liczbowe)
- niedostępność pracowników
- limit czasu solvera
- tryb `fit_projects` / `optimize_all`

### Do dopisania — wejścia dla AI:
```python
set_hard_deadline(projekt_id, data)        # "musi skończyć się przed X" — twarde ograniczenie
set_soft_deadline(projekt_id, data, penalty) # "powinien skończyć się przed X" — miękkie z karą
freeze_stage(projekt_id, stage, data)      # "ten etap nie ruszaj"
set_project_priority(projekt_id, waga)     # priorytet liczbowy z opisu słownego
set_worker_unavailable(worker, od, do)     # urlop/L4 z rozmowy
```

### Do dopisania — wyjścia dla AI (żeby mógł ocenić wynik):
```python
get_conflicts() → list[dict]               # lista konfliktów czytelna dla AI
get_critical_path(projekt_id) → list       # co blokuje projekt
get_deadline_violations() → list[dict]     # które projekty przekraczają terminy i o ile
explain_result() → str                     # wynik w formie tekstowej
get_schedule_summary() → dict              # skrót harmonogramu wszystkich projektów
```

## Przypadek użycia 2: Analiza stanu projektów (read-only)

Prostszy od optymalizatora — AI tylko czyta bazę, nie zmienia nic.
Można zrobić jako pierwszy krok przed optymalizatorem.

**Przykładowe zapytania głosowe/tekstowe:**
- *"Które projekty są opóźnione i dlaczego?"*
- *"Kiedy realnie skończymy KOWALSKI?"*
- *"Co blokuje NOWAK?"*
- *"Podsumuj stan produkcji na dziś"*
- *"Który pracownik jest najbardziej przeciążony?"*
- *"Jakie projekty są zagrożone w tym miesiącu?"*

**Co AI robi:**
1. Czyta harmonogram z bazy (plan vs rzeczywistość)
2. Porównuje daty planowane z aktualnymi
3. Identyfikuje opóźnienia i ich przyczyny (brak startu etapu, pracownik zajęty, itd.)
4. Na podstawie historii podobnych projektów szacuje realne daty ukończenia
5. Generuje raport słowny — dla Ciebie lub dla klienta

**Dane których potrzebuje AI (już są w bazie):**
- `stage_schedule` — daty planowane
- `stage_actual_periods` — rzeczywiste starty/końce etapów
- `project_stages` — stan etapów (aktywny, zakończony, nie rozpoczęty)
- historia poprzednich projektów — do szacowania realistycznych terminów

**Wartość biznesowa:**
Zamiast ręcznie przeglądać timeline każdego projektu — jedno pytanie
i dostajesz raport z priorytetyzacją problemów.

## Kolejność implementacji (rekomendowana)

1. **Analiza stanu** (read-only) — najszybszy efekt, zero ryzyka
   - okno czatu w GUI
   - tools: `get_schedule_summary()`, `get_delays()`, `get_critical_path()`
   - AI odpowiada na pytania o stan projektów
2. **Wejście głosowe** — Whisper API, opcjonalnie
3. **Dopisać funkcje API** (wejścia + wyjścia) w `rm_optimizer.py`
4. **Optymalizator AI** — `rm_ai_optimizer.py` + pętla agentowa + zapis do bazy
