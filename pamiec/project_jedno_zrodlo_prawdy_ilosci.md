---
name: project-jedno-zrodlo-prawdy-ilosci
description: "Model docelowy ZK — \"Ilość BOM\" i \"Ilość (zam.)\" to DWIE RÓŻNE informacje; okno Projekt/Aktualizacja jako frontend Subiekta"
metadata: 
  node_type: memory
  type: project
  originSessionId: 42739f9a-ed55-4c6c-a06d-d2bf1b97a8bf
  modified: 2026-09-08T23:13:19.355Z
---

**⏸ WDROŻENIE ODŁOŻONE (decyzja 2026-09-09).** Na teraz ilości idą **sztywno z arkusza RM_BAZA przy zasiewie**, tak jak dotąd — nie wdrażamy edycji ilości w Subiekcie. Działa tylko etap 0 (raportowanie rozjazdu). Poniższe to specyfikacja na później. Pełny opis: `ANALIZA_ZK_DWA_ZRODLA_PRAWDY.md` (ramka na początku sekcji 11).

Nadal aktualne mimo odłożenia: blokada klucza pozycji wysłanych (chroni przed duplikatami kartotek niezależnie od edycji ilości) oraz testy zapotrzebowania z etapu 0c.

**Sedno:** nie blokujemy ilości — rozdzielamy pojęcia. `Ilość BOM` (własność RM_BAZA/Inventora) i `Ilość (zam.)` (własność Subiekta) to dwie różne informacje, nie dwie kopie jednej. Rozjazd 10 vs 4 nie jest błędem: tyle wynika z konstrukcji, tyle jest zamówione. Żadna nie nadpisuje drugiej.

**Okno Projekt/Aktualizacja ma dwa etapy życia:** (1) pierwszy zasiew — zakłada kartoteki, komplety, ZK; (2) potem jest **frontendem/nakładką na Subiekta** — edycja `Ilość (zam.)` zapisuje bezpośrednio do ZK, a nie do BOM-u.

**Cykl życia kolumny „Ilość (zam.)" (3 fazy):** przed zasiewem — edytowalna w arkuszu, to z niej idzie ilość na ZK; przy zasiewie — nadpisywana wartością odczytaną z Subiekta; po zasiewie — zablokowana, pokazuje stan Subiekta. Zasiew = moment przekazania własności. Zablokowana komórka sama jest znacznikiem "wysłane" — nie trzeba osobnej flagi. (DZIŚ działa tylko faza pierwsza.)

**⛔ WARIANT 1 ODRZUCONY (2026-09-09) — struktura ZK zostaje BEZ ZMIAN.** Testy 0c (tryb `zapotrzebowanie-test`, plik `ZapotrzebowanieTest.cs`, czysty odczyt) na bazie produkcyjnej wykazały:
- `ZapotrzebowanieNaAsortyment()` **NIE rozwija kompletów** — 209 pozycji, w tym **26 KOMPLETÓW**. Czyli zapotrzebowanie na części stoi WYŁĄCZNIE na płaskich wierszach TW, które most dopisuje obok kompletu.
- `IKalkulatorZapotrzebowania` (jedyna alternatywa, `ObslugaKompletow = ZamowSkladniki`) **jest NIEOSIĄGALNY ze Sfery**: `InvalidOperationException: IInjectionScope ... cannot be constructed`.
- Zagnieżdżenia realne: 6 z 28 kompletów zawiera inny komplet.

→ Usunięcie składników z ZK wyzerowałoby zapotrzebowanie, nie dając nic w zamian. **Składniki KT zostają na ZK jako niezależne płaskie pozycje.** Ich ilości poprawia się RĘCZNIE w Subiekcie — RM_BAZA ich nie przelicza ani nie edytuje. Etap 5 (przeliczanie składników) ODPADA. Wracać tylko gdyby nowa wersja Sfery udostępniła kalkulator.

