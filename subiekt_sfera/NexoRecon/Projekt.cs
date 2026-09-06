// Tryb "projekt" — ZAPIS do Subiekta: kartoteki, komplety (Z/ZZ) i ZK projektu.
//
//   NexoRecon.exe projekt --plan=plan.json [--out=wynik.json] [--zapisz] [konfig.json]
//
// BEZ --zapisz to SUCHY PRZEBIEG: czyta Subiekta, mówi co by zrobił, nic nie zapisuje.
// Z --zapisz wykonuje operacje w kolejności: kartoteki → komplety Z → komplety ZZ → ZK.
//
// Kolejność nie jest przypadkowa (SUBIEKT_PROJEKTY_WYDANIA.md, sekcja 5):
// składnik musi istnieć w Subiekcie, zanim dodamy go do kompletu, a komplety Z
// muszą istnieć, zanim wejdą jako składniki do ZZ.
//
// Wejściowy plan.json (buduje go subiekt_projekt.py):
// {
//   "projekt": "2222", "tytul": "Projekt 2222 - Ceramizator",
//   "podmiot": "RMPAK",                       // NazwaSkrocona albo NIP
//   "pozycje": [ {"symbol":"013-100.220","nazwa":"Kątownik","typ":"Z","ilosc":2,
//                 "skladniki":[{"symbol":"013-100.221","ilosc":4}]} ]
// }
// typ: X|XX|Z|ZZ|STANDARD|ZNORMALIZOWANE — komplet powstaje TYLKO dla Z i ZZ.

