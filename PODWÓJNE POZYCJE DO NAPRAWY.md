# Instrukcja dla agenta: naprawa zdublowanych składników kompletów w Subiekcie

Wykonujesz to na **stanowisku w firmie**, na **produkcyjnej** bazie Subiekta.
Czytaj do końca, zanim uruchomisz cokolwiek z `--zapisz`.

Kontekst techniczny: `SUBIEKT_ZMIANY_2026-09-06.md`, sekcja **12b**.

---

## Na czym polega problem

`Projekt.cs` (do commita `caa4f94`) dopisywał składniki kompletu przez
`Skladniki.Dodaj()` bez sprawdzenia, czy już są. Każde **ponowne** założenie
tego samego kompletu — drugi projekt z tymi samymi numerami rysunków albo
powtórka tego samego projektu — dokładało cały skład od nowa, obok.

Skutek w bazie: komplet ma każdy składnik jako **dwa (lub więcej) osobne
wiersze** po tej samej ilości. Subiekt sumuje wiersze, więc liczy
**podwójne zapotrzebowanie**. Na demo: 25 kompletów, każdy ×2.

Kod jest już naprawiony (skład = plan, czyszczony przed wpisaniem). Twoje
zadanie to **posprzątać bazę** z tego, co zdążyło powstać.

---

## Czego NIE wolno

- **Nie uruchamiaj `--zapisz` bez wcześniejszego suchego przebiegu i jego
  przejrzenia.** Raport jest bezpieczny, zapis nie.
- **Nie naprawiaj ręcznie kompletów oznaczonych `pominiety-rozne-ilosci`.**
  Narzędzie celowo je pomija — dwie różne ilości znaczą, że nie wiadomo,
  która jest prawdziwa. To decyzja człowieka z drzewkiem Inventora w ręku.
  Wypisz je w raporcie końcowym.
- **Nie zapisuj, gdy ktoś w tym momencie zakłada projekt w RM_BAZA.** Zapytaj,
  zanim zaczniesz krok 4.
- **Nie pushuj na gita.** Jeśli coś zmienisz w kodzie — commit lokalny
  i informacja w raporcie. Push tylko na wyraźne polecenie.
- **Nie „poprawiaj" `Projekt.cs` ani `KompletNapraw.cs`** w trakcie tej
  operacji. Jeśli narzędzie zachowuje się inaczej niż opisano — zatrzymaj się
  i zgłoś, zamiast dopasowywać kod do sytuacji.

---

## Krok 0 — upewnij się, że masz właściwą binarkę

Tryb `komplet-napraw` istnieje od commita `caa4f94`. **Starsza binarka nie
zgłosi błędu**: nieznany tryb potraktuje jak brak trybu, wypisze raport
rozpoznawczy na konsolę i skończy kodem 0 — a plik `--out` **nie powstanie**.

```
cd C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER
git log --oneline -1                          # ma zawierać caa4f94 lub nowszy
git log --oneline -1 -- subiekt_sfera/NexoRecon/KompletNapraw.cs   # plik musi istnieć
```

Binarka do użycia — **jedna z dwóch**, w tej kolejności:

1. `C:\iLogic\Subiekt\MOST\NexoRecon.exe` — sprawdź `wersja.json` obok: `sha`
   musi być `caa4f94` lub nowszy. Jeśli starszy → opcja 2.
2. Zbuduj sam:
   ```
   python -c "import subiekt_bridge as b; b.zatrzymaj_most()"
   cd subiekt_sfera\NexoRecon
   dotnet build -c Release -nowarn:MSB3277
   ```
   i używaj `subiekt_sfera\NexoRecon\bin\Release\NexoRecon.exe`.

Test, że binarka zna tryb (ma powstać plik i zawierać klucz `sprawdzono`):

```
NexoRecon.exe komplet-napraw --symbol=NIE-MA-TAKIEGO --out=C:\RMPAK_CLIENT\test_trybu.json
type C:\RMPAK_CLIENT\test_trybu.json
```

Brak pliku = stara binarka. Wróć do opcji 2.

Konfiguracja połączenia: `C:\RMPAK_CLIENT\.nexo_sfera.json` musi wskazywać
**serwer firmowy**, nie `localhost` / `.\INSERTNEXO`. Sprawdź pole `serwer`.

---

## Krok 1 — raport (nic nie zmienia)

```
NexoRecon.exe komplet-napraw --out=C:\RMPAK_CLIENT\komplety_raport.json
```

Przeczytaj plik. Klucze na górze:

| pole | znaczenie |
|---|---|
| `sprawdzono` | ile kompletów w bazie |
| `do_naprawy` | ile ma duplikaty **jednoznaczne** (te same ilości) — narzędzie naprawi |
| `niejednoznacznych` | ile ma duplikaty o **różnych** ilościach — narzędzie **pominie** |
| `kroki` | lista per komplet |

