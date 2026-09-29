---
name: project_zk_pozycja_bez_kartoteki
description: Okno ZD padało „Object reference not set" — pozycja otwartego ZK BEZ kartoteki wywraca SDK ZapotrzebowanieNaAsortyment(); most od 4b2c55f omija ją i raportuje; jak diagnozować NRE ze Sfery (ilspycmd), pułapka projekcji EF
metadata:
  type: project
---

# ZK z pozycją bez kartoteki → okno ZD padało (29.09.2026)

**Objaw:** okno „Zamówienia do dostawców" w RM_BAZA: *Object reference not
set to an instance of an object*, pusta tabela. Tryb mostu `zapotrzebowanie`
padał `NullReferenceException` **wewnątrz SDK**:
`ZamowieniaOdKlientow.ZapotrzebowanieNaAsortyment()` → `Lookup.Create`.

**Przyczyna (dekompilacja):** metoda grupuje pozycje otwartych ZK po
`t.Item1.AsortymentAktualny.Id`. Ręczne **`ZK 2/09/2026` (SIA Kvadro)** ma
pozycję **Id 124800: „Gasket", 12 szt × 25 zł, `Jednorazowy = 1`** — czyli
**pozycja jednorazowa wpisana bez kartoteki** ([[project_usluga_jednorazowa_uj]]).
`AsortymentAktualnyId = NULL`, `AsortymentWybranyId = 123970` → wiersz
w `AsortymentyHistoria` (FK tej kolumny idzie do HISTORII, nie do
`Asortymenty`!) z nazwą „Gasket" i pustym `Asortyment_Id`. Nikt niczego nie
usunął — Sfera po prostu nie umie policzyć zapotrzebowania, gdy na otwartym
ZK jest pozycja jednorazowa. To ograniczenie SDK, nie błąd danych.

## ⛔ Dlaczego z zewnątrz „wszystko wyglądało dobrze"

* Tryb `dokumenty` czyta pozycje **projekcją EF** (`Select(p => new {
  p.AsortymentAktualny.Symbol … })`) — INNER JOIN, zepsuta pozycja **znika
  ze zrzutu bez śladu**; do tego `if (sym.Length == 0) continue;`.
  ZK 2/09/2026 pokazywało 1 pozycję (Delivery cost) zamiast 2.
* `stan` po symbolu znajdował wszystkie 280 pozostałych pozycji — bo
  problemowa nie ma symbolu, więc nie było o co pytać.
* Kopia dla MAG też nic nie pokaże — synchronizuje kartoteki, nie pozycje ZK.

**Wniosek:** przy NRE z wnętrza Sfery **nie diagnozować projekcjami** —
tylko przegląd **encji** (`zk.Pozycje` → `p.AsortymentAktualny == null`).

## ⛔ Błędna hipoteza (kosztowała ~1 h)

