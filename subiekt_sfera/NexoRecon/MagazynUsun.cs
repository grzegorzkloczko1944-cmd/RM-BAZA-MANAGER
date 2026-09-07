// Tryb "magazyn-usun" — USUWA magazyny. ZAPISUJE.
//
//   NexoRecon.exe magazyn-usun --symbole="GAL;OUT" [--out=w.json] [--zapisz]
//
// Bez --zapisz suchy przebieg: mówi, co da się usunąć, a NIC nie kasuje —
// tak samo jak kartoteka-usun i zd-usun.
//
// Po co: uruchamiając magazyn od zera (MAGAZYN.md) zostają magazyny z demo
// albo takie, które przestały być używane. Magazyn bez stanu i bez dokumentów
// to sama kartoteka — zaśmieca listy wyboru w każdym oknie, gdzie wskazuje się
// magazyn.
//
// ⚠️ USUNIĘCIE JEST NIEODWRACALNE i Subiekt pozwala na nie TYLKO wtedy, gdy
// magazyn nie ma powiązań: stanów, dokumentów, pozycji w dokumentach. Magazyn,
// na którym kiedykolwiek wystawiono dokument, zostanie — i to jest poprawne,
// bo skasowanie rozspójniłoby te dokumenty. Żeby usunąć magazyn używany
// wcześniej, trzeba najpierw usunąć jego dokumenty (tryb "zd-usun" czyta
// ZK/ZD/RW/WZ) — ale historii RW/WZ zwykle usuwać nie wolno.
//
// ⚠️ Ta sama pułapka co w KartotekaUsun.cs (sprawdzone 05.09.2026): Usun()
// potrafi wrócić BEZ WYJĄTKU, choć Subiekt odmówił, a MoznaUsunac bywa
// nadmiernie optymistyczne. Dlatego rozstrzyga dopiero ponowne wyszukanie
// po symbolu — "usuniety" tylko wtedy, gdy magazynu naprawdę już nie ma.

using System.Linq;

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class MagazynUsun
{
    public static int Uruchom(Uchwyt sfera, string? symbole, string? outPath, bool zapisz)
    {
        if (string.IsNullOrWhiteSpace(symbole))
        {
            Console.WriteLine("Tryb magazyn-usun: brak --symbole=\"GAL;OUT\"");
            return 1;
        }
        var chciane = symbole.Split(';', StringSplitOptions.RemoveEmptyEntries |
                                         StringSplitOptions.TrimEntries);
        var magazyny = sfera.PodajObiektTypu<InsERT.Moria.ModelOrganizacyjny.IMagazyny>();
        var kroki = new List<Krok>();
        var usuniete = 0;

        foreach (var symbol in chciane)
        {
            // Dopasowanie luźne (TRIM, wielkość liter) jak w całym moście.
            var enc = magazyny.Dane.Wszystkie().ToList().FirstOrDefault(m =>
                (Bezp(() => m.Symbol) ?? "").Trim()
                    .Equals(symbol, StringComparison.OrdinalIgnoreCase));
            if (enc == null)
            {
                kroki.Add(new Krok(symbol, "blad", "nie ma takiego magazynu"));
                continue;
            }

            try
            {
                using var ob = magazyny.Znajdz(enc);

                if (!zapisz)
                {
                    kroki.Add(new Krok(symbol, "do-usuniecia",
                        "wstępnie — Subiekt zdecyduje przy zapisie"));
                    continue;
                }

                object? wynikUsun = null;
                try
                {
                    var met = ob.GetType().GetMethod("Usun", Type.EmptyTypes)
                              ?? ob.GetType().GetInterfaces()
                                   .Select(i => i.GetMethod("Usun", Type.EmptyTypes))
                                   .FirstOrDefault(x => x != null);
                    wynikUsun = met != null ? met.Invoke(ob, null) : ob.Usun();
                }
                catch (System.Reflection.TargetInvocationException tie) when (tie.InnerException != null)
                {
                    throw tie.InnerException;
                }
                var bledy = Bezp(ob.PodajBledy);

                // Rozstrzyga stan bazy, nie wynik Usun() — patrz nagłówek.
                var nadalJest = false;
                try
                {
                    nadalJest = magazyny.Dane.Wszystkie().ToList().Any(m =>
                        (Bezp(() => m.Symbol) ?? "").Trim()
                            .Equals(symbol, StringComparison.OrdinalIgnoreCase));
                }
                catch { }

                if (nadalJest)
                {
                    kroki.Add(new Krok(symbol, "blad",
                        "Subiekt odmówił usunięcia — magazyn ma stany albo dokumenty"
                        + (string.IsNullOrWhiteSpace(bledy) ? "" : $" ({bledy})")
                        + (wynikUsun is bool b && !b ? " [Usun()=false]" : "")));
                    continue;
                }
                usuniete++;
                kroki.Add(new Krok(symbol, "usuniety", null));
            }
            catch (Exception e)
            {
                kroki.Add(new Krok(symbol, "blad", $"{e.GetType().Name}: {e.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(new { zapisano = zapisz, usuniete, kroki },
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

    internal record Krok(string Symbol, string Status, string? Szczegoly);
}
