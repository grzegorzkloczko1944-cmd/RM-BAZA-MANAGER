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
}

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
}

internal static class ZapotrzebowanieBezpieczne
{
    /// Zapotrzebowanie ze wszystkich otwartych ZK — bez ryzyka NRE.
    ///
    /// Najpierw wlasny przeglad ENCJI (nie projekcja EF! — INNER JOIN cicho
    /// gubi zepsute pozycje i baza wyglada na czysta). Gdy sa pozycje bez
    /// kartoteki — liczymy sami, z pominieciem tylko tych pozycji. Gdy nie ma
    /// — SDK jak dotad, a gdyby mimo to padlo, ten sam tryb wlasny.
    public static WynikZapotrzebowania Policz(Uchwyt sfera)
    {
        var wynik = new WynikZapotrzebowania();
        var zam = sfera.ZamowieniaOdKlientow();
        var zepsute = new HashSet<int>();
        var otwarteZk = new List<InsERT.Moria.ModelDanych.DokumentZK>();

        try
        {
            foreach (var zk in zam.Dane.Wszystkie().ToList())
            {
                if (CzyZamkniety(zk)) continue;
                otwarteZk.Add(zk);
                var numer = Bezp(() => zk.NumerWewnetrzny?.PelnaSygnatura) ?? "?";
                List<InsERT.Moria.ModelDanych.PozycjaDokumentu> pozZk;
                try { pozZk = zk.Pozycje.ToList(); }
                catch (Exception ex)
                {
                    wynik.Bledy.Add(new { dokument = numer, blad = "nie da sie odczytac pozycji: " + ex.Message });
                    continue;
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
        }
        catch (Exception ex)
        {
            wynik.Bledy.Add(new { blad = "przeglad ZK: " + ex.GetType().Name + ": " + ex.Message });
        }

        if (zepsute.Count == 0)
        {
            try
            {
                wynik.Potrzeby = zam.ZapotrzebowanieNaAsortyment()
                    .Select(x => new Potrzeba(x.Asortyment, x.Ilosc, x.JednostkaMiary, x.Dostawca,
                                              (x.PozycjeZK ?? Enumerable.Empty<InsERT.Moria.ModelDanych.PozycjaDokumentu>()).ToList()))
                    .ToList();
                wynik.Tryb = "sdk";
                return wynik;
            }
            catch (Exception ex)
            {
                wynik.Bledy.Add(new { blad = "SDK ZapotrzebowanieNaAsortyment: " + ex.GetType().Name + ": " + ex.Message });
            }
        }

        wynik.Potrzeby = ZapotrzebowanieWlasne(otwarteZk, zepsute);
        wynik.Tryb = "wlasny";
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
