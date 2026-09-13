# -*- coding: utf-8 -*-
"""Schowek → BOM: dopisanie brakujących pozycji PRZED wystawieniem RW.

Realizuje SCHOWEK_RW_ALGORYTM.md. Jedyne pytanie o pozycję ze schowka:

    Czy jej SYMBOL występuje już w kolumnie „Nr rysunku" tego projektu?

    JEST   → nie ruszamy BOM-u, tylko RW.
    NIE MA → najpierw wiersz w RM_BAZA, potem RW.

Działa, bo „Ilość dostarczonych" w arkuszu jest CZYTANA z Subiekta, nie
wpisywana przez RM_BAZA. Wystarczy więc zapewnić, że w chwili odczytu
istnieje wiersz, do którego ta ilość ma się przypiąć.

⛔ REGUŁA NADRZĘDNA: RW nie powstaje, dopóki RM_BAZA nie potwierdzi zapisu
pozycji. Wydanie z Subiekta nie może pojawić się wcześniej niż rekord, do
którego ma się przypiąć — inaczej arkusz pokaże ilość „znikąd" albo zgubi
ją przy odczycie.

Potwierdzeniem jest udany zapis w JEDNYM z dwóch miejsc:

    lock wolny albo NASZ   → baza projektu
    lock trzyma KTOŚ INNY  → tabela poczekalni w master.sqlite
                             (arkusz nałoży wiersz przy „Przejmij Lock")

W obu wypadkach RW powstaje normalnie — brak locka NIE blokuje wydania.
Blokuje je dopiero nieudany zapis w którymkolwiek z tych miejsc.

Poczekalnia to kopia sprawdzonego wzorca z wysyłki ZD
(`zd_zamowione_pozycje`, `subiekt_wyslij_zd.py:215`): master jest dostępny
bez locka, a nałożenie robi ten, kto z natury ma do tego prawo.

CZEGO TU NIE MA — świadomie
───────────────────────────
* żadnego `source='warehouse'` ani znacznika „pozycja magazyniera": po
  operacji to zwykła pozycja projektu i następnym razem zostanie znaleziona
  po numerze, więc drugi wiersz nie powstanie;
* żadnego odkładania ILOŚCI — te czyta się z Subiekta;
* żadnego sterowania kolejnością wierszy: arkusz sortuje alfabetycznie
  i tak zostaje (decyzja 13.09.2026).
"""

from datetime import datetime


#: Nazwa poczekalni w master. Wiersze czekające na nałożenie do BOM-u,
#: gdy w chwili rozliczenia lock trzymał ktoś inny.
TABELA = "schowek_nowe_pozycje"


class BladBom(Exception):
    """Nie udało się przygotować BOM-u — RW NIE MOŻE powstać."""


# ── wyszukanie symbolu w BOM-ie ─────────────────────────────────────────────
#
# Porównanie po TRIM + case-insensitive, na OBU polach numeru rysunku.
# „Nr rysunku" w arkuszu to wartość efektywna:
#     COALESCE(NULLIF(work_drawing_no,''), src_drawing_no)
# więc symbol może siedzieć w którymkolwiek z nich.
#
# To samo zapytanie, co walidacja duplikatów przy ręcznym dodawaniu pozycji
# (RM_BAZA_v15_MAG_STATS_ORG.py:11895) — celowo, żeby schowek i arkusz
# uznawały za duplikat dokładnie to samo.
SQL_SZUKAJ = """
    SELECT id
      FROM items
     WHERE project_id = ?
       AND ( LOWER(TRIM(COALESCE(work_drawing_no, ''))) = LOWER(TRIM(?))
          OR LOWER(TRIM(COALESCE(src_drawing_no,  ''))) = LOWER(TRIM(?)) )
     LIMIT 1
"""


def znajdz_w_bom(con, project_id, symbol):
    """item_id pozycji o tym numerze rysunku albo None."""
    s = (symbol or "").strip()
    if not s or con is None or not project_id:
        return None
    w = con.execute(SQL_SZUKAJ, (project_id, s, s)).fetchone()
    return w[0] if w else None


def podziel(con, project_id, pozycje):
    """({są w BOM-ie}, [brakujące]) dla pozycji ze schowka.

    `pozycje` — [{symbol, nazwa, ilosc}] z `subiekt_schowek.do_rozliczenia`.
    """
    sa, brak = {}, []
    for p in pozycje:
        item_id = znajdz_w_bom(con, project_id, p["symbol"])
        if item_id:
            sa[p["symbol"]] = item_id
        else:
            brak.append(p)
    return sa, brak


