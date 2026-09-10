# Migracja dokumentów na nowy format Uwag i Tytułu

Instrukcja do przeprowadzenia **na bazie firmowej**. Na demo (M-OLD) zostało
to już zrobione 10.09.2026 — ten dokument opisuje, jak powtórzyć to
w firmie i czego się spodziewać.

---

## 1. Co się zmieniło i dlaczego

Do 10.09.2026 numer projektu trafiał do Uwag w **czterech niezgodnych
formatach**, które nawzajem się nie rozumiały:

| Kto wystawiał | Co lądowało w Uwagach |
|---|---|
| Formularze RW/PW/ZD z Edytora, ZK z arkusza | `2741` |
| ZK z mostu (gdy `uwagi` puste) | `Projekt 2741` |
| PW z kalkulatora RMPAK | `RM_BAZA — PROJEKT 2741` |
| RW z kalkulatora RMPAK | `RM_BAZA — PROJEKT 2741 \| PW: PW 3/MASTER/2026` |

`numer_projektu_z_uwag()` brał **całą treść Uwag** jako numer, więc trzy
z czterech formatów nie pasowały do niczego.

### Format docelowy

```text
Uwagi:  2741 Projekt          ← pierwszy wiersz: numer + słowo dla człowieka
        pilne, do piątku      ← drugi wiersz i dalej: uwagi użytkownika

Tytuł:  RM_BAZA 2741          ← znacznik: to wystawiła RM_BAZA
```

- **Numer projektu** = pierwszy człon pierwszego wiersza Uwag (do pierwszej
  spacji). Słowo „Projekt" jest tylko dla człowieka, kod go nie czyta.
- **Uwagi użytkownika** = od drugiego wiersza w dół.
- **Rozpoznanie „nasz dokument"** = samo `RM_BAZA` w Tytule.

### Dlaczego akurat tak