„Pusty Magazyn na ZK zakładanych przez RM_BAZA" — korelacja była mocna
(2 ZK bez magazynu, oba z RM_BAZA, oba aktywne; ręczne miały MASTER).
Po uzupełnieniu magazynu błąd został. Poprawka i tak weszła (Projekt.cs:
nowe ZK dostają MASTER, istniejące uzupełniane) — ale **to nie była
przyczyna**. Przy okazji: pierwsza wersja tej poprawki raportowała
`magazyn-uzupelniony` bez `Zapisz()` (gałąź „bez-zmian" go pomija) —
raport mostu kłamał, wykryte dopiero odczytem z bazy. **Po każdym zapisie
mostem weryfikować odczytem, nie raportem.**

## Naprawa w moście — docelowa (`c3bcd9b`, wystawiona 29.09 15:45)

**Gwarancja: okno ZD nie pada i nie liczy gorzej niż Sfera, niezależnie od
tego, co leży na ZK.** `Zapotrzebowanie.cs`:

1. Przed SDK własny przegląd **encji** otwartych ZK (`!Zamkniety` przez
   dynamic, odwrót po nazwie statusu). Pozycja z `AsortymentAktualny == null`
   jest ROZPOZNANA przez `AsortymentWybrany` (wiersz `AsortymentyHistoria`):
   nazwa, symbol, `Jednorazowy`. JSON `bledy`: `{dokument, pozycja_id, ilosc,
   nazwa, symbol, rodzaj: jednorazowa|bez-kartoteki, blad}`.
2. Są takie pozycje → liczymy sami (`tryb: "wlasny"`) — **replika**
   `BudujPozycjeZapotrzebowaniaNaPodstawieGrupy` z SDK: ilość niezrealizowana
   = `IloscDoRealizacji.PozostalaIlosc` (kolumna utrzymywana przez Subiekt),
   jednostka wspólna albo bazowa z przeliczeniem proporcją
   `IloscWJednostceBazowej/Ilosc`, dostawca domyślny =
   `DaneAsortymentuDostawcyPodstawowego.Podmiot` (= `DostawcaPodstawowy()`).
   Nie ma → SDK jak dotąd; gdyby mimo to padło → ten sam tryb własny.
3. Okno ZD: jednorazowe → pasek informacyjny („Pominięto 1 pozycję
   jednorazową: „Gasket" (ZK 2/09/2026)"), bez-kartoteki → ostrzeżenie
   z nazwą/Id i prośbą o sprawdzenie dokumentu.

⛔ **Kalkulator SDK (`IKalkulatorZapotrzebowania`) jako alternatywa NIE
działa** spoza Subiekta — wymaga kontenera DI (`IInjectionScope`);
`zapotrzebowanie-test` pokazuje to od dawna. Nie próbować ponownie.

## Jak czytać bazę Subiekta wprost (tylko SELECT)

`sqlcmd` jest w `C:\Program Files\Microsoft SQL Server\Client SDK\ODBC\170\Tools\Binn\`,
dane logowania w `C:\RMPAK_CLIENT\.nexo_sfera.json` (`sa`). Schemat
`ModelDanychContainer`: `Dokumenty`, `PozycjeDokumentu` (90 kolumn:
`AsortymentAktualnyId`→`Asortymenty`, `AsortymentWybranyId`→`AsortymentyHistoria`,
`Dokument_Id`, `Ilosc`, `Opis`), `Asortymenty` (Id 100007–111396),
`AsortymentyHistoria` (Symbol, Nazwa, Jednorazowy, Asortyment_Id).
Kolumna `timestamp` nie rzutuje się na NVARCHAR — pomijać. `-W` i `-y`
w sqlcmd się wykluczają.

## Jak dekompilować SDK (działa)

`dotnet tool install -g ilspycmd` → `~/.dotnet/tools/ilspycmd.exe -t
<pełna.nazwa.Typu> <dll>` (jeden typ) albo `-p -o <katalog> <dll>`
(cały projekt; 1675 plików dla Logistyka.dll). Który plik: `grep -l
<nazwa> C:\iLogic\SUBIEKT\Bin\InsERT.Moria.*.dll`. Dekompilacja
„do jednego pliku" ma 24 błędy i gubi metody rozszerzające — szukać
w katalogu projektu. Dokumentacja TSV (82k wpisów) NIE ma
`ZapotrzebowanieNaAsortyment`.

## Do zrobienia (user)

Pozycja **Id 124800 „Gasket"** na **`ZK 2/09/2026`** to legalna sprzedaż
jednorazowa — NIE trzeba jej usuwać. Dopóki jakikolwiek otwarty ZK ma pozycję
jednorazową, zapotrzebowanie liczy się awaryjnie (bez przeliczania jednostek
i dostawcy domyślnego). Jeśli to przeszkadza: podmienić na kartotekę
(np. właściwy oring) albo zrealizować/zamknąć ZK. Podejrzewane przez usera
`027-300.06Z` / `027-100.00ZZ` (błędy importu) są **w porządku** — obie
w zapotrzebowaniu normalnie.

Zobacz też: [[project_master_stuck_transaction]] (ta sama zasada:
raport ≠ stan bazy), [[feedback_most_rebuild_release]], [[feedback_most_w_gicie]].
