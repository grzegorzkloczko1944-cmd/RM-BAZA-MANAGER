# TODO — okno wydania z magazynu (subiekt_wydanie_gui.py)

Znalezione w code review 12.09.2026. Pozycje bez znacznika ✅ czekają.

## ✅ ZROBIONE 13.09.2026: awaria mostu blokuje okno

Pierwotnie zapisane jako „brak fallbacku do starego CLI". Rozstrzygnięte
INACZEJ — decyzja użytkownika: *„zamiast kombinować — zablokować wydania
gdy most padł — to jest awaria"*.

Fallbacku świadomie NIE dokładamy. Bez pewnego odczytu z Subiekta nie wolno
wydawać (§4 planu), a wolniejsza droga przez stare CLI tylko udawałaby, że
jest dobrze.

### Co było naprawdę zepsute

Czerwone „⛔ Wydanie niemożliwe" było **samym napisem** — `var_polaczenie`
nikt nie sprawdzał. Skanowanie szło dalej, bo `_skanuj` pyta o stany INNĄ
drogą niż most (`subiekt_stany.query_stock`), więc kody się znajdowały.
Magazynier kompletował całą paletę i dowiadywał się o awarii dopiero przy
„Zakończ wydanie", gdy obowiązkowy świeży odczyt padał drugi raz. Cała
praca szła w kosz.

Awaria była przy tym **wybiórcza i myląca**: reszta RM_BAZA działała
normalnie, więc wyglądało to na usterkę jednego okna bez powodu.

### Co jest teraz

- **duże czerwone okno** na wierzchu (`_alarm_awarii`) — z dzwonkiem,
  `grab_set()` i przyciskiem „Rozumiem"; okno wydania bywa na pełnym
  ekranie, a magazynier ma ręce zajęte skanerem
- **czerwona belka pod nagłówkiem** (`_belka_awarii`) — zostaje po
  zamknięciu alarmu, bo inaczej jedynym śladem byłby napis Arial 8
  w dolnym rogu (użytkownik: *„na czerwono jest tylko napis w rogu"*)

- flaga `self.polaczony` — ustawiana w obu ścieżkach odczytu
  (startowej `_po_odczycie` i kontrolnej `_po_kontroli`)
- `_ustaw_blokade_awarii()` wyszarza pole skanera, „Dodaj" i „Zakończ"
- strażnicy w `_skanuj`, `_dodaj_do_sesji` i `_zakoncz` — bo skrót
  `<Return>` na `spin_ilosc` omija wyszarzony przycisk
- **„Odśwież" zostaje czynny** — to jedyna droga powrotu
- **sesja NIE jest kasowana** — awaria bywa chwilowa, a skasowanie
  skompletowanej palety byłoby karą za cudzą usterkę; komunikat mówi
  wprost, że pozycje nie przepadły
- awaria wykryta dopiero przy zapisie też przełącza okno w tryb awarii
  (wcześniej pasek dalej pokazywałby „połączono")


### ⚠️ Przy okazji: 5 zepsutych obsług błędu

Żywy test z ubitym mostem wykrył `NameError` w `_po_odczycie` — i ten sam
błąd w czterech innych miejscach:

```python
self.after(0, lambda: self._po_odczycie(None, str(e), None))
#                                            ^ 'e' juz nie istnieje
```

Python kasuje `e` na końcu bloku `except`, a lambda sięga po nią PÓŹNIEJ,
w `after`. Skutek: **obsługa błędu sama się wywalała** i nie wykonywała —
pasek dalej pokazywał „Łączenie z Subiektem…", pole skanera zostawało
aktywne. Najgroźniejsze przy zapisie (linie 1506, 1544): komunikat o
nieudanym wystawieniu RW nigdy nie dochodził do magazyniera.

Naprawione wszędzie przez związanie wartości domyślnym argumentem:
`lambda b=str(e): ...`

**Wniosek na przyszłość:** testy na atrapach tego nie złapały. Dopiero
uruchomienie okna z realnie niedziałającym mostem.

## Średnie: parametr `magazyn` w `wydanie-stan` przyjmowany, ale nieużywany

- Sygnatura: `subiekt_sfera/NexoRecon/WydanieStan.cs:63`
- Zbieranie danych (ZK/PW/RW) leci **globalnie**, bez filtra magazynu:
  `WydanieStan.cs:81`, `:82`, `:85`

**Skutek:** przy więcej niż jednym magazynie liczniki „wydano"/„potrzeba"
mogą mieszać dane między magazynami — okno pokaże np. wydanie z MASTER jako
pokrywające potrzebę liczoną też z innego magazynu.

**Do zrobienia:** albo filtrować dokumenty po `Magazyn` w zapytaniu, albo —
jeśli świadomie liczymy sumarycznie przez wszystkie magazyny — usunąć
parametr z sygnatury i dopisać komentarz czemu.

## ✅ ZROBIONE 13.09.2026: limit 400 dokumentów USUNIĘTY

Użytkownik: *„limit 400 to wielki błąd"* — i miał rację, wcześniejsza ocena
(„per rodzaj dokumentu, więc wystarczy na długo") była za łagodna.

### Dlaczego to był poważny błąd

`Take(400)` wykonywał się **PRZED** sprawdzeniem numeru projektu: baza
zwracała 400 najnowszych dokumentów JAKICHKOLWIEK, a dopiero potem pętla
odsiewała nasze. RW to najczęstszy dokument w firmie — wystawiany codziennie
na wszystkie projekty naraz — więc 400 ostatnich RW to może być kilka
tygodni. Starsze RW projektu wypadały poza okno.

Skutek **cichy**: `wydano` za małe → `pozostało` za duże → magazynier wydaje
**drugi raz** to, co już wydano. Nic nie ostrzegało, liczby wyglądały
wiarygodnie. Gorsze niż awaria mostu: tam okno się zatrzymuje, tu spokojnie
kłamie.

### To był już drugi raz

`Take(100)` na ZK w `Projekt.cs` powodował zakładanie DRUGIEGO ZK dla tego
samego projektu — zgłoszone 07.09.2026 (*„user założy projekt na projekcie
i narobi się bałagan"*). Tam limit też usunięto, a nad
`Projekt.ZnajdzZkProjektu` stoi komentarz z tą historią.

### Co zrobione

Limit usunięty, w jego miejsce komentarz ⛔ z pełnym uzasadnieniem, żeby
nikt go nie dołożył z powrotem.

**Zmierzone przez stały most (baza demo):** 0,08 s — tyle samo co z limitem.
Koszt nigdy nie leżał w liczbie dokumentów, tylko w logowaniu do Sfery
(~17 s), które stały most płaci RAZ.

⚠️ Baza demo jest uboga w dokumenty — na firmowej, z realną historią RW,
warto zmierzyć ponownie.

### Gdyby kiedyś realnie bolało

Filtrować **po projekcie**, nie po liczbie najnowszych. Ale uwaga: predykatu
z `Znacznik.NumerProjektu` nie da się przetłumaczyć na SQL — `ObjectQuery`
zwróci wtedy po cichu **pustkę** zamiast błędu (pułapka opisana
w `Projekt.cs:752`). Filtr musi iść PO `ToList()`.
