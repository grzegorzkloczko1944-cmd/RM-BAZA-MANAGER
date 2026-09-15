---
name: project_master_watchdog_ro
description: "Watchdog master.sqlite degradował sesję do READ-ONLY — objawy wszędzie, przyczyna jedna (07.09.2026)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 834ab505-1a4e-4f62-bb02-1b4871507207
  modified: 2026-09-07T11:05:15.141Z
---

**Naprawione 07.09.2026, commit `2cf4473`.** Najgroźniejszy błąd, jaki dotąd
znalazłem w tym projekcie: objawiał się w wielu miejscach naraz, a przyczyna była
jedna i całkowicie niewidoczna.

## Mechanizm

`database_manager.ensure_master_alive()` przy odpowiedzi `database is locked` —
a na dysku sieciowym wystarczy chwilowy skok opóźnienia — zamykał połączenie
i otwierał je na nowo przez `connect_master()`, czyli **zawsze jako
`mode=ro&immutable=1`**. Od tej sekundy w sesji ADMIN-a:

- **każdy zapis cicho padał** — SQLite nie zgłasza błędu przy `commit()` na RO
- **`immutable=1` dawał nieświeże odczyty** — stąd „raz chodzi szybko, raz wolno"

Naprawa: `db_manager` pamięta tryb (`master_wants_rw`) i po zerwaniu odtwarza
**ten sam**, zamiast degradować do odczytu.

## Dlaczego trwało pół dnia

Objawy nie wskazywały na przyczynę i wyglądały na trzy osobne błędy:

| Objaw | Co naprawdę |
|---|---|
| „nie mogę zrobić projektu aktywnym" | zapis na połączeniu RO |
| „sequence item 0: expected str instance, NoneType found" | ten sam lock w `colnames()` → pusty zbiór → `pick_col` daje `None` |
| „raz szybko, raz wolno" | `immutable=1` po degradacji |

**Diagnostyka, która wreszcie zadziałała** — zamiast zgadywania:
- porównanie zapisu **z zewnątrz** (świeże połączenie RW, transakcja cofana)
  z zapisem **z aplikacji**: z zewnątrz przechodził, z aplikacji nie → wina
  połączenia, nie pliku ani uprawnień
- `faulthandler.dump_traceback_later(15, repeat=True)` w skrypcie startowym
  (`C:\RMPAK_CLIENT\subiekt_logi\_start_z_faulthandler.py`) — pokazuje, na czym
  stoi wątek GUI przy zawieszeniu
- uruchamianie przez `cmd /k ... | tee` zamiast `pythonw` — bez konsoli błędy
  z wątków giną bez śladu

## ⚠️ Wzorce, które to umożliwiły

- **Cichy `except: pass` wokół całej logiki** — w RM_MANAGER kolory wierszy nigdy
  się nie przypinały (funkcja z innego systemu statusów), i nikt tego nie widział.
- **Funkcja awaryjnie zwracająca pustą wartość zamiast rzucać** — `colnames()`
  przy błędzie dawał pusty zbiór, co prowadziło do bezsensownego SQL-a zamiast
  czytelnego „baza zajęta".
- **UPDATE bez sprawdzenia `rowcount`** — SQLite nie uznaje za błąd UPDATE-u,
  który nic nie zmienił. Przy zapisach krytycznych: `rowcount` + **odczyt
  kontrolny po commicie**.

## Przy okazji (to samo commit)

- Okna list projektów: pozycja liczona **po** zbudowaniu treści (`winfo_width()`
  przed nią zwraca 1) + `lift`/`focus_force`; pasek przycisków 60 → 92 px, bo
  `pack_propagate(False)` obcinał legendę.
- **RM_MANAGER, kolory wierszy**: status i aktywność szły oba przez `foreground`,
  więc „nieaktywny" i „wstrzymany" miały ten sam szary. Rozdzielone jak w RM_BAZA
  — **status na TLE, nieaktywność na kolorze TEKSTU**, a tag `inactive` doklejany
  zawsze, nie tylko „gdy nie ma innych tagów".

**How to apply:** Przy każdym „zapisało się, ale nie widać efektu" w RM_BAZA
najpierw sprawdzić, czy `master_con` nie jest RO — próba `BEGIN IMMEDIATE`
na świeżym połączeniu z zewnątrz rozstrzyga w sekundę. Patrz
[[reference_db_paths]], [[feedback_start_rm_baza]].
