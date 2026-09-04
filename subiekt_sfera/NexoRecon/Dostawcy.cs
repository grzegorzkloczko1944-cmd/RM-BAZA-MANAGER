// Tryb "dostawcy" — zakłada kontrahentów w Subiekcie z listy RM_BAZA. ZAPISUJE.
//
//   NexoRecon.exe dostawcy --plan=dostawcy.json [--out=w.json] [--zapisz]
//
// Bez --zapisz suchy przebieg: mówi kogo by założył, nic nie zapisuje.
//
// plan.json:
//   { "dostawcy": [ {"nazwa":"AUSPOL", "nip":"1234567890",
//                    "email":"biuro@...", "telefon":"..."} ] }
//
// Po co: RM_BAZA ma 113 dostawców, Subiekt 629 kontrahentów, a ~35 realnych
// firm z RM_BAZA nie ma odpowiednika w Subiekcie (pomiar 04.09.2026).
// Bez kontrahenta nie da się wystawić ZD.
//
// ⚠️ Sfera NIE udostępnia pobierania danych z GUS — to funkcja interfejsu
// Subiekta. Dlatego zakładamy kontrahenta z tego, co ma RM_BAZA, i wpisujemy
// NIP w pole NIP (zapisywalne). Dzięki temu użytkownik zaznacza w Subiekcie
// nowego kontrahenta i od razu klika „Pobierz z GUS" — bez przepisywania NIP-u.
// W Uwagach zostaje ślad pochodzenia wpisu.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Dostawcy
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }

        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
        var lista = plan.Dostawcy ?? new List<Dost>();
        if (lista.Count == 0) { Console.WriteLine("Plan bez dostawców."); return 1; }

        var podmioty = sfera.Podmioty();
        var kroki = new List<Krok>();

        // Istniejący — po NIP i po nazwie, żeby nie zakładać duplikatów.
        var istniejace = podmioty.Dane.WszystkieFirmy().ToList();
        var poNip = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var poNazwie = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var p in istniejace)
        {
            var nazwa = (Bezp(() => p.NazwaSkrocona) ?? "").Trim();
            if (nazwa.Length > 0) poNazwie.Add(nazwa);
            var nip = (Bezp(() => (string?)p.NIP) ?? "").Replace("-", "").Trim();
            if (nip.Length > 0 && !poNip.ContainsKey(nip)) poNip[nip] = nazwa;
        }

        foreach (var d in lista)
        {
            var nazwa = (d.Nazwa ?? "").Trim();
            var nip = (d.Nip ?? "").Replace("-", "").Replace(" ", "").Trim();
            if (nazwa.Length == 0)
            {
                kroki.Add(new Krok("", "blad", "pusta nazwa"));
                continue;
            }
            if (nip.Length > 0 && poNip.TryGetValue(nip, out var juz))
            {
                kroki.Add(new Krok(nazwa, "istnieje", $"ten NIP ma już „{juz}”"));
                continue;
            }
            if (poNazwie.Contains(nazwa))
            {
                kroki.Add(new Krok(nazwa, "istnieje", "kontrahent o tej nazwie już jest"));
                continue;
            }
            if (!zapisz)
            {
                kroki.Add(new Krok(nazwa, "do-zalozenia",
                    nip.Length > 0 ? $"NIP {nip}" : "bez NIP"));
                continue;
            }

            try
            {
                using var ob = podmioty.UtworzFirme();
                ob.Dane.NazwaSkrocona = nazwa;
                if (nip.Length > 0)
                {
                    // NIP w polu NIP — dzięki temu „Pobierz z GUS" w Subiekcie
                    // działa od razu, bez przepisywania numeru.
                    try { ob.Dane.NIP = nip; } catch { /* format odrzucony — zostaje w Uwagach */ }
                }
                if (!string.IsNullOrWhiteSpace(d.Telefon))
                    try { ob.Dane.Telefon = d.Telefon!.Trim(); } catch { }

                var uwagi = "Dodany z RM_BAZA"
                          + (nip.Length > 0 ? $"; NIP {nip} — użyj „Pobierz z GUS”" : "")
                          + (!string.IsNullOrWhiteSpace(d.Email) ? $"; e-mail {d.Email!.Trim()}" : "");
                try { ob.Dane.Uwagi = uwagi; } catch { }

                if (!ob.Zapisz())
                {
                    kroki.Add(new Krok(nazwa, "blad", Bezp(ob.PodajBledy)));
                    continue;
                }
                poNazwie.Add(nazwa);
                if (nip.Length > 0) poNip[nip] = nazwa;
                kroki.Add(new Krok(nazwa, "zalozony", nip.Length > 0 ? $"NIP {nip}" : "bez NIP"));
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok(nazwa, "blad", $"{ex.GetType().Name}: {ex.Message}"));
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
        return 0;
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record Dost(string Nazwa, string? Nip, string? Email, string? Telefon);
    internal record Plan(List<Dost>? Dostawcy);
    internal record Krok(string Nazwa, string Status, string? Szczegoly);
}
