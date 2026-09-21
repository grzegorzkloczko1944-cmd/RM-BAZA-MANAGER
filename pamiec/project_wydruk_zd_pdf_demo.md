---
name: project-wydruk-zd-pdf-demo
description: "Eksport PDF zamówienia (tryb wydruk) działa w firmie, ale nie na demo M-OLD — różnica instalacji, nie błąd kodu"
metadata: 
  node_type: memory
  type: project
  originSessionId: e0ba9b4b-d4d7-4304-bc9f-6adc6046664a
  modified: 2026-09-04T21:44:22.747Z
---

Tryb `wydruk` w NexoRecon (eksport ZD do PDF wzorcem Subiekta, używany przez
`subiekt_wyslij_zd.py`) **działa na firmowym Subiekcie, a nie działa na
instalacji demo `Nexo_RMPRODUKCJA` na M-OLD**. Nie diagnozować tego od nowa
ani nie przepisywać kodu na podstawie objawu z demo.

Ustalenia z `NexoRecon.exe wydruk-recon` (2026-09-04, M-OLD):

- wzorzec wydruku **jest** znaleziony (`typ_wzorca_z_konfiguracji: 13800`,
  `WzorceWydrukow;Id=76`), format `pdf` jest na liście dostępnych,
- parametry ustawiają się poprawnie, ale `SciezkaEksportu` zostaje
  **domyślna** (`...\AppData\Local\Temp\`), mimo podania `--pdf=`,
- `Eksport()` **nie rzuca wyjątku i nie tworzy pliku** — nigdzie, nie tylko
  w katalogu docelowym (sprawdzone `find` po całym Temp),
- `konta_pocztowe: 0` — demo nie ma skonfigurowanej poczty w Subiekcie.

Dostępne sygnatury (gdyby kiedyś trzeba było wrócić do tematu):
`Eksport()`, `Eksport(Object, StiExportFormat, String, Boolean)`,
`Eksport(List)`, plus warianty Async. Kod woła bezparametrową.

**Why:** Kuszące jest „naprawienie" tego przez przejście na sygnaturę
z parametrami, ale skoro w firmie PDF się generuje, zmiana groziłaby
zepsuciem działającej ścieżki dla objawu widocznego tylko na demo.

**How to apply:** Na M-OLD okno „Wyślij zamówienie" pokaże `problemy: 1`
(brak PDF) — to oczekiwane, samego wydruku ZD tu nie przetestujesz.

Reszta ścieżki DZIAŁA i da się ją sprawdzić na miejscu:

* **rysunki z serwera** — `V:` na M-OLD ma folder `2627 YamCandle_Z`
  (387 plików), a wyszukiwarka znajduje po 2–3 pliki na numer rysunku
  (`pdf`/`dxf`/`dwf`). Testować na projekcie **2627** i pozycjach
  z numerem rysunku. Projekt 3500 nie ma folderu na `V:`, a jego pozycje
  to elementy handlowe (łożyska, kołki), które rysunków nie mają — stąd
  „Załączników: 0" przy pierwszej próbie.
* **Outlook COM** — udaje się, gdy Outlook akurat działa; potrafi paść
  („Wykonanie serwera nie powiodło się"), bo na M-OLD nie ma licencji ani
  skonfigurowanego konta (okno „Plik danych programu Outlook"). Wtedy kod
  poprawnie schodzi na `mailto:` — bez załączników, z komunikatem.
* wiadomość jest tylko OTWIERANA (`Display`), nigdy `Send()`.

`tresc_wiadomosci()` oczekuje **krotek** `(symbol, nazwa, ilosc, jm)` —
podanie słowników nie rzuca błędu, tylko wypisuje nazwy kluczy.
