# -*- coding: utf-8 -*-
"""
Dopasowanie pozycji ZNORMALIZOWANYCH do kartotek Subiekta — logika.

Po co, skoro `subiekt_podobne.py` odradza fuzzy match?

Tamten pomiar (04.09.2026) dotyczył DETALI: nazwy takie jak „Płyta
zewnętrzna" / „Płyta wewnętrzna" różnią się jednym słowem, a znaczą różne
części — 389 fałszywych par, żaden próg ich nie rozdziela. Tu jest inaczej
z dwóch powodów:

1. **Tylko ZNORMALIZOWANE.** Dla nich nazwa JEST kodem katalogowym:
   „ASK KFL 001", „GN 822.6-4-M8-C", „5M/4960 25mm". Porównujemy więc kody,
   nie opisy konstrukcyjne. Detale (Kabina, Słupek, Pas lewy) są wykluczone
   — to na nich fuzzy match trafiał w kartoteki z cudzych projektów.

2. **Nic nie dzieje się automatycznie.** Podpowiedzi to WYŁĄCZNIE lista do
   wyboru przez człowieka; bez kliknięcia nie powstaje żadne mapowanie.
   Zapis idzie jako SPOSOB_RECZNY, czyli decyzja, której automat już nie
   nadpisze.

Skąd biorą się pozycje bez kartoteki: znormalizowane nie mają numeru
rysunku, więc RM_BAZA robi im symbol przez obcięcie nazwy do 13 znaków
(„Blokada GN 822.6-4-M8-C" → „BlokadaGN822."). Takim symbolem nie da się
trafić w Subiekta — stąd potrzeba ręcznego skojarzenia.

Miara: podobieństwo Jaccarda na tokenach alfanumerycznych (symbol + nazwa
kartoteki vs nazwa pozycji), z premią za wspólne tokeny „mocne" — czyli
takie, które zawierają cyfrę („822", "M8", "5M", "001"). W kodach
katalogowych to one niosą tożsamość, a same słowa („Koło", „Dysza") są
wspólne dla setek pozycji.
"""

import re
from typing import List, Dict, Optional

# Minimalny wynik, żeby w ogóle pokazać podpowiedź. Niżej to już losowe
# wspólne słowo — lepiej pokazać pusto i dać userowi wpisać własne, niż
# proponować śmieć, który ktoś kliknie w pośpiechu.
PROG_POKAZ = 0.15
ILE_PODPOWIEDZI = 5

_ROZDZIELACZ = re.compile(r"[^0-9A-ZĄĆĘŁŃÓŚŻŹ]+")
_MA_CYFRE = re.compile(r"\d")

# Numer rysunku RMPAK: „2632-200.37", „027-100.00Z", „ZP196-000.00ZZ",
# „013-100.04a" — grupa cyfr, myślnik, grupa cyfr, kropka, cyfry i
# ewentualna końcówka typu (X/XX/Z/ZZ). Taka kartoteka to DETAL konkretnego
# projektu, nigdy odpowiednik normalium: „ASKUBAL KFL 000" nie ma nic
# wspólnego z „2621-000.00ZZ Ceramizator", choć oba mają w sobie „000"
# (zgłoszone 09.09.2026).
_NUMER_RYSUNKU = re.compile(
    r"^[A-Z]{0,4}\d{2,4}-\d{2,3}\.\d{2}[A-Z]{0,2}$", re.IGNORECASE)


def wyglada_na_numer_rysunku(symbol: str) -> bool:
    """Czy symbol kartoteki to numer rysunku detalu (a nie kod handlowy)."""
    return bool(_NUMER_RYSUNKU.match((symbol or "").strip()))


def tokeny(tekst: str) -> set:
    """Tokeny alfanumeryczne (≥2 znaki) z tekstu, wielkimi literami.

    Jednoznakowe odpadają: „x" z „20x15" i „i" z „p-M6" to szum, a nie kod.
    """
    if not tekst:
        return set()
    return {t for t in _ROZDZIELACZ.split(tekst.upper()) if len(t) >= 2}


def _mocne(zbior: set) -> set:
    """Tokeny niosące tożsamość — te z cyfrą („822", „M8", „KFL001")."""
    return {t for t in zbior if _MA_CYFRE.search(t)}


