// Tryb "pz-utworz" — PRZYJĘCIE ZEWNĘTRZNE z dostawy. ZAPISUJE.
//
//   NexoRecon.exe pz-utworz --plan=pz.json [--out=w.json] [--zapisz]
//
// Bez --zapisz suchy przebieg: sprawdza ZD, pozycje i kartoteki, mówi co by
// przyjął, nic nie zapisuje.
//
// plan.json:
//   { "nip": "9721002583",                       // dostawca (gdy brak ZD)
//     "zd_pozycje": [ {"zd_id": 100214, "pozycja_id": 100501, "ilosc": 4} ],
//     "reczne":     [ {"symbol": "688 ZZ", "ilosc": 2, "cena": 4.30} ],
//     "magazyn": "MASTER",
//     "nr_wz": "WZ/01578/26",                    // → NumerZewnetrzny PZ
//     "uwagi": "DOSTAWA 17, paczka 1/2" }
//
// ⚠️ DLACZEGO WypelnijNaPodstawieZD, A NIE Pozycje.Dodaj — ta sama lekcja co
// w Zd.cs („ZD MUSI powstać przez UtworzNaPodstawieZapotrzebowania"):
// dodanie pozycji wprost dałoby PZ bez powiązania z ZD. Subiekt nie wiedziałby,
// że zamówienie zostało zrealizowane, ZD wisiałoby „do realizacji" w
// nieskończoność, a RM_BAZA musiałaby prowadzić własną sieć ZD↔PZ — czego
// notatka o obiegu przyjęć wprost zakazuje („Subiekt trzyma relacje SAM").
//
//   IPrzyjecieZewnetrzne.WypelnijNaPodstawieZD(IEnumerable<PozycjaDokumentu>, DokumentZD)
//     „Dodaje podane pozycje zamówienia do dostawcy na dokument przyjęcia jako
//      realizacje. dokumentZDGlowny — ZD, z którego będzie przepisany podmiot."
//
// Pozycje z KILKU ZD tego samego dostawcy idą jednym wywołaniem (jedna paczka
// bywa z kilku zamówień); podmiot bierze się z pierwszego ZD. Ilość mniejsza
// niż zamówiona = realizacja częściowa — resztę Subiekt sam trzyma w
// `IloscDoRealizacji` pozycji ZD, więc kolejna dostawa widzi, ile zostało.
//
// Pozycje RĘCZNE (spoza ZD — dostawca dołożył coś ekstra) idą przez
// Pozycje.Dodaj, jak w Pw.cs. Dostawa BEZ żadnego ZD: podmiot po NIP.
//
// Wzorzec zapisu (konfiguracja, data, magazyn, Uwagi/Tytuł, PodajBledy)
// skopiowany z Pw.cs — te same pułapki: bez daty i magazynu dokument jest
// w bazie, ale nie widać go na listach.

