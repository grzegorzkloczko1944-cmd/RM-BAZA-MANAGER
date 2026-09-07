// Tryb "projekt-cofnij" — USUWA to, co tryb "projekt" założył: ZK, komplety,
// kartoteki. ZAPISUJE.
//
//   NexoRecon.exe projekt-cofnij --plan=plan.json [--out=w.json] [--zapisz]
//
// Bez --zapisz suchy przebieg: mówi co ZNALAZŁ i co dałoby się usunąć,
// NIC nie kasuje.
//
// plan.json — TEN SAM plik, którego użyto do założenia projektu:
//   { "projekt":"2222", "pozycje":[ {"symbol":"013-100.220","typ":"Z", ...} ] }
// (Podmiot/Tytul/Uwagi niepotrzebne tutaj — używamy tylko Projekt i symboli
// z Pozycje, żeby wiedzieć, CO szukać).
//
// Po co: subiekt_projekt.py ostrzega przed zapisem, że kartoteki i komplety
// są TRWAŁE — ale trwałe nie znaczy nieusuwalne, znaczy "nie da się cofnąć
// jednym kliknięciem po fakcie". Ten tryb jest tym właśnie "po fakcie":
// projekt założono, minęło kilka dni, nic więcej z nim nie zrobiono
// (żadnego wydania, zamówienia, faktury) — da się bezpiecznie sprzątnąć.
//
// KOLEJNOŚĆ jest odwrotna do zakładania (Projekt.cs): najpierw ZK (bo dopóki
// istnieje, kartoteki są "użyte na dokumencie" i Subiekt odmówi ich
// usunięcia — patrz KartotekaUsun.cs), potem komplety OD GÓRY DRZEWA (ZZ
// przed Z — odwrotnie niż przy zakładaniu, bo składnik nie może zniknąć,
// dopóki komplet nadrzędny go zawiera), na końcu zwykłe kartoteki.
//
// BEZPIECZNIK, nie dodatkowy kod: Subiekt SAM odmówi usunięcia czegokolwiek,
// co ma powiązania spoza tego planu (inny projekt korzysta z tego samego
// oringu, ktoś już wydał materiał, wystawiono fakturę na ZK). Ten tryb nie
// próbuje tego przewidzieć — po prostu próbuje usunąć i uczciwie raportuje,
// co się nie udało i dlaczego (ta sama zasada weryfikacji stanem bazy co
// w KartotekaUsun.cs / MagazynUsun.cs / ZdUsun.cs, żeby nie zgłosić
// fałszywego sukcesu — patrz MAGAZYN.md sekcja 6.4b).

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class ProjektCofnij
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }

        var plan = JsonSerializer.Deserialize<Projekt.Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;

        var kroki = new List<Projekt.Krok>();
        var pozycje = plan.Pozycje ?? new List<Projekt.PozPlan>();

        // ── 1. ZK ────────────────────────────────────────────────────────
        // Wszystkie dopasowania po Uwagach, nie tylko najnowsze — jeśli
        // ktoś już wpadł w bałagan z sekcji "duplikaty ZK" (Projekt.cs),
        // cofnięcie ma sprzątnąć WSZYSTKIE, nie tylko jedno.
        var zk = ZnajdzWszystkieZk(sfera, plan.Projekt);
        foreach (var d in zk)
        {
            var numer = NumerZk(d);
            if (!zapisz) { kroki.Add(new Projekt.Krok("zk", numer, "do-usuniecia", null)); continue; }
            UsunDokument(sfera.ZamowieniaOdKlientow(), d, numer, kroki);
        }
        if (zk.Count == 0)
            kroki.Add(new Projekt.Krok("zk", plan.Projekt ?? "", "brak", "nie znaleziono ZK tego projektu"));

        // ── 2. KOMPLETY — od góry drzewa (odwrotnie niż zakładanie) ───────
        var odGory = PosortujOdGory(pozycje);
        foreach (var p in odGory)
            UsunKartoteke(sfera, p.Symbol, "komplet", kroki, zapisz);

        // ── 3. ZWYKŁE KARTOTEKI (X/XX/STANDARD/ZNORMALIZOWANE) ────────────
        var zwykle = pozycje.Where(p => !Rowne(p.Typ, "Z") && !Rowne(p.Typ, "ZZ"));
        foreach (var p in zwykle)
            UsunKartoteke(sfera, p.Symbol, "kartoteka", kroki, zapisz);

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

    /// Odwrotność Projekt.PosortujOdDolu: ZZ przed Z, licząc głębokość po
    /// faktycznym zagnieżdżeniu (nie po samym typie — ZZ potrafi zawierać ZZ,
    /// patrz komentarz w Projekt.cs).
    static List<Projekt.PozPlan> PosortujOdGory(List<Projekt.PozPlan> pozycje)
    {
        var odDolu = Projekt.PosortujOdDoluDlaCofniecia(pozycje);
        odDolu.Reverse();
        return odDolu;
    }

    static void UsunKartoteke(Uchwyt sfera, string symbol, string rodzaj,
                               List<Projekt.Krok> kroki, bool zapisz)
    {
        var asort = sfera.Asortymenty();
        var enc = asort.Dane.WyszukajPoSymbolu(symbol.Trim());
        if (enc == null)
        {
            List<Asortyment> wszystkie = asort.Dane.Wszystkie().ToList();
            var luzne = wszystkie.FirstOrDefault(a => string.Equals((a.Symbol ?? "").Trim(), symbol.Trim(),
                                                                     StringComparison.OrdinalIgnoreCase));
            if (luzne != null) enc = asort.Dane.WyszukajPoSymbolu(luzne.Symbol);
        }
        if (enc == null)
        {
            kroki.Add(new Projekt.Krok(rodzaj, symbol, "brak", "nie ma takiej kartoteki"));
            return;
        }

        if (!zapisz) { kroki.Add(new Projekt.Krok(rodzaj, symbol, "do-usuniecia", null)); return; }

        try
        {
            using var ob = asort.Znajdz(enc);
            object obObj = ob;
            object? wynikUsun = null;
            try
            {
                var typ = obObj.GetType();
                var met = typ.GetMethod("Usun", Type.EmptyTypes)
                          ?? typ.GetInterfaces()
                               .Select(i => i.GetMethod("Usun", Type.EmptyTypes))
                               .FirstOrDefault(x => x != null);
                wynikUsun = met != null ? met.Invoke(obObj, null) : ob.Usun();
            }
            catch (System.Reflection.TargetInvocationException tie) when (tie.InnerException != null)
            {
                throw tie.InnerException;
            }
            var bledy = Bezp(ob.PodajBledy);

            // Rozstrzyga stan bazy, nie wynik Usun() — patrz nagłówek pliku
            // i MAGAZYN.md 6.4b (KartotekaUsun.cs, MagazynUsun.cs, ZdUsun.cs
            // padły na tej samej pułapce, zanim dostały tę weryfikację).
            var nadalJest = asort.Dane.WyszukajPoSymbolu(symbol.Trim()) != null;
            if (nadalJest)
            {
                kroki.Add(new Projekt.Krok(rodzaj, symbol, "blad",
                    "Subiekt odmówił usunięcia — kartoteka ma dokumenty, stany "
                    + "albo jest składnikiem innego kompletu spoza tego projektu"
                    + (string.IsNullOrWhiteSpace(bledy) ? "" : $" ({bledy})")
                    + (wynikUsun is bool b && !b ? " [Usun()=false]" : "")));
                return;
            }
            kroki.Add(new Projekt.Krok(rodzaj, symbol, "usunieta", null));
        }
        catch (Exception e)
        {
            kroki.Add(new Projekt.Krok(rodzaj, symbol, "blad", $"{e.GetType().Name}: {e.Message}"));
        }
    }

    static void UsunDokument(dynamic kolekcja, DokumentZK d, string numer, List<Projekt.Krok> kroki)
    {
        try
        {
            using var ob = (IDisposable)kolekcja.Znajdz(d);
            dynamic obiekt = ob;
            var wlasnosc = ((object)obiekt).GetType().GetProperty("MoznaUsunac");
            if (wlasnosc != null && wlasnosc.GetValue(obiekt) is bool mozna && !mozna)
            {
                kroki.Add(new Projekt.Krok("zk", numer, "blad",
                    "Subiekt nie pozwala usunąć — dokument ma powiązania (zrealizowany/rozliczony)"));
                return;
            }
            obiekt.Usun();

            // Ta sama weryfikacja co w ZdUsun.cs po naprawie 07.09.2026:
            // Usun() potrafi wrócić bez wyjątku, choć Subiekt odmówił.
            var nadalJest = ((IEnumerable<dynamic>)kolekcja.Dane.Wszystkie())
                .Any(x => string.Equals(
                    Bezp(() => (string?)x.NumerWewnetrzny?.PelnaSygnatura) ?? "",
                    numer, StringComparison.OrdinalIgnoreCase));
            if (nadalJest)
            {
                kroki.Add(new Projekt.Krok("zk", numer, "blad",
                    "Subiekt odmówił usunięcia — dokument ma powiązania (zrealizowany/rozliczony)"));
                return;
            }
            kroki.Add(new Projekt.Krok("zk", numer, "usuniete", null));
        }
        catch (Exception ex)
        {
            kroki.Add(new Projekt.Krok("zk", numer, "blad", $"{ex.GetType().Name}: {ex.Message}"));
        }
    }

    /// Wszystkie ZK dopasowane do numeru projektu (ta sama logika co
    /// Projekt.PasujeUwagi — oba formaty Uwag, "numer" i "Projekt {numer}"),
    /// nie tylko najnowsze, bo cofnięcie ma sprzątnąć bałagan, nie tylko
    /// jeden dokument z niego.
    static List<DokumentZK> ZnajdzWszystkieZk(Uchwyt sfera, string? projekt)
    {
        if (string.IsNullOrWhiteSpace(projekt)) return new List<DokumentZK>();
        var szukany = projekt.Trim();
        try
        {
            // ToList() PRZED Where() — patrz komentarz przy Projekt.ZnajdzZkProjektu:
            // ObjectQuery nie przetłumaczy PasujeUwagi na SQL i po cichu zwróci zero.
            return sfera.ZamowieniaOdKlientow().Dane.Wszystkie().ToList()
                .Where(d => Projekt.PasujeUwagi(Bezp(() => d.Uwagi), szukany))
                .OrderByDescending(d => d.DataWprowadzenia)
                .ToList();
        }
        catch { return new List<DokumentZK>(); }
    }

    static string NumerZk(DokumentZK d) => Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "?";

    static bool Rowne(string? a, string b) => string.Equals((a ?? "").Trim(), b, StringComparison.OrdinalIgnoreCase);

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }
}
