# -*- coding: utf-8 -*-
"""Klient RM_SERWER — jedyna droga do master.sqlite i subiekt_mapowania.sqlite.

    RM_BAZA / RM_MANAGER  ──TCP──►  RM_SERWER  ──►  C:\\Apps\\RM_SERWER\\dane\\

⚠️ NIE MA TRYBU LOKALNEGO. Świadoma decyzja (11.09.2026): jedna ścieżka
zamiast dwóch. Dwie ścieżki oznaczałyby, że każda nowa operacja musi działać
w obu trybach — a ta rzadziej używana cicho gnije, aż ktoś na nią trafi
w najgorszym momencie.

Konsekwencja, którą trzeba znać: **gdy serwer nie odpowiada, zapisy i odczyty
mastera nie działają.** Praca na projekcie trwa (pliki projektów są poza tym
etapem), ale dostawcy, użytkownicy i ustawienia są niedostępne. Dlatego
serwer chodzi jako usługa z auto-restartem, a wycofanie zmiany to podmiana
`.exe` — nie przełącznik.

UŻYCIE

    import rm_klient
    rm_klient.ustaw_serwer(host="192.168.100.84", port=5060, sekret="…")

    dostawcy = rm_klient.master_read("suppliers-list")
    rm_klient.master_exec("supplier-delete", {"supplier_id": 7})
    rm_klient.master_batch([
        {"operation": "supplier-add",   "params": {...}},
        {"operation": "user-audit-add", "params": {...}},
    ])

Operacje z prefiksem `map-` trafiają do `subiekt_mapowania.sqlite`, reszta do
mastera — routingiem zajmuje się serwer, wołający nie musi o tym wiedzieć.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import socket
import struct
import uuid

PROTOKOL_MIN = 1
DOMYSLNY_PORT = 5060
TIMEOUT_S = 30

_host = None
_port = DOMYSLNY_PORT
_sekret = None


class BladSerwera(Exception):
    """Operacja się nie udała — JEDYNY wyjątek, jaki widzi wołający.

    `dostepny=False` znaczy „nie dojechaliśmy do serwera" — wtedy GUI mówi
    „serwer niedostępny, spróbuj za chwilę". `dostepny=True` to zwykła odmowa
    (nieznana operacja, brak parametru) i jest błędem wołającego.
    """

    def __init__(self, komunikat, dostepny=True):
        super().__init__(komunikat)
        self.dostepny = dostepny


# ═══════════════════════════════════════════════════════════════════════
# Konfiguracja
# ═══════════════════════════════════════════════════════════════════════

def ustaw_serwer(host, port=None, sekret=None):
    """Adres serwera. Wołane raz, przy starcie aplikacji."""
    global _host, _port, _sekret
    if not host:
        raise ValueError("adres RM_SERWER jest wymagany")
    _host = host
    _port = int(port or DOMYSLNY_PORT)
    _sekret = sekret


def skonfigurowany():
    return bool(_host)


def opis():
    """Jedna linia do logu i okna diagnostycznego."""
    if not _host:
        return "RM_SERWER NIESKONFIGUROWANY"
    return "RM_SERWER %s:%d%s" % (_host, _port,
                                  "" if _sekret else "  (HMAC WYŁĄCZONY)")


# ═══════════════════════════════════════════════════════════════════════
# Transport — 4 bajty długości LE + UTF-8 JSON (jak subiekt_bridge)
# ═══════════════════════════════════════════════════════════════════════

def _czytaj_dokladnie(sock, ile):
    bufor = b""
    while len(bufor) < ile:
        czesc = sock.recv(ile - len(bufor))
        if not czesc:
            raise ConnectionError("Serwer zamknął połączenie.")
        bufor += czesc
    return bufor


def _kanoniczny_json(obiekt):
    """Postać, na której liczymy podpis — MUSI być identyczna co w serwerze.

    Kolejność kluczy, brak spacji i `ensure_ascii=False` (w danych są polskie
    znaki). Bez tego podpis raz na jakiś czas nie zgodzi się bez powodu.
    """
    return json.dumps(obiekt or {}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def _hmac(request_id, cmd, args):
    if not _sekret:
        return None
    tresc = "%s|%s|%s" % (request_id or "", cmd or "", _kanoniczny_json(args))
    return hmac.new(_sekret.encode("utf-8"), tresc.encode("utf-8"),
                    hashlib.sha256).hexdigest()


_kto_cache = None


def _kto():
    """Kto pyta — do logu serwera i wpisu w dzienniku."""
    global _kto_cache
    if _kto_cache is None:
        import getpass
        import os
        try:
            host = socket.gethostname()
        except Exception:
            host = "?"
        _kto_cache = {"user": getpass.getuser(), "host": host, "pid": os.getpid()}
    return _kto_cache


def ustaw_uzytkownika(user):
    """Podmienia nazwę użytkownika na zalogowanego w RM_BAZA.

    Domyślnie idzie login Windows; aplikacja ma własnych użytkowników
    (ADMIN, GKI…) i to oni mają być widoczni w logu serwera.
    """
    _kto()
    if user:
        _kto_cache["user"] = str(user)


def zapytaj(cmd, args=None, request_id=None, timeout=TIMEOUT_S, kto=None):
    """Jedno żądanie na własnym połączeniu. Zwraca `data` z odpowiedzi."""
    if not _host:
        raise BladSerwera(
            "RM_SERWER nieskonfigurowany — brak adresu w sync_config.json",
            dostepny=False)

    zadanie = {"cmd": cmd, "args": args or {}, "request_id": request_id,
               "kto": kto or _kto()}
    podpis = _hmac(request_id, cmd, args)
    if podpis:
        zadanie["hmac"] = podpis

    surowe = json.dumps(zadanie, ensure_ascii=False).encode("utf-8")
    try:
        with socket.create_connection((_host, _port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(struct.pack("<i", len(surowe)) + surowe)
            (dlugosc,) = struct.unpack("<i", _czytaj_dokladnie(sock, 4))
            odp = json.loads(_czytaj_dokladnie(sock, dlugosc).decode("utf-8"))
    except (OSError, ConnectionError, socket.timeout) as e:
        # Serwer nieosiągalny — TO jest wyjątek, nie `ok: false`.
        raise BladSerwera("RM_SERWER niedostępny (%s:%s): %s" % (_host, _port, e),
                          dostepny=False)

    if not odp.get("ok"):
        raise BladSerwera(odp.get("blad") or "serwer odmówił bez powodu")
    return odp.get("data") or {}


# ═══════════════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════════════

def master_read(operation, params=None, timeout=TIMEOUT_S):
    """Odczyt. Zwraca listę słowników.

    `request_id` generujemy mimo idempotencji odczytu — wchodzi do podpisu
    HMAC i pozwala odnaleźć żądanie w logu serwera.
    """
    dane = zapytaj("master-read", {"operation": operation, "params": params},
                   request_id=str(uuid.uuid4()), timeout=timeout)
    return dane.get("rows") or []


def master_exec(operation, params=None, request_id=None, timeout=TIMEOUT_S):
    """Pojedynczy zapis. Zwraca {'rowcount', 'lastrowid'}.

    `request_id` podaje się JAWNIE tylko wtedy, gdy ponawiamy tę samą
    operację po zerwanym połączeniu — wtedy musi być ten sam identyfikator,
    inaczej ochrona przed duplikatem nie zadziała.
    """
    return zapytaj("master-exec", {"operation": operation, "params": params},
                   request_id=request_id or str(uuid.uuid4()), timeout=timeout)


def master_batch(operacje, request_id=None, timeout=TIMEOUT_S):
    """Kilka zapisów jako JEDNA transakcja — wszystko albo nic.

    Wszystkie operacje muszą dotyczyć tej samej bazy (serwer odrzuca batch
    mieszający master z mapowaniami — transakcja nie obejmuje dwóch plików).
    """
    dane = zapytaj("master-batch", {"operacje": operacje},
                   request_id=request_id or str(uuid.uuid4()), timeout=timeout)
    return dane.get("wyniki") or []


def ping(timeout=5):
    """Stan serwera albo None, gdy nieosiągalny.

    Nie rzuca — służy do sprawdzania „czy jest", więc brak odpowiedzi to
    informacja, nie awaria.
    """
    try:
        return zapytaj("ping", request_id=str(uuid.uuid4()), timeout=timeout)
    except BladSerwera:
        return None
