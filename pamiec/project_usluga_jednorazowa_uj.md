---
name: project_usluga_jednorazowa_uj
description: "UJ (usluga jednorazowa) w Subiekcie to pozycja BEZ kartoteki, wpisana wprost na dokument — e-Faktura nie niesie tej informacji, a kartoteka zna tylko Towar/Komplet/Usluga"
metadata:
  node_type: project
  type: project
---

Ustalone 18.09.2026 przy dopasowywaniu pozycji faktur KSeF do kartotek.

Na FZ w Subiekcie kolumna typu pokazuje `TW` (towar) albo **`UJ` — usluga
jednorazowa**. Przyklad: FZ od „MA-JA", poz. 24 „Dostawa" 250 zl = `UJ`,
reszta pozycji `TW`.

⚠️ **`UJ` NIE JEST rodzajem kartoteki.** Kartoteka Subiekta zna tylko trzy
rodzaje — zmierzone na produkcji (3389 pozycji): `Towar` 3205, `Komplet` 103,
`Usługa` 81. Nie ma tam „uslugi jednorazowej".

**Czym wiec jest `UJ`:** pozycja wpisana WPROST NA DOKUMENT, bez kartoteki.
Dokumentacja SDK potwierdza to wprost bledem walidacji
`AsortymentJednorazowyPodlaczonyDoKartotekowegoBlad` — „Blad wystepujacy, gdy
towar jednorazowy ma ustawione powiazanie z towarem kartotekowym". Czyli
jednorazowy i kartotekowy to swiaty ROZLACZNE.

**Czego NIE MA w e-Fakturze:** `IDaneWierszaFaktury` (37 wlasciwosci) nie ma
pola towar/usluga. Sprawdzone pulapki:
* `RodzajWiersza` → `RodzajWierszaEFaktury` to KOREKTY
  (Wiersz / PrzedKorekta / Korekta / PoKorekcie), nie rodzaj asortymentu;
* `DanePozycjiDokumentuElektronicznego.UslugaKosztowa` mowi tylko, czy pozycja
  powstala ze ZGRUPOWANYCH wg stawki VAT pozycji kosztowych.

To logiczne: e-Faktura jest dokumentem DOSTAWCY i nie wie, czym dana linia
jest w NASZYM magazynie. Podzial powstaje dopiero przy przetwarzaniu na FZ.

**How to apply:**
- Pozycji z kolejki KSeF NIE DA SIE automatycznie oznaczyc jako `UJ` na
  podstawie samej e-Faktury — tej informacji tam po prostu nie ma.
- Zeby okno RM_BAZA wiedzialo, ze „Dostawa" od MA-JA to usluga, potrzebne jest
  POWIAZANIE symbol dostawcy → kartoteka (`DaneAsortymentuDlaPodmiotu`) albo
  decyzja czlowieka. Bez tego zostaje heurystyka po nazwie
  (`_NAZWA_USLUGI` w `ksef_kartoteki.py`) — proteza, nie odczyt ze stanu.
- ⚠️ Gdyby dokladac tryb mostu pod `UJ`: to pozycja dokumentu, wiec czytac ja
  z `PozycjaDokumentu` na FZ (`RodzajAsortymentu`, `AsortymentAktualnyId` = 0),
  NIE z kartoteki — tam jej nie ma.

Patrz [[project_sfera_kolejka_efaktur]], [[project_dopasowanie_podpowiedzi]].
