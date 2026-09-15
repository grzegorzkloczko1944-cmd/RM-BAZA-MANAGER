---
name: project_subiekt_puste_zlozenia_decyzje
description: "Projekt w Subiekcie — każde złożenie Z/ZZ bez składu idzie do okna decyzji (nie tylko biblioteczne); „Popraw drzewko\" to szary zapis, nie przycisk (09.09.2026)"
metadata: 
  node_type: memory
  type: project
  originSessionId: b4b4fbd4-107b-4ece-9328-8ca8b8a060fc
  modified: 2026-09-09T13:30:44.612Z
---

**Zmiana 09.09.2026 (commit po `adf6841`):** w `build_plan` KAŻDE złożenie
Z/ZZ bez składników trafia do `bib_bez_skladu` → okno „⛔ Decyzje"
(załóż bez składu / pomiń). Wcześniej tylko z flagą `dwf_biblioteka`;
złożenie z projektu bez składu było twardym błędem bez wyjścia z okna.
Pochodzenie w `plan["bez_skladu_z_biblioteki"]` — etykieta
`[biblioteka B:\]` vs `[projekt — brak w *_OUT.xlsx]`.

**Why:** user (3000 Testowy, `027-100.00Z` Zespół wrzeciona,
`dwf_biblioteka=0`) widział szary przycisk „⛔ Popraw drzewko (1)" i nie
mógł nic zrobić z okna; „Decyzje" znikał, bo lista bibliotecznych była
pusta. Decyzja jest jawna, więc reguła „pusty komplet nie przechodzi po
cichu" nadal trzyma.

**Anatomia okna (żeby nie tłumaczyć od nowa):**
- „⛔ Popraw drzewko (n)" / „⛔ Najpierw decyzje (n)" = przycisk **Zapisz do
  Subiekta** w stanie DISABLED z napisem-powodem (`_odswiez_stan_zapisu`).
  Nigdy nie był klikalny.
- „⛔ Decyzje (n)" = czerwony przycisk na górnej belce, `pack()` tylko gdy
  są nierozstrzygnięte; `pack_forget()` gdy nie ma. Jego brak = brak
  decyzji do podjęcia, nie awaria.
- Decyzje żyją tylko w pamięci okna (`_bib_decyzje`), nie są zapisywane.

**Pułapka „w domu było inaczej":** BOM projektu 89 na Y: nie zmienił się
od 08.09 13:57, a user w nocy widział 2 błędy (m.in. „Chwytak"), których
w danych na Y: NIE MA (jest tylko blacha „Ramię chwytaka"). Historia
(`Y:/RM_BAZA/subiekt_historia/notatka_89.json`) zna tylko `027-100.00Z`
z 08.09 19:21. Nocna praca szła na innej kopii danych — nie szukać tego
w kodzie. Patrz [[feedback_no_direct_db_edits]], [[project_subiekt_zk_komplety]].
