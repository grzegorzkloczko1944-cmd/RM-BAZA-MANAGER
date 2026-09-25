---
name: project_zlozenie_tylko_znormalizowane
description: "Złożenie Z, którego cały skład to znormalia, idzie do Subiekta jako TOWAR (STANDARD) — nie jako pusty komplet; arkusz DRZEWKO TEKST nie zawiera znormaliów"
metadata:
  type: project
---

# Złożenie ze składem tylko znormalizowanym = TOWAR, nie pusty komplet

Naprawione 25.09.2026 (`101c3c8`).

Zgłoszenie: `2637-100.01Z` „Rama Feniks Z25L" leciała do decyzji
**„złożenie bez ani jednego składnika"** i blokowała zapis —
„Popraw drzewko (1)".

## ⚠️ Przyczyna: arkusz „DRZEWKO TEKST" NIE ZAWIERA znormaliów

Na 2637: **329 wierszy, zero bez numeru rysunku**. Złożenie, którego całym
składem jest nakrętka `DIN 934 M16`, wygląda tam na **liść bez dzieci** —
i stąd fałszywe „puste złożenie".

Reguła importera OUT, której RM_BAZA nie znała: **element wykonawczy**
(rama cięta i spawana) dostaje **ten sam numer i nazwę co złożenie**, żeby
nie dublował się ani w częściach, ani w znormaliach.

## Rozwiązanie

`import_bom.zlozenia_tylko_znormalizowane()` czyta sekcję
**„PELNA TABELA (BOM)"** (nie DRZEWKO TEKST) i zwraca złożenia, którym
po odrzuceniu **samych siebie** zostają same znormalia. `build_plan` daje
im typ **STANDARD** — jak zwykłemu towarowi.

Dzięki temu widzą towar, a nie pusty komplet, wszystkie cztery ścieżki:
trzy liczniki okna (`blad`, `puste_blad`, krok mostu) **i sam most**.

## Co zostaje bez zmian

Złożenie **całkiem puste** nadal idzie do decyzji — to realny brak danych.
Patrz [[project_subiekt_puste_zlozenia_decyzje]].

Sprawdzone headless na 2637: 47 kompletów bez zmian, rama STANDARD, lista
„Popraw drzewko" pusta.

Powiązane: [[project_subiekt_puste_zlozenia_decyzje]], [[project_normalia_po_klasie]].
