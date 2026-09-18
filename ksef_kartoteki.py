# -*- coding: utf-8 -*-
"""
Dopasowanie pozycji faktury KSeF do kartotek Subiekta.

Warstwa BEZ GUI — da się uruchomić ze skryptu i zmierzyć na danych.
Okno archiwum (`ksef_archiwum`) używa tego do kolumny „Kartoteka" i do
zbiorczego zakładania brakujących pozycji.

╔══════════════════════════════════════════════════════════════════════════╗
║ KOLEJNOŚĆ DOPASOWANIA — od najpewniejszego. Nie zmieniać bez pomiaru.    ║
║                                                                          ║
║   1. ręczne zapamiętane mapowanie (supplier_id + symbol)  → PEWNE        ║
║   2. NUMER RYSUNKU RM — nasz detal, nie towar obcy         → PEWNE        ║
║   3. dokładny symbol katalogowy                           → PEWNE        ║
║   4. symbol po normalizacji, TYLKO gdy jednoznaczny       → KANDYDAT     ║
║   5. BRAK → decyzja człowieka                                            ║
║                                                                          ║
║ ⚠️ Krok 3 PROPONUJE, nigdy nie zapisuje trwałego mapowania. Normalizacja ║
║ prędzej czy później zlepi dwa różne symbole, a błąd rozejdzie się po     ║
║ WSZYSTKICH przyszłych fakturach tego dostawcy.                           ║
║                                                                          ║
║ ⚠️ ŻADNEGO fuzzy match po nazwie. Zmierzone 04.09.2026 i odrzucone:      ║
║ 389 par RÓŻNYCH detali przekroczyło próg podobieństwa                    ║
║ ('Płyta zewnętrzna' vs 'Płyta wewnętrzna' = 0.933). Patrz nagłówek       ║
║ `subiekt_podobne.py` — tam jest pełny pomiar i uzasadnienie.             ║
╚══════════════════════════════════════════════════════════════════════════╝

Symbol sam z siebie NIE jest kluczem globalnym — dwóch dostawców używa tego
samego oznaczenia dla różnych rzeczy. Dlatego mapowanie trzyma parę
(`supplier_id`, `symbol_dostawcy`), a NIP z faktury służy tylko do znalezienia
`supplier_id`.
"""

import re

#: Cztery końcowe stany pozycji. `BRAK_DECYZJI` blokuje utworzenie PZ.
KARTOTEKA = "KARTOTEKA"              # dopasowana do istniejącego asortymentu
NOWA_KARTOTEKA = "NOWA_KARTOTEKA"    # kartoteka założona przed chwilą
USLUGA = "USLUGA"                    # nie bierze udziału w PZ
POZYCJA_ZBIORCZA = "POZYCJA_ZBIORCZA"  # jedna linia = wiele detali, patrz niżej
#: Detal z NASZEGO rysunku, zlecony kooperantowi. To NIE jest towar handlowy:
#: jego tożsamością jest numer rysunku, nie symbol dostawcy. Zmierzone na
#: fakturze AMB PRODUKT (17.09.2026): 5/5 numerów odnalazło się w BOM-ach
#: projektów, 0/5 w kartotece Subiekta — szukanie po symbolu jest tu
#: z definicji bezowocne. Wiąże się z pozycją ZD, nie z kartoteką.
RYSUNEK_RM = "RYSUNEK_RM"
BRAK_DECYZJI = "BRAK_DECYZJI"        # wymaga człowieka

#: Statusy, które pozwalają wystawić PZ. Usługa i pozycja zbiorcza nie wchodzą
#: na stan, ale też nie blokują — obie są świadomą decyzją człowieka.
STATUSY_OK = (KARTOTEKA, NOWA_KARTOTEKA, USLUGA, POZYCJA_ZBIORCZA, RYSUNEK_RM)
#: Statusy, których pozycje trafiają na PZ. `RYSUNEK_RM` wchodzi na stan
#: dopiero wtedy, gdy ma wskazaną kartotekę — sam numer rysunku nie wystarczy.
STATUSY_NA_PZ = (KARTOTEKA, NOWA_KARTOTEKA, RYSUNEK_RM)

