// Tryb "zd" — tworzy zamówienia do dostawców z wybranych pozycji. ZAPISUJE.
//
//   NexoRecon.exe zd --plan=zd.json [--out=wynik.json] --zapisz
//
// Bez --zapisz to suchy przebieg (mówi co by zrobił, nic nie zapisuje).
//
// plan.json (buduje go subiekt_zamowienia.py):
//   { "pozycje": [ {"symbol":"013-100.22X", "ilosc":4, "dostawca":"NAZWA"} ] }
//
// ⚠️ ZD MUSI powstać przez UtworzNaPodstawieZapotrzebowania() — inaczej nie ma
// powiązania z ZK i Subiekt dalej uważa zamówienie klienta za niezrealizowane.
// Pierwsza wersja tworzyła ZD wprost (Utworz(konfiguracja) + Pozycje.Dodaj),
// bo most jest bezstanowy i nie da się przenieść obiektów
// PozycjaZestawieniaZapotrzebowania między wywołaniami procesu. Efekt
// (04.09.2026): ZD 5 i 6/09/2026 powstały poprawnie, ale te same pozycje
// wciąż wisiały w zapotrzebowaniu — wyglądało to, jakby zamówienie zniknęło.
//
// Rozwiązanie: zapotrzebowanie pobieramy i realizujemy w JEDNYM uruchomieniu.
// Plan z Pythona wskazuje pozycje po symbolu; tutaj dopasowujemy je do świeżo
// pobranego zestawienia i przekazujemy Sferze oryginalne obiekty.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Dokumenty.Logistyka;   // PozycjaZestawieniaZapotrzebowania
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Zd
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }

        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
        var pozycje = plan.Pozycje ?? new List<PozPlan>();
        if (pozycje.Count == 0) { Console.WriteLine("Plan bez pozycji."); return 1; }

        var zamowieniaZk = sfera.ZamowieniaOdKlientow();
        var zamowienia = sfera.ZamowieniaDoDostawcow();
        var kroki = new List<Krok>();
        var utworzone = new List<Zam>();

        // Podmioty raz do pamięci — dopasowanie po nazwie skróconej, jak w Projekt.cs.
        var firmy = sfera.Podmioty().Dane.WszystkieFirmy().ToList();

        Podmiot? ZnajdzDostawce(string nazwa)
        {
            var s = (nazwa ?? "").Trim();
            if (s.Length == 0) return null;
            return firmy.FirstOrDefault(p => string.Equals((p.NazwaSkrocona ?? "").Trim(), s,
                                                           StringComparison.OrdinalIgnoreCase))
                ?? firmy.FirstOrDefault(p => (p.NazwaSkrocona ?? "").Contains(s,
                                                           StringComparison.OrdinalIgnoreCase));
        }

        // Świeże zestawienie — to z niego biorą się obiekty, które Sfera potrafi
        // powiązać z ZK. Plan z Pythona tylko WSKAZUJE, które z nich zamówić
        // i u kogo.
        var zestawienie = zamowieniaZk.ZapotrzebowanieNaAsortyment();
        var wgSymbolu = new Dictionary<string, PozycjaZestawieniaZapotrzebowania>(
            StringComparer.OrdinalIgnoreCase);
        foreach (var z in zestawienie)
        {
            var sym = Bezp(() => z.Asortyment?.Symbol)?.Trim();
            if (!string.IsNullOrEmpty(sym)) wgSymbolu[sym] = z;
        }

        var doRealizacji = new List<PozycjaZestawieniaZapotrzebowania>();
        var brakujace = new List<string>();

        foreach (var p in pozycje)
        {
            var symbol = (p.Symbol ?? "").Trim();
            var nazwaDostawcy = (p.Dostawca ?? "").Trim();
            if (nazwaDostawcy.Length == 0)
            {
                kroki.Add(new Krok("pozycja", symbol, "blad", "brak dostawcy"));
                continue;
            }
            var podmiot = ZnajdzDostawce(nazwaDostawcy);
            if (podmiot == null)
            {
                kroki.Add(new Krok("pozycja", symbol, "blad",
                    $"nie znaleziono podmiotu „{nazwaDostawcy}” w Subiekcie"));
                continue;
            }
            if (!wgSymbolu.TryGetValue(symbol, out var poz))
            {
                // Pozycji nie ma już w zapotrzebowaniu — ktoś ją w międzyczasie
                // zamówił albo wydał. Lepiej pominąć niż utworzyć duplikat.
                brakujace.Add(symbol);
                kroki.Add(new Krok("pozycja", symbol, "blad",
                    "nie ma jej już w zapotrzebowaniu (zamówiona lub wydana w międzyczasie)"));
                continue;
            }

            // Właściwości pozycji zestawienia są read-only, więc dostawcę
            // i ilość z okna wnosimy przez konstruktor. PozycjeZK przepisujemy
            // z oryginału — to one wiążą ZD z zamówieniem klienta.
            doRealizacji.Add(new PozycjaZestawieniaZapotrzebowania(
                poz.Asortyment,
                p.Ilosc > 0 ? p.Ilosc : poz.Ilosc,
                poz.JednostkaMiary,
                podmiot,
                poz.PozycjeZK));
            kroki.Add(new Krok("pozycja", symbol,
                zapisz ? "do-zamowienia" : "do-utworzenia", nazwaDostawcy));
        }

        if (doRealizacji.Count == 0)
        {
            kroki.Add(new Krok("zd", "", "blad", "brak pozycji do zamówienia"));
        }
        else if (zapisz)
        {
            try
            {
                // Sfera sama grupuje po dostawcy I zakłada powiązanie z ZK —
                // dzięki temu pozycje znikają z zapotrzebowania po zamówieniu.
                foreach (var zd in zamowienia.UtworzNaPodstawieZapotrzebowania(doRealizacji))
                {
                    using (zd)
                    {
                        var dostawca = Bezp(() => zd.Dane.Podmiot?.NazwaSkrocona) ?? "";

                        // ⚠️ UtworzNaPodstawieZapotrzebowania NIE wypełnia daty
                        // wystawienia ani magazynu. Dokument bez daty wystawienia
                        // istnieje w bazie, ale WYPADA Z LIST w Subiekcie (filtrują
                        // po tej dacie i po zakresie „bieżące") — user go po prostu
                        // nie widzi. Zgłoszone 04.09.2026: „w subiekcie nie widzę
                        // tych z RM_BAZA", choć most je zwracał.
                        try
                        {
                            if (zd.Dane.DataWydaniaWystawienia == default)
                                zd.Dane.DataWydaniaWystawienia = DateTime.Today;
                        }
                        catch { /* pole opcjonalne w niektórych konfiguracjach */ }

                        try
                        {
                            if (zd.Dane.Magazyn == null)
                                zd.Dane.Magazyn = sfera.Magazyny().Dane.Wszystkie()
                                    .FirstOrDefault(m => m.Symbol == "MAG")
                                    ?? sfera.Magazyny().Dane.Wszystkie().FirstOrDefault();
                        }
                        catch { /* ZD bywa bez magazynu — nie blokujemy zapisu */ }

                        if (!zd.Zapisz())
                        {
                            kroki.Add(new Krok("zd", dostawca, "blad", Bezp(zd.PodajBledy)));
                            continue;
                        }
                        var numer = Bezp(() => zd.Dane.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                        var ile = 0;
                        try { ile = zd.Dane.Pozycje.Count(); } catch { }
                        utworzone.Add(new Zam(numer, dostawca, ile));
                        kroki.Add(new Krok("zd", dostawca, $"utworzone {numer} ({ile} poz.)", null));
                    }
                }
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok("zd", "", "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(new { zapisano = zapisz, zd = utworzone, kroki },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record PozPlan(string Symbol, decimal Ilosc, string? Dostawca);
    internal record Plan(List<PozPlan>? Pozycje);
    internal record Zam(string Numer, string Dostawca, int Pozycji);
    internal record Krok(string Rodzaj, string Symbol, string Status, string? Szczegoly);
}
