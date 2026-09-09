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
    /// Katalog Bin SDK Sfery — najpierw ten, z ktorego chodzi ZAINSTALOWANY
    /// Subiekt, potem statyczne kopie.
    ///
    /// ⚠️ DLACZEGO INSTALACJA SUBIEKTA MA PIERWSZENSTWO (09.09.2026)
    ///
    /// Sfera ODMAWIA polaczenia, gdy wersja bibliotek != wersja bazy:
    ///     "Wersja bazy danych to 61.1.1.9471, a wersja Sfery to 61.1.0.9431"
    /// Baza aktualizuje sie sama przy uruchomieniu Subiekta, a statyczna
    /// kopia w C:\iLogic\SUBIEKT\Bin\ (1,1 GB wgrywane recznie raz przy
    /// zakladaniu stanowiska) zostaje na starej wersji. Efekt: most startuje,
    /// odpowiada na ping, ale NIGDY nie osiaga ready — a RM_BAZA wisi
    /// w _czekaj_na_gotowosc (uzytkownik: "na przejeciu locka RM_BAZA wisi").
    ///
    /// Subiekt nexo instaluje sie przez ClickOnce do profilu uzytkownika:
    ///     %LOCALAPPDATA%\InsERT\Deployments\Nexo\&lt;NAZWA+hash&gt;\Binaries
    /// Nazwa katalogu zawiera nazwe bazy i hash, wiec jest inna na kazdym
    /// stanowisku — dlatego SZUKAMY, zamiast wpisywac na sztywno. Katalog
    /// jest AKTUALIZOWANY W MIEJSCU (sprawdzone: jeden katalog, data zmiany
    /// = moment aktualizacji), wiec biblioteki sa z definicji zgodne z baza.
    ///
    /// Gdy Subiekta na maszynie nie ma (albo chodzi na innym koncie —
    /// Deployments siedzi w profilu), schodzimy na dotychczasowe kopie.
    /// Konfig nadal moze wszystko nadpisac polem SdkBin.
    /// </summary>
    public static string DomyslnySdkBin()
    {
        var zInstalacji = SzukajBinariowSubiekta();
        if (zInstalacji != null) return zInstalacji;

        const string nowy = @"C:\iLogic\SUBIEKT\Bin\";
        return Directory.Exists(nowy)
            ? nowy
            : @"C:\iLogic\Subiekt_nexo_PRO_dokumentacja\SDK\Bin\";
    }

    /// <summary>
    /// Katalog Binaries zainstalowanego Subiekta nexo albo null.
    /// Przy kilku instalacjach (rozne bazy) bierzemy NAJSWIEZSZA — to ta,
    /// ktorej uzywano ostatnio, wiec najpewniej zgodna z baza, do ktorej
    /// laczy sie most.
    /// </summary>
    static string? SzukajBinariowSubiekta()
    {
        try
        {
            var baza = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "InsERT", "Deployments", "Nexo");
            if (!Directory.Exists(baza)) return null;

            string? najlepszy = null;
            DateTime najnowszy = DateTime.MinValue;
            foreach (var katalog in Directory.GetDirectories(baza))
            {
                var bin = Path.Combine(katalog, "Binaries");
                // Sprawdzamy KONKRETNY plik, nie samo istnienie katalogu:
                // pusty albo niedokonczony deployment nie moze wygrac.
                var sfera = Path.Combine(bin, "InsERT.Moria.Sfera.dll");
                if (!File.Exists(sfera)) continue;
                var kiedy = File.GetLastWriteTimeUtc(sfera);
                if (kiedy > najnowszy) { najnowszy = kiedy; najlepszy = bin; }
            }
            return najlepszy;
        }
        catch
        {
            return null;   // brak dostepu do profilu — zostaja kopie statyczne
        }
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
        Podepnij(Rozstrzygnij(sdkBin));
    }

    /// <summary>
    /// Ktory katalog Bin wygrywa: z konfigu czy z instalacji Subiekta.
    ///
    /// Konfigowy `sdkBin` bywa ZASZLOSCIA, nie decyzja. Na stanowisku
    /// budujacego wskazywal rozpakowana dokumentacje SDK z 04.08.2026,
    /// podczas gdy baza byla juz na 61.1.1.9471 — Sfera odmawiala
    /// polaczenia, a most nigdy nie osiagal ready (09.09.2026).
    ///
    /// Reguła: jesli instalacja Subiekta ma NOWSZE biblioteki niz katalog
    /// z konfigu, wygrywa instalacja — bo to ona jest zgodna z baza, ktora
    /// aktualizuje sie razem z nia. Konfig zostaje uszanowany, gdy wskazuje
    /// biblioteki co najmniej tak swieze (albo gdy Subiekta tu nie ma).
    /// </summary>
    static string Rozstrzygnij(string? zKonfigu)
    {
        var zInstalacji = SzukajBinariowSubiekta();
        if (string.IsNullOrWhiteSpace(zKonfigu))
            return zInstalacji ?? DomyslnySdkBin();
        if (zInstalacji == null)
            return zKonfigu!;

        var kiedyKonfig = DataSfery(zKonfigu!);
        var kiedyInstalacja = DataSfery(zInstalacji);
        return kiedyInstalacja > kiedyKonfig ? zInstalacji : zKonfigu!;
    }

    /// <summary>Data pliku Sfery w katalogu; MinValue, gdy go nie ma.</summary>
    static DateTime DataSfery(string katalog)
    {
        try
        {
            var p = Path.Combine(katalog, "InsERT.Moria.Sfera.dll");
            return File.Exists(p) ? File.GetLastWriteTimeUtc(p) : DateTime.MinValue;
        }
        catch { return DateTime.MinValue; }
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
