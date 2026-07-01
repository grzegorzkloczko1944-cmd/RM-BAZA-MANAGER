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
