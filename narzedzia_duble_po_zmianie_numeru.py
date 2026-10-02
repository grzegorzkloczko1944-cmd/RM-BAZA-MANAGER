# -*- coding: utf-8 -*-
"""Duble po zmianie numeru rysunku - raport i (opcjonalnie) kasowanie.

SUCHY PRZEBIEG domyslnie. Kasuje dopiero z --zapisz.
Para to: wiersz STARY (ma work_drawing_no != src_drawing_no) i wiersz NOWY
dopisany przez aktualizacje BOM pod SRC-owym numerem tego pierwszego.
"""
import os, sqlite3, sys

#   python narzedzia_duble_po_zmianie_numeru.py 75            (suchy przebieg)
#   python narzedzia_duble_po_zmianie_numeru.py 75 --zapisz   (kasuje duble)
#
# ⚠️ Dziala na bazie NA SERWERZE. Gdy projekt jest przejety lockiem, zmiany
# siedza w kopii lokalnej i tu ich jeszcze NIE WIDAC — najpierw zwolnij lock.
args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args:
    print("Podaj numer projektu, np.: %s 75" % os.path.basename(sys.argv[0]))
    raise SystemExit(1)
PID = int(args[0])
p = os.path.join(os.sep + os.sep + "W2019S", "RM_SERWER$",
                 "RM_BAZA_projects", "project_%d.sqlite" % PID)
if not os.path.isfile(p):
    print("Brak bazy projektu: %s" % p)
    raise SystemExit(1)
zapisz = "--zapisz" in sys.argv

con = sqlite3.connect(p)
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT id, src_drawing_no, work_drawing_no, subiekt_symbol, src_qty,"
    "       order_qty, delivered_qty, src_name, work_name, src_row, notes"
    "  FROM items WHERE project_id = ?", (PID,)).fetchall()

def stara_nazwa(r):
    """Nazwa SPRZED recznej edycji — z pliku BOM albo z kartoteki Subiekta.

    Pozycje dopisane wprost z kartoteki (wozki Hiwin, lozyska, pasy) maja
    `src_drawing_no` PUSTE i wtedy jedynym sladem jest `subiekt_symbol`.
    """
    for kand in (r["src_drawing_no"], r["subiekt_symbol"]):
        k = (kand or "").strip()
        if k:
            return k
    return "" 

def efekt(r):
    return ((r["work_drawing_no"] or r["src_drawing_no"] or "").strip())

wg_nazwy = {}
for r in rows:
    wg_nazwy.setdefault(efekt(r).upper(), []).append(r)

print("Pozycji w projekcie %d: %d\n" % (PID, len(rows)))
kandydaci = []
for r in rows:
    work = (r["work_drawing_no"] or "").strip()
    src = stara_nazwa(r)
    if not work or not src or work.upper() == src.upper():
        continue
    # user zmienil nazwe; czy pod STARA nazwa dopisal sie nowy wiersz?
    for inny in wg_nazwy.get(src.upper(), []):
        if inny["id"] == r["id"]:
            continue
        kandydaci.append((r, inny))

if not kandydaci:
    print("Nie znaleziono dubli po zmianie numeru rysunku.")
else:
    print("ZNALEZIONE PARY (zostaje TWOJ wiersz, do kasacji dubel z pliku):\n")
    for stary, dubel in kandydaci:
        print("  ZOSTAJE id=%-5s %-14s (stara=%-12s) qty=%-4s zam=%-5s dost=%-5s %r"
              % (stary["id"], efekt(stary), stara_nazwa(stary),
                 stary["src_qty"], stary["order_qty"], stary["delivered_qty"],
                 (stary["work_name"] or stary["src_name"] or "")[:22]))
        print("  KASUJE id=%-5s %-14s (stara=%-12s) qty=%-4s zam=%-5s dost=%-5s %r"
              % (dubel["id"], efekt(dubel), stara_nazwa(dubel),
                 dubel["src_qty"], dubel["order_qty"], dubel["delivered_qty"],
                 (dubel["work_name"] or dubel["src_name"] or "")[:22]))
        ostrzez = []
        if dubel["delivered_qty"]:
            ostrzez.append("ma DOSTARCZONO=%s" % dubel["delivered_qty"])
        if dubel["order_qty"]:
            ostrzez.append("ma ZAMOWIONO=%s" % dubel["order_qty"])
        if dubel["notes"]:
            ostrzez.append("ma UWAGI")
        print("     %s\n" % ("UWAGA: dubel " + ", ".join(ostrzez)
                             if ostrzez else "dubel pusty - bezpieczny do kasacji"))

if zapisz and kandydaci:
    ids = [d["id"] for _s, d in kandydaci]
    con.executemany("DELETE FROM items WHERE id = ?", [(i,) for i in ids])
    con.commit()
    print("USUNIETO %d wierszy: %s" % (len(ids), ids))
elif kandydaci:
    print("To byl SUCHY PRZEBIEG. Kasowanie: dopisz --zapisz")
con.close()
