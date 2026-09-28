# -*- coding: utf-8 -*-
"""subiekt_kopia_zlecenia.py — wykonawca zleceń synchronizacji kopii Subiekta.

    MAG (Inventor) ──POST /mag/synchronizuj──► serwer: zlecenia_sync (nowe)
                                                        │
    RM_BAZA na stacji z mostem  ◄── co 30 s pyta ───────┘
      przejmuje (atomowo) → subiekt_kopia_sync.synchronizuj() → gotowe/blad

Po co: synchronizację zleca się z MAG, ale wykonać ją może tylko stacja
z działającym mostem Sfery (serwer W2019S mostu nie ma). Decyzja 27.09.2026:
nie przywiązywać tego do jednej maszyny — robi to dowolna stacja z mostem,
z pierwszeństwem dla `PREFEROWANE`.

PIERWSZEŃSTWO: komputer z listy przejmuje zlecenie od razu; każdy inny
dopiero, gdy zlecenie czeka dłużej niż `CZEKAJ_NA_PREFEROWANY_S` (preferowany
wyłączony, bez mostu). Z dwóch stacji naraz wygrywa jedna — przejęcie to
`UPDATE … WHERE status='nowe'` na serwerze (rm_serwer_operacje, sekcja
ZLECENIA SYNCHRONIZACJI).

INDEKS MODELI 3D (28.09.2026, decyzja usera): drugi rodzaj zlecenia,
„indeks3d". Zakłada je serwer (co noc po 2:00) albo przycisk „Synchronizuj 3D"
w MAG. Wykonuje DOWOLNA stacja z Inventorem — bez pierwszeństwa, żeby nie być
przywiązanym do jednego komputera. Skrypt NIE jest częścią RM_BAZA: przy
każdym zleceniu pobieramy aktualny `indeks_modeli_3d.py` z serwera
(/mag/skrypt/...) do %TEMP%/RM_MAG i dopiero on decyduje (`moge_wykonac`),
czy ta stacja się nadaje (biblioteka, wersja Inventora). Poprawka skryptu =
podmiana pliku na serwerze, bez nowego .exe.

Wątek-demon, bez Tk. Stanowisko bez mostu i bez Inventora — wątek w ogóle
nie startuje. Błąd serwera albo mostu nie wychodzi
do użytkownika: to praca w tle, a wynik (także błąd) trafia do zlecenia
i widać go w MAG.
"""
from __future__ import annotations

import os
import threading
import time
import traceback

import rm_klient

#: Kto przejmuje zlecenia bez czekania (COMPUTERNAME, wielkie litery).
#: MONGO — firma, szybki i z dobrym łączem do serwera; M-OLD — dom.
PREFEROWANE = ("MONGO", "M-OLD")

#: Ile sekund zlecenie czeka na komputer z listy, zanim weźmie je inny.
CZEKAJ_NA_PREFEROWANY_S = 120

#: Co ile sekund stacja pyta serwer o zlecenie (jedno lekkie zapytanie).
CO_ILE_S = 30

#: Postęp wysyłamy nie częściej niż co tyle sekund — to tylko pasek w MAG.
POSTEP_CO_S = 5

_watek = None


def _komputer():
    return (os.environ.get("COMPUTERNAME") or "?").upper()


def wykonawca_id():
    return "%s/%s" % (_komputer(), os.environ.get("USERNAME") or "?")


def _jest_most():
    """Czy ta stacja w ogóle ma most (binarka + konfiguracja Subiekta)."""
    try:
        import subiekt_bridge
        return bool(subiekt_bridge._find_exe()) and os.path.isfile(subiekt_bridge.CONFIG_PATH)
    except Exception:
        return False


def _jest_inventor():
    """Czy na tej stacji jest Inventor (zarejestrowany ApprenticeServer)."""
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "Inventor.ApprenticeServer"))
        return True
    except Exception:
        return False


#: Port serwera HTTP MAG na tym samym hoście co RM_SERWER.
PORT_MAG = 5061


def pobierz_skrypt(nazwa="indeks_modeli_3d.py"):
    """Świeży skrypt z serwera -> %TEMP%/RM_MAG/<nazwa> -> załadowany moduł.

    Za KAŻDYM zleceniem od nowa (decyzja usera) — zawsze wersja z serwera.
    importlib, nie runpy.run_path: funkcje modułu muszą mieć żywe globals
    przez cały przebieg (moduł trzymamy w zwracanej referencji).
    """
    import importlib.util
    import tempfile
    import urllib.request
    host = getattr(rm_klient, "_host", None) or rm_klient.DOMYSLNY_HOST
    url = "http://%s:%d/mag/skrypt/%s" % (host, PORT_MAG, nazwa)
    with urllib.request.urlopen(url, timeout=30) as r:
        dane = r.read()
    katalog = os.path.join(tempfile.gettempdir(), "RM_MAG")
    os.makedirs(katalog, exist_ok=True)
    plik = os.path.join(katalog, nazwa)
    with open(plik, "wb") as f:
        f.write(dane)
    spec = importlib.util.spec_from_file_location("mag_" + nazwa[:-3], plik)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _postep_zlecenia(zlecenie, kto):
    """Funkcja postępu odsyłająca krótkie komunikaty do zlecenia (co 5 s)."""
    ostatnio = [0.0]

    def postep(tekst):
        if time.time() - ostatnio[0] < POSTEP_CO_S:
            return
        ostatnio[0] = time.time()
        try:
            rm_klient.master_exec("sub-zlecenie-postep", {
                "postep": tekst, "id": zlecenie["id"], "wykonawca": kto})
        except Exception:
            pass                         # pasek w MAG — nie powód do przerwania
    return postep


