# -*- coding: utf-8 -*-
"""Opis pozycji IGUS (iProperties Description) wg nazw na igus.pl, w skrócie, po polsku."""
import re

def opis(sym):
    s = sym.upper().strip()
    if re.match(r"[ER]\d", s): return "prowadnik kablowy e-chain"
    if re.match(r"(KBRM|KBM|KGLM|GLRM|GERM|EGLM|KSTM|KGHM|KARM)", s): return "łożysko kuliste"
    if s.startswith("PRT"):
        if "HTD8M" in s: return "łożysko obrotowe z uzębieniem HTD8M"
        if "AT10" in s: return "łożysko obrotowe z uzębieniem AT10"
        if "-TO" in s: return "łożysko obrotowe z uzębieniem"
        return "łożysko obrotowe"
    m = re.match(r"WJ(\d*)([A-Z]*)-(\d{2})", s)
    if m:
        lit = m.group(2)
        if lit.startswith("RM"): return "łożysko hybrydowe z podwójną rolką" if m.group(3) == "21" else "łożysko hybrydowe"
        if lit.endswith("E") and lit not in ("",): return "oprawa stojakowa, kasowanie luzu"      # UME, QME: luz regulowany (igus: „clearance infinitely adjustable”)
        return "oprawa stojakowa"
    if re.match(r"WSX-", s): return "szyna podwójna"
    mb = re.match(r"^((?:WSQ|WS)-\d{2}-\d{2,3})(?:\s|$)", s)
    if mb and mb.group(1) in ("WS-10-40", "WS-10-80", "WS-16-60", "WS-20-80", "WS-25-120", "WSQ-06-30", "WSQ-10-40", "WSQ-10-80"): return "system prowadnicy liniowej"
    if re.match(r"WSQ-|WS-", s): return "szyna pojedyncza"
    if re.match(r"WW-", s): return "kompletny wózek"
    if re.match(r"(WWP|WWPL|WWPV|WWC|WWS|WWBCX|WK|WEKA)", s): return "element prowadnicy drylin W"
    if re.match(r"TS-", s): return "szyna prowadząca"
    if re.match(r"TW-", s): return "wózek liniowy"
    if re.match(r"TK-", s): return "element prowadnicy drylin T"
    if re.match(r"NW-", s): return "wózek prowadzący"
    if re.match(r"RJUM-", s): return "liniowe łożysko ślizgowe"
    if re.match(r"FJUM-|QJFM-", s): return "oprawa kołnierzowa"
    if re.match(r"(SLW|RJ4JP)", s): return "łożysko liniowe drylin R"
    m = re.match(r"([A-Z]{1,2})(SM|FM|TM|PM|UM|UCM)-", s)
    if m:
        return {"SM": "tuleja ślizgowa", "FM": "tuleja ślizgowa z kołnierzem", "TM": "podkładka oporowa", "PM": "płytka ślizgowa"}.get(m.group(2), "łożysko ślizgowe")
    return None

def wymiar(sym):
    """Wymiary tulei iglidur z kodu: [litera][SM|FM|…]-d1d2-b  ->  'Ø12 × Ø16 × 20 mm' (średnica wewn. × zewn. × długość)."""
    m = re.match(r"^[A-Z]{1,2}(?:SM|FM|TM|PM|UM|UCM)-(\d{2})(\d{2})-(\d{2})$", sym.upper().strip())
    if not m: return None
    d1, d2, b = (int(x) for x in m.groups())
    return "Ø%d × Ø%d × %d mm" % (d1, d2, b)

if __name__ == "__main__":
    for t in ("MSM-1216-20", "PSM-4550-30", "GFM-0810-10", "WFM-5055-40", "XSM-0405-10", "ZFM-7580-50", "JUCM-1620-20", "WS-20-80"):
        print("%-14s %s" % (t, wymiar(t)))
    for t in ("WJ200UM-01-10", "WJ200UME-01-10", "WJ200QM-01-06", "WJ200UME-01-16", "WJRM-01-10", "WSQ-10-80", "WS-20 L200", "PRT-01-150-TO-AT10", "PRT-01-200-TO-HTD8M", "PSM-4550-30", "GFM-0810-10", "E2C.15.30.038.0 L240", "NW-12-80", "TW-01-20", "WJUME-01-10"):
        print("%-22s %s" % (t, opis(t)))
