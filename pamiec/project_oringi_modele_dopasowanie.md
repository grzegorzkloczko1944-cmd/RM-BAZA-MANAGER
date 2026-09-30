---
name: project_oringi_modele_dopasowanie
description: "Oringi 30.09.2026: nomenklatura w Subiekcie w większości poprawiona (202 kartoteki OR-), zostały 3 wyjątki i 19 modeli .ipt do przemianowania na nowe symbole przed zasiewem indeksu 3D"
metadata:
  type: project
---

# Oringi: dopasowanie modeli 3D po poprawkach nomenklatury (30.09.2026)

Kontynuacja [[project_oringi_wymiarowka]] i
[[project_oringi_nomenklatura_do_poprawy]] — tamta lista 14 pozycji
została w większości zrealizowana przez usera w Subiekcie. Ta notatka
zastępuje jej sekcję „Otwarte pytania" i „Do zrobienia".

## Stan na 30.09.2026: 202 kartoteki `OR-`, 205 modeli `.ipt`

Katalog: `B:\Znormalizowane\Oringi` (205 `.ipt` + 205 miniatur `.png`,
`OldVersions` puste). Porównanie po WYMIARZE (średnica×przekrój, klucz
niezależny od zapisu materiału): **16 kartotek bez modelu 3D**, **19 plików
modeli osieroconych** (nadmiar to 3 pary duplikatów silikonowych).

## ⛔ Trzy kartoteki niezgodne z wzorcem — WYNIK (30.09.2026)

Wbrew wcześniejszemu zapisowi w tej notatce **symbol JEST zmienialny przez
most** — tryb `symbole` (`Symbole.cs`) istniał od dawna, tylko nie był
używany do tego celu i nie miał osłony na kartoteki użyte. User: „popraw
most, można zmieniać symbole o ile nie były użyte w dokumentach Subiekta".
Dodana osłona (`248cb2d`): `enc.PozycjeDokumentu.Count()` przed zapisem —
kartoteka użyta wraca jako błąd z liczbą dokumentów, nie jest zmieniana.

| symbol | problem | wynik |
|---|---|---|
| `OR-13x1,5 EPDM 70` | małe `x`, zbędna twardość, duplikuje `OR-13X1,5 EPDM` | **ZOSTAJE** — 3 dokumenty, most odmówił. `OR-13X1,5 EPDM` (1 dokument) jest kanoniczna od teraz; stara wisi jako martwy synonim. |
| `OR-11x2 FPM` | małe `x` | **ZMIENIONE na `OR-11X2 FPM`** — 0 dokumentów, zapis przeszedł, zweryfikowany niezależnym odczytem katalogu. |
| `OR-110X5.33 SIL` | kropka zamiast przecinka | **ZOSTAJE** — okazała się użyta (**1 dokument: PW 7/09/2026, 3 szt.**), zaskoczenie względem wcześniejszego założenia „zero ryzyka". Most odmówił; usuwanie PW tylko dla kosmetyki nazwy odrzucone (cofnęłoby realny stan magazynowy). |

**Lekcja z `OR-13x1,5 EPDM 70` i `OR-110X5.33 SIL`:** przy planowaniu
zmiany/usunięcia duplikatu sprawdzać `NaDokumentach`
(`PozycjeDokumentu.Count()`) ZAWSZE, nie tylko przy podejrzeniu — pozornie
„czysta" kartoteka (jedyna tego wymiaru, brak konkurenta) też może mieć
realne przyjęcie. Więcej użyć nie znaczy, że nazwa jest właściwa, ale to
Subiekt/most rozstrzyga, czy wolno ruszać, nie zgadywanie z boku.

Zobacz też: [[project_subiekt_scalanie_kartotek]] (scalanie NADAL nie
zmienia symboli — to inny mechanizm niż `symbole`).

## Modele do przemianowania — 8 jednoznacznych

Dopasowanie po wymiarze, materiał się zgadza:

