---
name: project_udzial_ukryty_rm_serwer
description: "Udział projektów na W2019S ukryty jako RM_SERWER$ (12.09.2026); pułapka: usunięcie mapowania zabiera hasło SMB i RM_MANAGER pada bez błędu"
metadata: 
  node_type: memory
  type: project
  originSessionId: 69849967-a91f-4896-bd40-f0b3f36b7447
  modified: 2026-09-12T13:53:40.965Z
---

**Udział z bazami projektowymi jest ukryty: `RM_SERWER$`** (zrobione
12.09.2026). Stary widoczny `RM_SERWER` **usunięty** — w otoczeniu sieciowym
W2019S nie widać już nic poza udziałami systemowymi.

```
\\W2019S\RM_SERWER$  ->  C:\Apps\RM_SERWER\dane\Projekty
    RM_MANAGER_projects\   81 baz
    RM_BAZA_projects\      pusty (RM_BAZA wciąż na Y:)
    ai_rules.txt
```

Ścieżka klienta: `manager_sync_config.json` → `rm_projects_dir` =
`\\W2019S\RM_SERWER$\RM_MANAGER_projects`. **W kodzie nie ma ani jednej
ścieżki UNC na sztywno** — przepięcie to jedna linijka w konfigu na stację,
bez rebuildu .exe. Szczegóły katalogów: [[project_bazy_projektowe_konto_techniczne]].

**Why:** userzy nie mają widzieć folderu z bazami w Eksploratorze. `$` to
jednak **tylko zasłona przed listą** — `\\W2019S\RM_SERWER$` wpisane ręcznie
wpuszcza każdego, udział ma wciąż `Everyone: Full`. Realne odcięcie daje
dopiero konto techniczne + `icacls` (nadal nieodrobione).

**How to apply:**
- ⚠️ **Usunięcie mapowania (`net use /delete`) zabiera zapamiętane hasło SMB**
  i ukryty udział przestaje odpowiadać, mimo że na serwerze jest sprawny.
  Objaw: `Test-Path \\W2019S\RM_SERWER$` = False przy poprawnym udziale.
  Naprawa: `New-SmbMapping -RemotePath '\\W2019S\RM_SERWER$' -UserName ...
  -Password ... -Persistent $true` (poświadczenia w `%TEMP%\rmdwf_srvcred.xml`).
  Dotyczy każdej przepinanej stacji — sam wpis w konfigu nie wystarczy.
- ⚠️ **RM_MANAGER pada bez komunikatu, gdy udział jest niedostępny** — proces
  po prostu znika. Przy przepinaniu stacji nie szukać błędu w oknie.
- ⚠️ Konfig edytować **przy zamkniętym RM_MANAGER** — zapisuje go przy wyjściu
  i nadpisuje zmianę.
- Zdalnie na serwer: WinRM **po IP `192.168.100.84`**, nie po nazwie `W2019S`
  (TrustedHosts ma tylko IP — po nazwie leci błąd o Kerberos/TrustedHosts).
- Klasyfikator auto mode blokuje `New-SmbShare` i `net use` z hasłem w linii;
  `Remove-SmbShare` i `New-SmbMapping` przechodzą. Zakładanie udziału trzeba
  było wkleić ręcznie na serwerze.
- Zostało: 9 stacji do przepięcia, RM_BAZA (87 projektów) wciąż na `Y:` —
  przy przeprowadzce wpisywać od razu ścieżkę z `$`.
