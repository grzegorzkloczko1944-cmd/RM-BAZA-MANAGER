// Zapotrzebowanie liczone tak, zeby NIGDY nie wywrocilo trybu mostu.
//
// ⛔ DLACZEGO TEN PLIK ISTNIEJE (30.09.2026)
//
// SDK `ZamowieniaOdKlientow().ZapotrzebowanieNaAsortyment()` PADA
// NullReferenceException, gdy na OTWARTYM ZK lezy pozycja bez kartoteki:
// grupuje po `t.Item1.AsortymentAktualny.Id` (dekompilacja Logistyka.dll).
// W praktyce wywala to pozycja JEDNORAZOWA — legalna sprzedaz bez kartoteki
// („Gasket", 12 szt, ZK 2/09/2026). To ograniczenie SDK, nie blad danych.
//
// 29.09 osłona powstala WEWNATRZ Zapotrzebowanie.cs — i to byl blad.
// Te sama metode SDK wola takze Zd.cs (tworzenie ZD), ktory osłony nie
// dostal, wiec:
//   * okno ZD otwieralo sie poprawnie (lista liczona trybem wlasnym),
//   * ale „Utworz ZD" nadal padalo tym samym „Object reference not set...".
// Zgloszone 30.09.2026. Naprawa objawu w jednym z czterech wywolan jest
// naprawa pozorna — dlatego logika mieszka TERAZ TUTAJ, a wolajacy tylko
// z niej korzystaja. Dokladajac nowy tryb, ktory potrzebuje zapotrzebowania,
// wolaj `Policz()` — NIE `ZapotrzebowanieNaAsortyment()` wprost.
//
// Wynik jest WIERNY SDK: `ZapotrzebowanieWlasne` to replika
// `BudujPozycjeZapotrzebowaniaNaPodstawieGrupy` (ta sama dekompilacja), wiec
// tryb wlasny liczy to samo, co Subiekt — z pominieciem pozycji, ktorych
// Sfera nie umie policzyc.
//
// ⛔ `IKalkulatorZapotrzebowania` jako alternatywa NIE dziala spoza Subiekta:
// wymaga kontenera DI (`IInjectionScope`). Potwierdzone ponownie 30.09.2026
// trybem `zapotrzebowanie-test`. Nie probowac.

using InsERT.Moria.Sfera;

namespace NexoRecon;

/// Jedna potrzeba zakupowa — te same pola co `PozycjaZestawieniaZapotrzebowania`
/// z SDK, zeby wolajacy nie musial wiedziec, skad dane pochodza.
///
/// `PozycjeZK` jest tu KLUCZOWE: to one wiaza ZD z zamowieniem klienta
/// (`UtworzNaPodstawieZapotrzebowania`). Tryb wlasny musi je przepisac
/// z oryginalnych pozycji, inaczej powstanie ZD „wiszace w prozni".
internal sealed class Potrzeba
{
    public InsERT.Moria.ModelDanych.Asortyment? Asortyment;
    public decimal Ilosc;
    public InsERT.Moria.ModelDanych.JednostkaMiaryAsortymentu? JednostkaMiary;
    public InsERT.Moria.ModelDanych.Podmiot? Dostawca;
    public List<InsERT.Moria.ModelDanych.PozycjaDokumentu> PozycjeZK;

    public Potrzeba(InsERT.Moria.ModelDanych.Asortyment? a, decimal ilosc,
                    InsERT.Moria.ModelDanych.JednostkaMiaryAsortymentu? jm,
                    InsERT.Moria.ModelDanych.Podmiot? dostawca,
                    List<InsERT.Moria.ModelDanych.PozycjaDokumentu> pozycje)
    { Asortyment = a; Ilosc = ilosc; JednostkaMiary = jm; Dostawca = dostawca; PozycjeZK = pozycje; }

    /// Gotowe teksty do listy (tylko `Policz(..., tylkoOdczyt: true)` w trybie
    /// wlasnym). Wtedy encje sa PUSTE — lista nie doczytuje ich po jednej.
    public OpisPotrzeby? Opis;
}

internal sealed record OpisPotrzeby(string Symbol, string Nazwa, string Jm, string? Dostawca,
                                    List<(string Numer, string Tytul, string Uwagi, decimal Ilosc)> Zrodla);

