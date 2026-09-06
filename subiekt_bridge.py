# -*- coding: utf-8 -*-
"""Klient stałego mostu do Subiekta nexo PRO.

Jedno miejsce, przez które RM_BAZA rozmawia z Subiektem. Moduły GUI wołają
`call(...)` i nie muszą wiedzieć, czy dane przyszły przez stały most, czy
przez stare `subprocess.run` — to jest cel tej warstwy.

    import subiekt_bridge as bridge

    dane = bridge.call("katalog")
    dane = bridge.call("stan", {"symbols": symbole})
    dane = bridge.call("zd", {"plan": pozycje, "zapisz": True}, write=True)

Dlaczego to istnieje: do tej pory każde kliknięcie uruchamiało nowy proces
`NexoRecon.exe`, który logował się do Sfery od zera — około 10 s narzutu na
każdą operację. Stały most (`NexoRecon.exe server`) loguje się raz i trzyma
sesję, więc kolejne odczyty schodzą do milisekund.
Szczegóły i uzasadnienie: SUBIEKT_STALY_MOST_PLAN.md.

Moduł sam dba o to, żeby most działał — użytkownik niczego nie uruchamia
ręcznie. Jeśli mostu nie ma, `call()` startuje go w tle i czeka na sesję.
Gdy most nie wstanie, robota leci starym CLI (fallback), więc awaria mostu
nie zatrzymuje pracy.

WAŻNE — zapis vs odczyt (plan, sekcja 14): przy `write=True` moduł NIGDY nie
ponawia operacji po niejednoznacznym błędzie. Powtórzenie zapisu to duplikat
ZD albo kartoteki, a most nie jest w stanie stwierdzić, czy zmiana przeszła.
"""

import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from subiekt_stany import _find_exe, CONFIG_PATH

HOST = "127.0.0.1"
PORT = 51273

#: Minimalna wersja protokołu, z jaką ten klient umie rozmawiać.
#: Po „git pull" Python bywa nowszy niż zbudowana binarka — wtedy zamiast
#: zgadywać po datach plików (most_starszy_niz_zrodla) dostajemy jasną
#: odpowiedź z handshake (plan, sekcje 25–26).
PROTOKOL_MIN = 1

#: Ile czekamy na zalogowanie się mostu do Sfery. Samo logowanie to ~10–15 s,
#: więc margines jest spory — to i tak koszt płacony raz na dzień pracy.
START_TIMEOUT_S = 40

#: Domyślny timeout pojedynczej komendy.
TIMEOUT_S = 180

#: Ustawione na True po nieudanej próbie startu — żeby nie próbować
#: uruchamiać mostu przy każdym kliknięciu, gdy na tym stanowisku
#: coś jest z nim nie tak (brak binarki, zajęty port, błąd licencji).
_most_niedostepny = False
_lock = threading.Lock()

#: Jak czesto wolno zagladac na serwer po nowszy most.
#:
#: To odczyt z DYSKU SIECIOWEGO, a panel Subiekta otwiera sie wiele razy
#: dziennie — sprawdzanie za kazdym razem oznaczaloby staly ruch po Y:
#: dla informacji, ktora zmienia sie moze raz na kilka dni. Raz na dobe
#: wystarczy: most wystawia jedna osoba, planowo (zgloszone 06.09.2026 —
#: "skanowanie ma byc jakies rzadkie, nie co chwila").
SPRAWDZAJ_NOWSZY_CO_S = 24 * 3600

#: Plik ze znacznikiem ostatniego zajrzenia na serwer. NIE zmienna w pamieci:
#: RM_BAZA bywa uruchamiana kilka razy dziennie, a przy zmiennej kazdy start
#: liczylby sie od zera i sprawdzanie wracaloby do "przy kazdym otwarciu".
ZNACZNIK_SPRAWDZENIA = r"C:\RMPAK_CLIENT\.most_sprawdzony"


class BridgeUnavailable(Exception):
    """Mostu nie ma i nie udało się go uruchomić — wołający ma użyć CLI."""


