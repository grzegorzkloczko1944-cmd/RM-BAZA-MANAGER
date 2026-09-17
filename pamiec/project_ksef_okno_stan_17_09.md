---
name: project_ksef_okno_stan_17_09
description: Stan prac nad oknem faktur KSeF na 17.09.2026 wieczorem — co zrobione, co NIE zrobione, gdzie przerwano i co dalej
metadata:
  type: project
---

**Punkt wznowienia pracy.** Sesja 17.09.2026, przerwana na przebudowie okna.
Kolejność czytania: ten plik → [[project_obieg_przyjec_dostawa_pz]] (decyzje
architektoniczne) → [[project_ksef_archiwum_kolumny]] (pułapki archiwum).

## ⚠️ GDZIE PRZERWANO — pierwsza rzecz do zrobienia

Okno archiwum **NIE WYGLĄDA** jak uzgodniona makieta. Użytkownik: „to nic nie
przypomina tego okna, w żadnym procencie".

Powód: na pytanie o zakres padła odpowiedź „tylko kolumny + okno zakładania"
i dokładnie to powstało — kolumny dołożone do STAREGO okna. Makieta pokazuje
NOWE okno. Różnice:

| makieta | stan faktyczny |
|---|---|
| drzewo faktur po lewej, grupowane po dacie, odznaki „Nowa"/„Brak kartotek"/„Rozliczona" | płaska tabela na górze |
| nagłówek z danymi faktury, dostawcy (Podmiot1) i nabywcy (Podmiot2) | pasek filtrów |
| zakładki: Pozycje / Dodatkowe informacje / Plik XML / Historia | brak |
| liczniki jako kolorowe chipy | zwykły tekst |
| **panel decyzji WBUDOWANY na dole** — radio 4 typów, pola, szybkie akcje | osobne okno modalne |
| kolorowe znaczniki typu i statusu | zwykły tekst |

⚠️ **Najważniejsza różnica jest funkcjonalna, nie kosmetyczna:** w makiecie
klikasz wiersz i decydujesz od razu, z podglądem pól, wyszukiwarką kartoteki
i wyborem ZD. Dziś trzeba otworzyć modal ze wszystkimi brakami naraz. To inny
sposób pracy.

**Makieta:** `G:\Mój dysk\SUBIEKT\ChatGPT Image 17 wrz 2026, 20_52_03.png`

**Nie zapytano jeszcze o priorytet przebudowy:** (a) sam panel decyzji na dole,
(b) cały układ naraz, (c) tylko wygląd tabeli i liczniki.

## Co DZIAŁA (wdrożone i zmierzone)

**Import XML z dysku** — przycisk w archiwum. Klucz trójstopniowo: numer KSeF
z nazwy pliku → NIP+numer w archiwum → `LOKALNA-`. Sześć wczytań tych samych
plików = trzy faktury, zero duplikatów.

**Naprawiony bug blokujący wszystko:** `FV_KSEF.sqlite` nie miała
`_server_request_log`, więc ŻADEN zapis `ksef-*` nie przechodził — także
„Pobierz nowe" z API.

**Kolumny pozycji** `indeks` + `dodatkowe` (JSON), wdrożone na produkcji.

**Warstwa dopasowania** `ksef_kartoteki.py` — trzy typy identyfikatora,
hierarchia z numerem rysunku przed symbolem katalogowym, statusy:
KARTOTEKA / NOWA_KARTOTEKA / USLUGA / POZYCJA_ZBIORCZA / RYSUNEK_RM /
BRAK_DECYZJI.

**Indeks rysunków z BOM-ów** — `rm_klient.indeks_rysunkow()`, buduje SERWER
(komenda `indeks-rysunkow`), cache 10 min w pamięci procesu. Zmierzone:
0,05 s dla 91 projektów i 4554 numerów.

**Tryb `pz` w moście** — pomiar przyjęć, wyłącznie odczyt. Zbudowany lokalnie,
**NIE wystawiony** na `\\W2019S\RM_SERWER$\MOST` (przerwane w trakcie).

## Stan wdrożenia