/// Wynik liczenia: potrzeby + co odpadlo i dlaczego + ktorym trybem policzone.
internal sealed class WynikZapotrzebowania
{
    public List<Potrzeba> Potrzeby = new();
    /// Pozycje, ktorych SDK nie umie policzyc — kazda z nazwa i rodzajem
    /// (`jednorazowa` = normalna sprzedaz, `bez-kartoteki` = blad danych).
    /// Idzie do JSON-a jako `bledy` i RM_BAZA pokazuje to uzytkownikowi.
    public List<object> Bledy = new();
    /// "sdk" albo "wlasny" — do pola `tryb` w JSON.
    public string Tryb = "sdk";
    /// Czasy etapow w ms — do pola `czasy_ms` w JSON (pomiar wydajnosci).
    public Dictionary<string, long> Czasy = new();
}

internal static class ZapotrzebowanieBezpieczne
{
    /// Zapotrzebowanie ze wszystkich otwartych ZK — bez ryzyka NRE.
    ///
    /// Najpierw wlasny przeglad ENCJI (nie projekcja EF! — INNER JOIN cicho
    /// gubi zepsute pozycje i baza wyglada na czysta). Gdy sa pozycje bez
    /// kartoteki — liczymy sami, z pominieciem tylko tych pozycji. Gdy nie ma
    /// — SDK jak dotad, a gdyby mimo to padlo, ten sam tryb wlasny.
    /// `tylkoOdczyt`: wolajacy potrzebuje samych tekstow do listy (tryb
    /// `zapotrzebowanie`), nie encji do utworzenia ZD — tryb wlasny liczy
    /// wtedy jednym zapytaniem bez sledzenia encji (01.10.2026).
    public static WynikZapotrzebowania Policz(Uchwyt sfera, bool tylkoOdczyt = false)
    {
        var wynik = new WynikZapotrzebowania();
        var zam = sfera.ZamowieniaOdKlientow();
        var zepsute = new HashSet<int>();
        var sw = System.Diagnostics.Stopwatch.StartNew();
        // Tylko do porownan wynikow (01.10.2026): "wlasny" = tryb wlasny mimo
        // dzialajacego SDK, "stary" = dawna sciezka encjami (bez zapytan zbiorczych).
        var wymus = (Environment.GetEnvironmentVariable("NEXORECON_ZAPOTRZEBOWANIE") ?? "").Trim().ToLowerInvariant();

        // 1. Przeglad: TYLKO ZK z pozycja bez kartoteki — jedno zapytanie SQL.
        //    Do 01.10.2026 przeglad wczytywal KAZDY ZK i kazda jego pozycje
        //    osobno (leniwe ladowanie): ~450 ms w domu, wiecej w firmie.
        //    `AsortymentAktualny == null` w Where to LEFT JOIN + IS NULL —
        //    w filtrze nie gubi pozycji jak projekcja pol kartoteki (INNER JOIN).
        List<InsERT.Moria.ModelDanych.DokumentZK>? otwarteZk = null;
        List<InsERT.Moria.ModelDanych.DokumentZK>? podejrzane = null;
        if (wymus != "stary")
        {
            try
            {
                podejrzane = zam.Dane.Wszystkie()
                    .Where(zk => zk.Pozycje.Any(p => p.AsortymentAktualny == null))
                    .ToList();
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("zapotrzebowanie: szybki przeglad ZK nie poszedl, pelny: " + ex.Message);
                wynik.Czasy["awaria_szybkiego_przegladu"] = 1;
            }
        }
        if (podejrzane != null)
        {
            foreach (var zk in podejrzane)
                if (!CzyZamkniety(zk)) SprawdzPozycje(zk, wynik, zepsute);
        }
        else
        {
            otwarteZk = PrzegladPelny(zam.Dane.Wszystkie(), wynik, zepsute);
        }
        wynik.Czasy["przeglad_zk"] = sw.ElapsedMilliseconds; sw.Restart();

        if (zepsute.Count == 0 && wymus != "wlasny" && wymus != "stary")
        {
            try
            {
                wynik.Potrzeby = zam.ZapotrzebowanieNaAsortyment()
                    .Select(x => new Potrzeba(x.Asortyment, x.Ilosc, x.JednostkaMiary, x.Dostawca,
                                              (x.PozycjeZK ?? Enumerable.Empty<InsERT.Moria.ModelDanych.PozycjaDokumentu>()).ToList()))
                    .ToList();
                wynik.Tryb = "sdk";
                wynik.Czasy["sdk"] = sw.ElapsedMilliseconds;
                return wynik;
            }
            catch (Exception ex)
            {
                wynik.Bledy.Add(new { blad = "SDK ZapotrzebowanieNaAsortyment: " + ex.GetType().Name + ": " + ex.Message });
            }
        }

        // 2. Tryb wlasny. Na produkcji to ZWYKLA sciezka, dopoki jakikolwiek
        //    otwarty ZK ma pozycje jednorazowa (ZK 2/09/2026, „Gasket").
        List<Potrzeba>? potrzeby = null;
        //    Szybko (jedno zapytanie) TYLKO dla listy. Tworzenie ZD (Zd.cs)
        //    potrzebuje encji i zostaje na drodze sprawdzonej na produkcji
        //    od 30.09 — tam czas nie gra roli, a pomylka kosztuje dokument.
        if (tylkoOdczyt && wymus != "stary")
        {
            try { potrzeby = ZapotrzebowanieWlasneOdczyt(zam.Dane.Wszystkie(), zepsute); }
            catch (Exception ex)
            {
                Console.Error.WriteLine("zapotrzebowanie: szybki tryb wlasny nie poszedl, encjami: " + ex.Message);
                wynik.Czasy["awaria_szybkiego_wlasnego"] = 1;
            }
        }
        if (potrzeby == null)
        {
            otwarteZk ??= PrzegladPelny(zam.Dane.Wszystkie(), new WynikZapotrzebowania(), new HashSet<int>());
            potrzeby = ZapotrzebowanieWlasne(otwarteZk, zepsute);
        }
        wynik.Potrzeby = potrzeby;
        wynik.Tryb = "wlasny";
        wynik.Czasy["wlasny"] = sw.ElapsedMilliseconds;
        return wynik;
    }

