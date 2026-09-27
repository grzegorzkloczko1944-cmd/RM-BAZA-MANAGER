// Tryb "zdjecie" — GALERIA ZDJĘĆ kartoteki asortymentu. Czyta i ZAPISUJE.
//
//   NexoRecon.exe zdjecie --plan=plan.json [--out=w.json] [--zapisz]
//
// Bez --zapisz to suchy przebieg: mówi, co by zrobił, i NIC nie zmienia.
// Sam ODCZYT (akcja "lista") działa zawsze — nie wymaga --zapisz.
//
// plan.json:
//   { "akcja": "lista",   "symbol": "016-100.05" }
//   { "akcja": "dodaj",   "symbol": "016-100.05", "pliki": ["C:\\foto\\a.jpg"] }
//   { "akcja": "dodaj",   "symbol": "016-100.05",
//     "nazwa": "uchwyt.png", "typ": "png", "dane_b64": "iVBORw0..." }
//   { "akcja": "usun",    "symbol": "016-100.05", "numery": [2] }
//   { "akcja": "glowne",  "symbol": "016-100.05", "numery": [1] }
//
// Po co: magazynier szuka „016-100.05", a nie wie, jak ta rzecz wygląda.
// Zdjęcie przy kartotece rozstrzyga to w sekundę — i jest widoczne dla
// WSZYSTKICH w Subiekcie, nie tylko na stanowisku, które je wgrało.
//
// ⚠️ MINIATURY ROBI SUBIEKT SAM. API przyjmuje tylko oryginał
// (DodajZdjecie), a oddaje i oryginał, i miniaturę
// (IZdjecie.PobierzZawartosc / PobierzZawartoscMiniatury) — nie ma metody
// „dodaj miniaturę". Tak samo Szerokosc/Wysokosc/RozmiarBajty/Typ są
// tylko do odczytu: wypełnia je Subiekt przy zapisie. Nic nie skalujemy
// po naszej stronie (dokumentacja Sfery 61.1, sprawdzone 27.09.2026).
//
// ⚠️ Galeria żyje na OBIEKCIE BIZNESOWYM, nie na encji: trzeba
// asort.Znajdz(encja), potem PobierzGalerieZdjec() i na końcu Zapisz() —
// tak samo jak przy polach własnych (PolaWlasne.cs).
//
// DWIE DROGI DODAWANIA są w API i obie tu obsługujemy:
//   DodajZdjecie(sciezka)            — plik widoczny dla SESJI SFERY,
//                                      czyli dla mostu, nie dla klienta;
//   DodajZdjecie(nazwa, typ, bajty)  — treść w żądaniu, działa zdalnie.
// Stały most chodzi na serwerze, a RM_BAZA na stacji — dlatego klient
// wysyła BAJTY (base64), nie ścieżkę. Ścieżka zostaje dla wywołań CLI
// uruchamianych na tej samej maszynie co Subiekt.

