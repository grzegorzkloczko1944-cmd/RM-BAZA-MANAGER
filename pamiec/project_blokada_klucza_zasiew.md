---
name: project-blokada-klucza-zasiew
description: Blokada edycji klucza (numer rysunku / nazwa znormalizowanej) dla pozycji zasianych do Subiekta — WDROŻONA i potwierdzona
metadata: 
  node_type: memory
  type: project
  originSessionId: 42739f9a-ed55-4c6c-a06d-d2bf1b97a8bf
  modified: 2026-09-08T23:38:15.026Z
---

**WDROŻONE i potwierdzone na żywych danych (2026-09-09, projekt 3500 / project_71).**

Pozycja, która ma już kartotekę w Subiekcie, nie pozwala zmienić w arkuszu głównym swojego **klucza dopasowania**:
- pozycja **rysunkowa** → zablokowany **numer rysunku** (kolumna 0); nazwa zostaje edytowalna, bo to tylko opis;
- pozycja **znormalizowana** (bez numeru) → zablokowana **nazwa** (kolumna 1), bo z niej powstaje symbol (`symbol_z_nazwy`).

Przy próbie edycji: `messagebox` z symbolem z Subiekta, datą zasiewu i wskazówką („cofnij projekt → popraw → zasiej ponownie"), potem `refresh_data()` cofa zmianę.

**Gdzie:**
- kolumny `subiekt_symbol`, `subiekt_zasiew_at` w tabeli `items` — dodane przez `_migrate_project_schema` w RM_BAZA_v15_MAG_STATS_ORG.py;
- `subiekt_projekt.zapisz_zasiew(project_id, wynik)` — stawia znacznik po udanym zapisie do Subiekta (statusy kartotek `zalozona` i `istnieje`); dwie ścieżki dopasowania: po numerze rysunku i po `symbol_z_nazwy` dla znormalizowanych;
- `_pobierz_zasiew_subiekt()` / `_pozycja_bez_numeru()` + blok w `on_cell_edited` (przed walidacją duplikatów).

**Uzupełnianie znacznika dla projektów zasianych WCZEŚNIEJ:** `zapisz_zasiew` można wywołać z zapisanego logu (`znajdz_logi_projektu(id)` → `logi[0][1]`) — czysty zapis do bazy RM_BAZA, Subiekt nie jest odpytywany. Tak uzupełniono projekt 71 (211 pozycji).

**Why:** Zmiana klucza po zasiewie sprawia, że przy kolejnym uruchomieniu Projekt/Aktualizacja RM_BAZA nie rozpozna istniejącej kartoteki i założy DUPLIKAT. Znacznik musi być w bazie, nie w pamięci — po restarcie nie byłoby z czego odtworzyć blokady.

**Dodatkowo wdrożone 2026-09-09 (ten sam mechanizm znacznika):**
- **Blokada „Ilość (zam.)" (kolumna 4)** — WŁĄCZONA (twarda). Po zasiewie właścicielem wartości jest Subiekt; przed zasiewem kolumna działa normalnie. Świadoma konsekwencja: na projekcie zasianym ilości zmienia się WYŁĄCZNIE ręcznie w Subiekcie, dopóki nie powstanie edycja przez okno Projekt/Aktualizacja. User przystał na to po teście (blokada była w międzyczasie zdjęta, gdy przeszkadzała w testowaniu, i włączona z powrotem).
- **Cache ilości z ZK** — `_zapisz_ilosci_z_subiekta()` wołane przy zwalnianiu locka (obok `_naloz_zamowienia_zd`), przed zamknięciem połączenia i wysyłką pliku na serwer. Źródło: tryb mostu **`zk-ilosci`** (`ZkIlosci.cs`, czysty odczyt) + `subiekt_projekt.pobierz_ilosci_zk()`. **Cache'em jest PLIK PROJEKTU** — stanowisko z mostem odświeża i zapisuje, stanowiska BEZ Subiekta czytają zwykły plik z dysku sieciowego i pracują jak dotąd. Dopasowanie: najpierw `subiekt_symbol`, potem numer rysunku.
- **Kolumna „Typ / Źródło"** (indeks 22, DOKLEJONA NA KOŃCU za „Casting" — indeksy 0-21 są zaszyte w kilkunastu miejscach kodu). Pokazuje rolę: `KT` / `TW` / `Składnik KT <symbol>` / `KT • Składnik KT <symbol>`. Liczona z DRZEWKA projektu (`read_tree`, pliki `*_OUT.xlsx` na V:), nie z Subiekta — `_przelicz_role_pozycji()` + `_odswiez_role_pozycji()` (cache per projekt, bo to odczyt z dysku sieciowego).

**How to apply:** Z modelu [[project-jedno-zrodlo-prawdy-ilosci]] pozostają ODŁOŻONE: edycja ilości przez okno Subiekta (etap 5), cache `qty_subiekt` + odczyt przy locku, read-back po zapisie, oraz wariant 1 (na ZK sam KT) czekający na testy zapotrzebowania 0c. Rozjazd BOM vs ZK jest nadal tylko raportowany ([[project-zk-ilosci-nie-porownywane]]).

**Pułapka przy diagnozie:** RM_BAZA chodzi pod `pythonw.exe` — BEZ konsoli, więc `print` w cichym `except` przepada bez śladu. Dlatego dodano `_log_techniczny()` piszący do `C:\RMPAK_CLIENT\subiekt_logi\subiekt_projekt.log`. Przy debugowaniu czegokolwiek w tym module — zaglądać tam, nie liczyć na stdout.

**Wydajność — WAŻNE:** odczyt ilości MUSI iść przez stały most (`subiekt_bridge.call`), nie przez osobny proces. Pomiar 2026-09-09: zimny start = **18,6 s**, ciepły most = **0,3 s**. Funkcja chodzi przy zwalnianiu locka, gdzie user czeka. Dodatkowo `_zapisz_ilosci_z_subiekta()` sprawdza `_find_exe()` PRZED próbą — stanowisko bez Subiekta odpuszcza natychmiast zamiast czekać ~19 s na most, który i tak nie wstanie.

**Jak testować stanowisko BEZ mostu:** samo ubicie procesu NIE wystarcza (RM_BAZA uruchomi go ponownie). Trzeba przemianować plik we WSZYSTKICH lokalizacjach z `EXE_CANDIDATES` — dziś są dwie: `subiekt_sfera/NexoRecon/bin/Release/NexoRecon.exe` oraz `C:\iLogic\Subiekt\MOST\NexoRecon.exe`. Sprawdzić `_find_exe()` → ma zwrócić `None`.
