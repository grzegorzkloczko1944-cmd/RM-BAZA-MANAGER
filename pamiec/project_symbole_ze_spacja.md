---
name: project_symbole_ze_spacja
description: Symbole kartotek w Subiekcie ZAWIERAJĄ spacje — nigdy nie ciąć kodu na pierwszej spacji
metadata: 
  node_type: memory
  type: project
  originSessionId: 5f190e79-13f0-43ff-a820-54ac4e6eb565
  modified: 2026-09-10T22:59:18.628Z
---

Symbol kartoteki w Subiekcie **może zawierać spacje**. Realne przykłady z bazy: `6212 2RS`, `3310 2RS`, `UCFL204 UCFL 204`, `DIN 933 M8x30`, `626 ZZ`.

**Why:** kod, który robi `kod.split()[0]`, zamienia `6212 2RS` w `6212` i kartoteka nie zostaje znaleziona — a użytkownik widzi „nie ma takiej kartoteki", choć jest. Wpadłem w to 2026-09-11 przy oknie wydania, kopiując wzorzec ze starego skanera. Tam było poprawne, bo tamten szuka po **numerze rysunku** (`2627-100.16Z`), a numery rysunku spacji nie mają. Symbole — mają.

**How to apply:** przy szukaniu kartoteki po tym, co wpisano/zeskanowano, pytaj **najpierw o cały tekst**, a dopiero gdy nic nie ma — o pierwszy człon (na wypadek pola uzupełnionego nazwą, np. „UCFL201 Zespół łożyskowy"). `query_stock()` przyjmuje listę, więc oba warianty idą w jednym zapytaniu:

```python
kandydaci = [kod] + ([kod.split()[0]] if " " in kod else [])
dane = subiekt_stany.query_stock(kandydaci)
for k in kandydaci:
    if (dane.get(k) or {}).get("Istnieje"):
        ...
```

Przy okazji: **położenie magazynowe** (`Polozenie` na kartotece) ma format `R6/P5` = regał/półka. Wypełnione głównie na pozycjach magazynowych (łożyska, elementy katalogowe); detale projektowe zwykle go nie mają.

Powiązane: [[project_okno_wydania_rw]]
