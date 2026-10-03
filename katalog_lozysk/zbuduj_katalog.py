# -*- coding: utf-8 -*-
"""zbuduj_katalog.py — katalog łożysk kulkowych zwykłych (z głębokim rowkiem).

    python katalog_lozysk/zbuduj_katalog.py          # pobiera PDF-y, buduje JSON

Wynik: `katalog_lozysk/lozyska_kulkowe.json` — ładowany przez RM_SERWER do
`subiekt_kopia.sqlite`, tabela `lozyska` (patrz `rm_serwer_operacje.
zaladuj_katalog_lozysk`). Makro MAG pokazuje z niego wymiary kartotek
i okno „Katalog łożysk".

ŹRÓDŁA (katalogi producentów, publiczne PDF-y):
  * GŁÓWNE — Timken, „Deep Groove Ball Bearing Catalog" (10857):
    serie 60/62/63/64, 617/618/619, 160/161, 622/623/630, miniaturowe 6xx.
  * UZUPEŁNIENIE — FBJ, „Deep Groove Ball Bearings" (tabela): rozmiary,
    których Timken nie ma (duże 618/619, część 64xx).

WIARYGODNOŚĆ: wymiary d×D×B są znormalizowane (ISO 15) i muszą być
identyczne u wszystkich producentów — skrypt porównuje Timken z FBJ i PRZERYWA
przy choćby jednej różnicy. Pomiar 28.09.2026: 160 wspólnych, 0 różnic.
Nośności, obroty i masa są producenta — biorę Timken; dla uzupełnień z FBJ
tylko wartości wiarygodne (FBJ ma literówki: 6219 Cr=10800, 16001 skopiowane
z 6001, rozjechany wiersz 6052 — odrzucone).

Warianty uszczelnień (Z, ZZ/2Z, RS, 2RS, 2RZ, N, NR, C3…) mają wymiary
łożyska bazowego — katalog trzyma TYLKO oznaczenia bazowe.
"""
import json
import os
import re
import sys
import urllib.request

TU = os.path.dirname(os.path.abspath(__file__))
WYNIK = os.path.join(TU, "lozyska_kulkowe.json")
ZRODLA = {
    "timken": "https://www.timken.com/resources/10857_deep-groove-ball-brgs-catalog/",
    "fbj": "https://www.fbj-bearings.com/pdf_bearings_table/Deep%20Groove%20Ball%20Bearings.pdf",
}
LICZ = re.compile(r"^(\d+(\.\d+)?|-)$")


