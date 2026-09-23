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

---

## Stan po audycie 23.09.2026 — WSZYSTKIE `.spec` domknięte

Pułapka wróciła po raz trzeci, bo okna z 17–18.09 nie zostały dopisane.
Naprawione w dwóch krokach, oba na `main`:

| commit | gdzie | co |
|---|---|---|
| `7ba48ff` (firma) | `RM_BAZA_v15_MAG.spec` | 13 modułów: `ksef_faktury_gui`, `ksef_kartoteki`, `subiekt_dostawa_gui`, półprodukty (3), schowek GUI+BOM, `subiekt_sklej_duplikaty`, `subiekt_wydane_do_arkusza`, `database_manager`, `import_bom`, `dwf_thumb` |
| `b145036` (dom) | `RM_BAZA_v15_MAG.spec` + **`RM_MANAGER.spec`** | 5 modułów przeoczonych wyżej |

Dom dołożył:
* **`subiekt_schowek`** — warstwa danych schowka. Do `.spec` trafiły
  `subiekt_schowek_gui` i `subiekt_schowek_bom`, ale nie moduł, z którego
  OBA korzystają (`subiekt_schowek_gui:40`). Kafel „Schowek" padłby u usera.
* **`pandas`** (linia 17051), **`psutil`** (linia 234) — leniwe w RM_BAZA.
* **`RM_MANAGER.spec`**, nietknięty od 16.09, miał tę samą dziurę:
  `rm_optimizer` (`rm_manager_gui:28371, 28515`), `client_version` (`:1499`),
  `requests` (`rm_manager.py:7812`).

**Audyt wszystkich pięciu `.spec` jest teraz czysty.** `RM_KOD.spec`
i oba `RM_Tray_Organizer.spec` nie mają leniwych importów.

### ⚠️ `schedule` — NIE dopisywać, mimo że audyt go wskazuje

`backup_manager.py:1029` importuje `schedule` w `try/except` jako zależność
**opcjonalną**, a pakiet NIE JEST zainstalowany. Wpis w `.spec` wywali build
(„module not found"). Gdyby kiedyś doszedł harmonogram kopii: najpierw
`pip install schedule`, potem wpis. Powód siedzi też w komentarzu w `.spec`.

### `datas` ze źródłami `.py` — NIE jest wymagane

30 modułów jest w `hiddenimports` BEZ wpisu w `datas` i działa (m.in.
`material_calculator`, `rm_klient`, `lock_manager_serwer`). Sprawdzone:
nic w kodzie nie ładuje modułów z pliku (`spec_from_file_location`, `exec`,
`SourceFileLoader` — zero trafień), więc `hiddenimports` wystarcza.
Nie dopisywać źródeł „dla symetrii".

### Fałszywe alarmy audytu — nie dopisywać

Skrypt zgłasza też moduły, które PyInstaller widzi sam:
moduł **wejściowy** `.spec`, oraz importy **top-level** (`backup_manager`
w RM_BAZA, `rm_manager` w RM_MANAGER). Każde zgłoszenie weryfikować
`grep -n "import X"` — z 9 kandydatów realnych było 5.

### Skrypt audytu: `audyt_spec.py`

```
python audyt_spec.py
```

Przechodzi wszystkie `.spec` w repo, dla każdego znajduje moduł wejściowy
(obsługuje `.py` i `.pyw`), liczy domknięcie leniwych importów przez AST
i wypisuje, czego brakuje. Uruchomić **po dołożeniu każdego nowego okna**
i przed budowaniem `.exe` do rozesłania.
