---
name: feedback-git-pull-multi-maszyna
description: "Zawsze przypominaj o git pull/status przed zmianą kodu, gdy użytkownik pracuje na tym samym repo z dwóch maszyn (firma + M-OLD w domu)"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e0ba9b4b-d4d7-4304-bc9f-6adc6046664a
  modified: 2026-09-03T21:15:56.705Z
---

Przed jakąkolwiek zmianą kodu w RM-BAZA-MANAGER przypominaj o `git pull`
(i sprawdzeniu `git status`), gdy sesja dzieje się na innej maszynie niż
zwykle — użytkownik pracuje na tym samym repo/branchu (`main`) zarówno
w firmie, jak i na komputerze domowym `M-OLD` (od 2026-09-03, testy
integracji Subiekt nexo, patrz [[project_subiekt_integracja_m_old]]).

**Why:** Użytkownik jest jedynym committerem, pracuje bezpośrednio na
`main` z obu miejsc (świadomie wybrał prostszy model zamiast branchy),
więc jedyne zabezpieczenie przed rozjazdem/nadpisaniem pracy to
zawsze aktualny `pull` przed startem i commitowanie tylko sprawdzonych
zmian. Dane (bazy sqlite, `.nexo_sfera.json`) są bezpieczne strukturalnie
przez `.gitignore` — to kod jest jedynym punktem ryzyka.

**How to apply:** Na początku sesji dotyczącej zmian w kodzie tego repo
(nie dotyczy czystej lektury/analizy) zaproponuj lub wykonaj `git pull`
i `git status` zanim zaczniesz edytować pliki. Nie pushuj bez wyraźnej
zgody — patrz [[feedback_git_push]].
