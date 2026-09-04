// Tryb "zapotrzebowanie" — czego brakuje na otwartych ZK. Tylko odczyt.
//
//   NexoRecon.exe zapotrzebowanie [--out=zapotrzebowanie.json] [konfig.json]
//
// Zwraca to, co Subiekt sam wyliczył: pozycje zamówione przez klienta (czyli
// z naszych ZK projektowych), których jeszcze nie pokryto ani zamówieniem do
// dostawcy, ani wydaniem. To wejście do tworzenia ZD (tryb "zd").
//
// ⚠️ ZapotrzebowanieNaAsortyment() NIE przyjmuje parametrów — liczy zapotrzebowanie
// ze WSZYSTKICH niezrealizowanych ZK naraz, nie da się go zawęzić do jednego
// projektu po stronie Sfery. Dlatego zwracamy `zk` (numery i tytuły dokumentów,
// z których wynika dana potrzeba) i filtrowanie per projekt robi RM_BAZA.
//
// `Dostawca` bywa pusty — to podpowiedź z kartoteki asortymentu, nie obowiązek.
// Uzupełnienie go jest zadaniem człowieka w oknie RM_BAZA.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Zapotrzebowanie
{
    public static int Uruchom(Uchwyt sfera, string? outPath)
    {
        var zam = sfera.ZamowieniaOdKlientow();

        // Lista podmiotów leci razem z zapotrzebowaniem, bo okno i tak jej
        // potrzebuje (wybór dostawcy z listy), a to oszczędza drugie
        // uruchomienie procesu i drugie logowanie do Sfery (~8 s).
        // Powód: nazwy dostawców z RM_BAZA pokrywają się z Subiektem tylko
        // częściowo — pomiar 04.09.2026 na projekcie 2619: 7 z 15 (47 %).
        // Reszta to dopiski („Alufrost domówione"), dwie firmy w jednym polu
        // („DAGAR + RMPAK") albo w ogóle nie-dostawcy („magazyn", „anulowane").
        var podmioty = sfera.Podmioty().Dane.WszystkieFirmy()
            .Select(p => new { p.NazwaSkrocona })
            .ToList()
            .Select(p => (p.NazwaSkrocona ?? "").Trim())
            .Where(n => n.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderBy(n => n, StringComparer.OrdinalIgnoreCase)
            .ToList();

        var pozycje = new List<Poz>();
        foreach (var p in zam.ZapotrzebowanieNaAsortyment())
        {
            // Numery ZK stojące za tą potrzebą — po nich RM_BAZA rozpozna projekt
            // (Uwagi na ZK to numer projektu, patrz SUBIEKT_PROJEKTY_WYDANIA.md).
            var zrodla = new List<Zrodlo>();
            try
            {
                foreach (var poz in p.PozycjeZK ?? Enumerable.Empty<InsERT.Moria.ModelDanych.PozycjaDokumentu>())
                {
                    var d = poz.Dokument;
                    if (d == null) continue;
                    zrodla.Add(new Zrodlo(
                        Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "",
                        Bezp(() => d.Tytul) ?? "",
                        Bezp(() => d.Uwagi) ?? "",
                        poz.Ilosc));
                }
            }
            catch { /* brak powiązań nie unieważnia samej pozycji zapotrzebowania */ }

            // Stan magazynowy — „dostępne" z kroku 3 przepływu
            // (SUBIEKT_PRZEPLYW_OPIS.md). Zapotrzebowanie mówi tylko ile
            // BRAKUJE; żeby pokazać pełny obraz (potrzeba / dostępne / ze stanu
            // / kupić), trzeba dołożyć stan tej kartoteki.
            // „Dostępne" w Subiekcie to stan JUŻ pomniejszony o rezerwacje
            // i dyspozycje — czyli to, co realnie można wziąć. Zwracamy też
            // składniki osobno, bo „mam 63 szt" i „mam 63, ale 60 zarezerwowane"
            // to dwie różne decyzje zakupowe.
            decimal dostepne = 0, zadysponowane = 0, zarezerwowane = 0;
            try
            {
                foreach (var s in p.Asortyment.StanyMagazynowe)
                {
                    dostepne += s.IloscDostepna;
                    zadysponowane += s.IloscZadysponowana;
                    zarezerwowane += s.IloscZarezerwowanaIlosciowo
                                   + s.IloscZarezerwowanaDostawowo;
                }
            }
            catch { /* kartoteka bez ruchu magazynowego */ }

            // Progi zamawiania z kartoteki: StanMinimalny = próg, poniżej
            // którego domawiamy; StanOptymalny = poziom, do którego uzupełniamy
            // (użytkownik zapisuje to jako „10/15"). Definiowane PER MAGAZYN,
            // więc sumujemy — firma ma jeden magazyn towarowy (MAG).
            decimal stanMin = 0, stanOpt = 0;
            try
            {
                foreach (var z in p.Asortyment.StanyWMagazynachZakresy)
                {
                    // StanMinimalny jest zawsze wypełniony (0 = nie pilnujemy),
                    // StanOptymalny bywa pusty — stąd różne traktowanie.
                    stanMin += z.StanMinimalny;
                    stanOpt += z.StanOptymalny.GetValueOrDefault();
                }
            }
            catch { /* progi są opcjonalne — większość kartotek ich nie ma */ }

            pozycje.Add(new Poz(
                Bezp(() => p.Asortyment?.Symbol) ?? "",
                Bezp(() => p.Asortyment?.Nazwa) ?? "",
                p.Ilosc,
                dostepne,
                zadysponowane,
                zarezerwowane,
                stanMin,
                stanOpt,
                // JednostkaMiary tu jest typu JednostkaMiaryAsortymentu, a symbol
                // („szt") siedzi dopiero w jej zagnieżdżonej JednostkaMiary —
                // ta sama ścieżka co w Stan.cs (p.JednostkaMiaryAs.JednostkaMiary.Symbol).
                Bezp(() => p.JednostkaMiary?.JednostkaMiary?.Symbol) ?? "",
                Bezp(() => p.Dostawca?.NazwaSkrocona),
                zrodla));
        }

        // Pozycje JUŻ ZAMÓWIONE — znikają z zapotrzebowania (bo są pokryte),
        // więc bez tego user nie widzi, co się z nimi stało. Bierzemy ZD
        // „do realizacji": zamówione u dostawcy, jeszcze nieprzyjęte.
        var zamowione = new List<PozZd>();
        try
        {
            foreach (var d in sfera.ZamowieniaDoDostawcow().Dane.Wszystkie()
                                   .OrderByDescending(d => d.DataWprowadzenia)
                                   .Take(200).ToList())
            {
                var numer = Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                var dostawca = Bezp(() => d.Podmiot?.NazwaSkrocona) ?? "";
                // Data WYSTAWIENIA, nie wprowadzenia — to ją widać w Subiekcie
                // i po niej filtrują się listy dokumentów. Starsze ZD z RM_BAZA
                // mogą jej nie mieć (błąd naprawiony 04.09.2026) — wtedy
                // pokazujemy datę wprowadzenia, żeby kolumna nie była pusta.
                // ToString bez formatu, bo typ pola różni się między wersjami
                // SDK (DateTime / DateOnly); tniemy do 10 znaków = yyyy-MM-dd.
                var data = Bezp(() =>
                {
                    var w = d.DataWydaniaWystawienia;
                    var s = w == default
                        ? d.DataWprowadzenia.ToString("yyyy-MM-dd",
                            System.Globalization.CultureInfo.InvariantCulture)
                        : Convert.ToDateTime(w).ToString("yyyy-MM-dd",
                            System.Globalization.CultureInfo.InvariantCulture);
                    return s;
                }) ?? "";
                var status = Bezp(() => d.StatusDokumentu?.Nazwa) ?? "";
                try
                {
                    foreach (var poz in d.Pozycje)
                    {
                        var sym = Bezp(() => poz.AsortymentAktualny?.Symbol);
                        if (string.IsNullOrWhiteSpace(sym)) continue;
                        zamowione.Add(new PozZd(sym!.Trim(),
                            Bezp(() => poz.AsortymentAktualny?.Nazwa) ?? "",
                            poz.Ilosc, numer, dostawca, data, status));
                    }
                }
                catch { /* dokument bez czytelnych pozycji — pomijamy */ }
            }
        }
        catch { /* brak dostępu do ZD nie może wywalić całego odczytu */ }

        var json = JsonSerializer.Serialize(new { pozycje, podmioty, zamowione },
            new JsonSerializerOptions
            {
                WriteIndented = false,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });

        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record Zrodlo(string Numer, string Tytul, string Uwagi, decimal Ilosc);
    internal record PozZd(string Symbol, string Nazwa, decimal Ilosc, string Numer,
                          string Dostawca, string Data, string Status);
    internal record Poz(string Symbol, string Nazwa, decimal Ilosc,
                        decimal Dostepne, decimal Zadysponowane, decimal Zarezerwowane,
                        decimal StanMinimalny, decimal StanOptymalny,
                        string JednostkaMiary, string? Dostawca, List<Zrodlo> Zk);
}