using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Projekt
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }

        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;

        var asort = sfera.Asortymenty();
        var szablony = sfera.PodajObiektTypu<InsERT.Moria.Asortymenty.ISzablonyAsortymentu>();
        var kroki = new List<Krok>();

        // Mapa symboli już istniejących — jeden przelot, jak w Stan.cs.
        // Dopasowanie luźne (TRIM + ignorowanie wielkości liter), bo w bazie
        // są symbole ze spacją na końcu i różnicą a/A (plan, sekcja 12.2).
        var luzne = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var a in asort.Dane.Wszystkie().Select(a => new { a.Symbol }).ToList())
        {
            var k = (a.Symbol ?? "").Trim();
            if (k.Length > 0) luzne[k] = a.Symbol!;
        }

        Asortyment? Znajdz(string symbol)
        {
            var s = (symbol ?? "").Trim();
            if (s.Length == 0) return null;
            var enc = asort.Dane.WyszukajPoSymbolu(s);
            if (enc == null && luzne.TryGetValue(s, out var realny))
                enc = asort.Dane.WyszukajPoSymbolu(realny);
            return enc;
        }

        var pozycje = plan.Pozycje ?? new List<PozPlan>();

        // ── 1. KARTOTEKI ──────────────────────────────────────────────────
        // Zakładane pojedynczo, symbol po symbolu (plan, krok 12) — nigdy
        // masową pętlą bez kontroli, bo to jedyne miejsce gdzie koszt zależy
        // od tego CO piszemy.
        foreach (var p in pozycje)
        {
            var istnieje = Znajdz(p.Symbol) != null;
            if (istnieje) { kroki.Add(new Krok("kartoteka", p.Symbol, "istnieje", null)); continue; }

            if (!zapisz) { kroki.Add(new Krok("kartoteka", p.Symbol, "do-zalozenia", null)); continue; }

            try
            {
                using var ob = asort.Utworz();
                // Bez szablonu brakuje domyślnej jednostki miary (plan, krok 12).
                // Wzorzec z SDK\Przyklady\PrzykladyKartoteki\ObslugaKartotek.cs.
                // Pozycje typu Z/ZZ muszą dostać szablon Komplet — inaczej Sfera
                // odmawia później dodania składników (InvalidOperationException:
                // "Asortyment, do którego dodawane są składniki musi być kompletem",
                // znalezione na żywej Sferze 61.1.0.9431, M-OLD 2026-09-03).
                var jestKompletem = Rowne(p.Typ, "Z") || Rowne(p.Typ, "ZZ");
                ob.WypelnijNaPodstawieSzablonu(jestKompletem ? szablony.DaneDomyslne.Komplet : szablony.DaneDomyslne.Towar);
                ob.Dane.Symbol = p.Symbol.Trim();
                ob.Dane.Nazwa = string.IsNullOrWhiteSpace(p.Nazwa) ? p.Symbol.Trim() : p.Nazwa!.Trim();
                if (!ob.Zapisz())
                {
                    kroki.Add(new Krok("kartoteka", p.Symbol, "blad", Bezp(ob.PodajBledy)));
                    continue;
                }
                luzne[p.Symbol.Trim()] = p.Symbol.Trim();
                kroki.Add(new Krok("kartoteka", p.Symbol, "zalozona", null));
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok("kartoteka", p.Symbol, "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        // ── 2. KOMPLETY ───────────────────────────────────────────────────
        // Kolejność OD DOŁU DRZEWA: komplet musi istnieć, zanim wejdzie jako
        // składnik do nadrzędnego. Sortowanie po samym typie (Z przed ZZ) NIE
        // wystarcza — w realnych projektach ZZ zawiera ZZ (widziane w
        // "2607 Platyn": ZZ→ZZ 23 razy, drzewo na 4 poziomy, firma mówi o 6).
        // Stąd sortowanie topologiczne po faktycznym zagnieżdżeniu.
        foreach (var p in PosortujOdDolu(pozycje))
        {
                var skl = p.Skladniki ?? new List<SkladnikPlan>();
                if (skl.Count == 0)
                {
                    // Subiekt odrzuci komplet bez składników (NieZdefiniowanoSkladnikowKompletuBlad),
                    // więc nie próbujemy — zgłaszamy to jako pominięcie, nie błąd.
                    kroki.Add(new Krok("komplet", p.Symbol, "pominiety-brak-skladnikow", null));
                    continue;
                }

                if (!zapisz)
                {
                    var brakujace = skl.Where(s => Znajdz(s.Symbol) == null).Select(s => s.Symbol).ToList();
                    kroki.Add(new Krok("komplet", p.Symbol,
                        brakujace.Count == 0 ? "do-utworzenia" : "do-utworzenia-po-zalozeniu-skladnikow",
                        brakujace.Count == 0 ? $"{skl.Count} składników"
                                             : $"brak kartotek składników: {string.Join(", ", brakujace)}"));
                    continue;
                }

                try
                {
                    var enc = Znajdz(p.Symbol);
                    if (enc == null) { kroki.Add(new Krok("komplet", p.Symbol, "blad", "brak kartoteki")); continue; }

                    using var ob = asort.Znajdz(enc);

                    // SKLAD = PLAN, nie "plan dopisany do tego, co juz bylo".
                    //
                    // Dodaj() nie sprawdza, czy skladnik juz jest — dopisuje
                    // kolejny wiersz. Drugie zalozenie tego samego kompletu
                    // (poprawka projektu albo drugi projekt z tymi samymi
                    // numerami rysunkow — u nas normalne, zespoly sie
                    // powtarzaja) dawalo wiec kazdy skladnik PODWOJNIE, a
                    // Subiekt liczyl z tego podwojne zapotrzebowanie. Znalezione
                    // 06.09.2026: 25 kompletow, wszystkie x2, zero czystych.
                    //
                    // Kartoteka opisuje, z czego sklada sie CZESC — to fakt
                    // konstrukcyjny z drzewka Inventora, nie projektowy. Wiec
                    // zrodlem prawdy jest plan: czyscimy i wpisujemy od nowa.
                    // Operacja jest przez to powtarzalna: drugi raz da ten sam
                    // wynik, a nie podwojony.
                    var wyczyszczono = WyczyscSklad(ob);

                    var dodane = 0;
                    var pominiete = new List<string>();
                    foreach (var s in skl)
                    {
                        var sEnc = Znajdz(s.Symbol);
                        if (sEnc == null) { pominiete.Add(s.Symbol); continue; }
                        // Dodaj(Asortyment, Decimal) — ilość w podstawowej jednostce miary.
                        ob.Skladniki.Dodaj(sEnc, s.Ilosc <= 0 ? 1m : s.Ilosc);
                        dodane++;
                    }
                    if (dodane == 0)
                    {
                        kroki.Add(new Krok("komplet", p.Symbol, "blad",
                            "żaden składnik nie ma kartoteki: " + string.Join(", ", pominiete)));
                        continue;
                    }
                    if (!ob.Zapisz())
                    {
                        kroki.Add(new Krok("komplet", p.Symbol, "blad", Bezp(ob.PodajBledy)));
                        continue;
                    }
                    var uwaga = pominiete.Count > 0 ? $"pominięto bez kartoteki: {string.Join(", ", pominiete)}" : null;
                    // "zaktualizowany" mowi, ze komplet JUZ mial sklad i zostal
                    // nadpisany — user widzi, ze to nie pierwsze zalozenie.
                    kroki.Add(new Krok("komplet", p.Symbol,
                        wyczyszczono > 0 ? $"zaktualizowany ({dodane} skl., zastąpiono {wyczyszczono})"
                                         : $"utworzony ({dodane} skl.)", uwaga));
                }
                catch (Exception ex)
                {
                    kroki.Add(new Krok("komplet", p.Symbol, "blad", $"{ex.GetType().Name}: {ex.Message}"));
                }
        }

        // ── 3. ZK ─────────────────────────────────────────────────────────
        string? zkNumer = null;
        if (!zapisz)
        {
            // Podgląd musi powiedzieć, czy powstanie NOWE ZK, czy dopiszemy do
            // istniejącego — to zupełnie inny skutek dla użytkownika.
            DokumentZK? juzJest = null;
            if (!string.IsNullOrWhiteSpace(plan.Projekt))
            {
                try
                {
                    juzJest = sfera.ZamowieniaOdKlientow().Dane.Wszystkie()
                        .OrderByDescending(d => d.DataWprowadzenia).Take(100).ToList()
                        .FirstOrDefault(d => (Bezp(() => d.Uwagi) ?? "").Trim()
                                             .Equals(plan.Projekt!.Trim(),
                                                     StringComparison.OrdinalIgnoreCase));
                }
                catch { }
            }

            if (juzJest != null)
            {
                var naZk = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                try
                {
                    foreach (var poz in juzJest.Pozycje)
                    {
                        var s = Bezp(() => poz.AsortymentAktualny?.Symbol)?.Trim();
                        if (!string.IsNullOrEmpty(s)) naZk.Add(s!);
                    }
                }
                catch { }
                var nowe = pozycje.Count(p =>
                {
                    var e = Znajdz(p.Symbol);
                    return e != null && !naZk.Contains((e.Symbol ?? "").Trim());
                });
                var numer = Bezp(() => juzJest.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                kroki.Add(new Krok("zk", numer, "do-dopisania",
                    $"dopisze {nowe} poz. ({naZk.Count} już na dokumencie)"));
            }
            else
            {
                var doZk = pozycje.Count;
                kroki.Add(new Krok("zk", plan.Projekt ?? "", "do-utworzenia",
                    $"{doZk} pozycji, podmiot: {plan.Podmiot}"));
            }
        }
        else
        {
            try
            {
                var zam = sfera.ZamowieniaOdKlientow();

                // Czy ten projekt ma już ZK? Szukamy po Uwagach — tam wpisujemy
                // numer projektu. Bez tego ponowne uruchomienie robiło DRUGI
                // dokument dla tego samego projektu i rozbijało zapotrzebowanie
                // na dwa (zgłoszone 04.09.2026: „chcę dorzucić resztę").
                DokumentZK? istniejace = null;
                if (!string.IsNullOrWhiteSpace(plan.Projekt))
                {
                    try
                    {
                        istniejace = zam.Dane.Wszystkie()
                            .OrderByDescending(d => d.DataWprowadzenia)
                            .Take(100).ToList()
                            .FirstOrDefault(d => (Bezp(() => d.Uwagi) ?? "").Trim()
                                                 .Equals(plan.Projekt!.Trim(),
                                                         StringComparison.OrdinalIgnoreCase));
                    }
                    catch { }
                }

                var podm = ZnajdzPodmiot(sfera, plan.Podmiot);
                if (podm == null && istniejace == null)
                {
                    kroki.Add(new Krok("zk", plan.Projekt ?? "", "blad", $"nie znaleziono podmiotu: {plan.Podmiot}"));
                }
                else
                {
                    // Dopisujemy do istniejącego ZK albo tworzymy nowe.
                    using var ob = istniejace != null
                        ? zam.Znajdz(istniejace)
                        : zam.UtworzZamowienieOdKlienta();

                    if (istniejace == null)
                    {
                        ob.Dane.Podmiot = podm;
                        if (!string.IsNullOrWhiteSpace(plan.Tytul)) ob.Dane.Tytul = plan.Tytul;
                        // Numer projektu też w Uwagach — tak firma już oznacza dokumenty
                        // (628 dokumentów z wypełnionym polem Uwagi, sekcja 2.1).
                        ob.Dane.Uwagi = string.IsNullOrWhiteSpace(plan.Uwagi) ? $"Projekt {plan.Projekt}" : plan.Uwagi;
                    }

                    // Co już jest na dokumencie — nie dublujemy pozycji.
                    var juzNaZk = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    try
                    {
                        foreach (var poz in ob.Dane.Pozycje)
                        {
                            var s = Bezp(() => poz.AsortymentAktualny?.Symbol)?.Trim();
                            if (!string.IsNullOrEmpty(s)) juzNaZk.Add(s!);
                        }
                    }
                    catch { }

                    var dodane = 0;
                    var pominietoJest = 0;
                    foreach (var p in pozycje)
                    {
                        var enc = Znajdz(p.Symbol);
                        if (enc == null) continue;
                        if (juzNaZk.Contains((enc.Symbol ?? "").Trim())) { pominietoJest++; continue; }
                        // Dodaj(String symbol, Decimal ilosc) — symbol realny z Subiekta,
                        // nie pytany, bo dopasowanie mogło być luźne (spacje/wielkość liter).
                        ob.Pozycje.Dodaj(enc.Symbol, p.Ilosc <= 0 ? 1m : p.Ilosc);
                        dodane++;
                    }

                    if (dodane == 0 && istniejace != null)
                    {
                        zkNumer = Bezp(() => ob.Dane.NumerWewnetrzny?.PelnaSygnatura);
                        kroki.Add(new Krok("zk", zkNumer ?? "", "bez-zmian",
                            $"wszystkie {pominietoJest} pozycji już są na dokumencie"));
                    }
                    else if (!ob.Zapisz())
                    {
                        kroki.Add(new Krok("zk", plan.Projekt ?? "", "blad", Bezp(ob.PodajBledy)));
                    }
                    else
                    {
                        zkNumer = Bezp(() => ob.Dane.NumerWewnetrzny?.PelnaSygnatura);
                        var co = istniejace != null
                            ? $"dopisano {dodane} poz."
                              + (pominietoJest > 0 ? $" ({pominietoJest} już było)" : "")
                            : $"utworzone ({dodane} poz.)";
                        kroki.Add(new Krok("zk", zkNumer ?? plan.Projekt ?? "", co, null));
                    }
                }
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok("zk", plan.Projekt ?? "", "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(new { zapisano = zapisz, zk = zkNumer, kroki },
            new JsonSerializerOptions { WriteIndented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    /// <summary>
    /// Komplety (Z/ZZ) w kolejności od najgłębszych do korzenia — składnik
    /// zapisany przed tym, co go zawiera. Głębokość liczona po faktycznym
    /// zagnieżdżeniu składników, nie po typie, bo ZZ potrafi zawierać ZZ.
    /// Cykl (gdyby BOM go zawierał) nie zapętla liczenia — ścieżka jest pilnowana.
    /// </summary>
    static List<PozPlan> PosortujOdDolu(List<PozPlan> pozycje)
    {
        var komplety = pozycje.Where(p => Rowne(p.Typ, "Z") || Rowne(p.Typ, "ZZ")).ToList();
        var wg = new Dictionary<string, PozPlan>(StringComparer.OrdinalIgnoreCase);
        foreach (var p in komplety) wg[p.Symbol.Trim()] = p;

        var glebokosc = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

        int Licz(PozPlan p, HashSet<string> sciezka)
        {
            var klucz = p.Symbol.Trim();
            if (glebokosc.TryGetValue(klucz, out var g)) return g;
            if (!sciezka.Add(klucz)) return 0;          // cykl — przerywamy

            var max = 0;
            foreach (var s in p.Skladniki ?? new List<SkladnikPlan>())
                if (wg.TryGetValue(s.Symbol.Trim(), out var dziecko))
                    max = Math.Max(max, Licz(dziecko, sciezka) + 1);

            sciezka.Remove(klucz);
            glebokosc[klucz] = max;
            return max;
        }

        foreach (var p in komplety) Licz(p, new HashSet<string>(StringComparer.OrdinalIgnoreCase));
        return komplety.OrderBy(p => glebokosc.TryGetValue(p.Symbol.Trim(), out var g) ? g : 0)
                       .ThenBy(p => p.Symbol)
                       .ToList();
    }

    /// <summary>
    /// Usuwa WSZYSTKIE skladniki kompletu. Zwraca, ile wierszy bylo.
    ///
    /// ISkladnikiKompletu nie ma "wyczysc" — jest tylko Usun(symbol) : bool
    /// (sprawdzone refleksja 06.09.2026). Nie wiadomo, czy Usun zdejmuje jedno
    /// wystapienie, czy wszystkie o tym symbolu, wiec wolamy w petli az zwroci
    /// false. Limit iteracji to bezpiecznik na wypadek, gdyby kiedys zaczelo
    /// zwracac true w nieskonczonosc.
    /// </summary>
    internal static int WyczyscSklad(dynamic ob)
    {
        var symbole = new List<string>();
        int bylo;
        try
        {
            IEnumerable<dynamic> sklad = ob.Dane.SkladnikiKompletu;
            var lista = sklad.ToList();
            bylo = lista.Count;
            foreach (var s in lista)
            {
                string? sym = s.Skladnik?.Symbol;
                if (!string.IsNullOrWhiteSpace(sym) && !symbole.Contains(sym)) symbole.Add(sym);
            }
        }
        catch
        {
            return 0;                 // brak kolekcji = nie ma czego czyscic
        }
        foreach (var sym in symbole)
        {
            var straznik = 0;
            while (straznik++ < 200 && (bool)ob.Skladniki.Usun(sym)) { }
        }
        return bylo;
    }

    static Podmiot? ZnajdzPodmiot(Uchwyt sfera, string? szukany)
    {
        if (string.IsNullOrWhiteSpace(szukany)) return null;
        var s = szukany.Trim();
        var firmy = sfera.Podmioty().Dane.WszystkieFirmy().ToList();
        return firmy.FirstOrDefault(p => string.Equals((p.NazwaSkrocona ?? "").Trim(), s, StringComparison.OrdinalIgnoreCase))
            ?? firmy.FirstOrDefault(p => (p.NIP ?? "").Replace("-", "").Trim() == s.Replace("-", ""))
            ?? firmy.FirstOrDefault(p => (p.NazwaSkrocona ?? "").Contains(s, StringComparison.OrdinalIgnoreCase));
    }

    static bool Rowne(string? a, string b) => string.Equals((a ?? "").Trim(), b, StringComparison.OrdinalIgnoreCase);

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record SkladnikPlan(string Symbol, decimal Ilosc);
    internal record PozPlan(string Symbol, string? Nazwa, string? Typ, decimal Ilosc, List<SkladnikPlan>? Skladniki);
    internal record Plan(string? Projekt, string? Tytul, string? Podmiot, string? Uwagi, List<PozPlan>? Pozycje);
    internal record Krok(string Rodzaj, string Symbol, string Status, string? Szczegoly);
}
