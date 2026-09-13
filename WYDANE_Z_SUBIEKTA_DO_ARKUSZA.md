# „Ilość dostarczonych" czytana z Subiekta

**Data:** 2026-09-13
**Status:** WDROŻONE — `subiekt_wydane_do_arkusza.py`
**Dotyczy:** arkusza głównego RM_BAZA, niezależnie od schowka montażowego

---

## ⛔ KLUCZOWA REGUŁA: NADPISUJEMY TYLKO TO, CO SUBIEKT ZNA

**POZYCJA, KTÓREJ SUBIEKT NIE ZNA, ZOSTAJE NIETKNIĘTA.**
**JEJ „ILOŚĆ DOSTARCZONYCH" DALEJ WPISUJE SIĘ RĘCZNIE.**

Nie każda pozycja projektu żyje w Subiekcie. Usługi, kooperacja, detale
nieskartotekowane istnieją tylko w RM_BAZA — dla nich `delivered_qty`
**musi zostać polem ręcznym**, bo nikt inny go nie wypełni. Nadpisanie ich
zerem skasowałoby jedyną informację, jaką ktoś tam wpisał.

```text
symbol JEST w odpowiedzi Subiekta   →  delivered_qty = wydano z RW
symbolu NIE MA w odpowiedzi         →  ZOSTAJE, CO BYŁO (wpis ręczny)
```

Rozpoznanie jest darmowe: tryb `wydanie-stan` zwraca **wyłącznie symbole
mające ślad w dokumentach projektu** (ZK, PW albo RW). Czego tam nie ma —
tego nie ruszamy. Nie trzeba żadnego znacznika „to pozycja z Subiekta".

---

## 1. Dlaczego to w ogóle powstało

Do 13.09.2026 `delivered_qty` była polem **wyłącznie ręcznym**: wpisywanym
w arkuszu albo przez stary skaner „Uzupełnianie DOSTARCZONO".

Kolumna SUBIEKT w arkuszu pokazywała trzy rzeczy — czy jest kartoteka, czy
jest ZK, czy jest ZD. **Wydania nigdy nie były w jej zakresie.** Nagłówek
`StanPozycji.cs` mówi to wprost:

> FZ (przyjęcia) świadomie POMINIĘTE — krok 13 przepływu nie jest zrobiony,
> a zgadywanie „przyszło" z niepełnych danych byłoby gorsze niż brak kolumny.

Skutek: **RW wystawione w Subiekcie nie zmieniało w arkuszu nic.** Wyszło
przy pierwszym wydaniu ze schowka — dokument powstał, magazynier zajrzał
do arkusza, a tam zero (projekt 3500, detal `2621-100.28`, RW na 1 szt.).

---

## 2. Skąd biorą się liczby

Tryb mostu **`wydanie-stan`** — ten sam, którego używa okno wydania. Zwraca
per symbol:

| pole | znaczenie |
|---|---|
| `potrzeba` | z ZK (zakupy) albo PW (produkcja własna) |
| `wydano` | **suma RW tego projektu** ← to nas interesuje |

Liczy je Subiekt, po numerze projektu w Uwagach dokumentu. Koszt: **0,08 s**
przez stały most.

Most **nie wymagał żadnych zmian** — dane już tam były, brakowało tylko
strony, która je zapisze do arkusza.

---

## 3. NADPISUJEMY, NIE DODAJEMY

`delivered_qty = wydano`, a nie `delivered_qty += wydano`.

Subiekt jest właścicielem faktu magazynowego, więc arkusz ma pokazywać
**jego sumę**, a nie to, co RM_BAZA zdążyła zaobserwować. Dodawanie
rozjeżdżałoby się przy:

* RW wystawionym poza RM_BAZA (ktoś zrobił dokument ręcznie w Subiekcie),
* powtórzonym odświeżeniu (ta sama liczba doliczona dwa razy),
* korekcie dokumentu w Subiekcie (usunięta pozycja nigdy by nie zeszła).

Wiersz, w którym liczba się nie zmieniła, **nie jest dotykany** — dzięki
temu `delivered_updated_at` nadal znaczy „kiedy naprawdę się zmieniło".

---

## 4. Co widzi użytkownik

`zapisz()` zwraca listę **faktycznych** zmian `(item_id, symbol, przed, po)`
— tylko tych, w których liczba się różni. Wołający ma z czego zbudować
raport „przed → po", zgodnie z zasadą **nic po cichu**.

Każda zmiana idzie też do dziennika pozycji (`_log_item_change`), więc
w historii wygląda tak samo jak ręczna poprawka.

---

## 5. Lock jest wymagany

Zapis idzie przez `db_manager.project_con` — połączenie arkusza do **kopii
lokalnej**. Bez locka jest READ-ONLY, a zapis obok tego połączenia i tak
zniknąłby przy najbliższym wgraniu kopii na serwer.

Wołający musi więc sprawdzić lock i powiedzieć, gdy go nie ma — zamiast
zapisywać w próżnię.

---

## 6. Sprawdzone

Test na prawdziwej strukturze `items` (kopia DDL z `project_71`):

```text
PRZED                          PO
2621-100.28    (puste)         1.0     ← Subiekt zna, RW 1 szt.
2627-100.01    3.0             5.0     ← Subiekt zna, RW 5 szt.
USL-SPAW       7.0             7.0     ← SUBIEKT NIE ZNA — NIETKNIĘTE
2627-200.04    2.0             0.0     ← Subiekt zna, brak RW → 0
```

Powtórne odświeżenie tymi samymi danymi: **0 zmian**.

---

## 7. Do domknięcia

1. **Kiedy odświeżać?** Dziś moduł jest gotowy, ale nikt go jeszcze nie
   woła. Naturalne miejsca: przy „Przejmij Lock" (mamy wtedy świeżą kopię
   i prawo zapisu) albo przycisk „Odśwież z Subiekta" na żądanie.
2. **Czy pokazywać raport zmian**, czy odświeżać po cichu? Zasada „nic po
   cichu" mówi, że przy pierwszym uruchomieniu na projekcie zmian może być
   dużo — warto je pokazać, choćby zbiorczo.
3. **Stary skaner** („Uzupełnianie DOSTARCZONO") wpisuje w to samo pole.
   Po odświeżeniu z Subiekta jego wpisy zostaną nadpisane dla pozycji,
   które Subiekt zna — do sprawdzenia, czy tak ma być.
