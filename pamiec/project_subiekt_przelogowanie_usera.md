---
name: project_subiekt_przelogowanie_usera
description: OTWARTE — przelogowanie usera w RM_BAZA nie rusza mostu Subiekta; ustalenia i warianty
metadata: 
  node_type: memory
  type: project
  originSessionId: 834ab505-1a4e-4f62-bb02-1b4871507207
  modified: 2026-09-06T15:37:35.079Z
---

**ODŁOŻONE 06.09.2026** („na razie zostawmy to"). Nic nie zaimplementowane.
Ważniejsze od samego problemu jest ustalenie niżej: konto Subiekta należy
do MASZYNY, nie do człowieka.

## Problem

Przelogowanie na innego usera w RM_BAZA zmienia `current_user`,
`current_user_role` i nazwę w `lock_manager` — i **nic więcej**. Most Subiekta
zostaje na koncie, na którym wystartował.

Trzy niezależne tożsamości, które dziś nie są ze sobą związane:

| Co | Skąd | Kiedy się zmienia |
|---|---|---|
| user RM_BAZA | tabela `users` w master.sqlite | przy przelogowaniu |
| operator nexo (most) | `nexoLogin` w `.nexo_sfera.json` | tylko przy restarcie mostu |
| konto Windows | system | nigdy |

Most **celowo** żyje dłużej niż sesja RM_BAZA (przeżywa zamknięcie aplikacji) —
to była cała idea stałego mostu, patrz [[project_subiekt_most_stan_serwera]].

## ⚠️ TO NIE JEST BŁĄD — konto Subiekta jest PRZYPISANE DO MASZYNY

Ustalone przez użytkownika 06.09.2026, gdy zaproponowałem przełączanie operatora
mostu przy zmianie usera. **Konto nexo należy do STANOWISKA, nie do człowieka** —
dlatego `.nexo_sfera.json` leży w profilu maszyny, a nie w bazie użytkowników.

Konsekwencja: przelogowanie usera w RM_BAZA **nie powinno** ruszać mostu. Most na
maszynie magazyniera pracuje jako magazynier, bo to jego stanowisko — niezależnie
od tego, kto akurat klika w RM_BAZA. Zapis w Subiekcie mówi więc prawdę o tym,
GDZIE dokument powstał.

Wariant A niżej (konfiguracja per user RM_BAZA) byłby **walką z tym założeniem** —
nie proponować go ponownie bez wyraźnej zmiany decyzji.

## Co ewentualnie zostaje (gdyby wróciło)

Jedyne, co ten model gubi, to informacja, KTO przy stanowisku zlecił operację.
Gdyby kiedyś było potrzebne, właściwą drogą jest wariant B — nazwisko usera
RM_BAZA w Uwagach ZD/ZK — a nie zmiana operatora nexo.

## Historyczne warianty (rozważane, zanim padło ustalenie o maszynie)

- **A. Konfiguracja per user RM_BAZA** — ⛔ ODRZUCONE (patrz wyżej): każdy
  wpisywałby swoje hasło nexo, most restartowałby się przy przelogowaniu.
  Sprzeczne z modelem "konto = maszyna", w dodatku ~10 s na każdą zmianę usera.
- **B. Konto techniczne + ślad w Uwagach** — nie udajemy, że wystawił to Kowalski;
  RM_BAZA dopisuje jego nazwisko w Uwagach ZD/ZK (i tak je wypełniamy). Zero kosztu,
  działa dla ludzi bez konta w nexo.
- **C. Blokada samych zapisów po przelogowaniu** — odczyty (Magazyn, Dokumenty,
  Zapotrzebowanie) bez zmian, bo tam operator nie ma znaczenia.

**How to apply:** Okno „Połączenie z Subiektem" ([[project_subiekt_okno_logowania]])
NIE jest tu luką — pyta o hasło ADMIN-a przy każdym otwarciu, niezależnie od
zalogowanego usera. Wracając do tematu, zacząć od pytania o konta nexo, nie od kodu.
