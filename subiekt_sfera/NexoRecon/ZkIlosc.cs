// Tryby "zk-ilosc" / "zk-cena" — zmieniają ILOŚĆ albo CENĘ NETTO pozycji
// na wskazanym ZK. ZAPISUJĄ.
//
//   NexoRecon.exe zk-ilosc --plan=plan.json [--out=w.json] [--zapisz]
//   plan pozycji: {"symbol": S, "ilosc": X}  albo  {"symbol": S, "cena": Y}
//   (pole decyduje, co się zmienia; obu naraz nie łączymy)
//
// CENA: `Cena.NettoPoRabacie` (+ NettoPrzedRabatem) — ten sam zapis co PW
// (Pw.UstawCenePozycji, pamiec/project_cena_na_pozycji_pw). Bez `Przelicz()`:
// mogłoby wrócić do ceny z cennika. Read-back pilnuje, czy cena weszła.
//
// Bez --zapisz to suchy przebieg: mówi, co zmieni i czego NIE ZROBI.
//
// plan.json:
//   { "zk": "ZK 6/CENTRALA/2026", "pozycje": [ {"symbol": "6004", "ilosc": 8} ] }
//
// Po co (02.10.2026): okno „Przegląd dokumentów" w RM_BAZA — dwuklik
// w ilość pozycji ZK. Po zasiewie właścicielem ilości jest Subiekt, więc
// zmiana idzie WPROST na dokument, nie do arkusza (arkusz pobierze ją
// przy następnym przejęciu locka).
//
// Czego NIE robimy (odmowa z opisem, user rozstrzyga w Subiekcie):
//   * ilość <= 0 — pozycję się USUWA, nie zeruje: zero wraca do arkusza
//     jako order_qty = 0 i pozycja wypada z BOM-u (ZkPozUsun.cs);
//   * zmniejszenie pozycji, która poszła dalej na ZD — zamówienie
//     u dostawcy jest zobowiązaniem, ZD zostałoby bez podstawy;
//   * symbol w KILKU wierszach dokumentu — nie zgadujemy, który zmienić.
// Zwiększenie pozycji z ZD wolno: nadwyżka trafi do zapotrzebowania.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class ZkIlosc
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }
        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
        var kroki = new List<Krok>();
        var numer = (plan.Zk ?? "").Trim();
        var zmiany = (plan.Pozycje ?? new List<PozPlan>())
            .Where(p => !string.IsNullOrWhiteSpace(p.Symbol) && (p.Ilosc.HasValue || p.Cena.HasValue))
            .ToList();
        if (numer.Length == 0 || zmiany.Count == 0)
        {
            kroki.Add(new Krok("zk", numer, "blad", "plan bez numeru ZK albo bez pozycji", null, null));
            return Wypisz(kroki, numer, false, outPath);
        }

        var zapisano = false;
        try
        {
            var zamowienia = sfera.ZamowieniaOdKlientow();
            // Jedno zapytanie po numerze — nie przegląd wszystkich ZK.
            var dok = zamowienia.Dane.Wszystkie()
                .Where(d => d.NumerWewnetrzny.PelnaSygnatura == numer)
                .ToList();
            if (dok.Count != 1)
            {
                kroki.Add(new Krok("zk", numer, "blad",
                    dok.Count == 0 ? "nie ma takiego ZK" : $"{dok.Count} dokumenty o tym numerze", null, null));
                return Wypisz(kroki, numer, false, outPath);
            }

            using var ob = zamowienia.Znajdz(dok[0]);
            var doZapisu = new List<(object poz, string sym, decimal nowa)>();
            var doCeny = new List<(object poz, string sym, decimal cena)>();
            foreach (var z in zmiany)
            {
                var sym = z.Symbol!.Trim();
                if (z.Cena.HasValue)
                {
                    var w = Projekt.ZnajdzWszystkiePozycjePubl(ob.Dane.Pozycje, sym);
                    if (w.Count != 1)
                    {
                        kroki.Add(new Krok("zk-poz", sym, w.Count == 0 ? "brak-na-zk" : "odmowa",
                            w.Count == 0 ? "nie ma jej na dokumencie"
                                         : $"jest w {w.Count} wierszach dokumentu — popraw w Subiekcie",
                            null, z.Cena));
                        continue;
                    }
                    var cenaTeraz = Bezp2(() => (decimal)((dynamic)w[0]).Cena.NettoPoRabacie);
                    if (z.Cena < 0)
                    {
                        kroki.Add(new Krok("zk-poz", sym, "odmowa", "cena nie może być ujemna", cenaTeraz, z.Cena));
                        continue;
                    }
                    if (z.Cena == cenaTeraz)
                    {
                        kroki.Add(new Krok("zk-poz", sym, "bez-zmian", $"cena już {Ilo2(cenaTeraz)} zł", cenaTeraz, z.Cena));
                        continue;
                    }
                    kroki.Add(new Krok("zk-poz", sym, zapisz ? "do-zmiany" : "do-zmiany (suchy)",
                        $"cena netto {Ilo2(cenaTeraz)} zł → ustawi {Ilo2(z.Cena.Value)} zł", cenaTeraz, z.Cena));
                    doCeny.Add((w[0], sym, z.Cena.Value));
                    continue;
                }
                var ilosc = z.Ilosc!.Value;
                var wiersze = Projekt.ZnajdzWszystkiePozycjePubl(ob.Dane.Pozycje, sym);
                if (wiersze.Count == 0)
                {
                    kroki.Add(new Krok("zk-poz", sym, "brak-na-zk", "nie ma jej na dokumencie", null, ilosc));
                    continue;
                }
                if (wiersze.Count > 1)
                {
                    kroki.Add(new Krok("zk-poz", sym, "odmowa",
                        $"jest w {wiersze.Count} wierszach dokumentu — nie zgaduję, który zmienić; popraw w Subiekcie",
                        null, ilosc));
                    continue;
                }
                var poz = wiersze[0];
                var naZk = Bezp2(() => (decimal)((dynamic)poz).Ilosc);
                if (ilosc <= 0)
                {
                    kroki.Add(new Krok("zk-poz", sym, "odmowa",
                        "ilości 0 nie ustawiam — pozycję się USUWA (zero wróciłoby do arkusza i pozycja wypadłaby z BOM-u)",
                        naZk, ilosc));
                    continue;
                }
                if (ilosc == naZk)
                {
                    kroki.Add(new Krok("zk-poz", sym, "bez-zmian", $"na ZK już {Ilo(naZk)}", naZk, ilosc));
                    continue;
                }
                var zd = ZkPozUsun.NumeryZdPubl(poz);
                if (zd.Count > 0 && ilosc < naZk)
                {
                    kroki.Add(new Krok("zk-poz", sym, "odmowa",
                        $"poszła dalej na {string.Join(", ", zd)} — zmniejszenia NIE robię, rozstrzygnij w Subiekcie",
                        naZk, ilosc));
                    continue;
                }
                var uwaga = zd.Count > 0
                    ? $"; uwaga: jest już na {string.Join(", ", zd)} — nadwyżka trafi do zapotrzebowania"
                    : "";
                kroki.Add(new Krok("zk-poz", sym, zapisz ? "do-zmiany" : "do-zmiany (suchy)",
                    $"na ZK {Ilo(naZk)} → ustawi {Ilo(ilosc)}{uwaga}", naZk, ilosc));
                doZapisu.Add((poz, sym, ilosc));
            }

            if (!zapisz || (doZapisu.Count == 0 && doCeny.Count == 0))
                return Wypisz(kroki, numer, false, outPath);

            foreach (var (poz, _, nowa) in doZapisu)
                Projekt.UstawIloscPozycjiPubl(poz, nowa);
            foreach (var (poz, sym, cena) in doCeny)
                if (Pw.UstawCenePozycjiPubl(poz, cena) is null)
                {
                    kroki.Add(new Krok("zk-poz", sym, "blad",
                        "Sfera nie przyjęła ceny (Cena.NettoPoRabacie) — NIE zapisuję dokumentu", null, cena));
                    return Wypisz(kroki, numer, false, outPath);
                }
            // Przeliczenie tylko przy zmianie ilości — przy cenie mogłoby
            // podstawić cenę z cennika w miejsce wpisanej.
            if (doZapisu.Count > 0) { try { ob.Przelicz(); } catch { } }
            if (!ob.Zapisz())
            {
                kroki.Add(new Krok("zk", numer, "blad",
                    Bezp(ob.PodajBledy) ?? "Subiekt odrzucił zapis ZK", null, null));
                return Wypisz(kroki, numer, false, outPath);
            }

            // READ-BACK: Zapisz()==true nie znaczy, że ilości weszły.
            // Jedno zapytanie: pozycje tego ZK, symbol + ilość.
            var poZapisie = zamowienia.Dane.Wszystkie()
                .Where(d => d.NumerWewnetrzny.PelnaSygnatura == numer)
                .SelectMany(d => d.Pozycje.Select(p => new { p.AsortymentAktualny.Symbol, p.Ilosc,
                                                             Cena = p.Cena.NettoPoRabacie }))
                .ToList();
            var cenyPo = poZapisie
                .GroupBy(p => (p.Symbol ?? "").Trim().ToUpperInvariant())
                .ToDictionary(g => g.Key, g => g.First().Cena);
            var iloscPo = poZapisie
                .GroupBy(p => (p.Symbol ?? "").Trim().ToUpperInvariant())
                .ToDictionary(g => g.Key, g => g.Sum(p => p.Ilosc));
            foreach (var (_, sym, cena) in doCeny)
            {
                var jest = cenyPo.TryGetValue(sym.ToUpperInvariant(), out var c) ? c : (decimal?)null;
                if (jest == cena)
                {
                    zapisano = true;
                    kroki.Add(new Krok("zk-poz", sym, "zmieniona",
                        $"cena netto jest teraz {Ilo2(cena)} zł (potwierdzone odczytem)", null, cena));
                }
                else
                    kroki.Add(new Krok("zk-poz", sym, "blad",
                        $"po zapisie cena {(jest is null ? "—" : Ilo2(jest.Value))} zł, a miała być {Ilo2(cena)} zł — sprawdź w Subiekcie",
                        jest, cena));
            }
            foreach (var (_, sym, nowa) in doZapisu)
            {
                var jest = iloscPo.TryGetValue(sym.ToUpperInvariant(), out var v) ? v : (decimal?)null;
                if (jest == nowa)
                {
                    zapisano = true;
                    kroki.Add(new Krok("zk-poz", sym, "zmieniona",
                        $"na ZK jest teraz {Ilo(nowa)} (potwierdzone odczytem)", null, nowa));
                }
                else
                    kroki.Add(new Krok("zk-poz", sym, "blad",
                        $"po zapisie na ZK jest {(jest is null ? "—" : Ilo(jest.Value))}, a miało być {Ilo(nowa)} — sprawdź w Subiekcie",
                        jest, nowa));
            }
        }
        catch (Exception ex)
        {
            kroki.Add(new Krok("zk", numer, "blad", $"{ex.GetType().Name}: {ex.Message}", null, null));
        }
        return Wypisz(kroki, numer, zapisano, outPath);
    }

    static int Wypisz(List<Krok> kroki, string? zk, bool zapisano, string? outPath)
    {
        var json = JsonSerializer.Serialize(new { zapisano, zk, kroki },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    static string Ilo(decimal d) => d.ToString("0.##");
    static string Ilo2(decimal d) => d.ToString("0.00");
    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }
    static decimal Bezp2(Func<decimal> f) { try { return f(); } catch { return 0m; } }

    internal record PozPlan(string? Symbol, decimal? Ilosc, decimal? Cena = null);
    internal record Plan(string? Zk, List<PozPlan>? Pozycje);
    internal record Krok(string Rodzaj, string Symbol, string Status, string? Szczegoly,
                         decimal? NaZk, decimal? Nowa);
}
