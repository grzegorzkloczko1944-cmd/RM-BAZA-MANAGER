---
name: project_mag_okno_przegladarka
description: Okno MAG — lista w kontrolce WebBrowser (kółko natywnie); pułapki VBA6/MSForms/MSHTML rozbrojone 28.09.2026, każda kosztowała rundę
metadata:
  type: project
---

# Okno MAG: lista w przeglądarce (WebBrowser) — DZIAŁA (28.09.2026)

Lista wyników = `Shell.Explorer.2` w MSForms: kółko myszy i klawiatura
działają NATYWNIE (po zakazie hooków — [[feedback_bez_hookow_vba]]),
miniatury ładuje sama z `/mag/miniatura`. 7 OSOBNYCH kolumn (user, dobitnie):
miniatura | Symbol | Nazwa | Opis | Stan | Cena | 3D — bez łączenia
symbol+nazwa w jednej komórce. Nagłówki w `<thead>` tabeli, nie w MSForms —
inaczej rozjeżdżają się z kolumnami przy DPI.

Źródła: `NOW/MAKRA/MAG_zrodla/czesci/` → `zloz_MAG.py` → `MAG.vba`
(JEDEN plik do wklejenia; u usera `Module9` w Default.ivb).

## ⛔ Pułapki (każda zjadła rundę debugowania)

* **`Set WithEvents SHDocVw.WebBrowser = ctl.Object` → Type mismatch (13).**
  MSForms oddaje goły `IWebBrowser2` bez info o klasie. Klik łapać przez
  `WithEvents MSHTML.HTMLDocument` (dokument, nie przeglądarka).
* **Domyślne źródło zdarzeń HTMLDocument = `HTMLDocumentEvents`** (nie
  Events2): `onclick` BEZ parametrów; element spod kursora z
  `dok.parentWindow.event.srcElement`. Handler z `pEvtObj` się NIE kompiluje.
* **Błąd kompilacji przy `Execute` przez COM = goły „User interrupt"** —
  bez dialogu i numeru linii. Główne źródła: procedura wstawiona W ŚRODKU
  sekcji deklaracji (deklaracje po procedurze!) i zła sygnatura zdarzenia.
* **`References.AddFromGuid` unieważnia uchwyty COM projektu** — po dodaniu
  referencji wziąć świeży `vbp.VBComponents(nazwa)`, inaczej „Object
  variable not set".
* **Bez `<!DOCTYPE html>` quirks mode** psuje szerokości kolumn.
* **Piksele przeglądarki są FIZYCZNE**, MSForms w punktach × skala Windows:
  wymiary w CSS mnożyć przez `screen.deviceXDPI / 96`.
* **`Declare` w JEDNEJ linii** — kontynuacja ` _` wewnątrz nieaktywnej
  gałęzi `#If VBA7` dopisywała na końcu modułu śmieć `()`.
* `sk.Designer` bywa niedostępny (err 91) — sprzątanie kontrolek projektanta
  tylko best-effort, nie może blokować podmiany kodu.
* Po `VBComponents.Remove` nazwa bywa zajęta do resetu — nie robić
  Remove+Add pod tą samą nazwą w jednym przebiegu.
* Dwa razy „poprawka nie weszła" (zły anchor edycji / odrzucony zapis) →
  user oglądał starą wersję i słusznie się wściekł. **Po instalacji
  weryfikować ZAWARTOŚĆ kodu w Inventorze**, nie tylko plik źródłowy.

Testy: kopia `Default.ivb` jako projekt `MAG_TEST` (scratchpad),
`test_kopia.py` + `pomocnicze_mag.vba`; wynik przez `%TEMP%\mag_test.txt`,
krok awarii okna w `%TEMP%\MAG_okno_blad.txt` (`DebugListy()` w oknie).

Powiązane: [[feedback_bez_hookow_vba]], [[feedback_makra_ivb_nazwa_mag]],
[[project_mag_kopia_subiekta_http]]

- MsgBox z okna MAG, gdy edytor VBA jest otwarty: po OK na wierzch wychodzi EDYTOR (okienko należy do niego) — wygląda jak „wywaliło do VBA", błędu brak. Dlatego „Synchronizuj 3D" bez pytania (28.09.2026); „Synchronizuj SUBIEKT" ma jeszcze MsgBox (TAK/NIE miniatury).
