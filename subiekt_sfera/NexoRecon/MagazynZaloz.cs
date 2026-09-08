// Tryb "magazyn-zaloz" — zakłada JEDEN magazyn. ZAPISUJE.
//
//   NexoRecon.exe magazyn-zaloz --plan=m.json [--out=w.json] [--zapisz]
//
// Bez --zapisz suchy przebieg: sprawdza, czy symbol wolny, nic nie zapisuje.
//
// plan.json:
//   { "symbol":"MASTER", "nazwa":"MASTER", "opis":"...",
//     "jednostka":"RM PRODUKCJA" }   // Symbol albo Nazwa istniejącej
//                                     // jednostki organizacyjnej — WYMAGANE
//
// Po co: uruchomienie magazynu nr 2 obok MAG (SUBIEKT PODWÓJNE POZYCJE DO
// NAPRAWY.md / MAGAZYN.md) — magazyn trzeba założyć, zanim cokolwiek na niego
// pójdzie. Sfera to udostępnia (SDK: "IMagazyny Methods" -> Utworz, dziedziczy
// standardowy wzorzec IObiektyBiznesowe — ten sam co IAsortymenty.Utworz()
// w Kartoteka.cs), więc nie ma powodu robić tego wyłącznie ręcznie w GUI.
//
// Świadomie WĄSKI zakres: tylko Symbol/Nazwa/Opis. "Magazyn Properties"
// (SDK) pokazuje dziesiątki pól (MagazynGlowny, MagazynProdukcji,
// MagazynPrzyjec, MagazynWydan, powiązania z POS/kontami integracji...) —
// to ustawienia biznesowe, które ma sens klikać świadomie w Subiekcie,
// nie zgadywać w JSON-ie. Ten tryb zakłada gołą, poprawną kartotekę
// magazynu; resztę dostraja się w GUI.
//
// ⚠️ WYJĄTEK: JednostkiOrganizacyjne. Subiekt odrzuca zapis magazynu bez
// co najmniej jednej — "musi być podłączony do co najmniej jednej jednostki
// organizacyjnej" (sprawdzone na produkcji 07.09.2026). To nie jest pole
// biznesowe do świadomego wyboru jak MagazynGlowny — bez niego magazyn
// w ogóle nie powstaje.
//
// plan.jednostka to Symbol ALBO Nazwa istniejącej jednostki organizacyjnej
// (np. "RM PRODUKCJA") — dopasowanie dokładne po TRIM, bez rozróżniania
// wielkości liter, tak jak wszędzie indziej w tym moście.
//
// ⚠️ PUŁAPKA nazw: "jednostka organizacyjna" w Sferze to DWIE różne rzeczy
// o łudząco podobnych nazwach interfejsów, sprawdzone 07.09.2026:
//   - InsERT.Moria.Kadry.Duze.IJednostkiOrganizacyjne — DZIAŁ kadrowy
//     (JednostkaOrganizacyjnaGr: Nazwa, JednostkaNadrzedna... BRAK Symbol,
//     BRAK NIP). To nie to, mimo najbardziej oczywistej nazwy.
//   - InsERT.Moria.ModelOrganizacyjny — CENTRALA/ODDZIAŁ firmy (klasa
//     JednostkaOrganizacyjna, z podklasami Centrala i Oddzial; ma Symbol,
//     Magazyny...). TO jest to, czego wymaga Magazyn.Dane.JednostkiOrganizacyjne.
//     Dostęp: ICentrale.Znajdz() (zawsze dokładnie jedna w systemie) i
//     IOddzialy.Dane.Wszystkie() (może być zero lub więcej).
// Tryb NIE zakłada nowej jednostki/oddziału (to decyzja biznesowa dla GUI);
// jeśli podana nazwa nie pasuje do centrali ani żadnego oddziału, zwraca
// błąd z pełną listą tego, co jest w bazie, żeby nie zgadywać na ślepo.

