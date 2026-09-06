// Tryb "komplet-napraw" — usuwa ZDUBLOWANE skladniki kompletow.
//
//   NexoRecon.exe komplet-napraw [--symbol=... | --symbols-file=...] [--zapisz]
//
// Bez symboli: przeglada WSZYSTKIE komplety w bazie. Bez --zapisz: tylko
// raport, nic nie zmienia.
//
// Skad problem: Projekt.cs dopisywal skladniki przez Dodaj() bez sprawdzenia,
// czy juz sa. Drugie zalozenie kompletu (drugi projekt z tymi samymi numerami
// rysunkow albo powtorka tego samego) dawalo kazdy skladnik podwojnie,
// a Subiekt liczyl z tego podwojne zapotrzebowanie. Znalezione 06.09.2026:
// 25 kompletow, wszystkie x2. Projekt.cs jest juz odporny (czysci sklad
// przed wpisaniem), ten tryb sprzata to, co zdazylo powstac.
//
// ZASADA BEZPIECZENSTWA: naprawiamy tylko duplikaty JEDNOZNACZNE — te same
// symbole z TA SAMA iloscia. Gdy ilosci sie roznia (np. 1 i 2), nie wiemy,
// ktora jest prawdziwa: raportujemy i pomijamy, czlowiek decyduje.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class KompletNapraw
{
    public static int Uruchom(Uchwyt sfera, List<string>? symbole, string? outPath, bool zapisz)
    {
        var asort = sfera.Asortymenty();

        // Jedna projekcja po wszystkich kompletach — ten sam wzorzec co
        // Komplet.cs. Rodzaj filtrujemy po nazwie, bo "Komplet" to jedyny
        // rodzaj, ktory ma sklad.
        var komplety = asort.Dane.Wszystkie()
            .Where(a => a.Rodzaj.Nazwa == "Komplet")
            .Select(a => new
            {
                a.Symbol,
                Sklad = a.SkladnikiKompletu.Select(s => new
                {
                    Symbol = s.Skladnik.Symbol,
                    s.Ilosc,
                }),
            })
            .ToList();

        if (symbole is { Count: > 0 })
        {
            var chciane = new HashSet<string>(symbole.Select(s => s.Trim()), StringComparer.OrdinalIgnoreCase);
            komplety = komplety.Where(k => chciane.Contains((k.Symbol ?? "").Trim())).ToList();
        }

        var kroki = new List<Krok>();
        int naprawionych = 0, doNaprawy = 0, niejednoznacznych = 0;

        foreach (var k in komplety)
        {
            var symbol = (k.Symbol ?? "").Trim();
            var grupy = k.Sklad
                .GroupBy(s => (s.Symbol ?? "").Trim(), StringComparer.OrdinalIgnoreCase)
                .Where(g => g.Count() > 1)
                .ToList();
            if (grupy.Count == 0) continue;

            // Duplikat jednoznaczny = wszystkie wystapienia maja ta sama ilosc.
            var jednoznaczne = grupy.Where(g => g.Select(s => s.Ilosc).Distinct().Count() == 1).ToList();
            var sporne = grupy.Where(g => g.Select(s => s.Ilosc).Distinct().Count() > 1)
                              .Select(g => $"{g.Key} ({string.Join("/", g.Select(s => s.Ilosc))})")
                              .ToList();

            if (sporne.Count > 0)
            {
                niejednoznacznych++;
                kroki.Add(new Krok(symbol, "pominiety-rozne-ilosci",
                    "duplikaty z ROZNYMI ilosciami, nie wiadomo ktora prawdziwa: " + string.Join(", ", sporne)));
                if (jednoznaczne.Count == 0) continue;
            }

            var opis = string.Join(", ", jednoznaczne.Select(g => $"{g.Key} x{g.Count()}"));
            doNaprawy++;

            if (!zapisz)
            {
                kroki.Add(new Krok(symbol, "do-naprawy", $"{jednoznaczne.Count} skladnikow zdublowanych: {opis}"));
                continue;
            }

            try
            {
                var enc = asort.Dane.WyszukajPoSymbolu(symbol);
                if (enc == null) { kroki.Add(new Krok(symbol, "blad", "brak kartoteki")); continue; }
                using var ob = asort.Znajdz(enc);

                // Usun(symbol) w petli az zwroci false, potem JEDEN wpis
                // z oryginalna iloscia — patrz Projekt.WyczyscSklad, ten sam
                // powod: SDK nie ma "wyczysc" ani "ustaw".
                foreach (var g in jednoznaczne)
                {
                    var ilosc = g.First().Ilosc;
                    var straznik = 0;
                    while (straznik++ < 200 && ob.Skladniki.Usun(g.Key)) { }
                    ob.Skladniki.Dodaj(g.Key, ilosc);
                }

                if (!ob.Zapisz())
                {
                    kroki.Add(new Krok(symbol, "blad", Bezp(ob.PodajBledy) ?? "Zapisz() = false"));
                    continue;
                }
                naprawionych++;
                kroki.Add(new Krok(symbol, "naprawiony", opis));
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok(symbol, "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(new
        {
            zapisano = zapisz && naprawionych > 0,
            sprawdzono = komplety.Count,
            do_naprawy = doNaprawy,
            naprawionych,
            niejednoznacznych,
            kroki,
        }, new JsonSerializerOptions
        {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
        });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record Krok(string Symbol, string Status, string? Szczegoly);
}
