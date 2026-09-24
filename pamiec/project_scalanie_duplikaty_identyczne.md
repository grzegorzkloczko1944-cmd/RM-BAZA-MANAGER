---
name: project_scalanie_duplikaty_identyczne
description: "Scal kody handlowe nie widziało dwóch wierszy o IDENTYCZNYM zapisie — filtr patrzył na warianty pisowni, nie na liczbę wierszy"
metadata:
  type: project
---

**Okno „Scal kody handlowe" pomijało duplikaty tego samego zapisu
(naprawione 24.09.2026).**

Zgłoszenie: projekt 73 (2937 Feniks) ma **dwa wiersze**
`SS 6004 2RS 20x42x12` — identyczny symbol, identyczna nazwa. Okno ich
w ogóle nie pokazywało.

## Przyczyna

Filtr „Tylko z podobnymi" w `subiekt_scalanie_gui._odswiez_liste`:

```python
ma_co = bool(p["identyczne"] or p["podobne"])
```

`identyczne` to **inne ZAPISY** tego samego klucza (`zapisy[1:]`
w `pozycje_z_podobnymi`) — czyli różnice w pisowni. Gdy oba wiersze
zapisane są **tak samo**, jest jeden zapis, `identyczne` jest puste
i pozycja wypada z listy.

Kontrast na tym samym projekcie — te dwa okno **pokazywało**, bo miały
rozjazd zapisu:

| klucz | wierszy | warianty | widoczne? |
|---|---|---|---|
| `SS60042RS20X42X12` | 2 | `['SS 6004 2RS 20x42x12']` | ⛔ NIE |
| `KOŁO12T100MM...` | 2 | `KOŁO` vs `Koło` | ✔ tak |
| `NAKRĘTKATR16X4` | 2 | `Nakrętka TR16x4` vs `...x4.` | ✔ tak |

Liczba wierszy siedziała w `p["ile"]` (= 2) i **nikt jej nie sprawdzał**.

## Naprawa

