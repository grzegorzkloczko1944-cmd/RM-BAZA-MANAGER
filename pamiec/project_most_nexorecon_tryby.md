---
name: project-most-nexorecon-tryby
description: "Most NexoRecon — podział trybów odczytu, kasowanie dokumentów, konieczność przebudowy po git pull"
metadata: 
  node_type: memory
  type: project
  originSessionId: e0ba9b4b-d4d7-4304-bc9f-6adc6046664a
  modified: 2026-09-05T03:12:29.491Z
---

**Po `git pull` na firmowej maszynie trzeba przebudować most:**
`dotnet build -c Release` w `subiekt_sfera/NexoRecon`. `NexoRecon.exe` nie jest
w repozytorium — tylko źródła `.cs`. Bez tego nowe tryby nie działają.

**Trzy tryby odczytu, każdy do czego innego** (2026-09-05):

- `stan` — pyta punktowo o KONKRETNE symbole (`--symbols-file`), zwraca też
  ostatnią cenę zakupu i datę przyjęcia. Pod projekt: „czy mam to, czego
  potrzebuję do tego BOM-u".
- `katalog` — pełna lista {Symbol, Nazwa} BEZ stanów, do dopasowania po nazwie.
  Stany pominięte świadomie: `StanyMagazynowe` per kartoteka to najdroższa
  część odczytu.
- `magazyn` — pełna lista ZE stanami. „Co w ogóle mam na magazynie". Bez
  historii FZ (drugi kosztowny przelot). Pomiar na demo: 14 s, 27 pozycji.

**`zd-usun` kasuje ZK, ZD, RW i WZ** — rodzaj rozpoznaje z prefiksu numeru,
więc jedno wywołanie sprząta mieszaną listę. Nazwa trybu została historyczna.

**Pułapka: `MoznaUsunac` istnieje na ZD, ale NIE na ZK** (`ZamowienieOdKlientaBO`
→ RuntimeBinderException). Własność sprawdzana refleksją; przy jej braku
próbujemy usunąć i łapiemy ewentualną odmowę Subiekta.

**Kolejność kasowania: ZD PRZED ZK.** ZD powstaje z powiązaniem do ZK, więc
usunięcie ZK jako pierwszego zostawia osierocone zamówienie, a Subiekt potrafi
wtedy odmówić skasowania samego ZK.

**Asortyment nie ma pola magazynu ani jednostki miary wprost.** Kartoteka to
sama definicja towaru; stan powstaje z dokumentu przyjęcia (PZ/FZ) i to on
wskazuje magazyn — dlatego jedna kartoteka ma stany na kilku magazynach naraz.

Zob. [[project-subiekt-integracja-m-old]], [[project-zd-portal-rfq]].
