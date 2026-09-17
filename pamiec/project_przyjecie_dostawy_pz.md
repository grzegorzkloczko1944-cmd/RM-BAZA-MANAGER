---
name: project_przyjecie_dostawy_pz
description: Okno „Przyjęcie dostawy" (kafel 📦) — DOSTAWA → PZ w Subiekcie, ZBUDOWANE 18.09.2026; PZ realizuje ZD przez WypelnijNaPodstawieZD; pułapki Sfery (IloscDoRealizacji.PozostalaIlosc, dynamic Utworz, snake_case w planie)
metadata:
  type: project
---

Punkt 2 planu z [[project_obieg_przyjec_dostawa_pz]] — zrobiony 18.09.2026,
przetestowany na demo M-OLD (DOSTAWA 1 → `PZ 1/MASTER/2026`).

## Po co

Towar wchodzi na stan, gdy PRZYJDZIE, nie gdy przyjdzie faktura. Pytanie
użytkownika (18.09.2026): „jak przyjmować dostawy, gdy nie ma faktury,
a przyszedł towar z WZ?" — odpowiedź: to jest GŁÓWNA ścieżka, faktura
przychodzi później i tylko kontroluje (okno Faktury z KSeF dopina ją po WZ).

## Co to jest

`subiekt_dostawa_gui.py` — kafel „📦 Przyjęcie dostawy" (nieodwracalny) →
`RM_BAZA.open_subiekt_dostawa()`. Szata jak okno dokumentów.

