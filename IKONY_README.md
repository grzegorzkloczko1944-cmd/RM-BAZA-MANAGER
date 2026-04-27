# 🎨 Ikony aplikacji - Instrukcja

## Szybki start

### 1. Wygeneruj ikony

```bash
python generate_icons.py
```

To utworzy:
- `rm_manager_icon.ico` + `rm_manager_icon.png` — biała litera **M** na czerwonym tle
- `rm_baza_icon.ico` + `rm_baza_icon.png` — biała litera **B** na czerwonym tle

### 2. Uruchom aplikację

Ikony będą automatycznie załadowane w oknie głównym (jeśli pliki `.ico` istnieją).

### 3. Kompilacja z ikoną

#### RM_MANAGER

```bash
pyinstaller RM_MANAGER.spec
```

Plik `.spec` już zawiera konfigurację ikony (`icon='rm_manager_icon.ico'`).

#### RM_BAZA (gdy będzie spec file)

Dodaj do pliku `.spec` w sekcji `EXE`:

```python
exe = EXE(
    ...
    icon='rm_baza_icon.ico',
)
```

---

## Wymagania

```bash
pip install Pillow
```

---

## Personalizacja

Edytuj `generate_icons.py` aby zmienić:

- **Kolor tła**: `bg_color = (220, 53, 69)`
- **Kolor tekstu**: `text_color = (255, 255, 255)`
- **Rozmiar**: `create_icon('M', 'plik.ico', size=256)`
- **Literę**: `create_icon('RM', ...)` — może być więcej niż jedna litera

---

## Troubleshooting

### Błąd: "ModuleNotFoundError: No module named 'PIL'"

```bash
pip install Pillow
```

### Ikona nie pojawia się w GUI

- Sprawdź czy pliki `.ico` są w tym samym katalogu co skrypty Python
- Sprawdź komunikaty w konsoli: `⚠️ Nie można załadować ikony: ...`

### Ikona nie pojawia się po kompilacji

- Upewnij się że plik `.ico` istnieje **przed** kompilacją
- Sprawdź czy ścieżka w `.spec` jest poprawna: `icon='rm_manager_icon.ico'`
- **Windows**: Explorer może cachować ikony — restart eksploratora lub komputera

---

## Struktura plików

```
RM-BAZA-MANAGER/
├── generate_icons.py          # Skrypt generujący
├── rm_manager_icon.ico         # Ikona RM_MANAGER (Windows)
├── rm_manager_icon.png         # Ikona RM_MANAGER (PNG)
├── rm_baza_icon.ico            # Ikona RM_BAZA (Windows)
├── rm_baza_icon.png            # Ikona RM_BAZA (PNG)
├── RM_MANAGER.spec             # Konfiguracja PyInstaller
├── rm_manager_gui.py           # ← ustawia ikonę w GUI
└── RM_BAZA_v15_MAG_STATS_ORG.py # ← ustawia ikonę w GUI
```

---

## Format .ico

Generated icons contain multiple sizes for Windows optimization:
- 16×16, 32×32, 48×48, 64×64, 128×128, 256×256

This ensures sharp display in:
- Task bar
- Alt+Tab switcher
- File Explorer (różne widoki)
- Shortcut icons
