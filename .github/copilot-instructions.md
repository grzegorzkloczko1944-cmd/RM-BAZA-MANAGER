# Copilot Instructions — NOW / Inventor VBA Macros

## ZAKAZ MODYFIKACJI KODU — modele inne niż Claude Sonnet

**PRZED każdą modyfikacją kodu musisz:**
1. Podać swoją pełną nazwę modelu (np. "Claude Sonnet 4.6", "Claude Haiku 4.5", "GPT-4o")
2. Jeśli jesteś modelem **Haiku**, **mini**, **flash** lub innym modelem "lite/fast/small" — **NIE modyfikuj kodu**. Zamiast tego napisz dokładnie: "⚠️ UWAGA: Jestem Claude Haiku (lub inny mały model). Zmiana kodu przez Haiku może wprowadzić błędy. Czy chcesz kontynuować? (tak/nie)"
3. Czekaj na jawne "tak" lub "yes" od użytkownika zanim cokolwiek zmienisz w plikach .ivb

## Kontekst projektu

- Język: VBA7 64-bit (Autodesk Inventor 2013)
- Pliki: `BOM_MACRO.ivb`, `TOOLS++.ivb`, `IAM_MACRO.ivb`, `MESH++.ivb`
- API Inventor 2013 nie posiada `Document.Saved` — nie używaj tej właściwości
- Zewnętrzne zależności: patrz `CLAUDE.md`

## Zasady pracy z kodem VBA/Inventor

- Nie dodawaj kodu diagnostycznego/debug do plików produkcyjnych bez pytania
- Nie używaj właściwości API które nie są potwierdzone dla Inventor 2013
- Przed dodaniem nowej właściwości obiektu Inventor — sprawdź czy istnieje w tej wersji
- Preferuj minimalne zmiany (surgical fix) zamiast refaktoringu całej funkcji
