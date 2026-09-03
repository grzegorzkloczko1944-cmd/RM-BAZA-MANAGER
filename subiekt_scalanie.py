# -*- coding: utf-8 -*-
"""
Scalanie wariantów zapisu elementów handlowych w BOM-ach RM_BAZA.

Problem
───────
Detale własne mają numer rysunku — jednoznaczny klucz. Elementy handlowe
(łożyska, siłowniki, oringi) numeru nie mają: ich „nazwa" w BOM-ie to kod
katalogowy wpisywany ręcznie, więc ten sam element bywa zapisany różnie:

    'UCFL 201'   'UCFL-201'   'UCFL201'      ← jedno łożysko, 3 zapisy
    'KFL 001'    'KFL001'
    'EBP-L-335-8-C6'  'EBP-L.335-8-C6'  'EBP-L_335-8-C6'

Skutki sięgają dalej niż Subiekt: w arkuszu to trzy osobne pozycje, w RFQ
trzy zapytania, w Subiekcie trzy kartoteki z rozbitą historią cen i stanem
magazynowym w trzech miejscach.

Dlaczego zapis do BOM-u, a nie scalanie przy odczycie
──────────────────────────────────────────────────────
Scalanie „w locie" wymagałoby, żeby KAŻDE miejsce w RM_BAZA (arkusz, wycena,
RFQ, eksport do Subiekta) pamiętało o tej samej normalizacji — jedno
przeoczenie i znowu widać dwie pozycje. Zapis kanonicznego kodu do danych
daje jedną prawdę, o której reszta kodu nie musi wiedzieć.

Dlaczego mechanizm PROPONUJE, a nie decyduje
─────────────────────────────────────────────
Wybór „najczęstszy wariant wygrywa" trafia w 18 z 28 przypadków, ale:

  * 10 przypadków to REMIS (np. 'GN-614-5 NI' 2 proj. vs 'GN-614-5-NI'
    2 proj.) — częstotliwość nie rozstrzyga;
  * czasem większość jest zapisem GORSZYM: 'CFM-TR-G-B.60-SH-' (wiszący
    myślnik na końcu) wygrywa 4:1 z czystszym 'CFM-TR-G-B.60-SH'.

Dlatego `zaproponuj()` zwraca propozycję do zatwierdzenia, a `zastosuj()`
przyjmuje jawne decyzje. Bez backupu nie zapisuje.

Użycie
──────
    import subiekt_scalanie as S

    grupy = S.zaproponuj()                    # co i na co
    for g in grupy:
        print(g.kanoniczny, '<-', g.warianty)

    S.zastosuj(grupy, backup_dir=...)         # dopiero to zapisuje
"""

import os
import re
import shutil
import sqlite3
from datetime import datetime

from subiekt_stany import PROJECTS_DIR, looks_like_drawing_no

# Kolumny, w których siedzi nazwa/kod pozycji. Kolejność jak w reszcie
# integracji (work_ przed src_) — patrz subiekt_stany.read_project_drawings.
KOLUMNY_NAZW = ("work_name", "src_name")

_SEPARATORY = re.compile(r"[\s\-_./]+")


def norm_kod(s):
    """Kod sprowadzony do postaci porównywalnej — klucz grupowania wariantów."""
    return _SEPARATORY.sub("", (s or "").strip().upper())


class Grupa:
    """Jeden element handlowy i wszystkie jego zapisy w BOM-ach."""

    def __init__(self, klucz, warianty):
        self.klucz = klucz
        # {wariant: {"projekty": set(pid), "ile": int}}
        self.warianty = warianty
        self.kanoniczny = self._domyslny()

    def _domyslny(self):
        """Najczęstszy wariant (po liczbie projektów, potem wystąpień).

        Przy remisie wygrywa alfabetycznie pierwszy — arbitralne, ale
        powtarzalne; remisy i tak wymagają decyzji człowieka.
        """
        return sorted(
            self.warianty,
            key=lambda w: (-len(self.warianty[w]["projekty"]),
                           -self.warianty[w]["ile"], w),
        )[0]

    @property
    def remis(self):
        """Czy częstotliwość NIE rozstrzyga — wtedy wybór należy do człowieka."""
        licz = sorted((len(v["projekty"]) for v in self.warianty.values()), reverse=True)
        return len(licz) > 1 and licz[0] == licz[1]

    @property
    def do_zmiany(self):
        """Warianty, które zostaną zastąpione kanonicznym."""
        return [w for w in self.warianty if w != self.kanoniczny]

    @property
    def projekty(self):
        return sorted({p for v in self.warianty.values() for p in v["projekty"]})

    def __repr__(self):
        return f"<Grupa {self.kanoniczny!r} <- {self.do_zmiany}>"


# ── Zbieranie ───────────────────────────────────────────────────────────────
def _sciezka(pid):
    return os.path.join(PROJECTS_DIR, f"project_{pid}.sqlite")


def _kolumny(con):
    return {r[1] for r in con.execute("PRAGMA table_info('items')")}


