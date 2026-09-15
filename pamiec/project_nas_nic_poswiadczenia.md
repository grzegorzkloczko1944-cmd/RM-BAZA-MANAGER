---
name: project_nas_nic_poswiadczenia
description: "NAS \\\\nic: poswiadczenie w Menedzerze MUSI byc jedno, jako Mongo (bez prefiksu nic\\); drugi zapis = blad 1219 i martwe V:/B:/Y:"
metadata: 
  node_type: memory
  type: project
  originSessionId: 58f9b752-f127-4b24-a83d-09f1cb22b23c
  modified: 2026-09-15T12:19:25.474Z
---

# ⛔ NIE RUSZAĆ WPISU `Domain:target=nic` W MENEDŻERZE POŚWIADCZEŃ ⛔
# ⛔ NIE DOPISYWAĆ DRUGIEGO JAKO `nic\mongo` ⛔
# ⛔ DWA RÓŻNE ZAPISY TEGO SAMEGO KONTA = BŁĄD 1219 ⛔

**Poprawny stan (15.09.2026, działa):**

```
cmdkey /list  ->  Target: Domain:target=nic
                  Type:   Domain Password
                  User:   Mongo          <-- BEZ prefiksu "nic\"

HKCU\Network  ->  V: \\nic\PROJEKTY    user=(puste)
                  B: \\nic\BIBLIOTEKA  user=(puste)
                  Y: \\nic\rysunki     user=(puste)
```

Mapowania mają **puste `user=`** — hasło biorą z tego jednego wpisu
w Menedżerze. Tak ma zostać.

**Why:** Windows porównuje nazwę użytkownika jako TEKST. `Mongo` ≠ `nic\mongo`,
mimo że na NAS-ie to jedno konto. Dwie takie tożsamości do serwera `\\nic`
w jednej sesji logowania → **błąd systemu 1219** („Wielokrotne połączenia
z serwerem […] przy użyciu więcej niż jednej nazwy użytkownika są
niedozwolone") i wszystkie dyski NAS-a padają naraz.

**Objaw w RM_BAZA:** program muli — każde zaznaczenie wiersza z rysunkiem
wisi ~3 s, bo szuka miniatury DWF na martwym `V:`/`B:` i czeka na timeout.
To NIE jest regresja kodu. Pierwsze, co sprawdzić: `Test-Path V:\`.

**How to apply:**
- ⚠️ **Hasło w `backup_nic.bat` (`nic\mongo`) NIE DZIAŁA z tej stacji** —
  próba mapowania nim daje błąd 5 („Odmowa dostępu"). Nie używać go do
  ratowania dysków, nie sugerować go userowi.
- ⚠️ **Skasowanie wpisu z Menedżera nie naprawia 1219** — żywa sesja SMB
  żyje dalej, dopóki jakiś proces trzyma na niej uchwyt (np. RM_BAZA
  odpalona z `Y:`). Bez admina nie widać, kto trzyma:
  `Get-SmbConnection`, `net view`, logi `SMBClient/*` → „Odmowa dostępu".
- **Naprawa 1219 = RESTART KOMPUTERA.** Sprawdzone: to jedyna pewna droga
  bez podniesionych uprawnień. `net use * /delete /y` nie wystarcza.
- Po restarcie mapowania **nie wrócą same**, jeśli `HKCU\Network` było
  czyszczone. Odtworzenie (user musi być zalogowany do `\\nic`, np. przez
  Eksplorator — wtedy `net use` widzi `\\nic\IPC$ OK`):
  ```powershell
  net use V: \\nic\PROJEKTY   /persistent:yes
  net use B: \\nic\BIBLIOTEKA /persistent:yes
  net use Y: \\nic\rysunki    /persistent:yes
  ```
  **Bez `/user:` i bez hasła** — to jest cała sztuczka.
- `backup_nic.bat` chodzi na **serwerze W2019S**, nie na stacji — osobna
  maszyna, osobne sesje SMB. **Nie może powodować 1219 tutaj.** Ta teoria
  (14.09) była błędna, nie wracać do niej. Patrz [[project_backup_nic_poza_gitem]].
- Kontekst liter: [[project_odciecie_od_Y]], [[project_udzial_ukryty_rm_serwer]].
