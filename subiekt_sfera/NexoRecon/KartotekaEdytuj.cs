// Tryb "kartoteka-edytuj" — zmienia ISTNIEJACE kartoteki asortymentu. ZAPISUJE.
//
//   NexoRecon.exe kartoteka-edytuj --plan=p.json [--out=w.json] [--zapisz]
//
// Bez --zapisz suchy przebieg: mowi, co by sie zmienilo, nic nie rusza.
//
// plan.json:
//   { "pozycje": [
//       { "symbol":"012-100.16",          // KLUCZ — po nim szukamy kartoteki
//         "nazwa":"Katownik separatora",  // pola opcjonalne: brak = bez zmiany
//         "cena": 12.50,
//         "opis":"...",
//         "sklad":[{"symbol":"012-100.11","ilosc":2}]   // tylko dla kompletow
//       } ] }
//
// Po co osobno od "kartoteka": tamten tryb ZAKLADA nowa i celowo odmawia,
// gdy symbol zajety. Tutaj jest odwrotnie — kartoteka MUSI istniec. Okno
// "Asortyment" w RM_BAZA (07.09.2026) poprawia dane wprost na liscie, wiec
// potrzebuje trybu, ktory zmienia to, co juz jest.
//
// SYMBOLU NIE ZMIENIAMY. Jest kluczem wszedzie — w kodach kreskowych, na
// dokumentach, w BOM-ie RM_BAZA i w skladach kompletow. Od zmiany symbolu
// jest osobny tryb "symbole", ktory wie, co przy tym poprawic.
//
// SKLAD: ta sama zasada co w Projekt.cs i KompletNapraw.cs — plan jest
// PRAWDA, wiec czyscimy stary sklad i wpisujemy podany od nowa. Inaczej
// dwukrotna edycja zdublowalaby skladniki (dokladnie ten blad, ktory
// naprawialismy 06.09.2026). Po zapisie Lp idzie 1..N.
//
// Pole "sklad" pominiete w planie = sklad NIE JEST RUSZANY. Pusta lista to
// co innego niz brak pola: znaczy "wyczysc sklad" i tak jest traktowana.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class KartotekaEdytuj
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }
        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;

        var asort = sfera.Asortymenty();
        var kroki = new List<Krok>();
        int zmienionych = 0;

        foreach (var p in plan.Pozycje ?? new List<PozPlan>())
        {
            var symbol = (p.Symbol ?? "").Trim();
            if (symbol.Length == 0) continue;

            try
            {
                var enc = Znajdz(asort, symbol);
                if (enc == null)
                {
                    kroki.Add(new Krok(symbol, "brak", "nie ma takiej kartoteki w Subiekcie"));
                    continue;
                }

                using var ob = asort.Znajdz(enc);
                var zmiany = new List<string>();

                // Nazwa/cena/opis: porownujemy PRZED przypisaniem, zeby raport
                // mowil o faktycznych zmianach, a nie o tym, co przyszlo w planie.
                var nazwa = (p.Nazwa ?? "").Trim();
                if (nazwa.Length > 0 && nazwa != ((string?)ob.Dane.Nazwa ?? "").Trim())
                {
                    zmiany.Add($"nazwa: „{ob.Dane.Nazwa}” → „{nazwa}”");
                    if (zapisz) ob.Dane.Nazwa = nazwa;
                }

                if (p.Cena is { } cena)
                {
                    var stara = decimal.Round((decimal)ob.Dane.CenaEwidencyjna, 2);
                    var nowa = decimal.Round(cena, 2);
                    if (stara != nowa)
                    {
                        zmiany.Add($"cena ewid.: {stara:0.00} → {nowa:0.00}");
                        if (zapisz) try { ob.Dane.CenaEwidencyjna = nowa; } catch { }
                    }
                }

                if (p.Opis != null)
                {
                    var stary = (Bezp(() => (string?)ob.Dane.Opis) ?? "").Trim();
                    var nowy = p.Opis.Trim();
                    if (stary != nowy)
                    {
                        zmiany.Add("opis zmieniony");
                        if (zapisz) try { ob.Dane.Opis = nowy; } catch { }
                    }
                }

                // Sklad kompletu — tylko gdy pole jest w planie (null = nie ruszaj).
                if (p.Sklad != null)
                {
                    var opisSkladu = Sklad(ob, p.Sklad, zapisz);
                    if (opisSkladu != null) zmiany.Add(opisSkladu);
                }

                if (zmiany.Count == 0)
                {
                    kroki.Add(new Krok(symbol, "bez-zmian", null));
                    continue;
                }

                var opisZmian = string.Join("; ", zmiany);
                if (!zapisz)
                {
                    kroki.Add(new Krok(symbol, "do-zmiany", opisZmian));
                    continue;
                }

                if (!ob.Zapisz())
                {
                    kroki.Add(new Krok(symbol, "blad", Bezp(ob.PodajBledy) ?? "Zapisz() = false"));
                    continue;
                }
                zmienionych++;
                kroki.Add(new Krok(symbol, "zmieniona", opisZmian));
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok(symbol, "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(new
        {
            // "zapisano" mowi, czy zapis SIE UDAL, nie czy o niego proszono —
            // ta sama zasada co w RW po pomylce z 05.09.2026.
            zapisano = zapisz && zmienionych > 0,
            zmienionych,
            kroki,
        }, new JsonSerializerOptions
        {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
        });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    /// <summary>
    /// Ustawia sklad kompletu na dokladnie ten z planu. Zwraca opis zmiany
    /// albo null, gdy sklad juz sie zgadza.
    /// </summary>
    static string? Sklad(InsERT.Moria.Asortymenty.IAsortyment ob, List<SkladPlan> plan, bool zapisz)
    {
        // Obecny sklad — do porownania, zeby nie raportowac zmiany, ktorej nie ma.
        var teraz = new Dictionary<string, decimal>(StringComparer.OrdinalIgnoreCase);
        try
        {
            foreach (var s in (IEnumerable<dynamic>)ob.Dane.SkladnikiKompletu)
            {
                var sym = ((string?)s.Skladnik.Symbol ?? "").Trim();
                if (sym.Length == 0) continue;
                teraz[sym] = teraz.TryGetValue(sym, out var byla) ? byla + (decimal)s.Ilosc : (decimal)s.Ilosc;
            }
        }
        catch
        {
            return null;                // kartoteka nie jest kompletem
        }

        var chciany = new Dictionary<string, decimal>(StringComparer.OrdinalIgnoreCase);
        foreach (var s in plan)
        {
            var sym = (s.Symbol ?? "").Trim();
            if (sym.Length == 0) continue;
            chciany[sym] = s.Ilosc <= 0 ? 1m : s.Ilosc;
        }

        if (teraz.Count == chciany.Count
            && teraz.All(kv => chciany.TryGetValue(kv.Key, out var i) && i == kv.Value))
            return null;

        var dodane = chciany.Keys.Where(k => !teraz.ContainsKey(k)).ToList();
        var usuniete = teraz.Keys.Where(k => !chciany.ContainsKey(k)).ToList();
        var zmienione = chciany.Where(kv => teraz.TryGetValue(kv.Key, out var i) && i != kv.Value)
                               .Select(kv => $"{kv.Key} {teraz[kv.Key]:0.##}→{kv.Value:0.##}").ToList();

        var czesci = new List<string>();
        if (dodane.Count > 0) czesci.Add($"+{dodane.Count} ({string.Join(", ", dodane)})");
        if (usuniete.Count > 0) czesci.Add($"−{usuniete.Count} ({string.Join(", ", usuniete)})");
        if (zmienione.Count > 0) czesci.Add("ilości: " + string.Join(", ", zmienione));
        var opis = "skład: " + string.Join(", ", czesci);

        if (!zapisz) return opis;

        // Plan jest prawda: czyscimy i wpisujemy od nowa. SDK nie ma "ustaw"
        // ani "wyczysc" — tylko Usun(symbol) w petli (patrz Projekt.WyczyscSklad).
        foreach (var sym in teraz.Keys.ToList())
        {
            var straznik = 0;
            while (straznik++ < 200 && (bool)ob.Skladniki.Usun(sym)) { }
        }
        foreach (var kv in chciany)
            ob.Skladniki.Dodaj(kv.Key, kv.Value);
        KompletNapraw.Przenumeruj(ob);
        return opis;
    }

    /// <summary>
    /// Kartoteka po symbolu, z tym samym luznym dopasowaniem co Kartoteka.cs
    /// (TRIM, wielkosc liter) — symbole bywaja wpisane z ogonkiem spacji.
    /// </summary>
    /// <remarks>
    /// Zwraca <c>Asortyment</c>, NIE <c>dynamic</c>. To istotne: gdy encja jest
    /// dynamic, obiekt z <c>asort.Znajdz(enc)</c> tez staje sie dynamic, a wtedy
    /// binder wybiera przeciazenie <c>Skladniki.Usun</c> po typie runtime i nie
    /// trafia w zadne z trzech (Asortyment / int / string) — leci
    /// "No overload for method 'Usun' takes 1 arguments" (07.09.2026).
    /// Typ statyczny encji sprawia, ze <c>ob</c> tez jest statyczny i przeciazenia
    /// rozstrzyga kompilator, tak jak w KompletNapraw.cs.
    /// </remarks>
    static InsERT.Moria.ModelDanych.Asortyment? Znajdz(
        InsERT.Moria.Asortymenty.IAsortymenty asort, string symbol)
    {
        var enc = asort.Dane.WyszukajPoSymbolu(symbol);
        if (enc != null) return enc;
        var luzne = asort.Dane.Wszystkie().Select(a => a.Symbol).ToList()
            .FirstOrDefault(s => string.Equals((s ?? "").Trim(), symbol,
                                               StringComparison.OrdinalIgnoreCase));
        return luzne == null ? null : asort.Dane.WyszukajPoSymbolu(luzne);
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record SkladPlan(string? Symbol, decimal Ilosc);
    internal record PozPlan(string? Symbol, string? Nazwa, decimal? Cena, string? Opis,
                            List<SkladPlan>? Sklad);
    internal record Plan(List<PozPlan>? Pozycje);
    internal record Krok(string Symbol, string Status, string? Szczegoly);
}
