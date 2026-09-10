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

# Reguła Uwag/Tytułu jest WSPÓLNA dla wszystkich dokumentów — jedno miejsce,
# żeby zapis i odczyt nie rozjechały się przy zmianie formatu (patrz
# subiekt_zamowienia.numer_projektu_z_uwag i Znacznik.cs po stronie mostu).
from subiekt_zamowienia import (MARKER, nasz_dokument, numer_projektu_z_uwag,
                               tytul_dokumentu, zloz_uwagi)

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


def project_id_z_polaczenia(con):
    """id projektu z otwartego połączenia — z nazwy pliku „project_71.sqlite".

    Kalkulator dostaje `project_con`, nie id, a lista do PW musi czytać bazę
    OSOBNYM połączeniem read-only (żeby nie wisieć na cudzej transakcji).
    """
    try:
        for _seq, name, file in con.execute("PRAGMA database_list"):
            if name == "main" and file:
                base = os.path.basename(file)
                if base.startswith("project_") and base.endswith(".sqlite"):
                    return int(base[len("project_"):-len(".sqlite")])
    except Exception:
        pass
    return None


def lista_do_pw(project_id, projects_dir=None):
    """Pozycje projektu, które wejdą na PW. Źródłem jest BAZA, nie GUI.

    Zwraca (pozycje, pominiete_komplety):

        pozycje  – [{item_id, symbol, nazwa, ilosc, cena, typ}] posortowane
                   po symbolu; `cena` bywa None (pozycja nieprzeliczona)
        pominiete_komplety – [{symbol, nazwa}] złożenia Z/ZZ produkcji własnej,
                   które świadomie NIE wchodzą na PW (powstają ze składników)

    Czytamy WSZYSTKIE pozycje projektu i filtrujemy tutaj, bo reguła
    „co jest nasze" zależy od typu, nie tylko od `supplier_id` (złożenie bez
    dostawcy też jest nasze) — SQL-em po samym supplier_id by tego nie złapał.

    Filtry GUI (szukanie, „tylko niedostarczone", zakres cen) NIE MAJĄ tu
    wpływu: dokument buduje się z pełnej listy z bazy. Inaczej user
    z zawężonym widokiem wystawiłby PW na 8 z 30 pozycji i dowiedział się
    o tym po fakcie (ustalenia §8).
    """
    import os as _os
    if projects_dir is None:
        try:
            from subiekt_stany import PROJECTS_DIR as projects_dir
        except Exception:
            projects_dir = r"C:\RMPAK_CLIENT\RM_MANAGER\RM_BAZA\projects"
    path = _os.path.join(projects_dir, f"project_{project_id}.sqlite")
    if not _os.path.isfile(path):
        raise FileNotFoundError(path)

    id_prod = id_dostawcow_produkcji()
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info('items')")}
        typ_cols = [c for c in ("class_manual", "class_effective", "class_auto")
                    if c in cols]
        # Ukryte pozycje nie trafiają do Subiekta — ten sam warunek co wszędzie.
        where = " WHERE COALESCE(is_hidden, 0) = 0" if "is_hidden" in cols else ""
        sel = ("id, COALESCE(work_drawing_no, norm_drawing_no, src_drawing_no, ''), "
               "COALESCE(work_name, src_name, ''), "
               "order_qty, work_qty, src_qty, price_pln, supplier_id, "
               + ("COALESCE(" + ", ".join(typ_cols) + ", '')" if typ_cols else "''"))
        rows = con.execute(f"SELECT {sel} FROM items{where}").fetchall()
    finally:
        con.close()

    pozycje, pominiete = [], []
    for (item_id, nr, nazwa, oq, wq, sq, cena, sup_id, typ) in rows:
        if not czy_produkcja_wlasna(sup_id, typ, id_prod):
            continue
        symbol = (nr or "").strip() or (nazwa or "").strip()
        if not symbol:
            continue                      # bez symbolu nie ma czego przyjąć
        if not na_pw(typ):
            pominiete.append({"symbol": symbol, "nazwa": nazwa or symbol})
            continue
        pozycje.append({
            "item_id": item_id,
            "symbol": symbol,
            "nazwa": nazwa or symbol,
            "ilosc": ilosc_produkcyjna(oq, wq, sq),
            "cena": float(cena) if cena not in (None, "") else None,
            "typ": (typ or "").strip(),
        })
    pozycje.sort(key=lambda p: p["symbol"])
    pominiete.sort(key=lambda p: p["symbol"])
    return pozycje, pominiete


