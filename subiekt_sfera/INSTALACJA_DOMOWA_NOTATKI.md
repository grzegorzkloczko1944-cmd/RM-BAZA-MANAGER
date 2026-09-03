# Instalacja Subiekt nexo PRO demo — komputer domowy (M-OLD)

Notatki z pierwszej próby postawienia środowiska testowego integracji
RM_BAZA ↔ Subiekt na komputerze domowym (nie firmowym). Kontekst ogólny:
[`../SUBIEKT_INTEGRACJA_PLAN.md`](../SUBIEKT_INTEGRACJA_PLAN.md),
[`README.md`](README.md).

## 🐛 2026-09-03: bug znaleziony i naprawiony w Projekt.cs (tryb zapisu)

Pierwszy test trybu `projekt --zapisz` na M-OLD (kartoteka+komplet Z+ZK)
wykrył realny bug: kartoteki dla pozycji typu `Z`/`ZZ` były zakładane
przez `WypelnijNaPodstawieSzablonu(szablony.DaneDomyslne.Towar)` —
zawsze jako zwykły Towar, niezależnie od `typ` w planie. Sfera wtedy
odrzuca późniejsze dodanie składników:

```
InvalidOperationException: Asortyment, do którego dodawane są składniki
musi być kompletem.
```

**Naprawa** (`Projekt.cs`, sekcja "1. KARTOTEKI"): dla pozycji z
`typ = Z` lub `ZZ` używamy `szablony.DaneDomyslne.Komplet` zamiast
`.Towar`. Właściwość `Komplet` istnieje na `ISzablonyAsortymentu.DaneDomyslne`
— potwierdzone diagnostycznie na żywej Sferze (tymczasowy tryb
`diag-komplet` w `Program.cs`, usunięty po potwierdzeniu):

```
Wlasciwosci DaneDomyslne: Towar_Id, Usluga_Id, Komplet_Id, Opakowanie_Id,
Oplata_Id, Towar, Usluga, Komplet, Opakowanie, Oplata, DefaultData, DefaultDataIds
```

Po naprawie: pełny test `kartoteki → komplet Z (2 składniki) → ZK`
przeszedł bez błędów (`ZK 6/CENTRALA/2026`, kod wyjścia 0).

**Status:** zmiana w working tree, NIE scommitowana — czeka na decyzję
użytkownika o commicie (patrz [[feedback_git_push]]).

---

## ✅ 2026-09-03: środowisko gotowe, test dymny UDANY (kod wyjścia 0)

Subiekt przy pierwszym uruchomieniu sam założył gotową firmę
demonstracyjną: **`RMPRODUKCJA`** → baza SQL **`Nexo_RMPRODUKCJA`**
(potwierdzone przez `sqlcmd -S .\INSERTNEXO -E -Q "SELECT name FROM sys.databases"`).
Operator: login **`Szef`**.

Finalny `C:\RMPAK_CLIENT\.nexo_sfera.json` (Windows Auth, bo działa
od razu bez zgadywania hasła `sa`):

```json
{
  "serwer": ".\\INSERTNEXO",
  "baza": "Nexo_RMPRODUKCJA",
  "sqlWindowsAuth": true,
  "sqlUser": null,
  "sqlHaslo": null,
  "nexoLogin": "Szef",
  "nexoHaslo": "***",
  "sdkBin": "C:\\iLogic\\Subiekt_nexo_PRO_dokumentacja\\SDK\\Bin\\"
}
```

**Test dymny w dwóch krokach:**
1. Celowo złe `nexoHaslo` → kod wyjścia `3`, komunikat "logowanie
   operatora nexo 'Szef' nie powiodło się" — potwierdza że `Polacz`
   (SQL, sieć, licencja PRO, wersja SDK=wersja bazy) przeszedł, padło
   dopiero logowanie.
2. Prawdziwe hasło → kod wyjścia `0`, pełny odczyt: 4 magazyny (MAG/MAP/OUT/GAL),
   29 kartotek (dane demo InsERT — kosmetyki/perfumy, nie prawdziwe RM-y),
   54 kontrahentów, dokumenty ZD/PZ/WZ z pozycjami.

**Wniosek:** cały łańcuch Sfera→sieć→SQL→licencja→logowanie działa
na M-OLD identycznie jak w firmie. Środowisko gotowe do dalszych
testów `NexoRecon.exe projekt` / `subiekt_projekt.py` na danych demo,
bez ryzyka dla firmowej bazy `192.168.100.4` (patrz [[project_subiekt_integracja_m_old]]
w pamięci — dane rozdzielone, kod wspólny przez git).

