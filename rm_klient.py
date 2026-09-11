# -*- coding: utf-8 -*-
"""Klient RM_SERWER — dostęp do master.sqlite z RM_BAZA.

Dwa tryby, jedna warstwa wywołań (PLAN_RM_SERWER.md §2a):

    tryb „serwer"  →  TCP do RM_SERWER na maszynie `nic`
    tryb „legacy"  →  ten sam SQL, wykonany lokalnie na własnym połączeniu

Ta sama mapa operacja → SQL (`rm_serwer_operacje`) po obu stronach, więc tryb
legacy nie jest osobną implementacją do utrzymywania — to ten sam kod wołany
z innego miejsca.

⚠️ TRYB JEST GLOBALNY, USTAWIA GO ADMIN. Nie per-stanowisko. Gdyby każdy
komputer wybierał niezależnie, PC1 pisałby przez serwer, a PC2 bezpośrednio po
SMB do tego samego pliku — dokładnie mechanizm awarii z 11.09.2026 (§0).
Flaga siedzi w `sync_config.json` na `Y:`, czytana przy starcie.

TRYB LEGACY MA TERMIN WAŻNOŚCI (§2a) — 2–4 tygodnie stabilnej pracy po
cutoverze, potem znika razem z `master_con`. Dopóki istnieje, każda nowa
operacja musi działać w OBU trybach.

UŻYCIE

    import rm_klient
    rm_klient.ustaw_tryb("serwer", host="192.168.100.84", port=5060, sekret="…")

    dostawcy = rm_klient.master_read("suppliers-list")
    rm_klient.master_exec("supplier-delete", {"supplier_id": 7})
    rm_klient.master_batch([
        {"operation": "supplier-add",    "params": {...}},
        {"operation": "user-audit-add",  "params": {...}},
    ])
"""

from __future__ import annotations

import hashlib
import hmac
import json
import socket
import struct
import threading
import uuid

import rm_serwer_operacje as ops

PROTOKOL_MIN = 1
DOMYSLNY_PORT = 5060
TIMEOUT_S = 30

#: Stan modułu. Ustawiany raz przy starcie RM_BAZA przez `ustaw_tryb()`.
_tryb = "legacy"
_host = None
_port = DOMYSLNY_PORT
_sekret = None
_polaczenie_lokalne = None      # tylko w trybie legacy
_lock = threading.Lock()        # legacy: master_con bywa dzielony między wątkami


class BladSerwera(Exception):
    """Operacja się nie udała — JEDYNY wyjątek, jaki widzi wołający.

    `dostepny=False` znaczy „nie dojechaliśmy do serwera" — wtedy GUI mówi
    „serwer niedostępny, spróbuj za chwilę". `dostepny=True` to normalna
    odmowa (nieznana operacja, brak parametru) i jest błędem wołającego.

    ⚠️ Ten sam typ leci w OBU trybach. W trybie legacy `rm_serwer_operacje`
    rzuca `BladOperacji`, który opakowujemy tutaj — inaczej kod wołający
    musiałby łapać dwa różne wyjątki zależnie od trybu, co przeczy idei
    „jedna warstwa, dwa transporty". Wykrył to test równoważności trybów.
    """

    def __init__(self, komunikat, dostepny=True):
        super().__init__(komunikat)
        self.dostepny = dostepny


# ═══════════════════════════════════════════════════════════════════════
# Konfiguracja trybu
# ═══════════════════════════════════════════════════════════════════════

def ustaw_tryb(tryb, host=None, port=None, sekret=None, polaczenie=None):
    """Ustawia tryb pracy. Woła to RM_BAZA raz, przy starcie.

    `polaczenie` — istniejące `sqlite3.Connection` do mastera; wymagane
    w trybie legacy, ignorowane w trybie serwer.
    """
    global _tryb, _host, _port, _sekret, _polaczenie_lokalne
    if tryb not in ("serwer", "legacy"):
        raise ValueError("tryb musi być 'serwer' albo 'legacy', nie %r" % (tryb,))
    _tryb = tryb
    _host = host or _host
    _port = int(port or _port)
    _sekret = sekret if sekret is not None else _sekret
    if polaczenie is not None:
        _polaczenie_lokalne = polaczenie
    if tryb == "serwer" and not _host:
        raise ValueError("tryb 'serwer' wymaga adresu hosta")


def tryb():
    return _tryb


def czy_serwer():
    return _tryb == "serwer"


def opis_trybu():
    """Jedna linia do logu i okna diagnostycznego."""
    if _tryb == "serwer":
        return "serwer %s:%d%s" % (_host, _port,
                                   "" if _sekret else "  (HMAC WYŁĄCZONY)")
    return "legacy — master.sqlite bezpośrednio po SMB"


