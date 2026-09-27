---
name: feedback_makra_ivb_nazwa_mag
description: Makra Inventora dostarczać jako .ivb (nie .bas); makro magazynowe nazywa się MAG — tej nazwy używać wszędzie
metadata:
  type: feedback
---

Makra Inventora oddawać jako plik **`.ivb`** (projekt VBA), nie `.bas` —
„tak sobie nazywam makra". Aktywne makra leżą w repo NOW, `NOW/MAKRA/`.

Makro magazynowe (Inventor ↔ Subiekt: szukanie kartoteki, stan, miniatura,
wstawianie modelu 3D) nazywa się **MAG** i tej nazwy używamy WSZĘDZIE:
`MAG.ivb`, plan `PLAN_MAG.md`, serwer `rm_mag_http.py`, adresy `/mag/...`,
klucz konfiguracji `port_mag`. Nie „makro Wstaw z magazynu", nie „makro 3D".

**Why:** użytkownik (27.09.2026): „posługujmy się MAG, wszędzie, jest prosto
i szybko napisać".

**How to apply:** nowe pliki/adresy/nazwy dotyczące tego makra zaczynać od
MAG. ⚠️ Nie mylić z symbolem magazynu `MAG` w Subiekcie
([[project_rm_baza_magazyn_hardcoded]]) — w kodzie Subiekta „MAG" to
magazyn, w makrach i serwerze HTTP to nazwa makra.

**Aktualizacja = wklejenie JEDNEGO pliku** (użytkownik 27.09.2026: „makro
jako tekst przeklejany z VS Code" → „wszystko musi być w tym makrze, jeden
cały plik do wklejenia"). Źródło: `NOW/MAKRA/MAG_zrodla/MAG.vba`, wklejane
do jednego modułu. Kod okna siedzi w tym samym pliku w liniach `'@|`;
makro przy starcie samo zakłada okno przez VBIDE (`VBComponents.Add(3)`)
w KAŻDYM projekcie z tym modułem, a kontrolki zakłada kod okna
(`Me.Controls.Add` + `WithEvents`). Odwołanie do okna TYLKO po nazwie
(`VBA.UserForms.Add("MAG_okno")`) — bezpośrednie `MAG_okno.Show` nie
kompiluje się, gdy okna jeszcze nie ma („Can't find project or library").
⛔ Nie przebudowywać `.ivb` skryptem przy każdej zmianie: Inventor nie zamyka
załadowanego projektu przez COM (E_INVALIDARG), a stara kopia w pamięci
potrafi nadpisać nową przy zapisie z edytora.
Test bez UI: `InventorVBAMembers.Item(...).Execute()` na projekcie
tymczasowym z `VBAProjects.Add()` — uruchamia Sub przez COM.

**Gdzie MAG żyje u usera (28.09.2026):** w `Module9` projektu aplikacji
`Default.ivb` („miałem jechać normalnie na zwykłym Module9"). NIE osobny
`MAG.ivb`, NIE projekty tymczasowe. ⛔ Nie zakładać w jego sesji Inventora
projektów testowych (`VBAProjects.Add`) bez pytania — `MAG_KOMP_TMP` został
na liście po błędzie kompilacji (VBA w [break], komunikat na ekranie usera).
⚠️ Inventor 2013 (M-OLD) ma **VBA 6 32-bit** (`Inventor32bitHost.exe`) — bez
`PtrSafe`/`LongPtr`; deklaracje API tylko w `#If VBA7 … #Else`.

