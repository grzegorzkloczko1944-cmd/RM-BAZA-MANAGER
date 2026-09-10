// Tryb "zk-nowe" — tworzy NOWE zamówienie od klienta z podanych pozycji. ZAPISUJE.
//
//   NexoRecon.exe zk-nowe --plan=zk.json [--out=wynik.json] [--zapisz]
//
// Bez --zapisz to suchy przebieg: mówi, co powstanie, i NIC nie zapisuje.
//
// plan.json:
//   { "projekt": "2741", "podmiot": "ABC Sp. z o.o.", "uwagi": "pilne, do piatku",
//     "termin": "2026-09-30",
//     "pozycje": [ {"symbol":"2741-000", "ilosc":1, "cena":120000} ] }
//
// Czym różni się od trybu "projekt"
// ─────────────────────────────────
// Tryb "projekt" robi CAŁY import BOM-u: zakłada kartoteki, buduje komplety
// Z/ZZ i dopiero na końcu ZK — i to on obsługuje DOPISYWANIE do istniejącego
// zamówienia. Tutaj chodzi o coś węższego: wystawić nowe ZK z pozycji, które
// user zebrał ręcznie w Edytorze kartotek. Kartoteki już istnieją (formularz
// to sprawdza), kompletów nie ruszamy.
//
// ⚠️ JEDEN PROJEKT = JEDNO ZK
// Jeśli dla podanego numeru projektu ZK już istnieje, tryb ODMAWIA utworzenia
// drugiego — decyzja użytkownika z 10.09.2026, spójna z regułą, którą
// Projekt.cs egzekwuje od 04.09. Dwa ZK na jeden projekt rozbijają
// zapotrzebowanie na dwa dokumenty, więc ZD przestaje widzieć całość, a tryby
// "projekt" i "zk-ilosci" wstrzymują się przy duplikatach. Dopisywanie pozycji
// do istniejącego ZK robi się w arkuszu RM_BAZA (tryb "projekt"), nie tutaj.
//
// Wyszukiwanie istniejącego ZK idzie przez Projekt.ZnajdzZkProjektu — TĘ SAMĄ
// metodę, której używa zapis BOM-u. Dzięki temu oba tryby zawsze mówią o tym
// samym dokumencie; własna kopia dopasowania rozjechałaby się przy pierwszej
// zmianie formatu Uwag.

