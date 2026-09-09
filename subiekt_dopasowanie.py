# -*- coding: utf-8 -*-
"""
Etap 3 pracy z elementami handlowymi: DOPASOWANIE do kartotek Subiekta.

Ciąg jest taki:

    1. scalanie zapisów      „UCFL 201" / „UCFL-201" / „UCFL201" → jeden kod
    2. scalanie podobnych    człowiek rozstrzyga potencjalne duplikaty
    3. TO OKNO               kanoniczny kod → konkretne Id kartoteki Subiekta

Ten moduł nie scala niczego. Ma jedno zadanie: dla każdego kodu odpowiedzieć
„które dokładnie Id w Subiekcie?" — albo uczciwie powiedzieć, że nie wie.

═══ ZASADY, KTÓRE MUSZĄ ZOSTAĆ ═══════════════════════════════════════════

**Powiązaniem jest Id, nie nazwa.** Symbol i nazwa lądują w mapowaniu tylko
jako informacja dla człowieka — dzięki temu poprawienie nazwy w Subiekcie
nie zrywa połączenia.

**Żadnego automatycznego fuzzy.** Pomiar z 04.09.2026 (subiekt_podobne.py)
pokazał 389 fałszywych par przy nazwach: „Płyta zewnętrzna" vs „Płyta
wewnętrzna" = 0.933. Podobieństwo może najwyżej USTAWIAĆ KOLEJNOŚĆ
kandydatów w oknie; nigdy niczego nie przypina.

**Niejednoznaczność jest widoczna, nie ukryta.** Poprzednie
`dopasuj_katalog()` robiło `setdefault`, czyli przy dwóch kartotekach o tym
samym znormalizowanym symbolu brało pierwszą z brzegu. W katalogu (3547
kartotek) jest tego realnie: 45 kolizji po symbolu („6004 ZZ" vs „6004ZZ")
i 130 po nazwie („Uszczelka clamp VITON" to TRZY kartoteki: DN10 K=34,
DN10 K=50,5, DN20 K=34). Taki przypadek musi trafić do człowieka.

**Odrzucenie jest pamiętane.** Bez tego user odpina błędne skojarzenie,
a automat przy następnym otwarciu przypina je z powrotem — bo reguła
„symbol == symbol" nadal zachodzi.
"""

from typing import Dict, List, Optional

import subiekt_mapowania
from subiekt_scalanie import norm_kod

# Stany pozycji — kolejność od „gotowe" do „nie wiadomo".
STAN_ZAPAMIETANE = "zapamietane"      # globalne mapowanie (decyzja człowieka)
STAN_SYMBOL = "symbol"                # dokładnie 1 kartoteka po symbolu
STAN_NAZWA = "nazwa"                  # dokładnie 1 po nazwie — do zatwierdzenia
STAN_NIEJEDNOZNACZNE = "niejednoznaczne"   # kilka kandydatów, decyduje człowiek
STAN_BRAK = "brak"                    # nic nie pasuje

#: Do interfejsu: opis i kolor każdego stanu.
OPIS_STANU = {
    STAN_ZAPAMIETANE: ("zapamiętane", "#d6eaf8"),
    STAN_SYMBOL: ("dokładny symbol", "#d5f5e3"),
    STAN_NAZWA: ("po nazwie — potwierdź", "#fdebd0"),
    STAN_NIEJEDNOZNACZNE: ("kilku kandydatów", "#fae5d3"),
    STAN_BRAK: ("brak kartoteki", "#fadbd8"),
}


class Indeks:
    """Katalog Subiekta zindeksowany po znormalizowanym symbolu i nazwie.

    W przeciwieństwie do starego `dopasuj_katalog()` trzyma LISTY, nie
    pojedyncze pozycje — inaczej kolizja znika z pola widzenia.
    """

    def __init__(self, katalog: List[Dict]):
        self.katalog = list(katalog or [])
        self.wg_symbolu: Dict[str, List[Dict]] = {}
        self.wg_nazwy: Dict[str, List[Dict]] = {}
        self.wg_id: Dict[object, Dict] = {}
        for poz in self.katalog:
            k = norm_kod(poz.get("symbol"))
            if k:
                self.wg_symbolu.setdefault(k, []).append(poz)
            k = norm_kod(poz.get("nazwa"))
            if k:
                self.wg_nazwy.setdefault(k, []).append(poz)
            if poz.get("id") is not None:
                self.wg_id[poz["id"]] = poz

    def __len__(self):
        return len(self.katalog)

    def po_id(self, id_subiekt) -> Optional[Dict]:
        return self.wg_id.get(id_subiekt)

    def szukaj(self, fraza: str, ile: int = 50) -> List[Dict]:
        """Kartoteki zawierające frazę w symbolu albo nazwie.

        Kolejność: najpierw trafienia w SYMBOL (to identyfikator), potem
        w nazwę; w obu grupach krótsze symbole pierwsze — krótszy zwykle
        znaczy „czystszy" kod katalogowy.
        """
        f = (fraza or "").strip().upper()
        if not f:
            return []
        w_symbolu, w_nazwie = [], []
        for poz in self.katalog:
            symbol = (poz.get("symbol") or "").upper()
            nazwa = (poz.get("nazwa") or "").upper()
            if f in symbol:
                w_symbolu.append(poz)
            elif f in nazwa:
                w_nazwie.append(poz)
        klucz = lambda p: len(p.get("symbol") or "")
        return (sorted(w_symbolu, key=klucz) + sorted(w_nazwie, key=klucz))[:ile]