def wynik(tokeny_pozycji: set, tokeny_kartoteki: set) -> float:
    """0..1 — jak bardzo kartoteka pasuje do pozycji.

    Jaccard (część wspólna / suma) plus premia za wspólne tokeny z cyfrą.
    Bez premii „Koło 5M-20-15-14" tak samo pasowało do „Koło zębate 20 5M 15"
    jak do „Koło ręczne VRTP.125" — decyduje właśnie wspólne „5M" i „20".
    """
    if not tokeny_pozycji or not tokeny_kartoteki:
        return 0.0
    wspolne = tokeny_pozycji & tokeny_kartoteki
    if not wspolne:
        return 0.0

    mocne_wspolne = _mocne(wspolne)
    mocne_pozycji = _mocne(tokeny_pozycji)

    # Gdy pozycja ma tokeny „kodowe" (z cyfrą), a kartoteka nie trafiła
    # w ŻADEN z nich — to nie jest ta sama rzecz, choćby zgadzało się słowo
    # opisowe. Bez tego „Dźwignia LAC.63 p-M6x20" dostawało podpowiedź
    # „Czujnik CAB" (symbol „63"), bo samo „63" wystarczało do przekroczenia
    # progu. Rozstrzyga kod, nie rzeczownik.
    # Token SAMYCH cyfr („000", „63", „10") nie jest trafieniem w kod:
    # „000" z „ASKUBAL KFL 000" pasuje do KAŻDEGO numeru rysunku typu
    # 2621-000.00ZZ, a „63" z „Dźwignia LAC.63" do kartoteki o symbolu „63"
    # (Czujnik CAB). Tożsamość niosą tokeny MIESZANE (litera+cyfra: „M8",
    # „5M", „GN822") — te liczymy jako kodowe.
    mieszane_wspolne = {t for t in mocne_wspolne if not t.isdigit()}
    mieszane_pozycji = {t for t in mocne_pozycji if not t.isdigit()}

    # Gdy pozycja ma tokeny mieszane, a kartoteka nie trafiła w żaden —
    # to nie ta sama rzecz, choćby zgadzała się liczba albo rzeczownik.
    if mieszane_pozycji and not mieszane_wspolne:
        return 0.0

    # Pozycja bez tokenów mieszanych („ASKUBAL KFL 000") — wtedy decyduje
    # część wspólna SŁÓW, a sama zgodna liczba nie może wystarczyć.
    if not mieszane_pozycji:
        slowa_wspolne = {t for t in wspolne if not _MA_CYFRE.search(t)}
        if not slowa_wspolne:
            return 0.0

    baza = len(wspolne) / len(tokeny_pozycji | tokeny_kartoteki)
    if mieszane_pozycji:
        # Ile z „kodowych" tokenów pozycji pokryła kartoteka.
        premia = len(mieszane_wspolne) / len(mieszane_pozycji)
        return min(1.0, 0.6 * baza + 0.4 * premia)
    return baza


def policz_uzycia(projects_dir: str) -> Dict[str, int]:
    """{SYMBOL: w ilu projektach użyty} — z kolumny items.subiekt_symbol.

    Popularność jest mocną przesłanką przy wyborze kartoteki: jeśli firma
    od dawna zamawia „KFL 001", to prawie na pewno o tę kartotekę chodzi,
    a nie o podobnie nazwaną, użytą raz. Ta sama zasada, co kolumna
    „Najczęściej w firmie" w oknie scalania kodów.

    Liczymy PROJEKTY, nie wiersze: dziesięć pozycji w jednym projekcie to
    nadal jeden przypadek użycia.
    """
    import glob
    import os
    import sqlite3

    licznik: Dict[str, int] = {}
    for sciezka in glob.glob(os.path.join(projects_dir, "project_*.sqlite")):
        try:
            con = sqlite3.connect(f"file:{sciezka}?mode=ro", uri=True, timeout=3)
            try:
                symbole = {(r[0] or "").strip().upper() for r in con.execute(
                    "SELECT DISTINCT subiekt_symbol FROM items "
                    "WHERE subiekt_symbol IS NOT NULL AND subiekt_symbol <> ''")}
            finally:
                con.close()
        except Exception:
            continue          # baza w trakcie zapisu / uszkodzona — pomijamy
        for sym in symbole:
            if sym:
                licznik[sym] = licznik.get(sym, 0) + 1

    # Drugie źródło: globalna tabela mapowań. `items.subiekt_symbol`
    # wypełnia dopiero zasiew projektu (funkcja świeża — 09.09.2026 miał ją
    # jeden projekt), a mapowania pamiętają skojarzenia od początku i
    # przeżywają usunięcie projektu. Bez tego kolumna „Użyć" pokazywałaby
    # samo „—" i nie pomagała w niczym.
    try:
        import sqlite3
        import subiekt_mapowania
        con = sqlite3.connect(f"file:{subiekt_mapowania.DB_PATH}?mode=ro",
                              uri=True, timeout=3)
        try:
            for (sym,) in con.execute(
                    "SELECT symbol_subiekt FROM mapowania "
                    "WHERE symbol_subiekt IS NOT NULL AND symbol_subiekt <> ''"):
                k = (sym or "").strip().upper()
                if k and k not in licznik:
                    licznik[k] = 1
        finally:
            con.close()
    except Exception:
        pass          # brak tabeli mapowań = zostaje to, co z projektów

    return licznik


