// Tryb "komplet" — co komplet ZAWIERA i W CZYM SAM SIEDZI. Tylko odczyt.
//
//   NexoRecon.exe komplet --symbol=2632-350.24ZZ [--out=wynik.json] [konfig.json]
//
// Powstal, zeby odpowiedziec na konkretna obawe (06.09.2026): czy komplety
// zalozone przez tryb "projekt" naprawde maja skladniki i czy sa wpiete
// w komplet nadrzedny, czy "wisza w powietrzu". Bez tego dalo sie sprawdzic
// tylko rodzaj kartoteki (Komplet/Towar), a to nie mowi nic o powiazaniach.
//
// Dla kazdego pytanego symbolu zwraca:
//   * Rodzaj kartoteki (Towar / Komplet / Usluga),
//   * Skladniki — co wchodzi w jego sklad (symbol, nazwa, ilosc, rodzaj),
//   * WchodziW — komplety, w ktorych skladzie ten symbol wystepuje.
//
// WchodziW liczymy przelotem po WSZYSTKICH kompletach w bazie (jest ich
// ~150), bo Sfera nie daje relacji odwrotnej wprost.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Komplet
{
    public static int Uruchom(Uchwyt sfera, List<string> symbole, string? outPath)
    {
        var asort = sfera.Asortymenty();

        // JEDNA PROJEKCJA, bez przelotu po calej bazie na relacje odwrotna:
        // Sfera ma ja gotowa jako SkladnikiWKompletach (patrz
        // InsERT.Moria.ModelDanych.XML — Asortyment.SkladnikiKompletu
        // i .SkladnikiWKompletach). Element obu kolekcji to SkladnikKompletu
        // z polami Komplet, Skladnik, Ilosc.
        var wszystkie = asort.Dane.Wszystkie()
            .Select(a => new
            {
                a.Symbol,
                a.Nazwa,
                Rodzaj = a.Rodzaj.Nazwa,
                Sklad = a.SkladnikiKompletu.Select(s => new
                {
                    Symbol = s.Skladnik.Symbol,
                    Nazwa = s.Skladnik.Nazwa,
                    RodzajSkl = s.Skladnik.Rodzaj.Nazwa,
                    s.Ilosc,
                }),
                Nadrzedne = a.SkladnikiWKompletach.Select(s => new
                {
                    Symbol = s.Komplet.Symbol,
                    Nazwa = s.Komplet.Nazwa,
                    RodzajNad = s.Komplet.Rodzaj.Nazwa,
                    s.Ilosc,
                }),
            })
            .ToList();

        var luzne = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var a in wszystkie)
        {
            var k = (a.Symbol ?? "").Trim();
            if (k.Length > 0) luzne[k] = a.Symbol!;
        }

        var wynik = new List<Poz>();
        foreach (var pytany in symbole)
        {
            var szukany = (pytany ?? "").Trim();
            if (szukany.Length == 0) continue;
            var dopasowany = luzne.TryGetValue(szukany, out var d) ? d : null;
            var enc = dopasowany == null
                ? null
                : wszystkie.FirstOrDefault(a => a.Symbol == dopasowany);

            if (enc == null)
            {
                wynik.Add(new Poz(szukany, null, false, "", new List<Skladnik>(),
                                  new List<Nadrzedny>()));
                continue;
            }

            var skladniki = enc.Sklad
                .Select(s => new Skladnik((s.Symbol ?? "").Trim(), s.Nazwa ?? "",
                                          s.RodzajSkl ?? "", s.Ilosc))
                .ToList();
            var nadrzedne = enc.Nadrzedne
                .Select(s => new Nadrzedny((s.Symbol ?? "").Trim(), s.Nazwa ?? "",
                                           s.RodzajNad ?? "", s.Ilosc))
                .ToList();

            wynik.Add(new Poz(szukany, (enc.Symbol ?? "").Trim(), true,
                              enc.Rodzaj ?? "", skladniki, nadrzedne));
        }

        var json = JsonSerializer.Serialize(new { pozycje = wynik },
            new JsonSerializerOptions
            {
                WriteIndented = false,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    internal record Skladnik(string Symbol, string Nazwa, string Rodzaj, decimal Ilosc);
    internal record Nadrzedny(string Symbol, string Nazwa, string Rodzaj, decimal Ilosc);
    internal record Poz(string Pytany, string? Symbol, bool Istnieje, string Rodzaj,
                        List<Skladnik> Skladniki, List<Nadrzedny> WchodziW);
}
