// Tryb "zk-poz-usun" — usuwa POJEDYNCZE POZYCJE z ZK projektu. ZAPISUJE.
//
//   NexoRecon.exe zk-poz-usun --plan=plan.json [--out=w.json] [--zapisz]
//
// Bez --zapisz to suchy przebieg: mówi, co by usunął i czego NIE RUSZY.
//
// plan.json:
//   { "projekt": "3500", "symbole": ["2627-100.22Z", "..."] }
//
// Po co: gdy pozycja zmienia dostawcę z realnego na RMPAK ("jednak robimy
// u siebie"), wypada z planu ZK — ale tryb "projekt" jej NIE ZDEJMUJE
// z dokumentu, bo przechodzi wyłącznie po pozycjach planu. Zostawała
// SIEROTA: detal zamówiony u dostawcy i jednocześnie robiony u siebie
// (RMPAK_ZMIANA_DOSTAWCY_ZLOZEN.md).
//
// ⚠️ NIE USUWAMY pozycji, która poszła dalej do ZD. Zamówienie do dostawcy
// jest zobowiązaniem wobec kontrahenta — zdjęcie pozycji z ZK zerwałoby
// powiązanie, a ZD zostałoby bez podstawy. Takie pozycje raportujemy jako
// "realizowana" i user rozstrzyga je sam w Subiekcie.
//
// Powiązanie czytamy przez PozycjeRealizujace (pozycja ZK → pozycje ZD, które
// ją realizują) — odwrotny kierunek tego, co Zapotrzebowanie.DokumentyZk()
// robi dla ZD.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class ZkPozUsun
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }
        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
        var szukane = new HashSet<string>(
            (plan.Symbole ?? new List<string>())
                .Select(s => (s ?? "").Trim().ToUpperInvariant())
                .Where(s => s.Length > 0));
        var kroki = new List<Krok>();
        if (szukane.Count == 0)
        {
            kroki.Add(new Krok("zk", "", "blad", "plan bez symboli"));
            return Wypisz(kroki, null, false, outPath);
        }

        var numerProjektu = (plan.Projekt ?? "").Trim();
        string? zkNumer = null;
        var usuniete = 0;
        var realizowane = 0;

        try
        {
            var zamowienia = sfera.ZamowieniaOdKlientow();

            // ZK projektu rozpoznajemy TĄ SAMĄ metodą co tryb "projekt".
            // Wcześniej stała tu własna kopia dopasowania (Equals na całych
            // Uwagach) — dokładnie to, przed czym ostrzega nagłówek ZkNowe.cs:
            // przy zmianie formatu Uwag (10.09.2026: numer to pierwszy człon,
            // reszta należy do człowieka) kopia przestałaby cokolwiek znajdować,
            // a tryb po cichu mówiłby „nie ma czego usuwać".
            var (dokument, duplikaty) = Projekt.ZnajdzZkProjektu(sfera, numerProjektu);
            if (dokument == null)
            {
                kroki.Add(new Krok("zk", numerProjektu, "brak",
                    "nie znaleziono ZK tego projektu — nie ma czego usuwać"));
                return Wypisz(kroki, null, zapisz, outPath);
            }

            // ⚠️ Nie ruszamy cudzego dokumentu. Numer projektu w Uwagach wpisuje
            // też człowiek zakładający ZK ręcznie, a ten tryb USUWA pozycje.
            if (!Projekt.NaszeZk(dokument))
            {
                kroki.Add(new Krok("zk",
                    Bezp(() => (string?)dokument.NumerWewnetrzny?.PelnaSygnatura) ?? "",
                    "blad",
                    "ma w Uwagach numer tego projektu, ale nie wystawiła go RM_BAZA "
                    + "(brak znacznika w Tytule) — NIE usuwam pozycji z cudzego "
                    + "dokumentu. Popraw go ręcznie w Subiekcie."));
                return Wypisz(kroki, null, zapisz, outPath);
            }

            // Dwa+ ZK na projekt: nie zgadujemy, z którego zdejmować pozycje.
            if (duplikaty.Count > 0)
            {
                var numery = string.Join(", ", new[] { dokument }.Concat(duplikaty)
                    .Select(d => Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "?"));
                kroki.Add(new Krok("zk", numerProjektu, "blad",
                    $"projekt ma {duplikaty.Count + 1} dokumenty ZK ({numery}) — "
                    + "nie zgaduję, z którego zdjąć pozycje. Uporządkuj je w Subiekcie."));
                return Wypisz(kroki, null, zapisz, outPath);
            }

            zkNumer = Bezp(() => (string?)dokument.NumerWewnetrzny?.PelnaSygnatura) ?? "";
            using var ob = zamowienia.Znajdz(dokument);

            // Zbieramy PRZED usuwaniem: modyfikacja kolekcji w trakcie
            // iterowania po niej potrafi pominąć elementy.
            var doUsuniecia = new List<object>();
            foreach (var poz in (System.Collections.IEnumerable)ob.Dane.Pozycje)
            {
                var sym = (Bezp(() => (string?)((dynamic)poz).AsortymentAktualny?.Symbol) ?? "")
                          .Trim().ToUpperInvariant();
                if (sym.Length == 0 || !szukane.Contains(sym)) continue;

                var zd = NumeryZd(poz);
                if (zd.Count > 0)
                {
                    realizowane++;
                    kroki.Add(new Krok("zk-poz", sym, "realizowana",
                        $"poszła dalej na {string.Join(", ", zd)} — NIE USUWAM, "
                        + "rozstrzygnij w Subiekcie"));
                    continue;
                }
                doUsuniecia.Add(poz);
                kroki.Add(new Krok("zk-poz", sym,
                    zapisz ? "do-usuniecia" : "do-usuniecia (suchy)",
                    $"{Ilo(Bezp2(() => (decimal)((dynamic)poz).Ilosc))} szt., bez ZD"));
            }

            foreach (var sym in szukane)
                if (!kroki.Any(k => k.Symbol == sym))
                    kroki.Add(new Krok("zk-poz", sym, "brak-na-zk", "nie ma jej na dokumencie"));

            if (zapisz && doUsuniecia.Count > 0)
            {
                foreach (var poz in doUsuniecia)
                {
                    // Usun() albo — gdy się nie da — wyzerowanie ilości.
                    // Ten sam fallback co przy konsolidacji w Projekt.cs:
                    // pozycja z ilością 0 nie generuje zapotrzebowania.
                    // ⚠️ TYLKO prawdziwe usunięcie. Wyzerowania ilości NIE
                    // używamy jako zamiennika: zero z ZK wraca do bazy projektu
                    // przez `_zapisz_ilosci_z_subiekta` (order_qty = 0), więc
                    // pozycja znika z BOM-u i nie da się już zmienić jej
                    // dostawcy — a chodziło o coś odwrotnego (10.09.2026).
                    //
                    // Sfera nie wystawia `Usun` na pozycjach ZK (ma je tylko
                    // dla dokumentów księgowych i windykacyjnych), więc przy
                    // niepowodzeniu mówimy wprost, że trzeba to zrobić ręcznie.
                    if (Projekt.UsunPozycjePubl(ob, poz)) usuniete++;
                    else
                    {
                        var sym = (Bezp(() => (string?)((dynamic)poz).AsortymentAktualny?.Symbol)
                                   ?? "").Trim();
                        kroki.Add(new Krok("zk-poz", sym, "nie-do-usuniecia",
                            "Sfera nie pozwala usunąć pozycji z ZK — usuń ją ręcznie "
                            + "w Subiekcie. NIE zerujemy ilości: zero wróciłoby do BOM-u."));
                    }
                }
                try { ob.Przelicz(); } catch { }
                if (!ob.Zapisz())
                {
                    kroki.Add(new Krok("zk", zkNumer ?? "", "blad",
                        Bezp(ob.PodajBledy) ?? "Subiekt odrzucił zapis ZK"));
                    usuniete = 0;
                }
                else
                {
                    // READ-BACK: Zapisz()==true NIE ZNACZY, że pozycje zniknęły.
                    // Usun() szuka metody refleksją i po cichu zwraca false, gdy
                    // jej nie znajdzie — most raportował wtedy „usunięto 3 poz.",
                    // a na dokumencie stały dalej wszystkie (10.09.2026).
                    // Czytamy dokument OD NOWA i sprawdzamy, czego naprawdę nie ma.
                    var zostaly = new List<string>();
                    try
                    {
                        foreach (var d2 in sfera.ZamowieniaOdKlientow().Dane.Wszystkie())
                        {
                            var nr2 = Bezp(() => (string?)d2.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                            if (nr2 != zkNumer) continue;
                            foreach (var poz in (System.Collections.IEnumerable)d2.Pozycje)
                            {
                                var sym = (Bezp(() => (string?)((dynamic)poz).AsortymentAktualny?.Symbol)
                                           ?? "").Trim().ToUpperInvariant();
                                var ile = Bezp2(() => (decimal)((dynamic)poz).Ilosc);
                                if (szukane.Contains(sym) && ile > 0) zostaly.Add(sym);
                            }
                            break;
                        }
                    }
                    catch (Exception ex)
                    {
                        kroki.Add(new Krok("zk", zkNumer ?? "", "uwaga",
                            $"nie udało się zweryfikować usunięcia: {ex.Message}"));
                    }

                    if (zostaly.Count > 0)
                    {
                        usuniete -= zostaly.Count;
                        kroki.Add(new Krok("zk", zkNumer ?? "", "blad",
                            $"NIE ZDJĘTO {zostaly.Count} poz.: {string.Join(", ", zostaly)} — "
                            + "ani usunięcie, ani wyzerowanie nie przeszło. Popraw je ręcznie "
                            + "w Subiekcie."));
                    }
                    if (usuniete > 0)
                        kroki.Add(new Krok("zk", zkNumer ?? "", "zapisane",
                            $"zdjęto z zamówienia {usuniete} poz. (potwierdzone odczytem)"
                            + (realizowane > 0 ? $", {realizowane} pominięto (są na ZD)" : "")));
                }
            }
            else if (!zapisz)
            {
                kroki.Add(new Krok("zk", zkNumer ?? "", "suchy",
                    $"usunie {doUsuniecia.Count} poz."
                    + (realizowane > 0 ? $", pominie {realizowane} (są na ZD)" : "")));
            }
        }
        catch (Exception ex)
        {
            kroki.Add(new Krok("zk", numerProjektu, "blad", $"{ex.GetType().Name}: {ex.Message}"));
        }

        return Wypisz(kroki, zkNumer, zapisz && usuniete > 0, outPath);
    }

    /// Numery ZD realizujących tę pozycję ZK. Pusta lista = nikt jej nie
    /// zamówił, więc można ją bezpiecznie zdjąć z dokumentu.
    static List<string> NumeryZd(object poz)
    {
        var out_ = new List<string>();
        try
        {
            if (Zapotrzebowanie.Wlasc(poz, "PozycjeRealizujace")
                is not System.Collections.IEnumerable kol) return out_;
            foreach (var r in kol)
            {
                // PozycjaRealizujaca → Dokument → NumerWewnetrzny
                var pz = Zapotrzebowanie.Wlasc(r, "PozycjaRealizujaca") ?? r;
                var dok = Zapotrzebowanie.Wlasc(pz, "Dokument");
                if (dok == null) continue;
                var nr = Zapotrzebowanie.Wlasc(dok, "NumerWewnetrzny");
                var sygn = nr == null ? null : Zapotrzebowanie.Wlasc(nr, "PelnaSygnatura")?.ToString();
                if (!string.IsNullOrWhiteSpace(sygn) && !out_.Contains(sygn!)) out_.Add(sygn!);
            }
        }
        catch { /* brak powiązania traktujemy jak brak ZD — patrz niżej */ }
        return out_;
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
    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }
    static decimal Bezp2(Func<decimal> f) { try { return f(); } catch { return 0m; } }

    internal record Plan(string? Projekt, List<string>? Symbole);
    internal record Krok(string Rodzaj, string Symbol, string Status, string? Szczegoly);
}
