# 🎯 Interaktywna Edycja Dat na Wykresie - Quick Guide

## ✨ Nowa funkcjonalność - Drag & Resize

**Możesz teraz edytować daty szablonu bezpośrednio na wykresie Gantt przez przeciąganie krawędzi pasków myszką!**

### 🖱️ Dwa tryby edycji:

1. **🎯 Drag & Resize** (ZALECANE) - Przeciągnij krawędź paska myszką
2. **📝 Dialog** (FALLBACK) - Kliknij środek paska aby otworzyć okno z formularzem

---

## 🚀 Jak używać - Drag & Resize

### 1. Otwórz wbudowany wykres

1. Wybierz projekt z listy
2. Przejdź do zakładki **"Wykresy"**
3. Kliknij **"📊 Wbudowany wykres"** (wymaga matplotlib)

### 2. Znajdź krawędź paska szablonu

- **Najedź myszką** na początek lub koniec szarego paska (szablon)
- **Kursor zmieni się na ↔** (resize cursor) gdy jesteś nad krawędzią
- **Status bar** pokaże: *"🖱️ Przeciągnij aby zmienić początek/koniec szablonu: ETAP"*

### 3. Przeciągnij krawędź

- **Kliknij i przytrzymaj** lewym przyciskiem myszy na krawędzi
- **Przeciągnij** w lewo (wcześniejsza data) lub w prawo (późniejsza data)
- **Czerwona linia przerywana** pokazuje preview nowej pozycji
- **Status bar** pokazuje datę pod kursorem

### 4. Puść przycisk myszy

- **Nowa data zostanie automatycznie zapisana** do bazy
- **Prognoza zostanie przeliczona** (uwzględniając zależności)
- **Wykres zostanie odświeżony**
- **Status bar** pokaże potwierdzenie: *"✅ Zaktualizowano początek/koniec szablonu: ETAP → DD-MM-YYYY"*

### 5. Anulowanie przeciągania

- **Przesuń mysz poza wykres** i puść przycisk - operacja zostanie anulowana
- **Status bar** pokaże: *"⚠️ Przeciąganie anulowane (puszczono poza wykresem)"*

---

## 📝 Tryb Dialog (fallback)

### Kiedy używać dialogu?
- Gdy chcesz wprowadzić konkretną datę z klawiatury
- Gdy wolisz wpisać datę niż przeciągać myszką
- Gdy trudno trafić w krawędź (np. bardzo krótkie paski)

### Jak otworzyć dialog?
- **Kliknij środek szarego paska** (nie krawędź!)
- Otworzy się okno z polem do wprowadzenia daty
- Format: **DD-MM-YYYY** (np. `15-04-2026`)
- Naciśnij **Enter** lub **💾 Zapisz**

---

## 🎨 Kolory pasków na wykresie

| Kolor | Typ | Drag & Resize | Dialog | Hover Cursor |
|-------|-----|---------------|--------|--------------|
| 🩶 **Szary** | Szablon (plan) | ✅ TAK | ✅ TAK | ↔ (na krawędzi), 👆 (na środku) |
| 🟢 **Zielony** | Rzeczywiste okresy | ❌ Nie | ❌ Nie | → (default) |
| 🔵 **Niebieski** | Prognoza | ❌ Nie | ❌ Nie | → (default) |
| 🟢 **Jasno-zielony** | Milestone | ❌ Nie | ❌ Nie | → (default) |

---

## 🎯 Wskazówki i triki

### Precyzyjne pozycjonowanie
- **Tolerancja krawędzi:** ±3 dni - kursor zmienia się na ↔ gdy jesteś w odległości 3 dni od początku/końca
- **Zoom:** Użyj narzędzi zoom z paska matplotlib aby powiększyć wykres i precyzyjniej ustawić datę
- **Preview:** Czerwona linia przerywana pokazuje dokładnie gdzie zostanie ustawiona nowa data

### Skróty klawiszowe podczas drag
- **Nie ma** - przeciąganie działa tylko myszką
- Aby anulować: przesuń myszkę poza wykres przed puszczeniem

### Szybka edycja całego harmonogramu
1. **Przeciągnij początek** pierwszego etapu (PROJEKT)
2. System automatycznie przeliczy wszystkie następne etapy (zależności FS/SS)
3. Jeśli chcesz zmienić czas trwania - **przeciągnij koniec** paska

