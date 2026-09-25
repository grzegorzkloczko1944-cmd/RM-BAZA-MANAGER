---
name: project_treeviewselect_czysci_panel
description: "Edytor kartotek: opóźniony <<TreeviewSelect>> czyścił panel 2 dla pozycji spoza drzewa (klon) — filtr musi stać w _na_wybor_wezla, nie u wołającego"
metadata:
  type: project
---

# Opóźniony `<<TreeviewSelect>>` kasuje panel 2

Naprawione 25.09.2026. **Ta sama przyczyna wróciła tego dnia TRZY RAZY**
pod różnymi objawami — stąd osobna notatka.

## Mechanizm

Klon (i wybór z listy 4) **nie ma węzła w drzewie** — i mieć nie ma:
decyzja użytkownika z 25.09.2026 brzmi „klona robię w panelu 2 i tylko
tam, klawiszem Klonuj". Ale każde ruszenie drzewa gubi tam zaznaczenie:

```
_odswiez_drzewo()  →  Treeview traci zaznaczenie
                   →  Tk wysyła <<TreeviewSelect>>
                   →  _na_wybor_wezla() widzi puste zaznaczenie
                   →  _wyczysc_panel_szczegolow() + _zaznaczony = None
```

Użytkownik traci formularz, nad którym pracuje, i **nie może już zapisać**.

## ⛔ Dlaczego blokada u wołającego NIE WYSTARCZA

Pierwsze dwa podejścia (`e5a7fb8` i moja poprawka w `_zmien_symbol`)
stawiały guard po stronie tego, kto rusza drzewo:

```python
if getattr(self, "_z_listy", False):
    return          # NIE WYSTARCZA
```

**Tk dostarcza `<<TreeviewSelect>>` PO powrocie z funkcji**, która ruszyła
drzewo. Guard zdąży się skończyć, zanim zdarzenie przyjdzie — a ono
przychodzi później, przy dowolnej następnej akcji (np. gdy user zaczyna
wpisywać NAZWĘ). Stąd objaw wyglądał za każdym razem inaczej.

**Filtr musi stać na KOŃCU łańcucha**, w `_na_wybor_wezla`:

```python
if getattr(self, "_z_listy", False) and self._zaznaczony in self.pozycje:
    return          # pozycja z panelu 2 — nie czyścimy
```

## Trzy objawy, jedna przyczyna

| Objaw zgłoszony przez usera | Gdzie ruszało drzewo |
|---|---|
| „kasuje cały symbol" przy dopisywaniu znaku | `_zmien_symbol` → `_odswiez_drzewo` |
| panel pustoszał przy wpisywaniu nazwy | opóźnione zdarzenie z poprzedniej akcji |
| po zapisie klona formularz znikał | `_zapis_gotowy` → `_odswiez_drzewo` + `_zaznacz_w_drzewie` |

W `_zapis_gotowy` doszło też pokazywanie **symbolu z `Kartoteka.symbol`**,
nie z klucza słownika — klon siedzi pod kluczem technicznym
`\x00klon:<symbol>`, który nie ma prawa trafić userowi przed oczy.

## ⚠️ Przy testach Tk: `update()` ≠ `mainloop()`

Test „nie działa", który wprowadził mnie w błąd: wątek roboczy woła
`self.after(0, ...)`, a to **wymaga żywej pętli Tk**. W teście z samym
`root.update()` leci `RuntimeError: main thread is not in main loop`
i callback nigdy nie dochodzi — mimo że w aplikacji działa poprawnie.
Testując wątki w Tk, używaj `root.mainloop()` + `root.after(...)`.

Powiązane: [[project_subiekt_edytor_kartotek]], [[project_dopasuj_kartoteke_wiersza]],
[[project_katalog_cache_odswiezanie]].
