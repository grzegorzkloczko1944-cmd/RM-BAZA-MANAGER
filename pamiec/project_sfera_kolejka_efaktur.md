---
name: project_sfera_kolejka_efaktur
description: "Sfera UDOSTEPNIA kolejke e-Faktur KSeF (modul Odbior) przez DokumentyElektroniczne() — osobna kartoteka, nie DokumentyZakupu; ze statusem zakladek i flagami"
metadata:
  node_type: memory
  type: project
---

**Kolejka e-Faktur z modulu „KSeF → Odbior" JEST dostepna ze Sfery** — ustalone
18.09.2026, zweryfikowane w dokumentacji NA DYSKU i w binarce SDK.

⚠️ To **osobna kartoteka**, NIE `sfera.DokumentyZakupu()`. Tamto zwraca tylko
FZ juz istniejace; faktury z zakladki „DO PRZETWORZENIA" nie sa jeszcze
dokumentami Subiekta i tamtedy ich NIE WIDAC (nasz tryb `faktury` w Faktury.cs
czyta wlasnie DokumentyZakupu — stad ograniczenie).

| co | jak |
|---|---|
| kartoteka | `sfera.DokumentyElektroniczne()` → `IDokumentyElektroniczne` |
| encja | `InsERT.Moria.ModelDanych.DokumentElektroniczny` |
| odczyt | `.Dane.Wszystkie(...)` → `IQueryable`, filtrowalne LINQ-iem |
| pobieranie z KSeF | `sfera.KoordynatorOdbioruEFaktur()` |
| e-Faktura → FZ | `dokumentZakupu.ObslugaImportuEFaktur.WypelnijNaPodstawieDokumentuElektronicznego(de)` |

**Pola:** `NumerKSeF`, `NumerDokumentu`, `DataWystawienia`, `NazwaKlienta`,
`NIPSprzedawcy`, `Wartosc` (decimal), `StatusPrzetworzenia` (byte),
`Rodzaj`, `Xml` (pelna tresc), `DokumentPowiazanyId` (utworzona FZ).

**`StatusPrzetworzeniaEFaktury` = 1:1 zakladki modulu Odbior:**
1 `DoPrzetworzeniaWKsiegowosci`, 2 `DoPrzetworzeniaWSubiekcie` (DO PRZETWORZENIA),
3 `Przetworzona`, 4 `PrzetworzonaRecznie`, 5 `Nieokreslony`, 6 `Odrzucona`.
Zapis: `UstawStatusPrzetworzenia(...)`.

**Flaga (kolorowa gwiazdka z kolumny „Flaga")** — czytelna i zapisywalna:
`FlagaWlasna` (`Kolor` RGB, `Ksztalt`, `Domena`) + `FlagHeader.Description`
(opis nadany przez uzytkownika). ⚠️ To wlasciwosci NAWIGACYJNE — moga byc null
i wymagac eager loadingu; w projekcji brac wprost `FlagaWlasna.Kolor` itd.
Flagi w nexo sa konfigurowalne przez uzytkownika, wiec znaczenie koloru
czytac z `FlagHeader.Description`, NIE zakladac z gory.

## Pozycje faktury z kolejki (18.09.2026)

⛔ **`DokumentElektroniczny.Xml` (byte[], „Tresc dokumentu") JEST NIECZYTELNY
wprost.** Nie jest to UTF-8 ani gzip/zlib/raw deflate — 1576 bajtow szumu
o wysokiej entropii na cala fakture. Proba zdekodowania go jako string psuje
bajty nieodwracalnie (C# GetString gubi dane, base64 pokazal prawdziwa
zawartosc). Encja NIE MA tez zadnej wlasciwosci z pozycjami.

✅ **Wlasciwa droga:** `IDokumentyElektroniczne.PobierzDane(dokument)` zwraca
`IDaneEFaktury` z gotowymi, rozkodowanymi danymi:

| co | gdzie |
|---|---|
| pozycje | `Wiersze` → `IEnumerable<IDaneWierszaFaktury>` |
| pola wiersza | `LP` (**STRING**, moze byc „1.1"), `NazwaTowaru`, `Indeks`, `JednostkaMiary`, `Ilosc` (decimal), `CenaNetto`/`WartoscNetto` (**decimal?**) |
| numery WZ | `WydaniaZewnetrzne` — klucz do zestawienia z PZ ([[project_rozliczanie_faktury_z_pz_plan]]) |
| numery zamowien | `NumeryZamowien` |
| naglowek | `NumerFaktury`, `DataWystawienia`, `KwotaDoZaplaty`, `DaneSprzedawcy`, `TabelaVAT` |

⚠️ Typy sa niespojne: `Ilosc` to `decimal`, ale ceny `decimal?` — potrzebne
dwa helpery (`Kwota` / `KwotaN`), inaczej kompilator odbija kazde uzycie.

Sprawdzone na produkcji: 16/16 faktur „do przetworzenia" ma pozycje (42 razem),
z nazwami, jednostkami i cenami; transport jako osobna linia; numery WZ
przychodza (np. Neumo: szesc numerow na jednej fakturze).

**How to apply:**
- Most tego jeszcze NIE UZYWA — do zrobienia nowy tryb CLI (np. `efaktury`)
  obok istniejacego `faktury`. Dopiero wtedy okno faktur dostanie trzeci tryb
  „nieprzetworzone w Subiekcie" ([[project_ksef_okno_zrodla_przelacznik]]).
- Dowody: `C:/iLogic/Subiekt_nexo_PRO_dokumentacja/CHM/sfera/html/`
  — `8a1d7711-a5aa-48a6-b55d-cf23954336d1.htm` (przyklady KSeF, gotowy kod
  filtrujacy DO PRZETWORZENIA), `210C227A.htm` (pola), `7224E8A2.htm` (enum),
  `5BBE28E7.htm` (interfejs). Indeks calej dokumentacji:
  `CHM/sfera_index.tsv` (81 984 wpisow) — uzywac go do dalszych poszukiwan.
- Typy potwierdzone w `C:/iLogic/Subiekt/Bin/InsERT.Moria.API.dll` (SDK 61.1.0.9431).

Patrz [[project_subiekt_nexo_sfera]], [[project_ksef_okno_faktur_wdrozone]].