### Visual feedback
- **Najedź na krawędź** → kursor ↔ + komunikat w status bar
- **Najedź na środek** → kursor 👆 + komunikat "Kliknij aby edytować"
- **Podczas drag** → czerwona linia preverywana + data w status bar
- **Po zapisie** → wykres odświeżony + zielony komunikat sukcesu

---

## 💡 Przykładowy scenariusz - Drag & Resize

**Scenariusz:** Projekt "Linia A" - montaż trwa dłużej, trzeba przesunąć koniec o 5 dni

### Stary sposób (dialog):
1. Menu → Narzędzia → Edytuj daty
2. Znajdź MONTAŻ w tabeli
3. Kliknij pole "Szablon Koniec"
4. Wpisz nową datę
5. Zapisz
6. Czekaj na przeliczenie
7. Czekaj na odświeżenie

**⏱️ Czas: ~30 sekund, 7 kroków**

### Nowy sposób (drag & resize):
1. Najedź na prawy koniec szarego paska MONTAŻ
2. Przeciągnij w prawo o ~5 dni
3. Puść mysz

**⏱️ Czas: ~3 sekundy, 3 kroki** ✨

---

## 🔒 Uprawnienia

**Wymagane uprawnienie:** `can_edit_dates`

### Komunikaty błędów uprawnień:
```
🚫 Brak uprawnień do edycji dat (rola: VIEWER)
```
**Rozwiązanie:** Skontaktuj się z administratorem aby zmienić rolę na `PLANNER` lub `ADMIN`

---

## 🐛 Rozwiązywanie problemów

### "Kursor nie zmienia się na ↔"
**Przyczyna:** Nie jesteś wystarczająco blisko krawędzi paska
**Rozwiązanie:**
- Przybliż wykres (zoom)
- Najedź dokładnie na początek lub koniec szarego paska
- Tolerancja: ±3 dni od krawędzi

### "Można edytować tylko paski szablonu (szare)"
**Przyczyna:** Najechałeś/kliknąłeś na zielony (rzeczywiste) lub niebieski (prognoza) pasek
**Rozwiązanie:**
- Znajdź szary pasek - zazwyczaj jest pod spodem lub obok
- Jeśli nie widzisz szarego paska = szablon nie jest ustawiony, ustaw go najpierw przez dialog

### "Przeciąganie anulowane (puszczono poza wykresem)"
**Przyczyna:** Przypadkowo przesunąłeś mysz poza wykres przed puszczeniem
**Rozwiązanie:**
- Spróbuj ponownie, tym razem upewnij się że puszczasz mysz wewnątrz obszaru wykresu
- Lub użyj trybu dialog (kliknij środek paska)

### "Data końca nie może być wcześniejsza niż data początku"
**Przyczyna:** Przeciągnąłeś koniec paska przed jego początek (lub odwrotnie)
**Rozwiązanie:**
- Przeciągnij ponownie w drugą stronę
- Lub użyj trybu dialog do wprowadzenia konkretnej daty

### Wykres się nie odświeża po drag
**Przyczyna:** Rzadki błąd odświeżania
**Rozwiązanie:**
- Kliknij przycisk **🔄 Wbudowany wykres** ponownie
- Lub kliknij **🔄 Odśwież** w menu Widok

### ✨ Wykres zachowuje widok po edycji
**Funkcja:** Po przeciągnięciu i zapisaniu daty, wykres automatycznie:
- ✅ Zachowuje aktualne ustawienia zoom
- ✅ Zachowuje aktualne ustawienia pan (przesunięcie)
- ✅ Nie resetuje widoku do domyślnego
- ✅ Pozostajesz dokładnie tam gdzie byłeś przed edycją

**Dzięki temu:** Możesz szybko edytować wiele pasków bez utraty kontekstu wizualnego!

---

## 📋 Przykładowy scenariusz użycia

**Scenariusz:** Projekt "Linia A" - rozpoczęliśmy projektowanie tydzień później niż planowano

