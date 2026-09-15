---
name: project_zd_szablon_adresowy
description: "ZD nie ma Odbiorcy, adres dostawy = Techniczna 2 (AdresMojejFirmy); Subiekt wypelnial to sam i wysylal dostawce do RMPAK-u w Konstancinie"
metadata: 
  node_type: memory
  type: project
  originSessionId: 58f9b752-f127-4b24-a83d-09f1cb22b23c
  modified: 2026-09-15T14:36:42.458Z
---

**Stały szablon adresowy zamówienia do dostawcy** (commit `eb21869`,
15.09.2026, sprawdzone na produkcji).

**Problem:** Subiekt wypełniał sekcje adresowe ZD **sam** — RM_BAZA nigdzie
ich nie ustawiała. Na wydruku wychodziło:

```
Odbiorca:      RMPAK Sp. z o.o., Kazimierza Pułaskiego 20, Konstancin-Jeziorna
Adres dostawy: Kazimierza Pułaskiego 20, Konstancin-Jeziorna
```

Czyli dostawca dostawał polecenie wysłania towaru **do RMPAK-u**, podczas gdy
materiał przyjeżdża do nas na **Techniczną 2, Piaseczno**.

**Reguła (decyzja użytkownika: „zawsze", stały szablon):**
- `Odbiorca` + `OdbiorcaWybrany` → `null` (wzorzec drukuje sekcję tylko dla
  ustawionego podmiotu — brak podmiotu = brak sekcji na wydruku)
- cztery pola adresu dostawy → `AdresMojejFirmy`:
  `MiejsceDostawyZewnetrzne`, `AdresOdbiorcy`, `AdresDostawOdbiorcy`,
  `AdresKorespondencyjnyOdbiorcy`

Kod: `Zd.cs` → `UstawAdresyZamowienia()`, wołane po ustawieniu daty
wystawienia, przy każdym zakładanym ZD.

**How to apply:**
- ⚠️ **ŻADNYCH Id NA SZTYWNO.** Na produkcji adres firmy = `101251`,
  Konstancin = `100013`, ale to numery TEJ bazy — na innej instalacji będą
  inne. Adres bierzemy z samego dokumentu (`AdresMojejFirmy`), który Subiekt
  wypełnia poprawnie.
- ⚠️ Zapis przez `UstawWartosc()` z **odczytem kontrolnym** — ta sama pułapka
  Sfery co przy Uwagach i Tytule: setter przy jawnej implementacji interfejsu
  potrafi po cichu nic nie zrobić. Patrz [[project_subiekt_uwagi_tytul]].
- Błąd szablonu **nie przerywa** zakładania ZD — leci krok „uwaga" do raportu.
- **Jak znaleźć nazwy pól:** tryb `wydruk-recon` wypisuje teraz
  `pola_adresowe` (nazwa, typ, wartość, czy zapisywalne). Dokument ZD ma ich
  ~60 i bez tego zgadywanie, które odpowiada za sekcję na wydruku, jest
  bezcelowe.
- **Jak zweryfikować wydruk:** `pymupdf` jest zainstalowany —
  `pymupdf.open(pdf)[0].get_text()`. ⚠️ Ręczne rozpakowywanie strumieni
  PDF-a regexem NIE DZIAŁA na tych wydrukach (czcionki inaczej kodowane),
  daje fałszywe „brak" dla każdego słowa.
- Procedura testu na produkcji, gdyby trzeba powtórzyć: założyć ZD trybem
  `zd --zapisz`, sprawdzić `wydruk-recon` + PDF, usunąć trybem
  `zd-usun --zapisz`, potwierdzić że zapotrzebowanie wróciło do stanu
  sprzed testu (pozycja wraca, gdy ZD zniknie).
- ZD wysłane wcześniej zostają bez zmian — zmiana dokumentu, który dostawca
  już dostał mailem, niczego u niego nie odkręca.
- Most wystawiony: `\\W2019S\RM_SERWER$\MOST` (sha `eb21869`).
  Patrz [[project_subiekt_wysylka_zd]], [[project_zd_pdf_brakujace_dll]].
