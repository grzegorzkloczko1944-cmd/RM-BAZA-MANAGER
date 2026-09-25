---
name: project_katalog_cache_odswiezanie
description: "Katalog Subiekta: JEDEN cache na dysku (12h→1h) + osobna kopia w pamięci każdego okna; nowa kartoteka unieważnia cache u źródła, F5 wymusza świeże pobranie"
metadata:
  type: project
---

# Cache katalogu Subiekta — dwie warstwy, nie jedna

Uporządkowane 25.09.2026 po zgłoszeniu: „dodaję kartotekę i w oknie jej
nie widać, bo korzysta ze starego cache".

## Ile tego naprawdę jest

Wbrew pierwszemu wrażeniu **nie ma „wszystkich buforów"**. Są dokładnie dwie
warstwy — żadnych `lru_cache`, żadnych globalnych słowników w modułach:

1. **Plik na dysku:** `C:\RMPAK_CLIENT\subiekt_katalog.json`, dotykany
   WYŁĄCZNIE w `subiekt_scalanie.py`. Wspólny dla wszystkich okien,
   przeżywa ich zamknięcie.
2. **Kopia w pamięci okna:** `self.katalog` (edytor, panel 4),
   `self._katalog` (Scal kody, Półprodukty), `self.indeks` (Dopasuj wiersz).
   Wczytywana **RAZ przy otwarciu okna**.

⚠️ Te warstwy są NIEZALEŻNE. Skasowanie pliku nie odświeża otwartego okna —
i odwrotnie. Obie trzeba obsłużyć osobno.

## Reguła: unieważniamy U ŹRÓDŁA

`subiekt_scalanie.uniewaznij_katalog()` kasuje plik. Wołane automatycznie
w `subiekt_asortyment.zaloz_kartoteke()` po udanym zapisie
(`status == "zalozona"`, tylko przy `zapisz=True`).

**Dlaczego tam, a nie w oknach:** tędy przechodzi KAŻDA ścieżka zakładania
kartoteki — edytor, „Załóż wszystkie", kartoteki z faktury KSeF — także te
dopisane w przyszłości. Żadne okno nie musi o tym pamiętać.

Ważność cache: **1 h** (`KATALOG_WAZNY_H`, było 12 h). Po naprawie automatu
limit jest już tylko siatką na kartoteki zakładane POZA RM_BAZA — wprost
w Subiekcie albo na drugiej maszynie.

## Panel 4 edytora odświeża się sam po zapisie

`_dociagnij_katalog_po_zapisie()` — w wątku, bo most to ~9 s przy zimnym
starcie (przy stałym moście 0,1 s). Kasuje też plik cache, żeby pozostałe
okna nie czytały katalogu bez świeżej kartoteki.

Objaw sprzed naprawy: user zapisywał `ELGD-BS`, dostawał potwierdzenie,
a lista 4 pokazywała tylko starsze `ELGD` — kartoteka BYŁA w Subiekcie
przez cały czas.

## F5

* **W oknach Subiekta** (Dopasuj kartotekę) — własny `bind("<F5>")`.
  ⚠️ Konieczny: `_skrot_arkusza` w RM_BAZA **celowo odfiltrowuje** F2–F6
  w oknach Toplevel, więc globalny bind tam nie zadziała.
* **W arkuszu** — `odswiez_wszystko()`: `refresh_data()` + kasowanie cache.

⛔ **NIE wpinać kasowania cache w `refresh_data()`** — ma ponad 130 wywołań
i leci po każdej edycji komórki. F5 samo tylko kasuje plik (natychmiast);
~9 s zapłaci dopiero okno, które katalogu potrzebuje, w swoim wątku.

## ⚠️ Nazwy kluczy

`pobierz_katalog()` (panel 4) zwraca `Symbol`, `Nazwa`, `Opis`, `Rodzaj`,
`CenaEwidencyjna` — **z wielkiej litery**.
`wczytaj_katalog_subiekta()` zwraca `symbol`, `nazwa`, `opis` — małymi.
Pomylenie tego daje pustą listę bez żadnego błędu.

Powiązane: [[project_subiekt_edytor_kartotek]], [[project_dopasuj_kartoteke_wiersza]],
[[project_treeviewselect_czysci_panel]], [[project_subiekt_staly_most]].