#: Skąd wzięło się dopasowanie — do pokazania człowiekowi i do decyzji,
#: czy wolno zapisać mapowanie bez pytania.
ZRODLO_MAPOWANIE = "mapowanie"       # ręczna decyzja z przeszłości
ZRODLO_SYMBOL = "symbol"             # dokładne trafienie
ZRODLO_NORMALIZACJA = "normalizacja"  # KANDYDAT — wymaga potwierdzenia

#: Skąd wzięliśmy identyfikator pozycji — to NIE to samo, co źródło dopasowania.
#: Kolumna „Źródło" w oknie pokazuje właśnie to, bo od tego zależy, na ile
#: identyfikatorowi wolno ufać.
IDENT_INDEKS = "INDEKS"    # pole <Indeks> z wiersza faktury
IDENT_SYMBOL = "SYMBOL"    # całe P_7 jest symbolem (QUAY)
IDENT_NAZWA = "NAZWA"      # kod wyłuskany z początku P_7 (AMB) — PROPOZYCJA
IDENT_RYSUNEK = "RYSUNEK"  # numer rysunku RM — nasz detal, nie towar obcy
IDENT_BRAK = "BRAK"        # nie da się wskazać identyfikatora (alu-frost)

#: Źródło dopasowania po numerze rysunku (krok 2 hierarchii).
ZRODLO_RYSUNEK = "rysunek"

#: Jednostki, po których poznajemy usługę, gdy dostawca nie oznaczył jej inaczej.
_JEDNOSTKI_USLUG = {"usl", "usł", "usl.", "usł.", "godz", "godz.", "h", "rbh"}
#: „Usługa kurierska", „Usługi transportowe", „OBSLUGA", „Obsługa
#: zamówienia" — na POCZĄTKU tekstu. Sam początek, bo „usług" w środku
#: nazwy bywa częścią nazwy towaru.
#: ⚠️ Lista rozszerzona 18.09.2026: „Dostawa" (MA-JA, `szt`, bez Opisu)
#: dostawala TW i „BRAK DECYZJI", choc w kartotece Subiekta stoi jako
#: `12 — Usluga dostawy`, rodzaj „Usluga". Takie pozycje nie wchodza na stan
#: i nie maja po co blokowac PZ. To nadal PODPOWIEDZ — czlowiek moze zmienic.
_NAZWA_USLUGI = re.compile(
    r"^(us[łl]ug[aiy]?|obs[łl]ug[aiy]?|dostaw[ay]?|transport(?:u|em|ow\w*)?"
    r"|przesy[łl]k[ai]?|fracht\w*|op[łl]at[ay]?|pakowani\w*|spedycj\w*)\b")


#: Kod rysunku RM w postaci `013-100.30a`, `ROTO-100.01`, `2557-100.15X` —
#: człon, myślnik, liczba, kropka, liczba, opcjonalna literka. Celowo WĄSKI:
#: szerszy wzorzec rozbijał symbole QUAY (`618/4 2Z=684 2Z` → `618/4` + reszta),
#: a to cały symbol, nie kod z nazwą.
_KOD_RYSUNKU = re.compile(r"^([A-Z0-9]{2,}-[0-9]{2,}\.[0-9]+[A-Za-z]{0,2})\s+(\S.*)$")
#: Ten sam wzorzec, ale gdy numer rysunku stoi SAM (`027-200.01`) — bez nazwy
#: doklejonej za nim.
_SAM_RYSUNEK = re.compile(r"^[A-Z0-9]{2,}-[0-9]{2,}\.[0-9]+[A-Za-z]{0,2}$")


