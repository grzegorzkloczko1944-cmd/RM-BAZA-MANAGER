# -*- coding: utf-8 -*-
"""rm_mag_http.py — serwer HTTP TYLKO DO ODCZYTU dla makra MAG (Inventor).

    makro VBA ──HTTP GET──► :5061 ──► subiekt_kopia.sqlite   (kartoteki, stany, miniatury)
                                  └─► subiekt_mapowania.sqlite (modele_3d)

Po co osobne wejście: RM_SERWER mówi własnym protokołem po TCP z HMAC-SHA256,
czego w VBA praktycznie nie da się zrobić. `MSXML2.XMLHTTP` umie HTTP GET —
stąd ten serwer (PLAN_MAG.md, sekcja 3; ustalenia: osobny port,
bez uwierzytelniania, sieć lokalna, sam odczyt).

⚠️ HTTP NIE PISZE DO BAZ. Bazy otwierane są `mode=ro`. Jedyny wyjątek to
`POST /mag/synchronizuj` — i on też nie pisze sam: przekazuje operację
`sub-zlecenie-dodaj` do wątku roboczego RM_SERWER (jeden pisarz, jak
wszystko inne). Dane kopii pisze stacja z mostem (`subiekt_kopia_sync.py`
przez `subiekt_kopia_zlecenia.py`), indeks modeli — `indeks_modeli_3d.py`.

ADRESY (wszystkie GET, odpowiedź JSON; `&format=tsv` = tekst dla VBA)

    /mag/status                     wiek kopii, liczba kartotek
    /mag/szukaj?q=łożysko 6004      symbol, nazwa, opis, nazwa pliku 3D
    /mag/kartoteka?symbol=016-100.03
    /mag/modele?symbol=016-100.03   pliki .ipt/.iam do wstawienia
    /mag/miniatura?symbol=016-100.03   obrazek (image/png, image/jpeg…)
    POST /mag/synchronizuj?miniatury=1&kto=GKI   zlecenie synchronizacji —
                                      wykona stacja z mostem (MONGO pierwsza)

TSV: pierwszy wiersz = nazwy kolumn, dalej po wierszu na rekord, pola
rozdzielone TAB. Tabulatory i końce linii w danych zamieniane na spację —
w VBA wystarcza `Split(tekst, vbLf)` i `Split(wiersz, vbTab)`.

Uruchamiany z `rm_serwer.uruchom` jako wątek (jedna usługa NSSM), albo
samodzielnie do testów:

    python rm_mag_http.py --kopia dane\\subiekt_kopia.sqlite
                            --mapowania dane\\subiekt_mapowania.sqlite --port 5061
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

#: Ogonki → bez ogonków, małe litery. Ta sama tablica co w `rm_serwer`
#: i `ksef_archiwum.uprosc` — „lozysko" ma znaleźć „Łożysko".
_OGONKI_PL = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")

#: Ile wyników zwraca wyszukiwarka, gdy makro nie poda `limit`.
LIMIT_DOMYSLNY = 50
LIMIT_MAX = 500

TYPY_OBRAZKOW = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                 "bmp": "image/bmp", "gif": "image/gif"}

#: Kolumny wyniku wyszukiwania — kolejność = kolejność w TSV.
KOLUMNY_SZUKAJ = ["symbol", "nazwa", "opis", "rodzaj", "dostepne",
                  "zarezerwowane", "cena", "ma_miniature", "modeli",
                  "bez_modelu", "id"]


def uprosc(s):
    if s is None:
        return ""
    return str(s).translate(_OGONKI_PL).lower()


def _log_domyslny(tekst):
    print("%s  %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tekst),
          flush=True)


class Bazy:
    """Ścieżki baz + otwieranie połączeń tylko do odczytu.

    Połączenie na ŻĄDANIE, nie wspólne: serwer jest wielowątkowy, a otwarcie
    lokalnego pliku SQLite to ułamek milisekundy.
    """

    def __init__(self, kopia, mapowania=None):
        self.kopia = kopia
        self.mapowania = mapowania

    @staticmethod
    def _uri(sciezka):
        return "file:" + os.path.abspath(sciezka).replace(os.sep, "/") + "?mode=ro"

    def polacz(self):
        if not self.kopia or not os.path.isfile(self.kopia):
            raise FileNotFoundError("brak kopii Subiekta — nie było synchronizacji")
        con = sqlite3.connect(self._uri(self.kopia), uri=True, timeout=10)
        con.row_factory = sqlite3.Row
        con.create_function("UPROSC", 1, uprosc, deterministic=True)
        con.execute("PRAGMA busy_timeout=5000")
        ma_modele = False
        if self.mapowania and os.path.isfile(self.mapowania):
            try:
                con.execute("ATTACH DATABASE ? AS map", (self._uri(self.mapowania),))
                con.execute("SELECT 1 FROM map.modele_3d LIMIT 1")
                ma_modele = True
            except sqlite3.Error:
                pass           # serwer bez indeksu modeli — reszta działa
        return con, ma_modele


# ── zapytania ──────────────────────────────────────────────────────────────

def _modele_sql(ma_modele):
    """Kolumny `modeli`/`bez_modelu` — liczone z `map.modele_3d` po symbolu.

    Klucz mapowania to numer rysunku WIELKIMI literami (`subiekt_mapowania._key`),
    a symbol kartoteki detalu RMPAK = numer rysunku.
    """
    if not ma_modele:
        return "NULL AS modeli, NULL AS bez_modelu"
    return ("(SELECT COUNT(*) FROM map.modele_3d m"
            "  WHERE m.numer_rysunku = UPPER(TRIM(k.symbol)) AND m.sciezka != '')"
            "   AS modeli,"
            " (SELECT COUNT(*) FROM map.modele_3d m"
            "  WHERE m.numer_rysunku = UPPER(TRIM(k.symbol)) AND m.sciezka = '')"
            "   AS bez_modelu")


def szukaj(bazy, q, limit):
    """Kartoteki pasujące do WSZYSTKICH słów zapytania.

    Słowo pasuje, gdy siedzi w symbolu, nazwie, opisie albo w nazwie pliku
    modelu 3D (ustalenie 3 planu). Kolejność: trafienie dokładne w symbol,
    potem symbol od początku, potem reszta alfabetycznie.
    """
    slowa = [w for w in uprosc(q).split() if w]
    if not slowa:
        return []
    con, ma_modele = bazy.polacz()
    try:
        warunki, parametry = [], []
        for w in slowa:
            wzor = "%" + w.replace("%", "").replace("_", "") + "%"
            pola = ("UPROSC(k.symbol) LIKE ? OR UPROSC(k.nazwa) LIKE ?"
                    " OR UPROSC(k.opis) LIKE ?")
            parametry += [wzor, wzor, wzor]
            if ma_modele:
                pola += (" OR EXISTS (SELECT 1 FROM map.modele_3d m"
                         "  WHERE m.numer_rysunku = UPPER(TRIM(k.symbol))"
                         "    AND UPROSC(m.sciezka) LIKE ?)")
                parametry.append(wzor)
            warunki.append("(" + pola + ")")
        calosc = uprosc(q).strip()
        sql = ("SELECT k.id, k.symbol, k.nazwa, k.opis, k.rodzaj, k.dostepne,"
               "       k.zarezerwowane, k.cena,"
               "       EXISTS (SELECT 1 FROM miniatury z WHERE z.id_subiekt = k.id"
               "               AND z.dane_b64 != '') AS ma_miniature, "
               + _modele_sql(ma_modele) +
               "  FROM kartoteki k WHERE " + " AND ".join(warunki) +
               " ORDER BY (UPROSC(k.symbol) = ?) DESC,"
               "          (UPROSC(k.symbol) LIKE ?) DESC, k.symbol"
               " LIMIT ?")
        parametry += [calosc, calosc + "%", limit]
        return [dict(w) for w in con.execute(sql, parametry)]
    finally:
        con.close()


def kartoteka(bazy, symbol):
    con, ma_modele = bazy.polacz()
    try:
        w = con.execute(
            "SELECT k.*, EXISTS (SELECT 1 FROM miniatury z WHERE z.id_subiekt = k.id"
            "         AND z.dane_b64 != '') AS ma_miniature, "
            + _modele_sql(ma_modele) +
            "  FROM kartoteki k WHERE k.symbol = ? COLLATE NOCASE",
            (symbol.strip(),)).fetchone()
        if w is None:
            return None
        d = dict(w)
        try:
            d["magazyny"] = json.loads(d.pop("magazyny_json") or "[]")
        except ValueError:
            d["magazyny"] = []
        return d
    finally:
        con.close()


def modele(bazy, symbol):
    """{"symbol", "modele": [{sciezka, part_number, istnieje}], "bez_modelu", "znany"}.

    `znany` = False: rysunku nie ma w indeksie (nie skanowany). `bez_modelu`
    = True: skanowany i NA PEWNO nie ma modelu — makro mówi to wprost,
    zamiast podstawiać cokolwiek (plan, sekcja 2).
    """
    con, ma_modele = bazy.polacz()
    try:
        if not ma_modele:
            return {"symbol": symbol, "modele": [], "bez_modelu": False,
                    "znany": False, "uwaga": "brak indeksu modeli na serwerze"}
        wiersze = con.execute(
            "SELECT sciezka, part_number, zrodlo, kolejnosc FROM map.modele_3d"
            " WHERE numer_rysunku = ? ORDER BY kolejnosc, sciezka",
            (symbol.strip().upper(),)).fetchall()
        lista = [{"sciezka": w["sciezka"], "part_number": w["part_number"],
                  "zrodlo": w["zrodlo"]} for w in wiersze if w["sciezka"]]
        return {"symbol": symbol, "modele": lista,
                "bez_modelu": bool(wiersze) and not lista,
                "znany": bool(wiersze)}
    finally:
        con.close()


def miniatura(bazy, symbol):
    """(bajty, content-type) albo None."""
    con, _ = bazy.polacz()
    try:
        w = con.execute(
            "SELECT z.typ, z.dane_b64 FROM miniatury z"
            "  JOIN kartoteki k ON k.id = z.id_subiekt"
            " WHERE k.symbol = ? COLLATE NOCASE AND z.dane_b64 != ''",
            (symbol.strip(),)).fetchone()
        if w is None:
            return None
        typ = (w["typ"] or "png").lower().lstrip(".")
        return base64.b64decode(w["dane_b64"]), TYPY_OBRAZKOW.get(typ, "image/png")
    finally:
        con.close()


def status(bazy):
    con, ma_modele = bazy.polacz()
    try:
        ile = con.execute("SELECT COUNT(*) FROM kartoteki").fetchone()[0]
        mini = con.execute(
            "SELECT COUNT(*) FROM miniatury WHERE dane_b64 != ''").fetchone()[0]
        ostatnie = {}
        for w in con.execute(
                "SELECT co, MAX(kiedy) AS kiedy FROM synchronizacje GROUP BY co"):
            ostatnie[w["co"]] = w["kiedy"]
        modeli = None
        if ma_modele:
            modeli = con.execute(
                "SELECT COUNT(DISTINCT numer_rysunku) FROM map.modele_3d"
                " WHERE sciezka != ''").fetchone()[0]
        z = {}
        try:
            z = dict(con.execute("SELECT * FROM zlecenia_sync"
                                 " ORDER BY id DESC LIMIT 1").fetchone() or {})
        except sqlite3.Error:
            pass                          # baza sprzed tabeli zleceń
        # Płasko, nie zagnieżdżone — TSV dla VBA nie niesie słowników.
        return {"kartotek": ile, "miniatur": mini, "rysunkow_z_modelem": modeli,
                "kartoteki_z": ostatnie.get("kartoteki"),
                "miniatury_z": ostatnie.get("miniatury"),
                "zlecenie_id": z.get("id"), "zlecenie_status": z.get("status"),
                "zlecenie_wykonawca": z.get("wykonawca"),
                "zlecenie_postep": z.get("postep"), "zlecenie_wynik": z.get("wynik"),
                "zlecenie_zlecono": z.get("zlecono")}
    finally:
        con.close()


# ── HTTP ───────────────────────────────────────────────────────────────────

def _tsv(wiersze, kolumny):
    def pole(v):
        if v is None:
            return ""
        if isinstance(v, float):
            v = ("%.4f" % v).rstrip("0").rstrip(".")     # bez „1e-05" w VBA
        return str(v).replace("\t", " ").replace("\r", " ").replace("\n", " ")
    linie = ["\t".join(kolumny)]
    linie += ["\t".join(pole(w.get(k)) for k in kolumny) for w in wiersze]
    return "\n".join(linie) + "\n"


def zbuduj_handler(bazy, log, zlec=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RM_MAG/1.0"

        def log_message(self, fmt, *args):     # zamiast stderr — do logu serwera
            pass

        def _wyslij(self, kod, cialo, typ):
            if isinstance(cialo, str):
                cialo = cialo.encode("utf-8")
            self.send_response(kod)
            self.send_header("Content-Type", typ)
            self.send_header("Content-Length", str(len(cialo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cialo)

        def _dane(self, kod, dane, tsv, kolumny=None):
            if tsv:
                if isinstance(dane, dict) and kolumny is None:
                    kolumny = list(dane)
                    dane = [dane]
                self._wyslij(kod, _tsv(dane if isinstance(dane, list) else [dane],
                                       kolumny), "text/plain; charset=utf-8")
            else:
                self._wyslij(kod, json.dumps(dane, ensure_ascii=False),
                             "application/json; charset=utf-8")

        def do_POST(self):
            url = urlparse(self.path)
            p = {k: v[0] for k, v in parse_qs(url.query).items()}
            tsv = p.get("format", "").lower() == "tsv"
            if url.path.rstrip("/") != "/mag/synchronizuj":
                self._dane(404, {"blad": "nieznany adres"}, tsv)
                return
            if zlec is None:
                self._dane(503, {"blad": "serwer bez obsługi zleceń"}, tsv)
                return
            try:
                kto = (p.get("kto") or "MAG").strip()[:40]
                wynik = zlec("sub-zlecenie-dodaj", {
                    "miniatury": 1 if p.get("miniatury") in ("1", "tak") else 0,
                    "zlecil": "%s@%s" % (kto, self.client_address[0])})
                nowe = bool((wynik or {}).get("rowcount"))
                log("MAG: zlecenie synchronizacji od %s@%s — %s" % (
                    kto, self.client_address[0], "nowe" if nowe else "już było"))
                self._dane(200, {"zlecono": int(nowe),
                                 "komunikat": "zlecono" if nowe else
                                 "synchronizacja już czeka albo trwa"}, tsv)
            except Exception as e:
                log("⚠️  MAG HTTP POST %s: %s" % (self.path, e))
                self._dane(500, {"blad": "%s: %s" % (type(e).__name__, e)}, tsv)

        def do_GET(self):
            t0 = time.time()
            url = urlparse(self.path)
            p = {k: v[0] for k, v in parse_qs(url.query).items()}
            tsv = p.get("format", "").lower() == "tsv"
            sciezka = url.path.rstrip("/")
            try:
                if sciezka == "/mag/status":
                    self._dane(200, status(bazy), tsv)
                elif sciezka == "/mag/szukaj":
                    try:
                        limit = min(int(p.get("limit") or LIMIT_DOMYSLNY), LIMIT_MAX)
                    except ValueError:
                        limit = LIMIT_DOMYSLNY
                    self._dane(200, szukaj(bazy, p.get("q", ""), limit), tsv,
                               KOLUMNY_SZUKAJ)
                elif sciezka == "/mag/kartoteka":
                    d = kartoteka(bazy, p.get("symbol", ""))
                    if d is None:
                        self._dane(404, {"blad": "nie ma takiej kartoteki"}, tsv)
                    else:
                        if tsv:
                            d = {k: v for k, v in d.items() if k != "magazyny"}
                        self._dane(200, d, tsv)
                elif sciezka == "/mag/modele":
                    d = modele(bazy, p.get("symbol", ""))
                    if tsv:
                        # TSV: po wierszu na model; brak wierszy + nagłówek
                        # `bez_modelu`/`znany` w pierwszej linii mówi, dlaczego.
                        kol = ["sciezka", "part_number", "zrodlo"]
                        tekst = "#znany=%d\tbez_modelu=%d\n" % (d["znany"], d["bez_modelu"])
                        self._wyslij(200, tekst + _tsv(d["modele"], kol),
                                     "text/plain; charset=utf-8")
                    else:
                        self._dane(200, d, False)
                elif sciezka == "/mag/miniatura":
                    m = miniatura(bazy, p.get("symbol", ""))
                    if m is None:
                        self._wyslij(404, b"", "text/plain")
                    else:
                        self._wyslij(200, m[0], m[1])
                else:
                    self._dane(404, {"blad": "nieznany adres",
                                     "adresy": ["/mag/status", "/mag/szukaj?q=",
                                                "/mag/kartoteka?symbol=",
                                                "/mag/modele?symbol=",
                                                "/mag/miniatura?symbol="]}, tsv)
            except FileNotFoundError as e:
                self._dane(503, {"blad": str(e)}, tsv)
            except Exception as e:
                log("⚠️  MAG HTTP %s: %s" % (self.path, e))
                self._dane(500, {"blad": "%s: %s" % (type(e).__name__, e)}, tsv)
            finally:
                ms = (time.time() - t0) * 1000
                if ms > 500:
                    log("MAG HTTP wolne: %s %.0f ms" % (self.path, ms))

    return Handler


def uruchom_w_tle(kopia, mapowania, port, nasluch="0.0.0.0", log=_log_domyslny,
                  zlec=None):
    """Startuje serwer w wątku-demonie. Zwraca serwer albo None przy błędzie.

    Błąd portu NIE przewraca RM_SERWER — makro to dodatek, a 5060 ma działać.
    """
    try:
        srv = ThreadingHTTPServer((nasluch, port),
                                  zbuduj_handler(Bazy(kopia, mapowania), log, zlec))
    except OSError as e:
        log("⛔ MAG HTTP: nie mogę zająć portu %d: %s" % (port, e))
        return None
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, name="mag-http",
                     daemon=True).start()
    log("MAG HTTP: %s:%d (tylko odczyt)" % (nasluch, port))
    return srv


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Serwer HTTP dla makra MAG")
    ap.add_argument("--kopia", required=True, help="subiekt_kopia.sqlite")
    ap.add_argument("--mapowania", help="subiekt_mapowania.sqlite (modele_3d)")
    ap.add_argument("--port", type=int, default=5061)
    ap.add_argument("--nasluch", default="0.0.0.0")
    a = ap.parse_args()
    srv = uruchom_w_tle(a.kopia, a.mapowania, a.port, a.nasluch)
    if srv is None:
        return 1
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
