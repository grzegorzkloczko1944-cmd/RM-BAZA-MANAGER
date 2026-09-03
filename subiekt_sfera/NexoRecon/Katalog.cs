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
    public static int Uruchom(Uchwyt sfera, string? outPath)
    {
        var asort = sfera.Asortymenty();

        // Projekcja na Select PRZED ToList — inaczej materializujemy pełne
        // encje Asortyment (z leniwymi kolekcjami stanów), a potrzebne są
        // trzy pola tekstowe.
        var pozycje = asort.Dane.Wszystkie()
            .Select(a => new { a.Symbol, a.Nazwa })
            .ToList()
            .Select(a => new Kart(
                (a.Symbol ?? "").Trim(),
                (a.Nazwa ?? "").Trim()))
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

    internal record Kart(string Symbol, string Nazwa);
}
