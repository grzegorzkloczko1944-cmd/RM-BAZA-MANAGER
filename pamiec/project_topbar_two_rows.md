---
name: project_topbar_two_rows
description: Górny pasek RM_MANAGER rozbity na dwa wiersze — przyciski narzędzi wyłaziły poza okno na małej rozdzielczości
metadata: 
  node_type: memory
  type: project
  originSessionId: 82f2a873-9dc2-427e-b90e-cba22eee7c22
---

Górny pasek (top bar) RM_MANAGER rozbity na DWA wiersze (2026-07-19), bo przyciski wyłaziły poza okno i na mniejszej rozdzielczości ucinały panel użytkownika/backup po prawej.

- `self.top_frame` (wiersz 1, height=54): PROJEKT label + project_combo + Odśwież + 4 lock buttons (Przejmij/Wymuś/Anuluj/Zdejmij) + separator + Backup label/combo + separator + UŻYTKOWNIK label/combo (po prawej). Elementy krytyczne — zawsze widoczne.
- `self.top_frame2` (wiersz 2, height=48): label "NARZĘDZIA:" + 8 przycisków: Alarmy, Multi-projekt, Kopiuj projekt, Urlopy, Status, Podsumowanie, Optymalizator, AI Asystent.

Oba framy pack(fill=X) + pack_propagate(False). warning_frame i notifications_banner: pack z after=self.top_frame2 (nie top_frame — inaczej wcisnęłyby się MIĘDZY wiersze paska).

Dodając nowy przycisk narzędzia → dawaj go na self.top_frame2 (pady=6, nie 10).
