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

Zasięg: podpowiedzi z całej bazy, zapis TYLKO w bieżącym projekcie
──────────────────────────────────────────────────────────────────
Warianty zbierane są ze **wszystkich** projektów — bo to one mówią, który
zapis jest w firmie przyjęty ('UCFL 201' w 13 projektach vs 'UCFL201'
w 6). Ale zmieniany jest **wyłącznie projekt, nad którym user pracuje**.

Powód: masowa podmiana w 22 projektach naraz dotyka danych, których nikt
w tym momencie nie ogląda — błędny wybór wyszedłby na jaw za pół roku,
w projekcie, którego nikt nie łączył z tą decyzją. Scalanie „to, co mam
przed oczami" trzyma skutek tam, gdzie jest uwaga użytkownika.

Dlaczego mechanizm PROPONUJE, a nie decyduje
─────────────────────────────────────────────
Wybór „najczęstszy wariant wygrywa" trafia w 18 z 28 przypadków, ale:

  * 10 przypadków to REMIS (np. 'GN-614-5 NI' 2 proj. vs 'GN-614-5-NI'
    2 proj.) — częstotliwość nie rozstrzyga;
  * czasem większość jest zapisem GORSZYM: 'CFM-TR-G-B.60-SH-' (wiszący
    myślnik na końcu) wygrywa 4:1 z czystszym 'CFM-TR-G-B.60-SH'.

Dlatego `zaproponuj_dla_projektu()` zwraca propozycję do zatwierdzenia,
a `zastosuj()` przyjmuje jawne decyzje. Bez backupu nie zapisuje.

