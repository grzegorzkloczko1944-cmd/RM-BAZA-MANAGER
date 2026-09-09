// Tryb "pw" — PRZYCHÓD WEWNĘTRZNY: dodaje towar na stan magazynu. ZAPISUJE.
//
//   NexoRecon.exe pw --plan=pw.json [--out=w.json] [--zapisz]
//
// Bez --zapisz to suchy przebieg: sprawdza kartoteki i mówi, co by przyjął.
//
// plan.json:
//   { "pozycje": [ {"symbol":"011-100.49", "ilosc": 3, "cena": 90.00} ],
//     "uwagi": "RM_BAZA - PROJEKT 2641",
//     "magazyn": "MASTER" }
//
// "cena" jest OPCJONALNA (cena netto za sztukę). Bez niej pozycja wchodzi po
// 0 zł — tak działa inwentaryzacja opisana niżej. Z ceną: PW produkcji własnej
// RMPAK, gdzie każdy detal niesie koszt wytworzenia z Kalkulatora RMPAK
// (RMPAK_PRODUKCJA_USTALENIA.md). Gdy cena jest w planie, ale nie da się jej
// ustawić — dokument NIE powstaje.
//
// Po co: uruchomienie magazynu nr 2 (SUBIEKT PODWÓJNE POZYCJE DO NAPRAWY.md,
// MAGAZYN.md) — inwentaryzacja z Excela ma wejść jako stan startowy. Pozycje
// mają TE SAME symbole co już istniejące kartoteki (ustalone z użytkownikiem:
// "te pozycje są z magazynu wyciągnięte... a w nowym magazynie one dalej będą
// tymi samymi pozycjami, bo mają te same symbole") — PW więc NIE zakłada
// nowych kartotek, tylko dopisuje stan istniejącym, po Symbolu. Kartoteki bez
// odpowiednika (patrz arkusz "Brak w Subiekcie") są tu pomijane z jasnym
// powodem — ich założenie to osobna decyzja (tryb "kartoteka").
//
// Lustrzane odbicie Rw.cs (ROZCHÓD): ta sama struktura planu, ten sam wzorzec
// Utworz(konfiguracja) + Pozycje.Dodaj, te same pułapki (data wystawienia
// i magazyn trzeba ustawić samemu, inaczej dokument wypada z list). Różnica:
// IPrzychodyWewnetrzne zamiast IRozchodyWewnetrzne, DataWydaniaWystawienia
// zamiast tego samego pola (Dokument ma jedno wspólne pole dla obu kierunków).

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Pw
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }
        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
        var pozycje = plan.Pozycje ?? new List<PozPlan>();
        if (pozycje.Count == 0) { Console.WriteLine("Plan bez pozycji."); return 1; }

        var asort = sfera.Asortymenty();
        var kroki = new List<Krok>();
        var doPrzyjecia = new List<(string Symbol, decimal Ilosc, decimal? Cena)>();

        foreach (var p in pozycje)
        {
            var symbol = (p.Symbol ?? "").Trim();
            if (symbol.Length == 0) { kroki.Add(new Krok("pozycja", "", "blad", "pusty symbol")); continue; }
            if (p.Ilosc <= 0)
            {
                kroki.Add(new Krok("pozycja", symbol, "blad", $"ilość {p.Ilosc} — musi być dodatnia"));
                continue;
            }
            dynamic? enc = null;
            try { enc = asort.Dane.WyszukajPoSymbolu(symbol); } catch { }
            if (enc == null) { kroki.Add(new Krok("pozycja", symbol, "blad", "brak kartoteki")); continue; }
            if (p.Cena is < 0)
            {
                kroki.Add(new Krok("pozycja", symbol, "blad", $"cena {p.Cena} — nie może być ujemna"));
                continue;
            }
            doPrzyjecia.Add((symbol, p.Ilosc, p.Cena));
            var opisCeny = p.Cena is { } c ? $" × {c:0.00}" : "";
            kroki.Add(new Krok("pozycja", symbol, zapisz ? "do-przyjecia" : "do-przyjecia (suchy)",
                               $"{p.Ilosc:0.##}{opisCeny}"));
        }

        string? numer = null;
        if (doPrzyjecia.Count == 0)
        {
            kroki.Add(new Krok("pw", "", "blad", "żadna pozycja nie nadaje się do przyjęcia"));
        }
        else if (zapisz)
        {
            try
            {
                var przychody = sfera.PrzychodyWewnetrzne();
                var konfig = KonfiguracjaPw(sfera);
                using var pw = konfig != null ? przychody.Utworz(konfig) : przychody.Utworz();

                // Droga zapisu ceny raportowana RAZ, nie przy każdej pozycji —
                // przy 300 detalach raport byłby 300 identycznymi wierszami.
                string? drogaCeny = null;
                var bezCeny = new List<string>();
                foreach (var (symbol, ilosc, cena) in doPrzyjecia)
                {
                    var enc = asort.Dane.WyszukajPoSymbolu(symbol);
                    pw.Pozycje.Dodaj(enc.Symbol, ilosc);
                    if (cena is not { } c) continue;

                    // Dodaj() nie zwraca pozycji — bierzemy ostatnią z dokumentu.
                    object? poz = null;
                    try
                    {
                        var wszystkie = ((System.Collections.IEnumerable)pw.Dane.Pozycje)
                            .Cast<object>().ToList();
                        poz = wszystkie.LastOrDefault();
                    }
                    catch { }
                    if (poz is null) { bezCeny.Add(symbol); continue; }

                    var droga = UstawCenePozycji(poz, c);
                    if (droga is null) bezCeny.Add(symbol);
                    else drogaCeny ??= droga;
                }
                if (drogaCeny != null)
                    kroki.Add(new Krok("pw", "", "cena-ustawiona", $"drogą: {drogaCeny}"));
                // Cicha pozycja po 0 zł byłaby gorsza niż brak dokumentu —
                // magazyn przyjąłby produkcję bezwartościowo i nikt by nie wiedział.
                if (bezCeny.Count > 0)
                    kroki.Add(new Krok("pw", "", "blad",
                        $"NIE UDAŁO SIĘ USTAWIĆ CENY dla {bezCeny.Count} poz.: "
                        + string.Join(", ", bezCeny.Take(10))
                        + (bezCeny.Count > 10 ? " …" : "")));

                // Ta sama pułapka co w Rw.cs / Zd.cs: bez daty wystawienia
                // i magazynu dokument jest w bazie, ale nie widać go na listach.
                try
                {
                    if ((DateTime)pw.Dane.DataWydaniaWystawienia == default(DateTime))
                        pw.Dane.DataWydaniaWystawienia = DateTime.Today;
                }
                catch { }
                try
                {
                    var magazyny = sfera.Magazyny().Dane.Wszystkie().ToList();
                    // Fallback gdy plan nie poda magazynu — "MASTER" (magazyn
                    // nr 2, przemianowany z "Magazyn" 08.09.2026). Ten sam symbol
                    // co w Rw.cs, Zd.cs i subiekt_magazyn_gui.py.
                    var chciany = (plan.Magazyn ?? "MASTER").Trim();
                    pw.Dane.Magazyn = magazyny.FirstOrDefault(m =>
                            string.Equals((Bezp(() => m.Symbol) ?? "").Trim(), chciany,
                                          StringComparison.OrdinalIgnoreCase))
                        ?? magazyny.FirstOrDefault();
                }
                catch { }

                if (!string.IsNullOrWhiteSpace(plan.Uwagi))
                    UstawUwagi(pw.Dane, plan.Uwagi.Trim(), kroki);

                // Nie zapisujemy PW, na którym miała być cena, a jej nie ma:
                // dokument po 0 zł jest gorszy niż jego brak, bo wygląda na
                // poprawny i trzeba go potem ręcznie anulować w Subiekcie.
                if (bezCeny.Count > 0)
                {
                    kroki.Add(new Krok("pw", "", "blad",
                        "PW NIE zapisane — najpierw musi działać ustawianie ceny."));
                }
                else if (!pw.Zapisz())
                {
                    var magazyn = Bezp(() => (string?)pw.Dane.Magazyn?.Symbol) ?? "?";
                    kroki.Add(new Krok("pw", "", "blad",
                        BledyDokumentu((object)pw)
                        ?? $"Subiekt odrzucil zapis PW bez podania powodu "
                           + $"(magazyn {magazyn}, {doPrzyjecia.Count} poz.)."));
                }
                else
                {
                    numer = Bezp(() => pw.Dane.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                    kroki.Add(new Krok("pw", numer, $"utworzone ({doPrzyjecia.Count} poz.)", null));
                }
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok("pw", "", "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        // zapisano = czy PW FAKTYCZNIE powstalo, nie "czy proszono o zapis" — ta sama
        // pulapka co w Rw.cs (odrzucony zapis nie moze wygladac jak sukces).
        var json = JsonSerializer.Serialize(
            new { zapisano = zapisz && !string.IsNullOrEmpty(numer), numer, kroki },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    /// Konfiguracja domyślna PW — wzorem KonfiguracjaRw w Rw.cs: szukamy po
    /// typie (ModelDanych.Konfiguracja), nie tylko po nazwie właściwości.
    static dynamic? KonfiguracjaPw(Uchwyt sfera)
    {
        try
        {
            object dd = sfera.Konfiguracje().DaneDomyslne;
            var t = dd.GetType();
            var typKonfig = typeof(InsERT.Moria.ModelDanych.Konfiguracja);
            var prop = t.GetProperties()
                .Concat(t.GetInterfaces().SelectMany(i => i.GetProperties()))
                .Where(p => typKonfig.IsAssignableFrom(p.PropertyType))
                .FirstOrDefault(p => p.Name.Equals("PrzychodWewnetrzny", StringComparison.OrdinalIgnoreCase))
                ?? t.GetProperties()
                .Concat(t.GetInterfaces().SelectMany(i => i.GetProperties()))
                .Where(p => typKonfig.IsAssignableFrom(p.PropertyType))
                .FirstOrDefault(p => p.Name.Contains("Przychod", StringComparison.OrdinalIgnoreCase));
            return prop?.GetValue(dd);
        }
        catch { return null; }
    }

    static void UstawUwagi(object dane, string chciane, List<Krok> kroki)
    {
        string? mam = null;
        try { ((dynamic)dane).Uwagi = chciane; mam = ((dynamic)dane).Uwagi; } catch { }
        if (mam != chciane)
        {
            foreach (var i in dane.GetType().GetInterfaces())
            {
                var pr = i.GetProperty("Uwagi");
                if (pr == null || !pr.CanWrite) continue;
                try { pr.SetValue(dane, chciane); mam = pr.GetValue(dane) as string; } catch { }
                if (mam == chciane) break;
            }
        }
        if (mam != chciane)
            kroki.Add(new Krok("pw", "", "uwaga", $"nie udało się ustawić Uwag (odczyt: \"{mam}\")"));
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    /// Wzorem BledyDokumentu w Rw.cs — refleksja, brak metody PodajBledy()
    /// nie może wywalać wyjątku, żeby nie przykryć prawdziwego powodu odrzucenia.
    static string? BledyDokumentu(object? bo)
    {
        if (bo is null) return null;
        try
        {
            var met = bo.GetType().GetMethod("PodajBledy", Type.EmptyTypes);
            if (met is null) return null;
            var w = met.Invoke(bo, null);
            var tekst = w switch
            {
                null => null,
                string s => s,
                System.Collections.IEnumerable e when w is not string
                    => string.Join("; ", e.Cast<object?>().Select(x => x?.ToString())
                                          .Where(x => !string.IsNullOrWhiteSpace(x))),
                _ => w.ToString(),
            };
            return string.IsNullOrWhiteSpace(tekst) ? null : tekst;
        }
        catch
        {
            return null;
        }
    }

    /// Cena pozycji PW. Zwraca opis drogi, która zadziałała, albo null.
    ///
    /// PW produkcji RMPAK niesie cenę wytworzenia (kalkulacja z Kalkulatora
    /// RMPAK) — bez niej dokument jest bezwartościowy, bo magazyn przyjąłby
    /// detale po 0 zł.
    ///
    /// `PozycjaDokumentu.Cena` NIE jest liczbą, tylko obiektem
    /// `InsERT.Moria.ModelDanych.Cena` (ustalone diagnostyką 09.09.2026 —
    /// pierwsze podejście „Cena = decimal" leciało wyjątkiem). Obiekt ma
    /// cztery zapisywalne pola decimal:
    ///
    ///   NettoPrzedRabatem, NettoPoRabacie, BruttoPrzedRabatem, BruttoPoRabacie
    ///
    /// Ustawiamy OBA pola netto na tę samą wartość, bo PW produkcji własnej
    /// nie zna rabatu — cena wytworzenia jest ceną końcową. `NettoPoRabacie`
    /// to pole, które Subiekt uznaje za cenę pozycji: tak właśnie czyta ją
    /// Dokumenty.cs:94 przy read-backu, więc zapis i odczyt patrzą w to samo
    /// miejsce.
    ///
    /// Brutto zostawiamy Subiektowi — przelicza je sam ze stawki VAT
    /// kartoteki; wpisane ręcznie mogłoby się z tym wyliczeniem rozjechać.
    static string? UstawCenePozycji(object poz, decimal cena)
    {
        object? obCena = null;
        try { obCena = ((dynamic)poz).Cena; } catch { }
        if (obCena is null) return null;

        var ustawione = new List<string>();
        foreach (var nazwa in new[] { "NettoPrzedRabatem", "NettoPoRabacie" })
        {
            var pr = obCena.GetType().GetProperty(nazwa);
            if (pr is null || !pr.CanWrite || pr.PropertyType != typeof(decimal)) continue;
            try
            {
                pr.SetValue(obCena, cena);
                if ((decimal?)pr.GetValue(obCena) == cena) ustawione.Add(nazwa);
            }
            catch { }
        }
        // Bez NettoPoRabacie cena nie jest ceną pozycji — samo
        // NettoPrzedRabatem zostawiłoby dokument z zerową wartością.
        return ustawione.Contains("NettoPoRabacie")
            ? $"Cena.{string.Join("+", ustawione)}" : null;
    }

    internal record PozPlan(string? Symbol, decimal Ilosc, decimal? Cena = null);
    internal record Plan(List<PozPlan>? Pozycje, string? Uwagi, string? Magazyn);
    internal record Krok(string Rodzaj, string Symbol, string Status, string? Szczegoly);
}
