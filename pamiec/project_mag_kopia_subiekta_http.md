---
name: project_mag_kopia_subiekta_http
description: Makro MAG (Inventor) czyta KOPIĘ Subiekta z serwera przez HTTP :5061 (rm_mag_http.py), kopię pisze stacja (subiekt_kopia_sync.py) — W2019S nie ma mostu Sfery
metadata:
  type: project
---

# MAG — kopia Subiekta na serwerze + HTTP (27.09.2026)

Priorytet usera 27.09: „czytać Subiekta, wystawić przez HTTP, zapisać bazę
Subiekta do SQL na serwerze" — PRZED skanowaniem modeli 3D.

**Dlaczego kopia, a nie most na żywo:** most Sfery działa tylko na
stacjach (SDK `C:\iLogic\Subiekt\Bin` + logowanie operatora). W2019S go
nie ma, więc serwer HTTP nie ma jak zapytać Subiekta.

```
stacja: subiekt_kopia_sync.py ── sub-* ──► W2019S: subiekt_kopia.sqlite
                                               └─► rm_mag_http.py :5061 ◄── MAG.ivb
```

* `sub-` = piąta baza RM_SERWER, WAL (lokalny dysk — zakaz WAL dotyczy SMB);
* HTTP tylko GET, bazy `mode=ro`, `&format=tsv` dla VBA (brak parsera JSON);
* kartoteki podmieniane kompletem jedną transakcją; pusty katalog z mostu
  NIE podmienia (to awaria mostu, nie pusty Subiekt);
* miniatury po jednej kartotece (0,08 s), tylko nowe.

**Stan:** przetestowane na serwerze testowym na M-OLD, NIE wdrożone.
Wdrożenie wymaga restartu usługi RM_SERWER (uzgodnić) i otwarcia portu
5061 w zaporze W2019S. Adresy: `/mag/status|szukaj|kartoteka|modele|miniatura`, klucz konfiguracji `port_mag`.

**Synchronizacja (27.09.2026):** RĘCZNA, ale nie z jednej maszyny.
Przycisk „Synchronizuj" w MAG → `POST /mag/synchronizuj` → zlecenie
w `zlecenia_sync` → RM_BAZA na stacji z mostem pyta co 30 s
(`subiekt_kopia_zlecenia.py`) i przejmuje atomowo. **MONGO** (firma, szybki,
dobre łącze) i **M-OLD** (dom) biorą od razu, inne stacje po 2 min.
Z miniaturami = od nowa (zdjęcia dodane do istniejących kartotek).
Praca w RM_BAZA/Subiekcie w trakcie: bez przeszkód; na stacji
wykonującej zapytania do Subiekta +~0,1 s (wspólna kolejka mostu).

Plan: `PLAN_MAG.md`, sekcja 6b. Powiązane:
[[project_indeks_modeli_3d]], [[project_subiekt_most_stan_serwera]],
[[project_master_journal_delete]]
