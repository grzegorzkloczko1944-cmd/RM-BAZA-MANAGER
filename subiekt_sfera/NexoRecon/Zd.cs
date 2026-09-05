// Tryb "zd" — tworzy zamówienia do dostawców z wybranych pozycji. ZAPISUJE.
//
//   NexoRecon.exe zd --plan=zd.json [--out=wynik.json] --zapisz
//
// Bez --zapisz to suchy przebieg (mówi co by zrobił, nic nie zapisuje).
//
// plan.json (buduje go subiekt_zamowienia.py):
//   { "pozycje": [ {"symbol":"013-100.22X", "ilosc":4, "dostawca":"NAZWA"} ] }
//
// ⚠️ ZD MUSI powstać przez UtworzNaPodstawieZapotrzebowania() — inaczej nie ma
// powiązania z ZK i Subiekt dalej uważa zamówienie klienta za niezrealizowane.
// Pierwsza wersja tworzyła ZD wprost (Utworz(konfiguracja) + Pozycje.Dodaj),
// bo most jest bezstanowy i nie da się przenieść obiektów
// PozycjaZestawieniaZapotrzebowania między wywołaniami procesu. Efekt
// (04.09.2026): ZD 5 i 6/09/2026 powstały poprawnie, ale te same pozycje
// wciąż wisiały w zapotrzebowaniu — wyglądało to, jakby zamówienie zniknęło.
//
// Rozwiązanie: zapotrzebowanie pobieramy i realizujemy w JEDNYM uruchomieniu.
// Plan z Pythona wskazuje pozycje po symbolu; tutaj dopasowujemy je do świeżo
// pobranego zestawienia i przekazujemy Sferze oryginalne obiekty.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Dokumenty.Logistyka;   // PozycjaZestawieniaZapotrzebowania
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Zd
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }

        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
        var pozycje = plan.Pozycje ?? new List<PozPlan>();
        if (pozycje.Count == 0) { Console.WriteLine("Plan bez pozycji."); return 1; }

        var zamowieniaZk = sfera.ZamowieniaOdKlientow();
        var zamowienia = sfera.ZamowieniaDoDostawcow();
        var asort = sfera.Asortymenty();          // do pozycji ręcznych (po symbolu)
        var kroki = new List<Krok>();
        var utworzone = new List<Zam>();

        // Podmioty raz do pamięci — dopasowanie po nazwie skróconej, jak w Projekt.cs.
        var firmy = sfera.Podmioty().Dane.WszystkieFirmy().ToList();

        Podmiot? ZnajdzDostawce(string nazwa)
        {
            var s = (nazwa ?? "").Trim();
            if (s.Length == 0) return null;
            return firmy.FirstOrDefault(p => string.Equals((p.NazwaSkrocona ?? "").Trim(), s,
                                                           StringComparison.OrdinalIgnoreCase))
                ?? firmy.FirstOrDefault(p => (p.NazwaSkrocona ?? "").Contains(s,
                                                           StringComparison.OrdinalIgnoreCase));
        }

        // Świeże zestawienie — to z niego biorą się obiekty, które Sfera potrafi
        // powiązać z ZK. Plan z Pythona tylko WSKAZUJE, które z nich zamówić
        // i u kogo.
        var zestawienie = zamowieniaZk.ZapotrzebowanieNaAsortyment();
        var wgSymbolu = new Dictionary<string, PozycjaZestawieniaZapotrzebowania>(
            StringComparer.OrdinalIgnoreCase);
        foreach (var z in zestawienie)
        {
            var sym = Bezp(() => z.Asortyment?.Symbol)?.Trim();
            if (!string.IsNullOrEmpty(sym)) wgSymbolu[sym] = z;
        }

        var doRealizacji = new List<PozycjaZestawieniaZapotrzebowania>();
        var brakujace = new List<string>();
        // Pozycje ręczne (spoza BOM-u): (podmiot, symbol, ilość) — dokładane do
        // ZD wprost, bo w zestawieniu zapotrzebowania ich nie ma.
        var reczne = new List<(Podmiot Podmiot, string Symbol, decimal Ilosc)>();

        foreach (var p in pozycje)
        {
            var symbol = (p.Symbol ?? "").Trim();
            var nazwaDostawcy = (p.Dostawca ?? "").Trim();
            if (nazwaDostawcy.Length == 0)
            {
                kroki.Add(new Krok("pozycja", symbol, "blad", "brak dostawcy"));
                continue;
            }
            var podmiot = ZnajdzDostawce(nazwaDostawcy);
            if (podmiot == null)
            {
                kroki.Add(new Krok("pozycja", symbol, "blad",
                    $"nie znaleziono podmiotu „{nazwaDostawcy}” w Subiekcie"));
                continue;
            }
            if (!wgSymbolu.TryGetValue(symbol, out var poz))
            {
                if (p.Reczna == true)
                {
                    // Pozycja dodana ręcznie w oknie — spoza BOM-u, więc nie ma
                    // jej w zapotrzebowaniu. Trafi do ZD wprost (patrz niżej),
                    // nie przez UtworzNaPodstawieZapotrzebowania.
                    reczne.Add((podmiot, symbol, p.Ilosc <= 0 ? 1m : p.Ilosc));
                    kroki.Add(new Krok("pozycja", symbol,
                        zapisz ? "do-zamowienia (ręczna)" : "do-utworzenia (ręczna)", nazwaDostawcy));
                    continue;
                }
                // Pozycji nie ma już w zapotrzebowaniu — ktoś ją w międzyczasie
                // zamówił albo wydał. Lepiej pominąć niż utworzyć duplikat.
                brakujace.Add(symbol);
                kroki.Add(new Krok("pozycja", symbol, "blad",
                    "nie ma jej już w zapotrzebowaniu (zamówiona lub wydana w międzyczasie)"));
                continue;
            }

            // Właściwości pozycji zestawienia są read-only, więc dostawcę
            // i ilość z okna wnosimy przez konstruktor. PozycjeZK przepisujemy
            // z oryginału — to one wiążą ZD z zamówieniem klienta.
            doRealizacji.Add(new PozycjaZestawieniaZapotrzebowania(
                poz.Asortyment,
                p.Ilosc > 0 ? p.Ilosc : poz.Ilosc,
                poz.JednostkaMiary,
                podmiot,
                poz.PozycjeZK));
            kroki.Add(new Krok("pozycja", symbol,
                zapisz ? "do-zamowienia" : "do-utworzenia", nazwaDostawcy));
        }

        if (doRealizacji.Count == 0 && reczne.Count == 0)
        {
            kroki.Add(new Krok("zd", "", "blad", "brak pozycji do zamówienia"));
        }
        else if (zapisz)
        {
            try
            {
                // Sfera sama grupuje po dostawcy I zakłada powiązanie z ZK —
                // dzięki temu pozycje znikają z zapotrzebowania po zamówieniu.
                var utworzoneZd = doRealizacji.Count > 0
                    ? zamowienia.UtworzNaPodstawieZapotrzebowania(doRealizacji).ToList()
                    : new List<InsERT.Moria.Dokumenty.Logistyka.IZamowienieDoDostawcy>();

                // Dostawcy, którzy mają TYLKO pozycje ręczne — dla nich ZD musi
                // powstać wprost, bo zestawienie nic dla nich nie zwróci.
                var podmiotyZd = new HashSet<int>(utworzoneZd
                    .Select(z => Bezp2(() => z.Dane.Podmiot?.Id ?? 0)).Where(i => i > 0));
                var konfiguracjaZd = sfera.Konfiguracje().DaneDomyslne.ZamowienieDoDostawcy;
                foreach (var grupa in reczne.GroupBy(r => r.Podmiot.Id))
                {
                    if (podmiotyZd.Contains(grupa.Key)) continue;
                    var nowy = zamowienia.Utworz(konfiguracjaZd);
                    nowy.Dane.Podmiot = grupa.First().Podmiot;
                    utworzoneZd.Add(nowy);
                    podmiotyZd.Add(grupa.Key);
                }

                foreach (var zd in utworzoneZd)
                {
                    using (zd)
                    {
                        var dostawca = Bezp(() => zd.Dane.Podmiot?.NazwaSkrocona) ?? "";

                        // Ręczne pozycje tego dostawcy — dopisane do dokumentu.
                        var idPodm = Bezp2(() => zd.Dane.Podmiot?.Id ?? 0);
                        foreach (var r in reczne.Where(r => r.Podmiot.Id == idPodm))
                        {
                            var enc = asort.Dane.WyszukajPoSymbolu(r.Symbol);
                            if (enc != null) zd.Pozycje.Dodaj(enc.Symbol, r.Ilosc);
                            else kroki.Add(new Krok("pozycja", r.Symbol, "blad", "brak kartoteki"));
                        }

                        // ⚠️ UtworzNaPodstawieZapotrzebowania NIE wypełnia daty
                        // wystawienia ani magazynu. Dokument bez daty wystawienia
                        // istnieje w bazie, ale WYPADA Z LIST w Subiekcie (filtrują
                        // po tej dacie i po zakresie „bieżące") — user go po prostu
                        // nie widzi. Zgłoszone 04.09.2026: „w subiekcie nie widzę
                        // tych z RM_BAZA", choć most je zwracał.
                        try
                        {
                            if (zd.Dane.DataWydaniaWystawienia == default)
                                zd.Dane.DataWydaniaWystawienia = DateTime.Today;
                        }
                        catch { /* pole opcjonalne w niektórych konfiguracjach */ }

                        // Uwagi z planu (np. "MAGAZYN") — tylko gdy podano; ZD
                        // z zapotrzebowania ZK zostawiamy bez zmian.
                        if (!string.IsNullOrWhiteSpace(plan.Uwagi))
                        {
                            // ⚠️ Pulapka Sfery: setter przy JAWNEJ implementacji
                            // interfejsu potrafi po cichu nic nie zrobic. Pierwsza
                            // wersja robila zd.Dane.Uwagi = ... i ZD 7/09/2026
                            // powstalo bez "MAGAZYN". Dlatego: zwykle przypisanie,
                            // potem settery z interfejsow, na koniec ODCZYT
                            // z powrotem — i krok w wyniku, gdy sie nie zgadza.
                            var chciane = plan.Uwagi.Trim();
                            object dane = zd.Dane;
                            try { zd.Dane.Uwagi = chciane; } catch { }
                            string? mam = null;
                            try { mam = zd.Dane.Uwagi; } catch { }
                            if (mam != chciane)
                            {
                                foreach (var i in dane.GetType().GetInterfaces())
                                {
                                    var pr = i.GetProperty("Uwagi");
                                    if (pr == null || !pr.CanWrite) continue;
                                    try { pr.SetValue(dane, chciane); } catch { }
                                    try { mam = pr.GetValue(dane) as string; } catch { }
                                    if (mam == chciane) break;
                                }
                            }
                            if (mam != chciane)
                                kroki.Add(new Krok("zd", dostawca, "uwaga",
                                    $"nie udalo sie ustawic Uwag=\"{chciane}\" (odczyt: \"{mam}\")"));
                        }

                        try
                        {
                            if (zd.Dane.Magazyn == null)
                                zd.Dane.Magazyn = sfera.Magazyny().Dane.Wszystkie()
                                    .FirstOrDefault(m => m.Symbol == "MAG")
                                    ?? sfera.Magazyny().Dane.Wszystkie().FirstOrDefault();
                        }
                        catch { /* ZD bywa bez magazynu — nie blokujemy zapisu */ }

                        if (!zd.Zapisz())
                        {
                            kroki.Add(new Krok("zd", dostawca, "blad", Bezp(zd.PodajBledy)));
                            continue;
                        }
                        var numer = Bezp(() => zd.Dane.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                        var ile = 0;
                        try { ile = zd.Dane.Pozycje.Count(); } catch { }
                        utworzone.Add(new Zam(numer, dostawca, ile));
                        kroki.Add(new Krok("zd", dostawca, $"utworzone {numer} ({ile} poz.)", null));
                    }
                }
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok("zd", "", "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(new { zapisano = zapisz, zd = utworzone, kroki },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }
    static int Bezp2(Func<int> f) { try { return f(); } catch { return 0; } }

    internal record PozPlan(string Symbol, decimal Ilosc, string? Dostawca, bool? Reczna);
    // Uwagi na ZD — okno magazynu wpisuje tu "MAGAZYN", zeby zamowienie
    // na sklad dalo sie odroznic od projektowych (kolumna Projekt w Przegladzie
    // dokumentow bierze sie z Uwag).
    internal record Plan(List<PozPlan>? Pozycje, string? Uwagi);
    internal record Zam(string Numer, string Dostawca, int Pozycji);
    internal record Krok(string Rodzaj, string Symbol, string Status, string? Szczegoly);
}