Dwa źródła pozycji w jednym oknie (decyzja użytkownika: „oba"):
* **otwarte ZD dostawcy** — lista pozycji z `do_realizacji > 0`, zaznaczasz
  co przyszło, ilość domyślnie = do realizacji, edycja dwuklikiem w arkuszu;
* **spoza ZD** — z kartoteki (dostawca dołożył coś ekstra).

Nagłówek: dostawca (kontrahent Subiekta; ci z otwartymi ZD oznaczeni),
data przyjęcia (fizyczna, idzie na PZ), magazyn (domyślnie z ZD dostawcy),
WZ / nr zamówienia / identyfikator własny — **żaden nie jest wymagany**,
ale bez któregoś faktura nie znajdzie przyjęcia (okno ostrzega).

## Gdzie co się zapisuje — i w jakiej KOLEJNOŚCI

1. suchy przebieg `pz-utworz` (Subiekt sprawdza ZD, pozycje, kartoteki) — błąd = nic nie zapisano
2. `dostawy` + `dostawy_pozycje` na masterze (status `PRZYJMOWANA`)
3. most `pz-utworz --zapisz` → PZ w Subiekcie
4. `dostawa-pz-ustaw`: `pz_numer`, `pz_id`, status `PZ` albo `BLAD_PZ`

Kolejność celowa: DOSTAWA przed PZ, żeby przy odrzuceniu PZ nic nie zginęło —
dostawa zostaje w historii z `BLAD_PZ`, przycisk „Ponów PZ" próbuje jeszcze
raz z tych samych pozycji. Odwrotnie (PZ bez dostawy) nie da się domknąć.

Uproszczenie względem notatki o obiegu: **bez tabeli `dostawa_zd_pozycje`**
(wiele-do-wielu). Linia dostawy niesie `zd_id` + `zd_pozycja_id` wprost —
100 szt. przychodzące 40+35+25 to trzy dostawy, każda z własną linią.

## ⚠️ PZ MUSI powstać przez WypelnijNaPodstawieZD — nie Pozycje.Dodaj

Ta sama lekcja co w `Zd.cs` (ZD przez `UtworzNaPodstawieZapotrzebowania`):

```
IPrzyjecieZewnetrzne.WypelnijNaPodstawieZD(IEnumerable<PozycjaDokumentu>, DokumentZD)
  „Dodaje podane pozycje ZD na dokument przyjęcia jako realizacje;
   dokumentZDGlowny — ZD, z którego przepisany będzie podmiot."
```

Dzięki temu Subiekt sam trzyma relację ZD↔PZ (`Realizuje`) i realizację
częściową: po przyjęciu 3 z 8 `PozostalaIlosc` ZD spadło na 5 — kolejna
dostawa widzi resztę bez żadnej tabeli w RM_BAZA. Pozycje z kilku ZD
tego samego dostawcy idą jednym wywołaniem; ilość mniejsza od zamówionej
ustawiana po fakcie (`poz.Ilosc = x` na zwróconych pozycjach).

Pozycje spoza ZD — `Pozycje.Dodaj` + cena jak w `Pw.cs`. Dostawa bez ZD —
podmiot po NIP. WZ dostawcy → `NumerZewnetrzny` (to pole czyta tryb `pz`
i po nim faktura dopina się do przyjęcia). Uwagi: `DOSTAWA <id> WZ <nr>`.

## Tryb `dokumenty` zwraca teraz Id pozycji i ilość do realizacji

`Dokumenty.cs`: `PozDok` dostał na KOŃCU `Id` i `DoRealizacji` (tylko ZD);
Python `_przelicz_dokumenty` → `"id"`, `"do_realizacji"`. GUI wskazuje Sferze
pozycje po Id, nie po symbolu. Stare mosty → 0 (nic się nie wywala).

## ⚠️ Pułapki Sfery i C#, które kosztowały rundy (18.09.2026)

1. **`PozycjaDokumentu.IloscDoRealizacji` to OBIEKT, nie decimal** (jak
   `Cena`) — liczba siedzi w `.PozostalaIlosc`. Rzutowanie na decimal =
   CS0030. Czytać PO materializacji (nie w projekcji EF), bo gdyby Sfera
   liczyła to pole, nieprzetłumaczalne wyrażenie wywaliłoby cały tryb.
2. **`Utworz(konfig)` z argumentem `dynamic` zwraca `dynamic`** — wtedy
   lambda w `WypelnijNaPodstawieZD` nie kompiluje się (CS1977). Rzutować
   konfigurację na `Konfiguracja` i deklarować `IPrzyjecieZewnetrzne pz`.
   `Pw.cs` tego nie zauważył, bo używa tylko `Dodaj()`.
3. **`PropertyNameCaseInsensitive` NIE łączy `zd_pozycje` z `ZdPozycje`**
   (podkreślenia). Bez `[JsonPropertyName]` lista ZD była pusta i suchy
   przebieg **pomijał realizację PO CICHU** — żadnego błędu, tylko brak
   kroków `zd-pozycja`. Rekordy planu mają jawne nazwy snake_case.
4. Polski cudzysłów `„…"` zamknięty prostym `"` wewnątrz f-stringa =
   SyntaxError; zamykać `”`.
5. Restart lokalnego serwera na M-OLD **zamyka RM_BAZA** — potwierdzone
   drugi raz; pytać przed restartem, potem odpalić ponownie.

## Test (harness `scratchpad/test_dostawa.py`, z `--zapisz` = prawdziwe PZ na demo)

QUAY, `2602-100.42X` 3 z 8 z ZD 2 + `688 ZZ` ×2 spoza ZD → DOSTAWA 1,
`PZ 1/MASTER/2026`, `Realizuje = ZD 2/CENTRALA/2026`, `NumerZewnetrzny =
WZ/TEST/01`, 2 pozycje, ZD 2 do realizacji 8 → 5. Historia pokazuje status
`PZ`. 9 sprawdzeń, 0 błędów.

NIE testowane: dostawa bez ZD (podmiot po NIP), „Ponów PZ" po BLAD_PZ,
nadwyżka ponad zamówienie (czy Subiekt odmówi — krok „uwaga" to sygnalizuje).

## Stan wdrożenia

* git `main`: kod; most zbudowany lokalnie, **NIE wystawiony** na
  `\\W2019S\RM_SERWER$\MOST`
* serwer: `MIGRACJE_DOSTAWY` (tabele `dostawy`, `dostawy_pozycje`) +
  operacje `dostawy-*` / `dostawa-*` — **wdrażać `rm_serwer.py` i
  `rm_serwer_operacje.py` RAZEM**, restart obowiązkowy (nowe operacje)
* następne z planu: 3. powiązanie z ZD — ZROBIONE PRZY OKAZJI (Subiekt),
  4. PZ — ZROBIONE, 5. rozliczanie faktury względem PZ (po WZ) — do zrobienia

Patrz [[project_obieg_przyjec_dostawa_pz]], [[project_ksef_okno_faktur_wdrozone]],
[[project_symbole_dostawcy_w_sferze]].
