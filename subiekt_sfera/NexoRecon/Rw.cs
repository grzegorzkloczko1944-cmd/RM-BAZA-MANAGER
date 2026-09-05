// Tryb "rw" — ROZCHÓD WEWNĘTRZNY: zdejmuje towar ze stanu magazynu. ZAPISUJE.
//
//   NexoRecon.exe rw --plan=rw.json [--out=w.json] [--zapisz]
//
// Bez --zapisz to suchy przebieg: sprawdza kartoteki i mówi, co by wydał.
//
// plan.json:
//   { "pozycje": [ {"symbol":"011-100.49", "ilosc": 3} ],
//     "uwagi": "MAGAZYN: zuzyte / uszkodzone",
//     "magazyn": "MAG" }
//
// Po co: magazynier zdejmuje z magazynu to, czego fizycznie już nie ma —
// zużyte, uszkodzone, wydane bez dokumentu. Do tej pory robił to na
// karteczkach (ostatnie realne RW: lipiec 2023, patrz
// SUBIEKT_PROJEKTY_WYDANIA.md), więc stany w Subiekcie rozjeżdżały się
// z półką. RW zostawia ślad: kto, kiedy, ile, dlaczego (Uwagi).
//
// To NIE jest „usuń kartotekę" — indeks i historia zostają, znika tylko stan.
// Kasowanie kartoteki to osobny tryb (kartoteka-usun) i Subiekt pozwala na
// nie wyłącznie bez żadnej historii.
//
// Wzorzec tworzenia jak w Zd.cs (Utworz(konfiguracja) + Pozycje.Dodaj),
// z tymi samymi pułapkami: data wystawienia i magazyn trzeba ustawić
// samemu, inaczej dokument istnieje, ale WYPADA Z LIST w Subiekcie.
// Uwagi zapisujemy z odczytem kontrolnym — setter przy jawnej implementacji
// interfejsu potrafi po cichu nic nie zrobić.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Rw
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }
        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
        var pozycje = plan.Pozycje ?? new List<PozPlan>();
        if (pozycje.Count == 0) { Console.WriteLine("Plan bez pozycji."); return 1; }

        var asort = sfera.Asortymenty();
        var kroki = new List<Krok>();
        var doWydania = new List<(string Symbol, decimal Ilosc)>();

        foreach (var p in pozycje)
        {
            var symbol = (p.Symbol ?? "").Trim();
            if (symbol.Length == 0) { kroki.Add(new Krok("pozycja", "", "blad", "pusty symbol")); continue; }
            if (p.Ilosc <= 0)
            {
                kroki.Add(new Krok("pozycja", symbol, "blad", $"ilość {p.Ilosc} — musi być dodatnia"));
                continue;
            }
            dynamic? enc = null;
            try { enc = asort.Dane.WyszukajPoSymbolu(symbol); } catch { }
            if (enc == null) { kroki.Add(new Krok("pozycja", symbol, "blad", "brak kartoteki")); continue; }
            doWydania.Add((symbol, p.Ilosc));
            kroki.Add(new Krok("pozycja", symbol, zapisz ? "do-wydania" : "do-wydania (suchy)", $"{p.Ilosc:0.##}"));
        }

        string? numer = null;
        if (doWydania.Count == 0)
        {
            kroki.Add(new Krok("rw", "", "blad", "żadna pozycja nie nadaje się do wydania"));
        }
        else if (zapisz)
        {
            try
            {
                var rozchody = sfera.RozchodyWewnetrzne();
                var konfig = KonfiguracjaRw(sfera);
                using var rw = konfig != null ? rozchody.Utworz(konfig) : rozchody.Utworz();

                foreach (var (symbol, ilosc) in doWydania)
                {
                    var enc = asort.Dane.WyszukajPoSymbolu(symbol);
                    rw.Pozycje.Dodaj(enc.Symbol, ilosc);
                }

                // Ta sama pułapka co przy ZD: bez daty wystawienia i magazynu
                // dokument jest w bazie, ale nie widać go na listach.
                try
                {
                    // `rw` jest dynamic (Utworz z konfiguracją znalezioną refleksją),
                    // więc porównanie z gołym `default` nie ma typu — stąd DateTime.
                    if ((DateTime)rw.Dane.DataWydaniaWystawienia == default(DateTime))
                        rw.Dane.DataWydaniaWystawienia = DateTime.Today;
                }
                catch { }
                try
                {
                    var magazyny = sfera.Magazyny().Dane.Wszystkie().ToList();
                    var chciany = (plan.Magazyn ?? "MAG").Trim();
                    rw.Dane.Magazyn = magazyny.FirstOrDefault(m =>
                            string.Equals((Bezp(() => m.Symbol) ?? "").Trim(), chciany,
                                          StringComparison.OrdinalIgnoreCase))
                        ?? magazyny.FirstOrDefault();
                }
                catch { }

                if (!string.IsNullOrWhiteSpace(plan.Uwagi))
                    UstawUwagi(rw.Dane, plan.Uwagi.Trim(), kroki);

                if (!rw.Zapisz())
                {
                    // RozchodWewnetrznyBO nie ma PodajBledy() — patrz
                    // BledyDokumentu. Gdy Subiekt nie poda powodu, mowimy
                    // przynajmniej, na czym operacja stanela.
                    var magazyn = Bezp(() => (string?)rw.Dane.Magazyn?.Symbol) ?? "?";
                    kroki.Add(new Krok("rw", "", "blad",
                        BledyDokumentu((object)rw)
                        ?? $"Subiekt odrzucil zapis RW bez podania powodu "
                           + $"(magazyn {magazyn}, {doWydania.Count} poz.). "
                           + "Najczestsze przyczyny: brak stanu na magazynie, "
                           + "kartoteka bez ceny ewidencyjnej, zamkniety okres."));
                }
                else
                {
                    numer = Bezp(() => rw.Dane.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                    kroki.Add(new Krok("rw", numer, $"utworzone ({doWydania.Count} poz.)", null));
                }
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok("rw", "", "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(new { zapisano = zapisz, numer, kroki },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    /// Konfiguracja domyślna RW — nazwa właściwości w DaneDomyslne nie jest
    /// udokumentowana (dla ZD to „ZamowienieDoDostawcy"), więc szukamy po
    /// „Rozchod" refleksją; null = Utworz() bez konfiguracji.
    static dynamic? KonfiguracjaRw(Uchwyt sfera)
    {
        try
        {
            object dd = sfera.Konfiguracje().DaneDomyslne;
            var t = dd.GetType();
            // Po TYPIE, nie tylko po nazwie: pierwsza wersja brała pierwszą
            // właściwość z "RozchodWewn" w nazwie i trafiała w konfigurację pól
            // własnych — Utworz() odrzucał ją jako "invalid arguments"
            // (05.09.2026). Utworz przyjmuje wyłącznie ModelDanych.Konfiguracja.
            var typKonfig = typeof(InsERT.Moria.ModelDanych.Konfiguracja);
            var prop = t.GetProperties()
                .Concat(t.GetInterfaces().SelectMany(i => i.GetProperties()))
                .Where(p => typKonfig.IsAssignableFrom(p.PropertyType))
                .FirstOrDefault(p => p.Name.Equals("RozchodWewnetrzny", StringComparison.OrdinalIgnoreCase))
                ?? t.GetProperties()
                .Concat(t.GetInterfaces().SelectMany(i => i.GetProperties()))
                .Where(p => typKonfig.IsAssignableFrom(p.PropertyType))
                .FirstOrDefault(p => p.Name.Contains("Rozchod", StringComparison.OrdinalIgnoreCase));
            return prop?.GetValue(dd);
        }
        catch { return null; }
    }

    static void UstawUwagi(object dane, string chciane, List<Krok> kroki)
    {
        string? mam = null;
        try { ((dynamic)dane).Uwagi = chciane; mam = ((dynamic)dane).Uwagi; } catch { }
        if (mam != chciane)
        {
            foreach (var i in dane.GetType().GetInterfaces())
            {
                var pr = i.GetProperty("Uwagi");
                if (pr == null || !pr.CanWrite) continue;
                try { pr.SetValue(dane, chciane); mam = pr.GetValue(dane) as string; } catch { }
                if (mam == chciane) break;
            }
        }
        if (mam != chciane)
            kroki.Add(new Krok("rw", "", "uwaga", $"nie udało się ustawić Uwag (odczyt: \"{mam}\")"));
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    /// <summary>
    /// Bledy walidacji dokumentu — o ile ten typ w ogole je udostepnia.
    ///
    /// RozchodWewnetrznyBO NIE ma PodajBledy(), w przeciwienstwie do BO
    /// kartoteki czy ZD. Wywolanie `Bezp(rw.PodajBledy)` wygladalo na
    /// zabezpieczone, ale nie bylo: konwersja `rw.PodajBledy` (dynamic) na
    /// Func&lt;string?&gt; leci PRZED wejsciem do Bezp, wiec RuntimeBinderException
    /// wychodzil na zewnatrz, wpadal w catch calego zapisu i PRZYKRYWAL
    /// prawdziwy powod, dla ktorego Zapisz() zwrocilo false. Uzytkownik
    /// widzial "does not contain a definition for 'PodajBledy'" zamiast
    /// informacji, czego brakuje na dokumencie (zgloszone 06.09.2026).
    ///
    /// Dlatego pytamy refleksja: brak metody = brak dodatkowych szczegolow,
    /// a nie wyjatek.
    /// </summary>
    static string? BledyDokumentu(object? bo)
    {
        if (bo is null) return null;
        try
        {
            var met = bo.GetType().GetMethod("PodajBledy", Type.EmptyTypes);
            if (met is null) return null;
            var w = met.Invoke(bo, null);
            var tekst = w switch
            {
                null => null,
                string s => s,
                System.Collections.IEnumerable e when w is not string
                    => string.Join("; ", e.Cast<object?>().Select(x => x?.ToString())
                                          .Where(x => !string.IsNullOrWhiteSpace(x))),
                _ => w.ToString(),
            };
            return string.IsNullOrWhiteSpace(tekst) ? null : tekst;
        }
        catch
        {
            return null;      // diagnostyka nie moze przykryc wlasciwego bledu
        }
    }

    internal record PozPlan(string? Symbol, decimal Ilosc);
    internal record Plan(List<PozPlan>? Pozycje, string? Uwagi, string? Magazyn);
    internal record Krok(string Rodzaj, string Symbol, string Status, string? Szczegoly);
}
