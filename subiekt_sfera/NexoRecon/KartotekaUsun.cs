// Tryb "kartoteka-usun" — USUWA kartoteki asortymentu z Subiekta.
//
//   NexoRecon.exe kartoteka-usun --symbole="011-100.49;015-100.13" [--out=w.json] [--zapisz]
//
// Bez --zapisz to suchy przebieg: mówi, co da się usunąć i dlaczego nie,
// a NIC nie kasuje. Tak samo jak zd-usun.
//
// Po co: magazynier zdejmuje z magazynu indeksy, których już nie używamy —
// kartoteki zakładane pod projekty, które dawno się skończyły. Zostają na
// liście w Subiekcie i zaśmiecają wyszukiwanie (3444 kartoteki, z czego stan
// ma 794).
//
// ⚠️ USUNIĘCIE JEST NIEODWRACALNE i Subiekt pozwala na nie TYLKO wtedy, gdy
// kartoteka nie ma żadnych powiązań: dokumentów, stanów, rezerwacji, pozycji
// w kompletach. Dlatego pytamy najpierw `MoznaUsunac` / `CzyMoznaUsunac()` —
// ustalone refleksją 05.09.2026 (SDK tego nie dokumentuje). Kartoteka z historią
// zostaje w bazie i to jest poprawne: skasowanie jej rozspójniłoby dokumenty,
// które ją wymieniają.
//
// Właściwość istnieje pod dwiema nazwami zależnie od wersji SDK, a przy jawnej
// implementacji interfejsu GetProperty na typie zwraca null — stąd odczyt
// przez GetInterfaces(), jak w pozostałych trybach.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class KartotekaUsun
{
    public static int Uruchom(Uchwyt sfera, string? symbole, string? outPath, bool zapisz)
    {
        if (string.IsNullOrWhiteSpace(symbole))
        {
            Console.WriteLine("Tryb kartoteka-usun: brak --symbole=\"SYM1;SYM2\"");
            return 1;
        }
        var chciane = symbole.Split(';', StringSplitOptions.RemoveEmptyEntries |
                                         StringSplitOptions.TrimEntries);
        var asort = sfera.Asortymenty();
        var wszystkie = asort.Dane.Wszystkie().ToList();
        var kroki = new List<Krok>();
        var usuniete = 0;

        foreach (var symbol in chciane)
        {
            var enc = wszystkie.FirstOrDefault(a =>
                (Bezp(() => a.Symbol) ?? "").Trim()
                    .Equals(symbol, StringComparison.OrdinalIgnoreCase));
            if (enc == null)
            {
                kroki.Add(new Krok(symbol, "blad", "nie ma takiej kartoteki"));
                continue;
            }

            try
            {
                using var ob = asort.Znajdz(enc);

                // Czy Subiekt w ogóle na to pozwala. Sprawdzamy ZAWSZE, także
                // w suchym przebiegu — po to on jest, żeby wiedzieć z góry.
                var mozna = MoznaUsunac(ob);
                if (mozna == false)
                {
                    kroki.Add(new Krok(symbol, "blad",
                        "Subiekt nie pozwala usunąć — kartoteka ma dokumenty, "
                        + "stany albo jest składnikiem kompletu"));
                    continue;
                }

                if (!zapisz)
                {
                    // MoznaUsunac zwracalo true dla kartoteki ze stanem i ZD
                    // (05.09.2026), wiec suchy przebieg NIE jest gwarancja —
                    // ostateczna odpowiedz daje dopiero Usun() z weryfikacja.
                    kroki.Add(new Krok(symbol, "do-usuniecia",
                        "wstępnie — Subiekt zdecyduje przy zapisie"));
                    continue;
                }

                // ⚠️ Usun() potrafi wrocic BEZ WYJATKU, choc Subiekt odmowil:
                // 05.09.2026 kartoteka 015-100.13 (stan 30, otwarte ZD) dostala
                // status "usunieta", a istniala dalej. Dlatego: wynik Usun()
                // (bywa bool), PodajBledy() i — decydujace — ponowne wyszukanie
                // po symbolu. "usunieta" tylko gdy kartoteki NAPRAWDE nie ma.
                object? wynikUsun = null;
                try
                {
                    var met = ob.GetType().GetMethod("Usun", Type.EmptyTypes)
                              ?? ob.GetType().GetInterfaces()
                                   .Select(i => i.GetMethod("Usun", Type.EmptyTypes))
                                   .FirstOrDefault(x => x != null);
                    wynikUsun = met != null ? met.Invoke(ob, null) : ob.Usun();
                }
                catch (System.Reflection.TargetInvocationException tie) when (tie.InnerException != null)
                {
                    throw tie.InnerException;
                }
                var bledy = Bezp(ob.PodajBledy);
                var nadalJest = false;
                try { nadalJest = asort.Dane.WyszukajPoSymbolu(symbol) != null; } catch { }

                if (nadalJest)
                {
                    kroki.Add(new Krok(symbol, "blad",
                        "Subiekt odmówił usunięcia — kartoteka ma dokumenty, stany "
                        + "albo jest składnikiem kompletu"
                        + (string.IsNullOrWhiteSpace(bledy) ? "" : $" ({bledy})")
                        + (wynikUsun is bool b && !b ? " [Usun()=false]" : "")));
                    continue;
                }
                usuniete++;
                kroki.Add(new Krok(symbol, "usunieta", null));
            }
            catch (Exception e)
            {
                // Najczęstszy powód: kartoteka jednak ma powiązania. Komunikat
                // Subiekta jest tu bardziej konkretny niż nasz, więc go oddajemy.
                kroki.Add(new Krok(symbol, "blad", $"{e.GetType().Name}: {e.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(new { zapisano = zapisz, usuniete, kroki },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    /// true / false / null gdy Subiekt nie odpowiada wprost.
    /// Dwie nazwy (właściwość i metoda) + GetInterfaces, bo przy jawnej
    /// implementacji GetProperty na typie zwraca null.
    static bool? MoznaUsunac(object ob)
    {
        var t = ob.GetType();
        try
        {
            var wl = t.GetProperty("MoznaUsunac")
                     ?? t.GetInterfaces().Select(i => i.GetProperty("MoznaUsunac"))
                          .FirstOrDefault(x => x != null);
            if (wl != null && wl.GetValue(ob) is bool b) return b;
        }
        catch { }
        try
        {
            var met = t.GetMethod("CzyMoznaUsunac", Type.EmptyTypes)
                      ?? t.GetInterfaces().Select(i => i.GetMethod("CzyMoznaUsunac", Type.EmptyTypes))
                           .FirstOrDefault(x => x != null);
            if (met != null && met.Invoke(ob, null) is bool b2) return b2;
        }
        catch { }
        return null;
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record Krok(string Symbol, string Status, string? Szczegoly);
}
