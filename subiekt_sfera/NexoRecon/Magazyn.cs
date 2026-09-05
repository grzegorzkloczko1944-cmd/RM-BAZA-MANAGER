// Tryb "magazyn" — stany CAŁEGO magazynu Subiekta. Tylko odczyt.
//
//   NexoRecon.exe magazyn [--tylko-niezerowe] [--out=magazyn.json] [konfig.json]
//
// Czym się różni od pozostałych trybów odczytu:
//
//   stan     — pyta punktowo o KONKRETNE symbole (--symbols-file), zwraca też
//              ostatnią cenę zakupu i datę przyjęcia. Używane pod projekt:
//              „czy mam na stanie to, czego potrzebuję do tego BOM-u".
//   katalog  — pełna lista {Symbol, Nazwa} BEZ stanów, do dopasowania po
//              nazwie. Stany pominięte świadomie, bo są najdroższe.
//   magazyn  — TU: pełna lista ZE stanami. „Co w ogóle mam na magazynie",
//              niezależnie od jakiegokolwiek projektu.
//
// Koszt: StanyMagazynowe czytane per kartoteka to najdroższa część odczytu
// (dlatego nie ma ich w trybie „katalog"). Przy ~2700 kartotekach liczyć
// należy kilkadziesiąt sekund. Dlatego:
//   * historii zakupów (FZ) tu NIE MA — to drugi kosztowny przelot, a do
//     pytania „ile mam" niepotrzebny; od tego jest tryb „stan",
//   * --tylko-niezerowe pomija kartoteki bez ruchu, co przy magazynie
//     z długim ogonem martwych indeksów skraca wynik i czas.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Magazyn
{
    public static int Uruchom(Uchwyt sfera, string? outPath, bool tylkoNiezerowe)
    {
        var asort = sfera.Asortymenty();

        // Projekcja PRZED ToList — jak w Katalog.cs. Materializacja pełnych
        // encji ciągnęłaby leniwe kolekcje, których tu nie potrzebujemy.
        var kartoteki = asort.Dane.Wszystkie()
            .Select(a => new { a.Id, a.Symbol, a.Nazwa, a.CenaEwidencyjna })
            .ToList();

        var wynik = new List<Poz>();
        foreach (var k in kartoteki)
        {
            var symbol = (k.Symbol ?? "").Trim();
            if (symbol.Length == 0) continue;

            var enc = Bezp(() => asort.Dane.WyszukajPoSymbolu(symbol));
            if (enc == null) continue;

            var stany = new List<StanMag>();
            decimal dostepne = 0, zadysponowane = 0, zarezerwowane = 0;
            try
            {
                foreach (var s in enc.StanyMagazynowe)
                {
                    var mag = BezpS(() => s.Magazyn?.Symbol) ?? "?";
                    stany.Add(new StanMag(mag, s.IloscDostepna, s.IloscZadysponowana));
                    dostepne += s.IloscDostepna;
                    zadysponowane += s.IloscZadysponowana;
                    zarezerwowane += s.IloscZarezerwowanaIlosciowo
                                   + s.IloscZarezerwowanaDostawowo;
                }
            }
            catch { /* brak stanów = kartoteka bez ruchu */ }

            // Kartoteki bez ruchu to zwykle martwe indeksy — przy przeglądzie
            // magazynu tylko zaśmiecają listę.
            if (tylkoNiezerowe && dostepne == 0 && zadysponowane == 0) continue;

            wynik.Add(new Poz(
                k.Id, symbol, (k.Nazwa ?? "").Trim(),
                BezpS(() => enc.Rodzaj?.Nazwa),
                dostepne, zadysponowane, zarezerwowane,
                decimal.Round(k.CenaEwidencyjna, 2),
                stany));
        }

        var json = JsonSerializer.Serialize(new { pozycje = wynik },
            new JsonSerializerOptions
            {
                WriteIndented = false,   // kilka tysięcy rekordów — czyta maszyna
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    static T? Bezp<T>(Func<T?> f) where T : class { try { return f(); } catch { return null; } }
    static string? BezpS(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record StanMag(string Magazyn, decimal Dostepne, decimal Zadysponowane);

    // Jednostki miary tu nie ma — Asortyment nie wystawia jej wprost, a do
    // pytania „ile mam na stanie" nie jest konieczna (tryb „stan" też jej
    // nie zwraca).
    internal record Poz(int Id, string Symbol, string Nazwa, string? Rodzaj,
                        decimal Dostepne, decimal Zadysponowane, decimal Zarezerwowane,
                        decimal CenaEwidencyjna, List<StanMag> Magazyny);
}
