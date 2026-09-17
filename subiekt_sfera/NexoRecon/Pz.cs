// Tryb "pz" — POMIAR przyjęć zewnętrznych. WYŁĄCZNIE ODCZYT, nic nie zapisuje.
//
//   NexoRecon.exe pz [--limit=60] [--out=w.json]
//
// Pytanie, na które odpowiada (17.09.2026), zanim ktokolwiek napisze zapis PZ:
// co Subiekt NAPRAWDĘ tworzy przy FZ ze skutkiem magazynowym i jakie relacje
// zapisuje sam. Bez tego grozi dorobienie własnej tabeli powiązań obok tej,
// którą Subiekt już prowadzi.
//
// Konkretnie mierzymy:
//   * ile PZ w ogóle jest i z jakiego okresu,
//   * czy jedna FZ = jeden PZ (`NumeryDokumentowRealizowanych` / `...Zewnetrznych`),
//   * czy widać powiązanie z ZD,
//   * ile pozycji PZ ma dopasowany asortyment, a ile weszło „luźnym tekstem",
//   * jaką datę magazynową niesie dokument,
//   * jakie pola relacji Sfera w ogóle wystawia (refleksja — CHM indeksuje część).
//
// Wzorzec ten sam co w Faktury.cs: encje na pozycjach przychodzą jako Detached,
// więc symbol czytamy z mapy Id → symbol zbudowanej jednym przelotem.

