// Tryb "faktury" — rozpoznanie faktur zakupu (FZ). Tylko odczyt.
//
//   NexoRecon.exe faktury [--limit=60] [--out=w.json]
//
// Pytanie, na które odpowiada (04.09.2026): jak dopasować pozycje z faktury
// KSeF do zamówień? Zanim cokolwiek napiszemy, trzeba wiedzieć:
//   * ile FZ ma numer KSeF (czyli przyszło elektronicznie),
//   * czy pozycje mają dopasowany asortyment, czy są „luźnym tekstem",
//   * czy widać powiązanie z ZD/PZ,
//   * jak wyglądają symbole i nazwy na pozycjach — czy da się je dopasować.

using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Faktury
{
    public static int Uruchom(Uchwyt sfera, int limit, string? outPath)
    {
        var wynik = new List<Fak>();

        // Encje asortymentu na pozycjach FZ przychodza jako Detached — odczyt
        // p.AsortymentAktualny.Symbol daje wtedy pustke, mimo ze Id jest
        // wypelnione. Dlatego budujemy mape Id -> symbol jednym przelotem.
        var wgId = new Dictionary<int, (string Symbol, string Nazwa)>();
        try
        {
            foreach (var a in sfera.Asortymenty().Dane.Wszystkie()
                                   .Select(a => new { a.Id, a.Symbol, a.Nazwa }).ToList())
                wgId[a.Id] = ((a.Symbol ?? "").Trim(), (a.Nazwa ?? "").Trim());
        }
        catch { }

        // Jednorazowa diagnostyka: jakie pola ma DokumentDZ i PozycjaDokumentu.
        // Dokumentacja CHM indeksuje tylko czesc, wiec zgadywanie nazw kosztowalo
        // juz kilka nieudanych kompilacji.
        try
        {
            var pierwszy = sfera.DokumentyZakupu().Dane.Wszystkie().Take(1).ToList().FirstOrDefault();
            if (pierwszy != null)
            {
                var pola = pierwszy.GetType().GetProperties()
                    .Where(x => x.PropertyType == typeof(string))
                    .Select(x => x.Name).OrderBy(x => x).ToList();
                Console.WriteLine("POLA TEKSTOWE DokumentDZ: " + string.Join(", ", pola));
                try
                {
                    var poz = pierwszy.Pozycje.Take(1).ToList().FirstOrDefault();
                    if (poz != null)
                    {
                        var t = poz.GetType();
                        Console.WriteLine("TYP POZYCJI: " + t.Name);
                        foreach (var pi in t.GetProperties().OrderBy(x => x.Name))
                        {
                            if (!pi.Name.Contains("Asort", StringComparison.OrdinalIgnoreCase)
                                && !pi.Name.Contains("Nazw", StringComparison.OrdinalIgnoreCase)
                                && !pi.Name.Contains("Symbol", StringComparison.OrdinalIgnoreCase)) continue;
                            string v;
                            try { v = pi.GetValue(poz)?.ToString() ?? "(null)"; } catch (Exception e) { v = "!" + e.GetType().Name; }
                            Console.WriteLine($"   {pi.Name,-34} = {(v.Length > 60 ? v[..60] : v)}");
                        }
                    }
                }
                catch { }
            }
        }
        catch (Exception ex) { Console.WriteLine("diag: " + ex.Message); }

        try
        {
            foreach (var d in sfera.DokumentyZakupu().Dane.Wszystkie()
                                   .OrderByDescending(x => x.DataWprowadzenia)
                                   .Take(limit).ToList())
            {
                var pozycje = new List<PozFak>();
                try
                {
                    foreach (var p in d.Pozycje)
                    {
                        // AsortymentAktualny puste = pozycja NIE dopasowana do
                        // kartoteki (weszła jako tekst). To kluczowa liczba:
                        // mówi, ile roboty zostaje człowiekowi przy imporcie.
                        // Symbol z mapy po Id — patrz komentarz wyzej.
                        var id = 0;
                        try { id = p.AsortymentAktualnyId ?? 0; } catch { }
                        // Gdy "aktualny" jest pusty, probujemy "wybranego" —
                        // na FZ z e-Faktury czesc pozycji ma wypelnione tylko to.
                        if (id == 0) { try { id = p.AsortymentWybranyId; } catch { } }
                        wgId.TryGetValue(id, out var kart);
                        decimal cena = 0;
                        try { cena = p.Cena.NettoPoRabacie; } catch { }
                        // ⚠️ Pozycje BEZ kartoteki (uslugi, koszty transportu)
                        // maja id = 0, wiec symbol i nazwa kartoteki sa puste,
                        // a `Opis` bywa niewypelniony — w oknie zostawala sama
                        // cena i nie dalo sie poznac, co to za pozycja
                        // (zgloszone 18.09.2026). Nazwe skladamy z tego, co jest.
                        var opis = Bezp(() => p.Opis) ?? "";
                        var nazwaNaDok = opis.Length > 0 ? opis
                                       : (kart.Nazwa ?? "").Length > 0 ? kart.Nazwa
                                       : Bezp(() => p.AsortymentWybrany?.Nazwa) ?? "";
                        // Uslugi kosztowe e-Faktury sa oznaczone osobna encja —
                        // gdy nie ma ZADNEJ nazwy, przynajmniej nazwijmy rodzaj.
                        if (nazwaNaDok.Length == 0)
                        {
                            var uslugaKosztowa = Bezp(() =>
                                p.DanePozycjiDokumentuElektronicznego?.UslugaKosztowa == true
                                    ? "(usługa kosztowa)" : null);
                            nazwaNaDok = uslugaKosztowa ?? "(pozycja bez kartoteki)";
                        }
                        // ⚠️ `UJ` (usluga jednorazowa) — tak Subiekt oznacza pozycje
                        // WPISANA WPROST NA DOKUMENT, bez kartoteki. To NIE jest
                        // rodzaj kartoteki: kartoteka zna tylko Towar/Komplet/Usluga,
                        // a SDK ma osobny blad walidacji na probe polaczenia
                        // jednorazowej z kartotekowa. Czytamy to Z POZYCJI DOKUMENTU,
                        // bo tylko tam ta informacja istnieje (18.09.2026).
                        // `RodzajAsortymentu` NA POZYCJI mowi, czym ta linia jest
                        // NA DOKUMENCIE — „Towar" / „Usługa". To odczyt ze stanu
                        // Subiekta, nie zgadywanie po nazwie (18.09.2026).
                        var rodzajPoz = Bezp(() => p.RodzajAsortymentu?.Nazwa) ?? "";
                        // ⛔ `RodzajAsortymentu` NIE mowi, czym pozycja jest —
                        // mowi, czy ma podpieta KARTOTEKE. Zmierzone na 536
                        // pozycjach: „Towar" = ma symbol 277/277, „Usługa" =
                        // nie ma symbolu 249/259. Zwykle towary bez kartoteki
                        // („Worki na smieci") wychodzily jako usluga.
                        //
                        // Dlatego NIE wyprowadzamy stad UJ. Oddajemy surowy
                        // rodzaj (do diagnostyki) i sam fakt braku kartoteki;
                        // co z tym zrobic, rozstrzyga okno albo czlowiek.
                        var bezKartoteki = id == 0;

                        decimal wartosc = 0;
                        // `Wartosc` na pozycji to obiekt (jak `Cena`) — bierzemy
                        // netto PO rabacie, spojnie z cena wyzej.
                        try { wartosc = decimal.Round(p.Wartosc.NettoPoRabacie, 2); } catch { }
                        pozycje.Add(new PozFak(
                            kart.Symbol ?? "",
                            kart.Nazwa ?? "",
                            nazwaNaDok,
                            p.Ilosc,
                            decimal.Round(cena, 2),
                            // JednostkaMiaryAs to JednostkaMiaryAsortymentu —
                            // wlasciwa nazwa siedzi w zagniezdzonym JednostkaMiary.
                            Bezp(() => p.JednostkaMiaryAs?.JednostkaMiary?.Symbol)
                                ?? Bezp(() => p.JednostkaMiaryAs?.JednostkaMiary?.Nazwa) ?? "",
                            wartosc,
                            rodzajPoz,
                            bezKartoteki));
                    }
                }
                catch { }

                wynik.Add(new Fak(
                    Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "",
                    Bezp(() => d.NumerZewnetrzny) ?? "",
                    Data(d),
                    Bezp(() => d.Podmiot?.NazwaSkrocona) ?? "",
                    // ⚠️ NIP jest KLUCZEM kontrahenta w oknie faktur: bez niego
                    // „Kontrahent w Subiekcie" zawsze pokazuje BRAK i zapis
                    // powiazan symboli jest zablokowany (18.09.2026).
                    Bezp(() => d.Podmiot?.NIP) ?? "",
                    Bezp(() => d.StatusDokumentu?.Nazwa) ?? "",
                    // Numery zamowien, ktore ta faktura realizuje — Subiekt trzyma
                    // to powiazanie SAM. To odpowiedz na pytanie „jak dopasowac
                    // fakture do ZD": nie trzeba parsowac, wystarczy odczytac.
                    Bezp(() => d.NumeryDokumentowRealizowanych) ?? "",
                    Bezp(() => d.Uwagi) ?? "",
                    pozycje.Count,
                    pozycje.Count(p => p.Symbol.Length > 0),
                    pozycje,
                    // Kwota faktury — w oknie kolumna "Netto" pokazywala 0,00
                    // dla KAZDEJ FZ, bo rekord w ogole jej nie niosl.
                    // ⚠️ `Wartosc` to decimal ("kwota do zaplaty"), NIE obiekt
                    // z .Netto/.Brutto — netto skladamy z towarow i uslug.
                    Kwota(() => d.WartoscTowarowNetto + d.WartoscUslugNetto),
                    Kwota(() => d.Wartosc.BruttoPoRabacie),
                    // Numer KSeF jest WPROST na dokumencie — `NumerKSeFDokumentu`
                    // (klasa bazowa `Dokument`, nie `DokumentZakupu`). Bez niego
                    // nie da sie zestawic FZ z archiwum FV_KSEF.
                    Bezp(() => d.NumerKSeFDokumentu?.Numer) ?? ""));
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine("Blad odczytu FZ: " + ex.Message);
        }

        var json = JsonSerializer.Serialize(new { faktury = wynik },
            new JsonSerializerOptions
            {
                WriteIndented = false,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    static string Data(Dokument d) => Bezp(() =>
    {
        var w = d.DataWydaniaWystawienia;
        var dt = w == default ? d.DataWprowadzenia : Convert.ToDateTime(w);
        return dt.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    }) ?? "";

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    static decimal Kwota(Func<decimal> f) { try { return decimal.Round(f(), 2); } catch { return 0; } }

    internal record PozFak(string Symbol, string NazwaKartoteki, string NazwaNaDokumencie,
                           decimal Ilosc, decimal Cena, string Jm, decimal Wartosc,
                           string RodzajPozycji, bool BezKartoteki);

    // ⚠️ `NumeryRealizowanych` to NIE numer KSeF — to numery ZAMOWIEN (ZD),
    // ktore ta faktura realizuje. Pole nazywalo sie kiedys `NumerKSeF` i ta
    // nazwa kosztowala pol dnia szukania: filtr po niej pokazywal 3 faktury
    // ze 120 (18.09.2026). Prawdziwy numer KSeF jest w `NumerKSeF` nizej.
    internal record Fak(string Numer, string NumerOryginalny, string Data, string Podmiot,
                        string Nip, string Status, string NumeryRealizowanych, string Uwagi,
                        int Pozycji, int Dopasowanych, List<PozFak> Pozycje,
                        decimal WartoscNetto, decimal WartoscBrutto, string NumerKSeF);
}
