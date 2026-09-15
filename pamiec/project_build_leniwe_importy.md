---
name: project_build_leniwe_importy
description: PyInstaller nie widzi importów wewnątrz funkcji — .exe RM_BAZA nie zawierał całej integracji z Subiektem
metadata:
  type: project
---

**Naprawione 07.09.2026, commit `5792ac1`** (`RM_BAZA_v15_MAG_STATS_ORG.spec`).

## Pułapka

RM_BAZA importuje moduły Subiekta **leniwie** — `import subiekt_panel` siedzi
wewnątrz metody, nie na górze pliku. To świadome: start aplikacji nie płaci za
okna, których większość userów nie otworzy.

Ale **PyInstaller analizuje importy statycznie** i takiego modułu NIE WIDZI.
Przy pustym `hiddenimports` w `.spec` do `.exe` nie trafiło **ani jedno** z 20
takich modułów.

**Dlaczego to było niewidoczne:** build kończył się sukcesem, `.exe` startowało,
a dopiero kliknięcie „SUBIEKT" dawało `ModuleNotFoundError` — i to **u usera, nie
u budującego**, bo ten ma obok pliki `.py`. To samo dotyczyło KSeF, kalkulatora
materiału i panelu plików.

## Jak wyliczyć listę (nie ręcznie)

Domknięcie zależności przez AST: znajdź importy lokalnych modułów **wewnątrz
funkcji/klas** (te, których nie ma na poziomie modułu), potem rekurencyjnie to,
co one same importują. Wyszło 34 moduły lokalne + 10 zewnętrznych, które wchodzą
tylko przez nie i bywają gubione przy importach dynamicznych: `tksheet`,
`win32com`/`pythoncom`, `PIL`.

## Weryfikacja — trzy stopnie

1. wszystkie moduły z `.spec` importują się w Pythonie
2. ich nazwy są obecne w archiwum zbudowanego `.exe` (`nazwa.encode() in dane`)
3. `.exe` startuje i otwiera okna Subiekta

## ⚠️ Przy dokładaniu nowego okna

Nowy moduł ładowany leniwie **trzeba dopisać do listy w `.spec`**, inaczej
zniknie z `.exe` po cichu. Ten sam problem dotyczy każdego `.spec` w repo.

**Bliźniacza pułapka (RM_TRAY, ten sam dzień):** `build_tray_organizer.bat`
szukał ikony `rm_tray_icon.ico`, a plik nazywa się `Tray_icon.ico` — warunek
`if exist` nigdy nie był spełniony, więc skrypt cicho ustawiał `--icon=NONE`
i budował `.exe` **bez ikony**, kończąc sukcesem. Naprawione w repo NOW
(`3e4b9b4`): build idzie przez `.spec`, który jest jedynym źródłem prawdy
o parametrach.

**How to apply:** Po każdej zmianie w oknach Subiekta i przed rozesłaniem `.exe`
sprawdzić punkt 2 — obecność modułów w archiwum. Patrz
[[project_exe_persistent_paths]], [[project_subiekt_karta_pozycji]].
