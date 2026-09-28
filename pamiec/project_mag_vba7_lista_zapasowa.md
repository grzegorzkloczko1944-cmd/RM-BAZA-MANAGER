---
name: project_mag_vba7_lista_zapasowa
description: MAG na VBA7 64-bit (Inventor 2015) — WebBrowser nie da się osadzić, lista zapasowa Forms.ListBox; plus pułapka LLMNR/IPv6 dająca 21 s na zapytanie
metadata:
  type: project
---

Uruchomienie MAG w firmie (MONGO, Inventor 2015) 28.09.2026. Okno wstało
dopiero po dwóch niezależnych naprawach.

## 1. VBA7 64-bit nie osadza WebBrowser

`Me.Controls.Add("Shell.Explorer.2")` → **-2146762748**
(`TRUST_E_SUBJECT_NOT_TRUSTED`, „Temat nie jest zaufany dla podanej akcji").

Przyczyna: kontrolka WebBrowser **nie ma kategorii „safe for scripting"**
(brak `Implemented Categories` w CLSID `{8856F961-…}`), a polityka
`URLACTION_ACTIVEX_OVERRIDE_OBJECT_SAFETY` = **DISALLOW**, więc host nie
może tego obejść. VBA6 32-bit (Inventor 2013, M-OLD) osadzał ją mimo braku
deklaracji — stąd MAG działał w domu, a w firmie nie.

Sprawdzenie polityki: `CoInternetCreateSecurityManager` →
`ProcessUrlAction` (slot 7 w vtable). `ACTIVEX_RUN` wychodzi ALLOW,
`OVERRIDE_OBJECT_SAFETY` — DISALLOW.

**Fix:** okno próbuje przeglądarkę, a gdy host odmówi, zakłada
`Forms.ListBox` (7 kolumn, nagłówki osobnym Labelem). Bez sprawdzania
wersji Inventora — liczy się wynik próby. Klik trafia do tego samego
`Wybierz(i)` co klik w HTML. Różnica: brak miniatur W LIŚCIE, zdjęcie
wybranej pozycji pokazuje prawy panel jak dotąd.
`MSComctlLib.ListView` odpada — nie jest zarejestrowany w 64-bit.

## ⛔ Trzy hipotezy SPRAWDZONE I ODRZUCONE (nie powtarzać)

1. **Rozmiar projektu** (`Default.ivb` 41 tys. linii). Komunikat makra sam
   to sugerował. Obalone: identyczny błąd w `MAG.ivb` na 1929 liniach.
2. **Flaga `Compatibility Flags` = 0x21** na CLSID kontrolki (wpis
   z 2019-12-07, jedyny taki wśród 735). Zdjęta do 0 — bez wpływu,
   **przywrócona**. To NIE kill-bit (ten ma 0x400).
3. **Stara wartość polityki w pamięci procesu** — restart Inventora nic
   nie zmienił.

Bitdefender też niewinny (mimo precedensu z `reset_klawiszy`): w chwili
awarii zero zdarzeń i logów AV.

## 2. LLMNR zwracał IPv6 → 21 s na każde zapytanie

Po naprawie okna: „Błąd: Limit czasu operacji został przekroczony".
Nazwa `W2019S` rozwiązywała się przez LLMNR/NetBIOS na link-local
**`fe80::375b:767d:c3f8:a0f6`**, osiągalny na karcie `Ethernet 2`, ale
NIE na `Ethernet` — połączenie wisiało. Zmierzone: **21,1 s po nazwie,
0,07 s po IP**; makro ma `connect=3000 ms`, więc przerywało.

**Fix:** wpis w `hosts` TEJ stacji (kopia: `hosts.backup_MAG`):

    192.168.100.84	W2019S

Po `ipconfig /flushdns`: **0,02 s**.

⚠️ **NIE wpisywać IP do `MAG_SERWER`** — na M-OLD `hosts` kieruje `W2019S`
na 127.0.0.1, więc sztywne IP zabiłoby MAG w domu. Naprawa zawsze
w `hosts` stacji, nie w kodzie. (Zdążyłem to zrobić źle i cofnąć.)

## Komunikat o nieudanym oknie

Obwiniał ZAWSZE duży projekt — przez to trzy błędne diagnozy i pół dnia.
Od 28.09.2026 pokazuje ślad z `%TEMP%\MAG_okno_blad.txt` („Na czym
stanęło"). **Ten plik to pierwsze miejsce do sprawdzenia**, gdy okno nie
wstaje; kod okna zapisuje tam krok i numer błędu.

Zobacz też: [[project_mag_okno_przegladarka]], [[feedback_makra_ivb_nazwa_mag]],
[[project_mag_wdrozenie_firma_wykonane]], [[project_srodowisko_domowe_m_old]].
