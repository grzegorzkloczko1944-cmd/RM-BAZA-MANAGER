---
name: project-subiekt-staly-most
description: "Staly most NexoRecon.exe server — jedna sesja Sfery zamiast ~10s logowania na kazde klikniecie; zaimplementowany, branch most-server"
metadata: 
  node_type: memory
  type: project
  originSessionId: 84b92fee-687a-4149-a6e7-61f854134405
  modified: 2026-09-05T23:25:50.280Z
---

Przebudowa komunikacji RM_BAZA ↔ Subiekt nexo PRO: zamiast uruchamiac `NexoRecon.exe` na kazde klikniecie (~9-10 s na start procesu + logowanie do Sfery), dziala staly lokalny most `NexoRecon.exe server` — loguje sie raz i trzyma sesje. Plan: SUBIEKT_STALY_MOST_PLAN.md.

**Stan (2026-09-06): kroki A-J zrobione na branchu `most-server`.** Nie zmergowane do main.

Architektura:
- `NexoSession.cs` — cykl zycia polaczenia (Connect/Reconnect/CzyZywa)
- `CommandDispatcher.cs` — mapa tryb→handler, wspolna dla CLI i servera; `CzyZapis()` traktuje `progi` osobno (zapis tylko z `--plan`, sama flaga `--zapisz` nie wystarcza)
- `ServerHost.cs` — TcpListener 127.0.0.1:51273, framing 4B little-endian + UTF-8 JSON, watek per klient ale JEDEN worker dotykajacy Sfery (kolejka BlockingCollection); ping/status omijaja kolejke
- `Rozpoznanie.cs` — domyslny tryb raportu, CLI-only
- `subiekt_bridge.py` — klient: `call()`, `wywolaj()`, autostart mostu, handshake protokolu, fallback do starego CLI
- `bridge_test.py` — klient testowy, `python bridge_test.py bench`

Handlery (Stan.cs, Katalog.cs...) NIE byly zmieniane — server materializuje plik tymczasowy na `--out` i przechwytuje `Console.Out`.

Wyniki (baza demo M-OLD, 247 kartotek): kontrahenci 104 ms vs 14 368 ms CLI, magazyn 753 ms vs 14 218 ms, stan 296 ms vs 14 135 ms. Jedno logowanie na wszystkie komendy. Dane identyczne ze stara sciezka.

**Pulapka, ktora kosztowala debugowanie:** tryb server padal natychmiast (0xE0434352), gdy Python startowal go z `DETACHED_PROCESS` — bez konsoli `Console.OutputEncoding = Encoding.UTF8` rzuca IOException. Recznie z konsoli dzialalo bez zarzutu. Dlatego kazdy komunikat w ServerHost idzie przez `Powiedz()`, ktore zawsze pisze takze do logu `C:\RMPAK_CLIENT\subiekt_logi\bridge_RRRRMMDD.log`.

**Czego jeszcze nie zrobiono:** prawdziwe zapisy do bazy przez most nie sa przetestowane (tylko suche przebiegi `zapisz=False`) — to krok L. Benchmark z sekcji 33 trzeba powtorzyc w firmie na 3444 kartotekach. Powrot: `git checkout main` + kopia `NexoRecon.dll.dziala-20260906` w bin/Release.

**Why:** narzut startowy Sfery dominowal czas niemal kazdej operacji; po zmianie widac, ze realna praca to 100-800 ms, wiec cache (sekcja 20 planu) prawdopodobnie nie bedzie potrzebny.

**How to apply:** przy pracy nad mostem trzymac zasade retry READ vs WRITE — zapisy (zd, kartoteka, projekt, dostawcy, termin, zd-usun) NIGDY nie sa ponawiane automatycznie, wraca `UNKNOWN_COMMIT_STATE`. Powiazane: [[project_most_nexorecon_tryby]], [[feedback_git_push]].