def braki_przed_pw(pozycje):
    """Czego brakuje, żeby wystawić PW. [] = można wystawiać.

    Zwraca [(symbol, czego_brak)] — nie sam komunikat, żeby GUI mogło
    pokazać to przy konkretnym wierszu i dać przycisk „Załóż kartotekę".

    Kartoteki w Subiekcie tu NIE sprawdzamy: to pytanie do mostu, a ta
    funkcja ma działać też bez połączenia (i szybko, przy każdym odświeżeniu
    listy). Brak kartoteki wychodzi w suchym przebiegu PW.
    """
    braki = []
    for p in pozycje:
        if not p.get("ilosc") or p["ilosc"] <= 0:
            braki.append((p["symbol"], "brak ilości"))
        if p.get("cena") is None or p["cena"] <= 0:
            braki.append((p["symbol"], "brak ceny"))
    return braki


def plan_pw(project_id, numer_projektu, pozycje, magazyn="MASTER"):
    """Plan dla mostu (tryb „pw"). Sam słownik — bez zapisu i bez sieci.

    `uwagi` niosą numer projektu, bo tak firma oznacza dokumenty i tak po
    nich filtruje (F8 / kolumna Uwagi) — ten sam wzorzec co ZK. Znacznik
    RM_BAZA idzie osobno, w Tytule (patrz MARKER).
    """
    return {
        "pozycje": [{"symbol": p["symbol"],
                     "ilosc": p["ilosc"],
                     "cena": p["cena"]} for p in pozycje],
        "uwagi": zloz_uwagi(numer_projektu),
        "tytul": tytul_dokumentu(numer_projektu),
        "magazyn": magazyn,
    }


def wyslij_pw(plan, zapisz=False, timeout=600):
    """Suchy przebieg (zapisz=False) albo REALNY zapis PW. Zwraca dict mostu.

    Bez ponawiania po niejednoznacznym błędzie: powtórzenie zrobiłoby drugi
    dokument przyjęcia, a tego nie da się cofnąć jednym kliknięciem.
    """
    from subiekt_stany import _find_exe, CONFIG_PATH
    if not _find_exe():
        raise RuntimeError(
            "Nie znaleziono NexoRecon.exe.\n\n"
            "Zbuduj most:\n  cd subiekt_sfera\\NexoRecon\n  dotnet build -c Release")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")

    args = {"plan": plan}
    if zapisz:
        args["zapisz"] = True
    import subiekt_bridge
    return subiekt_bridge.call("pw", args, timeout=timeout, write=zapisz)


def sprawdz_pw(wynik, plan):
    """Read-back: czy to, co Subiekt zapisał, zgadza się z planem.

    Zwraca (ok, numer, uwagi). Sukcesu NIE wolno ogłosić tylko dlatego, że
    nie było wyjątku (ustalenia §13) — dokument mógł powstać niepełny albo
    z inną ceną.

    Porównujemy PO WIERSZACH, nie po sumie na symbol: ten sam detal bywa na
    dokumencie w kilku wierszach po różnych cenach (widać to na PW demo),
    więc zsumowanie zatarłoby różnicę.
    """
    numer = (wynik or {}).get("numer") or ""
    if not (wynik or {}).get("zapisano") or not numer:
        return False, numer, ["Subiekt nie potwierdził zapisu dokumentu."]

    oczek = {}
    for p in plan.get("pozycje", []):
        klucz = (str(p["symbol"]).strip().upper(), round(float(p["ilosc"]), 3),
                 round(float(p["cena"] or 0), 2))
        oczek[klucz] = oczek.get(klucz, 0) + 1

    try:
        import subiekt_bridge
        dane = subiekt_bridge.call("dokumenty", {"limit": 400}, timeout=300, write=False)
        dok = next((d for d in (dane or {}).get("dokumenty", [])
                    if d.get("Rodzaj") == "PW" and d.get("Numer") == numer), None)
    except Exception as e:
        return False, numer, [f"Nie udało się odczytać PW z Subiekta: {e}"]
    if dok is None:
        return False, numer, [f"Zapisany dokument {numer} nie został odnaleziony przy odczycie."]

    mam = {}
    for p in dok.get("Pozycje", []):
        klucz = (str(p.get("Symbol", "")).strip().upper(),
                 round(float(p.get("Ilosc") or 0), 3),
                 round(float(p.get("Cena") or 0), 2))
        mam[klucz] = mam.get(klucz, 0) + 1

    uwagi = []
    for k, ile in oczek.items():
        if mam.get(k, 0) < ile:
            uwagi.append(f"{k[0]}: plan {k[1]:g} × {k[2]:.2f} — nie znaleziono na dokumencie")
    for k, ile in mam.items():
        if oczek.get(k, 0) < ile:
            uwagi.append(f"{k[0]}: na dokumencie {k[1]:g} × {k[2]:.2f} — nie było w planie")
    return (not uwagi), numer, uwagi


