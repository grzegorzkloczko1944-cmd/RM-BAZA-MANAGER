# RM_BAZA ↔ Subiekt nexo PRO — plan stałego mostu Sfera

## Cel dokumentu

Ten plik jest instrukcją dla agenta programistycznego, który ma przebudować obecną komunikację RM_BAZA z Subiektem nexo PRO tak, aby zlikwidować około **9–10 s narzutu na każde uruchomienie `NexoRecon.exe`**.

Najważniejszy cel:

> **Nie uruchamiać i nie logować Sfery od nowa przy każdym kliknięciu w RM_BAZA.**
> Na każdym komputerze użytkownika ma działać **jeden lokalny, stale uruchomiony proces mostu**, który loguje się do Sfery raz i obsługuje kolejne żądania z RM_BAZA przez tę samą sesję.

Nie należy przy okazji przebudowywać logiki biznesowej zamówień, magazynu, projektów itd. Pierwszy etap ma dotyczyć przede wszystkim **transportu, cyklu życia sesji Sfery i wspólnej warstwy wywołań**.

---

---

# 0. Stan realizacji (06.09.2026)

Kroki **A–J zrobione** na branchu `most-server` (7 commitów, niescalone z `main`).

## Co powstało

| Plik | Rola |
|---|---|
| `subiekt_sfera/NexoRecon/NexoSession.cs` | cykl życia sesji: `Connect` / `Reconnect` / `CzyZywa` |
| `subiekt_sfera/NexoRecon/CommandDispatcher.cs` | mapa tryb → handler, wspólna dla CLI i servera |
| `subiekt_sfera/NexoRecon/ServerHost.cs` | `NexoRecon.exe server`: TCP, kolejka, jeden worker |
| `subiekt_sfera/NexoRecon/Rozpoznanie.cs` | domyślny tryb raportu, przeniesiony z `Program.cs` |
| `subiekt_bridge.py` | klient: `call()`, `wywolaj()`, autostart, fallback |
| `subiekt_sfera/bridge_test.py` | klient testowy (`python bridge_test.py bench`) |

Handlery (`Stan.cs`, `Katalog.cs`, …) **nie były zmieniane** — server materializuje
plik tymczasowy na `--out` i przechwytuje `Console.Out`, więc kontrakt „plan
z pliku, JSON do pliku" został nienaruszony.

## Pomiary (baza demo M-OLD, 247 kartotek)

| Komenda | Stare CLI | Most |
|---|---:|---:|
| katalog (2. i kolejne) | ~13 500 ms | **8–50 ms** |
| kontrahenci | 14 368 ms | **104 ms** |
| stan | 14 135 ms | **296 ms** |
| stan-pozycji | 13 951 ms | **233 ms** |
| magazyn | 14 218 ms | **753 ms** |
| dokumenty | 14 343 ms | **873 ms** |

Jedno logowanie do Sfery na wszystkie komendy. Dane porównane ze starą ścieżką —
identyczne. **To nie jest benchmark z sekcji 33** — ten trzeba powtórzyć w firmie
na 3444 kartotekach.

## Czego NIE zrobiono

- **Krok L: prawdziwe zapisy przez most są przetestowane tylko częściowo.**
  Potwierdzone na demo: **RW** (`RW 1/MAG/2026`, stan 259 → 258). Reszta
  (`zd`, `kartoteka`, `dostawcy`, `projekt`, `termin`, `zd-usun`) sprawdzona
  wyłącznie w trybie podglądu (`zapisz=False`).
- Benchmark z sekcji 33 w firmie.
- Cache (sekcja 20) — po pomiarach wygląda na zbędny, ale decyzja dopiero
  po benchmarku firmowym.
- Token lokalny (sekcja 12) — do rozważenia przed wdrożeniem na wszystkie
  stanowiska.

## Pułapki wykryte przy wdrożeniu

**Tryb server padał natychmiast pod `DETACHED_PROCESS`.** Bez konsoli
`Console.OutputEncoding = Encoding.UTF8` rzuca `IOException` i proces ginął
z `0xE0434352`, **zanim cokolwiek zdążył zalogować**. Ręcznie z konsoli działał
bez zarzutu, więc błąd ujawniłby się dopiero u użytkownika. Dlatego każdy
komunikat w `ServerHost` idzie przez `Powiedz()`, które zawsze pisze też do logu.

**Most blokuje plik `NexoRecon.exe`.** Przed `dotnet build` trzeba go zatrzymać:

```
python -c "import subiekt_bridge as b; b.zatrzymaj_most()"
```

To nowa konsekwencja stałego procesu — wcześniej proces kończył się sam.

