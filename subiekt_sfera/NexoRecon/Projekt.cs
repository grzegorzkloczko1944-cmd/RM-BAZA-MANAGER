// Tryb "projekt" — ZAPIS do Subiekta: kartoteki, komplety (Z/ZZ) i ZK projektu.
//
//   NexoRecon.exe projekt --plan=plan.json [--out=wynik.json] [--zapisz] [konfig.json]
//
// BEZ --zapisz to SUCHY PRZEBIEG: czyta Subiekta, mówi co by zrobił, nic nie zapisuje.
// Z --zapisz wykonuje operacje w kolejności: kartoteki → komplety Z → komplety ZZ → ZK.
//
// Kolejność nie jest przypadkowa (SUBIEKT_PROJEKTY_WYDANIA.md, sekcja 5):
// składnik musi istnieć w Subiekcie, zanim dodamy go do kompletu, a komplety Z
// muszą istnieć, zanim wejdą jako składniki do ZZ.
//
// Wejściowy plan.json (buduje go subiekt_projekt.py):
// {
//   "projekt": "2222", "tytul": "Projekt 2222 - Ceramizator",
//   "podmiot": "RMPAK",                       // NazwaSkrocona albo NIP
//   "pozycje": [ {"symbol":"013-100.220","nazwa":"Kątownik","typ":"Z","ilosc":2,
//                 "skladniki":[{"symbol":"013-100.221","ilosc":4}]} ]
// }
// typ: X|XX|Z|ZZ|STANDARD|ZNORMALIZOWANE — komplet powstaje TYLKO dla Z i ZZ.

using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using InsERT.Moria.ModelDanych;
using InsERT.Moria.Sfera;

namespace NexoRecon;

