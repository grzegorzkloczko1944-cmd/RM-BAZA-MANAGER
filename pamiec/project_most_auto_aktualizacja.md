---
name: project_most_auto_aktualizacja
description: "Most aktualizuje się SAM przy starcie RM_BAZA + okienko; wcześniej milkło całkowicie przez BOM w wersja.json (utf-8-sig!)"
metadata:
  type: project
---

**Most Subiekta aktualizuje się automatycznie przy starcie RM_BAZA**
(16.09.2026). Wcześniej był tylko PROPONOWANY przyciskiem, a i to nie działało.

## ⛔ PUŁAPKA, KTÓRA UCISZYŁA CAŁY MECHANIZM: BOM w `wersja.json`

`_wersja_zrodla()` czytało plik jako `utf-8`. `wersja.json` wystawiany
z PowerShella przez `Set-Content -Encoding utf8` ma **BOM** (Windows
PowerShell 5.1 zawsze go dopisuje), więc:

```
json.load() → JSONDecodeError: Unexpected UTF-8 BOM
           → _wersja_zrodla() zwraca None
           → dostepna_nowsza() zwraca (False, '')
           → ŻADNEJ propozycji, ŻADNEGO przycisku „Pobierz most"
```

Most wystawiony na serwerze **nie docierał do nikogo** i nic o tym nie
mówiło. Objaw: „user odpalił nowy EXE i nie pociągnęło samo mostu".

**Naprawa:** `encoding="utf-8-sig"` w `_wersja_zrodla` (czyta oba warianty)
+ przepisanie plików na serwerze, stanowisku i w buildzie bez BOM.

⚠️ **Wystawiając most, zapisuj `wersja.json` Pythonem, nie PowerShellem.**
To ta sama pułapka, którą wcześniej złapał skrypt `dowiaz_biblioteki_wydruku.ps1`
— tam BOM był potrzebny, tu jest trucizną.

## Automat przy starcie

`rozgrzej_w_tle()` → `aktualizuj_przy_starcie()` w `subiekt_bridge.py`:
wykrywa nowszy most, pobiera go i pokazuje okienko z wersją i opisem zmian.

⚠️ **Tylko przy starcie, nie przy każdym sprawdzeniu.** Podmiana RESTARTUJE
most, więc w trakcie pracy przerwałaby komuś zapis ZK/ZD. Przy starcie nikt
nie ma otwartej operacji. Panel Subiekta dalej tylko PROPONUJE — zastrzeżenie
z `_proponuj_aktualizacje` zostaje w mocy.

⚠️ `wymuszone=True` omija bramkę dobową (`SPRAWDZAJ_NOWSZY_CO_S`, znacznik
`C:\RMPAK_CLIENT\.most_sprawdzony`). Przy starcie pytamy ZAWSZE — odczyt to
jeden mały plik wobec 9 s, które i tak kosztuje logowanie do Sfery.

⚠️ Ze ŹRÓDEŁ aktualizacja jest pomijana (`czy_z_binarki()`) — u budującego
źródłem prawdy jest repo, nie serwer.

**How to apply:**
- Okienko: GUI podstawia `subiekt_bridge.po_aktualizacji_mostu`; moduł nie zna
  Tk. Wywołanie idzie z WĄTKU TŁA, więc w RM_BAZA opakowane w `after(0, ...)`.
- Nic nie rzuca: brak serwera, zajęty plik czy inny protokół nie zatrzymują
  startu programu — zostaje stary most i propozycja w panelu.
- Test bez ruszania produkcji: skopiować `C:\iLogic\Subiekt\MOST` do `%TEMP%`,
  cofnąć `zbudowano` w kopii, podstawić `b._find_exe` i
  `b.DOCELOWY_KATALOG_MOSTU` na kopię (scratchpad `test_auto.py`).
- Powiązane: [[project_subiekt_most_stan_serwera]], [[feedback_most_w_gicie]].
