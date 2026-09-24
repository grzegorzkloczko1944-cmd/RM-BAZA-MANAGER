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
        # Fraza z kilku czlonow ("6004 rS") szukana DOSLOWNIE nie trafia
        # w nic, bo kartoteka nazywa sie "SS 6004 2RS" — czlony sa te same,
        # ale w innej kolejnosci i z dodatkami. Wymagamy wiec, zeby kazdy
        # czlon wystapil gdziekolwiek w symbolu albo nazwie (09.09.2026).
        czlony = [c for c in f.split() if c]
        w_symbolu, w_nazwie = [], []
        for poz in self.katalog:
            symbol = (poz.get("symbol") or "").upper()
            nazwa = (poz.get("nazwa") or "").upper()
            razem = symbol + " " + nazwa
            if not all(c in razem for c in czlony):
                continue
            if f in symbol or all(c in symbol for c in czlony):
                w_symbolu.append(poz)
            else:
                w_nazwie.append(poz)
        klucz = lambda p: len(p.get("symbol") or "")
        return (sorted(w_symbolu, key=klucz) + sorted(w_nazwie, key=klucz))[:ile]


def klasyfikuj(kod: str, indeks: Indeks, mapowanie: Optional[Dict] = None,
               odrzucone: Optional[set] = None, nazwa: str = "",
               bez_numeru: bool = False) -> Dict:
    """Jeden element → {stan, kandydaci, wybrany}. Bez żadnego fuzzy.

    CZYM SZUKAMY (zasada użytkownika, 09.09.2026):

    * znormalizowany MA kod w bazie  → pracujemy na KODZIE,
    * NIE MA kodu                    → pracujemy na NAZWIE.

    To nie jest drobiazg. Pozycja bez numeru rysunku dostaje symbol
    wyliczony przez `symbol_z_nazwy()` — obcięty do 13 znaków, bez spacji
    („rolka SITI 8010235" → „rolkaSITI8010"). Takiego ciągu NIE MA nigdzie:
    ani w RM_BAZA, ani w Subiekcie. Szukanie po nim to gwarantowane zero
    trafień, więc dla tych pozycji kluczem jest pełna nazwa.

    Kolejność reguł (A–E):
      A. jest globalne mapowanie              → zapamiętane
      B. dokładnie 1 kartoteka po kluczu      → symbol (zielone)
      C. dokładnie 1 po nazwie                → nazwa (żółte, do potwierdzenia)
      D. więcej niż jedna                     → niejednoznaczne (decyzja)
      E. nic                                  → brak

    `odrzucone` to zbiór par (KOD, id_subiekt), które człowiek już odrzucił —
    taki kandydat nie może zostać przyjęty automatem. Zostaje na liście
    kandydatów do ręcznego wyboru, ale nie „wygrywa" sam.
    """
    odrzucone = odrzucone or set()
    # Klucz wyszukiwania: kod, gdy jest prawdziwy; inaczej nazwa.
    klucz = (nazwa or kod) if bez_numeru else (kod or nazwa)
    k = norm_kod(klucz)
    wynik = {"kod": kod, "stan": STAN_BRAK, "kandydaci": [], "wybrany": None,
             "klucz": klucz}

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

    # Pozycja bez numeru: jej „symbol" w Subiekcie i tak powstaje z nazwy,
    # więc sprawdzamy oba indeksy — kartoteka mogła zostać założona
    # wcześniej dokładnie tą samą drogą.
    po_symbolu = list(indeks.wg_symbolu.get(k, []))
    if bez_numeru and not po_symbolu:
        po_symbolu = [p for p in indeks.wg_nazwy.get(k, [])]
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
    # ⛔ DOPASOWANIE WYLACZONE (24.09.2026, decyzja uzytkownika) ──────────────
    # Algorytm ma WIDZIEC PUSTA TABELE mapowan: kazda pozycja trafia do okna
    # jako „do decyzji" / „brak kartoteki", nic nie jest podpowiadane z tego,
    # co zapisano wczesniej. Dane w tabeli mapowan SA NIETKNIETE — to tylko
    # odciecie odczytu w tym jednym miejscu.
    #
    # ⚠️ NIE ROZSZERZAC tego wylaczenia na `subiekt_projekt.py` (scalanie
    # ilosci na ZK). Tamto korzysta z tej samej tabeli, ale robi co innego:
    # skleja wiersze BOM-u wskazujace JEDNA kartoteke. Bez niego most —
    # ktory ustawia ilosc WPROST, nie dodaje — pozwala drugiej pozycji
    # nadpisac pierwsza i na dokumencie zostaje mniejsza liczba
    # (7+1 dawalo 1 zamiast 8; projekt 2627, 15.09.2026).
    #
    # POWROT: skasowac te trzy linie i odkomentowac `get_many` ponizej.
    mapowania = {}
    # mapowania = subiekt_mapowania.get_many(kody) or {}
    odrzucone = wczytaj_odrzucone()

    out = []
    for it in wybrane:
        kod = (it.get("nr") or "").strip()
        nazwa = (it.get("nazwa") or "").strip()
        bez_nr = bool(it.get("bez_numeru"))
        info = klasyfikuj(kod, indeks,
                          mapowania.get(norm_kod(kod)) or mapowania.get(kod),
                          odrzucone, nazwa=nazwa, bez_numeru=bez_nr)
        info["nazwa_rm"] = nazwa
        # ILOSC Z BOM-u, nie z ZK. `qty` to COALESCE(order_qty, ...),
        # a `order_qty` jest ODBICIEM dokumentu: dwa wiersze dowiazane
        # do jednej kartoteki widza TE SAMA pozycje ZK i pokazywaly
        # obie 4.0, majac w BOM-ie 4 i 20 (15.09.2026).
        info["ilosc"] = (it.get("qty_bom")
                         if it.get("qty_bom") not in (None, "")
                         else it.get("qty"))
        # Czy `kod` to PRAWDZIWY numer rysunku z BOM-u, czy symbol wyliczony
        # z nazwy przez symbol_z_nazwy() (obcięcie do 13 znaków, bez spacji).
        # Dla pozycji bez numeru rysunku ten drugi jest fikcją: w bazie go
        # NIE MA i nie da się po nim niczego zlokalizować — tożsamością jest
        # nazwa. Interfejs musi te przypadki rozróżniać (09.09.2026).
        info["bez_numeru"] = bez_nr
        out.append(info)
    return out


