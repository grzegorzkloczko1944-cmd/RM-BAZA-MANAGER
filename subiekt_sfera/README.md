# subiekt_sfera — most RM_BAZA ↔ Subiekt nexo PRO (Sfera)

Kontekst, decyzje i ściąga API: [`../SUBIEKT_INTEGRACJA_PLAN.md`](../SUBIEKT_INTEGRACJA_PLAN.md)
(sekcje 9–11). Tu tylko instrukcja obsługi.

## Co tu jest

| | |
|---|---|
| `NexoRecon/` | most C# (.NET 8, x64): tryby `stan` (odczyt) i `projekt` (zapis) |
| `nexo_sfera.example.json` | wzór konfigu z hasłami — skopiuj do `C:\RMPAK_CLIENT\.nexo_sfera.json` |

⚠️ **Tryb `projekt` jako jedyny ZAPISUJE do Subiekta** — i tylko z jawnym
`--zapisz`. Bez tej flagi robi suchy przebieg (czyta, mówi co by zrobił).
Domyślny tryb rozpoznawczy i tryb `stan` pozostają wyłącznie do odczytu.

W repo są **tylko źródła** (~10 KB). Wynik budowania (`bin/`, 549 MB, 554 pliki)
i konfig z hasłami są w `.gitignore` — nie commitować.

## Wymagania (wszystko jest na tej maszynie)

* Subiekt nexo **PRO** z aktywnym abonamentem (licencja PRO musi być **na bazie**, do której się łączymy)
* nexo SDK **w tej samej wersji co baza** — `C:\iLogic\SUBIEKT` (61.1.0.9431), katalogi `Bin\` + `Narzedzia\`
* dotnet SDK (jest 10.x) + runtime .NET 8 (jest 8.0.14)

## Budowanie

```
cd subiekt_sfera\NexoRecon
dotnet build -c Release -nowarn:MSB3277
```

Ścieżki do SDK są w `NexoRecon.csproj` (`nexoSdkBinPath`, `nexoSdkNarzedziaPath`).
Ostrzeżenie MSB3277 (unifikacja `mscorlib`) jest nieszkodliwe.

## Uruchamianie

```
bin\Release\NexoRecon.exe                              # konfig domyślny C:\RMPAK_CLIENT\.nexo_sfera.json
bin\Release\NexoRecon.exe inny_konfig.json
bin\Release\NexoRecon.exe --symbol=NR-RYS-1 --symbol=NR-RYS-2 --limit=30
```

Wypisuje: magazyny, kartoteki (liczba, rodzaje, kształt symboli, próbki), stany
per magazyn, kontrahentów, ostatnie ZD/PZ/WZ/RW z pozycjami; `--symbol=` sprawdza
konkretne numery rysunków i ich stany.

### Tryb `projekt` — kartoteki, komplety i ZK

```
bin\Release\NexoRecon.exe projekt --plan=plan.json --out=wynik.json            # SUCHY przebieg
bin\Release\NexoRecon.exe projekt --plan=plan.json --out=wynik.json --zapisz   # realny ZAPIS
```

Plan (buduje go `subiekt_projekt.py` z BOM-u projektu):

```json
{ "projekt": "2607", "tytul": "Projekt 2607 Platyn", "podmiot": "RMPAK",
  "pozycje": [ { "symbol": "2607-200.27ZZ", "nazwa": "Łuk transportera 72",
                 "typ": "ZZ", "ilosc": 1,
                 "skladniki": [ { "symbol": "013-100.22X", "ilosc": 4 } ] } ] }
```

Kolejność operacji: kartoteki → komplety (**topologicznie, od najgłębszych**,
bo `ZZ` bywa składnikiem `ZZ`) → ZK. Komplet powstaje tylko dla `typ` = `Z`/`ZZ`
i tylko gdy ma składniki. Szczegóły i uzasadnienie:
[`../SUBIEKT_PROJEKTY_WYDANIA.md`](../SUBIEKT_PROJEKTY_WYDANIA.md), sekcje 5 i 7.

Kody wyjścia: `1` brak konfigu, `2` błąd `Polacz` (SQL/licencja/wersja), `3` złe
logowanie operatora nexo, `0` OK.

## Typowe błędy (z FAQ SDK)

| komunikat | przyczyna |
|---|---|
| `Login failed for user 'sa'` | złe hasło SQL w konfigu |
| `Licencja zabrania używania Sfery w podanej bazie` | brak licencji PRO Subiekta na tej bazie |
| `Podana baza danych jest w innej wersji niż użyte biblioteki` | SDK ≠ wersja bazy — pobrać SDK w wersji bazy |
| `zawiera ona oczekujące aktualizacje` | uruchomić Subiekta, żeby dokończył aktualizację bazy |
| `Could not load ... InsERT.Moria.Security.Core` | proces nie jest 64-bit albo brak `ijwhost.dll` obok exe |
| brak wskazanej bazy danych | nazwa bazy bez przedrostka `Nexo_` |