| gdzie | co |
|---|---|
| git `main` | wypchnięte do `c904d07` |
| serwer `C:\Apps\RM_SERWER` | `rm_serwer.py`, `rm_serwer_operacje.py` aktualne (backupy `.bak_20260917_*`) |
| most `MOST\` | **STARY** (sha `4aca0ff`) — bez trybu `pz` |
| `rm_klient.py` na serwerze | z 11.09, ale serwer go NIE importuje — nieużywany |

⚠️ Most: `git diff 4aca0ff..HEAD -- subiekt_sfera/` pokazuje TYLKO `Pz.cs`
i rejestrację trybu — żadnych poprawek spoza repo. `wersja.json` w
`bin\Release` jest już przygotowany (sha `c904d07`), wystarczy skopiować pliki.

## Pomiary, na których stoją decyzje

**Trzy faktury, ta sama schema FA(3), trzy różne układy** (`V:\! HASIOK\`):

| dostawca | pozycji | Kartoteka | Rysunek RM | Brak |
|---|---|---|---|---|
| QUAY `RVQ/05195/26` | 55 | 11 | 0 | 44 |
| AMB `FV 45/07/2026` | 5 | 0 | **5** | 0 |
| alu-frost `FVS/LAS/26/07/00417` | 4 | 0 | 0 | 4 |

**Numery rysunku AMB:** 5/5 w BOM-ach projektów, **0/5** w kartotece Subiekta.
`013-100.30b` występuje w SZEŚCIU projektach — stąd wybór ZD należy do człowieka.

**PZ w Subiekcie:** 350/350 pozycji ma asortyment (FZ tylko 75%), bo Subiekt
nie tworzy PZ dla pozycji bez kartoteki. `FZ 24/09/2026` QUAY — 53 pozycje,
0 dopasowanych, **towar nigdy nie wszedł na stan**.

## Plan dalszych prac

1. **przebudowa okna wg makiety** ← TUTAJ PRZERWANO
2. dopasowanie + zakładanie kartotek (logika gotowa, GUI do poprawy)
3. ekran przyjęcia DOSTAWY
4. powiązanie pozycji z ZD
5. generowanie PZ
6. rozliczanie faktury względem istniejących PZ

## Drobiazgi do zrobienia

- nazwa kartoteki nieedytowalna w oknie decyzji — idzie `Opis + symbol`
- `project_2611.sqlite` nie ma tabeli `items` (pomijana cicho w indeksie)
- reguły uprawnień do WinRM nie dopisane do `.claude/settings.local.json`
  (blokada „Self-Modification" — użytkownik musi wkleić ręcznie):
  `PowerShell(New-PSSession -ComputerName 192.168.100.84 *)`,
  `PowerShell(Copy-Item -ToSession *)`, `PowerShell(Restart-Service RM_SERWER *)`

## Pułapki z tej sesji

⚠️ **Restart usługi RM_SERWER ZAMYKA otwarte RM_BAZA na stacjach** — zdarzyło
się o 17:08, aplikacja zniknęła bez błędu (kod wyjścia 0).

⚠️ **Wdrażać `rm_serwer.py` i `rm_serwer_operacje.py` RAZEM.** Wgranie samego
`rm_serwer_operacje.py` z nowymi ALTER-ami zatrzymało serwer na „duplicate
column" — stary `rm_serwer.py` puszczał migracje gołą pętlą bez try.

⚠️ **Dostęp do serwera: WinRM po IP `192.168.100.84`, NIE po nazwie `W2019S`.**
Poświadczenia `%TEMP%\rmdwf_srvcred.xml`, instrukcja w
`NOW/DOKUMENTACJA/DOSTEP_SERWER.md`. Udział `\\W2019S\RM_SERWER$` wskazuje na
`dane\Projekty`, więc baz przez niego NIE widać; `C$` odmawia dostępu.

⚠️ **Python na stacji nie otwiera `\\W2019S\RM_SERWER$\...` przez `os.listdir`**,
choć bash widzi — bazy projektowe czytać przez WinRM albo przez serwer.
