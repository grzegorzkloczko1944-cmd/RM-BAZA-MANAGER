---
name: project_kalkulator_zz_poza_pw
description: "Kalkulator RMPAK wycenia złożenia Z/ZZ, których PW nigdy nie przyjmie — luka + otwarte pytanie o koszt montażu (odłożone 29.09.2026)"
metadata:
  node_type: memory
  type: project
  originSessionId: 2ce09832-b3af-42b5-8d1b-2f96962306d6
  modified: 2026-09-29T21:50:10.189Z
---

Kalkulator RMPAK bierze pozycje tylko po dostawcy (`_load_rmpak_items`, `WHERE supplier_id IN`), a lista do PW (`subiekt_produkcja.lista_do_pw`) dodatkowo odrzuca Z/ZZ (`na_pw`). Złożenie z dostawcą RMPAK da się więc wycenić (i wlicza się do „Sumy całkowitej"), ale nigdy nie trafi na PW — bez żadnego ostrzeżenia. Przypadek: 2637 Feniks Z 25L, 027-300.00ZZ Napęd chwytaka, 3 h → 453 zł, „0 poz. na PW, 48 kompletów pominiętych", przycisk „Wystaw PW" wyszarzony.

**Why:** ustalenia §7 (lista = dostawca) i §10 (PW tylko TW) żyją osobno, nikt ich nie spiął w GUI. Głębiej: robocizna montażu złożenia nie ma miejsca w modelu — wartość KT = suma składników.

**How to apply:** user 29.09.2026 powiedział „zostawmy na razie". Nie wdrażać bez zgody. Propozycja czekająca: (1) wyszarzyć Z/ZZ w kalkulatorze z dopiskiem „komplet — nie idzie na PW" + rozbić sumę; (2) decyzja usera, gdzie księgować montaż (np. osobna pozycja TW „Montaż <nr>" na PW, albo tylko informacyjnie). Kontekst: [[project_rmpak_produkcja_pw_rw]].

**PW a lokalna kopia (29/30.09.2026, poprawione):** z lockiem kalkulator zapisuje cenę do lokalnej kopii (`C:\RMPAK_CLIENT\project_<id>.sqlite`), a PW liczy się z pliku NA SERWERZE — ze świeżą ceną podgląd pokazywał „BRAK”. ⛔ NIE przełączać PW na lokalną kopię (próbowane i wycofane tego samego dnia): „Anuluj” może ją skasować, a wtedy PW w Subiekcie ma cenę, której baza nie zna. Rozwiązanie: PW zawsze z serwera + `_rozjazd_z_serwerem` porównuje (symbol, ilość, cena) z kopią i blokuje PW komunikatem „zwolnij lock”.
