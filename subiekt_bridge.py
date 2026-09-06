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


def _uruchom_most():
    """Startuje `NexoRecon.exe server` w tle. Zwraca True, gdy się udało."""
    exe = _find_exe()
    if not exe:
        return False
    if not os.path.isfile(CONFIG_PATH):
        return False

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
    """Upewnia się, że most działa i jest zalogowany.

    Rzuca BridgeUnavailable, gdy mostu nie da się uruchomić — wołający
    ma wtedy użyć starego CLI.
    """
    global _most_niedostepny

    dane = ping()
    if dane and dane.get("ready"):
        _sprawdz_protokol(dane)
        return

    with _lock:
        # Drugie sprawdzenie pod blokadą: kilka okien RM_BAZA startuje
        # równocześnie i bez tego każde próbowałoby uruchomić własny most.
        dane = ping()
        if dane and dane.get("ready"):
            _sprawdz_protokol(dane)
            return

        if _most_niedostepny:
            raise BridgeUnavailable("Most jest oznaczony jako niedostępny.")

        # Most może już wstawać (inne okno go uruchomiło) — wtedy tylko czekamy.
        if dane is None and not _uruchom_most():
            _most_niedostepny = True
            raise BridgeUnavailable("Nie udało się uruchomić NexoRecon.exe server.")

        if not _czekaj_na_gotowosc(START_TIMEOUT_S):
            _most_niedostepny = True
            raise BridgeUnavailable(
                f"Most nie zalogował się do Sfery w {START_TIMEOUT_S} s."
            )

        dane = ping()
        if dane:
            _sprawdz_protokol(dane)


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
        # jest bezpieczne także dla zapisu.
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
