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
    /mag/szukaj?q=łożysko 6004[&typ=ID|-]   symbol, nazwa, opis, nazwa pliku 3D;
                                      typ: filtr (- = bez typu); z typem q może być puste
    /mag/typy                    typy pozycji + liczba kartotek
    /mag/kartoteka?symbol=016-100.03
    /mag/modele?symbol=016-100.03   pliki .ipt/.iam do wstawienia
    /mag/miniatura?symbol=016-100.03   obrazek (image/png, image/jpeg…)
    /mag/miniatura3d?symbol=016-100.03 miniatura MODELU 3D (z pliku .ipt/.iam)
    /mag/lozyska?q=600|688|20x42&d=&dz=&b=&seria=&na_stanie=1
                                      katalog łożysk kulkowych + stan w Subiekcie
    POST /mag/synchronizuj?miniatury=1&kto=GKI   zlecenie synchronizacji —
                                      wykona stacja z mostem (MONGO pierwsza)
    POST /mag/model3d/przypisz?symbol=&sciezka=&kto=   ręczne przypisanie
    POST /mag/model3d/usun?symbol=&sciezka=            usunięcie ręcznego
    POST /mag/model3d/miniatura?sciezka=&typ=png|bmp[&subiekt=SYMBOL]
                                  miniatura ze stacji (base64 w treści); z `subiekt`
                                  także zdjęcie kartoteki w Subiekcie (zlecenie)
    POST /mag/typ/dodaj?nazwa=&kto=     nowy typ pozycji
    POST /mag/typ/zmien?id=&nazwa=&kto= zmiana nazwy
    POST /mag/typ/usun?id=&kto=         usunięcie (typ zdjęty z kartotek)
    POST /mag/typ/przypisz?typ=ID|-&kto=   symbole w treści (linia =
                                      symbol zakodowany jak w URL)
    POST /mag/synchronizuj3d?kto=GKI  zlecenie indeksu modeli 3D — wykona
                                      dowolna stacja z Inventorem
    /mag/skrypt/indeks_modeli_3d.py   skrypt dla stacji (biała lista)

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
import re
import sqlite3
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

#: Ogonki → bez ogonków, małe litery. Ta sama tablica co w `rm_serwer`
#: i `ksef_archiwum.uprosc` — „lozysko" ma znaleźć „Łożysko".
_OGONKI_PL = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")

#: Ile wyników zwraca wyszukiwarka, gdy makro nie poda `limit`.
LIMIT_DOMYSLNY = 50
LIMIT_MAX = 500

TYPY_OBRAZKOW = {"png": "image/png", "png/biale": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                 "bmp": "image/bmp", "gif": "image/gif"}

#: Kolumny wyniku wyszukiwania — kolejność = kolejność w TSV.
KOLUMNY_SZUKAJ = ["symbol", "nazwa", "opis", "rodzaj", "dostepne",
                  "zarezerwowane", "cena", "ma_miniature", "modeli",
                  "bez_modelu", "ma_mini3d", "id", "lozysko", "wymiary",
                  "typ", "typ_id"]

#: Skrypty, które stacje pobierają z serwera i uruchamiają na zlecenie.
SKRYPTY_DLA_STACJI = {"indeks_modeli_3d.py"}

#: Kolumny katalogu łożysk (/mag/lozyska) — kolejność = kolejność w TSV.
KOLUMNY_LOZYSKA = ["oznaczenie", "seria", "d", "dz", "b", "wymiary", "cr_kn",
                   "c0r_kn", "n_smar", "n_olej", "masa_kg", "aliasy", "uwaga",
                   "zrodlo", "kartotek", "na_stanie", "symbole"]

#: Najdłuższa nazwa typu pozycji (lista w oknie MAG).
TYP_MAX = 40


def _liczba(x):
    """20.0 -> '20', 2.5 -> '2.5'."""
    return "" if x is None else ("%g" % x)


def wymiary_tekst(r):
    return "%sx%sx%s" % (_liczba(r["d"]), _liczba(r["dz"]), _liczba(r["b"]))