Statusy w `kroki`:

- `do-naprawy` — symbol, ile składników, które i ile razy
- `pominiety-rozne-ilosci` — do decyzji człowieka, **zapisz te symbole**

Jeśli `do_naprawy = 0` i `niejednoznacznych = 0` → baza jest czysta, zakończ
raportem i nie rób nic więcej.

---

## Krok 2 — kopia bazy PRZED zapisem

Poproś użytkownika o archiwizację bazy w Subiekcie (albo backup SQL)
i **poczekaj na potwierdzenie**, że jest zrobiona. Nie pomijaj tego kroku,
nawet jeśli `do_naprawy` jest małe.

---

## Krok 3 — jeden komplet na próbę

Wybierz z raportu komplet z **najmniejszą** liczbą zdublowanych składników.

```
NexoRecon.exe komplet-napraw --symbol=<SYMBOL> --zapisz --out=C:\RMPAK_CLIENT\napraw_1.json
NexoRecon.exe komplet        --symbol=<SYMBOL>          --out=C:\RMPAK_CLIENT\kontrola_1.json
```

W `napraw_1.json`: `naprawionych: 1`, krok ze statusem `naprawiony`.
W `kontrola_1.json`: w `pozycje[0].Skladniki` każdy symbol występuje
**dokładnie raz**, z ilością taką, jaka była w raporcie.

Jeśli cokolwiek się nie zgadza — **STOP**, nie idź do kroku 4, zgłoś.

---

## Krok 4 — wszystkie pozostałe

Upewnij się, że nikt akurat nie zakłada projektu. Potem:

```
NexoRecon.exe komplet-napraw --zapisz --out=C:\RMPAK_CLIENT\napraw_all.json
```

Sprawdź: `naprawionych` = `do_naprawy` z tego przebiegu, zero kroków ze
statusem `blad`. Jeśli są błędy — wypisz je, nie ponawiaj na ślepo.

Weryfikacja:

```
NexoRecon.exe komplet-napraw --out=C:\RMPAK_CLIENT\komplety_po.json
```

Ma być `do_naprawy: 0`. `niejednoznacznych` może zostać > 0 — to te
z kroku 5.

---

## Krok 5 — sporne: tylko wypisz

Komplety `pominiety-rozne-ilosci` zostaw. W raporcie końcowym podaj dla
każdego: symbol i listę składników z ilościami (są w `Szczegoly`). Człowiek
ustawi je ręcznie w Subiekcie (Asortyment → kartoteka → zakładka Składniki)
według drzewka z Inventora.

---

## Krok 6 — zamówienia, których naprawa NIE cofnie

Jeśli od podwojenia składu ktoś tworzył ZD z zapotrzebowania, ilości w tych
ZD były liczone z **podwójnego** składu i mogły pójść do dostawcy zawyżone.
Naprawa kartotek nie zmienia istniejących dokumentów.

Wypisz otwarte ZD, które zawierają składniki z raportu:

```
cd C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER
python -X utf8 -c "
import json, subiekt_bridge as b
raport = json.load(open(r'C:\RMPAK_CLIENT\komplety_raport.json', encoding='utf-8'))
symbole = set()
for k in raport['kroki']:
    for czesc in (k.get('Szczegoly') or '').split(':')[-1].split(','):
        s = czesc.strip().split(' x')[0].strip()
        if s: symbole.add(s.upper())
dok = b.call('dokumenty', {'limit': 500}).get('dokumenty', [])
print('Otwarte ZD z pozycjami z naprawianych kompletow:')
for d in dok:
    if d.get('Rodzaj') != 'ZD' or 'realizacj' not in (d.get('Status') or '').lower():
        continue
    trafione = [(p.get('Symbol'), p.get('Ilosc')) for p in d.get('Pozycje') or []
                if (p.get('Symbol') or '').strip().upper() in symbole]
    if trafione:
        print(' ', d.get('Numer'), d.get('Podmiot'), '->', trafione)
"
```

Tej listy **nie naprawiasz** — przekazujesz ją człowiekowi. Tylko on wie, co
już przyszło i co jest w drodze.

---

## Raport końcowy — co masz odesłać

```
1. Binarka: ścieżka + sha z wersja.json (albo "zbudowana lokalnie z <sha>")
2. Krok 1: sprawdzono / do_naprawy / niejednoznacznych
3. Krok 3: symbol próbny, wynik kontroli (OK / co się nie zgadzało)
4. Krok 4: naprawionych, błędy (jeśli były — treść)
5. Weryfikacja: do_naprawy po naprawie
6. Sporne do ręcznej decyzji: lista symboli z ilościami
7. Otwarte ZD z pozycjami z naprawianych kompletów: lista
8. Czy było cokolwiek nieoczekiwanego
```

Pliki `*.json` z `C:\RMPAK_CLIENT\` zostaw — to ślad operacji.
