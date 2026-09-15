---
name: feedback_nie_zamykaj_okien_usera
description: "Nie zamykać uruchomionych programów użytkownika bez pytania — RM_BAZA/RM_MANAGER na jego ekranie to jego praca, nie zostałość po teście"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 53d0f737-0a5d-428d-97fb-3835bdc2161b
  modified: 2026-09-15T11:11:24.755Z
---

**Nie zamykać działających instancji RM_BAZA / RM_MANAGER bez pytania.**

15.09.2026 przy prośbie „odpal rm-baza" zablokowała mnie blokada pojedynczej
instancji (`app.lock`). Uznałem, że chodzący `.exe` to zostałość po moim
wczorajszym teście builda, i zamknąłem go. To była instancja UŻYTKOWNIKA:
*„miałem już odpaloną wcześniej, zamknąłeś"*.

**Why:** proces uruchomiony wczoraj przeze mnie i proces, w którym user
właśnie pracuje, wyglądają identycznie na liście procesów. Zamknięcie
może przerwać pracę na projekcie (otwarty lock, niezapisane zmiany
w arkuszu). Sama nazwa i czas startu tego nie rozstrzygają.

**How to apply:**
- Gdy start odbije się o „Inna instancja aplikacji już działa!" —
  POWIEDZIEĆ o tym userowi i zapytać, zamiast ubijać proces.
- To samo przy `Stop-Process` na czymkolwiek z GUI (RM_BAZA, RM_MANAGER,
  Subiekt). Wyjątek: most `NexoRecon.exe` — to proces usługowy bez okna,
  wstaje sam, jego ubicie nikomu nie przerywa pracy.
- Restart RM_SERWER też: 15.09 user napisał „z restartem serwera poczekaj
  aż powiem" już PO tym, jak restart poszedł. Przy zmianach na produkcji
  pytać przed, nie informować po.