def podsumowanie(pozycje: List[Dict]) -> Dict[str, int]:
    """Licznik pozycji w każdym stanie — do nagłówka okna."""
    out = {s: 0 for s in OPIS_STANU}
    for p in pozycje or []:
        out[p["stan"]] = out.get(p["stan"], 0) + 1
    return out


# ── Podpowiedzi dla „brak kartoteki" ────────────────────────────────────────
#
# ⚠️ TO NIE JEST DOPASOWANIE — TO PROPOZYCJE DO OBEJRZENIA PRZEZ CZŁOWIEKA.
#
# Reguła jeden-do-jednego (klasyfikuj() wyżej) odpowiada na pytanie „które Id",
# i albo trafia dokładnie, albo mówi „brak kartoteki" z pustą listą. W projekcie
# 89 takich pozycji było 46 na 123 — panel kandydatów świecił pustką, choć
# kartoteka często istniała pod minimalnie innym zapisem („9261 SGS-M10x1,25"
# vs „SGS-M10x1,25", „ASK KFL 001" vs „KFL 001").
#
# ⚠️ DLACZEGO TO NIGDY NIE MOŻE PRZYPINAĆ SAMO (pomiar 04.09.2026,
# subiekt_podobne.py): 389 par RÓŻNYCH detali przekracza każdy sensowny próg —
# „Płyta zewnętrzna" vs „Płyta wewnętrzna" = 0.933, „Korek 14mm" vs „Korek
# 64mm" = 0.889. Prawdziwe trafienia dają 1.000, fałszywe siedzą tuż pod nimi
# i żaden próg ich nie rozdziela. Zatwierdzone błędne skojarzenie trafiłoby do
# GLOBALNYCH mapowań i po cichu działało we wszystkich przyszłych projektach.
# Dlatego: podpowiedź pokazujemy, wybiera CZŁOWIEK, nic nie dzieje się samo.
#
# Porównujemy KAŻDE pole z każdym (nazwa i symbol po obu stronach) i bierzemy
# najlepszy wynik — pomiar na projekcie 89 pokazał, że samo porównanie nazw
# gubi trafienia oczywiste dla człowieka: „Korpus zaworu" = 1.000 wychodzi
# dopiero z pary nazwa~nazwa, a „3304" → „3304 RS 20x52x22,2" z nazwa~symbol.

