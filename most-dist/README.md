# most-dist — kopia zapasowa wystawionego mostu

Ten katalog żyje **tylko na gałęzi `most-server`**. Nie jest częścią `main`
i nie ma się z nim scalać — na `main` są źródła (`subiekt_sfera/NexoRecon/*.cs`),
tutaj leży gotowa binarka, którą realnie dostali użytkownicy.

Po co w gicie, skoro dystrybucja idzie inną drogą: żeby dało się odtworzyć,
**co dokładnie mieli userzy danego dnia** — i wrócić do tego, gdyby nowy build
okazał się zepsuty. 590 KB, więc koszt żaden.

## Zawartość

```
NexoRecon.exe                most: tryb server + stare CLI
NexoRecon.dll
NexoRecon.deps.json
NexoRecon.runtimeconfig.json
wersja.json                  protokół, data builda, commit źródła
```

Bez `.pdb` (symbole debug — na stanowiskach zbędne) i bez DLL-i SDK Sfery
(~1,1 GB, leżą w `C:\iLogic\Subiekt\Bin\`, trafiają na stanowisko raz).

## Prawdziwa droga dystrybucji

```
dotnet build  →  C:\iLogic\Subiekt\MOST\  →  serwer  →  panel SUBIEKT → „Pobierz most”
```

Git jest **obok** tego, nie w środku. `subiekt_bridge.py::pobierz_most()`
czyta z folderu sieciowego (`Y:/Z:/X:/V:\RMPAK_CLIENT\Subiekt\MOST` albo
`paths.bridge_dir` w `sync_config.json`), nie z repo.

## Aktualizacja po zmianie w moście

1. Na `main`: zmień `.cs`, zbuduj (`dotnet build -c Release -nowarn:MSB3277`).
   Most musi być zatrzymany, inaczej `MSB3027` — plik zablokowany.
2. Skopiuj wynik do `C:\iLogic\Subiekt\MOST\` i zaktualizuj tam `wersja.json`:
   - `zbudowano` — data i godzina,
   - `sha` — **commit źródła** (`git rev-parse --short HEAD`), po nim odtworzysz kod,
   - `protokol` — tylko gdy zmienił się kontrakt komend (`ServerHost.Protokol`;
     wymaga też podbicia `PROTOKOL_MIN` w `subiekt_bridge.py`).
3. Wgraj `MOST\` na serwer — to jest moment, w którym userzy dostają nową wersję.
4. Dopiero potem, dla kopii: `git checkout most-server`, skopiuj te same pliki
   do `most-dist/`, commit, push.

Kolejność ma znaczenie: git jest zapisem tego, co **już** wystawione, więc nie
commituj tu binarki, której nie ma jeszcze na serwerze.

## Sprawdzenie, czy kopia zgadza się ze źródłem

```
git diff <sha z wersja.json>..main -- subiekt_sfera/NexoRecon/
```

Pusto = binarka odpowiada bieżącym źródłom. Cokolwiek = ktoś zmienił `.cs`
i nie przebudował mostu.
