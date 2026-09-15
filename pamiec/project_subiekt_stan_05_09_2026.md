---
name: project_subiekt_stan_05_09_2026
description: Stan integracji Subiekt↔RM_BAZA na 05.09.2026 — co działa, pułapki Sfery, co otwarte
metadata:
  type: project
---

Punkt kontrolny integracji Subiekt nexo PRO ↔ RM_BAZA. Ostatni commit: patrz git log (05.09.2026 wieczór: f65b4e6 → d88a928 → dostawca z ZD). Szczegóły każdej zmiany są w komunikatach commitów — `git log` od `916a7a3` w górę.

## Co działa na produkcji

**Przepływ:** RM_BAZA zakłada ZK (kartoteki + komplety Z/ZZ) → z braków powstają ZD per dostawca → ZD idzie mailem do dostawcy → FZ przyjmuje towar. Wydania monterom (RW) technicznie gotowe, wdrożenie zależy od adopcji.

**Okna:** Załóż projekt, Zamówienia do dostawców (ZD), Przegląd dokumentów (ZK/ZD/RW/WZ), Stany magazynu, Powiązanie dostawców, Archiwum faktur KSeF, Wyślij ZD. Wszystkie osiem mają kręciołek w pasku stanu.

**Most `NexoRecon.exe`** — tryby: stan, katalog, kontrahenci, zapotrzebowanie, projekt, zd, zd-usun, dostawcy, stan-pozycji, dokumenty, faktury, kartoteka, magazyn, wydruk, wydruk-recon, symbole, termin. Bezstanowy: jedno uruchomienie = jedno zapytanie, ~10-11 s (start Sfery + logowanie).

## „Zamówiono" z wysyłki ZD → arkusz projektu (f65b4e6)

**Model:** wysyłka NIE pisze do plików projektów. Zapisuje fakt do master (`zd_zamowione_pozycje`), a nakłada go arkusz: przy **Przejmij Lock** (świeża kopia), przy **Zwolnij Lock** (przed wgraniem kopii — bez tego gubiło wpisy, które przyszły w trakcie trzymania locka) i od razu, gdy projekt przejęty u siebie. Wpisy kasowane dopiero po zweryfikowanym syncu; wygasają po 180 dni. Funkcje: `odloz_zamowienia / naloz_zamowienia / usun_zamowienia` w subiekt_wyslij_zd.py, hook `_naloz_zamowienia_zd` w arkuszu.

**Dlaczego nie zapis wprost / agent / atomowy lock:** edycja = kopia lokalna, sync kopiuje CAŁY plik; `release_lock` zwalnia lock PRZED wgraniem kopii (szpara); czytelnik ma `immutable=1` (nie widzi zmian, ale nie może nadpisać — brak kopii). Odrzucone po kolei: zapis tylko do otwartego projektu (inne nigdy się nie aktualizują), przejmowanie cudzych locków (wyrywa projekt), zapis wprost z O_EXCL (ginie pod cudzą kopią), agent w tle (za skomplikowane — użytkownik).

**Adres wiersza BOM per projekt:** `bom.update()` po symbolu nadpisywał adres (3000 Testowy = kopia z rysunkami 2632 Feniks). `scal_bom` → `refs {nr projektu: (project_id, item_id)}`, `refy_bom` wybiera z kolumny Projekt. Projekt pozycji JUŻ zamówionej idzie z **Uwag ZK przez most** (`ProjektZk` w Zapotrzebowanie.cs), nie z BOM-u.

**Dostawca też wraca do arkusza:** wpis w master niesie `supplier_id` (dopasowanie po NIP z kartoteki Subiekta, awaryjnie po nazwie przez `_uprosc_nazwe`; kilku kandydatów = nie zgadujemy, kolumna zostaje). `naloz` nadpisuje `items.supplier_id` i loguje nazwami. Okienko pokazuje nazwę z listy RM_BAZA (QUAY), nie pełną z Subiekta.

**Dwie drogi wysyłki, obie muszą dawać `bom_ref`:** okno zamówień (`zbuduj_wiersze`) i okno Przegląd dokumentów (`_pozycje_z_bomem`, projekt per pozycja z trybu `dokumenty` mostu — Uwagi samego ZD są puste). Test 05.09: jedno ZD → Korpus 4 szt z dwóch ZK → ptaszki w 3000 (od razu, mój lock) i 2632 (przy przejęciu przez Andrzeja) → oba na Y: z tym samym terminem.

**Dane testowe:** 3000 Testowy (project 89) ma 6 poz. ☑ z terminem 2026-12-12 z testów 05.09 — nie prawdziwe zamówienie. 2632 Feniks NIE ma ZK w Subiekcie (tylko 2619, 2621, 3000).

