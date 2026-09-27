# PLAN — makro „Wstaw z magazynu" (Inventor ↔ Subiekt)

Stan: **plan, nic nie zaimplementowane.** Spisany 27.09.2026 po rozpoznaniu
na żywych danych. Wszystkie liczby niżej są **zmierzone**, nie szacowane.

## Czego ma dotyczyć

Makro w Inventorze pokazuje kartoteki Subiekta: **stan magazynowy**,
**miniaturę detalu**, a po wybraniu **wstawia model 3D** do otwartego
złożenia.

---

## 1. Rozpoznanie — co już istnieje

| warstwa | stan | uwagi |
|---|---|---|
| stany magazynowe | ✅ tryb `stan` mostu | |
| miniatury kartotek | ✅ tryb `zdjecie` mostu | 991 kartotek ma już rysunek (27.09) |
| katalog kartotek | ✅ tryb `katalog` | 3514 kartotek |
| RM_SERWER | ✅ port 5060, HMAC | **własny protokół TCP, NIE HTTP** |
| makra VBA | ✅ 8 sztuk | `ORING.ivb` ma gotowy wzorzec `Occurrences.Add` |
| **makro ↔ serwer** | ❌ **nie istnieje** | w makrach zero linii HTTP |
| **symbol → model 3D** | ❌ **nie istnieje** | patrz sekcja 2 |

⚠️ Wcześniejsze wrażenie, że „makra gadają z RM_BAZA", było **błędne**:
trafienia `grep` to `<meta http-equiv>` w raportach HTML i jeden komentarz
w `IAM_MACRO_Y.ivb`. Żadnej integracji nie ma.

---

## 2. Jak ustalić model 3D dla numeru rysunku — ROZSTRZYGNIĘTE

### ⛔ NIE po nazwie pliku

Sprawdzone na danych — nazwy nie mają ze sobą nic wspólnego:

```
2470-500.30 Gumka pryzmy FORMA.idw  →  gumka pryzmydsss.ipt
016-100.03 Uchwyt lusterka.idw      →  blaszka lusterka, 304 gr1,5mm.ipt
016-100.23 …                        →  Patykczakczak.ipt
```

Zbieżność przy `011-100.07 Trójkąt R1` → `trójkąt R1.ipt` to **przypadek**.
Zgadywanie po nazwie wstawiłoby nie ten model — i to po cichu.

### ⛔ NIE surowym odczytem IDW

Dwie próby, obie zawiodły:
* odczyt bajtów w `utf-16-le` + `latin-1` → 57% trafień;
* po dołożeniu `utf-16-be` → 75%, ale polskie znaki wychodzą rozsypane
  (`trójkąt r1.ipt` czytane jako `trójkŵ r1.ipt`), więc dopasowanie do
  indeksu plików zawodzi.

Starsze IDW to kontener **OLE** (`D0 CF 11 E0`), a referencje siedzą
w wewnętrznych strumieniach w formacie Inventora — nie jako czysty tekst.

### ✅ TAK — `Inventor.ApprenticeServer`

```python
app = win32com.client.Dispatch("Inventor.ApprenticeServer")
dok = app.Open(sciezka_idw)
for i in range(1, dok.File.ReferencedFiles.Count + 1):
    print(dok.File.ReferencedFiles.Item(i).FullFileName)
app.Close()
```

Zmierzone na `B:\Czujniki RM` (59 rysunków):

| wynik | ile | % |
|---|---|---|
| jeden model | 48 | 81% |
| kilka modeli | 0 | 0% |
| **rysunek bez modelu** | 11 | 19% |
| błąd odczytu | **0** | 0% |

**0,11 s na plik** → indeks całej biblioteki (1899 rysunków) w **~3,5 min**.

