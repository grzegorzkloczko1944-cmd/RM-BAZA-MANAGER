// Tryb "zd-usun" — kasuje wskazane dokumenty. ZAPISUJE (usuwa).
//
//   NexoRecon.exe zd-usun --numery="ZD 1/09/2026;ZK 5/CENTRALA/2026" [--out=w.json] --zapisz
//
// Bez --zapisz tylko pokazuje, co by usunął.
//
// Kasuje WYŁĄCZNIE dokumenty o dokładnie podanych numerach — żadnych zakresów
// ani filtrów po dacie. Usunięcie dokumentu jest nieodwracalne, więc lista musi
// być jawna i krótka; przy niepasującym numerze zgłaszamy błąd zamiast zgadywać.
//
// Powód powstania (04.09.2026): pierwsze ZD z RM_BAZA tworzone były bez
// powiązania z ZK (patrz Zd.cs) i zostały w bazie jako śmieci do posprzątania.
//
// Rozszerzone 05.09.2026 na ZK, RW i WZ: po testach integracji w bazie zostają
// śmieci wszystkich typów, a kasowanie ZK trzeba było klikać ręcznie
// w Subiekcie. Typ rozpoznajemy z PREFIKSU numeru, więc jedno wywołanie
// sprząta mieszaną listę. Nazwa trybu została "zd-usun" — zmiana zepsułaby
// istniejące wywołania z RM_BAZA (subiekt_zamowienia.usun_zd).
//
// 10.09.2026 doszło PW — przychody wewnętrzne z kalkulatora RMPAK. Dotąd
// wypadały z listy rodzajów i kasowanie kończyło się „nie znaleziono dokumentu
// o tym numerze", choć dokument istniał i był widoczny w Przeglądzie.
//
// ⚠️ Kasujemy tylko to, na co pozwala Subiekt (MoznaUsunac). Dokument
// zrealizowany albo powiązany z innym zostaje i wraca jako "blad" —
// nie próbujemy tego obchodzić.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class ZdUsun
{
    public static int Uruchom(Uchwyt sfera, string numeryArg, string? outPath, bool zapisz)
    {
        var chciane = numeryArg.Split(';', StringSplitOptions.RemoveEmptyEntries)
                               .Select(s => s.Trim())
                               .Where(s => s.Length > 0)
                               .ToHashSet(StringComparer.OrdinalIgnoreCase);
        if (chciane.Count == 0) { Console.WriteLine("Brak numerów do usunięcia."); return 1; }

        var kroki = new List<Krok>();
        var znalezione = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        // Typ dokumentu z prefiksu numeru — jedno wywołanie sprząta mieszaną
        // listę. Przeszukujemy tylko te rodzaje, które faktycznie padły
        // w --numery, żeby nie ciągnąć z bazy czterech list bez potrzeby.
        // PW doszlo 10.09.2026: bez niego kasowanie przychodu wewnetrznego
        // wpadalo w galaz „szukamy wszedzie" i przegladalo ZK/ZD/RW/WZ —
        // wszedzie poza kolekcja, w ktorej PW naprawde leza. Konczylo sie
        // komunikatem „nie znaleziono dokumentu o tym numerze", choc dokument
        // spokojnie istnial i byl widoczny w Przegladzie dokumentow.
        var WSZYSTKIE = new[] { "ZK", "ZD", "RW", "WZ", "PW" };
        var rodzaje = WSZYSTKIE
            .Where(r => chciane.Any(n => n.StartsWith(r + " ", StringComparison.OrdinalIgnoreCase)
                                      || n.StartsWith(r + "/", StringComparison.OrdinalIgnoreCase)))
            .ToList();
        if (rodzaje.Count == 0)
        {
            // Numer bez rozpoznanego prefiksu — szukamy wszędzie, zamiast
            // odsyłać z niczym.
            rodzaje = WSZYSTKIE.ToList();
        }

        foreach (var rodzaj in rodzaje)
        {
            dynamic kolekcja;
            try { kolekcja = Kolekcja(sfera, rodzaj); }
            catch (Exception ex)
            {
                kroki.Add(new Krok(rodzaj, "blad", $"nie udało się otworzyć listy: {ex.Message}"));
                continue;
            }

            // Ostatnie 300 dokumentów danego typu — kasujemy świeże śmieci,
            // nie archiwum sprzed lat.
            List<dynamic> dokumenty;
            try
            {
                dokumenty = ((IEnumerable<dynamic>)kolekcja.Dane.Wszystkie())
                    .OrderByDescending(d => (object)d.DataWprowadzenia)
                    .Take(300)
                    .ToList();
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok(rodzaj, "blad", $"nie udało się wczytać dokumentów: {ex.Message}"));
                continue;
            }

            foreach (var d in dokumenty)
            {
                var numer = Bezp(() => (string?)d.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                if (numer.Length == 0 || !chciane.Contains(numer)) continue;
                znalezione.Add(numer);

                var podmiot = Bezp(() => (string?)d.Podmiot?.NazwaSkrocona) ?? "";
                var pozycji = 0;
                try { pozycji = Enumerable.Count((IEnumerable<dynamic>)d.Pozycje); } catch { }
                var opis = $"{rodzaj}: {podmiot}, {pozycji} poz.";
                // Id USUWANEGO dokumentu — po nim RM_BAZA sprzata swoj dziennik
                // wysylek. Numer sie do tego nie nadaje, bo Subiekt nada go
                // zaraz nastepnemu dokumentowi (07.09.2026).
                var id = 0;
                try { id = (int)d.Id; } catch { }

                if (!zapisz)
                {
                    kroki.Add(new Krok(numer, "do-usuniecia", opis, id));
                    continue;
                }

                try
                {
                    using var ob = (IDisposable)kolekcja.Znajdz(d);
                    dynamic obiekt = ob;

                    // MoznaUsunac ma ZD, ale nie ZK (ZamowienieOdKlientaBO go
                    // nie zna — RuntimeBinderException, 05.09.2026). Pytamy
                    // refleksją: gdy własność istnieje i mówi „nie", odpuszczamy;
                    // gdy jej nie ma, próbujemy usunąć i ewentualną odmowę
                    // Subiekta łapiemy niżej jako wyjątek.
                    var wlasnosc = ((object)obiekt).GetType().GetProperty("MoznaUsunac");
                    if (wlasnosc != null
                        && wlasnosc.GetValue(obiekt) is bool mozna && !mozna)
                    {
                        kroki.Add(new Krok(numer, "blad",
                            "Subiekt nie pozwala usunąć tego dokumentu (zrealizowany lub zablokowany)"));
                        continue;
                    }
                    obiekt.Usun();

                    // ⚠️ Usun() potrafi wrocic BEZ WYJATKU, choc Subiekt
                    // odmowil — sprawdzone 07.09.2026 na WZ w bazie demo:
                    // tryb raportowal "usuniete" dla 12 dokumentow, a wszystkie
                    // 12 zostawalo w bazie. MoznaUsunac tez tego nie wylapuje
                    // (dla WZ zwracalo true). Ta sama pulapka co w
                    // KartotekaUsun.cs i MagazynUsun.cs, wiec i to samo
                    // lekarstwo: rozstrzyga STAN BAZY, nie wynik Usun().
                    // Falszywy sukces jest tu gorszy niz blad — RM_BAZA na jego
                    // podstawie cofa "Zamowiono" w arkuszu (subiekt_zamowienia.py),
                    // wiec skasowalaby slad po ZD, ktore dalej istnieje.
                    var nadalJest = false;
                    try
                    {
                        nadalJest = ((IEnumerable<dynamic>)kolekcja.Dane.Wszystkie())
                            .Any(x => string.Equals(
                                Bezp(() => (string?)x.NumerWewnetrzny?.PelnaSygnatura) ?? "",
                                numer, StringComparison.OrdinalIgnoreCase));
                    }
                    catch { }

                    if (nadalJest)
                    {
                        var bledy = Bezp(() => (string?)obiekt.PodajBledy());
                        kroki.Add(new Krok(numer, "blad",
                            "Subiekt odmowil usuniecia — dokument ma powiazania "
                            + "(zrealizowany, rozliczony albo powiazany z innym dokumentem)"
                            + (string.IsNullOrWhiteSpace(bledy) ? "" : $" ({bledy})")));
                        continue;
                    }
                    kroki.Add(new Krok(numer, "usuniete", opis, id));
                }
                catch (Exception ex)
                {
                    kroki.Add(new Krok(numer, "blad", $"{ex.GetType().Name}: {ex.Message}"));
                }
            }
        }

        foreach (var brak in chciane.Except(znalezione, StringComparer.OrdinalIgnoreCase))
            kroki.Add(new Krok(brak, "blad", "nie znaleziono dokumentu o tym numerze"));

        var json = JsonSerializer.Serialize(new { zapisano = zapisz, kroki },
            new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    // Rodzaj → kolekcja Sfery. Te same akcesory, których używa Dokumenty.cs,
    // więc lista do skasowania pokrywa się z tym, co widać w oknie przeglądu.
    static dynamic Kolekcja(Uchwyt sfera, string rodzaj) => rodzaj switch
    {
        "ZK" => sfera.ZamowieniaOdKlientow(),
        "ZD" => sfera.ZamowieniaDoDostawcow(),
        "RW" => sfera.RozchodyWewnetrzne(),
        "WZ" => sfera.WydaniaZewnetrzne(),
        "PW" => sfera.PrzychodyWewnetrzne(),
        _ => throw new ArgumentException($"nieznany rodzaj dokumentu: {rodzaj}")
    };

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    internal record Krok(string Numer, string Status, string? Szczegoly, int Id = 0);
}
