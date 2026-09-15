---
name: project_ai_chart_rendering
description: "AI Asystent RM_MANAGER umie rysować wykresy (Gantt/bar) — narzędzie render_chart, matplotlib→PNG osadzany w tk.Text"
metadata: 
  node_type: memory
  type: project
  originSessionId: 82f2a873-9dc2-427e-b90e-cba22eee7c22
---

AI Asystent harmonogramu (rm_ai_optimizer.py) ma narzędzie **render_chart** (dodane 2026-07-15) rysujące wykresy graficzne.

**Jak działa:**
- Narzędzie `render_chart(chart_type, title, items)` w AIOptimizerContext. Typy: 'gantt' (oś czasu, items z label+start+end+color) i 'bar' (słupki, items z label+value). Kolory: red/orange/green/blue (red=opóźnione). Gantt rysuje linię "dziś".
- matplotlib backend 'Agg' (bezpieczny w wątku roboczym GUI), zapis PNG do tempfile.
- Ścieżki PNG → `context.chart_paths` (lista, zerowana na starcie każdej tury w run_ai_agent).
- GUI (rm_manager_gui.py, ai_chat_dialog ~27737): po session.send() `_finish` czyta session.context.chart_paths i osadza obrazy w tk.Text przez `_embed_chart` (PIL→ImageTk, image_create). Referencje PhotoImage trzymane w liście `chat_images` — inaczej tkinter je zwalnia.
- SYSTEM_PROMPT + oba pliki ai_rules.txt (Y:\RM_MANAGER\ + lokalny repo) mówią agentowi że UMIE rysować (wcześniej odpowiadał "nie umiem").

**PyInstaller:** dodano matplotlib do RM_MANAGER.spec (hiddenimports + collect_all). Bez tego .exe padał na import matplotlib. PIL już był.

Powiązane: [[project_ai_optimizer_stages_paths]].
