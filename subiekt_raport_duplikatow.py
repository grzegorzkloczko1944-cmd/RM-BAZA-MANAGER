# -*- coding: utf-8 -*-
"""
Raport: elementy handlowe zapisane w BOM-ach na kilka sposobów.

Problem
───────
Detale własne mają numer rysunku (`2627-100.01`) — jednoznaczny klucz.
Elementy handlowe (łożyska, siłowniki, kołki, oringi) numeru NIE mają:
ich „nazwa" w BOM-ie to kod katalogowy producenta. A ten sam kod bywa
wpisany różnie, zależnie od tego kto i kiedy go wpisywał:

    'UCFL 201'   'UCFL-201'   'UCFL201'          ← to samo łożysko
    'KFL 001'    'KFL001'
    'Oring 16x3' 'oring_16x3'
    'EBP-L-335-8-C6'  'EBP-L.335-8-C6'  'EBP-L_335-8-C6'

Każdy wariant to w Subiekcie OSOBNA kartoteka — rozbita historia cen,
stan magazynowy w kilku miejscach, a przy zamawianiu łatwo o pomyłkę.

Dlaczego raport, a nie automat
──────────────────────────────
Bo naprawa należy do danych źródłowych (BOM), nie do integracji. Gdyby
scalać dopiero przy wysyłce do Subiekta, RM_BAZA nadal pokazywałaby
warianty jako różne pozycje — w wycenach, w RFQ, w arkuszu.

Dobór klucza: warianty różnią się WYŁĄCZNIE separatorami i wielkością
liter, więc normalizacja rozstrzyga je pewnie. Świadomie NIE ma tu
dopasowania rozmytego (fuzzy) — pomiar na projekcie 2627 pokazał, że przy
nazwach detali daje 389 fałszywych par ('Płyta zewnętrzna' vs 'wewnętrzna'
= 0.93), więc do kojarzenia pozycji się nie nadaje.

To narzędzie TYLKO CZYTA bazy projektów. Nie łączy się z Subiektem.

Użycie
──────
    python subiekt_raport_duplikatow.py                    # wszystkie projekty
    python subiekt_raport_duplikatow.py 52 71              # wybrane projekty
    python subiekt_raport_duplikatow.py --out=raport.txt   # do pliku
"""

import os
import re
import sqlite3
import sys

from subiekt_stany import PROJECTS_DIR, looks_like_drawing_no


# Separatory i wielkość liter to jedyne, co odróżnia warianty tego samego
# kodu ('UCFL 201' / 'UCFL-201' / 'UCFL201'). Kropka też bywa separatorem
# ('EBP-L.335' vs 'EBP-L_335'), więc wchodzi do zbioru.
_SEPARATORY = re.compile(r"[\s\-_./]+")


def norm_kod(s):
    """Kod katalogowy sprowadzony do postaci porównywalnej."""
    return _SEPARATORY.sub("", (s or "").strip().upper())