def stany_z_magazynu(pozycje_magazynu) -> Dict[str, float]:
    """{SYMBOL: ilość dostępna} z komendy mostu „magazyn"."""
    out: Dict[str, float] = {}
    for p in pozycje_magazynu or []:
        sym = (p.get("Symbol") or "").strip().upper()
        if not sym:
            continue
        try:
            out[sym] = float(p.get("Dostepne") or 0)
        except (TypeError, ValueError):
            out[sym] = 0.0
    return out


class Indeks:
    """Katalog Subiekta przygotowany do szybkiego wyszukiwania.

    Tokeny liczone RAZ dla 3500 kartotek — inaczej każde pytanie o
    podpowiedzi (a jest ich tyle, co pozycji w oknie) skanowałoby katalog
    od nowa.
    """

    def __init__(self, katalog: List[Dict], uzycia: Optional[Dict] = None,
                 stany: Optional[Dict] = None):
        # Oba słowniki są opcjonalne: okno ma się otworzyć także wtedy, gdy
        # magazyn jest chwilowo nieosiągalny albo liczenie użyć trwa.
        self.uzycia = uzycia or {}
        self.stany = stany or {}
        self.pozycje = []
        for poz in katalog or []:
            symbol = (poz.get("symbol") or "").strip()
            nazwa = (poz.get("nazwa") or "").strip()
            if not symbol and not nazwa:
                continue
            # Kartoteki o symbolu będącym numerem rysunku odpadają: szukamy
            # odpowiednika NORMALIUM, a detal z cudzego projektu nim nie jest.
            if wyglada_na_numer_rysunku(symbol):
                continue
            self.pozycje.append((tokeny(f"{symbol} {nazwa}"), poz))

    def __len__(self):
        return len(self.pozycje)

    def podpowiedzi(self, tekst: str, ile: int = ILE_PODPOWIEDZI,
                    prog: float = PROG_POKAZ) -> List[Dict]:
        """Najlepiej pasujące kartoteki — [{wynik, symbol, nazwa, id}].

        Posortowane malejąco. Pusta lista, gdy nic nie przekroczyło progu —
        to poprawny wynik, nie błąd: user wpisuje wtedy symbol ręcznie.
        """
        t = tokeny(tekst)
        if not t:
            return []
        trafienia = []
        for tk, poz in self.pozycje:
            w = wynik(t, tk)
            if w >= prog:
                trafienia.append((w, poz))
        # Malejąco po wyniku, przy remisie krótszy symbol pierwszy — krótszy
        # zwykle znaczy „czystszy" kod katalogowy.
        trafienia.sort(key=lambda x: (-x[0], len((x[1].get("symbol") or ""))))
        return [self._opis(w, p) for w, p in trafienia[:ile]]

    def _opis(self, w, p) -> Dict:
        symbol = (p.get("symbol") or "").strip()
        klucz = symbol.upper()
        return {"wynik": round(w, 3) if w is not None else None,
                "symbol": symbol,
                "nazwa": (p.get("nazwa") or "").strip(),
                "id": p.get("id"),
                # None = nie wiemy (nie podano danych), 0 = wiemy, że zero.
                "uzyc": self.uzycia.get(klucz) if self.uzycia else None,
                "stan": self.stany.get(klucz) if self.stany else None}

    def znajdz_tekstem(self, fraza: str, ile: int = 30) -> List[Dict]:
        """Zwykłe szukanie po fragmencie — gdy user woli wpisać sam.

        Nie miesza się z podpowiedziami: tu liczy się dosłowne zawieranie,
        bez żadnej heurystyki.
        """
        f = (fraza or "").strip().upper()
        if not f:
            return []
        out = []
        for _tk, p in self.pozycje:
            symbol = (p.get("symbol") or "").strip()
            nazwa = (p.get("nazwa") or "").strip()
            if f in symbol.upper() or f in nazwa.upper():
                out.append(self._opis(None, p))
                if len(out) >= ile:
                    break
        return out


def pozycje_do_dopasowania(items: List[Dict], katalog: List[Dict],
                           dopasuj_katalog) -> List[Dict]:
    """ZNORMALIZOWANE bez kartoteki w Subiekcie — wejście dla okna.

    `dopasuj_katalog` wstrzykiwane z subiekt_scalanie, żeby nie duplikować
    reguły dopasowania po znormalizowanym kodzie (symbol przed nazwą).
    Pozycja, która ma trafienie 1:1, nie wymaga niczyjej decyzji.
    """
    znorm = [it for it in (items or [])
             if (it.get("typ") or "").upper() == "ZNORMALIZOWANE"]
    if not znorm:
        return []
    kody = [(it.get("nr") or "").strip() for it in znorm]
    trafienia = dopasuj_katalog(kody, katalog or [])
    braki = []
    for it in znorm:
        kod = (it.get("nr") or "").strip()
        if trafienia.get(kod):
            continue
        braki.append({
            "kod": kod,
            "nazwa": (it.get("nazwa") or "").strip(),
            "ilosc": it.get("qty"),
        })
    return braki