def _zakoncz(zlecenie, kto, status, opis, co):
    try:
        rm_klient.master_exec("sub-zlecenie-zakoncz", {
            "status": status, "wynik": opis[:500], "id": zlecenie["id"],
            "wykonawca": kto})
    except Exception as e:
        print("⚠️  Zlecenie %s %s: nie odnotowano końca: %s" % (co, zlecenie["id"], e))
    print("ℹ️  %s (zlecenie %s): %s — %s" % (co, zlecenie["id"], status, opis))


_odmowy_3d = set()                        # id zleceń, których ta stacja nie weźmie


def wykonaj_indeks3d(zlecenie, kto):
    """Zlecenie „indeks3d": pobierz skrypt, zapytaj czy się nadajemy, przejmij, wykonaj."""
    if zlecenie["id"] in _odmowy_3d:
        return False
    try:
        mod = pobierz_skrypt("indeks_modeli_3d.py")
    except Exception as e:
        print("ℹ️  Indeks 3D: nie pobrano skryptu z serwera: %s" % e)
        return False
    try:
        import pythoncom
        pythoncom.CoInitialize()            # COM (Apprentice) w tym wątku
    except Exception:
        pass
    ok, powod = mod.moge_wykonac()
    if not ok:
        # Nie przejmujemy — zlecenie zostaje dla stacji, która się nadaje.
        _odmowy_3d.add(zlecenie["id"])
        print("ℹ️  Indeks 3D (zlecenie %s): ta stacja się nie nadaje — %s" % (zlecenie["id"], powod))
        return False
    wynik = rm_klient.master_exec("sub-zlecenie-przejmij",
                                  {"wykonawca": kto, "id": zlecenie["id"]})
    if not (wynik or {}).get("rowcount"):
        return False                     # ktoś był szybszy
    try:
        opis = "%s | %s" % (powod, mod.wykonaj_zlecenie(postep=_postep_zlecenia(zlecenie, kto)))
        status = "gotowe"
    except Exception as e:
        opis = "%s: %s" % (type(e).__name__, e)
        status = "blad"
        traceback.print_exc()
    _zakoncz(zlecenie, kto, status, opis, "Indeks modeli 3D")
    return True


def _most_zyje():
    try:
        import subiekt_bridge
        return subiekt_bridge.ping(timeout=3) is not None
    except Exception:
        return False


def wykonaj(zlecenie, kto):
    """Przejmuje i wykonuje jedno zlecenie. True, gdy to MY je wykonaliśmy."""
    import subiekt_kopia_sync

    wynik = rm_klient.master_exec("sub-zlecenie-przejmij",
                                  {"wykonawca": kto, "id": zlecenie["id"]})
    if not (wynik or {}).get("rowcount"):
        return False                     # ktoś był szybszy

    postep = _postep_zlecenia(zlecenie, kto)
    miniatury = bool(zlecenie.get("miniatury"))
    try:
        # Z miniaturami = OD NOWA: zdjęcia dodane do istniejących kartotek
        # inaczej by nie weszły (kopia zna je jako „bez zdjęcia").
        opis = subiekt_kopia_sync.synchronizuj(
            z_miniaturami=miniatury, miniatury_od_nowa=miniatury, postep=postep)
        status = "gotowe"
    except Exception as e:
        opis = "%s: %s" % (type(e).__name__, e)
        status = "blad"
        traceback.print_exc()
    _zakoncz(zlecenie, kto, status, opis, "Synchronizacja kopii Subiekta")
    return True


def _petla(most, inventor):
    kto = wykonawca_id()
    preferowany = _komputer() in PREFEROWANE
    zgloszono_blad = False
    time.sleep(20)                       # po starcie RM_BAZA ma inne zajęcia
    while True:
        try:
            if most:
                oczekujace = rm_klient.master_read("sub-zlecenie-oczekujace")
                if oczekujace:
                    z = oczekujace[0]
                    kolej = preferowany or (z.get("wiek_s") or 0) >= CZEKAJ_NA_PREFEROWANY_S
                    if kolej and _most_zyje():
                        wykonaj(z, kto)
            if inventor:
                # Indeks 3D: dowolna stacja z Inventorem, bez pierwszeństwa.
                z3 = rm_klient.master_read("sub-zlecenie-oczekujace-rodzaj",
                                           {"rodzaj": "indeks3d"})
                if z3:
                    wykonaj_indeks3d(z3[0], kto)
            zgloszono_blad = False
        except Exception as e:
            # Stary serwer bez operacji `sub-*`, chwilowy brak sieci — raz
            # do konsoli, potem cisza aż do pierwszego udanego zapytania.
            if not zgloszono_blad:
                print("ℹ️  Zlecenia synchronizacji niedostępne: %s" % e)
                zgloszono_blad = True
        time.sleep(CO_ILE_S)


def uruchom_w_tle():
    """Start wątku wykonawcy — raz na proces; stacja z mostem i/lub Inventorem."""
    global _watek
    if _watek is not None:
        return
    most, inventor = _jest_most(), _jest_inventor()
    if not (most or inventor):
        return
    _watek = threading.Thread(target=_petla, args=(most, inventor),
                              name="mag-zlecenia", daemon=True)
    _watek.start()
