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

Wątek-demon, bez Tk. Stanowisko bez mostu (brak binarki albo konfiguracji
Subiekta) — wątek w ogóle nie startuje. Błąd serwera albo mostu nie wychodzi
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
    try:
        rm_klient.master_exec("sub-zlecenie-zakoncz", {
            "status": status, "wynik": opis[:500], "id": zlecenie["id"],
            "wykonawca": kto})
    except Exception as e:
        print("⚠️  Zlecenie synchronizacji %s: nie odnotowano końca: %s"
              % (zlecenie["id"], e))
    print("ℹ️  Synchronizacja kopii Subiekta (zlecenie %s): %s — %s"
          % (zlecenie["id"], status, opis))
    return True


def _petla():
    kto = wykonawca_id()
    preferowany = _komputer() in PREFEROWANE
    zgloszono_blad = False
    time.sleep(20)                       # po starcie RM_BAZA ma inne zajęcia
    while True:
        try:
            oczekujace = rm_klient.master_read("sub-zlecenie-oczekujace")
            zgloszono_blad = False
            if oczekujace:
                z = oczekujace[0]
                kolej = preferowany or (z.get("wiek_s") or 0) >= CZEKAJ_NA_PREFEROWANY_S
                if kolej and _most_zyje():
                    wykonaj(z, kto)
        except Exception as e:
            # Stary serwer bez operacji `sub-*`, chwilowy brak sieci — raz
            # do konsoli, potem cisza aż do pierwszego udanego zapytania.
            if not zgloszono_blad:
                print("ℹ️  Zlecenia synchronizacji niedostępne: %s" % e)
                zgloszono_blad = True
        time.sleep(CO_ILE_S)


def uruchom_w_tle():
    """Start wątku wykonawcy — raz na proces, tylko na stacji z mostem."""
    global _watek
    if _watek is not None or not _jest_most():
        return
    _watek = threading.Thread(target=_petla, name="kopia-subiekta-zlecenia",
                              daemon=True)
    _watek.start()
