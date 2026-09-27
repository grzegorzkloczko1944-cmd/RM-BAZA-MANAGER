---
name: project_mag_katalog_lozysk
description: Katalog łożysk kulkowych w MAG (293 poz., Timken+FBJ, wymiary sprawdzone krzyżowo); kolumna Wymiary, filtr 6x/12x30/x30; pułapki SQLite d/D i 24 kontynuacje VBA
metadata:
  type: project
---

# Katalog łożysk kulkowych w MAG (28.09.2026)

Łożyska kulkowe zwykłe (z głębokim rowkiem): 293 oznaczenia bazowe —
6xx, 617/618/619, 160/161, 60/62/63/64, 622/623/630.

* Źródła: `katalog_lozysk/zbuduj_katalog.py` pobiera PDF-y Timken (główne)
  i FBJ (uzupełnienie), parsuje, **porównuje wymiary i przerywa przy różnicy**
  (160 wspólnych, 0 różnic). Wynik: `katalog_lozysk/lozyska_kulkowe.json`.
* RM_SERWER ładuje JSON przy starcie do `subiekt_kopia.sqlite`, tabela
  `lozyska` — tylko gdy plik się zmienił (`lozyska_meta.wersja`).
  ⚠ Na W2019S trzeba wgrać także katalog `katalog_lozysk/`.
* HTTP: `/mag/lozyska` (katalog + ile kartotek i stanu w Subiekcie),
  `szukaj`/`kartoteka` dostały `lozysko` i `wymiary`.
* MAG: kolumna **Wymiary** (między Stan i Cena), przycisk **„Katalog łożysk"**
  (okno `MAG_lozyska`, linie `'@l|`); klik w łożysko = szukanie w oknie MAG.
* Filtr wymiarów (user): `6x` = otwór, `12x30` = otwór+średnica, `12x30x8`,
  `x30` = średnica; litera x obowiązkowa, żeby `6004` zostało oznaczeniem.

## Rozpoznanie kartoteki
Tylko NA POCZĄTKU symbolu i tylko oznaczenia z katalogu (z aliasami):
`6004 ZZ`, `6001ZZ`, `SS 6008 2RS`, `16004ZZ`, `688ZZ` (alias 618/8),
`6004-2RS`. Numery rysunków (`013-100.03`, `2453-600.21`) odrzucane.
Aliasy handlowe: 618/8 = 688, 61804 = 6804, 619/5 = 695.

## ⚠ Pułapki
* **SQLite nie odróżnia wielkości liter w nazwach kolumn** — `d` i `D` to
  „duplicate column". Zewnętrzna średnica = kolumna `dz`.
* **Miniaturowe 618/x, 619/x: wersje ZZ/2RS bywają SZERSZE** (688 = 8x16x4,
  688ZZ = 8x16x5) — w danych `uwaga`, w oknie gwiazdka przy B.
* **VBA: max 24 kontynuacje ` _` na instrukcję — TAKŻE w liniach `'@|`**
  (komentarz z ` _` na końcu też się kontynuuje): „Too many line
  continuations" przy wklejaniu. `zloz_MAG.py` pilnuje tego sam.
* FBJ ma literówki (6219 Cr=10800, 16001 skopiowane z 6001, rozjechany 6052)
  i miesza jednostki (618xx w N, 64xx w kN) — skrypt to odsiewa.

Powiązane: [[project_mag_okno_przegladarka]], [[project_mag_kopia_subiekta_http]]