def kody_z_projektu(path):
    """[(kod, nazwa_dostawcy)] — pozycje BEZ numeru rysunku, czyli handlowe."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.DatabaseError:
        return []
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info('items')")}
        if not cols:
            return []
        name_cols = [c for c in ("work_name", "src_name") if c in cols]
        if not name_cols:
            return []
        extra = [c for c in ("src_supplier_text",) if c in cols]
        sel = ["work_drawing_no", "norm_drawing_no", "src_drawing_no"] + name_cols + extra
        where = " WHERE COALESCE(is_hidden, 0) = 0" if "is_hidden" in cols else ""
        rows = con.execute(f"SELECT {', '.join(sel)} FROM items{where}").fetchall()
    except sqlite3.DatabaseError:
        return []
    finally:
        con.close()

    n0 = 3
    n1 = n0 + len(name_cols)
    out = []
    for r in rows:
        nr = next((v for v in r[0:3] if v not in (None, "") and str(v).strip()), None)
        # Pozycja z numerem rysunku to detal własny — ma swój klucz, pomijamy.
        if nr is not None and looks_like_drawing_no(str(nr)):
            continue
        nazwa = next((v for v in r[n0:n1] if v not in (None, "") and str(v).strip()), None)
        if not nazwa:
            continue
        dost = next((v for v in r[n1:] if v not in (None, "") and str(v).strip()), "")
        out.append((str(nazwa).strip(), str(dost).strip()))
    return out


def zbierz(project_ids=None):
    """{klucz: {wariant: {"projekty": set, "ile": int, "dostawcy": set}}}"""
    if not os.path.isdir(PROJECTS_DIR):
        raise RuntimeError(f"Katalog projektów niedostępny: {PROJECTS_DIR}")

    wg_klucza = {}
    zbadane = 0
    for fn in sorted(os.listdir(PROJECTS_DIR)):
        m = re.fullmatch(r"project_(\d+)\.sqlite", fn)
        if not m:
            continue
        pid = int(m.group(1))
        if project_ids and pid not in project_ids:
            continue
        zbadane += 1
        for kod, dostawca in kody_z_projektu(os.path.join(PROJECTS_DIR, fn)):
            k = norm_kod(kod)
            if not k:
                continue
            war = wg_klucza.setdefault(k, {}).setdefault(
                kod, {"projekty": set(), "ile": 0, "dostawcy": set()})
            war["projekty"].add(pid)
            war["ile"] += 1
            if dostawca:
                war["dostawcy"].add(dostawca)
    return wg_klucza, zbadane


def sformatuj(wg_klucza, zbadane):
    # Interesują nas tylko klucze zapisane na więcej niż jeden sposób.
    kolizje = {k: v for k, v in wg_klucza.items() if len(v) > 1}

    L = []
    L.append("=" * 78)
    L.append("ELEMENTY HANDLOWE ZAPISANE NA KILKA SPOSOBÓW")
    L.append("=" * 78)
    L.append("")
    L.append(f"Projektów przejrzanych:            {zbadane}")
    L.append(f"Unikalnych kodów (po normalizacji): {len(wg_klucza)}")
    L.append(f"Kodów z rozbieżnym zapisem:        {len(kolizje)}")
    L.append("")
    if not kolizje:
        L.append("Nie znaleziono rozbieżności. Zapis kodów jest spójny.")
        L.append("=" * 78)
        return "\n".join(L)

    L.append("Każda grupa poniżej to JEDEN element zapisany różnie.")
    L.append("Warianty różnią się tylko separatorami/wielkością liter.")
    L.append("Wybierz jeden zapis i ujednolić go w BOM-ach wskazanych projektów.")
    L.append("")

    # Najpierw te w największej liczbie projektów — tam poprawka daje najwięcej.
    def zasieg(v):
        return len({p for w in v.values() for p in w["projekty"]})

    for k in sorted(kolizje, key=lambda k: (-zasieg(kolizje[k]), k)):
        warianty = kolizje[k]
        L.append("─" * 78)
        L.append(f"  {len(warianty)} warianty:")
        for kod in sorted(warianty):
            w = warianty[kod]
            pids = ", ".join(str(p) for p in sorted(w["projekty"]))
            linia = f"      {kod!r:<52} projekty: {pids}"
            if w["ile"] > len(w["projekty"]):
                linia += f"  (wystąpień: {w['ile']})"
            L.append(linia)
            for d in sorted(w["dostawcy"]):
                L.append(f"          dostawca: {d}")
    L.append("─" * 78)
    L.append("")
    L.append("Nic nie zostało zmienione — to tylko odczyt.")
    L.append("=" * 78)
    return "\n".join(L)


def main(argv):
    ids = {int(a) for a in argv if a.isdigit()} or None
    out = next((a[len("--out="):] for a in argv if a.startswith("--out=")), None)

    wg_klucza, zbadane = zbierz(ids)
    tekst = sformatuj(wg_klucza, zbadane)

    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(tekst)
        print(f"Zapisano: {out}")
        return 0

    # Konsola Windows to zwykle cp1250 — ramki i część znaków z nazw nie mają
    # w niej odpowiednika i print() wywala się na UnicodeEncodeError. Wypis
    # ma pokazać dane, nie ozdobniki, więc zastępujemy to, czego terminal
    # nie zniesie (do pliku idzie pełny UTF-8, bez okrojeń).
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        print(tekst)
    except UnicodeEncodeError:
        print(tekst.encode(enc, errors="replace").decode(enc, errors="replace"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
