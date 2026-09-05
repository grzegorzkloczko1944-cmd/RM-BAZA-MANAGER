// Tryb "wydruk-recon" — ROZPOZNANIE, nie zapis do bazy.
//
//   NexoRecon.exe wydruk-recon --numer="ZD 7/09/2026" [--out=wynik.json] [--pdf=C:\sciezka]
//
// Pytanie: czy da się z RM_BAZA zrobić to, co Subiekt robi ręcznie — wygenerować
// PDF zamówienia do dostawcy i wysłać mailem? Dokumentacja SDK mówi, że tak:
//   sfera.Wydruki().Utworz(TypWzorcaWydruku) -> IWydruk
//   IWydruk.ParametryDrukowania (IWydrukParametry): SciezkaEksportu,
//       FormatEksportu, DostepneFormatyEksportu, WybranyWzorzec, ZastapPliki
//   IWydruk.ObiektDoWydruku = dokument
//   IWydruk.Eksport()  — "Eksportuj obiekt do pliku (czeka, aż operacja się wykona)"
//
// Ale dokumentacja nie mówi, KTÓRY TypWzorcaWydruku odpowiada ZD ani czy PDF jest
// wśród DostepneFormatyEksportu w konsoli bez GUI (wydruki nexo renderują się
// przez WPF/XPS — to główne ryzyko: silnik wydruku może wymagać kontekstu
// graficznego, którego proces konsolowy nie ma).
//
// Ten tryb NIC nie zapisuje do bazy Subiekta — tworzy najwyżej plik PDF na dysku.
// Wypisuje: dostępne formaty, wzorce, typ wzorca z konfiguracji dokumentu, oraz
// wynik próby eksportu (albo pełny wyjątek, jeśli się nie uda).