Co dalej — dopasowanie do Subiekta
───────────────────────────────────
Scalony kod idzie do `znajdz_w_subiekcie()`, które szuka kartoteki po tej
samej znormalizowanej postaci (symbol ALBO nazwa). Ta sama zasada na obu
etapach: 'UCFL 201' w BOM i 'UCFL201' w Subiekcie to jeden element.
Świadomie BEZ dopasowania rozmytego — pomiar (plan, „Krok 2b") pokazał,
że przy nazwach daje fałszywe trafienia, których próg nie odsiewa.

Użycie
──────
    import subiekt_scalanie as S

    grupy = S.zaproponuj_dla_projektu(52)     # co jest do scalenia TU
    for g in grupy:
        print(g.kanoniczny, '<-', g.do_zmiany)

    S.zastosuj(grupy, project_id=52, backup_dir=...)   # dopiero to zapisuje

    kat = S.wczytaj_katalog_subiekta()        # raz
    S.znajdz_w_subiekcie('UCFL 201', kat)     # -> kartoteka albo None
"""

import json
import os
import re
import shutil
import sqlite3
import time
from datetime import datetime

from subiekt_stany import PROJECTS_DIR, looks_like_drawing_no

# Kolumny, w których siedzi nazwa/kod pozycji. Kolejność jak w reszcie
# integracji (work_ przed src_) — patrz subiekt_stany.read_project_drawings.
KOLUMNY_NAZW = ("work_name", "src_name")
#: Numer rysunku, w tej samej kolejnosci waznosci co nazwy: roboczy przed
#: importowym. Dwa wiersze o TYM SAMYM numerze to duplikat nawet wtedy, gdy
#: nazwy sie roznia — arkusz sygnalizuje to czerwonym paskiem „DUPLIKATY
#: NUMEROW RYSUNKOW", a okno scalania dlugo tego nie widzialo (25.09.2026).
KOLUMNY_RYSUNKU = ("work_drawing_no", "src_drawing_no")
#: Opis pozycji — kolejnosc jak wyzej: roboczy przed importowym. Okno
#: scalania pokazuje go obok nazwy, tak jak arkusz RM_BAZA (25.09.2026).
KOLUMNY_OPISU = ("work_desc", "src_desc")

_SEPARATORY = re.compile(r"[\s\-_./]+")


def norm_kod(s):
    """Kod sprowadzony do postaci porównywalnej — klucz grupowania wariantów."""
    return _SEPARATORY.sub("", (s or "").strip().upper())


class Grupa:
    """Jeden element handlowy i jego zapisy — w tym projekcie i w całej bazie.

    `w_projekcie` to warianty obecne w BOM-ie, nad którym user pracuje —
    tylko one będą zmieniane. `warianty` obejmuje całą bazę i służy do
    podpowiedzi, który zapis jest w firmie przyjęty.
    """

    def __init__(self, klucz, warianty, w_projekcie):
        self.klucz = klucz
        # {wariant: {"projekty": set(pid), "ile": int}} — cała baza
        self.warianty = warianty
        # {wariant: ile wystąpień} — tylko bieżący projekt
        self.w_projekcie = w_projekcie
        # Docelowy zapis. Domyślnie najczęstszy wariant, ale user może wpisać
        # WŁASNY — czasem żaden istniejący nie jest dobry ('Nakrętka TR16x4..'
        # z kropkami, 'CFM-TR-G-B.60-SH-' z wiszącym myślnikiem).
        self.kanoniczny = self._domyslny()

    @property
    def wlasny(self):
        """Czy docelowy zapis został wpisany ręcznie, a nie wybrany z listy."""
        return self.kanoniczny not in self.warianty

    def _domyslny(self):
        """Najczęstszy wariant w CAŁEJ bazie (po projektach, potem wystąpieniach).

        Liczy się cała baza, nie sam projekt — chodzi o to, jak firma
        zapisuje ten kod na co dzień, a nie jak akurat wyszło tutaj.
        Przy remisie wygrywa alfabetycznie pierwszy: arbitralne, ale
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
        """Warianty z BIEŻĄCEGO projektu, które zostaną zastąpione kanonicznym."""
        return [w for w in self.w_projekcie if w != self.kanoniczny]

    @property
    def wystapien_do_zmiany(self):
        return sum(self.w_projekcie[w] for w in self.do_zmiany)

    @property
    def projekty(self):
        """Wszystkie projekty, w których ten kod występuje (kontekst, nie zasięg zmiany)."""
        return sorted({p for v in self.warianty.values() for p in v["projekty"]})

    def __repr__(self):
        return f"<Grupa {self.kanoniczny!r} <- {self.do_zmiany}>"


# ── Zbieranie ───────────────────────────────────────────────────────────────
def _sciezka(pid):
    return os.path.join(PROJECTS_DIR, f"project_{pid}.sqlite")


def _kolumny(con):
    return {r[1] for r in con.execute("PRAGMA table_info('items')")}


def _nazwy_handlowe(con):
    """[nazwa] — pozycje BEZ numeru rysunku z jednego połączenia do bazy projektu."""
    cols = _kolumny(con)
    name_cols = [c for c in KOLUMNY_NAZW if c in cols]
    if not name_cols:
        return []
    # KLASA rozstrzyga, co jest handlowe — nie ksztalt numeru (25.09.2026).
    # `looks_like_drawing_no` uznawala za „numer rysunku" kazdy tekst
    # z cyfra i bez spacji. Po przypisaniu kartoteki w RM_BAZA symbol
    # Subiekta laduje w work_drawing_no — normalia „6004ZZ" czy „UCFL201"
    # (bez spacji) wygladala wtedy na detal i ZNIKALA z tego okna; „6004 ZZ"
    # (ze spacja) zostawala tylko przypadkiem. Spacje w symbolach sa
    # dozwolone (pamiec/project_symbole_ze_spacja), wiec test tekstu jest
    # bezuzyteczny. Klasa z importu (ZNORMALIZOWANE / STANDARD / X / Z…)
    # jest jednoznaczna; stary test zostaje TYLKO dla baz bez kolumn klasy.
    ma_klase = "class_auto" in cols
    sel = ["work_drawing_no", "norm_drawing_no", "src_drawing_no"] + name_cols
    if ma_klase:
        sel.append("COALESCE(class_manual, class_auto)")
    where = " WHERE COALESCE(is_hidden, 0) = 0" if "is_hidden" in cols else ""
    wiersze = [tuple(r) for r in con.execute(f"SELECT {', '.join(sel)} FROM items{where}")]

    def _detal(r):
        """Czy wiersz to detal wlasny (ma swoj klucz, nie jest handlowy)."""
        if ma_klase:
            return (r[-1] or "").strip().upper() != "ZNORMALIZOWANE"
        nr = next((v for v in r[0:3] if v not in (None, "") and str(v).strip()), None)
        return nr is not None and looks_like_drawing_no(str(nr))

    # ── WYJATEK: numer rysunku POWTORZONY (25.09.2026) ───────────────────────
    #
    # Regula nizej odsiewa wiersze z numerem rysunku — to detale wlasne, maja
    # swoj klucz i nie sa „kodami handlowymi". Ale element handlowy tez bywa
    # opisany numerem: 2637 Feniks ma dwa wiersze `HGH15SO` (szyna liniowa)
    # o roznych nazwach — „HGH15CA" i „HGH15CA Z0". Arkusz krzyczal o nich
    # czerwonym paskiem „DUPLIKATY NUMEROW RYSUNKOW", a tutaj nie wchodzily
    # w ogole, wiec nie bylo czego zaznaczyc ani scalic.
    #
    # Wpuszczamy WYLACZNIE numery wystepujace WIECEJ NIZ RAZ. Detal wlasny
    # z unikalnym numerem zostaje poza oknem, dokladnie jak dotad.
    ile_rysunkow = {}
    for r in wiersze:
        nr = next((v for v in r[0:3] if v not in (None, "") and str(v).strip()), None)
        if nr is not None and _detal(r):
            k = str(nr).strip().upper()
            ile_rysunkow[k] = ile_rysunkow.get(k, 0) + 1
    powtorzone = {k for k, n in ile_rysunkow.items() if n > 1}

    n_nazw = len(name_cols)
    out = []
    for r in wiersze:
        nr = next((v for v in r[0:3] if v not in (None, "") and str(v).strip()), None)
        # Detal wlasny ma swoj klucz — nie dotykamy, chyba ze jego numer
        # stoi w kilku wierszach (patrz wyzej).
        if _detal(r):
            if nr is None or str(nr).strip().upper() not in powtorzone:
                continue
        nazwa = next((v for v in r[3:3 + n_nazw] if v not in (None, "") and str(v).strip()), None)
        if nazwa:
            out.append(str(nazwa).strip())
    return out


def zbierz_warianty(project_ids=None, biezacy=None):
    """{klucz: {wariant: {"projekty": set, "ile": int}}}

    `biezacy` = (project_id, con): ten jeden projekt czytany jest z podanego
    połączenia zamiast z pliku na serwerze. Konieczne przy locku — arkusz
    RM_BAZA pracuje wtedy na LOKALNEJ kopii (db_manager.open_project_local)
    i to ona jest aktualna; plik zdalny zostanie nadpisany dopiero przy
    zwolnieniu locka.
    """
    if not os.path.isdir(PROJECTS_DIR):
        raise RuntimeError(f"Katalog projektów niedostępny: {PROJECTS_DIR}")
    biezacy_id, biezacy_con = biezacy if biezacy else (None, None)

    wg = {}

    def dodaj(pid, nazwy):
        for nazwa in nazwy:
            k = norm_kod(nazwa)
            if not k:
                continue
            w = wg.setdefault(k, {}).setdefault(nazwa, {"projekty": set(), "ile": 0})
            w["projekty"].add(pid)
            w["ile"] += 1

    for fn in sorted(os.listdir(PROJECTS_DIR)):
        m = re.fullmatch(r"project_(\d+)\.sqlite", fn)
        if not m:
            continue
        pid = int(m.group(1))
        if project_ids and pid not in project_ids:
            continue
        if pid == biezacy_id:
            continue          # ten czytamy z żywego połączenia, niżej
        try:
            con = sqlite3.connect(f"file:{os.path.join(PROJECTS_DIR, fn)}?mode=ro", uri=True)
        except sqlite3.DatabaseError:
            continue
        try:
            nazwy = _nazwy_handlowe(con)
        except sqlite3.DatabaseError:
            continue
        finally:
            con.close()
        dodaj(pid, nazwy)

    if biezacy_con is not None and (not project_ids or biezacy_id in project_ids):
        dodaj(biezacy_id, _nazwy_handlowe(biezacy_con))
    return wg


def zaproponuj_dla_projektu(project_id):
    """[Grupa] — co da się scalić W TYM projekcie, z podpowiedzią z całej bazy.

    Zwraca grupy, w których bieżący projekt ma zapis INNY niż kanoniczny
    (przyjęty w firmie). Obejmuje więc dwa przypadki:

      * projekt ma kilka wariantów tego samego kodu u siebie,
      * projekt ma jeden wariant, ale odbiegający od reszty bazy.

    Ten drugi jest równie ważny — to on tworzy duplikat w Subiekcie, mimo
    że wewnątrz projektu nic nie wygląda podejrzanie.
    """
    cala_baza = zbierz_warianty()          # kontekst: jak firma to zapisuje
    tylko_ten = zbierz_warianty({project_id})

    grupy = []
    for klucz, w_projekcie_pelne in tylko_ten.items():
        warianty = cala_baza.get(klucz, w_projekcie_pelne)
        w_projekcie = {w: v["ile"] for w, v in w_projekcie_pelne.items()}
        g = Grupa(klucz, warianty, w_projekcie)
        if g.do_zmiany:                    # nic do roboty, jeśli już kanoniczny
            grupy.append(g)

    # Najpierw te o największej liczbie wystąpień tutaj — najwięcej zmienią.
    grupy.sort(key=lambda g: (-g.wystapien_do_zmiany, g.kanoniczny))
    return grupy


def zaproponuj(project_ids=None):
    """[Grupa] — kody zapisane niespójnie w całej bazie (widok przeglądowy).

    Do raportu/diagnostyki. Do scalania używa się
    `zaproponuj_dla_projektu()`, bo zapis obejmuje jeden projekt.
    """
    wg = zbierz_warianty(project_ids)
    grupy = []
    for k, v in wg.items():
        if len(v) > 1:
            grupy.append(Grupa(k, v, {w: d["ile"] for w, d in v.items()}))
    grupy.sort(key=lambda g: (-len(g.projekty), g.kanoniczny))
    return grupy


# ── Zapis ───────────────────────────────────────────────────────────────────
def _backup(pid, backup_dir):
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cel = os.path.join(backup_dir, f"project_{pid}_{stamp}.sqlite")
    shutil.copy2(_sciezka(pid), cel)
    return cel


# Pola, które przy scalaniu wierszy trzeba ZSUMOWAĆ, a nie nadpisać —
# dwie pozycje tego samego elementu to łącznie tyle sztuk, ile w obu.
KOLUMNY_ILOSCI = ("src_qty", "work_qty", "order_qty", "delivered_qty", "min_qty")

# Materiał — pusto w jednym z wierszy nie ma kasować wartości z drugiego,
# więc te kolumny mają własną regułę scalania (patrz scal_wiersze).
KOLUMNY_MATERIALU = ("mat_manual_text", "mat_effective_text", "mat_auto_text",
                     "src_material_text", "mat_grade")

# Pola, których wypełnienie znaczy, że na wierszu ktoś już pracował.
# Scalanie ma się odbywać na świeżym arkuszu (zaraz po imporcie), więc
# normalnie są puste; jeśli nie są, okno o tym uprzedza, zamiast po cichu
# skasować czyjąś robotę.
KOLUMNY_PRACY = ("supplier_id", "price_pln", "notes", "ordered_flag", "ordered_at",
                 "delivered_qty", "deadline_date", "status")


def wiersze_kodu(project_id, kody, con=None):
    """[{id, nazwa, kolumna, ...}] — wiersze BOM o podanych zapisach nazwy.

    Potrzebne przed scaleniem: pokazać, co dokładnie zostanie połączone
    i czy któryś z wierszy ma już wypełnione dane robocze.

    `con` — połączenie arkusza (db_manager.project_con); bez niego czytamy
    plik z serwera, co przy locku daje NIEAKTUALNE dane (patrz zbierz_warianty).
    """
    szukane = {(k or "").strip() for k in kody if (k or "").strip()}
    if not szukane:
        return []

    wlasne = con is None
    if wlasne:
        path = _sciezka(project_id)
        if not os.path.isfile(path):
            raise RuntimeError(f"Brak bazy projektu: {path}")
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
    try:
        cols = _kolumny(con)
        name_cols = [c for c in KOLUMNY_NAZW if c in cols]
        ilosci = [c for c in KOLUMNY_ILOSCI if c in cols]
        praca = [c for c in KOLUMNY_PRACY if c in cols]
        # Materiał w kolejności ważności: ręczny > wyliczony > z importu.
        # Różny materiał przy podobnej nazwie zwykle znaczy, że to jednak
        # RÓŻNE elementy — user musi to widzieć przed scaleniem.
        mat_cols = [c for c in ("mat_manual_text", "mat_effective_text",
                                "mat_auto_text", "src_material_text") if c in cols]
        extra = [c for c in ("src_modul", "src_row") if c in cols]
        # Numer rysunku — po nim poznajemy duplikat, ktorego NAZWY sie roznia
        # („HGH15CA" vs „HGH15CA Z0" przy tym samym work_drawing_no).
        rys_cols = [c for c in KOLUMNY_RYSUNKU if c in cols]
        opis_cols = [c for c in KOLUMNY_OPISU if c in cols]

        out = []
        # ⚠️ JEDEN WIERSZ = JEDEN WPIS. `name_cols` to work_name i src_name;
        # wiersz, ktory ma w obu ten sam zapis, wpadal tu DWA RAZY z tym
        # samym `id`. Przy scalaniu dwoch duplikatow dawalo to cztery wiersze
        # zamiast dwoch: okno pytalo „Polaczyc 4 wiersze?", ilosci sumowaly
        # sie podwojnie, a `scal_wiersze()` dostawalo powtorzone id.
        # Ta sama rodzina bledu co „jeden wiersz pod dwoma kluczami" przy
        # budowaniu listy (pamiec/project_scalanie_duplikaty_identyczne.md) —
        # tam naprawione 24.09, tutaj zostalo. Kolejnosc KOLUMNY_NAZW jest
        # istotna: wygrywa nazwa AKTUALNA, ta ktora user widzi w arkuszu.
        widziane = set()
        for col in name_cols:
            sel = (["id", col] + ilosci + praca + mat_cols + extra
                   + rys_cols + opis_cols)
            q = f"SELECT {', '.join(dict.fromkeys(sel))} FROM items"
            if "is_hidden" in cols:
                q += " WHERE COALESCE(is_hidden, 0) = 0"
            for r in con.execute(q):
                nazwa = (r[col] or "").strip()
                if nazwa not in szukane:
                    continue
                if r["id"] in widziane:
                    continue
                widziane.add(r["id"])
                material = next((str(r[c]).strip() for c in mat_cols
                                 if r[c] not in (None, "") and str(r[c]).strip()), "")
                out.append({
                    "id": r["id"],
                    "kolumna": col,
                    "nazwa": nazwa,
                    "material": material,
                    "ilosci": {c: r[c] for c in ilosci},
                    # Co na wierszu jest już wypełnione — do ostrzeżenia.
                    "praca": {c: r[c] for c in praca if r[c] not in (None, "", 0)},
                    "modul": r["src_modul"] if "src_modul" in r.keys() else None,
                    # Aktualny numer rysunku (work_ przed src_), pusty gdy brak.
                    "rysunek": next((str(r[c]).strip() for c in rys_cols
                                     if r[c] not in (None, "") and str(r[c]).strip()), ""),
                    # Opis jak w arkuszu: roboczy przeslania importowy.
                    "opis": next((str(r[c]).strip() for c in opis_cols
                                  if r[c] not in (None, "") and str(r[c]).strip()), ""),
                })
        return sorted(out, key=lambda w: w["id"])
    finally:
        if wlasne:
            con.close()


def zmien_nazwy(project_id, zmiany, backup_dir=None, tylko_probnie=False, con=None):
    """Zmienia nazwę wierszy BEZ łączenia ich — każdy zostaje osobno.

    `zmiany` to [(stary_zapis, nowy_zapis)]. W odróżnieniu od scal_wiersze()
    nic nie znika i nic się nie sumuje: to operacja porządkowa, używana gdy
    element ma już kartotekę w Subiekcie i chcemy, żeby BOM nazywał go tak
    samo jak ona.

    Tryby jak w scal_wiersze: z `con` piszemy do lokalnej kopii projektu
    (arkusz RM_BAZA przy locku), bez `con` — do pliku, i wtedy `backup_dir`
    jest wymagany.
    """
    # Wpis to (stary_zapis, nowa_nazwa) albo (stary_zapis, nowa_nazwa, opis).
    # Opis jest OPCJONALNY — pusty znaczy „nie ruszaj kolumny opisu".
    znormalizowane = []
    for wpis in zmiany:
        st, nw = wpis[0], wpis[1]
        op = wpis[2] if len(wpis) > 2 else ""
        if (st or "").strip() and (nw or "").strip() and st != nw:
            znormalizowane.append((st, nw, (op or "").strip()))
    zmiany = znormalizowane
    raport = {"project_id": project_id, "zmienionych": 0,
              "szczegoly": [], "backup": None, "probnie": tylko_probnie}
    if not zmiany:
        return raport

    wlasne = con is None
    if wlasne:
        if not backup_dir:
            raise ValueError("backup_dir jest wymagany — bez kopii nie zapisujemy.")
        path = _sciezka(project_id)
        if not os.path.isfile(path):
            raise RuntimeError(f"Brak bazy projektu: {path}")
        if not tylko_probnie:
            raport["backup"] = _backup(project_id, backup_dir)
        con = sqlite3.connect(f"file:{path}?mode={'ro' if tylko_probnie else 'rw'}", uri=True)
        con.row_factory = sqlite3.Row

    try:
        cols = _kolumny(con)
        name_cols = [c for c in KOLUMNY_NAZW if c in cols]
        # Opis piszemy do kolumny ROBOCZEJ — `src_desc` z importu zostaje
        # nietknieta, tak samo jak przy nazwie (work_ przeslania src_).
        # Wczesniej opis nie byl przenoszony w ogole: pozycja dostawala nazwe
        # z Subiekta, a opis zostawal stary (zgloszone 25.09.2026).
        opis_col = next((c for c in KOLUMNY_OPISU if c in cols), None)
        for stary, nowy, opis in zmiany:
            for c in name_cols:
                # TRIM w warunku — zapisy bywają z białymi znakami na końcu.
                n = con.execute(
                    f"SELECT COUNT(*) FROM items WHERE TRIM({c}) = ?", (stary,)).fetchone()[0]
                if not n:
                    continue
                if not tylko_probnie:
                    if opis and opis_col:
                        con.execute(
                            f"UPDATE items SET {c} = ?, {opis_col} = ? "
                            f"WHERE TRIM({c}) = ?", (nowy, opis, stary))
                    else:
                        con.execute(f"UPDATE items SET {c} = ? WHERE TRIM({c}) = ?",
                                    (nowy, stary))
                raport["zmienionych"] += n
                raport["szczegoly"].append((c, stary, nowy, n))
        if not tylko_probnie:
            con.commit()
    finally:
        if wlasne:
            con.close()

    return raport


def scal_wiersze(project_id, wiersze_ids, nazwa_docelowa, backup_dir=None,
                 tylko_probnie=False, con=None, opis_docelowy=None):
    """Zastępuje kilka wierszy BOM JEDNYM nowym: suma ilości, wspólna nazwa.

    Stare wiersze są USUWANE, a na ich miejsce wstawiany jest nowy — nie
    dziedziczy więc przypadkowych pól po żadnym z nich (dostawca, moduł,
    numer wiersza w pliku źródłowym). Przenoszone są tylko: nazwa docelowa,
    zsumowane ilości i pola wspólne dla wszystkich scalanych wierszy
    (np. project_id, klasa) — jeśli różnią się, pole zostaje puste.

    Dwa tryby:
      * `con` podane — pracujemy na połączeniu arkusza RM_BAZA (lokalna
        kopia przy locku). Kopię zapasową i odświeżenie robi wtedy okno,
        które ma dostęp do ścieżki lokalnej. To tryb produkcyjny.
      * bez `con` — otwieramy plik z serwera; `backup_dir` WYMAGANY.
        Tryb do skryptów/testów, gdy nikt nie trzyma locka.

    Operacja NIEODWRACALNA poza kopią. Pomyślana na świeży arkusz zaraz po
    imporcie, zanim ktokolwiek wpisze dostawców i ceny.
    """
    ids = sorted(set(int(i) for i in wiersze_ids))
    if len(ids) < 2:
        raise ValueError("Do scalenia trzeba co najmniej dwóch wierszy.")

    raport = {"project_id": project_id, "usuniete": ids, "nowy_id": None,
              "sumy": {}, "backup": None, "probnie": tylko_probnie}

    wlasne = con is None
    if wlasne:
        if not backup_dir:
            raise ValueError("backup_dir jest wymagany — bez kopii nie zapisujemy.")
        path = _sciezka(project_id)
        if not os.path.isfile(path):
            raise RuntimeError(f"Brak bazy projektu: {path}")
        if not tylko_probnie:
            raport["backup"] = _backup(project_id, backup_dir)
        con = sqlite3.connect(f"file:{path}?mode={'ro' if tylko_probnie else 'rw'}", uri=True)
        con.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info('items')")}
        ilosci = [c for c in KOLUMNY_ILOSCI if c in cols]
        name_cols = [c for c in KOLUMNY_NAZW if c in cols]

        znaki = ",".join("?" * len(ids))
        rows = con.execute(f"SELECT * FROM items WHERE id IN ({znaki})", ids).fetchall()
        if len(rows) < 2:
            raise RuntimeError("Nie znaleziono wszystkich wierszy do scalenia.")

        def _liczba(v):
            try:
                return float(v) if v not in (None, "") else None
            except (TypeError, ValueError):
                return None

        def _ladnie(s):
            # Bez ułamka, jeśli wychodzi całkowita — 5.0 sztuk wygląda
            # w arkuszu dziwnie.
            return int(s) if float(s).is_integer() else s

        # Suma ilości ze wszystkich scalanych wierszy.
        for c in ilosci:
            wartosci = [_liczba(r[c]) for r in rows]
            wartosci = [v for v in wartosci if v is not None]
            if wartosci:
                raport["sumy"][c] = _ladnie(sum(wartosci))

        # work_qty to RĘCZNA korekta ilości BOM, a arkusz pokazuje
        # COALESCE(work_qty, src_qty) — czyli work_qty PRZESŁANIA src_qty.
        # Sumowanie każdej kolumny osobno dawało więc złą liczbę na ekranie:
        # gdy tylko jeden z wierszy miał work_qty=1, scalony wiersz miał
        # src_qty=6 (poprawnie), ale work_qty=1 i arkusz pokazywał 1.
        # Sumujemy więc to, co widać: dla każdego wiersza bierzemy jego
        # wartość efektywną i dopiero to składamy.
        if "work_qty" in cols and any(_liczba(r["work_qty"]) is not None for r in rows):
            efektywne = []
            for r in rows:
                v = _liczba(r["work_qty"])
                if v is None and "src_qty" in cols:
                    v = _liczba(r["src_qty"])
                if v is not None:
                    efektywne.append(v)
            if efektywne:
                raport["sumy"]["work_qty"] = _ladnie(sum(efektywne))

        # Nowy wiersz: pola wspólne dla wszystkich scalanych zostają, różniące
        # się (moduł, src_row, dostawca…) celowo NIE — nowa pozycja nie ma
        # udawać żadnej z poprzednich.
        nowy = {}
        for c in cols:
            if c == "id":
                continue
            if c in ilosci or c in name_cols:
                continue
            wartosci = {r[c] for r in rows}
            if len(wartosci) == 1:
                nowy[c] = rows[0][c]

        # Materiał osobno: pusto w jednym wierszu to NIE sprzeciw wobec
        # wartości z drugiego. Reguła „identyczne we wszystkich" gubiła
        # materiał, gdy jeden z wierszy go po prostu nie miał ('Ogólny' +
        # brak → puste). Bierzemy więc niepuste wartości; przy realnym
        # konflikcie łączymy je, żeby żadna nie zniknęła po cichu — user
        # widzi rozbieżność w arkuszu i rozstrzyga ją sam.
        for c in KOLUMNY_MATERIALU:
            if c not in cols:
                continue
            wartosci = []
            for r in rows:
                v = r[c]
                if v in (None, ""):
                    continue
                v = str(v).strip()
                if v and v not in wartosci:
                    wartosci.append(v)
            if wartosci:
                nowy[c] = wartosci[0] if len(wartosci) == 1 else " / ".join(wartosci)

        for c in name_cols:
            # Nazwę wpisujemy tam, gdzie którykolwiek wiersz ją miał, żeby
            # pozycja nie zniknęła z widoku filtrującego po tej kolumnie.
            if any(r[c] not in (None, "") for r in rows):
                nowy[c] = nazwa_docelowa
        # OPIS docelowy — do kolumny ROBOCZEJ, jak przy `zmien_nazwy`.
        # None znaczy „nie narzucaj": zostaje to, co wyszlo z reguly pol
        # wspolnych wyzej. Pusty string rowniez nie nadpisuje, bo user
        # zwykle po prostu nie wybral kartoteki (25.09.2026).
        if opis_docelowy:
            opis_col = next((c for c in KOLUMNY_OPISU if c in cols), None)
            if opis_col:
                nowy[opis_col] = opis_docelowy
        nowy.update(raport["sumy"])

        if not tylko_probnie:
            kolumny = list(nowy)
            cur = con.execute(
                f"INSERT INTO items ({', '.join(kolumny)}) "
                f"VALUES ({', '.join('?' * len(kolumny))})",
                [nowy[c] for c in kolumny])
            raport["nowy_id"] = cur.lastrowid
            con.execute(f"DELETE FROM items WHERE id IN ({znaki})", ids)
            con.commit()
    finally:
        if wlasne:
            con.close()

    return raport


def zastosuj_podmiany(podmiany, project_id, backup_dir, tylko_probnie=False):
    """Zapisuje wprost pary (stary_zapis, nowy_zapis) — TYLKO w tym projekcie.

    Wariant dla GUI, gdzie user sam decyduje, co z czym scalić i pod jaką
    nazwą — nowa nazwa nie musi istnieć w żadnym BOM-ie (bywa, że każdy
    dotychczasowy zapis jest zły: 'Nakrętka TR16x4..' z kropkami).

    `backup_dir` jest WYMAGANY — plik projektu jest najpierw kopiowany.
    """
    if not backup_dir:
        raise ValueError("backup_dir jest wymagany — bez kopii nie zapisujemy.")
    if not project_id:
        raise ValueError("project_id jest wymagany — scalamy jeden projekt naraz.")

    path = _sciezka(project_id)
    if not os.path.isfile(path):
        raise RuntimeError(f"Brak bazy projektu: {path}")

    raport = {"project_id": project_id, "zmienionych": 0,
              "szczegoly": [], "backup": None, "probnie": tylko_probnie}
    podmiany = [(s, n) for s, n in podmiany if s != n]
    if not podmiany:
        return raport

    if not tylko_probnie:
        raport["backup"] = _backup(project_id, backup_dir)

    tryb = "ro" if tylko_probnie else "rw"
    con = sqlite3.connect(f"file:{path}?mode={tryb}", uri=True)
    try:
        cols = _kolumny(con)
        name_cols = [c for c in KOLUMNY_NAZW if c in cols]
        for stary, nowy in podmiany:
            for col in name_cols:
                # TRIM w warunku, bo zapisy bywają z białymi znakami na końcu.
                n = con.execute(
                    f"SELECT COUNT(*) FROM items WHERE TRIM({col}) = ?",
                    (stary,)).fetchone()[0]
                if not n:
                    continue
                if not tylko_probnie:
                    con.execute(
                        f"UPDATE items SET {col} = ? WHERE TRIM({col}) = ?",
                        (nowy, stary))
                raport["zmienionych"] += n
                raport["szczegoly"].append((col, stary, nowy, n))
        if not tylko_probnie:
            con.commit()
    finally:
        con.close()

    return raport


def zastosuj(grupy, project_id, backup_dir, tylko_probnie=False):
    """Zapisuje kanoniczny kod w miejsce wariantów — TYLKO w tym projekcie.

    `backup_dir` jest WYMAGANY — plik projektu jest najpierw kopiowany.
    To zmiana danych; bez kopii nie ma odwrotu.

    `tylko_probnie=True` liczy, co by się stało, i nic nie zapisuje.
    """
    if not backup_dir:
        raise ValueError("backup_dir jest wymagany — bez kopii nie zapisujemy.")
    if not project_id:
        raise ValueError("project_id jest wymagany — scalamy jeden projekt naraz.")

    path = _sciezka(project_id)
    if not os.path.isfile(path):
        raise RuntimeError(f"Brak bazy projektu: {path}")

    podmiany = [(w, g.kanoniczny) for g in grupy for w in g.do_zmiany]
    raport = {"project_id": project_id, "zmienionych": 0,
              "szczegoly": [], "backup": None, "probnie": tylko_probnie}
    if not podmiany:
        return raport

    if not tylko_probnie:
        raport["backup"] = _backup(project_id, backup_dir)

    tryb = "ro" if tylko_probnie else "rw"
    con = sqlite3.connect(f"file:{path}?mode={tryb}", uri=True)
    try:
        cols = _kolumny(con)
        name_cols = [c for c in KOLUMNY_NAZW if c in cols]
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
                raport["zmienionych"] += n
                raport["szczegoly"].append((col, stary, nowy, n))
        if not tylko_probnie:
            con.commit()
    finally:
        con.close()

    return raport


# ── Kandydaci: kody podobne, ale NIE identyczne po normalizacji ─────────────
# Osobna kategoria od grup scalania i celowo NIE zaznaczana domyślnie.
#
# Powód: w BOM-ach sąsiadują ze sobą kody, które różnią się jednym znakiem,
# a oznaczają zupełnie inny element:
#
#     'KFL001'  vs  'KFL002'              inny rozmiar łożyska
#     'GS14 10-12' / 'GS14 14-12' / 'GS14 14-16'   trzy rozmiary
#     'DFM-20-20-P-A-GF' vs 'DFM-20-40-P-A-GF'     inny skok siłownika
#     'UCFL 201' vs 'UCFL201-12'          201 to nie 201-12
#     '12x14X10 SBT' vs '12x14X10 SBT E'  wersja E
#
# Scalenie takiej pary jest GORSZE niż zostawienie duplikatu — kończy się
# zamówieniem złej części. Dlatego mechanizm je pokazuje jako „do
# sprawdzenia", ale nigdy nie proponuje scalenia sam.

def _wspolny_prefiks(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


# Segment długości: 'L' + cyfry ('T5 L260 szer16', 'MGW12H L350', 'HGR15 L260',
# 'WS-20 L1300'). Dwa kody różniące się TYLKO nim to różne elementy — inna
# długość paska/szyny, nie inny zapis tego samego. Także 'MGW12H' vs
# 'MGW12H L350': bez długości i z długością to nie jest ta sama pozycja.
#
# Porównanie musi działać na ORYGINALNYM zapisie, nie na znormalizowanym:
# normalizacja skleja 'UCFL 201' w 'UCFL201', gdzie 'L201' wygląda jak
# segment długości, choć 'L' jest częścią nazwy rodziny (UCFL). Stąd wymóg
# granicy słowa przed 'L' — w oryginale przed długością zawsze stoi spacja
# albo separator.
#
# Jednostka bywa dopisana ('WS-10 L240mm', 'L1300m') albo pominięta
# ('T5 L260') — traktujemy to jak jeden segment, żeby 'L240mm' i 'L300mm'
# rozpoznać jako tę samą różnicę co 'L240' i 'L300'.
_DLUGOSC = re.compile(r"(?<![A-Za-z0-9])L\d+(?:mm|cm|m)?\b", re.IGNORECASE)


def _bez_dlugosci(s):
    return _DLUGOSC.sub("L#", s or "")


def _rozni_sie_tylko_dlugoscia(a, b):
    """Czy oba zapisy są tożsame po zastąpieniu segmentu długości?

    Argumenty to ORYGINALNE zapisy (nie znormalizowane) — patrz wyżej.
    """
    return norm_kod(_bez_dlugosci(a)) == norm_kod(_bez_dlugosci(b))


def znajdz_kandydatow(project_id, min_prefiks=4):
    """[(kod_a, kod_b, wspolny_prefiks)] — kody podobne, do ręcznej oceny.

    Kryterium: wspólny początek co najmniej `min_prefiks` znaków po
    normalizacji, przy różnej reszcie. Prefiks, nie podobieństwo rozmyte —
    bo kody katalogowe czyta się od lewej (rodzina, potem rozmiar), więc
    wspólny początek to sensowna przesłanka, a rozmyte dopasowanie łapałoby
    zbieżności bez znaczenia (pomiar: 389 fałszywych par, plan „Krok 2b").

    Zwraca pary posortowane od najdłuższego wspólnego początku — te na
    górze najczęściej są prawdziwymi duplikatami.
    """
    wg = zbierz_warianty({project_id})
    klucze = sorted(wg)

    # Do reguł o długości potrzebny jest ORYGINALNY zapis (patrz _DLUGOSC):
    # po normalizacji 'UCFL 201' → 'UCFL201' i 'L201' udaje segment długości.
    oryginal = {k: sorted(wg[k])[0] for k in klucze}

    pary = []
    for i, a in enumerate(klucze):
        for b in klucze[i + 1:]:
            n = _wspolny_prefiks(a, b)
            if n < min_prefiks:
                continue
            oa, ob = oryginal[a], oryginal[b]
            # Różnica wyłącznie w długości ('T5 L260' vs 'T5 L330') to inny
            # element, nie inny zapis — pomijamy zamiast zawracać głowę.
            if _rozni_sie_tylko_dlugoscia(oa, ob):
                continue
            # To samo, gdy jeden kod ma segment długości, a drugi nie
            # ('MGW12H' vs 'MGW12H L350') — dookreślenie długości robi
            # z tego inną pozycję.
            krotszy, dluzszy = (oa, ob) if len(oa) <= len(ob) else (ob, oa)
            if norm_kod(dluzszy).startswith(norm_kod(krotszy)):
                reszta = dluzszy[len(krotszy):].strip()
                if reszta and _DLUGOSC.fullmatch(reszta):
                    continue
            # Jeden kod będący początkiem drugiego ('UCFL201' w 'UCFL20112')
            # to najczęstszy wzorzec prawdziwego duplikatu — podnosimy go wyżej.
            zawiera = a.startswith(b) or b.startswith(a)
            pary.append((a, b, n, zawiera))

    pary.sort(key=lambda t: (-t[3], -t[2]))

    # Z kluczy z powrotem na oryginalne zapisy — user ma widzieć to, co w BOM.
    def zapisy(k):
        return sorted(wg[k])

    return [(zapisy(a), zapisy(b), n, zawiera) for a, b, n, zawiera in pary]


def pozycje_z_podobnymi(project_id, min_prefiks=4, con=None):
    """[{"kod", "ile", "identyczne", "podobne"}] — kody handlowe projektu.

    Jeden wpis na kod występujący w tym projekcie, a w nim:

      * `identyczne` — inne zapisy TEGO SAMEGO kodu (różnica separatorów
        albo wielkości liter); to pewne duplikaty,
      * `podobne`    — kody o wspólnym początku, które MOGĄ być tą samą
        rzeczą, ale równie dobrze innym rozmiarem (KFL001/KFL002).

    Dzięki temu user widzi przy każdej pozycji cały jej kontekst i sam
    decyduje, co do niej należy — zamiast oglądać dwie rozłączne listy.

    `con` — połączenie arkusza; przy locku to jedyne aktualne źródło.
    """
    biezacy = (project_id, con) if con is not None else None
    wg = zbierz_warianty({project_id}, biezacy=biezacy)
    cala_baza = zbierz_warianty(biezacy=biezacy)
    klucze = sorted(wg)
    oryginal = {k: sorted(wg[k])[0] for k in klucze}

    # Pary podobnych — te same reguły co znajdz_kandydatow (długości odpadają).
    sasiedzi = {k: [] for k in klucze}
    for i, a in enumerate(klucze):
        for b in klucze[i + 1:]:
            n = _wspolny_prefiks(a, b)
            if n < min_prefiks:
                continue
            oa, ob = oryginal[a], oryginal[b]
            if _rozni_sie_tylko_dlugoscia(oa, ob):
                continue
            krotszy, dluzszy = (oa, ob) if len(oa) <= len(ob) else (ob, oa)
            if norm_kod(dluzszy).startswith(norm_kod(krotszy)):
                reszta = dluzszy[len(krotszy):].strip()
                if reszta and _DLUGOSC.fullmatch(reszta):
                    continue
            zawiera = a.startswith(b) or b.startswith(a)
            sasiedzi[a].append((b, n, zawiera))
            sasiedzi[b].append((a, n, zawiera))

    # Materiał i ilości per zapis — różny materiał przy podobnej nazwie
    # zwykle znaczy, że to jednak inne elementy (uwaga użytkownika).
    szczegoly = {}
    znalezione = wiersze_kodu(project_id, [oryginal[k] for k in klucze], con=con)

    # ⚠️ JEDEN WIERSZ = JEDEN KLUCZ. `wiersze_kodu()` przechodzi po WSZYSTKICH
    # kolumnach nazw, więc wiersz przepisany na inną nazwę wraca DWA RAZY:
    # raz pod starą (`src_name`), raz pod nową (`work_name`). Przy rozbijaniu
    # na osobne pozycje listy dawało to klucz `#id` w dwóch różnych pozycjach
    # naraz — Treeview odrzucał kolizję iid i CAŁA pozycja znikała z okna
    # (24.09.2026: wiersz 264 jako „6004" i jako „SS 6004 2RS 20x42x12").
    #
    # Wiersz należy do klucza swojej AKTUALNEJ nazwy — tej, którą user widzi
    # w arkuszu. Kolejność jak w RM_BAZA: robocza przed importową.
    pierwszenstwo = {c: i for i, c in enumerate(KOLUMNY_NAZW)}
    aktualna = {}
    for w in znalezione:
        poprzednia = aktualna.get(w["id"])
        if (poprzednia is None
                or pierwszenstwo.get(w["kolumna"], 99)
                < pierwszenstwo.get(poprzednia["kolumna"], 99)):
            aktualna[w["id"]] = w

    for w in znalezione:
        d = szczegoly.setdefault(norm_kod(w["nazwa"]),
                                 {"materialy": set(), "ilosc": 0, "wiersze": []})
        # Pojedyncze wiersze BOM-u — potrzebne, zeby duplikat tego samego
        # zapisu rozbic na OSOBNE pozycje listy (patrz nizej). Tylko dla
        # nazwy AKTUALNEJ, inaczej wiersz trafilby pod dwa klucze.
        if aktualna.get(w["id"]) is w:
            q_w = w["ilosci"].get("work_qty")
            if q_w in (None, ""):
                q_w = w["ilosci"].get("src_qty") or 0
            try:
                q_w = float(q_w)
            except (TypeError, ValueError):
                q_w = 0.0
            d["wiersze"].append({"id": w["id"], "nazwa": w["nazwa"],
                                 "material": w.get("material") or "",
                                 "rysunek": w.get("rysunek") or "",
                                 "opis": w.get("opis") or "",
                                 "ilosc": q_w})
        if w["material"]:
            d["materialy"].add(w["material"])
        # Jak arkusz: COALESCE(work_qty, src_qty) — work_qty to ręczna korekta
        # i przesłania wartość z importu (database_manager.get_project_items).
        q = w["ilosci"].get("work_qty")
        if q in (None, ""):
            q = w["ilosci"].get("src_qty") or 0
        try:
            d["ilosc"] += float(q)
        except (TypeError, ValueError):
            pass

    out = []
    for k in klucze:
        zapisy = sorted(wg[k])
        w_bazie = cala_baza.get(k, {})
        sz = szczegoly.get(k, {"materialy": set(), "ilosc": 0, "wiersze": []})
        # Nr rysunku i Opis — jak w arkuszu RM_BAZA. Bierzemy z pierwszego
        # wiersza tego kodu; przy rozbiciu na osobne wpisy (nizej) kazdy
        # dostaje swoje wlasne (25.09.2026).
        _w0 = (sz.get("wiersze") or [{}])[0]
        wspolne = {
            "rysunek": _w0.get("rysunek", ""),
            "opis": _w0.get("opis", ""),
            "kod": zapisy[0],
            "ile": sum(v["ile"] for v in wg[k].values()),
            "material": " / ".join(sorted(sz["materialy"])),
            "ilosc_bom": sz["ilosc"],
            # Kilka zapisów tego samego klucza = pewny duplikat wewnątrz projektu.
            "identyczne": zapisy[1:],
            "podobne": [
                {"kod": oryginal[b], "wspolne": n, "prefiks": z}
                for b, n, z in sorted(sasiedzi[k], key=lambda t: (-t[2], -t[1]))
            ],
            # Jak ten kod zapisuje reszta firmy — podpowiedź do nazwy docelowej.
            "w_bazie": {w: len(v["projekty"]) for w, v in w_bazie.items()},
        }

        # ⚠️ DUPLIKAT W ARKUSZU = OSOBNE WIERSZE W OKNIE (24.09.2026).
        #
        # Gdy ten sam kod stoi w kilku wierszach BOM-u zapisany TAK SAMO,
        # jeden wpis na liście nie da się scalić: „Scal zaznaczone" wymaga
        # DWÓCH zaznaczonych wierszy, a użytkownik widzi jeden. Rozbijamy
        # więc taką pozycję na tyle wpisów, ile jest wierszy w arkuszu —
        # dokładnie to, co user ma przed oczami w RM_BAZA.
        #
        # Klucz musi zostać UNIKALNY: jest tożsamością wiersza w oknie
        # (iid w Treeview i element zbioru `_zaznaczone`).
        #
        # Różne ZAPISY tego samego klucza („KOŁO" vs „Koło") NIE są tu
        # rozbijane — tam scala się przemianowaniem, `identyczne` niesie
        # komplet wariantów.
        wiersze_k = sz.get("wiersze") or []
        if len(zapisy) == 1 and len(wiersze_k) > 1:
            for w in sorted(wiersze_k, key=lambda x: x["id"]):
                out.append({**wspolne,
                            "klucz": f"{k}#{w['id']}",
                            "item_id": w["id"],
                            "kod": w["nazwa"],
                            "rysunek": w.get("rysunek", ""),
                            "opis": w.get("opis", ""),
                            "ile": 1,
                            "material": w["material"],
                            "ilosc_bom": w["ilosc"],
                            # Rodzeństwo z arkusza — powód, dla którego ten
                            # wiersz w ogóle trafia na listę.
                            "rodzenstwo": len(wiersze_k)})
        else:
            out.append({**wspolne, "klucz": k, "item_id": None,
                        "rodzenstwo": 0})

    # ── DUPLIKAT PO NUMERZE RYSUNKU (25.09.2026) ─────────────────────────────
    #
    # Wszystko powyzej grupuje po NAZWIE. Dwa wiersze o tym samym numerze
    # rysunku, ale roznych nazwach, wypadaly wiec z okna calkiem — user
    # widzial w arkuszu czerwony pasek „DUPLIKATY NUMEROW RYSUNKOW", a tutaj
    # nie mial czego zaznaczyc (2637 Feniks: id 936/937, oba `HGH15SO`,
    # nazwy „HGH15CA" i „HGH15CA Z0").
    #
    # Takie wiersze dokladamy jako OSOBNE wpisy — po jednym na wiersz, tak
    # samo jak przy duplikacie tego samego zapisu, zeby dalo sie zaznaczyc
    # oba i scalic. Klucz `rys:<numer>#<id>` nie koliduje z kluczami nazw.
    wg_rysunku = {}
    for sz in szczegoly.values():
        for w in sz.get("wiersze") or []:
            r = (w.get("rysunek") or "").strip().upper()
            if r:
                wg_rysunku.setdefault(r, []).append(w)

    juz_rozbite = {p["item_id"] for p in out if p.get("item_id")}
    for rys, wiersze_r in sorted(wg_rysunku.items()):
        if len(wiersze_r) < 2:
            continue
        # Nie dublujemy wierszy, ktore juz stoja na liscie osobno (ten sam
        # zapis nazwy) — tam user ma je pod wlasnym kluczem.
        if all(w["id"] in juz_rozbite for w in wiersze_r):
            continue
        for w in sorted(wiersze_r, key=lambda x: x["id"]):
            out.append({
                "klucz": f"rys:{rys}#{w['id']}",
                "item_id": w["id"],
                "kod": w["nazwa"],
                "rysunek": w.get("rysunek", ""),
                "opis": w.get("opis", ""),
                "ile": 1,
                "material": w["material"],
                "ilosc_bom": w["ilosc"],
                "identyczne": [],
                "podobne": [],
                "w_bazie": {},
                "rodzenstwo": 0,
                # Powod, dla ktorego ten wiersz jest na liscie — GUI pokazuje
                # to w kolumnie „Podobne w tym projekcie".
                "rysunek_dubel": rys,
                "rysunek_ile": len(wiersze_r),
            })

    # Najpierw te, przy których jest co decydować.
    # Duplikaty (rodzenstwo>0) licza się jak warianty pisowni, żeby stały
    # wysoko; `kod` trzyma wiersze tej samej pozycji obok siebie.
    out.sort(key=lambda p: (-(len(p["identyczne"]) * 10
                              + (10 if p.get("rodzenstwo") else 0)
                              + len(p["podobne"])),
                            p["kod"], p.get("item_id") or 0))
    return out


# ── Dopasowanie do kartoteki Subiekta ───────────────────────────────────────
# Kopia kartoteki Subiekta na dysku. Pobranie przez most kosztuje ~15 s
# (start Sfery + przelot po Wszystkie()), a kartoteki zmieniają się rzadko —
# bez cache każde pierwsze kliknięcie w oknie oznaczało kilkanaście sekund
# czekania.
#
# LOKALNIE, obok reszty plików stanowiska (`subiekt_kolumny.json`,
# `.nexo_sfera.json`). To cache, nie dane: nie ma powodu dzielić go między
# stacjami ani czytać przez SMB. Dawne `dirname(PROJECTS_DIR)/subiekt_katalog.json`
# po przenosinach wskazywało korzeń udziału z bazami projektów — i nigdy nie
# zostało tam zapisane, więc każde otwarcie okna pobierało kartoteki od nowa
# (audyt 14.09.2026).
KATALOG_CACHE = r"C:\RMPAK_CLIENT\subiekt_katalog.json"
KATALOG_WAZNY_H = 12          # po tylu godzinach odświeżamy w tle


def wczytaj_katalog_subiekta(tylko_cache=False, max_wiek_h=None):
    """[{"id", "symbol", "nazwa"}] — kartoteka Subiekta.

    Domyślnie: cache z dysku, jeśli jest świeży; inaczej pyta most i zapisuje
    wynik. `tylko_cache=True` nigdy nie sięga do Subiekta — zwraca to, co jest
    na dysku (albo pustą listę), żeby okno mogło pokazać dane natychmiast.
    """
    wiek_ok = None
    try:
        if os.path.isfile(KATALOG_CACHE):
            wiek_h = (time.time() - os.path.getmtime(KATALOG_CACHE)) / 3600.0
            limit = KATALOG_WAZNY_H if max_wiek_h is None else max_wiek_h
            wiek_ok = wiek_h <= limit
            if tylko_cache or wiek_ok:
                with open(KATALOG_CACHE, encoding="utf-8") as f:
                    dane = json.load(f)
                # ⚠️ Cache sprzed 24.09.2026 ma tylko id/symbol/nazwa.
                # Bez opisu i ceny okna nie odróżnią wariantów tej samej
                # części, więc taki plik traktujemy jak nieważny — inaczej
                # nowe kolumny zostałyby puste aż do ręcznego „Kartoteki".
                if isinstance(dane, list) and dane and "opis" in dane[0]:
                    return dane
    except Exception:
        pass          # uszkodzony cache nie może blokować pobrania

    if tylko_cache:
        return []

    import subiekt_podobne
    katalog = subiekt_podobne.pobierz_katalog()

    # Stany: tryb mostu „katalog" ich NIE CZYTA (to najdroższa część odczytu),
    # więc dociągamy je jednym zapytaniem — tak samo jak Edytor kartotek
    # (`_katalog_worker`) i okno „Dopasuj kartotekę Subiekta". `magazyn`
    # zwraca komplet w ~0,1 s przez stały most, więc kolumna „Stan" nie
    # kosztuje już tego, co kiedyś.
    #
    # Błąd stanów NIE MOŻE przewrócić katalogu: bez nich okna działają
    # dalej, tylko kolumna zostaje pusta.
    try:
        from subiekt_magazyn_gui import pobierz_magazyn
        stany = {}
        for p in pobierz_magazyn(tylko_niezerowe=True) or []:
            sym = str(p.get("Symbol") or "").strip().upper()
            if sym:
                stany[sym] = (float(p.get("Dostepne") or 0)
                              + float(p.get("Zarezerwowane") or 0))
        for poz in katalog:
            poz["stan"] = stany.get(str(poz.get("symbol") or "").strip().upper())
    except Exception:
        pass

    try:
        os.makedirs(os.path.dirname(KATALOG_CACHE), exist_ok=True)
        with open(KATALOG_CACHE, "w", encoding="utf-8") as f:
            json.dump(katalog, f, ensure_ascii=False)
    except Exception:
        pass          # brak zapisu cache to strata prędkości, nie błąd
    return katalog


def katalog_wiek_h():
    """Wiek cache w godzinach albo None, gdy go nie ma."""
    try:
        if os.path.isfile(KATALOG_CACHE):
            return (time.time() - os.path.getmtime(KATALOG_CACHE)) / 3600.0
    except Exception:
        pass
    return None


def dopasuj_katalog(kody, katalog):
    """{kod: kartoteka albo None} — dopasowanie wielu kodów naraz.

    Jedno przejście po katalogu zamiast pełnego skanu na każdy kod (przy
    2745 kartotekach i kilkudziesięciu pozycjach to różnica odczuwalna
    w oknie).
    """
    wg_symbolu, wg_nazwy = {}, {}
    for poz in katalog:
        k = norm_kod(poz.get("symbol"))
        if k:
            wg_symbolu.setdefault(k, poz)
        k = norm_kod(poz.get("nazwa"))
        if k:
            wg_nazwy.setdefault(k, poz)

    out = {}
    for kod in kody:
        k = norm_kod(kod)
        # Symbol przed nazwą — to on jest identyfikatorem kartoteki.
        out[kod] = wg_symbolu.get(k) or wg_nazwy.get(k) if k else None
    return out


def znajdz_w_subiekcie(kod, katalog):
    """Kartoteka odpowiadająca kodowi, albo None.

    Porównanie po znormalizowanej postaci — tej samej, która grupuje
    warianty w BOM-ie. Dzięki temu 'UCFL 201' z BOM-u znajduje 'UCFL201'
    w Subiekcie: dla obu systemów to jeden element.

    Sprawdzany jest najpierw SYMBOL (właściwy identyfikator kartoteki),
    potem NAZWA — bo elementy handlowe bywają założone z kodem wpisanym
    w nazwę, a symbolem nadanym ręcznie.

    Świadomie BEZ dopasowania rozmytego: pomiar (plan, „Krok 2b") pokazał
    389 fałszywych par przy nazwach, m.in. 'Płyta zewnętrzna' vs
    'Płyta wewnętrzna' = 0.933.
    """
    k = norm_kod(kod)
    if not k:
        return None
    for poz in katalog:
        if norm_kod(poz.get("symbol")) == k:
            return poz
    for poz in katalog:
        if norm_kod(poz.get("nazwa")) == k:
            return poz
    return None


def sformatuj_propozycje(grupy, project_id=None):
    naglowek = "SCALANIE ELEMENTÓW HANDLOWYCH — propozycja"
    if project_id:
        naglowek += f" (projekt {project_id})"
    L = ["=" * 78, naglowek, "=" * 78, ""]
    if not grupy:
        L.append("Brak wariantów do scalenia — kody w tym projekcie są spójne")
        L.append("z zapisem przyjętym w pozostałych projektach.")
        return "\n".join(L)

    remisy = [g for g in grupy if g.remis]
    L.append(f"Grup do scalenia w tym projekcie: {len(grupy)}")
    L.append(f"  wystąpień do zmiany:             {sum(g.wystapien_do_zmiany for g in grupy)}")
    L.append(f"  wymagających decyzji (remis):    {len(remisy)}")
    L.append("")
    L.append("Zmieniany jest TYLKO ten projekt. Liczby przy wariantach pokazują,")
    L.append("jak dany kod zapisano w całej bazie — stąd propozycja kanonicznego.")
    L.append("Przy remisie częstotliwość nie rozstrzyga — sprawdź ręcznie.")
    L.append("")
    for g in grupy:
        znak = "  ⚠ REMIS" if g.remis else ""
        L.append("-" * 78)
        w_bazie = len(g.warianty.get(g.kanoniczny, {}).get("projekty", ()))
        skad = f"   [w bazie: {w_bazie} proj.]" if w_bazie else "   [tylko w tym projekcie]"
        L.append(f"  ZOSTAJE:  {g.kanoniczny!r}{skad}{znak}")
        for w in sorted(g.do_zmiany):
            ile_tu = g.w_projekcie[w]
            v = g.warianty.get(w, {})
            w_bazie = len(v.get("projekty", ()))
            L.append(f"  zmienić:  {w!r}   (tu: {ile_tu}x, w bazie: {w_bazie} proj.)")
    L.append("-" * 78)
    return "\n".join(L)