using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Pz
{
    public static int Uruchom(Uchwyt sfera, int limit, string? outPath)
    {
        var wynik = new List<DokPz>();

        var wgId = new Dictionary<int, (string Symbol, string Nazwa)>();
        try
        {
            foreach (var a in sfera.Asortymenty().Dane.Wszystkie()
                                   .Select(a => new { a.Id, a.Symbol, a.Nazwa }).ToList())
                wgId[a.Id] = ((a.Symbol ?? "").Trim(), (a.Nazwa ?? "").Trim());
        }
        catch { }

        // Diagnostyka pól: które właściwości relacyjne Sfera faktycznie wystawia
        // na PZ. Zgadywanie nazw kosztowało już kilka nieudanych kompilacji
        // (patrz ten sam komentarz w Faktury.cs).
        try
        {
            var pierwszy = sfera.PrzyjeciaZewnetrzne().Dane.Wszystkie().Take(1).ToList().FirstOrDefault();
            if (pierwszy != null)
            {
                var t = pierwszy.GetType();
                var tekst = t.GetProperties()
                    .Where(x => x.PropertyType == typeof(string))
                    .Select(x => x.Name).OrderBy(x => x).ToList();
                Console.WriteLine("POLA TEKSTOWE PZ: " + string.Join(", ", tekst));

                Console.WriteLine("POLA RELACYJNE PZ (nazwa = wartosc):");
                foreach (var pi in t.GetProperties().OrderBy(x => x.Name))
                {
                    var n = pi.Name;
                    if (!n.Contains("Realizow", StringComparison.OrdinalIgnoreCase)
                        && !n.Contains("Powiaz", StringComparison.OrdinalIgnoreCase)
                        && !n.Contains("Zrodl", StringComparison.OrdinalIgnoreCase)
                        && !n.Contains("Nadrzed", StringComparison.OrdinalIgnoreCase)
                        && !n.Contains("Zamowien", StringComparison.OrdinalIgnoreCase)
                        && !n.Contains("Dokument", StringComparison.OrdinalIgnoreCase)) continue;
                    string v;
                    try { v = pi.GetValue(pierwszy)?.ToString() ?? "(null)"; }
                    catch (Exception e) { v = "!" + e.GetType().Name; }
                    Console.WriteLine($"   {n,-42} = {(v.Length > 70 ? v[..70] : v)}");
                }

                try
                {
                    var poz = pierwszy.Pozycje.Take(1).ToList().FirstOrDefault();
                    if (poz != null)
                    {
                        Console.WriteLine("TYP POZYCJI PZ: " + poz.GetType().Name);
                        foreach (var pi in poz.GetType().GetProperties().OrderBy(x => x.Name))
                        {
                            var n = pi.Name;
                            if (!n.Contains("Asort", StringComparison.OrdinalIgnoreCase)
                                && !n.Contains("Realizow", StringComparison.OrdinalIgnoreCase)
                                && !n.Contains("Zrodl", StringComparison.OrdinalIgnoreCase)) continue;
                            string v;
                            try { v = pi.GetValue(poz)?.ToString() ?? "(null)"; }
                            catch (Exception e) { v = "!" + e.GetType().Name; }
                            Console.WriteLine($"   {n,-42} = {(v.Length > 70 ? v[..70] : v)}");
                        }
                    }
                }
                catch { }
            }
            else Console.WriteLine("UWAGA: brak jakiegokolwiek PZ w bazie.");
        }
        catch (Exception ex) { Console.WriteLine("diag PZ: " + ex.Message); }

        try
        {
            foreach (var d in sfera.PrzyjeciaZewnetrzne().Dane.Wszystkie()
                                   .OrderByDescending(x => x.DataWprowadzenia)
                                   .Take(limit).ToList())
            {
                var pozycje = new List<PozPz>();
                try
                {
                    foreach (var p in d.Pozycje)
                    {
                        var id = 0;
                        try { id = p.AsortymentAktualnyId ?? 0; } catch { }
                        wgId.TryGetValue(id, out var kart);
                        decimal cena = 0;
                        try { cena = p.Cena.NettoPoRabacie; } catch { }
                        pozycje.Add(new PozPz(
                            id,
                            kart.Symbol ?? "",
                            kart.Nazwa ?? "",
                            Bezp(() => p.Opis) ?? "",
                            p.Ilosc,
                            decimal.Round(cena, 2)));
                    }
                }
                catch { }

                wynik.Add(new DokPz(
                    Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "",
                    Bezp(() => d.NumerZewnetrzny) ?? "",
                    Data(d),
                    Bezp(() => d.Podmiot?.NazwaSkrocona) ?? "",
                    Bezp(() => d.StatusDokumentu?.Nazwa) ?? "",
                    // Kluczowe dla pytania „czy Subiekt sam wie, co z czym":
                    // numery dokumentow, ktore ten PZ realizuje (ZD? FZ?).
                    Bezp(() => d.NumeryDokumentowRealizowanych) ?? "",
                    Bezp(() => d.NumeryZewnetrzneDokumentowRealizowanych) ?? "",
                    Bezp(() => d.Magazyn?.Nazwa) ?? "",
                    Bezp(() => d.Uwagi) ?? "",
                    pozycje.Count,
                    pozycje.Count(p => p.AsortymentId > 0),
                    pozycje));
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine("Blad odczytu PZ: " + ex.Message);
        }

        var json = JsonSerializer.Serialize(new { pz = wynik },
            new JsonSerializerOptions
            {
                WriteIndented = false,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        Console.WriteLine($"PZ odczytanych: {wynik.Count} — NIC NIE ZAPISANO.");
        return 0;
    }

    static string Data(Dokument d) => Bezp(() =>
    {
        var w = d.DataWydaniaWystawienia;
        var dt = w == default ? d.DataWprowadzenia : Convert.ToDateTime(w);
        return dt.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    }) ?? "";

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record PozPz(int AsortymentId, string Symbol, string NazwaKartoteki,
                          string NazwaNaDokumencie, decimal Ilosc, decimal Cena);

    internal record DokPz(string Numer, string NumerZewnetrzny, string Data, string Podmiot,
                          string Status, string Realizuje, string RealizujeZewnetrzne,
                          string Magazyn, string Uwagi,
                          int Pozycji, int Dopasowanych, List<PozPz> Pozycje);
}
