# Słownik części znormalizowanych — plan

> **Status:** projekt, nic jeszcze nie zaimplementowane (stan 02.09.2026).
> Niezależny od integracji Subiekt nexo PRO (patrz `SUBIEKT_INTEGRACJA_PLAN.md`)
> — można budować od razu, bez czekania na API nexo.

## 1. Problem

Logistyk po imporcie BOM z Inventora dostaje różnie opisane części znormalizowane
(łożyska, prowadnice liniowe, śruby itp.) — te same elementy zapisane różnie przez
różnych konstruktorów, w różnych standardach nazewnictwa, czasem z symbolami
różnych dostawców (np. HIWIN `HGW20CC` vs ORION `OR-LG20-C` dla tego samego
funkcjonalnie elementu). Dziś to się dopasowuje ręcznie.

## 2. Model danych (3 tabele)

**`elementy_znormalizowane`** — jeden wiersz = jeden fizycznie odróżnialny towar.
| pole | opis |
|---|---|
| `id` | PK |
| `kategoria` | np. "łożysko kulkowe", "prowadnica liniowa" |
| `rozmiar`, `material`, `klasa_wariant` | cechy techniczne — to one decydują, czy dwa zapisy to ten sam element (np. INOX = inny `material` = inny wiersz, nie alias) |
| `dodatkowy_opis` | wewnętrzny opis firmowy, jedno pole tekstowe (specjalne pokrycie, sztywne/luźne itp. — kilka wartości po średniku jeśli trzeba) |
| `sciezka_modelu_3d` | ścieżka do pliku `.ipt`/`.iam` — wypełniana ręcznie przez logistyka/konstruktora przy potwierdzaniu elementu, bez automatycznej konsolidacji/deduplikacji (patrz uwaga niżej) |
| `symbol_subiekt` | puste dopóki nie założona kartoteka w Subiekcie (POST, reguła "na żądanie") |
| `status` | do weryfikacji / potwierdzony / wycofany |

**`aliasy`** — różne zapisy z Inventora wskazujące na ten sam element.
| pole | opis |
|---|---|
| `element_id` (FK) | |
| `tekst` | dokładny string z modelu, np. "6004 INOX" |
| `pewnosc` | potwierdzony / propozycja — makro nigdy nie wstawia automatycznie dopasowania `propozycja` bez zatwierdzenia logistyka |

**`odpowiedniki_dostawcow`** — ten sam element, różny symbol u różnych dostawców.
| pole | opis |
|---|---|
| `element_id` (FK) | |
| `dostawca`, `symbol_dostawcy` | |
| `w_pelni_zamienny` | flaga bool — zaznaczyć `N` w razie wątpliwości, nie zakładać zamienności domyślnie |

**Uwaga do `sciezka_modelu_3d`:** dziś nie ma jednej biblioteki części
znormalizowanych — ten sam model (np. HGW20HC) bywa fizycznie skopiowany
do wielu folderów projektów osobno (potwierdzone testem na `C:\projekty`,
patrz `SLOWNIK_CZESCI_ZNORMALIZOWANYCH_PLAN.md` § historia rozmów).
Pole trzyma jedną wskazaną ręcznie ścieżkę (do wzorcowej kopii lub
biblioteki producenta), nie próbuje automatycznie wybierać "tej właściwej"
spośród duplikatów — to świadome uproszczenie, nie do rozbudowy bez
osobnej decyzji o konsolidacji plików.

## 2a. CREATE TABLE (SQLite)

