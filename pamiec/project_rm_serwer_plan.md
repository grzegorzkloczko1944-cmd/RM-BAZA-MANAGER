---
name: project_rm_serwer_plan
description: "PLAN_RM_SERWER.md — serwer RM_BAZA w 3 etapach (master → projekty+locki checkout/checkin → pliki, Y: znika); v8 z 11.09.2026, etap 1 gotowy do kodowania; decyzje po 4 recenzjach"
metadata: 
  node_type: memory
  type: project
  originSessionId: b4b4fbd4-107b-4ece-9328-8ca8b8a060fc
  modified: 2026-09-11T15:32:27.263Z
---

Plan wykonawczy: **`PLAN_RM_SERWER.md`** w repo (wcześniej `PLAN_SERWER_LOCKI_MASTER.md`
→ `PLAN_SERWER_MASTER.md`; historia w gicie `c6130ff`…`9fd3cd3`). Wersja 8, 11.09.2026.

**Cel docelowy (decyzja użytkownika):** RM_BAZA bez dysków sieciowych. Trzy etapy,
każdy z własnym cutoverem:

1. **master.sqlite przez serwer** — opisany w pełni, **do kodowania jako pierwszy**
   (3–4 dni). Leczy przyczynę awarii z 11.09 ([[project_master_stuck_transaction]]).
2. **projekty + locki przez serwer** — `checkout`/`checkin`; **kopia lokalna zostaje,
   244 zapytania SQL zostają, reguły locków 1:1** (jeden lock/user, stale 300 s,
   heartbeat 30 s, force, bulk dla RM_MANAGER). Zmienia się tylko transport.
3. **pliki (rysunki, biblioteka, chat, bramka wersji) przez serwer** — do wyceny;
   skany po B:/V: wymagają indeksu po stronie serwera.

**Why:** dziesięć procesów otwierających jeden SQLite po SMB to przyczyna, nie
objaw; serwer z jednym wątkiem zapisu usuwa ją. Etap 2 NIE przebudowuje warstwy
danych (wersje 2–4 planu próbowały nowego systemu lease/epoch — odrzucone jako
refaktor działającego elementu bez bólu; potem wrócił jako *transport*, gdy celem
stało się zniknięcie Y:).

**How to apply:**
- Twarde zasady etapu 1: klient **nie otwiera** mastera wcale (także read-only —
  czytelnik trzyma SHARED); **brak fallbacku per-klient** (przy awarii zapisy
  zablokowane, praca na projekcie trwa); nazwane operacje, nigdy SQL; `request_id`
  + `_server_request_log` **w masterze** (jedna transakcja); HMAC z kanonicznym
  JSON (nie chroni przed replayem — to robi request_log); master na **lokalnym**
  `D:` maszyny `nic`; weryfikacja `handle.exe` na `nic`, nie „Otwarte pliki";
  **cutover** wszystkich naraz, nie pilot; rollback = kopia `D:`→`Y:` +
  `integrity_check`, NIE restore sprzed cutoveru.
- Zewnętrzni pisarze mastera do objęcia w etapie 1: RM_MANAGER (`sync_to_master`),
  `backup_manager`; czytelnicy → snapshot. Drugi SQLite wielu pisarzy po SMB:
  `subiekt_mapowania.sqlite` — do rozstrzygnięcia (§16 planu).
- Wzorzec serwera i klienta: most Subiekta (`ServerHost.cs`, `subiekt_bridge.py`),
  TCP + 4 bajty długości + JSON.
- Powiązane: [[project_rm_baza_db_model_decision]], [[project_master_journal_delete]],
  [[project_master_con_retire_crash]], [[feedback_most_w_gicie]].