using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class PzUtworz
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }
        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
        var zdPoz = plan.ZdPozycje ?? new List<ZdPoz>();
        var reczne = plan.Reczne ?? new List<Reczna>();
        if (zdPoz.Count == 0 && reczne.Count == 0) { Console.WriteLine("Plan bez pozycji."); return 1; }

        var kroki = new List<Krok>();
        var asort = sfera.Asortymenty();

        // ── 1. Pozycje ZD: encje z żywych dokumentów, po Id ─────────────────
        var zamowienia = sfera.ZamowieniaDoDostawcow();
        var wgZd = new Dictionary<int, DokumentZD>();
        // (pozycja ZD, ilość do przyjęcia) — encje potrzebne do WypelnijNaPodstawieZD
        var doRealizacji = new List<(PozycjaDokumentu Poz, decimal Ilosc, int ZdId)>();
        foreach (var z in zdPoz)
        {
            if (!wgZd.TryGetValue(z.ZdId, out var zd))
            {
                zd = zamowienia.Dane.Wszystkie().FirstOrDefault(d => d.Id == z.ZdId);
                if (zd is null)
                {
                    kroki.Add(new Krok("zd", z.ZdId.ToString(), "blad", "nie ma ZD o tym Id"));
                    continue;
                }
                wgZd[z.ZdId] = zd;
            }
            var poz = zd.Pozycje.FirstOrDefault(p => p.Id == z.PozycjaId);
            if (poz is null)
            {
                kroki.Add(new Krok("zd-pozycja", z.PozycjaId.ToString(), "blad",
                    $"ZD {Numer(zd)} nie ma pozycji o tym Id"));
                continue;
            }
            var symbol = (Bezp(() => poz.AsortymentAktualny?.Symbol) ?? "").Trim();
            // `IloscDoRealizacji` to OBIEKT (jak `Cena`) — liczba siedzi
            // w `PozostalaIlosc` (dokumentacja: IloscDoRealizacji klasa).
            var doReal = Bezp2(() => poz.IloscDoRealizacji.PozostalaIlosc) ?? poz.Ilosc;
            if (z.Ilosc <= 0)
            {
                kroki.Add(new Krok("zd-pozycja", symbol, "blad", $"ilość {z.Ilosc} — musi być dodatnia"));
                continue;
            }
            if (z.Ilosc > doReal)
                // Nadwyżka to realna sytuacja (dostawca przysłał więcej) — ale
                // Subiekt może odmówić realizacji ponad zamówienie. Mówimy
                // o tym wprost, zamiast cicho obcinać.
                kroki.Add(new Krok("zd-pozycja", symbol, "uwaga",
                    $"przyjęcie {z.Ilosc:0.##} > do realizacji {doReal:0.##} (ZD {Numer(zd)})"));
            doRealizacji.Add((poz, z.Ilosc, z.ZdId));
            kroki.Add(new Krok("zd-pozycja", symbol, zapisz ? "do-przyjecia" : "do-przyjecia (suchy)",
                $"{z.Ilosc:0.##} z ZD {Numer(zd)} (do realizacji było {doReal:0.##})"));
        }

        // ── 2. Pozycje ręczne: po symbolu kartoteki ─────────────────────────
        var doDodania = new List<(string Symbol, decimal Ilosc, decimal? Cena)>();
        foreach (var r in reczne)
        {
            var symbol = (r.Symbol ?? "").Trim();
            if (symbol.Length == 0) { kroki.Add(new Krok("pozycja", "", "blad", "pusty symbol")); continue; }
            if (r.Ilosc <= 0) { kroki.Add(new Krok("pozycja", symbol, "blad", $"ilość {r.Ilosc} — musi być dodatnia")); continue; }
            dynamic? enc = null;
            try { enc = asort.Dane.WyszukajPoSymbolu(symbol); } catch { }
            if (enc == null) { kroki.Add(new Krok("pozycja", symbol, "blad", "brak kartoteki")); continue; }
            if (r.Cena is < 0) { kroki.Add(new Krok("pozycja", symbol, "blad", "cena ujemna")); continue; }
            doDodania.Add((symbol, r.Ilosc, r.Cena));
            kroki.Add(new Krok("pozycja", symbol, zapisz ? "do-przyjecia" : "do-przyjecia (suchy)",
                $"{r.Ilosc:0.##}{(r.Cena is { } c ? $" × {c:0.00}" : "")} (spoza ZD)"));
        }

        // ── 3. Podmiot: z ZD, a bez ZD — po NIP ─────────────────────────────
        Podmiot? podmiot = null;
        if (wgZd.Count == 0)
        {
            var nip = (plan.Nip ?? "").Replace("-", "").Replace(" ", "").Trim();
            if (nip.Length > 0)
                podmiot = sfera.Podmioty().Dane.WszystkieFirmy().ToList().FirstOrDefault(p =>
                    ((Bezp(() => (string?)p.NIP) ?? "").Replace("-", "").Trim()) == nip);
            if (podmiot is null)
                kroki.Add(new Krok("podmiot", nip, "blad",
                    "dostawa bez ZD wymaga kontrahenta o tym NIP w Subiekcie"));
        }

        string? numer = null;
        int? pzId = null;
        var moznaZapisac = (doRealizacji.Count > 0 || doDodania.Count > 0)
                           && (wgZd.Count > 0 || podmiot != null)
                           && !kroki.Any(k => k.Status == "blad");
        if (!moznaZapisac)
        {
            kroki.Add(new Krok("pz", "", "blad", "PZ nie powstanie — popraw błędy wyżej"));
        }
        else if (zapisz)
        {
            try
            {
                var przyjecia = sfera.PrzyjeciaZewnetrzne();
                var konfig = KonfiguracjaPz(sfera) as Konfiguracja;
                // ⚠️ Jawny typ: z argumentem `dynamic` wynik Utworz() też byłby
                // dynamic, a wtedy lambda w WypelnijNaPodstawieZD nie kompiluje
                // się (CS1977). Pw.cs tego nie zauważył, bo używa tylko Dodaj().
                using InsERT.Moria.Dokumenty.Logistyka.IPrzyjecieZewnetrzne pz =
                    konfig != null ? przyjecia.Utworz(konfig) : przyjecia.Utworz();

                // Realizacje ZD — jednym wywołaniem, podmiot z pierwszego ZD.
                if (doRealizacji.Count > 0)
                {
                    var glowny = wgZd[doRealizacji[0].ZdId];
                    var dodane = pz.WypelnijNaPodstawieZD(doRealizacji.Select(x => x.Poz).ToList(), glowny);
                    // Ilość przyjęta ≠ zamówiona → realizacja częściowa. Pozycje
                    // wracają w kolejności podania; dopasowujemy po symbolu
                    // dla pewności, bo kolejności API nie gwarantuje.
                    var lista = dodane?.ToList() ?? new List<PozycjaDokumentu>();
                    foreach (var (poz, ilosc, _) in doRealizacji)
                    {
                        var sym = Bezp(() => poz.AsortymentAktualny?.Symbol) ?? "";
                        var naPz = lista.FirstOrDefault(p =>
                            string.Equals(Bezp(() => p.AsortymentAktualny?.Symbol), sym,
                                          StringComparison.OrdinalIgnoreCase)
                            && p.Ilosc != ilosc);
                        if (naPz is null) continue;
                        try { naPz.Ilosc = ilosc; }
                        catch (Exception e)
                        {
                            kroki.Add(new Krok("zd-pozycja", sym, "uwaga",
                                $"nie udało się zmienić ilości na {ilosc:0.##}: {e.Message}"));
                        }
                    }
                    kroki.Add(new Krok("pz", "", "realizacja-zd",
                        $"{lista.Count} poz. z {wgZd.Count} ZD: {string.Join(", ", wgZd.Values.Select(Numer))}"));
                }
                else if (podmiot != null)
                {
                    pz.Dane.Podmiot = podmiot;
                }

                // Pozycje spoza ZD — jak w Pw.cs.
                var bezCeny = new List<string>();
                foreach (var (symbol, ilosc, cena) in doDodania)
                {
                    var enc = asort.Dane.WyszukajPoSymbolu(symbol);
                    pz.Pozycje.Dodaj(enc.Symbol, ilosc);
                    if (cena is not { } c) continue;
                    object? poz = null;
                    try
                    {
                        poz = ((System.Collections.IEnumerable)pz.Dane.Pozycje).Cast<object>().LastOrDefault();
                    }
                    catch { }
                    if (poz is null || UstawCenePozycji(poz, c) is null) bezCeny.Add(symbol);
                }
                if (bezCeny.Count > 0)
                    kroki.Add(new Krok("pz", "", "uwaga",
                        "nie udało się ustawić ceny: " + string.Join(", ", bezCeny.Take(10))));

                // ⚠️ Data PZ = data FIZYCZNEGO przyjęcia (z planu), nie „dziś" —
                // magazynier bywa wpisuje wczorajszą paczkę. Bez daty w planie
                // zostaje dzisiejsza; pusta data = dokument niewidoczny na listach.
                try
                {
                    var data = DateTime.TryParseExact(plan.Data ?? "", "yyyy-MM-dd", null,
                                   System.Globalization.DateTimeStyles.None, out var d)
                               ? d : DateTime.Today;
                    pz.Dane.DataWydaniaWystawienia = data;
                }
                catch
                {
                    try { pz.Dane.DataWydaniaWystawienia = DateTime.Today; } catch { }
                }
                try
                {
                    var magazyny = sfera.Magazyny().Dane.Wszystkie().ToList();
                    var chciany = (plan.Magazyn ?? "MASTER").Trim();
                    var mag = magazyny.FirstOrDefault(m =>
                        string.Equals((Bezp(() => m.Symbol) ?? "").Trim(), chciany,
                                      StringComparison.OrdinalIgnoreCase));
                    if (mag != null) pz.Dane.Magazyn = mag;
                    else if (pz.Dane.Magazyn == null) pz.Dane.Magazyn = magazyny.FirstOrDefault();
                }
                catch { }

                // Numer WZ dostawcy → NumerZewnetrzny. To pole PZ czyta tryb
                // `pz` (pomiar 17.09.2026) i po nim faktura KSeF dopina się
                // do przyjęcia (Numer wydania na pozycji faktury).
                if (!string.IsNullOrWhiteSpace(plan.NrWz))
                    UstawPole(pz.Dane, "NumerZewnetrzny", plan.NrWz.Trim(), kroki);
                if (!string.IsNullOrWhiteSpace(plan.Uwagi))
                    UstawPole(pz.Dane, "Uwagi", plan.Uwagi.Trim(), kroki);
                UstawPole(pz.Dane, "Tytul", Znacznik.Tytul(), kroki);

                if (!pz.Zapisz())
                {
                    kroki.Add(new Krok("pz", "", "blad",
                        BledyDokumentu((object)pz)
                        ?? "Subiekt odrzucił zapis PZ bez podania powodu."));
                }
                else
                {
                    numer = Bezp(() => pz.Dane.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                    pzId = Bezp2(() => (int)pz.Dane.Id);
                    kroki.Add(new Krok("pz", numer,
                        $"utworzone ({doRealizacji.Count} z ZD + {doDodania.Count} spoza)", null));
                }
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok("pz", "", "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(
            new { zapisano = zapisz && !string.IsNullOrEmpty(numer), numer, pzId, kroki },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    static string Numer(Dokument d) => Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? d.Id.ToString();

    /// Konfiguracja domyślna PZ — wzorem KonfiguracjaPw: po typie, potem po nazwie.
    static dynamic? KonfiguracjaPz(Uchwyt sfera)
    {
        try
        {
            object dd = sfera.Konfiguracje().DaneDomyslne;
            var t = dd.GetType();
            var typKonfig = typeof(Konfiguracja);
            var props = t.GetProperties().Concat(t.GetInterfaces().SelectMany(i => i.GetProperties()))
                .Where(p => typKonfig.IsAssignableFrom(p.PropertyType)).ToList();
            var prop = props.FirstOrDefault(p => p.Name.Equals("PrzyjecieZewnetrzne", StringComparison.OrdinalIgnoreCase))
                    ?? props.FirstOrDefault(p => p.Name.Contains("PrzyjecieZewn", StringComparison.OrdinalIgnoreCase));
            return prop?.GetValue(dd);
        }
        catch { return null; }
    }

    /// Kopia z Pw.cs — setter przez jawny interfejs bywa cichy, stąd odczyt kontrolny.
    static void UstawPole(object dane, string nazwa, string chciane, List<Krok> kroki)
    {
        string? mam = null;
        try
        {
            var pr0 = dane.GetType().GetProperty(nazwa);
            if (pr0 != null && pr0.CanWrite) { pr0.SetValue(dane, chciane); mam = pr0.GetValue(dane) as string; }
        }
        catch { }
        if (mam != chciane)
        {
            foreach (var i in dane.GetType().GetInterfaces())
            {
                var pr = i.GetProperty(nazwa);
                if (pr == null || !pr.CanWrite) continue;
                try { pr.SetValue(dane, chciane); mam = pr.GetValue(dane) as string; } catch { }
                if (mam == chciane) break;
            }
        }
        if (mam != chciane)
            kroki.Add(new Krok("pz", "", "uwaga", $"nie udało się ustawić pola {nazwa} (odczyt: \"{mam}\")"));
    }

    /// Kopia z Pw.cs — `Cena` to obiekt, ustawiamy NettoPrzedRabatem + NettoPoRabacie.
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
            try { pr.SetValue(obCena, cena); if ((decimal?)pr.GetValue(obCena) == cena) ustawione.Add(nazwa); }
            catch { }
        }
        return ustawione.Contains("NettoPoRabacie") ? $"Cena.{string.Join("+", ustawione)}" : null;
    }

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
        catch { return null; }
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }
    static T? Bezp2<T>(Func<T> f) where T : struct { try { return f(); } catch { return null; } }

    // ⚠️ Klucze planu sa snake_case (tak pisze Python). PropertyNameCaseInsensitive
    // NIE laczy `zd_pozycje` z `ZdPozycje` — bez jawnych nazw lista ZD byla
    // pusta i suchy przebieg pomijal realizacje PO CICHU (18.09.2026).
    internal record ZdPoz([property: JsonPropertyName("zd_id")] int ZdId,
                          [property: JsonPropertyName("pozycja_id")] int PozycjaId,
                          [property: JsonPropertyName("ilosc")] decimal Ilosc);
    internal record Reczna([property: JsonPropertyName("symbol")] string? Symbol,
                           [property: JsonPropertyName("ilosc")] decimal Ilosc,
                           [property: JsonPropertyName("cena")] decimal? Cena);
    internal record Plan([property: JsonPropertyName("nip")] string? Nip,
                         [property: JsonPropertyName("zd_pozycje")] List<ZdPoz>? ZdPozycje,
                         [property: JsonPropertyName("reczne")] List<Reczna>? Reczne,
                         [property: JsonPropertyName("magazyn")] string? Magazyn,
                         [property: JsonPropertyName("nr_wz")] string? NrWz,
                         [property: JsonPropertyName("uwagi")] string? Uwagi,
                         [property: JsonPropertyName("data")] string? Data);
    internal record Krok(string Rodzaj, string Symbol, string Status, string? Szczegoly);
}
