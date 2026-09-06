// Tryb jednorazowy (CLI): zestaw sesje, wykonaj jedna komende, wyjdz.
//
// Wydzielone z Program.cs, bo to cialo dotyka typow SDK (sesja.Sfera to
// Uchwyt z InsERT.Moria.Sfera) i NIE MOZE lezec w Main — patrz SdkLoader.cs.
// Ta metoda jest kompilowana dopiero przy wywolaniu, czyli po podpieciu hooka.

using System;
using System.Collections.Generic;
using System.Linq;

namespace NexoRecon;

internal static class Cli
{
    public static int Uruchom(string[] args, string cfgPath, string tryb, bool cicho,
                              List<string> szukane, string? planFile, string? outPath,
                              bool zapisz, int limit, string? numeryArg)
    {
        NexoSession sesja;
        try
        {
            sesja = NexoSession.Wczytaj(cfgPath);
        }
        catch (SesjaException ex)
        {
            Console.WriteLine(ex.Message);
            return ex.KodWyjscia;
        }

        if (!cicho || outPath != null)
        {
            Console.WriteLine(sesja.OpisPolaczenia);
            Console.WriteLine($"Proces 64-bit: {Environment.Is64BitProcess}   (Sfera nexo >=57 wymaga 64-bit)");
        }

        using (sesja)
        {
            try
            {
                sesja.Connect();
            }
            catch (SesjaException ex)
            {
                Console.WriteLine(ex.Message);
                return ex.KodWyjscia;
            }

            if (!cicho || outPath != null) Console.WriteLine($"Zalogowano operatora: {sesja.Operator}");

            // Tryb domyslny (bez nazwy trybu) — raport rozpoznawczy na stdout.
            // Nie idzie przez dispatcher: pisze tekst dla czlowieka, nie JSON.
            if (!cicho)
                return Rozpoznanie.Uruchom(sesja.Sfera, limit, szukane);

            var komenda = new Komenda(
                Tryb: tryb,
                Symbole: szukane,
                PlanPath: planFile,
                OutPath: outPath,
                Zapisz: zapisz,
                Limit: limit,
                Numery: numeryArg,
                Magazyn: args.FirstOrDefault(a => a.StartsWith("--magazyn="))?["--magazyn=".Length..],
                Data: args.FirstOrDefault(a => a.StartsWith("--data="))?["--data=".Length..],
                SymboleCsv: args.FirstOrDefault(a => a.StartsWith("--symbole="))?["--symbole=".Length..],
                Projekt: args.FirstOrDefault(a => a.StartsWith("--projekt="))?["--projekt=".Length..],
                PdfDir: args.FirstOrDefault(a => a.StartsWith("--pdf="))?["--pdf=".Length..],
                TylkoNiezerowe: args.Any(a => a.Equals("--tylko-niezerowe", StringComparison.OrdinalIgnoreCase)));

            return CommandDispatcher.Wykonaj(sesja.Sfera, komenda);
        }
    }
}
