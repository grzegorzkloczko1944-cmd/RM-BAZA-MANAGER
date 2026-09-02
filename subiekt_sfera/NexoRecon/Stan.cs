// Tryb "stan" — wyjście MASZYNOWE (JSON) dla RM_BAZA. Tylko odczyt.
//
//   NexoRecon.exe stan --symbols-file=lista.txt [--out=wynik.json] [konfig.json]
//   NexoRecon.exe stan --symbol=013-100.22X --symbol=8043214
//
// Zwraca dla każdego pytanego numeru rysunku: czy jest kartoteka, stany per
// magazyn, ostatnią cenę zakupu (z FZ) i datę ostatniego przyjęcia.
//
// Dopasowanie symbolu — zgodnie z ustaleniami z rozpoznania (plan, sekcja 12.2):
// dokładnie, a jeśli nie ma, to po TRIM + bez rozróżniania wielkości liter
// (w bazie są symbole ze spacją na końcu i różnicą a/A).

using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Stan
{
    public static int Uruchom(Uchwyt sfera, List<string> symbole, string? outPath)
    {
        var asort = sfera.Asortymenty();

        // Jeden przelot po kartotekach — mapa do dopasowania luźnego.
        // 2745 kartotek, więc trzymanie tego w pamięci jest bez znaczenia,
        // a oszczędza zapytanie na każdy pytany symbol.
        var wszystkie = asort.Dane.Wszystkie().Select(a => new { a.Id, a.Symbol }).ToList();
        var luzne = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var a in wszystkie)
        {
            var k = (a.Symbol ?? "").Trim();
            if (k.Length > 0) luzne[k] = a.Symbol!;   // ostatni wygrywa, wystarczy
        }

        var wynik = new List<Poz>();
        foreach (var pytany in symbole)
        {
            var szukany = (pytany ?? "").Trim();
            if (szukany.Length == 0) continue;

            var enc = asort.Dane.WyszukajPoSymbolu(szukany);
            var dopasowanie = "dokladne";
            if (enc == null && luzne.TryGetValue(szukany, out var realny))
            {
                enc = asort.Dane.WyszukajPoSymbolu(realny);
                dopasowanie = "luzne";
            }
            if (enc == null)
            {
                wynik.Add(new Poz(pytany!, null, false, null, null, 0, 0, null, null, new List<StanMag>()));
                continue;
            }

            var stany = new List<StanMag>();
            decimal dostepne = 0, zadysponowane = 0;
            try
            {
                foreach (var s in enc.StanyMagazynowe)
                {
                    var mag = Bezp(() => s.Magazyn?.Symbol) ?? "?";
                    stany.Add(new StanMag(mag, s.IloscDostepna, s.IloscZadysponowana,
                                          s.IloscZarezerwowanaIlosciowo, s.IloscZarezerwowanaDostawowo));
                    dostepne += s.IloscDostepna;
                    zadysponowane += s.IloscZadysponowana;
                }
            }
            catch { /* brak stanów = kartoteka bez ruchu */ }

            // Ostatni zakup: pozycje dokumentów zakupu tej kartoteki.
            decimal? ostCena = null; string? ostData = null;
            try
            {
                var poz = enc.PozycjeDokumentu
                    .Where(p => p.Dokument != null && p.Dokument.Symbol == "FZ" && p.Ilosc > 0)
                    .OrderByDescending(p => p.Dokument.DataWprowadzenia)
                    .Take(1).ToList();
                if (poz.Count > 0)
                {
                    var p = poz[0];
                    ostData = p.Dokument.DataWprowadzenia.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
                    // Cena jednostkowa netto po rabacie — to, co faktycznie zaplacono za sztuke.
                    ostCena = decimal.Round(p.Cena.NettoPoRabacie, 2);
                }
            }
            catch { /* pola opcjonalne — brak ceny nie jest błędem */ }

            wynik.Add(new Poz(
                pytany!, enc.Symbol, true, enc.Nazwa,
                Bezp(() => enc.Rodzaj?.Nazwa),
                dostepne, zadysponowane,
                ostCena, ostData, stany) with { Dopasowanie = dopasowanie });
        }

        var json = JsonSerializer.Serialize(new { pozycje = wynik },
            new JsonSerializerOptions { WriteIndented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping });

        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record StanMag(string Magazyn, decimal Dostepne, decimal Zadysponowane,
                            decimal RezerwacjaIlosciowa, decimal RezerwacjaDostawowa);

    internal record Poz(string Pytany, string? Symbol, bool Istnieje, string? Nazwa, string? Rodzaj,
                        decimal Dostepne, decimal Zadysponowane, decimal? OstatniaCenaZakupu,
                        string? DataOstatniegoZakupu, List<StanMag> Magazyny)
    {
        public string Dopasowanie { get; init; } = "brak";
    }
}
