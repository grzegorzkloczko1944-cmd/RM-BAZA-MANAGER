# Backup danych RM_SERWER na drugą maszynę (`\\nic`)

**Stan: skrypt napisany i wgrany na serwer, NIEURUCHOMIONY i BEZ harmonogramu.**
Do dokończenia. Zapisane 12.09.2026.

---

## Po co

Cały system leży na **jednym dysku C: serwera W2019S**: master RM_BAZA,
`rm_manager.sqlite`, bazy projektów obu programów, mapowania Subiekta, KSeF.

RM_SERWER robi własne kopie baz (spójne, przez SQLite Online Backup API), ale
odkłada je **w tym samym miejscu** — `C:\Apps\RM_SERWER\dane\Projekty\backup_*`.
Padnięcie dysku zabiera oryginał i kopie naraz. Ten skrypt wynosi dane poza serwer.

## Co jest zrobione

Plik `C:\Apps\RM_SERWER\backup_nic.bat` — wgrany na serwer (5229 B), **nie
uruchomiony ani razu**. Źródło: `rm_serwer_backup_nic.bat` w scratchpadzie sesji
(do przeniesienia do repo przy dokańczaniu).

## Co zostało do zrobienia

1. **Uruchomić ręcznie** i sprawdzić log `C:\Apps\RM_SERWER\logi\backup_nic.log`
   — czy `net use` przechodzi z sesji usługi i ile trwa pierwszy przebieg.
2. **Sprawdzić miejsce na `\\nic\PROJEKTY`** — skrypt liczy na ~150 MB, ale
   pierwszy przebieg z `/MAXAGE:30` może ściągnąć więcej kopii baz.
3. **Zarejestrować w Harmonogramie zadań** — codziennie w nocy, **po 01:00**
   (RM_SERWER robi swój wewnętrzny backup ok. 00:57, więc kopiujemy już świeże
   pliki). Konto: `.\mongo`, „uruchom niezależnie od tego, czy użytkownik jest
   zalogowany".
4. **Sprawdzić po pierwszej nocy** plik `_ostatni_udany_backup.txt` w katalogu
   docelowym — to znacznik dla monitoringu.

## Decyzje wbudowane w skrypt (żeby nie przemyśliwać od nowa)

**Żywe bazy `.sqlite` NIE są kopiowane bezpośrednio.** `robocopy` złapałby je
w połowie transakcji i kopia byłaby uszkodzona. Zamiast nich lecą spójne kopie
z `backup_*\master`, które serwer robi przez Online Backup API — jedyny
bezpieczny sposób na kopię działającej bazy SQLite.

**`backup_RM_MANAGER\projects` (2,35 GB) pomijamy.** To archiwum kopii plików
projektów — backup backupów. Żywe pliki i tak kopiujemy. Dzięki temu na `\\nic`
ląduje ~150 MB zamiast 2,7 GB.

**Dostęp do `\\nic` przez UNC, nie literę dysku.** Wzorzec zerżnięty
z `C:\Apps\NOW\RM_DWF\_service_launcher.bat`: litery kolidują między usługami
startującymi równocześnie (`System error 85 "device name already in use"`),
UNC jest per-share i nie zajmuje globalnego zasobu. Konto `nic\mongo`,
`net use` z retry 10×3 s — po restarcie sieć bywa jeszcze nieaktywna.

**`/MIR` na plikach projektów, BEZ `/MIR` na kopiach baz.** Projekty mają być
lustrem (skasowany projekt znika też z kopii, inaczej katalog rośnie bez końca).
Kopie baz przeciwnie — rotacja na serwerze zostawia 20 sztuk, a na `\\nic` mają
przeżyć także starsze, bo to jedyne miejsce odporne na padnięcie C:.

**`/FFT`** — czas z dokładnością 2 s. Bez tego SMB przepisuje wszystko co noc
przez zaokrąglenia timestampów. **`/R:2 /W:5`** — domyślny milion prób potrafi
zawiesić zadanie na dobę, gdy plik jest zajęty.

**Kod wyjścia robocopy 0–7 to sukces** (bity: 1 skopiowano, 2 dodatkowe,
4 niezgodne), dopiero 8+ to błąd. Skrypt to rozróżnia — inaczej każdy udany
backup raportowałby awarię.

## Czego ten backup NIE zastępuje

Kopiuje dane, nie stan usługi. Odtworzenie serwera od zera wymaga jeszcze
Pythona 3.12, NSSM i rejestracji usługi — opis w `PLAN_RM_SERWER.md`.
Kod i konfiguracja lecą do `BACKUP_RM_SERWER\aplikacja`, więc nie trzeba ich
szukać w gicie.
