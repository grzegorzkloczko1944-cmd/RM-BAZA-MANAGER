---
name: project-rmpak-calc-qty-bug
description: Kalkulator RMPAK dzielil cene/szt przez 1 gdy work_qty/order_qty NULL — fix src_qty w COALESCE
metadata:
  type: project
---

Kalkulator RMPAK (`rmpak_calculator.py`, `_load_rmpak_items`) liczyl "Ilosc szt." do dzielenia ceny jako `COALESCE(work_qty, order_qty, 1)`. Pozycje importowane z BOM maja `work_qty=order_qty=NULL`, a ilosc siedzi w `src_qty` (kolumna "Ilosc BOM" w arkuszu). Fallback spadal do 1 → cena/szt = wartosc calej partii (np. 2630-500.20: 246 zamiast 246/4=61.50). Dotyczylo prawie wszystkich pozycji RMPAK w projekcie, nie jednej.

Fix (commit 2659d63): `COALESCE(work_qty, order_qty, src_qty, 1)` w [rmpak_calculator.py:65]. `target_qty` juz wczesniej mial src_qty w fallbacku (linia 70), ale to tylko kolorowanie statusu dostaw, nie dzielenie ceny.

**Uwaga — poprawka kodu NIE przelicza wstecz zapisanych cen.** `price_pln` w bazie zostaje stary dopoki ktos nie wejdzie do kalkulatora i nie kliknie "Zapisz cene/szt" (albo skrypt zbiorczy). Przeliczanie zbiorcze bazy projektu tylko gdy projekt NIE jest zalockowany (patrz [[reference-db-paths]] + lock w Y:/RM_BAZA/locks/project_N.lock).

**Why:** blad byl systemowy i niewidoczny bo "wygladal ok" na pozycjach gdzie work_qty=src_qty.
**How to apply:** przy bugach ceny/szt sprawdzaj najpierw ktora kolumna qty jest NULL na zywej bazie; "Ilosc szt.: 1" w kalkulatorze = objaw pominietego src_qty.