using System.IO;
using System.Reflection;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class WydrukRecon
{
    public static int Uruchom(Uchwyt sfera, string? numer, string? outPath, string? pdfDir)
    {
        var raport = new Dictionary<string, object?>();
        var kroki = new List<string>();

        // ── 1. Znajdź dokument ZD ──────────────────────────────────────────
        var zam = sfera.ZamowieniaDoDostawcow();
        var wszystkie = zam.Dane.Wszystkie()
            .OrderByDescending(d => d.DataWprowadzenia).Take(50).ToList();

        var dok = string.IsNullOrWhiteSpace(numer)
            ? wszystkie.FirstOrDefault()
            : wszystkie.FirstOrDefault(d =>
                (Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "")
                    .Contains(numer!, StringComparison.OrdinalIgnoreCase));

        if (dok == null)
        {
            raport["blad"] = "Nie znaleziono ZD" + (numer != null ? $" o numerze „{numer}”" : "");
            raport["dostepne"] = wszystkie.Take(10)
                .Select(d => Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura)).ToList();
            Wypisz(raport, outPath);
            return 1;
        }

        var sygnatura = Bezp(() => dok.NumerWewnetrzny?.PelnaSygnatura) ?? "";
        raport["dokument"] = sygnatura;
        raport["podmiot"] = Bezp(() => dok.Podmiot?.NazwaSkrocona);
        kroki.Add($"znaleziono ZD: {sygnatura}");

        // Adres e-mail dostawcy — bez niego wysyłka i tak nie ruszy. Nazwa pola
        // na Podmiocie nie jest oczywista, więc szukamy refleksją i przy okazji
        // wypisujemy, które właściwości w ogóle wyglądają na adres.
        try
        {
            var podm = dok.Podmiot;
            if (podm != null)
            {
                var polaEmail = podm.GetType().GetProperties()
                    .Where(p => p.Name.Contains("Mail", StringComparison.OrdinalIgnoreCase)
                             || p.Name.Contains("Email", StringComparison.OrdinalIgnoreCase))
                    .ToList();
                raport["pola_email_podmiotu"] = polaEmail.Select(p => p.Name).ToList();
                foreach (var p in polaEmail)
                {
                    var v = SzukajWlasciwosci(podm, p.Name)?.ToString();
                    if (!string.IsNullOrWhiteSpace(v)) { raport["email_dostawcy"] = v; break; }
                }
            }
        }
        catch { /* rozpoznanie — brak maila nie przerywa reszty */ }

        // ── 1b. Pola DAT na dokumencie — czy jest termin realizacji? ───────
        try
        {
            var polaDat = dok.GetType().GetProperties()
                .Where(p => p.PropertyType == typeof(DateTime) ||
                            p.PropertyType == typeof(DateTime?) ||
                            p.Name.Contains("Data", StringComparison.OrdinalIgnoreCase) ||
                            p.Name.Contains("Termin", StringComparison.OrdinalIgnoreCase))
                .ToList();
            raport["pola_dat"] = polaDat.Select(p =>
            {
                var v = SzukajWlasciwosci(dok, p.Name);
                return $"{p.Name} ({p.PropertyType.Name}) = {v?.ToString() ?? "null"}"
                       + (p.CanWrite ? " [zapisywalne]" : " [tylko odczyt]");
            }).ToList();
        }
        catch (Exception ex) { kroki.Add($"pola dat: {ex.Message}"); }

        // ── 2. Jaki typ wzorca wydruku ma ZD ───────────────────────────────
        // Dokumentacja: IKonfiguracjaObowiazujaca.TypWzorcaWydruku — czyli typ
        // bierze się z konfiguracji dokumentu, nie trzeba go zgadywać.
        object? typWzorca = null;
        try
        {
            var konf = sfera.Konfiguracje().DaneDomyslne.ZamowienieDoDostawcy;
            typWzorca = SzukajWlasciwosci(konf, "TypWzorcaWydruku");
            raport["typ_wzorca_z_konfiguracji"] = typWzorca?.ToString();
            kroki.Add($"typ wzorca z konfiguracji: {typWzorca?.ToString() ?? "BRAK"}");
        }
        catch (Exception ex)
        {
            kroki.Add($"nie udało się odczytać typu wzorca z konfiguracji: {ex.Message}");
        }

        // Fallback: poszukaj w enumie TypWzorcaWydruku pozycji dla ZD.
        if (typWzorca == null)
        {
            try
            {
                var enumTyp = AppDomain.CurrentDomain.GetAssemblies()
                    .SelectMany(a => { try { return a.GetTypes(); } catch { return Array.Empty<Type>(); } })
                    .FirstOrDefault(t => t.IsEnum && t.Name == "TypWzorcaWydruku");
                if (enumTyp != null)
                {
                    var nazwy = Enum.GetNames(enumTyp);
                    raport["enum_wszystkie_pozycje"] = nazwy.Length;
                    var pasujace = nazwy.Where(n =>
                        n.Contains("Zamowien", StringComparison.OrdinalIgnoreCase) ||
                        n.Contains("Dostaw", StringComparison.OrdinalIgnoreCase)).ToList();
                    raport["enum_kandydaci_ZD"] = pasujace;
                    kroki.Add($"kandydaci w enumie TypWzorcaWydruku: {string.Join(", ", pasujace)}");
                    var wybrany = pasujace.FirstOrDefault(n =>
                        n.Contains("DoDostawcy", StringComparison.OrdinalIgnoreCase))
                        ?? pasujace.FirstOrDefault();
                    if (wybrany != null) typWzorca = Enum.Parse(enumTyp, wybrany);
                }
                else kroki.Add("nie znaleziono enuma TypWzorcaWydruku w załadowanych zestawach");
            }
            catch (Exception ex) { kroki.Add($"przeszukanie enuma nieudane: {ex.Message}"); }
        }

        if (typWzorca == null)
        {
            raport["kroki"] = kroki;
            raport["wniosek"] = "Nie ustalono typu wzorca wydruku dla ZD.";
            Wypisz(raport, outPath);
            return 1;
        }

        // ── 3. Utwórz wydruk i zobacz, co oferuje ──────────────────────────
        try
        {
            var wydruki = sfera.Wydruki();
            var metodaUtworz = wydruki.GetType().GetMethods()
                .FirstOrDefault(m => m.Name == "Utworz" && m.GetParameters().Length == 1);
            if (metodaUtworz == null)
            {
                raport["blad"] = "IWydruki nie ma metody Utworz(typ)";
                raport["kroki"] = kroki;
                Wypisz(raport, outPath);
                return 1;
            }

            var wydruk = metodaUtworz.Invoke(wydruki, new[] { typWzorca });
            kroki.Add("utworzono IWydruk");

            var param = SzukajWlasciwosci(wydruk!, "ParametryDrukowania");
            if (param != null)
            {
                raport["formaty_eksportu"] = AsListaTekstow(SzukajWlasciwosci(param, "DostepneFormatyEksportu"));
                raport["dostepne_wzorce"] = AsListaTekstow(SzukajWlasciwosci(param, "DostepneWzorce"));
                raport["wybrany_wzorzec"] = SzukajWlasciwosci(param, "WybranyWzorzec")?.ToString();
                kroki.Add("odczytano parametry drukowania");
            }
            else kroki.Add("BRAK ParametryDrukowania na IWydruk");

            // ── 4. Próba eksportu do PDF ───────────────────────────────────
            if (param != null)
            {
                var katalog = pdfDir ?? Path.GetTempPath();
                Directory.CreateDirectory(katalog);
                var plik = Path.Combine(katalog,
                    $"{sygnatura.Replace('/', '-').Replace(' ', '_')}.pdf");

                Ustaw(wydruk!, "ObiektDoWydruku", dok);
                Ustaw(param, "SciezkaEksportu", katalog);
                Ustaw(param, "NazwaDokumentuUzytkownika",
                      Path.GetFileNameWithoutExtension(plik));
                Ustaw(param, "ZastapPliki", true);

                // FormatEksportu to string — wybierz PDF z dostępnych.
                var formaty = AsListaTekstow(SzukajWlasciwosci(param, "DostepneFormatyEksportu"));
                var pdfFormat = formaty?.FirstOrDefault(f =>
                    f.Contains("pdf", StringComparison.OrdinalIgnoreCase)) ?? "PDF";
                Ustaw(param, "FormatEksportu", pdfFormat);
                raport["uzyty_format"] = pdfFormat;

                // Weryfikacja, że ustawienia RZECZYWIŚCIE się przyjęły — przy
                // jawnej implementacji setter potrafi po cichu nic nie zrobić.
                raport["potwierdzenie"] = new Dictionary<string, string?>
                {
                    ["SciezkaEksportu"] = SzukajWlasciwosci(param, "SciezkaEksportu")?.ToString(),
                    ["FormatEksportu"] = SzukajWlasciwosci(param, "FormatEksportu")?.ToString(),
                    ["NazwaDokumentuUzytkownika"] = SzukajWlasciwosci(param, "NazwaDokumentuUzytkownika")?.ToString(),
                    ["ObiektDoWydruku"] = SzukajWlasciwosci(wydruk!, "ObiektDoWydruku") == null ? "NULL" : "ustawiony",
                };

                // Sygnatury Eksport() na konkretnej implementacji bywają inne niż
                // w dokumentacji interfejsu — wypisz je i wybierz tę bez parametrów,
                // a jak nie ma, tę z jednym parametrem listy (można podać null).
                // IWydruk bywa implementowany JAWNIE — wtedy GetType().GetMethods()
                // nic nie pokazuje. Metod trzeba szukać na samym interfejsie.
                var interfejsy = wydruk!.GetType().GetInterfaces();
                raport["interfejsy_wydruku"] = interfejsy.Select(i => i.Name).ToList();
                var kandydaci = interfejsy
                    .SelectMany(i => i.GetMethods())
                    .Concat(wydruk.GetType().GetMethods())
                    .Where(m => m.Name == "Eksport" || m.Name == "EksportAsync")
                    .ToList();
                raport["sygnatury_eksport"] = kandydaci
                    .Select(m => $"{m.Name}({string.Join(", ", m.GetParameters().Select(p => p.ParameterType.Name))})")
                    .ToList();

                var metodaEksport = kandydaci.FirstOrDefault(m => m.Name == "Eksport" && m.GetParameters().Length == 0)
                                 ?? kandydaci.FirstOrDefault(m => m.Name == "Eksport" && m.GetParameters().Length == 1);
                if (metodaEksport == null)
                {
                    kroki.Add("BRAK metody Eksport() — dostępne: " +
                              string.Join(" | ", (List<string>)raport["sygnatury_eksport"]!));
                }
                else
                {
                    try
                    {
                        var argi = metodaEksport.GetParameters().Length == 0
                            ? null : new object?[] { null };
                        metodaEksport.Invoke(wydruk, argi);
                        var sukces = SzukajWlasciwosci(wydruk, "OstatniaOperacjaZakonczonaSukcesem");
                        raport["eksport_sukces"] = sukces;
                        var powstale = Directory.GetFiles(katalog, "*.pdf")
                            .Where(f => File.GetLastWriteTime(f) > DateTime.Now.AddMinutes(-2))
                            .ToList();
                        raport["pliki_pdf"] = powstale;
                        raport["pdf_powstal"] = powstale.Count > 0;
                        kroki.Add(powstale.Count > 0
                            ? $"PDF POWSTAŁ: {string.Join(", ", powstale)}"
                            : "Eksport nie rzucił wyjątku, ale pliku PDF nie ma");

                        var bledy = wydruk.GetType().GetMethod("PobierzListeBledow");
                        if (bledy != null)
                            raport["bledy_wydruku"] = bledy.Invoke(wydruk, null)?.ToString();
                    }
                    catch (TargetInvocationException tie)
                    {
                        var w = tie.InnerException ?? tie;
                        raport["eksport_wyjatek"] = $"{w.GetType().Name}: {w.Message}";
                        raport["eksport_stack"] = w.StackTrace?.Split('\n').Take(6).ToArray();
                        kroki.Add($"EKSPORT RZUCIŁ: {w.GetType().Name}: {w.Message}");
                    }
                }
            }
        }
        catch (Exception ex)
        {
            var w = (ex as TargetInvocationException)?.InnerException ?? ex;
            raport["blad"] = $"{w.GetType().Name}: {w.Message}";
            raport["stack"] = w.StackTrace?.Split('\n').Take(6).ToArray();
        }

        // ── 5. Czy Sfera w ogóle umie wysłać maila ─────────────────────────
        try
        {
            var poczta = sfera.WiadomosciPocztowe();
            raport["poczta_typ"] = poczta.GetType().FullName;
            raport["poczta_metody"] = poczta.GetType().GetMethods()
                .Where(m => !m.IsSpecialName && m.DeclaringType == poczta.GetType())
                .Select(m => m.Name).Distinct().Take(25).ToList();
            var konta = sfera.KontaPocztowe();
            var lista = konta.GetType().GetProperty("Dane")?.GetValue(konta);
            // Wszystkie() bywa przeciążone (np. z parametrem filtra) — bierzemy
            // bezparametrowe, inaczej Invoke leci "Parameter count mismatch".
            var mWszystkie = lista?.GetType().GetMethods()
                .FirstOrDefault(m => m.Name == "Wszystkie" && m.GetParameters().Length == 0);
            var wszystkieKonta = mWszystkie?.Invoke(lista, null)
                as System.Collections.IEnumerable;
            var nazwyKont = new List<string>();
            if (wszystkieKonta != null)
                foreach (var k in wszystkieKonta)
                    nazwyKont.Add(SzukajWlasciwosci(k!, "Nazwa")?.ToString()
                                  ?? SzukajWlasciwosci(k!, "Adres")?.ToString() ?? "?");
            raport["konta_pocztowe"] = nazwyKont;
            kroki.Add($"kont pocztowych w Subiekcie: {nazwyKont.Count}");
        }
        catch (Exception ex) { kroki.Add($"poczta niedostępna: {ex.Message}"); }

        raport["kroki"] = kroki;
        Wypisz(raport, outPath);
        return 0;
    }

    // ── pomocnicze ─────────────────────────────────────────────────────────
    // Interfejsy Sfery bywają implementowane JAWNIE — wtedy GetType().GetProperty()
    // zwraca null, choć właściwość istnieje. Szukamy więc też po interfejsach.
    static PropertyInfo? Wlasciwosc(object obj, string nazwa)
    {
        var p = obj.GetType().GetProperty(nazwa);
        if (p != null) return p;
        foreach (var i in obj.GetType().GetInterfaces())
        {
            p = i.GetProperty(nazwa);
            if (p != null) return p;
        }
        return null;
    }

    static object? SzukajWlasciwosci(object obj, string nazwa)
    {
        try { return Wlasciwosc(obj, nazwa)?.GetValue(obj); }
        catch { return null; }
    }

    static void Ustaw(object obj, string nazwa, object? wartosc)
    {
        try
        {
            var p = Wlasciwosc(obj, nazwa);
            if (p != null && p.CanWrite) p.SetValue(obj, wartosc);
        }
        catch { /* rozpoznanie — nie przerywamy na jednej właściwości */ }
    }

    static List<string>? AsListaTekstow(object? o)
    {
        if (o == null) return null;
        if (o is System.Collections.IEnumerable en && o is not string)
        {
            var lista = new List<string>();
            foreach (var x in en) lista.Add(x?.ToString() ?? "");
            return lista;
        }
        return new List<string> { o.ToString() ?? "" };
    }

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    static void Wypisz(object raport, string? outPath)
    {
        var json = JsonSerializer.Serialize(raport, new JsonSerializerOptions
        {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
        });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
    }
}
