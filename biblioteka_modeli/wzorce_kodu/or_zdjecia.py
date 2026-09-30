import sys, os, base64, time
sys.path.insert(0, r"C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER")
sys.stdout.reconfigure(encoding="utf-8")
import subiekt_bridge
D = "B:/Znormalizowane/Oringi/miniatury"; zapisz = "--zapisz" in sys.argv
syms = sorted(f[:-4] for f in os.listdir(D) if f.lower().endswith(".png"))
maja, wysl, brak, bl = 0, 0, [], []; t0 = time.time()
for i, s in enumerate(syms, 1):
    try:
        st = subiekt_bridge.call("zdjecie", {"plan": {"akcja": "lista", "symbol": s}, "zapisz": False}, timeout=120, write=False)
        if any(k.get("Status") == "blad" for k in st.get("kroki", [])): brak.append(s); continue
        if st.get("zdjecia"): maja += 1; continue
        if zapisz:
            dane = open(D + "/" + s + ".png", "rb").read()
            subiekt_bridge.call("zdjecie", {"plan": {"akcja": "dodaj", "symbol": s, "nazwa": s + ".png", "typ": "png",
                                "dane_b64": base64.b64encode(dane).decode("ascii")}, "zapisz": True}, timeout=300, write=True)
        wysl += 1
    except Exception as e:
        bl.append("%s: %s" % (s, str(e)[:70]))
    if i % 50 == 0 or i == len(syms): print("%d/%d wysłane %d, miały %d, bez kartoteki %d, błędy %d (%.0f s)" % (i, len(syms), wysl, maja, len(brak), len(bl), time.time() - t0), flush=True)
print(("WYSŁANE" if zapisz else "DO WYSŁANIA"), wysl, "| miały zdjęcie:", maja, "| bez kartoteki:", brak, "| błędy:", bl[:10])