#: Domyślny próg. Wybrany na realnych danych (projekt 89, 46 pozycji):
#: 0.70 zostawia trafne (DIN 6923, KFL 001, SGS-M10x1,25) i odcina szum
#: („Nypel do węża" → „Oś napędowa" = 0.64, „3304" → „DR3430" = 0.60).
PROG_PODPOWIEDZI = 0.70

#: Ile propozycji na pozycję. Więcej niż 5 i tak nikt nie przegląda.
TOP_PODPOWIEDZI = 5


def _pola_zrodlowe(poz: Dict) -> List[tuple]:
    """(etykieta, tekst) z pozycji RM_BAZA — nazwa i kod/numer rysunku.

    Dla pozycji BEZ numeru rysunku `kod` jest symbolem wyliczonym z nazwy
    (obcięcie do 13 znaków), więc niesie mniej niż sama nazwa — ale bywa
    jedynym miejscem, gdzie został np. numer katalogowy producenta.
    """
    return [("nazwa", (poz.get("nazwa_rm") or "").strip()),
            ("symbol", (poz.get("kod") or "").strip())]


def podpowiedzi(poz: Dict, katalog: List[Dict], prog: float = PROG_PODPOWIEDZI,
                top_n: int = TOP_PODPOWIEDZI, pomijaj_symbole=(),
                bez_numeru_rysunku: bool = False) -> List[Dict]:
    """[{wynik, skad, kartoteka}] — najbardziej podobne kartoteki, najlepsza pierwsza.

    `pomijaj_symbole` — kartoteki już przypisane innym pozycjom tego projektu;
    bez tego ta sama kartoteka podpowiada się kilku detalom naraz.

    `bez_numeru_rysunku` wyłącza porównania, w których po stronie RM_BAZA stoi
    kod/numer rysunku. Numery z jednej rodziny projektów są do siebie podobne
    z natury („ZP179-401.00ZZ" vs „ZP196-000.00ZZ" = 0.75), a nie mówią nic
    o tym, czy to ta sama część — użytkownik przełącza to w oknie.
    """
    try:
        from subiekt_podobne import podobienstwo
    except ImportError:
        return []

    zrodla = [(nz, t) for nz, t in _pola_zrodlowe(poz) if t]
    if bez_numeru_rysunku:
        zrodla = [(nz, t) for nz, t in zrodla if nz != "symbol"]
    if not zrodla:
        return []

    pomijane = {str(s).strip().upper() for s in (pomijaj_symbole or ()) if s}
    out = []
    for k in katalog or []:
        if (k.get("symbol") or "").strip().upper() in pomijane:
            continue
        best, skad = 0.0, ""
        for nz, tekst in zrodla:
            for np_, cel in (("nazwa", k.get("nazwa")), ("symbol", k.get("symbol"))):
                if not cel:
                    continue
                w = podobienstwo(tekst, cel)
                if w > best:
                    # Skrót, nie pełne słowa: „symbol ~ symbol" nie mieści się
                    # w kolumnie i ucinało się do „symbol ~ sy…" (15.09.2026).
                    # n = nazwa, s = symbol; po stronie RM_BAZA → Subiekta.
                    best, skad = w, f"{nz[0]}→{np_[0]}".upper()
        if best >= prog:
            out.append({"wynik": best, "skad": skad, "kartoteka": k})

    # Malejąco; przy remisie krótsza nazwa pierwsza — zwykle jest tą ogólną,
    # a nie wariantem z dopiskiem.
    out.sort(key=lambda d: (-d["wynik"], len(d["kartoteka"].get("nazwa") or "")))
    return out[:top_n]


def zajete_symbole(pozycje: List[Dict]) -> set:
    """Symbole kartotek już przypisanych w tym projekcie."""
    out = set()
    for p in pozycje or []:
        w = p.get("wybrany") or {}
        s = (w.get("symbol") or "").strip().upper()
        if s:
            out.add(s)
    return out


