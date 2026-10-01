"""Klika „Tak” w oknie 'Microsoft Visual Basic for Applications' (błąd ładowania modułu VBA)
wyłącznie dla procesów Inventor.exe, które NIE są sesjami użytkownika (PID w CHRONIONE).
python watchdog_vba.py <pid_chroniony> [<pid_chroniony> ...]"""
import sys, time, ctypes, ctypes.wintypes as wt, win32gui, win32con, win32process
CHRONIONE = {int(x) for x in sys.argv[1:]}
LOG = open(__file__.replace("watchdog_vba.py", "watchdog_log.txt"), "a", encoding="utf-8")
u32 = ctypes.windll.user32
def tekst(h):
    try: return win32gui.GetWindowText(h)
    except Exception: return ""
def przyciski(h):
    out = []
    win32gui.EnumChildWindows(h, lambda c, _: out.append(c), None)
    return [c for c in out if win32gui.GetClassName(c) == "Button"]
def okna():
    res = []
    win32gui.EnumWindows(lambda h, _: res.append(h), None)
    return res
def czy_inventor(pid):
    PROCESS_QUERY_LIMITED = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
    if not h: return False
    buf = ctypes.create_unicode_buffer(260); n = wt.DWORD(260)
    ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
    ctypes.windll.kernel32.CloseHandle(h)
    return buf.value.lower().endswith("inventor.exe")
print("watchdog start; chronione PID:", sorted(CHRONIONE), flush=True)
while True:
    for h in okna():
        if not win32gui.IsWindowVisible(h): continue
        if tekst(h) != "Microsoft Visual Basic for Applications": continue
        pid = win32process.GetWindowThreadProcessId(h)[1]
        if pid in CHRONIONE or not czy_inventor(pid): continue
        tak = [b for b in przyciski(h) if tekst(b).replace("&", "").strip().lower() in ("tak", "yes")]
        if tak:
            win32gui.PostMessage(tak[0], win32con.BM_CLICK, 0, 0)
            msg = "%s kliknięto Tak (pid %d)" % (time.strftime("%H:%M:%S"), pid)
            print(msg, flush=True); LOG.write(msg + "\n"); LOG.flush()
            time.sleep(1)
    time.sleep(0.3)
