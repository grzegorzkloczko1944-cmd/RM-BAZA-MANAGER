// Tryb "symbole" — zmienia SYMBOL istniejących kartotek. ZAPISUJE (--zapisz).
//
//   NexoRecon.exe symbole --plan=symbole.json [--out=wynik.json] [--zapisz]
//
// Bez --zapisz to suchy przebieg: mówi, co by zrobił, i nic nie zapisuje.
//
// plan.json:
//   [ {"id":109055, "stary":"ZaślepkaDN50D", "nowy":"ZaslepkaDN50D"} ]
//
// Po co: symbol kartoteki musi być czystym ASCII, bo Code 128 nie zakoduje
// „ł", „ś", „ę" — etykiety z kodem kreskowym dla takiej kartoteki nie da się
// wydrukować. Generator symboli poprawiono 05.09.2026, ale 14 kartotek
// powstało wcześniej i siedzi w bazie.
//
// ⚠️ Zmieniamy WYŁĄCZNIE pole Symbol. Nazwa (z polskimi znakami) zostaje
// nietknięta — to ona jest opisem dla człowieka. Nie ruszamy też długości
// symbolu: trzy pozycje mają >13 znaków, ale skracanie ich zmieniałoby
// więcej niż poproszono.
//
// ⚠️ „stary" w planie jest WERYFIKOWANY przed zapisem. Jeśli kartoteka ma
// dziś inny symbol (ktoś ją w międzyczasie poprawił), pozycja jest pomijana
// — lepiej pominąć niż nadpisać cudzą zmianę.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Symbole
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }

        var plan = JsonSerializer.Deserialize<List<Poz>>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true }) ?? new List<Poz>();
        if (plan.Count == 0) { Console.WriteLine("Plan bez pozycji."); return 1; }

        var asort = sfera.Asortymenty();
        var wszystkie = asort.Dane.Wszystkie().ToList();
        var kroki = new List<Krok>();
        var zmienione = 0;

        foreach (var p in plan)
        {
            var enc = wszystkie.FirstOrDefault(a => Bezp2(() => a.Id) == p.Id);
            if (enc == null)
            {
                kroki.Add(new Krok(p.Id, p.Stary, p.Nowy, "blad", "nie znaleziono kartoteki o tym Id"));
                continue;
            }

            var obecny = (Bezp(() => enc.Symbol) ?? "").Trim();
            if (!obecny.Equals((p.Stary ?? "").Trim(), StringComparison.Ordinal))
            {
                kroki.Add(new Krok(p.Id, p.Stary, p.Nowy, "pominieto",
                    $"symbol w bazie to teraz „{obecny}” — ktoś go zmienił, nie nadpisuję"));
                continue;
            }
            if (obecny.Equals((p.Nowy ?? "").Trim(), StringComparison.Ordinal))
            {
                kroki.Add(new Krok(p.Id, p.Stary, p.Nowy, "pominieto", "symbol już poprawny"));
                continue;
            }
            if (string.IsNullOrWhiteSpace(p.Nowy))
            {
                kroki.Add(new Krok(p.Id, p.Stary, p.Nowy, "blad", "nowy symbol pusty"));
                continue;
            }
            // Kolizja: symbol musi być unikalny w Subiekcie.
            var zajety = wszystkie.FirstOrDefault(a =>
                Bezp2(() => a.Id) != p.Id &&
                (Bezp(() => a.Symbol) ?? "").Trim()
                    .Equals(p.Nowy!.Trim(), StringComparison.OrdinalIgnoreCase));
            if (zajety != null)
            {
                kroki.Add(new Krok(p.Id, p.Stary, p.Nowy, "blad",
                    $"symbol „{p.Nowy}” zajęty przez Id={Bezp2(() => zajety.Id)}"));
                continue;
            }

            if (!zapisz)
            {
                kroki.Add(new Krok(p.Id, p.Stary, p.Nowy, "do-zmiany", null));
                continue;
            }

            try
            {
                using var ob = asort.Znajdz(enc);
                ob.Dane.Symbol = p.Nowy!.Trim();
                if (ob.Zapisz())
                {
                    zmienione++;
                    kroki.Add(new Krok(p.Id, p.Stary, p.Nowy, "zmieniono", null));
                }
                else
                {
                    kroki.Add(new Krok(p.Id, p.Stary, p.Nowy, "blad", Bezp(ob.PodajBledy)));
                }
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok(p.Id, p.Stary, p.Nowy, "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(new { zapisano = zapisz, zmienione, kroki },
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
    static int Bezp2(Func<int> f) { try { return f(); } catch { return 0; } }

    internal record Poz(int Id, string? Stary, string? Nowy);
    internal record Krok(int Id, string? Stary, string? Nowy, string Status, string? Szczegoly);
}