# ── dopisanie wiersza do bazy projektu ──────────────────────────────────────
#
# Kolumny jak przy pozycji dodanej ręcznie (is_manual=1): wypełniamy i pola
# źródłowe `src_*`, i robocze `work_*`. Tak robi „Dodaj pozycję" w arkuszu,
# dzięki czemu „Powrót do BOM" ma co przywracać.
SQL_DODAJ = """
    INSERT INTO items (
        project_id, is_manual, is_hidden,
        src_drawing_no, src_name, src_qty,
        work_drawing_no, work_name, work_qty,
        created_at, updated_at
    ) VALUES (?, 1, 0, ?, ?, 0, ?, ?, 0, ?, ?)
"""


def dodaj_do_bom(con, project_id, symbol, nazwa):
    """Dopisuje wiersz i zwraca item_id. Ilość 0 — Subiekt ją wypełni.

    ⚠️ Sprawdzenie duplikatu POWTÓRZONE tuż przed zapisem: między zebraniem
    listy a tym momentem pozycję mógł dodać ktoś inny (drugi magazynier,
    import, Edytor kartotek). Bez tego powstałby drugi wiersz na ten sam
    detal.

    Ilość docelowa zostaje 0, bo pozycja weszła SPOZA BOM-u — nie było na nią
    zapotrzebowania konstrukcyjnego. „Ilość dostarczonych" i tak przyjdzie
    z Subiekta po wystawieniu RW. Pozostałe pola (typ, materiał, dostawca)
    zostają puste: nie mamy o tej pozycji żadnej wiedzy konstrukcyjnej,
    a wpisanie czegokolwiek byłoby zmyślaniem.
    """
    istnieje = znajdz_w_bom(con, project_id, symbol)
    if istnieje:
        return istnieje                      # ktoś nas uprzedził — dobrze
    s = (symbol or "").strip()
    n = (nazwa or "").strip() or s           # bez nazwy z Subiekta: sam symbol
    teraz = datetime.now().isoformat()
    cur = con.execute(SQL_DODAJ, (project_id, s, n, s, n, teraz, teraz))
    con.commit()
    return cur.lastrowid


# ── dopisanie wydanych ilości do „Ilość dostarczonych" ──────────────────────
def zapisz_wydane_z_subiekta(con, project_id, wydane):
    """Przepisuje do `delivered_qty` STAN Z SUBIEKTA. Zwraca liczbę zmienionych.

    `wydane` — {SYMBOL: ilość} z trybu mostu `wydanie-stan` (pole `wydano`),
    czyli SUMA wszystkich RW tego projektu, policzona przez Subiekta.

    ⚠️ NADPISUJEMY, nie dodajemy — i to jest różnica zasadnicza.
    Decyzja użytkownika 13.09.2026: „ilości mają iść z SUBIEKTA".
    Subiekt jest właścicielem faktu magazynowego, więc arkusz ma pokazywać
    JEGO stan, a nie sumę tego, co RM_BAZA zdążyła zaobserwować. Dodawanie
    („+= to, co właśnie wydałem") rozjeżdżałoby się przy każdym RW
    wystawionym poza RM_BAZA, przy powtórzonym zapisie i po korekcie
    dokumentu w Subiekcie.

    „Wydane z magazynu" i „dostarczone od dostawcy" to dla PROJEKTU jeden
    fakt: detal dotarł i można go montować („wydane to ma iść do odebrane").

    Pomijamy symbole, których nie ma w BOM-ie — nie ma gdzie zapisać.
    """
    if con is None or not project_id or not wydane:
        return 0
    teraz = datetime.now().isoformat()
    ile = 0
    for symbol, ilosc in wydane.items():
        item_id = znajdz_w_bom(con, project_id, symbol)
        if not item_id:
            continue
        con.execute(
            "UPDATE items"
            "   SET delivered_qty = ?, delivered_updated_at = ?, updated_at = ?"
            " WHERE id = ? AND COALESCE(delivered_qty, -1) <> ?",
            (float(ilosc), teraz, teraz, item_id, float(ilosc)))
        ile += con.total_changes and 1 or 0
    con.commit()
    return ile


# ── poczekalnia w master (gdy lock trzyma ktoś inny) ────────────────────────
def odloz_w_master(serwer, project_id, pozycje, kto=None):
    """Zapisuje brakujące wiersze do poczekalni. Zwraca liczbę odłożonych.

    Wołane, gdy nie mamy locka. Nałoży je arkusz przy „Przejmij Lock" —
    ten sam przebieg co `_naloz_zamowienia_zd()` dla wysyłki ZD.
    """
    if not pozycje:
        return 0
    teraz = datetime.now().isoformat(timespec="seconds")
    operacje = [{
        "operation": "schowek-nowe-dodaj",
        "params": {"project_id": project_id,
                   "symbol": (p["symbol"] or "").strip(),
                   "nazwa": (p.get("nazwa") or "").strip(),
                   "kto": (kto or "").strip(),
                   "kiedy": teraz},
    } for p in pozycje]
    try:
        serwer.master_batch(operacje)
    except Exception as e:
        raise BladBom("Nie udało się odłożyć nowych pozycji w master:\n%s" % e)
    return len(operacje)