# ═══════════════════════════════════════════════════════════════════════
# Transport — jak w subiekt_bridge: 4 bajty długości LE + UTF-8 JSON
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
    """Musi dać identyczny ciąg co `rm_serwer.kanoniczny_json` — inaczej
    podpis raz na jakiś czas nie zgodzi się bez powodu (§7)."""
    return json.dumps(obiekt or {}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def _hmac(request_id, cmd, args):
    if not _sekret:
        return None
    tresc = "%s|%s|%s" % (request_id or "", cmd or "", _kanoniczny_json(args))
    return hmac.new(_sekret.encode("utf-8"), tresc.encode("utf-8"),
                    hashlib.sha256).hexdigest()


def zapytaj(cmd, args=None, request_id=None, timeout=TIMEOUT_S, kto=None):
    """Jedno żądanie na własnym połączeniu. Zwraca `data` z odpowiedzi."""
    zadanie = {
        "cmd": cmd,
        "args": args or {},
        "request_id": request_id,
        "kto": kto or _kto(),
    }
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
    """Podmienia nazwę użytkownika w `kto` na zalogowanego w RM_BAZA.

    Domyślnie idzie login Windows; RM_BAZA ma własnych użytkowników
    (ADMIN, GKI…) i to oni mają być widoczni w logu serwera.
    """
    _kto()
    if user:
        _kto_cache["user"] = str(user)


# ═══════════════════════════════════════════════════════════════════════
# API — te trzy funkcje zastępują master_con w całym RM_BAZA
# ═══════════════════════════════════════════════════════════════════════

def master_read(operation, params=None, timeout=TIMEOUT_S):
    """Odczyt z mastera. Zwraca listę słowników.

    Idempotentny, więc bez `request_id` po stronie ochrony — ale i tak
    generujemy go do podpisu i śledzenia żądania w logu.
    """
    if _tryb == "serwer":
        dane = zapytaj("master-read",
                       {"operation": operation, "params": params},
                       request_id=str(uuid.uuid4()), timeout=timeout)
        return dane.get("rows") or []
    with _lock:
        try:
            return ops.wykonaj_odczyt(_con(), operation, params)
        except ops.BladOperacji as e:
            raise BladSerwera(str(e)) from e


def master_exec(operation, params=None, request_id=None, timeout=TIMEOUT_S):
    """Pojedynczy zapis. Zwraca {'rowcount', 'lastrowid'}.

    `request_id` generujemy tutaj, gdy wołający go nie podał. Wołający podaje
    go TYLKO wtedy, gdy chce ponowić tę samą operację po zerwanym połączeniu —
    wtedy musi użyć tego samego identyfikatora, inaczej ochrona przed
    duplikatem nie zadziała (§3).
    """
    request_id = request_id or str(uuid.uuid4())
    if _tryb == "serwer":
        return zapytaj("master-exec",
                       {"operation": operation, "params": params},
                       request_id=request_id, timeout=timeout)
    with _lock:
        con = _con()
        try:
            con.execute("BEGIN IMMEDIATE")
            wynik = ops.wykonaj_zapis(con, operation, params)
            con.commit()
            return wynik
        except ops.BladOperacji as e:
            try:
                con.rollback()
            except Exception:
                pass
            raise BladSerwera(str(e)) from e
        except Exception:
            # Rollback ZAWSZE — brak tego wywołał awarię 11.09: nieudany
            # commit zostawiał transakcję i blokował plik całej firmie.
            try:
                con.rollback()
            except Exception:
                pass
            raise


def master_batch(operacje, request_id=None, timeout=TIMEOUT_S):
    """Kilka zapisów jako JEDNA transakcja — wszystko albo nic.

    Do tego, co dziś jest dwoma `execute` i jednym `commit`: „dodaj dostawcę
    + wpis do audytu". Bez batcha drugi zapis mógłby nie dojść i zostawić
    dane bez śladu w dzienniku.
    """
    request_id = request_id or str(uuid.uuid4())
    if _tryb == "serwer":
        dane = zapytaj("master-batch", {"operacje": operacje},
                       request_id=request_id, timeout=timeout)
        return dane.get("wyniki") or []
    with _lock:
        con = _con()
        try:
            con.execute("BEGIN IMMEDIATE")
            wyniki = [ops.wykonaj_zapis(con, o.get("operation"), o.get("params"))
                      for o in operacje]
            con.commit()
            return wyniki
        except ops.BladOperacji as e:
            try:
                con.rollback()
            except Exception:
                pass
            raise BladSerwera(str(e)) from e
        except Exception:
            try:
                con.rollback()
            except Exception:
                pass
            raise


def ping(timeout=5):
    """Stan serwera albo None, gdy nieosiągalny. Nie rzuca — służy do
    sprawdzania „czy jest", więc brak odpowiedzi to informacja, nie awaria."""
    if _tryb != "serwer":
        return {"tryb": "legacy"}
    try:
        return zapytaj("ping", request_id=str(uuid.uuid4()), timeout=timeout)
    except BladSerwera:
        return None


# ═══════════════════════════════════════════════════════════════════════
# Tryb legacy
# ═══════════════════════════════════════════════════════════════════════

def _con():
    if _polaczenie_lokalne is None:
        raise BladSerwera(
            "tryb legacy bez połączenia z masterem — wywołaj ustaw_tryb(..., polaczenie=con)",
            dostepny=False)
    return _polaczenie_lokalne
