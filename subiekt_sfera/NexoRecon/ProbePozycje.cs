// Tryb "probe-pozycje" — SONDA: jak naprawdę usunąć pozycję z ZK. Diagnostyka.
//
//   NexoRecon.exe probe-pozycje --projekt=TEST-USUN-1 --numery="SYM1;SYM2" [--out=w.json] [--zapisz]
//
// Bez --zapisz: WYŁĄCZNIE ODCZYT. Zrzuca refleksją prawdziwe typy obiektu ZK,
// kolekcji `ob.Pozycje` (interfejsy, metody publiczne i JAWNE implementacje
// interfejsów przez GetInterfaceMap) oraz kolekcji EF `ob.Dane.Pozycje`.
//
// Z --zapisz: próbuje po kolei wariantów usunięcia pierwszej wskazanej pozycji
// i mówi, który przeszedł (z READ-BACK po Zapisz, bo Zapisz()==true nic nie dowodzi).
//
// ⛔ ZAPIS TYLKO NA ZK TESTOWYM: numer projektu MUSI zaczynać się od
// "TEST-USUN". Na każdym innym tryb odmawia niezależnie od flagi. To jest
// sonda na piaskownicy, nie narzędzie produkcyjne — gdy wariant się potwierdzi,
// trafia do Projekt.UsunPozycje, a ten plik zostaje jako dokumentacja.
//
// Po co (02.10.2026): ZkPozUsun szuka metody "Usun" przez GetType().GetMethods()
// na `ob.Pozycje` i jej nie znajduje; dokumentacja API (IPozycjeDokumentu) ma
// same Dodaj*. Hipotezy: (a) Usun/Remove jest JAWNĄ implementacją interfejsu
// (GetMethods jej nie pokazuje), (b) działa Remove na kolekcji EF Dane.Pozycje,
// (c) jest metoda o innej nazwie na ob/ob.Dane. Sonda rozstrzyga, zamiast zgadywać.
//
// USTALENIA PIERWSZEJ RUNDY (02.10.2026, ZK testowe):
//   * `ob.Pozycje` zwraca SAM obiekt biznesowy (ZamowienieOdKlientaBO implementuje
//     IPozycjeDokumentu) — stąd szukanie "Usun" na nim trafiało w metody BO.
//   * `ob.Dane.Pozycje` to WrappedEntityCollection<PozycjaDokumentu> z Remove(poz).
//   * Dopasowanie po słowach kluczowych łapało ŚMIECI (OnUsunietoPozycjePromocyjna,
//     UsunRezerwacje, ...Cleared) — każde „udane", każde z Zapisz() na TYM SAMYM
//     obiekcie, więc gdy doszło do Remove, zapis padł na OptimisticConcurrency.
//     Stąd druga runda: filtr bez szumu, Remove pierwszy, ŚWIEŻY BO na każdy wariant.

