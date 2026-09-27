# PLAN — makro „Wstaw z magazynu" (Inventor ↔ Subiekt)

Stan: **etap 1 napisany (27.09.2026), jeszcze nie uruchomiony na produkcji.**
Spisany 27.09.2026 po rozpoznaniu na żywych danych. Wszystkie liczby niżej
są **zmierzone**, nie szacowane. Przebieg etapu 1 — sekcja 6a.

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

## 5a. Znormalia — model z pary OUT + IAM (inżynieria odwrotna)

Znormalia (łożyska, siłowniki, paski) **nie mają numeru rysunku ani IDW**,
więc droga z sekcji 2 ich nie obejmuje. Pierwsze podejście — „nazwa pliku
modelu = symbol kartoteki" — dało **14 z 723 (2%)** i zostało **porzucone**:
brakujących modeli nie ma pod żadną nazwą, więc to nie był problem
nazewnictwa.

### Skąd naprawdę wziąć mapowanie

Pomysł użytkownika (27.09.2026): normalia **siedzą w złożeniach**, a tam
mają przypisany model. Zmierzone i potwierdzone.

Łańcuch danych, którym powstaje BOM:

```
model 3D → IDW (tabelka — TU użytkownik poprawia nazwy) → CSV → importer → OUT.xlsx
```

Stąd dwa źródła, które trzeba zestawić:

| źródło | co wie | czego nie wie |
|---|---|---|
| `OUT.xlsx`, arkusz `ELEMENTY ZNORMALIZOWANE` | nazwę wg tabelki IDW (`688ZZ`) + ilość | pliku modelu |
| IAM przez `ApprenticeServer` | plik modelu + ilość wystąpień | nazwy z tabelki |