def zbierz_warianty(project_ids=None):
    """{klucz: {wariant: {"projekty": set, "ile": int}}}"""
    if not os.path.isdir(PROJECTS_DIR):
        raise RuntimeError(f"Katalog projektów niedostępny: {PROJECTS_DIR}")

    wg = {}
    for fn in sorted(os.listdir(PROJECTS_DIR)):
        m = re.fullmatch(r"project_(\d+)\.sqlite", fn)
        if not m:
            continue
        pid = int(m.group(1))
        if project_ids and pid not in project_ids:
            continue
        try:
            con = sqlite3.connect(f"file:{os.path.join(PROJECTS_DIR, fn)}?mode=ro", uri=True)
        except sqlite3.DatabaseError:
            continue
        try:
            cols = _kolumny(con)
            name_cols = [c for c in KOLUMNY_NAZW if c in cols]
            if not name_cols:
                continue
            sel = ["work_drawing_no", "norm_drawing_no", "src_drawing_no"] + name_cols
            where = " WHERE COALESCE(is_hidden, 0) = 0" if "is_hidden" in cols else ""
            rows = con.execute(f"SELECT {', '.join(sel)} FROM items{where}").fetchall()
        except sqlite3.DatabaseError:
            continue
        finally:
            con.close()

        for r in rows:
            nr = next((v for v in r[0:3] if v not in (None, "") and str(v).strip()), None)
            # Ma numer rysunku → detal własny, ma swój klucz. Nie dotykamy.
            if nr is not None and looks_like_drawing_no(str(nr)):
                continue
            nazwa = next((v for v in r[3:] if v not in (None, "") and str(v).strip()), None)
            if not nazwa:
                continue
            nazwa = str(nazwa).strip()
            k = norm_kod(nazwa)
            if not k:
                continue
            w = wg.setdefault(k, {}).setdefault(nazwa, {"projekty": set(), "ile": 0})
            w["projekty"].add(pid)
            w["ile"] += 1
    return wg


def zaproponuj(project_ids=None):
    """[Grupa] — tylko kody zapisane na więcej niż jeden sposób."""
    wg = zbierz_warianty(project_ids)
    grupy = [Grupa(k, v) for k, v in wg.items() if len(v) > 1]
    # Najpierw te o największym zasięgu — tam scalenie daje najwięcej.
    grupy.sort(key=lambda g: (-len(g.projekty), g.kanoniczny))
    return grupy


# ── Zapis ───────────────────────────────────────────────────────────────────
def _backup(pid, backup_dir):
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cel = os.path.join(backup_dir, f"project_{pid}_{stamp}.sqlite")
    shutil.copy2(_sciezka(pid), cel)
    return cel


def zastosuj(grupy, backup_dir, tylko_probnie=False):
    """Zapisuje kanoniczny kod w miejsce wariantów. Zwraca raport.

    `backup_dir` jest WYMAGANY — każdy dotykany plik projektu jest najpierw
    kopiowany. To zmiana danych historycznych; bez kopii nie ma odwrotu.

    `tylko_probnie=True` liczy, co by się stało, i nic nie zapisuje.
    """
    if not backup_dir:
        raise ValueError("backup_dir jest wymagany — bez kopii nie zapisujemy.")

    # Które projekty w ogóle trzeba ruszyć i jakie podmiany je czekają.
    plan = {}
    for g in grupy:
        for wariant in g.do_zmiany:
            for pid in g.warianty[wariant]["projekty"]:
                plan.setdefault(pid, []).append((wariant, g.kanoniczny))

    raport = {"projekty": {}, "zmienionych": 0, "backupy": [], "probnie": tylko_probnie}

    for pid, podmiany in sorted(plan.items()):
        path = _sciezka(pid)
        if not os.path.isfile(path):
            raport["projekty"][pid] = {"blad": "brak pliku"}
            continue

        if not tylko_probnie:
            raport["backupy"].append(_backup(pid, backup_dir))

        tryb = "ro" if tylko_probnie else "rw"
        con = sqlite3.connect(f"file:{path}?mode={tryb}", uri=True)
        try:
            cols = _kolumny(con)
            name_cols = [c for c in KOLUMNY_NAZW if c in cols]
            ile_pid = 0
            szczegoly = []
            for stary, nowy in podmiany:
                for col in name_cols:
                    # TRIM w warunku, bo warianty bywają z białymi znakami
                    # na końcu ('8025354 ' — plan, sekcja 12.2).
                    q = f"SELECT COUNT(*) FROM items WHERE TRIM({col}) = ?"
                    n = con.execute(q, (stary,)).fetchone()[0]
                    if not n:
                        continue
                    if not tylko_probnie:
                        con.execute(
                            f"UPDATE items SET {col} = ? WHERE TRIM({col}) = ?",
                            (nowy, stary))
                    ile_pid += n
                    szczegoly.append((col, stary, nowy, n))
            if not tylko_probnie:
                con.commit()
            raport["projekty"][pid] = {"zmienionych": ile_pid, "szczegoly": szczegoly}
            raport["zmienionych"] += ile_pid
        finally:
            con.close()

    return raport


def sformatuj_propozycje(grupy):
    L = ["=" * 78,
         "SCALANIE ELEMENTÓW HANDLOWYCH — propozycja",
         "=" * 78, ""]
    if not grupy:
        L.append("Brak wariantów do scalenia. Zapis kodów jest spójny.")
        return "\n".join(L)

    remisy = [g for g in grupy if g.remis]
    L.append(f"Grup do scalenia: {len(grupy)}")
    L.append(f"  w tym wymagających decyzji (remis): {len(remisy)}")
    L.append("")
    L.append("Kanoniczny = wariant proponowany do zostawienia.")
    L.append("Przy remisie częstotliwość nie rozstrzyga — sprawdź ręcznie.")
    L.append("")
    for g in grupy:
        znak = "  ⚠ REMIS" if g.remis else ""
        L.append("-" * 78)
        L.append(f"  ZOSTAJE:  {g.kanoniczny!r}{znak}")
        for w in sorted(g.do_zmiany):
            v = g.warianty[w]
            L.append(f"  zmienić:  {w!r}   (projekty: {sorted(v['projekty'])}, wystąpień: {v['ile']})")
    L.append("-" * 78)
    return "\n".join(L)