def jest_numerem_rysunku(s):
    r"""Czy tekst wygląda na numer rysunku RM (`027-200.01`, `2602-100.41X`).

    ⚠️ Porównania numerów rysunku są NIEWRAŻLIWE NA WIELKOŚĆ LITER — zmierzone
    17.09.2026 na 4554 numerach z 91 BOM-ów: różnicę niesie litera jako taka
    (`.30a` / `.30b` / `.30c` to kolejne długości boku transportera), ale NIE
    jej wielkość. Jedyna kolizja po podniesieniu do wielkich liter to
    `Uszczelka` / `uszczelka`, czyli nie numer rysunku.

    Faktura AMB pisze `013-100.30B`, BOM ma `013-100.30b` — to TEN SAM detal
    i rozróżnianie ich gubiłoby 6 z 6 trafień.
    """
    return bool(_SAM_RYSUNEK.match((s or "").strip()))


def klucz_rysunku(s):
    """Numer rysunku sprowadzony do porównywalnej postaci (wielkie litery).

    Patrz `jest_numerem_rysunku` — wielkość liter jest w tych numerach
    przypadkowa, a `a`/`b`/`c` na końcu i tak zostają rozróżnione.
    """
    return (s or "").strip().upper()


def rozpoznaj_identyfikator(pozycja):
    r"""(identyfikator, nazwa, zrodlo) — czym ta pozycja się identyfikuje.

    ⚠️ NIE KAŻDA POZYCJA MA SYMBOL DOSTAWCY. Zmierzone na trzech fakturach
    (17.09.2026) — trzy zupełnie różne układy przy tej samej schemie FA(3):

    * **QUAY** — `P_7` to czysty symbol (`618/6 2Z`), `<Indeks>` brak.
      → IDENT_SYMBOL, identyfikator = całe P_7.

    * **AMB PRODUKT** — `<Indeks>` NIE ISTNIEJE, a `P_7` skleja kod rysunku
      z nazwą: `013-100.30a Bok transportera 0,3mb`.
      → IDENT_NAZWA, identyfikator = `013-100.30a`, nazwa = reszta.
      To PROPOZYCJA wyłuskana regexem — człowiek zatwierdza mapowanie.

    * **alu-frost** — `<Indeks>` jest, ale to KATEGORIA, nie symbol:
      `Detale cięte laserem` powtarza się w 3 z 4 wierszy, a pozycje różnią
      się dopiero pełnym `P_7`. Takiego indeksu NIE WOLNO użyć jako symbolu
      kartoteki — jedna linia może odpowiadać wielu detalom z kilku ZD.
      → IDENT_BRAK; pozycja jest kandydatem na POZYCJA_ZBIORCZA.

    Pełne `P_7` zostaje zawsze — jako `tekst_pozycji` w wyniku dopasowania.
    """
    tekst = (getattr(pozycja, "nazwa", "") or "").strip()
    indeks = (getattr(pozycja, "indeks", "") or "").strip()

    if indeks:
        # Indeks RÓWNY całej nazwie to normalny identyfikator (alu-frost:
        # `Usługa Kurierska`). Indeks będący tylko PREFIKSEM dłuższej nazwy
        # jest podejrzany o bycie kategorią — `dopasuj` odrzuci go, gdy
        # dodatkowo powtarza się w kilku wierszach.
        if indeks.upper() == tekst.upper() or not tekst.upper().startswith(indeks.upper()):
            return indeks, tekst, IDENT_INDEKS

    # Numer rysunku SAM — nasz detal bez nazwy na fakturze (`027-200.01`).
    if jest_numerem_rysunku(tekst):
        return tekst, tekst, IDENT_RYSUNEK

    # Numer rysunku + nazwa w jednym polu (AMB: `013-100.30a Bok transportera`).
    m = _KOD_RYSUNKU.match(tekst)
    if m:
        return m.group(1), m.group(2).strip(), IDENT_RYSUNEK

    if indeks:
        # Prefiks dłuższej nazwy — zwracamy go, ale `dopasuj` sprawdzi jeszcze,
        # czy nie jest kategorią powtórzoną w kilku pozycjach.
        return indeks, tekst, IDENT_INDEKS

    return tekst, tekst, IDENT_SYMBOL


