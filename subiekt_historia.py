# -*- coding: utf-8 -*-
"""Wspólna historia operacji na Subiekcie — jeden katalog dla wszystkich stanowisk.

    import subiekt_historia
    subiekt_historia.zapisz_historie("projekt", wynik, project_id=71, plan=plan)
    subiekt_historia.zapisz_historie("zd", wynik, projekty=["3500"])
    logi = subiekt_historia.znajdz_logi("projekt", project_id=71)

PO CO TO JEST
-------------
Każde okno Subiekta pisało swój ślad do LOKALNEGO `C:\\RMPAK_CLIENT\\subiekt_logi`,
osobno i w innym formacie. W pracy jednoosobowej to wystarczało, ale przy kilku
stanowiskach się rozjeżdża (zgłoszone 08.09.2026):

    „w wersji sieciowej każdy user musi mieć do tego dostęp,
     bo jeden zapisuje, inny może chcieć skasować"

Najostrzej widać to przy cofaniu projektu: czyta ono plan z logu zakładania,
więc gdyby log leżał tylko lokalnie, cofnąć mógłby WYŁĄCZNIE ten, kto zakładał.
Kolega z drugiego stanowiska zobaczyłby „brak zapisanego logu", choć projekt
w Subiekcie normalnie istnieje.

GDZIE
-----
Katalog `subiekt_historia` obok `master.sqlite`, czyli tam, gdzie i tak leży
wspólna baza. Ścieżka liczona z konfiguracji (PROJECTS_DIR z sync_config.json),
nigdy zaszyta na sztywno — na każdym stanowisku wskaże ten sam folder.

DLACZEGO PLIKI, A NIE TABELA W master.sqlite
--------------------------------------------
master chodzi pod lockiem i jest krytyczny dla pracy — historia to zapis „obok",
którego awaria (zajęty plik, brak sieci) nie może zablokować zapisu do Subiekta
ani pracy na arkuszu. Pliki JSON są też czytelne bez narzędzi, co przy
sprzątaniu po błędzie bywa ważniejsze niż wygoda zapytań.

ZAWSZE DWA MIEJSCA
------------------
Zapis idzie na serwer I lokalnie. Serwer jest źródłem prawdy dla wszystkich,
lokalny ślad zostaje, gdy serwer akurat niedostępny — i nie przepada wtedy
informacja, co ta maszyna zrobiła w Subiekcie.
"""

import json
import os
from datetime import datetime

from subiekt_stany import PROJECTS_DIR

#: Lokalny ślad tej maszyny — ten sam katalog, którego moduły używały dotąd.
LOG_DIR_LOKALNY = r"C:\RMPAK_CLIENT\subiekt_logi"


def historia_dir():
    """Wspólny katalog historii na serwerze — obok master.sqlite."""
    return os.path.join(os.path.dirname(PROJECTS_DIR.rstrip("\\/")), "subiekt_historia")


