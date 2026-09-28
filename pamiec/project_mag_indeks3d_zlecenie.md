---
name: project_mag_indeks3d_zlecenie
description: Indeks modeli 3D robi się ZLECENIEM — serwer wydaje skrypt (/mag/skrypt), dowolna stacja z Inventorem pobiera go przy każdym zleceniu do %TEMP%; nocne zlecenie po 2:00 + przycisk „Synchronizuj 3D"
metadata:
  type: project
---

Decyzja usera 28.09.2026: „nie chcę być przywiązany do jednego komputera —
skrypt na serwerze, serwer odpala, korzysta z działającego komputera usera"
+ wariant B: „stacja za każdą synchronizacją pobiera nowy skrypt do TEMP".

* Zlecenia w `subiekt_kopia.sqlite/zlecenia_sync` mają `rodzaj`:
  `kopia` (most Subiekta, MONGO/M-OLD pierwsze) albo `indeks3d`
  (dowolna stacja z Inventorem, bez pierwszeństwa). Stare operacje bez
  rodzaju widzą TYLKO `kopia` — niezaktualizowana RM_BAZA nie weźmie 3D.
* Serwer: `zlec_indeks_nocny` w `_sprzatanie` (raz na dobę po 2:00),
  `POST /mag/synchronizuj3d`, `GET /mag/skrypt/indeks_modeli_3d.py`
  (biała lista `SKRYPTY_DLA_STACJI`). Plik skryptu leży obok `rm_serwer.py`.
* Stacja (`subiekt_kopia_zlecenia.wykonaj_indeks3d`): wątek startuje, gdy
  jest most LUB Inventor (rejestr `Inventor.ApprenticeServer`); pobiera
  skrypt do `%TEMP%\RM_MAG\`, ładuje importlib (nie runpy — funkcje muszą
  mieć żywe globals), `moge_wykonac()` → dopiero wtedy przejmuje.
  `pythoncom.CoInitialize()` w wątku przed Apprentice.
* Decyzja „czy stacja się nadaje" jest W SKRYPCIE (czyli na serwerze):
  `WYMAGANY_INVENTOR` (M-OLD 17, reszta 19 = Inventor 2015).
* Skrypt wewnątrz RM_BAZA NIE nadpisuje konfiguracji `rm_klient` ani
  użytkownika (inaczej wszystkie żądania RM_BAZA szłyby jako INDEKS_MODELI_3D).
* MAG: przyciski „Synchronizuj SUBIEKT" (dawne „Synchronizuj") i
  „Synchronizuj 3D"; pasek stanu pokazuje „3D: …" gdy czeka/trwa/błąd.

Powiązane: [[project_indeks_modeli_3d]], [[project_mag_kopia_subiekta_http]],
[[project_mag_wdrozenie_firma_todo]]
