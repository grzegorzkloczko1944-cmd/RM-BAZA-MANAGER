---
name: feedback_nie_czekaj_na_dlugie_operacje
description: "Nie blokować rozmowy pętlą czekającą na długą operację (kopiowanie GB, build) — odpalić i sprawdzić wynik później"
metadata:
  type: feedback
---

Nie czekać w pętli na zakończenie długiej operacji po stronie serwera
(robocopy 2,8 GB, build, długi import). 14.09.2026 odpaliłem zadanie backupu
i wstawiłem pętlę „sprawdź stan co 20-30 s, aż skończy" — rozmowa stała
kilka minut, a użytkownik zapytał: *„co tak myślisz tyle czasu?"*.

**Why:** operacja i tak chodzi po swojemu na serwerze i skończy się bez
mojego nadzoru. Patrzenie na „stan: Running" w kółko nie daje ŻADNEJ
informacji poza tą, że jeszcze trwa — a odbiera użytkownikowi możliwość
powiedzenia czegokolwiek.

**How to apply:** uruchomić, potwierdzić że wystartowało (stan `Running`,
pierwsze pliki na miejscu), oddać głos. Wynik sprawdzić JEDNYM zapytaniem
przy następnej wymianie zdań albo gdy user zapyta. Jeśli naprawdę muszę
poczekać — użyć `run_in_background: true`, nie pętli blokującej.