---

## Stan na 2026-09-03 wieczór (aktualizacja po 2. próbie)

### ✅ Instalacja SQL Server + InsERT nexo + Serwer Urządzeń Zewnętrznych — UDANA

Po restarcie (błąd "pending reboot" opisany niżej) zombie proces `setup`
(PID sprzed restartu, 0s CPU, bez widocznego okna) trzeba było zabić
ręcznie (`Stop-Process -Force`) i odpalić `InsERT_nexo.exe` z Downloads
jeszcze raz. Druga próba przeszła "Instalacja standardowa" do końca,
3/3 kroki. Potwierdzone stanem usług:

```
MSSQL$INSERTNEXO         Running   SQL Server (INSERTNEXO)
SQLAgent$INSERTNEXO      Stopped   SQL Server Agent (INSERTNEXO)   -- normalne, Agent nie jest potrzebny
SQLBrowser                Running   SQL Server Browser
SQLTELEMETRY$INSERTNEXO  Running   SQL Server CEIP service
InsERTDevicesService      Running   InsERT Serwer Urządzeń Zewnętrznych (usługa)
```

Rejestr `HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL`
potwierdza instancję: **`INSERTNEXO` → `MSSQL15.INSERTNEXO`**.
Czyli `serwer` w configu to **`.\INSERTNEXO`** (localhost, nazwana
instancja) — zgodnie z przewidywaniem z pierwszej notatki.

**Wersje zainstalowane (z rejestru Uninstall):**
- InsERT nexo: **`61.1.0.9431`**
- InsERT Serwer Urządzeń Zewnętrznych: `19.2.9226.0`

Wersja InsERT nexo **zgadza się dokładnie** z pobranym SDK
(`nexoSDK_61.1.0.9431`) — nie trzeba dociągać innej wersji SDK.

Po instalacji Windows poprosił o **kolejny restart** (finalizacja,
nie błąd — usługi już były `Running` przed tym komunikatem). Do
zrobienia przed dalszymi krokami (zakładanie podmiotu w Subiekcie,
`.nexo_sfera.json`, test dymny).

---

## Przebieg pierwszej próby (dla historii — SQL padł, potem naprawione)

### Zrobione

1. **nexo SDK pobrane i rozpakowane**, wersja `61.1.0.9431` — **ta sama**
   co na firmowym komputerze. Link (bez logowania, sprawdzony w planie
   02.09.2026):
   ```
   https://ftp.insert.com.pl/pub/demo/InsERT_nexo/nexoSDK.exe
   ```
   Rozpakowane do `C:\iLogic\Subiekt_nexo_PRO_dokumentacja\SDK\` —
   **uwaga**: `nexoSDK.exe -o"..." -y` tworzy dodatkowy podkatalog
   `SDK\nexoSDK_61.1.0.9431\` ze środkiem (`Bin`, `Narzedzia`, ...).
   Trzeba przenieść zawartość o poziom wyżej, żeby ścieżki w
   `NexoRecon.csproj` (`SDK\Bin\`, `SDK\Narzedzia\`) się zgadzały.
   Też trzeba `Unblock-File` na `nexoSDK.exe` przed uruchomieniem
   (Windows blokuje pliki pobrane z sieci).

2. **dotnet SDK 8 doinstalowany** (`dotnet --list-sdks` pokazywał tylko
   runtime 8.0.30, brakowało SDK). Przez winget:
   ```
   & "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe" install --id Microsoft.DotNet.SDK.8 -e
   ```
   (`winget` nie był w PATH tej sesji PowerShell — trzeba pełnej ścieżki).
   Zainstalowana wersja: `8.0.424`.

3. **Build `NexoRecon.exe` udany**, zero błędów/ostrzeżeń:
   ```
   cd subiekt_sfera\NexoRecon
   dotnet build -c Release -nowarn:MSB3277
   ```
   Wynik w `bin\Release\` (~549 MB, >500 plików, zgodnie z README).

### Zablokowane — instalacja SQL Server nie powiodła się

Instalator `InsERT nexo 61.1.0` (Subiekt PRO demo) próbuje postawić
**SQL Server 2019 Express**, instancja nazwana **`INSERTNEXO`**.
Padło na etapie `Database Engine Services` + `SQL Server Replication`:

```
Component name:      Microsoft ODBC Driver for SQL Server
Error description:   A previous installation required a reboot of the
                      machine for changes to take effect. To proceed,
                      restart your computer and then run Setup again.
