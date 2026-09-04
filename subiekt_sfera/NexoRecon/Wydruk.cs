// Tryb "wydruk" — eksportuje dokument (domyślnie ZD) do PDF. NIC nie zapisuje do bazy.
//
//   NexoRecon.exe wydruk --numery="ZD 4/09/2026;ZD 5/09/2026" --pdf=C:\katalog [--out=wynik.json]
//
// Używa tego samego wzorca, którym Subiekt drukuje ręcznie — typ wzorca bierze
// się z konfiguracji dokumentu (IKonfiguracjaObowiazujaca.TypWzorcaWydruku),
// więc PDF wygląda 1:1 jak ten z Subiekta.
//
// ⚠️ Obiekty wydruku implementują interfejsy JAWNIE — GetType().GetProperty()
// i GetMethods() zwracają wtedy null/pustkę, choć składowe istnieją. Dlatego
// wszystkie odwołania idą przez pomocnicze Wlasciwosc()/Metoda(), które
// przeszukują też GetInterfaces(). Rozpoznane trybem "wydruk-recon" 04.09.2026.

using System.IO;
using System.Reflection;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Wydruk
{
    public static int Uruchom(Uchwyt sfera, string? numery, string? outPath, string? pdfDir)
    {
        if (string.IsNullOrWhiteSpace(numery))
        {
            Console.WriteLine("Tryb wydruk: brak --numery=\"ZD 4/09/2026\"");
            return 1;
        }
        var katalog = pdfDir ?? Path.Combine(Path.GetTempPath(), "rm_baza_zd");
        Directory.CreateDirectory(katalog);

        var chciane = numery.Split(';', StringSplitOptions.RemoveEmptyEntries |
                                        StringSplitOptions.TrimEntries);

        var zam = sfera.ZamowieniaDoDostawcow();
        // Bierzemy szerszy zakres niż liczba szukanych — numer wskazuje dokument
        // z ostatnich dni, ale nie zawsze jest wśród kilku najnowszych.
        var ostatnie = zam.Dane.Wszystkie()
            .OrderByDescending(d => d.DataWprowadzenia).Take(300).ToList();

        // Typ wzorca z konfiguracji ZD — nie zgadujemy.
        object? typWzorca = null;
        try
        {
            var konf = sfera.Konfiguracje().DaneDomyslne.ZamowienieDoDostawcy;
            typWzorca = Czytaj(konf, "TypWzorcaWydruku");
        }
        catch { /* niżej obsłużone jako błąd */ }

        var wyniki = new List<object>();
        if (typWzorca == null)
        {
            Wypisz(new { blad = "Nie ustalono typu wzorca wydruku dla ZD.", pliki = wyniki }, outPath);
            return 1;
        }

        var wydruki = sfera.Wydruki();
        var mUtworz = wydruki.GetType().GetMethods()
            .FirstOrDefault(m => m.Name == "Utworz" && m.GetParameters().Length == 1);
        if (mUtworz == null)
        {
            Wypisz(new { blad = "IWydruki bez metody Utworz(typ)", pliki = wyniki }, outPath);
            return 1;
        }

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
                wyniki.Add(new { numer = szukany, ok = false, blad = "nie znaleziono dokumentu" });
                continue;
            }

            var sygnatura = Bezp(() => dok.NumerWewnetrzny?.PelnaSygnatura) ?? szukany;
            // Ukośniki z numeru (ZD 4/09/2026) nie przejdą w nazwie pliku.
            var nazwa = sygnatura.Replace('/', '-').Replace('\\', '-').Replace(' ', '_');
            var docelowy = Path.Combine(katalog, nazwa + ".pdf");

            try
            {
                if (File.Exists(docelowy)) File.Delete(docelowy);

                var wydruk = mUtworz.Invoke(wydruki, new[] { typWzorca })!;
                var param = Czytaj(wydruk, "ParametryDrukowania");
                if (param == null)
                {
                    wyniki.Add(new { numer = sygnatura, ok = false, blad = "brak ParametryDrukowania" });
                    continue;
                }

                var formaty = AsLista(Czytaj(param, "DostepneFormatyEksportu"));
                var pdf = formaty?.FirstOrDefault(f =>
                    f.Contains("pdf", StringComparison.OrdinalIgnoreCase)) ?? "pdf";

                Pisz(wydruk, "ObiektDoWydruku", dok);
                Pisz(param, "SciezkaEksportu", katalog);
                Pisz(param, "NazwaDokumentuUzytkownika", nazwa);
                Pisz(param, "FormatEksportu", pdf);
                Pisz(param, "ZastapPliki", true);

                var mEksport = Metody(wydruk, "Eksport")
                    .FirstOrDefault(m => m.GetParameters().Length == 0);
                if (mEksport == null)
                {
                    wyniki.Add(new { numer = sygnatura, ok = false, blad = "brak metody Eksport()" });
                    continue;
                }

                mEksport.Invoke(wydruk, null);

                var sukces = Czytaj(wydruk, "OstatniaOperacjaZakonczonaSukcesem") as bool? ?? false;
                var powstal = File.Exists(docelowy);
                wyniki.Add(new
                {
                    numer = sygnatura,
                    ok = sukces && powstal,
                    plik = powstal ? docelowy : null,
                    dostawca = Bezp(() => dok.Podmiot?.NazwaSkrocona),
                    // NIP jest pewniejszym kluczem do maila dostawcy w RM_BAZA
                    // niż nazwa — te w Subiekcie bywają pełne („SPÓŁKA Z O.O.”),
                    // a w RM_BAZA skrócone („QUAY”).
                    nip = NipPodmiotu(dok.Podmiot),
                    blad = powstal ? null : "eksport nie utworzył pliku"
                });

                (wydruk as IDisposable)?.Dispose();
            }
            catch (Exception ex)
            {
                var w = (ex as TargetInvocationException)?.InnerException ?? ex;
                wyniki.Add(new { numer = sygnatura, ok = false, blad = $"{w.GetType().Name}: {w.Message}" });
            }
        }

        Wypisz(new { katalog, pliki = wyniki }, outPath);
        return 0;
    }

    // ── refleksja odporna na jawną implementację interfejsów ───────────────
    static PropertyInfo? Wlasciwosc(object obj, string nazwa)
    {
        var p = obj.GetType().GetProperty(nazwa);
        if (p != null) return p;
        foreach (var i in obj.GetType().GetInterfaces())
        {
            p = i.GetProperty(nazwa);
            if (p != null) return p;
        }
        return null;
    }

    static IEnumerable<MethodInfo> Metody(object obj, string nazwa) =>
        obj.GetType().GetInterfaces().SelectMany(i => i.GetMethods())
           .Concat(obj.GetType().GetMethods())
           .Where(m => m.Name == nazwa);

    static object? Czytaj(object obj, string nazwa)
    {
        try { return Wlasciwosc(obj, nazwa)?.GetValue(obj); } catch { return null; }
    }

    static void Pisz(object obj, string nazwa, object? wartosc)
    {
        try
        {
            var p = Wlasciwosc(obj, nazwa);
            if (p != null && p.CanWrite) p.SetValue(obj, wartosc);
        }
        catch { /* pojedyncza właściwość nie może wywrócić całego wydruku */ }
    }

    static List<string>? AsLista(object? o)
    {
        if (o == null) return null;
        if (o is System.Collections.IEnumerable en && o is not string)
        {
            var l = new List<string>();
            foreach (var x in en) l.Add(x?.ToString() ?? "");
            return l;
        }
        return new List<string> { o.ToString() ?? "" };
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    /// Nazwa pola z NIP-em na Podmiocie nie jest oczywista (bywa w zagnieżdżonym
    /// obiekcie identyfikacyjnym), więc szukamy refleksją po nazwie właściwości.
    static string? NipPodmiotu(object? podmiot)
    {
        if (podmiot == null) return null;
        try
        {
            foreach (var p in podmiot.GetType().GetProperties())
            {
                if (!p.Name.Contains("Nip", StringComparison.OrdinalIgnoreCase)) continue;
                var v = p.GetValue(podmiot)?.ToString();
                if (!string.IsNullOrWhiteSpace(v)) return new string(v.Where(char.IsDigit).ToArray());
            }
            // NIP bywa schowany w obiekcie z danymi identyfikacyjnymi.
            foreach (var nazwa in new[] { "DaneIdentyfikacyjne", "Identyfikator", "DanePodstawowe" })
            {
                var pod = podmiot.GetType().GetProperty(nazwa)?.GetValue(podmiot);
                if (pod == null) continue;
                var glebiej = NipPodmiotu(pod);
                if (!string.IsNullOrWhiteSpace(glebiej)) return glebiej;
            }
        }
        catch { /* brak NIP-u nie może wywrócić wydruku */ }
        return null;
    }

    static void Wypisz(object raport, string? outPath)
    {
        var json = JsonSerializer.Serialize(raport, new JsonSerializerOptions
        {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
        });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
    }
}
