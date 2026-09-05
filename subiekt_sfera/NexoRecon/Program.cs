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

// Konfig = argument pozycyjny konczacy sie .json. Wyklucz przelaczniki (--out=... tez konczy sie .json).
var cfgPath = args.FirstOrDefault(a => !a.StartsWith("--") && a.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
              ?? @"C:\RMPAK_CLIENT\.nexo_sfera.json";
var szukane = args.Where(a => a.StartsWith("--symbol=")).Select(a => a["--symbol=".Length..]).ToList();

// Tryb "stan": wyjscie JSON dla RM_BAZA (patrz Stan.cs). Symbole z pliku
// (po jednym w linii) albo z --symbol=. Plik, bo BOM potrafi miec setki pozycji,
// a wiersz polecenia Windows ma limit dlugosci.
// Nazwa trybu = pierwszy argument. Jeden string zamiast N zmiennych bool,
// bo przy kazdym nowym trybie trzeba bylo dopisywac sie w trzech miejscach
// (deklaracja + dwa warunki "czy wypisywac naglowek") i latwo bylo o tym
// zapomniec - wtedy tryb maszynowy zasmiecal JSON tekstem powitalnym.
var tryb = args.Length > 0 && !args[0].StartsWith("--") ? args[0].ToLowerInvariant() : "";
// Tryby maszynowe: wyjscie czyta Python, wiec zadnych naglowkow na stdout
// (chyba ze jest --out=, wtedy JSON idzie do pliku i stdout jest wolny).
//   stan            - punktowe zapytania o symbole + stany (Stan.cs)
//   katalog         - pelna lista {Symbol, Nazwa} do fuzzy match (Katalog.cs)
//   zapotrzebowanie - czego brakuje na otwartych ZK (Zapotrzebowanie.cs)
//   projekt         - kartoteki/komplety/ZK; JEDYNY tryb ZAPISUJACY, i tylko z --zapisz
//   zd              - zamowienia do dostawcow z wybranych pozycji; ZAPISUJE (--zapisz)
//   zd-usun         - kasuje ZD o podanych numerach; USUWA (--zapisz)
//   kontrahenci     - lista firm z NIP-ami (powiazanie dostawcow RM_BAZA)
//   dostawcy        - zaklada kontrahentow z listy RM_BAZA; ZAPISUJE (--zapisz)
//   stan-pozycji    - kartoteka + ZK + ZD dla listy symboli (kolumna SUBIEKT)
//   dokumenty       - lista ZK/ZD/RW/WZ z pozycjami (okno przegladu)
//   magazyn         - stany CALEGO magazynu (bez wiazania z projektem)
var trybyMaszynowe = new[] { "stan", "katalog", "kontrahenci", "zapotrzebowanie",
                             "projekt", "zd", "zd-usun", "dostawcy", "stan-pozycji",
                             "dokumenty", "faktury", "kartoteka", "wydruk-recon", "wydruk",
                             "magazyn" };
var cicho = trybyMaszynowe.Contains(tryb);
var trybStan = tryb == "stan";
var trybProjekt = tryb == "projekt";
var trybKatalog = tryb == "katalog";
var trybZapotrzebowanie = tryb == "zapotrzebowanie";
var trybZd = tryb == "zd";
var trybZdUsun = tryb == "zd-usun";
var numeryArg = args.FirstOrDefault(a => a.StartsWith("--numery="))?["--numery=".Length..];
var planFile = args.FirstOrDefault(a => a.StartsWith("--plan="))?["--plan=".Length..];
var zapisz = args.Any(a => a.Equals("--zapisz", StringComparison.OrdinalIgnoreCase));
var symbolsFile = args.FirstOrDefault(a => a.StartsWith("--symbols-file="))?["--symbols-file=".Length..];
var outPath = args.FirstOrDefault(a => a.StartsWith("--out="))?["--out=".Length..];
if (symbolsFile != null)
{
    if (!File.Exists(symbolsFile)) { Console.WriteLine($"BRAK PLIKU Z SYMBOLAMI: {symbolsFile}"); return 1; }
    szukane.AddRange(File.ReadAllLines(symbolsFile).Select(x => x.Trim()).Where(x => x.Length > 0));
}
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

if (!cicho || outPath != null)
{
    Console.WriteLine($"Sfera {DanePolaczenia.WersjaSfery}  ->  serwer={cfg.Serwer}  baza={cfg.Baza}  auth={(cfg.SqlWindowsAuth ? "Windows" : "SQL:" + cfg.SqlUser)}");
    Console.WriteLine($"Proces 64-bit: {Environment.Is64BitProcess}   (Sfera nexo >=57 wymaga 64-bit)");
}

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
    if (!cicho || outPath != null) Console.WriteLine($"Zalogowano operatora: {cfg.NexoLogin}");

    if (trybStan)
    {
        if (szukane.Count == 0) { Console.WriteLine("Tryb stan: brak symboli (--symbol= albo --symbols-file=)."); return 1; }
        return NexoRecon.Stan.Uruchom(sfera, szukane, outPath);
    }

    if (trybKatalog)
        return NexoRecon.Katalog.Uruchom(sfera, outPath);

    if (tryb == "kontrahenci")
        return NexoRecon.Katalog.Kontrahenci(sfera, outPath);

    if (tryb == "dokumenty")
        return NexoRecon.Dokumenty.Uruchom(sfera, limit > 15 ? limit : 200, outPath);

    if (tryb == "faktury")
        return NexoRecon.Faktury.Uruchom(sfera, limit > 15 ? limit : 60, outPath);

    if (tryb == "kartoteka")
    {
        if (planFile == null) { Console.WriteLine("Tryb kartoteka: brak --plan=plik.json"); return 1; }
        return NexoRecon.Kartoteka.Uruchom(sfera, planFile, outPath, zapisz);
    }

    if (tryb == "stan-pozycji")
    {
        if (szukane.Count == 0) { Console.WriteLine("Tryb stan-pozycji: brak symboli."); return 1; }
        var projekt = args.FirstOrDefault(a => a.StartsWith("--projekt="))?["--projekt=".Length..];
        return NexoRecon.StanPozycji.Uruchom(sfera, szukane, projekt, outPath);
    }

    if (tryb == "dostawcy")
    {
        if (planFile == null) { Console.WriteLine("Tryb dostawcy: brak --plan=plik.json"); return 1; }
        return NexoRecon.Dostawcy.Uruchom(sfera, planFile, outPath, zapisz);
    }

    if (trybZapotrzebowanie)
        return NexoRecon.Zapotrzebowanie.Uruchom(sfera, outPath);

    if (trybZd)
    {
        if (planFile == null) { Console.WriteLine("Tryb zd: brak --plan=plik.json"); return 1; }
        return NexoRecon.Zd.Uruchom(sfera, planFile, outPath, zapisz);
    }

    if (tryb == "magazyn")
    {
        var tylkoNiezerowe = args.Any(a => a.Equals("--tylko-niezerowe",
                                                    StringComparison.OrdinalIgnoreCase));
        return NexoRecon.Magazyn.Uruchom(sfera, outPath, tylkoNiezerowe);
    }

    if (trybZdUsun)
    {
        if (numeryArg == null) { Console.WriteLine("Tryb zd-usun: brak --numery=\"ZD 1/09/2026;...\""); return 1; }
        return NexoRecon.ZdUsun.Uruchom(sfera, numeryArg, outPath, zapisz);
    }

    if (tryb == "wydruk-recon")
    {
        var pdfDir = args.FirstOrDefault(a => a.StartsWith("--pdf="))?["--pdf=".Length..];
        return NexoRecon.WydrukRecon.Uruchom(sfera, numeryArg, outPath, pdfDir);
    }

    if (tryb == "wydruk")
    {
        var pdfDir = args.FirstOrDefault(a => a.StartsWith("--pdf="))?["--pdf=".Length..];
        return NexoRecon.Wydruk.Uruchom(sfera, numeryArg, outPath, pdfDir);
    }

    if (trybProjekt)
    {
        if (planFile == null) { Console.WriteLine("Tryb projekt: brak --plan=plik.json"); return 1; }
        return NexoRecon.Projekt.Uruchom(sfera, planFile, outPath, zapisz);
    }

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
            Console.WriteLine($"    {a.Symbol,-25} {Skroc(a.Nazwa, 45),-45} rodzaj={Bezp(() => a.Rodzaj?.Nazwa)} jm={Bezp(() => a.JednostkaMagazynowa?.JednostkaMiary?.Symbol)}");

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

        // Pola tekstowe podmiotu — szukamy miejsca na NIP/notatkę przy
        // zakładaniu kontrahenta z RM_BAZA (dokumentacja CHM ich nie indeksuje).
        if (firmy.Count > 0)
        {
            var t = firmy[0].GetType();
            var tekstowe = t.GetProperties()
                .Where(pi => pi.PropertyType == typeof(string) && pi.CanWrite)
                .Select(pi => pi.Name)
                .OrderBy(n => n)
                .ToList();
            Console.WriteLine("  zapisywalne pola tekstowe Podmiot:");
            Console.WriteLine("     " + string.Join(", ", tekstowe));
        }
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
        Console.WriteLine($"    {Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura),-22} wyst={d.DataWydaniaWystawienia:yyyy-MM-dd} wprow={d.DataWprowadzenia:yyyy-MM-dd}  {Skroc(Bezp(() => d.Podmiot?.NazwaSkrocona), 30),-30} mag={Bezp(() => d.Magazyn?.Symbol),-6} poz={Bezp(() => d.Pozycje.Count().ToString())}  status={Bezp(() => d.StatusDokumentu?.Nazwa)}");
    // Pola „kto/gdzie" — do diagnozy widoczności dokumentu u różnych operatorów.
    // Szukamy refleksją, bo dokumentacja CHM indeksuje tylko część pól encji
    // Dokument, a nazwy (Oddzial / Stanowisko / Wystawil) różnią się między
    // typami dokumentów.
    if (ostatnie.Count > 0)
    {
        var d0 = ostatnie[0];
        var t = d0.GetType();
        var interesujace = t.GetProperties()
            .Where(pi => pi.GetIndexParameters().Length == 0)
            .Where(pi => pi.Name.Contains("Oddzial", StringComparison.OrdinalIgnoreCase)
                      || pi.Name.Contains("Stanowisko", StringComparison.OrdinalIgnoreCase)
                      || pi.Name.Contains("Wystawi", StringComparison.OrdinalIgnoreCase)
                      || pi.Name.Contains("Operator", StringComparison.OrdinalIgnoreCase)
                      || pi.Name.Contains("Uzytkownik", StringComparison.OrdinalIgnoreCase)
                      || pi.Name.Contains("Miejsce", StringComparison.OrdinalIgnoreCase)
                      || pi.Name.Contains("Wprowadz", StringComparison.OrdinalIgnoreCase)
                      || pi.Name.Contains("Flaga", StringComparison.OrdinalIgnoreCase)
                      || pi.Name.Contains("Kategoria", StringComparison.OrdinalIgnoreCase)
                      || pi.Name.Contains("Podtyp", StringComparison.OrdinalIgnoreCase)
                      || pi.Name.Contains("Rodzaj", StringComparison.OrdinalIgnoreCase))
            .Where(pi => !pi.Name.EndsWith("Id", StringComparison.Ordinal))
            .OrderBy(pi => pi.Name)
            .ToList();
        if (interesujace.Count > 0)
        {
            Console.WriteLine($"  kontekst {Bezp(() => d0.NumerWewnetrzny?.PelnaSygnatura)}:");
            foreach (var pi in interesujace)
            {
                var v = Bezp(() => pi.GetValue(d0)?.ToString());
                Console.WriteLine($"     {pi.Name,-28} = {Skroc(v, 55) ?? "(null)"}");
            }
        }
    }

    if (pokazPozycje && ostatnie.Count > 0)
    {
        var d = ostatnie[0];
        Console.WriteLine($"  pozycje najnowszego ({Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura)}):");
        foreach (var p in d.Pozycje.Take(limit))
            Console.WriteLine($"     {Bezp(() => p.AsortymentAktualny?.Symbol),-25} {Skroc(Bezp(() => p.AsortymentAktualny?.Nazwa), 40),-40} ilość={p.Ilosc,10} {Bezp(() => p.JednostkaMiaryAs?.JednostkaMiary?.Symbol)}");
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