**Kolizja nazw `Magazyn`.** Encja SDK vs handler `Magazyn.cs`: wewnątrz
`namespace NexoRecon` wygrywa handler. `Rozpoznanie.cs` używa aliasu
`MagazynSfera`.

## Powrót do starego mostu

```
git checkout main
cd subiekt_sfera\NexoRecon\bin\Release
copy NexoRecon.dll.dziala-20260906 NexoRecon.dll
copy NexoRecon.exe.dziala-20260906 NexoRecon.exe
```

Kopia binarki leży poza gitem, w `bin/Release`.

## Do ustalenia przed wdrożeniem w firmie

Most loguje się kontem z `C:\RMPAK_CLIENT\.nexo_sfera.json`. Sekcja 2 zakłada,
że każde stanowisko używa **swojego** operatora nexo — jeśli w firmie wszystkie
stanowiska mają ten sam plik konfiguracyjny, dokumenty będą wystawiane na jedno
konto. Do sprawdzenia.

---

# 1. Stan obecny

RM_BAZA jest aplikacją Python/Tkinter. Komunikacja z Subiektem odbywa się przez most C#:

```text
RM_BAZA (Python)
    |
    | subprocess.run(...)
    v
NexoRecon.exe (.NET 8 x64)
    |
    v
Sfera nexo
    |
    v
Subiekt nexo PRO / baza SQL
```

Obecny most jest praktycznie bezstanowy:

1. Python przygotowuje plik wejściowy JSON / TXT w `%TEMP%`.
2. Python uruchamia `NexoRecon.exe` z odpowiednim trybem.
3. `NexoRecon.exe` startuje.
4. Łączy się i loguje do Sfery.
5. Wykonuje jedno zadanie.
6. Zapisuje wynik do pliku JSON.
7. Proces kończy się.
8. Następne kliknięcie uruchamia cały cykl ponownie.

W wielu modułach występuje obecnie bezpośrednie:

```python
subprocess.run([exe, "tryb", ...])
```

Przykładowe moduły:

- `subiekt_stany.py`
- `subiekt_dokumenty_gui.py`
- `subiekt_magazyn_gui.py`
- `subiekt_zamowienia.py`
- `subiekt_projekt.py`
- `subiekt_dostawcy.py`
- `subiekt_asortyment.py`
- `subiekt_wyslij_zd.py`
- `subiekt_podobne.py`

## Obserwowane czasy

Z komentarzy i pomiarów w aktualnym kodzie:

- start / pojedyncze proste wywołanie mostu: około **9–10 s**,
- pobranie około **3444 kartotek**: około **9 s**, czyli niemal tyle samo co sam start mostu,
- przegląd dokumentów: około **9 s**,
- magazyn z pełnymi stanami około **794 pozycji**: około **15–16 s**,
- generowanie PDF ZD: około **11 s**.

Wniosek:

> Dla dużej części operacji dominującym kosztem nie jest sama operacja w Subiekcie, tylko ciągłe uruchamianie procesu i zestawianie sesji Sfery.

---

# 2. Docelowa architektura

Każdy komputer użytkownika ma mieć **swój własny lokalny most**.

Przy 10 użytkownikach:

```text
PC USER1
RM_BAZA -> lokalny NexoRecon server -> Sfera USER1

PC USER2
RM_BAZA -> lokalny NexoRecon server -> Sfera USER2

...

PC USER10
RM_BAZA -> lokalny NexoRecon server -> Sfera USER10
```

Nie tworzyć jednego centralnego serwera Sfery dla wszystkich użytkowników w pierwszej wersji.

Powody:

- każdy użytkownik ma własne konto/licencję,
- każdy komputer ma własną sesję Sfery,
- awaria jednego mostu nie zatrzymuje firmy,
- brak centralnej kolejki 10 użytkowników,
- prostsza diagnostyka,
- prostsze uprawnienia,
- krótsza droga komunikacji,
- łatwiej zachować zgodność z obecną konfiguracją per stanowisko.

## Ważne założenie wdrożeniowe

Lokalny bridge powinien logować się do Sfery tym samym użytkownikiem nexo, którego używa operator na danym stanowisku.

Nie projektować wspólnego konta typu `ADMIN` dla wszystkich mostów.

---

# 3. Co ma działać na każdym komputerze

Docelowo:

```text
RM_BAZA.exe / Python
    |
    | lokalny klient
    v
subiekt_bridge.py
    |
    | TCP 127.0.0.1
    v
NexoRecon.exe server
    |
    | jedna żywa sesja
    v
Sfera nexo
```

Proces `NexoRecon.exe server`:

- uruchamia się raz,
- loguje do Sfery raz,
- utrzymuje sesję,
- czeka na kolejne komendy,
- wykonuje je kolejno,
- odpowiada JSON-em,
- pozostaje uruchomiony.

