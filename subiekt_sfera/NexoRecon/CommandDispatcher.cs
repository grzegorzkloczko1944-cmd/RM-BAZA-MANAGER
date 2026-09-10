// CommandDispatcher — jedno miejsce, ktore wie, jaki tryb wola ktory handler.
//
// Do tej pory ta wiedza byla drabinka `if (tryb == "...")` w Program.cs.
// Tryb "server" potrzebuje tej samej mapy, a duplikowanie jej to prosta droga
// do rozjechania sie CLI i servera (SUBIEKT_STALY_MOST_PLAN.md sekcja 4:
// "Nie duplikowac logiki biznesowej miedzy trybem CLI i server").
//
// Kontrakt handlerow zostaje NIETKNIETY: nadal `Uruchom(Uchwyt, ..., outPath)`,
// nadal czytaja plan z pliku i pisza JSON do pliku. Dispatcher tylko wybiera
// handler i podaje mu argumenty. Dzieki temu Krok C nie dotyka ani jednej
// linii logiki biznesowej — server materializuje sobie pliki tymczasowe
// i czyta wynik (patrz ServerHost).
//
// READ vs WRITE (sekcja 14 planu) jest tu deklarowane jawnie, bo od tego
// zalezy, czy wolno ponowic komende po reconnect. Nie wyprowadzamy tego
// z obecnosci flagi --zapisz: "progi" bez planu to odczyt, a z planem zapis,
// wiec flaga sama w sobie nie wystarcza.

using InsERT.Moria.Sfera;

namespace NexoRecon;

/// <summary>Argumenty komendy — wspolne dla CLI i servera.</summary>
/// <param name="Symbole">Z <c>--symbol=</c> / <c>--symbols-file=</c>.</param>
/// <param name="PlanPath">Sciezka plan.json (<c>--plan=</c>).</param>
/// <param name="OutPath">Gdzie handler ma zapisac JSON (<c>--out=</c>).</param>
/// <param name="Zapisz">Czy naprawde zapisac do Subiekta (<c>--zapisz</c>).</param>
internal sealed record Komenda(
    string Tryb,
    List<string>? Symbole = null,
    string? PlanPath = null,
    string? OutPath = null,
    bool Zapisz = false,
    int Limit = 15,
    string? Numery = null,
    string? Magazyn = null,
    string? Data = null,
    string? SymboleCsv = null,
    string? Projekt = null,
    string? PdfDir = null,
    bool TylkoNiezerowe = false);

internal static class CommandDispatcher
{
    /// <summary>
    /// Tryby ZAPISUJACE. Po zerwanej sesji NIE WOLNO ich automatycznie
    /// ponowic — bridge nie wie, czy zapis przeszedl (sekcja 14 planu).
    /// </summary>
    static readonly HashSet<string> Zapisujace = new(StringComparer.OrdinalIgnoreCase)
    {
        "kartoteka", "kartoteka-usun", "kartoteka-edytuj", "projekt", "zd", "zd-usun",
        "dostawcy", "progi", "rw", "pw", "termin", "symbole", "komplet-napraw", "magazyn-zaloz",
        "magazyn-usun", "projekt-cofnij", "kartoteki", "zk-poz-usun",
    };

    /// <summary>
    /// Czy komenda moze zapisac do Subiekta. "progi" liczy sie jako zapis
    /// tylko z planem — bez niego to czysty odczyt progow.
    /// </summary>
    public static bool CzyZapis(Komenda k) =>
        // "progi" i "pola-wlasne" licza sie jako zapis TYLKO z planem —
        // bez planu to czysty odczyt (progow / metadanych pol wlasnych).
        k.Tryb.Equals("progi", StringComparison.OrdinalIgnoreCase)
        || k.Tryb.Equals("pola-wlasne", StringComparison.OrdinalIgnoreCase)
            ? !string.IsNullOrWhiteSpace(k.PlanPath)
            : Zapisujace.Contains(k.Tryb);

