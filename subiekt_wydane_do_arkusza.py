# -*- coding: utf-8 -*-
"""„Ilość dostarczonych" z Subiekta — dla pozycji, które Subiekt zna.

PO CO
─────
Do 13.09.2026 `delivered_qty` była polem WYŁĄCZNIE ręcznym: wpisywanym
w arkuszu albo przez stary skaner „Uzupełnianie DOSTARCZONO". Kolumna
SUBIEKT pokazywała tylko „czy jest kartoteka / ZK / ZD" — wydania nigdy
nie były w jej zakresie (`StanPozycji.cs`: „FZ świadomie POMINIĘTE").

Skutek: RW wystawione w Subiekcie nie zmieniało nic w arkuszu. Wyszło przy
pierwszym wydaniu ze schowka — dokument powstał, arkusz stał w miejscu.

⚠️ DWA ŚWIATY W JEDNEJ KOLUMNIE — I TO JEST CELOWE
──────────────────────────────────────────────────
Nie każda pozycja projektu żyje w Subiekcie. Część istnieje tylko
w RM_BAZA (usługi, kooperacja, detale nieskartotekowane) i dla nich
`delivered_qty` **musi zostać polem ręcznym** — nikt inny go nie wypełni.

Dlatego nadpisujemy TYLKO te pozycje, które Subiekt zna i potrafi
policzyć. Rozpoznanie jest darmowe: tryb `wydanie-stan` zwraca wyłącznie
symbole mające ślad w dokumentach projektu (ZK, PW albo RW). Czego tam
nie ma — tego nie ruszamy.

    symbol JEST w odpowiedzi Subiekta   → delivered_qty = wydano z RW
    symbolu NIE MA                      → zostaje, co było (wpis ręczny)

NADPISUJEMY, NIE DODAJEMY
─────────────────────────
Subiekt jest właścicielem faktu magazynowego, więc arkusz ma pokazywać
JEGO sumę, a nie to, co RM_BAZA zdążyła zaobserwować. Dodawanie
(„+= to, co właśnie wydałem") rozjeżdżałoby się przy RW wystawionym poza
RM_BAZA, przy powtórzonym zapisie i po korekcie dokumentu w Subiekcie.
"""

from datetime import datetime


def wydane_z_subiekta(numer_projektu, magazyn="MASTER", timeout=300):
    """{SYMBOL: ilość} — suma RW tego projektu, prosto z Subiekta.

    Tylko symbole, które Subiekt zna. Rzuca wyjątek, gdy most nie działa —
    wołający decyduje, czy to blokuje pracę.
    """
    import subiekt_bridge
    from subiekt_zamowienia import sam_numer
    dane = subiekt_bridge.call(
        "wydanie-stan",
        {"projekt": sam_numer(numer_projektu), "magazyn": magazyn},
        timeout=timeout, write=False) or {}
    out = {}
    for p in dane.get("pozycje") or ():
        symbol = (p.get("symbol") or "").strip()
        if symbol:
            out[symbol] = float(p.get("wydano") or 0)
    return out


def _mapa_bom(con, project_id):
    """{SYMBOL_WIELKIMI: (item_id, delivered_qty)} — CAŁY BOM jednym zapytaniem.

    ⚠️ PAKIETEM, NIE N+1. Pytanie o każdy symbol osobno to przy 200 pozycjach
    400 zapytań (SELECT + UPDATE na sztukę). Jeden przelot po tabeli załatwia
    wszystko i pozwala potem zrobić jeden `executemany`.

    Klucz normalizowany TRIM + wielkie litery, na wartości EFEKTYWNEJ numeru
    (`COALESCE(NULLIF(work_…), src_…)`) — tak samo, jak numer widzi arkusz.
    Trzymamy oba warianty (roboczy i źródłowy), bo symbol z Subiekta może
    pasować do któregokolwiek.
    """
    mapa = {}
    for item_id, work, src, dost in con.execute(
            "SELECT id, work_drawing_no, src_drawing_no, delivered_qty"
            "  FROM items WHERE project_id = ?", (project_id,)):
        for kandydat in (work, src):
            k = (kandydat or "").strip().upper()
            # Pierwszy wygrywa: `work_drawing_no` idzie przed `src_`, tak jak
            # w COALESCE, więc nadpisanie zepsułoby pierwszeństwo.
            if k and k not in mapa:
                mapa[k] = (item_id, None if dost is None else float(dost))
    return mapa


def zapisz(con, project_id, wydane, log=None):
    """Wpisuje `wydane` do delivered_qty. Zwraca listę faktycznych zmian.

    Zwraca `[(item_id, symbol, przed, po)]` — tylko pozycje, w których
    liczba się ZMIENIŁA. Dzięki temu wołający może pokazać użytkownikowi,
    co się stało („nic po cichu"), zamiast raportować setki „zmian" bez
    zmiany.

    `con` MUSI być połączeniem arkusza (`db_manager.project_con`) pod
    lockiem — RM_BAZA pracuje na kopii lokalnej i nadpisuje plik na
    serwerze przy zwalnianiu locka, więc zapis obok tego połączenia znika.
    """
    if con is None or not project_id or not wydane:
        return []
    teraz = datetime.now().isoformat()
    mapa = _mapa_bom(con, project_id)          # JEDEN odczyt całego BOM-u

    zmiany, do_zapisu = [], []
    for symbol, ilosc in wydane.items():
        trafienie = mapa.get((symbol or "").strip().upper())
        if not trafienie:
            continue                    # pozycji nie ma w BOM-ie — nie ruszamy
        item_id, przed = trafienie
        po = float(ilosc)
        if przed is not None and abs(przed - po) < 1e-9:
            continue                    # bez zmiany — nie dotykamy wiersza
        do_zapisu.append((po, teraz, teraz, item_id))
        zmiany.append((item_id, symbol, przed, po))

    if do_zapisu:
        con.executemany(                        # JEDEN zapis pakietowy
            "UPDATE items SET delivered_qty = ?, delivered_updated_at = ?,"
            "                 updated_at = ? WHERE id = ?", do_zapisu)
        con.commit()
    if log:
        for item_id, _s, przed, po in zmiany:
            try:
                log(item_id, "UPDATE", "delivered_qty", przed, po)
            except Exception:
                pass                    # log nie może psuć zapisu
    return zmiany


def odswiez(con, project_id, numer_projektu, magazyn="MASTER",
            log=None, timeout=300):
    """Pobiera z Subiekta i zapisuje. Zwraca listę zmian (jak `zapisz`).

    Wyjątek mostu przepuszczamy w górę — wołający ma powiedzieć
    użytkownikowi, że dane są nieaktualne, zamiast po cichu pokazywać stare.
    """
    return zapisz(con, project_id,
                  wydane_z_subiekta(numer_projektu, magazyn, timeout), log)