RM_BAZA nie powinno wymagać od użytkownika ręcznego uruchamiania bridge'a.

---

# 4. Nie tworzyć osobnego programu, jeśli nie trzeba

Najlepiej zachować **jeden `NexoRecon.exe`** i dodać mu nowy tryb:

```text
NexoRecon.exe server
```

Obecne tryby CLI mają nadal działać:

```text
NexoRecon.exe stan ...
NexoRecon.exe katalog ...
NexoRecon.exe dokumenty ...
NexoRecon.exe projekt ...
...
```

Dzięki temu:

- zachowujemy kompatybilność,
- można łatwo wrócić do starego trybu,
- CLI pozostaje narzędziem diagnostycznym,
- migracja Pythona może być stopniowa.

Docelowa struktura C# powinna oddzielić:

```text
Program / argumenty CLI
        |
        v
CommandDispatcher
        |
        v
wspólne handlery komend
        |
        v
BridgeSession / Sfera
```

Dwa hosty korzystają z tych samych handlerów:

```text
CliHost      -> wykonaj jedną komendę -> zakończ proces
ServerHost   -> wykonuj wiele komend -> proces stale żywy
```

Nie duplikować logiki biznesowej między trybem CLI i server.

---

# 5. Transport Python ↔ C#

## Zalecenie: TCP tylko na localhost

Dla pierwszej wersji użyć:

```text
127.0.0.1:51273
```

Powody:

- Python ma `socket` w bibliotece standardowej,
- C# ma `TcpListener`,
- brak dodatkowych zależności,
- łatwe debugowanie,
- działa niezależnie od nazw użytkowników Windows,
- port jest dostępny tylko lokalnie, jeśli listener binduje wyłącznie `IPAddress.Loopback`.

Nie binduj:

```text
0.0.0.0
```

Nie wystawiać bridge'a do LAN.

Named Pipe jest również dobrym rozwiązaniem, ale TCP localhost będzie prostsze do wdrożenia i debugowania przy obecnym Pythonie.

---

# 6. Protokół

Zastosować prosty protokół JSON request/response.

Nie używać JSON rozdzielanego samym newline, jeśli odpowiedzi mogą kiedyś zawierać nietypowe dane.

Najprościej:

```text
4 bajty długości little-endian
+
UTF-8 JSON
```

Przykładowe żądanie:

```json
{
  "protocol": 1,
  "request_id": "bdbebdc4-58fe-4b18-84c8-45c7ab04171b",
  "command": "stan",
  "args": {
    "symbols": [
      "2627-100.01",
      "2627-100.02"
    ]
  }
}
```

Odpowiedź:

```json
{
  "protocol": 1,
  "request_id": "bdbebdc4-58fe-4b18-84c8-45c7ab04171b",
  "ok": true,
  "duration_ms": 184,
  "data": {
    "pozycje": []
  }
}
```

Błąd:

```json
{
  "protocol": 1,
  "request_id": "bdbebdc4-58fe-4b18-84c8-45c7ab04171b",
  "ok": false,
  "error": {
    "code": "SESSION_LOST",
    "message": "Utracono sesję Sfery",
    "retryable": true
  }
}
```

---

# 7. Komendy, które obecnie trzeba obsłużyć

Agent ma przejrzeć aktualny kod C# i zachować wszystkie istniejące tryby.

Z Pythona obecnie widać co najmniej:

```text
ping                  NOWE
status                NOWE

stan
stan-pozycji
katalog
dokumenty
magazyn
kontrahenci
zapotrzebowanie

kartoteka
kartoteka-usun

projekt

zd
zd-usun

progi
rw

dostawcy

wydruk
termin
```

Agent ma przeszukać całe repozytorium `NexoRecon` i upewnić się, że nie pominięto żadnego trybu.

---

# 8. Najważniejsza zasada: jedna sesja Sfery, jeden worker

Nie wykonywać kilku operacji Sfery równolegle na jednej sesji.

RM_BAZA ma GUI wielookienkowe i obecnie uruchamia wiele `threading.Thread`, więc kilka okien może jednocześnie poprosić bridge o dane.

Po stronie bridge'a zrobić:

```text
klient 1 ----\
klient 2 -----\
klient 3 ------> kolejka -> JEDEN worker Sfery -> odpowiedź
klient 4 -----/
```

## Dlaczego

Nie zakładać, że obiekty Sfery są bezpieczne wielowątkowo.

Najbezpieczniej:

- sesja jest tworzona przez jeden dedykowany worker,
- wszystkie wywołania Sfery wykonuje ten sam worker,
- żądania są serializowane,
- listener TCP nie dotyka bezpośrednio obiektów Sfery.

