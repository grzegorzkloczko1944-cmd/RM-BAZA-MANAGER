# -*- coding: utf-8 -*-
"""Wiersze kupowanych półfabrykatów w BOM-ie projektu.

Półprodukt trafia na ZK (`subiekt_projekt.pozycje_polproduktow`), ale sam
rysunek go nie opisuje — w BOM-ie nie ma dla niego wiersza. Bez tego wiersza
logistyk widzi na zamówieniu towar, którego nie ma w arkuszu: nie ma gdzie
pokazać „Ilość (zam.)", nie ma do czego przypiąć „Ilości dostarczonych"
i odczyt wydań z Subiekta nie ma czego odświeżyć (14.09.2026).

⚠️ To jest pozycja SPOZA DRZEWKA — `is_manual=1`, jak wiersze dodawane
ręcznie i te ze schowka. Inventor jej nie zna, więc „Przelicz" korzeni jej
nie dotyka i nic się w drzewku nie rozjeżdża: ilość liczy się wyłącznie
z relacji (ilość detali × `ilosc_na_szt`).

Klucz i ilości liczy `subiekt_projekt.pozycje_polproduktow` — tutaj tylko
zapis do bazy projektu, tą samą drogą co `subiekt_schowek_bom`.
"""

from datetime import datetime


#: Ten sam warunek co przy ręcznym dodawaniu pozycji i w schowku: symbol
#: bywa numerem rysunku ALBO nazwą (pozycja znormalizowana), więc szukamy
#: w obu polach, po TRIM i wielkości liter.
SQL_SZUKAJ = """
    SELECT id FROM items
     WHERE project_id = ?
       AND (LOWER(TRIM(COALESCE(work_drawing_no, ''))) = LOWER(TRIM(?))
         OR LOWER(TRIM(COALESCE(src_drawing_no, ''))) = LOWER(TRIM(?))
         OR LOWER(TRIM(COALESCE(work_name, ''))) = LOWER(TRIM(?))
         OR LOWER(TRIM(COALESCE(src_name, ''))) = LOWER(TRIM(?)))
     LIMIT 1
"""

SQL_DODAJ = """
    INSERT INTO items (
        project_id, is_manual, is_hidden,
        src_drawing_no, src_name, src_qty,
        work_drawing_no, work_name, work_qty,
        order_qty, subiekt_symbol, notes, created_at, updated_at
    ) VALUES (?, 1, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def znajdz_w_bom(con, project_id, symbol, nazwa=None):
    """Wiersz tej kartoteki albo None.

    ⚠️ Szukamy po SYMBOLU (zapisanym w `subiekt_symbol`) ORAZ po nazwie:
    wiersz zakladamy z nazwa kartoteki w polu nazwy, wiec sam symbol
    nie wystarczy. Bez tego `zsynchronizuj` nie rozpoznawal wlasnego
    wiersza i przy kazdym wywolaniu dokladal duplikat (14.09.2026).
    """
    s = (symbol or "").strip()
    if not s:
        return None
    r = con.execute(
        "SELECT id FROM items WHERE project_id = ?"
        "   AND LOWER(TRIM(COALESCE(subiekt_symbol, ''))) = LOWER(TRIM(?))"
        " LIMIT 1", (project_id, s)).fetchone()
    if r:
        return r[0]
    n = (nazwa or "").strip() or s
    r = con.execute(SQL_SZUKAJ, (project_id, s, s, n, n)).fetchone()
    return r[0] if r else None


def _uwaga(z_rysunkow):
    """„półprodukt do: 2609-100.07 (3 szt.)" — skąd wzięła się ta ilość."""
    czesci = ["%s (%s szt.)" % (nr, _ilo(ile))
              for nr, ile in sorted((z_rysunkow or {}).items())]
    return "półprodukt do: " + ", ".join(czesci) if czesci else "półprodukt"


def _ilo(x):
    try:
        f = float(x)
        return str(int(f)) if f == int(f) else ("%.2f" % f).rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(x)


def zsynchronizuj(con, project_id, pozycje_polproduktow):
    """Dopisuje brakujące wiersze i odświeża ilości istniejących.

    `pozycje_polproduktow` — wynik `subiekt_projekt.pozycje_polproduktow()`.
    Zwraca (dodane, zaktualizowane) jako listy opisów do raportu — NIC PO
    CICHU: wołający pokazuje je użytkownikowi.

    ⚠️ Aktualizujemy TYLKO wiersze, które sami założyliśmy (`is_manual=1`
    i nasza notatka). Gdyby ten sam symbol był prawdziwą pozycją BOM-u,
    jego „Ilość (zam.)" jest czyimś zamówieniem — nadpisanie zafałszowałoby
    dane. Taki przypadek i tak nie powinien wystąpić, bo
    `pozycje_polproduktow` pomija kartoteki obecne w planie.
    """
    dodane, zmienione = [], []
    teraz = datetime.now().isoformat()

    for p in pozycje_polproduktow or []:
        symbol = (p.get("symbol") or "").strip()
        if not symbol:
            continue
        nazwa = (p.get("nazwa") or "").strip() or symbol
        ile = float(p.get("ilosc") or 0)
        if ile <= 0:
            continue
        uwaga = _uwaga(p.get("polprodukt_dla"))

        istnieje = znajdz_w_bom(con, project_id, symbol, nazwa)
        if istnieje is None:
            # Symbol kupowanej kartoteki NIE jest numerem rysunku — to towar
            # handlowy, jak łożysko. Idzie w nazwę, a numer zostaje pusty:
            # dokładnie tak, jak pozycje znormalizowane.
            con.execute(SQL_DODAJ, (project_id, "", nazwa, ile, "", nazwa,
                                    ile, ile, symbol, uwaga, teraz, teraz))
            dodane.append("%s — %s szt. (%s)" % (nazwa, _ilo(ile), uwaga))
            continue

        r = con.execute(
            "SELECT COALESCE(order_qty, 0), COALESCE(notes, ''), is_manual"
            "  FROM items WHERE id = ?", (istnieje,)).fetchone()
        if not r:
            continue
        stara, notes, manual = float(r[0] or 0), r[1] or "", r[2]
        if not (manual == 1 and notes.startswith("półprodukt")):
            continue                     # cudzy wiersz — nie dotykamy
        if abs(stara - ile) < 1e-9 and notes == uwaga:
            continue                     # bez zmian
        con.execute(
            "UPDATE items SET order_qty = ?, work_qty = ?, notes = ?,"
            "       updated_at = ? WHERE id = ?",
            (ile, ile, uwaga, teraz, istnieje))
        zmienione.append("%s — %s → %s szt." % (nazwa, _ilo(stara), _ilo(ile)))

    if dodane or zmienione:
        con.commit()
    return dodane, zmienione
