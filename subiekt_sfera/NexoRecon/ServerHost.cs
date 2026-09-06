// ServerHost — staly most: NexoRecon.exe server
//
// Sedno przebudowy (SUBIEKT_STALY_MOST_PLAN.md): proces startuje raz, loguje
// sie do Sfery raz i obsluguje kolejne komendy z RM_BAZA przez ta sama sesje.
// Wczesniej kazde klikniecie placilo ~9-10 s za start procesu i logowanie.
//
// Architektura (plan sekcja 8) — JEDEN worker na sesje:
//
//     TcpListener (watek per klient)
//          |
//          v
//     BlockingCollection<Zadanie>
//          |
//          v
//     SferaWorker (JEDEN watek)
//          |
//          v
//     CommandDispatcher -> handlery -> Sfera
//
// Obiekty Sfery nie sa bezpieczne wielowatkowo i nie zakladamy, ze sa.
// Watki TCP nigdy nie dotykaja uchwytu — tylko wkladaja zadania do kolejki
// i czekaja na TaskCompletionSource.
//
// Transport: 4 bajty dlugosci little-endian + UTF-8 JSON (plan sekcja 6).
// Nasluch WYLACZNIE na 127.0.0.1 — bridge nie ma prawa wyjsc do LAN.

using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace NexoRecon;

internal static class ServerHost
{
    /// <summary>Wersja mostu — rosnie przy zmianach zachowania.</summary>
    public const string Wersja = "1.0.0";

    /// <summary>
    /// Wersja protokolu. Python zna minimalna zgodna wersje i po handshake
    /// wie, czy binarka jest starsza niz zrodla (plan sekcja 25-26) — pewniej
    /// niz dotychczasowe porownywanie dat plikow .cs i .exe.
    /// </summary>
    public const int Protokol = 1;

    /// <summary>Port loopback. Staly, zeby Python nie musial go szukac.</summary>
    public const int Port = 51273;

    /// <summary>Zadanie w kolejce: komenda + miejsce na odpowiedz.</summary>
    sealed record Zadanie(JsonObject Zadanie_, TaskCompletionSource<JsonObject> Wynik);

    static readonly BlockingCollection<Zadanie> Kolejka = new();
    static readonly Stopwatch Uptime = Stopwatch.StartNew();

    // Stan raportowany przez "status". Pisze go worker, czytaja watki TCP,
    // wiec leci przez volatile / Interlocked zamiast blokady.
    static volatile string _ostatniaKomenda = "";
    static long _ostatniaMs;
    static volatile NexoSession? _sesja;
    static int _obsluzonych;