Przykładowo w C#:

```text
TcpListener
    |
    v
Request objects
    |
    v
BlockingCollection<Request>
    |
    v
SferaWorker Thread
    |
    v
CommandDispatcher
```

Każdy request posiada `TaskCompletionSource<Response>` albo podobny mechanizm oczekiwania na wynik.

---

# 9. Cykl życia bridge'a

## Start RM_BAZA

Python:

1. robi `ping`,
2. jeśli bridge odpowiada -> używa go,
3. jeśli nie odpowiada -> uruchamia:

```text
NexoRecon.exe server
```

4. czeka maksymalnie np. 15–20 s na `ready`,
5. jeśli bridge się nie uruchomi -> pokazuje czytelny błąd albo używa starego fallbacku CLI.

Schemat:

```text
RM_BAZA
  |
  +-- ping bridge
       |
       +-- działa -> gotowe
       |
       +-- nie działa
              |
              +-- start NexoRecon.exe server
              |
              +-- czekaj na ping
                     |
                     +-- OK -> gotowe
                     |
                     +-- FAIL -> fallback / komunikat
```

## Zamknięcie RM_BAZA

Nie ma potrzeby automatycznie zabijać bridge'a.

Bridge może działać cały dzień.

Opcjonalnie później:

- timeout bezczynności np. 2–4 h,
- albo proces zamykany przy wylogowaniu Windows.

Na początku lepiej pozostawić bridge aktywny do końca sesji Windows.

---

# 10. `ping` i `status`

Dodać dwie komendy diagnostyczne.

## `ping`

Powinna być bardzo lekka i NIE wykonywać zapytania do Subiekta.

Przykład:

```json
{
  "ok": true,
  "data": {
    "ready": true,
    "pid": 12345,
    "bridge_version": "1.0.0",
    "protocol": 1
  }
}
```

## `status`

Może zwracać:

```json
{
  "ready": true,
  "session_connected": true,
  "user": "KOWALSKI",
  "computer": "PC-KOWALSKI",
  "pid": 12345,
  "uptime_s": 18341,
  "queue_length": 0,
  "last_request": "magazyn",
  "last_request_ms": 6124,
  "bridge_version": "1.0.0"
}
```

Nie zwracać haseł ani innych sekretów.

---

# 11. Konfiguracja istniejąca

Obecny Python używa m.in.:

```text
C:\RMPAK_CLIENT\.nexo_sfera.json
```

oraz szuka bridge'a m.in. w:

```text
<repo>\subiekt_sfera\NexoRecon\bin\Release\NexoRecon.exe

C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER\
    subiekt_sfera\NexoRecon\bin\Release\NexoRecon.exe

C:\RMPAK_CLIENT\NexoRecon\NexoRecon.exe
```

Nie rozwalać obecnej konfiguracji.

Tryb server powinien korzystać z tego samego pliku konfiguracyjnego połączenia, co stare CLI.

---

# 12. Bezpieczeństwo lokalnego bridge'a

Minimum:

- bind tylko `127.0.0.1`,
- nie wystawiać portu do sieci,
- nie logować haseł,
- nie przesyłać hasła w każdym request,
- dane logowania są używane tylko przy otwieraniu sesji.

Dodatkowo można dodać lokalny token:

```json
{
  "bridge_token": "losowy_długi_token"
}
```

Klient wysyła go w każdym request.

To chroni przed przypadkowym wywołaniem bridge'a przez inny lokalny proces.

Nie jest to konieczne do pierwszego benchmarku, ale warto dodać przed wdrożeniem na wszystkie stanowiska.

---

# 13. Reconnect Sfery

Stała sesja musi przetrwać realne warunki:

- komputer uśpiony,
- chwilowy brak sieci,
- restart SQL,
- restart serwera,
- chwilowy brak dostępu do bazy,
- Subiekt zamknięty lub otwarty,
- długą bezczynność.

Bridge powinien mieć stan:

```text
STARTING
READY
RECONNECTING
ERROR
STOPPING
```

## Przy błędzie sesji

Schemat:

```text
request
  |
  v
wywołanie Sfery
  |
  +-- OK -> odpowiedź
  |
  +-- błąd sesji
          |
          +-- zamknij starą sesję
          +-- utwórz nową
          +-- zaloguj ponownie
          +-- READY
```

---

# 14. Bardzo ważne: retry READ vs WRITE

Nie wolno bezmyślnie automatycznie powtarzać operacji zapisujących.

## Operacje odczytu

Przykłady:

```text
stan
katalog
dokumenty
magazyn
kontrahenci
zapotrzebowanie
stan-pozycji
```

Jeżeli sesja zerwie się przed wykonaniem, można:

1. reconnect,
2. ponowić request raz.

