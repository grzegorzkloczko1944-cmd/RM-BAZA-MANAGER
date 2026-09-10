// Tryb "wydanie-stan" — stan wydawania materiału na projekt. WYLACZNIE ODCZYT.
//
//   NexoRecon.exe wydanie-stan --projekt=2741 [--magazyn=MASTER] [--out=w.json]
//
// Zasila okno magazyniera „Wydanie z magazynu" (RM_BAZA_OKNO_WYDANIA_RW_PLAN.md).
// Jedno wywolanie daje wszystko, co okno pokazuje na starcie:
//
//     POTRZEBA          ZK (zakupy) + PW (produkcja wlasna)
//     WYDANO WCZESNIEJ  RW tego projektu
//     POZOSTALO         potrzeba - wydano  (liczy juz okno)
//
// DLACZEGO OSOBNY TRYB, SKORO JEST "dokumenty"
// ────────────────────────────────────────────
// Tryb "dokumenty" ciagnie ZK+ZD+RW+PW+WZ RAZEM Z POZYCJAMI i cenami — ~9 s.
// Skaner magazyniera odpytuje przy otwarciu okna i jeszcze raz przed zapisem
// RW, wiec taki koszt jest nie do przyjecia. Tutaj: trzy kolekcje zamiast
// pieciu, same sumy per symbol, zero cen i kosztow.
//
// DLACZEGO POTRZEBA IDZIE Z DWOCH DOKUMENTOW
// ──────────────────────────────────────────
// Tory sa rozdzielone (RMPAK_PRODUKCJA_USTALENIA.md §2):
//
//     Dostawca ≠ RMPAK  → tor zakupowy    → ZK
//     Dostawca = RMPAK  → tor produkcji   → PW → RW
//
// Detale produkcji wlasnej SWIADOMIE nie trafiaja na ZK, bo RMPAK nie zamawia
// u siebie. Sama ZK pokazalaby wiec tylko polowe tego, co magazynier wydaje.
// BOM tez nie jest dobrym zrodlem: mowi, co konstruktor zaprojektowal, a nie
// co realnie kupiono albo wyprodukowano.
//
// ⚠️ ZK I PW SIE NIE SUMUJA
// Te drogi sa rozlaczne z zalozenia. Symbol wystepujacy w obu (stare dane,
// zle ustawiony dostawca) idzie do "konflikty" z OBIEMA liczbami, a jego
// potrzeba zostaje NIEPOLICZONA. Ciche 4+6=10 byloby liczba, ktorej nikt
// nie zamierzal.
//
// ROZPOZNANIE PROJEKTU
// Numer projektu = pierwszy czlon pierwszego wiersza Uwag (Znacznik.cs).
// Do LICZENIA wydan wystarczy sam numer — takze na dokumencie wystawionym
// recznie w Subiekcie, bo magazynier fizycznie wydal towar i to jest fakt.
// Znacznik RM_BAZA w Tytule rozstrzyga co innego (czy dokumentem wolno
// zarzadzac) i tutaj NIE jest sprawdzany.
//
// RW bez numeru projektu w Uwagach NIE jest liczone — nie wiadomo, na ktory
// projekt poszlo. Ale wraca w "rw_bez_projektu", zeby okno moglo powiedziec,
// czemu stan magazynu spadl, a licznik nie drgnal.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class WydanieStan
{
    /// Ile ostatnich dokumentow kazdego rodzaju przegladamy. Projekt zyje
    /// tygodniami, wiec jego dokumenty sa wsrod nowszych; pelny przelot po
    /// wszystkich RW w bazie kosztowalby przy kazdym otwarciu okna.
    const int LIMIT = 400;

    public static int Uruchom(Uchwyt sfera, string? projekt, string? magazyn, string? outPath)
    {
        var szukany = (projekt ?? "").Trim();
        if (szukany.Length == 0)
        {
            Wypisz(new { blad = "brak --projekt=" }, outPath);
            return 1;
        }

        // symbol -> ilosc, osobno dla kazdego zrodla
        var zZk = new Dictionary<string, decimal>(StringComparer.OrdinalIgnoreCase);
        var zPw = new Dictionary<string, decimal>(StringComparer.OrdinalIgnoreCase);
        var zRw = new Dictionary<string, decimal>(StringComparer.OrdinalIgnoreCase);
        var rwBezProjektu = new List<object>();
        string? blad = null;

        try
        {
            Zbierz(() => sfera.ZamowieniaOdKlientow().Dane.Wszystkie(), szukany, zZk, null);
            Zbierz(() => sfera.PrzychodyWewnetrzne().Dane.Wszystkie(), szukany, zPw, null);
            // Tylko przy RW zbieramy odrzucone dokumenty: to one tlumacza
            // roznice miedzy stanem magazynu a licznikiem wydan.
            Zbierz(() => sfera.RozchodyWewnetrzne().Dane.Wszystkie(), szukany, zRw, rwBezProjektu);
        }
        catch (Exception ex)
        {
            blad = $"{ex.GetType().Name}: {ex.Message}";
        }

        // Symbol i na ZK, i na PW — potrzeby NIE liczymy, oddajemy do decyzji.
        var konflikty = new List<object>();
        foreach (var s in zZk.Keys.Where(zPw.ContainsKey).OrderBy(x => x))
            konflikty.Add(new { symbol = s, zk = zZk[s], pw = zPw[s] });
        var sporne = new HashSet<string>(
            konflikty.Select(k => (string)k.GetType().GetProperty("symbol")!.GetValue(k)!),
            StringComparer.OrdinalIgnoreCase);

        // Jedna lista: wszystko, co ma potrzebe ALBO zostalo juz wydane.
        // Pozycja wydana bez potrzeby (potrzeba: null) to material spoza
        // planu — smar, elektrody, srub „z reki". Okno oznacza ja POZA BOM.
        var symbole = new SortedSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var s in zZk.Keys) symbole.Add(s);
        foreach (var s in zPw.Keys) symbole.Add(s);
        foreach (var s in zRw.Keys) symbole.Add(s);

        var pozycje = new List<object>();
        foreach (var s in symbole)
        {
            decimal? potrzeba = null;
            string? zrodlo = null;
            if (!sporne.Contains(s))
            {
                if (zZk.TryGetValue(s, out var ilZk)) { potrzeba = ilZk; zrodlo = "ZK"; }
                else if (zPw.TryGetValue(s, out var ilPw)) { potrzeba = ilPw; zrodlo = "PW"; }
            }
            pozycje.Add(new
            {
                symbol = s,
                potrzeba,
                zrodlo,
                wydano = zRw.TryGetValue(s, out var w) ? w : 0m,
            });
        }

        Wypisz(new
        {
            projekt = szukany,
            magazyn = (magazyn ?? "").Trim(),
            pozycje,
            konflikty,
            rw_bez_projektu = rwBezProjektu,
            blad,
        }, outPath);
        return blad is null ? 0 : 1;
    }

    /// <summary>
    /// Sumuje pozycje dokumentow TEGO projektu do `cel`. Dokumenty bez numeru
    /// projektu w Uwagach trafiaja do `odrzucone` (gdy podano) — inaczej sa
    /// po prostu pomijane.
    /// </summary>
    static void Zbierz(Func<IQueryable<Dokument>> zrodlo, string projekt,
                       Dictionary<string, decimal> cel, List<object>? odrzucone)
    {
        // Projekcja z zagniezdzona kolekcja idzie do bazy jako JEDNO zapytanie
        // z JOIN-ami. Materializacja dokumentow i siegniecie po AsortymentAktualny
        // w petli to osobne zapytanie na KAZDA pozycje — ta sama pulapka, ktora
        // w Dokumenty.cs kosztowala 3,6 s na 109 dokumentow.
        var dane = zrodlo()
            .OrderByDescending(d => d.DataWprowadzenia)
            .Take(LIMIT)
            .Select(d => new
            {
                Numer = d.NumerWewnetrzny.PelnaSygnatura,
                d.DataWydaniaWystawienia,
                d.Uwagi,
                Pozycje = d.Pozycje.Select(p => new
                {
                    Symbol = p.AsortymentAktualny.Symbol,
                    p.Ilosc,
                }),
            })
            .ToList();

        foreach (var d in dane)
        {
            var numerProjektu = Znacznik.NumerProjektu(d.Uwagi);
            if (!numerProjektu.Equals(projekt, StringComparison.OrdinalIgnoreCase))
            {
                // Nie nasz projekt. Do listy „pominietych" trafiaja TYLKO
                // dokumenty bez zadnego numeru — te z cudzym numerem naleza
                // do innego projektu i nie sa zadna anomalia.
                if (odrzucone != null && numerProjektu.Length == 0)
                    odrzucone.Add(new
                    {
                        numer = d.Numer,
                        data = Data(d.DataWydaniaWystawienia),
                        pozycji = d.Pozycje.Count(),
                    });
                continue;
            }

            foreach (var p in d.Pozycje)
            {
                var s = (p.Symbol ?? "").Trim();
                if (s.Length == 0) continue;
                cel[s] = cel.TryGetValue(s, out var byla) ? byla + p.Ilosc : p.Ilosc;
            }
        }
    }

    /// Data w formacie yyyy-MM-dd. Typ pola rozni sie miedzy wersjami SDK
    /// (DateTime / DateOnly), stad object + Convert — ten sam wzorzec co
    /// w Dokumenty.cs i Zapotrzebowanie.cs.
    static string Data(object? wartosc)
    {
        try
        {
            if (wartosc == null || wartosc.Equals(default(DateTime))) return "";
            return Convert.ToDateTime(wartosc)
                .ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
        }
        catch { return ""; }
    }

    static void Wypisz(object obj, string? outPath)
    {
        var json = JsonSerializer.Serialize(obj, new JsonSerializerOptions
        {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
    }
}