def zapisz_historie(rodzaj, wynik, project_id=None, plan=None, **dodatkowe):
    """Zapisuje ślad operacji do obu katalogów. Zwraca ścieżkę serwerową (albo lokalną).

    `rodzaj` to prefiks pliku i zarazem rodzaj operacji: "projekt", "zd",
    "zd-usun", "rw", "pw", "projekt-cofnij"…
    `project_id` (gdy podany) wchodzi do nazwy pliku, żeby dało się szukać
    logów jednego projektu bez otwierania wszystkich.
    `plan` to plan wysłany do mostu — bez niego cofnięcie nie ma czego użyć.
    `dodatkowe` dopisuje dowolne pola (np. projekty=["3500"], dostawca="QUAY").

    Nigdy nie rzuca — brak dostępu do serwera nie może wywalić operacji,
    która w Subiekcie już się wykonała.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nazwa = (f"{rodzaj}_{project_id}_{stamp}.json" if project_id
             else f"{rodzaj}_{stamp}.json")

    zapis = dict(wynik or {})
    if plan is not None:
        zapis["plan"] = plan
    if project_id is not None:
        zapis.setdefault("project_id", project_id)
    zapis.setdefault("rodzaj", rodzaj)
    zapis.setdefault("kto", os.environ.get("USERNAME") or "?")
    zapis.setdefault("komputer", os.environ.get("COMPUTERNAME") or "?")
    zapis.setdefault("kiedy", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    zapis.update(dodatkowe)

    zapisane = []
    for katalog in (historia_dir(), LOG_DIR_LOKALNY):
        try:
            os.makedirs(katalog, exist_ok=True)
            path = os.path.join(katalog, nazwa)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(zapis, f, ensure_ascii=False, indent=1)
            zapisane.append(path)
        except Exception:
            continue          # drugie miejsce nadal może się udać
    return zapisane[0] if zapisane else None


def wczytaj_notatke(project_id):
    """Lista „do zrobienia" projektu — {zadania: [...], tekst, kto, kiedy}.

    Zadanie: {tekst, zrobione, zrodlo, kto, kiedy, zrobil, zrobione_kiedy}.
    `zrodlo` = "auto" (wykryte przez okno) albo "reczne" (dopisane przez usera) —
    auto-zadania są odtwarzane przy każdym podglądzie, więc nie wolno ich
    dublować; ręczne zostają nietknięte.

    Trzymana w tym samym wspólnym katalogu co historia, w JEDNYM pliku na
    projekt (nadpisywanym), nie w kolejnych wpisach: to bieżąca lista rzeczy
    do zrobienia, nie dziennik. Wspólna, bo notuje jeden, a robi często ktoś
    inny (zgłoszone 08.09.2026).
    """
    nazwa = f"notatka_{project_id}.json"
    for katalog in (historia_dir(), LOG_DIR_LOKALNY):
        try:
            with open(os.path.join(katalog, nazwa), encoding="utf-8") as f:
                dane = json.load(f)
            dane.setdefault("zadania", [])
            return dane
        except Exception:
            continue
    return {"project_id": project_id, "zadania": [], "tekst": ""}


def zapisz_notatke(project_id, zadania=None, tekst=None):
    """Zapisuje listę zadań i notatkę projektu w obu katalogach."""
    stare = wczytaj_notatke(project_id) or {}
    dane = {
        "project_id": project_id,
        "zadania": stare.get("zadania", []) if zadania is None else zadania,
        "tekst": stare.get("tekst", "") if tekst is None else tekst,
        "kto": os.environ.get("USERNAME") or "?",
        "komputer": os.environ.get("COMPUTERNAME") or "?",
        "kiedy": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    nazwa = f"notatka_{project_id}.json"
    zapisane = []
    for katalog in (historia_dir(), LOG_DIR_LOKALNY):
        try:
            os.makedirs(katalog, exist_ok=True)
            path = os.path.join(katalog, nazwa)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(dane, f, ensure_ascii=False, indent=1)
            zapisane.append(path)
        except Exception:
            continue
    return zapisane[0] if zapisane else None


def scal_zadania(project_id, wykryte):
    """Dokłada auto-zadania, których jeszcze nie ma, zachowując odhaczenia.

    `wykryte` to lista tekstów wyliczonych przez okno przy podglądzie. Zadanie
    już obecne (ten sam tekst) NIE jest dodawane drugi raz ani odznaczane —
    inaczej każde odświeżenie kasowałoby to, co user zdążył odhaczyć.
    Zwraca pełną listę zadań.
    """
    dane = wczytaj_notatke(project_id) or {"zadania": []}
    zadania = dane.get("zadania", [])
    # Porównujemy po treści ORYGINALNEJ (`auto_tekst`), nie po bieżącej: user
    # często dopisuje do auto-zadania ustalenie („czeka na rysunek od…"), a bez
    # tego kolejny podgląd wstawiłby oryginał jeszcze raz i miałby dwa wpisy
    # o tym samym (sprawdzone 08.09.2026).
    istnieje = {z.get("auto_tekst") or z.get("tekst") for z in zadania}
    teraz = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nowe = [{"tekst": t, "auto_tekst": t, "zrobione": False, "zrodlo": "auto",
             "kto": os.environ.get("USERNAME") or "?", "kiedy": teraz}
            for t in wykryte if t not in istnieje]
    if nowe:
        zadania = zadania + nowe
        zapisz_notatke(project_id, zadania=zadania)
    return zadania


def znajdz_logi(rodzaj=None, project_id=None, wymagaj_planu=False, limit=200):
    """[(ścieżka, dane)] — najnowsze pierwsze, z serwera i lokalnie bez duplikatów.

    Ten sam plik w obu katalogach to jeden zapis; wersja serwerowa wygrywa,
    bo tam trafiają zapisy wszystkich stanowisk.
    """
    if project_id is not None and rodzaj:
        prefiks = f"{rodzaj}_{project_id}_"
    elif rodzaj:
        prefiks = f"{rodzaj}_"
    else:
        prefiks = ""

    widziane, wyniki = set(), []
    for katalog in (historia_dir(), LOG_DIR_LOKALNY):
        try:
            pliki = [f for f in os.listdir(katalog)
                     if f.startswith(prefiks) and f.endswith(".json")]
        except OSError:
            continue                     # serwer niedostępny — zostaje lokalny
        for f in sorted(pliki, reverse=True)[:limit]:
            if f in widziane:
                continue
            try:
                with open(os.path.join(katalog, f), encoding="utf-8") as fh:
                    dane = json.load(fh)
            except Exception:
                continue
            if wymagaj_planu and not dane.get("plan"):
                continue
            widziane.add(f)
            wyniki.append((os.path.join(katalog, f), dane))

    wyniki.sort(key=lambda x: os.path.basename(x[0]), reverse=True)
    return wyniki[:limit]
