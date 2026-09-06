// NexoSession — cykl zycia polaczenia ze Sfera, wydzielony z Program.cs.
//
// Po co: do tej pory polaczenie powstawalo i ginelo razem z procesem
// (Program.cs: mp.Polacz(...) -> using (sfera) { ...jedna komenda... }).
// Kazde klikniecie w RM_BAZA placilo wiec ~9-10 s na start procesu,
// Polacz() i ZalogujOperatora(). Przy trybie "server" ten sam uchwyt ma
// obsluzyc setki komend, wiec logowanie musi byc oddzielone od wykonania
// komendy i musi dac sie powtorzyc bez restartu procesu.
//
// Tryb CLI korzysta z tej samej klasy — patrz SferaHost.Uruchom. Dzieki temu
// nie ma dwoch sciezek logowania, ktore moglyby sie rozjechac.
//
// UWAGA na watki: ta klasa NIE jest bezpieczna wielowatkowo i taka byc nie
// musi. Zalozenie calej przebudowy (SUBIEKT_STALY_MOST_PLAN.md sekcja 8) jest
// takie, ze wszystkie wywolania Sfery robi JEDEN dedykowany worker.

using System.IO;
using System.Runtime.Loader;
using System.Text.Json;
using InsERT.Moria.Sfera;
using InsERT.Mox.Product;

namespace NexoRecon;

/// <summary>Konfiguracja polaczenia z <c>C:\RMPAK_CLIENT\.nexo_sfera.json</c>.</summary>
internal record Konfig(string Serwer, string Baza, bool SqlWindowsAuth, string? SqlUser, string? SqlHaslo,
                       string NexoLogin, string NexoHaslo, string? SdkBin);

/// <summary>Stan sesji — raportowany przez komende <c>status</c>.</summary>
internal enum StanSesji { Starting, Ready, Reconnecting, Error, Stopping }

/// <summary>Blad zestawienia sesji. Niesie kod wyjscia zgodny ze starym CLI.</summary>
internal sealed class SesjaException : Exception
{
    /// <summary>Kod wyjscia procesu: 1 = konfig, 2 = Polacz, 3 = logowanie.</summary>
    public int KodWyjscia { get; }

    public SesjaException(int kodWyjscia, string message) : base(message) => KodWyjscia = kodWyjscia;
}

/// <summary>
/// Utrzymuje polaczenie ze Sfera. W trybie CLI zyje tyle co jedna komenda,
/// w trybie server — cala sesje Windows uzytkownika.
/// </summary>
internal sealed class NexoSession : IDisposable
{
    readonly Konfig _cfg;
    MenedzerPolaczen? _mp;
    Uchwyt? _sfera;

    public StanSesji Stan { get; private set; } = StanSesji.Starting;

    /// <summary>Login operatora nexo — do <c>status</c>. Hasla nie ujawniamy.</summary>
    public string Operator => _cfg.NexoLogin;

    /// <summary>Kiedy sesja zostala zestawiona (ostatni udany <see cref="Connect"/>).</summary>
    public DateTime? ZalogowanoO { get; private set; }

    /// <summary>Ile razy sesja byla zestawiana — 1 przy zdrowym dniu pracy.</summary>
    public int LicznikLogowan { get; private set; }

    NexoSession(Konfig cfg) => _cfg = cfg;

    /// <summary>
    /// Wczytuje konfig i podpina rozwiazywanie bibliotek SDK. Samo
    /// <see cref="Connect"/> jest osobno, bo w trybie server chcemy najpierw
    /// wystartowac (i miec czym odpowiedziec na ping), a dopiero potem placic
    /// ~10 s na logowanie.
    /// </summary>
    public static NexoSession Wczytaj(string cfgPath)
    {
        if (!File.Exists(cfgPath))
            throw new SesjaException(1,
                $"BRAK KONFIGU: {cfgPath}\n" +
                @"Skopiuj subiekt_sfera\nexo_sfera.example.json do C:\RMPAK_CLIENT\.nexo_sfera.json i uzupelnij hasla.");

        var cfg = JsonSerializer.Deserialize<Konfig>(File.ReadAllText(cfgPath),
                      new JsonSerializerOptions { PropertyNameCaseInsensitive = true, ReadCommentHandling = JsonCommentHandling.Skip })!;

        // Ubezpieczenie: jesli jakiejs biblioteki nexo nie skopiowalo do bin,
        // doladuj ja z Bin SDK. Hook jest globalny i idempotentny w praktyce
        // (ten sam katalog), ale podpinamy go raz — patrz _hookPodpiety.
        SdkLoader.Podepnij(cfg.SdkBin ?? SdkLoader.DomyslnySdkBin());
        return new NexoSession(cfg);
    }