using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Zdjecia
{
    internal sealed class Plan
    {
        public string? Akcja { get; set; }
        public string? Symbol { get; set; }
        public List<string>? Pliki { get; set; }
        public string? Nazwa { get; set; }
        public string? Typ { get; set; }
        [JsonPropertyName("dane_b64")] public string? DaneB64 { get; set; }
        public List<int>? Numery { get; set; }
        /// <summary>Numer zdjęcia, dla którego dołączyć bajty miniatury
        /// (base64). Klient rysuje z tego podgląd — most chodzi na serwerze,
        /// więc pliku z dysku stacji i tak by nie zobaczył.</summary>
        public int? Miniatura { get; set; }
    }

    internal record Krok(string Symbol, string Status, string? Szczegoly);

    internal record Foto(int? Numer, string? Nazwa, string? Typ, int? Szerokosc,
                         int? Wysokosc, long? RozmiarBajty, bool Glowne,
                         int MiniaturaBajty);

    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }
        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;

        var symbol = (plan.Symbol ?? "").Trim();
        var akcja = (plan.Akcja ?? "lista").Trim().ToLowerInvariant();
        if (symbol.Length == 0) { Console.WriteLine("zdjecie: brak \"symbol\""); return 1; }

        var kroki = new List<Krok>();
        var zdjecia = new List<Foto>();
        var zmienione = 0;
        string? miniaturaB64 = null;

        var asort = sfera.Asortymenty();
        var enc = asort.Dane.WyszukajPoSymbolu(symbol);
        if (enc == null)
        {
            kroki.Add(new Krok(symbol, "blad", "nie ma takiej kartoteki"));
            return Wypisz(outPath, zapisz, akcja, symbol, zmienione, zdjecia, kroki, miniaturaB64);
        }

        try
        {
            using var ob = asort.Znajdz(enc);
            var galeria = ob.PobierzGalerieZdjec();
            if (galeria == null)
            {
                kroki.Add(new Krok(symbol, "blad", "ta kartoteka nie udostępnia galerii zdjęć"));
                return Wypisz(outPath, zapisz, akcja, symbol, zmienione, zdjecia, kroki, miniaturaB64);
            }

            switch (akcja)
            {
                case "lista":
                    break;                       // samo zebranie stanu, niżej

                case "dodaj":
                {
                    var zPliku = plan.Pliki ?? new List<string>();
                    var maBajty = !string.IsNullOrWhiteSpace(plan.DaneB64);
                    if (zPliku.Count == 0 && !maBajty)
                    {
                        kroki.Add(new Krok(symbol, "blad",
                            "brak zdjęcia: podaj \"pliki\" albo \"dane_b64\"+\"typ\""));
                        break;
                    }

                    foreach (var sciezka in zPliku)
                    {
                        // ⚠️ Plik musi być widoczny dla SESJI SFERY (most na
                        // serwerze), nie dla klienta — stąd jawny komunikat
                        // zamiast wyjątku z głębi SDK.
                        if (!File.Exists(sciezka))
                        {
                            kroki.Add(new Krok(symbol, "blad",
                                $"most nie widzi pliku: {sciezka} — wyślij zdjęcie jako dane_b64"));
                            continue;
                        }
                        if (!zapisz)
                        {
                            kroki.Add(new Krok(symbol, "do-dodania",
                                $"{Path.GetFileName(sciezka)} ({new FileInfo(sciezka).Length} B)"));
                            continue;
                        }
                        galeria.DodajZdjecie(sciezka);
                        zmienione++;
                        kroki.Add(new Krok(symbol, "dodane", Path.GetFileName(sciezka)));
                    }

                    if (maBajty)
                    {
                        byte[] bajty;
                        try { bajty = Convert.FromBase64String(plan.DaneB64!); }
                        catch (FormatException)
                        {
                            kroki.Add(new Krok(symbol, "blad", "dane_b64 nie są poprawnym base64"));
                            break;
                        }
                        var nazwa = (plan.Nazwa ?? "zdjecie").Trim();
                        var typ = (plan.Typ ?? Path.GetExtension(nazwa).TrimStart('.'))
                                  .Trim().TrimStart('.').ToLowerInvariant();
                        if (typ.Length == 0) typ = "jpg";
                        if (!zapisz)
                        {
                            kroki.Add(new Krok(symbol, "do-dodania",
                                $"{nazwa} ({bajty.Length} B, typ {typ})"));
                        }
                        else
                        {
                            galeria.DodajZdjecie(nazwa, typ, bajty);
                            zmienione++;
                            kroki.Add(new Krok(symbol, "dodane", $"{nazwa} ({bajty.Length} B)"));
                        }
                    }
                    break;
                }

                case "usun":
                case "glowne":
                {
                    var numery = new HashSet<int>(plan.Numery ?? new List<int>());
                    if (numery.Count == 0)
                    {
                        kroki.Add(new Krok(symbol, "blad", "brak \"numery\": [...]"));
                        break;
                    }
                    foreach (var z in galeria.PobierzZdjecia())
                    {
                        var nr = Bezp2(() => z.NumerZdjecia);
                        if (nr == null || !numery.Contains(nr.Value)) continue;
                        var opis = $"nr {nr} {Bezp(() => z.Nazwa)}";
                        if (!zapisz)
                        {
                            kroki.Add(new Krok(symbol,
                                akcja == "usun" ? "do-usuniecia" : "do-ustawienia", opis));
                            continue;
                        }
                        // OdlaczZdjecie, nie Usun — ta druga jest Obsolete
                        // od wersji 47 SDK.
                        if (akcja == "usun") galeria.OdlaczZdjecie(z);
                        else galeria.UstawJakoPodstawowe(z);
                        zmienione++;
                        kroki.Add(new Krok(symbol,
                            akcja == "usun" ? "odlaczone" : "ustawione-glowne", opis));
                    }
                    if (kroki.Count == 0)
                        kroki.Add(new Krok(symbol, "blad", "nie ma zdjęć o podanych numerach"));
                    break;
                }

                default:
                    kroki.Add(new Krok(symbol, "blad",
                        $"nieznana akcja \"{akcja}\" (lista / dodaj / usun / glowne)"));
                    break;
            }

            if (zapisz && zmienione > 0)
            {
                ob.Zapisz();
                var bledy = Bezp(ob.PodajBledy);
                if (!string.IsNullOrWhiteSpace(bledy))
                    kroki.Add(new Krok(symbol, "uwaga", bledy));
            }

            // Stan PO operacji — zawsze, żeby wołający nie musiał pytać drugi raz.
            foreach (var z in galeria.PobierzZdjecia())
            {
                var mini = 0;
                byte[]? miniBajty = null;
                try
                {
                    miniBajty = z.PobierzZawartoscMiniatury();
                    mini = (miniBajty ?? Array.Empty<byte>()).Length;
                }
                catch { }
                // Bajty TYLKO dla jednego, wskazanego zdjęcia — cała galeria
                // w base64 rozdęłaby odpowiedź bez potrzeby.
                if (plan.Miniatura != null && miniBajty is { Length: > 0 }
                    && Bezp2(() => z.NumerZdjecia) == plan.Miniatura)
                    miniaturaB64 = Convert.ToBase64String(miniBajty);
                zdjecia.Add(new Foto(
                    Bezp2(() => z.NumerZdjecia), Bezp(() => z.Nazwa), Bezp(() => z.Typ),
                    Bezp2(() => z.Szerokosc), Bezp2(() => z.Wysokosc),
                    Bezp3(() => z.RozmiarBajty),
                    Bezp2b(() => z.CzyGlowneZdjecie) ?? false, mini));
            }
        }
        catch (System.Reflection.TargetInvocationException tie) when (tie.InnerException != null)
        {
            kroki.Add(new Krok(symbol, "blad",
                $"{tie.InnerException.GetType().Name}: {tie.InnerException.Message}"));
        }
        catch (Exception e)
        {
            kroki.Add(new Krok(symbol, "blad", $"{e.GetType().Name}: {e.Message}"));
        }

        return Wypisz(outPath, zapisz, akcja, symbol, zmienione, zdjecia, kroki, miniaturaB64);
    }

    static int Wypisz(string? outPath, bool zapisz, string akcja, string symbol,
                      int zmienione, List<Foto> zdjecia, List<Krok> kroki,
                      string? miniaturaB64 = null)
    {
        var json = JsonSerializer.Serialize(
            new { zapisano = zapisz, akcja, symbol, zmienione, zdjecia, kroki,
                  miniatura_b64 = miniaturaB64 },
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
    static int? Bezp2(Func<int?> f) { try { return f(); } catch { return null; } }
    static bool? Bezp2b(Func<bool> f) { try { return f(); } catch { return null; } }
    static long? Bezp3(Func<long?> f) { try { return f(); } catch { return null; } }
}
