// NexoRecon — most RM_BAZA <-> Subiekt nexo PRO przez Sfere.
//
// Uzycie:  NexoRecon.exe [tryb] [sciezka\do\konfig.json] [--symbol=ABC-123 ...] [--limit=20]
// Konfig domyslnie: C:\RMPAK_CLIENT\.nexo_sfera.json  (poza repo! wzor: ..\nexo_sfera.example.json)
//
// Ten plik odpowiada TYLKO za: parsowanie argumentow CLI, zestawienie sesji
// i oddanie roboty dispatcherowi. Logika trybow siedzi w handlerach
// (Stan.cs, Katalog.cs, ...), mapa trybow w CommandDispatcher.cs, a cykl
// zycia polaczenia w NexoSession.cs.
//
// Podzial jest po to, zeby tryb "server" (staly most — SUBIEKT_STALY_MOST_PLAN.md)
// mogl uzyc tych samych handlerow bez restartowania procesu i logowania sie
// do Sfery przy kazdej komendzie. Wczesniej wszystko bylo w tym pliku
// i sesja zyla dokladnie tyle, co jedna komenda — stad ~9-10 s narzutu.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using NexoRecon;

Console.OutputEncoding = Encoding.UTF8;

// Konfig = argument pozycyjny konczacy sie .json. Wyklucz przelaczniki (--out=... tez konczy sie .json).
var cfgPath = args.FirstOrDefault(a => !a.StartsWith("--") && a.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
              ?? @"C:\RMPAK_CLIENT\.nexo_sfera.json";
var szukane = args.Where(a => a.StartsWith("--symbol=")).Select(a => a["--symbol=".Length..]).ToList();

// Nazwa trybu = pierwszy argument. Jeden string zamiast N zmiennych bool,
// bo przy kazdym nowym trybie trzeba bylo dopisywac sie w trzech miejscach
// (deklaracja + dwa warunki "czy wypisywac naglowek") i latwo bylo o tym
// zapomniec - wtedy tryb maszynowy zasmiecal JSON tekstem powitalnym.
var tryb = args.Length > 0 && !args[0].StartsWith("--") ? args[0].ToLowerInvariant() : "";

// Tryby maszynowe: wyjscie czyta Python, wiec zadnych naglowkow na stdout
// (chyba ze jest --out=, wtedy JSON idzie do pliku i stdout jest wolny).
// Lista trybow zyje w CommandDispatcher — tu tylko pytamy, czy tryb jest znany.
var cicho = CommandDispatcher.Zna(tryb);

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