def _indeksy_zbiorcze(pozycje):
    """Indeksy, które powtarzają się w kilku wierszach — czyli kategorie.

    `Detale cięte laserem` u alu-frost opisuje trzy różne dostawy. Symbol
    występujący raz może być identyfikatorem; powtórzony na pewno nie jest.
    """
    licz = {}
    for p in pozycje:
        i = (getattr(p, "indeks", "") or "").strip().upper()
        if i:
            licz[i] = licz.get(i, 0) + 1
    return {i for i, n in licz.items() if n > 1}


def normalizuj_symbol(s):
    r"""Symbol do postaci porównywalnej: same litery i cyfry, wielkie.

    `IR 12*16*20` → `IR121620`, `T5-295/16` → `T529516`. Świadomie gubimy
    separatory, bo każdy dostawca stawia je inaczej — ale właśnie dlatego
    wynik wolno traktować tylko jako KANDYDATA (patrz nagłówek modułu).
    """
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def wyglada_na_usluge(pozycja):
    """Czy pozycja to raczej usługa niż towar magazynowy.

    Podpowiedź dla okna, NIE rozstrzygnięcie: decyzję podejmuje człowiek.

    ⚠️ Zmierzone 18.09.2026 (wcześniejszy opis tej funkcji KŁAMAŁ): `OBSLUGA`
    z faktury QUAY ma jednostkę `szt.`, nie `usł.`, a jej `Opis` to „Obsluga"
    — ani jednostka, ani „usług" w opisie jej nie łapały. Pozycja dostawała
    TW, a „Usługi: 1" w liczniku pochodziło z ręcznej decyzji. Stąd trzeci
    test: nazwa/indeks/Opis zaczynające się od „usługa…" albo „obsługa…".
    Nie ma sensu zakładać takim pozycjom kartoteki magazynowej tylko po to,
    żeby licznik pokazał 55/55.
    """
    jm = (getattr(pozycja, "jednostka", "") or "").strip().lower()
    if jm in _JEDNOSTKI_USLUG:
        return True
    opis = (getattr(pozycja, "dodatkowe", None) or {}).get("Opis", "") or ""
    if "usług" in opis.lower() or "uslug" in opis.lower():
        return True
    # Nazwa, indeks albo Opis ZACZYNAJĄCE się od „Usługa…"/„Obsługa…".
    # alu-frost: „Usługa Kurierska", `szt`, bez DodatkowyOpis. QUAY:
    # „OBSLUGA", `szt.`, Opis „Obsluga". Żadnej z nich nie widziały dwa
    # powyższe testy (18.09.2026). Tylko początek tekstu — patrz _NAZWA_USLUGI.
    for tekst in ((getattr(pozycja, "nazwa", "") or ""),
                  (getattr(pozycja, "indeks", "") or ""), opis):
        if _NAZWA_USLUGI.match(tekst.strip().lower()):
            return True
    return False


def proponowana_nazwa(pozycja):
    """Nazwa dla nowej kartoteki: opis z faktury + symbol dostawcy.

    `Sprzęgło` + `ROTEX GS19 64ShDH` → `Sprzęgło ROTEX GS19 64ShDH`.
    Zgodne z tym, jak wyglądają istniejące kartoteki („Łożysko liniowe
    LMF 16 LUU", „Zespół łożyskowy UCP205"). Gdy opisu brak — sam symbol.

    To PROPOZYCJA; pole jest edytowalne przed zapisem.
    """
    symbol = (getattr(pozycja, "nazwa", "") or "").strip()
    opis = (getattr(pozycja, "dodatkowe", None) or {}).get("Opis", "").strip()
    if not opis:
        return symbol
    if normalizuj_symbol(opis) and normalizuj_symbol(opis) in normalizuj_symbol(symbol):
        return symbol                    # opis już siedzi w symbolu
    return ("%s %s" % (opis, symbol)).strip()


