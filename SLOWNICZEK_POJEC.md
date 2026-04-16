# 🇵🇱 RM_MANAGER - Słowniczek pojęć

## Podstawowe terminy

| Polski | Angielski (techniczny) | Wyjaśnienie |
|--------|------------------------|-------------|
| **Szablon** | Template | Planowane daty rozpoczęcia i zakończenia etapów (pierwotny harmonogram) |
| **Prognoza** | Forecast | Przewidywane daty uwzględniające rzeczywiste postępy i opóźnienia |
| **Odchylenie** | Variance | Różnica między planem (szablon) a rzeczywistością (w dniach) |
| **Oś czasu** | Timeline | Chronologiczny widok wszystkich etapów projektu |
| **Podsumowanie** | Dashboard | Przegląd statusu projektu, odchyleń i kluczowych informacji |
| **Ścieżka krytyczna** | Critical Path | Najważniejsze etapy, które wpływają na termin zakończenia projektu |
| **Okres** | Period | Przedział czasu, w którym etap był aktywny (może być wiele okresów dla jednego etapu) |

---

## Statusy projektu

| Polski | Angielski | Ikona | Znaczenie |
|--------|-----------|-------|-----------|
| **ZGODNIE Z PLANEM** | ON_TRACK | 🟢 | Projekt realizowany bez opóźnień |
| **ZAGROŻONY** | AT_RISK | 🟡 | Niewielkie opóźnienie, wymaga uwagi |
| **OPÓŹNIONY** | DELAYED | 🔴 | Znaczne opóźnienie, wymaga działań naprawczych |

---

## Operacje na etapach

| Przycisk | Angielski | Działanie |
|----------|-----------|-----------|
| **🟢 ROZPOCZNIJ** | START | Rozpoczyna etap projektu, zapisuje datę rozpoczęcia |
| **🔴 ZAKOŃCZ** | END | Kończy etap projektu, zapisuje datę zakończenia, oblicza odchylenie |

---

## Typy zależności między etapami

| Kod | Nazwa polska | Angielski | Opis |
|-----|--------------|-----------|------|
| **FS** | Koniec-Początek | Finish-to-Start | Etap B może rozpocząć się dopiero po zakończeniu etapu A |
| **SS** | Początek-Początek | Start-to-Start | Etap B może rozpocząć się gdy etap A się rozpocznie |
| **lag** | Opóźnienie | Lag days | Dodatkowe dni między etapami (np. czas schnięcia) |

---

## Etapy projektu (domyślne)

| Kod | Nazwa | Typowy czas |
|-----|-------|-------------|
| **PRZYJETY** | Przyjęty do realizacji | 1-2 dni |
| **PROJEKT** | Projektowanie | 14 dni |
| **KOMPLETACJA** | Kompletacja materiałów | 10 dni |
| **MONTAZ** | Montaż mechaniczny | 21 dni |
| **AUTOMATYKA** | Automatyka i programowanie | 14 dni |
| **URUCHOMIENIE** | Uruchomienie i testy | 7 dni |
| **ODBIORY** | Odbiory techniczne | 7 dni |
| **POPRAWKI** | Poprawki poodbiorowe | 7 dni |
| **WSTRZYMANY** | Projekt wstrzymany | - |
| **ZAKONCZONY** | Projekt zakończony | - |

---

## Menu i funkcje

### Menu "Plik"
- **Konfiguracja ścieżek...** - wybór lokalizacji master.sqlite
- **Nowy projekt...** - utworzenie nowego projektu (w przygotowaniu)
- **Zamknij** - zamknięcie aplikacji

### Menu "Widok"
- **Odśwież** - odświeżenie wszystkich widoków (🔄 Odśwież)

### Menu "Narzędzia"
- **Synchronizuj z RM_BAZA** - ręczna synchronizacja statusu projektu
- **Ścieżka krytyczna** - wyświetla 5 najważniejszych etapów
- **Edytuj daty szablonu i prognozy** - ✨ **NOWA FUNKCJA**

---

## Zakładki w panelu głównym

### 📅 Oś czasu
Pokazuje dla każdego etapu:
- Status (🟢 trwa, ⏺️ nieaktywny, ✔️ zakończony)
- Daty szablonu (plan)
- Daty prognozy (przewidywane)
- Odchylenie (+/- dni)
- Historia okresów (wielokrotne rozpoczęcia/zakończenia)

### 📊 Podsumowanie
Pokazuje:
- Status projektu (🟢🟡🔴)
- Całkowite odchylenie
- Przewidywane zakończenie projektu
- Aktywne etapy
- Ścieżkę krytyczną (top 5)

### 📜 Historia
Tabela ze wszystkimi okresami:
- Etap
- Data rozpoczęcia
- Data zakończenia (lub "TRWA")
- Czas trwania
- Status (Aktywny/Zakończony)

---

## Ikony i symbole

