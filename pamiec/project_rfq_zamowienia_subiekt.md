---
name: project_rfq_zamowienia_subiekt
description: "Zakładka Subiekt w portalu RM_RFQ — archiwum, termin wiszenia, podgląd, kontakt; wdrożenie przez WinRM"
metadata: 
  node_type: memory
  type: project
  originSessionId: 834ab505-1a4e-4f62-bb02-1b4871507207
  modified: 2026-09-05T18:32:26.326Z
---

Zamówienia ZD z Subiekta w portalu RM_RFQ (zakładka **Subiekt**). Domknięte 05.09.2026, wszystko na produkcji.

## Gdzie co leży

- **Portal**: repo `NOW`, katalog `RM_RFQ/` (Flask). Szczegóły decyzji w `RM_RFQ/STATUS.md`.
- **Klient**: repo `RM-BAZA-MANAGER` — `subiekt_wyslij_zd.py` (okno wysyłki) + `rm_sync_agent.py` (HTTP do portalu).
- **Produkcja**: serwer W2019S `192.168.100.84`, `C:\Apps\NOW`, usługa NSSM `RM_RFQ`, port 5070, `rfq.rm-app.pl`.

## Wdrożenie (sprawdzona droga)

`git push` z lokalu → na serwerze `git pull --ff-only` + `Restart-Service RM_RFQ`. Dostęp: **WinRM z poświadczeniami** `%TEMP%\rmdwf_srvcred.xml` (DPAPI, tylko konto mongo na tej maszynie) — patrz `NOW/DOKUMENTACJA/DOSTEP_SERWER.md`.

```powershell
$cred = Import-Clixml "$env:TEMP\rmdwf_srvcred.xml"
$s = New-PSSession -ComputerName 192.168.100.84 -Credential $cred
Invoke-Command -Session $s -ScriptBlock { Set-Location C:\Apps\NOW; git pull --ff-only; Restart-Service RM_RFQ -Force }
```

⚠️ Baza produkcyjna portalu: `C:\Apps\NOW\RM_RFQ\rm_rfq.db` (mimo `data_dir` = `C:\Apps\RM_RFQ\Baza_rysunkow` w configu — to katalog PLIKÓW, nie bazy).
⚠️ Skrypty diagnostyczne na serwerze: `sys.stdout.reconfigure(encoding="utf-8")`, inaczej cp1250 wywala się na emoji.
⚠️ Portal chodzi na deweloperskim serwerze Flaska (`WARNING: development server`) — do zamiany na waitress, osobny temat.

## Co dodane 05.09.2026

| Funkcja | Sedno |
|---|---|
| Archiwizuj / Usuń + Archiwum (Subiekt) | wzorzec z `casting_*`; usunięcie kasuje kopię w portalu, **nie** ZD w Subiekcie |
| Termin wiszenia (`orders.expires_at`) | domyślnie **+14 dni** (`ORDER_DEFAULT_DAYS`), `_archive_expired_orders` przy wejściu na listę, bez schedulera |
| Podgląd zamówień | `preview_supplier_order` — **nie stempluje** `view_count`/`last_viewed_at`; wspólne `_order_items_for_view` |
| Podgląd zapytań — dwa bloki | zapytania u góry, zamówienia pod `hr.section-split`; każdy blok filtruje po EXISTS |
| Kontakt prowadzącego | `kontakt_prowadzacego()` w RM_BAZA czyta kadry z RM_MANAGER **cicho** (bez blokujących okien jak `_rfq_contact`) |

## Pułapki, które kosztowały czas

**Pole `<input type="date">` w tabeli.** Wpisane na stałe w każdy wiersz rozpycha kolumny (nazwa dostawcy łamie się na dwie linie). Atrybut `hidden` NIE wystarczy — przegrywa z regułą `display: inline`. Rozwiązanie: pole z zerowym rozmiarem + `position:absolute`, ikonka 📅 obok, `showPicker()` na klik. **Nie** `display:none` — wtedy `showPicker()` nie ma czego zakotwiczyć i kalendarz się nie otwiera.

**Termin trzeba odnawiać w trzech miejscach**, inaczej zamówienie wraca do archiwum od razu: przy ponownej wysyłce (`/api/orders`), przy `unarchive`, przy migracji (liczony od `created_at`).

**Maile dostawców: 13/113** — kreski w portalu to prawda o danych z RM_BAZA, nie usterka. Nie kombinować z automatycznym uzupełnianiem, user dopisuje ręcznie.

**Ponowna wysyłka tego samego ZD** aktualizuje istniejące zamówienie (`code` unikalny) — nie tworzy duplikatu.

**How to apply:** Zmiany w portalu commituj w repo NOW i wdrażaj przez WinRM (push → pull → restart). Klient (RM_BAZA) to osobne repo i osobny commit — działa lokalnie, nie na serwerze. Patrz [[project_subiekt_stan_05_09_2026]], [[project_subiekt_wysylka_zd]].