internal static class Projekt
{
    public static int Uruchom(Uchwyt sfera, string planPath, string? outPath, bool zapisz)
    {
        if (!File.Exists(planPath)) { Console.WriteLine($"BRAK PLANU: {planPath}"); return 1; }

        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;

        var asort = sfera.Asortymenty();
        var szablony = sfera.PodajObiektTypu<InsERT.Moria.Asortymenty.ISzablonyAsortymentu>();
        var kroki = new List<Krok>();

        // Mapa symboli już istniejących — jeden przelot, jak w Stan.cs.
        // Dopasowanie luźne (TRIM + ignorowanie wielkości liter), bo w bazie
        // są symbole ze spacją na końcu i różnicą a/A (plan, sekcja 12.2).
        // W TYM SAMYM przelocie bierzemy SKLAD kompletow. Suchy przebieg
        // porownuje sklad z BOM-u ze stanem w Subiekcie i robil to przez
        // asort.Znajdz(symbol) + podglad.Dane.SkladnikiKompletu OSOBNO dla
        // kazdego kompletu: 49 zlozen = 49 zapytan przez Sfere, ~5 s na jedno
        // przeliczenie ilosci (log mostu 09.09.2026: cmd=projekt srednia
        // 5275 ms przy 45 ms na cmd=komplet, ktory czyta to samo JEDNYM
        // zapytaniem LINQ — Komplet.cs). Jeden przelot kosztuje tyle, co
        // dotychczasowa mapa symboli.
        var luzne = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var skladWBazie = new Dictionary<string, List<(string, decimal)>>(StringComparer.OrdinalIgnoreCase);
        foreach (var a in asort.Dane.Wszystkie()
                     .Select(a => new
                     {
                         a.Symbol,
                         Sklad = a.SkladnikiKompletu.Select(s => new { s.Skladnik.Symbol, s.Ilosc }),
                     }).ToList())
        {
            var k = (a.Symbol ?? "").Trim();
            if (k.Length == 0) continue;
            luzne[k] = a.Symbol!;
            var lista = new List<(string, decimal)>();
            try
            {
                foreach (var s in a.Sklad)
                {
                    var sym = (s.Symbol ?? "").Trim();
                    if (sym.Length > 0) lista.Add((sym.ToUpperInvariant(), s.Ilosc));
                }
            }
            catch { /* kartoteka bez skladu albo uszkodzony wpis - pusty sklad */ }
            skladWBazie[k] = lista;
        }

        Asortyment? Znajdz(string symbol)
        {
            var s = (symbol ?? "").Trim();
            if (s.Length == 0) return null;
            var enc = asort.Dane.WyszukajPoSymbolu(s);
            if (enc == null && luzne.TryGetValue(s, out var realny))
                enc = asort.Dane.WyszukajPoSymbolu(realny);
            return enc;
        }

        // Czy kartoteka o tym symbolu ISTNIEJE — z mapy jednego przelotu,
        // bez pytania Sfery. WyszukajPoSymbolu to zapytanie do bazy; wolane
        // per pozycja (354) i per skladnik dawalo grubo ponad 400 zapytan na
        // KAZDY przebieg, choc odpowiedz siedzi juz w `luzne`
        // (09.09.2026: zapis i podglad "trwaja w chuj").
        bool Istnieje(string symbol)
        {
            var s = (symbol ?? "").Trim();
            return s.Length > 0 && luzne.ContainsKey(s);
        }

        // Czy sklad w Subiekcie jest DOKLADNIE taki jak w planie (para
        // symbol+ilosc, kolejnosc nieistotna). Uzywane i przez suchy przebieg,
        // i przez zapis — zeby zapis nie przepisywal od nowa czegos, o czym
        // podglad wlasnie powiedzial "bez zmian".
        bool SkladTakiSam(List<(string, decimal)> wBazie, List<SkladnikPlan> plan)
        {
            var zPlanu = plan
                .Select(x => (x.Symbol.Trim().ToUpperInvariant(), x.Ilosc <= 0 ? 1m : x.Ilosc))
                .OrderBy(x => x.Item1).ThenBy(x => x.Item2).ToList();
            var stare = wBazie.OrderBy(x => x.Item1).ThenBy(x => x.Item2).ToList();
            return zPlanu.Count == stare.Count
                   && zPlanu.Zip(stare, (a, b) => a.Item1 == b.Item1 && a.Item2 == b.Item2).All(x => x);
        }

        // Realny symbol z Subiekta (z zachowana wielkoscia liter i spacjami)
        // albo null. Z mapy jednego przelotu — bez pytania Sfery.
        string? RealnySymbol(string symbol)
        {
            var s = (symbol ?? "").Trim();
            if (s.Length == 0) return null;
            return luzne.TryGetValue(s, out var realny) ? realny : null;
        }

        // Sklad kompletu z jednego przelotu; null = nie ma takiej kartoteki.
        // Dopasowanie luzne tak samo jak w Znajdz (TRIM + ignorowanie a/A).
        List<(string, decimal)>? SkladZMapy(string symbol)
        {
            var s = (symbol ?? "").Trim();
            if (s.Length == 0) return null;
            return skladWBazie.TryGetValue(s, out var lista) ? lista : null;
        }

        var pozycje = plan.Pozycje ?? new List<PozPlan>();

        // ── 1. KARTOTEKI ──────────────────────────────────────────────────
        // Zakładane pojedynczo, symbol po symbolu (plan, krok 12) — nigdy
        // masową pętlą bez kontroli, bo to jedyne miejsce gdzie koszt zależy
        // od tego CO piszemy.
        foreach (var p in pozycje)
        {
            var istnieje = Istnieje(p.Symbol);
            if (istnieje) { kroki.Add(new Krok("kartoteka", p.Symbol, "istnieje", null)); continue; }

            if (!zapisz) { kroki.Add(new Krok("kartoteka", p.Symbol, "do-zalozenia", null)); continue; }

            try
            {
                using var ob = asort.Utworz();
                // Bez szablonu brakuje domyślnej jednostki miary (plan, krok 12).
                // Wzorzec z SDK\Przyklady\PrzykladyKartoteki\ObslugaKartotek.cs.
                // Pozycje typu Z/ZZ muszą dostać szablon Komplet — inaczej Sfera
                // odmawia później dodania składników (InvalidOperationException:
                // "Asortyment, do którego dodawane są składniki musi być kompletem",
                // znalezione na żywej Sferze 61.1.0.9431, M-OLD 2026-09-03).
                var jestKompletem = Rowne(p.Typ, "Z") || Rowne(p.Typ, "ZZ");
                ob.WypelnijNaPodstawieSzablonu(jestKompletem ? szablony.DaneDomyslne.Komplet : szablony.DaneDomyslne.Towar);
                ob.Dane.Symbol = p.Symbol.Trim();
                ob.Dane.Nazwa = string.IsNullOrWhiteSpace(p.Nazwa) ? p.Symbol.Trim() : p.Nazwa!.Trim();
                if (!ob.Zapisz())
                {
                    kroki.Add(new Krok("kartoteka", p.Symbol, "blad", Bezp(ob.PodajBledy)));
                    continue;
                }
                luzne[p.Symbol.Trim()] = p.Symbol.Trim();
                // Swiezo zalozona kartoteka nie ma jeszcze skladu — wpisujemy
                // pusty, zeby dalsze kroki czytaly mape, a nie Sfere.
                skladWBazie[p.Symbol.Trim()] = new List<(string, decimal)>();
                kroki.Add(new Krok("kartoteka", p.Symbol, "zalozona", null));
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok("kartoteka", p.Symbol, "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        // ── 2. KOMPLETY ───────────────────────────────────────────────────
        // Kolejność OD DOŁU DRZEWA: komplet musi istnieć, zanim wejdzie jako
        // składnik do nadrzędnego. Sortowanie po samym typie (Z przed ZZ) NIE
        // wystarcza — w realnych projektach ZZ zawiera ZZ (widziane w
        // "2607 Platyn": ZZ→ZZ 23 razy, drzewo na 4 poziomy, firma mówi o 6).
        // Stąd sortowanie topologiczne po faktycznym zagnieżdżeniu.
        foreach (var p in PosortujOdDolu(pozycje))
        {
                var skl = p.Skladniki ?? new List<SkladnikPlan>();
                if (skl.Count == 0)
                {
                    // Subiekt odrzuci komplet bez składników (NieZdefiniowanoSkladnikowKompletuBlad),
                    // więc nie próbujemy — zgłaszamy to jako pominięcie, nie błąd.
                    kroki.Add(new Krok("komplet", p.Symbol, "pominiety-brak-skladnikow", null));
                    continue;
                }

                if (!zapisz)
                {
                    var brakujace = skl.Where(s => !Istnieje(s.Symbol)).Select(s => s.Symbol).ToList();

                    // Czy ten komplet JUZ ma sklad w Subiekcie i czy sklad
                    // z BOM-u faktycznie sie od niego ROZNI?
                    //
                    // Zapis zawsze czysci i wpisuje od nowa (patrz "SKLAD =
                    // PLAN" nizej), wiec technicznie kazdy istniejacy komplet
                    // jest "zastepowany". Ale mowienie tego przy 25 kompletach,
                    // z ktorych 23 maja DOKLADNIE ten sam sklad, to falszywy
                    // alarm — user pyta "dlaczego zastepuje, skoro pozycje maja
                    // te same numery i nazwy" i ma racje (zgloszone 08.09.2026).
                    // Porownujemy wiec (symbol, ilosc) i mowimy prawde:
                    // "bez zmian" albo co konkretnie sie zmieni.
                    var juzMaSklad = 0;
                    var takiSam = false;
                    var staryOpis = new List<(string, decimal)>();
                    // Sklad z mapy zbudowanej jednym przelotem wyzej —
                    // zero zapytan do Sfery w petli po kompletach.
                    if (SkladZMapy(p.Symbol) is List<(string, decimal)> wBazie)
                    {
                        try
                        {
                            juzMaSklad = wBazie.Count;
                            staryOpis = wBazie;

                            // Rozstrzyga PARA (symbol, ilosc) — sama liczba
                            // skladnikow nie wystarczy: 4 na 4 moze znaczyc
                            // podmienioną pozycje albo zmieniona ilosc.
                            takiSam = SkladTakiSam(wBazie, skl);
                        }
                        catch { }
                    }

                    var status = juzMaSklad > 0
                                    ? (takiSam ? "bez-zmian" : "do-aktualizacji")
                               : brakujace.Count == 0 ? "do-utworzenia"
                               : "do-utworzenia-po-zalozeniu-skladnikow";
                    var opis = juzMaSklad > 0
                        ? (takiSam ? $"skład identyczny ({juzMaSklad} skł.) — nic się nie zmieni"
                                   : OpiszRoznice(staryOpis, skl))
                        : brakujace.Count == 0 ? $"{skl.Count} składników"
                                               : $"brak kartotek składników: {string.Join(", ", brakujace)}";
                    kroki.Add(new Krok("komplet", p.Symbol, status, opis));
                    continue;
                }

                try
                {
                    // Sklad JUZ identyczny → nie ruszamy kartoteki. Czyszczenie
                    // i wpisywanie od nowa dawalo ten sam stan koncowy, ale
                    // kosztowalo otwarcie + zapis kartoteki przez Sfere dla
                    // KAZDEGO kompletu: 49 zlozen projektu 3000 = ~10 s na
                    // zapis, w ktorym nic sie nie zmienialo (09.09.2026).
                    // Podglad juz to wykrywal i pisal "bez zmian" — zapis
                    // przepisywal mimo to.
                    if (SkladZMapy(p.Symbol) is List<(string, decimal)> wBazieZ
                        && wBazieZ.Count > 0 && SkladTakiSam(wBazieZ, skl))
                    {
                        kroki.Add(new Krok("komplet", p.Symbol, "bez-zmian",
                                           $"skład identyczny ({wBazieZ.Count} skł.) — pominięto"));
                        continue;
                    }

                    var enc = Znajdz(p.Symbol);
                    if (enc == null) { kroki.Add(new Krok("komplet", p.Symbol, "blad", "brak kartoteki")); continue; }

                    using var ob = asort.Znajdz(enc);

                    // SKLAD = PLAN, nie "plan dopisany do tego, co juz bylo".
                    //
                    // Dodaj() nie sprawdza, czy skladnik juz jest — dopisuje
                    // kolejny wiersz. Drugie zalozenie tego samego kompletu
                    // (poprawka projektu albo drugi projekt z tymi samymi
                    // numerami rysunkow — u nas normalne, zespoly sie
                    // powtarzaja) dawalo wiec kazdy skladnik PODWOJNIE, a
                    // Subiekt liczyl z tego podwojne zapotrzebowanie. Znalezione
                    // 06.09.2026: 25 kompletow, wszystkie x2, zero czystych.
                    //
                    // Kartoteka opisuje, z czego sklada sie CZESC — to fakt
                    // konstrukcyjny z drzewka Inventora, nie projektowy. Wiec
                    // zrodlem prawdy jest plan: czyscimy i wpisujemy od nowa.
                    // Operacja jest przez to powtarzalna: drugi raz da ten sam
                    // wynik, a nie podwojony.
                    var wyczyszczono = WyczyscSklad(ob);

                    var dodane = 0;
                    var pominiete = new List<string>();
                    foreach (var s in skl)
                    {
                        var sEnc = Znajdz(s.Symbol);
                        if (sEnc == null) { pominiete.Add(s.Symbol); continue; }
                        // Dodaj(Asortyment, Decimal) — ilość w podstawowej jednostce miary.
                        ob.Skladniki.Dodaj(sEnc, s.Ilosc <= 0 ? 1m : s.Ilosc);
                        dodane++;
                    }
                    if (dodane == 0)
                    {
                        kroki.Add(new Krok("komplet", p.Symbol, "blad",
                            "żaden składnik nie ma kartoteki: " + string.Join(", ", pominiete)));
                        continue;
                    }
                    // Lp 1..N od razu — po wyczyszczeniu i dopisaniu Subiekt
                    // nadalby kolejne numery po starych (np. 23..33).
                    KompletNapraw.Przenumeruj(ob);
                    if (!ob.Zapisz())
                    {
                        kroki.Add(new Krok("komplet", p.Symbol, "blad", Bezp(ob.PodajBledy)));
                        continue;
                    }
                    var uwaga = pominiete.Count > 0 ? $"pominięto bez kartoteki: {string.Join(", ", pominiete)}" : null;
                    // "zaktualizowany" mowi, ze komplet JUZ mial sklad i zostal
                    // nadpisany — user widzi, ze to nie pierwsze zalozenie.
                    kroki.Add(new Krok("komplet", p.Symbol,
                        wyczyszczono > 0 ? $"zaktualizowany ({dodane} skl., zastąpiono {wyczyszczono})"
                                         : $"utworzony ({dodane} skl.)", uwaga));
                }
                catch (Exception ex)
                {
                    kroki.Add(new Krok("komplet", p.Symbol, "blad", $"{ex.GetType().Name}: {ex.Message}"));
                }
        }

        // ── 3. ZK ─────────────────────────────────────────────────────────
        string? zkNumer = null;
        if (!zapisz)
        {
            // Podgląd musi powiedzieć, czy powstanie NOWE ZK, czy dopiszemy do
            // istniejącego — to zupełnie inny skutek dla użytkownika.
            var (juzJest, duplikaty) = ZnajdzZkProjektu(sfera, plan.Projekt);
            if (duplikaty.Count > 0)
                kroki.Add(new Krok("zk", plan.Projekt ?? "", "UWAGA-DUPLIKATY",
                    $"projekt ma już {duplikaty.Count + 1} dokumenty ZK: "
                    + string.Join(", ", new[] { NumerZk(juzJest) }.Concat(duplikaty.Select(NumerZk)))
                    + " — zanim cokolwiek zapiszesz, ustal ręcznie z którym dokumentem pracujesz"));

            if (juzJest != null)
            {
                // Symbol ORAZ ilość. Sam HashSet symboli nie odróżniał 4 od 10,
                // więc zmiana ilości w BOM-ie przechodziła jako „bez zmian”,
                // a zapis i tak jej nie przenosił (zgłoszone 08.09.2026).
                var naZk = CzytajPozycjeZk(juzJest.Pozycje);
                var nowe = 0;
                var prodPominiete = 0;
                foreach (var p in pozycje)
                {
                    // Ten sam filtr co w pętli zapisu — podgląd nie może
                    // zapowiadać dopisania pozycji, której zapis nie doda.
                    if (p.ProdukcjaWlasna) { prodPominiete++; continue; }
                    var e = Znajdz(p.Symbol);
                    if (e == null) continue;
                    var sym = (e.Symbol ?? "").Trim();
                    if (!naZk.TryGetValue(sym, out var naDok)) { nowe++; continue; }

                    // Zapowiedź tego, co zrobi zapis: uzupełni ilość do stanu
                    // z BOM-u (dopisując różnicę) albo zostawi, gdy na ZK jest
                    // WIĘCEJ — bo tego nie zabieramy (patrz pętla zapisu).
                    var zBomu = p.Ilosc < 0 ? 0m : p.Ilosc;
                    if (zBomu > naDok)
                        kroki.Add(new Krok("zk-poz", sym, "do-uzupelnienia",
                            $"na ZK: {Ilo(naDok)} → ustawi {Ilo(zBomu)} "
                            + $"({Roznica(zBomu, naDok)})"));
                    else if (zBomu < naDok)
                        // Zmniejszenie to osobna kategoria — user musi je
                        // zobaczyć wyraźnie, bo zabiera coś z dokumentu
                        // księgowego (0 = wyzerowanie pozycji).
                        kroki.Add(new Krok("zk-poz", sym, "do-zmniejszenia",
                            $"na ZK: {Ilo(naDok)} → ustawi {Ilo(zBomu)} "
                            + $"({Roznica(zBomu, naDok)})"
                            + (zBomu == 0 ? " — POZYCJA WYZEROWANA" : "")));
                }
                var doUzupelnienia = kroki.Count(k => k.Rodzaj == "zk-poz"
                                                      && k.Status == "do-uzupelnienia");
                var doZmniejszenia = kroki.Count(k => k.Rodzaj == "zk-poz"
                                                      && k.Status == "do-zmniejszenia");
                var numer = Bezp(() => juzJest.NumerWewnetrzny?.PelnaSygnatura) ?? "";
                kroki.Add(new Krok("zk", numer, "do-dopisania",
                    $"dopisze {nowe} poz."
                    + (doUzupelnienia > 0 ? $", zwiększy ilość w {doUzupelnienia} poz." : "")
                    + (doZmniejszenia > 0 ? $", ZMNIEJSZY ilość w {doZmniejszenia} poz." : "")
                    + $" ({naZk.Count} już na dokumencie)"
                    + (prodPominiete > 0 ? $", {prodPominiete} poz. produkcji własnej pominięto" : "")));
            }
            else
            {
                // Produkcja własna nie wchodzi na ZK — podgląd MUSI liczyć tak
                // samo jak zapis. Inaczej suchy przebieg mówi „211 pozycji",
                // a dokument dostaje 180 i user dowiaduje się o różnicy po
                // fakcie (zasada „nic po cichu").
                var prod = pozycje.Count(p => p.ProdukcjaWlasna);
                var doZk = pozycje.Count - prod;
                kroki.Add(new Krok("zk", plan.Projekt ?? "", "do-utworzenia",
                    $"{doZk} pozycji, podmiot: {plan.Podmiot}"
                    + (prod > 0 ? $" ({prod} poz. produkcji własnej pominięto — idą na PW)" : "")));
            }
        }
        else
        {
            try
            {
                var zam = sfera.ZamowieniaOdKlientow();

                // Czy ten projekt ma już ZK? Szukamy po Uwagach — tam wpisujemy
                // numer projektu. Bez tego ponowne uruchomienie robiło DRUGI
                // dokument dla tego samego projektu i rozbijało zapotrzebowanie
                // na dwa (zgłoszone 04.09.2026: „chcę dorzucić resztę").
                var (istniejace, duplikaty) = ZnajdzZkProjektu(sfera, plan.Projekt);

                // Dwa+ ZK dla tego samego projektu to dokładnie ten balagan,
                // przed ktorym ma chronic dopasowanie po Uwagach — jesli mimo
                // to powstaly (rozne zrodla: reczne zalozenie w GUI, zbieg
                // dwoch uzytkownikow, stary limit Take(100) sprzed naprawy
                // 07.09.2026), NIE zgadujemy do ktorego dopisac. Zatrzymujemy
                // sie i oddajemy decyzje czlowiekowi.
                if (duplikaty.Count > 0)
                {
                    var numery = string.Join(", ",
                        new[] { istniejace }.Concat(duplikaty).Select(NumerZk));
                    kroki.Add(new Krok("zk", plan.Projekt ?? "", "blad",
                        $"projekt ma już {duplikaty.Count + 1} dokumenty ZK ({numery}) — "
                        + "zapis wstrzymany, żeby nie pogłębić bałaganu. Scal je ręcznie "
                        + "w Subiekcie albo usuń zbędny, potem uruchom ponownie."));
                }
                else
                {

                var podm = ZnajdzPodmiot(sfera, plan.Podmiot);
                if (podm == null && istniejace == null)
                {
                    kroki.Add(new Krok("zk", plan.Projekt ?? "", "blad", $"nie znaleziono podmiotu: {plan.Podmiot}"));
                }
                else
                {
                    // Dopisujemy do istniejącego ZK albo tworzymy nowe.
                    using var ob = istniejace != null
                        ? zam.Znajdz(istniejace)
                        : zam.UtworzZamowienieOdKlienta();

                    if (istniejace == null)
                    {
                        ob.Dane.Podmiot = podm;
                        if (!string.IsNullOrWhiteSpace(plan.Tytul)) ob.Dane.Tytul = plan.Tytul;
                        // Numer projektu też w Uwagach — tak firma już oznacza dokumenty
                        // (628 dokumentów z wypełnionym polem Uwagi, sekcja 2.1).
                        ob.Dane.Uwagi = string.IsNullOrWhiteSpace(plan.Uwagi) ? $"Projekt {plan.Projekt}" : plan.Uwagi;
                    }

                    // Co już jest na dokumencie — nie dublujemy pozycji.
                    // Ilość trzymana razem z symbolem, żeby rozjazd dało się
                    // zgłosić zamiast przemilczeć (zgłoszone 08.09.2026).
                    var juzNaZk = CzytajPozycjeZk(ob.Dane.Pozycje);

                    var dodane = 0;
                    var pominietoJest = 0;
                    var roznice = 0;
                    var zmienioneIlosci = 0;
                    var pominietoProdukcja = 0;
                    foreach (var p in pozycje)
                    {
                        // PRODUKCJA WŁASNA nie wchodzi na ZK: RMPAK jest
                        // producentem i nie zamawia detali u siebie. Filtr stoi
                        // TYLKO tutaj, przy pozycjach dokumentu — kartoteka
                        // i skład kompletu powstały wyżej normalnie, bo detal
                        // własny bywa składnikiem KT i komplet musi być pełny
                        // (RMPAK_PRODUKCJA_USTALENIA.md §9).
                        //
                        // Te pozycje idą własnym torem: Kalkulator RMPAK → PW → RW.
                        if (p.ProdukcjaWlasna)
                        {
                            pominietoProdukcja++;
                            kroki.Add(new Krok("zk-poz", p.Symbol, "produkcja-wlasna",
                                               "robimy u siebie — nie zamawiamy; idzie na PW"));
                            continue;
                        }
                        // Realny symbol z mapy, nie z Sfery: `enc` sluzyl tu
                        // WYLACZNIE do odczytania enc.Symbol, a WyszukajPoSymbolu
                        // w petli po 354 pozycjach kosztowalo ~13 s na kazdy
                        // zapis (log mostu 09.09.2026: cmd=projekt zapis=True
                        // 13245 ms i 14580 ms przy 459 ms na suchy przebieg).
                        var sym = RealnySymbol(p.Symbol);
                        if (sym == null) continue;
                        if (juzNaZk.TryGetValue(sym, out var naDok))
                        {
                            // Pozycja JEST na dokumencie — doprowadzamy jej ilość
                            // do stanu z BOM-u, dopisując RÓŻNICĘ. Operacja jest
                            // idempotentna: drugie kliknięcie „zapisz" nic już
                            // nie zmieni (rożnica = 0). Dodawanie pełnej ilości
                            // z BOM-u podwajałoby ją przy każdym powtórzeniu.
                            // Ilość 0 = user chce wyzerować pozycję na ZK.
                            // Nie podnosimy jej do 1, bo to świadoma decyzja.
                            var zBomu = p.Ilosc < 0 ? 0m : p.Ilosc;
                            if (zBomu == naDok) { pominietoJest++; continue; }

                            try
                            {
                                // UstawIlosc — ustawia ilość WPROST, więc działa
                                // i w górę, i w dół (0 zeruje pozycję). Prostsze
                                // i uczciwsze niż dopisywanie różnicy osobnym
                                // wierszem: na dokumencie zostaje jedna pozycja
                                // z właściwą liczbą, a nie kilka do zsumowania.
                                // Ten sam symbol bywa w KILKU wierszach dokumentu —
                                // wcześniejsza wersja „dopisz różnicę" dokładała
                                // nowe wiersze zamiast zmieniać istniejące, więc
                                // 2627-650.11ZZ miał dwa wiersze po 1. Ustawienie
                                // tylko pierwszego na cel NIC nie zmieniało sumy
                                // (sprawdzone diagnostyką 09.09.2026).
                                // KONSOLIDACJA: pierwszy wiersz = ilość docelowa,
                                // reszta usunięta (albo wyzerowana, gdy Usun brak).
                                var wiersze = ZnajdzWszystkiePozycje(ob.Dane.Pozycje, sym);
                                if (wiersze.Count == 0)
                                    throw new InvalidOperationException("nie znaleziono pozycji na dokumencie");
                                UstawIloscPozycji(wiersze[0], zBomu);
                                var usuniete = 0; var wyzerowane = 0;
                                foreach (var extra in wiersze.Skip(1))
                                {
                                    if (UsunPozycje(ob, extra)) usuniete++;
                                    else { UstawIloscPozycji(extra, 0m); wyzerowane++; }
                                }
                                zmienioneIlosci++;
                                kroki.Add(new Krok("zk-poz", sym,
                                    zBomu > naDok ? "ilosc-uzupelniona" : "ilosc-zmniejszona",
                                    $"na ZK było {Ilo(naDok)} → ustawiono {Ilo(zBomu)} "
                                    + $"({Roznica(zBomu, naDok)})"));
                            }
                            catch (Exception ex)
                            {
                                roznice++;
                                kroki.Add(new Krok("zk-poz", sym, "blad",
                                    $"nie udało się ustawić ilości: {ex.Message}"));
                            }
                            continue;
                        }
                        // Dodaj(String symbol, Decimal ilosc) — symbol realny z Subiekta,
                        // nie pytany, bo dopasowanie mogło być luźne (spacje/wielkość liter).
                        var ileDodane = p.Ilosc <= 0 ? 1m : p.Ilosc;
                        ob.Pozycje.Dodaj(sym, ileDodane);
                        dodane++;
                        // Kazda DOPISANA pozycja ma swoj wiersz w raporcie.
                        // Dotad zk-poz raportowal wylacznie zmiany ilosci, wiec
                        // po zapisie user widzial "dopisano 2 poz." i PUSTA
                        // tabele — nie dalo sie sprawdzic, co konkretnie weszlo
                        // na dokument (zgloszone 09.09.2026: "nic nie widze").
                        kroki.Add(new Krok("zk-poz", sym, "dopisana",
                            $"dodano na ZK w ilosci {ileDodane:0.###}"));
                    }

                    if (dodane == 0 && zmienioneIlosci == 0 && istniejace != null)
                    {
                        zkNumer = Bezp(() => ob.Dane.NumerWewnetrzny?.PelnaSygnatura);
                        // „Wszystko już jest” tylko wtedy, gdy naprawdę się
                        // zgadza. Przy rozjeździe ilości to byłby fałsz.
                        kroki.Add(new Krok("zk", zkNumer ?? "", "bez-zmian",
                            roznice > 0
                                ? $"{pominietoJest} pozycji już na dokumencie, "
                                  + $"w tym {roznice} z INNĄ ILOŚCIĄ niż BOM — nic nie zmieniono"
                                : $"wszystkie {pominietoJest} pozycji już są na dokumencie"));
                    }
                    else
                    {
                        // Przelicz() PRZED Zapisz() — bez tego zmiana ilości na
                        // istniejącej pozycji NIE utrwala się: Zapisz() zwracało
                        // true, raport mówił „ustawiono 1", a ZK zostawało na 2
                        // (sprawdzone na żywo 09.09.2026). Tak robi przykład SDK
                        // (FakturowanieWydan.cs: Ilosc = …; Przelicz(); Zapisz()).
                        var przeliczOk = true;
                        if (zmienioneIlosci > 0)
                        {
                            try { ob.Przelicz(); }
                            catch (Exception ex)
                            {
                                przeliczOk = false;
                                kroki.Add(new Krok("zk", plan.Projekt ?? "", "blad",
                                    $"Przelicz() po zmianie ilości: {ex.GetType().Name}: {ex.Message}"));
                            }
                        }

                        if (!przeliczOk)
                        {
                            // nie zapisujemy dokumentu w niespójnym stanie
                        }
                        else if (!ob.Zapisz())
                        {
                            kroki.Add(new Krok("zk", plan.Projekt ?? "", "blad", Bezp(ob.PodajBledy)));
                        }
                        else
                        {
                            zkNumer = Bezp(() => ob.Dane.NumerWewnetrzny?.PelnaSygnatura);
                            // Produkcja własna w podsumowaniu, nie tylko w wierszach:
                            // bez tego user widzi „dopisano 22 poz." przy 30 w planie
                            // i nie wie, gdzie się podziało 8 (zasada „nic po cichu").
                            var prod = pominietoProdukcja > 0
                                ? $" — {pominietoProdukcja} poz. produkcji własnej pominięto (idą na PW)" : "";
                            var co = (istniejace != null
                                ? $"dopisano {dodane} poz."
                                  + (zmienioneIlosci > 0 ? $", zmieniono ilość w {zmienioneIlosci} poz." : "")
                                  + (pominietoJest > 0 ? $" ({pominietoJest} bez zmian"
                                      + (roznice > 0 ? $", {roznice} wymaga uwagi" : "") + ")" : "")
                                : $"utworzone ({dodane} poz.)") + prod;
                            kroki.Add(new Krok("zk", zkNumer ?? plan.Projekt ?? "", co, null));
                        }
                    }
                }
                }
            }
            catch (Exception ex)
            {
                kroki.Add(new Krok("zk", plan.Projekt ?? "", "blad", $"{ex.GetType().Name}: {ex.Message}"));
            }
        }

        var json = JsonSerializer.Serialize(new { zapisano = zapisz, zk = zkNumer, kroki },
            new JsonSerializerOptions { WriteIndented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
        if (outPath is null) Console.WriteLine(json);
        else File.WriteAllText(outPath, json, new UTF8Encoding(false));
        return 0;
    }

    /// <summary>
    /// Komplety (Z/ZZ) w kolejności od najgłębszych do korzenia — składnik
    /// zapisany przed tym, co go zawiera. Głębokość liczona po faktycznym
    /// zagnieżdżeniu składników, nie po typie, bo ZZ potrafi zawierać ZZ.
    /// Cykl (gdyby BOM go zawierał) nie zapętla liczenia — ścieżka jest pilnowana.
    /// </summary>
    /// Wrapper internal dla ProjektCofnij.cs — PosortujOdDolu zostaje prywatne
    /// dla własnej czytelności (używane tylko lokalnie przy zakładaniu),
    /// odwrotna kolejność przy cofaniu potrzebuje tej samej logiki liczenia
    /// głębokości, więc nie duplikujemy jej w drugim pliku.
    internal static List<PozPlan> PosortujOdDoluDlaCofniecia(List<PozPlan> pozycje) => PosortujOdDolu(pozycje);

    static List<PozPlan> PosortujOdDolu(List<PozPlan> pozycje)
    {
        var komplety = pozycje.Where(p => Rowne(p.Typ, "Z") || Rowne(p.Typ, "ZZ")).ToList();
        var wg = new Dictionary<string, PozPlan>(StringComparer.OrdinalIgnoreCase);
        foreach (var p in komplety) wg[p.Symbol.Trim()] = p;

        var glebokosc = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

        int Licz(PozPlan p, HashSet<string> sciezka)
        {
            var klucz = p.Symbol.Trim();
            if (glebokosc.TryGetValue(klucz, out var g)) return g;
            if (!sciezka.Add(klucz)) return 0;          // cykl — przerywamy

            var max = 0;
            foreach (var s in p.Skladniki ?? new List<SkladnikPlan>())
                if (wg.TryGetValue(s.Symbol.Trim(), out var dziecko))
                    max = Math.Max(max, Licz(dziecko, sciezka) + 1);

            sciezka.Remove(klucz);
            glebokosc[klucz] = max;
            return max;
        }

        foreach (var p in komplety) Licz(p, new HashSet<string>(StringComparer.OrdinalIgnoreCase));
        return komplety.OrderBy(p => glebokosc.TryGetValue(p.Symbol.Trim(), out var g) ? g : 0)
                       .ThenBy(p => p.Symbol)
                       .ToList();
    }

    /// <summary>
    /// Usuwa WSZYSTKIE skladniki kompletu. Zwraca, ile wierszy bylo.
    ///
    /// ISkladnikiKompletu nie ma "wyczysc" — jest tylko Usun(symbol) : bool
    /// (sprawdzone refleksja 06.09.2026). Nie wiadomo, czy Usun zdejmuje jedno
    /// wystapienie, czy wszystkie o tym symbolu, wiec wolamy w petli az zwroci
    /// false. Limit iteracji to bezpiecznik na wypadek, gdyby kiedys zaczelo
    /// zwracac true w nieskonczonosc.
    /// </summary>
    /// <remarks>
    /// Parametr MUSI byc typem statycznym (IAsortyment), NIE dynamic. Przy
    /// dynamic binder wybiera przeciazenie Skladniki.Usun po typie runtime
    /// i nie trafia w zadne z trzech (Asortyment / int / string) — leci
    /// "No overload for method 'Usun' takes 1 arguments", mimo ze Usun(string)
    /// istnieje. Kazdy komplet konczyl sie wtedy bledem i NIE POWSTAWAL
    /// (zgloszone 07.09.2026: 25 bledow, 0 kompletow, ZK utworzone).
    /// Ten sam blad i ta sama naprawa co w KartotekaEdytuj.cs.
    /// </remarks>
    internal static int WyczyscSklad(InsERT.Moria.Asortymenty.IAsortyment ob)
    {
        var symbole = new List<string>();
        int bylo;
        try
        {
            IEnumerable<dynamic> sklad = ob.Dane.SkladnikiKompletu;
            var lista = sklad.ToList();
            bylo = lista.Count;
            foreach (var s in lista)
            {
                string? sym = s.Skladnik?.Symbol;
                if (!string.IsNullOrWhiteSpace(sym) && !symbole.Contains(sym)) symbole.Add(sym);
            }
        }
        catch
        {
            return 0;                 // brak kolekcji = nie ma czego czyscic
        }
        foreach (var sym in symbole)
        {
            var straznik = 0;
            while (straznik++ < 200 && (bool)ob.Skladniki.Usun(sym)) { }
        }
        return bylo;
    }

    /// <summary>
    /// Szuka ZK projektu po Uwagach (dopasowanie dokładne, TRIM + bez rozróżniania
    /// wielkości liter). Zwraca NAJNOWSZE dopasowanie i listę WSZYSTKICH pozostałych
    /// dopasowań (duplikaty) — wołający decyduje, co z nimi zrobić.
    ///
    /// Bez limitu Take() — poprzednia wersja brała tylko 100 ostatnich ZK i milczące
    /// wypadanie starego dokumentu poza to okno prowadziło do DRUGIEGO ZK dla tego
    /// samego projektu (zgłoszone 07.09.2026: "user założy projekt na projekcie
    /// i narobi się bałagan"). Kolekcja ZK w praktyce nie jest na tyle duża, żeby
    /// pełny przelot zaszkodził (dziesiątki-setki, nie dziesiątki tysięcy).
    /// </summary>
    internal static (DokumentZK? najnowsze, List<DokumentZK> duplikaty) ZnajdzZkProjektu(Uchwyt sfera, string? projekt)
    {
        if (string.IsNullOrWhiteSpace(projekt)) return (null, new List<DokumentZK>());
        var szukany = projekt.Trim();
        try
        {
            // ⚠️ ToList() PRZED Where(): Dane.Wszystkie() zwraca ObjectQuery
            // (Entity Framework), który próbuje przetłumaczyć predykat na SQL.
            // Wywołania własnych metod (PasujeUwagi) nie umie — i zamiast
            // rzucić błąd zwraca po cichu pustkę. Sprawdzone 07.09.2026:
            // filtrowanie przed materializacją nie znajdowało ŻADNEGO ZK,
            // choć trzy istniały. Ta sama pułapka co przy .ToList() na
            // ObjectQuery<Asortyment> w ProjektCofnij.cs.
            var trafienia = sfera.ZamowieniaOdKlientow().Dane.Wszystkie().ToList()
                .Where(d => PasujeUwagi(Bezp(() => d.Uwagi), szukany))
                .OrderByDescending(d => d.DataWprowadzenia)
                .ToList();
            if (trafienia.Count == 0) return (null, new List<DokumentZK>());
            return (trafienia[0], trafienia.Skip(1).ToList());
        }
        catch { return (null, new List<DokumentZK>()); }
    }

    /// <summary>
    /// Dopasowanie Uwag do numeru projektu — musi rozumieć OBA formaty, w
    /// jakich numer tam trafia: dokładnie sam numer (gdy plan.Uwagi podano
    /// z góry) i domyślny "Projekt {numer}" (linia niżej, gdy plan.Uwagi
    /// jest puste). Sprawdzone 07.09.2026: dopasowanie tylko "równe" nie
    /// łapało własnego domyślnego formatu — zakładanie tego samego projektu
    /// drugi raz tworzyło DRUGIE ZK zamiast dopisać do pierwszego, bo zapis
    /// (ta metoda) i odczyt (dawne porównanie Equals) patrzyły na dwa różne
    /// stringi dla tego samego numeru.
    /// </summary>
    /// <summary>
    /// Co dokladnie zmieni sie w skladzie kompletu: ktore rysunki doszly,
    /// ktore znikly, ktorym zmienila sie ilosc.
    ///
    /// "ma 19 skl., po zapisie bedzie 20" nie mowilo, KTORY skladnik doszedl —
    /// a przy podmianie rysunku w zlozeniu (19 -> 19) nie mowilo w ogole nic
    /// (zgloszone 08.09.2026: "a gdy sie zmienia rysunek w zlozeniu, bedzie
    /// pokazany?"). Sama liczba skladnikow nie jest informacja o zmianie.
    /// </summary>
    static string OpiszRoznice(List<(string Symbol, decimal Ilosc)> stare, List<SkladnikPlan> nowe)
    {
        var st = stare.ToDictionary(x => x.Symbol, x => x.Ilosc);
        var nw = new Dictionary<string, decimal>();
        foreach (var s in nowe)
            nw[s.Symbol.Trim().ToUpperInvariant()] = s.Ilosc <= 0 ? 1m : s.Ilosc;

        var doszlo = nw.Keys.Where(k => !st.ContainsKey(k)).OrderBy(k => k).ToList();
        var znikly = st.Keys.Where(k => !nw.ContainsKey(k)).OrderBy(k => k).ToList();
        var ilosci = nw.Keys.Where(k => st.ContainsKey(k) && st[k] != nw[k])
                            .OrderBy(k => k)
                            .Select(k => $"{k}: {st[k]:0.##}→{nw[k]:0.##}").ToList();

        var czesci = new List<string>();
        if (doszlo.Count > 0) czesci.Add("+ " + Skroc(doszlo));
        if (znikly.Count > 0) czesci.Add("− " + Skroc(znikly));
        if (ilosci.Count > 0) czesci.Add("ilość: " + Skroc(ilosci));
        return czesci.Count > 0
            ? string.Join("   ", czesci)
            : $"{stare.Count} → {nowe.Count} skł.";
    }

    /// Trzy pozycje wystarcza, zeby zrozumiec zmiane; reszta i tak nie zmiesci
    /// sie w kolumnie tabeli.
    static string Skroc(List<string> lista) =>
        lista.Count <= 3 ? string.Join(", ", lista)
                         : string.Join(", ", lista.Take(3)) + $" … (+{lista.Count - 3})";

    internal static bool PasujeUwagi(string? uwagi, string projekt)
    {
        var u = (uwagi ?? "").Trim();
        if (u.Length == 0) return false;
        if (u.Equals(projekt, StringComparison.OrdinalIgnoreCase)) return true;
        if (u.Equals($"Projekt {projekt}", StringComparison.OrdinalIgnoreCase)) return true;
        return false;
    }

    static string NumerZk(DokumentZK? d) =>
        d is null ? "?" : (Bezp(() => d.NumerWewnetrzny?.PelnaSygnatura) ?? "?");

    static Podmiot? ZnajdzPodmiot(Uchwyt sfera, string? szukany)
    {
        if (string.IsNullOrWhiteSpace(szukany)) return null;
        var s = szukany.Trim();
        var firmy = sfera.Podmioty().Dane.WszystkieFirmy().ToList();
        return firmy.FirstOrDefault(p => string.Equals((p.NazwaSkrocona ?? "").Trim(), s, StringComparison.OrdinalIgnoreCase))
            ?? firmy.FirstOrDefault(p => (p.NIP ?? "").Replace("-", "").Trim() == s.Replace("-", ""))
            ?? firmy.FirstOrDefault(p => (p.NazwaSkrocona ?? "").Contains(s, StringComparison.OrdinalIgnoreCase));
    }

    static bool Rowne(string? a, string b) => string.Equals((a ?? "").Trim(), b, StringComparison.OrdinalIgnoreCase);

    static string? Bezp(Func<string?> f) { try { return f(); } catch { return null; } }

    /// Pozycja dokumentu o danym symbolu — albo null.
    ///
    /// Ten sam symbol moze wystapic w kilku wierszach (dopisywane partiami);
    /// bierzemy PIERWSZY, bo to na nim ustawiamy ilosc docelowa. Pozostale
    /// zostawiamy — usuwanie pozycji z dokumentu ksiegowego to inna decyzja
    /// niz zmiana liczby sztuk.
    static object? ZnajdzPozycje(IEnumerable<PozycjaDokumentu> pozycje, string symbol)
    {
        try
        {
            foreach (var poz in pozycje)
            {
                var s = Bezp(() => poz.AsortymentAktualny?.Symbol)?.Trim();
                if (!string.IsNullOrEmpty(s)
                    && string.Equals(s, symbol, StringComparison.OrdinalIgnoreCase))
                    return poz;
            }
        }
        catch { }
        return null;
    }

    /// WSZYSTKIE wiersze dokumentu o danym symbolu, w kolejnosci na dokumencie.
    static List<object> ZnajdzWszystkiePozycje(IEnumerable<PozycjaDokumentu> pozycje, string symbol)
    {
        var wynik = new List<object>();
        try
        {
            foreach (var poz in pozycje)
            {
                var s = Bezp(() => poz.AsortymentAktualny?.Symbol)?.Trim();
                if (!string.IsNullOrEmpty(s)
                    && string.Equals(s, symbol, StringComparison.OrdinalIgnoreCase))
                    wynik.Add(poz);
            }
        }
        catch { }
        return wynik;
    }

    /// Usuwa wiersz z dokumentu przez kolekcje biznesowa `ob.Pozycje`.
    /// Sygnatury Usun nie znamy na pewno (dokumentacja milczy), wiec szukamy
    /// refleksja metody "Usun" przyjmujacej pozycje albo jej Id. Zwraca false,
    /// gdy sie nie da — wtedy wolajacy zeruje ilosc zamiast usuwac.
    /// Ta sama logika dla ZkPozUsun — usuwanie pozycji z dokumentu jest
    /// nietrywialne (refleksja po metodzie „Usun" przyjmującej pozycję albo
    /// jej Id), więc nie powielamy go w drugim miejscu.
    internal static bool UsunPozycjePubl(object ob, object poz) => UsunPozycje(ob, poz);

    static bool UsunPozycje(object ob, object poz)
    {
        try
        {
            var kolekcja = ob.GetType().GetProperty("Pozycje")?.GetValue(ob);
            if (kolekcja == null) return false;
            foreach (var mi in kolekcja.GetType().GetMethods().Where(m => m.Name == "Usun"))
            {
                var pars = mi.GetParameters();
                if (pars.Length != 1) continue;
                if (pars[0].ParameterType.IsInstanceOfType(poz))
                {
                    var r = mi.Invoke(kolekcja, new[] { poz });
                    return r is not bool b || b;
                }
            }
        }
        catch { }
        return false;
    }

    /// Ustawia ilosc pozycji dokumentu.
    ///
    /// `UstawIlosc` jest na klasie pozycji, ale jej dokladna sygnatura roznila
    /// sie miedzy wersjami Sfery (bywa przeciazona o jednostke miary), dlatego
    /// szukamy jej refleksja i probujemy wariantow po kolei. Gdy zadnego nie
    /// ma — wolamy o tym wprost, zamiast po cichu nic nie zrobic.

    /// Dla ZkPozUsun — `UstawIlosc` jest METODĄ ROZSZERZAJĄCĄ, więc zwykłe
    /// `poz.Ilosc = x` przez dynamic nic nie robi (patrz komentarz niżej).
    /// Nie powielamy tego szukania w drugim pliku.
    internal static void UstawIloscPozycjiPubl(object poz, decimal ilosc)
        => UstawIloscPozycji(poz, ilosc);

    static void UstawIloscPozycji(object poz, decimal ilosc)
    {
        var typ = poz.GetType();

        // UstawIlosc to METODA ROZSZERZAJACA (PozycjaExtensions), czyli
        // STATYCZNA metoda w osobnej klasie, przyjmujaca pozycje jako pierwszy
        // argument. Szukanie jej na instancji znajdowalo co innego i zmiana
        // nie zapisywala sie do Subiekta, mimo ze raport mowil, ze zaszla
        // (09.09.2026 — "zdjelo tylko w oknie, nie w Subiekcie").
        foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
        {
            Type[] typy;
            try { typy = asm.GetTypes(); } catch { continue; }
            foreach (var t in typy)
            {
                if (!t.IsAbstract || !t.IsSealed) continue;      // tylko klasy statyczne
                foreach (var mi in t.GetMethods().Where(m => m.Name == "UstawIlosc" && m.IsStatic))
                {
                    var pars = mi.GetParameters();
                    if (pars.Length < 2) continue;
                    if (!pars[0].ParameterType.IsInstanceOfType(poz)) continue;
                    if (pars[1].ParameterType != typeof(decimal)) continue;

                    var args = new object?[pars.Length];
                    args[0] = poz;
                    args[1] = ilosc;
                    for (int i = 2; i < pars.Length; i++)
                        args[i] = pars[i].HasDefaultValue ? pars[i].DefaultValue
                                : (pars[i].ParameterType.IsValueType
                                   ? Activator.CreateInstance(pars[i].ParameterType) : null);
                    mi.Invoke(null, args);
                    return;
                }
            }
        }

        // Metoda instancji — gdyby w tej wersji Sfery jednak byla.
        foreach (var mi in typ.GetMethods().Where(m => m.Name == "UstawIlosc"))
        {
            var pars = mi.GetParameters();
            if (pars.Length >= 1 && pars[0].ParameterType == typeof(decimal))
            {
                var args = new object?[pars.Length];
                args[0] = ilosc;
                for (int i = 1; i < pars.Length; i++)
                    args[i] = pars[i].HasDefaultValue ? pars[i].DefaultValue
                            : (pars[i].ParameterType.IsValueType
                               ? Activator.CreateInstance(pars[i].ParameterType) : null);
                mi.Invoke(poz, args);
                return;
            }
        }

        throw new InvalidOperationException(
            "nie znaleziono UstawIlosc (ani rozszerzajacej, ani na pozycji)");
    }

    /// {symbol → ilość} z pozycji dokumentu ZK.
    ///
    /// Wcześniej czytany był sam HashSet symboli, przez co 4 i 10 były dla
    /// mostu tym samym stanem: zmiana ilości w BOM-ie nie pojawiała się ani
    /// w suchym przebiegu, ani w raporcie po zapisie (zgłoszone 08.09.2026 —
    /// „pokazało pomnożone ilości, ale w oknie potwierdzającym zero informacji”).
    ///
    /// Ten sam symbol może wystąpić na dokumencie w kilku pozycjach — wtedy
    /// ilości sumujemy, bo z punktu widzenia zapotrzebowania liczy się łączna
    /// ilość zamówiona, nie sposób jej rozpisania na wiersze.
    internal static Dictionary<string, decimal> CzytajPozycjeZk(IEnumerable<PozycjaDokumentu> pozycje)
    {
        var mapa = new Dictionary<string, decimal>(StringComparer.OrdinalIgnoreCase);
        try
        {
            foreach (var poz in pozycje)
            {
                var s = Bezp(() => poz.AsortymentAktualny?.Symbol)?.Trim();
                if (string.IsNullOrEmpty(s)) continue;
                decimal ile = 0m;
                try { ile = poz.Ilosc; } catch { }
                mapa[s!] = mapa.TryGetValue(s!, out var byla) ? byla + ile : ile;
            }
        }
        catch { }
        return mapa;
    }

    /// Ilość bez zbędnych zer — „4” zamiast „4,000”, ale „1,5” zostaje.
    /// Kropka dziesiętna niezależna od ustawień regionalnych, żeby raport
    /// czytało się tak samo na każdym stanowisku.
    static string Ilo(decimal x) => x.ToString("0.###", CultureInfo.InvariantCulture);

    /// „różnica +6” / „różnica −2” — znak wprost, żeby z jednego rzutu oka
    /// było widać, czy BOM urósł, czy zmalał względem dokumentu.
    static string Roznica(decimal zBomu, decimal naDok)
    {
        var d = zBomu - naDok;
        return "różnica " + (d > 0 ? "+" : d < 0 ? "−" : "") + Ilo(Math.Abs(d));
    }

    internal record SkladnikPlan(string Symbol, decimal Ilosc);
    internal record PozPlan(string Symbol, string? Nazwa, string? Typ, decimal Ilosc,
                            List<SkladnikPlan>? Skladniki,
                            // JAWNA nazwa z JSON-a: PropertyNameCaseInsensitive
                            // ignoruje wielkość liter, ale NIE podkreślenia —
                            // bez tego atrybutu "produkcja_wlasna" nie trafiało
                            // w ProdukcjaWlasna i filtr milczał (09.09.2026).
                            [property: JsonPropertyName("produkcja_wlasna")]
                            bool ProdukcjaWlasna = false);
    internal record Plan(string? Projekt, string? Tytul, string? Podmiot, string? Uwagi, List<PozPlan>? Pozycje);
    internal record Krok(string Rodzaj, string Symbol, string Status, string? Szczegoly);
}
