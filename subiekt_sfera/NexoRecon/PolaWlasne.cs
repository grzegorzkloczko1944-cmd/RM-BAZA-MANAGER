// Tryb "pola-wlasne" — DIAGNOSTYKA pól własnych asortymentu. Tylko odczyt.
//
//   NexoRecon.exe pola-wlasne [--out=wynik.json] [konfig.json]
//
// Po co: magazynier trzymał położenie na magazynie (regał/półka) w polu
// "Opis" kartoteki, razem z czym popadnie. Docelowo ma to iść do własnego
// pola. Subiekt NIE MA standardowego pola na położenie — sprawdzone w
// Dokumentacja_bazy_danych_nexo.htm: kolumna "Lokalizacja" na asortymencie
// jest opisana wprost jako "Dla przyszłych zastosowań" (zarezerwowana przez
// InsERT, nie ma jej w GUI), a druga "Lokalizacja" siedzi na pozycji
// dokumentu przyjęcia, nie na kartotece.
//
// Zostają POLA WŁASNE. Ten tryb mówi, które z nich są w tej bazie założone,
// jak się nazywają i czy są widoczne — czyli do którego wolno pisać.
// Sam nic nie zakłada ani nie zmienia.
//
// API za przykładem SDK (Przyklady/nexoPolaWlasne2):
//   IProstePolaWlasne.PobierzProstePolaWlasne<Asortyment>() -> Id, Nazwa, Widoczne
// Wartości czyta/pisze się osobno, przez IPolaWlasneAdv2Accessor
// (PobierzWartoscTypuTekst / UstawWartoscTypuTekst) — tego tu jeszcze nie ma.
//
// ⚠️ Pola własne wersji 2 NIE wymagają podmiany InsERT.Moria.ModelDanych.dll
// (tego wymaga dopiero wersja 1), więc dystrybucja mostu zostaje bez zmian.
//
// Interfejsy pobieramy przez sfera.PodajObiektTypu<T>() — tak samo jak
// ISzablonyAsortymentu w Kartoteka.cs i Projekt.cs. Gdy typu nie ma
// (inna wersja SDK), mówimy to wprost zamiast wywalać wyjątkiem: to tryb
// rozpoznawczy, ma działać także tam, gdzie pól własnych nie skonfigurowano.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class PolaWlasne
{
    /// Zapis WARTOSCI pola wlasnego na kartotekach asortymentu.
    ///
    ///   NexoRecon.exe pola-wlasne --plan=p.json [--out=w.json] [--zapisz]
    ///
    /// plan.json:
    ///   { "pole": "PoleWlasne1",
    ///     "pozycje": [ {"symbol":"011-100.49", "wartosc":"R5/P1"} ] }
    ///
    /// Po co: polozenie na magazynie (regal/polka) trzymane dotad w polu "Opis"
    /// razem z czym popadnie — MAGAZYN.md, sekcja o polu "Polozenie". Subiekt nie
    /// ma standardowego pola na polozenie (kolumna Lokalizacja jest "dla przyszlych
    /// zastosowan"), wiec uzywamy prostego pola wlasnego asortymentu.
    ///
    /// Zapis idzie WPROST na encje: Asortyment.PolaWlasne.PoleWlasne1..8
    /// (typ PolaWlasneAsortyment). NIE przez UtworzPolaWlasneAdv2Accessor —
    /// tamten obsluguje pola ZAAWANSOWANE v2, ktorych ta baza nie ma i rzuca
    /// wtedy InvalidOperationException. Po ustawieniu wartosci trzeba zapisac
    /// obiekt biznesowy kartoteki (ob.Zapisz()).
    public static int Zapis(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }
        var plan = JsonSerializer.Deserialize<PlanZapisu>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
        var pole = (plan.Pole ?? "PoleWlasne1").Trim();
        var pozycje = plan.Pozycje ?? new List<PozZapisu>();
        if (pozycje.Count == 0) { Console.WriteLine("Plan bez pozycji."); return 1; }

        var asort = sfera.Asortymenty();
        var kroki = new List<KrokZapisu>();
        int zmienionych = 0;

        foreach (var p in pozycje)
        {
            var symbol = (p.Symbol ?? "").Trim();
            if (symbol.Length == 0) continue;
            var wartosc = (p.Wartosc ?? "").Trim();

            try
            {
                dynamic? enc = null;
                try { enc = asort.Dane.WyszukajPoSymbolu(symbol); } catch { }
                if (enc == null)
                {
                    // Dopasowanie luzne jak wszedzie indziej (TRIM, wielkosc liter).
                    var luzny = asort.Dane.Wszystkie().Select(a => a.Symbol).ToList()
                        .FirstOrDefault(s => string.Equals((s ?? "").Trim(), symbol,
                                                           StringComparison.OrdinalIgnoreCase));
                    if (luzny != null) enc = asort.Dane.WyszukajPoSymbolu(luzny);
                }
                if (enc == null)
                {
                    kroki.Add(new KrokZapisu(symbol, "brak", "nie ma takiej kartoteki"));
                    continue;
                }

                using var ob = asort.Znajdz(enc);
                var dane = (InsERT.Moria.ModelDanych.Asortyment)ob.Dane;

                // ⚠️ NIE uzywamy UtworzPolaWlasneAdv2Accessor — to accessor pol
                // ZAAWANSOWANYCH (v2), ktorych ta baza nie ma:
                //   "Dla encji 'Asortyment' nie zdefiniowano zaawansowanych pol
                //    wlasnych w wersji 2." (sprawdzone na produkcji 07.09.2026)
                // PROSTE pola wlasne (PoleWlasne1..8) siedza wprost na encji:
                //   Asortyment.PolaWlasne -> PolaWlasneAsortyment { PoleWlasne1..8 }
                var pw = dane.PolaWlasne;
                if (pw == null)
                {
                    kroki.Add(new KrokZapisu(symbol, "blad", "kartoteka nie ma obiektu PolaWlasne"));
                    continue;
                }
                var propPola = pw.GetType().GetProperty(pole);
                if (propPola == null || !propPola.CanWrite)
                {
                    kroki.Add(new KrokZapisu(symbol, "blad", $"brak zapisywalnego pola „{pole}”"));
                    continue;
                }

                string? stara = null;
                try { stara = propPola.GetValue(pw) as string; } catch { }
                if ((stara ?? "").Trim() == wartosc)
                {
                    kroki.Add(new KrokZapisu(symbol, "bez-zmian", wartosc));
                    continue;
                }

                if (!zapisz)
                {
                    kroki.Add(new KrokZapisu(symbol, "do-zmiany", $"„{stara}” → „{wartosc}”"));
                    continue;
                }

                propPola.SetValue(pw, wartosc);
                if (!ob.Zapisz())
                {
                    kroki.Add(new KrokZapisu(symbol, "blad", "Zapisz() = false"));
                    continue;
                }
                zmienionych++;
                kroki.Add(new KrokZapisu(symbol, "zmieniona", $"„{stara}” → „{wartosc}”"));
            }
            catch (Exception ex)
            {
                kroki.Add(new KrokZapisu(symbol, "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(
            new { pole, zapisano = zapisz, zmienionych, kroki },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    internal record PozZapisu(string? Symbol, string? Wartosc);
    internal record PlanZapisu(string? Pole, List<PozZapisu>? Pozycje);
    internal record KrokZapisu(string Symbol, string Status, string? Szczegoly);

    public static int Uruchom(Uchwyt sfera, string? outPath)
    {
        var proste = new List<Pole>();
        var zaawansowane = new List<Pole>();
        var uwagi = new List<string>();

        // PROSTE pola własne (PolaWlasne1..8) — te są dla Asortymentu i Podmiotu.
        try
        {
            dynamic api = sfera.PodajObiektTypu<InsERT.Moria.PolaWlasne2.IProstePolaWlasne>();
            bool ma = false;
            try { ma = api.MaProstePolaWlasne(typeof(Asortyment)); } catch { }
            uwagi.Add($"MaProstePolaWlasne(Asortyment) = {ma}");

            foreach (var pole in api.PobierzProstePolaWlasne(typeof(Asortyment)))
                proste.Add(Czytaj(pole));
        }
        catch (Exception ex)
        {
            uwagi.Add($"proste pola własne niedostępne: {ex.GetType().Name}: {ex.Message}");
        }

        // ZAAWANSOWANE — osobny mechanizm, w tej bazie tabela była pusta
        // (SUBIEKT_PROJEKTY_WYDANIA.md 2.2). Czytamy dla pełności obrazu.
        try
        {
            dynamic api = sfera.PodajObiektTypu<InsERT.Moria.PolaWlasne2.IZaawansowanePolaWlasne>();
            foreach (var pole in api.PobierzZaawansowanePolaWlasne(typeof(Asortyment)))
                zaawansowane.Add(Czytaj(pole));
        }
        catch (Exception ex)
        {
            uwagi.Add($"zaawansowane pola własne niedostępne: {ex.GetType().Name}: {ex.Message}");
        }

        var json = JsonSerializer.Serialize(
            new { proste, zaawansowane, uwagi },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    /// Id/Nazwa/Widoczne czytamy pojedynczo — brak którejkolwiek właściwości
    /// w danej wersji SDK ma dać puste pole, a nie wywalić całego odczytu.
    static Pole Czytaj(dynamic pole) => new Pole(
        Bezp(() => (string?)pole.Id),
        Bezp(() => (string?)pole.Nazwa),
        BezpBool(() => (bool?)pole.Widoczne),
        Bezp(() => (string?)pole.Typ?.ToString()));

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }
    static bool? BezpBool(Func<bool?> f) { try { return f(); } catch { return null; } }

    internal record Pole(string? Id, string? Nazwa, bool? Widoczne, string? Typ);
}
