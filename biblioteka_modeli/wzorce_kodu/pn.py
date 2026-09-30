import os,win32com.client
D="B:/Znormalizowane/Oringi"
a=win32com.client.Dispatch("Inventor.ApprenticeServer")
bad=[]
fs=sorted(f for f in os.listdir(D) if f.endswith(".ipt"))
for f in fs:
    d=a.Open(os.path.normpath(D+"/"+f))
    try: pn=d.PropertySets.Item("Design Tracking Properties").Item("Part Number").Value
    finally: d.Close()
    if pn.lower()!=f[:-4].lower(): bad.append((f[:-4],pn))
print(len(fs),"plików; PN różny od nazwy:",len(bad))
for b in bad: print(" ",b)
