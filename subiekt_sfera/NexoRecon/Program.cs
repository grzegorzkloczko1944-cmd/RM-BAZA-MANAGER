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

// Bez konsoli (DETACHED_PROCESS — tak RM_BAZA startuje tryb "server")
// ustawienie kodowania rzuca IOException i proces pada z 0xE0434352,
// zanim zdazy cokolwiek zalogowac. Kodowanie jest potrzebne tylko wtedy,
// gdy ktos naprawde patrzy na stdout.
try { Console.OutputEncoding = Encoding.UTF8; } catch (IOException) { }

// Konfig = argument pozycyjny konczacy sie .json. Wyklucz przelaczniki (--out=... tez konczy sie .json).
var cfgPath = args.FirstOrDefault(a => !a.StartsWith("--") && a.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
              ?? @"C:\RMPAK_CLIENT\.nexo_sfera.json";

// ⚠️ HOOK SDK PRZED CZYMKOLWIEK, CO DOTYKA InsERT.* — i zadnego typu SDK
// w tym pliku. Bez tego most wystawiony jako 5 plikow (bez bibliotek
// InsERT obok) padal na FileNotFoundException jeszcze przed pierwsza
// instrukcja Main. Dlaczego — patrz SdkLoader.cs.
SdkLoader.PodepnijZKonfigu(cfgPath);
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

// Tryb "server" — staly most. Sam zarzadza cyklem zycia sesji (loguje raz
// i utrzymuje ja miedzy komendami), wiec wchodzi przed zwyklym Wczytaj/Connect.
if (tryb == "server")
    return ServerHost.Uruchom(cfgPath, args.Any(a => a.Equals("--console", StringComparison.OrdinalIgnoreCase)));

// Reszta (sesja, handlery) siedzi w Cli.cs, bo dotyka typow SDK,
// a Main nie moze — patrz SdkLoader.cs.
return Cli.Uruchom(args, cfgPath, tryb, cicho, szukane, planFile, outPath, zapisz, limit, numeryArg);