**Kluczowe zasady:**
- **RM_BAZA NIE edytuje składu KT i nie przelicza składników** — duplikowanie logiki kompletów byłoby powrotem do dwóch źródeł prawdy, tym razem dla składu.
- **Read-back po KAŻDYM zapisie**: zapis → ponowny odczyt → porównanie → dopiero komunikat sukcesu. Brak zgodności = ostrzeżenie, nie sukces.
- Kolumna **„Typ / Źródło"**: `KT` / `TW` / `Składnik KT <symbol>` — czysta informacja dla usera, gdzie iść zmienić ilość.
- **Kryterium blokady** „Ilość (zam.)": decyduje **znacznik zasiewu** (`subiekt_symbol` w bazie) — po zasiewie kolumna jest zablokowana, przed zasiewem edytowalna. Blokada wynika ze stanu danych, nie z wyglądu GUI. (Reguła `—` dla składników bez wiersza ZK straciła sens po odrzuceniu wariantu 1 — składniki MAJĄ własne wiersze.)
- **Rola ≠ typ kartoteki.** Ten sam symbol może być JEDNOCZEŚNIE samodzielny i składnikiem KT (RM_BAZA sumuje numer rysunku do jednej pozycji BOM-u).
- Powiązanie trzymamy przez **symbol** kartoteki (numer rysunku / symbol znormalizowanej) — bez wymyślania dodatkowego ID.
- **Blokada KLUCZA pozycji wysłanych** w arkuszu: dla pozycji rysunkowych — **numer rysunku**; dla **znormalizowanych — NAZWA**, bo z niej powstaje symbol (`symbol_z_nazwy`). Zmiana klucza = duplikat kartoteki przy następnym zasiewie. Nazwa pozycji rysunkowej zostaje edytowalna (to tylko opis).
- Pozycja **usunięta** z ZK: `Ilość (zam.)` = 0, `Ilość BOM` bez zmian.
- **Składnik KT: `Ilość (zam.)` = `—`, NIE zero.** Po wariancie 1 nie ma własnego wiersza na ZK, więc zero byłoby kłamstwem („nic nie zamówiono", gdy potrzeba wynika z KT). Rozróżnienie: `0` = stwierdzenie, `—` = brak własnej ilości na dokumencie. Rozwinięte zapotrzebowanie (KT ×3 → UCFL201 ×6) to **osobna kolumna "Zapotrzebowanie"**, nigdy „Ilość (zam.)" — 6 szt. nie jest ilością pozycji na ZK.
- SQLite (`qty_subiekt`, `qty_subiekt_at`) to **cache odczytu**, nie drugie źródło prawdy.
- Odczyt z Subiekta przy wzięciu locka i po wymuszonym przejęciu.
- Założenie organizacyjne: nikt nie edytuje tych danych bezpośrednio w Nexo (user potwierdził: "nikt nie będzie grzebał").

**ZWERYFIKOWANE: Subiekt NIE przelicza składników KT na ZK.** Relacja `PozycjaKomplet`/`PozycjeSkladnik` istnieje tylko na dokumentach produkcyjnych (ZPM/ZPR); `NiePrzeliczajSkladnikowPoZmianieIlosciKompletu` występuje wyłącznie na zleceniach produkcyjnych. Na ZK komplet to JEDNA pozycja, rozwinięcie dopiero przy ZK→ZD (`ZamienKompletyNaSkladniki`).

**Kluczowe odkrycie:** ZK ma dziś **hybrydową reprezentację BOM-u** — most wysyła KT ORAZ jego składniki jako osobne, niezależne pozycje. Subiekt nie zna między nimi relacji. To wyjaśnia, dlaczego zmiana KT nie rusza TW **i dlaczego obecne zapotrzebowanie na części w ogóle działa** (bierze się z tych płaskich wierszy).

**Decyzja: wariant 1** — docelowo na ZK ma iść sam KT. ALE ⛔ nie wolno usunąć składników z zasiewu bez jednoczesnej przebudowy zapotrzebowania: `ZapotrzebowanieNaAsortyment()` (używane w `Zapotrzebowanie.cs`) jest bezparametrowe i prawdopodobnie NIE rozwija kompletów. Właściwe API: `IKalkulatorZapotrzebowania.ListaZapotrzebowaniaAsortymentowWgMetodyWyliczania` z `MetodaWyliczaniaKZD.ObslugaKompletow = ZamowSkladniki`. Przed zmianą dwa testy (etap 0c): (1) czy obecna metoda rozwija komplety, (2) czy `ZamowSkladniki` rozwija **zagnieżdżone** KT do końca.

**How to apply:** Plan wdrożenia (etapy 0a–7) w sekcji 11 dokumentu. Etap 0a (test Sfery) najpierw. Do czasu wdrożenia obowiązuje [[project-zk-ilosci-nie-porownywane]] — most raportuje różnice, nie zapisuje ich.
