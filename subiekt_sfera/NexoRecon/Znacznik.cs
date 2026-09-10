// Jak RM_BAZA oznacza SWOJE dokumenty w Subiekcie — jedno miejsce dla ZK, PW,
// RW i ZD. Ustalone 10.09.2026, po tym jak okazalo sie, ze kazdy tryb robil to
// inaczej i tryby nie rozumialy nawzajem swoich dokumentow.
//
// DWA POLA, DWIE ROLE
// ───────────────────
//   Uwagi:  "2741 Projekt\npilne, do piatku"
//   Tytul:  "RM_BAZA 2741"            ← znacznik: to wystawila RM_BAZA
//
// UWAGI maja dwa pietra i dwoch autorow:
//
//   2741 Projekt        ← PIERWSZY WIERSZ, wpisuje RM_BAZA
//   pilne, do piatku    ← reszta: co czlowiek wpisal w polu „Uwagi" w okienku
//
// W pierwszym wierszu numer stoi PRZED spacja, za nim slowo „Projekt" — zeby
// ktos ogladajacy sam wydruk wiedzial, co ta liczba znaczy. Kod czyta tylko
// PIERWSZY CZLON tego wiersza (do pierwszej spacji), wiec slowo „Projekt"
// jest wylacznie dla czlowieka i nie miesza sie do dopasowania.
//
// To pole SIE DRUKUJE (sekcja „Uwagi • Notes" na wzorcu) — w odroznieniu od
// Tytulu. Dlatego wlasnie tu, a nie w Tytule, laduje tresc dla czlowieka.
//
// DWA ROZNE PODZIALY, KAZDY W SWOIM MIEJSCU
//   • numer projektu  → pierwszy czlon pierwszego wiersza (do spacji)
//   • uwagi czlowieka → wszystko od DRUGIEGO wiersza w dol
// Uwagi bywaja wielowyrazowe, wiec ich granica musi byc koniec wiersza;
// numer spacji nie zawiera, wiec jego granica moze byc spacja.
//
// TYTUL — znacznik pochodzenia. Tytul sie NIE drukuje i czlowiek wystawiajacy
// dokument recznie go nie wypelnia, wiec jego obecnosc jest wiarygodnym
// dowodem, ze dokument wyszedl z RM_BAZA.
//
// DLACZEGO ZNACZNIK NIE MOZE ZOSTAC W UWAGACH
// ───────────────────────────────────────────
// Poprzednio PW/RW mialy "RM_BAZA — PROJEKT 2741" w Uwagach i po tym tekscie
// subiekt_produkcja.dokumenty_produkcji() poznawala swoje dokumenty. Ale skoro
// pierwszy czlon Uwag ma byc numerem projektu, marker z przodu juz sie nie
// miesci — a doklejony z tylu bylby nie do odroznienia od uwagi czlowieka.
// Stad przeprowadzka do Tytulu.
//
// DLACZEGO W TYTULE JEST TEZ NUMER
// ────────────────────────────────
// Rozpoznanie idzie po samym "RM_BAZA" (Nasz), numer w Tytule to zapasowy slad
// na wypadek, gdyby ktos wyczyscil Uwagi — decyzja uzytkownika z 10.09.2026:
// „tak na wszelki wypadek, ale parsujemy po samym RM_BAZA".
//
// ⚠️ BEZ KOMPATYBILNOSCI WSTECZ
// Stare formaty ("Projekt 2741" w Uwagach, "RM_BAZA — PROJEKT 2741") NIE sa
// juz rozumiane — swiadoma decyzja z 10.09.2026, dokumentow bylo malo i
// zostaly poprawione recznie. Nie dopisuj tu obslugi starych formatow: to
// wlasnie ona spowodowala, ze zapis i odczyt patrzyly na dwa rozne stringi.

namespace NexoRecon;

internal static class Znacznik
{
    /// <summary>Slowo w Tytule, po ktorym poznajemy dokument z RM_BAZA.</summary>
    internal const string MARKER = "RM_BAZA";

    /// <summary>
    /// Tresc pola Tytul dla nowego dokumentu: "RM_BAZA 2741".
    /// Bez numeru (gdy nieznany) zostaje samo "RM_BAZA".
    /// </summary>
    internal static string Tytul(string? projekt)
    {
        var p = (projekt ?? "").Trim();
        return p.Length == 0 ? MARKER : $"{MARKER} {p}";
    }

    /// <summary>Opis numeru w pierwszym wierszu Uwag — dla czytajacego wydruk.</summary>
    internal const string OPIS_NUMERU = "Projekt";

    /// <summary>
    /// Tresc pola Uwagi: "2741 Projekt" w pierwszym wierszu, uwagi czlowieka
    /// od drugiego wiersza w dol.
    /// </summary>
    internal static string Uwagi(string? projekt, string? uwagi)
    {
        var p = (projekt ?? "").Trim();
        var u = (uwagi ?? "").Trim();
        if (p.Length == 0) return u;
        var pierwszy = $"{p} {OPIS_NUMERU}";
        return u.Length == 0 ? pierwszy : $"{pierwszy}\n{u}";
    }

    /// <summary>
    /// Numer projektu z Uwag — PIERWSZY CZLON pierwszego wiersza, czyli tekst
    /// do pierwszej spacji. Slowo „Projekt" za nim jest tylko dla czlowieka.
    /// Odpowiednik subiekt_zamowienia.numer_projektu_z_uwag() po stronie Pythona;
    /// obie musza dzielic tak samo, inaczej zapis i odczyt sie rozjada.
    /// </summary>
    internal static string NumerProjektu(string? uwagi)
    {
        var u = (uwagi ?? "").Trim();
        if (u.Length == 0) return "";
        var koniec = u.IndexOfAny(new[] { '\n', '\r' });
        var pierwszy = (koniec < 0 ? u : u.Substring(0, koniec)).Trim();
        var spacja = pierwszy.IndexOf(' ');
        return spacja < 0 ? pierwszy : pierwszy.Substring(0, spacja);
    }

    /// <summary>Uwagi czlowieka — wszystko OD DRUGIEGO wiersza w dol.</summary>
    internal static string UwagiCzlowieka(string? uwagi)
    {
        var u = (uwagi ?? "").Trim();
        var koniec = u.IndexOfAny(new[] { '\n', '\r' });
        return koniec < 0 ? "" : u.Substring(koniec).Trim();
    }

    /// <summary>Czy ten dokument wystawila RM_BAZA (znacznik w Tytule)?</summary>
    internal static bool Nasz(string? tytul) =>
        (tytul ?? "").Contains(MARKER, StringComparison.OrdinalIgnoreCase);

    /// <summary>
    /// Czy dokument dotyczy tego projektu — po numerze z Uwag.
    /// UWAGA: nie mowi nic o tym, CZYJ jest dokument; recznie wystawiony
    /// z tym samym numerem tez pasuje. Do operacji, ktore zmieniaja albo
    /// kasuja dokument, sprawdzaj dodatkowo Nasz(tytul).
    /// </summary>
    internal static bool PasujeProjekt(string? uwagi, string? projekt) =>
        NumerProjektu(uwagi).Equals((projekt ?? "").Trim(),
                                    StringComparison.OrdinalIgnoreCase)
        && (projekt ?? "").Trim().Length > 0;
}
