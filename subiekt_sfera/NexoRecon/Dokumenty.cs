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
            // ⚠️ JEDNA PROJEKCJA, NIE NAWIGACJE W PĘTLI. Wcześniej ToList()
            // materializował dokumenty, a potem dla KAŻDEJ z ~1400 pozycji
            // szło osobne zapytanie po AsortymentAktualny, Cena i
            // JednostkaMiaryAs — 3,6 s na 109 dokumentów (06.09.2026).
            // Projekcja z zagnieżdżoną kolekcją idzie do bazy jako jedno
            // zapytanie z JOIN-ami (ten sam wzorzec co w Magazyn.cs).
            //
            // Pozycje ZD trzymamy jako ENCJE (PozEnc), bo ProjektZk schodzi
            // po powiązaniach ZD→ZK refleksją i potrzebuje żywego obiektu.
            // Reszta rodzajów tego nie używa, więc płaci tylko ZD.
            var czyZd = rodzaj == "ZD";
            var dane = zrodlo()
                .OrderByDescending(x => x.DataWprowadzenia)
                .Take(limit)
                .Select(d => new
                {
                    Numer = d.NumerWewnetrzny.PelnaSygnatura,
                    d.DataWydaniaWystawienia,
                    d.DataWprowadzenia,
                    Podmiot = d.Podmiot.NazwaSkrocona,
                    d.Tytul,
                    d.Uwagi,
                    Status = d.StatusDokumentu.Nazwa,
                    Magazyn = d.Magazyn.Symbol,
                    Dokument = d,           // do Termin() i ProjektZk()
                    Pozycje = d.Pozycje.Select(p => new
                    {
                        Symbol = p.AsortymentAktualny.Symbol,
                        Nazwa = p.AsortymentAktualny.Nazwa,
                        p.Ilosc,
                        Jm = p.JednostkaMiaryAs.JednostkaMiary.Symbol,
                        Cena = p.Cena.NettoPoRabacie,
                        Pozycja = p,        // do ProjektZk() przy ZD
                    }),
                })
                .ToList();

            foreach (var d in dane)
            {
                var pozycje = new List<PozDok>();
                decimal wartosc = 0;
                foreach (var p in d.Pozycje)
                {
                    var sym = (p.Symbol ?? "").Trim();
                    if (sym.Length == 0) continue;
                    wartosc += p.Cena * p.Ilosc;
                    pozycje.Add(new PozDok(
                        sym,
                        p.Nazwa ?? "",
                        p.Ilosc,
                        p.Jm ?? "szt",
                        decimal.Round(p.Cena, 2),
                        // Projekt POZYCJI — z Uwag ZK, którą realizuje (tylko ZD).
                        // Uwagi samego ZD są puste, a jedno ZD zbiera detale
                        // z kilku projektów; bez tego okno dokumentów nie
                        // wiedziało, gdzie postawić „Zamówiono" (05.09.2026).
                        czyZd ? Zapotrzebowanie.ProjektZk(p.Pozycja) : ""));
                }

                wynik.Add(new Dok(
                    rodzaj,
                    d.Numer ?? "",
                    Data(d.DataWydaniaWystawienia, d.DataWprowadzenia),
                    d.Podmiot ?? "",
                    d.Tytul ?? "",
                    (d.Uwagi ?? "").Trim(),
                    d.Status ?? "",
                    Termin(d.Dokument),
                    d.Magazyn ?? "",
                    decimal.Round(wartosc, 2),
                    pozycje));
            }
        }
        catch { /* brak dostępu do typu dokumentu nie może wywalić reszty */ }
    }

    static string Data(object? wystawienia, DateTime wprowadzenia)
    {
        // Data wystawienia, a gdy pusta (starsze ZD z RM_BAZA) — wprowadzenia.
        // Typ pola rozni sie miedzy wersjami SDK (DateTime / DateOnly), stad
        // object + Convert — tak samo jak w Zapotrzebowanie.cs.
        return Bezp(() =>
        {
            var dt = wystawienia == null || wystawienia.Equals(default(DateTime))
                ? wprowadzenia
                : Convert.ToDateTime(wystawienia);
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
                           decimal Cena, string Projekt);

    internal record Dok(string Rodzaj, string Numer, string Data, string Podmiot,
                        string Tytul, string Uwagi, string Status, string Termin,
                        string Magazyn,
                        decimal Wartosc, List<PozDok> Pozycje);
}