#: Marker w polu TYTUŁ dokumentu — po nim RM_BAZA rozpoznaje SWOJE PW/RW.
#: Bez niego numery trzeba by trzymać lokalnie, a baza projektu bez locka
#: jest READ-ONLY: zapis się nie udawał i dokument istniał w Subiekcie,
#: o którym RM_BAZA nie wiedziała (PW 2/MASTER/2026, 10.09.2026).
#:
#: Subiekt jest źródłem prawdy dla wystawionego dokumentu (§21 v2), więc
#: czytamy stamtąd i nie ma czego trzymać po dwóch stronach.
#:
#: PRZEPROWADZKA Z UWAG DO TYTUŁU (10.09.2026)
#: Marker siedział w Uwagach jako „RM_BAZA — PROJEKT 2741". Nie może tam
#: zostać, odkąd pierwszy wiersz Uwag jest numerem projektu: z przodu się nie
#: mieści, a doklejony niżej byłby nie do odróżnienia od uwagi człowieka.
#: Tytuł nadaje się lepiej — nie drukuje się i nikt nie wypełnia go ręcznie,
#: więc jego obecność naprawdę świadczy o pochodzeniu dokumentu.
#:
#: Sama stała mieszka w subiekt_zamowienia (importowana na górze pliku) —
#: dwie kopie rozjechałyby się przy pierwszej zmianie.


def dokumenty_produkcji(numer_projektu, timeout=600):
    """{"PW": [...], "RW": [...]} — dokumenty produkcji tego projektu z SUBIEKTA.

    Rozpoznanie dwuczłonowe (10.09.2026):
      • TYTUŁ musi nieść znacznik RM_BAZA — dowód, że to nasz dokument,
      • pierwszy człon UWAG musi być tym numerem projektu.

    Sam numer nie wystarcza: użytkownik wystawiający RW ręcznie w Subiekcie
    też wpisuje numer projektu w Uwagi, a taki dokument nie może trafić do
    RW jako źródło. Nie trzymamy tych numerów lokalnie — patrz MARKER.

    Każdy wpis: {numer, data, uwagi, pozycje: [{symbol, nazwa, ilosc, cena}]}.
    Rzuca wyjątkiem tylko przy błędzie połączenia; brak dokumentów to nie błąd.
    """
    import subiekt_bridge
    dane = subiekt_bridge.call("dokumenty", {"limit": 400}, timeout=timeout, write=False)
    cel = str(numer_projektu or "").strip().upper()
    out = {"PW": [], "RW": []}
    for d in (dane or {}).get("dokumenty", []):
        rodzaj = d.get("Rodzaj")
        if rodzaj not in out:
            continue
        uwagi = str(d.get("Uwagi") or "").strip()
        # Znacznik w Tytule odsiewa dokumenty wystawione ręcznie w Subiekcie
        # albo przez inne narzędzie — te nie są „nasze" i nie wolno ich brać
        # za źródło RW. Numer z Uwag zawęża do TEGO projektu.
        if not nasz_dokument(d.get("Tytul")):
            continue
        if cel and numer_projektu_z_uwag(uwagi).upper() != cel:
            continue
        out[rodzaj].append({
            "numer": d.get("Numer") or "",
            "data": d.get("Data") or "",
            "uwagi": uwagi,
            "wartosc": float(d.get("Wartosc") or 0),
            "pozycje": [{"symbol": (p.get("Symbol") or "").strip(),
                         "nazwa": p.get("Nazwa") or "",
                         "ilosc": float(p.get("Ilosc") or 0),
                         "cena": float(p.get("Cena") or 0)}
                        for p in (d.get("Pozycje") or []) if (p.get("Symbol") or "").strip()],
        })
    for k in out:
        out[k].sort(key=lambda x: x["numer"])
    return out


def pw_do_rw(numer_projektu, timeout=600):
    """Pozycje potwierdzonego PW — źródło dla RW. Zwraca (pozycje, numer, blad).

    RW NIE jest budowane z BOM-u ani z kalkulatora (§11 ustaleń): bierze
    dokładnie to, co przyjęło PW. Dzięki temu przyjęcie i wydanie nie
    rozjadą się, nawet gdy ktoś później zmieni ilości w projekcie.
    """
    try:
        dok = dokumenty_produkcji(numer_projektu, timeout)
    except Exception as e:
        return [], None, f"Nie udało się odczytać dokumentów z Subiekta: {e}"

    pw = dok["PW"]
    if not pw:
        return [], None, ("Nie znaleziono PW tego projektu w Subiekcie. "
                          "Najpierw wystaw PW — RW powstaje z przyjęcia, nie z BOM-u.")
    if len(pw) > 1:
        numery = ", ".join(d["numer"] for d in pw)
        return [], None, (f"Dla tego projektu istnieje kilka PW ({numery}). "
                          "RM_BAZA nie wie, z którego budować RW — zostaw jedno, "
                          "usuwając zbędne w Subiekcie.")
    if not pw[0]["pozycje"]:
        return [], pw[0]["numer"], f"PW {pw[0]['numer']} nie ma pozycji."
    return pw[0]["pozycje"], pw[0]["numer"], None


