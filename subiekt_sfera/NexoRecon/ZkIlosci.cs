// Tryb "zk-ilosci" — ilosci pozycji z ZK projektu. Wylacznie ODCZYT.
//
//   NexoRecon.exe zk-ilosci --projekt=3500 [--out=wynik.json] [konfig.json]
//
// Po co: „Ilosc (zam.)" w arkuszu RM_BAZA ma pokazywac stan z Subiekta, ale
// NIE KAZDE stanowisko ma dostep do Subiekta. Stanowisko z mostem odswieza te
// wartosci i zapisuje je do pliku projektu, ktory po zwolnieniu locka trafia
// na dysk sieciowy — reszta czyta juz zwykly plik projektu i pracuje jak dotad.
//
// Cache'em jest wiec PLIK PROJEKTU, nie osobny magazyn: nie trzeba niczego
// synchronizowac ani rozstrzygac, ktora kopia jest nowsza — obowiazuje ta sama
// sciezka, ktora RM_BAZA i tak ma dla calego BOM-u.
//
// ZK odnajdywane po numerze projektu w polu Uwagi — dokladnie tak samo jak
// w trybie "projekt" (Projekt.ZnajdzZkProjektu), zeby oba tryby zawsze mowily
// o TYM SAMYM dokumencie.

using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class ZkIlosci
{
    public static int Uruchom(Uchwyt sfera, string? projekt, string? outPath)
    {
        var pozycje = new List<PozIlosc>();
        string? numerZk = null;
        string? blad = null;
        var duplikatyOpis = new List<string>();
        // Czy ZK, z ktorej czytamy ilosci, NIE wyszla z RM_BAZA.
        var obce = false;

        if (string.IsNullOrWhiteSpace(projekt))
        {
            blad = "brak --projekt=";
        }
        else
        {
            try
            {
                var (zk, duplikaty) = Projekt.ZnajdzZkProjektu(sfera, projekt);
                if (zk == null)
                {
                    blad = $"nie znaleziono ZK dla projektu „{projekt}”";
                }
                else
                {
                    numerZk = Bezp(() => zk.NumerWewnetrzny?.PelnaSygnatura);

                    // Dwa+ dokumenty na projekt to sytuacja, ktorej tryb "projekt"
                    // nie przepuszcza przy zapisie. Tutaj tylko czytamy, wiec
                    // nie przerywamy — ale mowimy o tym wprost, bo ilosci moga
                    // pochodzic z niewlasciwego dokumentu.
                    foreach (var d in duplikaty)
                        duplikatyOpis.Add(Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "?");

                    // Dokument z numerem projektu w Uwagach, ale bez znacznika
                    // RM_BAZA w Tytule, moze byc zalozony recznie przez kogos
                    // innego. Tutaj tylko czytamy, wiec nie przerywamy — ale
                    // ilosci trafiaja do arkusza jako „Ilosc (zam.)", wiec user
                    // musi wiedziec, ze pochodza z NIE NASZEGO dokumentu.
                    obce = !Projekt.NaszeZk(zk);

                    // Ta sama funkcja, ktorej uzywa zapis — sumuje powtorzony
                    // symbol, bo liczy sie laczna ilosc zamowiona.
                    foreach (var kv in Projekt.CzytajPozycjeZk(zk.Pozycje))
                        pozycje.Add(new PozIlosc(kv.Key, kv.Value));
                }
            }
            catch (Exception e)
            {
                blad = $"{e.GetType().Name}: {e.Message}";
            }
        }

        var json = JsonSerializer.Serialize(new
        {
            projekt,
            zk = numerZk,
            duplikaty = duplikatyOpis,
            // true = ilosci pochodza z dokumentu bez znacznika RM_BAZA
            // (mogl go zalozyc recznie ktos inny) — patrz Znacznik.cs.
            obce_zk = obce,
            pozycji = pozycje.Count,
            pozycje,
            blad,
        }, new JsonSerializerOptions
        {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        });

        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return blad is null ? 0 : 1;
    }

    static T? Bezp<T>(Func<T?> f) { try { return f(); } catch { return default; } }

    internal record PozIlosc(string Symbol, decimal Ilosc);
}
