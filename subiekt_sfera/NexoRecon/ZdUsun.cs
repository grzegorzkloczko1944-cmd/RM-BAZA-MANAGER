// Tryb "zd-usun" — kasuje wskazane zamówienia do dostawców. ZAPISUJE (usuwa).
//
//   NexoRecon.exe zd-usun --numery="ZD 1/09/2026;ZD 2/09/2026" [--out=w.json] --zapisz
//
// Bez --zapisz tylko pokazuje, co by usunął.
//
// Kasuje WYŁĄCZNIE dokumenty o dokładnie podanych numerach — żadnych zakresów
// ani filtrów po dacie. Usunięcie dokumentu jest nieodwracalne, więc lista musi
// być jawna i krótka; przy niepasującym numerze zgłaszamy błąd zamiast zgadywać.
//
// Powód powstania (04.09.2026): pierwsze ZD z RM_BAZA tworzone były bez
// powiązania z ZK (patrz Zd.cs) i zostały w bazie jako śmieci do posprzątania.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class ZdUsun
{
    public static int Uruchom(Uchwyt sfera, string numeryArg, string? outPath, bool zapisz)
    {
        var chciane = numeryArg.Split(';', StringSplitOptions.RemoveEmptyEntries)
                               .Select(s => s.Trim())
                               .Where(s => s.Length > 0)
                               .ToHashSet(StringComparer.OrdinalIgnoreCase);
        if (chciane.Count == 0) { Console.WriteLine("Brak numerów do usunięcia."); return 1; }

        var zamowienia = sfera.ZamowieniaDoDostawcow();
        var kroki = new List<Krok>();
        var znalezione = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        // Ostatnie 300 ZD — kasujemy świeże śmieci, nie archiwum sprzed lat.
        var dokumenty = zamowienia.Dane.Wszystkie()
            .OrderByDescending(d => d.DataWprowadzenia)
            .Take(300)
            .ToList();

        foreach (var d in dokumenty)
        {
            var numer = Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "";
            if (numer.Length == 0 || !chciane.Contains(numer)) continue;
            znalezione.Add(numer);

            var dostawca = Bezp(() => d.Podmiot?.NazwaSkrocona) ?? "";
            var pozycji = 0;
            try { pozycji = d.Pozycje.Count(); } catch { }

            if (!zapisz)
            {
                kroki.Add(new Krok(numer, "do-usuniecia", $"{dostawca}, {pozycji} poz."));
                continue;
            }

            try
            {
                using var ob = zamowienia.Znajdz(d);
                if (!ob.MoznaUsunac)
                {
                    kroki.Add(new Krok(numer, "blad",
                        "Subiekt nie pozwala usunąć tego dokumentu (zrealizowany lub zablokowany)"));
                    continue;
                }
                ob.Usun();
                kroki.Add(new Krok(numer, "usuniete", $"{dostawca}, {pozycji} poz."));
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok(numer, "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        foreach (var brak in chciane.Except(znalezione, StringComparer.OrdinalIgnoreCase))
            kroki.Add(new Krok(brak, "blad", "nie znaleziono dokumentu o tym numerze"));

        var json = JsonSerializer.Serialize(new { zapisano = zapisz, kroki },
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

    internal record Krok(string Numer, string Status, string? Szczegoly);
}
