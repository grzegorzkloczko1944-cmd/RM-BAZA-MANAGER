---
name: project_zk_poz_usun_dane_pozycje_remove
description: Usuwanie pozycji z ZK dziala przez ob.Dane.Pozycje.Remove(poz) + Zapisz() - nie przez ob.Pozycje.Usun (nie istnieje); sonda probe-pozycje i ZK testowe TEST-USUN
metadata:
  type: project
---

# Pozycję z ZK usuwa `ob.Dane.Pozycje.Remove(poz)` + `ob.Zapisz()` (02.10.2026)

Do tej pory tryb `zk-poz-usun` ZAWSZE kończył się „Sfera nie pozwala usunąć
pozycji z ZK — usuń ręcznie". Komentarz w kodzie mówił, że Sfera nie wystawia
`Usun` dla ZK. To było PRAWDZIWE, ale szukano w złym miejscu.

## Co ustaliła sonda (`ProbePozycje.cs`, tryb `probe-pozycje`)

* `ob.Pozycje` (IPozycjeDokumentu) zwraca **sam obiekt biznesowy**
  `ZamowienieOdKlientaBO` — ma tylko `Dodaj*`/`SprobujDodac*`. Dokumentacja
  API (`InsERT.Moria.API.xml`) to potwierdza: `Usun(pozycja)` istnieje tylko
  na dokumentach księgowych, windykacyjnych, cennikach, inwentaryzacji.
* `ob.Dane.Pozycje` to `WrappedEntityCollection<PozycjaDokumentu>` (EF) z
  `Remove(PozycjaDokumentu)`. **Remove + ob.Zapisz() usuwa pozycję z dokumentu
  w bazie** — potwierdzone read-backiem; dokument zostaje.
* `poz.DetachFromParent()` rzuca InvalidOperationException — nie tędy.

## Pułapki, które kosztowały pierwszą rundę

1. **Dopasowanie po słowach kluczowych łapie śmieci**: `OnUsunietoPozycjePromocyjna`,
   `UsunRezerwacje`, `...Cleared` — każde „wywołane", każde z `Zapisz()`.
2. **Po kilku `Zapisz()` na TYM SAMYM BO** kolejny zapis pada na
   `OptimisticConcurrencyException: Dane zostały zmienione w tle` — właściwy
   kandydat wyglądał na nieudany. Każdy wariant MUSI dostać świeży
   `zamowienia.Znajdz(dokument)` i świeżo odszukaną pozycję.
3. W `EF` projekcja `p.AsortymentAktualny.Id` w zagnieżdżonym Select rzuca
   TargetInvocationException (osobna notatka: [[project_subiekt_id_tozsamosc]]).

## Wdrożone

`Projekt.UsunPozycje` — po dotychczasowym szukaniu `Usun` na `ob.Pozycje`
dochodzi fallback: `Remove` ZADEKLAROWANE NA KLASIE kolekcji `ob.Dane.Pozycje`
(nie duplikat z mapy `ICollection<T>`). `ZkPozUsun` bez zmian logiki — ma już
read-back po zapisie. Komunikat o niepowodzeniu mówi, co próbowano.

Test produkcyjny: `zk-poz-usun` zdjął `HGW15SO` z ZK testowego, potem
`HGH15SO`+`HGW15SO` z `ZK 3/09/2026` (2637) — „zdjęto 2 poz. (potwierdzone
odczytem)". `zk-ilosci` 2637: 5 linii HG*, same SOK.

## Piaskownica: `TEST-USUN*`

`probe-pozycje --zapisz` działa WYŁĄCZNIE na projekcie o numerze zaczynającym
się od `TEST-USUN` — tryb sam odmawia na innym. ZK testowe zakłada się trybem
`projekt` (plan z 2 istniejącymi kartotekami, podmiot RMPAK), kasuje
`zd-usun --numery="ZK n/mm/rrrr"` po opróżnieniu. Tak zrobiono 02.10.2026
(`ZK 1/10/2026`, usunięte). Osierocone kartoteki po teście: `kartoteka-usun`.

Powiązane: [[project_aktualizacja_bom_zmiana_numeru]]