class Dopasowanie:
    """Wynik dopasowania JEDNEJ pozycji. Bez logiki — nosi decyzję."""

    __slots__ = ("pozycja", "status", "asortyment_id", "symbol_subiekt",
                 "nazwa_subiekt", "zrodlo", "identyfikator", "nazwa_pozycji",
                 "zrodlo_identyfikatora", "rodzaj_kartoteki")

    def __init__(self, pozycja, status=BRAK_DECYZJI, asortyment_id=None,
                 symbol_subiekt="", nazwa_subiekt="", zrodlo="",
                 identyfikator="", nazwa_pozycji="", zrodlo_identyfikatora=IDENT_BRAK,
                 rodzaj_kartoteki=""):
        self.pozycja = pozycja
        #: Rodzaj WSKAZANEJ kartoteki Subiekta („Towar"/„Usługa"/„Komplet").
        #: Pusty, gdy pozycja nie ma kartoteki — wtedy i tylko wtedy wolno
        #: zgadywać typ z nazwy.
        self.rodzaj_kartoteki = rodzaj_kartoteki
        self.status = status
        self.asortyment_id = asortyment_id
        self.symbol_subiekt = symbol_subiekt
        self.nazwa_subiekt = nazwa_subiekt
        self.zrodlo = zrodlo
        #: Czym pozycja się identyfikuje — pusty, gdy się nie da (alu-frost).
        self.identyfikator = identyfikator
        #: Nazwa/opis pozycji. Dla AMB to `P_7` BEZ kodu; inaczej całe `P_7`.
        self.nazwa_pozycji = nazwa_pozycji
        #: IDENT_* — na ile identyfikatorowi wolno ufać.
        self.zrodlo_identyfikatora = zrodlo_identyfikatora

    @property
    def pewne(self):
        """Czy dopasowanie wolno przyjąć bez pytania człowieka."""
        return self.zrodlo in (ZRODLO_MAPOWANIE, ZRODLO_SYMBOL)

    def __repr__(self):
        return "<Dopasowanie %s %s id=%s %s>" % (
            getattr(self.pozycja, "nazwa", "?"), self.status,
            self.asortyment_id, self.zrodlo)


def _usluga_po_nazwie(katalog, nazwa):
    """Kartoteka rodzaju „Usługa" pasująca nazwą do pozycji faktury.

    Dopasowanie jest luźne (jedna nazwa zawiera drugą), bo dostawca pisze
    „Dostawa", a kartoteka nazywa się „Usługa dostawy". Wolno tak TYLKO dla
    usług: nie wchodzą na stan, więc pomyłka nie psuje magazynu, a i tak
    zostaje widoczna w oknie i do zmiany przez człowieka.

    Zwraca kartotekę tylko przy JEDNYM trafieniu — dwa znaczą, że nazwa nie
    rozstrzyga, i wtedy lepiej zostawić wybór człowiekowi.
    """
    n = _rdzen(nazwa)
    if len(n) < 4:
        return None
    trafienia = []
    for k in katalog:
        rodzaj = (k.get("rodzaj") or k.get("Rodzaj") or "").strip().lower()
        if not rodzaj.startswith("usług") and not rodzaj.startswith("uslug"):
            continue
        # Porównujemy RDZENIE słów, bo nazwy różnią się odmianą:
        # „Dostawa" na fakturze vs „Usługa dostawy" w kartotece.
        slowa = {_rdzen(s) for s in (k.get("nazwa") or k.get("Nazwa") or "").split()}
        if n in slowa:
            trafienia.append(k)
    return trafienia[0] if len(trafienia) == 1 else None


def _rdzen(slowo):
    """Słowo bez końcówki fleksyjnej — „dostawa"/„dostawy" → „dostaw"."""
    s = (slowo or "").strip().lower()
    for k in ("ami", "ach", "owy", "owa", "ego", "ej", "y", "a", "i", "u", "e", "ę", "ą"):
        if len(s) > 4 and s.endswith(k):
            return s[: -len(k)]
    return s


def _indeksuj_katalog(katalog):
    """Dwie mapy: po symbolu dokładnym i po znormalizowanym.

    Mapa znormalizowana trzyma LISTĘ — gdy dwa różne symbole zlewają się do
    tej samej postaci, dopasowanie jest NIEJEDNOZNACZNE i nie wolno go użyć.
    """
    doslownie, znormalizowane = {}, {}
    for k in katalog:
        sym = (k.get("symbol") or k.get("Symbol") or "").strip()
        if not sym:
            continue
        doslownie.setdefault(sym.upper(), k)
        znormalizowane.setdefault(normalizuj_symbol(sym), []).append(k)
    return doslownie, znormalizowane


