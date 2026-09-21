---
name: project_swieta_auto_seed
description: Polskie święta auto-zasiewane do company_calendar przy starcie (rok + rok+1); święta ruchome algorytmem Gaussa
metadata: 
  node_type: memory
  type: project
  originSessionId: 383a3826-b965-4168-84c4-7cd465f3f22c
---

Kalendarz firmowy (`company_calendar`) jest **auto-zasiewany polskimi świętami ustawowymi** przy inicjalizacji master — `ensure_rm_master_tables()` woła `seed_polish_holidays(db, rok)` dla bieżącego i przyszłego roku. Idempotentne: NIE nadpisuje istniejących wpisów (ręcznych korekt, sobót pracujących).

**Funkcje (rm_manager.py):**
- `polish_public_holidays(year)` → dict {ISO: opis}; stałe + ruchome.
- `_easter_sunday(year)` → Wielkanoc algorytmem Gaussa/Meeusa; Poniedziałek Wielkanocny (+1), Zielone Świątki (+49), Boże Ciało (+60).
- `seed_polish_holidays(db, year, overwrite=False)` → wpisuje jako `day_type='HOLIDAY'`, zwraca liczbę dodanych.

**Why:** bez tego liczenie dni roboczych ([[project_urlopy_dni_robocze]]) pomijałoby tylko weekendy, nie święta. Zasiane ręcznie 2025–2027 do prawdziwej bazy (2026-07-20).

**How to apply:** 1 maja ma neutralny opis „1 Maja" (świadomie, bez wchodzenia w nazwę). Uwaga: święto w sobotę/niedzielę (np. 15.08 czasem) i tak jest wolne jako weekend — nie dublować liczenia.
