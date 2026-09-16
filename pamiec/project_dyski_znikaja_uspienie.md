---
name: project_dyski_znikaja_uspienie
description: "Znikające dyski V:/B:/Y: + dialog „Przywracanie połączeń sieciowych" błąd 85 = KOMPUTER USYPIA SIĘ po 30 min (System Idle); nie SMB, nie poświadczenia, nie backup_nic.bat"
metadata:
  type: project
---

# ⛔ ZNIKAJĄCE DYSKI SIECIOWE = UŚPIENIE KOMPUTERA, NIE SIEĆ ⛔

**16.09.2026.** Dyski `V:`/`B:`/`Y:` „znikały" kilka razy dziennie, przy
wybudzeniu wyskakiwał dialog *„Przywracanie połączeń sieciowych — Y: z
\\nic\rysunki: Nazwa lokalnego urządzenia jest już w użyciu"* (błąd **85**,
NIE 1219). Diagnostyka Windows zgłaszała „Brama domyślna jest niedostępna".

**Przyczyna (dowód z dziennika System, Kernel-Power Id 42):**

```
07:06  Przyczyna: System Idle
07:38  Przyczyna: System Idle
08:09  Przyczyna: System Idle
09:27  Przyczyna: System Idle
10:37  Przyczyna: System Idle
11:10  Przyczyna: System Idle
12:06  Przyczyna: System Idle
```

Plan „Zrównoważony", `STANDBYIDLE` AC = `0x708` = **1800 s = 30 minut**.
Pół godziny bez ruchu myszą → S3 → łącze pada („Stan łączności w trybie
wstrzymania: Disconnected") → sesje SMB do NAS-a giną. Po wybudzeniu Windows
odtwarza mapowania, `Y:` jest jeszcze zajęte przez martwą sesję → błąd 85.
Wpisy DNS 1014 (timeouty) pojawiają się dokładnie po wybudzeniach.

**Naprawa:** `powercfg /change standby-timeout-ac 0` (+ `hibernate-timeout-ac 0`).
Odwracalne w Ustawienia → System → Zasilanie → Ekran i uśpienie.

**How to apply — czego NIE robić przy tym objawie:**
- ⛔ **Nie szukać winnego w `backup_nic.bat`** — chodzi na serwerze W2019S,
  osobna maszyna, osobne sesje SMB. Sprawdzone dwa razy (15.09 i 16.09).
  Patrz [[project_backup_nic_poza_gitem]].
- ⛔ **Nie ruszać poświadczeń w Menedżerze** — to był INNY błąd (1219, 15.09),
  patrz [[project_nas_nic_poswiadczenia]]. Rozróżnienie: 1219 = „więcej niż
  jedna nazwa użytkownika", 85 = „nazwa urządzenia już w użyciu".
- ⛔ **Nie wyłączać oszczędzania energii karty sieciowej** jako „naprawy" —
  to hipoteza z 16.09 rano, obalona po odczycie dziennika. Może kiedyś warto,
  ale to nie ta awaria.
- **Pierwsze pytanie przy „znikających dyskach":**
  `Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; Id=42}`
  — jeśli są wpisy z godzin pracy, to uśpienie. Koniec diagnozy.
- `Test-Path V:\` zwraca True zaraz po wybudzeniu (mapowania persistent
  wracają same), więc „dyski działają" w chwili sprawdzania NIE znaczy, że
  problem zniknął. Patrzeć w historię, nie w stan.
