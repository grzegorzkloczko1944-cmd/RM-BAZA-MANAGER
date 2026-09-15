# -*- coding: utf-8 -*-
"""Dopisywanie półproduktu na ZK WSZYSTKICH aktywnych projektów.

Relacja „rysunek → półprodukt" jest globalna, więc dotyczy każdego projektu,
w którym ten rysunek występuje. Bez tego modułu trzeba było otwierać
Projekt/Aktualizacja osobno dla każdego z nich — przy sześciu projektach
z tym samym kołem to sześć przebiegów ręcznie (zgłoszone 15.09.2026).

⚠️ PISZEMY DO ZK TAKŻE WTEDY, GDY KTOŚ TRZYMA LOCK na projekcie (decyzja
użytkownika): ZK żyje w Subiekcie, nie w bazie projektu, a arkusz zaciągnie
pozycję sam przy najbliższym przejęciu locka (`_dopisz_pozycje_z_zk`).
Lock chroni bazę projektu, nie dokument zamówienia.

Kolejność jest ta sama, co przy zwykłym zapisie projektu:
    relacja → plan ograniczony do półproduktów → most (tryb „projekt")
Most sam decyduje, czy dopisać pozycję, czy podnieść ilość istniejącej.
"""

import os
import sqlite3


def projekty_z_rysunkiem(numer_rysunku, tylko_aktywne=True):
    """[(project_id, nazwa, ilosc)] — gdzie ten rysunek jest w BOM-ie.

    Czyta bazy projektów po kolei: numer rysunku nie jest w masterze, tylko
    w `items` każdego projektu. Przy ~60 projektach to ~60 otwarć pliku
    read-only — akceptowalne, bo wołane raz, po kliknięciu użytkownika.

    Pomija projekty bez pliku bazy (np. WAREHOUSE bez BOM-u) i ukryte
    pozycje — tak samo jak reszta integracji.
    """
    nr = (numer_rysunku or "").strip().upper()
    if not nr:
        return []
    try:
        import rm_klient
        import subiekt_stany
    except Exception:
        return []

    out = []
    for w in rm_klient.master_read("projekty-do-selektora"):
        if tylko_aktywne and not w.get("active"):
            continue
        if (w.get("project_type") or "MACHINE") != "MACHINE":
            continue
        pid = w["project_id"]
        sciezka = os.path.join(subiekt_stany.PROJECTS_DIR,
                               "project_%s.sqlite" % pid)
        if not os.path.isfile(sciezka):
            continue
        try:
            con = sqlite3.connect("file:%s?mode=ro" % sciezka, uri=True)
            r = con.execute(
                "SELECT COALESCE(order_qty, work_qty, src_qty) FROM items"
                " WHERE UPPER(COALESCE(work_drawing_no, src_drawing_no)) = ?"
                "   AND COALESCE(is_hidden, 0) = 0 LIMIT 1", (nr,)).fetchone()
            con.close()
        except Exception:
            continue
        if r:
            out.append((pid, w["name"], float(r[0] or 0)))
    return out


def plan_polproduktow(project_id, nazwa_projektu, podmiot=""):
    """Plan dla mostu ograniczony do POZYCJI PÓŁPRODUKTÓW tego projektu.

    Zwraca (plan, pozycje) albo (None, []) — gdy projekt nie ma czego dopisać.
    Ilości liczy `subiekt_projekt.pozycje_polproduktow`, czyli tak samo jak
    przy zwykłym zapisie: ilość detali × ilość na sztukę, sumowane po
    kartotece.
    """
    import subiekt_projekt as PR
    plan = PR.build_plan(project_id, nazwa_projektu, podmiot or "",
                         nazwa_projektu)[0]
    pozycje = [p for p in plan["pozycje"] if p.get("polprodukt_dla")]
    if not pozycje:
        return None, []
    mini = dict(plan)
    mini["pozycje"] = pozycje
    return mini, pozycje


def rozeslij(numer_rysunku, podmiot="", pomin_projekt=None, zapisz=True):
    """Dopisuje półprodukty rysunku na ZK wszystkich aktywnych projektów.

    Zwraca [(project_id, nazwa, opis_wyniku, blad)] — po jednym wierszu na
    projekt, do pokazania użytkownikowi (zasada „nic po cichu”).

    `pomin_projekt` — bieżący projekt, gdy zapisał się już inną drogą.
    `zapisz=False` — suchy przebieg, do podglądu przed decyzją.
    """
    import subiekt_projekt as PR

    wynik = []
    for pid, nazwa, _ile in projekty_z_rysunkiem(numer_rysunku):
        if pomin_projekt is not None and pid == pomin_projekt:
            continue
        try:
            plan, pozycje = plan_polproduktow(pid, nazwa, podmiot)
        except Exception as e:
            wynik.append((pid, nazwa, None, "nie zbudowano planu: %s" % e))
            continue
        if not plan:
            wynik.append((pid, nazwa, "brak półproduktów w planie", None))
            continue
        try:
            odp = PR.run_bridge(plan, zapisz=zapisz)
        except Exception as e:
            wynik.append((pid, nazwa, None, str(e)))
            continue
        blad = (odp or {}).get("blad")
        if blad:
            wynik.append((pid, nazwa, None, str(blad)))
            continue
        # Co most naprawdę zrobił — kroki `zk` i `zk-poz`.
        opisy = [k.get("Szczegoly") or k.get("Status")
                 for k in (odp.get("kroki") or [])
                 if k.get("Rodzaj") == "zk"]
        wynik.append((pid, nazwa,
                      "; ".join(o for o in opisy if o) or "bez zmian", None))
    return wynik
