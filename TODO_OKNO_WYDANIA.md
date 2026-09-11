# TODO — okno wydania z magazynu (subiekt_wydanie_gui.py)

Znalezione w code review 12.09.2026, jeszcze nie naprawione.

## Średnie: brak fallbacku do starego CLI

Wywołania mostu w oknie idą bez fallbacku:

- `subiekt_wydanie_gui.py:575` (odczyt startowy `wydanie-stan`)
- `subiekt_wydanie_gui.py:1316` (kontrola przed wystawieniem RW)

Wzorzec fallbacku istnieje gdzie indziej — patrz warstwa wywołań w
`subiekt_magazyn_gui.py:76` (`_uruchom`): stały most, a gdy się nie da go
uruchomić, leci stare CLI (`_uruchom_cli`), więc okno działa dalej, tylko
wolniej.

**Skutek:** gdy stały most nie wystartuje, magazynier nie przejdzie ani
odczytu startowego, ani kontroli przed RW — okno wydania staje całkowicie,
podczas gdy reszta RM_BAZA (magazyn, dokumenty) ma zapasową ścieżkę.

**Do zrobienia:** przepuścić oba wywołania przez tę samą warstwę z
fallbackiem co `subiekt_magazyn_gui.py`, albo dodać fallback bezpośrednio
w `subiekt_bridge.call`.

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

## Niskie/średnie: twardy limit 400 dokumentów

- `subiekt_sfera/NexoRecon/WydanieStan.cs:61` (`const int LIMIT = 400`)
- Użycie: `WydanieStan.cs:153` (`.Take(LIMIT)`)

**Skutek:** możliwe zaniżenie „wydano wcześniej", jeśli projekt ma starsze
RW poza ostatnimi 400 dokumentami danego rodzaju w bazie.

**Do zrobienia:** sprawdzić, czy limit jest per rodzaj dokumentu czy łączny,
i czy 400 realnie wystarcza na długo żyjące projekty — albo podnieść limit,
albo filtrować po projekcie na poziomie zapytania zamiast brać N najnowszych
i filtrować w pamięci.
