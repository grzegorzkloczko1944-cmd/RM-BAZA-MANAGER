// Tryb "katalog" — zrzut całej kartoteki asortymentu do JSON. Tylko odczyt.
//
//   NexoRecon.exe katalog [--out=katalog.json] [konfig.json]
//
// Po co osobny tryb, skoro jest "stan": tryb "stan" pyta punktowo o KONKRETNE
// numery (WyszukajPoSymbolu per symbol) i zwraca stany magazynowe. Tutaj chodzi
// o coś innego — o pełną listę {Symbol, Nazwa} do dopasowania PO NAZWIE po
// stronie Pythona, bo Sfera nie ma zapytania "podobna nazwa" (plan, sekcja
// „Krok 2b"): jest tylko WyszukajPoSymbolu (dokładne) albo Wszystkie() (pełna
// lista). Fuzzy match musi więc liczyć się lokalnie, na ściągniętej liście.
//
// Koszt: jeden przelot po Wszystkie() — ~8 s przy 2745 kartotekach (pomiar
// z sekcji 12). Płacony RAZ na otwarcie okna, nie per pozycja, dlatego wynik
// jest zapisywany do pliku i czytany przez Pythona w całości.
//
// Stanów magazynowych tu NIE ma świadomie — to najdroższa część odczytu
// (StanyMagazynowe per kartoteka), a do szukania duplikatu po nazwie zbędna.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Katalog
{
    /// <summary>
    /// Tryb "kontrahenci" — lista firm z NIP-ami do powiązania z dostawcami
    /// RM_BAZA. Osobno od "katalog", bo tam chodzi o asortyment.
    /// NIP jest kluczem twardym: nazwy pokrywają się tylko w ~55 %
    /// (pomiar 04.09.2026 na 113 dostawcach RM_BAZA).
    /// </summary>
    public static int Kontrahenci(Uchwyt sfera, string? outPath)
    {
        // Podmiot ma NazwaSkrocona (właściwość) i NIP — pobieramy przez Bezp(),
        // bo część pól bywa metodami/rzuca przy pustych danych.
        var firmy = sfera.Podmioty().Dane.WszystkieFirmy().ToList()
            .Select(p => new Kontr(
                p.Id,
                (Bezp(() => p.NazwaSkrocona) ?? "").Trim(),
                (Bezp(() => (string?)p.NIP) ?? "").Replace("-", "").Replace(" ", "").Trim()))
            .Where(k => k.NazwaSkrocona.Length > 0)
            .OrderBy(k => k.NazwaSkrocona, StringComparer.OrdinalIgnoreCase)
            .ToList();

        var json = JsonSerializer.Serialize(new { kontrahenci = firmy },
            new JsonSerializerOptions
            {
                WriteIndented = false,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    internal record Kontr(int Id, string NazwaSkrocona, string NIP);

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    public static int Uruchom(Uchwyt sfera, string? outPath)
    {
        var asort = sfera.Asortymenty();

        // Projekcja na Select PRZED ToList — inaczej materializujemy pełne
        // encje Asortyment (z leniwymi kolekcjami stanów), a potrzebne są
        // trzy pola tekstowe.
        // CenaEwidencyjna dochodzi do projekcji, bo od niej zależy, czy RW
        // policzy koszt materiału (kartoteka bez ceny → pozycja na RW z zerem).
        //
        // Rodzaj doszedł pod okno „Asortyment" (07.09.2026): tam lista ma
        // wyglądać jak w Subiekcie (TW/KT/US), a stany doczytywane są OSOBNO
        // na żądanie — dlatego ich tu dalej nie ma, katalog musi zostać tanim
        // odczytem (~9 s na 3444 kartotekach).
        // Rodzaj idzie przez nawigację W PROJEKCJI, nie po materializacji —
        // sięgnięcie po niego z gotowej encji to zapytanie na kartotekę.
        // Jednostki miary tu nie ma świadomie: okno Asortyment jej nie
        // pokazuje, a każde dodatkowe pole to koszt na całej liście.
        // WKompletach — w ilu kompletach ta kartoteka jest skladnikiem.
        // Potrzebne, zeby okno Asortyment umialo wskazac "duchy": kartoteki
        // bez stanu I nieuzywane nigdzie. Sam zerowy stan nie wystarcza —
        // czesc kupowana pod zamowienie stoi na zerze, a duchem nie jest,
        // bo siedzi w skladzie kompletu (07.09.2026).
        // Relacja odwrotna jest w SDK gotowa (SkladnikiWKompletach, tak samo
        // jak w Komplet.cs), wiec liczymy ja w TEJ SAMEJ projekcji — bez
        // drugiego przelotu po bazie i bez kosztu na kartoteke.
        var pozycje = asort.Dane.Wszystkie()
            .Select(a => new
            {
                a.Id,
                a.Symbol,
                a.Nazwa,
                a.CenaEwidencyjna,
                Rodzaj = a.Rodzaj.Nazwa,
                WKompletach = a.SkladnikiWKompletach.Count(),
            })
            .ToList()
            .Select(a => new Kart(
                a.Id,
                (a.Symbol ?? "").Trim(),
                (a.Nazwa ?? "").Trim(),
                decimal.Round(a.CenaEwidencyjna, 2),
                (a.Rodzaj ?? "").Trim(),
                a.WKompletach))
            .Where(k => k.Symbol.Length > 0)
            .ToList();

        var json = JsonSerializer.Serialize(new { pozycje },
            new JsonSerializerOptions
            {
                WriteIndented = false,   // ~2700 rekordów — plik czyta maszyna, nie człowiek
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });

        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    // Id kartoteki — RM_BAZA pokazuje je obok symbolu, żeby dało się
    // jednoznacznie wskazać pozycję w Subiekcie (symbole bywają zapisane
    // różnie, Id nie).
    internal record Kart(int Id, string Symbol, string Nazwa, decimal CenaEwidencyjna,
                         string Rodzaj, int WKompletach);
}