def klasyfikuj(kod: str, indeks: Indeks, mapowanie: Optional[Dict] = None,
               odrzucone: Optional[set] = None) -> Dict:
    """Jeden kod → {stan, kandydaci, wybrany}. Bez żadnego fuzzy.

    Kolejność reguł (A–E z ustaleń):
      A. jest globalne mapowanie              → zapamiętane
      B. dokładnie 1 kartoteka po symbolu     → symbol (zielone)
      C. dokładnie 1 po nazwie                → nazwa (żółte, do potwierdzenia)
      D. więcej niż jedna                     → niejednoznaczne (decyzja)
      E. nic                                  → brak

    `odrzucone` to zbiór par (KOD, id_subiekt), które człowiek już odrzucił —
    taki kandydat nie może zostać przyjęty automatem. Zostaje na liście
    kandydatów do ręcznego wyboru, ale nie „wygrywa" sam.
    """
    odrzucone = odrzucone or set()
    k = norm_kod(kod)
    wynik = {"kod": kod, "stan": STAN_BRAK, "kandydaci": [], "wybrany": None}

    # A. Decyzja człowieka zapisana wcześniej — najwyższy priorytet.
    if mapowanie:
        poz = indeks.po_id(mapowanie.get("id_subiekt"))
        if poz is None:
            # Kartoteka mogła zniknąć albo mapowanie jest sprzed czasów, gdy
            # zapisywaliśmy Id. Trzymamy się symbolu, ale mówimy prawdę:
            # to nadal decyzja człowieka, tylko bez potwierdzenia w katalogu.
            poz = {"id": mapowanie.get("id_subiekt"),
                   "symbol": mapowanie.get("symbol_subiekt") or "",
                   "nazwa": mapowanie.get("nazwa_subiekt") or ""}
        wynik.update(stan=STAN_ZAPAMIETANE, wybrany=poz, kandydaci=[poz])
        return wynik

    if not k:
        return wynik

    po_symbolu = list(indeks.wg_symbolu.get(k, []))
    if len(po_symbolu) == 1 and (kod, po_symbolu[0].get("id")) not in odrzucone:
        wynik.update(stan=STAN_SYMBOL, wybrany=po_symbolu[0], kandydaci=po_symbolu)
        return wynik
    if len(po_symbolu) > 1:
        wynik.update(stan=STAN_NIEJEDNOZNACZNE, kandydaci=po_symbolu)
        return wynik

    po_nazwie = list(indeks.wg_nazwy.get(k, []))
    if len(po_nazwie) == 1 and (kod, po_nazwie[0].get("id")) not in odrzucone:
        # Świadomie NIE jest to stan „gotowe": symbol jest identyfikatorem
        # kartoteki, nazwa bywa powtórzona przy różnych rzeczach.
        wynik.update(stan=STAN_NAZWA, wybrany=po_nazwie[0], kandydaci=po_nazwie)
        return wynik
    if len(po_nazwie) > 1:
        wynik.update(stan=STAN_NIEJEDNOZNACZNE, kandydaci=po_nazwie)
        return wynik

    # Odrzucony jedyny kandydat: nie przyjmujemy go, ale pokazujemy.
    if po_symbolu or po_nazwie:
        wynik.update(stan=STAN_NIEJEDNOZNACZNE, kandydaci=po_symbolu + po_nazwie)
    return wynik


