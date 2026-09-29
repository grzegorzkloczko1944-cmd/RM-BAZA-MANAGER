---
name: project_backupy_tylko_przy_starcie
description: "NIEAKTUALNE od przeniesienia kopii na RM_SERWER — kopie baz robi serwer codziennie sam (sprawdza co godzinę); dawny problem „kopie tylko przy starcie programu” (14.09.2026) rozwiązany"
metadata:
  type: project
---

**Stan (sprawdzone 29.09.2026): kopie robi RM_SERWER, codziennie, sam.**

`rm_serwer.py`, `_sprzatanie()` → co godzinę `_trzeba_backupu()` → `_backup()`:
* **bazy serwera**: `master.sqlite` i `subiekt_mapowania.sqlite` i `FV_KSEF.sqlite`
  → `backup_RM_BAZA\master`, `rm_manager.sqlite` → `backup_RM_MANAGER\master`
  (`sqlite3.backup`, rotacja `backup_ile`, domyślnie 20 kopii);
* **pliki projektów** obu programów (`_backup_projektow`, rotacja `backup_dni`,
  domyślnie 30 dni) — log pisze je tylko, gdy powstała nowa kopia.
* „Czy dziś już była kopia” czyta z KATALOGU, nie z pamięci procesu — restart
  usługi nie daje ani podwójnych kopii, ani dnia bez kopii.

Log domowego serwera: `Backup: master_20260928_002706…`, `…_20260929_004956…`
— 4 bazy dziennie, po 17 kopii każdej. Kopii plików projektów w logu wtedy
nie było (zapis tylko przy zmianie) — potwierdzić w katalogu, gdyby padło
pytanie.

W klientach wywołanie przy starcie USUNIĘTE (w `RM_BAZA_v15_MAG_STATS_ORG.py`
i `rm_manager_gui.py` został komentarz „Tutaj stało `…run_backup_in_background`”);
ręczny backup z menu RM_BAZA działa nadal.

## Historia (dlaczego to zmieniono)

14.09.2026: backup w RM_BAZA i RM_MANAGER odpalał się **tylko raz, przy starcie
programu** — aplikacja chodząca tydzień bez restartu nie robiła kopii ani razu
(14.09: RM_BAZA 0 kopii przy pięciu pracujących stacjach). User wtedy zdecydował
„zostaje jak jest”, a rozwiązaniem okazało się przeniesienie kopii na serwer,
który chodzi bez przerwy jako usługa. Backup przy zwalnianiu locka
(`backup_on_release`) na produkcji nadal WYŁĄCZONY — już niepotrzebny.

Patrz [[project_audyt_min_po_przenosinach]], [[project_rm_serwer_etap25_domkniecie]].
