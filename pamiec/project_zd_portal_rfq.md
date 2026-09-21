---
name: project-zd-portal-rfq
description: "Zamówienia ZD wysyłane magic-linkiem przez portal RM_RFQ — zakładka Subiekt, stan wdrożenia i pułapki"
metadata: 
  node_type: memory
  type: project
  originSessionId: e0ba9b4b-d4d7-4304-bc9f-6adc6046664a
  modified: 2026-09-05T03:12:11.687Z
---

Od 2026-09-05 zamówienia ZD można wysłać dostawcy **linkiem do portalu RM_RFQ**
zamiast załącznikami w mailu. Portal liczy otwarcia, więc widać, czy dostawca
w ogóle zajrzał w rysunki. Wybór trybu jest w oknie wysyłki ZD (pole „Rysunki").

**Stan: działa lokalnie na M-OLD, na serwerze firmowym NIEWDROŻONE.**

**Przed użyciem w firmie** — `base_url` w `RM_RFQ/config.json` musi wskazywać
adres produkcyjny, w OBU miejscach (płaskim i w sekcji `server`). Dziś w obu
stoi `http://localhost:5070`, więc magic-linki prowadzą donikąd. Cloudflare nie
wymaga zmian — trasy zamówień siedzą pod `/portal/*`, objętym Bypass policy.

**Dopasowanie dostawcy idzie po NIP-ie z Subiekta**, nie po nazwie ani mailu.
Powód: „ABC s.c." istnieje wyłącznie w Subiekcie (nie ma go w RM_BAZA ani
w portalu), a jeden adres `98k@wp.pl` mają w portalu 24 firmy — ZD dla ABC
poszło jako QUAY. Tylko 6 ze 103 dostawców ma NIP po obu stronach; resztę trzeba
powiązać w oknie „Dostawcy RM_BAZA ↔ kontrahenci Subiekta".

**Widok dostawcy jest read-only na poziomie trasy** (przyjmuje tylko GET,
POST → 405), nie tylko w interfejsie. Zamówienie ma ustaloną cenę i nie podlega
negocjacji — stąd świadomy brak potwierdzenia przyjęcia w portalu.

Pliki: `data/orders/<id>/<pozycja>/`, obok `data/rfq/` i `data/casting/`.

Szczegóły i decyzje projektowe: `NOW/RM_RFQ/STATUS.md`, sekcja „Zakładka
SUBIEKT". Zob. [[project-subiekt-integracja-m-old]], [[reference-db-paths]].
