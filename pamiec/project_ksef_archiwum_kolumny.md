---
name: project_ksef_archiwum_kolumny
description: Archiwum KSeF — brak _server_request_log w FV_KSEF blokował KAŻDY zapis; import XML z dysku; pola pozycji różne u każdego dostawcy (17.09.2026)
metadata:
  type: project
---

Trzy rzeczy ustalone 17.09.2026 przy dorabianiu importu faktur z dysku.

## 1. ⚠️ FV_KSEF.sqlite nie miała `_server_request_log` — żaden zapis nie działał

**Objaw:** okno archiwum pokazuje „Nie udało się wczytać 1 plików", a na konsoli
`BladSerwera: baza: no such table: _server_request_log`. Dotyczyło to **każdej**
operacji `ksef-*`, więc i „🌐 Pobierz nowe" z API — nie tylko importu z dysku.
Dwie faktury widoczne w archiwum pochodziły sprzed migracji treści do bazy.

**Przyczyna:** `FV_KSEF` to czwarta baza serwera (12.09.2026). Pozostałe trzy mają
dziennik idempotencji z komentarzem, że **musi być w każdej bazie osobno** — zapis
i wpis do dziennika idą jedną transakcją, a transakcja SQLite nie rozciąga się na
dwa pliki. `MIGRACJE_KSEF` tworzyło tylko `faktury` i `pozycje`.

**Nauka na przyszłość: dodając piątą bazę — skopiuj `_server_request_log`.**
Inaczej odczyty działają, zapisy nie, a błąd wychodzi dopiero przy pierwszym zapisie.

## 2. ⚠️ Puste `MIGRACJE_KSEF` leci gołą pętlą — ALTER musi być warunkowy

`rm_serwer.py` puszczał `for sql in ops.MIGRACJE_KSEF: execute(sql)` **bez try**.
Powtórzony `ALTER TABLE` rzuca „duplicate column" i **zabiłby start serwera** przy
drugim uruchomieniu. Stąd `zastosuj_migracje_ksef()` — ten sam wzorzec, co
`zastosuj_migracje()` dla mastera: ALTER tylko gdy `PRAGMA table_info` nie widzi
kolumny. `CREATE TABLE IF NOT EXISTS` **nie doda kolumn** do istniejącej tabeli.

## 3. Pola pozycji: każdy dostawca opisuje towar inaczej

Zmierzone na trzech fakturach, **ta sama schema FA(3)** `2025/06/25/13775`:

| | AMB PRODUKT | alu-frost | QUAY |
|---|---|---|---|
| pól w `FaWiersz` | 7 (minimum) | **10** | 7 |
| `Indeks` | ✗ | ✓ ale to **kategoria**, nie symbol | ✗ |
| `DodatkowyOpis` | brak | 1 (bez `NrWiersza`) | 159, 4 klucze |
| co jest w `P_7` | kod **+ nazwa** | opis kompletu | czysty symbol |

- **`Indeks` NIE jest symbolem** — alu-frost wpisuje tam „Detale cięte laserem",
  to samo w 3 z 4 wierszy. Nie używać jako identyfikatora pozycji.
- **Klucze `DodatkowyOpis` nadaje wystawca** (QUAY: `Opis`, `Marka`,
  `Numer wydania`, `Numer zamówienia`). Nie kodować na sztywno — trzymane jako
  JSON w kolumnie `pozycje.dodatkowe`, GUI buduje z nich kolumny dynamicznie.
- `DodatkowyOpis` leży w `<Fa>` **obok** wierszy, wiąże się przez `<NrWiersza>`;
  wpisy bez `NrWiersza` dotyczą całej faktury — pomijamy.
- `P_7` u QUAY ma **wiodące spacje** (`'   618/4 2Z'`) — pułapka przy dopasowaniu.
- **11 numerów WZ** w nagłówku + per pozycja (`Numer wydania`) — to realny punkt
  zaczepienia do zestawiania faktury z dostawą, lepszy niż dopasowanie po nazwie.
  Patrz [[project_ksef_price_import]].

**Czego parser nadal nie bierze z nagłówka:** brutto `P_15`, VAT `P_14_1`, termin
płatności, NIP nabywcy (`Podmiot2` — weryfikacja, czy faktura na Waszą firmę).

## 4. Import ręcznego XML-a — klucz zastępczy

Faktura od klienta nie ma numeru KSeF (nadaje go system przy wysyłce, w treści FA
go nie ma). `ksef_number` jest kluczem głównym, więc `zastepcze_id()` buduje
`LOKALNA-<NIP>-<numer faktury>`. Ta sama para jest unikalna i powtarzalna, więc
powtórny import = ten sam klucz = nadpisanie, nie duplikat.

⚠️ **Znane ograniczenie:** gdyby ta sama faktura przyszła później przez API
z prawdziwym numerem KSeF, **trafi do archiwum drugi raz** jako osobny wpis.
Wykrywanie po parze NIP+numer — do zrobienia, gdy API ruszy.

**How to apply:**
- Wdrożenie na serwer: `wdroz_ksef_kolumny.bat` w repo, uruchomić **na W2019S**.
  Idempotentny, **nie wymaga restartu usługi**.
- Dostęp do serwera: WinRM po **IP `192.168.100.84`**, nie po nazwie `W2019S`
  (po nazwie nie działa). Poświadczenia `%TEMP%\rmdwf_srvcred.xml`, instrukcja
  w `NOW/DOKUMENTACJA/DOSTEP_SERWER.md`. Patrz [[project_rm_serwer_wdrozenie]].
- ⚠️ Udział `\\W2019S\RM_SERWER$` wskazuje na `dane\Projekty`, **nie** na `dane` —
  baz przez niego nie widać, są piętro wyżej. `C$` odmawia dostępu.
