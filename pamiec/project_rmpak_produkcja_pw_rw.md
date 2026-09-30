---
name: project_rmpak_produkcja_pw_rw
description: "Produkcja wlasna RMPAK - PW/RW zamiast ZK, proces dziala end-to-end"
metadata: 
  node_type: memory
  type: project
  originSessionId: bd77b2db-aa7d-4871-a44f-b0388f221230
  modified: 2026-09-09T23:17:58.156Z
---

Tor produkcji własnej RMPAK: kalkulacja → PW → RW, osobny od toru zakupowego (ZK). Ustalenia w repo: `RMPAK_PRODUKCJA_USTALENIA.md`.

**Zasady, które nie podlegają renegocjacji bez powodu:**

* Ilość na PW z **projektu / BOM** (`COALESCE(work_qty, src_qty)`), NIE z `order_qty`. RMPAK nie zamawia u siebie.
* Produkcja własna = dostawca RMPAK / „RMPAK + materiał", **albo złożenie Z/ZZ bez dostawcy**. Wyjątek: złożenie z realnym dostawcą (MAJA) to zakup → zostaje na ZK.
* Filtr działa **tylko przy dodawaniu pozycji na dokument ZK** — nigdy przy budowie planu ani składów KT, inaczej drzewko się rozpada.
* Na PW idą **wyłącznie TW**. Komplety KT nie mają własnego stanu.
* **PW z ceną, RW bez ceny.** Ale RW NIE jest bezwartościowe: cena netto to parametr handlowy (na dokumencie magazynowym = 0), a wartość niesie `KosztMagazynowy`, który Subiekt liczy sam z ceny przyjęcia. Patrz [[project_koszt_magazynowy_vs_cena]].
* **Numery PW/RW czytane z Subiekta**, nie trzymane lokalnie — rozpoznanie po markerze „RM_BAZA — PROJEKT <nr>" w Uwagach. Ten sam wzorzec co `Ilość (zam.)`. Powód: `project_con` bez locka jest READ-ONLY, więc zapis lokalny cicho przepadał.
* `DAGAR + RMPAK` (kooperacja) celowo NIEROZSTRZYGNIĘTE — idzie na ZK.

**Stan 2026-09-10 (wypchnięte, `6dedb94`): wszystkie 5 kroków GOTOWE.** Proces przeszedł end-to-end na projekcie 3500 (id 71): ZK dostał 180 z 211 pozycji, `PW 2/MASTER/2026` (6 detali, 4848 PLN), `RW 1/MASTER/2026` z markerem `| PW: PW 2/MASTER/2026`, wartość 4848 zł jako koszt magazynowy.

Kod: `subiekt_produkcja.py` (cała reguła + PW/RW), sekcja w `rmpak_calculator.py`, filtr w `Projekt.cs`, cena w `Pw.cs`, koszt w `Dokumenty.cs`. Okno złożeń: `subiekt_zlozenia_gui.py`.

**Zmiana dostawcy złożeń** (commit `6178a42`): menu prawym w Projekt/Aktualizacja, kolumna „Dostawca” w tabeli, tryb mostu `zk-poz-usun` (zdejmuje z ZK pozycje przeniesione na produkcję własną, ale NIE rusza tych, które poszły dalej na ZD). Zapis MUSI iść przez `db_manager.project_con`, nie osobnym połączeniem — patrz [[project_zapis_do_bazy_projektu]]. Sfera nie wystawia `Usun` dla pozycji ZK; most NIGDY nie zeruje ilości jako zamiennik (zero wraca do BOM-u przez `_zapisz_ilosci_z_subiekta`).

**Nierozstrzygnięte:** magazyn dla PW/RW (na sztywno MASTER), status `DAGAR + RMPAK`, migracja `RMPAK + materiał` → jeden dostawca.

**How to apply:** przy zmianach trzymać wzorzec suchy przebieg → potwierdzenie → zapis → read-back po wierszach. Rebuild mostu: [[feedback_most_rebuild_release]]. Ceny na PW: [[project_cena_na_pozycji_pw]].

**RW wróciło do kalkulatora (29.09.2026, na prośbę usera):** przycisk „📤 Wystaw RW z <PW>” pod „Wystaw PW”. Kolejka **1:1 PW → RW**, najstarsze PW bez RW pierwsze (`subiekt_produkcja.kolejka_rw` + `pw_w_uwagach`). Rozpoznanie „PW ma już RW” po numerze PW w Uwagach RW (`PW: PW 6/MASTER/2026`, stare `| PW: …` też). ⛔ NIE wracać do `pw_do_rw` (suma wszystkich PW) — przy PW różnicowym wydałoby drugi raz. RW z okna magazynu nie niesie numeru PW, więc kolejki nie zamyka — podwójne wydanie zatrzyma dopiero suchy przebieg (za mały stan).

**Panel „Dokumenty produkcji” (29/30.09.2026):** tabelka par PW | RW (✔ / ⏳ czeka na RW, 3 ostatnie, RW bez PW osobno) zamiast numerów po przecinku; licznik „Do nowego PW: N / Już przyjęte: M” (z `do_pw`, nie wszystkie pozycje RMPAK — stary „2 poz. na PW” przy przyjętych wyglądał jak zaproszenie do ponownego PW); „Wystaw PW” szary, gdy nic nowego. Przyciski `side="bottom"` i `before=` pierwszego widżetu — panel ma stałą wysokość, a Tk daje miejsce w kolejności pakowania. Podgląd PW/RW otwiera się raz (`_jeden_podglad`): kliknięcia z kolejki przy mulącej RM_BAZA otwierały kilka okien.

**Test okna Tk bez RM_BAZA:** wątek w tle woła `win.after` — działa tylko pod `mainloop()`, nie w pętli `update()` (tam wyjątek połykany, panel wisi na „Odczyt z Subiekta…”). Zrzut: `SetProcessDpiAwareness(1)` + okno `zoomed`, patrz [[project_zrzut_ekranu_dpi]].

**Szybkość kalkulatora (30.09.2026):** otwarcie pytało Subiekta 3× o dokumenty (2× synchronicznie, każde 3–8 s w domu, dłużej w firmie), a KAŻDY filtr (`_load_items`) jeszcze raz dla kolorów. Teraz JEDEN odczyt w tle (`_odswiez_numery_dokumentow` → `_po_odczycie_subiekta`), z niego pary PW/RW + kolory + licznik (`przyjete_z_dokumentow`, cache `_przyjete`). Z Subiekta czytają tylko: otwarcie, „Odśwież”, wystawienie PW/RW i podgląd PW (`_pozycje_pw(swiezo=True)` — dokument zawsze z aktualnego stanu). Filtry i zapis ceny — z cache. Pomiar 2637 dom: okno 3,1 s → 0,7 s. ⛔ Nie dokładać synchronicznego odczytu Subiekta do `_load_items`.