using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class ZkNowe
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }

        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
        var pozycje = plan.Pozycje ?? new List<PozPlan>();
        var kroki = new List<Krok>();
        string? numer = null;

        if (pozycje.Count == 0)
        {
            kroki.Add(new Krok("zk", "", "blad", "plan bez pozycji"));
            return Wynik(outPath, zapisz, null, kroki, false);
        }

        // ── 1. CZY PROJEKT MA JUŻ ZK ────────────────────────────────────
        var projekt = (plan.Projekt ?? "").Trim();
        if (projekt.Length > 0)
        {
            var (istniejace, duplikaty) = Projekt.ZnajdzZkProjektu(sfera, projekt);
            if (istniejace != null)
            {
                var numery = string.Join(", ", new[] { istniejace }.Concat(duplikaty)
                    .Select(d => (Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "?")));

                // Blokada obowiazuje TAKZE dla dokumentu wystawionego recznie:
                // drugie ZK rozbija zapotrzebowanie niezaleznie od tego, kto
                // zalozyl pierwsze. Ale rada musi byc inna — przy cudzym ZK
                // arkusz tez odmowi zapisu, wiec odsylanie tam wprowadzaloby
                // w blad (patrz Projekt.cs, gałąź „nie wystawiła go RM_BAZA").
                var rada = Projekt.NaszeZk(istniejace)
                    ? "Pozycje dopisz przez arkusz RM_BAZA (zapis projektu do Subiekta)."
                    : "UWAGA: tego ZK nie wystawiła RM_BAZA (brak znacznika w Tytule) — "
                      + "sprawdź w Subiekcie, czy to na pewno zamówienie tego projektu. "
                      + "Jeśli tak, wpisz w jego Tytuł „" + Znacznik.Tytul(projekt)
                      + "”; jeśli nie — popraw jego Uwagi albo użyj innego numeru.";

                kroki.Add(new Krok("zk", projekt, "blad",
                    $"projekt {projekt} ma już ZK ({numery}) — drugiego nie zakładamy. "
                    + rada));
                return Wynik(outPath, zapisz, null, kroki, false);
            }
        }

        // ── 2. PODMIOT ──────────────────────────────────────────────────
        var podm = Projekt.ZnajdzPodmiotPubl(sfera, plan.Podmiot);
        if (podm == null)
        {
            kroki.Add(new Krok("zk", projekt, "blad",
                $"nie znaleziono klienta: „{plan.Podmiot}”"));
            return Wynik(outPath, zapisz, null, kroki, false);
        }

        // ── 3. KARTOTEKI ────────────────────────────────────────────────
        var asort = sfera.Asortymenty();
        var brakujace = new List<string>();
        foreach (var p in pozycje)
        {
            var symbol = (p.Symbol ?? "").Trim();
            if (symbol.Length == 0) continue;
            if (asort.Dane.WyszukajPoSymbolu(symbol) == null)
            {
                brakujace.Add(symbol);
                kroki.Add(new Krok("pozycja", symbol, "blad", "brak kartoteki w Subiekcie"));
            }
            else
            {
                kroki.Add(new Krok("pozycja", symbol,
                    zapisz ? "do-dodania" : "do-dodania (suchy)",
                    $"{p.Ilosc:0.##}" + (p.Cena is { } c ? $" × {c:0.00}" : "")));
            }
        }
        if (brakujace.Count > 0)
        {
            kroki.Add(new Krok("zk", projekt, "blad",
                $"{brakujace.Count} pozycji bez kartoteki — załóż je przed wystawieniem ZK"));
            return Wynik(outPath, zapisz, null, kroki, false);
        }

        if (!zapisz)
        {
            kroki.Add(new Krok("zk", projekt, "do-utworzenia",
                $"klient: {Bezp(() => podm.NazwaSkrocona)}, pozycji: {pozycje.Count}"));
            return Wynik(outPath, zapisz, null, kroki, true);
        }

        // ── 4. ZAPIS ────────────────────────────────────────────────────
        try
        {
            var zam = sfera.ZamowieniaOdKlientow();
            using var ob = zam.UtworzZamowienieOdKlienta();
            ob.Dane.Podmiot = podm;
            // Uwagi: numer projektu z przodu, za nim swobodne uwagi z formularza
            // — to pole się DRUKUJE. Tytuł: znacznik RM_BAZA, po którym poznajemy
            // własne dokumenty. Patrz Znacznik.cs.
            ob.Dane.Uwagi = Znacznik.Uwagi(projekt, plan.Uwagi);
            ob.Dane.Tytul = Znacznik.Tytul(projekt);

            // Bez daty wystawienia dokument istnieje, ale WYPADA Z LIST
            // w Subiekcie — ta sama pułapka co przy ZD i RW. Pole nazywa się
            // DataWydaniaWystawienia i siedzi na klasie bazowej Dokument
            // (DokumentZK ma z dat tylko DataSprzedazy).
            try
            {
                if ((DateTime)ob.Dane.DataWydaniaWystawienia == default(DateTime))
                    ob.Dane.DataWydaniaWystawienia = DateTime.Today;
            }
            catch { }

            if (!string.IsNullOrWhiteSpace(plan.Termin)
                && DateTime.TryParse(plan.Termin, CultureInfo.InvariantCulture,
                                     DateTimeStyles.None, out var termin))
            {
                try { ob.Dane.TerminRealizacji = termin; }
                catch
                {
                    kroki.Add(new Krok("zk", projekt, "uwaga",
                        "nie udało się ustawić terminu — dokument powstał bez niego"));
                }
            }

            var dodane = 0;
            foreach (var p in pozycje)
            {
                var symbol = (p.Symbol ?? "").Trim();
                if (symbol.Length == 0) continue;
                var enc = asort.Dane.WyszukajPoSymbolu(symbol);
                if (enc == null) continue;
                var poz = ob.Pozycje.Dodaj(enc.Symbol, p.Ilosc <= 0 ? 1m : p.Ilosc);
                if (p.Cena is { } cena && cena > 0)
                    UstawCenePozycji(poz, cena, symbol, kroki);
                dodane++;
            }

            if (!ob.Zapisz())
            {
                kroki.Add(new Krok("zk", projekt, "blad",
                    BledyDokumentu((object)ob) ?? "Subiekt odrzucił zapis ZK"));
                return Wynik(outPath, zapisz, null, kroki, false);
            }
            numer = Bezp(() => ob.Dane.NumerWewnetrzny?.PelnaSygnatura);
            kroki.Add(new Krok("zk", projekt, "utworzone",
                $"{numer} — {dodane} pozycji, klient {Bezp(() => podm.NazwaSkrocona)}"));
        }
        catch (Exception ex)
        {
            kroki.Add(new Krok("zk", projekt, "blad", $"{ex.GetType().Name}: {ex.Message}"));
            return Wynik(outPath, zapisz, null, kroki, false);
        }

        return Wynik(outPath, zapisz, numer, kroki, true);
    }

    /// <summary>
    /// Cena pozycji ZK. `PozycjaDokumentu.Cena` to OBIEKT (InsERT.Moria.ModelDanych.Cena),
    /// nie liczba — ta sama pułapka co w Pw.cs (ustalone diagnostyką 09.09.2026).
    /// Brak ceny NIE jest błędem: ZK bez cen jest poprawne, cenę i tak ustala
    /// się przy fakturze.
    /// </summary>
    static void UstawCenePozycji(object poz, decimal cena, string symbol, List<Krok> kroki)
    {
        try
        {
            var obCena = ((dynamic)poz).Cena;
            try { obCena.Netto = cena; return; } catch { }
            try { obCena.NettoPoRabacie = cena; return; } catch { }
        }
        catch { }
        kroki.Add(new Krok("pozycja", symbol, "uwaga",
            $"nie udało się ustawić ceny {cena:0.00} — pozycja bez ceny"));
    }

    static int Wynik(string? outPath, bool zapisano, string? numer, List<Krok> kroki, bool ok)
    {
        var json = JsonSerializer.Serialize(new { zapisano, ok, numer, kroki },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        // Zawsze 0: odmowa (istniejące ZK, brak kartotek) to RAPORT z powodem,
        // nie awaria mostu — kod != 0 rzuca BridgeError i user nie widzi,
        // CO zablokowało zapis. Decyzję niesie pole "ok".
        return 0;
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }
    static string? Bezp(Func<object?> f)
    {
        try { return f()?.ToString(); } catch { return null; }
    }

    /// Błędy walidacji dokumentu — o ile ten typ je udostępnia (wzorem Rw.cs).
    static string? BledyDokumentu(object? bo)
    {
        if (bo is null) return null;
        try
        {
            var met = bo.GetType().GetMethod("PodajBledy", Type.EmptyTypes);
            var tekst = met?.Invoke(bo, null) as string;
            return string.IsNullOrWhiteSpace(tekst) ? null : tekst;
        }
        catch { return null; }
    }

    internal record PozPlan(string? Symbol, decimal Ilosc, decimal? Cena = null);
    // Uwagi — to, co user wpisal w polu „Uwagi" formularza. Numer projektu
    // dochodzi osobno (Projekt) i most sklada oba: numer w pierwszym wierszu,
    // uwagi pod nim. Pole Tytul dokumentu niesie znacznik RM_BAZA i NIE
    // pochodzi z planu — patrz Znacznik.cs.
    internal record Plan(string? Projekt, string? Podmiot, string? Uwagi,
                         string? Termin, List<PozPlan>? Pozycje);
    internal record Krok(string Rodzaj, string Symbol, string Status, string? Szczegoly);
}