Gotowy schemat do skopiowania. Uwaga: SQLite domyślnie **nie egzekwuje**
kluczy obcych — trzeba włączyć `PRAGMA foreign_keys = ON;` na każdym
połączeniu (inaczej `ON DELETE CASCADE` nic nie zrobi).

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE elementy_znormalizowane (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kategoria       TEXT NOT NULL,
    rozmiar         TEXT,
    material        TEXT,
    klasa_wariant   TEXT,
    dodatkowy_opis  TEXT,
    sciezka_modelu_3d TEXT,
    symbol_subiekt  TEXT,
    status          TEXT NOT NULL DEFAULT 'do weryfikacji'
                        CHECK (status IN ('do weryfikacji', 'potwierdzony', 'wycofany')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE aliasy (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    element_id  INTEGER NOT NULL REFERENCES elementy_znormalizowane(id) ON DELETE CASCADE,
    tekst       TEXT NOT NULL,
    pewnosc     TEXT NOT NULL DEFAULT 'propozycja'
                    CHECK (pewnosc IN ('potwierdzony', 'propozycja')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (tekst)
);

CREATE INDEX idx_aliasy_element_id ON aliasy(element_id);

CREATE TABLE odpowiedniki_dostawcow (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    element_id        INTEGER NOT NULL REFERENCES elementy_znormalizowane(id) ON DELETE CASCADE,
    dostawca          TEXT NOT NULL,
    symbol_dostawcy   TEXT NOT NULL,
    w_pelni_zamienny  INTEGER NOT NULL DEFAULT 0 CHECK (w_pelni_zamienny IN (0, 1)),
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (element_id, dostawca)
);

CREATE INDEX idx_odpowiedniki_element_id ON odpowiedniki_dostawcow(element_id);
```

Dwa celowe ograniczenia integralności, warte uwagi:
- **`UNIQUE (tekst)` w `aliasy`** — ten sam zapis tekstowy nie może wskazywać
  na dwa różne elementy naraz. Bez tego dopasowanie w makrze Inventora
  byłoby niejednoznaczne (który element wybrać?). Insert z powtórzonym
  aliasem rzuci błąd zamiast po cichu tworzyć niespójność.
- **`UNIQUE (element_id, dostawca)` w `odpowiedniki_dostawcow`** — jeden
  dostawca nie może mieć dwóch różnych symboli dla tego samego elementu
  (to sygnał błędu danych, nie prawdziwej sytuacji biznesowej).

## 3. Decyzje podjęte (rozmowa 02.09.2026)

- [x] Symbol kartoteki = numer rysunku RM_BAZA — numery są niepowtarzalne,
      zmiana konstrukcyjna zawsze dostaje nowy numer, nigdy nie nadpisuje
      starego pod tym samym symbolem. (dotyczy detali własnych, nie tej bazy —
      zapisane też w `SUBIEKT_INTEGRACJA_PLAN.md`)
- [x] Sufiks X/XX wchodzi w numer rysunku automatycznie (jest jego częścią).
- [x] Materiały (blacha, profile) — poza zakresem integracji z Subiektem,
      nie dotyczy słownika części znormalizowanych.
- [x] "Dodatkowy opis" — jedno pole tekstowe w `elementy_znormalizowane`,
      nie osobna tabela (jeden element = zwykle jeden taki opis).
- [x] Kto zatwierdza: każdy może dopisać wiersz/alias, ale status
      "potwierdzony" nadaje wyłącznie logistyk.
- [x] Powiązanie z modelem 3D: pole `sciezka_modelu_3d` (tekst, ręcznie
      wypełniane), bez automatycznej konsolidacji zduplikowanych kopii
      plików w projektach — to osobny, większy temat na później.
- [x] Przechowywanie: **osobny plik SQLite** (`slownik_czesci.sqlite`),
      zgodnie z istniejącym podziałem RM_BAZA (`master.sqlite`,
      `rm_manager.sqlite`, `project_<id>.sqlite` — każdy zakres danych
      w swoim pliku). Ta baza jest globalna, nie per-projekt.
- [x] Współbieżność:
      - **Odczyt** (dopasowanie aliasu) — bez blokad, wielu userów jednocześnie
        przez `open_ro()` jak reszta RM_BAZA (`db.py`).
      - **Zapis** (nowy element/alias) — reużyć wzorzec `RMLockManager`
        (`rm_lock_manager.py` / `lock_manager_v2.py`, sprawdzony: 2 miesiące,
        5 użytkowników), ale **nie** jako lock sesyjny z heartbeatem jak przy
        projekcie. Zapis do słownika to pojedyncza krótka operacja: jeden
        globalny klucz locka (np. `slownik_czesci.lock`), wzorzec
        acquire → insert → release w jednej transakcji, bez heartbeatu.

## 4. Narzędzie zbierania danych wstępnych

[`slownik_czesci_znormalizowanych_SZABLON.xlsx`](slownik_czesci_znormalizowanych_SZABLON.xlsx)
— arkusz do ręcznego wypełnienia przez logistyka/konstruktorów (kolumny 1:1
z modelem danych, żeby import był mechaniczny). Arkusz 2 zawiera instrukcję
wypełniania.

## 5. Kolejne kroki (do zrobienia)

1. Utworzyć `slownik_czesci.sqlite` ze schematem 3 tabel powyżej.
2. Skrypt importu z xlsx → SQLite: rozbija Alias 1/2/3 i Dostawca 1/2 +
   Symbol z płaskiego arkusza na osobne wiersze w tabelach potomnych.
   Uruchamialny wielokrotnie (re-import po każdej aktualizacji arkusza),
   nie jednorazowo.
3. [x] **Rozstrzygnięte 02.09.2026:** import obejmuje całość (wszystkie statusy),
   status zachowany w bazie. Filtrowanie (np. tylko "potwierdzony" do
   automatycznego wstawiania symbolu w Inventorze) dzieje się na poziomie
   zapytania dopasowującego (punkt 4), nie na etapie importu.
4. Funkcja dopasowania (dokładny tekst aliasu → element kanoniczny +
   symbol Subiekt, jeśli już przypisany) — używana przez makro Inventora.
5. `symbol_subiekt` pozostaje pusty do czasu integracji nexo PRO API
   (`SUBIEKT_INTEGRACJA_PLAN.md`) — nie blokuje punktów 1–4.
6. Makro Inventora czytające BOM i odpytujące tę bazę — wstawia symbol
   tylko przy dopasowaniu `potwierdzony`, nigdy przy `propozycja`/braku
   dopasowania (flaguje do ręcznego przeglądu zamiast zgadywać).