def dopasuj(pozycje, katalog, mapowania=None):
    """Dopasowuje pozycje faktury do kartotek. Zwraca [Dopasowanie].

    `katalog`   — [{"id", "symbol", "nazwa"}] z `wczytaj_katalog_subiekta()`
                  albo [{"Id", "Symbol", "Nazwa"}] prosto z mostu.
    `mapowania` — {symbol_dostawcy_upper: {"asortyment_id", "symbol", "nazwa"}}
                  dla TEGO dostawcy. Ma pierwszeństwo nad wszystkim.
    """
    doslownie, znormalizowane = _indeksuj_katalog(katalog)
    mapowania = {(k or "").upper(): v for k, v in (mapowania or {}).items()}
    wynik = []

    zbiorcze = _indeksy_zbiorcze(pozycje)

    for p in pozycje:
        ident, nazwa_poz, zrodlo_id = rozpoznaj_identyfikator(p)

        # Indeks powtórzony w kilku wierszach to KATEGORIA, nie identyfikator
        # (alu-frost: `Detale cięte laserem` w 3 z 4 pozycji). Taka linia może
        # odpowiadać wielu detalom z kilku ZD — nie zakładamy jej kartoteki.
        if (getattr(p, "indeks", "") or "").strip().upper() in zbiorcze:
            ident, zrodlo_id = "", IDENT_BRAK

        def _mk(status, kart=None, zrodlo=""):
            return Dopasowanie(
                p, status,
                (kart or {}).get("id") or (kart or {}).get("Id"),
                (kart or {}).get("symbol") or (kart or {}).get("Symbol") or "",
                (kart or {}).get("nazwa") or (kart or {}).get("Nazwa") or "",
                zrodlo, ident, nazwa_poz, zrodlo_id,
                # Rodzaj WSKAZANEJ kartoteki — to jest odczyt ze stanu Subiekta
                # i ma pierwszeństwo przed zgadywaniem typu z nazwy.
                (kart or {}).get("rodzaj") or (kart or {}).get("Rodzaj") or "")

        # Bez identyfikatora nie ma czego szukać w kartotece — od razu
        # decyzja człowieka (kandydat na POZYCJA_ZBIORCZA).
        if not ident:
            wynik.append(_mk(BRAK_DECYZJI))
            continue

        # 1. Ręczne mapowanie — decyzja człowieka z przeszłości, wygrywa
        #    z każdym automatem.
        m = mapowania.get(ident.upper())
        if m:
            wynik.append(Dopasowanie(
                p, KARTOTEKA, m.get("asortyment_id"), m.get("symbol", ""),
                m.get("nazwa", ""), ZRODLO_MAPOWANIE, ident, nazwa_poz, zrodlo_id))
            continue

        # 2. NUMER RYSUNKU — nasz detal. Idzie PRZED symbolem katalogowym, bo
        #    to inna tożsamość: dla takiej pozycji szukanie w kartotece
        #    dostawcy jest z definicji bezowocne (AMB: 5/5 w BOM-ach,
        #    0/5 w kartotece Subiekta). Kartoteka bywa, ale wiąże się ją
        #    ręcznie — bo ten sam rysunek występuje w wielu projektach
        #    (`013-100.30B` w sześciu), więc ZD wybiera człowiek.
        if zrodlo_id == IDENT_RYSUNEK:
            k = doslownie.get(ident.upper())
            # ⚠️ Numer rysunku, ktory MA dokladna kartoteke w Subiekcie, jest
            # zwykla pozycja katalogowa — nie ma powodu wyrozniac go statusem
            # RYSUNEK_RM.
            #
            # Inaczej wynik zalezal od tego, czy dostawca powtorzyl numer
            # w nazwie towaru: `REG-300.11X Podkladka lozyska oporowego`
            # szlo tedy i dostawalo „RYSUNEK RM", a `REG-300.20` z nazwa
            # „Nakretka szesciokatna Tr16x4" bylo rozpoznawane jako INDEKS
            # i dostawalo „KARTOTEKA" — mimo ze obie kartoteki sa identyczne
            # co do budowy i obie sa rodzaju „Towar" (zgloszone 18.09.2026).
            #
            # RYSUNEK_RM zostaje dla numerow BEZ kartoteki — tam faktycznie
            # trzeba siegnac do mapowan po numerze rysunku i wybrac projekt.
            if k:
                wynik.append(_mk(KARTOTEKA, k, ZRODLO_SYMBOL))
                continue
            wynik.append(Dopasowanie(
                p, RYSUNEK_RM, None, "", "", "", ident, nazwa_poz, zrodlo_id))
            continue

        # 3. Dokładny symbol katalogowy.
        k = doslownie.get(ident.upper())
        if k:
            wynik.append(_mk(KARTOTEKA, k, ZRODLO_SYMBOL))
            continue

        # 4. Po normalizacji — TYLKO gdy jednoznaczne. Dwa trafienia znaczą,
        #    że normalizacja zlała różne symbole; wtedy decyduje człowiek.
        kandydaci = znormalizowane.get(normalizuj_symbol(ident), [])
        if len(kandydaci) == 1:
            wynik.append(_mk(KARTOTEKA, kandydaci[0], ZRODLO_NORMALIZACJA))
            continue

        # 5. USŁUGA — pozycja bez symbolu, która wygląda na usługę (dostawa,
        #    transport, obsługa…). Nie wchodzi na stan, więc nie ma po co
        #    blokować PZ statusem „brak decyzji" (18.09.2026).
        #
        #    Gdy w kartotece Subiekta stoi pozycja rodzaju „Usługa" o tej samej
        #    nazwie, wskazujemy ją wprost — `12 — Usługa dostawy` dla „Dostawa"
        #    z MA-JA. To dopasowanie po NAZWIE, więc tylko dla usług: przy
        #    towarach nazwa bywa wieloznaczna i zgadywanie po niej dało 389
        #    fałszywych par (patrz notatka o podpowiedziach).
        if wyglada_na_usluge(p):
            k = _usluga_po_nazwie(katalog, nazwa_poz or ident)
            if k:
                wynik.append(_mk(USLUGA, k, ZRODLO_SYMBOL))
            else:
                wynik.append(_mk(USLUGA))
            continue

        # 6. Brak — statusu nie nadajemy automatycznie: to decyzja człowieka.
        wynik.append(_mk(BRAK_DECYZJI))

    return wynik