# Wymiar w zapytaniu (user, 28.09.2026): „6x" = otwór 6, „12x30" = otwór
# i średnica, „12x30x8" = komplet, „x30" = sama średnica zewnętrzna.
# Pusta część = dowolna. Litera x MUSI być, żeby „6004" zostało oznaczeniem.
_WYMIAR_W_ZAPYTANIU = re.compile(
    r"^(\d+(?:[.,]\d+)?)?x(\d+(?:[.,]\d+)?)?(?:x(\d+(?:[.,]\d+)?))?$")


def _wymiar_z_tokenu(tok):
    """'6x' / '12x30' / '12x30x8' / 'x30' -> (d|None, D|None, B|None) albo None."""
    m = _WYMIAR_W_ZAPYTANIU.match((tok or "").lower())
    if not m or not any(m.groups()):
        return None
    return tuple(float(x.replace(",", ".")) if x else None for x in m.groups())


def _pasuje_wymiar(r, wym):
    d, dz, b = wym
    return (r is not None and (d is None or r["d"] == d)
            and (dz is None or r["dz"] == dz) and (b is None or r["b"] == b))


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
        return "NULL AS modeli, NULL AS bez_modelu, 0 AS ma_mini3d"
    return ("(SELECT COUNT(*) FROM map.modele_3d m"
            "  WHERE m.numer_rysunku = UPPER(TRIM(k.symbol)) AND m.sciezka != '')"
            "   AS modeli,"
            " (SELECT COUNT(*) FROM map.modele_3d m"
            "  WHERE m.numer_rysunku = UPPER(TRIM(k.symbol)) AND m.sciezka = '')"
            "   AS bez_modelu,"
            " EXISTS (SELECT 1 FROM map.modele_3d m JOIN miniatury_3d t"
            "         ON t.sciezka = m.sciezka"
            "  WHERE m.numer_rysunku = UPPER(TRIM(k.symbol)) AND t.dane_b64 != '')"
            "   AS ma_mini3d")


def _ma_cechy(con):
    """Czy w mapowaniach jest `kartoteki_cechy` (serwer po migracji 30.09.2026)."""
    try:
        con.execute("SELECT 1 FROM map.kartoteki_cechy LIMIT 1")
        return True
    except sqlite3.Error:
        return False


def _cechy_sql(ma_cechy):
    """(kolumny, JOIN) typu i wymiarów kartoteki `k`."""
    if not ma_cechy:
        return ("NULL AS wymiary, NULL AS lozysko, NULL AS typ_id, NULL AS typ,"
                " NULL AS typ_zrodlo", "")
    return ("c.wymiary, c.lozysko, c.id_typu AS typ_id, r.nazwa AS typ,"
            " c.typ_zrodlo",
            " LEFT JOIN map.kartoteki_cechy c ON c.id_subiekt = k.id"
            " LEFT JOIN map.typy_pozycji r ON r.id = c.id_typu")


def szukaj(bazy, q, limit, typ=""):
    """Kartoteki pasujące do WSZYSTKICH słów zapytania.

    Słowo pasuje, gdy siedzi w symbolu, nazwie, opisie albo w nazwie pliku
    modelu 3D (ustalenie 3 planu). Kolejność: trafienie dokładne w symbol,
    potem symbol od początku, potem reszta alfabetycznie.

    typ: id typu pozycji, "-" = bez typu, "" = wszystkie. Z wybranym
    typem puste zapytanie pokazuje cały typ.
    """
    slowa = [w for w in uprosc(q).split() if w]
    # „20x42" / „20x42x12" = wymiar — filtr po wymiarach kartoteki, nie po tekście.
    wymiary = [_wymiar_z_tokenu(w) for w in slowa]
    wym = next((x for x in wymiary if x), None)
    slowa = [w for w, x in zip(slowa, wymiary) if not x]
    typ = (typ or "").strip()
    if not slowa and not wym and not typ:
        return []
    con, ma_modele = bazy.polacz()
    try:
        ma_cechy = _ma_cechy(con)
        if (wym or typ) and not ma_cechy:
            return []
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
        if wym:
            for kol, x in zip(("c.d", "c.dz", "c.b"), wym):
                if x is not None:
                    warunki.append(kol + " = ?")
                    parametry.append(x)
        if typ == "-":
            warunki.append("c.id_typu IS NULL")
        elif typ:
            warunki.append("c.id_typu = ?")
            parametry.append(int(typ))
        kolumny, join = _cechy_sql(ma_cechy)
        calosc = uprosc(q).strip()
        sql = ("SELECT k.id, k.symbol, k.nazwa, k.opis, k.rodzaj, k.dostepne,"
               "       k.zarezerwowane, k.cena, " + kolumny + ","
               "       EXISTS (SELECT 1 FROM miniatury z WHERE z.id_subiekt = k.id"
               "               AND z.dane_b64 != '') AS ma_miniature, "
               + _modele_sql(ma_modele) +
               "  FROM kartoteki k" + join + " WHERE " + " AND ".join(warunki) +
               " ORDER BY (UPROSC(k.symbol) = ?) DESC,"
               "          (UPROSC(k.symbol) LIKE ?) DESC, k.symbol LIMIT ?")
        parametry += [calosc, calosc + "%", int(limit)]
        return [dict(w) for w in con.execute(sql, parametry)]
    finally:
        con.close()


