# -*- coding: utf-8 -*-
"""Schowek montażowy — bufor między monterem a dokumentem RW.

PO CO TO JEST
─────────────
Zgłoszenie magazyniera: monterzy biorą element, zaraz oddają bo nie pasuje,
biorą inny, dobierają, zwracają. Robienie RW na każdy taki ruch jest bez
sensu księgowo (element wraca tego samego dnia), zniechęca do jakiejkolwiek
ewidencji i tak nie odda prawdy — nikt nie zdąży klikać między próbami.

Schowek zbiera w ciągu dnia same ZDARZENIA (pobrano / oddano), a Subiekt
widzi jeden dokument dopiero przy rozliczeniu — i to NETTO, nie sumę prób:

    bierze:  A×1, B×2, C×1        →   RW: A×1, B×1, D×3
    oddaje:  B×1, C×1                 (zamiany znikają z papierologii)
    dobiera: D×3

⚠️ KLUCZOWA WŁASNOŚĆ: zwrot tego samego dnia = ZERO ŚLADU na dokumencie.
`+1 pobrano, −1 oddano → 0 → nie trafia na RW`. To jedyny powód, dla którego
to w ogóle rozwiązuje problem magazyniera — nie wolno tego „uprościć" do
zwykłego koszyka pozycji.

JEDEN SCHOWEK, PROJEKT PRZY POZYCJI
───────────────────────────────────
⚠️ Schowek NIE NALEŻY do projektu. Jest JEDEN, wspólny dla stanowiska,
a projekt siedzi przy KAŻDYM RUCHU (decyzja 14.09.2026: „schowek ma nie być
przypisany do projektu tylko niezależny, pozycje przypisujemy do projektu").

Magazynier skanuje po kolei rzeczy na różne projekty do jednego koszyka —
przełączając pole „Projekt" w nagłówku, tak samo jak przełącza montera.
Przy rozliczeniu powstaje TYLE RW, ILE PROJEKTÓW: każdy dokument musi mieć
swój numer w Uwagach, bo po nim Subiekt liczy wydania per projekt.

Poprzednia wersja zakładała schowek NA PROJEKT i była błędna: po pięciu
wydaniach w pliku leżało pięć schowków, a magazynier ma widzieć jeden.

GDZIE TO ŻYJE — PLIK ROBOCZY, NIE BAZA
──────────────────────────────────────
Schowek NIE trafia do bazy projektu ani na serwer. Leży w zwykłym pliku JSON
na stanowisku magazyniera. Decyzja użytkownika (13.09.2026): „dlaczego to
idzie do bazy? to ma iść tylko do Subiekta".

* **Bufor to stan przejściowy.** Do Subiekta idzie WYNIK (jedno RW), a nie
  droga, którą do niego doszliśmy.
* **Zero locka.** Zapis do bazy projektu wymagałby locka, czyli skanowanie
  blokowałoby projekt wszystkim innym.
* **Przeżywa zamknięcie okna.** Monter wziął rano, oddaje po południu.
* **Schowek ogólny** (serwis, eksploatacja) nie ma projektu, więc nie miałby
  gdzie zamieszkać w bazie projektowej.

Konsekwencja: schowek jest LOKALNY dla stanowiska. Drugi magazynier na innym
komputerze go nie zobaczy. Przy jednym stanowisku wydawania to bez znaczenia;
gdyby kiedyś było ich kilka, plik przenosi się na udział sieciowy albo do
RM_SERWER — reszta modułu zostaje bez zmian.

Rozliczenie do RW opisuje SCHOWEK_RW_ALGORYTM.md. Ten moduł kończy się na
`do_rozliczenia()` — dalej jest już sprawa okna i mostu.
"""

import json
import os
import tempfile
from datetime import datetime


#: Plik roboczy stanowiska. Obok innych plików RM_BAZA (sync_config.json,
#: subiekt_kolumny.json), bo to ta sama kategoria: stan tego komputera.
SCIEZKA = r"C:\RMPAK_CLIENT\schowki_montazowe.json"

#: Jedyny status, jaki schowek przyjmuje.
#:
#: Nie ma juz ROZLICZONEGO: schowek jest JEDEN na stanowisko i nigdy sie
#: nie zamyka. Po wystawieniu RW znikaja tylko ruchy tego projektu
#: (`usun_projekt`), a reszta zostaje — bo moga tam czekac pozycje innych
#: projektow. Pole `status` zostaje w pliku, bo po nim szuka `biezacy()`.
OTWARTY = "OTWARTY"