Warunek w trzech miejscach GUI (filtr, licznik w nagłówku, kolumna
„Podobne w tym projekcie"):

```python
ma_co = bool(p["identyczne"] or p["podobne"] or p.get("ile", 0) > 1)
```

Taki wiersz nie ma czego pokazać w kolumnie „Podobne", więc dostaje własny
opis: **„⚠ ten sam kod w 2 wierszach"**.

Wynik na projekcie 73: pokazywanych 30 → **31**, doszła dokładnie ta jedna
pozycja.

## Wlasciwe rozwiazanie: duplikat = OSOBNE WIERSZE w oknie

⚠️ **Dwie pierwsze proby byly obejsciami i zostaly cofniete.** Pokazywaly
duplikat jako JEDEN wpis listy i kombinowaly, zeby dalo sie go scalic
(warunek `sum(ile) >= 2` zamiast `len(wybrane) >= 2`). To nie to:
**„Scal zaznaczone” z definicji laczy dwa zaznaczone wiersze**, a user
widzial jeden — nie mial czego zaznaczyc.

Lista pokazuje teraz **tyle wpisow, ile jest wierszy w arkuszu**:

```
klucz='SS60042RS20X42X12#264'  item_id=264   4 szt.
klucz='SS60042RS20X42X12#267'  item_id=267  13 szt.  material='Stal, miekka'
```

Klucz **musi** zostac unikalny — jest tozsamoscia wiersza w oknie (iid
w Treeview i element zbioru `_zaznaczone`). Stad `klucz#item_id`.

⚠️ **Rozbijamy TYLKO duplikaty identycznego zapisu** (`len(zapisy) == 1`).
Rozjazdy pisowni („KOŁO” vs „Koło”, „Nakrętka TR16x4” vs „…x4.”) zostaja
jednym wpisem z lista `identyczne` — tam scala sie PRZEMIANOWANIEM, nie
laczeniem wierszy.

⚠️ **Scalanie po `item_id`**, gdy wpisy je maja: bez tego zaznaczenie
jednego wiersza wciagneloby oba (`wiersze_kodu()` szuka po nazwie).
Wybor ma byc jawny.

Sprawdzone na projekcie 73: 91 wpisow, wszystkie klucze unikalne,
zaznaczenie obu → scalanie dostaje wiersze 264 i 267, suma 17 szt.

## ⚠️ PULAPKA: jeden wiersz pod DWOMA kluczami

Pierwsze wdrozenie rozbicia zepsulo liste — rozbilo **nie te pozycje**:
`6004` pokazalo sie dwa razy, a `SS 6004 2RS 20x42x12` **znikneto calkiem**.

Przyczyna: `wiersze_kodu()` przechodzi po WSZYSTKICH kolumnach nazw
(`KOLUMNY_NAZW = ("work_name", "src_name")`). Wiersz przepisany na inna
nazwe wraca wiec **dwa razy**:

```
id=264  src_name='6004'  work_name='SS 6004 2RS 20x42x12'
        -> raz pod kluczem '6004', raz pod 'SS60042RS20X42X12'
```

Klucz `#264` trafial do dwoch roznych pozycji naraz — a jest to `iid`
w Treeview. Tk odrzucal kolizje i cala pozycja przepadala z widoku.

**Naprawa:** przy budowaniu `szczegoly["wiersze"]` wiersz liczy sie tylko
dla swojej **AKTUALNEJ** nazwy — tej, ktora user widzi w arkuszu
(`work_name` przed `src_name`, kolejnosc z `KOLUMNY_NAZW`). Materialy
i ilosc sumuja sie jak dotad, bo tam duplikat nie szkodzil.

Po naprawie na projekcie 73: 90 wpisow, wszystkie klucze unikalne, zaden
wiersz BOM nie wystepuje w dwoch pozycjach, rozbite tylko `SS 6004 2RS`.

## (historyczne) Przycisk „Scal zaznaczone” milczal

Samo pokazanie pozycji nie wystarczyło. Lista pokazuje **jeden wpis na kod**,
więc duplikat stojący w dwóch wierszach arkusza jest tam **jednym** elementem.
A warunki liczyły pozycje listy, nie wiersze BOM-u:

```python
if len(wybrane) < 2:          # _scal — cichy return, bez komunikatu
state=... if len(wybrane) >= 2 ...   # przycisk zostawał szary
```

Użytkownik widział zaznaczoną pozycję i nieaktywny przycisk: „nie mam z czym
scalić". Właściwa miara to **liczba wierszy BOM-u** — `p["ile"]`:

```python
if sum(p.get("ile", 1) for p in wybrane) < 2:
```

Reszta `_scal` była już gotowa: `wiersze_kodu()` zwraca oba wiersze
(sprawdzone: id 264 i 267), `scal_wiersze()` je łączy.

⚠️ Napis na przycisku też pokazuje teraz **wiersze**, nie pozycje —
„Scal zaznaczone (2)" przy jednej zaznaczonej pozycji jest poprawne.

## ⚠️ Ślepa uliczka — nie powtarzać

Pierwsza próba szła w `subiekt_scalanie.Grupa.do_zmiany` /
`zaproponuj_dla_projektu()`. **To nie jest kod tego okna** — okno
„Scal kody handlowe" woła `pozycje_z_podobnymi()`. Zmiana została cofnięta
(`git checkout`). `zaproponuj_dla_projektu` obsługuje inną ścieżkę i steruje
ZAPISEM (podmiana nazw `stary → nowy`, `subiekt_scalanie.py` ~630) — tam
identyczne wiersze faktycznie nie mają czego podmieniać.

Duplikaty scala się przyciskiem **„Scal zaznaczone"** (scalanie WIERSZY,
`scal_wiersze`), nie przemianowaniem.

Powiązane: [[project_sklejanie_duplikatow_bom]], [[project_dopasuj_kartoteke_wiersza]].