⚠️ Kolumna **`Pliki 3D` w OUT to NIE ścieżka** — trzyma flagę `STP`
(„istnieje eksport STEP"). `import_bom.py:369` ją czyta i nic z nią nie robi.
Sprawdzone: w `C:\iLogic` nie ma kodu, który by ją wypełniał ścieżką.

### Part Number — most dla zwykłych detali

Detale RMPAK mają w modelu `Part Number` równy numerowi rysunku, więc dla
nich mapowanie jest **pewne bez żadnej heurystyki**:

```
Oś kół pozycjonera.ipt      PN=PL-300.06
Koło pod łańcuch 06-B2.ipt  PN=PL-300.05
```

Znormalia mają `PN` **puste** — bo nazwę (`688ZZ`) nadaje się w tabelce IDW,
nie w modelu. Dlatego tylko one wymagają dopasowania.

### Reguła dopasowania (zmierzona)

Kandydaci = komponenty złożenia **bez Part Number**. Punktacja:

| sygnał | pkt |
|---|---|
| cały symbol z OUT zawarty w nazwie komponentu/pliku | 20 |
| wspólny kod katalogowy (≥4 znaki, zawiera cyfrę) | 12 + długość |
| kod jako podciąg | 9 |
| wspólne słowa (≥4 litery) | 2 / słowo |
| zgodna ilość | 3 |

Przyjęcie: **≥12 pkt i przewaga ≥6 pkt** nad drugim kandydatem.

⚠️ `ZZ` / `2RS` / `2Z` to **typ uszczelnienia, nie część kodu** — bez ich
obcinania `6004ZZ` nie trafia w `6004 2Z Łożysko….ipt`. Ta jedna poprawka
podniosła wynik z 52% na 66%.

### Wynik pomiaru — `B:\!BIBLIOTEKA`, 27.09.2026

23 złożenia, 124 pozycje znormalizowane, czas **15 s**:

| | pozycji | |
|---|---|---|
| **pewne** (automat) | 82 | **66%** |
| **niepewne** (człowiek) | 42 | 34% |

46 unikalnych symboli zmapowanych pewnie, **1 konflikt** (`6004ZZ` wskazuje
różne modele w różnych złożeniach — rozstrzyga człowiek).

Trafienia:

```
61804ZZ                  → 61804.ipt
688ZZ                    → C688ZZ.ipt
6404ZZ                   → 6404 2Z Łożysko nierdzwne 20x72x19.ipt
VTT.60-B-M12             → Three-lobe handwheel VTT.60-B-M12.ipt
170849 DFM-25-30-P-A-GF  → DFM-25-30-P-A-GF Siłownik z prowadzeniem.iam
1059632 SICK GL6G-P4211  → GL6G-P4211 Sick 1059632.iam
```

### Czego automat nie ruszy — i to jest robota dla człowieka

Te 34% to pozycje, w których nazwa w tabelce nie ma **nic wspólnego**
z nazwą modelu. Żadna heurystyka tego nie złapie:

```
SP-1,2/10,6/30 Sprężyna 1,2x10,6x30   →  sprężyna klawiszy wewn.ipt
Silnik 86BYG-118 8,5Nm                →  silnik Sanyo Denki 8,5Nm.ipt
Pasek T5/260 szer. 16mm               →  Pasek obrotnicy t5-260.ipt
```

To **42 pozycje, nie 723** — skala pracy na kilkanaście minut. Narzędzie dla
współpracownika (lista kartotek bez modelu + szukajka po `B:` + podgląd)
ma sens dopiero po pomiarze na całej `B:`; przy takim rzędzie wielkości może
wystarczyć ręczne uzupełnienie listy.

Kolumna `kto` w tabeli `modele_3d` (sekcja 4) jest właśnie na to: odróżnia
wpis z automatu od decyzji człowieka.

### Otwarte

* **Pomiar na całej `B:`** — zmierzono tylko `!BIBLIOTEKA` (23 złożenia).
  Na całym dysku będzie tego kilkaset i statystyka może wyglądać inaczej,
  zwłaszcza w starszych projektach. **To trzeba zrobić przed budowaniem
  narzędzia dla współpracownika.**
* **Czytanie tabelki wprost z IDW** — pomiar bierze nazwy z OUT (który już
  niesie edycje z tabelki). Sięgnięcie do IDW dałoby dodatkowo *kolejność
  pozycji* jako klucz dopasowania i mogłoby podnieść te 66%.
* Wpis z automatu ma trafiać jako propozycja do potwierdzenia czy od razu
  jako mapowanie — do rozstrzygnięcia przy implementacji.

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

## 6a. Etap 1 — zrobione (27.09.2026)

**Kod:** `indeks_modeli_3d.py` (skaner) + tabela `modele_3d` i operacje
`map-model3d`, `-many`, `-wszystkie`, `-zapisz`, `-usun-auto`, `-czysc`
w `rm_serwer_operacje.py` (koniec pliku).

```
python indeks_modeli_3d.py                    # suchy przebieg (domyślnie)
python indeks_modeli_3d.py --zapisz           # zapis, tylko zmienione IDW
python indeks_modeli_3d.py --zapisz --pelny   # przebudowa (ręczne zostają)
python indeks_modeli_3d.py --raport r.txt     # pełna lista do pliku
```

**Sprawdzone** na osobnym serwerze testowym (port 5099, puste bazy):
zapis, drugi przebieg pomija niezmienione IDW, wpis `reczny` przeżywa
`--pelny`, `part_number` zapisany.

**Rozstrzygnięte przy implementacji:**

* rysunek bez modelu = wiersz z `sciezka = ''` (nie osobna tabela) —
  jedno zapytanie odróżnia „bez modelu" od „nie skanowano";
* `zrodlo` = `idw` / `reczny`; automat nigdy nie rusza ręcznych (reguła
  w SQL, jak `map-put`);
* `part_number` modelu zapisywany jako **kontrola** — rozjazd z numerem
  rysunku idzie do raportu;
* pomijane katalogi: `OldVersions`, `Nieaktualne`, `Templates`; numery
  z apostrofem (`2020-300.10'`) to wersje wycofane;
* **203 numery leżą na `B:` w dwóch miejscach** (np. `!BIBLIOTEKA\Elewator`
  i `WaterFall EWTR`) — wygrywa nowszy IDW, rozbieżne modele (po nazwie
  pliku) raport pokazuje jako konflikt;
* model **poza `B:`** albo nieistniejący → zapisany jako „bez modelu",
  a w raporcie widać, co IDW wskazywał.

**⚠️ Pułapki znalezione na M-OLD:**

* **Inventor 2013 na M-OLD** nie otwiera IDW zapisanych nowszym Inventorem —
  w `Czujniki RM` 33 z 61 plików (wszystkie z 2024–2026). Pełny skan
  **tylko na stacji firmowej**; skrypt sam ostrzega przy masowych błędach.
* **IDW pamiętają ścieżkę autora** `C:\BibliotekaRM\…`. Na M-OLD taki katalog
  istnieje (to ten sam, który jest udostępniony jako `B:`), więc Apprentice
  rozwiązywał referencje na `C:`. Skaner przepisuje `C:\BibliotekaRM\` →
  `B:\` (stała `TEN_SAM_KATALOG`), tylko gdy plik na `B:` istnieje.
  `C:\Biblioteka` (bez „RM") to INNY katalog — `016-100.05` wskazuje tam
  model, którego na `B:` nie ma, zgodnie z tym, co mówił użytkownik.

**Do zrobienia przed etapem 2:** wdrożyć `rm_serwer_operacje.py` na
W2019S (restart usługi — uzgodnić), potem `indeks_modeli_3d.py --zapisz`
na stacji z Inventorem firmowym i przejrzeć raport (konflikty, PN ≠ numer).

---

## 7. Ustalenia (27.09.2026)

| # | sprawa | decyzja |
|---|---|---|
| 1 | port | **osobny** (np. 5061), nie ruszamy protokołu na 5060 |
| 2 | uwierzytelnienie | **bez** — endpoint tylko do odczytu, w LAN |
| 3 | wyszukiwanie | po **symbolu**, **nazwie kartoteki**, **numerze rysunku** i **nazwie pliku 3D** |
| 4 | znormalia | ~~po symbolu~~ → **z pary OUT + IAM**, patrz sekcja 5a (zmierzone 66%) |
| 5 | zakres dysków | **tylko `B:`**; `V:` poza planem |

Bez odpowiedzi zostaje tylko to, co rozstrzygnie się przy pisaniu kodu:
* gdzie ustawiać kolejne wystąpienia przy wielu modelach (sekcja 5).

(Rysunki bez modelu — pusty wiersz, patrz 6a.)

---

## 8. Pliki rozpoznania

`pomiar_modele_znormalia.py` (w repo) — pomiar z sekcji 5a. Czysty
odczyt, `--root` wskazuje katalog, `--json` zapisuje pary. Powtarzalny:

```
python pomiar_modele_znormalia.py --root "B:\!BIBLIOTEKA"
python pomiar_modele_znormalia.py --root "B:\\" --json pary.json
```

Skrypty jednorazowe (`zwiad_ole.py`, `pomiar_b2.py`, `test_katalog.py`)
zostały w scratchpadzie sesji — sekcja 2 zawiera komplet potrzebnych
wywołań, gdyby trzeba było je odtworzyć.
