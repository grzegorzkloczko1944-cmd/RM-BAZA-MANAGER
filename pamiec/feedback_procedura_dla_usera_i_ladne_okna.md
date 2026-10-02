---
name: feedback_procedura_dla_usera_i_ladne_okna
description: „Jaka procedura naprawy?" = kroki w RM_BAZA dla usera, nie czytanie kodu; nowe okna w stylu aplikacji (nie simpledialog/messagebox) — user ocenia wygląd
metadata:
  type: feedback
---

1. **Pytanie o procedurę = kroki klikane w RM_BAZA.** 02.10.2026 user zapytał „jaka jest procedura naprawy?" (dublety w arkuszu), a ja zacząłem czytać kod narzędzia — przerwał: „ale przez usera, nie w kodzie rm-baza".
   **How to apply:** najpierw odpowiedź jako lista kroków w interfejsie (który przycisk/okno/menu), z decyzją, którą user musi podjąć. Kod czytać tylko, gdy kroków nie da się podać bez sprawdzenia — i wtedy powiedzieć, że sprawdzam.

2. **Okna mają być ładne.** User odrzucił systemowe `simpledialog.askstring` („popracuj nad designem, te okno ma być ładne"). Wzorzec, który przyjął: `subiekt_dokumenty_gui._okno_ilosci` — ciemny pasek (#2c3e50) z tytułem i kontekstem, karta pozycji, duże liczby „teraz → nowa", ±, walidacja w oknie (wyszarzony przycisk zamiast osobnego okna błędu), zielony przycisk główny, Enter/Esc. Komunikaty: `subiekt_projekt.komunikat` (info/warn/error, pytanie=True).
   **How to apply:** nowe dialogi w tym stylu; przed oddaniem zrobić zrzut (PIL `ImageGrab` + `ctypes.windll.user32.SetProcessDPIAware()` + prostokąt z `subiekt_stany._prostokat_okna`, inaczej kadr się rozjeżdża) i obejrzeć.

3. **User nie widzi wewnętrznych nazw** — „Usuń zaznaczone" mylił dokumenty z pozycjami; etykieta ma mówić, CO się kasuje.

Powiązane: [[feedback_nic_po_cichu]], [[project_okna_pokazane_zbudowane]].
