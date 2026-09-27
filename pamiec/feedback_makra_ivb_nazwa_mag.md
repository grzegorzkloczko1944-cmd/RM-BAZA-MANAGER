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
