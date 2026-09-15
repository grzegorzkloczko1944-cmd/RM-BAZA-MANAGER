---
name: project_subiekt_wysylka_zd
description: Wysyłka ZD mailem — PDF ze Sfery + rysunki z serwera + Outlook COM; działa, ale UX do poprawy (04.09.2026)
metadata:
  type: project
---

Przycisk ✉ „Wyślij ZD dostawcy" w oknie Zamówień do dostawców ([subiekt_zamowienia.py](subiekt_zamowienia.py) `_wyslij_zd`) + moduł [subiekt_wyslij_zd.py](subiekt_wyslij_zd.py) + tryb `wydruk` w moście ([Wydruk.cs](subiekt_sfera/NexoRecon/Wydruk.cs)). **Stan 04.09.2026: działa end-to-end, ale użytkownik ocenił jako „jakiś kasztan" — UX do przerobienia.**

**Co działa (sprawdzone na produkcji):** `sfera.Wydruki().Utworz(typ)` → ustawić `ObiektDoWydruku`, `SciezkaEksportu`, `FormatEksportu="pdf"`, `NazwaDokumentuUzytkownika`, `ZastapPliki` → `Eksport()`. PDF-y dla ZD 4/09/2026 (QUAY) i 3/09/2026 (ADR-CNC), po 2 strony, wzorcem Subiekta (Wasz własny `Id=100000`, nie fabryczny). Typ wzorca bierze się z `Konfiguracje().DaneDomyslne.ZamowienieDoDostawcy.TypWzorcaWydruku` (=13800) — **nie zgadywać**. Dostępnych formatów eksportu jest 20 (pdf, xls, html, svg, xps…).

**Why (pułapki, które kosztowały czas):**
- Obiekty wydruku implementują interfejsy **JAWNIE** — `GetType().GetProperty()` i `GetMethods()` zwracają null/pustkę, choć składowe istnieją. Trzeba szukać po `GetInterfaces()`. Objaw: „BRAK metody Eksport()", `sygnatury_eksport: []`. Stąd pomocnicze `Wlasciwosc()`/`Metody()` w Wydruk.cs.
- Setter przy jawnej implementacji potrafi po cichu nic nie zrobić → zawsze odczytać wartość z powrotem i potwierdzić, zanim uzna się eksport za udany.
- **Most musi być zbudowany w Release** (`dotnet build -c Release -nowarn:MSB3277`) — `_find_exe()` ignoruje bin/Debug. Sam się na tym przejechałem; mechanizm wykrywania starego mostu zadziałał i powiedział wprost, o co chodzi.

**PORAŻKA z mailami — do zapamiętania:**
1. Zacząłem od `IWydruk.Eksport()` szukanego na typie konkretnym → 0 metod (patrz jawne interfejsy wyżej). Stracone dwie iteracje.
2. Sprawdzałem drogę „Sfera wysyła maila" — `WiadomosciPocztowe()` ma `UtworzNowaWiadomosc`, ALE **kont pocztowych w Subiekcie jest 0**. Klient poczty nexo nie jest u nich skonfigurowany, więc ta droga jest ślepa bez wcześniejszego ustawiania kont w Subiekcie. Użytkownik sam zaproponował „PDF ze Sfery, resztę ogarnie Python" — i to była trafniejsza decyzja niż moje drążenie API poczty.
3. Napisałem, że „mailto: nie umie załączników" — użytkownik odpisał „UMIE bo tak robi". Formalnie miałem rację co do samego `mailto:` (standard nie przenosi załączników), ale to była **nieistotna dygresja**: Subiekt robi to przez COM Outlooka, nie przez mailto. Zamiast prostować, trzeba było od razu sprawdzić, jaki jest domyślny klient — Outlook 16.0, COM działa, `pywin32` zainstalowany.
4. Dopasowanie maila dostawcy zacząłem po NAZWIE → 0/2 trafień, bo w Subiekcie nazwy są pełne („QUAY BIURO HANDLOWO-USŁUGOWE SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ"), a w RM_BAZA skrócone („QUAY"). Przerobione na **NIP** — zgadza się co do cyfry (QUAY 9721002583, ADR-CNC 1251766125). Klucz po NIP był już ustalony wcześniej przy wiązaniu dostawców, patrz [[project_subiekt_nexo_sfera]] — powinienem był od razu z niego skorzystać.

**How to apply:** Wysyłka NIGDY nie woła `Send()` — tylko `mail.Display(False)`, człowiek klika Wyślij. Rysunki zbierane są `_find_files_for_drawing` z arkusza głównego (ta sama funkcja co RFQ: PDF/DXF/DWF/STEP/STP/STL, katalogi projektu + ZP/), nie własną logiką. Nadawca w podpisie = `users.display_name` zalogowanego. Fallback na `mailto:` istnieje, gdy nie ma Outlooka — wtedy okno mówi wprost, że załączniki trzeba dopiąć ręcznie, i otwiera katalog. **Maile dostawców: 13/113 wypełnionych** (04.09.2026) — użytkownik uzupełnia w trakcie pracy, brak adresu nie blokuje (pole edytowalne). Patrz [[project_subiekt_zk_komplety]].