class BladSchowka(Exception):
    """Operacja niemożliwa — z powodem czytelnym dla magazyniera."""


# ── plik ────────────────────────────────────────────────────────────────────
def _pusty():
    return {"wersja": 1, "nastepny_id": 1, "schowki": []}


def wczytaj(sciezka=None):
    """Zawartość pliku roboczego. Brak pliku = pusty schowek, nie błąd."""
    p = sciezka or SCIEZKA
    if not os.path.isfile(p):
        return _pusty()
    try:
        with open(p, encoding="utf-8") as f:
            dane = json.load(f) or {}
    except (OSError, ValueError):
        # Uszkodzony plik nie może zablokować wydawania — magazynier ma
        # pracować dalej, a stary plik zostaje obok do obejrzenia.
        _odloz_uszkodzony(p)
        return _pusty()
    dane.setdefault("schowki", [])
    dane.setdefault("nastepny_id",
                    max([s.get("id", 0) for s in dane["schowki"]] or [0]) + 1)
    return dane


def _odloz_uszkodzony(p):
    try:
        os.replace(p, p + ".uszkodzony-%s"
                   % datetime.now().strftime("%Y%m%d-%H%M%S"))
    except OSError:
        pass


def zapisz(dane, sciezka=None):
    """Zapis ATOMOWY — przez plik tymczasowy i podmianę.

    Magazynier skanuje seriami; zapis „w miejscu" przerwany zamknięciem
    programu zostawiłby obcięty JSON i cała dzisiejsza praca byłaby nie do
    odczytania.
    """
    p = sciezka or SCIEZKA
    katalog = os.path.dirname(p) or "."
    try:
        os.makedirs(katalog, exist_ok=True)
        uchwyt, tmp = tempfile.mkstemp(dir=katalog, suffix=".tmp")
        with os.fdopen(uchwyt, "w", encoding="utf-8") as f:
            json.dump(dane, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except OSError as e:
        raise BladSchowka("Nie udało się zapisać schowka:\n%s" % e)


# ── schowki ─────────────────────────────────────────────────────────────────
def sam_numer(projekt):
    """Sam numer projektu z tego, co dostaliśmy: „3500 dupal" → „3500".

    ⚠️ Schowek MUSI trzymać sam numer, nie pełną nazwę. Nazwa projektu bywa
    zmieniana w trakcie pracy, a wtedy zapisane „3500 dupal" przestałoby
    pasować do filtra i schowki znikałyby z listy (zapisane 13.09.2026, gdy
    pierwsze schowki wylądowały w pliku jako „3500 dupal — Agnieszka").
    Numer się nie zmienia — po nim rozpoznaje projekt także Subiekt.
    """
    return str(projekt or "").strip().split(" ")[0]


def utworz(sciezka=None, **_zgodnosc):
    """Nowy otwarty schowek — JEDEN, bez przypisania do projektu.

    Projekt i monter siedzą przy ruchach, nie tutaj. Argumenty nazwane są
    przyjmowane i ignorowane, żeby stary kod wołający `utworz(monter, ...)`
    nie wybuchał.
    """
    dane = wczytaj(sciezka)
    nowy = {
        "id": dane["nastepny_id"],
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": OTWARTY,
        "rw_numer": None,
        "rozliczony": None,
        "ruchy": [],
    }
    dane["schowki"].append(nowy)
    dane["nastepny_id"] += 1
    zapisz(dane, sciezka)
    return nowy["id"]


def biezacy(sciezka=None):
    """JEDEN otwarty schowek stanowiska — zakładany, gdy go jeszcze nie ma.

    To jest główny punkt wejścia. Schowek nie jest przypisany do projektu,
    więc nie ma czego wybierać: jest jeden i zawsze ten sam, aż do
    rozliczenia.
    """
    for s in wczytaj(sciezka)["schowki"]:
        if s.get("status") == OTWARTY:
            return {k: v for k, v in s.items() if k != "ruchy"}
    return pobierz(utworz(sciezka=sciezka), sciezka)


def _znajdz(dane, schowek_id):
    for s in dane["schowki"]:
        if s["id"] == schowek_id:
            return s
    raise BladSchowka("Nie ma schowka o numerze %s." % schowek_id)


def pobierz(schowek_id, sciezka=None):
    s = _znajdz(wczytaj(sciezka), schowek_id)
    return {k: v for k, v in s.items() if k != "ruchy"}


def _klucz(symbol):
    """Symbol do porównań: TRIM + wielkie litery.

    ⚠️ NIE tniemy na spacji — symbole w Subiekcie ją zawierają („6212 2RS",
    „DIN 933 M8x30"). Ta sama zasada co w skanerze okna wydania.
    """
    return (symbol or "").strip().upper()


def _bilans(s):
    """Bilans NETTO po parach (PROJEKT, SYMBOL) — tylko dodatnie.

    ⚠️ Kluczem jest PARA, nie sam symbol. Ten sam detal bywa wydawany na
    dwa projekty w tej samej sesji i musi zostać dwiema pozycjami — inaczej
    ilości zlałyby się w jedną i trafiły na niewłaściwy dokument.

    Jedyne miejsce, w którym powstaje „co jest w schowku". Liczymy z ruchów
    zamiast trzymać osobne pole, żeby historia i stan nie mogły się rozjechać.
    """
    razem, nazwy, oryginal, monterzy = {}, {}, {}, {}
    for r in s.get("ruchy", []):
        k = (sam_numer(r.get("projekt")), _klucz(r["symbol"]))
        razem[k] = razem.get(k, 0.0) + float(r["ilosc"])
        oryginal.setdefault(k, r["symbol"])
        if r.get("nazwa"):
            nazwy[k] = r["nazwa"]
        kto = (r.get("monter") or "").strip()
        if kto:
            monterzy.setdefault(k, {})
            monterzy[k][kto] = monterzy[k].get(kto, 0.0) + float(r["ilosc"])
    out = []
    for (projekt, _sym), ile in sorted(razem.items()):
        if ile <= 0:
            continue
        k = (projekt, _sym)
        ludzie = [n for n, x in sorted(monterzy.get(k, {}).items()) if x > 0]
        out.append({"projekt": projekt, "symbol": oryginal[k],
                    "nazwa": nazwy.get(k, ""), "ilosc": ile,
                    "monterzy": ", ".join(ludzie)})
    return out


def stan_schowka(schowek_id, sciezka=None):
    return _bilans(_znajdz(wczytaj(sciezka), schowek_id))


def ile_w_schowku(schowek_id, symbol, projekt=None, sciezka=None):
    """Bilans jednego symbolu W RAMACH PROJEKTU (może być 0)."""
    s = _znajdz(wczytaj(sciezka), schowek_id)
    k, pr = _klucz(symbol), sam_numer(projekt)
    return sum(float(r["ilosc"]) for r in s.get("ruchy", [])
               if _klucz(r["symbol"]) == k and sam_numer(r.get("projekt")) == pr)


def historia(schowek_id, sciezka=None):
    """Wszystkie ruchy od najnowszego — do okna „Historia"."""
    return list(reversed(_znajdz(wczytaj(sciezka), schowek_id).get("ruchy", [])))


def _wymagaj_otwartego(s):
    """Zabezpieczenie przed wpisem z pliku po starszej wersji programu.

    Dzis schowek jest zawsze otwarty — status ROZLICZONY istnial, gdy schowek
    nalezal do projektu i zamykal sie po RW.
    """
    if s.get("status") != OTWARTY:
        raise BladSchowka(
            "Ten schowek pochodzi ze starszej wersji i jest zamkniety. "
            "Zamknij i otworz okno ponownie — powstanie nowy.")


def _ruch(schowek_id, symbol, ilosc, nazwa, operator, monter, projekt, sciezka):
    dane = wczytaj(sciezka)
    s = _znajdz(dane, schowek_id)
    _wymagaj_otwartego(s)
    pr = sam_numer(projekt)
    s.setdefault("ruchy", []).append({
        "projekt": pr, "symbol": (symbol or "").strip(), "nazwa": nazwa or "",
        "ilosc": float(ilosc),
        "czas": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "operator": (operator or "").strip(),
        "monter": (monter or "").strip(),
    })
    zapisz(dane, sciezka)
    k = _klucz(symbol)
    return sum(float(r["ilosc"]) for r in s["ruchy"]
               if _klucz(r["symbol"]) == k and sam_numer(r.get("projekt")) == pr)


def pobrano(schowek_id, symbol, ilosc, nazwa=None, operator=None,
            monter=None, projekt=None, sciezka=None):
    """Monter WZIĄŁ element na dany projekt — ruch dodatni."""
    if not (symbol or "").strip():
        raise BladSchowka("Brak symbolu.")
    if ilosc <= 0:
        raise BladSchowka("Ilość musi być większa od zera.")
    return _ruch(schowek_id, symbol, ilosc, nazwa, operator, monter,
                 projekt, sciezka)


def oddano(schowek_id, symbol, ilosc, nazwa=None, operator=None,
           monter=None, projekt=None, sciezka=None):
    """Monter ODDAŁ element — ruch ujemny, w ramach TEGO SAMEGO projektu.

    ⛔ Nie wolno oddać więcej, niż jest w schowku NA TYM PROJEKCIE: ujemny
    bilans zaniżyłby RW przy rozliczeniu i rozjechał stan magazynu. Twardy
    błąd, zero zapisu („nic po cichu").
    """
    if not (symbol or "").strip():
        raise BladSchowka("Brak symbolu.")
    if ilosc <= 0:
        raise BladSchowka("Ilość musi być większa od zera.")
    ma = ile_w_schowku(schowek_id, symbol, projekt, sciezka)
    if ilosc > ma:
        raise BladSchowka(
            "W schowku jest %s szt. „%s”%s — nie można oddać %s. "
            "Żaden ruch nie został zapisany."
            % (_ilo(ma), (symbol or "").strip(),
               (" na projekcie %s" % sam_numer(projekt)) if projekt else "",
               _ilo(ilosc)))
    return _ruch(schowek_id, symbol, -ilosc, nazwa, operator, monter,
                 projekt, sciezka)


def usun_projekt(schowek_id, projekt, sciezka=None):
    """Kasuje ruchy JEDNEGO projektu — po wystawieniu jego RW.

    Schowek zbiera pozycje z kilku projektów naraz i rozlicza je osobnymi
    dokumentami. Po udanym RW znika TYLKO ten projekt; reszta zostaje, żeby
    dało się dokończyć wydanie, gdy któryś dokument się nie powiódł.

    Schowek NIE jest zamykany — jest jeden na stanowisko i żyje dalej.
    """
    dane = wczytaj(sciezka)
    s = _znajdz(dane, schowek_id)
    _wymagaj_otwartego(s)
    pr = sam_numer(projekt)
    s["ruchy"] = [r for r in s.get("ruchy", [])
                  if sam_numer(r.get("projekt")) != pr]
    zapisz(dane, sciezka)


def usun_pozycje(schowek_id, symbol, projekt=None, sciezka=None):
    """Kasuje CAŁĄ historię jednego symbolu — cofnięcie pomyłki skanowania.

    To NIE jest zwrot od montera: zwrot zostawia ślad (`oddano`), a to
    czyści tak, jakby skanu nigdy nie było. Do użycia, gdy magazynier
    dopisał pozycję do złego projektu.

    `projekt` zawęża kasowanie do jednego projektu — ten sam detal bywa
    w schowku na dwóch naraz i wtedy czyścimy tylko wskazany wiersz.
    """
    dane = wczytaj(sciezka)
    s = _znajdz(dane, schowek_id)
    _wymagaj_otwartego(s)
    k = _klucz(symbol)
    pr = sam_numer(projekt) if projekt else None
    s["ruchy"] = [r for r in s.get("ruchy", [])
                  if _klucz(r["symbol"]) != k
                  or (pr is not None and sam_numer(r.get("projekt")) != pr)]
    zapisz(dane, sciezka)


def ustaw_ilosc(schowek_id, symbol, ilosc, projekt=None, monter=None,
                operator=None, sciezka=None):
    """Poprawia ilość pozycji w schowku na dokładnie `ilosc`.

    Magazynier pomylił się przy wpisywaniu i chce po prostu wpisać dobrą
    liczbę, zamiast liczyć, ile trzeba zdjąć (14.09.2026: „chcę móc
    edytować w schowku ilość W SCHOWKU").

    ⚠️ Historii NIE KASUJEMY — dopisujemy RUCH KORYGUJĄCY na różnicę.
    Skasowanie i wpisanie od nowa zatarłoby ślad, kto ile faktycznie wziął,
    a to jedyna rzecz, po której da się później dojść, gdzie podział się
    detal. W „Historii ruchów" widać wtedy pobranie i korektę osobno.

    `ilosc=0` czyści pozycję bilansem, ale ślad zostaje.
    """
    ile = float(ilosc)
    if ile < 0:
        raise BladSchowka("Ilość nie może być ujemna.")
    teraz = ile_w_schowku(schowek_id, symbol, projekt, sciezka)
    roznica = ile - teraz
    if abs(roznica) < 1e-9:
        return teraz                    # nic się nie zmienia
    dane = wczytaj(sciezka)
    s = _znajdz(dane, schowek_id)
    _wymagaj_otwartego(s)
    # Nazwę i montera bierzemy z ostatniego ruchu tej pozycji, żeby wiersz
    # w tabeli nie stracił opisu po korekcie.
    k, pr = _klucz(symbol), sam_numer(projekt)
    nazwa, kto = "", (monter or "")
    for r in s.get("ruchy", []):
        if _klucz(r["symbol"]) == k and sam_numer(r.get("projekt")) == pr:
            nazwa = r.get("nazwa") or nazwa
            kto = kto or (r.get("monter") or "")
    s.setdefault("ruchy", []).append({
        "projekt": pr, "symbol": (symbol or "").strip(), "nazwa": nazwa,
        "ilosc": roznica,
        "czas": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "operator": (operator or "").strip(),
        "monter": kto,
        "korekta": True,
    })
    zapisz(dane, sciezka)
    return ile


def wyczysc(schowek_id, sciezka=None):
    """Kasuje wszystkie ruchy schowka. Schowek zostaje, pusty."""
    dane = wczytaj(sciezka)
    s = _znajdz(dane, schowek_id)
    _wymagaj_otwartego(s)
    s["ruchy"] = []
    zapisz(dane, sciezka)


# ── rozliczenie ─────────────────────────────────────────────────────────────
def do_rozliczenia(schowek_id, sciezka=None):
    """Pozycje, które pójdą na RW — bilans netto. Pusty = nie ma czego wydawać."""
    return stan_schowka(schowek_id, sciezka)


#: Ile dni trzymać rozliczone schowki, zanim znikną z pliku.
#:
#: Schowek po wystawieniu RW jest już tylko historią — fakt magazynowy
#: siedzi w Subiekcie, na dokumencie. Trzymanie go bez końca zaśmiecało
#: listę: po pięciu wydaniach było pięć wpisów, po miesiącu byłyby setki
#: („nie ma niezliczonej ilości schowków, ma być tylko jeden", 14.09.2026).
#:
#: Zero = kasuj natychmiast po rozliczeniu. Kilka dni zostawiamy po to, żeby
#: dało się jeszcze zajrzeć w „Historię ruchów" i sprawdzić, kto co wziął,
#: gdy ktoś zgłosi wątpliwość nazajutrz.
DNI_HISTORII = 3


def zajete_w_schowkach(tylko_otwarte=True, sciezka=None):
    """{SYMBOL: ilość} — co fizycznie chodzi po hali w rękach monterów.

    Subiekt o schowkach nie wie, więc jego stan jest ZAWYŻONY o te sztuki.
    Dostępność fizyczna = stan z Subiekta − to. Bez tego magazynier wyda
    drugi raz coś, co już ktoś trzyma (§4 BUFOR_SCHOWEK_MONTAZOWY.md).
    """
    razem = {}
    for s in wczytaj(sciezka)["schowki"]:
        if tylko_otwarte and s.get("status") != OTWARTY:
            continue
        for p in _bilans(s):
            razem[p["symbol"]] = razem.get(p["symbol"], 0.0) + p["ilosc"]
    return {k: v for k, v in razem.items() if v > 0}


def _ilo(x):
    """Liczba bez zbędnego ogona: 3 zamiast 3.0, ale 2.5 zostaje."""
    x = float(x)
    return str(int(x)) if abs(x - int(x)) < 1e-9 else ("%.3f" % x).rstrip("0")
