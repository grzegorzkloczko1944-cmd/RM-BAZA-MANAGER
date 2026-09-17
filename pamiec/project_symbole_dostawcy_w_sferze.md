---
name: project_symbole_dostawcy_w_sferze
description: Symbol dostawcy -> kartoteka JEST w Sferze (DaneAsortymentuDlaPodmiotu) — nie dorabiać własnej tabeli; pułapki zapisu (Rola, Waluta, kolejność Add)
metadata:
  type: project
---

Ustalone 17.09.2026 przy budowie okna faktur KSeF.

## ⚠️ NIE dorabiać tabeli `mapowania_dostawcow`

Notatka [[project_obieg_przyjec_dostawa_pz]] projektowała własną tabelę
`mapowania_dostawcow (supplier_id, symbol_dostawcy -> asortyment_id)`.
**To było niepotrzebne** — użytkownik słusznie zapytał „po co zakładać coś
takiego, jak to już ma Subiekt".

Sfera ma ten mechanizm wbudowany:

| API | co robi |
|---|---|
| `DaneAsortymentuDlaPodmiotu.Symbol` | „Symbol asortymentu dla powiązanego podmiotu" (1..64 znaki) |
| `DaneAsortymentuDlaPodmiotu.Nazwa` | nazwa towaru u tego dostawcy |
| `IAsortymentyDane.WyszukajPoSymboluDostawcy(symbol, podmiot)` | wyszukuje asortyment po symbolu dostawcy |

Czyli para (dostawca, symbol) → kartoteka JEST w Subiekcie, razem z gotową
wyszukiwarką. Własna tabela powtarzałaby to, co system już prowadzi — ten sam
błąd, przed którym ostrzega sekcja „Subiekt trzyma relacje dokumentów SAM".

**Dodatkowa korzyść:** raz zapisane powiązanie widzi też Subiekt przy zwykłym
wystawianiu dokumentów, nie tylko RM_BAZA.

⚠️ Zostaje natomiast `mapowania` (klucz `numer_rysunku`, 257 wpisów) — to INNA
tożsamość (nasze detale), patrz [[project_polprodukty_do_rysunkow]].

## Tryb `symbole-dostawcy` w moście

`NexoRecon.exe symbole-dostawcy --plan=plan.json [--zapisz]` — wzorzec jak
`dostawcy`: bez `--zapisz` suchy przebieg, raport kroków w JSON.

```json
{"powiazania": [{"nip":"9721002583", "symbolDostawcy":"688 2Z-8x16x5",
                 "symbol":"688 ZZ", "asortymentId":100591,
                 "nazwaUDostawcy":"...", "cenaDeklarowana":4.30}]}
```

## ⚠️ Trzy pułapki zapisu — pierwsza próba padła na 15/15

1. **Kolejność: `Add()` PRZED ustawianiem pól.** Encja niepodpięta do obiektu
   biznesowego rzuca `UnsponsoredModificationException` przy pierwszym
   przypisaniu. Najpierw `kolekcja.Add(new DaneAsortymentuDlaPodmiotu())`,
   dopiero potem `dane.Symbol = ...`.
2. **`Rola` jest WYMAGANA i to `Byte` (maska bitowa), nie enum.** Sfera odrzuca
   `0`, wypisując dozwolone kombinacje (Dostawca / Dostawca+podstawowy /
   Producent / ... / Odbiorca). `Dostawca` = **2**.
3. **`WalutaCenyDeklarowanej` jest wymagana** — bez niej „Nie ustawiono
   powiązanego obiektu". Waluty pobiera się przez `sfera.Waluty()`, która jest
   **metodą ROZSZERZAJĄCĄ** (`InsERT.Moria.Sfera.UchwytRozszerzenia`) — dlatego
   refleksja po samym `Uchwyt` jej NIE widzi (zmyliło diagnostykę o rundę).

⚠️ Kolekcja to zwykłe `ICollection<>` — **nie ma `.Dodaj()`**, jest `.Add()`,
a element tworzy się publicznym konstruktorem domyślnym.

## Pomiar: co dają powiązania (faktura QUAY RVQ/05195/26, 55 pozycji)

Zapisano 15 powiązań na bazie DEMO (M-OLD), ceny wzięte z faktury:

| | kartoteka | brak decyzji | kandydaci |
|---|---:|---:|---:|
| bez powiązań | 6 | 49 | 5 |
| **z powiązaniami** | **17** | **38** | 0 |

Wzrost 6 → 17 i zejście kandydatów niepewnych do zera (mapowanie ma
pierwszeństwo nad normalizacją, więc „kandydat" zamienia się w pewne
trafienie).

⚠️ Na demo **nie było ANI JEDNEGO** powiązania przed tą sesją (0/1620 kartotek)
— mechanizm istnieje, ale nikt go nie wypełniał. **W firmie trzeba to zmierzyć
osobno** (`NexoRecon.exe pz` wypisuje licznik na końcu); jeśli tam też jest
pusto, okno będzie je zapełniać przy każdej decyzji człowieka.

## Jak dobierano pary (żeby nie wpisać bzdury)

Dopasowanie potwierdzane **wymiarem z nazwy kartoteki**, nie podobieństwem
symbolu: faktura `688 2Z-8x16x5` ↔ kartoteka `688 ZZ 8x16x5` (2Z i ZZ to ten
sam typ uszczelnienia). Odrzucone: `UCP 205` → `UCP204` — inny rozmiar
łożyska, czyli błędne powiązanie mimo bliskiego symbolu.

⚠️ To potwierdza regułę z [[project_obieg_przyjec_dostawa_pz]]: **bez fuzzy
match po nazwie**. Trwałe powiązanie = decyzja człowieka.

## Stan

- kod: `subiekt_sfera/NexoRecon/SymboleDostawcy.cs`, tryb zarejestrowany
  w `CommandDispatcher` (Tryby + Zapisujace + switch)
- baza DEMO M-OLD: 15 powiązań QUAY zapisanych i odczytanych z powrotem
- **firma: nie ruszane** — most z tym trybem NIE jest wystawiony na
  `\\W2019S\RM_SERWER$\MOST`

Patrz [[project_ksef_okno_stan_17_09]], [[project_obieg_przyjec_dostawa_pz]],
[[reference_dokumentacja_sfery]].
