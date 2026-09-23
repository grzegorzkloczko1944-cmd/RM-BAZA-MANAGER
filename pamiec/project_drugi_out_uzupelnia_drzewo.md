---
name: project_drugi_out_uzupelnia_drzewo
description: "Drugi plik OUT uzupelnia drzewo: mechanizm JUZ ISTNIEJE (find_out_files skleja wszystkie OUT-y z folderu projektu), ilosci mnoza sie same; cena: obce OUT-y w folderze zasmiecaja okno Decyzje"
metadata:
  node_type: memory
  type: project
---

**Ustalenia 23.09.2026 (rozmowa + czytanie kodu).** Pierwotna wersja tej
notatki zakladala, ze trzeba dopisac opcje „wskaz plik OUT" w oknie Decyzji.
**Po przeczytaniu kodu: w duzej czesci NIEPOTRZEBNE — mechanizm juz dziala.**

## Problem

Projekt ma zaciagniety jeden `*_OUT.xlsx`. Jeden z podzespolow to zlozenie
z biblioteki — w pierwszym OUT jest PUSTY (lisc bez skladu), bo rozwiniecie
siedzi w drugim pliku OUT. Cel: drugim OUT-em uzupelnic drzewo.

## ✅ Co juz dziala (NIE pisac od nowa)

`build_plan` czyta **wszystkie** pliki `*_OUT.xlsx` z folderu projektu
i skleja je w JEDNO drzewko:

