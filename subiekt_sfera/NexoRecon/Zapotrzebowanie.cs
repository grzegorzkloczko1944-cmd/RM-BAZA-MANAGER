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
// projektu po stronie Sfery.
//
// To ona jest podłogą czasową tego trybu: pomiar 06.09.2026 (721 pozycji)
// dał 3,3 s na samo jej wywołanie z 3,7 s całości — reszta to słownik stanów
// (90 ms), pętla po pozycjach (242 ms) i ZD (93 ms). Jest to gotowa metoda
// SDK InsERT-a, nie nasze zapytanie, więc projekcje tu nic nie dadzą.
// Gdyby ten tryb miał kiedyś zejść niżej, jedyna droga to policzyć
// zapotrzebowanie samodzielnie z pozycji ZK — czyli powtórzyć logikę
// Subiekta, z ryzykiem, że wyjdą inne liczby niż w programie. Dlatego zwracamy `zk` (numery i tytuły dokumentów,
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

        // ⚠️ STANY I PROGI JEDNYM ZAPYTANIEM, NIE PER POZYCJA.
        // Nawigacja p.Asortyment.StanyMagazynowe / .StanyWMagazynachZakresy
        // wewnatrz petli to osobne zapytanie na kazda z ~720 pozycji —
        // 3,5 s na caly tryb (06.09.2026). Jedna projekcja po kartotekach
        // daje te same liczby w ~0,2 s; ten sam wzorzec co w Magazyn.cs.
        //
        // Klucz to SYMBOL, nie Id: Poz i tak identyfikuje kartoteke symbolem,
        // a symbol jest w Subiekcie unikalny.
        var stanySlownik = new Dictionary<string, decimal[]>(StringComparer.OrdinalIgnoreCase);
        try
        {
            foreach (dynamic a in (IEnumerable<dynamic>)sfera.Asortymenty().Dane.Wszystkie()
                .Select(x => new
                {
                    x.Symbol,
                    Stany = x.StanyMagazynowe.Select(st => new
                    {
                        st.IloscDostepna,
                        st.IloscZadysponowana,
                        st.IloscZarezerwowanaIlosciowo,
                        st.IloscZarezerwowanaDostawowo,
                    }),
                    Zakresy = x.StanyWMagazynachZakresy.Select(z => new
                    {
                        z.StanMinimalny,
                        z.StanOptymalny,
                    }),
                })
                .ToList())
            {
                var sym = ((string?)a.Symbol ?? "").Trim();
                if (sym.Length == 0) continue;
                // [dostepne, zadysponowane, zarezerwowane, min, opt]
                var w = new decimal[5];
                foreach (dynamic st in (IEnumerable<dynamic>)a.Stany)
                {
                    w[0] += (decimal)st.IloscDostepna;
                    w[1] += (decimal)st.IloscZadysponowana;
                    w[2] += (decimal)st.IloscZarezerwowanaIlosciowo
                          + (decimal)st.IloscZarezerwowanaDostawowo;
                }
                foreach (dynamic z in (IEnumerable<dynamic>)a.Zakresy)
                {
                    // StanMinimalny jest zawsze wypelniony (0 = nie pilnujemy),
                    // StanOptymalny bywa pusty — stad rozne traktowanie.
                    w[3] += (decimal)z.StanMinimalny;
                    w[4] += (decimal)(z.StanOptymalny ?? 0m);
                }
                stanySlownik[sym] = w;
            }
        }
        catch { /* bez stanow tryb dziala dalej, tyle ze z zerami */ }

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
            //
            // Progi zamawiania: StanMinimalny = próg, poniżej którego
            // domawiamy; StanOptymalny = poziom, do którego uzupełniamy
            // (użytkownik zapisuje to jako „10/15"). Jedno i drugie policzone
            // wyżej, hurtem — patrz stanySlownik.
            var symbol = (Bezp(() => p.Asortyment?.Symbol) ?? "").Trim();
            decimal dostepne = 0, zadysponowane = 0, zarezerwowane = 0;
            decimal stanMin = 0, stanOpt = 0;
            if (symbol.Length > 0 && stanySlownik.TryGetValue(symbol, out var w))
            {
                dostepne = w[0];
                zadysponowane = w[1];
                zarezerwowane = w[2];
                stanMin = w[3];
                stanOpt = w[4];
            }

            pozycje.Add(new Poz(
                symbol,
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
            // ⚠️ PROJEKCJA, NIE NAWIGACJA W PĘTLI — jak w Dokumenty.cs.
            // AsortymentAktualny per pozycja to osobne zapytanie na każdą
            // z ~1000 pozycji tych 200 ZD. Pozycję trzymamy też jako encję
            // (Pozycja), bo NumerZk/ProjektZk schodzą po powiązaniach ZD→ZK
            // refleksją i potrzebują żywego obiektu.
            foreach (var d in sfera.ZamowieniaDoDostawcow().Dane.Wszystkie()
                                   .OrderByDescending(d => d.DataWprowadzenia)
                                   .Take(200)
                                   .Select(d => new
                                   {
                                       Numer = d.NumerWewnetrzny.PelnaSygnatura,
                                       d.DataWydaniaWystawienia,
                                       d.DataWprowadzenia,
                                       Podmiot = d.Podmiot.NazwaSkrocona,
                                       Status = d.StatusDokumentu.Nazwa,
                                       Pozycje = d.Pozycje.Select(poz => new
                                       {
                                           Symbol = poz.AsortymentAktualny.Symbol,
                                           Nazwa = poz.AsortymentAktualny.Nazwa,
                                           poz.Ilosc,
                                           Pozycja = poz,
                                       }),
                                   })
                                   .ToList())
            {
                var numer = d.Numer ?? "";
                var dostawca = d.Podmiot ?? "";
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
                var status = d.Status ?? "";
                try
                {
                    foreach (var poz in d.Pozycje)
                    {
                        var sym = poz.Symbol;
                        if (string.IsNullOrWhiteSpace(sym)) continue;
                        zamowione.Add(new PozZd(sym!.Trim(),
                            poz.Nazwa ?? "",
                            poz.Ilosc, numer, dostawca, data, status,
                            NumerZk(poz.Pozycja), ProjektZk(poz.Pozycja)));
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
    /// Numer ZK, który ta pozycja ZD realizuje.
    ///
    /// Po zamówieniu pozycja znika z zapotrzebowania i wiersz odbudowujemy
    /// z danych ZD — a tam numeru ZK nie było, więc kolumna ZK robiła się
    /// pusta, choć powiązanie w Subiekcie istnieje (zgłoszone 05.09.2026:
    /// „dlaczego po utworzeniu ZD znika mi ZK z widoku").
    ///
    /// Droga (ustalona refleksją): PozycjeRealizowane -> PozycjaRealizowana
    /// -> Dokument -> NumerWewnetrzny.PelnaSygnatura. Jedna pozycja ZD może
    /// realizować kilka pozycji ZK, więc zbieramy unikalne numery.
    static string NumerZk(object poz)
    {
        var numery = new List<string>();
        foreach (var dok in DokumentyZk(poz))
        {
            var num = Wlasc(dok, "NumerWewnetrzny");
            var syg = num == null ? null : Wlasc(num, "PelnaSygnatura")?.ToString();
            if (!string.IsNullOrWhiteSpace(syg) && !numery.Contains(syg!))
                numery.Add(syg!);
        }
        return string.Join(", ", numery);
    }

    ///
    /// Numer PROJEKTU pozycji już zamówionej — z Uwag na ZK, którą ta pozycja
    /// realizuje (RM_BAZA wpisuje tam numer projektu przy zakładaniu ZK).
    ///
    /// Bez tego okno zamówień brało projekt z BOM-u po symbolu, a ten sam
    /// symbol bywa w kilku BOM-ach (kopia testowa 3000 ma rysunki Feniksa
    /// 2632) — „Zamówiono" z wysyłki ZD trafiało do 3000 zamiast do 2632
    /// (zgłoszone 05.09.2026). ZK wie, dla jakiego projektu powstała.
    ///
    internal static string ProjektZk(object poz)
    {
        var projekty = new List<string>();
        foreach (var dok in DokumentyZk(poz))
        {
            var u = Wlasc(dok, "Uwagi")?.ToString()?.Trim();
            if (!string.IsNullOrWhiteSpace(u) && !projekty.Contains(u!))
                projekty.Add(u!);
        }
        return string.Join(", ", projekty);
    }

    /// Dokumenty ZK realizowane przez pozycję ZD:
    /// PozycjeRealizowane -> PozycjaRealizowana -> Dokument (ustalone refleksją).
    internal static IEnumerable<object> DokumentyZk(object poz)
    {
        var wynik = new List<object>();
        try
        {
            if (Wlasc(poz, "PozycjeRealizowane") is not System.Collections.IEnumerable kol)
                return wynik;
            foreach (var r in kol)
            {
                var pz = Wlasc(r, "PozycjaRealizowana");
                var dok = pz == null ? null : Wlasc(pz, "Dokument");
                if (dok != null) wynik.Add(dok);
            }
        }
        catch { /* brak powiązania nie może wywalić odczytu */ }
        return wynik;
    }

    /// Właściwość po nazwie, także przy JAWNEJ implementacji interfejsu
    /// (GetType().GetProperty() zwraca wtedy null, choć składowa istnieje).
    internal static object? Wlasc(object o, string nazwa)
    {
        try
        {
            var p = o.GetType().GetProperty(nazwa);
            if (p != null) return p.GetValue(o);
            foreach (var i in o.GetType().GetInterfaces())
            {
                p = i.GetProperty(nazwa);
                if (p != null) return p.GetValue(o);
            }
        }
        catch { }
        return null;
    }

    internal record PozZd(string Symbol, string Nazwa, decimal Ilosc, string Numer,
                          string Dostawca, string Data, string Status, string Zk, string Projekt);
    internal record Poz(string Symbol, string Nazwa, decimal Ilosc,
                        decimal Dostepne, decimal Zadysponowane, decimal Zarezerwowane,
                        decimal StanMinimalny, decimal StanOptymalny,
                        string JednostkaMiary, string? Dostawca, List<Zrodlo> Zk);
}
