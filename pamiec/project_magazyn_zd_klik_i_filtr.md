---
name: project_magazyn_zd_klik_i_filtr
description: Okno Magazyn - klik w kolumne ZD otwiera liste zamowien i Przeglad dokumentow, filtr "pokaz wszystko"; pulapki Tk (pady jako krotka, polkniety wyjatek, okno w tle)
metadata:
  type: project
---

# Magazyn: klik w ZD + filtr „pokaż wszystko" (05.10.2026)

## Co robi kolumna ZD

Pokazuje numery **otwartych zamówień do dostawcy** dla danego symbolu.
`Magazyn.cs` czyta ostatnie **200** ZD wg `DataWprowadzenia` malejąco,
pomija ze statusem „zrealizowan*" i „anulowan*", a numery skleja przecinkiem.
Do numeru dokleja **zamówioną ilość**: `$"{numer} ({poz.Ilosc:0.##})"`, czyli
w komórce jest np. `ZD 68/09/2026 (4)`.

**Klik** (pojedynczy, gdy komórka niepusta) otwiera listę zamówień tej
pozycji; klik w numer otwiera Przegląd dokumentów ustawiony na tym ZD
z podświetloną pozycją.

⚠️ Kolejność numerów **zostawiamy taką, jaką daje most** — nie sortujemy.
Sortowanie tekstowe wstawiłoby „ZD 9" przed „ZD 10".

⚠️ Do wyszukiwarki dokumentów idzie **sam numer** (`_sam_numer` obcina
nawias z ilością). Z nawiasem Przegląd nie znajduje nic.

## Trzy pułapki Tk, które kosztowały dwie rundy „nie działa"

**1. `pady` jako krotka w opcji WIDGETU.** `tk.Label(..., pady=(6, 2))`
rzuca `TclError: bad screen distance "6 2"` — krotka jest poprawna tylko
w `.pack()` / `.grid()`. Tk **połyka wyjątki z handlerów**, a `pythonw` nie
ma konsoli, więc klik po prostu „nic nie robił". Dlatego wywołanie
`_okno_zd` jest w `try/except` z `messagebox` — cisza jest gorsza niż błąd.

**2. Dwuklik odpalał dwie rzeczy naraz.** Tk przy dwukliku wysyła najpierw
`<ButtonRelease-1>`, zaraz potem `<Double-Button-1>`. Bez wyjątku dla ZD
w `_on_dblclick` karta pozycji otwierała się na wierzchu i przykrywała
listę — wyglądało to jak „klikam ZD, a dostaję kartę pozycji".

**3. Przegląd dokumentów wychodził w tle.** `DokumentyWindow` ładuje dane
asynchronicznie (`after(100, _load_async)`, potem `after(200, _podzial)`),
więc jedno `lift()` tuż po utworzeniu jest **za wczesne** — kolejne
przerysowania oddają fokus. Rozwiązanie: podnoszenie ponawiane
(150/400/700 ms), krótkie `-topmost` zdejmowane po 300 ms, oraz **jawne
`grab_release()`** przed zamknięciem listy (była modalna przez `grab_set`,
a przy aktywnym grabie Windows potrafi nie oddać fokusu nowemu oknu).

## Filtr „pokaż wszystko (także bez stanu)"

Domyślnie okno pokazuje tylko kartoteki ze stanem albo z progiem —
`pobierz_magazyn(tylko_niezerowe=True)`. Checkbox przeładowuje listę
z `tylko_niezerowe=False`.

Stary komentarz w kodzie twierdził, że pełnego odczytu nie ma celowo, bo
jest wolny. **Zmierzone: 13 s dla 5275 kartotek** (3779 bez stanu) — do
przyjęcia przy świadomym kliknięciu, więc przełącznik wrócił.

## Mój błąd w tej sesji

Zakładając log diagnostyczny przez **heredoc w bashu**, wstawiłem `\n`,
który stał się prawdziwą nową linią i rozerwał literał — plik miał błąd
składni, a user testował wersję, która nie mogła działać. To ta sama
pułapka, przed którą ostrzega pamięć projektu. Do edycji plików z polskimi
znakami: narzędzie Write/Edit albo `chr(10)`, nigdy `\n` w heredocu.

Druga lekcja: trzy razy odesłałem usera do klikania, zanim odtworzyłem
problem w **izolowanym teście** (atrapa okna + `button.invoke()`), który
pokazał dokładny wyjątek w pół minuty. Przy GUI, gdzie Tk połyka błędy,
taki test powinien być pierwszym krokiem, nie ostatnim.

Powiązane: [[project_wydanie_kolumna_rw]] [[project_zapotrzebowanie_szybkie]]
