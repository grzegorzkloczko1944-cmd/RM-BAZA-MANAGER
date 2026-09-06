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

        // Otwarte ZD per symbol — TU, a nie osobnym wywolaniem mostu z Pythona.
        // Start Sfery i logowanie to ~10 s NA KAZDE uruchomienie NexoRecon.exe;
        // drugi przebieg (tryb "dokumenty") kosztowal wiecej niz cala reszta
        // odczytu (zmierzone 05.09.2026: 15 s + 12 s, z czego ~20 s to sam
        // narzut). Zrealizowane i anulowane pomijamy — zamowienie sprzed
        // miesiecy nie mowi nic o tym, czy trzeba domowic teraz.
        var zdWgSymbolu = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);
        try
        {
            foreach (var d in sfera.ZamowieniaDoDostawcow().Dane.Wszystkie()
                                   .OrderByDescending(d => d.DataWprowadzenia)
                                   .Take(200).ToList())
            {
                var status = (BezpS(() => d.StatusDokumentu?.Nazwa) ?? "").ToLowerInvariant();
                if (status.Contains("zrealizowan") || status.Contains("anulowan")) continue;
                var numer = BezpS(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                if (numer.Length == 0) continue;
                try
                {
                    foreach (var poz in d.Pozycje)
                    {
                        var sym = BezpS(() => poz.AsortymentAktualny?.Symbol)?.Trim();
                        if (string.IsNullOrEmpty(sym)) continue;
                        var opis = $"{numer} ({poz.Ilosc:0.##})";
                        if (!zdWgSymbolu.TryGetValue(sym, out var lista))
                            zdWgSymbolu[sym] = lista = new List<string>();
                        if (!lista.Contains(opis)) lista.Add(opis);
                    }
                }
                catch { /* dokument bez czytelnych pozycji */ }
            }
        }
        catch { /* brak dostepu do ZD nie moze wywalic odczytu stanow */ }

        // ⚠️ JEDNO ZAPYTANIE, NIE 3444. Wczesniejsza wersja wolala
        // WyszukajPoSymbolu per kartoteka i dla kazdej siegala po stany,
        // zakresy i dostawcow — czyli kilkanascie tysiecy zapytan do SQL,
        // zeby zwrocic ~800 rekordow. Na produkcji: ~7 s (06.09.2026).
        // Projekcja anonimowa z zagniezdzonymi kolekcjami idzie do bazy jako
        // jedno zapytanie z JOIN-ami; EF materializuje wszystko naraz.
        //
        // Rodzaj i dostawca sa w projekcji jako proste pola (nie encje) —
        // wyciagniecie ich po fakcie z materializowanej encji cofneloby caly
        // zysk, bo kazde siegniecie po nawigacje to osobne zapytanie.
        var dane = asort.Dane.Wszystkie()
            .Select(a => new
            {
                a.Id,
                a.Symbol,
                a.Nazwa,
                a.CenaEwidencyjna,
                Rodzaj = a.Rodzaj.Nazwa,
                Stany = a.StanyMagazynowe.Select(s => new
                {
                    Magazyn = s.Magazyn.Symbol,
                    s.IloscDostepna,
                    s.IloscZadysponowana,
                    s.IloscZarezerwowanaIlosciowo,
                    s.IloscZarezerwowanaDostawowo,
                }),
                Zakresy = a.StanyWMagazynachZakresy.Select(z => new
                {
                    z.StanMinimalny,
                    z.StanOptymalny,
                }),
                // Dostawca podstawowy: ten z ustawiona flaga, inaczej pierwszy.
                Dostawcy = a.DaneAsortymentuDlaPodmiotow
                    .Select(d => new
                    {
                        Nazwa = d.Podmiot.NazwaSkrocona,
                        Podstawowy = d.AsortymentDlaKtoregoDostawcaPodstawowy != null,
                    }),
            })
            .ToList();

        var wynik = new List<Poz>();
        foreach (var k in dane)
        {
            var symbol = (k.Symbol ?? "").Trim();
            if (symbol.Length == 0) continue;

            var stany = new List<StanMag>();
            decimal dostepne = 0, zadysponowane = 0, zarezerwowane = 0;
            foreach (var s in k.Stany)
            {
                stany.Add(new StanMag(s.Magazyn ?? "?", s.IloscDostepna, s.IloscZadysponowana));
                dostepne += s.IloscDostepna;
                zadysponowane += s.IloscZadysponowana;
                zarezerwowane += s.IloscZarezerwowanaIlosciowo + s.IloscZarezerwowanaDostawowo;
            }

            decimal stanMin = 0, stanOpt = 0;
            foreach (var z in k.Zakresy)
            {
                stanMin += z.StanMinimalny;
                stanOpt += z.StanOptymalny.GetValueOrDefault();
            }

            // Kartoteki bez ruchu to zwykle martwe indeksy — przy przegladzie
            // magazynu tylko zasmiecaja liste. Kartoteke z PROGIEM zostawiamy
            // mimo zera: to wlasnie ona jest "do domowienia".
            if (tylkoNiezerowe && dostepne == 0 && zadysponowane == 0 && stanMin == 0) continue;

            var dostawca = k.Dostawcy.FirstOrDefault(d => d.Podstawowy)?.Nazwa
                        ?? k.Dostawcy.FirstOrDefault()?.Nazwa;

            wynik.Add(new Poz(
                k.Id, symbol, (k.Nazwa ?? "").Trim(),
                k.Rodzaj,
                dostepne, zadysponowane, zarezerwowane,
                decimal.Round(k.CenaEwidencyjna, 2),
                stany, stanMin, stanOpt, dostawca?.Trim(),
                zdWgSymbolu.TryGetValue(symbol, out var zd) ? string.Join(", ", zd) : null));
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

    /// Nazwa dostawcy podstawowego kartoteki albo pierwszego z listy, albo null.
    static string? DostawcaPodstawowy(object enc)
    {
        try
        {
            var t = enc.GetType();
            var kandydaci = t.GetProperties()
                .Concat(t.GetInterfaces().SelectMany(i => i.GetProperties()))
                .Where(p => (p.Name.Contains("Dostawc") || p.Name.Contains("DlaPodmiot"))
                            && typeof(System.Collections.IEnumerable).IsAssignableFrom(p.PropertyType)
                            && p.PropertyType != typeof(string))
                .ToList();
            foreach (var prop in kandydaci)
            {
                if (prop.GetValue(enc) is not System.Collections.IEnumerable kol) continue;
                object? podst = null, pierwszy = null;
                foreach (var d in kol)
                {
                    if (d == null) continue;
                    pierwszy ??= d;
                    var flaga = d.GetType().GetProperty("AsortymentDlaKtoregoDostawcaPodstawowy");
                    if (flaga != null && flaga.GetValue(d) != null) { podst = d; break; }
                }
                var wyb = podst ?? pierwszy;
                if (wyb == null) continue;
                var podmiot = wyb.GetType().GetProperty("Podmiot")?.GetValue(wyb);
                var nazwa = podmiot?.GetType().GetProperty("NazwaSkrocona")?.GetValue(podmiot) as string;
                if (!string.IsNullOrWhiteSpace(nazwa)) return nazwa.Trim();
            }
        }
        catch { }
        return null;
    }

    static T? Bezp<T>(Func<T?> f) where T : class { try { return f(); } catch { return null; } }
    static string? BezpS(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record StanMag(string Magazyn, decimal Dostepne, decimal Zadysponowane);

    // Jednostki miary tu nie ma — Asortyment nie wystawia jej wprost, a do
    // pytania „ile mam na stanie" nie jest konieczna (tryb „stan" też jej
    // nie zwraca).
    internal record Poz(int Id, string Symbol, string Nazwa, string? Rodzaj,
                        decimal Dostepne, decimal Zadysponowane, decimal Zarezerwowane,
                        decimal CenaEwidencyjna, List<StanMag> Magazyny,
                        decimal StanMinimalny, decimal StanOptymalny, string? Dostawca,
                        string? Zd);
}