- `find_out_files()` — `glob("*_OUT.xlsx")`, **nierekurencyjnie**
  ([import_bom.py:491](../import_bom.py#L491))
- petla sklejajaca w `read_tree` ([subiekt_projekt.py:508-536](../subiekt_projekt.py#L508-L536))
- sklejanie po **numerze rysunku rodzica** (`sciezka[-2]`), nie po pliku
- przy >1 pliku leci `print`: `📄 Drzewko „…" z N plikow: nazwa (ile)`

To zachowanie **zamierzone i udokumentowane**: `V:\3500 Dupal` trzyma tez
`2627-650.11ZZ Transporterek_OUT.xlsx`, bo Transporterek wchodzi w sklad
Dupala.

**Warunek sklejenia:** korzen drugiego OUT musi miec TEN SAM `Nr rysunku`
co pusty wezel w pierwszym drzewku. Nie zgadza sie → drugie drzewko zawisa
obok jako osobny korzen, pusty wezel zostaje pusty i widac go w „⛔ Decyzje".
Cicho nie przejdzie.

## ✅ Ilosci mnoza sie SAME — nie mnozyc recznie

`ilosci_z_drzewa()` ([subiekt_projekt.py:836-878](../subiekt_projekt.py#L836-L878))
schodzi rekurencyjnie: `ile = ilosc_lokalna * ile_rodzica`. Korzen ×2 →
podzespol ×2 → jego czesci ×2 razy ich ilosc w podzespole. Pozycja w kilku
galeziach SUMUJE sie.

→ **Odpowiedz na stare pytanie „ktora ilosc mnozyc": `ilosc_lokalna`,
i mnozenie jest juz zrobione.** Obawa „ilosci sie mnoza, trzeba ×krotnosc"
byla niepotrzebna.

## Arkusz RM_BAZA vs drzewko — DWIE WARSTWY

| warstwa | zrodlo | odpowiada na |
|---|---|---|
| BOM (arkusz RM_BAZA) | `read_project_items(project_id)` — baza projektu | ktore pozycje ISTNIEJA |
| drzewko | pliki `*_OUT.xlsx` z folderu projektu | co w czym siedzi i po ile |

Spotykaja sie w [subiekt_projekt.py:1118-1122](../subiekt_projekt.py#L1118-L1122):
sklad kompletu bierze sie z `kids` (drzewko), a **BOM dziala jako FILTR** —
„do skladu bierzemy tylko to, co jest w BOM-ie". Dorzucenie pozycji z drugiego
OUT do arkusza + pliku do folderu = filtr przepuszcza, drzewko podaje strukture.

## Dlaczego KOPIA pliku do folderu projektu, a nie link do biblioteki

Nie chodzi o litere `V:` — `get_assembly_tree_root()` bierze sciezke
z konfiguracji (pole „Serwer projekty", `SERVER_DIR`); `V:/` to tylko fallback.
Chodzi o **folder projektu**:

1. **Kod sam szuka pliku** — `build_plan` dostaje nazwe projektu, nie sciezke;
   z prefiksu (czlon do pierwszej spacji) znajduje folder. Nie ma dialogu
   „wskaz plik".
2. **Wspolne zrodlo prawdy** — plik na lokalnym `C:` widzi tylko jedna osoba;
   u kolegi komplet wyszedlby bez skladu i wygladalo to na blad programu.
3. ⭐ **ZAMROZENIE STANU (argument usera)** — biblioteczny OUT zyje wlasnym
   zyciem; ktos poprawia zespol pod inny projekt i gdyby RM_BAZA czytalo
   oryginal z `B:\`, projekt zmienialby sie SAM. Kopia to odcina.
   Ten sam wzorzec co w reszcie systemu: sklad kompletu z drzewka projektu,
   nie z biblioteki.

**Cena odciecia (swiadoma):** dziala w jedna strone — poprawka w bibliotece
nie dotrze i nikt nie powiadomi. Kopia jest tez odcieta od biblioteki, ale
NIE od kolegow (ktos moze nadpisac). Nazwa pliku pokazujaca pochodzenie
i date oszczedza pozniejszego sledztwa.

→ **Kopia w folderze JEST zapamietanym wyborem** — trwalym i widocznym dla
wszystkich, w przeciwienstwie do `_bib_decyzje` zyjacego w pamieci okna.
To odpowiada na stare pytanie „czy zapamietywac wybor pliku".

## ✅ POTWIERDZONE NA ZYWYCH DANYCH — projekt 2637 (23.09.2026)

Pierwszy realny przypadek, zweryfikowany przed zapisem.

Projekt `V:\2637 Feniks Z 25L\2637-100.00ZZ 2637 Feniks Z 25L_OUT.xlsx`
mial DWA puste wezly `MODUL (ZZ)` na poziomie 2, ilosc 1:
`EWTR-820.00ZZ Elewator L` i `EWTR-820.45ZZ Elewator P`.

Rozwiniecia w bibliotece:
`B:\!BIBLIOTEKA\Elewator\Rysunki Elewator 820 EWTR\EWTR-820.{00,45}ZZ …_OUT.xlsx`
(obok lezaly te same zlozenia jako `.csv` — user wygenerowal z nich OUT-y,
bo CSV idzie inna sciezka: `tree_z_csv`, dla malych projektow spoza RM_BAZA).

Pomiar:

| sprawdzenie | wynik |
|---|---|
| korzen OUT-u bibliotecznego vs pusty wezel | ✅ zgodny co do znaku (oba) |
| wspolni rodzice projekt↔L, projekt↔P, L↔P | ✅ ZERO — nic sie nie nadpisze |
| glebokosc drzewek EWTR | plaskie: max poziom 2, zero wnukow |
| skladnikow wnoszonych | 42 na elewator, 0 juz obecnych w projekcie |
| czesci wspolnych L∩P | 38 (np. `011-100.67`, `EWTR-820.02XX`) |

38 czesci wspolnych to NIE blad — lewy i prawy elewator dziela komponenty.
W BOM-ie beda raz, `ilosci_z_drzewa` zsumuje je z obu galezi → ×2.
To najlatwiejsze miejsce na pomylke przy odbiorze, wiec ilosci wspolnych
czesci sprawdzic w planie PRZED zapisem.

Oba pliki skopiowane do folderu projektu 23.09.2026.
Kolejnosc: kopia plikow → zalozenie projektu w RM_BAZA (import widzi juz
trzy OUT-y, wiec pozycje EWTR trafiaja do arkusza od razu) → Projekt/
Aktualizuj. Odwrotna kolejnosc = drzewko zna pozycje, ale filtr BOM-u je
odetnie, bo nie ma ich w arkuszu.

## ⚠️ PULAPKA: ten sam numer jako RODZIC w dwoch OUT-ach → cicha hybryda

Sklejanie zaklada, ze numer rysunku identyfikuje sklad JEDNOZNACZNIE
w calym folderze. Gdy to nieprawda, dzieje sie to po cichu.

**Dwa rozne przypadki — nie mylic:**

| kolizja | zachowanie | ocena |
|---|---|---|
| ten sam numer jako **DZIECKO** w roznych rodzicach | `kids` kluczowane rodzicem → osobne wpisy, `ilosci_z_drzewa` SUMUJE | ✅ poprawne, jak „Ilosc calkowita" w Inventorze |
| ten sam numer jako **RODZIC** w dwoch plikach | listy skladnikow sklejane; przy tym samym dziecku **pierwszy wpis wygrywa**, drugi pomijany BEZ ostrzezenia | ⚠️ cicha hybryda |

Winowajca — [subiekt_projekt.py:532](../subiekt_projekt.py#L532):

```python
if not any(c[0].upper() == child.upper() for c in kids[parent]):
    kids[parent].append((child, qty))
```

Skutki przy kolizji rodzica:
- **rozne ilosci** tego samego dziecka (projekt 2, biblioteka 4) → zostaje
  ta z pliku przeczytanego WCZESNIEJ;
- **rozne sklady** tego samego zlozenia (biblioteka nowsza) → wychodzi
  HYBRYDA: suma obu list, nie sklad zadnej z wersji.

⚠️ **O zwyciezcy decyduje NAZWA PLIKU:** `find_out_files` robi
`sorted(glob(...))` — kolejnosc alfabetyczna. `2637-100.00ZZ…` < `EWTR-820…`,
wiec dzis projekt ma pierwszenstwo. Zmiana nazwy pliku zmienilaby wynik
i nikt by tego nie zauwazyl.

**Kiedy uderzy:** gdy biblioteka dostanie ZAGNIEZDZONE zlozenia i to samo
podzlozenie pojawi sie w dwoch OUT-ach. Dzis drzewka EWTR sa plaskie
(max poziom 2, zero wnukow), wiec wnosza tylko wlasny korzen — nie dotyczy.

### Jak rozwiazac — najprosciej

**Wariant minimalny (REKOMENDOWANY): wykryc i ostrzec, nie naprawiac.**
Mechanizm zostaje bez zmian; dokladamy tylko sygnal. W petli w `read_tree`
jest juz slownik `zrodla` — wystarczy zapamietac, KTORY plik wniosl danego
rodzica, i gdy drugi plik chce dopisac do rodzica juz obsadzonego z INNEGO
pliku:

- zgodny sklad → cisza (to normalne, np. ten sam zespol w obu OUT-ach);
- rozjazd (inna ilosc / inny zestaw dzieci) → ostrzezenie do `warn`,
  widoczne w oknie PRZED zapisem.

~15 linii, zero zmian zachowania dla danych bez kolizji, nic nie ukrywa.
Zgodne z [[feedback_nic_po_cichu]]: user MUSI zobaczyc rozjazd i zdecydowac.

**Wariant mocniejszy (gdy ostrzezenia zaczna byc czeste):** jawny priorytet
zrodel — plik projektu wygrywa z bibliotecznym niezaleznie od alfabetu,
bo to projekt jest wlascicielem struktury. Wymaga rozroznienia „skad plik"
(dzis `kids` tego nie niesie), wiec wiecej roboty.

**ODRZUCONE:** milczace scalanie „po sumie" (dzisiejszy stan) — daje sklad,
ktorego nie ma w zadnym pliku. Sortowanie po dacie zamiast nazwy — ta sama
cichosc, tylko inny arbitralny zwyciezca.

## ⚠️ OTWARTE: Decyzje pokazuja pozycje z OBCYCH projektow

**Zgloszone 23.09.2026 przez usera, DO SPRAWDZENIA — nie diagnozowane do konca.**

Zrodlo asymetrii:
- `items` ← `read_project_items(project_id)` — **tylko biezacy projekt**, czysto
- `kids` ← **wszystkie** OUT-y z folderu, sklejane po numerach **bez
  sprawdzania, z ktorego projektu pochodza**

To **ta sama przyczyna**, o ktorej mowi komentarz w
[subiekt_projekt.py:503-510](../subiekt_projekt.py#L503-L510) (zgloszone
10.09.2026: „ostrzezenia wyskakuja z obcego projektu") — wtedy zalatwione
tylko `print`-em do konsoli, nie naprawa.

⚠️ **To jest CENA mechanizmu z gory:** kazdy OUT dorzucony do folderu
poszerza drzewko dla WSZYSTKICH projektow czytanych z tego folderu.

**Czego potrzeba do diagnozy** (pytanie rozstrzygajace):
czy numery w ostrzezeniach maja prefiks INNEGO projektu niz biezacy?
- tak → filtr po prefiksie zalatwia sprawe, prosty fix
- nie (numery wlasne) → inna przyczyna (pozycje w BOM-ie, ktorych zaden OUT
  nie zna); filtr by NIE pomogl, a moglby ukryc cos realnego

Szybki podglad: konsola przy Projekt/Aktualizuj — linia
`📄 Drzewko „…" z N plikow` pokazuje, ile plikow wchodzi i ile rodzicow
wniosl kazdy.

## Na start

Sprawdzic na prawdziwych danych: numer rysunku pustego zlozenia vs korzen
drugiego OUT. Plan widac PRZED zapisem, wiec ilosci da sie zweryfikowac
zanim cokolwiek pojdzie do Subiekta ([[feedback_nic_po_cichu]]).

Patrz [[project_subiekt_puste_zlozenia_decyzje]], [[project_subiekt_zk_komplety]],
[[project_srodowisko_domowe_m_old]].