## Operacje zapisu

Przykłady:

```text
kartoteka
projekt
zd
zd-usun
progi
rw
dostawcy
termin
kartoteka-usun
```

Jeżeli połączenie zerwie się w trakcie zapisu, bridge może nie wiedzieć, czy operacja:

- nie została wykonana,
- została wykonana,
- została wykonana częściowo.

Nie robić automatycznego retry bez weryfikacji.

Zwrócić błąd typu:

```text
UNKNOWN_COMMIT_STATE
```

i pozwolić logice konkretnego handlera sprawdzić stan w Subiekcie.

Przykład:

- `kartoteka` może sprawdzić, czy symbol już istnieje,
- `zd` może sprawdzić dokument po znanym identyfikatorze / danych,
- `termin` można odczytać i porównać,
- `projekt` wymaga szczególnej ostrożności.

---

# 15. `request_id` i idempotency

Każdy request ma mieć UUID:

```text
request_id
```

Dla zapisów warto dodać:

```text
operation_id
```

Bridge powinien logować:

```text
operation_id
command
user
start
end
status
```

W późniejszym etapie można zrobić trwały lokalny journal ostatnich operacji i dzięki temu bezpiecznie odpowiadać na powtórzony request.

Nie jest to warunek MVP, ale architektura nie powinna tego blokować.

---

# 16. Nowy `subiekt_bridge.py`

Stworzyć jeden wspólny moduł klienta po stronie Pythona.

Przykładowe API:

```python
import subiekt_bridge as bridge

data = bridge.call(
    "stan",
    {"symbols": symbole},
    timeout=180,
)

data = bridge.call(
    "dokumenty",
    {"limit": 200},
    timeout=300,
)

data = bridge.call(
    "zd",
    {
        "pozycje": pozycje,
        "uwagi": uwagi,
    },
    timeout=300,
    write=True,
)
```

Moduł ma odpowiadać za:

- ping,
- autostart bridge'a,
- połączenie TCP,
- framing,
- JSON encode/decode,
- timeout,
- jednolity format błędów,
- wersję protokołu,
- fallback CLI.

Dzięki temu moduły GUI nie wiedzą już, czy komunikacja idzie przez proces stały czy stary subprocess.

---

# 17. Fallback do starego mechanizmu

Na czas migracji zachować:

```text
server -> preferred
CLI subprocess -> fallback
```

Przykład:

```python
def call(command, args, timeout, write=False):
    try:
        return _call_server(command, args, timeout)
    except BridgeUnavailable:
        return _call_legacy_cli(command, args, timeout)
```

Uwaga:

Fallback najlepiej stosować tylko wtedy, gdy bridge **nie wystartował**.

Jeżeli bridge działał i w trakcie zapisu zgłosił niejednoznaczny błąd, nie uruchamiać automatycznie tej samej operacji drugi raz przez CLI.

---

# 18. Minimalizacja zmian w obecnych modułach

Nie przepisywać całych GUI.

Przykład obecny:

```python
proc = subprocess.run(
    [exe, "dokumenty", f"--limit={limit}", f"--out={out}"],
    ...
)
```

Docelowo:

```python
from subiekt_bridge import call

data = call(
    "dokumenty",
    {"limit": limit},
    timeout=TIMEOUT_S,
)
```

Reszta funkcji:

- transformacja danych,
- GUI,
- filtry,
- tksheet,
- komunikaty,

powinna pozostać praktycznie bez zmian.

---

# 19. Kolejność migracji modułów

Najpierw migrować odczyty, bo są bezpieczne i łatwe do benchmarku.

## Etap 1 — diagnostyka

```text
ping
status
```

## Etap 2 — proste READ

```text
katalog
stan
kontrahenci
dokumenty
```

## Etap 3 — cięższe READ

```text
magazyn
zapotrzebowanie
stan-pozycji
```

Po tym etapie zrobić pomiary.

## Etap 4 — WRITE o małym ryzyku

```text
termin
progi
kartoteka
dostawcy
```

## Etap 5 — dokumenty

```text
zd
rw
projekt
zd-usun
kartoteka-usun
```

## Etap 6 — wydruk

```text
wydruk
```

---

# 20. Cache — dopiero po uruchomieniu stałego bridge'a

Nie zaczynać projektu od cache.

Najpierw usunąć koszt startu i ponownie zmierzyć.

Po zmianie prawdopodobnie część operacji będzie wystarczająco szybka bez cache.

Jeżeli nadal trzeba:

## Kandydaci do cache

```text
katalog             5–10 min
kontrahenci          5–10 min
lista magazynów      długo
```

## Raczej zawsze na żywo

```text
stan
magazyn
zapotrzebowanie
dokumenty
ZD
RW
termin
```

