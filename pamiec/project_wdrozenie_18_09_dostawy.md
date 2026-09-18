---
name: project_wdrozenie_18_09_dostawy
description: "Wystawienie 18.09.2026 — most 3b8ab7c (pz/PZ/symbole dostawcy) + serwer z operacjami dostaw; pulapka TrustedHosts po nazwie i jednorazowy wyscig na FV_KSEF"
metadata:
  node_type: memory
  type: project
---

Wystawione 18.09.2026 (po `git pull` `ce740d6..c29cb2a`): **most `3b8ab7c`**
i **serwer** z obiegiem przyjec dostaw.

- Most: binarka byla JUZ zbudowana na `most-server` (`73622e1`) — nie trzeba
  bylo `dotnet build`. Na serwerze stal `4aca0ff` z 16.09, bez `pz-utworz`
  i `symbole-dostawcy`. Skopiowane 5 plikow na `\W2019S\RM_SERWER$\MOST`.
- Serwer: `rm_serwer.py` + `rm_serwer_operacje.py` na `C:\Apps\RM_SERWER`,
  `Restart-Service RM_SERWER -Force`. Doszly tabele `dostawy`,
  `dostawy_pozycje` i 8 operacji (`ODCZYT`=166, `ZAPIS`=177).

**How to apply:**
- ⚠️ **TrustedHosts ma tylko IP `192.168.100.84`, NIE nazwe `W2019S`.**
  `New-PSSession -ComputerName W2019S` pada na „ServerNotTrusted" — laczyc
  sie po IP. Zob. [[project_rm_serwer_wdrozenie]].
- Kod serwera (`C:\Apps\RM_SERWER`) **nie jest widoczny przez udzial**
  `RM_SERWER$` — udzial wystawia tylko dane. Kod idzie wylacznie przez WinRM
  (`Copy-Item -ToSession`). Sam MOST lezy na udziale, wiec ide tam bez WinRM.
- ⚠️ **„migracje do dolozenia: 37" w `--sprawdz` to NIE zalegosc.**
  `--sprawdz` samo wola `zastosuj_migracje()` i liczy wykonane (idempotentne)
  instrukcje — 37 bedzie zawsze, takze na swiezo zmigrowanej bazie.
- ⚠️ Przy pierwszym restarcie watek `worker` wywalil sie raz na
  `duplicate column name: indeks` (`FV_KSEF.sqlite`) — **wyscig przy starcie,
  nie blad logiki**: guard w `zastosuj_migracje_ksef` jest poprawny, a schemat
  po fakcie jest kompletny (`indeks`/`dodatkowe`/`decyzja`, dane calo).
  Po powtornym restarcie **blad nie wrocil**. Gdyby wracal — szukac drugiego
  polaczenia migrujacego ta sama baze rownolegle.
- `rm_klient.py` na serwerze byl **starszy niz repo** (brak `DOMYSLNY_HOST`,
  `_ustawiony_recznie`, `_dociagnij_sekret`, `indeks_rysunkow`) — dociagniety
  18.09 do stanu `HEAD`. **Na serwerze nikt go nie importuje** (jedyne trafienia
  `rm_klient` to jego wlasny docstring UZYCIE), wiec podmiana nie wymagala
  restartu uslugi i nie moglaby niczego zepsuc. To kopia dla porzadku —
  modulu uzywaja STACJE, nie serwer.

Kopie do cofki (scratchpad sesji): most `MOST_BACKUP_4aca0ff`, serwer
`SERWER_BACKUP_17_09`.