    /// Dawny przeglad: kazdy ZK i kazda pozycja osobno. Zostaje jako zapas,
    /// gdyby zapytanie zbiorcze kiedys nie przeszlo (inna wersja Sfery).
    static List<InsERT.Moria.ModelDanych.DokumentZK> PrzegladPelny(
        IQueryable<InsERT.Moria.ModelDanych.DokumentZK> zrodlo, WynikZapotrzebowania wynik, HashSet<int> zepsute)
    {
        var otwarte = new List<InsERT.Moria.ModelDanych.DokumentZK>();
        try
        {
            var wszystkie = zrodlo.ToList();
            foreach (var zk in wszystkie)
            {
                if (CzyZamkniety(zk)) continue;
                otwarte.Add(zk);
                SprawdzPozycje(zk, wynik, zepsute);
            }
        }
        catch (Exception ex)
        {
            wynik.Bledy.Add(new { blad = "przeglad ZK: " + ex.GetType().Name + ": " + ex.Message });
        }
        return otwarte;
    }

    /// Pozycje bez kartoteki na jednym ZK -> `zepsute` + opis do `Bledy`.
    static void SprawdzPozycje(InsERT.Moria.ModelDanych.DokumentZK zk,
                               WynikZapotrzebowania wynik, HashSet<int> zepsute)
    {
        var numer = Bezp(() => zk.NumerWewnetrzny?.PelnaSygnatura) ?? "?";
        List<InsERT.Moria.ModelDanych.PozycjaDokumentu> pozZk;
        try { pozZk = zk.Pozycje.ToList(); }
        catch (Exception ex)
        {
            wynik.Bledy.Add(new { dokument = numer, blad = "nie da sie odczytac pozycji: " + ex.Message });
            return;
        }
        foreach (var pz in pozZk)
        {
            InsERT.Moria.ModelDanych.Asortyment? a = null;
            try { a = pz.AsortymentAktualny; } catch { }
            if (a != null) continue;
            zepsute.Add(pz.Id);
            // Co to za pozycja? `AsortymentWybrany` to wiersz HISTORII
            // (FK AsortymentWybranyId -> AsortymentyHistoria) — dla pozycji
            // JEDNORAZOWEJ ma nazwe i Jednorazowy = 1, a Asortyment_Id puste.
            // Bez nazwy w raporcie user szukal „usunietej kartoteki",
            // ktorej nigdy nie bylo (29.09.2026).
            string nazwa = "", symbolH = "";
            bool jednorazowa = false;
            try
            {
                var h = pz.AsortymentWybrany;
                if (h != null)
                {
                    nazwa = (Bezp(() => h.Nazwa) ?? "").Trim();
                    symbolH = (Bezp(() => h.Symbol) ?? "").Trim();
                    try { jednorazowa = h.Jednorazowy; } catch { }
                }
            }
            catch { }
            wynik.Bledy.Add(new
            {
                dokument = numer,
                pozycja_id = pz.Id,
                ilosc = pz.Ilosc,
                nazwa,
                symbol = symbolH,
                rodzaj = jednorazowa ? "jednorazowa" : "bez-kartoteki",
                blad = jednorazowa
                    ? "pozycja jednorazowa (bez kartoteki) - Subiekt nie liczy dla niej zapotrzebowania; pominieta"
                    : "pozycja bez kartoteki (AsortymentAktualny = null) - blad danych, sprawdz dokument w Subiekcie",
            });
        }
    }