1. Otwieram projekt "Linia A" (ID: 123)
2. Przechodzę do zakładki "Wykresy" → "📊 Wbudowany wykres"
3. Widzę szary pasek dla etapu PROJEKT (szablon: 01-04-2026 → 15-04-2026)
4. Klikam na **lewą część** szarego paska PROJEKT
5. W dialogu zmieniam datę z `01-04-2026` na `08-04-2026` (+7 dni)
6. Klikam **💾 Zapisz**
7. System automatycznie:
   - Aktualizuje szablon PROJEKT na 08-04-2026 → 22-04-2026 (zachowuje 14 dni trwania)
   - Przesuwa prognozę KOMPLETACJA na 22-04-2026 (FS dependency)
   - Przesuwa wszystkie kolejne etapy zgodnie z zależnościami
8. Wykres pokazuje nowy harmonogram - cały projekt przesunięty o 7 dni

---

## 🔗 Powiązane funkcje

- **Menu → Narzędzia → Edytuj daty szablonu i prognozy** - pełna tabela wszystkich dat
- **Menu → Narzędzia → Ścieżka krytyczna** - zobacz które etapy blokują projekt
- **Zakładka Dashboard** - sprawdź odchylenie od planu po zmianach

---

## 📊 Porównanie metod edycji

| Metoda | Szybkość | Precyzja | Łatwość | Najlepsze do |
|--------|----------|----------|---------|--------------|
| **🎯 Drag & Resize** | ⚡⚡⚡ Bardzo szybka | 🎯🎯 Dobra (±1 dzień) | 👍👍👍 Bardzo łatwa | Szybkich korekt, przesunięć |
| **📝 Dialog** | 🐌 Wolna | 🎯🎯🎯 Idealna | 👍👍 Średnia | Wprowadzania dokładnych dat |
| **📋 Pełna tabela** | 🐌🐌 Najwolniejsza | 🎯🎯🎯 Idealna | 👍 Trudna | Planowania całego harmonogramu |

**Najlepsze podejście:**
- **90% czasu:** Drag & Resize - szybkie, intuicyjne przeciąganie
- **10% czasu:** Dialog - gdy potrzebujesz konkretnej daty lub drag nie działa
- **Rzadko:** Pełna tabela - planowanie całego projektu od zera

---

## ✅ Zaimplementowano

### Drag & Resize (v2.0)
- ✅ Hover detection - detekcja krawędzi paska (±3 dni tolerancji)
- ✅ Cursor feedback - zmiana kursora na ↔ przy krawędzi, 👆 na środku
- ✅ Drag start - rozpoczęcie przeciągania po kliknięciu krawędzi
- ✅ Motion tracking - śledzenie ruchu myszy podczas drag
- ✅ Visual preview - czerwona linia przerywana pokazująca nową pozycję
- ✅ Live date display - wyświetlanie daty pod kursorem w status bar
- ✅ Drag end - zapisanie nowej daty po puszczeniu myszy
- ✅ Cancel support - anulowanie przez puszczenie poza wykresem
- ✅ Validation - sprawdzanie zgodności dat (koniec >= początek)
- ✅ Auto forecast - automatyczne przeliczanie prognozy
- ✅ Auto refresh - odświeżanie wykresu po zapisie
- ✅ **View preservation** - zachowanie zoom/pan po odświeżeniu (stabilny widok!)

### Dialog (v1.0 - fallback)
- ✅ Click detection - detekcja kliknięcia środka paska
- ✅ Single date dialog - prosty dialog do edycji jednej daty
- ✅ Keyboard support - Enter = zapisz, Escape = anuluj
- ✅ Format validation - DD-MM-YYYY → YYYY-MM-DD
- ✅ Logic validation - data końca >= data początku

### Uprawnienia
- ✅ Permission check - sprawdzanie `can_edit_dates`
- ✅ Error messages - przyjazne komunikaty o braku uprawnień

---

## 🎓 Przykłady użycia

### Przykład 1: Przesunięcie startu projektu o tydzień
**Zadanie:** Projektowanie zaczyna się tydzień później

**Krok po kroku:**
1. Otwórz wykres projektu
2. Znajdź szary pasek PROJEKT
3. Najedź na **lewą krawędź** (początek)
4. Kursor zmieni się na ↔
5. Przeciągnij w **prawo** o ~7 pozycji (dni)
6. Czerwona linia pokazuje preview nowej daty
7. Puść mysz
8. ✅ Gotowe! Wszystkie następne etapy przesunięte automatycznie

### Przykład 2: Wydłużenie montażu o 3 dni
**Zadanie:** Montaż potrwa dłużej niż planowano