Dlaczego to jest wiarygodne:
* ścieżki wracają **rozwiązane do `B:`**, nie jako `c:\gbůwica r1 125\`
  z zepsutymi znakami — zero zgadywania kodowań;
* `ApprenticeServer` to **osobny, lekki proces** — nie dotyka sesji
  Inventora użytkownika (przy pomiarze miał otwartych 803 dokumenty);
* `FileManager.GetReferencedFiles` **nie istnieje** w Inventorze 2015 —
  nie próbować.

⚠️ Te 19% to **nie luka metody, tylko stan faktyczny**. Użytkownik
potwierdził: `016-100.05` naprawdę nie ma modelu, a `016-100.05X` ma
(`uchyt pionowy lusterka.ipt`) — dokładnie tak, jak odczytał Apprentice.
Makro ma w takim wypadku powiedzieć „ten rysunek nie ma modelu 3D",
a nie podstawiać cokolwiek.

---

## 3. Architektura

```
Inventor / VBA                nowy endpoint HTTP            istniejące
──────────────                ──────────────────            ──────────
okno „Wstaw z magazynu"
  ├─ szukaj ───────────────►  /makro/szukaj?q=…    ────────► most: katalog
  │  ◄── symbol, nazwa, stan, cena, miniatura, modele ◄──── most: zdjecie
  │                                                  ◄──── modele_3d (SQLite)
  └─ [Wstaw] ──────────────►  /makro/modele?symbol=… ──────► lista ścieżek
        └─► Occurrences.Add dla KAŻDEGO modelu
```

**Cała logika po stronie serwera** (decyzja użytkownika). Makro robi jedno
zapytanie i dostaje komplet — nie skleja danych z trzech źródeł w VBA.

### Dlaczego osobny endpoint HTTP, a nie protokół RM_SERWER

RM_SERWER mówi własnym protokołem na gołym TCP, z HMAC-SHA256 po
`request_id|cmd|args`. W VBA to praktycznie nie do zrobienia. `MSXML2.XMLHTTP`
umie HTTP i JSON — stąd osobne wejście **tylko do odczytu**, w sieci lokalnej.

---

## 4. Indeks `symbol → modele 3D`

**Budowany na stacji z Inventorem, przechowywany na serwerze w SQLite**
(decyzja użytkownika). W2019S nie ma Inventora i nie będzie miał, ale
mapowania mają leżeć tam, gdzie reszta danych systemu — nie w pliku obok.

```
stacja (Inventor)                          serwer W2019S
─────────────────                          ─────────────
skan B: → lista IDW            (20 s)
ApprenticeServer → referencje  (3,5 min)
   └─► map-model3d-zapisz ────────────────► subiekt_mapowania.sqlite
                                              tabela `modele_3d`
