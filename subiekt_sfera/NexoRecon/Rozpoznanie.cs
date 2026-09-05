// Rozpoznanie — domyslny tryb NexoRecon (bez argumentu trybu): wypis
// magazynow, kartotek, stanow, kontrahentow i dokumentow na stdout.
//
// Kod przeniesiony 1:1 z Program.cs przy wydzielaniu CommandDispatcher
// (SUBIEKT_STALY_MOST_PLAN.md, Krok D). Zmieniona jest tylko obudowa:
// wczesniej byly to funkcje lokalne top-level domykajace `sfera`, `limit`
// i `szukane` — teraz sa to pola klasy, ustawiane raz w Uruchom().
//
// Tryb jest CLI-only i celowo NIE trafia do dispatchera: pisze czytelny
// raport na konsole, a nie JSON, wiec przez most server nie ma go po co
// wystawiac.

using System.Linq;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

// Encja SDK "Magazyn" koliduje z naszym handlerem trybu "magazyn"
// (Magazyn.cs) — wewnatrz namespace NexoRecon wygrywa nasza klasa statyczna.
// Wczesniej tego problemu nie bylo, bo ten kod siedzial w Program.cs poza
// namespace. Alias rozstrzyga to jawnie, bez zmiany nazwy handlera.
using MagazynSfera = InsERT.Moria.ModelDanych.Magazyn;

namespace NexoRecon;

internal sealed class Rozpoznanie
{
    readonly Uchwyt sfera;
    readonly int limit;
    readonly List<string> szukane;

    Rozpoznanie(Uchwyt sfera, int limit, List<string> szukane)
    {
        this.sfera = sfera;
        this.limit = limit;
        this.szukane = szukane;
    }

    public static int Uruchom(Uchwyt sfera, int limit, List<string> szukane)
        => new Rozpoznanie(sfera, limit, szukane).Wykonaj();

    int Wykonaj()
    {
    // ───────────────────────── MAGAZYNY ─────────────────────────
    var magazyny = new List<MagazynSfera>();
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
}
