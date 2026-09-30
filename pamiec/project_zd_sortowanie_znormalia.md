---
name: project_zd_sortowanie_znormalia
description: "Okno ZD sortuje jak arkusz — znormalia na górze CAŁEJ listy (grupa przed dostawcą); kryterium to KLASA z importu, nigdy kształt symbolu"
metadata:
  type: project
---

# Okno ZD: znormalia na górze, jak w arkuszu (30.09.2026)

Zgłoszenie: „gdy wpadają symbole znormalizowanych to się rozjeżdża
segregowanie, a znormalizowane chcę mieć na samej górze, zaś rysunki RMPAK
na dole" — arkusz główny i okno „Zamówienia do dostawców (ZD)".

## Co było

Arkusz **już to robił** (`database_manager`, jedyne zapytanie pobierające
pozycje — patrz [[project_normalia_po_klasie]]). Okno ZD **nie**: sortowało
po `(czy ma ZD, dostawca, symbol)`, więc znormalia rozsypywały się między
rysunki.

## Naprawa (`283ceb1`, `subiekt_zamowienia.py`)

```python
wiersze.sort(key=lambda w: (0 if znormalizowana(w.get("typ")) else 1,
                            bool(w.get("zd")), w["dostawca"] == "",
                            w["dostawca"], w["symbol"]))
```

**Grupa idzie PRZED dostawcą** — celowo. Inaczej znormalia byłyby na górze
osobno w każdej grupie dostawcy, a mają być na górze **całej listy**.

Nowa `znormalizowana()` przyjmuje `ZNORMALIZOWANE` **i skrócone `ZNORM`**
(arkusz skraca w kolumnie Typ, okno ZD bierze klasę wprost z bazy projektu).

⛔ Kryterium to **KLASA z importu**, nigdy kształt symbolu — ten test mylił
się w obie strony (`6004 ZZ` ze spacją vs `UCFL201` bez),
[[project_normalia_po_klasie]], [[project_symbole_ze_spacja]].

Sprawdzone na projekcie 75 (2637 Feniks, 317 pozycji): znormalia zajmują
ciągły blok na początku, żadna obca klasa tam nie wpada.

## ⚠️ Czego to NIE naprawia

Pozycje kupowane z klasą **`STANDARD`** albo **`X`** (`G503`, `G506`,
`Y9630`, `NU-600.19`, `T100-200.02X`) nadal są na dole — **po danych nie są
znormaliami** i żadna reguła kolejności ich nie podniesie. To poprawka
**Typu w arkuszu** (`class_manual`, odwracalna, nie rusza importu), nie
sortowania.

Bezpieczeństwo takiej zmiany (sprawdzone w kodzie 30.09):
* **symbol kartoteki powstaje z numeru rysunku, nie z klasy**
  (`symbol = nr or symbol_z_nazwy(nazwa)`) → kartoteki w Subiekcie się nie
  rozjadą, nic się nie zduplikuje;
* `STANDARD` i `ZNORMALIZOWANE` są w kodzie traktowane **identycznie**
  wszędzie poza sortowaniem (m.in. licznik „elementy handlowe");
* okna Scal kody / Raport duplikatów **zaczną** takie pozycje widzieć — to
  pożądane dla części kupowanej;
* ⛔ **NIE ruszać `Z` i `ZZ`** — tylko te zakładają komplety w Subiekcie
  (`KOMPLETY = ("Z","ZZ")`, `subiekt_projekt.py`). Zmiana `ZZ` →
  `ZNORMALIZOWANE` skasowałaby złożenie jako komplet.
* ⚠️ `X`/`XX` to detal cięty laserem — zmiana wyrzuca go z LASER EXPORT
  i z wyceny materiałowej.
