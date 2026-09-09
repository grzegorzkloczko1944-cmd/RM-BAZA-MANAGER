"""Produkcja własna RMPAK — jedno miejsce, które wie, co robimy u siebie.

RMPAK jest PRODUCENTEM, nie zamawia detali u siebie. Stąd rozdzielenie torów
(RMPAK_PRODUKCJA_USTALENIA.md §2):

    Dostawca ≠ RMPAK  → tor zakupowy       → ZK / Subiekt
    Dostawca = RMPAK  → tor produkcji      → BOM / projekt → PW → RW

Ten moduł odpowiada TYLKO na pytanie „czy ta pozycja jest nasza" i podaje
ilość produkcyjną. Świadomie NIE zna Subiekta ani Tkintera: ten sam warunek
czyta okno projektu (żeby nie wpisać detalu RMPAK na ZK) i kalkulator (żeby
zebrać listę do PW). Skopiowany osobno do dwóch modułów rozjechałby się przy
pierwszej zmianie listy dostawców.
"""

import os
import sqlite3

#: Dostawcy oznaczający produkcję własną. To NAZWY z master.sqlite → suppliers,
#: nie id — id różnią się między instalacjami (dom/firma), nazwy nie.
#:
#: Stan zastany 2026-09-09: „RMPAK+" z dokumentu w bazie NIE ISTNIEJE. Są za to
#: „RMPAK" (290 poz.) i „RMPAK + materiał" (21 poz.) — to drugie jest tym, co
#: dokument nazywa RMPAK+ (nasza robota + półprodukt od dostawcy). Docelowo
#: zostaje jeden „RMPAK", a różnica idzie w calc_mode (cut/semi), ale dopóki
#: w bazie są oba, proces nie może gubić pozycji.
#:
#: „DAGAR + RMPAK" (14 poz.) NIE jest tu celowo: kooperacja, gdzie część robi
#: firma zewnętrzna. Nierozstrzygnięte, czy to PW czy ZK — do ustalenia
#: z użytkownikiem, zanim trafi na którykolwiek dokument.
DOSTAWCY_PRODUKCJA = ("RMPAK", "RMPAK + materiał")


def _sciezka_master():
    """master.sqlite — ta sama ścieżka co reszta RM_BAZA."""
    try:
        from subiekt_stany import PROJECTS_DIR
        return os.path.join(os.path.dirname(PROJECTS_DIR), "master.sqlite")
    except Exception:
        return r"C:\RMPAK_CLIENT\RM_MANAGER\RM_BAZA\master.sqlite"


def id_dostawcow_produkcji(master_path=None):
    """{supplier_id} dla dostawców produkcji własnej.

    Pusty zbiór, gdy bazy nie ma albo nie ma tabeli — wtedy NIC nie jest
    produkcją własną i wszystko idzie starą drogą na ZK. To bezpieczniejsza
    strona błędu niż odwrotna: pominięcie pozycji na ZK jest widoczne dopiero
    przy dostawie, a nadmiarowa pozycja rzuca się w oczy od razu.
    """
    path = master_path or _sciezka_master()
    if not os.path.isfile(path):
        return set()
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return {r[0] for r in con.execute(
                "SELECT supplier_id FROM suppliers WHERE name IN "
                f"({','.join('?' * len(DOSTAWCY_PRODUKCJA))})",
                DOSTAWCY_PRODUKCJA)}
        finally:
            con.close()
    except sqlite3.Error:
        return set()


#: Typy, które NIE wchodzą na PW. RMPAK z elementów TW składa ZZ — czyli
#: z towarów robi u siebie komplet. W Subiekcie komplet (KT) nie ma własnego
#: stanu: jego stan wynika ze stanu składników. Przyjęcie kompletu OBOK jego
#: części byłoby przyjęciem tego samego dwa razy.
#:
#: Komplety zostają w planie projektu i mają pełny skład — filtr ZK (§9)
#: celowo nie rusza budowy kartotek. Chodzi wyłącznie o to, czego NIE
#: przyjmować dokumentem PW.
TYPY_KOMPLETOW = ("Z", "ZZ")


def na_pw(typ):
    """Czy taka pozycja wchodzi na PW.

    True dla TW (STANDARD / X / XX / cokolwiek innego), False dla kompletów.
    Nieznany typ traktujemy jak TW — pozycja pojawi się na liście do PW
    i user ją zobaczy, zamiast zniknąć bez śladu.
    """
    return str(typ or "").strip().upper() not in TYPY_KOMPLETOW


def czy_produkcja_wlasna(supplier_id, typ, id_produkcji):
    """Czy tę pozycję robimy u siebie. Jedno miejsce na całą regułę.

    Dwie drogi do „nasze":

    1. DOSTAWCA to RMPAK — dotyczy każdego typu, także detali TW.
    2. ZŁOŻENIE Z/ZZ bez wskazanego dostawcy — złożenie z definicji powstaje
       przez SKŁADANIE, a składamy u siebie. Pustego pola nie traktujemy jak
       „nie wiadomo": dla kompletu brak dostawcy znaczy, że nikt go nie
       dostarcza, bo robimy go sami.

    Wyjątek od 2: gdy ktoś wpisał przy złożeniu REALNEGO dostawcę (np. MAJA),
    zespół jest kupowany gotowy i zostaje na ZK. To świadoma decyzja
    człowieka wyrażona w polu, które już istnieje i już znaczy „kto to
    dostarcza" — nie dokładamy drugiego mechanizmu obok.

    Stan zastany na projekcie 22 (50 złożeń): 25 bez dostawcy + 13 RMPAK
    idzie na PW, 9 od MAJA zostaje na ZK.
    """
    if supplier_id is not None and supplier_id in id_produkcji:
        return True
    if str(typ or "").strip().upper() in TYPY_KOMPLETOW:
        return supplier_id is None
    return False


def ilosc_produkcyjna(order_qty, work_qty, src_qty):
    """Ile sztuk wytwarzamy — z PROJEKTU, świadomie z pominięciem order_qty.

    `order_qty` to ilość Z ZAMÓWIENIA (ZK) i dla pozycji kupowanych jest
    właściwym źródłem — Subiekt wie, ile realnie zamówiono. Ale detalu
    własnego nie zamawiamy, więc order_qty albo jest puste, albo pochodzi
    ze starego ZK sprzed tego ustalenia. Ilość produkcyjną zna wyłącznie
    projekt.

    Uwaga na kolejność: `read_project_items` czyta
    COALESCE(order_qty, work_qty, src_qty) — dla PW to ZŁA kolejność, bo
    order_qty jest pierwsze. Stąd ta funkcja zamiast powtórzenia COALESCE.
    """
    for v in (work_qty, src_qty):
        if v in (None, ""):
            continue
        try:
            ile = float(str(v).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if ile > 0:
            return ile
    return 0.0