using System.Linq;

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class MagazynZaloz
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }
        var p = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;

        var symbol = (p.Symbol ?? "").Trim();
        var nazwa = (p.Nazwa ?? "").Trim();
        if (symbol.Length == 0) return Wynik(outPath, "blad", "pusty symbol", null);
        if (nazwa.Length == 0) nazwa = symbol;

        var magazyny = sfera.PodajObiektTypu<InsERT.Moria.ModelOrganizacyjny.IMagazyny>();

        // Ta sama logika dopasowania luźnego co w Kartoteka.cs — symbole
        // magazynów w tej bazie bywają z niespodziankami (patrz naprawiona
        // spacja wiodąca w symbolu asortymentu, MAGAZYN.md).
        var istn = magazyny.Dane.Wszystkie().ToList()
            .FirstOrDefault(m => string.Equals((Bezp(() => m.Symbol) ?? "").Trim(), symbol,
                                                StringComparison.OrdinalIgnoreCase));
        if (istn != null)
            return Wynik(outPath, "istnieje", $"magazyn „{istn.Symbol}” już jest: {istn.Nazwa}",
                         istn.Symbol?.Trim());

        if (!zapisz) return Wynik(outPath, "do-zalozenia", nazwa, symbol);

        var jednostkaChciana = (p.Jednostka ?? "").Trim();
        if (jednostkaChciana.Length == 0)
            return Wynik(outPath, "blad",
                "brak \"jednostka\" w planie — magazyn wymaga co najmniej jednej jednostki organizacyjnej", symbol);

        // Centrala + oddziały — patrz komentarz na górze pliku (pułapka nazw).
        // dynamic zamiast typu bazowego: Nazwa/Symbol/NIP nie siedzą jednolicie
        // na JednostkaOrganizacyjna, tylko różnie na Centrala i Oddzial — refleksja
        // ominie różnice, których dokumentacja SDK nie oddaje 1:1.
        var kandydaci = new List<InsERT.Moria.ModelDanych.JednostkaOrganizacyjna>();
        try
        {
            var centrale = sfera.PodajObiektTypu<InsERT.Moria.ModelOrganizacyjny.ICentrale>();
            using var centralaBo = centrale.Znajdz();
            if (centralaBo?.Dane is not null) kandydaci.Add(centralaBo.Dane);
        }
        catch { /* centrala moze byc niedostepna w tej konfiguracji SDK */ }
        try
        {
            var oddzialy = sfera.PodajObiektTypu<InsERT.Moria.ModelOrganizacyjny.IOddzialy>();
            kandydaci.AddRange(oddzialy.Dane.Wszystkie());
        }
        catch { }

        var jednostka = kandydaci.FirstOrDefault(j => Pasuje((dynamic)j, jednostkaChciana));
        if (jednostka is null)
        {
            var dostepne = string.Join("; ", kandydaci.Select(j => OpiszJednostke((dynamic)j)));
            return Wynik(outPath, "blad",
                $"nie znaleziono jednostki organizacyjnej \"{jednostkaChciana}\". Dostępne: {dostepne}", symbol);
        }

        try
        {
            using var ob = magazyny.Utworz();
            ob.Dane.Symbol = symbol;
            ob.Dane.Nazwa = nazwa;
            if (!string.IsNullOrWhiteSpace(p.Opis))
                try { ob.Dane.Opis = p.Opis!.Trim(); } catch { }
            ob.Dane.JednostkiOrganizacyjne.Add(jednostka);

            if (!ob.Zapisz())
                return Wynik(outPath, "blad", Bezp(ob.PodajBledy) ?? "Zapisz() = false", symbol);
            return Wynik(outPath, "zalozony", $"{nazwa} (jednostka: {OpiszJednostke((dynamic)jednostka)})", symbol);
        }
        catch (Exception ex)
        {
            return Wynik(outPath, "blad", $"{ex.GetType().Name}: {ex.Message}", symbol);
        }
    }

    static int Wynik(string? outPath, string status, string? szczegoly, string? symbol)
    {
        var json = JsonSerializer.Serialize(new { status, szczegoly, symbol },
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

    /// dynamic zamiast typów statycznych: Nazwa/Symbol/NIP nie są jednolicie
    /// dostępne na typie bazowym JednostkaOrganizacyjna (patrz komentarz
    /// wyżej), a różne podklasy (Centrala/Oddzial) je różnie wystawiają.
    static bool Pasuje(dynamic j, string chciana)
    {
        foreach (var f in new Func<dynamic, string?>[]
                 { x => Bezp(() => (string?)x.Symbol), x => Bezp(() => (string?)x.Nazwa),
                   x => Bezp(() => (string?)x.NIP) })
        {
            var wart = (f(j) ?? "").Trim();
            if (wart.Length > 0 && string.Equals(wart, chciana, StringComparison.OrdinalIgnoreCase))
                return true;
        }
        return false;
    }

    static string OpiszJednostke(dynamic j)
    {
        var symbol = Bezp(() => (string?)j.Symbol) ?? "?";
        var nazwa = Bezp(() => (string?)j.Nazwa) ?? "?";
        var nip = Bezp(() => (string?)j.NIP);
        return nip is null ? $"{symbol} / {nazwa}" : $"{symbol} / {nazwa} / NIP {nip}";
    }

    internal record Plan(string? Symbol, string? Nazwa, string? Opis, string? Jednostka);
}