def kartoteka(bazy, symbol):
    con, ma_modele = bazy.polacz()
    try:
        ma_cechy = _ma_cechy(con)
        kolumny, join = _cechy_sql(ma_cechy)
        w = con.execute(
            "SELECT k.*, " + kolumny + ","
            "       EXISTS (SELECT 1 FROM miniatury z WHERE z.id_subiekt = k.id"
            "         AND z.dane_b64 != '') AS ma_miniature, "
            + _modele_sql(ma_modele) +
            "  FROM kartoteki k" + join + " WHERE k.symbol = ? COLLATE NOCASE",
            (symbol.strip(),)).fetchone()
        if w is None:
            return None
        d = dict(w)
        try:
            d["magazyny"] = json.loads(d.pop("magazyny_json") or "[]")
        except ValueError:
            d["magazyny"] = []
        r = None
        if d.get("lozysko"):
            r = con.execute("SELECT cr_kn, n_smar FROM lozyska WHERE oznaczenie = ?",
                            (d["lozysko"],)).fetchone()
        d["lozysko_cr_kn"] = r["cr_kn"] if r else None
        d["lozysko_n_smar"] = r["n_smar"] if r else None
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


def lozyska(bazy, q="", d=None, dz=None, b=None, seria="", tylko_na_stanie=False):
    """Katalog łożysk + co z tego jest w Subiekcie (kartotek, stan, symbole).

    q: oznaczenie / alias od początku („600" -> 6000..6009, „688")
       albo wymiar „20x42" / „20x42x12". d/dz/b: dokładne wymiary w mm.
    """
    con, _ = bazy.polacz()
    try:
        wiersze = [dict(r) for r in con.execute("SELECT * FROM lozyska ORDER BY seria, d, dz")]
        for r in wiersze:
            r["wymiary"] = wymiary_tekst(r)
        # Kartoteki -> łożyska: rozpoznanie zrobił serwer (`kartoteki_cechy`).
        w_sub = {}
        if _ma_cechy(con):
            for k in con.execute(
                    "SELECT c.lozysko, k.symbol, k.dostepne FROM kartoteki k"
                    "  JOIN map.kartoteki_cechy c ON c.id_subiekt = k.id"
                    " WHERE c.lozysko IS NOT NULL"):
                x = w_sub.setdefault(k["lozysko"], {"kartotek": 0, "na_stanie": 0.0, "symbole": []})
                x["kartotek"] += 1
                x["na_stanie"] += k["dostepne"] or 0
                x["symbole"].append(k["symbol"])
    finally:
        con.close()

    q = (q or "").strip().upper()
    wym = _wymiar_z_tokenu(q.lower()) if q else None
    wynik = []
    for r in wiersze:
        if wym and not _pasuje_wymiar(r, wym):
            continue
        if q and not wym:
            nazwy = [r["oznaczenie"].upper()] + (r.get("aliasy") or "").upper().split()
            if not any(n.startswith(q) for n in nazwy):
                continue
        if d is not None and r["d"] != d:
            continue
        if dz is not None and r["dz"] != dz:
            continue
        if b is not None and r["b"] != b:
            continue
        if seria and r["seria"] != seria:
            continue
        x = w_sub.get(r["oznaczenie"], {"kartotek": 0, "na_stanie": 0.0, "symbole": []})
        if tylko_na_stanie and not x["kartotek"]:
            continue
        w = dict(r)
        w["aliasy"] = " ".join((r.get("aliasy") or "").split())
        w.update(kartotek=x["kartotek"], na_stanie=x["na_stanie"],
                 symbole=", ".join(sorted(x["symbole"])[:6]))
        wynik.append(w)
    return wynik


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


