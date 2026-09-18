---
name: project_sesja_18_09_faktury_ksef
description: "Przebieg sesji 18.09.2026 — wdrozenie mostu i serwera, 5 trybow okna faktur KSeF, WZ per pozycja; co ustalono, co odrzucono i dlaczego"
metadata:
  node_type: memory
  type: project
---

Zapis calodniowej sesji 18.09.2026. Szczegoly techniczne sa w notatkach
tematycznych — tu KOLEJNOSC ustalen i **slepe uliczki**, zeby nikt nie
powtarzal tej samej drogi.

## Co zostalo wdrozone

| | |
|---|---|
| Most | `3b8ab7c` → … → **`f4ff4ce`** (stoi na serwerze), binarki na `most-server` |
| Serwer | operacje dostaw + `dostawy_pozycje.wz`; usluga restartowana, err log pusty |
| Okno faktur KSeF | 5 trybow zrodla, kolumny dynamiczne, wiazanie symboli |
| Okno przyjecia dostawy | wyszukiwarka dostawcy, WZ per pozycja, blokada 1 WZ = 1 PZ |

## ⛔ Slepe uliczki — NIE POWTARZAC

1. **`DokumentElektroniczny.Xml`** (byte[], „Tresc dokumentu") jest NIECZYTELNY
   wprost — nie UTF-8, nie gzip/zlib/deflate. Pozycje bierze sie przez
   `PobierzDane()`. Patrz [[project_sfera_kolejka_efaktur]].

2. **`PozycjaDokumentu.RodzajAsortymentu` NIE mowi, czym pozycja jest** — mowi,
   czy ma podpieta kartoteke. Zmierzone: „Towar" = ma symbol 277/277,
   „Usługa" = nie ma symbolu 249/259. Probowalem na tym oprzec typ TW/US
   i wyszly „Worki na smieci" jako usluga. WYCOFANE.

3. **`RodzajWiersza`** na e-Fakturze to KOREKTY (Wiersz/PrzedKorekta/Korekta/
   PoKorekcie), nie rodzaj towaru. **`UslugaKosztowa`** mowi tylko o grupowaniu
   wg stawki VAT. Patrz [[project_usluga_jednorazowa_uj]].

4. **Pole `NumerKSeF` w rekordzie `Fak`** trzymalo numery ZAMOWIEN. Filtr po nim
   pokazywal 3 faktury ze 120. Przemianowane na `NumeryRealizowanych`.

5. **Rekord `Fak` nie mial NIP-u** — przez to „Kontrahent w Subiekcie: BRAK"
   na KAZDEJ FZ i zablokowany zapis powiazan. To wygladalo jak „klawisze nie
   dzialaja".

## Zasada rozpoznawania typu pozycji (ustalona przez uzytkownika)

> JEST kartoteka → czytaj rodzaj Z SUBIEKTA, nie zgaduj.
> NIE MA kartoteki → dopiero wtedy proponuj z nazwy.

Heurystyka `wyglada_na_usluge` zostaje wylacznie dla pozycji bez kartoteki
(glownie kolejka KSeF, gdzie kartotek jeszcze nikt nie wskazal).

Przy okazji: numer rysunku Z KARTOTEKA dostaje status KARTOTEKA, nie
RYSUNEK_RM — dotad wynik zalezal od tego, czy dostawca powtorzyl numer
w nazwie (`REG-300.11X Podkladka…` vs `REG-300.20`).

## Otwarte na jutro

**Rozliczanie faktury z PZ** — ostatni niezrobiony punkt obiegu
([[project_rozliczanie_faktury_z_pz_plan]]). Dzisiejsza zasada
[[feedback_jedno_pz_na_wz]] czyni pierwszy szczebel jednoznacznym.

⚠️ Uzytkownik zapytal „faktura robi przyjecia?" — to kierunek ODRZUCONY
17.09.2026 na podstawie pomiaru (`FZ 24/09/2026`: 53 pozycje, 0 dopasowanych,
zero stanu). Faktura KONTROLUJE, nie tworzy. Do ustalenia zostal WYJATEK:
co zrobic, gdy faktura przyszla, a przyjecia nikt nie zrobil — czy pozwalac
wygenerowac z niej PZ. Pytanie zadane, odpowiedzi jeszcze nie ma.

Patrz [[project_obieg_przyjec_dostawa_pz]], [[project_przyjecie_dostawy_pz]].
