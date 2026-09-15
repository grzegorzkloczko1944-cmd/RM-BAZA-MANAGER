---
name: project_subiekt_symbol_spacja
description: Symbole kartotek ze spacja wiodaca w bazie Subiekta - most ich nie widzi, bo wszedzie trimuje
metadata:
  type: project
---

W bazie Subiekta sa kartoteki, ktorych Symbol ma **spacje wiodaca** (np.
`" 35/35/1,5"`, Id 101833, RURA KWADRATOWA 35X35X1,5). W oknie kartoteki
tego nie widac (padding kontrolki), ale na **liscie Asortymentu widac
wciecie** wzgledem sasiednich wierszy - to najpewniejszy sposob wykrycia.

Most NexoRecon trimuje symbole niemal wszedzie, co daje sprzeczne objawy:

- `Rw.cs` - robi `.Trim()` na symbolu z planu, potem `WyszukajPoSymbolu`
  dokladnie => **"brak kartoteki"**, pozycja nie schodzi ze stanu.
- `Stan.cs` - zwraca surowy `enc.Symbol` (ze spacja) i `Dopasowanie: "luzne"`.
  `luzne` = dokladne wyszukanie ZAWIODLO, czyli sygnal ze symbol jest brudny.
- `Magazyn.cs` - zwraca symbol JUZ przytrimowany => z jego wyniku nie da sie
  takich kartotek wykryc (`Symbol != Symbol.strip()` da 0 trafien).
- `Symbole.cs` (tryb do zmiany symbolu!) - linie 55 i 62 porownuja po trimie,
  wiec `" X"` vs `"X"` wychodzi rowne i tryb zwraca **"symbol juz poprawny"**
  bez zapisu. Tym trybem NIE DA SIE tego naprawic.

**Jak naprawic:** recznie w Subiekcie - kartoteka, pole Symbol, `Home`,
`Delete`, zapis. Albo poprawic `Symbole.cs`, zeby porownywalo bez trimu.

**Diagnostyka:** `[hex(ord(c)) for c in symbol]` na wyniku trybu `stan`
(nie `magazyn` - ten trimuje). Wiodaca spacja to `0x20`.

Wykryte 07.09.2026 przy zerowaniu magazynu MAG przez RW - patrz
[[project_subiekt_zerowanie_magazynu]].
