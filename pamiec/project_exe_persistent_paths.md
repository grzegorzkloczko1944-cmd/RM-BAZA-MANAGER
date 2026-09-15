---
name: project_exe_persistent_paths
description: Pułapka PyInstaller onefile — pliki obok __file__ znikają po zamknięciu; klucz API AI trzymać w trwałej lokalizacji
metadata: 
  node_type: memory
  type: project
  originSessionId: 82f2a873-9dc2-427e-b90e-cba22eee7c22
---

**Pułapka (naprawione 2026-07-18):** w skompilowanym .exe (PyInstaller onefile) `__file__` wskazuje na katalog tymczasowy `_MEIxxxx`, który jest KASOWANY po zamknięciu aplikacji. Każdy plik zapisywany "obok __file__" (os.path.dirname(os.path.abspath(__file__))) znika po zamknięciu.

Objaw: klucz API Anthropica nie był zapamiętywany — `_ai_key_file` w rm_manager_gui.py zapisywał `.ai_api_key` obok __file__. Z Pythona działało (plik w repo), z .exe znikał → pytanie o klucz przy każdym starcie.

**Naprawa (finalna):** klucz API trzymany w `self.config['ai_api_key']` → zapisywany do `manager_sync_config.json` (CONFIG_FILE_PATH) razem z resztą ustawień, jak sms_api_token. `_ai_save_api_key` ustawia self.config i woła save_config(); `_ai_load_api_key` czyta z self.config, a przy pustym — MIGRUJE jednorazowo ze starego pliku .ai_api_key (obok CONFIG_FILE_PATH lub obok __file__). Metoda `_ai_key_file` USUNIĘTA. Powód wyboru configu zamiast osobnego pliku: mniej artefaktów + nazwa .ai_api_key za bardzo krzyczała "sekret".
UWAGA save_config: żeby ai_api_key przetrwał, musi być na liście zachowywanych kluczy w save_config (dodany obok sms_*). Bez tego kolejny zapis configu by go skasował.

Zasada: wszelkie dane trwałe (klucze, cache, ustawienia user) w .exe MUSZĄ iść do stałej ścieżki (CONFIG_FILE_PATH dir / APPDATA / ~), NIGDY obok __file__.

Powiązane: [[project_ai_chart_rendering]], [[reference_db_paths]].
