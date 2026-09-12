# -*- coding: utf-8 -*-
"""RM_SERWER — jedyny właściciel master.sqlite.

    RM_BAZA (10 stanowisk) ──TCP──► RM_SERWER ──► C:\\Apps\\RM_SERWER\\dane\\master.sqlite

Powód istnienia (PLAN_RM_SERWER.md §0): dziesięć procesów otwierających jeden
plik SQLite przez SMB. 11.09.2026 master był zablokowany do zapisu 96–100%
czasu przez ponad 40 minut — nieudany `commit()` zostawiał transakcję otwartą,
a każdy kolejny klient dokładał swoją. Zakleszczenie odtwarzało się samo.
Jeden proces z jednym połączeniem usuwa przyczynę, zamiast ją obchodzić.

ARCHITEKTURA (wzorzec mostu Subiekta — `ServerHost.cs`)

    TcpListener (wątek na klienta)
         │
         ▼
    Queue[Zadanie]
         │
         ▼
    JEDEN wątek roboczy ──► sqlite3.Connection ──► master.sqlite

Wątki TCP nigdy nie dotykają bazy — wkładają zadanie do kolejki i czekają na
wynik. Współbieżność **znika z problemu**, zamiast być obsługiwana blokadami.

URUCHOMIENIE

    python rm_serwer.py                     # pierwszy plan, nasłuch wg config
    python rm_serwer.py --sprawdz           # diagnostyka: baza, operacje, port
    python rm_serwer.py --port 5060 --baza C:\\...\\master.sqlite

Na serwerze chodzi jako usługa NSSM — patrz `NOW/DOKUMENTACJA/DOSTEP_SERWER.md`.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import queue
import socket
import sqlite3
import struct
import sys
import threading
import time
import traceback
from datetime import datetime

import rm_serwer_operacje as ops

# ⚠️ Konsola Windows to domyślnie cp1250 — `print` z emoji rzuca wtedy
# UnicodeEncodeError i WYWALA PROCES. Pod NSSM i przez WinRM dzieje się to
# zawsze, więc bez tego serwer padał na własnym komunikacie diagnostycznym.
# Ten sam problem co przy starcie RM_BAZA (project_cp1250_emoji_print).
for _strumien in (sys.stdout, sys.stderr):
    try:
        _strumien.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════════════
# Konfiguracja
# ═══════════════════════════════════════════════════════════════════════

WERSJA = "1.0.0"

#: Wersja protokołu. Klient zna minimalną zgodną i przy niezgodności mówi
#: wprost, co zaktualizować — mechanizm z `subiekt_bridge._sprawdz_protokol`.
#: Rośnie, gdy zmiana łamie zgodność ramki albo znaczenia pól.
PROTOKOL = 1

KATALOG = os.path.dirname(os.path.abspath(__file__))
DOMYSLNA_BAZA = os.path.join(KATALOG, "dane", "master.sqlite")

#: Mapowania numer rysunku → kartoteka Subiekta. OSOBNY plik, obok mastera
#: (decyzja 11.09.2026: wszystkie bazy w jednym katalogu na serwerze).
DOMYSLNA_BAZA_MAPOWANIA = os.path.join(KATALOG, "dane", "subiekt_mapowania.sqlite")

# Trzecia baza: RM_MANAGER. Leży obok pozostałych w `dane\` — wszystkie bazy
# systemu w jednym miejscu, na lokalnym dysku serwera.
DOMYSLNA_BAZA_RM_MANAGER = os.path.join(KATALOG, "dane", "rm_manager.sqlite")
DOMYSLNY_PORT = 5060

#: Ile trzymamy odpowiedzi w `_server_request_log` (§3 planu).
RETENCJA_DZIENNIKA_H = 24

#: Limit ramki — zapora przed przypadkowym śmieciem z sieci zanim cokolwiek
#: sparsujemy. Największe realne żądanie to `master-batch` z kilkudziesięcioma
#: operacjami, czyli kilkadziesiąt KB.
MAX_RAMKA = 8 * 1024 * 1024


def wczytaj_config(sciezka=None):
    """Konfiguracja z pliku obok serwera. Brak pliku = wartości domyślne."""
    sciezka = sciezka or os.path.join(KATALOG, "rm_serwer_config.json")
    dane = {}
    if os.path.isfile(sciezka):
        try:
            with open(sciezka, "r", encoding="utf-8-sig") as f:   # -sig: BOM
                dane = json.load(f)
        except Exception as e:
            print("⚠️  Nie wczytano %s: %s — biorę domyślne" % (sciezka, e))
    return {
        "baza": dane.get("baza", DOMYSLNA_BAZA),
        "baza_mapowania": dane.get("baza_mapowania", DOMYSLNA_BAZA_MAPOWANIA),
        "baza_rm_manager": dane.get("baza_rm_manager", DOMYSLNA_BAZA_RM_MANAGER),
        "port": int(dane.get("port", DOMYSLNY_PORT)),
        "nasluch": dane.get("nasluch", "0.0.0.0"),
        "sekret": dane.get("sekret"),          # None = HMAC wyłączony
        "backup_katalog": dane.get("backup_katalog",
                                   os.path.join(KATALOG, "backup")),
        "backup_ile": int(dane.get("backup_ile", 20)),
        "log_katalog": dane.get("log_katalog", os.path.join(KATALOG, "logi")),
    }


# ═══════════════════════════════════════════════════════════════════════
# Log
# ═══════════════════════════════════════════════════════════════════════

_log_lock = threading.Lock()
_log_plik = None


def log(tekst):
    """Jedna linia do konsoli i do pliku dziennego.

    Pod NSSM stdout idzie do pliku usługi, ale własny log przeżywa restart
    usługi i daje się filtrować po operacji — to po nim szuka się „kto
    skasował dostawcę".
    """
    linia = "%s  %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tekst)
    with _log_lock:
        try:
            print(linia, flush=True)
        except Exception:
            pass                      # konsola cp1250 vs emoji — nie przerywa pracy
        if _log_plik:
            try:
                with open(_log_plik, "a", encoding="utf-8") as f:
                    f.write(linia + "\n")
            except Exception:
                pass


def _ustaw_log(katalog):
    global _log_plik
    try:
        os.makedirs(katalog, exist_ok=True)
        _log_plik = os.path.join(
            katalog, "rm_serwer_%s.log" % datetime.now().strftime("%Y%m%d"))
    except Exception as e:
        print("⚠️  Log do pliku wyłączony: %s" % e)


# ═══════════════════════════════════════════════════════════════════════
# Ramka: 4 bajty długości (LE) + UTF-8 JSON
# ═══════════════════════════════════════════════════════════════════════

def _nasz_znacznik(ogon: str) -> bool:
    """Czy to nasza automatyczna kopia, czyli `RRRRMMDD_GGMMSS`.

    Rotacja kasuje najstarsze pliki, więc musi rozpoznawać WYŁĄCZNIE własne.
    Obok leżą ręczne kopie z wdrożenia (`master_przed_rfq_20260911_201520`),
    a te mają zostać — ktoś je zrobił świadomie przed groźną zmianą.
    """
    return (len(ogon) == 15 and ogon[8] == "_"
            and ogon[:8].isdigit() and ogon[9:].isdigit())


def _czytaj_dokladnie(sock, ile):
    bufor = b""
    while len(bufor) < ile:
        kawalek = sock.recv(ile - len(bufor))
        if not kawalek:
            return None               # druga strona zamknęła
        bufor += kawalek
    return bufor


def czytaj_ramke(sock):
    naglowek = _czytaj_dokladnie(sock, 4)
    if naglowek is None:
        return None
    (dlugosc,) = struct.unpack("<i", naglowek)
    if dlugosc < 0 or dlugosc > MAX_RAMKA:
        raise ValueError("ramka %d B poza limitem" % dlugosc)
    surowe = _czytaj_dokladnie(sock, dlugosc)
    if surowe is None:
        return None
    return json.loads(surowe.decode("utf-8"))


def wyslij_ramke(sock, obiekt):
    surowe = json.dumps(obiekt, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack("<i", len(surowe)) + surowe)


# ═══════════════════════════════════════════════════════════════════════
# HMAC
# ═══════════════════════════════════════════════════════════════════════

def kanoniczny_json(obiekt):
    """Postać, na której liczymy podpis — MUSI być identyczna po obu stronach.

    Trzy rzeczy ustalone na sztywno: kolejność kluczy (`sort_keys`), brak
    spacji (`separators`) i kodowanie znaków (`ensure_ascii=False` — w danych
    są polskie znaki i nazwy dostawców). Bez tego podpis raz na jakiś czas
    nie zgodzi się bez powodu (§7 planu).
    """
    return json.dumps(obiekt or {}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def policz_hmac(sekret, request_id, cmd, args):
    """HMAC-SHA256 po `request_id|cmd|kanoniczny_json(args)`.

    Separator `|` między członami, żeby sklejenie pól nie dawało kolizji:
    („ab", „c") i („a", „bc") muszą dać różne podpisy.
    """
    tresc = "%s|%s|%s" % (request_id or "", cmd or "", kanoniczny_json(args))
    return hmac.new(sekret.encode("utf-8"), tresc.encode("utf-8"),
                    hashlib.sha256).hexdigest()


# ═══════════════════════════════════════════════════════════════════════
# Wątek roboczy — JEDYNY, który dotyka bazy
# ═══════════════════════════════════════════════════════════════════════

class Zadanie:
    __slots__ = ("zadanie", "wynik", "gotowe")

    def __init__(self, zadanie):
        self.zadanie = zadanie
        self.wynik = None
        self.gotowe = threading.Event()


class Serwer:
    def __init__(self, config):
        self.config = config
        self.baza = config["baza"]
        self.kolejka = queue.Queue()
        self.con = None
        self.con_map = None            # subiekt_mapowania.sqlite — osobny plik
        self.con_rmm = None            # rm_manager.sqlite — osobny plik
        self.start_czas = time.time()
        self.zapisow = 0
        self.odczytow = 0
        self.stop = threading.Event()
        self._ostatnie_sprzatanie = 0.0
        self._ostatni_backup = None

    # ── baza ──────────────────────────────────────────────────────────
    def polacz(self):
        os.makedirs(os.path.dirname(self.baza), exist_ok=True)
        nowa = not os.path.isfile(self.baza)
        self.con = sqlite3.connect(self.baza, timeout=30,
                                   check_same_thread=False)
        # journal=DELETE, nie WAL: baza jest lokalna, ale kopiujemy ją
        # przy rollbacku i backupie — WAL wymagałby checkpointu przed każdą
        # kopią, a DELETE zostawia jeden samowystarczalny plik.
        self.con.execute("PRAGMA journal_mode=DELETE")
        self.con.execute("PRAGMA synchronous=FULL")   # jedyny właściciel = stać nas
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.execute("PRAGMA busy_timeout=5000")
        if nowa:
            log("⚠️  Baza nie istniała — utworzono pustą: %s" % self.baza)
        zrobione = ops.zastosuj_migracje(self.con)
        if zrobione:
            log("Migracje: %d" % len(zrobione))
            for z in zrobione:
                log("   + %s" % z)
        mapa = ops.zbuduj_operacje_dostawcow(self.con)
        if mapa:
            log("Schemat suppliers: %s" % mapa)

        # Druga baza: mapowania Subiekta. Osobny plik, więc osobne
        # połączenie — ale ten sam wątek roboczy, więc nadal jeden pisarz.
        sciezka_map = self.config.get("baza_mapowania")
        if sciezka_map:
            os.makedirs(os.path.dirname(sciezka_map), exist_ok=True)
            self.con_map = sqlite3.connect(sciezka_map, timeout=30,
                                           check_same_thread=False)
            self.con_map.execute("PRAGMA journal_mode=DELETE")
            self.con_map.execute("PRAGMA synchronous=FULL")
            self.con_map.execute("PRAGMA busy_timeout=5000")
            for sql in ops.MIGRACJE_MAPOWANIA:
                self.con_map.execute(sql)
            self.con_map.commit()
            log("Mapowania: %s" % sciezka_map)

        # Trzecia baza: RM_MANAGER. Znów osobny plik i osobne połączenie,
        # ale ten sam wątek roboczy — nadal JEDEN pisarz na cały serwer.
        sciezka_rmm = self.config.get("baza_rm_manager")
        if sciezka_rmm:
            os.makedirs(os.path.dirname(sciezka_rmm), exist_ok=True)
            self.con_rmm = sqlite3.connect(sciezka_rmm, timeout=30,
                                           check_same_thread=False)
            self.con_rmm.execute("PRAGMA journal_mode=DELETE")
            self.con_rmm.execute("PRAGMA synchronous=FULL")
            self.con_rmm.execute("PRAGMA busy_timeout=5000")
            # ⚠️ Klucze obce są w tym schemacie używane (ON DELETE CASCADE),
            # a SQLite ma je DOMYŚLNIE WYŁĄCZONE — bez tego kasowanie
            # pracownika zostawiłoby osierocone wpisy w kilku tabelach.
            self.con_rmm.execute("PRAGMA foreign_keys=ON")
            for sql, _warunek in ops.MIGRACJE_RM_MANAGER:
                self.con_rmm.execute(sql)
            self.con_rmm.commit()
            log("RM_MANAGER: %s" % sciezka_rmm)

    # ── wykonanie pojedynczego żądania (w wątku roboczym) ─────────────
    def _polaczenie(self, operacja):
        """Które połączenie obsługuje tę operację.

        Prefiks `map-` → subiekt_mapowania.sqlite,
        prefiks `rmm-` → rm_manager.sqlite,
        reszta → master RM_BAZA.

        Routing po nazwie, nie po tabeli: wołający nie musi wiedzieć,
        w którym pliku co leży.
        """
        nazwa = operacja or ""
        if nazwa.startswith("map-"):
            if self.con_map is None:
                raise ops.BladOperacji("baza mapowań nie jest skonfigurowana")
            return self.con_map
        if nazwa.startswith("rmm-"):
            if self.con_rmm is None:
                raise ops.BladOperacji("baza RM_MANAGER nie jest skonfigurowana")
            return self.con_rmm
        return self.con

    def _wykonaj(self, z):
        cmd = z.get("cmd")
        args = z.get("args") or {}
        kto = z.get("kto") or {}
        rid = z.get("request_id")

        if cmd == "ping":
            return {"ok": True, "data": {
                "protokol": PROTOKOL, "wersja": WERSJA,
                "uptime_s": round(time.time() - self.start_czas, 1),
                "zapisow_od_startu": self.zapisow,
                "odczytow_od_startu": self.odczytow,
                "baza": self.baza,
            }}

        if cmd == "master-read":
            operacja = args.get("operation")
            wiersze = ops.wykonaj_odczyt(self._polaczenie(operacja), operacja,
                                         args.get("params"))
            self.odczytow += 1
            return {"ok": True, "data": {"rows": wiersze}}

        if cmd in ("master-exec", "master-batch"):
            return self._zapis(cmd, args, kto, rid)

        raise ops.BladOperacji("nieznana komenda: %r" % (cmd,))

    def _zapis(self, cmd, args, kto, rid):
        """Zapis + wpis do dziennika w JEDNEJ transakcji (§3)."""
        if not rid:
            raise ops.BladOperacji("operacja zmieniająca wymaga request_id")

        # Idempotencja: to samo request_id = ta sama odpowiedź, bez wykonania.
        if cmd == "master-exec":
            operacje = [{"operation": args.get("operation"),
                         "params": args.get("params")}]
        else:
            operacje = args.get("operacje") or []
            if not operacje:
                raise ops.BladOperacji("master-batch bez operacji")

        # Wszystkie operacje żądania muszą trafić do JEDNEJ bazy — transakcja
        # SQLite nie rozciąga się na dwa pliki. Mieszany batch odrzucamy,
        # zamiast po cichu zapisać połowę.
        con = self._polaczenie(operacje[0].get("operation"))
        for o in operacje[1:]:
            if self._polaczenie(o.get("operation")) is not con:
                raise ops.BladOperacji(
                    "batch miesza operacje z dwóch baz — rozdziel je")

        # Dziennik leży w TEJ SAMEJ bazie co operacja, bo zapis i jego ślad
        # idą jedną transakcją (§3). Na dysku, nie w pamięci — inaczej nie
        # chroniłby przed „serwer padł tuż po commicie".
        wiersz = con.execute(
            "SELECT result_json FROM _server_request_log WHERE request_id = ?",
            (rid,)).fetchone()
        if wiersz is not None:
            log("↩ powtórzone %s rid=%s — zwracam zapamiętany wynik" % (cmd, rid[:8]))
            dane = json.loads(wiersz[0]) if wiersz[0] else {}
            dane["powtorzone"] = True
            return {"ok": True, "data": dane}

        opis = ",".join(o.get("operation") or "?" for o in operacje)
        wyniki = []
        try:
            con.execute("BEGIN IMMEDIATE")
            for o in operacje:
                wyniki.append(ops.wykonaj_zapis(con, o.get("operation"),
                                                o.get("params")))
            dane = {"wyniki": wyniki} if cmd == "master-batch" else wyniki[0]
            con.execute(
                "INSERT INTO _server_request_log"
                " (request_id, operation, kto, result_json, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (rid, opis, json.dumps(kto, ensure_ascii=False),
                 json.dumps(dane, ensure_ascii=False),
                 datetime.now().isoformat(timespec="seconds")))
            con.commit()
        except Exception:
            # Rollback ZAWSZE — to jest dokładnie ta rzecz, której brak
            # wywołał awarię 11.09 (nieudany commit zostawiał transakcję).
            try:
                con.rollback()
            except Exception:
                pass
            raise

        self.zapisow += 1
        log("✓ %s %s rid=%s przez %s@%s" % (
            cmd, opis, rid[:8], kto.get("user", "?"), kto.get("host", "?")))
        return {"ok": True, "data": dane}

    # ── pętla wątku roboczego ─────────────────────────────────────────
    def worker(self):
        self.polacz()
        log("Baza gotowa: %s" % self.baza)
        while not self.stop.is_set():
            try:
                zad = self.kolejka.get(timeout=1.0)
            except queue.Empty:
                self._sprzatanie()
                continue
            try:
                zad.wynik = self._wykonaj(zad.zadanie)
            except ops.BladOperacji as e:
                zad.wynik = {"ok": False, "blad": str(e)}
            except sqlite3.Error as e:
                log("⚠️  SQLite: %s" % e)
                zad.wynik = {"ok": False, "blad": "baza: %s" % e}
            except Exception as e:
                log("⚠️  %s: %s" % (type(e).__name__, e))
                log(traceback.format_exc())
                zad.wynik = {"ok": False, "blad": "%s: %s" % (type(e).__name__, e)}
            finally:
                zad.gotowe.set()

    def _backup_jednej(self, con, prefiks, katalog=None):
        """Spójna kopia JEDNEJ bazy + rotacja jej własnych kopii.

        `sqlite3.Connection.backup` (Online Backup API) kopiuje bazę **bez
        blokowania zapisów** i bez ryzyka złapania pliku w połowie transakcji —
        inaczej niż `shutil.copy2`, którym robił to klient. Dlatego backup
        przeniósł się tutaj: klient, który nie otwiera już mastera, nie ma jak
        zrobić spójnej kopii.
        """
        katalog = katalog or self.config["backup_katalog"]
        os.makedirs(katalog, exist_ok=True)
        nazwa = "%s_%s.sqlite" % (prefiks, datetime.now().strftime("%Y%m%d_%H%M%S"))
        cel = os.path.join(katalog, nazwa)
        docelowe = sqlite3.connect(cel)
        try:
            con.backup(docelowe)
        finally:
            docelowe.close()

        # Rotacja: zostaje N najnowszych. Po nazwie, nie po mtime — nazwa
        # niesie czas utworzenia i nie zmienia się przy kopiowaniu katalogu.
        #
        # ⚠️ Filtrujemy po PEŁNYM prefiksie z podkreśleniem. Samo
        # `startswith("master_")` łapałoby też `master_przed_rfq_...`
        # (ręczne kopie z wdrożenia) i rotacja kasowałaby cudze pliki.
        czolo = prefiks + "_"
        kopie = sorted(f for f in os.listdir(katalog)
                       if f.startswith(czolo) and f.endswith(".sqlite")
                       and _nasz_znacznik(f[len(czolo):-len(".sqlite")]))
        ile = max(1, int(self.config.get("backup_ile", 20)))
        for stara in kopie[:-ile]:
            try:
                os.remove(os.path.join(katalog, stara))
            except OSError:
                pass
        log("Backup: %s (%.1f KB), kopii tej bazy: %d"
            % (nazwa, os.path.getsize(cel) / 1024, min(len(kopie), ile)))
        return cel

    def _backup(self):
        """Kopia WSZYSTKICH baz, którymi opiekuje się serwer.

        Wcześniej kopiowany był wyłącznie master RM_BAZA — `rm_manager.sqlite`
        (81 projektów, definicje etapów, blokady) i `subiekt_mapowania.sqlite`
        nie miały żadnego backupu, mimo że serwer jest ich jedynym właścicielem
        i nikt inny nie ma jak ich skopiować.

        Każda baza trafia do katalogu SWOJEGO programu — tam, gdzie klient
        trzyma backupy projektów — żeby kopie jednej aplikacji leżały w jednym
        miejscu, zamiast rozsypane po dwóch (ustalone 12.09.2026):

            master.sqlite             -> backup_RM_BAZA\\master
            rm_manager.sqlite         -> backup_RM_MANAGER\\master
            subiekt_mapowania.sqlite  -> backup_RM_BAZA\\master (obsługuje ją RM_BAZA)
        """
        zrobione = []
        for con, prefiks, katalog in (
                (self.con, "master", self._katalog_backupu("BAZA")),
                (self.con_rmm, "rm_manager", self._katalog_backupu("MANAGER")),
                (self.con_map, "subiekt_mapowania", self._katalog_backupu("BAZA"))):
            if con is None:
                continue
            try:
                zrobione.append(self._backup_jednej(con, prefiks, katalog))
            except Exception as e:
                # Nieudany backup jednej bazy nie może zablokować pozostałych.
                log("⚠️  Backup %s nieudany: %s" % (prefiks, e))
        return zrobione

    def _katalog_backupu(self, ktora: str) -> str:
        """Katalog `master\\` wewnątrz backupów danego programu.

        Konfiguracyjny `backup_katalog` pozostaje wartością zapasową — gdyby
        ktoś wskazał własną ścieżkę, wygrywa ona i wszystko ląduje tam, tak
        jak działo się to wcześniej.
        """
        wlasny = self.config.get("backup_katalog_%s" % ktora.lower())
        if wlasny:
            return wlasny
        korzen = os.path.dirname(self.baza)          # …\dane
        return os.path.join(korzen, "Projekty", "backup_RM_%s" % ktora, "master")

    def _sprzatanie(self):
        """Raz na dobę: czyszczenie dziennika. Robione w wątku roboczym,
        żeby nie dotykać połączenia z innego miejsca."""
        if time.time() - self._ostatnie_sprzatanie < 3600:
            return
        self._ostatnie_sprzatanie = time.time()
        try:
            ile = ops.wyczysc_dziennik(self.con, RETENCJA_DZIENNIKA_H)
            if ile:
                log("Dziennik: usunięto %d wpisów starszych niż %d h"
                    % (ile, RETENCJA_DZIENNIKA_H))
        except Exception as e:
            log("⚠️  Sprzątanie dziennika: %s" % e)

        # Backup raz na dobę — i tylko gdy coś się zapisało. Kopia bazy,
        # w której nic się nie zmieniło, to zajęte miejsce bez wartości.
        #
        # ⚠️ „Czy była już dziś kopia" czytamy z KATALOGU, nie z pola w
        # pamięci. Pole ginęło przy każdym restarcie usługi i dawało dwa
        # przeciwne błędy naraz: 11.09 powstały trzy kopie w ciągu doby
        # (20:51, 23:26, 00:57 — po każdym restarcie), a po restarcie
        # licznik zapisów też startuje od zera, więc dzień bez ruchu przez
        # kolejne 60 minut kończył się BRAKIEM backupu. Katalog pamięta to,
        # czego proces nie pamięta.
        try:
            if self._trzeba_backupu():
                self._backup()
        except Exception as e:
            log("⚠️  Backup nieudany: %s" % e)

    def _trzeba_backupu(self) -> bool:
        """Czy dziś powstała już automatyczna kopia mastera."""
        dzis = datetime.now().strftime("%Y%m%d")
        if self._ostatni_backup == dzis:
            return False
        katalog = self._katalog_backupu("BAZA")
        try:
            for f in os.listdir(katalog):
                if (f.startswith("master_") and f.endswith(".sqlite")
                        and _nasz_znacznik(f[len("master_"):-len(".sqlite")])
                        and f[len("master_"):len("master_") + 8] == dzis):
                    self._ostatni_backup = dzis      # już jest — nie pytaj dysku co godzinę
                    return False
        except OSError:
            pass                                     # katalog jeszcze nie istnieje
        # Pusty licznik zapisów po restarcie nie jest dowodem, że nic się nie
        # działo — dlatego warunek `zapisow > 0` obowiązuje tylko wtedy, gdy
        # proces żyje od początku doby i sam widział brak ruchu.
        if self.zapisow == 0 and self._ostatni_backup is not None:
            return False
        self._ostatni_backup = dzis
        return True

    def zleć(self, zadanie, timeout=120):
        z = Zadanie(zadanie)
        self.kolejka.put(z)
        if not z.gotowe.wait(timeout):
            return {"ok": False, "blad": "serwer nie odpowiedział w %ds" % timeout}
        return z.wynik

    # ── obsługa klienta ───────────────────────────────────────────────
    def obsluz(self, sock, adres):
        sekret = self.config.get("sekret")
        try:
            sock.settimeout(300)
            while True:
                zadanie = czytaj_ramke(sock)
                if zadanie is None:
                    return
                odp = self._sprawdz_i_wykonaj(zadanie, sekret)
                odp["request_id"] = zadanie.get("request_id")
                wyslij_ramke(sock, odp)
        except (ConnectionError, socket.timeout):
            pass
        except Exception as e:
            log("⚠️  klient %s: %s" % (adres[0], e))
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _sprawdz_i_wykonaj(self, zadanie, sekret):
        if sekret:
            podany = zadanie.get("hmac") or ""
            oczekiwany = policz_hmac(sekret, zadanie.get("request_id"),
                                     zadanie.get("cmd"), zadanie.get("args"))
            # compare_digest: czas porównania niezależny od treści.
            if not hmac.compare_digest(podany, oczekiwany):
                log("⛔ zły HMAC: cmd=%s" % zadanie.get("cmd"))
                return {"ok": False, "blad": "nieprawidłowy podpis żądania"}
        return self.zleć(zadanie)


# ═══════════════════════════════════════════════════════════════════════
# Start
# ═══════════════════════════════════════════════════════════════════════

def uruchom(config):
    _ustaw_log(config["log_katalog"])
    log("=" * 62)
    log("RM_SERWER %s (protokół %d)" % (WERSJA, PROTOKOL))
    log("baza:    %s" % config["baza"])
    log("nasłuch: %s:%d" % (config["nasluch"], config["port"]))
    log("HMAC:    %s" % ("włączony" if config.get("sekret") else "WYŁĄCZONY"))
    log("=" * 62)

    serwer = Serwer(config)
    threading.Thread(target=serwer.worker, name="worker", daemon=True).start()

    nasluch = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    nasluch.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        nasluch.bind((config["nasluch"], config["port"]))
    except OSError as e:
        log("⛔ Nie mogę zająć portu %d: %s" % (config["port"], e))
        return 1
    nasluch.listen(32)
    log("Nasłuchuję.")

    try:
        while True:
            sock, adres = nasluch.accept()
            threading.Thread(target=serwer.obsluz, args=(sock, adres),
                             daemon=True).start()
    except KeyboardInterrupt:
        log("Zatrzymanie na żądanie.")
    finally:
        serwer.stop.set()
        try:
            nasluch.close()
        except Exception:
            pass
    return 0


def sprawdz(config):
    """Diagnostyka bez nasłuchu: czy baza jest, co w niej siedzi, czy port wolny."""
    print("RM_SERWER %s (protokół %d)" % (WERSJA, PROTOKOL))
    print("baza: %s" % config["baza"])
    if not os.path.isfile(config["baza"]):
        print("  ⛔ BRAK PLIKU")
        return 1
    print("  rozmiar: %.1f KB" % (os.path.getsize(config["baza"]) / 1024))
    con = sqlite3.connect(config["baza"], timeout=10)
    try:
        stan = con.execute("PRAGMA integrity_check").fetchone()[0]
        print("  integrity_check: %s" % stan)
        zrobione = ops.zastosuj_migracje(con)
        print("  migracje do dołożenia: %d" % len(zrobione))
        mapa = ops.zbuduj_operacje_dostawcow(con)
        print("  schemat suppliers: %s" % (mapa or "nie wykryto"))
        for nazwa in ("suppliers-list", "users-list", "projects-list"):
            print("  %-16s %d wierszy" % (nazwa, len(ops.wykonaj_odczyt(con, nazwa))))
        ile = con.execute("SELECT COUNT(*) FROM _server_request_log").fetchone()[0]
        print("  _server_request_log: %d wpisów" % ile)
    finally:
        con.close()
    z = ops.znane_operacje()
    print("operacje: %d odczytu, %d zapisu" % (len(z["odczyt"]), len(z["zapis"])))
    s = socket.socket()
    try:
        s.bind((config["nasluch"], config["port"]))
        print("port %d: WOLNY" % config["port"])
    except OSError:
        print("port %d: ZAJĘTY" % config["port"])
    finally:
        s.close()
    return 0


def main():
    p = argparse.ArgumentParser(description="RM_SERWER — właściciel master.sqlite")
    p.add_argument("--baza")
    p.add_argument("--port", type=int)
    p.add_argument("--nasluch")
    p.add_argument("--config")
    p.add_argument("--sprawdz", action="store_true",
                   help="diagnostyka, bez uruchamiania nasłuchu")
    a = p.parse_args()

    config = wczytaj_config(a.config)
    if a.baza:
        config["baza"] = a.baza
    if a.port:
        config["port"] = a.port
    if a.nasluch:
        config["nasluch"] = a.nasluch

    return sprawdz(config) if a.sprawdz else uruchom(config)


if __name__ == "__main__":
    sys.exit(main())