# ── Dopisanie symbolu do BOM-u ──────────────────────────────────────────────
def _powod_pominiecia(con, cols, nazwa_col, nazwa) -> str:
    """Czemu UPDATE nic nie zmienił — żeby okno mogło powiedzieć user-owi.

    Kolejność pytań od najbardziej konkretnego: „to pozycja z Subiekta" jest
    ważniejszą informacją niż „ma już numer", bo znaczy „tak ma być".
    """
    if {"subiekt_symbol", "is_manual", "notes"} <= cols:
        z_subiekta = con.execute(
            f"SELECT COUNT(*) FROM items WHERE {nazwa_col} = ?"
            "  AND COALESCE(is_manual, 0) = 1"
            "  AND COALESCE(subiekt_symbol, '') <> ''"
            "  AND (COALESCE(notes, '') LIKE 'półprodukt%'"
            "       OR COALESCE(notes, '') = 'z zamówienia ZK')",
            (nazwa,)).fetchone()[0]
        if z_subiekta:
            return "pozycja pochodzi z Subiekta — nie ruszamy"
    if "ordered_flag" in cols:
        zamowione = con.execute(
            f"SELECT COUNT(*) FROM items WHERE {nazwa_col} = ?"
            "  AND COALESCE(ordered_flag, 0) = 1", (nazwa,)).fetchone()[0]
        if zamowione:
            return "pozycja jest już na ZK/ZD"
    return "pozycja ma już numer rysunku"


