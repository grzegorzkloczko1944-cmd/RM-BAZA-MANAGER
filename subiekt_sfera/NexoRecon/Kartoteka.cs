// Tryb "kartoteka" — zakłada JEDNĄ kartotekę asortymentu ręcznie. ZAPISUJE.
//
//   NexoRecon.exe kartoteka --plan=k.json [--out=w.json] [--zapisz]
//
// Bez --zapisz suchy przebieg: sprawdza, czy symbol wolny, nic nie zapisuje.
//
// plan.json:
//   { "symbol":"DIN 912 M6x20", "nazwa":"Śruba imbusowa M6x20",
//     "rodzaj":"towar",            // towar | usluga | komplet
//     "jm":"szt", "cena": 0.45, "opis":"..." }
//
// Po co osobny tryb, skoro "projekt" zakłada kartoteki: tamten idzie z BOM-u
// i zakłada seriami. Ten służy do ręcznego dorzucenia pozycji, której w BOM-ie
// nie ma (śruby, materiał pomocniczy, usługa) — z dowolnego okna RM_BAZA.
// Ten sam wzorzec zakładania (szablon → symbol → nazwa → Zapisz), żeby
// kartoteki ręczne niczym nie różniły się od tych z projektu.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Kartoteka
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }
        var p = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;

        var symbol = (p.Symbol ?? "").Trim();
        var nazwa = (p.Nazwa ?? "").Trim();
        if (symbol.Length == 0) return Wynik(outPath, "blad", "pusty symbol", null);
        if (nazwa.Length == 0) nazwa = symbol;

        var asort = sfera.Asortymenty();

        // Istnieje już? Dopasowanie luźne jak wszędzie (TRIM, wielkość liter).
        var istn = asort.Dane.WyszukajPoSymbolu(symbol);
        if (istn == null)
        {
            var luzne = asort.Dane.Wszystkie().Select(a => a.Symbol).ToList()
                .FirstOrDefault(s => string.Equals((s ?? "").Trim(), symbol, StringComparison.OrdinalIgnoreCase));
            if (luzne != null) istn = asort.Dane.WyszukajPoSymbolu(luzne);
        }
        if (istn != null)
            return Wynik(outPath, "istnieje", $"kartoteka „{istn.Symbol}” już jest: {istn.Nazwa}", istn.Symbol?.Trim());

        if (!zapisz) return Wynik(outPath, "do-zalozenia", $"{p.Rodzaj ?? "towar"}, jm {p.Jm ?? "szt"}", symbol);

        try
        {
            var szablony = sfera.PodajObiektTypu<InsERT.Moria.Asortymenty.ISzablonyAsortymentu>();
            using var ob = asort.Utworz();
            var rodzaj = (p.Rodzaj ?? "towar").Trim().ToLowerInvariant();
            // Szablon decyduje o rodzaju — bez niego brakuje domyślnej jednostki
            // miary (ta sama pułapka co w Projekt.cs).
            ob.WypelnijNaPodstawieSzablonu(rodzaj switch
            {
                "usluga" => szablony.DaneDomyslne.Usluga,
                "komplet" => szablony.DaneDomyslne.Komplet,
                _ => szablony.DaneDomyslne.Towar,
            });
            ob.Dane.Symbol = symbol;
            ob.Dane.Nazwa = nazwa;
            if (!string.IsNullOrWhiteSpace(p.Opis))
                try { ob.Dane.Opis = p.Opis!.Trim(); } catch { }
            if (p.Cena is > 0)
                try { ob.Dane.CenaEwidencyjna = p.Cena.Value; } catch { }

            if (!ob.Zapisz())
                return Wynik(outPath, "blad", Bezp(ob.PodajBledy) ?? "Zapisz() = false", symbol);
            return Wynik(outPath, "zalozona", $"{rodzaj}: {nazwa}", symbol);
        }
        catch (Exception ex)
        {
            return Wynik(outPath, "blad", $"{ex.GetType().Name}: {ex.Message}", symbol);
        }
    }

    static int Wynik(string? outPath, string status, string? szczegoly, string? symbol)
    {
        var json = JsonSerializer.Serialize(new { status, szczegoly, symbol },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record Plan(string? Symbol, string? Nazwa, string? Rodzaj, string? Jm,
                         decimal? Cena, string? Opis);
}
