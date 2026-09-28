---
name: project_mag_wdrozenie_firma_wykonane
description: MAG wdrożony na W2019S 28.09.2026 — kroki 0-6 zrobione, zostaje synchronizacja kopii i makro w Inventorze; pułapki BOM i cp1250 w skryptach wdrożeniowych
metadata:
  type: project
---

Wdrożenie MAG w firmie (instrukcja [[project_mag_wdrozenie_firma_todo]] /
`WDROZENIE_MAG_FIRMA.md`) wykonane 28.09.2026 na MONGO, commit `369c57d`.

**Zrobione — kroki 0-6:**

- Krok 0: `COMPUTERNAME=MONGO` zgodne z `PREFEROWANE`, `server_dir=V:/`
  już poprawne (pułapka `V:/SERVER_PROJEKTY` z M-OLD tu nie wystąpiła).
- Krok 2: diff serwer vs repo sprzed MAG (`0682436`) **pusty** — potwierdzone
  SHA256. Zero poprawek spoza gita, w przeciwieństwie do
  [[project_mapowania_subiekta_stan_14_09]].
- Backup: `C:\Apps\RM_SERWER\backup_przed_MAG_20260928_1221`.
- Kroki 3-4: 5 plików wgranych, `py_compile` 0, reguła zapory
  „RM_MAG HTTP (port 5061)" założona.
- Krok 5: restart RM_SERWER o 12:22. **Przerwa kilka sekund** — stanowiska
  (DYREKTOR, Agnieszka, DAREK, Grzegorz Talaga) wróciły w tej samej minucie.
  Log: `Kopia Subiekta: …subiekt_kopia.sqlite`, `+ katalog łożysk: 293 pozycji`,
  `MAG: zlecenie nocne indeks3d`. Bez Tracebacków.
- Krok 6: `/mag/status` → `kartotek 0` (kopia pusta, normalne przed synchro),
  `/mag/lozyska?q=6004` → `6004 … 20x42x12`, źródło Timken.

**ZOSTAJE (nie robione tej sesji):**

- Krok 7 — pierwsza synchronizacja kopii Subiekta
  (`python subiekt_kopia_sync.py --miniatury-od-nowa`, ~5 min). Dopóki nie
  zrobiona, `kartotek` = 0 i MAG pokaże tylko katalog łożysk.
- Krok 8 — makro MAG w Inventorze firmowym. **Pierwszy test na VBA7 64-bit**
  (w domu był VBA 6). Miejsce modułu do ustalenia z Grzegorzem.
- Krok 9 — indeks modeli 3D (przycisk „Synchronizuj 3D"); serwer sam założył
  już zlecenie nocne.

**⚠️ Pułapki skryptów wdrożeniowych (kosztowały 3 fałszywe alarmy):**

1. `Out-File -Encoding utf8` w PS 5.1 **dokleja BOM** (`ef bb bf`). Pliki
   serwera BOM-u nie mają → `git diff` pokazywał różnicę w 1. linii i bramka
   krzyczała „poprawki spoza gita", choć kod był identyczny co do bajtu
   (różnica dokładnie 3 B). Referencje generuj `git show` **przez Bash**,
   nie przez PowerShell.
2. `(git show "sha:plik") -join "\`n"` w PowerShellu **gubi końcowy newline
   i psuje kodowanie** — sumy kontrolne wychodzą inne niż prawdziwe.
3. Plik `.ps1` z polskimi znakami/emoji: PS 5.1 czyta go w **cp1250**, bajty
   rozsypują się i **łamią cudzysłów** → „The string is missing the
   terminator". Ta sama rodzina co [[project_cp1250_emoji_print]]. Skrypty
   wdrożeniowe pisz w czystym ASCII, a `Select-String` po logu filtruj
   wzorcem bez polskich znaków (dlatego filtr „łożysk" nic nie zwrócił,
   mimo że wpis w logu był).

Zobacz też: [[project_rm_serwer_wdrozenie]], [[project_mag_kopia_subiekta_http]],
[[project_mag_indeks3d_zlecenie]], [[feedback_nie_zamykaj_okien_usera]].