class BridgeError(RuntimeError):
    """Most odpowiedział błędem. `code` niesie kod z protokołu."""

    def __init__(self, message, code=None, retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


# ── transport: 4 bajty długości LE + UTF-8 JSON ─────────────────────────────
def _wyslij(sock, obiekt):
    surowe = json.dumps(obiekt, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack("<i", len(surowe)) + surowe)


def _odbierz(sock):
    naglowek = _czytaj_dokladnie(sock, 4)
    (dlugosc,) = struct.unpack("<i", naglowek)
    if dlugosc <= 0:
        raise BridgeError(f"Most zwrócił błędną długość ramki: {dlugosc}")
    return json.loads(_czytaj_dokladnie(sock, dlugosc).decode("utf-8"))


def _czytaj_dokladnie(sock, ile):
    bufor = b""
    while len(bufor) < ile:
        czesc = sock.recv(ile - len(bufor))
        if not czesc:
            raise ConnectionError("Most zamknął połączenie.")
        bufor += czesc
    return bufor


def _polacz(timeout):
    sock = socket.create_connection((HOST, PORT), timeout=timeout)
    sock.settimeout(timeout)
    return sock


def _zapytaj(command, args=None, timeout=TIMEOUT_S):
    """Jedno żądanie na własnym połączeniu. Zwraca surową odpowiedź."""
    with _polacz(timeout) as sock:
        _wyslij(sock, {
            "protocol": PROTOKOL_MIN,
            "request_id": str(uuid.uuid4()),
            "command": command,
            "args": args or {},
        })
        return _odbierz(sock)


# ── cykl życia mostu ────────────────────────────────────────────────────────
def ping(timeout=2):
    """Odpowiedź `ping` albo None, gdy mostu nie ma.

    Lekkie — nie dotyka Subiekta, więc nadaje się do sprawdzania w pętli.
    """
    try:
        odp = _zapytaj("ping", timeout=timeout)
        return odp.get("data") if odp.get("ok") else None
    except (OSError, ConnectionError, ValueError):
        return None


def status(timeout=5):
    """Diagnostyka mostu: stan sesji, kolejka, liczba logowań, uptime."""
    odp = _zapytaj("status", timeout=timeout)
    if not odp.get("ok"):
        raise BridgeError(_komunikat_bledu(odp))
    return odp["data"]


#: Po ilu dniach katalog roboczy w %TEMP% uznajemy za śmieć. Doba z zapasem:
#: najdłuższa operacja (wydruk PDF, zakładanie projektu) trwa minuty, więc nic
#: żywego nie ma prawa być starsze.
SMIECI_STARSZE_NIZ_DNI = 1


def posprzataj_temp():
    """Kasuje stare katalogi robocze w %TEMP%. Zwraca liczbę usuniętych.

    Moduły tworzą je przez `tempfile.mkdtemp(prefix="subiekt_…")` i nie
    sprzątają — pliki wejściowe i wyniki muszą przeżyć wywołanie mostu,
    a nikt nie wie, kiedy przestają być potrzebne. Przy jednym wywołaniu
    dziennie to nie problem; przy stałym moście i szybkich operacjach
    katalogów przybywa setkami (185 po trzech dniach testów, 06.09.2026).

    Sprzątamy tutaj, bo to jedyne miejsce, przez które przechodzi każda
    operacja Subiekta — także ta, która poleci starym CLI.
    """
    import shutil

    granica = time.time() - SMIECI_STARSZE_NIZ_DNI * 86400
    usuniete = 0
    try:
        baza = tempfile.gettempdir()
        for nazwa in os.listdir(baza):
            if not (nazwa.startswith("subiekt_") or nazwa == "nexo_bridge"):
                continue
            sciezka = os.path.join(baza, nazwa)
            if not os.path.isdir(sciezka):
                continue
            try:
                if nazwa == "nexo_bridge":
                    # Katalog mostu: kasujemy stare PODkatalogi, nie sam
                    # kontener — most może go właśnie używać.
                    for pod in os.listdir(sciezka):
                        p = os.path.join(sciezka, pod)
                        if os.path.isdir(p) and os.path.getmtime(p) < granica:
                            shutil.rmtree(p, ignore_errors=True)
                            usuniete += 1
                elif os.path.getmtime(sciezka) < granica:
                    shutil.rmtree(sciezka, ignore_errors=True)
                    usuniete += 1
            except OSError:
                pass          # zajęty albo zniknął w międzyczasie — trudno
    except OSError:
        pass                  # brak dostępu do %TEMP% nie może wywalić mostu
    return usuniete


def _uruchom_most():
    """Startuje `NexoRecon.exe server` w tle. Zwraca True, gdy się udało."""
    exe = _find_exe()
    if not exe:
        return False
    if not os.path.isfile(CONFIG_PATH):
        return False

    # Przy okazji startu mostu (raz na uruchomienie RM_BAZA) — sprzątanie
    # wczorajszych katalogów roboczych. Tu, bo to moment, w którym i tak
    # czekamy kilkanaście sekund na sesję Sfery.
    posprzataj_temp()

    # Bez konsoli i odczepiony od RM_BAZA — most ma przeżyć zamknięcie
    # programu i obsługiwać kolejne uruchomienia tego samego dnia
    # (plan, sekcja 9: bridge może działać cały dzień).
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    try:
        subprocess.Popen(
            [exe, "server"],
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError:
        return False
    return True


def _czekaj_na_gotowosc(limit_s):
    """Czeka, aż most zaloguje się do Sfery. True = gotowy do pracy.

    Most odpowiada na `ping` od razu po starcie, ale z `ready=False` —
    sesja Sfery wstaje dopiero po ~10–15 s. Czekamy na `ready`, bo
    inaczej pierwsza komenda poszłaby do niezalogowanego mostu.
    """
    koniec = time.monotonic() + limit_s
    while time.monotonic() < koniec:
        dane = ping()
        if dane and dane.get("ready"):
            return True
        time.sleep(0.25)
    return False


def zapewnij_most():
    """Upewnia się, że most działa (uruchamia go, gdy trzeba).

    NIE gwarantuje zalogowanej sesji — to robi worker mostu przed każdą
    komendą. Rzuca BridgeUnavailable, gdy mostu nie da się uruchomić —
    wołający ma wtedy użyć starego CLI.
    """
    global _most_niedostepny

    # Most ŻYJE = wystarczy, żeby wysłać komendę — nawet gdy ready=False.
    # Sesję Sfery odbudowuje worker w pre-checku przed komendą, a bez komendy
    # nikt jej nie odbuduje. Czekanie tu na ready (jak dawniej) po padzie
    # SQL kończyło się timeoutem, _most_niedostepny=True i RM_BAZA do końca
    # życia procesu jechała starym CLI, choć SQL dawno wrócił (znalezione
    # 06.09.2026 przy teście z zatrzymanym SQL). Na ready czekamy tylko po
    # własnym uruchomieniu mostu — niżej.
    dane = ping()
    if dane:
        _sprawdz_protokol(dane)
        return

    with _lock:
        # Drugie sprawdzenie pod blokadą: kilka okien RM_BAZA startuje
        # równocześnie i bez tego każde próbowałoby uruchomić własny most.
        dane = ping()
        if dane:
            _sprawdz_protokol(dane)
            return

        if _most_niedostepny:
            raise BridgeUnavailable("Most jest oznaczony jako niedostępny.")

        # Nieaktualną binarkę widać OD RAZU (data pliku), więc nie ma po co
        # uruchamiać jej i czekać 40 s na „ready", którego nigdy nie będzie.
        # Bez tego user przez trzy kwadranse minuty patrzy na kręciołek,
        # zanim zobaczy okienko z przyciskiem — i uznaje, że nic się nie
        # dzieje (zgłoszone 06.09.2026).
        if not _zna_tryb_server(_find_exe()):
            _most_niedostepny = True
            raise BridgeUnavailable(_powod_niewstania())

        # Most może już wstawać (inne okno go uruchomiło) — wtedy tylko czekamy.
        if dane is None and not _uruchom_most():
            _most_niedostepny = True
            raise BridgeUnavailable(_powod_niewstania(
                "Nie udało się uruchomić NexoRecon.exe server."))

        if not _czekaj_na_gotowosc(START_TIMEOUT_S):
            _most_niedostepny = True
            raise BridgeUnavailable(_powod_niewstania())

        dane = ping()
        if dane:
            _sprawdz_protokol(dane)


#: Czy pokazano już w tej sesji okienko o nieaktualnym moście. Raz wystarczy —
#: to sytuacja jednorazowa po „git pull", a nie powód do nękania przy każdym
#: kliknięciu.
_ostrzezono_o_buildzie = False


def _powod_niewstania(domyslny=None):
    """Czytelny powód, dla którego most nie wstał.

    Najczęstsza przyczyna to BRAK BUILDA po „git pull": katalog bin/ nie idzie
    przez gita, więc przychodzą nowe źródła .cs przy starym .exe. Stara binarka
    nie zna trybu „server" — nie zgłasza błędu, tylko traktuje go jak brak
    trybu i wypisuje domyślny raport rozpoznawczy do niewidocznego okna
    (DETACHED_PROCESS), po czym kończy się kodem 0. Python nie doczeka się
    „ready", schodzi na fallback CLI i wszystko DZIAŁA — tylko wolno jak przed
    przebudową, bez jednego komunikatu. Bez tej diagnostyki nikt by nie
    zauważył, że most w ogóle nie wstał.
    """
    exe = _find_exe()
    if not exe:
        return ("Nie znaleziono NexoRecon.exe.\n\n"
                "Zbuduj most:\n"
                "  cd subiekt_sfera\\NexoRecon\n"
                "  dotnet build -c Release -nowarn:MSB3277")
    if not _zna_tryb_server(exe):
        try:
            from subiekt_stany import most_starszy_niz_zrodla
            _, pliki = most_starszy_niz_zrodla(exe)
        except Exception:
            pliki = ""
        skad = f"\nŹródła nowsze od binarki: {pliki}.\n" if pliki else "\n"
        return ("NIEAKTUALNY MOST — trzeba go przebudować.\n\n"
                "NexoRecon.exe nie zna trybu „server”."
                + skad +
                "Katalog bin/ nie idzie przez gita, więc po „git pull”\n"
                "binarkę trzeba zbudować u siebie:\n\n"
                "    cd subiekt_sfera\\NexoRecon\n"
                "    dotnet build -c Release -nowarn:MSB3277\n\n"
                "Program działa dalej, ale każda operacja Subiekta trwa\n"
                "~10 s zamiast ułamka sekundy.")
    return domyslny or f"Most nie zalogował się do Sfery w {START_TIMEOUT_S} s."


def _zna_tryb_server(exe):
    """Czy binarka jest nowsza niż plik, który wprowadził tryb „server".

    Uruchomienie jej z „server" byłoby pewniejsze, ale niepraktyczne: samo
    logowanie do Sfery trwa ~14 s, więc stara binarka nie zdąży wypisać
    raportu rozpoznawczego w rozsądnym timeoucie i wygląda tak samo jak
    nowa, która zaczęła nasłuchiwać (sprawdzone 06.09.2026).

    Porównujemy więc z ServerHost.cs — plikiem, BEZ którego trybu „server"
    nie ma. To węższe i pewniejsze niż „którykolwiek .cs nowszy od .exe":
    zwykła zmiana w handlerze (np. Magazyn.cs) nie unieważnia trybu server,
    a fałszywe ostrzeżenie po każdym pullu nauczyłoby ludzi je ignorować.
    """
    try:
        if not exe or not os.path.isfile(exe):
            return False
        server_cs = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "subiekt_sfera", "NexoRecon", "ServerHost.cs")
        if not os.path.isfile(server_cs):
            return True          # nie wiemy — nie strasz bez powodu
        return os.path.getmtime(exe) + 1 >= os.path.getmtime(server_cs)
    except Exception:
        return True              # diagnostyka nie może wywalić wywołania


def ostrzez_o_moscie():
    """Pokazuje JEDNORAZOWE okienko, gdy most nie działa przez brak builda.

    Wołane z modułów GUI po złapaniu BridgeUnavailable. Bez okienka jedyną
    oznaką jest to, że „znowu wolno" — a to łatwo złożyć na karb Subiekta.
    """
    global _ostrzezono_o_buildzie
    if _ostrzezono_o_buildzie:
        return
    powod = _powod_niewstania()
    if "NIEAKTUALNY MOST" not in powod and "Nie znaleziono" not in powod:
        return                      # inna przyczyna — nie zawracamy głowy
    _ostrzezono_o_buildzie = True

    # call() leci zwykle z wątku roboczego (okna robią threading.Thread),
    # a tkinter wolno dotykać tylko z wątku głównego — stąd after(0, …) na
    # korzeniu aplikacji zamiast okna wprost.
    try:
        import tkinter as tk
        root = tk._default_root
        if root is not None:
            root.after(0, lambda: _okno_buildu(root, powod))
        else:
            _okno_buildu(None, powod)   # brak pętli tk (skrypt) — próbujemy wprost
    except Exception:
        pass                        # brak GUI nie może wywalić wywołania


#: Gdzie na stanowisku ma wylądować pobrana binarka. Ta sama ścieżka stoi
#: w EXE_CANDIDATES, więc most zostanie tam znaleziony bez dodatkowej
#: konfiguracji.
#: Gdzie laduje most na stanowisku usera — OBOK SDK Sfery, nie osobno.
#:
#: Most nie dziala sam: NexoSession.PodepnijSdk() doladowuje w locie 435
#: bibliotek InsERT z C:\iLogic\SUBIEKT\Bin\, wiec ten katalog i tak musi
#: byc na kazdej maszynie. Trzymanie binarki w drugim miejscu
#: (C:\RMPAK_CLIENT\NexoRecon) rozdzielalo jedna rzecz na dwie lokalizacje
#: bez powodu — teraz wszystko, co dotyczy Subiekta, lezy pod
#: C:\iLogic\Subiekt (decyzja 06.09.2026).
DOCELOWY_KATALOG_MOSTU = r"C:\iLogic\Subiekt\MOST"

#: Poczekalnia u osoby budujacej most — TO NIE JEST katalog, z ktorego
#: cokolwiek sie uruchamia.
#:
#: U dewelopera MOST pelnilby dwie role naraz: cel "Pobierz most"
#: i miejsce, z ktorego wgrywa na serwer. Klikniecie "Pobierz most"
#: nadpisywaloby wtedy swiezy build tym, co juz lezy na serwerze —
#: czyli cofalo wlasna prace. Staging rozdziela te role: budujesz tutaj,
#: wgrywasz stad na serwer, a MOST zostaje wylacznie tym, co dziala
#: na stanowisku (06.09.2026).
KATALOG_STAGING_MOSTU = r"C:\iLogic\Subiekt\MOST_STAGING"


#: Podfolder z samą binarką mostu wewnątrz folderu SUBIEKT.
#:
#: Most to cztery pliki, razem ~590 KB. Folder SUBIEKT trzyma obok 1,3 GB
#: SDK Sfery i instalkę .NET, więc pobieranie z korzenia ciągnęłoby przez
#: sieć całość przy każdej aktualizacji — a SDK zmienia się tylko przy
#: aktualizacji nexo i wgrywa się na stanowisko RAZ (ustalone 06.09.2026).
#:
#: ⚠️ NIE „bin": tak nazywa się katalog bibliotek SDK Sfery, który leży
#: w tym samym folderze. Wrzucenie mostu do niego mieszałoby dwie zupełnie
#: różne rzeczy w jednym miejscu.
PODFOLDER_MOSTU = "MOST"

#: Gdzie szukać folderu SUBIEKT, gdy nie ma wpisu w konfiguracji.
#: Ten sam zasób bywa zamapowany pod RÓŻNYMI literami — u większości Y:,
#: u części Z: — więc sprawdzamy po kolei zamiast wpisywać jedną na sztywno.
DOMYSLNE_ZRODLA_MOSTU = [
    # Realna lokalizacja na serwerze (06.09.2026): folder SUBIEKT leży
    # wewnątrz `iLogic\`, bo tak wygląda struktura u dewelopera i tak
    # została skopiowana. Sprawdzamy OBA warianty — z `iLogic` i bez —
    # żeby przeniesienie folderu nie wymagało zmiany kodu.
    r"Y:\RMPAK_CLIENT\iLogic\Subiekt",
    r"Z:\RMPAK_CLIENT\iLogic\Subiekt",
    r"X:\RMPAK_CLIENT\iLogic\Subiekt",
    r"V:\RMPAK_CLIENT\iLogic\Subiekt",
    r"Y:\RMPAK_CLIENT\Subiekt",
    r"Z:\RMPAK_CLIENT\Subiekt",
    r"X:\RMPAK_CLIENT\Subiekt",
    r"V:\RMPAK_CLIENT\Subiekt",
]


def _zrodlo_mostu():
    """Folder z gotowym mostem, albo None.

    Kolejność: wpis w sync_config.json → paths.bridge_dir (jeśli ktoś ma
    nietypową ścieżkę), potem domyślne litery dysków. Szukamy folderu,
    w którym FAKTYCZNIE leży NexoRecon.exe — sama obecność katalogu nie
    wystarczy, bo pusty albo cudzy folder dałby mylący komunikat.

    Dlaczego w ogóle: na stanowiskach RM_BAZA chodzi jako .exe — nie ma tam
    ani źródeł .cs, ani dotneta, więc budowanie u siebie odpada. Gotową
    binarkę wystawia jedna osoba, reszta ją pobiera (ustalone 06.09.2026).
    """
    kandydaci = []
    try:
        with open(r"C:\RMPAK_CLIENT\sync_config.json", encoding="utf-8") as f:
            z_configu = (json.load(f).get("paths") or {}).get("bridge_dir")
        if z_configu:
            kandydaci.append(z_configu)
    except Exception:
        pass                    # brak configu to nie błąd — mamy domyślne
    kandydaci += DOMYSLNE_ZRODLA_MOSTU

    for folder in kandydaci:
        # Most może leżeć w podfolderze bin\ (tak wystawiamy na serwerze,
        # żeby nie ciągnąć obok 1,3 GB SDK) albo wprost w podanym katalogu
        # — jeśli ktoś wskazał go dokładnie.
        for kandydat in (os.path.join(folder, PODFOLDER_MOSTU), folder):
            try:
                if os.path.isfile(os.path.join(kandydat, "NexoRecon.exe")):
                    return kandydat
            except OSError:
                continue        # dysk odłączony albo brak uprawnień
    return None


def _wersja_zrodla(folder):
    """{'protokol': int, 'zbudowano': str} z wersja.json w folderze, albo None."""
    try:
        with open(os.path.join(folder, "wersja.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def wersja_lokalna():
    """{'protokol','zbudowano','sha'} mostu uzywanego na tym stanowisku.

    Czytane z wersja.json LEZACEGO OBOK dzialajacej binarki, nie z ustalonej
    sciezki: most bywa w MOST\\, w starym C:\\RMPAK_CLIENT\\NexoRecon albo
    (u budujacego) wprost w bin\\Release repozytorium.
    """
    exe = _find_exe()
    if not exe:
        return None
    return _wersja_zrodla(os.path.dirname(exe))


def _czas_na_sprawdzenie():
    """Czy minela doba od ostatniego zajrzenia na serwer."""
    import time
    try:
        return (time.time() - os.path.getmtime(ZNACZNIK_SPRAWDZENIA)
                ) >= SPRAWDZAJ_NOWSZY_CO_S
    except OSError:
        return True                 # brak znacznika = jeszcze nie sprawdzalismy


def _odnotuj_sprawdzenie():
    """Zapisuje moment zajrzenia na serwer."""
    try:
        with open(ZNACZNIK_SPRAWDZENIA, "w", encoding="utf-8") as f:
            f.write("ostatnie sprawdzenie nowszego mostu\n")
    except OSError:
        pass                        # brak zapisu = sprawdzimy ponownie, nic zlego


def dostepna_nowsza(timeout_s=3, wymuszone=False):
    """Czy na serwerze lezy NOWSZA binarka niz uzywana. (bool, opis).

    ⚠️ POWSTALO, BO AUTOMAT REAGOWAL TYLKO NA MOST CALKIEM ZEPSUTY.
    Ostrzezenie o buildzie wypada wylacznie wtedy, gdy most nie wstaje —
    brak .exe albo binarka tak stara, ze nie zna trybu "server". Dopoki most
    dziala, nikt nie sprawdzal, czy na serwerze nie ma nowszego: userzy
    zostawali na wersji sprzed optymalizacji i nie mieli jak sie dowiedziec,
    ze istnieje szybsza (06.09.2026 — serwer miał e2c26d8, gdy zbudowane
    bylo juz 9e6838a).

    Porownujemy `zbudowano` (tekst "RRRR-MM-DD GG:MM", wiec sortuje sie
    leksykograficznie), a nie `sha` — skrot mowi tylko, ze COS sie rozni,
    nie ktora strona jest starsza. Rozny protokol = nie proponujemy nic:
    binarka niezgodna z tym klientem zrobilaby wiecej szkody niz stara.

    `timeout_s` nie jest tu egzekwowany — zostaje w sygnaturze, bo wolajacy
    (panel) robi to w watku i moze chciec limitowac; odczyt to jeden maly
    plik z dysku sieciowego.
    """
    if not czy_z_binarki():
        return False, ""            # u budujacego zrodlem prawdy jest repo
    if not wymuszone and not _czas_na_sprawdzenie():
        return False, ""            # zagladalismy niedawno — patrz SPRAWDZAJ_NOWSZY_CO_S
    zrodlo = _zrodlo_mostu()
    if not zrodlo:
        return False, ""            # serwer nieosiagalny — nie zawracamy glowy
    zdalna = _wersja_zrodla(zrodlo)
    lokalna = wersja_lokalna()
    # Znacznik stawiamy po UDANYM dosiegnieciu serwera. Gdy dysk byl
    # odlaczony, nie ma czego odkladac na dobe — sprobujemy nastepnym razem.
    if zdalna:
        _odnotuj_sprawdzenie()
    if not zdalna or not lokalna:
        return False, ""
    if zdalna.get("protokol") != lokalna.get("protokol"):
        return False, ""            # inny protokol — patrz pobierz_most()
    tam = (zdalna.get("zbudowano") or "").strip()
    tu = (lokalna.get("zbudowano") or "").strip()
    if not tam or not tu or tam <= tu:
        return False, ""
    return True, f"Na serwerze jest nowszy most (z {tam}, masz z {tu})."


def pobierz_most():
    """Kopiuje gotowy most z folderu sieciowego. Zwraca (ok, komunikat).

    Używane na stanowiskach, gdzie RM_BAZA chodzi z .exe. Sprawdza wersję
    protokołu PRZED kopiowaniem: binarka niezgodna z tym klientem zrobiłaby
    więcej szkody niż stara, bo Python wołałby tryby, których ona nie zna.
    """
    import shutil

    zrodlo = _zrodlo_mostu()
    if not zrodlo:
        return False, (
            "Nie znaleziono folderu z mostem.\n\n"
            "Sprawdzono:\n"
            + "\n".join(f"  • {s}" for s in DOMYSLNE_ZRODLA_MOSTU)
            + "\n\nJeśli zasób jest pod inną literą, dopisz ścieżkę\n"
              "w C:\\RMPAK_CLIENT\\sync_config.json:\n"
              '  "paths": { "bridge_dir": "Y:\\\\RMPAK_CLIENT\\\\Subiekt" }')

    wersja = _wersja_zrodla(zrodlo)
    if wersja and wersja.get("protokol") not in (None, PROTOKOL_MIN):
        return False, (f"Most w folderze mówi protokołem {wersja.get('protokol')},\n"
                       f"a ta wersja RM_BAZA rozumie {PROTOKOL_MIN}.\n\n"
                       "Zaktualizuj RM_BAZA albo wystaw pasujący most.")

    zatrzymaj_most()
    time.sleep(2)               # Windows zwalnia uchwyt do pliku z opóźnieniem
    try:
        os.makedirs(DOCELOWY_KATALOG_MOSTU, exist_ok=True)
        skopiowane = 0
        for nazwa in os.listdir(zrodlo):
            if nazwa == "wersja.json":
                continue
            zrodlowy = os.path.join(zrodlo, nazwa)
            if os.path.isfile(zrodlowy):
                shutil.copy2(zrodlowy, os.path.join(DOCELOWY_KATALOG_MOSTU, nazwa))
                skopiowane += 1
    except OSError as e:
        return False, (f"Nie udało się skopiować mostu:\n{e}\n\n"
                       "Sprawdź, czy RM_BAZA nie jest otwarta w drugim oknie.")

    global _most_niedostepny, _ostrzezono_o_buildzie
    _most_niedostepny = False
    _ostrzezono_o_buildzie = False
    kiedy = (wersja or {}).get("zbudowano")
    return True, (f"Most pobrany ({skopiowane} plików"
                  + (f", wersja z {kiedy}" if kiedy else "") + ").\n\n"
                  "Kolejne operacje Subiekta powinny już działać szybko.")


def czy_z_binarki():
    """Czy RM_BAZA chodzi jako .exe (PyInstaller), a nie ze źródeł.

    Decyduje, CO ma zrobić przycisk: na stanowisku z .exe nie ma źródeł .cs
    ani dotneta, więc most trzeba pobrać, a nie zbudować.
    """
    return getattr(sys, "frozen", False)


def zaktualizuj_most():
    """Buduje albo pobiera — zależnie od tego, jak działa RM_BAZA."""
    return pobierz_most() if czy_z_binarki() else zbuduj_most()


def zbuduj_most():
    """Zatrzymuje most i uruchamia `dotnet build`. Zwraca (ok, komunikat).

    Kolejność ma znaczenie: działający most trzyma otwarty NexoRecon.exe,
    więc build bez zatrzymania kończy się MSB3027 „plik jest zablokowany".
    """
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "subiekt_sfera", "NexoRecon")
    if not os.path.isdir(src):
        return False, f"Nie znaleziono źródeł mostu:\n{src}"

    zatrzymaj_most()
    time.sleep(2)                   # Windows zwalnia uchwyt do pliku z opóźnieniem
    try:
        proc = subprocess.run(
            ["dotnet", "build", "-c", "Release", "-nowarn:MSB3277"],
            cwd=src, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=600,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except FileNotFoundError:
        return False, ("Nie znaleziono „dotnet”.\n\n"
                       "Na tym stanowisku brakuje .NET SDK 8 — to osobna\n"
                       "instalacja (dotnet.microsoft.com), nie da się jej\n"
                       "skopiować jak katalogu SDK Sfery.")
    except subprocess.TimeoutExpired:
        return False, "Budowanie trwało ponad 10 minut i zostało przerwane."

    if proc.returncode == 0:
        global _most_niedostepny, _ostrzezono_o_buildzie
        _most_niedostepny = False       # spróbujemy mostu przy następnej operacji
        _ostrzezono_o_buildzie = False
        return True, ("Most zbudowany.\n\n"
                      "Kolejne operacje Subiekta powinny już działać szybko.")

    # Z wyjścia dotneta bierzemy same linie błędów — pełny log to setki linii.
    bledy = [l.strip() for l in (proc.stdout or "").splitlines() if ": error" in l]
    szczegoly = "\n".join(bledy[:6]) or (proc.stderr or "").strip()[:400] or "brak szczegółów"
    return False, f"Budowanie nie powiodło się (kod {proc.returncode}):\n\n{szczegoly}"


def _etykieta_przycisku():
    """Na stanowisku z .exe most się POBIERA, u dewelopera buduje."""
    return "⬇  Pobierz most" if czy_z_binarki() else "🔨  Zbuduj teraz"


def _okno_buildu(parent, powod):
    """Okienko z powodem i przyciskiem, który sam buduje most."""
    import tkinter as tk
    from tkinter import messagebox

    okno = tk.Toplevel(parent) if parent is not None else tk.Tk()
    okno.title("Subiekt — most nieaktualny")
    okno.resizable(False, False)

    tk.Label(okno, text="⚠ Most Subiekta jest nieaktualny", bg="#c0392b", fg="white",
             font=("Arial", 11, "bold"), anchor="w", padx=12, pady=8).pack(fill=tk.X)
    tk.Label(okno, text=powod, justify="left", anchor="w",
             padx=14, pady=10, font=("Arial", 9)).pack(fill=tk.X)

    stan = tk.Label(okno, text="", anchor="w", padx=14, fg="#7f8c8d", font=("Arial", 9))
    stan.pack(fill=tk.X)

    stopka = tk.Frame(okno)
    stopka.pack(fill=tk.X, padx=14, pady=(6, 12))

    btn_zamknij = tk.Button(stopka, text="Później", command=okno.destroy,
                            bg="#7f8c8d", fg="white", relief=tk.FLAT, padx=14)
    btn_zamknij.pack(side=tk.RIGHT)

    def buduj():
        btn_buduj.config(state=tk.DISABLED)
        btn_zamknij.config(state=tk.DISABLED)
        stan.config(text=("Pobieram most z serwera…" if czy_z_binarki()
                          else "Buduję… (kilkanaście sekund, nie zamykaj okna)"))
        okno.update_idletasks()

        wynik = {}

        def w_tle():
            wynik["r"] = zaktualizuj_most()

        # Build w osobnym wątku, żeby okno nie zamarzło na czas kompilacji.
        w = threading.Thread(target=w_tle, daemon=True)
        w.start()

        def sprawdz():
            if w.is_alive():
                okno.after(200, sprawdz)
                return
            ok, komunikat = wynik.get("r", (False, "Budowanie przerwane."))
            stan.config(text="")
            # topmost zdejmujemy przed messageboxem — inaczej komunikat
            # wyniku potrafi wylądować POD tym oknem i nie da się go kliknąć.
            try:
                okno.attributes("-topmost", False)
            except Exception:
                pass
            (messagebox.showinfo if ok else messagebox.showerror)(
                "Budowanie mostu", komunikat, parent=okno)
            if ok:
                okno.destroy()
            else:
                btn_buduj.config(state=tk.NORMAL)
                btn_zamknij.config(state=tk.NORMAL)

        okno.after(200, sprawdz)

    btn_buduj = tk.Button(stopka, text=_etykieta_przycisku(), command=buduj,
                          bg="#27ae60", fg="white", relief=tk.FLAT,
                          padx=18, font=("Arial", 9, "bold"))
    btn_buduj.pack(side=tk.RIGHT, padx=(0, 8))

    try:
        from subiekt_stany import wysrodkuj
        wysrodkuj(okno, parent)
    except Exception:
        pass

    # NA WIERZCH I Z FOKUSEM — bezwarunkowo. Okno wyskakuje samo, w reakcji
    # na kliknięcie w zupełnie innym miejscu programu, więc bez tego ląduje
    # pod oknem, które user właśnie otworzył, i przepada niezauważone.
    try:
        okno.grab_set()             # modalne: reszta RM_BAZA nie przejmie zdarzeń
        okno.attributes("-topmost", True)
        okno.lift()
        okno.focus_force()
        btn_buduj.focus_set()       # Enter = zbuduj, bo po to tu jesteśmy
        okno.bell()
        # Powtórka po chwili: tkinter potrafi oddać fokus oknu, które
        # dopiero się rysuje (to ono nas tu w ogóle wywołało).
        okno.after(150, lambda: _wymus_fokus(okno, btn_buduj))
        okno.after(600, lambda: _wymus_fokus(okno, btn_buduj))
    except Exception:
        pass                        # to nie może wywalić ostrzeżenia

    okno.bind("<Return>", lambda _e: buduj())
    okno.bind("<Escape>", lambda _e: okno.destroy())


def _wymus_fokus(okno, przycisk):
    """Ponawia wyniesienie okna — jednorazowe lift() bywa cofane."""
    try:
        if not okno.winfo_exists():
            return
        okno.lift()
        okno.focus_force()
        przycisk.focus_set()
    except Exception:
        pass                        # okno mogło już zostać zamknięte


def _sprawdz_protokol(dane_ping):
    """Handshake wersji — pewniejszy niż porównywanie dat .cs i .exe."""
    wersja = dane_ping.get("protocol")
    if wersja is None or wersja < PROTOKOL_MIN:
        raise BridgeUnavailable(
            f"NIEAKTUALNY MOST — protokół {wersja}, wymagany co najmniej "
            f"{PROTOKOL_MIN}.\n\n"
            "Katalog bin/ nie idzie przez gita, więc po „git pull” binarkę\n"
            "trzeba zbudować u siebie:\n\n"
            "    cd subiekt_sfera\\NexoRecon\n"
            "    dotnet build -c Release -nowarn:MSB3277"
        )


def _komunikat_bledu(odp):
    err = odp.get("error") or {}
    return err.get("message") or "Most zwrócił błąd bez opisu."


# ── główne API ──────────────────────────────────────────────────────────────
def call(command, args=None, timeout=TIMEOUT_S, write=False, fallback=None):
    """Wykonuje komendę przez most. Zwraca zawartość `data` z odpowiedzi.

    `write=True` oznacza operację ZAPISUJĄCĄ do Subiekta. Dla takich
    operacji NIE MA fallbacku ani ponowienia po niejednoznacznym błędzie:
    jeśli most zdążył wystartować i zgłosił UNKNOWN_COMMIT_STATE, nie
    wiadomo, czy zapis przeszedł, a ślepe powtórzenie zrobi duplikat
    (plan, sekcja 14 i 17).

    `fallback` to funkcja bez argumentów, wołana gdy mostu nie da się
    uruchomić. Zwykle jest to dotychczasowe wywołanie CLI.
    """
    try:
        zapewnij_most()
    except BridgeUnavailable:
        # Most nie wystartował — nic nie zostało wykonane, więc stare CLI
        # jest bezpieczne także dla zapisu. Ale fallback jest CICHY: bez
        # ostrzeżenia jedyną oznaką braku builda byłoby to, że „znowu wolno".
        ostrzez_o_moscie()
        if fallback is not None:
            return fallback()
        raise

    try:
        odp = _zapytaj(command, args, timeout=timeout)
    except socket.timeout:
        raise BridgeError(f"Subiekt nie odpowiedział w {timeout} s.", code="TIMEOUT")
    except (OSError, ConnectionError) as e:
        # Połączenie padło w trakcie. Dla odczytu można spróbować jeszcze raz
        # (most mógł się w międzyczasie przeładować); dla zapisu — nigdy.
        if write:
            raise BridgeError(
                "Utracono połączenie z mostem w trakcie operacji zapisującej.\n"
                "Nie wiadomo, czy zmiana została zapisana — sprawdź stan\n"
                f"w Subiekcie przed ponowieniem.\n\n{e}",
                code="UNKNOWN_COMMIT_STATE",
            )
        try:
            odp = _zapytaj(command, args, timeout=timeout)
        except (OSError, ConnectionError) as e2:
            if fallback is not None:
                return fallback()
            raise BridgeError(f"Most nie odpowiada: {e2}", code="BRIDGE_LOST")

    # SESSION_LOST retryable=True przychodzi TYLKO wtedy, gdy most sprawdził
    # sesję PRZED handlerem i nie zdołał jej odbudować — nic się nie
    # wykonało, więc ponowienie jest bezpieczne także dla zapisu. Typowo po
    # uśpieniu komputera: sieć wraca kilka sekund po wybudzeniu, pierwszy
    # reconnect trafia w tę dziurę, drugi już przechodzi. Jedno ponowienie
    # z odstępem — nie pętla, bo jeśli SQL naprawdę leży, user ma to
    # zobaczyć, a nie czekać.
    err = odp.get("error") or {}
    if not odp.get("ok") and err.get("code") == "SESSION_LOST" and err.get("retryable"):
        time.sleep(3)
        try:
            odp = _zapytaj(command, args, timeout=timeout)
        except socket.timeout:
            raise BridgeError(f"Subiekt nie odpowiedział w {timeout} s.", code="TIMEOUT")
        except (OSError, ConnectionError) as e:
            raise BridgeError(f"Most nie odpowiada: {e}", code="BRIDGE_LOST")

    if not odp.get("ok"):
        err = odp.get("error") or {}
        raise BridgeError(_komunikat_bledu(odp),
                          code=err.get("code"),
                          retryable=bool(err.get("retryable")))
    return odp.get("data") or {}


def wywolaj(tryb, argv=(), timeout=TIMEOUT_S, plan=None, symbole=None,
            fallback=None):
    """Most z argumentami w stylu CLI.

    Ułatwia przepinanie istniejących modułów: wołający podaje to samo, co
    dotąd budował w liście `cmd`, a ta funkcja tłumaczy przełączniki na args
    protokołu.

        dane = bridge.wywolaj("magazyn", ["--tylko-niezerowe"], fallback=...)
        dane = bridge.wywolaj("zd", ["--zapisz"], plan=pozycje)

    `plan` i `symbole` idą osobno, bo w CLI są plikami (`--plan=`,
    `--symbols-file=`), a przez most jadą jako dane w JSON-ie.

    `fallback` (funkcja bez argumentów) jest wołany, gdy mostu nie da się
    uruchomić. Dla operacji zapisujących jest bezpieczny, bo brak startu
    mostu oznacza, że nic się nie wykonało (plan, sekcja 17).
    """
    args = {}
    zapisz = False
    for a in argv:
        if a == "--zapisz":
            zapisz = True
        elif a == "--tylko-niezerowe":
            args["tylko_niezerowe"] = True
        elif a.startswith("--"):
            klucz, _, wartosc = a[2:].partition("=")
            klucz = klucz.replace("-", "_")
            if klucz in ("out", "plan", "symbols_file"):
                continue          # most nie używa plików pośrednich
            args[klucz] = int(wartosc) if wartosc.isdigit() else wartosc
    if zapisz:
        args["zapisz"] = True
    if plan is not None:
        args["plan"] = plan
    if symbole is not None:
        args["symbols"] = list(symbole)

    return call(tryb, args, timeout=timeout, write=zapisz, fallback=fallback)


def pozwol_na_ponowna_probe():
    """Zdejmuje pamięć o tym, że most nie wstał.

    `_most_niedostepny` żyje do końca procesu RM_BAZA: raz nieudany start
    i wszystkie kolejne wywołania lecą starym CLI, bez ponawiania. To dobre,
    gdy powód się nie zmienia (stara binarka, brak pliku), ale ZŁE po zmianie
    danych logowania — user poprawia hasło, a okno dalej odpowiada „most jest
    oznaczony jako niedostępny" i nie ma jak z tego wyjść bez restartu
    aplikacji (zgłoszone 06.09.2026).

    Woła to okno „Połączenie z Subiektem" przed ponownym startem mostu.
    """
    global _most_niedostepny, _ostrzezono_o_buildzie
    _most_niedostepny = False
    _ostrzezono_o_buildzie = False


def zatrzymaj_most():
    """Kończy proces mostu. Do diagnostyki — normalnie most żyje cały dzień."""
    dane = ping()
    if not dane:
        return False
    pid = dane.get("pid")
    if not pid:
        return False
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        return True
    except OSError:
        return False