Po zapisie kartoteki można zaktualizować cache przyrostowo zamiast kasować cały.

---

# 21. Oczekiwany efekt wydajnościowy

Nie wpisywać na sztywno gwarantowanych czasów.

Założenie do zweryfikowania benchmarkiem:

## Katalog

Obecnie:

```text
~9 s dla ~3444 kartotek
```

Jeżeli prawie cały czas to start/logowanie Sfery, po zmianie operacja może zejść do wartości bliskiej samemu czasowi pobrania danych.

## Dokumenty

Obecnie około:

```text
~9 s
```

Powinien zniknąć prawie cały koszt inicjalizacji.

## Magazyn

Obecnie:

```text
~15–16 s
```

Jeżeli około 9–10 s to start, pozostanie około kilku sekund realnej pracy Sfery.

Nie zakładać wyników — zmierzyć osobno:

```text
queue_wait_ms
session_check_ms
handler_ms
serialization_ms
total_ms
```

---

# 22. Logowanie wydajności

Bridge powinien pisać lokalny log, np.:

```text
C:\RMPAK_CLIENT\subiekt_logi\bridge_YYYYMMDD.log
```

Przykład:

```text
2026-09-05 14:23:01
user=JAN
cmd=magazyn
request_id=...
queue_wait=12ms
handler=5821ms
serialize=42ms
total=5875ms
status=OK
```

Dla reconnect:

```text
session_lost
reconnect_start
reconnect_ok
reconnect_ms=9421
```

Dzięki temu będzie wiadomo, czy problemem jest:

- kolejka,
- Sfera,
- baza SQL,
- serializacja,
- sam bridge.

---

# 23. Uruchamianie bridge'a

Preferowany wariant:

RM_BAZA sama uruchamia proces:

```python
subprocess.Popen(
    [exe, "server"],
    creationflags=...,
)
```

Bridge nie powinien otwierać konsoli użytkownikowi.

Można zastosować:

```text
CREATE_NO_WINDOW
DETACHED_PROCESS
```

z zachowaniem możliwości diagnostycznego uruchomienia ręcznego:

```text
NexoRecon.exe server --console
```

---

# 24. Jeden bridge na komputer

Przed uruchomieniem serwera musi być blokada przed podwójnym startem.

Możliwości:

- Windows named mutex,
- próba zajęcia portu,
- mutex + port.

Najlepiej:

```text
Global\RMPAK_NEXO_BRIDGE_<username>
```

lub lokalny mutex per użytkownik Windows.

Jeżeli drugi proces wystartuje:

```text
Bridge already running.
```

i kończy się.

---

# 25. Wersjonowanie

`ping` powinien zwracać:

```text
bridge_version
protocol_version
```

Python powinien znać minimalną zgodną wersję.

Przykład:

```text
Python wymaga protocol >= 1
```

Jeżeli po `git pull` Python jest nowszy niż bridge, użytkownik ma dostać czytelny komunikat.

Obecny kod już wykrywa sytuację, gdy `NexoRecon.exe` jest starszy niż źródła C# — zachować ten mechanizm lub zastąpić go jeszcze lepszym handshake wersji.

---

# 26. Istniejący problem starej binarki po `git pull`

Aktualny kod ma ochronę na przypadek:

- źródła `.cs` zostały zaktualizowane,
- `bin/Release` nie idzie przez git,
- stary `NexoRecon.exe` nie zna nowego trybu.

Nowy bridge powinien mieć jawny numer wersji/protokołu, dzięki czemu zamiast zgadywać po timestampach będzie można zrobić:

```text
client: protocol=2
server: protocol=1
=> BRIDGE_OUTDATED
```

To będzie pewniejsze.

---

# 27. Obsługa wielu okien RM_BAZA

Przykład:

```text
Okno Magazyn        -> request A
Okno Dokumenty      -> request B
Okno Zamówienia     -> request C
```

GUI nadal może działać asynchronicznie.

Bridge kolejkowuje:

```text
A -> B -> C
```

Każde okno dostaje swój wynik po zakończeniu.

Dobrze zwracać w statusie:

```text
queue_length
current_command
```

Można dzięki temu w GUI kiedyś pokazać:

```text
Subiekt zajęty: magazyn (4.2 s), oczekujące: 2
```

Nie jest to wymagane w pierwszym etapie.

---

# 28. Priorytety kolejki

Na początku zwykłe FIFO.

Nie komplikować.

W przyszłości można rozważyć:

```text
ping/status -> natychmiast
krótkie odczyty -> normalne
ciężkie eksporty PDF -> niskie
```

Ale MVP ma być prosty.

---

# 29. Wydruk PDF

`wydruk` może być dłuższą operacją.

