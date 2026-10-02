---
name: reference_szukanie_czesci_marketplace
description: Szukanie części na OLX/eBay/Allegro (poza RM_BAZA) — OLX ma publiczne API bez logowania, eBay Browse API z darmowym kluczem, Allegro offers/listing tylko dla zweryfikowanych aplikacji; printing-press-library nie ma OLX/Allegro
metadata:
  type: reference
---

Rozpoznane 02.10.2026 na prośbę usera („interesuje mnie przeszukiwanie ebay, allegro, olx" — szukanie części i podzespołów, NIE w RM_BAZA). Nic nie zbudowane — user nie zdecydował.

- **OLX** — `https://www.olx.pl/api/v1/offers/?query=<fraza>&limit=40&offset=..` (opcj. `category_id`, `sort_by=created_at:desc`), bez logowania, z nagłówkiem `User-Agent`. Cena w `params[key=price].value.label`, miasto `location.city.name`, link `url`. Test: „siłownik pneumatyczny" → 865 ofert. Nieudokumentowane oficjalnie — może się zmienić.
- **eBay** — oficjalne Browse API (wyszukiwanie aktywnych ofert, filtry cena/stan/kraj/wysyłka do PL, marketplace przez `X-EBAY-C-MARKETPLACE-ID`, np. EBAY_DE); darmowe konto deweloperskie + klucz; produkcyjny keyset wymaga zgłoszenia zwolnienia z powiadomień o usunięciu kont. Sprzedane oferty tylko przez Marketplace Insights (po zgodzie eBay). Finding API wyłączone 02.2025. (Z wiedzy, nie testowane.)
- **Allegro** — `GET /offers/listing` od 1.06.2021 TYLKO dla zweryfikowanych aplikacji (wniosek przez formularz), okrojone (10 stron, sprzedaż w przedziałach); zgłoszenie z 17.09.2026 (allegro-api #14013) bez odpowiedzi. Scraping strony — ochrona przed botami + regulamin, odradzone. Realnie: link do wyszukiwarki allegro.pl z frazą i filtrami.
- **printing-press-library** (github mvanhorn) — 546 CLI dla agentów, prawie wyłącznie US/Azja; brak OLX/Allegro/Ceneo; `ebay-pp-cli` działa na ciasteczkach Chrome, blokowany przez Akamai, połowa funkcji to atrapy. `kegol/olx-monitor` (PL, 0 gwiazdek, jeden dzień pracy) — tylko nieruchomości/auta.
- Alternatywa od ręki: wyszukiwanie w sieci / TinyFish w sesji Claude (płatne za uruchomienie).