```

### Gdzie dokładnie

`subiekt_mapowania.sqlite` **już istnieje** na serwerze i ma gotowy routing:
`rm_serwer.py:373` kieruje każdą operację z prefiksem `map-` właśnie tam.
Leży w nim już tabela `polprodukty` (relacja rysunek → półfabrykat), więc
`modele_3d` trafia w to samo miejsce i ten sam backup.

### Tabela

```sql
CREATE TABLE modele_3d (
    numer_rysunku TEXT NOT NULL,      -- „016-100.03", klucz dopasowania
    sciezka       TEXT NOT NULL,      -- „B:\\Czujniki RM\\blaszka….ipt"
    kolejnosc     INTEGER DEFAULT 0,  -- jeden rysunek = kilka modeli
    idw           TEXT,               -- z którego IDW to wyczytano
    kto           TEXT,
    kiedy         TEXT,
    PRIMARY KEY (numer_rysunku, sciezka)
);
```

⚠️ Rysunek **bez modelu** (19% przypadków) też zasługuje na wpis — inaczej
przy każdym odświeżeniu indeksu Apprentice otwierałby go na nowo. Osobna
tabela `modele_3d_puste(numer_rysunku, idw, kiedy)` albo wiersz ze
`sciezka = ''`; do rozstrzygnięcia przy implementacji.

### Operacje mostu/serwera

Nowa operacja = **jeden wpis** w `ODCZYT` albo `ZAPIS` w
`rm_serwer_operacje.py` — ani serwer, ani klient nie wymagają zmian
(patrz nagłówek tego pliku, sekcja DOPISYWANIE OPERACJI):

| operacja | rodzaj | do czego |
|---|---|---|
| `map-model3d` | ODCZYT | modele dla jednego numeru rysunku |
| `map-model3d-many` | ODCZYT | dla listy numerów (makro pyta hurtem) |
| `map-model3d-zapisz` | ZAPIS | wynik skanu ze stacji |
| `map-model3d-czysc` | ZAPIS | przed pełnym przebudowaniem indeksu |

Odświeżanie: ręcznie po zmianach w bibliotece albo zadaniem raz dziennie.
Pusty wynik znaczy „rysunek bez modelu" i **jest informacją**, nie brakiem
danych.

---

## 5. Wstawianie modeli

**Wstawiamy WSZYSTKIE modele z listy** (decyzja użytkownika) — `2470-500.30`
ma dwa (`gumka pryzmydsss.ipt` + `...forma.ipt`) i oba mają wejść.

Wzorzec jest już w `ORING.ivb`:

```vb
Set oNewOcc = oAsmDef.Occurrences.Add(SCIEZKA_IPT, oMatrix)
```

Do rozstrzygnięcia przy implementacji:
* gdzie ustawić kolejne wystąpienia (ta sama macierz? przesunięcie?);
* co zrobić, gdy aktywny dokument **nie jest złożeniem** — wtedy nie ma
  gdzie wstawiać, trzeba odmówić z komunikatem.

---

## 5a. Znormalia — model po SYMBOLU kartoteki

Znormalia (łożyska, śruby, siłowniki) **nie mają numeru rysunku ani IDW**,
więc droga z sekcji 2 ich nie obejmuje. Reguła jest inna i prostsza:
**nazwa pliku modelu = symbol kartoteki Subiekta** (decyzja użytkownika).

Dopasowanie odporne na spacje, myślniki i wielkość liter — `6004 ZZ`
znajduje `6004ZZ.ipt`.

Zmierzone na żywych danych (27.09.2026): **14 z 723 znormaliów** ma dziś
model w bibliotece. Działające przykłady:

```
6004 ZZ     → 6004ZZ.ipt          UCFL 201    → UCFL201.iam
5M 25 CP    → 5M 25 CP.ipt        oring 20x3  → oring_20x3.ipt
```

⚠️ Te 2% to **stan początkowy, nie sufit metody**. Pozostałych 709 modeli
po prostu NIE MA w bibliotece — to nie kwestia nazewnictwa:

```
DN25 AISI 316   KRÓCIEC 28x1,5       (pliku .ipt nie ma nigdzie na B:)
Z 7640051       UCHWYT PLEKSI 4
GN 474-B12      GN 474-B12 Łącznik dwukierunkowy
```

**Kierunek docelowy:** modele wiąże się z Subiektem i nazywa nomenklaturą
Subiekta. Wtedy pokrycie rośnie samo, bez zmiany kodu — dopasowanie po
symbolu już działa. Kartoteka bez modelu zachowuje się jak rysunek bez
modelu: makro pokazuje stan i miniaturę, ale nie wstawia niczego.

---

## 6. Kolejność prac

| etap | zakres | ryzyko |
|---|---|---|
| **1** | skrypt na stacji: skan `B:` + Apprentice → `map-model3d-zapisz` | żadne — czysty odczyt, zapis tylko do tabeli mapowań |
| **2** | endpoint `/makro/szukaj` i `/makro/modele` (tylko odczyt) | restart usługi |
| **3** | makro: okno + wyszukiwarka + stan + miniatura, **bez wstawiania** | żadne |
| **4** | wstawianie modeli (`Occurrences.Add`) | dotyka dokumentu użytkownika |

Etapy 1–3 nic nie psują. Dopiero 4 zmienia cokolwiek w Inventorze.

---

## 7. Ustalenia (27.09.2026)

| # | sprawa | decyzja |
|---|---|---|
| 1 | port | **osobny** (np. 5061), nie ruszamy protokołu na 5060 |
| 2 | uwierzytelnienie | **bez** — endpoint tylko do odczytu, w LAN |
| 3 | wyszukiwanie | po **symbolu**, **nazwie kartoteki**, **numerze rysunku** i **nazwie pliku 3D** |
| 4 | znormalia | model dopasowywany **po symbolu** — patrz sekcja 5a |
| 5 | zakres dysków | **tylko `B:`**; `V:` poza planem |

Bez odpowiedzi zostaje tylko to, co rozstrzygnie się przy pisaniu kodu:
* gdzie ustawiać kolejne wystąpienia przy wielu modelach (sekcja 5);
* czy rysunki bez modelu trzymać w osobnej tabeli, czy jako pusty wiersz
  (sekcja 4).

---

## 8. Pliki rozpoznania

Skrypty zwiadowcze użyte do pomiarów leżą w scratchpadzie sesji
(`zwiad_ole.py`, `pomiar_b2.py`, `test_katalog.py`) — nie w repo, bo to
narzędzia jednorazowe. Gdyby trzeba było powtórzyć pomiar, sekcja 2
zawiera komplet potrzebnych wywołań.