Nie uruchamiać osobnej sesji tylko do PDF.

Powinien iść przez ten sam worker.

Jeżeli kiedyś wydruk okaże się blokujący na długo, dopiero wtedy rozważyć osobny mechanizm.

Najpierw benchmark.

---

# 30. Nie mieszać tej przebudowy z logiką GUI

Agent ma uważać, żeby przy okazji nie przebudowywać:

- sposobu liczenia zapotrzebowania,
- mapowania dostawców,
- tworzenia ZD,
- zasad Z/ZZ,
- locków projektu,
- oznaczania Zamówiono,
- scalania BOM,
- wysyłki plików.

Te mechanizmy mają osobne ryzyka biznesowe.

Projekt stałego bridge'a ma być możliwie izolowany.

---

# 31. Ważne istniejące mechanizmy, których nie wolno zepsuć

## Globalne mapowanie numer rysunku -> kartoteka

`subiekt_mapowania.py`

Ręczne mapowanie ma pierwszeństwo przed automatem.

## Lock projektu

Operacje na BOM przy przejętym projekcie pracują na lokalnej kopii i dopiero przy zwolnieniu locka wracają na serwer.

Nie wolno zacząć pisać bezpośrednio do baz projektu na serwerze.

## ZD

Tworzenie ZD grupuje po dostawcy i korzysta z danych Subiekta + RM_BAZA.

## Dostawcy

NIP jest kluczem twardym.

Nie pogarszać tego przy przebudowie transportu.

---

# 32. Testy przed wdrożeniem

## Test 1 — start

1. brak bridge'a,
2. start RM_BAZA,
3. RM_BAZA uruchamia server,
4. około 10 s pierwszy login,
5. `ping` OK.

## Test 2 — drugi request

Natychmiast po pierwszym:

```text
katalog
```

Ma nie wystąpić ponowne 9–10 s logowania.

## Test 3 — trzy requesty pod rząd

```text
stan
dokumenty
kontrahenci
```

Sprawdzić log:

```text
reconnect = 0
session_start = 1
```

## Test 4 — dwa okna równocześnie

Jednocześnie:

```text
magazyn
dokumenty
```

Oczekiwane:

- brak crasha,
- brak równoległego dostępu do Sfery,
- jedno czeka w kolejce,
- oba dostają poprawne wyniki.

## Test 5 — utrata sieci

1. bridge READY,
2. odciąć połączenie z serwerem/bazą,
3. wykonać READ,
4. bridge raportuje błąd/reconnect,
5. po przywróceniu sieci odzyskuje sesję.

## Test 6 — write po reconnect

Dla zapisu nie może nastąpić ślepe podwójne wykonanie.

## Test 7 — restart bridge'a

1. zabić `NexoRecon.exe server`,
2. kliknąć odczyt w RM_BAZA,
3. klient wykrywa brak bridge'a,
4. uruchamia ponownie,
5. po loginie operacja działa.

## Test 8 — Subiekt GUI otwarty równocześnie

Na tym samym komputerze:

```text
Subiekt nexo PRO otwarty
+
RM_BAZA
+
NexoRecon server
```

Sprawdzić działanie na realnym użytkowniku stanowiska.

---

# 33. Benchmark obowiązkowy

Przed przebudową zapisać wyniki dla co najmniej:

```text
katalog
stan 1 symbol
stan 100 symboli
dokumenty
kontrahenci
magazyn
zapotrzebowanie
wydruk PDF
```

Każde minimum 3 razy.

Po przebudowie powtórzyć.

Tabela:

| Komenda | Stary cold | Stary kolejne | Server pierwszy | Server kolejne |
|---|---:|---:|---:|---:|
| katalog | | | | |
| stan 1 | | | | |
| stan 100 | | | | |
| dokumenty | | | | |
| kontrahenci | | | | |
| magazyn | | | | |
| zapotrzebowanie | | | | |
| wydruk | | | | |

Dopiero po benchmarku decydować o cache.

---

# 34. Proponowany plan implementacji dla agenta

## Krok A

Przejrzyj całe:

```text
subiekt_sfera\NexoRecon\
```

Znajdź:

- tworzenie połączenia,
- logowanie,
- obiekt kontekstu/Sfery,
- `Main`,
- dispatcher obecnych trybów,
- miejsca `Dispose`,
- zależności między handlerami a argumentami CLI.

## Krok B

Wydziel klasę utrzymującą sesję, np.:

```text
NexoSession
```

Odpowiada za:

```text
Connect()
Disconnect()
Reconnect()
IsAlive
CurrentUser
```

## Krok C

Wydziel:

```text
CommandDispatcher
```

który dostaje:

```text
command
args
session
```