    /// <summary>Wszystkie tryby obslugiwane przez dispatcher.</summary>
    public static readonly string[] Tryby =
    {
        "stan", "katalog", "kontrahenci", "dokumenty", "faktury", "kartoteka",
        "stan-pozycji", "dostawcy", "zapotrzebowanie", "zd", "magazyn",
        "zd-usun", "wydruk-recon", "termin", "symbole", "rw", "kartoteka-usun",
        "progi", "wydruk", "projekt", "komplet", "komplet-napraw", "kartoteka-edytuj",
        "pola-wlasne", "magazyn-zaloz", "magazyn-usun", "pw", "projekt-cofnij",
        "kartoteki", "zapotrzebowanie-test", "zk-ilosci", "zk-poz-usun",
    };

    public static bool Zna(string tryb) => Tryby.Contains(tryb, StringComparer.OrdinalIgnoreCase);

    /// <summary>
    /// Wykonuje komende na podanej sesji. Zwraca kod wyjscia (0 = OK),
    /// dokladnie tak jak stara drabinka w Program.cs.
    /// </summary>
    public static int Wykonaj(Uchwyt sfera, Komenda k)
    {
        switch (k.Tryb.ToLowerInvariant())
        {
            // ── ODCZYT ───────────────────────────────────────────────────────
            case "stan":
                if (k.Symbole is not { Count: > 0 })
                    return Brak("stan: brak symboli (--symbol= albo --symbols-file=).");
                return Stan.Uruchom(sfera, k.Symbole, k.OutPath);

            case "katalog":
                return Katalog.Uruchom(sfera, k.OutPath);

            // Bez planu: odczyt metadanych (jakie pola sa i czy widoczne).
            // Z planem: ZAPIS wartosci pola na kartotekach (--zapisz).
            case "pola-wlasne":
                return k.PlanPath is null
                    ? PolaWlasne.Uruchom(sfera, k.OutPath)
                    : PolaWlasne.Zapis(sfera, k.PlanPath, k.OutPath, k.Zapisz);

            // Sklad kompletu i relacja odwrotna ("w czym to siedzi") — do
            // sprawdzenia, czy komplety projektu nie wisza w powietrzu.
            // Sprzatanie zdublowanych skladnikow (patrz KompletNapraw.cs).
            // Bez --zapisz tylko raport; bez symboli — wszystkie komplety.
            case "komplet-napraw":
                return KompletNapraw.Uruchom(sfera, k.Symbole, k.OutPath, k.Zapisz);

            case "komplet":
                if (k.Symbole is not { Count: > 0 })
                    return Brak("komplet: brak symboli (--symbol= albo --symbols-file=).");
                return Komplet.Uruchom(sfera, k.Symbole, k.OutPath);

            case "kontrahenci":
                return Katalog.Kontrahenci(sfera, k.OutPath);

            // Domyslne limity z Program.cs: ponizej 15 traktowane jako
            // "nie podano", wiec wchodzi wartosc trybu (200 / 60).
            case "dokumenty":
                return Dokumenty.Uruchom(sfera, k.Limit > 15 ? k.Limit : 200, k.OutPath);

            case "faktury":
                return Faktury.Uruchom(sfera, k.Limit > 15 ? k.Limit : 60, k.OutPath);

            case "stan-pozycji":
                if (k.Symbole is not { Count: > 0 })
                    return Brak("stan-pozycji: brak symboli.");
                return StanPozycji.Uruchom(sfera, k.Symbole, k.Projekt, k.OutPath);

            case "zapotrzebowanie":
                return Zapotrzebowanie.Uruchom(sfera, k.OutPath);

            // Diagnostyka: czy zapotrzebowanie rozwija komplety na skladniki.
            // Czysty odczyt — patrz naglowek ZapotrzebowanieTest.cs.
            case "zapotrzebowanie-test":
                return ZapotrzebowanieTest.Uruchom(sfera, k.OutPath);

            // Ilosci pozycji z ZK projektu — zrodlo „Ilosc (zam.)" w arkuszu.
            // Czysty odczyt; zapisem do pliku projektu zajmuje sie RM_BAZA.
            case "zk-ilosci":
                return ZkIlosci.Uruchom(sfera, k.Projekt, k.OutPath);

            case "magazyn":
                return Magazyn.Uruchom(sfera, k.OutPath, k.TylkoNiezerowe);

            case "wydruk-recon":
                return WydrukRecon.Uruchom(sfera, k.Numery, k.OutPath, k.PdfDir);

            case "wydruk":
                return Wydruk.Uruchom(sfera, k.Numery, k.OutPath, k.PdfDir);

            // ── ZAPIS (bez --zapisz to suchy przebieg) ───────────────────────
            case "kartoteka":
                if (k.PlanPath is null) return Brak("kartoteka: brak --plan=plik.json");
                return Kartoteka.Uruchom(sfera, k.PlanPath, k.OutPath, k.Zapisz);

            // Wsadowo: zestaw kartotek + sklady kompletow w jednym przebiegu,
            // BEZ ZK (w odroznieniu od "projekt"). Backend Edytora kartotek.
            case "kartoteki":
                if (k.PlanPath is null) return Brak("kartoteki: brak --plan=plik.json");
                return Kartoteki.Uruchom(sfera, k.PlanPath, k.OutPath, k.Zapisz);

            case "magazyn-zaloz":
                if (k.PlanPath is null) return Brak("magazyn-zaloz: brak --plan=plik.json");
                return MagazynZaloz.Uruchom(sfera, k.PlanPath, k.OutPath, k.Zapisz);

            case "magazyn-usun":
                return MagazynUsun.Uruchom(sfera, k.SymboleCsv, k.OutPath, k.Zapisz);

            case "dostawcy":
                if (k.PlanPath is null) return Brak("dostawcy: brak --plan=plik.json");
                return Dostawcy.Uruchom(sfera, k.PlanPath, k.OutPath, k.Zapisz);

            case "zd":
                if (k.PlanPath is null) return Brak("zd: brak --plan=plik.json");
                return Zd.Uruchom(sfera, k.PlanPath, k.OutPath, k.Zapisz);

            case "zd-usun":
                if (k.Numery is null) return Brak("zd-usun: brak --numery=\"ZD 1/09/2026;...\"");
                return ZdUsun.Uruchom(sfera, k.Numery, k.OutPath, k.Zapisz);

            case "termin":
                return Termin.Uruchom(sfera, k.Numery, k.Data, k.OutPath, k.Zapisz);

            case "symbole":
                if (k.PlanPath is null) return Brak("symbole: brak --plan=plik.json");
                return Symbole.Uruchom(sfera, k.PlanPath, k.OutPath, k.Zapisz);

            case "rw":
                if (k.PlanPath is null) return Brak("rw: brak --plan=plik.json");
                return Rw.Uruchom(sfera, k.PlanPath, k.OutPath, k.Zapisz);

            case "pw":
                if (k.PlanPath is null) return Brak("pw: brak --plan=plik.json");
                return Pw.Uruchom(sfera, k.PlanPath, k.OutPath, k.Zapisz);

            case "zk-poz-usun":
                if (k.PlanPath is null) return Brak("zk-poz-usun: brak --plan=plik.json");
                return ZkPozUsun.Uruchom(sfera, k.PlanPath, k.OutPath, k.Zapisz);

            case "kartoteka-usun":
                return KartotekaUsun.Uruchom(sfera, k.SymboleCsv, k.OutPath, k.Zapisz);

            // Zmiana ISTNIEJACYCH kartotek (nazwa, cena, opis, sklad kompletu).
            // Symbolu NIE rusza — od tego jest tryb "symbole".
            case "kartoteka-edytuj":
                if (k.PlanPath is null) return Brak("kartoteka-edytuj: brak --plan=plik.json");
                return KartotekaEdytuj.Uruchom(sfera, k.PlanPath, k.OutPath, k.Zapisz);

            // Bez --plan to ODCZYT progow; z planem zapis (dopiero z --zapisz).
            case "progi":
                return Progi.Uruchom(sfera, k.PlanPath, k.OutPath, k.Zapisz, k.Magazyn);

            case "projekt":
                if (k.PlanPath is null) return Brak("projekt: brak --plan=plik.json");
                return Projekt.Uruchom(sfera, k.PlanPath, k.OutPath, k.Zapisz);

            case "projekt-cofnij":
                if (k.PlanPath is null) return Brak("projekt-cofnij: brak --plan=plik.json");
                return ProjektCofnij.Uruchom(sfera, k.PlanPath, k.OutPath, k.Zapisz);

            default:
                return Brak($"Nieznany tryb: {k.Tryb}");
        }
    }

    static int Brak(string komunikat)
    {
        Console.WriteLine("Tryb " + komunikat);
        return 1;
    }
}
