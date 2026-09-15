# PLAN AUTOMATYKA — dział automatyki w RM_BAZA

**Status: ROZPOZNANIE. Nic nie zaimplementowane, czeka na dane wejściowe.**
Rozmowa z 15.09.2026, do wznowienia.

---

## Pytanie wyjściowe

> „Mam w RM_BAZA nieużywane WAREHOUSE. Czy można całe MACHINES przekopiować
> i zrobić z WAREHOUSE drugi tryb dla działu automatyki?"

## Odpowiedź: NIE kopiować MACHINES

**`WAREHOUSE` nie jest osobnym modułem, który da się skopiować.** To 99
rozsianych warunków `if project_type == "WAREHOUSE"` — 80 z nich w samym
`RM_BAZA_v15_MAG_STATS_ORG.py`. Nie istnieje plik `machines.py` ani klasa,
którą można by zduplikować.

Cała realna różnica między trybami sprowadza się dziś do katalogu baz:

```python
# database_manager.py (kilka miejsc)
base_dir = self.projects_mag_dir if project_type == "WAREHOUSE" else self.projects_dir
```

Plus drobiazgi w nazwach plików i kluczach backupu. **Mechanizm już istnieje
i działa — trzeba go wypełnić treścią, nie duplikować.**

Skopiowanie 30 tys. linii, żeby użyć kilku procent funkcji, dałoby moduł,
w którym większość kodu jest martwa, a każda poprawka musi być zrobiona dwa
razy. To ta sama pułapka co dwa agenty AI —
patrz [`pamiec/project_ai_agents_two_places.md`](pamiec/project_ai_agents_two_places.md):
zmiana w jednym miejscu nie propaguje się do drugiego.

### Stan WAREHOUSE na 15.09.2026

87 projektów w bazie: **81 MACHINE, 6 WAREHOUSE**. Te 6 to numery 10–16
**bez nazw**, status `PROJEKT`. Martwe.

Decyzja: zostawić w spokoju albo docelowo usunąć — 99 warunków w kodzie to
koszt utrzymania bez korzyści. **Osobna sprawa, nie warunek dla automatyki.**

---

## Czego automatyka naprawdę potrzebuje

Ustalenia z rozmowy:

| Pytanie | Odpowiedź |
|---|---|
| Własny magazyn fizyczny? | **Nie — ten sam** |
| Detale w kartotece Subiekta? | **Nie ma ich** |
| Po co RM_BAZA zamiast Subiekta? | „żeby lepiej się pracowało na projektach, wszystko w jednym miejscu" |
| Operacje | przyjmowanie, wydawanie — **takie same** |
| Magazynier | **ten sam** |
| Detale mają | symbol, nazwę, opis |

**Wniosek: to nie jest osobny tryb aplikacji.** Te same operacje, na tych
samych danych, ten sam człowiek — tylko inny dział. Drugi moduł dałby dwa
okna robiące to samo i jednego magazyniera, który musi pamiętać, w którym
akurat jest.

### Co już działa i nie wymaga pisania

* okno **Magazyn** — `subiekt_magazyn_gui.py` (stany, progi, kartoteki)
* tryby mostu: **`pw`** (przyjęcie), **`rw`** (wydanie), `stan`, `stan-pozycji`,
  `progi`, `magazyn`, `magazyn-zaloz`, `magazyn-usun`
* **okno magazyniera** — lista kompletacyjna projektu, skaner, jedno RW
  (commit `1e563b9`)
* magazyn nr 2 — założony 07.09.2026,
  patrz [`pamiec/project_magazyn_nr2_migracja.md`](pamiec/project_magazyn_nr2_migracja.md)

**Przyjmowanie i wydawanie to dokładnie to, co robi Subiekt, a most już to
obsługuje.** Brakuje wyłącznie kartotek automatyki.

⚠️ **Nie budować przyjęć/wydań po stronie RM_BAZA.** Gdyby automatyka
przyjmowała i wydawała w RM_BAZA, a produkcja w Subiekcie, powstałyby dwa
źródła prawdy o tym samym magazynie.

---

## Proponowana kolejność

### 1. Zasiać kartoteki automatyki do Subiekta

