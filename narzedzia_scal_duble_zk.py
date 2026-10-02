# -*- coding: utf-8 -*-
"""Scalenie dubli z ZK z oryginalami. JEDNORAZOWE — pary wpisane na sztywno
(projekt 75, 02.10.2026). Przed uzyciem dla innego projektu popraw PARY.
SUCHY PRZEBIEG bez --zapisz."""
import os, sqlite3, sys, shutil
from datetime import datetime

PARY = [(2649, 2655, "HGH15SOK"), (2601, 2656, "HGW15SOK")]
zapisz = "--zapisz" in sys.argv
p = os.path.join(os.sep+os.sep+"W2019S", "RM_SERWER$", "RM_BAZA_projects", "project_75.sqlite")
con = sqlite3.connect(p); con.row_factory = sqlite3.Row

print("PLAN SCALENIA (projekt 75 / 2637):\n")
do_zrobienia = []
for zostaje, kasuj, symbol in PARY:
    o = con.execute("SELECT * FROM items WHERE id=?", (zostaje,)).fetchone()
    dub = con.execute("SELECT * FROM items WHERE id=?", (kasuj,)).fetchone()
    if not o or not dub:
        print("  POMIJAM %s/%s - brak wiersza" % (zostaje, kasuj)); continue
    print("  ZOSTAJE id=%-5s work=%-10s sym=%-10s -> sym BEDZIE %-10s"
          % (zostaje, o["work_drawing_no"], o["subiekt_symbol"], symbol))
    print("          opis=%r dostawca=%s zam=%s dost=%s"
          % ((o["src_desc"] or o["work_desc"] or "")[:26], o["supplier_id"],
             o["order_qty"], o["delivered_qty"]))
    print("  KASUJE  id=%-5s sym=%-10s zam=%s dost=%s notes=%r"
          % (kasuj, dub["subiekt_symbol"], dub["order_qty"],
             dub["delivered_qty"], dub["notes"]))
    if dub["delivered_qty"]:
        print("          !!! DUBEL MA DOSTARCZONO=%s - NIE KASUJE" % dub["delivered_qty"])
        continue
    print()
    do_zrobienia.append((zostaje, kasuj, symbol))

if zapisz and do_zrobienia:
    kop = p.replace(".sqlite", "_przed_scaleniem_%s.sqlite" % datetime.now().strftime("%Y%m%d_%H%M"))
    shutil.copy2(p, kop)
    print("Kopia zapasowa:", kop)
    for zostaje, kasuj, symbol in do_zrobienia:
        # OBA pola: widoczny numer rysunku I symbol Subiekta. Samo
        # `subiekt_symbol` zostawialo w arkuszu stara nazwe (02.10.2026).
        con.execute("UPDATE items SET work_drawing_no=?, subiekt_symbol=?,"
                    " updated_at=datetime('now') WHERE id=?", (symbol, symbol, zostaje))
        con.execute("DELETE FROM items WHERE id=?", (kasuj,))
    con.commit()
    print("ZROBIONE: %d par scalonych" % len(do_zrobienia))
elif do_zrobienia:
    print("To byl SUCHY PRZEBIEG. Zapis: dopisz --zapisz")
con.close()
