---
name: feedback-git-push
description: Nie wypychaj na gita bez wyraźnej zgody użytkownika
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 098fb48e-e5e2-4dfd-81f2-f26a87869b6e
---

Nie wykonuj `git push` bez wyraźnego polecenia użytkownika.

**Why:** Użytkownik chce kontrolować kiedy zmiany trafiają na zdalne repozytorium.

**How to apply:** Commituj lokalnie gdy poproszone, ale czekaj na osobne polecenie "pchaj na gita" / "push" zanim wykonasz `git push`.