Symbol, nazwa, opis — dokładnie to, co mają. Narzędzia gotowe:
* tryb mostu **`kartoteka`**
* **Edytor kartotek** — [`pamiec/project_subiekt_edytor_kartotek.md`](pamiec/project_subiekt_edytor_kartotek.md)
* okno **„Dopasowanie kartotek Subiekta"** — wiąże pozycje z arkusza
  z kartotekami; od 15.09 ma zakładkę **Podpowiedzi** i przepisuje pozycje
  bez numeru na symbol + nazwę z Subiekta
  ([`pamiec/project_dopasowanie_podpowiedzi.md`](pamiec/project_dopasowanie_podpowiedzi.md))

### 2. Sprawdzić, czy okno magazyniera im wystarcza

Zrobione dla produkcji. Jeśli automatyka pracuje tak samo — wystarczy dać
dostęp. Jeśli nie, dopiero wtedy wiadomo, czego brakuje, i będzie to drobna
zmiana, nie nowy moduł.

### 3. Projekty automatyki jako zwykłe projekty MACHINE

BOM, który zamiast numerów rysunku ma symbole z kartoteki. ZK, ZD i RW
zadziałają bez zmian.

---

## Otwarte: czy potrzebują drzewek?

To jedyna rzecz, która odróżnia projekt od zwykłej listy.

* **Bez drzewek** — płaska lista (symbol, nazwa, opis, ilość). Projekt
  automatyki to BOM bez złożeń; reszta działa identycznie. **Zero nowego kodu.**
* **Z drzewkami** — złożenia Z/ZZ, kompletacja. Też działa, ale ma pułapki:
  [`pamiec/project_subiekt_zk_komplety.md`](pamiec/project_subiekt_zk_komplety.md),
  [`pamiec/project_subiekt_puste_zlozenia_decyzje.md`](pamiec/project_subiekt_puste_zlozenia_decyzje.md)

⚠️ **To nie jest decyzja do podjęcia z góry.** Płaska lista i drzewko to ta
sama struktura w bazie — pozycja bez złożenia to po prostu pozycja. Można
zacząć płasko i dołożyć grupowanie później, bez przebudowy.

**Nie pytać ich o drzewka.** Spytać, jak prowadzą jeden montaż: w czym
trzymają listę części i czy dzielą ją na podzespoły. Odpowiedź powie
wszystko, a oni nie muszą wiedzieć, czym jest złożenie ZZ.

---

## Czego brakuje, żeby ruszyć

Automatyka ma **dwa źródła danych**:

1. **Excel** — lista prowadzona ręcznie
2. **Program do schematów z eksporterem elementów** — nazwa programu
   NIEUSTALONA (EPLAN? WSCAD? SEE Electrical? — formaty eksportu każdego
   z nich są znane i przewidywalne)

**Potrzebne do dalszej pracy:**

- [ ] **jeden przykładowy eksport** z programu do schematów
- [ ] **jeden przykładowy Excel** z listą części
- [ ] nazwa programu do schematów
- [ ] rząd wielkości: ile pozycji do zasiania

Z samego eksportu da się odczytać **bez pytania kogokolwiek**:
* czy elementy mają strukturę (szafa → listwa → aparaty) czy płaską listę
  — **to rozstrzyga sprawę drzewek**
* czy symbole są katalogowe (np. `XB4BA31`) — czyli czy da się je odnaleźć
  w Subiekcie
* co siedzi w opisie
* jak zapisane są ilości

RM_BAZA już żyje z eksportu BOM-u z Inventora — tu byłoby tak samo, tylko
z innego programu.

---

## Zasady, których się trzymamy

* ⛔ **Nie klonować MACHINES.** Jeden kod, wiele zestawów danych.
* ⛔ **Jedno źródło prawdy o magazynie — Subiekt.** RM_BAZA pokazuje i zleca,
  nie prowadzi własnej ewidencji stanów.
* ⛔ **CO PRZYSZŁO Z SUBIEKTA, NIE WRACA DO SUBIEKTA** — przy imporcie pozycji
  pilnować tej zasady,
  patrz [`pamiec/project_dopasowanie_podpowiedzi.md`](pamiec/project_dopasowanie_podpowiedzi.md).