using System.Collections;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.Json;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class ProbePozycje
{
    static readonly string[] SLOWA = { "usun", "remove", "delete", "wyczysc", "clear", "odlacz", "odepnij", "detach" };
    static readonly string[] SZUM_START = { "on", "get_", "set_", "remove_", "add_" };
    static readonly string[] SZUM_W = { "cleared", "clearing", "rezerwacj", "bledy", "error", "promocyj", "domain", "allow", "check" };

    public static int Uruchom(Uchwyt sfera, string? projekt, string? numery, string? outPath, bool zapisz)
    {
        var szukany = (projekt ?? "").Trim();
        var kroki = new List<object>();
        var dump = new Dictionary<string, object?>();
        if (szukany.Length == 0) { Wypisz(new { blad = "brak --projekt=" }, outPath); return 1; }

        var szukane = (numery ?? "").Split(';', StringSplitOptions.RemoveEmptyEntries)
            .Select(s => s.Trim().ToUpperInvariant()).Where(s => s.Length > 0).ToHashSet();

        var testowy = szukany.StartsWith("TEST-USUN", StringComparison.OrdinalIgnoreCase);
        if (zapisz && !testowy)
        {
            Wypisz(new { blad = "zapis dozwolony TYLKO na projekcie TEST-USUN*", projekt = szukany }, outPath);
            return 1;
        }

        try
        {
            var (dokument, _dupl) = Projekt.ZnajdzZkProjektu(sfera, szukany);
            if (dokument == null) { Wypisz(new { blad = "nie znaleziono ZK projektu", projekt = szukany }, outPath); return 1; }
            var zamowienia = sfera.ZamowieniaOdKlientow();
            string? zkNumer = Bezp(() => dokument.NumerWewnetrzny?.PelnaSygnatura);

            // ── ZRZUT TYPÓW (na osobnym, zaraz zamykanym obiekcie) ─────────
            List<string> nazwy;
            string? sym0 = null;
            using (var ob = zamowienia.Znajdz(dokument))
            {
                object obObj = ob;
                var (kol, dane, danePoz) = Skladowe(obObj);
                dump["ob.type"] = obObj.GetType().FullName;
                dump["ob.Pozycje.type"] = kol?.GetType().FullName;
                dump["ob.Dane.type"] = dane?.GetType().FullName;
                dump["ob.Dane.Pozycje.type"] = danePoz?.GetType().FullName;
                dump["ob.metody_pasujace"] = MetodyPasujace(obObj);
                dump["ob.Dane.Pozycje.metody_pasujace"] = danePoz is null ? null : MetodyPasujace(danePoz);

                object? poz0 = ZnajdzPozycje(danePoz, szukane, out sym0);
                nazwy = poz0 is null ? new List<string>()
                                     : Warianty(obObj, kol, dane, danePoz, poz0).Select(w => w.Item1).ToList();
                dump["warianty"] = nazwy;
                if (poz0 is null && szukane.Count > 0)
                    kroki.Add(new { krok = "cele", ile = 0, uwaga = "zadna z podanych pozycji nie stoi na ZK" });
            }

            // ── PRÓBY USUNIĘCIA (tylko --zapisz i TEST-USUN) ──────────────
            // Każdy wariant dostaje ŚWIEŻY obiekt biznesowy i świeżo odszukaną
            // pozycję — po nieudanym Zapisz() BO jest nieświeży i każdy kolejny
            // zapis pada na OptimisticConcurrencyException.
            string? udany = null;
            if (zapisz && sym0 != null)
            {
                foreach (var nazwa in nazwy)
                {
                    var (dokN, _) = Projekt.ZnajdzZkProjektu(sfera, szukany);
                    if (dokN == null) { kroki.Add(new { krok = "koniec", powod = "ZK znikło?" }); break; }
                    using var ob2 = zamowienia.Znajdz(dokN);
                    object ob2o = ob2;
                    var (kol2, dane2, danePoz2) = Skladowe(ob2o);
                    var poz2 = ZnajdzPozycje(danePoz2, new HashSet<string> { sym0.ToUpperInvariant() }, out _);
                    if (poz2 == null) { kroki.Add(new { krok = "koniec", powod = "pozycji juz nie ma na ZK" }); break; }

                    var w = Warianty(ob2o, kol2, dane2, danePoz2, poz2).FirstOrDefault(x => x.Item1 == nazwa);
                    if (w.Item2 == null)
                    {
                        kroki.Add(new { krok = "proba", symbol = sym0, wariant = nazwa, wynik = "wariant niedostepny na swiezym obiekcie" });
                        continue;
                    }

                    string wynik;
                    try { wynik = w.Item2() ? "wywolane" : "metoda zwrocila false"; }
                    catch (Exception ex) { wynik = $"wyjatek {Rdzen(ex).GetType().Name}: {Rdzen(ex).Message}"; }
                    kroki.Add(new { krok = "proba", symbol = sym0, wariant = nazwa, wynik });
                    if (wynik != "wywolane") continue;

                    bool zapisano; string? bledy = null;
                    try { zapisano = ob2.Zapisz(); if (!zapisano) bledy = Bezp(ob2.PodajBledy); }
                    catch (Exception ex) { zapisano = false; bledy = $"{Rdzen(ex).GetType().Name}: {Rdzen(ex).Message}"; }
                    kroki.Add(new { krok = "zapisz", symbol = sym0, wariant = nazwa, zapisano, bledy });
                    if (!zapisano) continue;

                    // READ-BACK z bazy: czy pozycja naprawdę zniknęła.
                    var (dokR, _) = Projekt.ZnajdzZkProjektu(sfera, szukany);
                    var zostalo = dokR == null ? -1 : Projekt.CzytajPozycjeZk(dokR.Pozycje).Keys
                        .Count(k => k.Trim().ToUpperInvariant() == sym0.ToUpperInvariant());
                    kroki.Add(new { krok = "read-back", symbol = sym0, wariant = nazwa, zostalo_pozycji_o_tym_symbolu = zostalo });
                    if (zostalo == 0) { udany = nazwa; break; }
                }
                kroki.Add(new { krok = "wynik", symbol = sym0, udany_wariant = udany ?? "ZADEN" });
            }

            Wypisz(new { projekt = szukany, zk = zkNumer, zapisz, testowy, udany_wariant = udany, dump, kroki }, outPath);
            return 0;
        }
        catch (Exception ex)
        {
            Wypisz(new { blad = $"{Rdzen(ex).GetType().Name}: {Rdzen(ex).Message}", dump, kroki }, outPath);
            return 1;
        }
    }

    static (object? kol, object? dane, object? danePoz) Skladowe(object ob)
    {
        var kol = ob.GetType().GetProperty("Pozycje")?.GetValue(ob);
        var dane = ob.GetType().GetProperty("Dane")?.GetValue(ob);
        var danePoz = dane?.GetType().GetProperty("Pozycje")?.GetValue(dane);
        return (kol, dane, danePoz);
    }

    /// Pierwsza pozycja z Dane.Pozycje, której symbol jest w `szukane`.
    static object? ZnajdzPozycje(object? danePoz, HashSet<string> szukane, out string? symbol)
    {
        symbol = null;
        if (danePoz is not IEnumerable en || szukane.Count == 0) return null;
        foreach (var poz in en)
        {
            var sym = (Bezp(() => (string?)((dynamic)poz).AsortymentAktualny?.Symbol) ?? "").Trim();
            if (szukane.Contains(sym.ToUpperInvariant())) { symbol = sym; return poz; }
        }
        return null;
    }

    /// Warianty usunięcia — od najbardziej obiecującego.
    static IEnumerable<(string, Func<bool>)> Warianty(object ob, object? kol, object? dane, object? danePoz, object poz)
    {
        // B) Remove na kolekcji EF Dane.Pozycje — NAJPIERW: jedyny kandydat,
        //    który w pierwszej rundzie w ogóle wyglądał na usuwanie pozycji.
        //    Tylko implementacja klasy (nie duplikat z mapy interfejsu).
        if (danePoz != null)
            foreach (var mi in WszystkieMetody(danePoz).Where(m => m.Name == "Remove" && m.GetParameters().Length == 1
                                                                 && m.GetParameters()[0].ParameterType.IsInstanceOfType(poz)
                                                                 && m.DeclaringType?.IsInterface == false))
            {
                var m = mi; yield return ($"ob.Dane.Pozycje.{m.DeclaringType?.Name}.{m.Name}(poz)", () => Wywolaj(m, danePoz, poz));
            }
        // A) metody o pasującej nazwie na ob.Pozycje / ob / ob.Dane przyjmujące pozycję
        foreach (var (nazwa, cel) in new[] { ("ob.Pozycje", kol), ("ob", ob), ("ob.Dane", dane) })
        {
            if (cel == null) continue;
            foreach (var mi in WszystkieMetody(cel).Where(m => Pasuje(m.Name) && m.GetParameters().Length == 1
                                                             && m.GetParameters()[0].ParameterType.IsInstanceOfType(poz)))
            {
                var m = mi; var c = cel; yield return ($"{nazwa}.{m.DeclaringType?.Name}.{m.Name}(poz)", () => Wywolaj(m, c, poz));
            }
        }
        // D) pozycja sama o sobie: poz.Usun() / poz.DetachFromParent()
        foreach (var mi in WszystkieMetody(poz).Where(m => Pasuje(m.Name) && m.GetParameters().Length == 0))
        {
            var m = mi; yield return ($"poz.{m.DeclaringType?.Name}.{m.Name}()", () => Wywolaj(m, poz, null));
        }
    }

    static bool Wywolaj(MethodInfo m, object cel, object? arg)
    {
        var r = m.Invoke(cel, arg is null ? Array.Empty<object>() : new[] { arg });
        return r is not bool b || b;
    }

    /// Nazwa wygląda na usuwanie POZYCJI, a nie na zdarzenie, getter czy czyszczenie błędów.
    static bool Pasuje(string nazwa)
    {
        var n = nazwa.ToLowerInvariant();
        var krotka = n.Contains('.') ? n[(n.LastIndexOf('.') + 1)..] : n;
        if (SZUM_START.Any(p => krotka.StartsWith(p))) return false;
        if (SZUM_W.Any(w => krotka.Contains(w))) return false;
        return SLOWA.Any(w => krotka.Contains(w));
    }

    /// Metody publiczne + niepubliczne + JAWNE implementacje interfejsów (przez GetInterfaceMap).
    static List<MethodInfo> WszystkieMetody(object o)
    {
        var t = o.GetType();
        var lista = new List<MethodInfo>(t.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance));
        foreach (var itf in t.GetInterfaces())
        {
            try { lista.AddRange(t.GetInterfaceMap(itf).InterfaceMethods); } catch { }
        }
        return lista.GroupBy(m => Sygnatura(m) + "|" + m.DeclaringType?.FullName).Select(g => g.First()).ToList();
    }

    static List<string> MetodyPasujace(object o) =>
        WszystkieMetody(o).Where(m => Pasuje(m.Name)).Select(m => $"{m.DeclaringType?.Name}.{Sygnatura(m)}")
                          .Distinct().OrderBy(x => x).ToList();

    static string Sygnatura(MethodInfo m) =>
        $"{m.Name}({string.Join(", ", m.GetParameters().Select(p => p.ParameterType.Name))})";

    static Exception Rdzen(Exception ex) { while (ex is TargetInvocationException t && t.InnerException != null) ex = t.InnerException; return ex; }
    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    static void Wypisz(object obj, string? outPath)
    {
        var json = JsonSerializer.Serialize(obj, new JsonSerializerOptions
        {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
    }
}
