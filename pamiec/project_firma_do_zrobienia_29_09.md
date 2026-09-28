---
name: project_firma_do_zrobienia_29_09
description: Lista na firmę po sesji domowej 28/29.09.2026 — wdrożenie MAG etap 4 (wstaw/przypisz/zdjęcia), oringi, białe tło miniatur
metadata:
  type: project
---

Zrobione w domu (M-OLD), do przeniesienia do firmy (user: „w firmie ogarnę resztę"):

1. **W2019S** — wgrać `rm_mag_http.py`, `rm_serwer_operacje.py`,
   `indeks_modeli_3d.py` (C:\Apps\RM_SERWER, diff+backup jak w
   WDROZENIE_MAG_FIRMA.md), restart RM_SERWER ZA ZGODĄ. Nowe: przypisz/usuń
   modelu, miniatura ze stacji, kolejka `zlecenia_zdjec`, białe tło.
2. **MONGO** — RM_BAZA z nowym `subiekt_kopia_zlecenia.py` (wgrywa zdjęcia
   do Subiekta z kolejki). .exe → nowy build (`.spec` ma już
   `subiekt_wybor_kartoteki_gui` dla F4).
3. **Stacje** — nowy `MAG.vba` (NOW/MAKRA/MAG_zrodla) do Module9, zamknąć
   stare okno MAG. `hosts` z `192.168.100.84 W2019S` na każdej stacji z MAG.
4. **Oringi** — `B:\Znormalizowane\Oringi` (205 modeli) skopiować, jeśli
   B: domowe ≠ firmowe; potem `python indeks_oringi_zasiew.py --zapisz`.
   Zdjęcia oringów do Subiekta — NIE wgrane, czeka na zgodę usera.
5. **Białe tło** starych miniatur — samo przy pierwszym „Synchronizuj 3D"
   (~20 min raz) albo w nocy.

Szczegóły: [[project_mag_wstaw_i_przypisz]], [[project_oringi_wymiarowka]],
[[project_mag_wdrozenie_firma_wykonane]].
