---
name: project_wdrozenie_firma_04_10_2026
description: WDROŻENIE W FIRMIE — jedna lista kroków dla agenta po pracy w domu 02–04.10.2026 (git pull, restart RM_SERWER, agent RFQ, most, .exe RM_BAZA i RM_MANAGER, testy po wdrożeniu); każdy krok: sprawdź → zrób → potwierdź
metadata:
  type: project
---

Spisane 04.10.2026 na M-OLD (dom). Wszystko jest na `origin/main`
(ostatni commit tej paczki: `fb3cc9f` + ta notatka). Dotyczy firmy: serwer
**W2019S** (RM_SERWER, agent RFQ, most) i stanowiska userów (.exe).

⛔ **Zasady, zanim cokolwiek zrobisz** ([[INDEKS_zasady]]):
- restartu RM_SERWER, zamknięcia RM_BAZA / RM_MANAGER u kogokolwiek —
  **najpierw zapytaj usera** (ktoś może mieć otwarty lock i niezapisaną pracę),
- nie pushuj bez zgody; `backup_nic.bat` zostaje poza gitem,
- każdy krok: **sprawdź, czy już nie zrobiony** (część mogła pójść w innej
  sesji — most `ac072b0` został wystawiony 03.10 14:11, patrz krok 4).

## Krok 1 — kod na W2019S

```
cd <repo RM-BAZA-MANAGER na W2019S>
git status                       # lokalne zmiany? NIE nadpisuj — pokaż userowi
git log -1 --oneline             # stan przed
git pull origin main
git log -1 --oneline             # ma być fb3cc9f albo nowszy
```

## Krok 2 — restart RM_SERWER (zapytaj usera o porę)

Serwer przy starcie sam robi migracje. Bez restartu NIE działa:
- **saldo godzin w Kadrach** — brak tabeli `employee_godziny_rozliczenia`
  (okno pokaże puste saldo, zapis odpracowania się wywali),
- ostrzeżenie przed 2× wysyłką ZD z adresem (`zd-wyslane-ostatnia`),
  powtórka wysyłki przestawia datę zamówienia (`zd-zamowione-dodaj-zachowaj`),
- przyspieszenia RM_MANAGER (odczyty zbiorcze `rmm-employee-vacation-base-
  wszystkie`, `…-quota-wszystkie`, `rmm-carryover-wszystkie`,
  `statusy-projektow-wszystkie`) — działa po staremu, wolniej.

Potwierdzenie po restarcie (z repo, Python):
```python
import rm_manager as rmm
print(rmm.get_godziny_rozliczenia())            # [] — nie wyjątek
print(len(rmm._master().master_read("statusy-projektow-wszystkie")))
```
oraz w `logi/rm_serwer_YYYYMMDD.log` linie CREATE TABLE/INDEX bez błędów.

## Krok 3 — agent RFQ (kolumna WYCENA)

Bez tego WYCENA w firmie = „⚠ brak danych" ([[project_stan_prac_02_10_2026]]):
1. skopiuj `sync_agent_run.example.bat` → `sync_agent_run.bat` (lokalny jest
   w .gitignore; stary ma `--master`, którego agent już nie przyjmuje),
2. `C:\RMPAK_CLIENT\sync_config.json` musi mieć `"rm_serwer": {"host", "port": 5060}`,
3. po minucie `sync_agent.log`: „Kooperanci wyslani / Wyniki pobrane", bez błędu.

## Krok 4 — most Subiekta (NexoRecon)

Sprawdź, co jest wystawione: `git show origin/most-server:most-dist/wersja.json`
(04.10 rano: `sha: ac072b0`, zbudowano 2026-10-03 14:11). Potem:
```
git diff <sha z wersja.json>..HEAD --stat -- subiekt_sfera/NexoRecon/
```
Od `ac072b0` doszły `KartotekaEdytuj.cs`, `Katalog.cs` (położenie R/P
w Edytorze kartotek, łożysko 688 — sesja `ab54606`/`1e7cf58`). Jeśli diff
pusty — krok pomiń. Jeśli nie: procedura z [[feedback_most_w_gicie]]
(`dotnet build -c Release -nowarn:MSB3277` → MOST_STAGING + `wersja.json`
→ smoke test → `\\W2019S\RM_SERWER$\MOST` → `most-dist` na `most-server`,
push obu gałęzi — **za zgodą**). Pułapka buildu: [[project_build_release_stimulsoft_hardlink]].

Stanowiska dociągają most same (panel Subiekt → „Sprawdź i zaktualizuj most").

## Krok 5 — .exe RM_BAZA i RM_MANAGER

Przebudować i rozesłać oba ([[INDEKS_build]], bramka wersji
[[project_client_version_gate]], pułapki [[project_build_leniwe_importy]],
[[project_spec_startfile_rm_kod]]). Co userzy dostaną:
- **RM_BAZA**: kolumna SUBIEKT po projekcie „(stan potrzeba/stan)", leniwie
  12 s po wyborze projektu, sama po wysyłce ZD; ostrzeżenie przed 2× ZD;
  okno szczegółów z odnośnikami ZK/ZD; WYCENA sama śledzi agenta RFQ;
  okna nie skaczą (pilnowanie rozmiaru i pozycji); miniatura nie wchodzi
  na filtry ([[project_zd_powtorka_i_kolumna_subiekt]]),
- **RM_MANAGER**: saldo godzin w Kadrach ([[project_urlopy_saldo_godzin]]),
  szybkie Kadry, lista projektów, Multi-projekt, oś czasu, plan serwisantów
  ([[project_rm_manager_czytanie_w_pakiecie]]).

## Krok 6 — testy po wdrożeniu (z userem)

- [ ] RM_MANAGER → Kadry otwiera się od razu; Rozliczenie i Pula < 1 s
- [ ] Kadry: nowa nieobecność „½ rano" → w kalendarzu dolna połowa kratki;
      Rozliczenie → ⏱ Saldo godzin pokazuje 4 h
- [ ] plan serwisantów przelicza się w ułamku sekundy (było „długie sekundy")
- [ ] RM_BAZA: po ~12 s od wyboru projektu kolumna SUBIEKT wypełnia się sama
- [ ] WYCENA bez „⚠ brak danych" (agent RFQ żyje)
- [ ] pierwszy lock na **2637** → okno „Powiązania z Subiektem — naprawa",
      kliknąć „Tak" ([[project_powiazania_kolizja_ilosci]])

## Nie sprawdzone realnym zapisem (uważać przy pierwszym użyciu)

- zakładanie ZK po poprawce daty wystawienia (PW/RW sprawdzone na demo:
  PW 11 / RW 28),
- cena i usuwanie pozycji z ZK z Przeglądu dokumentów,
- klik w numer ZK/ZD w oknie szczegółów (user zgłaszał „nie otwiera";
  po poprawce pokaże błąd w okienku zamiast milczeć).
