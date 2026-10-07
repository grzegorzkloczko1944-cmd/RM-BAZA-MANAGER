---
name: feedback_inventor_szybko_do_roboty
description: Zlecenie modelu w Inventorze usera („narysuj korek”) — od razu do roboty z jawnymi założeniami, bez długiego śledztwa; lista błędów z 07.10.2026, które zjadły czas
metadata:
  type: feedback
---

07.10.2026 user: „narysuj mi żółty korek do tego zjazdu… ścianka 2 mm” → budowa trwała ~30 s, a całość
bardzo długo. User: **„dlaczego tak długo to trwało????”** i kazał zapisać błędy.

**Błędy — nie powtarzać:**
1. **Most niezaładowany → pisanie klienta od zera.** Jest gotowy:
   `NOW/RM_INVENTOR_MCP/klient_usera.py` (tryb normalny = Inventor usera; `sesja()` do kroków
   zależnych od uchwytów). Na koniec dnia przypomnieć userowi o restarcie Claude Code.
2. **Śledztwo przed robotą** (grep po repo, README, dwa foldery projektów, wszystkie `.rm_zjazd.json`).
   Wystarczyło: `inventor_stan` + struktura → jeden `.rm_zjazd.json` zjazdu ze złożenia.
3. **Szukanie stylu koloru na raty** (3 podejścia, złe kodowanie / filtr). Od razu: `inventor_dokument_kolor
   lista=True` do pliku, przeszukać JSON. Żółty w Inventorze 2013 PL = **„Żółta”**.
4. **Tor zjazdu liczony z błędem** — `punkty` w `.rm_zjazd.json` to dicty, do `sciezka_w` idzie
   `[w["P"] for w in punkty]` (jak `rm_zjazd.punkty_P`).
5. **Podwójne sprawdzenia na końcu** (kolizje 2×, porównanie obu zjazdów) — raz wystarczy.
6. **Blokowanie Inventora usera** (drugi korek, 07.10): user „po co zamykasz IAM?… po co nieaktywny
   jest inventor czy zablokowany jak w nim robisz?”. Nic nie było zamknięte — ale (a) w czasie
   wywołania COM okno Inventora nie przyjmuje kliknięć, a `inventor_czytaj_kolizje` na 30 częściach
   (para po parze) trzyma je długo, i to puszczone 2×; (b) most gasił odświeżanie ekranu na KAŻDE
   polecenie, więc okno wyglądało na puste / zamknięte. Decyzja usera „Zrób”:
   - **kolizje całego złożenia w sesji usera tylko na jego prośbę** (nie „dla pewności” po wstawieniu),
   - most od `f782a6c`+1: w sesji usera odświeżanie ZOSTAJE (domyślne `ekran=None`), gaszą je tylko
     ciężkie odczyty całego złożenia (`ekran=False`: struktura, kolizje, BOM, wiązania, audyt,
     porównanie z RM_BAZA, stan magazynu, iProperties hurtem, zerwane wiązania); tryb TEST bez zmian.

**Why:** user pracuje na żywo w Inventorze i czeka; liczy się czas do efektu, nie kompletność analizy.

**How to apply:** przy prośbie o model / element w Inventorze usera:
- jedno zdanie założeń („korek Ø40×20 z parametrów zjazdu, wstawiam przy ramce 1:1, do iam głównego”)
  → od razu budowa → krótki raport; poprawki potem;
- wstawiać do **iam głównego** (aktywne złożenie), nie do podzłożenia generatora — user 07.10: „nie
  wstawiaj bezpośrednio w iam zjazdu tylko w iam główny”;
- nie zapisywać złożenia usera (niezapisane zmiany = jego praca), nową część zapisać obok złożenia;
- przy dłuższej pracy krótki komunikat co robię, nie cisza;
- uprzedzić, gdy coś zablokuje Inventor na dłużej niż kilka sekund („liczę kolizje ~30 s, Inventor nie
  będzie reagował”), a po wstawieniu sprawdzać tylko to, co wstawione (jego położenie / osie z wyniku
  `inventor_zlozenie_wstaw`), nie całe złożenie.

Przepis na korek w zjeździe (gotowiec): środek korka = `Z.stan(segs[0], s)` z toru
(`do_krawedzi` + `sciezka_w` jak `rm_zjazd._konce`), oś korka = góra przekroju `u`, w kanale
zamkniętym D w bok, H wzdłuż `u`, dno kanału = −H/2. Część: okrąg D, wyciągnięcie H, skorupa
z usuniętą górną ścianą. Styk spodu z dnem kolizje pokazują jako ~0,5 mm³ — to leżenie, nie błąd.
Powiązane: [[feedback_nie_zamykaj_okien_usera]].
