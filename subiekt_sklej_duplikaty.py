# -*- coding: utf-8 -*-
"""Sklejanie wierszy BOM-u o TYM SAMYM `subiekt_symbol`.

Po dowiązaniu w „Dopasowaniu kartotek" w arkuszu potrafią zostać dwa wiersze
wskazujące jedną kartotekę (2627: „12x14X10 SBT" 1+1 szt., „GN-614-5 NI"
2+2 szt.). Most ustawia ilość WPROST, więc druga pozycja NADPISUJE pierwszą
i na ZK ląduje mniejsza liczba.

Zasady (ustalenia użytkownika 15.09.2026): zostaje jedna pozycja, ilości się
sumują, reszta znika.

⚠️ CELOWO TYLKO JEDNA REGUŁA: identyczny `subiekt_symbol`. Nic nie zgadujemy
z nazwy, numeru rysunku ani mapowania — próba była i jest ODRZUCONA:

    „UCFL 201"  → kartoteka 100198
    „UCFL201"   → kartoteka 100532

To DWA różne towary w Subiekcie, a heurystyka po nazwie/numerze sklejała je
w jeden i zabierała sztuki z drugiego. Kod, który KASUJE wiersze BOM-u, nie
ma prawa zgadywać. Gdy dwa wiersze mają różny symbol — nie ruszamy ich,
choćby wyglądały identycznie. Poprawka należy wtedy do kartotek w Subiekcie
albo do dowiązania w „Dopasowaniu kartotek".

Grupowania po `id_subiekt` też NIE MA: 208 z 254 mapowań („założona") ma to
pole puste, więc reguła nie wyłapałaby ŻADNEJ pary (sprawdzone na 2627).
"""


def znajdz_duplikaty(con, project_id=None):
    """[{symbol, zostaje, do_usuniecia, suma}] — wiersze o tym samym symbolu.

    Zostaje pozycja o NAJNIŻSZYM `id`, czyli najstarsza. Przy identycznym
    symbolu wybór jest obojętny („gdy są równorzędne to obojętnie która”),
    a najniższe `id` daje wynik powtarzalny.
    """
    cols = {r[1] for r in con.execute("PRAGMA table_info(items)")}
    if "subiekt_symbol" not in cols:
        return []
    sql = ("SELECT id, TRIM(subiekt_symbol),"
           " COALESCE(NULLIF(TRIM(work_name), ''), src_name, ''),"
           " COALESCE(work_qty, src_qty, 0)"
           "  FROM items"
           " WHERE COALESCE(is_hidden, 0) = 0"
           "   AND COALESCE(TRIM(subiekt_symbol), '') <> ''")
    if project_id is not None and "project_id" in cols:
        sql += " AND project_id = %d" % int(project_id)

    grupy = {}
    for id_, symbol, nazwa, ilosc in con.execute(sql + " ORDER BY id"):
        w = {"id": id_, "symbol": symbol, "nazwa": nazwa,
             "ilosc": float(ilosc or 0)}
        grupy.setdefault(symbol.upper(), []).append(w)

    out = []
    for _, lista in sorted(grupy.items()):
        if len(lista) < 2:
            continue
        out.append({
            "symbol": lista[0]["symbol"],
            "zostaje": lista[0],
            "do_usuniecia": lista[1:],
            "suma": sum(w["ilosc"] for w in lista),
        })
    return out


def sklej(con, grupy):
    """Wykonuje sklejenie. Zwraca [(symbol, ile_usunieto, suma)] do raportu.

    Sumę wpisujemy w `work_qty` — kolumnę ROBOCZĄ. `src_qty` zostaje
    nietknięte jako ślad z importu BOM-u.

    ⚠️ ILOŚĆ BOM-u to COALESCE(work_qty, src_qty): wiersz z importu ma
    `work_qty` PUSTE i liczbę trzyma w `src_qty` (162/163 mają src_qty=1,
    work_qty=NULL). Sumowanie samego `work_qty` dawało zero.

    ⚠️ `order_qty` NIE JEST SUMOWANE, tylko CZYSZCZONE. To odbicie ilości
    z dokumentu, a oba wiersze pokazywały TĘ SAMĄ pozycję ZK — sumowanie
    dawało 4+4=8 i przesłaniało prawdziwą ilość BOM-u. Po wyczyszczeniu
    `read_project_items` (COALESCE(order_qty, work_qty, src_qty)) weźmie
    sumę, a most ustawi na ZK ilość policzoną z BOM-u.
    """
    raport = []
    for g in grupy or []:
        zostaje, usuwane = g["zostaje"], g["do_usuniecia"]
        if not usuwane:
            continue
        idy = ",".join(str(w["id"]) for w in [zostaje] + usuwane)
        suma = con.execute(
            "SELECT COALESCE(SUM(COALESCE(work_qty, src_qty, 0)), 0)"
            "  FROM items WHERE id IN (%s)" % idy).fetchone()[0]
        con.execute("UPDATE items SET work_qty = ?, order_qty = NULL"
                    " WHERE id = ?", (suma, zostaje["id"]))
        con.execute("DELETE FROM items WHERE id IN (%s)"
                    % ",".join(str(w["id"]) for w in usuwane))
        raport.append((g["symbol"], len(usuwane), suma))
    if raport:
        con.commit()
    return raport
