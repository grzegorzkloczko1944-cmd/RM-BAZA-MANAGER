// Tryb "scal" — SCALANIE zduplikowanych kartotek w jedną docelową. ZAPISUJE (--zapisz).
//
//   NexoRecon.exe scal --plan=scal.json [--out=wynik.json] [--zapisz]
//
// Bez --zapisz to suchy przebieg ("Sprawdź scalanie"): pełny raport tego,
// co by się stało, bez dotykania bazy — ta sama zasada co "kartoteki".
//
// plan.json:
//   {"cel": "DN10 K=34", "zrodla": ["1DN10 K=34", "DN10 K=50,5"]}
//
// ZASADA (10.09.2026): symbol kartoteki jest kluczem — siedzi w kodach
// kreskowych, dokumentach i składach kompletów — więc scalanie NIE zmienia
// żadnego symbolu i NIE zakłada nowej kartoteki. Kartoteka docelowa zostaje
// dokładnie taka, jaka jest (nazwa, cena, VAT, JM, opis, położenie, pola
// własne). Źródłowe są WYCOFYWANE, nie kasowane:
//
//   1. Każde wystąpienie źródła w składzie jakiegokolwiek kompletu jest
//      przepinane na cel. Gdy cel już w tym komplecie siedzi — ilości się
//      SUMUJĄ (jeden składnik, nie dwa identyczne). Relację odwrotną daje
//      SDK wprost: Asortyment.SkladnikiWKompletach (patrz Komplet.cs).
//   2. Źródło dostaje w Opisie i Uwagach znacznik "SCALONO DO: <cel>".
//      Sfera nie ma na kartotece flagi "nieaktywna"/"wycofana" (sprawdzone
//      w InsERT.Moria.ModelDanych.xml — nie ma takiej właściwości), więc
//      znacznik w polach tekstowych to jedyne, co da się zrobić bez
//      kasowania. Kartoteka z historią (faktury, PZ, ZK) MUSI zostać —
//      usunięcie rozspójniłoby dokumenty (patrz KartotekaUsun.cs).
//   3. Różnice danych między źródłem a celem (cena, JM, VAT, położenie)
//      są tylko RAPORTOWANE jako ostrzeżenia — człowiek decyduje, czy
//      naprawdę scala to samo. Nic nie jest mieszane automatycznie.
//
// BLOKADY: cel i wszystkie źródła muszą być tego samego rodzaju i NIE mogą
// być kompletami. Towar→Komplet zmieniałoby sens pozycji, a Komplet→Komplet
// wymaga decyzji o obu składach — to osobny etap, nie ten tryb.
//
// Alias "stary symbol → cel" zapisuje strona Pythona (subiekt_mapowania),
// bo to metadana RM_BAZA, nie Subiekta.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Scal
{
    const string ZNACZNIK = "SCALONO DO: ";

    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }
        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
        var celSym = (plan?.Cel ?? "").Trim();
        var zrodlaSym = (plan?.Zrodla ?? new List<string>())
            .Select(s => (s ?? "").Trim()).Where(s => s.Length > 0)
            .Where(s => !s.Equals(celSym, StringComparison.OrdinalIgnoreCase))
            .Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        if (celSym.Length == 0 || zrodlaSym.Count == 0)
        {
            Console.WriteLine("scal: plan wymaga \"cel\" i co najmniej jednego \"zrodla\" innego niż cel.");
            return 1;
        }

        var asort = sfera.Asortymenty();
        var kroki = new List<Krok>();
        // symbol -> (nazwa, opis) dla kolumn raportu. Uzupelniany w miare
        // poznawania encji; komplety dochodza z relacji odwrotnej, wiec nie
        // ma tu dodatkowego przelotu po bazie.
        var opisy = new Dictionary<string, (string Nazwa, string Opis, decimal? Stan)>(
            StringComparer.OrdinalIgnoreCase);
        void Zapamietaj(InsERT.Moria.ModelDanych.Asortyment a)
        {
            var sym = (a.Symbol ?? "").Trim();
            if (sym.Length > 0)
                opisy[sym] = ((a.Nazwa ?? "").Trim(),
                              (Bezp(() => (string?)a.Opis) ?? "").Trim(), Stan(a));
        }
        var roznice = 0;
        var kolizje = 0;
        var przepiec = 0;
        var uzycie = 0;

        // ── 1. KARTOTEKI: istnienie i rodzaj ─────────────────────────────
        var cel = Znajdz(asort, celSym);
        if (cel == null)
        {
            kroki.Add(new Krok("cel", celSym, "blad", "nie ma takiej kartoteki w Subiekcie"));
            return Wynik(outPath, zapisz, celSym, null, zrodlaSym, new(), 0, 0, 0, 0, kroki, false, opisy);
        }
        var rodzajCel = Rodzaj(cel);
        if (CzyKomplet(rodzajCel))
        {
            kroki.Add(new Krok("cel", celSym, "blad",
                "cel jest KOMPLETEM — scalanie kompletów to osobny etap (co ze składami obu?)"));
            return Wynik(outPath, zapisz, celSym, cel.Id, zrodlaSym, new(), 0, 0, 0, 0, kroki, false, opisy);
        }
        Zapamietaj(cel);
        kroki.Add(new Krok("cel", celSym, "cel",
            $"{rodzajCel}: {(cel.Nazwa ?? "").Trim()} — dane tej kartoteki ZOSTAJĄ"));

        var zrodla = new List<InsERT.Moria.ModelDanych.Asortyment>();
        var idZrodel = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        var blokada = false;
        foreach (var s in zrodlaSym)
        {
            var enc = Znajdz(asort, s);
            if (enc == null)
            {
                kroki.Add(new Krok("zrodlo", s, "blad", "nie ma takiej kartoteki w Subiekcie"));
                blokada = true;
                continue;
            }
            var r = Rodzaj(enc);
            if (CzyKomplet(r))
            {
                kroki.Add(new Krok("zrodlo", s, "blad", "to KOMPLET — kompletów ten tryb nie scala"));
                blokada = true;
                continue;
            }
            if (!string.Equals(r, rodzajCel, StringComparison.OrdinalIgnoreCase))
            {
                kroki.Add(new Krok("zrodlo", s, "blad",
                    $"rodzaj {r} ≠ rodzaj celu {rodzajCel} — scalamy tylko Towar→Towar / Usługa→Usługa"));
                blokada = true;
                continue;
            }
            var opisObecny = (Bezp(() => (string?)enc.Opis) ?? "").Trim();
            if (opisObecny.StartsWith(ZNACZNIK, StringComparison.OrdinalIgnoreCase))
            {
                kroki.Add(new Krok("zrodlo", s, "blad", $"już scalona: „{opisObecny}”"));
                blokada = true;
                continue;
            }
            zrodla.Add(enc);
            Zapamietaj(enc);
            idZrodel[(enc.Symbol ?? "").Trim()] = enc.Id;
            kroki.Add(new Krok("zrodlo", s, "zrodlo", $"{r}: {(enc.Nazwa ?? "").Trim()}"));
        }
        if (blokada)
        {
            kroki.Add(new Krok("scalanie", celSym, "blad", "przerwano — popraw listę źródeł"));
            return Wynik(outPath, zapisz, celSym, cel.Id, zrodlaSym, idZrodel, 0, 0, 0, 0, kroki, false, opisy);
        }

        // ── 2. RÓŻNICE DANYCH — tylko ostrzeżenia ────────────────────────
        foreach (var z in zrodla)
        {
            var zs = (z.Symbol ?? "").Trim();
            void Porownaj(string pole, string? a, string? b)
            {
                a = (a ?? "").Trim(); b = (b ?? "").Trim();
                if (string.Equals(a, b, StringComparison.OrdinalIgnoreCase)) return;
                roznice++;
                kroki.Add(new Krok("roznica", zs, "roznica",
                    $"{pole}: „{a}” (źródło) ≠ „{b}” (cel — zostaje)"));
            }
            Porownaj("nazwa", z.Nazwa, cel.Nazwa);
            Porownaj("cena ewid.", Cena(z), Cena(cel));
            Porownaj("JM", Jm(z), Jm(cel));
            Porownaj("VAT sprzedaży", Vat(z, true), Vat(cel, true));
            Porownaj("VAT zakupu", Vat(z, false), Vat(cel, false));
            Porownaj("położenie", Polozenie(z), Polozenie(cel));
            // Stan zrodla NIE przenosi sie sam: scalanie nie rusza magazynu.
            // Mowimy o tym wprost, bo to najczestsze nieporozumienie — po
            // scaleniu towar dalej lezy na starej kartotece i trzeba go
            // przeksiegowac (RW/PW), jesli ma byc na docelowej.
            var stanZ = Stan(z) ?? 0;
            if (stanZ != 0)
            {
                roznice++;
                kroki.Add(new Krok("roznica", zs, "roznica",
                    $"na stanie {stanZ:0.##} szt — scalanie NIE przenosi magazynu; "
                    + "przeksieguj RW/PW, jesli towar ma trafic na kartoteke docelowa"));
            }
        }

        // ── 3. UŻYCIE W KOMPLETACH → plan przepięć ───────────────────────
        // komplet → (suma ilości źródeł do przeniesienia, lista wpisów)
        var przepiecia = new Dictionary<string, Przepiecie>(StringComparer.OrdinalIgnoreCase);
        foreach (var z in zrodla)
        {
            var zs = (z.Symbol ?? "").Trim();
            foreach (var w in Nadrzedne(z))
            {
                uzycie++;
                if (!przepiecia.TryGetValue(w.Komplet, out var p))
                {
                    przepiecia[w.Komplet] = p = new Przepiecie(w.Komplet, w.NazwaKompletu);
                    // Nazwe kompletu mamy z relacji odwrotnej; opisu nie —
                    // doczytywanie go kosztowaloby zapytanie na komplet.
                    if (!opisy.ContainsKey(w.Komplet))
                        opisy[w.Komplet] = (w.NazwaKompletu, "", null);
                }
                p.Ilosc += w.Ilosc;
                p.Wpisy.Add($"{zs} x{w.Ilosc:0.##}");
            }
        }
        // Czy cel już siedzi w którymś z tych kompletów — wtedy kolizja = suma.
        var celW = Nadrzedne(cel).ToDictionary(w => w.Komplet, w => w.Ilosc, StringComparer.OrdinalIgnoreCase);
        foreach (var p in przepiecia.Values)
        {
            if (celW.TryGetValue(p.Komplet, out var juz))
            {
                kolizje++;
                p.IloscCelu = juz;
                kroki.Add(new Krok("komplet", p.Komplet, zapisz ? "do-przepiecia" : "kolizja",
                    $"cel już w składzie x{juz:0.##} + {string.Join(" + ", p.Wpisy)} → {celSym} x{juz + p.Ilosc:0.##} (SUMA)"));
            }
            else
            {
                kroki.Add(new Krok("komplet", p.Komplet, "do-przepiecia",
                    $"{string.Join(", ", p.Wpisy)} → {celSym} x{p.Ilosc:0.##}"));
            }
            przepiec++;
        }
        if (przepiecia.Count == 0)
            kroki.Add(new Krok("komplet", celSym, "bez-zmian", "żadne źródło nie jest składnikiem kompletu"));

        foreach (var z in zrodla)
            kroki.Add(new Krok("zrodlo", (z.Symbol ?? "").Trim(), "do-wycofania",
                $"opis/uwagi: „{ZNACZNIK}{celSym}” (kartoteka zostaje — historia dokumentów nietknięta)"));

        if (!zapisz)
            return Wynik(outPath, zapisz, celSym, cel.Id, zrodlaSym, idZrodel, uzycie, przepiec, kolizje, roznice, kroki, true, opisy);

        // ── 4. ZAPIS: przepięcia w kompletach ────────────────────────────
        var ok = true;
        var symboleZrodel = new HashSet<string>(zrodla.Select(z => (z.Symbol ?? "").Trim()),
                                                StringComparer.OrdinalIgnoreCase);
        foreach (var p in przepiecia.Values)
        {
            try
            {
                var encK = Znajdz(asort, p.Komplet);
                if (encK == null) { kroki.Add(new Krok("komplet", p.Komplet, "blad", "komplet zniknął w trakcie")); ok = false; continue; }
                using var ob = asort.Znajdz(encK);

                // Usuwamy wpisy źródeł i (jeśli był) celu, potem wpisujemy cel raz
                // z sumą. Skladniki.Usun(symbol) w pętli ze strażnikiem — SDK nie
                // ma "ustaw ilość" (ta sama droga co KartotekaEdytuj.Sklad).
                decimal suma = p.Ilosc + p.IloscCelu;
                foreach (var sym in symboleZrodel.Append(celSym))
                {
                    var straznik = 0;
                    while (straznik++ < 200 && (bool)ob.Skladniki.Usun(sym)) { }
                }
                ob.Skladniki.Dodaj(cel, suma);
                KompletNapraw.Przenumeruj(ob);
                if (!ob.Zapisz())
                {
                    kroki.Add(new Krok("komplet", p.Komplet, "blad", Bezp(ob.PodajBledy) ?? "Zapisz() = false"));
                    ok = false;
                    continue;
                }
                kroki.Add(new Krok("komplet", p.Komplet, "przepiety",
                    $"{string.Join(", ", p.Wpisy)}{(p.IloscCelu > 0 ? $" + cel x{p.IloscCelu:0.##}" : "")} → {celSym} x{suma:0.##}"));
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok("komplet", p.Komplet, "blad", $"{ex.GetType().Name}: {ex.Message}"));
                ok = false;
            }
        }

        // ── 5. ZAPIS: wycofanie źródeł ───────────────────────────────────
        // Dopiero po przepięciach: gdyby przepięcie padło, źródło bez
        // znacznika nadal wygląda na czynne i da się spróbować ponownie.
        foreach (var z in zrodla)
        {
            var zs = (z.Symbol ?? "").Trim();
            try
            {
                using var ob = asort.Znajdz(z);
                var znacznik = ZNACZNIK + celSym;
                var opis = (Bezp(() => (string?)ob.Dane.Opis) ?? "").Trim();
                var uwagi = (Bezp(() => (string?)ob.Dane.Uwagi) ?? "").Trim();
                try { ob.Dane.Opis = opis.Length == 0 ? znacznik : $"{znacznik} | {opis}"; } catch { }
                try { ob.Dane.Uwagi = uwagi.Length == 0 ? znacznik : $"{znacznik}\n{uwagi}"; } catch { }
                if (!ob.Zapisz())
                {
                    kroki.Add(new Krok("zrodlo", zs, "blad", Bezp(ob.PodajBledy) ?? "Zapisz() = false"));
                    ok = false;
                    continue;
                }
                kroki.Add(new Krok("zrodlo", zs, "wycofana", $"„{znacznik}”"));
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok("zrodlo", zs, "blad", $"{ex.GetType().Name}: {ex.Message}"));
                ok = false;
            }
        }

        return Wynik(outPath, zapisz, celSym, cel.Id, zrodlaSym, idZrodel, uzycie, przepiec, kolizje, roznice, kroki, ok, opisy);
    }

    // ── pomocnicze ───────────────────────────────────────────────────────

    /// Kartoteka po symbolu z luźnym dopasowaniem (TRIM, wielkość liter).
    /// Zwraca typ STATYCZNY — inaczej Skladniki.Usun/Dodaj nie rozstrzygają
    /// przeciążeń (patrz uwaga w KartotekaEdytuj.Znajdz).
    static InsERT.Moria.ModelDanych.Asortyment? Znajdz(
        InsERT.Moria.Asortymenty.IAsortymenty asort, string symbol)
    {
        var enc = asort.Dane.WyszukajPoSymbolu(symbol);
        if (enc != null) return enc;
        var luzne = asort.Dane.Wszystkie().Select(a => a.Symbol).ToList()
            .FirstOrDefault(s => string.Equals((s ?? "").Trim(), symbol,
                                               StringComparison.OrdinalIgnoreCase));
        return luzne == null ? null : asort.Dane.WyszukajPoSymbolu(luzne);
    }

    static string Rodzaj(InsERT.Moria.ModelDanych.Asortyment a) =>
        (Bezp(() => (string?)a.Rodzaj?.Nazwa) ?? "").Trim();

    static bool CzyKomplet(string rodzaj) =>
        rodzaj.Contains("omplet", StringComparison.OrdinalIgnoreCase);

    /// Ilosc na magazynie: dostepne + zarezerwowane, zsumowane po WSZYSTKICH
    /// magazynach — dokladnie tak, jak liczy okno Asortyment (patrz
    /// subiekt_asortyment_gui: stan = dostepne + rezerwacje). Rezerwacja to
    /// nadal towar lezacy w firmie, wiec przy decyzji "czy to ten sam element"
    /// musi byc widoczna.
    ///
    /// StanyMagazynowe to najdrozsza czesc odczytu (dlatego tryb "katalog"
    /// ich nie ma), ale tutaj pytamy o kilka kartotek, ktorych encje juz
    /// trzymamy — koszt jest znikomy.
    static decimal? Stan(InsERT.Moria.ModelDanych.Asortyment a)
    {
        try
        {
            decimal suma = 0;
            foreach (var s in a.StanyMagazynowe)
                suma += s.IloscDostepna + s.IloscZarezerwowanaIlosciowo
                      + s.IloscZarezerwowanaDostawowo;
            return suma;
        }
        catch { return null; }      // kartoteka bez ruchu magazynowego
    }

    static string Cena(InsERT.Moria.ModelDanych.Asortyment a)
    {
        try { return decimal.Round(a.CenaEwidencyjna, 2).ToString("0.00"); }
        catch { return ""; }
    }

    static string Jm(InsERT.Moria.ModelDanych.Asortyment a) =>
        Bezp(() => (string?)a.JednostkaMagazynowa?.JednostkaMiary?.Symbol) ?? "";

    static string Vat(InsERT.Moria.ModelDanych.Asortyment a, bool sprzedaz) =>
        Bezp(() => (string?)(sprzedaz ? a.StawkaVatSprzedaz?.Symbol : a.StawkaVatKupno?.Symbol)) ?? "";

    static string Polozenie(InsERT.Moria.ModelDanych.Asortyment a) =>
        Bezp(() => (string?)a.PolaWlasne?.PoleWlasne1) ?? "";

    /// W jakich kompletach ta kartoteka jest składnikiem (relacja odwrotna z SDK).
    static List<Wystapienie> Nadrzedne(InsERT.Moria.ModelDanych.Asortyment a)
    {
        var lista = new List<Wystapienie>();
        try
        {
            foreach (var s in a.SkladnikiWKompletach)
            {
                var k = (Bezp(() => (string?)s.Komplet?.Symbol) ?? "").Trim();
                if (k.Length == 0) continue;
                lista.Add(new Wystapienie(k, (Bezp(() => (string?)s.Komplet?.Nazwa) ?? "").Trim(), s.Ilosc));
            }
        }
        catch { /* brak relacji = nigdzie nie użyta */ }
        return lista;
    }

    static int Wynik(string? outPath, bool zapisano, string cel, int? idCel, List<string> zrodla,
                     Dictionary<string, int> idZrodel, int uzycie, int przepiec, int kolizje,
                     int roznice, List<Krok> kroki, bool ok,
                     Dictionary<string, (string Nazwa, string Opis, decimal? Stan)>? opisy = null)
    {
        if (opisy is { Count: > 0 })
            for (var i = 0; i < kroki.Count; i++)
                if (opisy.TryGetValue(kroki[i].Symbol, out var d))
                    kroki[i] = kroki[i] with { Nazwa = d.Nazwa, Opis = d.Opis, Stan = d.Stan };

        var json = JsonSerializer.Serialize(new
        {
            zapisano, ok, cel, idCel, zrodla, idZrodel,
            uzycieWKompletach = uzycie, doPrzepiecia = przepiec, kolizje, roznice, kroki,
        }, new JsonSerializerOptions
        {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
        });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        // Zawsze 0: odmowa (komplet, brak kartoteki, rozne rodzaje) to
        // RAPORT z powodami, nie awaria mostu. Kod != 0 sprawia, ze strona
        // Pythona rzuca BridgeError i user nie widzi, CO zablokowalo scalanie
        // (sprawdzone 10.09.2026). Decyzje niesie pole "ok" w JSON.
        return 0;
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    sealed class Przepiecie
    {
        public Przepiecie(string komplet, string nazwa) { Komplet = komplet; Nazwa = nazwa; }
        public string Komplet { get; }
        public string Nazwa { get; }
        public decimal Ilosc { get; set; }
        public decimal IloscCelu { get; set; }
        public List<string> Wpisy { get; } = new();
    }

    internal record Wystapienie(string Komplet, string NazwaKompletu, decimal Ilosc);
    internal record Plan(string? Cel, List<string>? Zrodla);
    /// Nazwa/Opis sa OPCJONALNE i dopisywane hurtem w Wynik() ze slownika
    /// kartotek — inaczej trzeba by je przekazywac w 21 miejscach, a wiekszosc
    /// krokow i tak dotyczy symbolu, ktory juz znamy. Raport bez nich pokazywal
    /// samo "016-100.06" i nie dalo sie poznac, co to za pozycja (10.09.2026).
    internal record Krok(string Rodzaj, string Symbol, string Status, string? Szczegoly,
                         string? Nazwa = null, string? Opis = null, decimal? Stan = null);
}
