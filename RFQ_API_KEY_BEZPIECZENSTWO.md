# Zabezpieczenie klucza rfq_api_key — plan

> **Status:** projekt, nic jeszcze nie zaimplementowane (zapisano 01.09.2026).
> Wynik rozmowy o bezpieczeństwie integracji RM_BAZA ↔ portal RM_RFQ.

## 1. Problem

`rfq_api_key` (nagłówek `X-API-Key`) uwierzytelnia `rm_sync_agent.py` wobec
**wszystkich** endpointów API portalu naraz — jeden token bez podziału na
odczyt/zapis. Uprawnia m.in. do:

- tworzenia nowych RFQ (`POST /api/rfq`)
- wysyłania zapytań i plików do kooperantów (`POST /api/rfq/{id}/items`)
- odczytu wszystkich danych ofertowych (`GET /api/sync/changes`, `/api/rfq/activity`)

Dziś ten klucz leży jawnym tekstem w `master.sqlite` → tabela `settings`
(`rfq_api_key`). To ten sam plik, do którego dostęp ma cała firma przez
`Y:\RM_BAZA\master.sqlite` — każdy, kto otworzy bazę SQLite (trywialne,
darmowe narzędzia), zobaczy klucz. Wyciek = ktokolwiek z zewnątrz może
podszyć się pod agenta: tworzyć RFQ, wysyłać zapytania do kooperantów,
czytać dane wycen.

Kierunek ruchu sieciowego jest zaprojektowany poprawnie (agent w sieci
firmowej sam inicjuje połączenia wychodzące HTTPS, portal nigdy nie ma
ścieżki z powrotem do `V:\`/`Y:\` — patrz nagłówek `rm_sync_agent.py`).
Problem jest wyłącznie w miejscu przechowywania klucza po stronie
firmowej, nie w architekturze samego kanału.

## 2. Gdzie dziś chodzi agent

Zweryfikowane 01.09.2026: **tylko na `W2019S`** (serwer), mimo że
`sync_agent_run.example.bat` ma gałąź `else` dającą lokalną ścieżkę
(`C:\RMPAK_CLIENT\RM_BAZY\RM_BAZA\master.sqlite`) dla dowolnego innego
hostname, a `sync_agent_install.ps1` zakłada trigger `-AtLogOn`
"w kontekście zalogowanego usera" — architektura dopuszcza wdrożenie na
zwykłej stacji roboczej, ale realnie tego nie ma. Przy planowaniu
migracji klucza uwzględnić tylko `W2019S`, chyba że do tego czasu ktoś
zainstaluje agenta gdzie indziej.

## 3. Plan naprawy

### Krok 1 — lokalny plik sekretów na W2019S

Zamiast `rfq_api_key` w `settings` (czytelnym z `Y:\` przez wszystkich),
trzymać klucz w pliku obok agenta na serwerze, np.:

```
C:\RMPAK_CLIENT\RM-BAZA-MANAGER\rfq_secrets.json
```

z uprawnieniami NTFS ograniczonymi do konta, na którym chodzi Task
Scheduler (nie "Everyone" / "Authenticated Users").

Zmiana w `rm_sync_agent.py`: dziś klucz czytany jest tak —

```python
self.api_key = self._setting('rfq_api_key', '')
```

Docelowo priorytet: najpierw lokalny plik sekretów (jeśli istnieje),
dopiero potem `settings` w `master.sqlite` jako fallback (zgodność
wsteczna na czas migracji — nie wywalać nagle działającej synchronizacji).

Format pliku, analogicznie do istniejącego `rfq_portal_url_server` /
`rfq_portal_url_local` (per-maszyna):

```json
{
  "rfq_api_key": "..."
}
```

### Krok 2 — usunięcie klucza z settings

Po potwierdzeniu, że agent czyta z pliku i synchronizacja działa
(kilka cykli bez błędu w `sync_agent.log`), usunąć wpis
`rfq_api_key` z tabeli `settings` w `master.sqlite`. Zostawienie go
tam "na wszelki wypadek" unieważnia cały sens migracji.

### Krok 3 — rotacja klucza

Wygenerować **nowy** klucz po stronie portalu i wpisać go już tylko
do chronionego pliku. Stary klucz mógł wyciec zanim został zabezpieczony
(przez cały okres, w którym leżał w `Y:\`), więc migracja bez rotacji
nie usuwa realnego ryzyka — tylko zamyka je na przyszłość.

### Krok 4 (opcjonalny, do ustalenia z administratorem portalu)

Sprawdzić, czy portal wspiera podział uprawnień tokenu (np. osobny
klucz tylko do odczytu `GET /api/sync/changes` dla ewentualnych
przyszłych integracji, które nie potrzebują prawa tworzenia RFQ).
Nie rozwiązuje problemu ekspozycji z kroku 1-3, ale ogranicza skutki
kolejnego wycieku w przyszłości.

## 4. Do rozstrzygnięcia przed implementacją

- Czy `sync_agent_run.bat` na `W2019S` (plik per-maszyna, w `.gitignore`,
  patrz `sync_agent_run.example.bat`) ma dostać nowy parametr wskazujący
  ścieżkę pliku sekretów, czy `rm_sync_agent.py` ma go szukać sam obok
  siebie (`Path(__file__).parent / 'rfq_secrets.json'`) bez zmian w `.bat`.
- Czy `rfq_secrets.json` też powinien trafić do `.gitignore` (żeby nikt
  przypadkiem nie scommitował klucza przy pracy na repo bezpośrednio
  na serwerze) — **tak, obowiązkowo**, dopisać przy implementacji.
