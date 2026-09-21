---
name: project_uwagi_tytul_dokumentow
description: "Numer projektu w 1. wierszu Uwag, znacznik RM_BAZA w Tytule — jedna reguła dla ZK/PW/RW/ZD"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5f190e79-13f0-43ff-a820-54ac4e6eb565
  modified: 2026-09-10T20:30:55.847Z
---

Wszystkie dokumenty w Subiekcie (ZK, PW, RW, ZD) oznaczane są tak samo (ustalone 2026-09-10):

```
Uwagi:  "2741 Projekt\npilne, do piątku"   ← 1. wiersz: numer + słowo "Projekt", niżej uwagi człowieka
Tytuł:  "RM_BAZA 2741"                      ← znacznik pochodzenia
```

- **Numer projektu** = pierwszy CZŁON pierwszego wiersza Uwag (do pierwszej spacji). Słowo „Projekt" za nim jest tylko dla człowieka czytającego wydruk — kod go nie czyta.
- **Uwagi człowieka** = wszystko od DRUGIEGO wiersza w dół (granica to koniec wiersza, bo uwagi bywają wielowyrazowe).
- **Rozpoznanie „nasz dokument"** = samo `RM_BAZA` w Tytule; numer w Tytule to tylko zapasowy ślad.

**Why:** Pole **Uwagi SIĘ DRUKUJE** (sekcja „Uwagi • Notes" na wzorcu Subiekta), a **Tytuł NIE** — sprawdzone na wydruku ZK. Dlatego treść dla ludzi idzie do Uwag, a techniczny znacznik do Tytułu. Wcześniej było odwrotnie (opis w Tytule) i opis był niewidoczny na papierze. Marker `RM_BAZA` musiał wyprowadzić się z Uwag, bo pierwszy wiersz zajął numer projektu.

Sam numer w Uwagach NIE dowodzi, że dokument jest nasz — użytkownik też go ręcznie wpisuje. Dlatego (wdrożone 2026-09-10) obowiązuje podział:

- **Szukanie/ostrzeganie** („projekt ma już ZK") — liczy się KAŻDY dokument z tym numerem, także ręczny: drugie ZK rozbija zapotrzebowanie niezależnie od tego, kto wystawił pierwsze.
- **Zmiana lub usunięcie** — wyłącznie dokumenty ze znacznikiem `RM_BAZA` w Tytule. Zabezpieczone: dopisywanie BOM-u (`Projekt.cs`), cofanie projektu (`ProjektCofnij.cs` — cudze raportuje jako `pominiete`, nie kasuje), usuwanie pozycji (`ZkPozUsun.cs`). `ZkIlosci.cs` tylko czyta, ale zwraca flagę `obce_zk`.

Pomocnicze: `Projekt.NaszeZk(dok)` i `Projekt.TylkoNasze(lista)` → `(nasze, obce)`.

**Wykrywanie ręcznych ZK** (`subiekt_projekt.zk_wymagajace_poprawy` / `zadania_z_zk_do_poprawy`): przy podglądzie zapisu BOM-u RM_BAZA zgłasza ZK, które mają numer projektu w Uwagach, ale nie mają znacznika w Tytule — z gotową instrukcją („wpisz RM_BAZA 3500”) i wpisem na wspólną listę „Do zrobienia”.

⚠️ **To pomoc, nie gwarancja.** Wykrywa tylko numer stojący NA POCZĄTKU Uwag (bo tak czyta go parser). ZK z Uwagami „Projekt 3500”, „proj. 3500” czy pustymi nie zostanie znalezione — i wtedy most spokojnie założy drugie ZK. Pełne wykrycie dubletu wymagałoby porównywania POZYCJI dokumentów, nie tekstu Uwag.

**How to apply:** Nigdy nie powtarzaj formatu w kodzie — używaj funkcji ze źródła:
- Python: `subiekt_zamowienia.zloz_uwagi()`, `numer_projektu_z_uwag()`, `uwagi_czlowieka()`, `tytul_dokumentu()`, `nasz_dokument()`
- C#: `Znacznik.cs` — `Uwagi()`, `NumerProjektu()`, `Tytul()`, `Nasz()`, `PasujeProjekt()`

⚠️ **Bez kompatybilności wstecz** — stare formaty („Projekt 2741", „RM_BAZA — PROJEKT 2741") nie są rozumiane. Nie dodawaj obsługi starych formatów: to właśnie ona sprawiła, że zapis i odczyt patrzyły na dwa różne stringi.

**Migracja wykonana 2026-09-10** na bazie `Nexo_RMPRODUKCJA`: przepisane 3 dokumenty projektu 3500 (ZK 1/CENTRALA/2026, PW 2/MASTER/2026, RW 1/MASTER/2026), zweryfikowane odczytem. Pozostałych 29 z 32 nie ruszano — nie mają numeru projektu (inwentaryzacja, czyszczenie demo, puste WZ). Do powtórki służy tryb mostu `migracja-uwagi` (`Migracja.cs`) — bierze **jawną listę** dokumentów w planie JSON, bo rozpoznanie starego formatu było niejednoznaczne; `--zapisz` dopiero po suchym przebiegu.

Uwaga: Tytuł dokumentu **nie bywa pusty** — Subiekt trzyma tam domyślnie nazwę typu („Przychód wewnętrzny"). Rozpoznanie po `MARKER` działa mimo to, ale nadpisanie Tytułu kasuje tę etykietę (świadoma decyzja użytkownika).

Powiązane: [[project_rmpak_produkcja_pw_rw]], [[feedback_most_rebuild_release]], [[project_zd_portal_rfq]]
