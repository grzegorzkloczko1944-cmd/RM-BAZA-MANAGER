// Tryb "pw" — PRZYCHÓD WEWNĘTRZNY: dodaje towar na stan magazynu. ZAPISUJE.
//
//   NexoRecon.exe pw --plan=pw.json [--out=w.json] [--zapisz]
//
// Bez --zapisz to suchy przebieg: sprawdza kartoteki i mówi, co by przyjął.
//
// plan.json:
//   { "pozycje": [ {"symbol":"011-100.49", "ilosc": 3} ],
//     "uwagi": "Stany startowe magazynu nr 2 - inwentaryzacja 28.05.2026",
//     "magazyn": "Magazyn" }
//
// Po co: uruchomienie magazynu nr 2 (SUBIEKT PODWÓJNE POZYCJE DO NAPRAWY.md,
// MAGAZYN.md) — inwentaryzacja z Excela ma wejść jako stan startowy. Pozycje
// mają TE SAME symbole co już istniejące kartoteki (ustalone z użytkownikiem:
// "te pozycje są z magazynu wyciągnięte... a w nowym magazynie one dalej będą
// tymi samymi pozycjami, bo mają te same symbole") — PW więc NIE zakłada
// nowych kartotek, tylko dopisuje stan istniejącym, po Symbolu. Kartoteki bez
// odpowiednika (patrz arkusz "Brak w Subiekcie") są tu pomijane z jasnym
// powodem — ich założenie to osobna decyzja (tryb "kartoteka").
//
// Lustrzane odbicie Rw.cs (ROZCHÓD): ta sama struktura planu, ten sam wzorzec
// Utworz(konfiguracja) + Pozycje.Dodaj, te same pułapki (data wystawienia
// i magazyn trzeba ustawić samemu, inaczej dokument wypada z list). Różnica:
// IPrzychodyWewnetrzne zamiast IRozchodyWewnetrzne, DataWydaniaWystawienia
// zamiast tego samego pola (Dokument ma jedno wspólne pole dla obu kierunków).

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Pw
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
        var doPrzyjecia = new List<(string Symbol, decimal Ilosc)>();

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
            doPrzyjecia.Add((symbol, p.Ilosc));
            kroki.Add(new Krok("pozycja", symbol, zapisz ? "do-przyjecia" : "do-przyjecia (suchy)", $"{p.Ilosc:0.##}"));
        }

        string? numer = null;
        if (doPrzyjecia.Count == 0)
        {
            kroki.Add(new Krok("pw", "", "blad", "żadna pozycja nie nadaje się do przyjęcia"));
        }
        else if (zapisz)
        {
            try
            {
                var przychody = sfera.PrzychodyWewnetrzne();
                var konfig = KonfiguracjaPw(sfera);
                using var pw = konfig != null ? przychody.Utworz(konfig) : przychody.Utworz();

                foreach (var (symbol, ilosc) in doPrzyjecia)
                {
                    var enc = asort.Dane.WyszukajPoSymbolu(symbol);
                    pw.Pozycje.Dodaj(enc.Symbol, ilosc);
                }

                // Ta sama pułapka co w Rw.cs / Zd.cs: bez daty wystawienia
                // i magazynu dokument jest w bazie, ale nie widać go na listach.
                try
                {
                    if ((DateTime)pw.Dane.DataWydaniaWystawienia == default(DateTime))
                        pw.Dane.DataWydaniaWystawienia = DateTime.Today;
                }
                catch { }
                try
                {
                    var magazyny = sfera.Magazyny().Dane.Wszystkie().ToList();
                    // Fallback gdy plan nie poda magazynu — "Magazyn" (nr 2),
                    // ten sam co w Rw.cs, Zd.cs i subiekt_magazyn_gui.py.
                    var chciany = (plan.Magazyn ?? "Magazyn").Trim();
                    pw.Dane.Magazyn = magazyny.FirstOrDefault(m =>
                            string.Equals((Bezp(() => m.Symbol) ?? "").Trim(), chciany,
                                          StringComparison.OrdinalIgnoreCase))
                        ?? magazyny.FirstOrDefault();
                }
                catch { }

                if (!string.IsNullOrWhiteSpace(plan.Uwagi))
                    UstawUwagi(pw.Dane, plan.Uwagi.Trim(), kroki);

                if (!pw.Zapisz())
                {
                    var magazyn = Bezp(() => (string?)pw.Dane.Magazyn?.Symbol) ?? "?";
                    kroki.Add(new Krok("pw", "", "blad",
                        BledyDokumentu((object)pw)
                        ?? $"Subiekt odrzucil zapis PW bez podania powodu "
                           + $"(magazyn {magazyn}, {doPrzyjecia.Count} poz.)."));
                }
                else
                {
                    numer = Bezp(() => pw.Dane.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                    kroki.Add(new Krok("pw", numer, $"utworzone ({doPrzyjecia.Count} poz.)", null));
                }
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok("pw", "", "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        // zapisano = czy PW FAKTYCZNIE powstalo, nie "czy proszono o zapis" — ta sama
        // pulapka co w Rw.cs (odrzucony zapis nie moze wygladac jak sukces).
        var json = JsonSerializer.Serialize(
            new { zapisano = zapisz && !string.IsNullOrEmpty(numer), numer, kroki },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    /// Konfiguracja domyślna PW — wzorem KonfiguracjaRw w Rw.cs: szukamy po
    /// typie (ModelDanych.Konfiguracja), nie tylko po nazwie właściwości.
    static dynamic? KonfiguracjaPw(Uchwyt sfera)
    {
        try
        {
            object dd = sfera.Konfiguracje().DaneDomyslne;
            var t = dd.GetType();
            var typKonfig = typeof(InsERT.Moria.ModelDanych.Konfiguracja);
            var prop = t.GetProperties()
                .Concat(t.GetInterfaces().SelectMany(i => i.GetProperties()))
                .Where(p => typKonfig.IsAssignableFrom(p.PropertyType))
                .FirstOrDefault(p => p.Name.Equals("PrzychodWewnetrzny", StringComparison.OrdinalIgnoreCase))
                ?? t.GetProperties()
                .Concat(t.GetInterfaces().SelectMany(i => i.GetProperties()))
                .Where(p => typKonfig.IsAssignableFrom(p.PropertyType))
                .FirstOrDefault(p => p.Name.Contains("Przychod", StringComparison.OrdinalIgnoreCase));
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
            kroki.Add(new Krok("pw", "", "uwaga", $"nie udało się ustawić Uwag (odczyt: \"{mam}\")"));
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    /// Wzorem BledyDokumentu w Rw.cs — refleksja, brak metody PodajBledy()
    /// nie może wywalać wyjątku, żeby nie przykryć prawdziwego powodu odrzucenia.
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
            return null;
        }
    }

    internal record PozPlan(string? Symbol, decimal Ilosc);
    internal record Plan(List<PozPlan>? Pozycje, string? Uwagi, string? Magazyn);
    internal record Krok(string Rodzaj, string Symbol, string Status, string? Szczegoly);
}