def miniatura3d(bazy, symbol):
    """(bajty, content-type) miniatury modelu 3D kartoteki albo None.

    Pierwszy model (wg `kolejnosc`), który ma miniaturę w `miniatury_3d`.
    """
    con, ma_modele = bazy.polacz()
    try:
        if not ma_modele:
            return None
        w = con.execute(
            "SELECT t.typ, t.dane_b64 FROM map.modele_3d m"
            "  JOIN miniatury_3d t ON t.sciezka = m.sciezka"
            " WHERE m.numer_rysunku = ? AND t.dane_b64 != ''"
            " ORDER BY m.kolejnosc, m.sciezka LIMIT 1",
            (symbol.strip().upper(),)).fetchone()
        if w is None:
            return None
        typ = (w["typ"] or "png").lower().lstrip(".")
        return base64.b64decode(w["dane_b64"]), TYPY_OBRAZKOW.get(typ, "image/png")
    finally:
        con.close()


#: Ta sama biblioteka pod dwiema nazwami (firma) — jak TEN_SAM_KATALOG
#: w indeks_modeli_3d.py. Indeks trzyma ścieżki przez B:.
TEN_SAM_KATALOG = {"C:\\BIBLIOTEKARM\\": "B:\\"}
MODELE_3D = (".ipt", ".iam")


def _normuj_sciezke(sciezka):
    s = (sciezka or "").strip().strip('"').replace("/", "\\")
    for stara, nowa in TEN_SAM_KATALOG.items():
        if s.upper().startswith(stara):
            return nowa + s[len(stara):]
    return s


