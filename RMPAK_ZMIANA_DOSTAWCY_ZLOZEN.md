# Zmiana dostawcy przy złożeniach Z/ZZ — ustalenia i stan

**Data:** 2026-09-10
**Status:** rozpoznane, NIEZAIMPLEMENTOWANE — czeka na decyzję gdzie i jak
**Kontekst:** `RMPAK_PRODUKCJA_USTALENIA.md` §9

---

## 1. Pytanie

Jak zmieniać złożenia Z/ZZ z produkcji własnej (RMPAK) na kupowane gotowe
u dostawcy. Ustalenie z rozmowy: **ma to być w oknie „Projekt / Aktualizacja"**,
a nie w oknie Złożeń.

---

## 2. Dlaczego NIE w oknie Złożeń — i dlaczego to nie blokuje tego pomysłu

Wcześniej odradziłem przepinanie dostawców w oknie Złożeń. Powód: `Projekt.cs`
**nie usuwa z ZK pozycji, które wypadły z planu** — pętla przechodzi wyłącznie
po tym, co plan zawiera. Ale to dotyczy tylko JEDNEGO kierunku.

Sprawdzone na `subiekt_produkcja.czy_produkcja_wlasna()`:

```text
KIERUNEK A — RMPAK → dostawca   („to jednak kupujemy")
    przed:  czy_produkcja_wlasna(None, "ZZ", ids) = True   (bez dostawcy = nasze)
    po:     czy_produkcja_wlasna(99,   "ZZ", ids) = False  (dostawca = zakup)
    SKUTEK: pozycja WCHODZI na ZK przy zasiewie → dopisze się normalnie ✓
            BEZPIECZNE

KIERUNEK B — dostawca → RMPAK   („jednak robimy u siebie")
    SKUTEK: pozycja WYPADA z planu ZK, ale ZOSTAJE na dokumencie → SIEROTA ⚠
            wymaga ręcznego usunięcia pozycji z ZK w Subiekcie
```

**Kierunek A, o który chodzi w tym wątku, jest bezpieczny.** Zasiew umie
dodawać pozycje do istniejącego ZK, więc nic nie zostaje po staremu.

Kierunek B nadal jest ryzykowny — okno Złożeń go **wykrywa** i ostrzega
(status SIEROTA, czerwony pasek), ale naprawa jest ręczna.

---

## 3. Kiedy zmiana jest bezpieczna

```text
PRZED zasiewem do Subiekta         → oba kierunki bezpieczne
PO zasiewie, kierunek A            → bezpieczny (pozycja dojdzie na ZK)
PO zasiewie, kierunek B            → SIEROTA, naprawa ręczna
PO wystawieniu PW                  → niebezpieczne, dokument już istnieje
```

---

## 4. Stan kodu — co jest, czego brakuje

**Jest:**

* `subiekt_projekt.read_project_items()` czyta `supplier_id` (linia ~159)
  i ustawia flagę `produkcja_wlasna` na pozycji.
* Reguła w jednym miejscu: `subiekt_produkcja.czy_produkcja_wlasna()`.
* Okno Projekt/Aktualizacja pokazuje pozycje w tabeli (`COLS`, ~1487).

**Brakuje:**

* Okno Projekt/Aktualizacja **nie ma zapisu do bazy projektu** — buduje plan
  i wysyła do mostu, nic nie zmienia lokalnie.
* Nie ma kolumny „Dostawca" w tej tabeli ani żadnej akcji zmiany.

**Wzorzec zapisu do skopiowania:** `subiekt_wyslij_zd.py:746`

```python
project_con.execute(
    "UPDATE items SET supplier_id=?, updated_at=? WHERE id=?",
    (supplier_id, teraz, item_id))
# + wpis do audytu:
log(item_id, 'EDIT', 'supplier_id', nazwy_dost.get(stare), nazwy_dost.get(nowy))
```

---

## 5. Do rozstrzygnięcia przed implementacją

### 5.1. Gdzie w oknie

* **menu prawym na wierszu** — „Ustaw dostawcę…", działa na wielu zaznaczonych
  naraz, nie zajmuje miejsca; wzorzec z innych okien RM_BAZA;
* **kolumna „Dostawca" do edycji** — widać od razu, co jest czyje, ale tabela
  ma już 10 kolumn;
* **oba** — kolumna tylko do odczytu, zmiana przez menu.

### 5.2. Co przy braku locka

Baza projektu bez locka jest **READ-ONLY** (log RM_BAZA: `REMOTE READ-ONLY`).
Na tym już się przewróciliśmy przy numerze PW — zapis cicho przepadał.

* komunikat „Weź lock projektu, żeby zmienić dostawcę" i przerwij, albo
* pozycja menu nieaktywna bez locka, z podpowiedzią dlaczego.

### 5.3. Czy ostrzegać przy kierunku B

Zmiana dostawca → RMPAK po zasiewie tworzy sierotę. Czy okno ma o tym
uprzedzać przed zapisem, czy zostawiamy wykrywanie w oknie Złożeń.

---

## 6. Skala — dane z projektu 22

```text
złożeń Z/ZZ razem:              50
  bez dostawcy (nasze):         25
  dostawca RMPAK:               13
  dostawca MAJA (kupowane):      9   ← tak wygląda efekt kierunku A
```

Na projekcie 3500 (id 71): 27 złożeń, 25 produkcji własnej, 2 kupowane.

---

## 7. Zasada, która za tym stoi

Pole **Dostawca** jest jedynym mechanizmem rozstrzygania „kupujemy czy
robimy" — świadomie nie dokładamy drugiego obok (§9 ustaleń). Wpisanie
realnego dostawcy przy złożeniu to decyzja człowieka wyrażona w polu, które
już istnieje i już to znaczy.