```

Log: `C:\Program Files\Microsoft SQL Server\150\Setup Bootstrap\Log\Summary.txt`

**Przyczyna:** zaległy restart w kolejce Windows Installer (prawdopodobnie
domino po instalacji dotnet SDK/winget tego samego wieczoru — nie musi
być powiązane, ale zbieżność czasowa). Nic wspólnego z SDK/buildem, które
są już gotowe i nie wymagają powtórki.

**Co przeszło mimo błędu:** SQL Browser, SQL Writer, SQL Client
Connectivity SDK, SQL Client Connectivity.

**Następny krok:** zrestartować komputer, uruchomić instalator InsERT
nexo ponownie — bootstrapper SQL powinien wznowić się i dokończyć
`SQLEngine`/`Replication` bez ponownego pobierania.

## Ustalone parametry pod przyszły `.nexo_sfera.json`

Z `ConfigurationFile.ini` widocznego w logu (`User Input Settings`),
**potwierdzone rejestrem po udanej instalacji**:

| pole configu | wartość |
|---|---|
| `serwer` | `.\INSERTNEXO` (instancja `INSERTNEXO` na localhost) — ✅ potwierdzone w rejestrze |
| `baza` | nieznana jeszcze — powstanie dopiero po założeniu podmiotu w Subiekcie (prefiks `Nexo_` doklei się automatycznie) |
| `sqlWindowsAuth` | `false` da się użyć — `SECURITYMODE: SQL` (tryb mieszany), `sa` ma ustawione hasło (`SAPWD`, zamaskowane w logu — trzeba będzie znać/ustawić) |
| `sqlUser` | `sa` |
| collation | `Polish_CI_AS` |
| `sdkBin` | `C:\iLogic\Subiekt_nexo_PRO_dokumentacja\SDK\Bin\` (tak samo jak firmowy) |

**Uwaga do testu dymnego:** przy Windows Auth nie ma gdzie wstawić
"celowo złego hasła" na poziomie SQL — trzeba by testować złe hasło
na poziomie `nexoLogin`/`nexoHaslo` (operator nexo, kod wyjścia `3`
z `Program.cs`), co i tak dowodzi więcej (że SQL+licencja+Sfera
przeszły, tylko login padł). Z `sa` (`sqlWindowsAuth: false`) można
testować też złe hasło SQL (kod wyjścia `2`, błąd w `Polacz`).

## Do zrobienia (stan na teraz)

1. ~~Dokończyć instalację SQL Server + InsERT nexo + Serwer Urządzeń
   Zewnętrznych.~~ ✅ zrobione (2. próba, po restarcie i zabiciu
   zombie procesu instalatora)
2. ~~Sprawdzić realną nazwę serwera/instancji w rejestrze~~ ✅
   potwierdzone: `.\INSERTNEXO`
3. ~~Sprawdzić wersję zainstalowanej bazy Subiekta vs wersja SDK~~ ✅
   obie `61.1.0.9431` — zgadza się, nic do pobrania
4. **Zrobić kolejny restart** (Windows poprosił po zakończeniu
   instalacji — finalizacja, nie błąd)
5. Założyć podmiot w Subiekcie (żeby powstała nazwa bazy `Nexo_...`)
6. Zbudować `.nexo_sfera.json` z realnymi wartościami (kopia wzoru
   `nexo_sfera.example.json`, docelowo `C:\RMPAK_CLIENT\.nexo_sfera.json`
   — poza repo, w `.gitignore`)
7. Test dymny: celowo złe hasło, potwierdzić że `Polacz`/logowanie
   operatora reaguje zgodnie z tabelką błędów w [`README.md`](README.md)

## Osobno: czytelna dokumentacja SDK (Fable, firmowy komputer)

Na firmowym komputerze istnieje ~1 GB przerobionej/czytelnej wersji
dokumentacji SDK (wygenerowanej wcześniej przez agenta Fable). Nie ma
do niej dostępu zdalnego z domu — użytkownik przeniesie ją fizycznie
(USB/dysk) przy najbliższej wizycie w firmie. Nie odtwarzano jej tutaj
od zera — na razie pracujemy na surowej dokumentacji z paczki SDK
(pliki `.chm`/`.pdf`/`.htm` w `C:\iLogic\Subiekt_nexo_PRO_dokumentacja\SDK\`).
