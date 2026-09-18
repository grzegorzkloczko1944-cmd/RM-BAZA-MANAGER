// Tryb "efaktury" — KOLEJKA ODBIORU e-Faktur KSeF. Tylko odczyt.
//
//   NexoRecon.exe efaktury [--limit=200] [--out=w.json]
//
// ⚠️ To INNA kartoteka niz tryb "faktury". Tamten czyta `DokumentyZakupu()`,
// czyli FZ juz istniejace w Subiekcie. TUTAJ czytamy `DokumentyElektroniczne()`
// — to, co widac w module „Krajowy System e-Faktur → Odbior". Faktury z
// zakladki DO PRZETWORZENIA NIE SA jeszcze dokumentami Subiekta, wiec tamtedy
// ich nie widac wcale (18.09.2026).
//
// `StatusPrzetworzenia` odwzorowuje zakladki modulu 1:1:
//   1 DoPrzetworzeniaWKsiegowosci, 2 DoPrzetworzeniaWSubiekcie (DO PRZETWORZENIA),
//   3 Przetworzona, 4 PrzetworzonaRecznie, 5 Nieokreslony, 6 Odrzucona.
//
// FLAGA (kolorowa gwiazdka w kolumnie „Flaga") jest KONFIGUROWALNA przez
// uzytkownika — kolor sam w sobie nic nie znaczy poza ta instalacja. Dlatego
// zwracamy komplet: kolor, nazwe slownikowa i opis nadany na dokumencie,
// a znaczenie ustala GUI/czlowiek. NIE zaszywac tu „zielona = realizuje".

using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Dokumenty.Logistyka;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class EFaktury
{
    public static int Uruchom(Uchwyt sfera, int limit, string? outPath)
    {
        var wynik = new List<EFak>();
        var kartoteka = sfera.DokumentyElektroniczne();
        try
        {
            foreach (var d in kartoteka.Dane.Wszystkie()
                                   .OrderByDescending(x => x.Id)
                                   .Take(limit).ToList())
            {
                // Flaga to wlasciwosci NAWIGACYJNE — bywaja null i moga
                // wymagac doczytania; kazde dotkniecie osobno w try.
                var flagaKolor = Bezp(() => d.FlagaWlasna?.Kolor) ?? "";
                var flagaNazwa = Bezp(() => d.FlagaWlasna?.Nazwa) ?? "";
                var flagaOpis = Bezp(() => d.FlagHeader?.Description) ?? "";

                // ⚠️ NIE czytamy `d.Xml` — to byte[] z trescia w postaci, ktorej
                // nie da sie odczytac wprost (ani UTF-8, ani gzip/zlib; 1576
                // bajtow szumu na cala fakture, 18.09.2026). Od tego jest
                // `PobierzDane`, ktore zwraca gotowy obiekt danych e-Faktury.
                var pozycje = new List<PozEFak>();
                var wz = "";
                var zamowienia = "";
                try
                {
                    var dane = kartoteka.PobierzDane(d);
                    if (dane != null)
                    {
                        foreach (var w in dane.Wiersze ?? Enumerable.Empty<IDaneWierszaFaktury>())
                        {
                            pozycje.Add(new PozEFak(
                                // ⚠️ `LP` to STRING (numer wiersza z faktury,
                                // moze byc "1.1"), nie liczba — oddajemy tekstem.
                                Bezp(() => w.LP) ?? "",
                                Bezp(() => w.NazwaTowaru) ?? "",
                                Bezp(() => w.Indeks) ?? "",
                                Bezp(() => w.JednostkaMiary) ?? "",
                                Kwota(() => w.Ilosc),
                                KwotaN(() => w.CenaNetto),
                                KwotaN(() => w.WartoscNetto),
                                Bezp(() => w.StawkaVat?.ToString()) ?? ""));
                        }
                        // Numery WZ i zamowien — klucz do zestawienia z PZ.
                        wz = Zlacz(() => dane.WydaniaZewnetrzne);
                        zamowienia = Zlacz(() => dane.NumeryZamowien);
                    }
                }
                catch (Exception ex) { Console.WriteLine("  (pozycje e-Faktury: " + ex.Message + ")"); }

                byte status = 0;
                try { status = d.StatusPrzetworzenia; } catch { }
                byte rodzaj = 0;
                try { rodzaj = d.Rodzaj; } catch { }

                wynik.Add(new EFak(
                    Bezp(() => d.NumerKSeF) ?? "",
                    Bezp(() => d.NumerDokumentu) ?? "",
                    Data(() => d.DataWystawienia),
                    Bezp(() => d.NazwaKlienta) ?? "",
                    Bezp(() => d.NIPSprzedawcy) ?? Bezp(() => d.NIPPodatnika) ?? "",
                    Kwota(() => d.Wartosc),
                    status,
                    NazwaStatusu(status),
                    rodzaj,
                    flagaKolor,
                    flagaNazwa,
                    flagaOpis,
                    // Id utworzonej FZ — gdy e-Faktura zostala juz przetworzona.
                    Liczba(() => d.DokumentPowiazanyId),
                    wz, zamowienia, pozycje,
                    pozycje.Count));
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine("Blad odczytu e-Faktur: " + ex.Message);
        }

        var json = JsonSerializer.Serialize(new { efaktury = wynik },
            new JsonSerializerOptions
            {
                WriteIndented = false,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    // Nazwy zakladek modulu Odbior — zeby GUI nie musialo znac numerow.
    static string NazwaStatusu(byte s) => s switch
    {
        1 => "Do przetworzenia w ksiegowosci",
        2 => "Do przetworzenia",
        3 => "Przetworzona",
        4 => "Przetworzona recznie",
        5 => "Nieokreslony",
        6 => "Odrzucona",
        _ => "",
    };

    static string Data(Func<DateTime> f)
    {
        try { return f().ToString("yyyy-MM-dd", CultureInfo.InvariantCulture); }
        catch { return ""; }
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }
    static decimal Kwota(Func<decimal> f) { try { return decimal.Round(f(), 2); } catch { return 0; } }

    //: To samo dla pol nullowalnych — na wierszu e-Faktury ceny sa decimal?,
    //: a ilosc juz nie. Bez tego kompilator odbija kazde uzycie.
    static decimal KwotaN(Func<decimal?> f) { try { return decimal.Round(f() ?? 0, 2); } catch { return 0; } }
    static int Liczba(Func<int?> f) { try { return f() ?? 0; } catch { return 0; } }

    static string Zlacz(Func<IEnumerable<string>?> f)
    {
        try { return string.Join(", ", f() ?? Enumerable.Empty<string>()); }
        catch { return ""; }
    }

    internal record EFak(string NumerKSeF, string NumerDokumentu, string DataWystawienia,
                         string Sprzedawca, string Nip, decimal Wartosc,
                         byte Status, string StatusNazwa, byte Rodzaj,
                         string FlagaKolor, string FlagaNazwa, string FlagaOpis,
                         int DokumentPowiazanyId, string WydaniaZewnetrzne,
                         string NumeryZamowien, List<PozEFak> Pozycje, int PozycjiIle);

    internal record PozEFak(string Lp, string Nazwa, string Indeks, string Jm,
                            decimal Ilosc, decimal CenaNetto, decimal WartoscNetto,
                            string StawkaVat);
}
