# -*- coding: utf-8 -*-
"""subiekt_kopia_sync.py — kopia Subiekta (kartoteki, stany, miniatury) na serwer.

    python subiekt_kopia_sync.py                  # kartoteki + stany + NOWE miniatury
    python subiekt_kopia_sync.py --bez-miniatur   # tylko kartoteki i stany (~1 s)
    python subiekt_kopia_sync.py --miniatury-od-nowa

Po co: makro MAG (Inventor) (PLAN_MAG.md) czyta kartoteki przez HTTP
z serwera (`rm_mag_http.py`), a serwer W2019S nie ma mostu Sfery — ten
działa tylko na stacjach z SDK w `C:\\iLogic\\Subiekt\\Bin`. Stacja czyta więc
Subiekta mostem i odkłada KOPIĘ do `subiekt_kopia.sqlite` operacjami `sub-*`.

ŹRÓDŁA (wszystkie przez stały most, pomiar M-OLD 27.09.2026)
    katalog  — id, symbol, nazwa, opis, rodzaj, cena     0,2 s / 1584 kart.
    magazyn  — stany, progi, dostawca, rozbicie na mag.  0,8 s
    zdjecie  — galeria JEDNEJ kartoteki                  0,08 s / kartotekę

KARTOTEKI I STANY: za każdym razem komplet. Paczki idą do `kartoteki_nowe`,
a podmiana to jeden batch (jedna transakcja) — makro nigdy nie widzi połowy.

MINIATURY: drogie (po jednym zapytaniu na kartotekę, w firmie ~5 min na
całość), więc domyślnie tylko dla kartotek, których kopia jeszcze nie zna.
Kartoteka bez zdjęcia też dostaje wpis (pusty) — inaczej każdy przebieg
pytałby o nią od nowa. Zmienione zdjęcie w Subiekcie: `--miniatury-od-nowa`.

⚠️ To tylko KOPIA. Nic nie zapisuje do Subiekta.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import rm_klient

#: Wierszy kartotek w jednym `master-batch` (~300 B na wiersz).
PACZKA_KARTOTEK = 500
#: Miniatur w jednym batchu — każda to kilka–kilkadziesiąt KB base64,
#: a ramka serwera ma limit 8 MB.
PACZKA_MINIATUR = 40


def skonfiguruj_serwer(adres=None):
    """`--serwer host:port` albo `sync_config.json` (jak RM_BAZA)."""
    if adres:
        host, _, port = adres.partition(":")
        rm_klient.ustaw_serwer(host, int(port) if port else None)
    else:
        try:
            cfg = json.loads(Path(r"C:\RMPAK_CLIENT\sync_config.json")
                             .read_text(encoding="utf-8-sig"))
            s = cfg.get("rm_serwer") or {}
            if s.get("host"):
                rm_klient.ustaw_serwer(s["host"], s.get("port"), s.get("sekret"))
        except Exception:
            pass              # brak pliku = adres firmowy z rm_klient
    rm_klient.ustaw_uzytkownika("SUBIEKT_KOPIA_SYNC")


def _teraz():
    return datetime.now().isoformat(timespec="seconds")


def _typ_obrazka(dane: bytes, typ_z_subiekta: str) -> str:
    """Typ po nagłówku pliku — `Typ` zdjęcia opisuje oryginał, nie miniaturę."""
    if dane[:4] == b"\x89PNG":
        return "png"
    if dane[:2] == b"\xff\xd8":
        return "jpg"
    if dane[:2] == b"BM":
        return "bmp"
    if dane[:3] == b"GIF":
        return "gif"
    return (typ_z_subiekta or "png").lower().lstrip(".")


def _dziennik(co, ile, sekund):
    return {"operation": "sub-synchronizacja-dodaj", "params": {
        "co": co, "ile": ile, "sekund": round(sekund, 1),
        "kto": os.environ.get("USERNAME") or "?",
        "komputer": os.environ.get("COMPUTERNAME") or "?", "kiedy": _teraz()}}


# ── kartoteki + stany ───────────────────────────────────────────────────────

def czytaj_kartoteki():
    """[wiersz tabeli `kartoteki`] — katalog złączony ze stanami po Id."""
    import subiekt_podobne
    from subiekt_magazyn_gui import pobierz_magazyn

    katalog = subiekt_podobne.pobierz_katalog()
    # Wszystkie kartoteki, także z zerowym stanem — makro ma pokazać „0",
    # a nie „brak danych".
    stany = {p.get("Id"): p for p in (pobierz_magazyn(tylko_niezerowe=False) or [])}
    kiedy = _teraz()
    wiersze = []
    for k in katalog:
        s = stany.get(k.get("id")) or {}
        wiersze.append({
            "id": k.get("id"),
            "symbol": (k.get("symbol") or "").strip(),
            "nazwa": k.get("nazwa") or "",
            "opis": k.get("opis") or "",
            "rodzaj": k.get("rodzaj") or "",
            "cena": k.get("cena"),
            "dostepne": s.get("Dostepne"),
            "zarezerwowane": s.get("Zarezerwowane"),
            "zadysponowane": s.get("Zadysponowane"),
            "stan_min": s.get("StanMinimalny"),
            "stan_opt": s.get("StanOptymalny"),
            "dostawca": s.get("Dostawca"),
            "magazyny_json": json.dumps(s.get("Magazyny") or [], ensure_ascii=False),
            "zsynchronizowano": kiedy,
        })
    return wiersze, len(stany)


def wyslij_kartoteki(wiersze, sekund):
    rm_klient.master_exec("sub-kartoteki-nowe-czysc", {})
    for i in range(0, len(wiersze), PACZKA_KARTOTEK):
        rm_klient.master_batch(
            [{"operation": "sub-kartoteka-nowa", "params": w}
             for w in wiersze[i:i + PACZKA_KARTOTEK]], timeout=120)
    # Podmiana kompletu — JEDNA transakcja.
    rm_klient.master_batch([
        {"operation": "sub-kartoteki-usun-wszystkie", "params": {}},
        {"operation": "sub-kartoteki-wstaw", "params": {}},
        {"operation": "sub-miniatury-sieroty-usun", "params": {}},
        _dziennik("kartoteki", len(wiersze), sekund),
    ], timeout=120)


# ── miniatury ───────────────────────────────────────────────────────────────

def miniatura_kartoteki(symbol):
    """(numer, typ, bajty) głównego zdjęcia albo None, gdy galeria pusta.

    Most oddaje bajty miniatury tylko dla zdjęcia o numerze z `Miniatura`.
    Pytamy od razu o nr 1 (zwykle główne); gdy główne ma inny numer —
    drugie zapytanie.
    """
    import subiekt_bridge

    def lista(numer):
        return subiekt_bridge.call(
            "zdjecie", {"plan": {"akcja": "lista", "symbol": symbol,
                                 "miniatura": numer}, "zapisz": False},
            timeout=120, write=False) or {}

    r = lista(1)
    zdjecia = r.get("zdjecia") or []
    if not zdjecia:
        return None
    glowne = next((z for z in zdjecia if z.get("Glowne")), zdjecia[0])
    numer = glowne.get("Numer")
    if numer != 1:
        r = lista(numer)
    b64 = r.get("miniatura_b64")
    if not b64:
        return None
    dane = base64.b64decode(b64)
    return numer, _typ_obrazka(dane, glowne.get("Typ")), b64


def _nic(_tekst):
    pass


def synchronizuj_miniatury(kartoteki, od_nowa=False, limit=0, postep=_nic):
    znane = set()
    if not od_nowa:
        znane = {w["id_subiekt"] for w in rm_klient.master_read(
            "sub-miniatury-stan", timeout=120)}
    do_zrobienia = [k for k in kartoteki if k["id"] not in znane and k["symbol"]]
    if limit:
        do_zrobienia = do_zrobienia[:limit]
    print(f"\n3. Miniatury: do sprawdzenia {len(do_zrobienia)}"
          f" (znane: {len(znane)})")
    if not do_zrobienia:
        return 0, 0

    t0 = time.time()
    paczka, z_obrazkiem, bledy = [], 0, []
    for i, k in enumerate(do_zrobienia, 1):
        try:
            m = miniatura_kartoteki(k["symbol"])
        except Exception as e:
            # Błąd jednej kartoteki nie przerywa reszty — i NIE zapisujemy
            # jej jako „bez zdjęcia", bo to byłaby nieprawda.
            bledy.append((k["symbol"], str(e)[:100]))
            continue
        numer, typ, b64 = m if m else (None, None, "")
        z_obrazkiem += 1 if m else 0
        paczka.append({"operation": "sub-miniatura-zapisz", "params": {
            "id_subiekt": k["id"], "symbol": k["symbol"], "numer_zdjecia": numer,
            "typ": typ, "dane_b64": b64, "zsynchronizowano": _teraz()}})
        if len(paczka) >= PACZKA_MINIATUR:
            rm_klient.master_batch(paczka, timeout=120)
            paczka = []
        if i % 100 == 0:
            postep(f"miniatury {i}/{len(do_zrobienia)}, z obrazkiem {z_obrazkiem}")
        if i % 200 == 0:
            print(f"   … {i}/{len(do_zrobienia)}  z obrazkiem {z_obrazkiem}"
                  f"  ({time.time() - t0:.0f}s)")
    paczka.append(_dziennik("miniatury", len(do_zrobienia) - len(bledy),
                            time.time() - t0))
    rm_klient.master_batch(paczka, timeout=120)

    print(f"   sprawdzono {len(do_zrobienia) - len(bledy)}, z obrazkiem"
          f" {z_obrazkiem}, błędów {len(bledy)}  ({time.time() - t0:.0f}s)")
    for sym, blad in bledy[:10]:
        print(f"   ⚠️  {sym}: {blad}")
    return z_obrazkiem, len(bledy)


def synchronizuj(z_miniaturami=True, miniatury_od_nowa=False, limit_miniatur=0,
                 postep=_nic):
    """Cała synchronizacja. Zwraca jednolinijkowy opis wyniku.

    Wołane z konsoli (`main`) i przez wykonawcę zleceń w RM_BAZA
    (`subiekt_kopia_zlecenia`). `postep(tekst)` dostaje krótkie komunikaty
    — wykonawca odsyła je na serwer, a MAG pokazuje na pasku.
    Rzuca przy błędzie; pusty katalog z mostu to też błąd.
    """
    t0 = time.time()
    postep("czytam katalog i stany z Subiekta")
    kartoteki, ze_stanem = czytaj_kartoteki()
    t_odczyt = time.time() - t0
    print(f"\n1. Subiekt: {len(kartoteki)} kartotek, stany dla {ze_stanem}"
          f"  ({t_odczyt:.1f}s)")
    if not kartoteki:
        # Pusty katalog to prawie na pewno awaria mostu, nie pusty Subiekt —
        # podmiana wyczyściłaby kopię na serwerze.
        raise RuntimeError("most zwrócił pusty katalog — kopii NIE podmieniono")

    t1 = time.time()
    postep(f"wysyłam {len(kartoteki)} kartotek na serwer")
    wyslij_kartoteki(kartoteki, t_odczyt)
    print(f"\n2. Serwer: kopia kartotek podmieniona  ({time.time() - t1:.1f}s)")
    opis = f"kartotek {len(kartoteki)}"

    if z_miniaturami:
        z_obrazkiem, bledy = synchronizuj_miniatury(
            kartoteki, miniatury_od_nowa, limit_miniatur, postep)
        opis += f", miniatur z obrazkiem {z_obrazkiem}"
        if bledy:
            opis += f", błędów {bledy}"
    opis += f" ({time.time() - t0:.0f} s)"
    print(f"\nGotowe: {opis}")
    return opis


def main():
    sys.stdout.reconfigure(encoding="utf-8")       # polska konsola, cp1250
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serwer", help="host:port RM_SERWER (domyślnie z sync_config.json)")
    ap.add_argument("--bez-miniatur", action="store_true")
    ap.add_argument("--miniatury-od-nowa", action="store_true",
                    help="pobierz ponownie miniatury WSZYSTKICH kartotek")
    ap.add_argument("--limit-miniatur", type=int, default=0,
                    help="najwyżej N kartotek (do próby)")
    a = ap.parse_args()

    skonfiguruj_serwer(a.serwer)
    print("=" * 72)
    print("KOPIA SUBIEKTA -> SERWER")
    print(f"   {rm_klient.opis()}")
    print("=" * 72)
    try:
        synchronizuj(not a.bez_miniatur, a.miniatury_od_nowa, a.limit_miniatur)
    except RuntimeError as e:
        print(f"   ⛔ {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
