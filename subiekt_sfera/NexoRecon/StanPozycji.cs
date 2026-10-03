// Tryb "stan-pozycji" — dla listy symboli: kartoteka + ZK + ZD. Tylko odczyt.
//
//   NexoRecon.exe stan-pozycji --symbols-file=lista.txt [--out=w.json] [--projekt=2621]
//
// Zasila kolumnę SUBIEKT w arkuszu głównym RM_BAZA (plan integracji, sekcja
// „Wizualny wskaźnik" — wzorzec kolumny WYCENA z RFQ: prefiks, kolor, klik).
//
// Trzy stany na pozycję, bo to trzy różne informacje dla planującego produkcję:
//   kartoteka — czy asortyment w ogóle istnieje w Subiekcie
//   ZK        — czy jest na liście projektu (dokument z numerem projektu w Uwagach)
//   ZD        — czy zamówiony u dostawcy i u kogo
//
// FZ (przyjęcia) świadomie POMINIĘTE — krok 13 przepływu nie jest zrobiony,
// a zgadywanie „przyszło" z niepełnych danych byłoby gorsze niż brak kolumny.
//
// ⚠️ TRZY PROJEKCJE, ZERO NAWIGACJI W PĘTLI (03.10.2026). Do tej pory dla
// KAŻDEGO symbolu z arkusza szło `WyszukajPoSymbolu` + `StanyMagazynowe`
// (dwa zapytania SQL na wiersz), a dla każdego ZK/ZD osobne `d.Pozycje` —
// przy 222 pozycjach i kilkunastu dokumentach ~500 zapytań zamiast 3.
// Na demo (lokalny SQL, mała baza) kosztowało to 0,4 s, w firmie przez
// sieć byłoby kilka sekund. Ten sam wzorzec co Magazyn.cs (7 s → 0,3 s,
// 06.09.2026) i Dokumenty.cs: wszystko, czego potrzeba, w jednym `Select`
// z zagnieżdżoną kolekcją, materializacja raz, dopasowanie w pamięci.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class StanPozycji
{
    public static int Uruchom(Uchwyt sfera, List<string> symbole, string? projekt, string? outPath)
    {
        // ── 1. Kartoteki: symbol, nazwa, suma dostępnego — JEDNO zapytanie.
        // Klucz po TRIM i bez wielkości liter: w bazie są symbole ze spacją
        // na końcu i różnicą a/A, a arkusz pyta „czystym" symbolem. Jeden
        // słownik zastępuje dawne WyszukajPoSymbolu + mapę „luźną".
        var kartoteki = new Dictionary<string, (string Symbol, string? Nazwa, decimal Stan)>(
            StringComparer.OrdinalIgnoreCase);
        try
        {
            var dane = sfera.Asortymenty().Dane.Wszystkie()
                .Select(a => new
                {
                    a.Symbol,
                    a.Nazwa,
                    Stany = a.StanyMagazynowe.Select(s => new { s.IloscDostepna }),
                })
                .ToList();
            foreach (var a in dane)
            {
                var k = (a.Symbol ?? "").Trim();
                if (k.Length == 0 || kartoteki.ContainsKey(k)) continue;
                decimal stan = 0;
                try { foreach (var s in a.Stany) stan += s.IloscDostepna; } catch { }
                kartoteki[k] = (a.Symbol!, a.Nazwa, stan);
            }
        }
        catch { /* brak dostępu do asortymentu — kolumna pokaże „brak" */ }

        // ── 2. Pozycje ZK — tylko dokumenty tego projektu, gdy podano --projekt.
        // Numer projektu siedzi w Uwagach ZK (SUBIEKT_PROJEKTY_WYDANIA.md).
        // Pozycje w TEJ SAMEJ projekcji co nagłówek — nie `d.Pozycje` po fakcie.
        var wZk = new Dictionary<string, (string Numer, decimal Ilosc)>(StringComparer.OrdinalIgnoreCase);
        try
        {
            var zk = sfera.ZamowieniaOdKlientow().Dane.Wszystkie()
                .OrderByDescending(d => d.DataWprowadzenia)
                .Take(200)
                .Select(d => new
                {
                    Numer = d.NumerWewnetrzny.PelnaSygnatura,
                    d.Uwagi,
                    Pozycje = d.Pozycje.Select(p => new
                    {
                        Symbol = p.AsortymentAktualny.Symbol,
                        p.Ilosc,
                    }),
                })
                .ToList();
            foreach (var d in zk)
            {
                var uwagi = (d.Uwagi ?? "").Trim();
                if (!string.IsNullOrEmpty(projekt) &&
                    !uwagi.Contains(projekt, StringComparison.OrdinalIgnoreCase)) continue;
                var numer = d.Numer ?? "";
                foreach (var p in d.Pozycje)
                {
                    var s = (p.Symbol ?? "").Trim();
                    if (s.Length > 0 && !wZk.ContainsKey(s))
                        wZk[s] = (numer, p.Ilosc);
                }
            }
        }
        catch { }

        // ── 3. Pozycje ZD — zamówione u dostawców (niezależnie od projektu, bo ZD
        // grupuje po dostawcy i może obejmować kilka projektów naraz; projekt
        // rozstrzyga RM_BAZA z trybu `dokumenty` — dopasuj_zd_do_projektu).
        var wZd = new Dictionary<string, (string Numer, string Dostawca, decimal Ilosc, string Status)>(
            StringComparer.OrdinalIgnoreCase);
        try
        {
            var zd = sfera.ZamowieniaDoDostawcow().Dane.Wszystkie()
                .OrderByDescending(d => d.DataWprowadzenia)
                .Take(200)
                .Select(d => new
                {
                    Numer = d.NumerWewnetrzny.PelnaSygnatura,
                    Dostawca = d.Podmiot.NazwaSkrocona,
                    Status = d.StatusDokumentu.Nazwa,
                    Pozycje = d.Pozycje.Select(p => new
                    {
                        Symbol = p.AsortymentAktualny.Symbol,
                        p.Ilosc,
                    }),
                })
                .ToList();
            foreach (var d in zd)
            {
                var numer = d.Numer ?? "";
                var dostawca = d.Dostawca ?? "";
                var status = d.Status ?? "";
                foreach (var p in d.Pozycje)
                {
                    var s = (p.Symbol ?? "").Trim();
                    if (s.Length > 0 && !wZd.ContainsKey(s))
                        wZd[s] = (numer, dostawca, p.Ilosc, status);
                }
            }
        }
        catch { }

        // ── 4. Dopasowanie w pamięci — bez pytania Sfery.
        var wynik = new List<Poz>();
        foreach (var pytany in symbole)
        {
            var s = (pytany ?? "").Trim();
            if (s.Length == 0) continue;

            var jest = kartoteki.TryGetValue(s, out var k);
            var symbolReal = jest ? k.Symbol.Trim() : s;
            wZk.TryGetValue(symbolReal, out var zk);
            wZd.TryGetValue(symbolReal, out var zd);

            wynik.Add(new Poz(
                pytany!, jest, jest ? k.Nazwa : null, jest ? k.Stan : 0,
                zk.Numer ?? "", zk.Ilosc,
                zd.Numer ?? "", zd.Dostawca ?? "", zd.Ilosc, zd.Status ?? ""));
        }

        var json = JsonSerializer.Serialize(new { pozycje = wynik },
            new JsonSerializerOptions
            {
                WriteIndented = false,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    internal record Poz(string Pytany, bool MaKartoteke, string? Nazwa, decimal Stan,
                        string Zk, decimal IloscZk,
                        string Zd, string Dostawca, decimal IloscZd, string StatusZd);
}
