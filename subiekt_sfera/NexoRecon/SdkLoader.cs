// Doladowywanie bibliotek SDK Sfery z C:\iLogic\Subiekt\Bin\ w locie.
//
// ⚠️ TA KLASA NIE MOZE ODWOLYWAC SIE DO ZADNEGO TYPU Z InsERT.*.
//
// Powod (znalezione 06.09.2026 przy sprawdzaniu mostu na serwerze): most
// rozdystrybuowany jako 5 plikow (bez 549 bibliotek InsERT, ktore build
// kopiuje do bin\Release) NIE URUCHAMIAL SIE W OGOLE:
//
//     FileNotFoundException: Could not load file or assembly
//     'InsERT.Moria.Sfera' ... at Program.<Main>$(String[] args)
//
// Hook AssemblyLoadContext.Resolving byl podpinany w NexoSession.Wczytaj(),
// czyli WEWNATRZ Main. Ale .NET kompiluje (JIT) cale cialo Main przy wejsciu
// do niego i przy tej okazji rozwiazuje kazdy typ, ktorego Main dotyka —
// a Main wolal Rozpoznanie.Uruchom(sesja.Sfera, ...) i
// CommandDispatcher.Wykonaj(sesja.Sfera, ...), gdzie Sfera to Uchwyt z SDK.
// Biblioteka byla wiec potrzebna ZANIM wykonala sie pierwsza instrukcja
// Main, czyli zanim hook mial szanse wstac. U budujacego nie bylo tego
// widac, bo RM_BAZA bierze most z bin\Release, gdzie 554 pliki leza obok.
//
// Stad dwie zasady:
//   1. Hook podpina sie TUTAJ, jako pierwsza instrukcja procesu, z klasy,
//      ktorej JIT nie wymaga zadnej biblioteki InsERT.
//   2. Main nie dotyka typow SDK — robota CLI siedzi w Cli.cs, ServerHost
//      ma wlasna metode. Obie sa kompilowane dopiero przy wywolaniu,
//      czyli juz po podpieciu hooka.

using System;
using System.IO;
using System.Runtime.Loader;
using System.Text.Json;

namespace NexoRecon;

internal static class SdkLoader
{
    static bool _podpiety;

    /// <summary>
    /// Katalog Bin SDK Sfery. C:\iLogic\SUBIEKT\Bin\ jest wgrywany na kazde
    /// stanowisko przy instalacji; stara lokalizacja (rozpakowana
    /// dokumentacja, z numerem wersji w nazwie) zostaje jako zapas dla
    /// maszyn, na ktorych nowego katalogu jeszcze nie ma.
    /// Konfig moze to nadpisac polem SdkBin.
    /// </summary>
    public static string DomyslnySdkBin()
    {
        const string nowy = @"C:\iLogic\SUBIEKT\Bin\";
        return Directory.Exists(nowy)
            ? nowy
            : @"C:\iLogic\Subiekt_nexo_PRO_dokumentacja\SDK\Bin\";
    }

    /// <summary>
    /// Podpina hook na podstawie pola SdkBin z konfigu. Brak konfigu albo
    /// zepsuty JSON nie sa tu bledem — bierzemy domyslny katalog, a czytelny
    /// komunikat o konfigu da pozniej NexoSession.Wczytaj. Tu chodzi tylko
    /// o to, zeby hook istnial, zanim ktokolwiek dotknie typow SDK.
    /// </summary>
    public static void PodepnijZKonfigu(string cfgPath)
    {
        string? sdkBin = null;
        try
        {
            if (File.Exists(cfgPath))
            {
                using var doc = JsonDocument.Parse(File.ReadAllText(cfgPath),
                    new JsonDocumentOptions { CommentHandling = JsonCommentHandling.Skip });
                foreach (var p in doc.RootElement.EnumerateObject())
                    if (p.Name.Equals("sdkBin", StringComparison.OrdinalIgnoreCase)
                        && p.Value.ValueKind == JsonValueKind.String)
                        sdkBin = p.Value.GetString();
            }
        }
        catch { /* zly konfig zglosi Wczytaj — z wlasciwym komunikatem */ }
        Podepnij(string.IsNullOrWhiteSpace(sdkBin) ? DomyslnySdkBin() : sdkBin!);
    }

    /// <summary>Hook jest globalny; podpinamy go raz — kolejne wywolania nic nie robia.</summary>
    public static void Podepnij(string sdkBin)
    {
        if (_podpiety) return;
        _podpiety = true;
        AssemblyLoadContext.Default.Resolving += (ctx, name) =>
        {
            var p = Path.Combine(sdkBin, name.Name + ".dll");
            return File.Exists(p) ? ctx.LoadFromAssemblyPath(p) : null;
        };
    }
}
