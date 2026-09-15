---
name: project_subiekt_projekt_z_csv
description: "Projekt w Subiekcie z pliku CSV (małe złożenia spoza RM_BAZA) — NIEDOKOŃCZONE, zapis nieprzetestowany (08.09.2026)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 47fa97da-3439-4292-864b-075339162d55
  modified: 2026-09-08T17:48:30.540Z
---

⚠️ **STAN NA 08.09.2026: działa suchy przebieg, ZAPIS NIEPRZETESTOWANY.**
User: „dokończymy tę funkcję w domu".

Małe złożenia (pojedynczy zespół z Inventora) nie mają wpisu w RM_BAZA ani
pliku `*_OUT.xlsx`, więc okno „Projekt / Aktualizacja w Subiekcie" ich nie
widziało. Produkowanie OUT tylko dla nich się nie opłaca — BOM w CSV jest już
pełnym opisem składu.

Kafel „📄 Projekt z pliku CSV" w panelu Subiekta + pozycja w menu górnym.
NIE wymaga otwartego projektu. Wskazujesz plik, wpisujesz nazwę projektu
(podpowiadana z nazwy pliku, idzie na ZK), reszta okna działa bez zmian.

**Klucz do rozwiązania:** `read_items_csv` zwraca dokładnie ten sam kształt co
`read_project_items`, a `tree_z_csv` — co `read_tree`, więc klasyfikacja,
`build_plan` i ZK nie wiedzą, skąd przyszły dane. `build_plan` i okno mają
opcjonalny `csv_path`; ścieżka bazodanowa NIETKNIĘTA.

**Samo złożenie nie jest wierszem BOM-u** — tożsamość niesie nazwa pliku
(`2622-200.81ZZ Zestaw Wagi.csv` → symbol + nazwa), więc dopisuję je jako
pozycję. Bez tego powstają same składniki bez kompletu.

Plik testowy: `V:\2622 Ceramizator_W\Rysunki Karuzela 200 2622\2622-200.81ZZ Zestaw Wagi.csv`
(8 składników, tuleje po 2 szt., cp1250, separator `;`).

**DO DOKOŃCZENIA:**
- przetestować zapis na żywym Subiekcie;
- sprawdzić cofanie — log idzie pod nazwą projektu, bo `project_id` nie
  istnieje, a `SubiektProjektCofnijWindow` szuka po id;
- zdecydować, czy płaski skład wystarcza (dziś podzespół = osobny plik CSV);
- notatki projektu zapisują się pod `project_id = None` — wszystkie takie
  projekty trafiają do jednego worka.

Powiązane: [[project_subiekt_edytor_kartotek]], [[project_subiekt_stan_05_09_2026]].
Dokumentacja: `SUBIEKT_ZMIANY_2026-09-08.md` sekcja 3.
