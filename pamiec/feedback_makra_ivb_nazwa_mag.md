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

**Aktualizacja = wklejenie tekstu** (użytkownik 27.09.2026: „a nie prościej
zrobić makro jako tekst i przeklejać z VS Code?"). Źródło to `.vba`
w `NOW/MAKRA/MAG_zrodla/`, user wkleja je Ctrl+A/Ctrl+V do modułu
i kodu okna. Dlatego okna makr zakładają kontrolki W KODZIE
(`Me.Controls.Add` + `WithEvents` w `UserForm_Initialize`), a w projekcie
okno jest puste — kontrolki z projektanta nie dają się przenieść tekstem.
⛔ Nie przebudowywać `.ivb` skryptem przy każdej zmianie: Inventor nie zamyka
załadowanego projektu przez COM (E_INVALIDARG), a stara kopia w pamięci
potrafi nadpisać nową przy zapisie z edytora.

