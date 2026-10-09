# Instrukcje dla agentów (Codex, Cowork, Copilot, Cursor, Gemini i inni)

**Pełne zasady pracy są w [`CLAUDE.md`](CLAUDE.md) — przeczytaj go w całości PRZED pracą.**
Ten plik celowo NIE powtarza `CLAUDE.md` (stara kopia się rozjechała i podawała nieaktualne
dane — 01.10.2026). Jest identyczny w repo NOW i RM-BAZA-MANAGER (pilnuje `sprawdz_kopie.py`).

Dotyczy komputera firmowego i domowego tak samo. Twarde reguły, obowiązują zawsze:

1. **Bez mixów między repo NOW ↔ RM-BAZA-MANAGER.** Każdy kod ma jedno miejsce. Nie kopiuj
   modułu do drugiego repo; kopia tylko zarejestrowana w `kopie_miedzy_repo.json` (w obu repo)
   i zmieniana w obu naraz. Przeniesiony program = stary katalog usunięty, bez „-COPY”,
   „_stary”, „v2” obok. Szczegóły: `CLAUDE.md` → „WSPÓLNE PLIKI Z DRUGIM REPO”.
2. **Hook `.githooks/pre-commit` (strażnik kopii) — nie obchodzić** (`--no-verify` zakazane).
   Zatrzymał commit → napraw przyczynę według komunikatu. Raport: `python sprawdz_kopie.py`.
   Na nowym klonie raz: `git config core.hooksPath .githooks`.
3. **Nie pushuj bez wyraźnej zgody użytkownika.** Commit lokalny — tak; push — dopiero po „pchaj”.
4. **Cudza praca w drzewie jest nietykalna.** Niezacommitowane zmiany, których nie zrobiłeś
   (inna sesja, inny agent, user) — nie commituj, nie cofaj, nie stashuj, nie formatuj.
   Commituj wyłącznie swoje pliki, po nazwie (`git add <plik>`, nie `git add -A`).
5. **Programy na produkcji:** nie zamykaj okien użytkownika (RM_BAZA, RM_MANAGER, Inventor),
   nie testuj w jego sesji Inventora, nie zapisuj do żywych baz bez zgody. Testy na kopiach.
6. **Język i ustalenia:** odpowiadasz po polsku; zanim zmienisz moduł, przeczytaj jego notatki
   (RM-BAZA-MANAGER: `pamiec/`, NOW: `DOKUMENTACJA/`) i `git log` — tam są decyzje usera
   i rzeczy, których nie wolno próbować ponownie.
