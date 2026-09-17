// Tryb "symbole-dostawcy" — powiazanie SYMBOLU DOSTAWCY z kartoteka. ZAPISUJE.
//
//   NexoRecon.exe symbole-dostawcy --plan=plan.json [--out=w.json] [--zapisz]
//
// Bez --zapisz suchy przebieg: mowi, co by powiazal, nic nie zapisuje.
//
// plan.json:
//   { "powiazania": [ {"nip":"9721002583", "symbolDostawcy":"688 2Z-8x16x5",
//                      "symbol":"688 ZZ", "asortymentId":100591,
//                      "nazwaUDostawcy":"..."} ] }
//
// ⚠️ PO CO TO ISTNIEJE — i dlaczego NIE wlasna tabela (17.09.2026).
//
// Dostawca nazywa towar po swojemu: na fakturze QUAY jest `688 2Z-8x16x5`,
// a w kartotece ten sam lozysko nazywa sie `688 ZZ`. Zeby pozycja faktury
// trafila na wlasciwa kartoteke, ktos musi RAZ powiedziec, ze to to samo.
//
// Sfera ma na to gotowy mechanizm i nie trzeba go dublowac:
//
//   DaneAsortymentuDlaPodmiotu.Symbol  — „Symbol asortymentu dla powiazanego
//                                         podmiotu" (1..64 znaki)
//   DaneAsortymentuDlaPodmiotu.Nazwa   — nazwa u tego dostawcy
//   IAsortymentyDane.WyszukajPoSymboluDostawcy(symbol, podmiot)
//                                      — wyszukuje asortyment po tym symbolu
//
// Czyli para (dostawca, symbol) -> kartoteka JEST w Subiekcie. Wlasna tabela
// powtarzalaby to, co system juz prowadzi — ten sam blad, przed ktorym
// ostrzega notatka o relacjach dokumentow („Subiekt trzyma je SAM").
// Dodatkowa korzysc: raz zapisane powiazanie widzi takze Subiekt przy
// zwyklym wystawianiu dokumentow, nie tylko RM_BAZA.
//
// ⚠️ Powiazanie jest ODWRACALNE — inaczej niz symbol nowej kartoteki, ktorego
// po zapisie nie da sie zmienic. Dlatego ten tryb jest bezpieczniejszy niz
// zakladanie kartotek i to on idzie pierwszy.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class SymboleDostawcy
{
    /// <summary>
    /// `DaneAsortymentuDlaPodmiotu.Rola` to maska bitowa (Byte), nie enum —
    /// sprawdzone refleksja. Sfera odrzuca 0 i wymienia dozwolone kombinacje
    /// (Dostawca / Dostawca+podstawowy / Producent / ... / Odbiorca);
    /// `Dostawca` to bit 2.
    /// </summary>
    const byte ROLA_DOSTAWCA = 2;

    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }

        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
        var lista = plan.Powiazania ?? new List<Pow>();
        if (lista.Count == 0) { Console.WriteLine("Plan bez powiazan."); return 1; }

        var asort = sfera.Asortymenty();
        var podmioty = sfera.Podmioty();
        var kroki = new List<Krok>();


        // Podmioty po NIP — jednym przelotem. NIP z faktury jest tym, co laczy
        // fakture z kontrahentem; symbol sam z siebie NIE jest kluczem globalnym,
        // bo dwoch dostawcow uzywa tego samego oznaczenia dla roznych rzeczy.
        var poNip = new Dictionary<string, dynamic>(StringComparer.OrdinalIgnoreCase);
        foreach (var p in podmioty.Dane.WszystkieFirmy().ToList())
        {
            var nip = (Bezp(() => (string?)p.NIP) ?? "").Replace("-", "").Trim();
            if (nip.Length > 0 && !poNip.ContainsKey(nip)) poNip[nip] = p;
        }

        // Waluta wymagana przy kazdym powiazaniu — pobieramy RAZ.
        // `Waluty()` to metoda rozszerzajaca Uchwytu, wiec refleksja po samym
        // `Uchwyt` jej nie widzi (stad wczesniejsze pudlo diagnostyki).
        var waluta = Bezp2(() =>
        {
            var wszystkie = sfera.Waluty().Dane.Wszystkie().ToList();
            return wszystkie.FirstOrDefault(x => ((string?)x.Symbol ?? "")
                       .Equals("PLN", StringComparison.OrdinalIgnoreCase))
                   ?? wszystkie.FirstOrDefault();
        });
        if (zapisz && waluta == null)
            Console.WriteLine("⚠️  Nie udalo sie ustalic waluty — zapis moze zostac odrzucony.");

        foreach (var w in lista)
        {
            var nip = (w.Nip ?? "").Replace("-", "").Replace(" ", "").Trim();
            var symbolDost = (w.SymbolDostawcy ?? "").Trim();
            var symbol = (w.Symbol ?? "").Trim();

            if (symbolDost.Length == 0 || symbolDost.Length > 64)
            {
                kroki.Add(new Krok(symbolDost, symbol, "blad",
                    "symbol dostawcy musi miec 1..64 znaki"));
                continue;
            }
            if (!poNip.TryGetValue(nip, out var podmiot))
            {
                kroki.Add(new Krok(symbolDost, symbol, "brak-dostawcy",
                    $"nie ma kontrahenta o NIP {nip}"));
                continue;
            }

            try
            {
                // Kartoteka: po Id (pewne) albo po symbolu.
                var enc = w.AsortymentId is { } id
                    ? asort.Dane.Wszystkie().FirstOrDefault(a => a.Id == id)
                    : asort.Dane.WyszukajPoSymbolu(symbol);
                if (enc == null)
                {
                    kroki.Add(new Krok(symbolDost, symbol, "brak-kartoteki",
                        "nie ma takiej kartoteki w Subiekcie"));
                    continue;
                }

                // Czy to powiazanie juz istnieje — nie dubluj.
                var juz = Bezp2(() => ((IEnumerable<dynamic>)enc.DaneAsortymentuDlaPodmiotow)
                    .FirstOrDefault(d => ((string?)d.Symbol ?? "").Trim()
                        .Equals(symbolDost, StringComparison.OrdinalIgnoreCase)
                        && d.Podmiot != null && d.Podmiot.Id == podmiot.Id));
                if (juz != null)
                {
                    kroki.Add(new Krok(symbolDost, (string?)enc.Symbol ?? symbol, "istnieje",
                        "ten symbol jest juz powiazany z ta kartoteka"));
                    continue;
                }

                if (!zapisz)
                {
                    kroki.Add(new Krok(symbolDost, (string?)enc.Symbol ?? symbol, "do-powiazania",
                        $"{Bezp(() => (string?)podmiot.NazwaSkrocona)} → {enc.Symbol}"));
                    continue;
                }

                using var ob = asort.Znajdz(enc);
                // Kolekcja to zwykle ICollection<> — element tworzymy konstruktorem
                // domyslnym (jest publiczny) i dokladamy przez Add.
                //
                // ⚠️ KOLEJNOSC MA ZNACZENIE. Pola ustawiamy DOPIERO po Add():
                // encja niepodpieta do obiektu biznesowego rzuca
                // `UnsponsoredModificationException` przy pierwszym przypisaniu
                // (zmierzone 17.09.2026 — pierwsza proba padla na 15/15).
                var dane = new InsERT.Moria.ModelDanych.DaneAsortymentuDlaPodmiotu();
                ob.Dane.DaneAsortymentuDlaPodmiotow.Add(dane);

                dane.Podmiot = podmiot;
                dane.Symbol = symbolDost;
                // Rola to maska bitowa (Byte), NIE enum. Sfera odrzuca 0,
                // wymieniajac dozwolone kombinacje — `Dostawca` = bit 2.
                dane.Rola = ROLA_DOSTAWCA;
                // Waluta jest wymagana (bez niej „Nie ustawiono powiazanego
                // obiektu"). Bierzemy domyslna z bazy — `Waluty()` to metoda
                // ROZSZERZAJACA Uchwytu (InsERT.Moria.Sfera.UchwytRozszerzenia).
                if (waluta != null) try { dane.WalutaCenyDeklarowanej = waluta; } catch { }
                if (w.CenaDeklarowana is { } cd)
                    try { dane.CenaDeklarowana = cd; } catch { }
                if (!string.IsNullOrWhiteSpace(w.NazwaUDostawcy))
                    try { dane.Nazwa = w.NazwaUDostawcy!.Trim(); } catch { }

                if (!ob.Zapisz())
                {
                    kroki.Add(new Krok(symbolDost, (string?)enc.Symbol ?? symbol, "blad",
                        Bezp(ob.PodajBledy)));
                    continue;
                }
                kroki.Add(new Krok(symbolDost, (string?)enc.Symbol ?? symbol, "powiazano",
                    $"{Bezp(() => (string?)podmiot.NazwaSkrocona)} → {enc.Symbol}"));
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok(symbolDost, symbol, "blad",
                    $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(new { zapisano = zapisz, kroki },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));

        foreach (var g in kroki.GroupBy(k => k.Status))
            Console.WriteLine($"  {g.Key}: {g.Count()}");
        return 0;
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }
    static dynamic? Bezp2(Func<dynamic?> f) { try { return f(); } catch { return null; } }

    internal record Pow(string? Nip, string? SymbolDostawcy, string? Symbol,
                        int? AsortymentId, string? NazwaUDostawcy,
                        decimal? CenaDeklarowana);
    internal record Plan(List<Pow>? Powiazania);
    internal record Krok(string SymbolDostawcy, string Symbol, string Status, string? Szczegoly);
}