    // DomyslnySdkBin() i PodepnijSdk() przeniesione do SdkLoader.cs — hook
    // musi dac sie podpiac z miejsca, ktorego JIT nie wymaga bibliotek InsERT,
    // a ta klasa ma pola typu Uchwyt/MenedzerPolaczen.

    /// <summary>Opis polaczenia na naglowek CLI (bez hasel).</summary>
    public string OpisPolaczenia =>
        $"Sfera {DanePolaczenia.WersjaSfery}  ->  serwer={_cfg.Serwer}  baza={_cfg.Baza}  " +
        $"auth={(_cfg.SqlWindowsAuth ? "Windows" : "SQL:" + _cfg.SqlUser)}";

    /// <summary>Uchwyt Sfery. Rzuca, jesli sesja nie jest zestawiona.</summary>
    public Uchwyt Sfera => _sfera ?? throw new InvalidOperationException("Sesja Sfery nie jest zestawiona.");

    /// <summary>
    /// Zestawia polaczenie i loguje operatora. To jest te ~9-10 s, ktore
    /// w trybie server placimy raz na start stanowiska.
    /// </summary>
    public void Connect()
    {
        Rozlacz();
        Stan = StanSesji.Starting;

        var dane = _cfg.SqlWindowsAuth
            ? DanePolaczenia.Jawne(_cfg.Serwer, _cfg.Baza, true)
            : DanePolaczenia.Jawne(_cfg.Serwer, _cfg.Baza, false, _cfg.SqlUser, _cfg.SqlHaslo);

        _mp = new MenedzerPolaczen();
        try
        {
            // Tylko Subiekt — kazdy dodatkowy produkt to dodatkowa licencja PRO.
            _sfera = _mp.Polacz(dane, ProductId.Subiekt);
        }
        catch (Exception ex)
        {
            Stan = StanSesji.Error;
            throw new SesjaException(2,
                "BLAD POLACZENIA (Polacz): " + ex.Message + "\n" +
                "Typowe przyczyny (FAQ SDK): brak przedrostka nexo_ w nazwie bazy; brak licencji PRO Subiekta na tej bazie;\n" +
                "wersja SDK != wersja bazy; baza ma oczekujace aktualizacje (uruchom Subiekta).");
        }

        if (!_sfera.ZalogujOperatora(_cfg.NexoLogin, _cfg.NexoHaslo))
        {
            Stan = StanSesji.Error;
            throw new SesjaException(3,
                $"BLAD: logowanie operatora nexo '{_cfg.NexoLogin}' nie powiodlo sie " +
                "(login = pole Login w Konfiguracja -> Uzytkownicy).");
        }

        Stan = StanSesji.Ready;
        ZalogowanoO = DateTime.Now;
        LicznikLogowan++;
    }

    /// <summary>
    /// Czy sesja odpowiada. Lekkie zapytanie o magazyny — jest ich kilka,
    /// wiec koszt jest pomijalny, a przechodzi cala droge do SQL, wiec
    /// wykryje zerwane polaczenie (uspiony komputer, restart SQL).
    /// </summary>
    public bool CzyZywa()
    {
        if (_sfera is null || Stan != StanSesji.Ready) return false;
        try
        {
            _ = _sfera.Magazyny().Dane.Wszystkie().Count();
            return true;
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Zamyka stara sesje i zestawia nowa. Wolane, gdy komenda READ padla
    /// na zerwanej sesji. Dla WRITE patrz sekcja 14 planu — tam ponowienie
    /// jest zabronione, bo nie wiadomo, czy zapis przeszedl.
    /// </summary>
    public void Reconnect()
    {
        Stan = StanSesji.Reconnecting;
        Connect();
    }

    void Rozlacz()
    {
        try { _sfera?.Dispose(); } catch { /* zamykanie nie moze wywalic procesu */ }
        _sfera = null;
        _mp = null;   // MenedzerPolaczen nie jest IDisposable — zwalnia go GC
    }

    public void Dispose()
    {
        Stan = StanSesji.Stopping;
        Rozlacz();
    }
}