**Uwagi SIĘ DRUKUJĄ**, Tytuł nie — sprawdzone na wzorcu wydruku (sekcja
„Uwagi • Notes"). Dlatego treść dla ludzi idzie do Uwag, a techniczny
znacznik do Tytułu. Wcześniej było odwrotnie i opis dokumentu był
niewidoczny na papierze.

Znacznik `RM_BAZA` musiał wyprowadzić się z Uwag, bo pierwszy wiersz zajął
numer projektu — z przodu się nie mieści, a doklejony niżej byłby nie do
odróżnienia od uwagi człowieka.

**Sam numer w Uwagach nie dowodzi, że dokument jest nasz** — użytkownik
zakładający ZK ręcznie w Subiekcie też go wpisuje. Stąd znacznik w Tytule:
Tytuł się nie drukuje i nikt nie wypełnia go ręcznie, więc jego obecność
jest wiarygodna.

---

## 2. Zanim zaczniesz

### Wymagania

1. **Kod z gita** — `git pull`, potem **przebuduj most**:
   ```
   cd subiekt_sfera/NexoRecon
   dotnet build -c Release
   ```
   Jeśli build zgłosi, że plik jest zablokowany — ubij proces `NexoRecon`
   (stały most trzyma stary kod).

2. **Kopia bazy Subiekta** — to zapis do bazy produkcyjnej. Migracja zmienia
   tylko pola tekstowe (Uwagi, Tytuł), nie rusza pozycji ani kwot, ale
   cofnąć da się wyłącznie z kopii.

### ⚠️ Bez kompatybilności wstecz

Stare formaty **nie są już rozumiane**. Dokument nieprzepisany przestaje
być odnajdywany: kalkulator nie zobaczy PW, „Wystaw RW" zostanie
wyszarzone, a zapis BOM-u do istniejącego ZK odmówi.

Nie dodawaj obsługi starych formatów „na wszelki wypadek" — to właśnie ona
sprawiła, że zapis i odczyt patrzyły na dwa różne stringi.

---

## 3. Rozpoznanie: co wymaga poprawy

Uruchom na bazie firmowej — **tylko odczyt, nic nie zmienia**:

```bash
python -c "
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import subiekt_bridge
from subiekt_zamowienia import numer_projektu_z_uwag, nasz_dokument
d = subiekt_bridge.call('dokumenty', {'limit': 800}, timeout=600, write=False)
docs = (d or {}).get('dokumenty', [])
print('RAZEM:', len(docs))
for x in sorted(docs, key=lambda a: (a.get('Rodzaj') or '', a.get('Numer') or '')):
    u = (x.get('Uwagi') or '').strip()
    if not u:
        continue
    print('%-3s %-22s znacznik=%-5s numer=%-10r uwagi=%r' % (
        x.get('Rodzaj'), x.get('Numer'),
        'TAK' if nasz_dokument(x.get('Tytul')) else 'nie',
        numer_projektu_z_uwag(u), u[:60]))
"
```

**Jak czytać wynik:**

| Co widzisz | Znaczenie |
|---|---|
| `znacznik=TAK`, `numer='2741'` | gotowe, nie ruszać |
| `numer='RM_BAZA'` lub `'Projekt'` | stary format — **do poprawy** |
| `znacznik=nie`, numer wygląda sensownie | albo nasz sprzed zmiany, albo **cudzy ręczny** — sprawdź w Subiekcie, kto go wystawił |
| Uwagi typu „Stany startowe magazynu" | nie dotyczy projektu, **zostawić** |

Ostatni wiersz jest ważny: nie każdy dokument z tekstem w Uwagach jest
projektowy. Na demo z 32 dokumentów poprawki wymagały **3**, reszta to
inwentaryzacja, czyszczenie po testach i puste WZ.

---

## 4. Migracja

### Dlaczego jawna lista, a nie automat

Stary format sklejał numer z opisem w jednym zdaniu
(`RM_BAZA — PROJEKT 3500 dupal`) i wariantów było kilka. Automat musiałby
**zgadywać**, gdzie kończy się numer, a zaczyna opis — przy pomyłce
nadpisałby dane w bazie produkcyjnej. Dokumentów jest niewiele, więc
człowiek wpisuje wprost, co ma być, a most tylko wykonuje.

### Krok 1 — plan

Utwórz `migracja_plan.json` na podstawie rozpoznania z punktu 3:

```json
{
  "dokumenty": [
    { "rodzaj": "ZK", "numer": "ZK 1/CENTRALA/2026",
      "projekt": "3500", "uwagi": "dupal" },
    { "rodzaj": "PW", "numer": "PW 2/MASTER/2026",
      "projekt": "3500", "uwagi": "dupal" },
    { "rodzaj": "RW", "numer": "RW 1/MASTER/2026",
      "projekt": "3500", "uwagi": "dupal | PW: PW 2/MASTER/2026" }
  ]
}
```

- `rodzaj` — `ZK`, `ZD`, `PW`, `RW` albo `WZ`
- `numer` — pełna sygnatura, dokładnie jak w Subiekcie
- `projekt` — **sam numer**, bez nazwy
- `uwagi` — co ma zostać pod numerem (opcjonalne); przy RW warto zachować
  numer źródłowego PW

Most sam złoży z tego `Uwagi = "<projekt> Projekt\n<uwagi>"` oraz
`Tytuł = "RM_BAZA <projekt>"`.

### Krok 2 — suchy przebieg

```bash
subiekt_sfera/NexoRecon/bin/Release/NexoRecon.exe migracja-uwagi \
    --plan=migracja_plan.json --out=sucho.json
```

Bez `--zapisz` **nic się nie zapisuje**. Wynik pokazuje PRZED → PO dla
każdego dokumentu:

```text
Uwagi: „3500” → „3500 Projekt ⏎ dupal”   Tytuł: „3500 dupal” → „RM_BAZA 3500”
```

`⏎` oznacza przejście do drugiego wiersza. **Przeczytaj to i sprawdź**,
zanim ruszysz dalej — zwłaszcza czy nic wartościowego nie znika z Tytułu.

### Krok 3 — zapis

```bash
subiekt_sfera/NexoRecon/bin/Release/NexoRecon.exe migracja-uwagi \
    --plan=migracja_plan.json --zapisz --out=zapis.json
```

### Krok 4 — weryfikacja odczytem

Nie ufaj raportowi zapisu, sprawdź co naprawdę siedzi w bazie:

```bash
python -c "
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import subiekt_bridge
from subiekt_zamowienia import numer_projektu_z_uwag, uwagi_czlowieka, nasz_dokument
cel = {'ZK 1/CENTRALA/2026', 'PW 2/MASTER/2026', 'RW 1/MASTER/2026'}
d = subiekt_bridge.call('dokumenty', {'limit': 800}, timeout=600, write=False)
for x in (d or {}).get('dokumenty', []):
    if x.get('Numer') not in cel: continue
    u = x.get('Uwagi') or ''
    print('%-20s numer=%r uwagi=%r nasz=%s' % (
        x.get('Numer'), numer_projektu_z_uwag(u), uwagi_czlowieka(u),
        nasz_dokument(x.get('Tytul'))))
"
```

Dla każdego wiersza `nasz=True` i numer bez śmieci.

### Krok 5 — sprawdzenie end-to-end

```bash
python -c "
import subiekt_produkcja as sp
dok = sp.dokumenty_produkcji('3500', timeout=600)
print('PW:', [d['numer'] for d in dok['PW']])
print('RW:', [d['numer'] for d in dok['RW']])
"
```

Jeśli kalkulator produkcji widzi dokumenty — migracja się udała.

---

## 5. Czego migracja NIE robi

**Nie ustawia znacznika na dokumentach bez numeru projektu.** Inwentaryzacje,
zakupy magazynowe, dokumenty wystawione ręcznie w Subiekcie zostają
nietknięte — i tak ma być.

**Nadpisuje Tytuł w całości**, także domyślną nazwę typu, którą wstawia tam
Subiekt („Przychód wewnętrzny", „Rozchód wewnętrzny"). To była świadoma
decyzja: nowe dokumenty z RM_BAZA dostają sam znacznik, więc stare mają
wyglądać tak samo. Jeśli w Tytule jest coś, czego szkoda — przenieś to
najpierw do `uwagi` w planie.

---

## 6. Skutki uboczne, o których trzeba wiedzieć

### Dokumenty bez znacznika stają się „cudze"

Od tej zmiany operacje, które dokument **zmieniają lub kasują**, wymagają
znacznika `RM_BAZA` w Tytule:

| Operacja | Zachowanie przy braku znacznika |
|---|---|
| Dopisanie BOM-u do istniejącego ZK | odmawia, mówi co wpisać w Tytuł |
| Cofnięcie projektu | **nie kasuje**, raportuje jako `pominiete` |
| Usunięcie pozycji z ZK | odmawia |
| Blokada „projekt ma już ZK" | działa dalej, także dla ręcznych |

To celowe: numer w Uwagach wpisuje też człowiek, więc sam numer nie
uprawnia do skasowania cudzego dokumentu.

**Praktycznie:** dokumenty sprzed migracji, których nie przepiszesz, będą
pomijane przy cofaniu projektu. Jeśli mają wrócić pod kontrolę RM_BAZA,
wystarczy wpisać w ich Tytuł `RM_BAZA <numer>` — ręcznie w Subiekcie albo
tym samym trybem `migracja-uwagi`.

### Wykrywanie ręcznych ZK

Przy podglądzie zapisu BOM-u RM_BAZA zgłasza ZK, które mają numer projektu
w Uwagach, ale nie mają znacznika — z gotową instrukcją i wpisem na listę
„Do zrobienia" projektu.

⚠️ To pomoc, **nie gwarancja**: wykrywa tylko numer stojący na początku
Uwag. ZK z Uwagami `Projekt 3500`, `proj. 3500` albo pustymi nie zostanie
znalezione i drugie ZK powstanie bez ostrzeżenia. Pełne wykrycie dubletu
wymagałoby porównywania pozycji dokumentów — nie jest zrobione.

---

## 7. Gdzie to siedzi w kodzie

Reguła jest w **jednym miejscu po każdej stronie** — nie powtarzaj jej
w nowym kodzie, wołaj te funkcje:

| Python (`subiekt_zamowienia.py`) | C# (`Znacznik.cs`) | Co robi |
|---|---|---|
| `zloz_uwagi(projekt, uwagi)` | `Znacznik.Uwagi()` | składa treść Uwag |
| `numer_projektu_z_uwag(uwagi)` | `Znacznik.NumerProjektu()` | wyciąga numer |
| `uwagi_czlowieka(uwagi)` | `Znacznik.UwagiCzlowieka()` | treść od 2. wiersza |
| `tytul_dokumentu(projekt)` | `Znacznik.Tytul()` | `RM_BAZA <numer>` |
| `nasz_dokument(tytul)` | `Znacznik.Nasz()` | czy nasz |
| `sam_numer(projekt)` | — | numer z nazwy projektu |

`sam_numer()` jest ważne: kalkulator RMPAK trzyma **pełną nazwę**
(`3500 dupal`), a okno projektu sam numer. Wszystkie powyższe funkcje
przyjmują jedno i drugie.

Tryb migracji: `subiekt_sfera/NexoRecon/Migracja.cs`.

---

## 8. Stan demo po migracji (10.09.2026)

Dla porównania — tak wygląda baza, na której to przećwiczono:

| Dokument | Uwagi | Tytuł |
|---|---|---|
| `ZK 1/CENTRALA/2026` | `3500 Projekt` / `dupal` | `RM_BAZA 3500` |
| `ZK 2/CENTRALA/2026` | `2627 Projekt` / … | `RM_BAZA 2627` |
| `PW 2/MASTER/2026` | `3500 Projekt` | `RM_BAZA 3500` |
| `PW 3/MASTER/2026` | `3500 Projekt` | `RM_BAZA 3500` |
| `RW 1/MASTER/2026` | `3500 Projekt` / `PW: PW 2/MASTER/2026` | `RM_BAZA 3500` |

Z 35 dokumentów znacznik ma 6; reszta to inwentaryzacja, dokumenty demo
i zasiew testowy — świadomie nietknięte.