    /// Tryb wlasny dla samej listy: tylko kolumny (bez encji i bez ich
    /// sledzenia). Te same reguly co `ZapotrzebowanieWlasne`.
    static List<Potrzeba> ZapotrzebowanieWlasneOdczyt(
        IQueryable<InsERT.Moria.ModelDanych.DokumentZK> zk, HashSet<int> zepsute)
    {
        var wiersze = zk
            .Where(d => !d.Zamkniety)
            .SelectMany(d => d.Pozycje
                .Where(p => p.AsortymentAktualny != null)
                .Select(p => new
                {
                    PozId = p.Id,
                    AId = p.AsortymentAktualny.Id,
                    p.AsortymentAktualny.Symbol,
                    p.AsortymentAktualny.Nazwa,
                    JmId = (int?)p.JednostkaMiaryAs.Id,
                    JmSym = p.JednostkaMiaryAs.JednostkaMiary.Symbol,
                    JmBazSym = p.AsortymentAktualny.PodstawowaJednostkaMiaryAsortymentu.JednostkaMiary.Symbol,
                    Dost = p.AsortymentAktualny.DaneAsortymentuDostawcyPodstawowego.Podmiot.NazwaSkrocona,
                    Pozostalo = (decimal?)p.IloscDoRealizacji.PozostalaIlosc,
                    p.Ilosc,
                    p.IloscWJednostceBazowej,
                    Numer = d.NumerWewnetrzny.PelnaSygnatura,
                    d.Tytul,
                    d.Uwagi,
                }))
            .ToList();

        var grupy = new Dictionary<int, List<int>>();
        for (int i = 0; i < wiersze.Count; i++)
        {
            var w = wiersze[i];
            if (zepsute.Contains(w.PozId)) continue;
            if ((w.Pozostalo ?? w.Ilosc) <= 0) continue;
            if (!grupy.TryGetValue(w.AId, out var lista)) grupy[w.AId] = lista = new List<int>();
            lista.Add(i);
        }

        var wynik = new List<Potrzeba>();
        foreach (var (_, idx) in grupy)
        {
            var pierwszy = wiersze[idx[0]];
            var jedna = idx.Select(i => wiersze[i].JmId ?? 0).Distinct().Count() == 1;
            decimal ilosc = 0m;
            foreach (var i in idx)
            {
                var w = wiersze[i];
                decimal wsp = 1m;
                if (!jedna && w.Ilosc != 0) wsp = w.IloscWJednostceBazowej / w.Ilosc;
                ilosc += (w.Pozostalo ?? w.Ilosc) * wsp;
            }
            var zrodla = idx.Select(i => (wiersze[i].Numer ?? "", wiersze[i].Tytul ?? "",
                                          wiersze[i].Uwagi ?? "", wiersze[i].Ilosc)).ToList();
            wynik.Add(new Potrzeba(null, ilosc, null, null, new())
            {
                Opis = new OpisPotrzeby((pierwszy.Symbol ?? "").Trim(), pierwszy.Nazwa ?? "",
                                        (jedna ? pierwszy.JmSym : pierwszy.JmBazSym) ?? "",
                                        pierwszy.Dost, zrodla),
            });
        }
        return wynik;
    }

