---
name: project_zd_powtorka_i_kolumna_subiekt
description: 03.10.2026 — ZD 5 poszło 2× i nie dało ptaszków; przyczyny (most oddawał całe Uwagi ZK zamiast numeru; wysyłka bez Id dokumentu), zabezpieczenie przed powtórką, kolumna SUBIEKT po projekcie (nie po symbolu), krótkie numery bez „CENTRALA”; co wystawić w firmie
metadata:
  type: project
---

Sesja 03.10.2026 (M-OLD, dom). Zgłoszenie: „mam wysłane ZD, a w projekcie
brak info, że pozycja zamówiona” (WJ200UME-01-10, ZD 5 do QUAY, projekty
2627+3500).

## Co było nie tak (trzy osobne rzeczy)

1. **Most oddawał przy pozycjach ZD całe Uwagi ZK** („3500 Projekt\ndupal”)
   zamiast numeru („3500”) — `Zapotrzebowanie.ProjektZk`. Porównanie
   z numerem projektu nie przechodziło; przy symbolu obecnym w DWÓCH BOM-ach
   `refy_bom` słusznie nie zgadywał i „Zamówiono” nie trafiało nigdzie.
   Dotyczyło KAŻDEGO ZD z detalem w kilku projektach od zmiany formatu Uwag
   (10.09). Objaw w oknie ZD: kolumna Projekt „3500 Pro…” przy zamówionych,
   „2627, 35…” przy niezamówionych.
   Naprawa: `numery_projektow_z_pozycji_zd()` w `subiekt_zamowienia.py`
   (działa ze STARYM mostem) + poprawka w `.cs` (sam numer przez
   `Znacznik.NumerProjektu`) — ta czeka na build w firmie.
2. **Wysyłka bez Id dokumentu** (ZD 4 z 02.10): mapa numer→Id w oknie
   Zamówień była budowana raz na życie okna, a ZD powstało w tym oknie po
   jej zbudowaniu. Ślad w dzienniku bez `dokument_id` → Przegląd pokazuje
   „niewysłane”, powtórka niewykrywalna. Naprawa: `_id_dokumentu` czyta
   listę ponownie przy pudle (raz na numer), cache kasowany po utworzeniu
   i usunięciu ZD; okno wysyłki PYTA, gdy Id brak (domyślnie Nie).
3. **Brak zabezpieczenia przed podwójną wysyłką** — ZD 5 ×2 w dzienniku.

## Zabezpieczenie przed powtórką (decyzja usera: ostrzeżenie, nie blokada)

`OknoWysylki`: `ostatnia_wysylka(dokument_id)` → pomarańczowy pasek
„To ZD wysłano już … na adres …”, temat „PONOWNIE: …”, przy „Wyślij”
pytanie z domyślnym NIE. Po potwierdzeniu w tym samym oknie kolejne
„Wyślij” to już powtórka.

**Powtórka niczego nie przestawia:** `naloz_zamowienia` nie nadpisuje
`ordered_at`, gdy pozycja już ma ptaszek; serwerowa
`zd-zamowione-dodaj-zachowaj` (upsert) zostawia `kiedy` dla tego samego
numeru ZD, pusty termin/dostawca nie kasuje poprzedniego, INNY numer ZD na
pozycji = nowa data. Klient woła ją z fallbackiem na stare
`zd-zamowione-dodaj`, gdy serwer odpowie „nieznana operacja”. Portal RFQ:
`code = "ZD 5/… #<Id>"` — numer wraca do obiegu, Id nie (nowe ZD 5 nie
wpadnie do zamówienia starego ZD 5).

## Kolumna SUBIEKT (arkusz główny)

- „Zamówione” = **WYSŁANE** (decyzja usera). `✉ ZD 4` wysłane (zielone),
  `⧗ ZD 2 · niewysłane` (żółte), `☰ ZK 1`, `❏ kartoteka (stan 3)`, `⬜ brak`.
