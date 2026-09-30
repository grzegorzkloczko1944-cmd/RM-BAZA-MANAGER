"""Wygląd przycisków RM_BAZA: ramka + podświetlenie pod myszą (30.09.2026).

Życzenie usera: „wyładnij klawisze w oknach — niech mają ramki i najechanie
myszą je podświetla". Jedno miejsce dla CAŁEJ aplikacji zamiast poprawiania
setek `tk.Button(...)` po kolei.

Dwie warstwy:

* baza opcji Tk — domyślny wygląd przycisku BEZ własnych ustawień (jasne tło,
  cienka ramka). Przycisk z własnym `bg` / `relief` zachowuje swoje: baza
  opcji to tylko wartości domyślne;
* `bind_class("Button", "<Enter>/<Leave>")` — podświetlenie KAŻDEGO przycisku,
  także kolorowego (zielony „Zapisz", czerwony „Zwolnij Lock"): jasny
  ciemnieje, kolorowy jaśnieje. Dopisane (`add="+"`) do wiązań Tk, więc
  klikanie działa jak dotąd.

⚠️ Tk na Windows NIE podświetla tk.Button pod myszą sam z siebie —
`activebackground` widać tylko w chwili wciśnięcia. Stąd własne wiązanie.

⚠️ Kod aplikacji zmienia `bg` przycisków w locie (np. „Wystaw RW” robi się
pomarańczowy, gdy dojdzie odczyt z Subiekta). Jeśli stanie się to, gdy mysz
jest nad przyciskiem, <Leave> NIE może przywrócić starego koloru — dlatego
przywracamy tylko wtedy, gdy przycisk nadal ma NASZ kolor podświetlenia.
"""

import tkinter as tk

#: Prawie biały — odcina się od szarych okien (#f0f0f0, Edytor #e6ebf0).
#: Wcześniejszy #e4e9ee zlewał się z tłem („mają kolory tła", 30.09.2026).
TLO = "#fbfcfd"
TLO_WCISNIETY = "#c5d9ec"
#: Jasny przycisk pod myszą: jasnoniebieski jak w Windows, nie „trochę
#: ciemniejszy szary" — ten był na jasnym tle ledwo widoczny.
TLO_POD_MYSZA = "#dcebf8"
TEKST = "#1f2d3a"

#: {ścieżka przycisku: (kolor oryginalny, kolor podświetlenia)}
_pod_mysza = {}


def _rgb(widget, kolor):
    r, g, b = widget.winfo_rgb(kolor)
    return r // 257, g // 257, b // 257


def kolor_podswietlenia(widget, kolor):
    """Jasny przycisk → jasnoniebieski; kolorowy → rozjaśniony o 30 %.

    18 % na nasyconych kolorach (zielony, pomarańczowy) było niewidoczne —
    user: „kolorowe klawisze nie mają podświetleń" (30.09.2026).
    """
    r, g, b = _rgb(widget, kolor)
    jasnosc = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    if jasnosc > 0.80:
        return TLO_POD_MYSZA
    r, g, b = (int(c + (255 - c) * 0.30) for c in (r, g, b))
    return "#%02x%02x%02x" % (r, g, b)


def _wejscie(event):
    w = event.widget
    try:
        if str(w.cget("state")) == "disabled":
            return
        stary = w.cget("background")
        nowy = kolor_podswietlenia(w, stary)
        _pod_mysza[str(w)] = (stary, nowy)
        w.configure(background=nowy)
    except (tk.TclError, AttributeError):
        pass


def _wyjscie(event):
    w = event.widget
    para = _pod_mysza.pop(str(w), None)
    if not para:
        return
    stary, nowy = para
    try:
        # Kod zmienił kolor w trakcie — zostawiamy jego wybór.
        if str(w.cget("background")) == nowy:
            w.configure(background=stary)
    except (tk.TclError, AttributeError):
        pass


def wlacz(root):
    """Raz, przy starcie aplikacji — PRZED budową okien (baza opcji działa
    tylko na przyciski tworzone po jej ustawieniu)."""
    for opcja, wartosc in (("background", TLO),
                           ("activeBackground", TLO_WCISNIETY),
                           ("foreground", TEKST),
                           # `groove`, nie `solid`: solid na Windows rysuje
                           # CZARNĄ linię („za ciemne ramki"), a groove bierze
                           # odcienie z tła przycisku — szara na jasnym,
                           # ciemnozielona na zielonym. Szarej ramki przez
                           # highlightThickness Tk na Windows nie rysuje.
                           ("relief", "groove"),
                           ("borderWidth", 2),
                           ("overRelief", "groove"),
                           ("cursor", "hand2")):
        root.option_add("*Button." + opcja, wartosc, "widgetDefault")
    root.bind_class("Button", "<Enter>", _wejscie, add="+")
    root.bind_class("Button", "<Leave>", _wyjscie, add="+")
