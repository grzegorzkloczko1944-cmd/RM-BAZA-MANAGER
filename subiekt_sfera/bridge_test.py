# -*- coding: utf-8 -*-
"""Testowy klient stalego mostu — niezalezny od RM_BAZA.

Sluzy do udowodnienia glownej tezy przebudowy (SUBIEKT_STALY_MOST_PLAN.md,
Krok G): drugie wywolanie tej samej komendy NIE placi ~9-10 s za start
procesu i logowanie do Sfery.

Uzycie:

    python bridge_test.py ping
    python bridge_test.py katalog
    python bridge_test.py bench          # katalog x3 + inne READ, z czasami

Most musi juz dzialac:

    NexoRecon.exe server --console
"""

import json
import socket
import struct
import sys
import time
import uuid

HOST = "127.0.0.1"
PORT = 51273


def call(command, args=None, timeout=300, sock=None):
    """Wysyla komende do mostu i zwraca (odpowiedz, czas_ms).

    `sock` pozwala puscic kilka komend po JEDNYM polaczeniu — wtedy mierzymy
    sam czas komendy, bez narzutu na zestawienie TCP.
    """
    wlasny = sock is None
    if wlasny:
        sock = socket.create_connection((HOST, PORT), timeout=timeout)
        sock.settimeout(timeout)
    try:
        zadanie = {
            "protocol": 1,
            "request_id": str(uuid.uuid4()),
            "command": command,
            "args": args or {},
        }
        surowe = json.dumps(zadanie, ensure_ascii=False).encode("utf-8")
        t0 = time.perf_counter()
        sock.sendall(struct.pack("<i", len(surowe)) + surowe)

        naglowek = _czytaj(sock, 4)
        (dlugosc,) = struct.unpack("<i", naglowek)
        tresc = _czytaj(sock, dlugosc)
        ms = (time.perf_counter() - t0) * 1000
        return json.loads(tresc.decode("utf-8")), ms
    finally:
        if wlasny:
            sock.close()


def _czytaj(sock, ile):
    bufor = b""
    while len(bufor) < ile:
        czesc = sock.recv(ile - len(bufor))
        if not czesc:
            raise ConnectionError("Most zamknal polaczenie.")
        bufor += czesc
    return bufor


def _ile_pozycji(odp):
    """Ile rekordow zwrocila komenda — do sprawdzenia, czy dane sa te same."""
    dane = odp.get("data") or {}
    for klucz in ("pozycje", "kontrahenci", "dokumenty"):
        if isinstance(dane.get(klucz), list):
            return len(dane[klucz])
    return sum(len(v) for v in dane.values() if isinstance(v, list))


def bench():
    """Glowny dowod: pierwszy katalog vs kolejne, po jednym polaczeniu."""
    print(f"{'komenda':<22}{'czas':>10}   wynik")
    print("-" * 55)

    with socket.create_connection((HOST, PORT), timeout=300) as s:
        s.settimeout(300)
        odp, ms = call("status", sock=s)
        d = odp.get("data", {})
        print(f"{'status':<22}{ms:>8.0f}ms   ready={d.get('ready')} "
              f"logowan={d.get('logins')} obsluzonych={d.get('handled')}")

        for i in range(1, 4):
            odp, ms = call("katalog", sock=s)
            ok = odp.get("ok")
            print(f"{'katalog #' + str(i):<22}{ms:>8.0f}ms   "
                  f"{'pozycji=' + str(_ile_pozycji(odp)) if ok else odp.get('error')}")

        for cmd in ("kontrahenci", "dokumenty", "magazyn", "zapotrzebowanie"):
            odp, ms = call(cmd, sock=s)
            ok = odp.get("ok")
            print(f"{cmd:<22}{ms:>8.0f}ms   "
                  f"{'rekordow=' + str(_ile_pozycji(odp)) if ok else odp.get('error')}")

        odp, _ = call("status", sock=s)
        d = odp.get("data", {})
        print("-" * 55)
        print(f"logowan do Sfery: {d.get('logins')}   "
              f"obsluzonych komend: {d.get('handled')}   "
              f"uptime: {d.get('uptime_s')}s")
        if d.get("logins") == 1:
            print("OK — jedna sesja obsluzyla wszystkie komendy.")
        else:
            print(f"UWAGA — sesja byla zestawiana {d.get('logins')} razy.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    try:
        if cmd == "bench":
            bench()
            return 0
        odp, ms = call(cmd)
        print(f"[{ms:.0f} ms]")
        print(json.dumps(odp, ensure_ascii=False, indent=2)[:2000])
        return 0 if odp.get("ok") else 1
    except (ConnectionRefusedError, OSError) as e:
        print(f"Brak mostu na {HOST}:{PORT} ({e}).\nUruchom: NexoRecon.exe server --console")
        return 2


if __name__ == "__main__":
    sys.exit(main())
