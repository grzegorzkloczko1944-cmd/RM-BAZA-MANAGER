---
name: project_odebrane_notatka_ilosc
description: Kolumna ODEBRANE w arkuszu przyjmuje ILOSC jako notatke (odebrane_notatka) obok kropki; migracja tylko pod lockiem, pole musi byc w allowed_fields
metadata:
  type: project
---

# ODEBRANE: ilość jako notatka (05.10.2026)

## Co robi

W kolumnie **ODEBRANE** można wpisać ilość, którą magazynier fizycznie
odebrał. Kropka działa jak dotąd — ilość wyświetla się **przed** kropką.
Liczby całkowite bez przecinka i zer końcowych; ułamek wpisuje się
przecinkiem.

## Dlaczego osobna kolumna, a nie `delivered_qty`

`delivered_qty` liczy się z **RW Subiekta** i jest przeliczane przy każdej
synchronizacji. Ręczna adnotacja magazyniera musi przeżyć ten przelicznik,
więc siedzi w osobnej kolumnie `odebrane_notatka`. Nadpisywanie
`delivered_qty` skasowałoby ją przy pierwszym odczycie stanów.

## Dwie pułapki

**1. Pole MUSI być w `allowed_fields`** w `database_manager.py`. Bez tego
zapis kończy się komunikatem „Pole odebrane_notatka nie jest dozwolone do
edycji" — zgłoszone przez usera przy pierwszym podejściu. Whitelist jest
celowa (chroni przed zapisem w dowolną kolumnę), więc każde nowe pole
edytowalne trzeba tam dopisać świadomie.

**2. Migracja wykonuje się TYLKO pod lockiem projektu.** Poza lockiem baza
otwiera się `?mode=ro&immutable=1`, więc `ALTER TABLE` nie przejdzie.
Kolumna pojawia się dopiero przy pierwszym otwarciu danego projektu do
edycji — i to jest normalne, nie błąd. Odczyt musi działać na obu
wariantach, stąd warunkowy `odebrane_select` (sprawdzenie przez
`PRAGMA table_info(items)`).

⚠️ Konsekwencja: zaraz po wdrożeniu **większość baz projektów kolumny nie
ma**. Sprawdzone 05.10 na serwerze — 1 z 8 ostatnio używanych baz miała
kolumnę (`project_89`, 1 wypełniona wartość, czyli zapis potwierdzony).
Reszta dostanie ją przy pierwszym otwarciu z lockiem. Nic nie trzeba
migrować ręcznie.

## Potwierdzone na żywym projekcie

05.10.2026, projekt **3000 Testowy** pod lockiem: wpisane `23` przy
`16006ZZ`, wartość **przetrwała przeładowanie arkusza** — czyli zapis idzie
do bazy, a nie tylko do widoku. Niezależnie sprawdzone w `project_89`:
kolumna istnieje, 1 wypełniona wartość.

## Jak sprawdzić, czy zapis naprawdę doszedł

Bazy projektów leżą na `\\W2019S\RM_SERWER$\RM_BAZA_projects`.
⚠️ SQLite **nie otworzy UNC przez URI** („invalid uri authority: W2019S") —
trzeba skopiować bazę lokalnie (`shutil.copy2`) i czytać kopię, nigdy
oryginał.

    SELECT COUNT(*) FROM items WHERE TRIM(COALESCE(odebrane_notatka,''))<>''

## Czego NIE zrobiono

* Notatka **nie trafia do eksportu XLSX** — jeśli ma się tam znaleźć,
  wymaga osobnej zmiany.

Powiązane: [[project_zapis_do_bazy_projektu]] [[project_magazyn_zd_klik_i_filtr]]
