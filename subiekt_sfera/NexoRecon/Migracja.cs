// Tryb "migracja-uwagi" — przepisuje Uwagi i Tytul ISTNIEJACYCH dokumentow
// na format ustalony 10.09.2026 (patrz Znacznik.cs). ZAPISUJE.
//
//   NexoRecon.exe migracja-uwagi --plan=plan.json [--out=w.json] [--zapisz]
//
// Bez --zapisz to SUCHY PRZEBIEG: mowi, co by zmienil (PRZED -> PO), i NIC
// nie zapisuje. Tak ma byc uruchamiany za pierwszym razem.
//
// plan.json — jawna lista dokumentow, nic sie nie dzieje "samo":
//   { "dokumenty": [
//       { "rodzaj": "PW", "numer": "PW 2/MASTER/2026",
//         "projekt": "3500", "uwagi": "dupal" }
//   ] }
//
// Kazdy wpis mowi wprost, co ma powstac:
//   Uwagi = "<projekt> Projekt\n<uwagi>"   (uwagi opcjonalne)
//   Tytul = "RM_BAZA <projekt>"
//
// DLACZEGO JAWNA LISTA, A NIE AUTOMAT PO CALEJ BAZIE
// ──────────────────────────────────────────────────
// Rozpoznanie starego formatu bylo NIEJEDNOZNACZNE: "RM_BAZA — PROJEKT 3500
// dupal" niesie numer i opis sklejone w jednym zdaniu, a takich sklejen bylo
// kilka wariantow. Automat musialby zgadywac, gdzie konczy sie numer, a zaczyna
// opis — i przy pomylce nadpisalby dane w bazie produkcyjnej. Dokumentow do
// poprawy bylo 3 (sprawdzone 10.09.2026 na 32 dokumentach w bazie), wiec
// czlowiek wpisuje wprost, co ma byc, a most tylko wykonuje.
//
// ⚠️ NADPISUJE Tytul w calosci — takze domyslna nazwe typu dokumentu, ktora
// Subiekt tam wstawia ("Przychod wewnetrzny"). Decyzja uzytkownika z 10.09.2026:
// nowe dokumenty z RM_BAZA i tak maja tam sam znacznik, wiec stare musza
// wygladac tak samo.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Migracja
{
    public static int Uruchom(Uchwyt sfera, string? planPath, string? outPath, bool zapisz)
    {
        var kroki = new List<Krok>();

        if (string.IsNullOrWhiteSpace(planPath) || !File.Exists(planPath))
        {
            Console.WriteLine($"BRAK PLANU: {planPath}");
            return 1;
        }

        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;

        var zmienionych = 0;
        foreach (var d in plan.Dokumenty ?? new List<DokPlan>())
        {
            var numer = (d.Numer ?? "").Trim();
            var rodzaj = (d.Rodzaj ?? "").Trim().ToUpperInvariant();
            var projekt = (d.Projekt ?? "").Trim();

            if (numer.Length == 0 || projekt.Length == 0)
            {
                kroki.Add(new Krok(numer, "blad",
                    "wpis bez numeru dokumentu albo bez numeru projektu — pomijam"));
                continue;
            }

            try
            {
                var kolekcja = Kolekcja(sfera, rodzaj);
                if (kolekcja == null)
                {
                    kroki.Add(new Krok(numer, "blad", $"nieznany rodzaj dokumentu: {rodzaj}"));
                    continue;
                }

                // Dokument po PELNEJ SYGNATURZE — tej samej, ktora widac
                // w Subiekcie i ktora user przepisuje do planu.
                dynamic? znaleziony = null;
                foreach (var dok in kolekcja.Dane.Wszystkie())
                {
                    var nr = Bezp(() => (string?)dok.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                    if (!nr.Equals(numer, StringComparison.OrdinalIgnoreCase)) continue;
                    znaleziony = dok;
                    break;
                }

                if (znaleziony == null)
                {
                    kroki.Add(new Krok(numer, "brak", "nie znaleziono dokumentu o tym numerze"));
                    continue;
                }

                var bylyUwagi = Bezp(() => (string?)znaleziony.Uwagi) ?? "";
                var bylTytul = Bezp(() => (string?)znaleziony.Tytul) ?? "";
                var noweUwagi = Znacznik.Uwagi(projekt, d.Uwagi);
                var nowyTytul = Znacznik.Tytul(projekt);

                if (bylyUwagi == noweUwagi && bylTytul == nowyTytul)
                {
                    kroki.Add(new Krok(numer, "bez-zmian", "już w nowym formacie"));
                    continue;
                }

                // Raport ZAWSZE mowi PRZED -> PO, takze w suchym przebiegu —
                // to jedyny moment, w ktorym user widzi, co zniknie z Tytulu.
                var opis = $"Uwagi: „{Jednolinijkowo(bylyUwagi)}” → „{Jednolinijkowo(noweUwagi)}”   "
                         + $"Tytuł: „{bylTytul}” → „{nowyTytul}”";

                if (!zapisz)
                {
                    kroki.Add(new Krok(numer, "do-zmiany", opis));
                    continue;
                }

                using var ob = kolekcja.Znajdz(znaleziony);

                // Ta sama pulapka Sfery co przy wystawianiu dokumentow: setter
                // przy JAWNEJ implementacji interfejsu potrafi po cichu nic nie
                // zrobic. Stad zapis + ODCZYT KONTROLNY (patrz Rw.cs/Pw.cs).
                UstawPole((object)ob.Dane, "Uwagi", noweUwagi, numer, kroki);
                UstawPole((object)ob.Dane, "Tytul", nowyTytul, numer, kroki);

                if (!ob.Zapisz())
                {
                    kroki.Add(new Krok(numer, "blad", "Subiekt odrzucił zapis dokumentu"));
                    continue;
                }

                zmienionych++;
                kroki.Add(new Krok(numer, "zmienione", opis));
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok(numer, "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(new { zapisano = zapisz, zmienionych, kroki },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return kroki.Any(k => k.Status == "blad") ? 1 : 0;
    }

    /// Rodzaj → kolekcja Sfery. Te same akcesory co w Dokumenty.cs i ZdUsun.cs,
    /// zeby migracja obejmowala dokladnie to, co widac w przegladzie.
    static dynamic? Kolekcja(Uchwyt sfera, string rodzaj) => rodzaj switch
    {
        "ZK" => sfera.ZamowieniaOdKlientow(),
        "ZD" => sfera.ZamowieniaDoDostawcow(),
        "PW" => sfera.PrzychodyWewnetrzne(),
        "RW" => sfera.RozchodyWewnetrzne(),
        "WZ" => sfera.WydaniaZewnetrzne(),
        _ => null,
    };

    /// Ustawia pole z odczytem kontrolnym — kopia wzorca z Rw.cs/Pw.cs.
    static void UstawPole(object dane, string nazwa, string chciane,
                          string numer, List<Krok> kroki)
    {
        string? mam = null;
        try
        {
            var pr0 = dane.GetType().GetProperty(nazwa);
            if (pr0 != null && pr0.CanWrite)
            {
                pr0.SetValue(dane, chciane);
                mam = pr0.GetValue(dane) as string;
            }
        }
        catch { }
        if (mam != chciane)
        {
            foreach (var i in dane.GetType().GetInterfaces())
            {
                var pr = i.GetProperty(nazwa);
                if (pr == null || !pr.CanWrite) continue;
                try { pr.SetValue(dane, chciane); mam = pr.GetValue(dane) as string; } catch { }
                if (mam == chciane) break;
            }
        }
        if (mam != chciane)
            kroki.Add(new Krok(numer, "uwaga",
                $"nie udało się ustawić pola {nazwa} (odczyt: „{mam}”)"));
    }

    /// Wielowierszowe Uwagi w JEDNEJ linii raportu — inaczej tabela w oknie
    /// RM_BAZA rozjezdza sie na drugim wierszu.
    static string Jednolinijkowo(string? s) =>
        (s ?? "").Replace("\r\n", " ⏎ ").Replace("\n", " ⏎ ").Replace("\r", " ⏎ ");

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record DokPlan(string? Rodzaj, string? Numer, string? Projekt, string? Uwagi);
    internal record Plan(List<DokPlan>? Dokumenty);
    internal record Krok(string Numer, string Status, string? Szczegoly);
}
