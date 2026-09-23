# -*- coding: utf-8 -*-
"""
DOKLEJ ZŁOŻENIE Z OUT — dokleja biblioteczne poddrzewo do BOM-u projektu.

Problem, który rozwiązuje (pomiar na projekcie 2637 + EWTR-820, 23.09.2026):
złożenie z biblioteki figuruje w drzewku projektu jako PUSTY węzeł (liść bez
składu), bo jego rozwinięcie siedzi w osobnym pliku *_OUT.xlsx. Żadna
z istniejących funkcji importu nie dokleja go poprawnie:

| funkcja        | korzeń EWTR-820.00ZZ | część wspólna 011-100.67 |
|----------------|----------------------|--------------------------|
| Import BOM     | KASUJE cały projekt  | —                        |
| Aktualizuj BOM | OK (zostaje 1)       | 5 zamiast 10 (bierze z pliku) |
| Dodaj BOM      | 1+1 = 2 (ŹLE)        | OK (5+5 = 10)            |

Sedno: korzeń jest ZARAZEM pozycją w BOM-ie projektu (puste złożenie)
I pierwszym wierszem w OUT-cie biblioteki, więc każda funkcja sumująca
liczy go podwójnie.

Tutaj sumowanie jest sterowane PER WIERSZ:
  * korzeń (poziom 1 w „DRZEWKO TEKST") → NIE sumuj, zostaw ilość z BOM-u,
  * składniki (poziom > 1)              → sumuj, jak „Dodaj BOM".

Moduł zapisywany w formacie „MODUŁ(ilość), MODUŁ(ilość)" — ten sam co
„Import moduł" (concatenate_modul w RM_BAZA_v15_MAG_STATS_ORG.py).

UWAGA: korzenia NIE WOLNO usuwać z BOM-u — subiekt_projekt.build_plan
zakłada komplet iterując po items po typie Z/ZZ. Bez korzenia nie ma
kompletu w Subiekcie, a składniki wiszą luzem.
"""

from pathlib import Path


def znajdz_korzen_drzewka(out_path):
    """Numer rysunku korzenia drzewka z pliku *_OUT.xlsx (albo None).

    Korzeń to jedyny wiersz arkusza „DRZEWKO TEKST" o ścieżce długości 1 —
    nie trzeba zgadywać po numerze ani po nazwie pliku.

    Zwraca None, gdy pliku nie da się przeczytać albo nie ma tam drzewka
    (np. wskazano zwykły BOM bez arkusza „DRZEWKO TEKST"). Wołający musi
    wtedy przerwać: bez korzenia nie wiadomo, czego NIE sumować.
    """
    try:
        from import_bom import find_assembly_tree_rows
        rows = find_assembly_tree_rows(Path(out_path))
    except Exception:
        return None

    for row in rows or []:
        sciezka = row.get("sciezka") or []
        if len(sciezka) == 1:
            nr = (row.get("nr_rysunku") or "").strip()
            if nr:
                return nr
    return None


def modul_z_iloscia(nazwa_modulu, ilosc):
    """„820(5)" — nazwa modułu z ilością w nawiasie.

    Format jak w „Import moduł" (concatenate_modul): przy wielu modułach
    pozycje sklejają się przecinkiem, żeby było widać, ile sztuk wchodzi
    z którego modułu.
    """
    nazwa = str(nazwa_modulu or "").strip()
    if not nazwa:
        return ""
    try:
        n = int(round(float(str(ilosc).replace(",", "."))))
    except (TypeError, ValueError):
        return nazwa
    return f"{nazwa}({n})"


def scal_moduly(stary, nazwa_modulu, ilosc):
    """Dopisz „MODUŁ(ilość)" do istniejącej wartości, po przecinku.

    Pusty `stary` → sama nowa wartość. Gdy ten sam moduł już tam jest,
    NIE dopisujemy go drugi raz — powtórny import tego samego pliku
    inaczej rozrastałby pole w nieskończoność („820(5), 820(5), …").
    """
    nowy = modul_z_iloscia(nazwa_modulu, ilosc)
    stary = str(stary or "").strip().rstrip(",").strip()
    if not nowy:
        return stary
    if not stary:
        return nowy
    # Czy ten moduł już występuje? Porównujemy samą nazwę przed nawiasem.
    nazwa = str(nazwa_modulu or "").strip()
    for czlon in stary.split(","):
        if czlon.strip().split("(")[0].strip() == nazwa:
            return stary
    return f"{stary}, {nowy}"
