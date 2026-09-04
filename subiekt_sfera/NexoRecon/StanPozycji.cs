// Tryb "stan-pozycji" — dla listy symboli: kartoteka + ZK + ZD. Tylko odczyt.
//
//   NexoRecon.exe stan-pozycji --symbols-file=lista.txt [--out=w.json] [--projekt=2621]
//
// Zasila kolumnę SUBIEKT w arkuszu głównym RM_BAZA (plan integracji, sekcja
// „Wizualny wskaźnik" — wzorzec kolumny WYCENA z RFQ: prefiks, kolor, klik).
//
// Trzy stany na pozycję, bo to trzy różne informacje dla planującego produkcję:
//   kartoteka — czy asortyment w ogóle istnieje w Subiekcie
//   ZK        — czy jest na liście projektu (dokument z numerem projektu w Uwagach)
//   ZD        — czy zamówiony u dostawcy i u kogo
//
// FZ (przyjęcia) świadomie POMINIĘTE — krok 13 przepływu nie jest zrobiony,
// a zgadywanie „przyszło" z niepełnych danych byłoby gorsze niż brak kolumny.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class StanPozycji
{
    public static int Uruchom(Uchwyt sfera, List<string> symbole, string? projekt, string? outPath)
    {
        var asort = sfera.Asortymenty();

        // Jeden przelot po kartotekach — dopasowanie luźne (TRIM + wielkość
        // liter), bo w bazie są symbole ze spacją na końcu i różnicą a/A.
        var luzne = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var a in asort.Dane.Wszystkie().Select(a => new { a.Symbol }).ToList())
        {
            var k = (a.Symbol ?? "").Trim();
            if (k.Length > 0) luzne[k] = a.Symbol!;
        }

        // Pozycje ZK — tylko dokumenty tego projektu, gdy podano --projekt.
        // Numer projektu siedzi w Uwagach ZK (SUBIEKT_PROJEKTY_WYDANIA.md).
        var wZk = new Dictionary<string, (string Numer, decimal Ilosc)>(StringComparer.OrdinalIgnoreCase);
        try
        {
            foreach (var d in sfera.ZamowieniaOdKlientow().Dane.Wszystkie()
                                   .OrderByDescending(d => d.DataWprowadzenia).Take(200).ToList())
            {
                var uwagi = (Bezp(() => d.Uwagi) ?? "").Trim();
                if (!string.IsNullOrEmpty(projekt) &&
                    !uwagi.Contains(projekt, StringComparison.OrdinalIgnoreCase)) continue;
                var numer = Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                try
                {
                    foreach (var p in d.Pozycje)
                    {
                        var s = Bezp(() => p.AsortymentAktualny?.Symbol)?.Trim();
                        if (!string.IsNullOrEmpty(s) && !wZk.ContainsKey(s!))
                            wZk[s!] = (numer, p.Ilosc);
                    }
                }
                catch { }
            }
        }
        catch { }

        // Pozycje ZD — zamówione u dostawców (niezależnie od projektu, bo ZD
        // grupuje po dostawcy i może obejmować kilka projektów naraz).
        var wZd = new Dictionary<string, (string Numer, string Dostawca, decimal Ilosc, string Status)>(
            StringComparer.OrdinalIgnoreCase);
        try
        {
            foreach (var d in sfera.ZamowieniaDoDostawcow().Dane.Wszystkie()
                                   .OrderByDescending(d => d.DataWprowadzenia).Take(200).ToList())
            {
                var numer = Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                var dostawca = Bezp(() => d.Podmiot?.NazwaSkrocona) ?? "";
                var status = Bezp(() => d.StatusDokumentu?.Nazwa) ?? "";
                try
                {
                    foreach (var p in d.Pozycje)
                    {
                        var s = Bezp(() => p.AsortymentAktualny?.Symbol)?.Trim();
                        if (!string.IsNullOrEmpty(s) && !wZd.ContainsKey(s!))
                            wZd[s!] = (numer, dostawca, p.Ilosc, status);
                    }
                }
                catch { }
            }
        }
        catch { }

        var wynik = new List<Poz>();
        foreach (var pytany in symbole)
        {
            var s = (pytany ?? "").Trim();
            if (s.Length == 0) continue;

            var enc = asort.Dane.WyszukajPoSymbolu(s);
            if (enc == null && luzne.TryGetValue(s, out var realny))
                enc = asort.Dane.WyszukajPoSymbolu(realny);

            decimal stan = 0;
            if (enc != null)
            {
                try { foreach (var st in enc.StanyMagazynowe) stan += st.IloscDostepna; }
                catch { }
            }

            var symbolReal = enc?.Symbol?.Trim() ?? s;
            wZk.TryGetValue(symbolReal, out var zk);
            wZd.TryGetValue(symbolReal, out var zd);

            wynik.Add(new Poz(
                pytany!, enc != null, enc?.Nazwa, stan,
                zk.Numer ?? "", zk.Ilosc,
                zd.Numer ?? "", zd.Dostawca ?? "", zd.Ilosc, zd.Status ?? ""));
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

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record Poz(string Pytany, bool MaKartoteke, string? Nazwa, decimal Stan,
                        string Zk, decimal IloscZk,
                        string Zd, string Dostawca, decimal IloscZd, string StatusZd);
}
