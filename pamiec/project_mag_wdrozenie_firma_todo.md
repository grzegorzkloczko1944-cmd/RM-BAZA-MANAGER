---
name: project_mag_wdrozenie_firma_todo
description: ⚠ DO ZROBIENIA 29.09.2026 w firmie — wdrożenie MAG na W2019S + MONGO wg WDROZENIE_MAG_FIRMA.md (restart RM_SERWER tylko za zgodą)
metadata:
  type: project
---

**Stan 28.09.2026 (koniec dnia):** MAG działa w domu (M-OLD). W firmie NIC
z tego nie ma — ani kopii Subiekta, ani HTTP :5061, ani katalogu łożysk.

Grzegorz zlecił wdrożenie agentowi na MONGO **29.09.2026**. Pełna instrukcja
krok po kroku: **`WDROZENIE_MAG_FIRMA.md`** w katalogu głównym repo.

Najważniejsze:
- 4 pliki na `C:\Apps\RM_SERWER` (WinRM po IP 192.168.100.84) — najpierw
  diff z repo i backup; `rm_serwer_config.json` NIE ruszać;
- zapora: port 5061;
- restart usługi RM_SERWER **tylko za zgodą** (zatrzymuje RM_BAZA wszystkim);
- sprawdzić `$env:COMPUTERNAME` MONGO vs `PREFEROWANE` w
  `subiekt_kopia_zlecenia.py`;
- MAG w Inventorze firmowym = pierwszy test na VBA7 64-bit.

Po wdrożeniu: zaktualizować tę notatkę (albo usunąć i zapisać przebieg).

Powiązane: [[project_mag_kopia_subiekta_http]], [[project_mag_katalog_lozysk]],
[[project_mag_okno_przegladarka]], [[project_rm_serwer_wdrozenie]]
