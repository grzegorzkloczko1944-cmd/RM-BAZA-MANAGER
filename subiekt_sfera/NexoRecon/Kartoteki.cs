// Tryb "kartoteki" — WSADOWE zakładanie i edycja kartotek wraz ze składami
// kompletów. ZAPISUJE.
//
//   NexoRecon.exe kartoteki --plan=k.json [--out=w.json] [--zapisz]
//
// Bez --zapisz suchy przebieg: mówi, co powstanie, co się zmieni, a co jest
// już takie samo — NIC nie zapisuje. To jest „Sprawdź całość" z edytora.
//
// plan.json:
//   { "pozycje": [
//       { "symbol":"SZ-100", "nazwa":"Szafa sterownicza", "rodzaj":"komplet",
//         "jm":"kpl", "cena":0, "opis":"...",
//         "skladniki":[ {"symbol":"KORP-01","ilosc":1},
//                       {"symbol":"ZAM-01","ilosc":2} ] },
//       { "symbol":"KORP-01", "nazwa":"Korpus", "rodzaj":"towar", "jm":"szt" }
//     ] }
//
// Po co osobny tryb, skoro są już "kartoteka" i "projekt":
//
//   kartoteka  — JEDNA kartoteka na wywołanie. Przy 30 pozycjach z edytora to
//                30 uruchomień; przez stały most szybciej, ale nadal 30 rund.
//   projekt    — cały zestaw naraz, ale ZAWSZE tworzy też ZK projektu i wymaga
//                podmiotu. Do budowania samych kartotek to narzut i skutek
//                uboczny (dokument, o który nikt nie prosił).
//   kartoteki  — TU: zestaw kartotek + składy kompletów, BEZ ZK i bez podmiotu.
//                Backend „Edytora kartotek" (okno drzewkowe, 08.09.2026).
//
// Kolejność operacji jest ta sama co w Projekt.cs i nieprzypadkowa:
//   1. kartoteki (składnik musi istnieć, zanim wejdzie do składu)
//   2. składy kompletów OD DOŁU DRZEWA (komplet musi istnieć, zanim wejdzie
//      jako składnik do nadrzędnego — ZZ potrafi zawierać ZZ)
//
// Pozycja, która już istnieje, jest EDYTOWANA (nazwa/cena/opis/skład), nie
// pomijana — edytor służy też do poprawiania istniejących kartotek. Symbol
// jest kluczem i nigdy się nie zmienia (kody kreskowe, dokumenty, składy).

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Kartoteki
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }
        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
        var pozycje = plan.Pozycje ?? new List<PozPlan>();
        if (pozycje.Count == 0) { Console.WriteLine("Plan bez pozycji."); return 1; }

        var asort = sfera.Asortymenty();
        var szablony = sfera.PodajObiektTypu<InsERT.Moria.Asortymenty.ISzablonyAsortymentu>();

        // Slownik stawek VAT — StawkaVatSprzedaz/Kupno to ENCJE StawkaVat,
        // nie liczby, wiec trzeba je znalezc po Symbolu ("23", "8", "zw").
        // Jeden odczyt na caly przebieg zamiast per pozycja.
        var stawkiVat = new Dictionary<string, dynamic>(StringComparer.OrdinalIgnoreCase);
        try
        {
            var kartoteka = sfera.PodajObiektTypu<InsERT.Moria.Slowniki.IStawkiVat>();
            foreach (var sv in kartoteka.Dane.Wszystkie())
            {
                var sym = (Bezp(() => (string?)sv.Symbol) ?? "").Trim();
                if (sym.Length > 0) stawkiVat[sym] = sv;
            }
        }
        catch { /* brak dostepu do slownika = pola VAT zostana pominiete */ }
        var kroki = new List<Krok>();
        int zalozonych = 0, zmienionych = 0, skladow = 0;

        // Mapa symboli JUZ w bazie — jeden przelot, zeby nie pytac per pozycja.
        var wBazie = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var a in asort.Dane.Wszystkie().Select(a => a.Symbol).ToList())
        {
            var s = (a ?? "").Trim();
            if (s.Length > 0) wBazie[s] = a!;
        }

        // ── 1. KARTOTEKI ─────────────────────────────────────────────────
        foreach (var p in pozycje)
        {
            var symbol = (p.Symbol ?? "").Trim();
            if (symbol.Length == 0) { kroki.Add(new Krok("kartoteka", "", "blad", "pusty symbol")); continue; }

            var jestKompletem = CzyKomplet(p.Rodzaj);
            var nazwa = string.IsNullOrWhiteSpace(p.Nazwa) ? symbol : p.Nazwa!.Trim();

            try
            {
                if (wBazie.TryGetValue(symbol, out var realny))
                {
                    // ISTNIEJE — edytujemy to, co przyszlo w planie. Pola pominiete
                    // (null) zostaja nietkniete; pusty string to swiadome wyczyszczenie.
                    var enc = asort.Dane.WyszukajPoSymbolu(realny);
                    if (enc == null)
                    {
                        kroki.Add(new Krok("kartoteka", symbol, "blad", "znikla z bazy w trakcie"));
                        continue;
                    }
                    using var ob = asort.Znajdz(enc);
                    var zmiany = new List<string>();

                    if (!string.IsNullOrWhiteSpace(p.Nazwa)
                        && nazwa != ((string?)ob.Dane.Nazwa ?? "").Trim())
                    {
                        zmiany.Add($"nazwa: „{ob.Dane.Nazwa}” → „{nazwa}”");
                        if (zapisz) ob.Dane.Nazwa = nazwa;
                    }
                    if (p.Cena is { } cena)
                    {
                        var stara = decimal.Round((decimal)ob.Dane.CenaEwidencyjna, 2);
                        var nowa = decimal.Round(cena, 2);
                        if (stara != nowa)
                        {
                            zmiany.Add($"cena ewid.: {stara:0.00} → {nowa:0.00}");
                            if (zapisz) try { ob.Dane.CenaEwidencyjna = nowa; } catch { }
                        }
                    }
                    if (p.Opis != null)
                    {
                        var stary = (Bezp(() => (string?)ob.Dane.Opis) ?? "").Trim();
                        if (stary != p.Opis.Trim())
                        {
                            zmiany.Add("opis zmieniony");
                            if (zapisz) try { ob.Dane.Opis = p.Opis.Trim(); } catch { }
                        }
                    }

                    UstawVat(ob.Dane, p, stawkiVat, zmiany, zapisz);
                    UstawPolaWlasne(ob.Dane, p, zmiany, zapisz);

                    if (zmiany.Count == 0)
                    {
                        kroki.Add(new Krok("kartoteka", symbol, "bez-zmian", null));
                    }
                    else if (!zapisz)
                    {
                        kroki.Add(new Krok("kartoteka", symbol, "do-zmiany", string.Join("; ", zmiany)));
                    }
                    else if (!ob.Zapisz())
                    {
                        kroki.Add(new Krok("kartoteka", symbol, "blad", Bezp(ob.PodajBledy) ?? "Zapisz() = false"));
                    }
                    else
                    {
                        zmienionych++;
                        kroki.Add(new Krok("kartoteka", symbol, "zmieniona", string.Join("; ", zmiany)));
                    }
                    continue;
                }

                // NIE ISTNIEJE — zakladamy.
                if (!zapisz)
                {
                    kroki.Add(new Krok("kartoteka", symbol, "do-zalozenia",
                        $"{(jestKompletem ? "komplet" : p.Rodzaj ?? "towar")}, jm {p.Jm ?? "szt"}"));
                    // Suchy przebieg: udajemy, ze juz jest, zeby sklady kompletow
                    // nizej nie raportowaly falszywie "brak skladnika".
                    wBazie[symbol] = symbol;
                    continue;
                }

                using (var ob = asort.Utworz())
                {
                    // Szablon MUSI byc zgodny z rodzajem — bez szablonu Komplet
                    // Sfera odmawia pozniej dodania skladnikow (patrz Projekt.cs).
                    ob.WypelnijNaPodstawieSzablonu(jestKompletem
                        ? szablony.DaneDomyslne.Komplet
                        : CzyUsluga(p.Rodzaj) ? szablony.DaneDomyslne.Usluga
                                              : szablony.DaneDomyslne.Towar);
                    ob.Dane.Symbol = symbol;
                    ob.Dane.Nazwa = nazwa;
                    if (!string.IsNullOrWhiteSpace(p.Opis))
                        try { ob.Dane.Opis = p.Opis!.Trim(); } catch { }
                    if (p.Cena is > 0)
                        try { ob.Dane.CenaEwidencyjna = p.Cena.Value; } catch { }
                    var pominiete = new List<string>();
                    UstawVat(ob.Dane, p, stawkiVat, pominiete, true);
                    UstawPolaWlasne(ob.Dane, p, pominiete, true);

                    if (!ob.Zapisz())
                    {
                        kroki.Add(new Krok("kartoteka", symbol, "blad", Bezp(ob.PodajBledy) ?? "Zapisz() = false"));
                        continue;
                    }
                }
                wBazie[symbol] = symbol;
                zalozonych++;
                kroki.Add(new Krok("kartoteka", symbol, "zalozona",
                    $"{(jestKompletem ? "komplet" : p.Rodzaj ?? "towar")}: {nazwa}"));
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok("kartoteka", symbol, "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        // ── 2. SKLADY KOMPLETOW, OD DOLU DRZEWA ──────────────────────────
        foreach (var p in PosortujOdDolu(pozycje))
        {
            var symbol = (p.Symbol ?? "").Trim();
            var skl = p.Skladniki ?? new List<SkladnikPlan>();
            if (skl.Count == 0)
            {
                // Subiekt odrzuca komplet bez skladnikow — zglaszamy jako
                // pominiecie, nie blad (tak samo jak Projekt.cs).
                kroki.Add(new Krok("komplet", symbol, "pominiety-brak-skladnikow", null));
                continue;
            }

            var brakujace = skl.Select(s => (s.Symbol ?? "").Trim())
                               .Where(s => s.Length > 0 && !wBazie.ContainsKey(s))
                               .ToList();
            if (brakujace.Count > 0)
            {
                kroki.Add(new Krok("komplet", symbol, "blad",
                    "brak kartotek skladnikow: " + string.Join(", ", brakujace)));
                continue;
            }

            if (!zapisz)
            {
                kroki.Add(new Krok("komplet", symbol, "do-ustawienia",
                    $"{skl.Count} skladnikow: " + string.Join(", ",
                        skl.Select(s => $"{s.Symbol} x{s.Ilosc:0.##}"))));
                continue;
            }

            try
            {
                var enc = asort.Dane.WyszukajPoSymbolu(wBazie[symbol]);
                if (enc == null)
                {
                    kroki.Add(new Krok("komplet", symbol, "blad", "brak kartoteki kompletu"));
                    continue;
                }
                using var ob = asort.Znajdz(enc);

                // Plan jest PRAWDA: czyscimy stary sklad i wpisujemy podany od
                // nowa. Inaczej ponowny zapis zdublowalby skladniki — dokladnie
                // ten blad, ktory naprawialismy 06.09.2026 (KompletNapraw.cs).
                WyczyscSklad(ob);

                var dodane = 0;
                foreach (var s in skl)
                {
                    var ss = (s.Symbol ?? "").Trim();
                    if (ss.Length == 0) continue;
                    var sEnc = asort.Dane.WyszukajPoSymbolu(wBazie[ss]);
                    if (sEnc == null) continue;
                    ob.Skladniki.Dodaj(sEnc, s.Ilosc <= 0 ? 1m : s.Ilosc);
                    dodane++;
                }

                if (!ob.Zapisz())
                {
                    kroki.Add(new Krok("komplet", symbol, "blad", Bezp(ob.PodajBledy) ?? "Zapisz() = false"));
                    continue;
                }
                skladow++;
                kroki.Add(new Krok("komplet", symbol, "sklad-ustawiony", $"{dodane} skladnikow"));
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok("komplet", symbol, "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(
            new { zapisano = zapisz, zalozonych, zmienionych, skladow, kroki },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    /// Stawki VAT sprzedazy/zakupu. Wartosc w planie to SYMBOL stawki
    /// ("23", "8", "zw") — dopasowany do slownika IStawkiVat. Nieznany symbol
    /// zglaszamy w zmianach zamiast cicho pomijac: uzytkownik ma wiedziec,
    /// ze stawka nie zostala ustawiona.
    static void UstawVat(dynamic dane, PozPlan p, Dictionary<string, dynamic> stawki,
                         List<string> zmiany, bool zapisz)
    {
        void Jedna(string? chciana, string nazwaPola, Func<dynamic> czytaj, Action<dynamic> ustaw)
        {
            var sym = (chciana ?? "").Trim();
            if (sym.Length == 0) return;
            if (!stawki.TryGetValue(sym, out var stawka))
            {
                zmiany.Add($"{nazwaPola}: nie ma stawki „{sym}” w slowniku — pominieto");
                return;
            }
            var obecna = (Bezp(() => (string?)czytaj()?.Symbol) ?? "").Trim();
            if (string.Equals(obecna, sym, StringComparison.OrdinalIgnoreCase)) return;
            zmiany.Add($"{nazwaPola}: „{obecna}” → „{sym}”");
            if (zapisz) try { ustaw(stawka); } catch { }
        }

        Jedna(p.VatSprzedaz, "VAT sprzedazy",
              () => dane.StawkaVatSprzedaz, v => dane.StawkaVatSprzedaz = v);
        Jedna(p.VatZakup, "VAT zakupu",
              () => dane.StawkaVatKupno, v => dane.StawkaVatKupno = v);
    }

    /// Proste pola wlasne PoleWlasne2..8 (PoleWlasne1 jest zajete na Polozenie
    /// magazynowe — patrz MAGAZYN.md). Zapis WPROST na encji:
    /// Asortyment.PolaWlasne.PoleWlasneN — NIE przez UtworzPolaWlasneAdv2Accessor,
    /// ktory obsluguje pola zaawansowane v2, nieobecne w tej bazie.
    static void UstawPolaWlasne(dynamic dane, PozPlan p, List<string> zmiany, bool zapisz)
    {
        if (p.PolaWlasne is null || p.PolaWlasne.Count == 0) return;
        object? pw = null;
        try { pw = dane.PolaWlasne; } catch { }
        if (pw is null)
        {
            zmiany.Add("pola wlasne: kartoteka nie ma obiektu PolaWlasne");
            return;
        }
        foreach (var (pole, wartosc) in p.PolaWlasne)
        {
            var nazwaPola = (pole ?? "").Trim();
            if (nazwaPola.Length == 0) continue;
            // PoleWlasne1 jest zarezerwowane na Polozenie — nie pozwalamy go
            // nadpisac z edytora, zeby nie skasowac danych magazynowych.
            if (nazwaPola.Equals("PoleWlasne1", StringComparison.OrdinalIgnoreCase))
            {
                zmiany.Add("PoleWlasne1 zarezerwowane na Polozenie — pominieto");
                continue;
            }
            var prop = pw.GetType().GetProperty(nazwaPola);
            if (prop is null || !prop.CanWrite)
            {
                zmiany.Add($"brak zapisywalnego pola „{nazwaPola}”");
                continue;
            }
            var stara = (Bezp(() => prop.GetValue(pw) as string) ?? "").Trim();
            var nowa = (wartosc ?? "").Trim();
            if (stara == nowa) continue;
            zmiany.Add($"{nazwaPola}: „{stara}” → „{nowa}”");
            if (zapisz) try { prop.SetValue(pw, nowa); } catch { }
        }
    }

    static bool CzyKomplet(string? rodzaj)
    {
        var r = (rodzaj ?? "").Trim();
        return r.Equals("komplet", StringComparison.OrdinalIgnoreCase)
            || r.Equals("Z", StringComparison.OrdinalIgnoreCase)
            || r.Equals("ZZ", StringComparison.OrdinalIgnoreCase);
    }

    static bool CzyUsluga(string? rodzaj) =>
        (rodzaj ?? "").Trim().Equals("usluga", StringComparison.OrdinalIgnoreCase)
        || (rodzaj ?? "").Trim().Equals("usługa", StringComparison.OrdinalIgnoreCase);

    /// ISkladnikiKompletu nie ma "wyczysc" — jest tylko Usun(symbol) : bool.
    /// Straznik chroni przed petla nieskonczona, gdyby Usun zwracalo true
    /// bez faktycznego usuniecia (ta sama ostroznosc co w Projekt.cs).
    static void WyczyscSklad(dynamic ob)
    {
        try
        {
            var symbole = new List<string>();
            IEnumerable<dynamic> sklad = ob.Dane.SkladnikiKompletu;
            foreach (var s in sklad)
            {
                var sym = (string?)s.Skladnik?.Symbol;
                if (!string.IsNullOrWhiteSpace(sym)) symbole.Add(sym!);
            }
            foreach (var sym in symbole)
            {
                var straznik = 0;
                while (straznik++ < 200 && (bool)ob.Skladniki.Usun(sym)) { }
            }
        }
        catch { /* brak skladu = nie ma czego czyscic */ }
    }

    /// Komplety posortowane OD DOLU drzewa: najpierw te, ktore niczego nie
    /// zawieraja, na koncu najbardziej zagniezdzone. ZZ potrafi zawierac ZZ
    /// (w "2607 Platyn" 23 razy, drzewo na 4 poziomy), wiec samo "Z przed ZZ"
    /// nie wystarcza — liczymy faktyczna glebokosc. Kopia z Projekt.cs.
    static List<PozPlan> PosortujOdDolu(List<PozPlan> pozycje)
    {
        var komplety = pozycje.Where(p => CzyKomplet(p.Rodzaj)).ToList();
        var wg = new Dictionary<string, PozPlan>(StringComparer.OrdinalIgnoreCase);
        foreach (var p in komplety) wg[(p.Symbol ?? "").Trim()] = p;

        var glebokosc = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

        int Licz(PozPlan p, HashSet<string> sciezka)
        {
            var klucz = (p.Symbol ?? "").Trim();
            if (glebokosc.TryGetValue(klucz, out var g)) return g;
            if (!sciezka.Add(klucz)) return 0;          // cykl — przerywamy

            var max = 0;
            foreach (var s in p.Skladniki ?? new List<SkladnikPlan>())
                if (wg.TryGetValue((s.Symbol ?? "").Trim(), out var dziecko))
                    max = Math.Max(max, Licz(dziecko, sciezka) + 1);

            sciezka.Remove(klucz);
            glebokosc[klucz] = max;
            return max;
        }

        foreach (var p in komplety) Licz(p, new HashSet<string>(StringComparer.OrdinalIgnoreCase));
        return komplety.OrderBy(p => glebokosc.TryGetValue((p.Symbol ?? "").Trim(), out var g) ? g : 0)
                       .ThenBy(p => p.Symbol)
                       .ToList();
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record SkladnikPlan(string? Symbol, decimal Ilosc);
    internal record PozPlan(string? Symbol, string? Nazwa, string? Rodzaj, string? Jm,
                            decimal? Cena, string? Opis, List<SkladnikPlan>? Skladniki,
                            string? VatSprzedaz = null, string? VatZakup = null,
                            Dictionary<string, string>? PolaWlasne = null);
    internal record Plan(List<PozPlan>? Pozycje);
    internal record Krok(string Rodzaj, string Symbol, string Status, string? Szczegoly);
}