def wpisz_numery_do_bom(project_id, pary: Dict[str, Dict]) -> Dict:
    """Przepisuje pozycję BOM na dane z kartoteki Subiekta.

    `pary` to {nazwa pozycji w BOM: {"symbol": ..., "nazwa": ...}}.
    Dopasowujemy po NAZWIE, bo te pozycje z definicji nie mają numeru —
    nazwa jest ich jedyną tożsamością.

    Wpisuje OBA pola (decyzja użytkownika 15.09.2026):

        przed:  numer = (pusto)     nazwa = „6004 RS"
        po:     numer = „6004RS"    nazwa = „6004RS INOX"

    Po co: arkusz zaczyna mówić tym samym językiem co Subiekt, więc przy
    NASTĘPNYM projekcie ta sama pozycja trafi od razu regułą jeden-do-jednego
    (symbol == symbol) i nie wróci do „brak kartoteki". To jest cel całego
    okna: uzupełnić BOM, ZANIM pójdzie do Subiekta.

    Zwraca {"wpisane": n, "pominiete": [(nazwa, powód), ...]}.

    ⚠️ TO JEST JEDYNE MIEJSCE, W KTÓRYM TO OKNO ZMIENIA BOM. Reszta wiąże
    tylko kod z Id kartoteki w globalnych mapowaniach.

    ⛔ NIE RUSZAMY POZYCJI JUŻ ZAMÓWIONYCH (`ordered_flag`). Detal, który
    wszedł na ZK/ZD, jest własnością dokumentu w Subiekcie — podmiana numeru
    rozjechałaby powiązanie ZD→pozycja i „Zamówiono" przestałoby wracać do
    arkusza.

    ⛔ NIE NADPISUJEMY ISTNIEJĄCEGO NUMERU. Warunek w SQL wymaga, żeby
    wszystkie trzy kolumny numeru były puste — inaczej pozycja nie jest tą,
    o której mówimy, a cudza wartość nie może zniknąć po cichu.

    ⚠️ NAZWĘ NADPISUJEMY, ale tylko w `work_name` — kolumnie ROBOCZEJ.
    `src_name` zostaje nietknięta: to zapis z importu BOM-u i po nim wraca
    pierwotna nazwa z arkusza konstruktora, gdyby trzeba było się cofnąć.
    """
    import sqlite3
    from subiekt_stany import PROJECTS_DIR
    import os

    wynik = {"wpisane": 0, "pominiete": []}
    if not pary:
        return wynik

    sciezka = os.path.join(PROJECTS_DIR, f"project_{project_id}.sqlite")
    if not os.path.exists(sciezka):
        wynik["pominiete"] = [(n, "brak bazy projektu") for n in pary]
        return wynik

    con = sqlite3.connect(sciezka)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(items)")}
        if "work_drawing_no" not in cols:
            wynik["pominiete"] = [(n, "baza bez work_drawing_no") for n in pary]
            return wynik

        pusty_numer = ("COALESCE(NULLIF(TRIM(work_drawing_no), ''),"
                       "         NULLIF(TRIM(norm_drawing_no), ''),"
                       "         NULLIF(TRIM(src_drawing_no), ''), '') = ''")
        # Starsze bazy projektów mogą nie mieć flagi zamówienia — wtedy nie ma
        # czego sprawdzać, a brak kolumny nie może zablokować całej operacji.
        warunek_zam = ("AND COALESCE(ordered_flag, 0) = 0"
                       if "ordered_flag" in cols else "")

        # ⛔ CO PRZYSZŁO Z SUBIEKTA, NIE WRACA DO SUBIEKTA.
        #
        # Wiersze dopisane przez `_dopisz_pozycje_z_zk` i półprodukty są
        # ROZPOZNAWANE PO BRAKU NUMERU RYSUNKU (patrz filtr w
        # subiekt_projekt.read_project_items). Wpisanie im numeru zdjęłoby tę
        # ochronę: `build_plan` policzyłby symbol z nazwy, most założyłby DRUGĄ
        # kartotekę obok istniejącej i dopisał ją na ZK przy każdym przebiegu
        # — duplikat towaru i podwójne zamówienie (awaria z 14.09.2026).
        #
        # Dlatego omijamy je TYM SAMYM warunkiem, którym rozpoznaje je tamten
        # filtr. Warunek jest jawny, a nie oparty na tym, jak dane wyglądają
        # dziś: dopisanie `notes` albo `is_manual` w przyszłości nie otworzy
        # tu furtki.
        warunek_z_subiekta = ""
        if {"subiekt_symbol", "is_manual", "notes"} <= cols:
            warunek_z_subiekta = (
                "AND NOT (COALESCE(is_manual, 0) = 1"
                "         AND COALESCE(subiekt_symbol, '') <> ''"
                "         AND (COALESCE(notes, '') LIKE 'półprodukt%'"
                "              OR COALESCE(notes, '') = 'z zamówienia ZK'))")
        nazwa_col = ("COALESCE(NULLIF(TRIM(work_name), ''), TRIM(src_name))"
                     if {"work_name", "src_name"} <= cols else "TRIM(src_name)")

        # Nazwę przepisujemy tylko wtedy, gdy baza ma kolumnę roboczą —
        # w starszych projektach zostaje sam numer.
        pisz_nazwe = "work_name" in cols

        for nazwa, dane in pary.items():
            nazwa = (nazwa or "").strip()
            if isinstance(dane, str):          # zgodność ze starym wywołaniem
                dane = {"symbol": dane}
            symbol = (dane.get("symbol") or "").strip()
            nazwa_sub = (dane.get("nazwa") or "").strip()
            if not nazwa or not symbol:
                continue
            # Najpierw sprawdzamy, CZY jest co ruszać i dlaczego nie.
            ile_pasuje = con.execute(
                f"SELECT COUNT(*) FROM items WHERE {nazwa_col} = ?",
                (nazwa,)).fetchone()[0]
            if not ile_pasuje:
                wynik["pominiete"].append((nazwa, "nie ma takiej pozycji w BOM"))
                continue
            ustaw = ["work_drawing_no = ?"]
            wart = [symbol]
            if pisz_nazwe and nazwa_sub:
                ustaw.append("work_name = ?")
                wart.append(nazwa_sub)
            cur = con.execute(
                f"UPDATE items SET {', '.join(ustaw)} "
                f"WHERE {nazwa_col} = ? AND {pusty_numer} "
                f"{warunek_zam} {warunek_z_subiekta}",
                (*wart, nazwa))
            if cur.rowcount:
                wynik["wpisane"] += cur.rowcount
            else:
                wynik["pominiete"].append((nazwa, _powod_pominiecia(
                    con, cols, nazwa_col, nazwa)))
        con.commit()
    finally:
        con.close()
    return wynik


# ── odrzucone dopasowania ───────────────────────────────────────────────
#
# Osobna tabela w tej samej bazie co mapowania — na RM_SERWER, operacje
# `map-odrzuc` / `map-odrzucone-lista` (schemat: migracje serwera). Bez niej
# „Odepnij" nic nie daje: automat przy następnym otwarciu ponownie dopasuje
# po symbolu tę samą kartotekę, którą człowiek właśnie odrzucił.
# Parametr `path=` został dla zgodności z wołającymi — ignorowany.


def wczytaj_odrzucone(path=None) -> set:
    """{(KOD, id_subiekt)} — pary odrzucone przez człowieka."""
    try:
        import rm_klient
        return {(r["klucz_rm"], r["id_subiekt"])
                for r in rm_klient.master_read("map-odrzucone-lista")}
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
        import rm_klient
        rm_klient.master_exec("map-odrzuc", {
            "klucz_rm": kod, "id_subiekt": id_subiekt, "symbol": symbol,
            "kto": kto or os.environ.get("USERNAME") or "?",
            "kiedy": datetime.now().isoformat(timespec="seconds")})
        return True
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
