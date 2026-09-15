---
name: project_magazyn_nr2_migracja
description: Migracja magazynu nr 2 w Subiekcie - pelna procedura od zera, wykonana 07.09.2026
metadata:
  type: project
---

Uruchomienie **magazynu nr 2 ("Magazyn")** obok starego MAG, z danymi
z inwentaryzacji Excel. Wykonane na produkcji 07.09.2026, zero bledow.
Pelna dokumentacja: `MAGAZYN.md` w repo.

## Kolejnosc krokow (sprawdzona)

1. **Wyzerowac stary MAG** - tryb `rw` partiami po 200 (787 kartotek,
   11996 szt). Komplety osobna partia. Patrz [[project_subiekt_zerowanie_magazynu]].
2. **Zalozyc magazyn** - tryb `magazyn-zaloz` (nowy). WYMAGA jednostki
   organizacyjnej, inaczej Subiekt odrzuca zapis.
3. **Oczyscic dane z Excela** - duplikaty (suma ilosci), wiersze bez symbolu
   i bez ilosci odpadaja.
4. **Porownac symbole z baza** - tryb `stan --symbols-file`.
5. **Zalozyc brakujace kartoteki** - tryb `kartoteka` (JEDNA na wywolanie,
   trzeba petla; ~10 s na kazde uruchomienie Sfery).
6. **Wypchnac stany** - tryb `pw` (nowy) partiami po 200.
7. **Zaktualizowac nazwy i opisy** - tryb `kartoteka-edytuj` (przyjmuje
   cala liste naraz, nie po jednej).
8. **Zapisac polozenia (regal/polka)** - tryb `pola-wlasne --plan --zapisz`
   (nowy) partiami po 300.

## Wynik 07.09.2026

24 kartoteki zalozone, 1353 kartoteki / 24366 szt na "Magazyn"
(PW 2-8/09/2026), 703 nazwy+opisy, 1367 regalow w PoleWlasne1.

## Pulapki ktore kosztowaly czas

- **Nie ma trybu "wyzeruj stany"** - stan to wynik dokumentow, nie pole.
- **Kartoteki sa WSPOLNE dla magazynow** - lista Asortyment pokazuje te same
  pozycje dla obu magazynow i to jest poprawne, nie kopiowanie danych.
- **Pola wlasne PROSTE zapisuje sie wprost na encji**
  (`Asortyment.PolaWlasne.PoleWlasne1`), NIE przez
  `UtworzPolaWlasneAdv2Accessor` (ten jest do pol ZAAWANSOWANYCH v2,
  ktorych baza nie ma). Dodatkowo to metoda rozszerzenia - nie dziala na
  `dynamic`, trzeba rzutowac na `InsERT.Moria.ModelDanych.Asortyment` (CS1973).
- **Dwie rozne "jednostki organizacyjne" w SDK** - patrz
  [[project_subiekt_magazyn_zaloz]].
- **Uslugi nie przyjmuja stanu** - `576410` byl rodzaju "Usluga", PW przyjelo
  pozycje do dokumentu ale stan sie nie utworzyl, bez bledu.
- **RM_BAZA ma MAG na sztywno** - patrz [[project_rm_baza_magazyn_hardcoded]].
  To NIE jest "kontekst magazynu" z GUI Subiekta.

## Przy powtorce w domu

Excel z danymi jest w repo: `magazyn 28.05.2026.xlsx`. Arkusze:
`Arkusz1` (oryginal), `Import do Magazynu` (gotowe dane), `Raport zmian`,
`Rozbieznosci do decyzji`, `Brak w Subiekcie`.

**Uwaga na rozbieznosci Excel vs Subiekt** - nie wszystkie roznice nazw to
nasze zmiany. Czesc to stare rozbieznosci gdzie Excel jest GORSZY (obciete
opisy, smieciowe nazwy typu "1"). Trzeba rozdzielic: pozycje z Opisem =
nasze swiadome zmiany, bez Opisu = do recznej decyzji.
