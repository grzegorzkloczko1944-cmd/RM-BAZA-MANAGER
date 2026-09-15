---
name: project_subiekt_uwagi_tytul
description: "Dokumenty Subiekta: UWAGI = '<numer> Projekt' + uwagi usera od 2. wiersza (drukuje sie), TYTUL = 'RM_BAZA <numer>' jako znacznik uprawniajacy do zmian"
metadata: 
  node_type: memory
  type: project
  originSessionId: b4b4fbd4-107b-4ece-9328-8ca8b8a060fc
  modified: 2026-09-11T00:00:00.000Z
---

Format obowiązujący od 11.09.2026 (**odwrócenie** wcześniejszej zasady
z 10.09 — wtedy było Uwagi=sam numer, Tytuł=opis):

```text
Uwagi:  2741 Projekt          ← 1. wiersz: numer + słowo dla człowieka
        pilne, do piątku      ← 2. wiersz i dalej: uwagi użytkownika
Tytuł:  RM_BAZA 2741          ← znacznik techniczny
```

- **Numer projektu** = pierwszy człon PIERWSZEGO WIERSZA Uwag (do spacji).
  Słowo „Projekt" jest dla człowieka, kod go nie czyta.
- **Rozpoznanie „nasz dokument"** = `RM_BAZA` w Tytule.

**Why:** **Uwagi się DRUKUJĄ, Tytuł nie** (wzorzec wydruku, sekcja
„Uwagi • Notes") — treść dla ludzi musi iść do Uwag. Wcześniej opis siedział
w Tytule i był niewidoczny na papierze. Znacznik wyprowadził się do Tytułu,
bo pierwszy wiersz Uwag zajął numer, a Tytułu nikt nie wypełnia ręcznie →
jego obecność jest wiarygodna. Sam numer w Uwagach NIE dowodzi, że dokument
jest nasz — człowiek zakładający ZK ręcznie też go wpisuje.

**How to apply:**
- **Nie powtarzaj reguły w nowym kodzie** — wołaj funkcje:
  Python `subiekt_zamowienia.py`: `zloz_uwagi()`, `numer_projektu_z_uwag()`,
  `uwagi_czlowieka()`, `tytul_dokumentu()`, `nasz_dokument()`, `sam_numer()`.
  C# `Znacznik.cs`: `Uwagi()`, `NumerProjektu()`, `UwagiCzlowieka()`,
  `Tytul()`, `Nasz()`.
- `sam_numer()` bo kalkulator trzyma pełną nazwę (`3500 dupal`), a okno
  projektu sam numer — funkcje przyjmują jedno i drugie.
- **Znacznik = uprawnienie.** Bez `RM_BAZA` w Tytule: dopisanie BOM-u do ZK
  odmawia, cofnięcie projektu POMIJA dokument, usunięcie pozycji z ZK
  odmawia. Blokada „projekt ma już ZK" działa niezależnie od znacznika.
- **BRAK kompatybilności wstecz — celowo.** Stare formaty (`Projekt 2741`,
  `RM_BAZA — PROJEKT 2741`, `… | PW: …`) nie są rozumiane. NIE dokładaj ich
  obsługi „na wszelki wypadek" — to właśnie ona rozjechała zapis z odczytem.
  Dokumenty przepisuje się trybem `migracja-uwagi` (`Migracja.cs`) wg
  `SUBIEKT_MIGRACJA_UWAGI_TYTUL.md`; migracja na demo zrobiona 10.09.2026,
  **na bazie firmowej jeszcze NIE**.
- Most (`Rw.cs`/`Pw.cs`): `UstawPole(dane, "Uwagi"|"Tytul", ...)` zawsze
  z ODCZYTEM KONTROLNYM — setter przy jawnej implementacji interfejsu
  potrafi po cichu nic nie zrobić.