    /// Replika `BudujPozycjeZapotrzebowaniaNaPodstawieGrupy` z SDK (dekompilacja
    /// Logistyka.dll, 29.09.2026), zeby „tryb wlasny" liczyl TO SAMO co Sfera:
    ///  * ilosc niezrealizowana = `IloscDoRealizacji.PozostalaIlosc` (kolumna,
    ///    ktora Subiekt sam utrzymuje przy realizacji ZD/WZ/sprzedazy);
    ///  * jednostka: gdy wszystkie pozycje maja te sama -> ta; inaczej jednostka
    ///    bazowa kartoteki, a ilosci przeliczone proporcja
    ///    `IloscWJednostceBazowej/Ilosc` z KAZDEJ pozycji (SDK robi
    ///    `PrzeliczIloscNaJednostke` — rozszerzenie z Asortymenty.dll, ktorej
    ///    nie referencujemy; proporcja daje ten sam wynik);
    ///  * dostawca domyslny = `DaneAsortymentuDostawcyPodstawowego.Podmiot`
    ///    (to samo, co `DostawcaPodstawowy()` w SDK).
    static List<Potrzeba> ZapotrzebowanieWlasne(
        List<InsERT.Moria.ModelDanych.DokumentZK> otwarte, HashSet<int> zepsute)
    {
        var grupy = new Dictionary<int, List<InsERT.Moria.ModelDanych.PozycjaDokumentu>>();
        var kartoteki = new Dictionary<int, InsERT.Moria.ModelDanych.Asortyment>();
        foreach (var zk in otwarte)
        {
            List<InsERT.Moria.ModelDanych.PozycjaDokumentu> pozZk;
            try { pozZk = zk.Pozycje.ToList(); } catch { continue; }
            foreach (var pz in pozZk)
            {
                if (zepsute.Contains(pz.Id)) continue;
                InsERT.Moria.ModelDanych.Asortyment? a = null;
                try { a = pz.AsortymentAktualny; } catch { }
                if (a == null) continue;
                if (Pozostalo(pz) <= 0) continue;
                if (!grupy.TryGetValue(a.Id, out var lista))
                {
                    lista = new List<InsERT.Moria.ModelDanych.PozycjaDokumentu>();
                    grupy[a.Id] = lista;
                    kartoteki[a.Id] = a;
                }
                lista.Add(pz);
            }
        }

        var wynik = new List<Potrzeba>();
        foreach (var (id, lista) in grupy)
        {
            var a = kartoteki[id];
            var jmIds = new HashSet<int>();
            foreach (var pz in lista)
                try { jmIds.Add(pz.JednostkaMiaryAs.Id); } catch { }
            InsERT.Moria.ModelDanych.JednostkaMiaryAsortymentu? jm = null;
            decimal ilosc = 0m;
            if (jmIds.Count == 1)
            {
                try { jm = lista[0].JednostkaMiaryAs; } catch { }
                foreach (var pz in lista) ilosc += Pozostalo(pz);
            }
            else
            {
                try { jm = a.PodstawowaJednostkaMiaryAsortymentu; } catch { }
                foreach (var pz in lista)
                {
                    var p = Pozostalo(pz);
                    decimal wsp = 1m;
                    try { if (pz.Ilosc != 0) wsp = pz.IloscWJednostceBazowej / pz.Ilosc; } catch { }
                    ilosc += p * wsp;
                }
            }
            InsERT.Moria.ModelDanych.Podmiot? dostawca = null;
            try { dostawca = a.DaneAsortymentuDostawcyPodstawowego?.Podmiot; } catch { }
            wynik.Add(new Potrzeba(a, ilosc, jm, dostawca, lista));
        }
        return wynik;
    }

    static decimal Pozostalo(InsERT.Moria.ModelDanych.PozycjaDokumentu pz)
    {
        try { return pz.IloscDoRealizacji?.PozostalaIlosc ?? pz.Ilosc; }
        catch { return pz.Ilosc; }
    }

    /// Zamkniety = zrealizowane/anulowane. Wlasciwosc SDK bywa niedostepna
    /// w naszej referencji, stad dynamic z odwrotem po nazwie statusu.
    static bool CzyZamkniety(InsERT.Moria.ModelDanych.DokumentZK zk)
    {
        try { return (bool)((dynamic)zk).Zamkniety; } catch { }
        var st = Bezp(() => zk.StatusDokumentu?.Nazwa) ?? "";
        return st.Equals("Zrealizowane", StringComparison.OrdinalIgnoreCase)
            || st.Equals("Anulowane", StringComparison.OrdinalIgnoreCase);
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }
}