def przygotuj_pozycje(items: List[Dict], indeks: Indeks,
                      tylko_handlowe: bool = True) -> List[Dict]:
    """Pozycje BOM-u sklasyfikowane pod dopasowanie.

    `tylko_handlowe` ogranicza się do ZNORMALIZOWANYCH — dla nich kod
    katalogowy jest tożsamością. Detale (numery rysunku) mają własną
    ścieżkę: kartoteka powstaje przy zakładaniu projektu.
    """
    wybrane = []
    for it in items or []:
        typ = (it.get("typ") or "").upper()
        if tylko_handlowe and typ != "ZNORMALIZOWANE":
            continue
        kod = (it.get("nr") or "").strip()
        if not kod:
            continue
        wybrane.append(it)

    kody = [(it.get("nr") or "").strip() for it in wybrane]
    mapowania = subiekt_mapowania.get_many(kody) or {}
    odrzucone = wczytaj_odrzucone()

    out = []
    for it in wybrane:
        kod = (it.get("nr") or "").strip()
        info = klasyfikuj(kod, indeks, mapowania.get(norm_kod(kod))
                          or mapowania.get(kod), odrzucone)
        info["nazwa_rm"] = (it.get("nazwa") or "").strip()
        info["ilosc"] = it.get("qty")
        out.append(info)
    return out


def podsumowanie(pozycje: List[Dict]) -> Dict[str, int]:
    """Licznik pozycji w każdym stanie — do nagłówka okna."""
    out = {s: 0 for s in OPIS_STANU}
    for p in pozycje or []:
        out[p["stan"]] = out.get(p["stan"], 0) + 1
    return out


# ── odrzucone dopasowania ───────────────────────────────────────────────
#
# Osobna tabela w tej samej bazie co mapowania. Bez niej „Odepnij" nic nie
# daje: automat przy następnym otwarciu ponownie dopasuje po symbolu tę samą
# kartotekę, którą człowiek właśnie odrzucił.

_DDL_ODRZUCONE = """
CREATE TABLE IF NOT EXISTS odrzucone_dopasowania (
    klucz_rm    TEXT NOT NULL,
    id_subiekt  INTEGER,
    symbol      TEXT,
    kto         TEXT,
    kiedy       TEXT NOT NULL,
    PRIMARY KEY (klucz_rm, id_subiekt)
)
"""


def _polacz(path=None):
    import sqlite3
    p = path or subiekt_mapowania.DB_PATH
    con = sqlite3.connect(p, timeout=15.0)
    con.execute("PRAGMA journal_mode=DELETE")   # WAL nie działa po SMB
    con.execute("PRAGMA busy_timeout=5000")
    con.row_factory = sqlite3.Row
    return con


def wczytaj_odrzucone(path=None) -> set:
    """{(KOD, id_subiekt)} — pary odrzucone przez człowieka."""
    try:
        con = _polacz(path)
        try:
            con.execute(_DDL_ODRZUCONE)
            return {(r["klucz_rm"], r["id_subiekt"])
                    for r in con.execute(
                        "SELECT klucz_rm, id_subiekt FROM odrzucone_dopasowania")}
        finally:
            con.close()
    except Exception as e:
        print(f"⚠️  wczytaj_odrzucone: {e}")
        return set()


def odrzuc(kod: str, id_subiekt, symbol: str = "", kto: str = None,
           path=None) -> bool:
    """Zapamiętaj, że ta kartoteka NIE pasuje do tego kodu."""
    import os
    from datetime import datetime
    if not kod:
        return False
    try:
        con = _polacz(path)
        try:
            con.execute(_DDL_ODRZUCONE)
            con.execute(
                "INSERT OR REPLACE INTO odrzucone_dopasowania "
                "(klucz_rm, id_subiekt, symbol, kto, kiedy) VALUES (?,?,?,?,?)",
                (kod, id_subiekt, symbol,
                 kto or os.environ.get("USERNAME") or "?",
                 datetime.now().isoformat(timespec="seconds")))
            con.commit()
            return True
        finally:
            con.close()
    except Exception as e:
        print(f"⚠️  odrzuc: {e}")
        return False


def zapisz_decyzje(decyzje: List[Dict], path=None) -> int:
    """[{kod, symbol, id, nazwa}] → ile zapisano.

    Zapis idzie jako SPOSOB_RECZNY: decyzja człowieka, której automat już
    nie nadpisze. Id jest właściwym powiązaniem, symbol i nazwa to opis.
    """
    wpisy = []
    for d in decyzje or []:
        kod = (d.get("kod") or "").strip()
        symbol = (d.get("symbol") or "").strip()
        if not kod or not symbol:
            continue
        wpisy.append((kod, symbol, subiekt_mapowania.SPOSOB_RECZNY,
                      d.get("id"), d.get("nazwa")))
    if not wpisy:
        return 0
    return subiekt_mapowania.put_many(wpisy, path=path)