def naloz_z_mastera(serwer, con, project_id, log=None):
    """Nakłada odłożone wiersze na OTWARTĄ POD LOCKIEM kopię projektu.

    Zwraca liczbę dopisanych. NIE kasuje wierszy z master — to robi
    `usun_z_mastera()` po udanym wgraniu kopii na serwer, dokładnie jak
    przy ZD. Dzięki temu „Anuluj" ani padnięcie sieci nie gubi pozycji:
    następny lock nałoży ją ponownie.

    Nakładanie jest IDEMPOTENTNE — `dodaj_do_bom` sprawdza duplikat, więc
    powtórka nic nie psuje, a pozycja dodana w międzyczasie ręcznie po
    prostu wygrywa.
    """
    if con is None or not project_id:
        return 0
    try:
        wiersze = serwer.master_read("schowek-nowe-list",
                                     {"project_id": project_id})
    except Exception as e:
        print("⚠️  Nie odczytano odłożonych pozycji schowka dla projektu "
              "%s: %s" % (project_id, e))
        return 0
    ile = 0
    for w in wiersze or ():
        symbol = (w.get("symbol") or "").strip()
        if not symbol:
            continue
        if znajdz_w_bom(con, project_id, symbol):
            continue                          # ktoś dodał ręcznie — nic nie robimy
        try:
            item_id = dodaj_do_bom(con, project_id, symbol, w.get("nazwa"))
        except Exception as e:
            print("⚠️  Nie dopisano pozycji %s: %s" % (symbol, e))
            continue
        ile += 1
        if log:
            try:
                log(item_id, "ADD", None, None, symbol,
                    drawing_no=symbol, item_name=w.get("nazwa") or symbol)
            except Exception:
                pass                          # log nie może psuć nakładania
    return ile


def usun_z_mastera(serwer, project_id, do_kiedy=None):
    """Sprząta poczekalnię PO udanym wgraniu kopii na serwer.

    ⚠️ `do_kiedy` NIE jest ozdobnikiem. Master jest wspólny: między
    nałożeniem a wgraniem kopii ktoś inny mógł dołożyć swój wpis dla tego
    samego projektu. Kasowanie „wszystkiego dla project_id" zabrałoby cudzy
    świeży wpis, zanim ktokolwiek go nałożył — dokładnie ten błąd złapano
    przy ZD 08.09.2026 (patrz `_naloz_zamowienia_zd`, znacznik
    `_zd_bufor_do`).
    """
    try:
        serwer.master_exec("schowek-nowe-usun",
                           {"project_id": project_id, "do_kiedy": do_kiedy})
    except Exception as e:
        print("⚠️  Nie wyczyszczono poczekalni schowka: %s" % e)


# ── całość: przygotowanie BOM-u przed RW ────────────────────────────────────
def przygotuj(con, serwer, project_id, pozycje, mamy_lock, kto=None):
    """Zapewnia, że każda pozycja ze schowka ma gdzie wylądować.

    Zwraca `(dopisane, odlozone)` — liczby do pokazania magazynierowi.
    Rzuca `BladBom`, gdy czegoś NIE UDAŁO się zapisać: wtedy wołający
    MUSI przerwać i nie wystawiać RW (reguła nadrzędna z nagłówka).

    `mamy_lock` — czy arkusz trzyma lock TEGO projektu; przy schowku
    ogólnym (bez projektu) wołający w ogóle tu nie zagląda.
    """
    if not project_id or not pozycje:
        return 0, 0
    _, brak = podziel(con, project_id, pozycje)
    if not brak:
        return 0, 0

    if mamy_lock and con is not None:
        dopisane = 0
        for p in brak:
            try:
                dodaj_do_bom(con, project_id, p["symbol"], p.get("nazwa"))
                dopisane += 1
            except Exception as e:
                raise BladBom(
                    "Nie udało się dopisać pozycji „%s” do arkusza:\n%s\n\n"
                    "RW NIE zostało wystawione — wydanie nie miałoby się "
                    "do czego przypiąć." % (p["symbol"], e))
        return dopisane, 0

    # Bez locka: wiersz idzie do poczekalni. To też jest potwierdzenie —
    # pozycja na pewno powstanie, najpóźniej przy następnym przejęciu.
    return 0, odloz_w_master(serwer, project_id, brak, kto)
