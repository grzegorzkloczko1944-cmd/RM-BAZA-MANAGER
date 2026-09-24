# -*- coding: utf-8 -*-
"""
Dopasowanie POJEDYNCZEJ pozycji arkusza do kartoteki Subiekta.

Odpowiednik okna „Dopasowanie kartotek", ale dla jednego wiersza i wołany
z menu prawego klawisza w arkuszu RM_BAZA. Powód rozdzielenia (decyzja
użytkownika, 24.09.2026): porządkowanie elementów znormalizowanych PRZED
importem projektu do Subiekta robi się pozycja po pozycji, patrząc na
konkretny wiersz — a nie na liście stu pozycji do przeklikania.

Dwa przypadki użycia, oba obsłużone tym samym narzędziem:

    1. (częstszy) projekt jeszcze nieimportowany — wszystko do obróbki,
    2. (rzadszy) dokładka BOM-u po imporcie — obrabiamy tylko dopisane,
       bo stare wiersze same się bronią (mają `subiekt_symbol`).

═══ ZASADY ═══════════════════════════════════════════════════════════════

**Tylko pozycje NIEZAIMPORTOWANE do Subiekta.** `sprawdz_edytowalnosc()`
pyta o `subiekt_symbol` — dokładnie ten sam znacznik, którym blokuje się
edycję nazwy w komórce (RM_BAZA_v15_MAG_STATS_ORG.py ~14186). Po zasiewie
zmiana nazwy sprawia, że przy kolejnym uruchomieniu okna Projekt/Aktualizacja
RM_BAZA nie rozpozna istniejącej kartoteki i założy DUPLIKAT obok niej.

**Celujemy w JEDEN wiersz, po `item_id`.** `subiekt_dopasowanie.
wpisz_numery_do_bom()` dopasowuje po NAZWIE, bo tam decyzje zapadają
hurtem dla całego BOM-u. Tutaj znamy konkretny wiersz i tylko jego wolno
ruszyć — dwie pozycje o tej samej nazwie w różnych złożeniach to norma.

**Bez zapisu do globalnych mapowań** (decyzja użytkownika, 24.09.2026).
Zmiana siedzi w BOM-ie tego projektu. Spójne z odcięciem czytania mapowań
z tego samego dnia — patrz subiekt_dopasowanie.przygotuj_pozycje().

**Nic po cichu.** Funkcje zwracają opis tego, co się stanie (`podglad_*`),
GUI pokazuje go PRZED zapisem, a po zapisie raport z wartościami.
"""

from typing import Dict, List, Optional

from subiekt_scalanie import norm_kod

#: Powody, dla których wiersza nie wolno tknąć. Klucz → tekst dla człowieka.
BLOKADA_ZASIEW = "zasiew"
BLOKADA_ZAMOWIONA = "zamowiona"
BLOKADA_Z_SUBIEKTA = "z_subiekta"
BLOKADA_BRAK_WIERSZA = "brak_wiersza"
BLOKADA_BRAK_LOCKA = "brak_locka"


def _kolumny(con) -> set:
    return {r[1] for r in con.execute("PRAGMA table_info(items)")}


