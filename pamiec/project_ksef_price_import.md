---
name: project_ksef_price_import
description: Import cen/pozycji z faktur KSeF do ZD — trzy typy faktur, wnioski z pomiarów na danych produkcyjnych (04.09.2026)
metadata:
  type: project
---

Dopasowywanie pozycji faktur KSeF do pozycji ZD w Subiekcie. **Wstrzymane 04.09.2026** — wracamy, gdy będzie więcej faktur i dostęp do KSeF (dziś faktury przychodzą od klienta ręcznie, XML-e i zdjęcia).

**Struktura FA(3):** `P_7` skleja kod i nazwę w jedno pole, `P_1` data, `P_2` numer, `P_8A/8B` jednostka/ilość, `P_9A` cena jedn., `P_11` wartość.

**Trzy typy faktur — zmierzone na realnych danych:**

| Typ | Przykład | `P_7` zawiera | Parsowalność |
|---|---|---|---|
| A | AMB PRODUKT | kod rysunku + nazwa | 5/5 — regex po numerze rysunku (prefiks) działa |
| B | alu-frost | opis całego kompletu | 0/4 — brak danych, nie da się; ręcznie |
| C | QUAY (RVQ/04895/26) | czysty symbol katalogowy (`608 2Z`, `UCFL 204`, `5M 305 (15)`) | trywialna, ale **brak kartotek w Subiekcie** |

**Kluczowy wniosek dla typu C:** to nie jest problem parsera. Zmierzone dopasowanie faktury QUAY: **1/13 do kartoteki Subiekta** (tylko `UCFL 204`), **1/11 do BOM-ów RM_BAZA** (`UCFB205`, bez spacji). 2995 kartotek w Subiekcie to głównie własne rysunki — normaliów handlowych tam nie ma, więc nie ma czego dopasować, bo takiego ZD nigdy nie było.

**Why:** Typ C jest najtańszy do naprawienia i daje największy zysk — normalia (łożyska, paski) kupowane są w kółko, więc raz założona kartoteka dopasuje się 1:1 na każdej kolejnej fakturze i wnosi towar na stan, co jest warunkiem punktu 2 planu (wydania monterom przez RW).

**Domiar typu A — 06.09.2026** (`Y:\RM_BAZA\faktury_ksef`, wciąż te same 2 XML-e,
nic nowego nie przyszło). Faktura AMB PRODUKT FV 45/07/2026, 5 pozycji, regex po
prefiksie parsuje 5/5. Ale sprawdzenie, dokąd te kody prowadzą, dało **odwrotność
problemu QUAY**:

| | |
|---|---|
| kartoteki w Subiekcie | **0 z 5** (`013-100.30a/B/c`, `ROTO-100.01`, `DUO-100.06`) |
| BOM-y RM_BAZA | **5 z 5** (np. `013-100.30B` w projektach 9, 10, 21, 25, 29, 65) |

Przy QUAY kodów nie było NIGDZIE. Tu są w BOM-ach wszystkich projektów, ale żaden
nie ma kartoteki — mimo że to własne rysunki, nie normalia. Te detale nigdy nie
przechodziły przez Subiekta, więc nie ma ZD ani kartoteki, do której faktura
mogłaby się dopiąć.

**Wniosek: sam parser typu A nie da dziś nic użytecznego** — sparsuje 5 linii
i nie będzie miał ich z czym zestawić (ani ceny do czego przypisać, ani towaru
czym przyjąć). Wartość pojawia się dopiero, gdy detale zaczną iść przez Subiekta:
kartoteka → ZD → faktura dopina się do zamówienia. To wzmacnia kolejność prac
niżej: **najpierw zakładanie kartotek, potem parser** — dla własnych rysunków
tak samo jak dla normaliów.

**How to apply:** Kolejność prac po wznowieniu: (1) import wsadowy kartotek normaliów — rozszerzyć `subiekt_asortyment.py` o wklejanie listy z faktury i hurtowe zakładanie, symbol = symbol katalogowy dostawcy; (2) parser regexowy dla typu A; (3) typ B zostaje ręczny. **Nie budować agenta AI do parsowania faktur** — problemem są brakujące dane i kartoteki, nie rozpoznawanie tekstu. Sprawdzone wcześniej: 60 FZ / 305 pozycji ma 0 dopasowanych asortymentów i 0 powiązań z zamówieniami; FZ pełni tu rolę dokumentu przyjęcia (PZ martwe od 11.2023). Rozwiązanie stosowane przez inne firmy: wymusić na dostawcy symbol i numer zamówienia na fakturze — regex tylko jako fallback. Patrz [[project_subiekt_nexo_sfera]], [[project_subiekt_zk_komplety]].