def przypisz_model(bazy, zlec, symbol, sciezka, kto):
    """Ręczne przypisanie modelu 3D do kartoteki (okno MAG, 29.09.2026).

    Wiersz `zrodlo='reczny'` w `modele_3d` — indeks z automatu go nie
    nadpisze ani nie skasuje. Zwraca {"sciezka", "nowy", "modele"}.
    """
    symbol = (symbol or "").strip()
    sciezka = _normuj_sciezke(sciezka)
    if not symbol:
        raise ValueError("brak symbolu")
    if not sciezka.lower().endswith(MODELE_3D):
        raise ValueError("to nie jest model Inventora (.ipt/.iam): %s" % sciezka)
    klucz = symbol.upper()
    con, ma_modele = bazy.polacz()
    try:
        if not ma_modele:
            raise ValueError("serwer bez indeksu modeli (subiekt_mapowania)")
        byl = con.execute(
            "SELECT zrodlo FROM map.modele_3d WHERE numer_rysunku = ? AND sciezka = ?",
            (klucz, sciezka)).fetchone()
        kolejnosc = con.execute(
            "SELECT COALESCE(MAX(kolejnosc) + 1, 0) FROM map.modele_3d"
            " WHERE numer_rysunku = ?", (klucz,)).fetchone()[0]
    finally:
        con.close()
    if byl is not None and byl[0] == "reczny":
        return {"sciezka": sciezka, "nowy": 0, "komunikat": "już przypisany"}
    zlec("map-model3d-usun-pusty-auto", {"numer_rysunku": klucz})
    zlec("map-model3d-zapisz", {
        "numer_rysunku": klucz, "sciezka": sciezka,
        "kolejnosc": kolejnosc if byl is None else 0,
        "part_number": None, "idw": None, "idw_mtime": None,
        "zrodlo": "reczny", "kto": kto,
        "kiedy": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return {"sciezka": sciezka, "nowy": 1, "komunikat": "przypisano"}


#: Miniatura wysylana ze stacji usera przy przypisaniu — sygnatury formatow.
SYGNATURY_MINIATUR = {"png": b"\x89PNG\r\n\x1a\n", "bmp": b"BM"}
MINIATURA_MAX = 3 * 1024 * 1024


def zapisz_miniature(zlec, sciezka, typ, dane_b64, kto, do_subiekta=""):
    """Miniatura modelu wyjęta z pliku NA STACJI usera (okno MAG, 29.09.2026).

    Obrazek renderuje Inventor usera (izometria, BIAŁE tło) — lepszy niż
    miniatura zapisana w pliku, więc `mtime = -1`: indeks go NIE nadpisuje
    (`indeks_modeli_3d.MTIME_RENDER`). Nowy render = ponowne przypisanie.
    """
    typ = (typ or "").lower()
    if typ not in SYGNATURY_MINIATUR:
        raise ValueError("nieznany typ miniatury: %s" % typ)
    try:
        dane = base64.b64decode(dane_b64 or "", validate=False)
    except Exception:
        raise ValueError("miniatura: zły base64")
    if not dane.startswith(SYGNATURY_MINIATUR[typ]):
        raise ValueError("miniatura: to nie jest %s" % typ)
    sciezka = _normuj_sciezke(sciezka)
    if not sciezka.lower().endswith(MODELE_3D):
        raise ValueError("to nie jest model Inventora (.ipt/.iam): %s" % sciezka)
    zlec("sub-mini3d-zapisz", {
        "sciezka": sciezka, "mtime": -1, "typ": typ,
        "dane_b64": base64.b64encode(dane).decode("ascii"),
        "kto": kto, "kiedy": time.strftime("%Y-%m-%dT%H:%M:%S")})
    wynik = {"sciezka": sciezka, "zapisano": 1, "bajtow": len(dane), "subiekt": ""}
    # Ta sama miniatura jako zdjęcie kartoteki w Subiekcie — zlecenie dla
    # stacji z mostem (decyzja, czy wysyłać, zapada w oknie MAG).
    if (do_subiekta or "").strip():
        zlec("sub-zdjecie-zlec", {
            "symbol": do_subiekta.strip(), "typ": typ,
            "dane_b64": base64.b64encode(dane).decode("ascii"), "zlecil": kto})
        wynik["subiekt"] = "zlecono"
    return wynik


def usun_przypisanie(zlec, symbol, sciezka):
    """Usuwa JEDEN ręczny wiersz. Automatycznych nie rusza."""
    w = zlec("map-model3d-usun-reczny", {
        "numer_rysunku": (symbol or "").strip().upper(),
        "sciezka": _normuj_sciezke(sciezka)})
    return {"usunieto": int((w or {}).get("rowcount") or 0)}


# ── typy pozycji (filtr w oknie MAG, user 30.09.2026) ─────────────────────

def _teraz():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _nazwa_typu(nazwa):
    n = " ".join((nazwa or "").split())
    if not n:
        raise ValueError("pusta nazwa typu")
    if len(n) > TYP_MAX:
        raise ValueError("nazwa typu dłuższa niż %d znaków" % TYP_MAX)
    return n


def _typy_tabela(con):
    """{id: (nazwa, auto)} — ValueError, gdy serwer nie ma jeszcze tabeli."""
    if not _ma_cechy(con):
        raise ValueError("serwer bez tabeli typów — potrzebny restart RM_SERWER")
    return {w[0]: (w[1], bool(w[2])) for w in con.execute(
        "SELECT id, nazwa, auto_klucz IS NOT NULL FROM map.typy_pozycji")}


def _zajeta_nazwa(tabela, nazwa, poza_id=None):
    """Id typu o tej samej nazwie (bez względu na wielkość liter i ogonki)."""
    klucz = uprosc(nazwa)
    return next((i for i, (n, _) in tabela.items()
                 if uprosc(n) == klucz and i != poza_id), None)


def typy(bazy):
    """[{id, nazwa, auto, kartotek}] — alfabetycznie, po polsku."""
    con, _ = bazy.polacz()
    try:
        if not _ma_cechy(con):
            return []
        wynik = [dict(w) for w in con.execute(
            "SELECT r.id, r.nazwa, r.auto_klucz IS NOT NULL AS auto,"
            "       (SELECT COUNT(*) FROM map.kartoteki_cechy c"
            "          JOIN kartoteki k ON k.id = c.id_subiekt"
            "         WHERE c.id_typu = r.id) AS kartotek"
            "  FROM map.typy_pozycji r")]
    finally:
        con.close()
    return sorted(wynik, key=lambda w: uprosc(w["nazwa"]))


def dodaj_typ(bazy, zlec, nazwa, kto):
    n = _nazwa_typu(nazwa)
    con, _ = bazy.polacz()
    try:
        jest = _zajeta_nazwa(_typy_tabela(con), n)
    finally:
        con.close()
    if jest is not None:
        return {"id": jest, "nowa": 0, "komunikat": "taki typ już jest"}
    w = zlec("map-typ-dodaj", {"nazwa": n, "kto": kto, "kiedy": _teraz()})
    return {"id": w["lastrowid"], "nowa": 1, "komunikat": "dodano typ " + n}


def zmien_typ(bazy, zlec, id_, nazwa, kto):
    n = _nazwa_typu(nazwa)
    id_ = int(id_)
    con, _ = bazy.polacz()
    try:
        tabela = _typy_tabela(con)
    finally:
        con.close()
    if id_ not in tabela:
        raise ValueError("nie ma takiego typu")
    if _zajeta_nazwa(tabela, n, poza_id=id_) is not None:
        raise ValueError("typ %s już jest" % n)
    zlec("map-typ-zmien", {"nazwa": n, "kto": kto, "kiedy": _teraz(), "id": id_})
    return {"id": id_, "komunikat": "%s -> %s" % (tabela[id_][0], n)}


def usun_typ(bazy, zlec, id_, kto):
    """Zdejmuje typ z kartotek i go usuwa — jedną transakcją."""
    id_ = int(id_)
    con, _ = bazy.polacz()
    try:
        tabela = _typy_tabela(con)
    finally:
        con.close()
    if id_ not in tabela:
        raise ValueError("nie ma takiego typu")
    nazwa, auto = tabela[id_]
    if auto:
        raise ValueError("%s przypisuje automat z katalogu — można go tylko przemianować" % nazwa)
    w = zlec([("map-typ-zdejmij", {"kto": kto, "kiedy": _teraz(), "id": id_}),
              ("map-typ-usun", {"id": id_})])
    zdjeto = int(w["wyniki"][0]["rowcount"] or 0)
    return {"usunieto": 1, "zdjeto": zdjeto,
            "komunikat": "usunięto typ %s (zdjęty z %d kartotek)" % (nazwa, zdjeto)}


def przypisz_typ(bazy, zlec, typ, symbole, kto):
    """Typ (id; "" / "-" = bez typu) dla listy symboli — decyzja
    ręczna, automat jej potem nie zmienia."""
    symbole = [s.strip() for s in symbole if s and s.strip()]
    if not symbole:
        raise ValueError("brak symboli")
    if len(symbole) > LIMIT_MAX * 4:
        raise ValueError("za dużo symboli naraz (%d)" % len(symbole))
    id_t = None if (typ or "").strip() in ("", "-") else int(typ)
    con, _ = bazy.polacz()
    try:
        tabela = _typy_tabela(con)
        if id_t is not None and id_t not in tabela:
            raise ValueError("nie ma takiego typu")
        znalezione = [(w[0], w[1]) for w in con.execute(
            "SELECT id, symbol FROM kartoteki"
            " WHERE UPPER(symbol) IN (SELECT UPPER(value) FROM json_each(?))",
            (json.dumps(symbole),))]
    finally:
        con.close()
    znane = {s.upper() for _, s in znalezione}
    brak = [s for s in symbole if s.upper() not in znane]
    if znalezione:
        zlec("map-cechy-typ", {"id_typu": id_t, "kto": kto, "kiedy": _teraz(),
                                   "lista_json": json.dumps(znalezione)})
    nazwa = tabela[id_t][0] if id_t is not None else "(bez typu)"
    return {"przypisano": len(znalezione), "nie_znaleziono": brak,
            "komunikat": "%s: %d kartotek" % (nazwa, len(znalezione))}


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
        z, z3 = {}, {}
        try:
            z = dict(con.execute("SELECT * FROM zlecenia_sync"
                                 " WHERE COALESCE(rodzaj, 'kopia') = 'kopia'"
                                 " ORDER BY id DESC LIMIT 1").fetchone() or {})
            z3 = dict(con.execute("SELECT * FROM zlecenia_sync"
                                  " WHERE rodzaj = 'indeks3d'"
                                  " ORDER BY id DESC LIMIT 1").fetchone() or {})
        except sqlite3.Error:
            pass                          # baza sprzed tabeli zleceń / kolumny
        zd_czeka, zd = 0, {}
        try:
            zd_czeka = con.execute("SELECT COUNT(*) FROM zlecenia_zdjec"
                                   " WHERE status IN ('nowe', 'w_toku')").fetchone()[0]
            zd = dict(con.execute("SELECT symbol, status, wynik FROM zlecenia_zdjec"
                                  " WHERE zakonczono IS NOT NULL"
                                  " ORDER BY id DESC LIMIT 1").fetchone() or {})
        except sqlite3.Error:
            pass                          # serwer sprzed kolejki zdjęć
        # Płasko, nie zagnieżdżone — TSV dla VBA nie niesie słowników.
        return {"kartotek": ile, "miniatur": mini, "rysunkow_z_modelem": modeli,
                "kartoteki_z": ostatnie.get("kartoteki"),
                "miniatury_z": ostatnie.get("miniatury"),
                "zlecenie_id": z.get("id"), "zlecenie_status": z.get("status"),
                "zlecenie_wykonawca": z.get("wykonawca"),
                "zlecenie_postep": z.get("postep"), "zlecenie_wynik": z.get("wynik"),
                "zlecenie_zlecono": z.get("zlecono"),
                "indeks_status": z3.get("status"), "indeks_wykonawca": z3.get("wykonawca"),
                "indeks_postep": z3.get("postep"), "indeks_wynik": z3.get("wynik"),
                "indeks_zlecono": z3.get("zlecono"), "indeks_zakonczono": z3.get("zakonczono"),
                "zdjecia_czeka": zd_czeka, "zdjecie_symbol": zd.get("symbol"),
                "zdjecie_status": zd.get("status"), "zdjecie_wynik": zd.get("wynik")}
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
            sciezka = url.path.rstrip("/")
            if sciezka.startswith("/mag/typ/"):
                if zlec is None:
                    self._dane(503, {"blad": "serwer bez obsługi zleceń"}, tsv)
                    return
                kto = (p.get("kto") or "MAG").strip()[:40]
                akcja = sciezka[len("/mag/typ/"):]
                try:
                    if akcja == "dodaj":
                        wynik = dodaj_typ(bazy, zlec, p.get("nazwa", ""), kto)
                    elif akcja == "zmien":
                        wynik = zmien_typ(bazy, zlec, p.get("id", ""), p.get("nazwa", ""), kto)
                    elif akcja == "usun":
                        wynik = usun_typ(bazy, zlec, p.get("id", ""), kto)
                    elif akcja == "przypisz":
                        # Symbole w treści, po jednym na linię, zakodowane jak w URL
                        # (okno wysyła treść jako us-ascii).
                        dl = int(self.headers.get("Content-Length") or 0)
                        if dl < 0 or dl > 1024 * 1024:
                            raise ValueError("zły rozmiar listy (%d B)" % dl)
                        cialo = self.rfile.read(dl).decode("ascii", "replace") if dl else ""
                        symbole = [unquote(x) for x in cialo.split("\n")]
                        if p.get("symbol"):
                            symbole.append(p["symbol"])
                        wynik = przypisz_typ(bazy, zlec, p.get("typ", ""), symbole, kto)
                    else:
                        self._dane(404, {"blad": "nieznany adres"}, tsv)
                        return
                    log("MAG: typ %s (%s@%s) — %s" % (
                        akcja, kto, self.client_address[0], wynik.get("komunikat")))
                    self._dane(200, wynik, tsv)
                except ValueError as e:
                    self._dane(400, {"blad": str(e)}, tsv)
                except Exception as e:
                    log("⚠️  MAG HTTP POST %s: %s" % (self.path, e))
                    self._dane(500, {"blad": "%s: %s" % (type(e).__name__, e)}, tsv)
                return
            if sciezka in ("/mag/model3d/przypisz", "/mag/model3d/usun",
                           "/mag/model3d/miniatura"):
                if zlec is None:
                    self._dane(503, {"blad": "serwer bez obsługi zleceń"}, tsv)
                    return
                kto = (p.get("kto") or "MAG").strip()[:40]
                try:
                    if sciezka.endswith("/miniatura"):
                        dl = int(self.headers.get("Content-Length") or 0)
                        if dl <= 0 or dl > MINIATURA_MAX * 2:
                            raise ValueError("miniatura: zły rozmiar (%d B)" % dl)
                        cialo = self.rfile.read(dl).decode("ascii", "replace")
                        wynik = zapisz_miniature(zlec, p.get("sciezka", ""), p.get("typ", ""),
                                                 cialo, kto, p.get("subiekt", ""))
                    elif sciezka.endswith("/przypisz"):
                        wynik = przypisz_model(bazy, zlec, p.get("symbol", ""),
                                               p.get("sciezka", ""), kto)
                    else:
                        wynik = usun_przypisanie(zlec, p.get("symbol", ""),
                                                 p.get("sciezka", ""))
                    log("MAG: %s %s <- %s (%s@%s) — %s" % (
                        sciezka.rsplit("/", 1)[1], p.get("symbol"), p.get("sciezka"),
                        kto, self.client_address[0], wynik))
                    self._dane(200, wynik, tsv)
                except ValueError as e:
                    self._dane(400, {"blad": str(e)}, tsv)
                except Exception as e:
                    log("⚠️  MAG HTTP POST %s: %s" % (self.path, e))
                    self._dane(500, {"blad": "%s: %s" % (type(e).__name__, e)}, tsv)
                return
            if sciezka not in ("/mag/synchronizuj", "/mag/synchronizuj3d"):
                self._dane(404, {"blad": "nieznany adres"}, tsv)
                return
            indeks3d = sciezka == "/mag/synchronizuj3d"
            if zlec is None:
                self._dane(503, {"blad": "serwer bez obsługi zleceń"}, tsv)
                return
            try:
                kto = (p.get("kto") or "MAG").strip()[:40]
                if indeks3d:
                    wynik = zlec("sub-zlecenie-dodaj-rodzaj", {
                        "miniatury": 0, "rodzaj": "indeks3d",
                        "zlecil": "%s@%s" % (kto, self.client_address[0])})
                else:
                    wynik = zlec("sub-zlecenie-dodaj", {
                        "miniatury": 1 if p.get("miniatury") in ("1", "tak") else 0,
                        "zlecil": "%s@%s" % (kto, self.client_address[0])})
                nowe = bool((wynik or {}).get("rowcount"))
                log("MAG: zlecenie %s od %s@%s — %s" % (
                    "indeks3d" if indeks3d else "synchronizacji", kto,
                    self.client_address[0], "nowe" if nowe else "już było"))
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
                    self._dane(200, szukaj(bazy, p.get("q", ""), limit, p.get("typ", "")),
                               tsv, KOLUMNY_SZUKAJ)
                elif sciezka == "/mag/typy":
                    self._dane(200, typy(bazy), tsv, ["id", "nazwa", "auto", "kartotek"])
                elif sciezka.startswith("/mag/skrypt/"):
                    # Skrypty wykonywane przez stacje na zlecenie serwera —
                    # TYLKO z białej listy, z katalogu serwera. Stacja pobiera
                    # je przy każdym zleceniu (decyzja usera 28.09.2026).
                    nazwa = sciezka[len("/mag/skrypt/"):]
                    plik = os.path.join(os.path.dirname(os.path.abspath(__file__)), nazwa)
                    if nazwa not in SKRYPTY_DLA_STACJI or not os.path.isfile(plik):
                        self._wyslij(404, b"", "text/plain")
                    else:
                        with open(plik, "rb") as f:
                            self._wyslij(200, f.read(), "text/x-python; charset=utf-8")
                elif sciezka == "/mag/lozyska":
                    def liczba(k):
                        try:
                            return float(p[k].replace(",", ".")) if p.get(k) else None
                        except ValueError:
                            return None
                    self._dane(200, lozyska(bazy, p.get("q", ""), liczba("d"), liczba("dz"),
                                            liczba("b"), p.get("seria", ""),
                                            p.get("na_stanie") == "1"),
                               tsv, KOLUMNY_LOZYSKA)
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
                elif sciezka == "/mag/miniatura3d":
                    m = miniatura3d(bazy, p.get("symbol", ""))
                    if m is None:
                        self._wyslij(404, b"", "text/plain")
                    else:
                        self._wyslij(200, m[0], m[1])
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
                                                "/mag/miniatura?symbol=",
                                                "/mag/miniatura3d?symbol=",
                                                "/mag/typy"]}, tsv)
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
