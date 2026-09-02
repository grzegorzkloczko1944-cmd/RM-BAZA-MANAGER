// NexoRecon — rozpoznanie bazy Subiekt nexo PRO przez Sferę. TYLKO ODCZYT.
//
// Użycie:  NexoRecon.exe [sciezka\do\konfig.json] [--symbol=ABC-123 ...] [--limit=20]
// Konfig domyślnie: C:\RMPAK_CLIENT\.nexo_sfera.json  (poza repo! wzór: ..\nexo_sfera.example.json)
//
// Odpowiada na pytania z SUBIEKT_INTEGRACJA_PLAN.md sekcja 7:
//  - czy da się połączyć Sferą (licencja PRO na bazie, wersja SDK = wersja bazy),
//  - jak wyglądają symbole kartotek (mapowanie po numerze rysunku),
//  - jakie są magazyny, stany, kontrahenci, dokumenty ZD/PZ/WZ/RW.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.Loader;
using System.Text;
using System.Text.Json;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;
using InsERT.Mox.Product;

Console.OutputEncoding = Encoding.UTF8;

var cfgPath = args.FirstOrDefault(a => a.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
              ?? @"C:\RMPAK_CLIENT\.nexo_sfera.json";
var szukane = args.Where(a => a.StartsWith("--symbol=")).Select(a => a["--symbol=".Length..]).ToList();
var limit = int.TryParse(args.FirstOrDefault(a => a.StartsWith("--limit="))?["--limit=".Length..], out var l) ? l : 15;

if (!File.Exists(cfgPath))
{
    Console.WriteLine($"BRAK KONFIGU: {cfgPath}");
    Console.WriteLine(@"Skopiuj subiekt_sfera\nexo_sfera.example.json do C:\RMPAK_CLIENT\.nexo_sfera.json i uzupełnij hasła.");
    return 1;
}
var cfg = JsonSerializer.Deserialize<Konfig>(File.ReadAllText(cfgPath),
              new JsonSerializerOptions { PropertyNameCaseInsensitive = true, ReadCommentHandling = JsonCommentHandling.Skip })!;

// Ubezpieczenie: jeśli jakiejś biblioteki nexo nie skopiowało do bin, doładuj ją z Bin SDK.
var sdkBin = cfg.SdkBin ?? @"C:\iLogic\Subiekt_nexo_PRO_dokumentacja\SDK\Bin\";
AssemblyLoadContext.Default.Resolving += (ctx, name) =>
{
    var p = Path.Combine(sdkBin, name.Name + ".dll");
    return File.Exists(p) ? ctx.LoadFromAssemblyPath(p) : null;
};

Console.WriteLine($"Sfera {DanePolaczenia.WersjaSfery}  ->  serwer={cfg.Serwer}  baza={cfg.Baza}  auth={(cfg.SqlWindowsAuth ? "Windows" : "SQL:" + cfg.SqlUser)}");
Console.WriteLine($"Proces 64-bit: {Environment.Is64BitProcess}   (Sfera nexo >=57 wymaga 64-bit)");

var dane = cfg.SqlWindowsAuth
    ? DanePolaczenia.Jawne(cfg.Serwer, cfg.Baza, true)
    : DanePolaczenia.Jawne(cfg.Serwer, cfg.Baza, false, cfg.SqlUser, cfg.SqlHaslo);

var mp = new MenedzerPolaczen();
Uchwyt sfera;
try
{
    sfera = mp.Polacz(dane, ProductId.Subiekt);   // tylko Subiekt — każdy dodatkowy produkt = dodatkowa licencja PRO
}
catch (Exception ex)
{
    Console.WriteLine("BŁĄD POŁĄCZENIA (Polacz): " + ex.Message);
    Console.WriteLine("Typowe przyczyny (FAQ SDK): brak przedrostka nexo_ w nazwie bazy; brak licencji PRO Subiekta na tej bazie;");
    Console.WriteLine("wersja SDK != wersja bazy; baza ma oczekujące aktualizacje (uruchom Subiekta).");
    return 2;
}
using (sfera)
{
    if (!sfera.ZalogujOperatora(cfg.NexoLogin, cfg.NexoHaslo))
    {
        Console.WriteLine($"BŁĄD: logowanie operatora nexo '{cfg.NexoLogin}' nie powiodło się (login = pole Login w Konfiguracja -> Użytkownicy).");
        return 3;
    }
    Console.WriteLine($"Zalogowano operatora: {cfg.NexoLogin}");

    // ───────────────────────── MAGAZYNY ─────────────────────────
    var magazyny = new List<Magazyn>();
    Sekcja("MAGAZYNY", () =>
    {
        magazyny = sfera.Magazyny().Dane.Wszystkie().ToList();
        foreach (var m in magazyny)
            Console.WriteLine($"  {m.Symbol,-10} {m.Nazwa,-40} id={m.Id}");
    });

    // ───────────────────────── KARTOTEKI ─────────────────────────
    Sekcja("KARTOTEKI ASORTYMENTU", () =>
    {
        var asort = sfera.Asortymenty();
        var q = asort.Dane.Wszystkie();
        var razem = q.Count();
        Console.WriteLine($"  razem: {razem}");
        try
        {
            foreach (var g in q.GroupBy(a => a.Rodzaj.Nazwa).Select(g => new { g.Key, N = g.Count() }).ToList())
                Console.WriteLine($"  rodzaj={g.Key}: {g.N}");
        }
        catch (Exception ex) { Console.WriteLine("  (grupowanie wg rodzaju nieudane: " + ex.Message + ")"); }

        // Kształt symboli — czy wyglądają jak numery rysunków?
        var symbole = q.Select(a => a.Symbol).ToList();
        var dl = symbole.Where(s => s != null).GroupBy(s => s!.Length).OrderBy(g => g.Key).ToList();
        Console.WriteLine("  długości symboli: " + string.Join(", ", dl.Select(g => $"{g.Key}:{g.Count()}")));
        Console.WriteLine($"  z myślnikiem: {symbole.Count(s => s?.Contains('-') == true)}   z '/': {symbole.Count(s => s?.Contains('/') == true)}   ze spacją: {symbole.Count(s => s?.Contains(' ') == true)}   tylko cyfry: {symbole.Count(s => s != null && s.All(char.IsDigit))}");

        Console.WriteLine($"  próbka {limit} (alfabetycznie):");
        foreach (var a in q.OrderBy(a => a.Symbol).Take(limit).ToList())
            Console.WriteLine($"    {a.Symbol,-25} {Skroc(a.Nazwa, 45),-45} rodzaj={Bezp(() => a.Rodzaj?.Nazwa)} grupa={Bezp(() => a.Grupa?.Nazwa)}");

        Console.WriteLine($"  próbka {limit} (najnowsze Id):");
        foreach (var a in q.OrderByDescending(a => a.Id).Take(limit).ToList())
            Console.WriteLine($"    {a.Symbol,-25} {Skroc(a.Nazwa, 45),-45} rodzaj={Bezp(() => a.Rodzaj?.Nazwa)}");
    });

    // ───────────────────────── SZUKANE SYMBOLE ─────────────────────────
    if (szukane.Count > 0) Sekcja("SZUKANE SYMBOLE (--symbol=)", () =>
    {
        var asort = sfera.Asortymenty();
        foreach (var s in szukane)
        {
            var a = asort.Dane.WyszukajPoSymbolu(s);
            if (a == null) { Console.WriteLine($"  {s}: BRAK kartoteki"); continue; }
            Console.WriteLine($"  {s}: {a.Nazwa}  rodzaj={Bezp(() => a.Rodzaj?.Nazwa)}  cenaEwid={a.CenaEwidencyjna}");
            WypiszStany(a);
        }
    });

    // ───────────────────────── STANY ─────────────────────────
    Sekcja("STANY MAGAZYNOWE", () =>
    {
        foreach (var m in magazyny)
        {
            var stany = m.StanyMagazynowe.ToList();
            var dodatnie = stany.Where(s => s.IloscDostepna > 0).ToList();
            Console.WriteLine($"  [{m.Symbol}] rekordów stanów: {stany.Count}, z dostępną ilością > 0: {dodatnie.Count}, zadysponowane>0: {stany.Count(s => s.IloscZadysponowana > 0)}");
            foreach (var s in dodatnie.OrderByDescending(s => s.IloscDostepna).Take(Math.Min(limit, 10)))
                Console.WriteLine($"     {Bezp(() => s.Asortyment?.Symbol),-25} dostępne={s.IloscDostepna,10}  zadysp={s.IloscZadysponowana,8}  rezIl={s.IloscZarezerwowanaIlosciowo,8}  rezDost={s.IloscZarezerwowanaDostawowo,8}");
        }
    });

    // ───────────────────────── KONTRAHENCI ─────────────────────────
    Sekcja("PODMIOTY / KONTRAHENCI", () =>
    {
        var podm = sfera.Podmioty();
        var firmy = podm.Dane.WszystkieFirmy().ToList();
        Console.WriteLine($"  firm: {firmy.Count}   kontrahent=true: {firmy.Count(p => Convert.ToBoolean((object?)p.Kontrahent))}   aktywnych: {firmy.Count(p => Convert.ToBoolean((object?)p.Aktywny))}");
        foreach (var p in firmy.OrderBy(p => p.NazwaSkrocona).Take(limit))
            Console.WriteLine($"    {Skroc(p.NazwaSkrocona, 40),-40} NIP={p.NIP,-12} tel={p.Telefon}");
    });

    // ───────────────────────── DOKUMENTY ─────────────────────────
    Dokumenty("ZD  zamówienia do dostawców", () => sfera.ZamowieniaDoDostawcow().Dane.Wszystkie(), pokazPozycje: true);
    Dokumenty("PZ  przyjęcia zewnętrzne",    () => sfera.PrzyjeciaZewnetrzne().Dane.Wszystkie(), pokazPozycje: true);
    Dokumenty("WZ  wydania zewnętrzne",      () => sfera.WydaniaZewnetrzne().Dane.Wszystkie());
    Dokumenty("RW  rozchody wewnętrzne",     () => sfera.RozchodyWewnetrzne().Dane.Wszystkie(), pokazPozycje: true);

    Console.WriteLine("\nKONIEC — nic nie zostało zapisane.");
    return 0;
}

// ───────────────────────── pomocnicze ─────────────────────────
void Sekcja(string tytul, Action a)
{
    Console.WriteLine($"\n=== {tytul} ===");
    try { a(); }
    catch (Exception ex) { Console.WriteLine($"  !! błąd sekcji: {ex.GetType().Name}: {ex.Message}"); }
}

void Dokumenty(string tytul, Func<IQueryable<Dokument>> zrodlo, bool pokazPozycje = false) => Sekcja(tytul, () =>
{
    var q = zrodlo();
    Console.WriteLine($"  razem: {q.Count()}");
    var ostatnie = q.OrderByDescending(d => d.DataWprowadzenia).Take(Math.Min(limit, 8)).ToList();
    foreach (var d in ostatnie)
        Console.WriteLine($"    {Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura),-22} wyst={d.DataWydaniaWystawienia:yyyy-MM-dd} wprow={d.DataWprowadzenia:yyyy-MM-dd}  {Skroc(Bezp(() => d.Podmiot?.NazwaSkrocona), 30),-30} mag={Bezp(() => d.Magazyn?.Symbol),-6} poz={Bezp(() => d.Pozycje.Count().ToString())}  status={Bezp(() => d.StatusDokumentu?.ToString())}");
    if (pokazPozycje && ostatnie.Count > 0)
    {
        var d = ostatnie[0];
        Console.WriteLine($"  pozycje najnowszego ({Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura)}):");
        foreach (var p in d.Pozycje.Take(limit))
            Console.WriteLine($"     {Bezp(() => p.AsortymentAktualny?.Symbol),-25} {Skroc(Bezp(() => p.AsortymentAktualny?.Nazwa), 40),-40} ilość={p.Ilosc,10} {Bezp(() => p.JednostkaMiaryAs?.ToString())}");
    }
});

void WypiszStany(Asortyment a)
{
    foreach (var s in a.StanyMagazynowe)
        Console.WriteLine($"     mag={Bezp(() => s.Magazyn?.Symbol),-6} dostępne={s.IloscDostepna}  zadysp={s.IloscZadysponowana}  rezIl={s.IloscZarezerwowanaIlosciowo}  rezDost={s.IloscZarezerwowanaDostawowo}");
}

static string? Bezp(Func<string?> f) { try { return f(); } catch { return "?"; } }
static string Skroc(string? s, int n) => s == null ? "" : (s.Length <= n ? s : s[..(n - 1)] + "...");

record Konfig(string Serwer, string Baza, bool SqlWindowsAuth, string? SqlUser, string? SqlHaslo,
              string NexoLogin, string NexoHaslo, string? SdkBin);
