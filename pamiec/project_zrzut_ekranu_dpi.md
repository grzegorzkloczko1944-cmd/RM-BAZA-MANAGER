---
name: project_zrzut_ekranu_dpi
description: Zrzut fragmentu ekranu w RM_BAZA wycinał losowe kawałki — skalowanie Windows 150% (Tk logiczne vs ImageGrab fizyczne); fix = kursor w pikselach fizycznych
metadata:
  type: project
---

# Zrzut fragmentu ekranu a skalowanie DPI (27.09.2026)

Objaw: „Zaznacz fragment ekranu" (edytor kartotek, zdjęcie kartoteki)
pokazywał losowe wyrywki, czasem tło Inventora — nie to, co zaznaczono.

Przyczyna: RM_BAZA **nie jest DPI-aware**, a M-OLD ma 3 monitory po **150%**.

| źródło | pulpit wirtualny |
|---|---|
| Tk / GetSystemMetrics w procesie | 7680×1441 od (−2560, −1) — logiczne |
| `ImageGrab.grab(all_screens=True)` | **11520×2161** od (−3840, −1) — fizyczne |

Wycinanie po współrzędnych Tk dawało obszar 1,5× za mały i przesunięty.
Pierwsza wersja (5f4797c) poprawiała tylko ujemny offset monitora po lewej
— to było za mało.

Fix (`subiekt_edytor_gui._kursor_fizyczny`): pozycja kursora przy
wciśnięciu i puszczeniu czytana w kontekście wątku `DPI_PER_MONITOR_V2`
(−4) → piksele fizyczne, ten sam układ co zrzut. Działa przy dowolnym
skalowaniu i układzie monitorów (w firmie też 3 monitory, inny układ).

⛔ Nie „naprawiać" stałym mnożnikiem 1,5 ani `SetProcessDpiAwareness` dla
całego procesu — to drugie zmienia wygląd całej RM_BAZA (Tk staje się
drobny na skalowanych ekranach).

Każdy przyszły zrzut/pozycjonowanie po współrzędnych ekranu w RM_BAZA ma
tę samą pułapkę. Powiązane: [[project_okna_trzy_monitory]]
