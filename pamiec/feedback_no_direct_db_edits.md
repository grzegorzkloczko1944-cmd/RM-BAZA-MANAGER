---
name: feedback-no-direct-db-edits
description: Nigdy nie edytuj bezpośrednio plików SQLite w C:\RMPAK_CLIENT\RM_BAZY — zmiany baz tylko przez kod RM_MANAGER
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 500936ae-c6e9-49ab-ab0c-8596f0fa4f28
---

Nie edytuj bezpośrednio żadnych plików w `C:\RMPAK_CLIENT\RM_BAZY`. To jest lokalna wersja robocza baz danych.

**Why:** W firmie działają identyczne bazy na produkcji. Użytkownik stosuje mechanizmy migracyjne wbudowane w kod RM_MANAGER (np. jednorazowe migracje idempotentne przy starcie), żeby jednym kliknięciem/uruchomieniem propagować zmiany na produkcję. Bezpośrednia edycja pliku SQLite pomija ten mechanizm i nie trafi na produkcję.

**How to apply:** Jeśli zmiana wymaga modyfikacji schematu lub danych bazy — implementuj ją jako migrację w kodzie Pythona (wzorzec już istniejący w projekcie: np. jednorazowa migracja JSON → stage_staff_assignments). Nigdy nie używaj narzędzi do zapisu plików ani SQL-a bezpośrednio na plikach w C:\RMPAK_CLIENT\RM_BAZY.
