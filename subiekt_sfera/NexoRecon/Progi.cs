// Tryb "progi" — STANY MINIMALNY/OPTYMALNY na kartotekach. Czyta i ZAPISUJE.
//
//   NexoRecon.exe progi --out=wynik.json                     (odczyt wszystkich)
//   NexoRecon.exe progi --plan=progi.json --out=w.json --zapisz
//
// Bez --zapisz to suchy przebieg: mówi, co by zrobił, i nic nie zapisuje.
//
// plan.json:
//   [ {"symbol":"011-100.67", "min":10, "opt":25} ]
//
// Po co: magazynier ma domawiać detale NA MAGAZYN, a nie pod konkretne
// zamówienie klienta. Progi są tym, co odróżnia „skończyło się" od „zaraz się
// skończy" — bez nich lista braków musiałaby powstawać z pamięci. Okno
// zamówień czyta je od dawna (Zapotrzebowanie.cs, kolumna Min/Opt), ale
// 05.09.2026 ŻADNA z 3442 kartotek ich nie miała: mechanizm był, danych nie.
// Wpisywanie ich w Subiekcie kartoteka po kartotece odpada, stąd zapis stąd.
//
// ⚠️ Progi są PER MAGAZYN (StanyWMagazynachZakresy), nie na kartotece.
// Odczyt sumuje wszystkie magazyny — firma ma jeden towarowy (MAG), więc
// suma równa się wartości z tego magazynu. Zapis idzie do magazynu wskazanego
// przez --magazyn, a gdy go nie podano — do PIERWSZEGO zakresu kartoteki.
// Kartoteka bez żadnego zakresu jest pomijana z jasnym powodem: zakresu nie
// zakładamy sami, bo to decyzja o tym, w którym magazynie towar ma być
// pilnowany.
//
// ⚠️ StanOptymalny jest nullowalny (decimal?), StanMinimalny nie. Zero
// w minimum znaczy „nie pilnujemy" — i tak właśnie czyści się próg.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Progi
{
    public static int Uruchom(Uchwyt sfera, string? planPath, string? outPath,
                              bool zapisz, string? magazyn)
    {
        var asort = sfera.Asortymenty();

        // ODCZYT — bez planu zwracamy progi wszystkich kartotek, które je mają.
        if (string.IsNullOrWhiteSpace(planPath))
            return Odczyt(asort, outPath);

        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }
        var plan = JsonSerializer.Deserialize<List<Poz>>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true }) ?? new List<Poz>();
        if (plan.Count == 0) { Console.WriteLine("Plan bez pozycji."); return 1; }

        var wszystkie = asort.Dane.Wszystkie().ToList();
        var kroki = new List<Krok>();
        var zmienione = 0;

        foreach (var p in plan)
        {
            var symbol = (p.Symbol ?? "").Trim();
            if (symbol.Length == 0)
            {
                kroki.Add(new Krok(symbol, p.Min, p.Opt, "blad", "pusty symbol"));
                continue;
            }
            var enc = wszystkie.FirstOrDefault(a =>
                (Bezp(() => a.Symbol) ?? "").Trim()
                    .Equals(symbol, StringComparison.OrdinalIgnoreCase));
            if (enc == null)
            {
                kroki.Add(new Krok(symbol, p.Min, p.Opt, "blad", "nie ma takiej kartoteki"));
                continue;
            }
            if (p.Min < 0 || (p.Opt.HasValue && p.Opt.Value < 0))
            {
                kroki.Add(new Krok(symbol, p.Min, p.Opt, "blad", "próg ujemny"));
                continue;
            }
            // Optymalny poniżej minimalnego nie ma sensu: zamówienie
            // uzupełniające wychodziłoby ujemne.
            if (p.Opt.HasValue && p.Opt.Value > 0 && p.Opt.Value < p.Min)
            {
                kroki.Add(new Krok(symbol, p.Min, p.Opt, "blad",
                    $"optymalny ({p.Opt}) poniżej minimalnego ({p.Min})"));
                continue;
            }
            if (!zapisz)
            {
                kroki.Add(new Krok(symbol, p.Min, p.Opt, "do-zmiany", null));
                continue;
            }

            var diag = "";
            var zalozony = false;
            try
            {
                using var ob = asort.Znajdz(enc);
                var zakresy = ob.Dane.StanyWMagazynachZakresy.ToList();
                if (zakresy.Count == 0)
                {
                    // Kartoteka nie ma jeszcze ZAKRESU (to nie to samo co stan:
                    // 794 kartoteki maja stan na MAG, a zakresow nie ma zadna).
                    // Zakres to definicja "pilnuj tego towaru w tym magazynie" —
                    // Subiekt nie zaklada jej sam, wiec zakladamy ja tutaj,
                    // inaczej progu nie ma gdzie zapisac.
                    // ⚠️ ToList() PRZED filtrowaniem: Wszystkie() to zapytanie
                    // LINQ to Entities i Subiekt probuje przetlumaczyc predykat
                    // na SQL — wlasna metoda Bezp() wywala sie wtedy z „does not
                    // recognize the method". Filtrujemy juz w pamieci.
                    var magazyny = sfera.Magazyny().Dane.Wszystkie().ToList();
                    var mag = string.IsNullOrWhiteSpace(magazyn)
                        ? magazyny.FirstOrDefault()
                        : magazyny.FirstOrDefault(m =>
                              (Bezp(() => (string?)m.Symbol) ?? "").Trim()
                                  .Equals(magazyn!.Trim(), StringComparison.OrdinalIgnoreCase));
                    if (mag == null)
                    {
                        kroki.Add(new Krok(symbol, p.Min, p.Opt, "blad",
                            $"nie znaleziono magazynu „{magazyn ?? "(pierwszy)"}”"));
                        continue;
                    }
                    // Dokladnie jak w przykladzie SDK (RealizacjaBase.cs): nowy
                    // obiekt, NAJPIERW Add do kolekcji, DOPIERO POTEM pola.
                    // Wczesniejsza wersja ustawiala Magazyn i Asortyment przed
                    // Add() przez refleksje — Zapisz() zwracal wtedy false bez
                    // zadnego bledu (PodajBledy puste). Kolejnosc ma znaczenie:
                    // Add() wpina encje w kontekst EF i sam ustawia rodzica.
                    try
                    {
                        var stan = new StanWMagazynieZakres();
                        ob.Dane.StanyWMagazynachZakresy.Add(stan);
                        stan.Magazyn = mag;
                        zakresy = ob.Dane.StanyWMagazynachZakresy.ToList();
                        zalozony = true;
                        if (zakresy.Count == 0)
                            throw new InvalidOperationException("kolekcja nadal pusta po Add()");
                    }
                    catch (Exception e)
                    {
                        kroki.Add(new Krok(symbol, p.Min, p.Opt, "blad",
                            $"nie udalo sie zalozyc zakresu magazynowego: {e.Message}"));
                        continue;
                    }
                }
                var cel = zakresy[0];
                if (!string.IsNullOrWhiteSpace(magazyn))
                {
                    var wskazany = zakresy.FirstOrDefault(z =>
                        (Bezp(() => z.Magazyn?.Symbol) ?? "").Trim()
                            .Equals(magazyn!.Trim(), StringComparison.OrdinalIgnoreCase));
                    if (wskazany == null)
                    {
                        kroki.Add(new Krok(symbol, p.Min, p.Opt, "blad",
                            $"kartoteka nie ma zakresu dla magazynu „{magazyn}”"));
                        continue;
                    }
                    cel = wskazany;
                }
                diag = $"mag={Bezp(() => (string?)cel.Magazyn?.Symbol) ?? "(null)"} " +
                       $"zakresow={zakresy.Count} nowy={(zalozony ? "tak" : "nie")}";
                cel.StanMinimalny = p.Min;
                // 0 w optymalnym czyścimy do null — „brak" i „zero" to co
                // innego, a Subiekt trzyma to pole jako nullowalne.
                cel.StanOptymalny = (p.Opt.HasValue && p.Opt.Value > 0) ? p.Opt : null;

                if (ob.Zapisz())
                {
                    zmienione++;
                    // Weryfikacja: otwieramy kartoteke na nowo i czytamy progi.
                    // Zapisz()==true nie musi znaczyc, ze zakres sie utrwalil.
                    string wer;
                    try
                    {
                        using var ob2 = asort.Znajdz(enc);
                        var z2 = ob2.Dane.StanyWMagazynachZakresy.ToList();
                        wer = z2.Count == 0 ? "PO ZAPISIE BRAK ZAKRESU"
                            : $"odczyt: min={z2[0].StanMinimalny} opt={z2[0].StanOptymalny}";
                    }
                    catch (Exception e) { wer = "weryfikacja: " + e.Message; }
                    kroki.Add(new Krok(symbol, p.Min, p.Opt, "zmieniono",
                        $"{Bezp(() => cel.Magazyn?.Symbol)} | zakres {(zalozony ? "NOWY" : "istniejacy")} | {wer}"));
                }
                else
                {
                    // PodajBledy() mowi, CO odrzucil Subiekt — samo „false" nic
                    // nie tlumaczy (wzorem Kartoteka.cs / Projekt.cs).
                    kroki.Add(new Krok(symbol, p.Min, p.Opt, "blad",
                        (Bezp(ob.PodajBledy) ?? "Zapisz() zwrocil false bez podania bledow") + " | " + diag));
                }
            }
            catch (Exception e)
            {
                kroki.Add(new Krok(symbol, p.Min, p.Opt, "blad", e.Message));
            }
        }

        Wypisz(new { zmienione, kroki }, outPath);
        return 0;
    }

    static int Odczyt(dynamic asort, string? outPath)
    {
        // Wzorem Magazyn.cs: projekcja symboli PRZED ToList, potem
        // WyszukajPoSymbolu per kartoteka. Encje z Wszystkie() NIE doladowuja
        // kolekcji zakresow (po udanym zapisie odczyt pokazywal "brak progu"),
        // a te z WyszukajPoSymbolu — tak. ~10 s na 3442 kartoteki.
        var pozycje = new List<Odczytana>();
        IEnumerable<object> symbole = ((IEnumerable<dynamic>)asort.Dane.Wszystkie())
            .Select(a => (object)new { Symbol = (string?)a.Symbol, Nazwa = (string?)a.Nazwa })
            .ToList();
        foreach (dynamic k in symbole)
        {
            var symbol = ((string?)k.Symbol ?? "").Trim();
            if (symbol.Length == 0) continue;
            dynamic? enc = null;
            try { enc = asort.Dane.WyszukajPoSymbolu(symbol); } catch { }
            if (enc == null) continue;
            decimal min = 0, opt = 0;
            var ma = false;
            try
            {
                foreach (var z in enc.StanyWMagazynachZakresy)
                {
                    min += (decimal)z.StanMinimalny;
                    opt += (decimal)(z.StanOptymalny ?? 0m);
                    ma = true;
                }
            }
            catch { /* kartoteka bez zakresow — progow nie ma */ }
            // Zwracamy TYLKO te z ustawionym progiem: 3442 kartoteki z zerami
            // to same smieci w JSON-ie, a okno i tak czyta stany osobno.
            if (ma && (min > 0 || opt > 0))
                pozycje.Add(new Odczytana(symbol, (string?)k.Nazwa ?? "", min, opt));
        }
        Wypisz(new { pozycje }, outPath);
        return 0;
    }

    static void Wypisz(object dane, string? outPath)
    {
        var json = JsonSerializer.Serialize(dane, new JsonSerializerOptions
        {
            WriteIndented = false,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
        });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record Poz(string? Symbol, decimal Min, decimal? Opt);
    internal record Krok(string Symbol, decimal Min, decimal? Opt, string Status, string? Szczegoly);
    internal record Odczytana(string Symbol, string Nazwa, decimal Min, decimal Opt);
}