def plan_rw(numer_projektu, pozycje, numer_pw, magazyn="MASTER"):
    """Plan dla mostu (tryb „rw"). Ilości PROSTO Z PW, bez przeliczania.

    BEZ CENY — decyzja użytkownika z 10.09.2026: „PW z ceną, RW bez ceny".
    I tak ma być: RW nie jest przez to bezwartościowe.

    Cena netto to parametr HANDLOWY i na dokumencie magazynowym zostaje
    zerowa. Wartość rozchodu niesie KOSZT MAGAZYNOWY, który Subiekt liczy
    SAM z ceny przyjęcia — sprawdzone na RW 1/MASTER/2026: cena netto 0,
    a `KosztMagazynowy` 4848 zł, dokładnie tyle co PW.

    Dlatego ceny NIE wpisujemy: gdyby ten sam detal leżał na magazynie
    w kilku partiach po różnych cenach, ręczna wartość rozjechałaby się
    z metodą wyceny rozchodu, którą stosuje magazyn.

    W Uwagach numer projektu ORAZ źródłowe PW — żeby z samego dokumentu
    w Subiekcie dało się odczytać, skąd się wziął (§16 v2). Numer PW idzie
    do DRUGIEGO wiersza, na miejsce uwag człowieka: pierwszy wiersz należy
    do numeru projektu, a Uwagi to jedyne z tych pól, które się drukuje.
    """
    return {
        "pozycje": [{"symbol": p["symbol"], "ilosc": p["ilosc"]} for p in pozycje],
        "uwagi": zloz_uwagi(numer_projektu, f"PW: {numer_pw}"),
        "tytul": tytul_dokumentu(numer_projektu),
        "magazyn": magazyn,
    }


def wyslij_rw(plan, zapisz=False, timeout=600):
    """Suchy przebieg (zapisz=False) albo REALNY zapis RW."""
    from subiekt_stany import _find_exe, CONFIG_PATH
    if not _find_exe():
        raise RuntimeError(
            "Nie znaleziono NexoRecon.exe.\n\n"
            "Zbuduj most:\n  cd subiekt_sfera\\NexoRecon\n  dotnet build -c Release")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")
    args = {"plan": plan}
    if zapisz:
        args["zapisz"] = True
    import subiekt_bridge
    return subiekt_bridge.call("rw", args, timeout=timeout, write=zapisz)


def sprawdz_rw(wynik, plan, numer_pw):
    """Read-back RW: czy wydano dokładnie to, co przyjęło PW.

    Zwraca (ok, numer, uwagi). Porównanie PO WIERSZACH (symbol, ilość) —
    ten sam powód co przy PW: jeden symbol bywa na dokumencie w kilku
    wierszach i suma zatarłaby różnicę.
    """
    numer = (wynik or {}).get("numer") or ""
    if not (wynik or {}).get("zapisano") or not numer:
        return False, numer, ["Subiekt nie potwierdził zapisu dokumentu."]

    oczek = {}
    for p in plan.get("pozycje", []):
        k = (str(p["symbol"]).strip().upper(), round(float(p["ilosc"]), 3))
        oczek[k] = oczek.get(k, 0) + 1
    try:
        import subiekt_bridge
        dane = subiekt_bridge.call("dokumenty", {"limit": 400}, timeout=300, write=False)
        dok = next((d for d in (dane or {}).get("dokumenty", [])
                    if d.get("Rodzaj") == "RW" and d.get("Numer") == numer), None)
    except Exception as e:
        return False, numer, [f"Nie udało się odczytać RW z Subiekta: {e}"]
    if dok is None:
        return False, numer, [f"Zapisany dokument {numer} nie został odnaleziony przy odczycie."]

    mam = {}
    for p in dok.get("Pozycje", []):
        k = (str(p.get("Symbol") or "").strip().upper(), round(float(p.get("Ilosc") or 0), 3))
        mam[k] = mam.get(k, 0) + 1
    uwagi = []
    for k, ile in oczek.items():
        if mam.get(k, 0) < ile:
            uwagi.append(f"{k[0]}: z PW {k[1]:g} szt. — nie znaleziono na RW")
    for k, ile in mam.items():
        if oczek.get(k, 0) < ile:
            uwagi.append(f"{k[0]}: na RW {k[1]:g} szt. — nie było na PW {numer_pw}")
    return (not uwagi), numer, uwagi


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
