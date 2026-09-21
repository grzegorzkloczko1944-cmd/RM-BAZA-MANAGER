---
name: project_bez_limitu_take_dokumenty
description: NIGDY Take(N) na kolekcjach dokumentow Sfery - limit odcina starsze dokumenty projektu i daje ciche bledy
metadata:
  type: project
---

W trybach mostu, ktore licza cokolwiek po dokumentach projektu (ZK/PW/RW),
**nie wolno ograniczac zapytania przez `Take(N)`**. Limit dziala PRZED
sprawdzeniem numeru projektu z Uwag, wiec baza oddaje N najnowszych
dokumentow JAKICHKOLWIEK, a dopiero petla odsiewa nasze. Starsze dokumenty
projektu po prostu znikaja — bez bledu, bez ostrzezenia.

**Zdarzylo sie DWA RAZY:**
- `Projekt.cs` — `Take(100)` na ZK → system zakladal DRUGIE ZK dla tego
  samego projektu (07.09.2026: „user zalozy projekt na projekcie i narobi
  sie balagan")
- `WydanieStan.cs` — `Take(400)` → `wydano` za male, `pozostalo` za duze,
  magazynier wydaje DRUGI RAZ (13.09.2026: „limit 400 to wielki blad")

RW jest tu najgorszy: to najczestszy dokument w firmie, wystawiany codziennie
na wszystkie projekty, wiec nawet 400 ostatnich to moze byc kilka tygodni.

**Why:** koszt nigdy nie lezal w liczbie dokumentow. Zmierzone: 0,08 s przez
staly most (bez limitu) vs ~17 s pierwszego wywolania — cala cena to
logowanie do Sfery, ktore staly most placi RAZ. Limit „optymalizowal" rzecz,
ktora nie byla waska gardlem, a placil za to poprawnoscia.

**How to apply:** widzisz `Take(` przy kolekcji dokumentow — usun. Jesli
kiedys realnie zaboli, filtruj PO PROJEKCIE, nie po liczbie najnowszych,
i **koniecznie po `ToList()`**: predykatu z `Znacznik.NumerProjektu`
ObjectQuery nie przetlumaczy na SQL i zwroci po cichu PUSTKE zamiast bledu
(`Projekt.cs:752`). Patrz [[project_uwagi_tytul_dokumentow]],
[[project_okno_wydania_rw]], [[feedback_most_rebuild_release]].
