// Tryb "dokumenty" — lista ZK i ZD z pozycjami. Tylko odczyt.
//
//   NexoRecon.exe dokumenty [--out=w.json] [--limit=200]
//
// Zasila okno „Zamówienia — przegląd" w RM_BAZA: jedna lista wszystkich
// dokumentów projektowych z możliwością wejścia w konkretny.
//
// Pozycje idą RAZEM z nagłówkami, bo alternatywą byłoby pytanie Subiekta
// osobno przy każdym kliknięciu w dokument (~8 s na wywołanie procesu —
// most jest bezstanowy). Przy kilkuset dokumentach to i tak jeden przelot.

using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Dokumenty
{
    public static int Uruchom(Uchwyt sfera, int limit, string? outPath)
    {
        var wynik = new List<Dok>();

        Zbierz(wynik, "ZK", limit, () => sfera.ZamowieniaOdKlientow().Dane.Wszystkie());
        Zbierz(wynik, "ZD", limit, () => sfera.ZamowieniaDoDostawcow().Dane.Wszystkie());
        // RW — wydania na produkcję. Dziś w firmie praktycznie nieużywane
        // (ostatnie realne z lipca 2023), ale to punkt 2 planu integracji:
        // gdy wrócą, mają się pokazywać w przeglądzie bez zmiany kodu.
        Zbierz(wynik, "RW", limit, () => sfera.RozchodyWewnetrzne().Dane.Wszystkie());
        // WZ — wydania zewnętrzne, dla kompletu obrazu wydań z magazynu.
        Zbierz(wynik, "WZ", limit, () => sfera.WydaniaZewnetrzne().Dane.Wszystkie());

        var json = JsonSerializer.Serialize(new { dokumenty = wynik },
            new JsonSerializerOptions
            {
                WriteIndented = false,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    static void Zbierz(List<Dok> wynik, string rodzaj, int limit,
                       Func<IQueryable<Dokument>> zrodlo)
    {
        try
        {
            foreach (var d in zrodlo().OrderByDescending(x => x.DataWprowadzenia)
                                      .Take(limit).ToList())
            {
                var pozycje = new List<PozDok>();
                decimal wartosc = 0;
                try
                {
                    foreach (var p in d.Pozycje)
                    {
                        var sym = Bezp(() => p.AsortymentAktualny?.Symbol);
                        if (string.IsNullOrWhiteSpace(sym)) continue;
                        decimal cena = 0;
                        try { cena = p.Cena.NettoPoRabacie; } catch { }
                        wartosc += cena * p.Ilosc;
                        pozycje.Add(new PozDok(
                            sym!.Trim(),
                            Bezp(() => p.AsortymentAktualny?.Nazwa) ?? "",
                            p.Ilosc,
                            Bezp(() => p.JednostkaMiaryAs?.JednostkaMiary?.Symbol) ?? "szt",
                            decimal.Round(cena, 2)));
                    }
                }
                catch { /* dokument bez czytelnych pozycji — nagłówek zostaje */ }

                wynik.Add(new Dok(
                    rodzaj,
                    Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "",
                    Data(d),
                    Bezp(() => d.Podmiot?.NazwaSkrocona) ?? "",
                    Bezp(() => d.Tytul) ?? "",
                    (Bezp(() => d.Uwagi) ?? "").Trim(),
                    Bezp(() => d.StatusDokumentu?.Nazwa) ?? "",
                    Termin(d),
                    Bezp(() => d.Magazyn?.Symbol) ?? "",
                    decimal.Round(wartosc, 2),
                    pozycje));
            }
        }
        catch { /* brak dostępu do typu dokumentu nie może wywalić reszty */ }
    }

    static string Data(Dokument d)
    {
        // Data wystawienia, a gdy pusta (starsze ZD z RM_BAZA) — wprowadzenia.
        return Bezp(() =>
        {
            var w = d.DataWydaniaWystawienia;
            var dt = w == default ? d.DataWprowadzenia : Convert.ToDateTime(w);
            return dt.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        }) ?? "";
    }

    /// Termin dostawy (pole TerminRealizacji). Mają go tylko zamówienia — WZ
    /// i RW nie — więc czytamy refleksją: brak pola daje pusty łańcuch, a nie
    /// błąd kompilacji ani wyjątek.
    static string Termin(Dokument d)
    {
        try
        {
            var p = d.GetType().GetProperty("TerminRealizacji");
            if (p?.GetValue(d) is DateTime dt)
                return dt.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        }
        catch { /* dokument bez terminu — kolumna zostaje pusta */ }
        return "";
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record PozDok(string Symbol, string Nazwa, decimal Ilosc, string Jm,
                           decimal Cena);

    internal record Dok(string Rodzaj, string Numer, string Data, string Podmiot,
                        string Tytul, string Uwagi, string Status, string Termin,
                        string Magazyn,
                        decimal Wartosc, List<PozDok> Pozycje);
}
