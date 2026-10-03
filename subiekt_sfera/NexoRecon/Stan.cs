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
//
// ⚠️ DWIE PROJEKCJE, ZERO NAWIGACJI W PĘTLI (03.10.2026). Do tej pory dla
// KAŻDEGO pytanego symbolu szło WyszukajPoSymbolu, potem StanyMagazynowe,
// s.Magazyn, Rodzaj, PolaWlasne i PozycjeDokumentu z FZ — kilka zapytań SQL
// na wiersz. Okno wydań pyta o 170–300 symboli → 1,0–1,2 s na demo, w firmie
// przez sieć wielokrotnie więcej. Teraz:
//   1. wszystkie kartoteki z polami i stanami — jedno zapytanie (wzorzec
//      Magazyn.cs), dopasowanie w pamięci,
//   2. ostatni zakup (FZ) tylko dla trafionych Id — drugie zapytanie.
// Wynik ma być IDENTYCZNY ze starym trybem — porównany JSON-em na trzech
// projektach przed wdrożeniem.

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

        // ── 1. Kartoteki z tym, co oddajemy — projekcja.
        // Najpierw tylko PYTANE symbole (`IN` w SQL — porównanie SQL Servera
        // ignoruje wielkość liter i spacje na końcu, czyli dokładnie dawne
        // dopasowanie „dokładne"). Karta jednej pozycji nie płaci za przelot
        // przez ~2000 kartotek (0,1 s zamiast 0,37 s). Pełny przelot tylko,
        // gdy coś nie trafiło — wtedy potrzebne dopasowanie luźne (spacja
        // z przodu symbolu w bazie), a nieistniejące symbole i tak go wymagają.
        var szukane = symbole.Select(s => (s ?? "").Trim()).Where(s => s.Length > 0)
                             .Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        var dane = Projekcja(asort.Dane.Wszystkie().Where(a => szukane.Contains(a.Symbol)));
        var znalezione = new HashSet<string>(dane.Select(d => (d.Symbol ?? "").TrimEnd()),
                                             StringComparer.OrdinalIgnoreCase);
        if (szukane.Any(s => !znalezione.Contains(s)))
            dane = Projekcja(asort.Dane.Wszystkie());

        // Dopasowanie jak dotąd: najpierw „DOKŁADNE” — tak, jak dopasowywało
        // WyszukajPoSymbolu, czyli porównanie SQL Servera: BEZ wielkości liter
        // i bez spacji na KOŃCU (sprawdzone 03.10.2026: „kfl001" stary tryb
        // dawał jako dokładne). Potem LUŹNE (pełny TRIM — spacja z przodu).
        // Luźna mapa — „ostatni wygrywa", tak samo jak w starej wersji.
        var dokladne = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        var luzne = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        for (var i = 0; i < dane.Count; i++)
        {
            var s = dane[i].Symbol ?? "";
            var bezKonca = s.TrimEnd();
            if (bezKonca.Length > 0 && !dokladne.ContainsKey(bezKonca)) dokladne[bezKonca] = i;
            var k = s.Trim();
            if (k.Length > 0) luzne[k] = i;
        }

        var trafione = new List<(string Pytany, int Idx, string Dopasowanie)>();
        foreach (var pytany in symbole)
        {
            var szukany = (pytany ?? "").Trim();
            if (szukany.Length == 0) continue;
            if (dokladne.TryGetValue(szukany, out var idx))
                trafione.Add((pytany!, idx, "dokladne"));
            else if (luzne.TryGetValue(szukany, out idx))
                trafione.Add((pytany!, idx, "luzne"));
            else
                trafione.Add((pytany!, -1, "brak"));
        }

        // ── 2. Ostatni zakup (FZ) — tylko dla trafionych kartotek, jednym
        // zapytaniem z podzapytaniem (OUTER APPLY), nie PozycjeDokumentu per
        // kartoteka. Cena netto po rabacie = to, co faktycznie zapłacono.
        var ostatni = new Dictionary<int, (DateTime Data, decimal Cena)>();
        try
        {
            var idy = trafione.Where(t => t.Idx >= 0).Select(t => dane[t.Idx].Id).Distinct().ToList();
            if (idy.Count > 0)
            {
                var zakupy = asort.Dane.Wszystkie()
                    .Where(a => idy.Contains(a.Id))
                    .Select(a => new
                    {
                        a.Id,
                        Ost = a.PozycjeDokumentu
                            .Where(p => p.Dokument != null && p.Dokument.Symbol == "FZ" && p.Ilosc > 0)
                            .OrderByDescending(p => p.Dokument.DataWprowadzenia)
                            .Select(p => new { p.Dokument.DataWprowadzenia, Cena = p.Cena.NettoPoRabacie })
                            .FirstOrDefault(),
                    })
                    .ToList();
                foreach (var z in zakupy)
                    if (z.Ost != null)
                        ostatni[z.Id] = (z.Ost.DataWprowadzenia, z.Ost.Cena);
            }
        }
        catch { /* pola opcjonalne — brak ceny nie jest błędem */ }

        // ── 3. Złożenie wyniku w pamięci.
        var wynik = new List<Poz>();
        foreach (var (pytany, idx, dopasowanie) in trafione)
        {
            if (idx < 0)
            {
                wynik.Add(new Poz(pytany, null, false, null, null, 0, 0, null, null, new List<StanMag>()));
                continue;
            }
            var k = dane[idx];

            // Stany są już StanMag (Projekcja); sumy jak dotąd.
            var stany = k.Stany;
            var dostepne = stany.Sum(s => s.Dostepne);
            var zadysponowane = stany.Sum(s => s.Zadysponowane);

            decimal? ostCena = null; string? ostData = null;
            if (ostatni.TryGetValue(k.Id, out var oz))
            {
                ostData = oz.Data.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
                ostCena = decimal.Round(oz.Cena, 2);
            }

            wynik.Add(new Poz(
                pytany, k.Symbol, true, k.Nazwa, k.Rodzaj,
                dostepne, zadysponowane,
                ostCena, ostData, stany) with
                {
                    Dopasowanie = dopasowanie,
                    // Id kartoteki — JEDYNA tozsamosc, ktorej nie rusza zmiana
                    // symbolu ani nazwy w Subiekcie. RM_BAZA zapisuje je jako
                    // `subiekt_id` i po nim dopasowuje pozycje (02.10.2026).
                    Id = k.Id,
                    Polozenie = (k.Polozenie ?? "").Trim(),
                    Opis = (k.Opis ?? "").Trim(),
                });
        }

        var json = JsonSerializer.Serialize(new { pozycje = wynik },
            new JsonSerializerOptions { WriteIndented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping });

        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    /// Jedna projekcja SQL: kartoteka + rodzaj + położenie + stany per magazyn.
    /// Wszystkie pola w jednym Select — nawigacje po materializacji to
    /// osobne zapytania na każdy wiersz (zasada z CLAUDE.md).
    static List<Kart> Projekcja(IQueryable<Asortyment> zrodlo) =>
        zrodlo.Select(a => new
            {
                a.Id,
                a.Symbol,
                a.Nazwa,
                Rodzaj = a.Rodzaj.Nazwa,
                a.Opis,
                // Polozenie (regal/polka) — proste pole wlasne PoleWlasne1.
                Polozenie = a.PolaWlasne.PoleWlasne1,
                Stany = a.StanyMagazynowe.Select(s => new
                {
                    Magazyn = s.Magazyn.Symbol,
                    s.IloscDostepna,
                    s.IloscZadysponowana,
                    s.IloscZarezerwowanaIlosciowo,
                    s.IloscZarezerwowanaDostawowo,
                }),
            })
            .ToList()
            .Select(a => new Kart(a.Id, a.Symbol, a.Nazwa, a.Rodzaj, a.Opis, a.Polozenie,
                a.Stany.Select(s => new StanMag(s.Magazyn ?? "?", s.IloscDostepna,
                    s.IloscZadysponowana, s.IloscZarezerwowanaIlosciowo,
                    s.IloscZarezerwowanaDostawowo)).ToList()))
            .ToList();

    internal record Kart(int Id, string? Symbol, string? Nazwa, string? Rodzaj, string? Opis,
                         string? Polozenie, List<StanMag> Stany);

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record StanMag(string Magazyn, decimal Dostepne, decimal Zadysponowane,
                            decimal RezerwacjaIlosciowa, decimal RezerwacjaDostawowa);

    internal record Poz(string Pytany, string? Symbol, bool Istnieje, string? Nazwa, string? Rodzaj,
                        decimal Dostepne, decimal Zadysponowane, decimal? OstatniaCenaZakupu,
                        string? DataOstatniegoZakupu, List<StanMag> Magazyny)
    {
        public string Dopasowanie { get; init; } = "brak";

        /// Id kartoteki w Subiekcie. null dla kartotek NIEISTNIEJACYCH.
        /// Property, nie parametr konstruktora — z tego samego powodu co
        /// Polozenie: Poz powstaje takze dla symboli bez kartoteki.
        public int? Id { get; init; }

        /// Polozenie na magazynie (regal/polka) z pola wlasnego PoleWlasne1.
        /// Jako property z wartoscia domyslna, a nie parametr konstruktora —
        /// Poz tworzymy tez dla kartotek NIEISTNIEJACYCH (Istnieje=false),
        /// gdzie polozenia po prostu nie ma.
        public string? Polozenie { get; init; }

        /// Opis kartoteki — rodzaj produktu, uzupelniony przy migracji
        /// (MAGAZYN.md). Tak samo jak Polozenie: property, nie parametr.
        public string? Opis { get; init; }
    }
}