## Portal RFQ — zamówienia ZD

Zakładka Subiekt domknięta 05.09.2026 (archiwum, termin +14 dni, podgląd, kontakt prowadzącego) — szczegóły i droga wdrożenia w [[project_rfq_zamowienia_subiekt]].

**Okno zamówień** ma teraz kolumnę PDF (📄, dwuklik, Podgląd/Nowy PDF w tle), szukanie dostawcy w filtrze (pole obok combo, dopasowanie po fragmencie) i filtr po numerze ZD. Okno wysyłki jest `transient` i wraca na wierzch po skanie plików; przycisk to „Utwórz i wyślij email".

## ⚠️ Pułapki, które kosztowały najwięcej czasu

**Jawna implementacja interfejsów Sfery** — `GetType().GetProperty()` i `GetMethods()` zwracają null/pustkę, choć składowe istnieją. Trzeba szukać po `GetInterfaces()`. Objaw: „BRAK metody Eksport()", `sygnatury_eksport: []`. Settery przy jawnej implementacji potrafią po cichu nic nie zrobić — zawsze odczytać wartość z powrotem i potwierdzić.

**Most MUSI być budowany w Release** — `dotnet build -c Release -nowarn:MSB3277`. `bin/Debug` jest ignorowany przez `_find_exe()`. Po `git pull` trzeba przebudować, bo `bin/` nie idzie przez gita.

**Symbol kartoteki tylko ASCII** — Code 128 nie zakoduje „ł", „ś", „ę"; wychodzi to dopiero przy drukowaniu etykiety. Osobna pułapka: myślnik U+2010 wygląda jak ASCII-owy, a kodu z niego nie ma. `do_ascii()` w subiekt_projekt.

**Status dokumentu w Subiekcie to stan MAGAZYNOWY** („Do realizacji", „Wydany towar"), nie ślad wysyłki — nie zmienia się po wysłaniu maila. Stąd osobna tabela `zd_wyslane` w master.sqlite.

**Numer ZD w kolumnie ma ILOŚĆ** („ZD 4/09/2026 (8)") i bywa zbiorczy — do operacji zawsze przez `_numery_zd()`.

**Szerokości kolumn** (`subiekt_kolumny.json`) pasują tylko do układu, w którym powstały — po dołożeniu kolumny nakładały się z przesunięciem i ostatnia wypadała poza ekran. Naprawione w `podepnij_szerokosci`: niezgodna długość → domyślne.

**Pasek stanu należy do kręciołka** — własny `status.config()` z workera kasuje animację. Do postępu wieloetapowego jest `tekst_kreciolka()`.

## Dane produkcyjne (pomierzone)

- 2993 kartoteki, 0 z polskimi znakami w symbolu (14 poprawiono trybem `symbole` 05.09.2026)
- 113 dostawców w RM_BAZA / 629 kontrahentów w Subiekcie, **klucz to NIP, nie nazwa** (nazwy w Subiekcie pełne, w RM_BAZA skrócone — dopasowanie po nazwie dawało 0/2)
- **maile dostawców: 13/113** — użytkownik uzupełnia w trakcie pracy, brak nie blokuje wysyłki
- PDF-y ZD w `Y:\RM_BAZA\zd_pdf\` (NIE %TEMP% — lokalny, niewidoczny dla innych stanowisk)

## Otwarte / świadomie odłożone

1. ~~Zamówiono/termin w arkuszu~~ — ZROBIONE f65b4e6.
1. **PDF nie jest archiwizowany w chwili wysyłki jako dowód** — zostaje ostatni wygenerowany plik. Programy księgowe robią to inaczej: wydruk z chwili wysyłki jest niezmienny.
2. **Import cen z faktur KSeF** — wstrzymane do dostępu produkcyjnego, patrz [[project_ksef_price_import]].
3. **Ceny 0,00 na pozycjach ZK** — otwarte, jeśli ZK ma zasilać faktury.
4. **Widoczność ZD u drugiego użytkownika** — diagnostyka refleksyjna została w moście na życzenie użytkownika.
5. **Diagnostyka w WydrukRecon.cs** (pola dat, powiązań) — do usunięcia po zamknięciu tematu.

**How to apply:** Przed zmianą w oknach Subiekta przeczytaj `git log` ostatnich commitów — opisy zawierają uzasadnienia decyzji i objawy błędów, których nie widać z samego kodu. Patrz też [[project_subiekt_nexo_sfera]], [[project_subiekt_zk_komplety]], [[project_subiekt_wysylka_zd]].