i zwraca obiekt wyniku.

## Krok D

Przepnij istniejące CLI przez dispatcher.

Po tym kroku wszystkie stare komendy muszą nadal działać bez zmiany Pythona.

## Krok E

Dodaj:

```text
ServerHost
```

oraz:

```text
NexoRecon.exe server
```

## Krok F

Dodaj:

```text
ping
status
```

## Krok G

Zrób mały testowy klient Python niezależny od RM_BAZA.

Przykład:

```text
bridge_test.py
```

Komendy:

```text
ping
katalog
stan
```

Najpierw udowodnij, że drugi `katalog` nie powoduje ponownego logowania.

## Krok H

Utwórz produkcyjny:

```text
subiekt_bridge.py
```

## Krok I

Przepnij tylko jeden moduł, najlepiej:

```text
subiekt_podobne.py -> katalog
```

lub inne proste READ.

## Krok J

Przepnij pozostałe READ.

## Krok K

Benchmark.

## Krok L

Dopiero potem przepinaj WRITE.

---

# 35. Kryteria akceptacji MVP

Projekt można uznać za udany, gdy:

1. `NexoRecon.exe server` loguje do Sfery tylko raz.
2. Co najmniej 20 kolejnych requestów działa bez restartu sesji.
3. `katalog` drugi raz nie płaci 9–10 s narzutu startowego.
4. Kilka okien RM_BAZA może wysyłać requesty równocześnie bez błędów.
5. Sfera jest obsługiwana przez jeden worker.
6. Bridge ma `ping`.
7. Bridge ma `status`.
8. RM_BAZA automatycznie uruchamia bridge, gdy go nie ma.
9. Stare tryby CLI nadal działają.
10. Istnieje fallback dla okresu migracji.
11. Log pokazuje czas każdej komendy.
12. Utrata bridge'a nie zawiesza GUI.
13. Błąd zapisu nie powoduje automatycznego, ślepego powtórzenia operacji.
14. Bridge działa niezależnie na każdym komputerze użytkownika.
15. Kod nie wymaga ręcznego klikania przez operatora.

---

# 36. Czego NIE robić

Nie:

- tworzyć jednego bridge'a na serwerze dla wszystkich 10 użytkowników,
- uruchamiać 10 sesji Sfery na jednym centralnym koncie,
- wykonywać równolegle komend Sfery w wielu wątkach jednej sesji,
- automatycznie retry'ować write po niejednoznacznym błędzie,
- wystawiać listenera na LAN,
- usuwać stare CLI przed zakończeniem migracji,
- dodawać cache zanim zmierzymy stałą sesję,
- przepisywać całego GUI,
- mieszać tej zmiany z PZ/KSeF/FZ,
- zmieniać reguł biznesowych RM_BAZA bez potrzeby.

---

# 37. Ostateczny obraz systemu

```text
┌───────────────────────────────────────────────────────────────┐
│                        KOMPUTER USERA                         │
│                                                               │
│  ┌──────────────────┐                                         │
│  │      RM_BAZA     │                                         │
│  │ Python / Tkinter │                                         │
│  └────────┬─────────┘                                         │
│           │                                                    │
│           │ subiekt_bridge.py                                  │
│           │ JSON / TCP localhost                               │
│           v                                                    │
│  ┌──────────────────────────────────────────────┐              │
│  │          NexoRecon.exe server               │              │
│  │                                              │              │
│  │ TcpListener                                  │              │
│  │      │                                       │              │
│  │      v                                       │              │
│  │ Request Queue                                │              │
│  │      │                                       │              │
│  │      v                                       │              │
│  │ ONE Sfera Worker                             │              │
│  │      │                                       │              │
│  │      v                                       │              │
│  │ persistent Nexo / Sfera session              │              │
│  └──────┬───────────────────────────────────────┘              │
│         │                                                      │
│         v                                                      │
│   Subiekt nexo PRO / SQL                                      │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

Przy 10 użytkownikach ten blok istnieje 10 razy, lokalnie na ich komputerach.

Kod jest wspólny, konfiguracja i sesja są per stanowisko.

---

# 38. Najważniejsza myśl projektowa

Obecnie architektura płaci około 10 sekund za inicjalizację przy prawie każdym wywołaniu.

Nie należy optymalizować pojedynczych zapytań o 200–500 ms, dopóki ten koszt istnieje.

Najpierw:

> **utrzymać żywy proces + żywą sesję Sfery i płacić koszt logowania raz na start stanowiska.**

Dopiero po tym mierzyć i decydować, czy potrzebne są:

- cache,
- batchowanie,
- szybsze zapytania,
- specjalne endpointy,
- dodatkowe indeksy,
- prefetch.

To jest główny kierunek przebudowy.