def podsumowanie(dopasowania):
    """{'razem', 'znalezione', 'brak', 'uslugi', 'kandydaci'} — do nagłówka okna."""
    return {
        "razem": len(dopasowania),
        "znalezione": sum(1 for d in dopasowania if d.status in (KARTOTEKA, NOWA_KARTOTEKA)),
        "brak": sum(1 for d in dopasowania if d.status == BRAK_DECYZJI),
        "uslugi": sum(1 for d in dopasowania if d.status == USLUGA),
        "zbiorcze": sum(1 for d in dopasowania if d.status == POZYCJA_ZBIORCZA),
        "rysunki": sum(1 for d in dopasowania if d.status == RYSUNEK_RM),
        "bez_identyfikatora": sum(1 for d in dopasowania if not d.identyfikator),
        "kandydaci": sum(1 for d in dopasowania if d.zrodlo == ZRODLO_NORMALIZACJA),
    }


def mozna_wystawic_pz(dopasowania):
    """Czy wszystkie pozycje mają rozstrzygnięty status (§ obieg przyjęć).

    Warunkiem NIE jest „100% pozycji ma kartoteki", tylko 100% pozycji
    MAGAZYNOWYCH — usługa jest świadomą decyzją i nie blokuje.
    """
    return all(d.status in STATUSY_OK for d in dopasowania)
