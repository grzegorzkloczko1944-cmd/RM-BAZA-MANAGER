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
    sel = ["work_drawing_no", "norm_drawing_no", "src_drawing_no"] + name_cols
    where = " WHERE COALESCE(is_hidden, 0) = 0" if "is_hidden" in cols else ""
    out = []
    for r in con.execute(f"SELECT {', '.join(sel)} FROM items{where}"):
        r = tuple(r)          # połączenie arkusza ma row_factory=Row
        nr = next((v for v in r[0:3] if v not in (None, "") and str(v).strip()), None)
        # Ma numer rysunku → detal własny, ma swój klucz. Nie dotykamy.
        if nr is not None and looks_like_drawing_no(str(nr)):
            continue
        nazwa = next((v for v in r[3:] if v not in (None, "") and str(v).strip()), None)
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

        out = []
        for col in name_cols:
            sel = ["id", col] + ilosci + praca + mat_cols + extra
            q = f"SELECT {', '.join(dict.fromkeys(sel))} FROM items"
            if "is_hidden" in cols:
                q += " WHERE COALESCE(is_hidden, 0) = 0"
            for r in con.execute(q):
                nazwa = (r[col] or "").strip()
                if nazwa not in szukane:
                    continue
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
                })
        return sorted(out, key=lambda w: w["id"])
    finally:
        if wlasne:
            con.close()


def scal_wiersze(project_id, wiersze_ids, nazwa_docelowa, backup_dir=None,
                 tylko_probnie=False, con=None):
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
    for w in wiersze_kodu(project_id, [oryginal[k] for k in klucze], con=con):
        d = szczegoly.setdefault(norm_kod(w["nazwa"]), {"materialy": set(), "ilosc": 0})
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
        sz = szczegoly.get(k, {"materialy": set(), "ilosc": 0})
        out.append({
            "klucz": k,
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
        })

    # Najpierw te, przy których jest co decydować.
    out.sort(key=lambda p: (-(len(p["identyczne"]) * 10 + len(p["podobne"])), p["kod"]))
    return out


# ── Dopasowanie do kartoteki Subiekta ───────────────────────────────────────
def wczytaj_katalog_subiekta():
    """[{"symbol", "nazwa"}] — kartoteka Subiekta przez most (odczyt).

    Kosztowne (jeden przelot po Wszystkie()), więc woła się raz i trzyma
    wynik, nie per pozycja.
    """
    import subiekt_podobne
    return subiekt_podobne.pobierz_katalog()


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