def pobierz(nazwa):
    """PDF do katalogu tymczasowego (nie trzymamy go w repo)."""
    import tempfile
    cel = os.path.join(tempfile.gettempdir(), "katalog_lozysk_%s.pdf" % nazwa)
    if not os.path.exists(cel) or os.path.getsize(cel) < 100000:
        req = urllib.request.Request(ZRODLA[nazwa], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r, open(cel, "wb") as f:
            f.write(r.read())
    return cel


def tokeny(strona):
    return [x.strip() for x in strona.get_text().split("\n") if x.strip()]


def seria(o):
    """6004 -> 60, 61804 -> 618, 16004 -> 160, 62204 -> 622, 623 -> 6xx, 618/5 -> 618."""
    if "/" in o:
        return o.split("/")[0]
    if len(o) == 3:
        return "6xx"
    if len(o) == 4:
        return o[:2]
    return o[:3]


def timken():
    import pymupdf
    ozn = re.compile(r"^(6\d{2,4}|16\d{3}|6\d{2}/\d+(\.\d+)?|61[6789]\d{2,3}|62\d{3}|63\d{3})(MB)?$")
    rek, mb = {}, set()
    for s in pymupdf.open(pobierz("timken")):
        t = tokeny(s)
        tekst = " ".join(t)
        if "Bearing No." not in tekst:
            continue
        # Tabela standardowa ma dodatkowo D2 i f (11 liczb), reszta 9.
        n = 11 if "D2" in tekst else 9
        j = 0
        while j < len(t):
            m = ozn.match(t[j])
            if m:
                k = j + 1
                while k < len(t) and t[k] == "•":        # kropki = warianty uszczelnień
                    k += 1
                num = t[k:k + n]
                if len(num) == n and all(LICZ.match(x) for x in num) and "-" not in num[:3]:
                    v = [None if x == "-" else float(x) for x in num]
                    if v[0] < v[1] and v[2] < v[1]:
                        baza = m.group(1)
                        if m.group(3):                         # MB = koszyk mosiężny, te same wymiary
                            mb.add(baza)
                        elif baza not in rek:
                            cr, c0, ns, no, ms = (v[6:11] if n == 11 else v[4:9])
                            rek[baza] = dict(oznaczenie=baza, d=v[0], D=v[1], B=v[2], r_min=v[3],
                                             Cr_kN=cr, C0r_kN=c0, n_smar=ns, n_olej=no, masa_kg=ms,
                                             zrodlo="Timken")
                        j = k + n
                        continue
            j += 1
    for o in rek:
        rek[o]["koszyk_mosiezny"] = o in mb
    return rek


def fbj():
    import pymupdf
    wiersze = {}
    for s in pymupdf.open(pobierz("fbj")):
        t = tokeny(s)
        j = 0
        while j < len(t):
            tok, nast = t[j], t[j + 1:j + 9]
            if (len(nast) == 8 and all(LICZ.match(x) and x != "-" for x in nast)
                    and re.search(r"\d", tok) and not re.match(r"^\d+\.\d+$", tok)):
                o = tok.rstrip("*").strip()
                # FBJ pisze 68xx/69xx i 68/600 — rynkowo to 618xx/619xx, 618/600.
                if re.match(r"^6[89]\d{2}$", o):
                    o = "61" + o[1:]
                if re.match(r"^6[89]/\d+$", o):
                    o = "61" + o[1:]
                v = [float(x) for x in nast]
                wiersze[o] = dict(oznaczenie=o, d=v[0], D=v[1], B=v[2], Cr=v[3], C0=v[4],
                                  n_smar=v[5], n_olej=v[6], masa_kg=v[7])
                j += 9
            else:
                j += 1
    return wiersze


def aliasy(o):
    """Handlowe nazwy tego samego łożyska: 618/8 = 688, 61804 = 6804, 619/5 = 695.

    Sklepy i kartoteki piszą raczej krótką formę (688, 6804) — bez aliasów
    rozpoznanie kartoteki „688ZZ" nie znalazłoby łożyska 618/8.
    """
    m = re.match(r"^61([89])/(\d)$", o)             # 618/8 -> 688, 619/5 -> 695
    if m:
        return ["6" + m.group(1) + m.group(2)]
    m = re.match(r"^61([89])(\d{2})$", o)           # 61804 -> 6804
    if m:
        return ["6" + m.group(1) + m.group(2)]
    return []


def kn(x):
    """FBJ miesza jednostki: 618xx w N, 64xx w kN."""
    return round(x / 1000.0, 2) if x > 1000 else x


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    T, F = timken(), fbj()
    kulkowe = re.compile(r"^(6[0-4]\d{2}|61[6-9]\d{2,3}|16[01]\d{2}|62[23]\d{2}|630\d{2}|6\d{2}|61[89]/\d+)$")

    # 1. Kontrola krzyżowa wymiarów — twarda.
    wsp = [o for o in T if o in F]
    rozne = [o for o in wsp if (T[o]["d"], T[o]["D"], T[o]["B"]) != (F[o]["d"], F[o]["D"], F[o]["B"])]
    print(f"Timken: {len(T)}  FBJ: {len(F)}  wspólnych: {len(wsp)}  różnych wymiarów: {len(rozne)}")
    if rozne:
        for o in rozne:
            print("  ⛔", o, (T[o]["d"], T[o]["D"], T[o]["B"]), (F[o]["d"], F[o]["D"], F[o]["B"]))
        sys.exit("Wymiary się nie zgadzają — katalog NIE zapisany.")

    # 2. Uzupełnienia z FBJ — tylko kulkowe zwykłe i wiarygodne.
    kat = dict(T)
    dodane, odrzucone = [], []
    for o, w in F.items():
        if o in kat or not kulkowe.match(o):
            continue
        if not (w["d"] < w["D"] and w["B"] < w["D"] and w["D"] - w["d"] >= 2 * w["B"] * 0.3):
            odrzucone.append((o, "rozjechane wymiary"))
            continue
        cr, c0 = kn(w["Cr"]), kn(w["C0"])
        ok = c0 > 0 and 0.35 <= cr / c0 <= 4.5
        if o == "16001":
            ok = False                                  # FBJ skopiował tu nośność 6001
        kat[o] = dict(oznaczenie=o, d=w["d"], D=w["D"], B=w["B"], r_min=None,
                      Cr_kN=cr if ok else None, C0r_kN=c0 if ok else None,
                      n_smar=w["n_smar"] if ok else None, n_olej=w["n_olej"] if ok else None,
                      masa_kg=w["masa_kg"] if ok else None, zrodlo="FBJ",
                      koszyk_mosiezny=False)
        dodane.append(o)
    print(f"Z FBJ dodane: {len(dodane)}  odrzucone: {odrzucone}")

    # 3. Zapis — posortowane po serii i średnicy.
    for r in kat.values():
        r["seria"] = seria(r["oznaczenie"])
        r["aliasy"] = aliasy(r["oznaczenie"])
        # Miniaturowe 618/x, 619/x: wersje ZZ/2RS bywają SZERSZE niż otwarte
        # (688 = 8x16x4, 688ZZ = 8x16x5) — B w katalogu dotyczy wersji otwartej.
        r["uwaga"] = ("B dla wersji otwartej; ZZ/2RS bywa szersze"
                      if re.match(r"^61[89]/", r["oznaczenie"]) else "")
    # ── WPISY WLASNE (nie z PDF-ow producentow) ──────────────────────────
    #
    # Dla serii miniaturowych B w katalogu dotyczy wersji OTWARTEJ, a wersja
    # ZZ/2RS bywa szersza (uwaga wyzej). Dla 688 obie wersje realnie
    # wystepuja w obrocie i OBIE mamy na magazynie, wiec „688" dostaje
    # wlasny wpis z B=5 — inaczej makro MAG pokazywaloby przy kartotece
    # „688 ZZ 8x16x5" wymiary 8x16x4 z aliasu 618/8 (03.10.2026).
    #
    # ⚠️ Alias „688" znika z 618/8, zeby jeden symbol nie mial dwoch zrodel
    # wymiarow. 618/8 zostaje bez zmian jako wersja otwarta 8x16x4.
    WLASNE = [
        dict(oznaczenie="688", d=8.0, D=16.0, B=5.0, r_min=0.2,
             Cr_kN=None, C0r_kN=None, n_smar=None, n_olej=None, masa_kg=None,
             zrodlo="EZO (wersja ZZ/2RS)", koszyk_mosiezny=False),
    ]
    # Oznaczenia POMIJANE mimo obecnosci w PDF-ach producentow. „618/8" to
    # wersja OTWARTA (8x16x4) — w obrocie mamy wylacznie uszczelniona „688"
    # (8x16x5), wiec wpis normowy tylko mylil kolumne Wymiary w MAG
    # (decyzja uzytkownika 03.10.2026, kartoteki 618/8 usuniete z Subiekta).
    POMIJAJ = {"618/8"}
    for o in POMIJAJ:
        kat.pop(o, None)

    wlasne_ozn = {w["oznaczenie"] for w in WLASNE}
    for w in WLASNE:
        w["seria"] = seria(w["oznaczenie"])
        w["aliasy"] = []
        w["uwaga"] = "wersja uszczelniona ZZ/2RS; otwarta 618/8 ma B=4"
        kat[w["oznaczenie"]] = w
    # Alias przejety przez wpis wlasny nie moze zostac przy bazowym.
    for r in kat.values():
        if r.get("aliasy"):
            r["aliasy"] = [a for a in r["aliasy"]
                           if a not in wlasne_ozn and a not in POMIJAJ]

    wynik = sorted(kat.values(), key=lambda r: (r["seria"], r["d"], r["D"]))
    with open(WYNIK, "w", encoding="utf-8") as f:
        json.dump({"zrodla": ZRODLA, "opis": "Łożyska kulkowe zwykłe (z głębokim rowkiem), "
                   "oznaczenia bazowe; wymiary mm, nośności kN, obroty RPM, masa kg.",
                   "lozyska": wynik}, f, ensure_ascii=False, indent=1)
    print(f"ZAPISANO {len(wynik)} łożysk -> {WYNIK}")
    from collections import Counter
    print(sorted(Counter(r["seria"] for r in wynik).items()))


if __name__ == "__main__":
    main()
