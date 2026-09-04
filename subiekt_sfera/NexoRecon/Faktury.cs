// Tryb "faktury" — rozpoznanie faktur zakupu (FZ). Tylko odczyt.
//
//   NexoRecon.exe faktury [--limit=60] [--out=w.json]
//
// Pytanie, na które odpowiada (04.09.2026): jak dopasować pozycje z faktury
// KSeF do zamówień? Zanim cokolwiek napiszemy, trzeba wiedzieć:
//   * ile FZ ma numer KSeF (czyli przyszło elektronicznie),
//   * czy pozycje mają dopasowany asortyment, czy są „luźnym tekstem",
//   * czy widać powiązanie z ZD/PZ,
//   * jak wyglądają symbole i nazwy na pozycjach — czy da się je dopasować.

using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Faktury
{
    public static int Uruchom(Uchwyt sfera, int limit, string? outPath)
    {
        var wynik = new List<Fak>();

        // Encje asortymentu na pozycjach FZ przychodza jako Detached — odczyt
        // p.AsortymentAktualny.Symbol daje wtedy pustke, mimo ze Id jest
        // wypelnione. Dlatego budujemy mape Id -> symbol jednym przelotem.
        var wgId = new Dictionary<int, (string Symbol, string Nazwa)>();
        try
        {
            foreach (var a in sfera.Asortymenty().Dane.Wszystkie()
                                   .Select(a => new { a.Id, a.Symbol, a.Nazwa }).ToList())
                wgId[a.Id] = ((a.Symbol ?? "").Trim(), (a.Nazwa ?? "").Trim());
        }
        catch { }

        // Jednorazowa diagnostyka: jakie pola ma DokumentDZ i PozycjaDokumentu.
        // Dokumentacja CHM indeksuje tylko czesc, wiec zgadywanie nazw kosztowalo
        // juz kilka nieudanych kompilacji.
        try
        {
            var pierwszy = sfera.DokumentyZakupu().Dane.Wszystkie().Take(1).ToList().FirstOrDefault();
            if (pierwszy != null)
            {
                var pola = pierwszy.GetType().GetProperties()
                    .Where(x => x.PropertyType == typeof(string))
                    .Select(x => x.Name).OrderBy(x => x).ToList();
                Console.WriteLine("POLA TEKSTOWE DokumentDZ: " + string.Join(", ", pola));
                try
                {
                    var poz = pierwszy.Pozycje.Take(1).ToList().FirstOrDefault();
                    if (poz != null)
                    {
                        var t = poz.GetType();
                        Console.WriteLine("TYP POZYCJI: " + t.Name);
                        foreach (var pi in t.GetProperties().OrderBy(x => x.Name))
                        {
                            if (!pi.Name.Contains("Asort", StringComparison.OrdinalIgnoreCase)
                                && !pi.Name.Contains("Nazw", StringComparison.OrdinalIgnoreCase)
                                && !pi.Name.Contains("Symbol", StringComparison.OrdinalIgnoreCase)) continue;
                            string v;
                            try { v = pi.GetValue(poz)?.ToString() ?? "(null)"; } catch (Exception e) { v = "!" + e.GetType().Name; }
                            Console.WriteLine($"   {pi.Name,-34} = {(v.Length > 60 ? v[..60] : v)}");
                        }
                    }
                }
                catch { }
            }
        }
        catch (Exception ex) { Console.WriteLine("diag: " + ex.Message); }

        try
        {
            foreach (var d in sfera.DokumentyZakupu().Dane.Wszystkie()
                                   .OrderByDescending(x => x.DataWprowadzenia)
                                   .Take(limit).ToList())
            {
                var pozycje = new List<PozFak>();
                try
                {
                    foreach (var p in d.Pozycje)
                    {
                        // AsortymentAktualny puste = pozycja NIE dopasowana do
                        // kartoteki (weszła jako tekst). To kluczowa liczba:
                        // mówi, ile roboty zostaje człowiekowi przy imporcie.
                        // Symbol z mapy po Id — patrz komentarz wyzej.
                        var id = 0;
                        try { id = p.AsortymentAktualnyId ?? 0; } catch { }
                        // Uwaga: na fakturach zakupu to pole bywa PUSTE (0) —
                        // patrz wynik rozpoznania 04.09.2026: 0 z 305 pozycji
                        // mialo dopasowany asortyment.
                        wgId.TryGetValue(id, out var kart);
                        decimal cena = 0;
                        try { cena = p.Cena.NettoPoRabacie; } catch { }
                        pozycje.Add(new PozFak(
                            kart.Symbol ?? "",
                            kart.Nazwa ?? "",
                            Bezp(() => p.Opis) ?? "",
                            p.Ilosc,
                            decimal.Round(cena, 2)));
                    }
                }
                catch { }

                wynik.Add(new Fak(
                    Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "",
                    Bezp(() => d.NumerZewnetrzny) ?? "",
                    Data(d),
                    Bezp(() => d.Podmiot?.NazwaSkrocona) ?? "",
                    Bezp(() => d.StatusDokumentu?.Nazwa) ?? "",
                    // Numery zamowien, ktore ta faktura realizuje — Subiekt trzyma
                    // to powiazanie SAM. To odpowiedz na pytanie „jak dopasowac
                    // fakture do ZD": nie trzeba parsowac, wystarczy odczytac.
                    Bezp(() => d.NumeryDokumentowRealizowanych) ?? "",
                    Bezp(() => d.Uwagi) ?? "",
                    pozycje.Count,
                    pozycje.Count(p => p.Symbol.Length > 0),
                    pozycje));
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine("Blad odczytu FZ: " + ex.Message);
        }

        var json = JsonSerializer.Serialize(new { faktury = wynik },
            new JsonSerializerOptions
            {
                WriteIndented = false,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    static string Data(Dokument d) => Bezp(() =>
    {
        var w = d.DataWydaniaWystawienia;
        var dt = w == default ? d.DataWprowadzenia : Convert.ToDateTime(w);
        return dt.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    }) ?? "";

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record PozFak(string Symbol, string NazwaKartoteki, string NazwaNaDokumencie,
                           decimal Ilosc, decimal Cena);

    internal record Fak(string Numer, string NumerOryginalny, string Data, string Podmiot,
                        string Status, string NumerKSeF, string Uwagi,
                        int Pozycji, int Dopasowanych, List<PozFak> Pozycje);
}