def czytaj_wiersz(con, item_id) -> Optional[Dict]:
    """Stan wiersza potrzebny do dopasowania. None, gdy wiersza nie ma.

    Nazwa liczona tak samo jak w arkuszu: robocza ma pierwszeństwo przed
    importową. Numer — pierwszy niepusty z trzech kolumn, ta sama kolejność
    co przy czytaniu BOM-u.
    """
    cols = _kolumny(con)
    if not cols:
        return None

    def wybierz(*nazwy):
        """COALESCE po tych kolumnach, które baza faktycznie ma."""
        maja = [f"NULLIF(TRIM({c}), '')" for c in nazwy if c in cols]
        return f"COALESCE({', '.join(maja)}, '')" if maja else "''"

    sql = (f"SELECT {wybierz('work_name', 'src_name')},"
           f"       {wybierz('work_drawing_no', 'norm_drawing_no', 'src_drawing_no')},"
           f"       {wybierz('subiekt_symbol')},"
           f"       COALESCE(ordered_flag, 0),"
           f"       COALESCE(is_manual, 0),"
           f"       COALESCE(notes, ''),"
           f"       {wybierz('subiekt_zasiew_at')}"
           f" FROM items WHERE id = ?"
           if {"ordered_flag"} <= cols else
           f"SELECT {wybierz('work_name', 'src_name')},"
           f"       {wybierz('work_drawing_no', 'norm_drawing_no', 'src_drawing_no')},"
           f"       {wybierz('subiekt_symbol')},"
           f"       0,"
           f"       COALESCE(is_manual, 0),"
           f"       COALESCE(notes, ''),"
           f"       {wybierz('subiekt_zasiew_at')}"
           f" FROM items WHERE id = ?")
    try:
        row = con.execute(sql, (item_id,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    return {
        "id": item_id,
        "nazwa": (row[0] or "").strip(),
        "numer": (row[1] or "").strip(),
        "subiekt_symbol": (row[2] or "").strip(),
        "ordered_flag": int(row[3] or 0),
        "is_manual": int(row[4] or 0),
        "notes": row[5] or "",
        "zasiew_at": (row[6] or "").strip(),
        "cols": cols,
    }


def sprawdz_edytowalnosc(wiersz: Optional[Dict]) -> Optional[Dict]:
    """None = wolno edytować. Inaczej {powod, tytul, tekst} dla człowieka.

    ⛔ TO JEST SEDNO TEGO NARZĘDZIA. Pozycja, która poszła już do Subiekta,
    jest własnością Subiekta: jej nazwa zrodziła symbol kartoteki, a na tej
    kartotece wiszą dokumenty. Podmiana nazwy tutaj nie zmienia niczego
    w Subiekcie — tworzy rozjazd, a przy następnym zasiewie DRUGĄ kartotekę.
    """
    if not wiersz:
        return {"powod": BLOKADA_BRAK_WIERSZA,
                "tytul": "Nie ma takiej pozycji",
                "tekst": "Wiersz zniknął z bazy projektu — odśwież arkusz."}

    # Wiersz dopisany PRZEZ Subiekta (półprodukt / pozycja z ZK). Rozpoznanie
    # to samo co w subiekt_projekt.read_project_items — patrz komentarz przy
    # wpisz_numery_do_bom(): CO PRZYSZŁO Z SUBIEKTA, NIE WRACA DO SUBIEKTA.
    notes = wiersz["notes"]
    if (wiersz["is_manual"] == 1 and wiersz["subiekt_symbol"]
            and (notes.startswith("półprodukt") or notes == "z zamówienia ZK")):
        return {"powod": BLOKADA_Z_SUBIEKTA,
                "tytul": "Pozycja pochodzi z Subiekta",
                "tekst": (
                    f"Ten wiersz założyła RM_BAZA z kartoteki Subiekta:\n\n"
                    f"    {wiersz['subiekt_symbol']}\n\n"
                    f"({notes})\n\n"
                    f"Takiej pozycji nie dopasowujemy — ona JUŻ wskazuje\n"
                    f"kartotekę. Zmiana nazwy zerwałaby powiązanie, a most\n"
                    f"założyłby drugą kartotekę obok istniejącej.")}

    if wiersz["ordered_flag"]:
        return {"powod": BLOKADA_ZAMOWIONA,
                "tytul": "Pozycja jest na zamówieniu",
                "tekst": (
                    "Ta pozycja trafiła już na dokument ZK/ZD w Subiekcie.\n\n"
                    "Należy do dokumentu — podmiana numeru rozjechałaby\n"
                    "powiązanie ZD→pozycja i „Zamówiono\" przestałoby\n"
                    "wracać do arkusza.")}

    if wiersz["subiekt_symbol"]:
        kiedy = wiersz["zasiew_at"] or "—"
        return {"powod": BLOKADA_ZASIEW,
                "tytul": "Pozycja jest już w Subiekcie",
                "tekst": (
                    f"Ta pozycja została założona w Subiekcie jako:\n\n"
                    f"    {wiersz['subiekt_symbol']}\n"
                    f"    (zasiew: {kiedy})\n\n"
                    f"Po zasiewie nazwa jest KLUCZEM kartoteki — zmiana tutaj\n"
                    f"nie zmieni niczego w Subiekcie, a przy następnym\n"
                    f"uruchomieniu okna Projekt/Aktualizacja RM_BAZA nie\n"
                    f"rozpozna istniejącej kartoteki i założy DUPLIKAT.\n\n"
                    f"Kartotekę poprawia się w Subiekcie albo w edytorze\n"
                    f"kartotek (menu SUBIEKT).")}
    return None


def klucz_szukania(wiersz: Dict) -> str:
    """Czym szukamy w katalogu Subiekta.

    Zasada użytkownika z 09.09.2026: **jest numer → szukamy numerem, nie ma
    numeru → szukamy nazwą**. Dla pozycji znormalizowanej symbol w Subiekcie
    i tak powstanie z nazwy, więc numer (gdyby był wyliczony) niczego nie
    znajdzie.
    """
    return wiersz["numer"] or wiersz["nazwa"]


def kandydaci(wiersz: Dict, indeks, fraza: str = "", ile: int = 40) -> List[Dict]:
    """Kartoteki Subiekta warte pokazania przy tym wierszu.

    Najpierw trafienia DOSŁOWNE (znormalizowany symbol albo nazwa równe
    kluczowi) — te idą na górę jako pewne. Potem szukanie po członach
    (`Indeks.szukaj`), które radzi sobie z inną kolejnością słów:
    „6004 rS" → „SS 6004 2RS".

    `fraza` puste = użyj klucza wiersza. Człowiek może ją nadpisać w oknie,
    gdy nazwa z arkusza jest zbyt krzywa, żeby cokolwiek znaleźć.
    """
    szukane = (fraza or "").strip() or klucz_szukania(wiersz)
    if not szukane:
        return []

    k = norm_kod(szukane)
    dokladne, widziane = [], set()
    for poz in (indeks.wg_symbolu.get(k, []) + indeks.wg_nazwy.get(k, [])):
        pid = poz.get("id")
        if pid in widziane:
            continue
        widziane.add(pid)
        dokladne.append({**poz, "dokladne": True})

    reszta = []
    for poz in indeks.szukaj(szukane, ile=ile):
        if poz.get("id") in widziane:
            continue
        widziane.add(poz.get("id"))
        reszta.append({**poz, "dokladne": False})

    return (dokladne + reszta)[:ile]


def _opis_wiersza(symbol: str, nazwa: str) -> str:
    """„SYMBOL   Nazwa" — jedna linia opisująca stan wiersza.

    Tak, jak user widzi go w arkuszu: symbol i nazwa obok siebie, a nie
    dwa osobne pola do sklejania w głowie (uwaga użytkownika 24.09.2026).
    """
    symbol = (symbol or "").strip()
    nazwa = (nazwa or "").strip()
    if symbol and nazwa:
        return f"{symbol}   {nazwa}"
    return symbol or nazwa or "(pusto)"


def podglad_wyboru(wiersz: Dict, kartoteka: Dict) -> Dict:
    """Co się zmieni w arkuszu po wybraniu tej kartoteki. Bez zapisu.

    Zwraca {"teraz", "bedzie", "zmiany", "bez_zmian"} — GUI pokazuje to
    człowiekowi PRZED dotknięciem bazy (zasada „nic po cichu").

    `teraz` i `bedzie` to gotowe linie „SYMBOL   Nazwa": jedna linia = jeden
    stan wiersza. Rozbicie na osobne pola („Numer/symbol: przed… po…",
    „Nazwa: przed… po…") było nieczytelne — trzeba było w pamięci składać,
    jak ostatecznie będzie wyglądał wiersz.

    `zmiany` zostaje dla raportu po zapisie (lista pól, które się ruszyły).
    """
    symbol = (kartoteka.get("symbol") or "").strip()
    nazwa = (kartoteka.get("nazwa") or "").strip()

    # Czego kartoteka nie niesie, to na wierszu zostaje bez zmian.
    symbol_po = symbol or wiersz["numer"]
    nazwa_po = nazwa or wiersz["nazwa"]

    zmiany = []
    if symbol and symbol != wiersz["numer"]:
        zmiany.append(("Numer / symbol", wiersz["numer"] or "(pusto)", symbol))
    if nazwa and nazwa != wiersz["nazwa"]:
        zmiany.append(("Nazwa", wiersz["nazwa"] or "(pusto)", nazwa))

    return {"teraz": _opis_wiersza(wiersz["numer"], wiersz["nazwa"]),
            "bedzie": _opis_wiersza(symbol_po, nazwa_po),
            "zmiany": zmiany,
            "bez_zmian": not zmiany}


def zastosuj_wybor(con, item_id, kartoteka: Dict) -> Dict:
    """Przepisuje JEDEN wiersz na symbol i nazwę z kartoteki Subiekta.

    ⚠️ Zapis przez przekazane połączenie (`db_manager.project_con`), NIE
    przez własne `sqlite3.connect` — przy locku RM_BAZA pisze do kopii
    lokalnej, a zapis wprost na serwer ginie (project_zapis_do_bazy_projektu).

    ⚠️ Nazwę piszemy tylko do `work_name` (robocza). `src_name` z importu
    zostaje nietknięta — po niej można wrócić do nazwy konstruktora.

    Blokadę sprawdzamy TU PONOWNIE, nie ufając GUI: między otwarciem okna
    a kliknięciem mógł wejść zasiew z innej maszyny.
    """
    wiersz = czytaj_wiersz(con, item_id)
    blok = sprawdz_edytowalnosc(wiersz)
    if blok:
        return {"ok": False, "blokada": blok}

    cols = wiersz["cols"]
    symbol = (kartoteka.get("symbol") or "").strip()
    nazwa = (kartoteka.get("nazwa") or "").strip()
    if not symbol:
        return {"ok": False, "blokada": {
            "powod": "brak_symbolu", "tytul": "Kartoteka bez symbolu",
            "tekst": "Wybrana kartoteka nie ma symbolu — nie ma czego wpisać."}}

    ustaw, wart = [], []
    if "work_drawing_no" in cols:
        ustaw.append("work_drawing_no = ?")
        wart.append(symbol)
    if nazwa and "work_name" in cols:
        ustaw.append("work_name = ?")
        wart.append(nazwa)
    if not ustaw:
        return {"ok": False, "blokada": {
            "powod": "stara_baza", "tytul": "Baza sprzed migracji",
            "tekst": "Ta baza projektu nie ma kolumn roboczych "
                     "(work_drawing_no / work_name)."}}

    try:
        con.execute(f"UPDATE items SET {', '.join(ustaw)} WHERE id = ?",
                    (*wart, item_id))
        con.commit()
    except Exception as e:
        # ⚠️ Baza bez locka jest READ-ONLY i SQLite mowi o tym po swojemu
        # ("attempt to write a readonly database"). Dla czlowieka to nie
        # jest zadna informacja — tlumaczymy na to, co ma zrobic
        # (zgloszone 24.09.2026). Lock mogl tez zniknac PO otwarciu okna:
        # wymuszenie z drugiej maszyny albo wygasniecie.
        if "readonly" in str(e).lower() or "read-only" in str(e).lower():
            return {"ok": False, "blokada": {
                "powod": BLOKADA_BRAK_LOCKA,
                "tytul": "Projekt tylko do odczytu",
                "tekst": (
                    "Nie masz locka na tym projekcie, wiec baza jest\n"
                    "otwarta tylko do odczytu i zapis nie przechodzi.\n\n"
                    "Kliknij „Przejmij Lock\" na gornym pasku RM_BAZA,\n"
                    "a potem otworz to okno ponownie (prawy klik na wierszu).\n\n"
                    "Jesli lock mial juz byc Twoj — ktos mogl go wymusic\n"
                    "z drugiej maszyny.")}}
        raise
    return {"ok": True, "symbol": symbol, "nazwa": nazwa,
            "przed": {"numer": wiersz["numer"], "nazwa": wiersz["nazwa"]}}


def plan_nowej_kartoteki(wiersz: Dict, jm: str = "szt") -> Dict:
    """Jak będzie wyglądać kartoteka założona z tego wiersza. Bez zapisu.

    Symbol liczy `subiekt_projekt.symbol_z_nazwy()` — ta sama funkcja, której
    użyje zasiew projektu. Dzięki temu kartoteka założona stąd zostanie
    potem rozpoznana jako TA SAMA, a nie zdublowana.
    """
    from subiekt_projekt import symbol_z_nazwy
    nazwa = wiersz["nazwa"]
    symbol = (wiersz["numer"] or "").strip() or symbol_z_nazwy(nazwa)
    return {"symbol": symbol, "nazwa": nazwa, "rodzaj": "towar", "jm": jm}


# ⛔ NIE MA TU `zaloz_kartoteke()` — I NIE DOPISYWAC (24.09.2026).
#
# Byla: brala symbol z `plan_nowej_kartoteki()`, nazwe z arkusza, rodzaj
# „towar" i jm „szt" — i zakladala kartoteke przez most. Dla pozycji, ktora
# w arkuszu jest SAMYM KODEM („7810210"), dawalo to kartoteke
# „7810210 / 7810210": nazwa nie niesie zadnej informacji, a po pol roku
# nikt nie wie, co to bylo. Uzytkownik odrzucil to wprost — celem
# porzadkowania jest usuniecie takiego balaganu, nie dokladanie go.
#
# Nowe kartoteki zaklada sie w EDYTORZE KARTOTEK (`subiekt_edytor_gui`,
# tryb `nowa=`), ktory ma komplet pol: rodzaj, jednostke, cene ewidencyjna,
# polozenie, opis — i obok liste istniejacych kartotek, wiec widac, czy
# podobna juz jest. Nazwe nadaje czlowiek.
#
# `plan_nowej_kartoteki()` ZOSTAJE: liczy symbol, ktory edytor dostaje
# jako wartosc poczatkowa.
