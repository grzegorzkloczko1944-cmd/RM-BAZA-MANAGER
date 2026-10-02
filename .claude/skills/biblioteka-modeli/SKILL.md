---
name: biblioteka-modeli
description: Biblioteki modeli 3D elementów handlowych (O-ringi, łożyska w oprawach, wózki Hiwin, Elesa-Ganter i kolejne) — jeden model na kartotekę Subiekta, iProperties, miniatury, indeks MAG, zdjęcia i opisy w Subiekcie. Użyj, gdy użytkownik mówi o modelach 3D do Subiekta/MAG, o nowej partii O-ringów, łożysk, wózków lub o znajdowaniu i kopiowaniu modeli z B:, V:, C:\Projekty.
---

# Biblioteka modeli 3D

Użytkownik uruchomił ten skill, bo chce, żebyś **bez tłumaczenia** wiedział, co i jak robić przy bibliotekach modeli 3D.

1. **Przeczytaj w całości** instrukcję dla agenta (zanim cokolwiek zrobisz):

   `C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER\biblioteka_modeli\README.md`

   Jeśli pliku nie ma (inny komputer) — w `C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER` zrób `git pull`
   (tylko odczyt zmian, bez commitów/pushów) i spróbuj ponownie. Przykłady kodu są w `wzorce_kodu\` obok — do adaptacji, nie do ślepego uruchamiania.

2. Zrób to, o co prosi użytkownik (jego zadanie: `$ARGUMENTS`). Jeśli nic nie podał — zacznij od
   **raportu stanu** wg README (przepis 5.A `stan` dla O-ringów: kartoteki vs modele, sieroty, Part Number, Opis, położenie)
   i zapytaj, którą rodzinę/partię ruszamy.

3. Trzymaj się zasad z README, szczególnie:
   * **suchy przebieg i liczby przed zapisem**; zapis do Subiekta, nadpisanie i kasowanie tylko na wyraźne polecenie w tej rozmowie,
   * osobna instancja Inventora (nigdy sesja użytkownika), zapis w formacie Inventora 2015 jest dozwolony (nie pytaj; podaj wersję w raporcie),
   * przy starcie nowej instancji Inventora wyskakuje okno VBA („Module7… kontynuować?”) — uruchom `wzorce_kodu\watchdog_vba.py` (z PID-ami sesji użytkownika jako chronionymi), nie każ klikać „Tak”,
   * gdy użytkownik chce pokazać zespołowi listę do zaakceptowania (ptaszki tak/nie) — patrz README sekcja 10 (strona HTML z miniaturami, wzorce `decyzje_*`),
   * nigdy nie wpisuj haseł, nie commituj/pushuj bez zgody,
   * na końcu raport wg checklisty z README (co zrobione — liczby, czego nie sprawdzałeś, co wymaga decyzji)
     oraz aktualizacja pamięci projektu.