| plik obecny | → nazwa docelowa (= symbol kartoteki) |
|---|---|
| `OR-1,6x2-70EPDM` | `OR-1,6X2 EPDM` |
| `OR-11x2-70NBR` | `OR-11X2 NBR` |
| `OR-13x1,5-70EPDM` | `OR-13x1,5 EPDM 70` *(kartoteka z literówką — patrz wyżej, model i tak musi na nią wskazywać, bo ta kartoteka żyje)* |
| `OR-20X2.5 EPDM` | `OR-20X2,5 EPDM` |
| `OR-58x3.5 80FPM` | `OR-58X3,5 FPM` |
| `OR-5X3,5NBR` | `OR-5X3,5 NBR` |
| `OR-7X2EPDM` | `OR-7X2 EPDM` |
| `OR-90X6` | `OR-90X6 SIL` |

Plus, po ustaleniu wyniku wyżej:
`OR-11x2` → `OR-11X2 FPM` (kartoteka już zmieniona, symbol pewny),
`OR-110X5.33 VMQ` → `OR-110X5.33 SIL` (⚠️ **kropka, NIE przecinek** —
kartoteka `OR-110X5.33 SIL` zostaje z kropką, most odmówił poprawy),
`OR-38X6 VMQ` → `OR-38X6 SIL` (kartoteka nowa, nie było jej 28.09).

I jeden bez zmiany wymiaru, tylko materiału: `OR-14X2,5` → `OR-14X2,5 FPM`.

## ⚠️ Trzy pary duplikatów silikonowych — do decyzji usera

Scalenie `S`/`Silikon` w Subiekcie do wspólnego `SIL` zostawiło DWA pliki
modelu na JEDNĄ kartotekę:

| kartoteka (jedna) | pliki (dwa) |
|---|---|
| `OR-38X4 SIL` | `OR-38X4 S.ipt` + `OR-38X4 Silikon.ipt` |
| `OR-40X3 SIL` | `OR-40X3 S.ipt` + `OR-40X3 Silikon.ipt` |
| `OR-92X6 SIL` | `OR-92X6 S.ipt` + `OR-92X6 Silikon.ipt` |

Nie rozstrzygnięte, który plik zostaje jako `<symbol>.ipt`, a co się dzieje
z drugim (podkatalog `_zbedne\` / kasowanie / user wybiera ręcznie) —
user przerwał to pytanie, wrócić przed ruszeniem plików w `B:`.

## Zakres poprawy modeli — NIE USTALONY

Trzy warianty czekają na decyzję: (a) tylko nazwa pliku + miniatura,
(b) pełne dopasowanie: nazwa + iProperty Part Number przez Inventor COM
+ miniatura, (c) wygenerować brakujące od nowa `generuj_modele.py`
zamiast przemianowywać. **Przed ruszeniem plików w `B:\Znormalizowane`
wymagana zgoda usera** — reguła [[feedback_biblioteka_pytaj_przed_hurtem]].

## Jak liczone (dla powtórzenia)

`sqlcmd`/most `katalog` daje pola: `Id, Symbol, Nazwa, Opis,
CenaEwidencyjna, Rodzaj, WKompletach, Skladnikow, NaDokumentach`
— **BRAK pola stanu magazynowego** w tym trybie (różni się od
`project_oringi_nomenklatura_do_poprawy`, gdzie stan brany z trybu
`stan`/`magazyn` osobno). Dopasowanie plik↔kartoteka po regexie
wymiaru: `(\d+(?:[.,]\d+)?)\s*[X/]\s*(\d+(?:[.,]\d+)?)` na symbolu
bez `OR-`, porównanie jako liczby (przecinek/kropka obojętne).

Zobacz też: [[project_oringi_wymiarowka]],
[[project_oringi_nomenklatura_do_poprawy]],
[[project_subiekt_scalanie_kartotek]],
[[feedback_biblioteka_pytaj_przed_hurtem]].