- ⛔ **W komórkach arkusza TYLKO symbole z BMP, nie emoji 📋🛒📇** (user:
  „scroll tak wolno działa, gdy mam dane w SUBIEKT"). Zmierzone tksheet
  7.5.19, 300 wierszy, okno 1400 px: pusta kolumna 62–67 ms/tick kółka,
  z emoji SMP 88–92 ms, z symbolami BMP 66–68 ms. Tk rysuje znaki spoza
  BMP czcionką zastępczą (Segoe UI Emoji) per komórka, a arkusz
  przerysowuje WSZYSTKIE widoczne komórki przy każdym ticku (koszt liniowy
  od liczby widocznych komórek, ~0,17 ms/komórkę — patrz komentarz przy
  `stepped_mousewheel`). Podświetlenia, długość tekstu, „·" — bez wpływu
  (zmierzone).
- **Po projekcie, nie po symbolu**: most `stan-pozycji` bierze ZD po samym
  symbolu (na 3300 TEST pokazywał „🛒 ZD 2” dla płyty zamawianej na
  2627/3500). `dopasuj_zd_do_projektu()` rozstrzyga z trybu `dokumenty`
  (projekt per pozycja ZD) + dziennika wysyłek — jeden odczyt, nie per
  pozycja. Cudze ZD idzie jako dopisek „· ZD 2 dla 3500, 2627”.
- Wynik kasowany przy zmianie projektu (`_subiekt_stany_pid` w
  `refresh_data`) — wcześniej na 3500 wisiały ZK Feniksa 2637.
- `krotki_numer()`: „ZD 4/CENTRALA/2026” → „ZD 4”. CENTRALA/MASTER to
  symbol magazynu z numeracji Subiekta, niepotrzebny; do mostu zawsze
  pełny numer.
- `zd_podzial` (ilość per projekt z ZK tej samej listy dokumentów) i
  `stan_pokrywa` (ZD NIEPRZYJĘTE, a stan ≥ potrzeba projektów z tego ZD →
  „⚠ ✉ ZD 4 · stan 200 pokrywa potrzebę 96", pomarańczowe; po przyjęciu
  dostawy alarm by kłamał, stąd warunek `do_realizacji > 0`).
- Szczegóły pozycji = własne okno `_okno_szczegolow_subiekt` (nagłówek
  z plakietką w kolorze komórki, sekcje Kartoteka / ZK / ZD / ostrzeżenie /
  cudze ZD, wysrodkuj + ukryj_do_zbudowania), nie `messagebox.showinfo`
  (jeden blok tekstu, nieczytelny; stawał na monitorze głównym). Numery
  ZK/ZD są odnośnikami: klik zamyka okno i otwiera Przegląd dokumentów
  ustawiony na tym dokumencie (`open_subiekt_dokumenty(szukaj=numer)` →
  `open_window(szukaj=…)`, ta sama droga co klik w numer RW w oknie wydania).
- Kolor komórki SUBIEKT odtwarza `_color_single_row` (jak WYCENA) — inaczej
  znikał po kliknięciu w wiersz (`dehighlight_cells` zdejmuje tło całego
  wiersza przy każdej zmianie zaznaczenia).
- **Leniwe wczytanie**: `SUBIEKT_AUTO_PO_S = 12` s po zmianie projektu
  (`_zaplanuj_sprawdzenie_subiekta` z `refresh_data`, tylko gdy pid się
  zmienił; zmiana projektu przed upływem kasuje odliczanie; stanowisko bez
  mostu nic nie planuje). `sprawdz_w_subiekcie(cichy=True)` — bez okienek,
  błąd do konsoli; z menu jak dotąd, z podsumowaniem. Stan trwały na
  serwerze (widoczny bez mostu) — nadal otwarte.
- **Samo się odświeża po zmianie**: `subiekt_panel.po_zmianie_subiekta(fn)`
  + `uniewaznij_odczyty()` woła słuchaczy; wołane z `subiekt_bridge.call
  (write=True)` (każdy zapis do Subiekta) i z `_odnotuj_wyslanie` (wysyłka
  ZD to zapis na serwerze RM_BAZA, most o niej nie wie). Arkusz:
  `_subiekt_zmiana_z_zewnatrz` → `after(0)` na wątek Tk → 3 s debounce →
  `sprawdz_w_subiekcie(cichy=True)`, tylko gdy kolumna była już policzona.

## Komunikacja w pakiecie — co znalazł dziennik mostu (03.10 wieczór)

`C:\RMPAK_CLIENT\subiekt_logi\bridge_YYYYMMDD.log`: 69× `dokumenty`,
39× `zapotrzebowanie`, 38× `magazyn`. Pojedyncze kroki są szybkie
(stan-pozycji 0,4 s / 222 symbole, dokumenty 1,0–1,2 s, zapotrzebowanie
1,8 s, serwer 0,02 s) — zwalniało POWTARZANIE: każde otwarcie panelu
SUBIEKT czytało cztery tryby od nowa (~3,5 s w kolejce mostu, a most
obsługuje żądania po kolei), „Sprawdź w Subiekcie" zaraz potem czytało
`dokumenty` piąty raz (panel przy zamknięciu kasuje swoje odczyty —
`_zostaw_tylko`), a drugi klik w „Sprawdź" ustawiał drugi komplet zapytań.

Naprawione: `subiekt_panel._OSTATNIE` (ostatni udany wynik na klucz,
ważny WAZNOSC_ODCZYTU_S = 60 s) — liczniki panelu nie pytają mostu, gdy
mają świeży wynik; `podejrzyj_odczyt()` (kopia bez zdejmowania wpisu) dla
kolumny SUBIEKT; `subiekt_bridge.call(write=True)` → `uniewaznij_odczyty()`
po każdym zapisie; blokada równoległego „Sprawdź"
(`_subiekt_sprawdzanie_trwa`). ⚠️ `odczyt_z_panelu` dla OKIEN celowo NIE
sięga do `_OSTATNIE` — „Odśwież" w oknie woła tę samą ścieżkę i musi
trafić w most.

`StanPozycji.cs` przepisany na trzy projekcje (kartoteki ze stanami, ZK
z pozycjami, ZD z pozycjami — wzorzec Magazyn.cs/Dokumenty.cs) zamiast
`WyszukajPoSymbolu` + `StanyMagazynowe` per symbol i `d.Pozycje` per
dokument (~500 zapytań). Zmierzone na demo, 220 symboli: 386–476 ms →
59–163 ms; wynik identyczny ze starym kodem (0 różnic na 220 pozycjach,
porównane JSON-em). Zbudowane w domu do `bin/Release` (most ubity za
zgodą usera, wstał sam przy pierwszym wywołaniu). ⚠️ W firmie nadal
trzeba `git pull` → `dotnet build -c Release` → wystawić.

## Przegląd dokumentów / okno ZD

Najnowszy na górze: most oddaje dokumenty grupami (ZK, ZD, RW, PW, WZ) —
sortowane teraz po (data, Id). Dialogi Wyślij/Usuń ZD/ZK: najnowsze na
górze (`_klucz_zd`, reverse).

## Do wystawienia w firmie

`rm_serwer_operacje.py` (dwie operacje: `zd-wyslane-ostatnia`,
`zd-zamowione-dodaj-zachowaj`) → restart RM_SERWER; most po `git pull`
→ `dotnet build -c Release`. Bez tego Python działa z fallbackami.

## Sprawdzone na żywo 03.10 01:15

Nowe ZD 4 (Id 100252, 2627+3500, 5 poz.) wysłane raz: dziennik ×1
z terminem 10.10, na serwerze czekają wpisy „Zamówiono” dla 2627 (3 poz.)
i 3500 (5 poz., w tym złożenia ZZ). Stare ZD 5 usunięte przeze mnie
(`usun_zd` + `uniewaznij_wyslania`). W dzienniku został osierocony wpis
„ZD 4” bez Id z 02.10 (dawne ZD 4 Feniksa, usunięte) — nieszkodliwy,
odczyty filtrują `dokument_id IS NOT NULL`.

Powiązane: [[project_zd_okno_do_zamowienia]], [[project_subiekt_wysylka_zd]],
[[project_subiekt_stan_05_09_2026]], [[project_stan_prac_02_10_2026]].