| Ikona | Znaczenie |
|-------|-----------|
| 🟢 | Etap trwa / Status OK |
| 🔴 | Zakończ etap / Opóźniony |
| 🟡 | Zagrożony |
| ⏺️  | Etap nieaktywny |
| ✔️ | Etap zakończony (rzeczywisty) |
| 📋 | Etap planowany (szablon) |
| ⚠️ | Odchylenie dodatnie (opóźnienie) |
| ✅ | Odchylenie ujemne lub zerowe (zgodny z planem) |
| 🔄 | Odśwież / Synchronizuj |
| 💾 | Zapisz |
| ✖️ | Anuluj / Błąd |
| 📂 | Wybór pliku |
| ⏳ | Operacja w toku... |

---

## Format daty

**Prawidłowy format:** `YYYY-MM-DD`

✅ **Przykłady poprawne:**
```
2026-04-15
2026-12-31
2025-01-01
```

❌ **Przykłady błędne:**
```
2026-4-5      (brak zer wiodących)
15.04.2026    (format europejski)
2026/04/15    (slash zamiast myślnika)
15-04-2026    (odwrotna kolejność)
2026-13-01    (nieprawidłowy miesiąc)
2026-02-30    (nieprawidłowy dzień)
```

---

## Kolory w GUI (motyw RM_BAZA)

| Kolor | Hex | Zastosowanie |
|-------|-----|--------------|
| Ciemnoszary | #2c3e50 | Górny pasek, nagłówki |
| Zielony | #27ae60 | Przycisk ROZPOCZNIJ, status OK |
| Czerwony | #e74c3c | Przycisk ZAKOŃCZ, błędy |
| Fioletowy | #9b59b6 | Przyciski akcji (Odśwież) |
| Pomarańczowy | #f39c12 | Ostrzeżenia |

---

## Skróty klawiaturowe

Obecnie brak dedykowanych skrótów. Możesz używać standardowych:
- `Alt+P` → Menu Plik
- `Alt+W` → Menu Widok
- `Alt+N` → Menu Narzędzia
- `Tab` / `Shift+Tab` → Nawigacja między polami
- `Enter` → Potwierdzenie (w dialogach)
- `Escape` → Anulowanie (w dialogach)

---

## Najczęściej zadawane pytania

### ❓ Jaka jest różnica między szablonem a prognozą?
**Szablon** to pierwotny plan (stały).  
**Prognoza** to przewidywanie uwzględniające rzeczywiste opóźnienia/przyspieszenia (zmienia się automatycznie).

### ❓ Czy mogę edytować prognozę?
Nie bezpośrednio. Prognoza jest obliczana automatycznie. Edytuj **szablon** lub zmień rzeczywiste daty przez **ROZPOCZNIJ/ZAKOŃCZ**.

### ❓ Co to znaczy "odchylenie +5 dni"?
Etap zakończył się 5 dni **po** planowanej dacie (opóźnienie).

### ❓ Co to znaczy "odchylenie -3 dni"?
Etap zakończył się 3 dni **przed** planowaną datą (przyspieszenie).

### ❓ Dlaczego prognoza następnego etapu się zmieniła?
Opóźnienie/przyspieszenie w jednym etapie **propaguje się** na kolejne etapy (cascading effect).

### ❓ Co to jest ścieżka krytyczna?
Lista 5 najważniejszych etapów, które **bezpośrednio wpływają** na datę zakończenia całego projektu.

### ❓ Czy mogę mieć kilka okresów dla jednego etapu?
Tak! Etap można **ROZPOCZNIJ → ZAKOŃCZ → ROZPOCZNIJ → ZAKOŃCZ...** wielokrotnie. System zapisze wszystkie okresy.

### ❓ Jak przywrócić domyślne daty szablonu?
Edytuj daty ręcznie w **Menu → Narzędzia → Edytuj daty...** lub zainicjalizuj projekt od nowa (usunięcie z rm_manager.sqlite).

---

## 📞 Wsparcie techniczne

W razie problemów:
1. Sprawdź komunikaty w dolnym pasku statusu (🟢🟡🔴)
2. Sprawdź konsolę Python (szczegółowe logi)
3. Zobacz [EDYCJA_DAT_README.md](EDYCJA_DAT_README.md) - szczegółowa dokumentacja
4. Zobacz [INSTALACJA_RM_MANAGER.md](INSTALACJA_RM_MANAGER.md) - troubleshooting

---

## 🎓 Trening

### Scenariusz testowy:

1. Uruchom `python test_rm_gui.py` (testowa baza)
2. Wybierz Projekt 100
3. Kliknij **🟢 ROZPOCZNIJ** dla etapu PROJEKT
4. Poczekaj kilka sekund
5. Kliknij **🔴 ZAKOŃCZ** dla etapu PROJEKT
6. Zobacz odchylenie (będzie bliskie 0, bo właśnie zakończone)
7. Sprawdź zakładkę **📅 Oś czasu** - zobacz propagację dat
8. Sprawdź zakładkę **📊 Podsumowanie** - status projektu
9. Menu → Narzędzia → **Edytuj daty...** - przesuń daty
10. Zapisz i zobacz jak zmienia się prognoza!

**Gratulacje!** Znasz już podstawy RM_MANAGER 🎉