**Krok po kroku:**
1. Otwórz wykres projektu
2. Znajdź szary pasek MONTAŻ (MONTAZ)
3. Najedź na **prawą krawędź** (koniec)
4. Kursor zmieni się na ↔
5. Przeciągnij w **prawo** o ~3 pozycje (dni)
6. Puść mysz
7. ✅ Gotowe! Czas trwania montażu wydłużony, kolejne etapy przesunięte

### Przykład 3: Precyzyjna data - dialog
**Zadanie:** Kompletacja musi zakończyć się dokładnie 2026-05-15

**Krok po kroku:**
1. Otwórz wykres projektu
2. Znajdź szary pasek KOMPLETACJA
3. Kliknij **środek** paska (nie krawędź!)
4. Otworzy się dialog
5. Wpisz datę: `15-05-2026`
6. Enter lub 💾 Zapisz
7. ✅ Gotowe! Data ustawiona precyzyjnie

---

## 🔧 Szczegóły techniczne

### Tolerancja detekcji krawędzi
```python
tolerance_days = 3  # ±3 dni od krawędzi
```
Jeśli kursor jest w odległości 3 dni od początku lub końca paska - traktowane jako krawędź.

### Event handlers
- `button_press_event` → `_on_chart_press()` - rozpoczęcie drag lub dialog
- `motion_notify_event` → `_on_chart_motion()` - hover + preview podczas drag
- `button_release_event` → `_on_chart_release()` - zapisanie nowej daty

### Visual feedback
- **Resize cursor:** `sb_h_double_arrow` (↔)
- **Click cursor:** `hand2` (👆)
- **Preview line:** Czerwona linia przerywana (`--`), alpha=0.7
- **zorder=1000:** Linia preview zawsze na wierzchu

### Walidacja
1. **Format daty:** DD-MM-YYYY → konwersja do ISO (YYYY-MM-DD)
2. **Logika dat:** data_końca >= data_początku
3. **Uprawnienia:** `can_edit_dates` przed każdą edycją

### Auto-update po edycji
```python
# Zapisz widok przed odświeżeniem
saved_xlim = ax.get_xlim()  # Zakres osi X (daty)
saved_ylim = ax.get_ylim()  # Zakres osi Y (etapy)

# 1. Zapisz do bazy (stage_schedule.template_start/end)
# 2. Przelicz prognozę (rmm.recalculate_forecast)
# 3. Odśwież wykres (create_embedded_gantt_chart with preserve_view=True)

# Przywróć widok po odświeżeniu
ax.set_xlim(saved_xlim)  # Zachowaj zoom na osi czasu
ax.set_ylim(saved_ylim)  # Zachowaj scroll etapów
canvas.draw_idle()

# 4. Pokaż komunikat (status_bar.config)
```

**Efekt:** Wykres pozostaje dokładnie w tym samym miejscu i przybliżeniu co przed edycją!

---

## 🎯 Roadmap (przyszłe funkcje)

### Planowane ulepszenia:
- [ ] **Undo/Redo** - cofnięcie ostatniej zmiany (Ctrl+Z)
- [ ] **Multi-select drag** - przeciąganie wielu pasków na raz
- [ ] **Snap to grid** - przyciąganie do siatki (dni, tygodnie)
- [ ] **Keyboard shortcuts** - strzałki do przesuwania o 1 dzień
- [ ] **Visual diff** - pokazanie zmian przed/po
- [ ] **History panel** - lista ostatnich zmian
- [ ] **Touch support** - wsparcie dla tabletów/ekranów dotykowych

### ✅ Ostatnio zaimplementowane:
- [x] **View preservation** - zachowanie zoom/pan po odświeżeniu (v2.1, 16.04.2026)

### Zgłoś sugestię:
Jeśli masz pomysł na ulepszenie - napisz do zespołu deweloperskiego!

---

**Autor:** RM_MANAGER Development Team  
**Data:** 16.04.2026  
**Wersja:** 2.1 (Drag & Resize + View Preservation)  
**Changelog:**
- v2.1 (16.04.2026): Dodano zachowanie zoom/pan po odświeżeniu wykresu
- v2.0 (16.04.2026): Drag & Resize - przeciąganie krawędzi pasków myszką
- v1.0 (16.04.2026): Dialog edycji pojedynczej daty po kliknięciu
