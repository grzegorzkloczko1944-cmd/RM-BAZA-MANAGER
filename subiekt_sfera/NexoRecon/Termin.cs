// Tryb "termin" — ustawia TERMIN REALIZACJI na zamówieniu do dostawcy. ZAPISUJE.
//
//   NexoRecon.exe termin --numery="ZD 4/09/2026" --data=2026-09-19 [--out=w.json] [--zapisz]
//
// Bez --zapisz to suchy przebieg: mówi, co by zrobił, i nic nie zapisuje.
//
// Pole `TerminRealizacji` (DateTime?) jest wprost na dokumencie ZD i jest
// zapisywalne — sprawdzone refleksją 05.09.2026 trybem "wydruk-recon".
// Domyślnie Subiekt wstawia tam datę wystawienia, więc dopóki nikt go nie
// ustawi świadomie, „termin" nie niesie żadnej informacji.
//
// Po co przez Sferę, a nie ręcznie w Subiekcie: termin wpisywany przy wysyłce
// zamówienia mailem ma wylądować i w treści maila, i na dokumencie — inaczej
// dostawca wie, na kiedy zamawiamy, a Subiekt nie.

using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Termin
{
    public static int Uruchom(Uchwyt sfera, string? numery, string? dataTekst,
                              string? outPath, bool zapisz)
    {
        if (string.IsNullOrWhiteSpace(numery))
        {
            Console.WriteLine("Tryb termin: brak --numery=\"ZD 4/09/2026\"");
            return 1;
        }
        if (string.IsNullOrWhiteSpace(dataTekst))
        {
            Console.WriteLine("Tryb termin: brak --data=RRRR-MM-DD");
            return 1;
        }
        // Format sztywny ISO — data przychodzi z Pythona, nie od użytkownika,
        // więc nie zgadujemy przy jakim locale ją sparsować.
        if (!DateTime.TryParseExact(dataTekst.Trim(), "yyyy-MM-dd",
                CultureInfo.InvariantCulture, DateTimeStyles.None, out var data))
        {
            Console.WriteLine($"Tryb termin: zła data „{dataTekst}” (oczekiwano RRRR-MM-DD)");
            return 1;
        }

        var chciane = numery.Split(';', StringSplitOptions.RemoveEmptyEntries |
                                        StringSplitOptions.TrimEntries);
        var zam = sfera.ZamowieniaDoDostawcow();
        var ostatnie = zam.Dane.Wszystkie()
            .OrderByDescending(d => d.DataWprowadzenia).Take(300).ToList();

        var kroki = new List<Krok>();
        var ustawione = 0;

        foreach (var szukany in chciane)
        {
            var dok = ostatnie.FirstOrDefault(d =>
                (Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "")
                    .Equals(szukany, StringComparison.OrdinalIgnoreCase))
                ?? ostatnie.FirstOrDefault(d =>
                    (Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "")
                        .Contains(szukany, StringComparison.OrdinalIgnoreCase));

            if (dok == null)
            {
                kroki.Add(new Krok(szukany, null, "blad", "nie znaleziono dokumentu"));
                continue;
            }
            var sygnatura = Bezp(() => dok.NumerWewnetrzny?.PelnaSygnatura) ?? szukany;
            var przed = Bezp(() => dok.TerminRealizacji?.ToString("yyyy-MM-dd"));

            if (!zapisz)
            {
                kroki.Add(new Krok(sygnatura, przed, "do-ustawienia", data.ToString("yyyy-MM-dd")));
                continue;
            }

            try
            {
                using var ob = zam.Znajdz(dok);
                ob.Dane.TerminRealizacji = data;
                if (ob.Zapisz())
                {
                    ustawione++;
                    kroki.Add(new Krok(sygnatura, przed, "ustawiono", data.ToString("yyyy-MM-dd")));
                }
                else
                {
                    kroki.Add(new Krok(sygnatura, przed, "blad", Bezp(ob.PodajBledy)));
                }
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok(sygnatura, przed, "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(
            new { zapisano = zapisz, ustawione, data = data.ToString("yyyy-MM-dd"), kroki },
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

    internal record Krok(string Numer, string? Przed, string Status, string? Szczegoly);
}
