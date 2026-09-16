---
name: project_sklejanie_duplikatow_bom
description: Sklejanie duplikatów BOM tylko po identycznym subiekt_symbol; heurystyka po nazwie/numerze ODRZUCONA
metadata:
  type: project
---

# Sklejanie duplikatów w BOM — tylko identyczny `subiekt_symbol`

`subiekt_sklej_duplikaty.py` łączy wiersze BOM-u wskazujące jedną kartotekę:
zostaje jeden, ilości się sumują, reszta znika. Wołane z przycisku
„🔗 Sklej duplikaty" w „Dopasowaniu kartotek".

Potrzebne, bo most ustawia ilość na ZK **wprost** — dwa wiersze na jedną
kartotekę nadpisują się i na dokumencie ląduje mniejsza liczba.

## Reguła: JEDNA, celowo

Grupujemy **wyłącznie** po identycznym `subiekt_symbol`. Nic nie zgadujemy
z nazwy, numeru rysunku ani mapowania.

## ⚠️ PRÓBOWANE I ODRZUCONE — nie powtarzać

**Heurystyka „docelowa kartoteka" (mapowanie → symbol → numer rysunku),
wzorowana na `subiekt_projekt.scal_po_kartotece`.** Napisana 15.09.2026,
odrzucona przed wdrożeniem po teście na projekcie 2627.

Powód — w Subiekcie istnieją osobne kartoteki o mylnie podobnych kluczach:

| klucz      | symbol w Subiekcie | `id_subiekt` |
|------------|--------------------|--------------|
| `UCFL 201` | `UCFL 201`         | 100198       |
| `UCFL201`  | `UCFL201`          | 100532       |

To **dwa różne towary**. Heurystyka sklejała je w jeden i zabierała sztuki
z drugiego. Kod, który KASUJE wiersze BOM-u, nie ma prawa zgadywać —
por. [[project_symbole_ze_spacja]].

Drugi błąd tej wersji: zdjęcie warunku `subiekt_symbol <> ''` wciągało do
grupowania wiersze bez symbolu (`GS14 10-12  ------`), które lądowały
razem w grupie z pustym kluczem i zostałyby skasowane.

**Grupowanie po `id_subiekt`** też sprawdzone i odrzucone: 208 z 254 mapowań
(`sposob='zalozona'`) ma to pole puste, więc reguła nie wyłapała **żadnej**
pary na 2627.

## Pułapki ilości

* Suma to `COALESCE(work_qty, src_qty)`. Wiersz z importu ma `work_qty`
  PUSTE i liczbę trzyma w `src_qty` — sumowanie samego `work_qty` dawało
  zero. Suma idzie do `work_qty`, `src_qty` zostaje jako ślad importu.
* `order_qty` **nie jest sumowane, tylko czyszczone**. To odbicie ilości
  z dokumentu, a oba wiersze pokazywały TĘ SAMĄ pozycję ZK — sumowanie
  dawało 4+4=8 zamiast 24. Por. [[project_jedno_zrodlo_prawdy_ilosci]].

## Test

`znajdz_duplikaty` na projekcie 2627 (`project_52.sqlite`) daje 3 grupy:
`12x14X10SBT` → 2 szt., `GN-614-5NI` → 4 szt., `WS-10L240mm` → 24 szt.
Wiersze 219 i 225 (UCFL201) muszą zostać **nietknięte**. Funkcja jest
idempotentna — drugi przebieg zwraca 0 grup.

⚠️ Testuj na **kopii** bazy projektu, nigdy na żywej.

## Numeracja plików baz

Baza projektu nazywa się po wewnętrznym `project_id` z `master.sqlite`,
NIE po numerze projektu: projekt **2627** to `project_52.sqlite`.
Por. [[reference_db_paths]].
