// Tryb "zapotrzebowanie-test" — DIAGNOSTYKA, wylacznie ODCZYT.
//
//   NexoRecon.exe zapotrzebowanie-test [--out=wynik.json] [konfig.json]
//
// Odpowiada na pytanie, od ktorego zalezy caly wariant 1 z
// ANALIZA_ZK_DWA_ZRODLA_PRAWDY.md (sekcja 6D.4a, testy 0c):
//
//   Czy zapotrzebowanie liczone przez Subiekta ROZWIJA komplety na skladniki,
//   czy zwraca sam komplet?
//
// Ma to znaczenie, bo dzis most wysyla na ZK komplet ORAZ jego skladniki jako
// osobne, plaskie pozycje. Jesli zapotrzebowanie na czesci bierze sie wlasnie
// z tych plaskich wierszy, to usuniecie ich z zasiewu (wariant 1) wyzerowaloby
// zapotrzebowanie — i trzeba przejsc na kalkulator z ObslugaKompletow.
//
// Porownujemy dwie sciezki na TYCH SAMYCH danych:
//   A) ZapotrzebowanieNaAsortyment()  — to, czego tryb "zapotrzebowanie" uzywa dzis
//   B) IKalkulatorZapotrzebowania z MetodaWyliczaniaKZD.ObslugaKompletow
//      w trzech wariantach: WstawKomplety / ZamowSkladniki / Pomin
//
// Dodatkowo rozpisujemy sklad kompletow z KARTOTEKI (SkladnikiKompletu),
// zeby dalo sie recznie sprawdzic, czy liczby z (B) faktycznie odpowiadaja
// ilosc_kompletu * ilosc_skladnika — takze dla kompletow ZAGNIEZDZONYCH
// (KT-A zawiera KT-B), co jest drugim pytaniem testu 0c.
//
// NIC NIE ZAPISUJE. Mozna uruchamiac na bazie produkcyjnej.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class ZapotrzebowanieTest
{
    public static int Uruchom(Uchwyt sfera, string? outPath)
    {
        var wynik = new Dictionary<string, object?>();
        var uwagi = new List<string>();

        // ── A. Metoda uzywana DZIS ────────────────────────────────────────
        var metodaA = new List<PozTest>();
        try
        {
            var zam = sfera.ZamowieniaOdKlientow();
            foreach (var p in zam.ZapotrzebowanieNaAsortyment())
            {
                var sym = Bezp(() => (string?)Wlasc(p, "Symbol"))
                          ?? Bezp(() => (string?)Wlasc(Wlasc(p, "Asortyment"), "Symbol"));
                decimal ile = 0m;
                try { ile = Convert.ToDecimal(Wlasc(p, "Zapotrzebowanie") ?? 0m); } catch { }
                if (!string.IsNullOrWhiteSpace(sym))
                    metodaA.Add(new PozTest(sym!.Trim(), ile, RodzajKartoteki(sfera, sym!.Trim())));
            }
        }
        catch (Exception e)
        {
            uwagi.Add($"ZapotrzebowanieNaAsortyment() nie zadzialalo: {e.GetType().Name}: {e.Message}");
        }

        // ── B. Kalkulator z jawna obsluga kompletow ───────────────────────
        // Nazwy typow i wlasciwosci szukane REFLEKSJA, bo nie znamy z gory
        // dokladnej sygnatury w tej wersji Sfery — a chodzi o diagnostyke,
        // ktora ma zadzialac albo uczciwie powiedziec, ze sie nie da.
        var metodaB = new Dictionary<string, List<PozTest>>();
        foreach (var wariant in new[] { "WstawKomplety", "ZamowSkladniki", "Pomin" })
        {
            try
            {
                var lista = PoliczKalkulatorem(sfera, wariant, out var blad);
                if (lista != null)
                    metodaB[wariant] = lista;
                else
                    uwagi.Add($"Kalkulator [{wariant}]: {blad}");
            }
            catch (Exception e)
            {
                uwagi.Add($"Kalkulator [{wariant}] wyjatek: {e.GetType().Name}: {e.Message}");
            }
        }

        // ── C. Sklady kompletow z KARTOTEK ────────────────────────────────
        // Zrodlo prawdy do recznego sprawdzenia mnozenia i zagniezdzen.
        var komplety = new List<KompletTest>();
        try
        {
            var asort = sfera.Asortymenty();
            foreach (var a in asort.Dane.Wszystkie())
            {
                if (!CzyKomplet(a)) continue;

                var skl = new List<SkladTest>();
                try
                {
                    var lista = Wlasc(a, "SkladnikiKompletu") as System.Collections.IEnumerable;
                    if (lista != null)
                        foreach (var s in lista)
                        {
                            var sym = Bezp(() => (string?)Wlasc(Wlasc(s, "Skladnik"), "Symbol"));
                            decimal ile = 0m;
                            try { ile = Convert.ToDecimal(Wlasc(s, "Ilosc") ?? 0m); } catch { }
                            if (!string.IsNullOrWhiteSpace(sym))
                                skl.Add(new SkladTest(sym!.Trim(), ile,
                                                      RodzajKartoteki(sfera, sym!.Trim())));
                        }
                }
                catch { }
                if (skl.Count > 0)
                    komplety.Add(new KompletTest((a.Symbol ?? "").Trim(), skl.Count, skl));
            }
        }
        catch (Exception e)
        {
            uwagi.Add($"Odczyt skladow kompletow nie zadzialal: {e.GetType().Name}: {e.Message}");
        }

        // ── D. Wniosek ────────────────────────────────────────────────────
        // Czy w metodzie A wystepuja KOMPLETY? Jesli tak — nie rozwija ich.
        var kompletyWA = metodaA.Where(p => p.Rodzaj == "KOMPLET").Select(p => p.Symbol).Take(10).ToList();
        var zagniezdzone = komplety
            .Where(k => k.Skladniki.Any(s => s.Rodzaj == "KOMPLET"))
            .Select(k => k.Symbol).Take(10).ToList();

        wynik["metoda_A_ZapotrzebowanieNaAsortyment"] = new
        {
            pozycji = metodaA.Count,
            kompletow_w_wyniku = metodaA.Count(p => p.Rodzaj == "KOMPLET"),
            przyklady_kompletow = kompletyWA,
            probka = metodaA.Take(15),
        };
        wynik["metoda_B_kalkulator"] = metodaB.ToDictionary(
            kv => kv.Key,
            kv => (object)new
            {
                pozycji = kv.Value.Count,
                kompletow_w_wyniku = kv.Value.Count(p => p.Rodzaj == "KOMPLET"),
                probka = kv.Value.Take(15),
            });
        wynik["komplety_w_katalogu"] = new
        {
            ile = komplety.Count,
            zagniezdzone_przyklady = zagniezdzone,
            ile_zagniezdzonych = komplety.Count(k => k.Skladniki.Any(s => s.Rodzaj == "KOMPLET")),
            probka = komplety.Take(10),
        };
        wynik["uwagi"] = uwagi;
        wynik["jak_czytac"] = new[]
        {
            "metoda_A.kompletow_w_wyniku > 0  => A NIE rozwija kompletow (zwraca sam komplet)",
            "porownaj metoda_B[ZamowSkladniki].pozycji z metoda_B[WstawKomplety].pozycji",
            "  — jesli ZamowSkladniki ma WIECEJ pozycji i 0 kompletow, rozwijanie dziala",
            "zagniezdzone_przyklady: sprawdz recznie, czy skladniki KT-B tez wyszly w ZamowSkladniki",
        };

        var json = JsonSerializer.Serialize(wynik, new JsonSerializerOptions
        {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    /// Liczy zapotrzebowanie kalkulatorem z zadanym trybem obslugi kompletow.
    /// Zwraca null + powod, gdy tej sciezki nie ma w tej wersji Sfery.
    static List<PozTest>? PoliczKalkulatorem(Uchwyt sfera, string wariant, out string blad)
    {
        blad = "";
        // Typ metody wyliczania i enum obslugi kompletow — po nazwie, bo
        // dokladny namespace roznil sie miedzy wersjami.
        var asmy = AppDomain.CurrentDomain.GetAssemblies();
        Type? tMetoda = null, tEnum = null;
        foreach (var a in asmy)
        {
            try
            {
                tMetoda ??= a.GetTypes().FirstOrDefault(t => t.Name == "MetodaWyliczaniaKZD");
                tEnum ??= a.GetTypes().FirstOrDefault(t => t.Name == "ObslugaKompletowDlaKZD");
            }
            catch { }
            if (tMetoda != null && tEnum != null) break;
        }
        if (tMetoda == null) { blad = "brak typu MetodaWyliczaniaKZD"; return null; }
        if (tEnum == null) { blad = "brak typu ObslugaKompletowDlaKZD"; return null; }

        // PodajObiektTypu<T> jest generyczna — typ interfejsu znamy dopiero
        // w runtime, wiec domykamy ja refleksja.
        Type? tKalk = null;
        foreach (var a in asmy)
        {
            try { tKalk ??= a.GetTypes().FirstOrDefault(t => t.Name == "IKalkulatorZapotrzebowania"); }
            catch { }
            if (tKalk != null) break;
        }
        if (tKalk == null) { blad = "brak typu IKalkulatorZapotrzebowania"; return null; }

        object? kalkulator = null;
        try
        {
            var podaj = sfera.GetType().GetMethods()
                .FirstOrDefault(m => m.Name == "PodajObiektTypu" && m.IsGenericMethodDefinition);
            if (podaj == null) { blad = "brak PodajObiektTypu<T>"; return null; }
            kalkulator = podaj.MakeGenericMethod(tKalk).Invoke(sfera, null);
        }
        catch (Exception e)
        {
            // Refleksja opakowuje prawdziwy blad w TargetInvocationException —
            // bez rozpakowania widac tylko bezuzyteczne "Exception has been thrown".
            var wew = e;
            while (wew.InnerException != null) wew = wew.InnerException;
            blad = $"PodajObiektTypu<IKalkulatorZapotrzebowania>: {wew.GetType().Name}: {wew.Message}";
            return null;
        }
        if (kalkulator == null) { blad = "IKalkulatorZapotrzebowania = null"; return null; }

        var metoda = Activator.CreateInstance(tMetoda);
        if (metoda == null) { blad = "nie da sie utworzyc MetodaWyliczaniaKZD"; return null; }
        var propObsluga = tMetoda.GetProperty("ObslugaKompletow");
        if (propObsluga == null) { blad = "MetodaWyliczaniaKZD bez ObslugaKompletow"; return null; }
        propObsluga.SetValue(metoda, Enum.Parse(tEnum, wariant));

        var mi = kalkulator.GetType().GetMethods()
            .FirstOrDefault(m => m.Name == "ListaZapotrzebowaniaAsortymentowWgMetodyWyliczania");
        if (mi == null) { blad = "brak metody ListaZapotrzebowaniaAsortymentowWgMetodyWyliczania"; return null; }

        // Sygnatura bywa rozna — podajemy metode wyliczania, reszte domyslnie.
        var pars = mi.GetParameters();
        var args = new object?[pars.Length];
        for (int i = 0; i < pars.Length; i++)
            args[i] = pars[i].ParameterType.IsAssignableFrom(tMetoda) ? metoda
                    : (pars[i].HasDefaultValue ? pars[i].DefaultValue
                    : (pars[i].ParameterType.IsValueType ? Activator.CreateInstance(pars[i].ParameterType) : null));

        var res = mi.Invoke(kalkulator, args) as System.Collections.IEnumerable;
        if (res == null) { blad = "metoda zwrocila null"; return null; }

        var lista = new List<PozTest>();
        foreach (var p in res)
        {
            var sym = Bezp(() => (string?)Wlasc(p, "Symbol"))
                      ?? Bezp(() => (string?)Wlasc(Wlasc(p, "Asortyment"), "Symbol"));
            decimal ile = 0m;
            foreach (var pole in new[] { "Zapotrzebowanie", "Ilosc", "IloscDoZamowienia" })
            {
                var v = Wlasc(p, pole);
                if (v != null) { try { ile = Convert.ToDecimal(v); } catch { } break; }
            }
            if (!string.IsNullOrWhiteSpace(sym))
                lista.Add(new PozTest(sym!.Trim(), ile, RodzajKartoteki(sfera, sym!.Trim())));
        }
        return lista;
    }

    // Cache rodzaju kartoteki — inaczej kazde sprawdzenie to strzal po sieci.
    static readonly Dictionary<string, string> _rodzaje =
        new(StringComparer.OrdinalIgnoreCase);

    static string RodzajKartoteki(Uchwyt sfera, string symbol)
    {
        if (_rodzaje.TryGetValue(symbol, out var r)) return r;
        var wynik = "?";
        try
        {
            var a = sfera.Asortymenty().Dane.WyszukajPoSymbolu(symbol);
            if (a != null) wynik = CzyKomplet(a) ? "KOMPLET" : "TOWAR";
        }
        catch { }
        _rodzaje[symbol] = wynik;
        return wynik;
    }

    /// Czy kartoteka jest KOMPLETEM.
    ///
    /// W SDK to METODA rozszerzajaca `Rodzaj.CzyKomplet()`, nie wlasciwosc —
    /// szukanie jej przez GetProperty zwracalo null i wszystko wychodzilo
    /// jako towar (pierwszy przebieg testu: 0 kompletow przy 25 realnych).
    /// Stad trzy proby po kolei: metoda na Rodzaju, metoda na kartotece,
    /// a na koniec sama nazwa rodzaju.
    static bool CzyKomplet(object? a)
    {
        if (a == null) return false;
        var rodzaj = Wlasc(a, "Rodzaj");
        foreach (var cel in new[] { rodzaj, a })
        {
            if (cel == null) continue;
            try
            {
                var mi = cel.GetType().GetMethod("CzyKomplet", Type.EmptyTypes);
                if (mi != null) return Convert.ToBoolean(mi.Invoke(cel, null) ?? false);
            }
            catch { }
        }
        // Metoda rozszerzajaca — statyczna, przyjmuje rodzaj jako argument.
        if (rodzaj != null)
        {
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                try
                {
                    foreach (var t in asm.GetTypes())
                    {
                        if (!t.IsAbstract || !t.IsSealed) continue;   // tylko klasy statyczne
                        var mi = t.GetMethod("CzyKomplet", new[] { rodzaj.GetType() });
                        if (mi != null) return Convert.ToBoolean(mi.Invoke(null, new[] { rodzaj }) ?? false);
                    }
                }
                catch { }
            }
        }
        return (rodzaj?.ToString() ?? "").IndexOf("komplet", StringComparison.OrdinalIgnoreCase) >= 0;
    }

    static object? Wlasc(object? o, string nazwa)
    {
        if (o == null) return null;
        try
        {
            var p = o.GetType().GetProperty(nazwa);
            if (p != null) return p.GetValue(o);
            foreach (var i in o.GetType().GetInterfaces())
            {
                p = i.GetProperty(nazwa);
                if (p != null) return p.GetValue(o);
            }
        }
        catch { }
        return null;
    }

    static T? Bezp<T>(Func<T?> f) { try { return f(); } catch { return default; } }

    internal record PozTest(string Symbol, decimal Ilosc, string Rodzaj);
    internal record SkladTest(string Symbol, decimal Ilosc, string Rodzaj);
    internal record KompletTest(string Symbol, int IleSkladnikow, List<SkladTest> Skladniki);
}