    public static int Uruchom(string cfgPath, bool konsola)
    {
        // Jeden bridge na uzytkownika Windows (plan sekcja 24). Mutex per
        // uzytkownik, nie Global\ — na terminalu kilka sesji moze miec
        // wlasne stanowiska, a kazde ma prawo do swojego mostu.
        using var mutex = new Mutex(true, $"Local\\RMPAK_NEXO_BRIDGE_{Environment.UserName}", out var pierwszy);
        if (!pierwszy)
        {
            Powiedz("Bridge already running.");
            return 4;
        }

        NexoSession sesja;
        try
        {
            sesja = NexoSession.Wczytaj(cfgPath);
        }
        catch (SesjaException ex)
        {
            Powiedz(ex.Message);
            return ex.KodWyjscia;
        }

        _sesja = sesja;
        using (sesja)
        {
            TcpListener listener;
            try
            {
                // WYLACZNIE loopback — nigdy IPAddress.Any (plan sekcja 5, 12).
                listener = new TcpListener(IPAddress.Loopback, Port);
                listener.Start();
            }
            catch (SocketException ex)
            {
                Powiedz($"Nie mozna nasluchiwac na 127.0.0.1:{Port}: {ex.Message}");
                return 5;
            }

            Log($"start bridge pid={Environment.ProcessId} port={Port} wersja={Wersja} protokol={Protokol}");
            if (konsola) Powiedz($"Bridge nasluchuje na 127.0.0.1:{Port} (pid {Environment.ProcessId}). Ctrl+C konczy.");

            // JEDEN watek roboczy — jedyny, ktory dotyka Sfery.
            var worker = new Thread(() => PetlaWorkera(sesja)) { IsBackground = true, Name = "SferaWorker" };
            worker.Start();

            // Logowanie do Sfery robi worker, jako pierwsze zadanie w kolejce.
            // Dzieki temu listener stoi od razu i odpowiada na ping "ready=false"
            // zamiast odrzucac polaczenia przez pierwsze ~10 s.
            Kolejka.Add(new Zadanie(new JsonObject { ["command"] = "__connect" },
                                    new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously)));

            while (true)
            {
                TcpClient klient;
                try { klient = listener.AcceptTcpClient(); }
                catch (SocketException) { break; }

                // Watek per klient: RM_BAZA ma wiele okien i kazde moze trzymac
                // wlasne polaczenie. Serializacja i tak nastapi w kolejce.
                var t = new Thread(() => ObsluzKlienta(klient)) { IsBackground = true };
                t.Start();
            }
            return 0;
        }
    }

    // ── worker: jedyny watek dotykajacy Sfery ────────────────────────────────
    static void PetlaWorkera(NexoSession sesja)
    {
        foreach (var z in Kolejka.GetConsumingEnumerable())
        {
            try
            {
                z.Wynik.SetResult(Obsluz(sesja, z.Zadanie_));
            }
            catch (Exception ex)
            {
                z.Wynik.SetResult(Blad("INTERNAL", ex.Message, retryable: false));
            }
        }
    }

    static JsonObject Obsluz(NexoSession sesja, JsonObject zad)
    {
        var cmd = (zad["command"]?.GetValue<string>() ?? "").ToLowerInvariant();

        // Wewnetrzne: pierwsze logowanie po starcie.
        if (cmd == "__connect")
        {
            try
            {
                var t = Stopwatch.StartNew();
                sesja.Connect();
                _ostatniaAktywnosc = DateTime.UtcNow;
                Log($"session_start ok ms={t.ElapsedMilliseconds} operator={sesja.Operator}");
                return Ok(new JsonObject());
            }
            catch (SesjaException ex)
            {
                Log($"session_start FAIL {ex.Message.Replace("\n", " | ")}");
                return Blad("SESSION_START_FAILED", ex.Message, retryable: false);
            }
        }

        var argsNode = zad["args"] as JsonObject ?? new JsonObject();
        // Jeden katalog na cale zadanie: plan wejsciowy i wynik handlera.
        // Kasowany w finally WykonajRaz, wiec %TEMP% nie rosnie.
        var katalogRoboczy = Path.Combine(Path.GetTempPath(), "nexo_bridge",
                                          Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(katalogRoboczy);
        var komenda = ZbudujKomende(cmd, argsNode, katalogRoboczy);
        var zapis = CommandDispatcher.CzyZapis(komenda);

        // Sesja po dluzszej przerwie (uspiony komputer, restart SQL) bywa
        // martwa, choc Stan mowi Ready. Sprawdzamy to PRZED handlerem, nie
        // dopiero po jego wyjatku — z dwoch powodow:
        //  * wyjatek z martwej sesji potrafi przyjsc po timeoutcie TCP,
        //    czyli po kilkudziesieciu sekundach zamiast od razu;
        //  * dla ZAPISU pad przed startem handlera jest jednoznaczny (nic sie
        //    nie wykonalo), a pad w trakcie — nie. Wykrycie go tutaj
        //    pozwala odpowiedziec SESSION_LOST retryable=true zamiast
        //    UNKNOWN_COMMIT_STATE i odsylania usera do Subiekta.
        // Tylko po bezczynnosci, zeby nie placic zapytania przy kazdym
        // klknieciu — przy zywej sesji jedna komenda po drugiej nie ma
        // szans jej zerwac.
        var blad = UpewnijSieZeSesjaZyje(sesja);
        if (blad != null) return blad;

        var zegar = Stopwatch.StartNew();
        var wynik = WykonajZReconnect(sesja, komenda, zapis, katalogRoboczy);
        zegar.Stop();
        _ostatniaAktywnosc = DateTime.UtcNow;

        _ostatniaKomenda = cmd;
        Interlocked.Exchange(ref _ostatniaMs, zegar.ElapsedMilliseconds);
        Interlocked.Increment(ref _obsluzonych);
        Log($"cmd={cmd} zapis={zapis} ms={zegar.ElapsedMilliseconds} ok={wynik["ok"]?.GetValue<bool>()}");
        return wynik;
    }

    /// <summary>Kiedy worker ostatnio z powodzeniem dotykal Sfery (UTC).</summary>
    static DateTime _ostatniaAktywnosc = DateTime.UtcNow;

    /// <summary>
    /// Po tylu sekundach bez komendy worker sprawdza sesje przed nastepna.
    /// Minuta: uspienie komputera trwa dluzej, a zwykla praca w oknie
    /// (klik, klik) miesci sie ponizej — wtedy nie placimy za sprawdzenie.
    /// </summary>
    const int BezczynnoscProgS = 60;

    /// <summary>
    /// Sprawdza sesje po dluzszej bezczynnosci i w razie potrzeby odbudowuje
    /// ja ZANIM ruszy handler. Null = mozna jechac. Blad = odpowiedz dla
    /// klienta; zawsze retryable, bo nic sie jeszcze nie wykonalo — takze
    /// dla zapisu (patrz komentarz w Obsluz).
    /// </summary>
    static JsonObject? UpewnijSieZeSesjaZyje(NexoSession sesja)
    {
        var bezczynnaS = (DateTime.UtcNow - _ostatniaAktywnosc).TotalSeconds;
        if (sesja.Stan == StanSesji.Ready && bezczynnaS < BezczynnoscProgS)
            return null;

        var t = Stopwatch.StartNew();
        if (sesja.CzyZywa())
        {
            Log($"session_check ok idle_s={bezczynnaS:F0} ms={t.ElapsedMilliseconds}");
            _ostatniaAktywnosc = DateTime.UtcNow;
            return null;
        }

        Log($"session_check DEAD idle_s={bezczynnaS:F0} stan={sesja.Stan} — reconnect przed komenda");
        try
        {
            t.Restart();
            sesja.Reconnect();
            Log($"reconnect_ok (pre-check) ms={t.ElapsedMilliseconds}");
            _ostatniaAktywnosc = DateTime.UtcNow;
            return null;
        }
        catch (SesjaException ex)
        {
            Log($"reconnect_FAIL (pre-check) {ex.Message.Replace("\n", " | ")}");
            // Nic nie ruszylo, wiec klient moze bezpiecznie ponowic — takze zapis.
            return Blad("SESSION_LOST",
                "Sesja Sfery padla (np. po uspieniu komputera) i nie udalo sie jej odbudowac. " +
                "Operacja NIE zostala wykonana — mozna ponowic.\n\n" + ex.Message,
                retryable: true);
        }
    }

    /// <summary>
    /// Wykonuje komende, a przy zerwanej sesji probuje raz ja odbudowac.
    /// KLUCZOWE (plan sekcja 14): ponowienie jest dozwolone TYLKO dla odczytu.
    /// Przy zapisie nie wiadomo, czy operacja przeszla, wiec zwracamy
    /// UNKNOWN_COMMIT_STATE i pozwalamy zdecydowac czlowiekowi/handlerowi.
    /// </summary>
    static JsonObject WykonajZReconnect(NexoSession sesja, Komenda k, bool zapis, string katalog)
    {
        try
        {
            return WykonajRaz(sesja, k, katalog);
        }
        catch (Exception ex)
        {
            if (sesja.CzyZywa())
                return Blad("HANDLER_ERROR", ex.Message, retryable: false);

            Log($"session_lost cmd={k.Tryb} {ex.Message}");

            if (zapis)
            {
                // Sesja byla zywa na starcie (pre-check w Obsluz), a padla
                // W TRAKCIE handlera — to jedyny naprawde niejednoznaczny
                // przypadek: nie wiemy, czy zapis przeszedl. Zadnego
                // automatycznego powtorzenia — od tego sa duplikaty ZD.
                try { sesja.Reconnect(); Log("reconnect_ok (po zapisie)"); } catch { /* zglosimy nizej */ }
                return Blad("UNKNOWN_COMMIT_STATE",
                    "Utracono sesje Sfery W TRAKCIE operacji zapisujacej. Nie wiadomo, czy zmiana " +
                    "zostala zapisana. Sprawdz stan w Subiekcie przed ponowieniem.\n\n" + ex.Message,
                    retryable: false);
            }

            try
            {
                var t = Stopwatch.StartNew();
                sesja.Reconnect();
                Log($"reconnect_ok ms={t.ElapsedMilliseconds}");
            }
            catch (SesjaException re)
            {
                Log($"reconnect_FAIL {re.Message.Replace("\n", " | ")}");
                return Blad("SESSION_LOST", re.Message, retryable: true);
            }

            try
            {
                return WykonajRaz(sesja, k, katalog);
            }
            catch (Exception ex2)
            {
                return Blad("HANDLER_ERROR", ex2.Message, retryable: false);
            }
        }
    }

    /// <summary>
    /// Uruchamia handler i zbiera jego wynik. Handlery pisza JSON do pliku
    /// (--out) i komunikaty bledow na stdout — kontrakt zostaje nietkniety,
    /// wiec server materializuje plik tymczasowy i przechwytuje stdout.
    /// Dzieki temu Krok E nie wymaga zmian w zadnym handlerze.
    /// </summary>
    static JsonObject WykonajRaz(NexoSession sesja, Komenda k, string katalog)
    {
        var outPath = Path.Combine(katalog, "out.json");

        var stary = Console.Out;
        var buf = new StringWriter();
        int kod;
        try
        {
            Console.SetOut(buf);
            kod = CommandDispatcher.Wykonaj(sesja.Sfera, k with { OutPath = outPath });
        }
        finally
        {
            Console.SetOut(stary);
        }

        var stdout = buf.ToString().Trim();
        try
        {
            if (kod != 0)
                return Blad("COMMAND_FAILED", stdout.Length > 0 ? stdout : $"Most zwrocil kod {kod}.", retryable: false);

            if (!File.Exists(outPath))
                return Blad("NO_OUTPUT", stdout.Length > 0 ? stdout : "Handler nie zapisal wyniku.", retryable: false);

            var tresc = File.ReadAllText(outPath);
            var dane = JsonNode.Parse(tresc) as JsonObject
                       ?? new JsonObject { ["wynik"] = JsonNode.Parse(tresc) };
            return Ok(dane);
        }
        finally
        {
            try { Directory.Delete(katalog, true); } catch { /* smieci w %TEMP% nie sa warte wyjatku */ }
        }
    }

    /// <summary>Mapuje args JSON na Komende — odpowiednik parsowania --flag w CLI.</summary>
    static Komenda ZbudujKomende(string tryb, JsonObject a, string katalogRoboczy)
    {
        List<string>? symbole = null;
        if (a["symbols"] is JsonArray arr)
            symbole = arr.Select(x => x?.GetValue<string>() ?? "").Where(s => s.Length > 0).ToList();

        // Plany przychodza jako obiekt/tablica JSON, a handlery czytaja je
        // z pliku. Zapisujemy wiec do %TEMP% zamiast przerabiac handlery —
        // ale do TEGO SAMEGO katalogu, ktory WykonajRaz kasuje w finally.
        // Wczesniej plan mial wlasny katalog, ktorego nikt nie sprzatal:
        // 27 pozostalosci z plan.json po trzech dniach (znalezione 06.09.2026).
        string? planPath = null;
        if (a["plan"] is JsonNode plan)
        {
            planPath = Path.Combine(katalogRoboczy, "plan.json");
            File.WriteAllText(planPath, plan.ToJsonString(), new UTF8Encoding(false));
        }

        return new Komenda(
            Tryb: tryb,
            Symbole: symbole,
            PlanPath: planPath,
            Zapisz: a["zapisz"]?.GetValue<bool>() ?? false,
            Limit: a["limit"]?.GetValue<int>() ?? 15,
            Numery: a["numery"]?.GetValue<string>(),
            Magazyn: a["magazyn"]?.GetValue<string>(),
            Data: a["data"]?.GetValue<string>(),
            SymboleCsv: a["symbole"]?.GetValue<string>(),
            Projekt: a["projekt"]?.GetValue<string>(),
            PdfDir: a["pdf"]?.GetValue<string>(),
            TylkoNiezerowe: a["tylko_niezerowe"]?.GetValue<bool>() ?? false);
    }

    // ── obsluga polaczenia ───────────────────────────────────────────────────
    static void ObsluzKlienta(TcpClient klient)
    {
        using (klient)
        using (var s = klient.GetStream())
        {
            try
            {
                while (true)
                {
                    var zadanie = Czytaj(s);
                    if (zadanie is null) return;      // klient zamknal polaczenie

                    var cmd = (zadanie["command"]?.GetValue<string>() ?? "").ToLowerInvariant();
                    JsonObject odp;

                    // ping i status NIE ida do kolejki (plan sekcja 10):
                    // maja odpowiadac natychmiast, takze gdy worker mieli
                    // ciezki magazyn albo wisi na reconnect.
                    if (cmd == "ping") odp = Ping();
                    else if (cmd == "status") odp = Status();
                    else if (!CommandDispatcher.Zna(cmd))
                        odp = Blad("UNKNOWN_COMMAND", $"Nieznana komenda: {cmd}", retryable: false);
                    else
                    {
                        var tcs = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
                        Kolejka.Add(new Zadanie(zadanie, tcs));
                        odp = tcs.Task.GetAwaiter().GetResult();   // timeout pilnuje klient
                    }

                    odp["request_id"] = zadanie["request_id"]?.DeepClone();
                    odp["protocol"] = Protokol;
                    Wyslij(s, odp);
                }
            }
            catch (IOException) { /* zerwane polaczenie to normalny koniec */ }
            catch (Exception ex) { Log($"blad klienta: {ex.Message}"); }
        }
    }

    static JsonObject Ping() => Ok(new JsonObject
    {
        ["ready"] = _sesja?.Stan == StanSesji.Ready,
        ["pid"] = Environment.ProcessId,
        ["bridge_version"] = Wersja,
        ["protocol"] = Protokol,
    });

    static JsonObject Status()
    {
        var s = _sesja;
        return Ok(new JsonObject
        {
            ["ready"] = s?.Stan == StanSesji.Ready,
            ["state"] = s?.Stan.ToString() ?? "Unknown",
            ["session_connected"] = s?.Stan == StanSesji.Ready,
            ["user"] = s?.Operator,
            ["computer"] = Environment.MachineName,
            ["pid"] = Environment.ProcessId,
            ["uptime_s"] = (long)Uptime.Elapsed.TotalSeconds,
            ["queue_length"] = Kolejka.Count,
            ["logins"] = s?.LicznikLogowan ?? 0,
            ["handled"] = Volatile.Read(ref _obsluzonych),
            ["last_request"] = _ostatniaKomenda,
            ["last_request_ms"] = Interlocked.Read(ref _ostatniaMs),
            ["bridge_version"] = Wersja,
        });
    }

    // ── framing: 4 bajty dlugosci LE + UTF-8 JSON ────────────────────────────
    /// <summary>Maksymalny rozmiar zadania — zapora przed bledna dlugoscia.</summary>
    const int MaxRamka = 64 * 1024 * 1024;

    static JsonObject? Czytaj(NetworkStream s)
    {
        var naglowek = new byte[4];
        if (!CzytajDokladnie(s, naglowek, 4)) return null;
        var dlugosc = BitConverter.ToInt32(naglowek, 0);
        if (dlugosc <= 0 || dlugosc > MaxRamka)
            throw new IOException($"Bledna dlugosc ramki: {dlugosc}");

        var bufor = new byte[dlugosc];
        if (!CzytajDokladnie(s, bufor, dlugosc)) return null;
        return JsonNode.Parse(Encoding.UTF8.GetString(bufor)) as JsonObject
               ?? throw new IOException("Zadanie nie jest obiektem JSON.");
    }

    static bool CzytajDokladnie(NetworkStream s, byte[] bufor, int ile)
    {
        var razem = 0;
        while (razem < ile)
        {
            var n = s.Read(bufor, razem, ile - razem);
            if (n == 0) return false;     // koniec strumienia
            razem += n;
        }
        return true;
    }

    static void Wyslij(NetworkStream s, JsonObject odp)
    {
        var bajty = Encoding.UTF8.GetBytes(odp.ToJsonString());
        s.Write(BitConverter.GetBytes(bajty.Length), 0, 4);
        s.Write(bajty, 0, bajty.Length);
        s.Flush();
    }

    // ── odpowiedzi ───────────────────────────────────────────────────────────
    static JsonObject Ok(JsonObject dane) => new()
    {
        ["protocol"] = Protokol,
        ["ok"] = true,
        ["data"] = dane,
    };

    static JsonObject Blad(string kod, string komunikat, bool retryable) => new()
    {
        ["protocol"] = Protokol,
        ["ok"] = false,
        ["error"] = new JsonObject
        {
            ["code"] = kod,
            ["message"] = komunikat,
            ["retryable"] = retryable,
        },
    };

    /// <summary>
    /// Komunikat dla czlowieka. Trafia na konsole, ale ZAWSZE tez do logu:
    /// RM_BAZA startuje most z DETACHED_PROCESS, wiec konsoli nie ma i sam
    /// Console.WriteLine rzuca IOException, gubiac przyczyne bledu.
    /// </summary>
    static void Powiedz(string tekst)
    {
        try { Console.WriteLine(tekst); } catch (IOException) { }
        Log(tekst.Replace("\n", " | "));
    }

    // ── log wydajnosci (plan sekcja 22) ──────────────────────────────────────
    static readonly object _logLock = new();

    static void Log(string tekst)
    {
        try
        {
            var dir = @"C:\RMPAK_CLIENT\subiekt_logi";
            Directory.CreateDirectory(dir);
            var plik = Path.Combine(dir, $"bridge_{DateTime.Now:yyyyMMdd}.log");
            lock (_logLock)
                File.AppendAllText(plik, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {tekst}{Environment.NewLine}");
        }
        catch { /* brak logu nie moze zatrzymac mostu */ }
    }
}
