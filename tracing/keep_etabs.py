import comtypes.client as cc, time, sys
cc.CreateObject("ETABSv1.Helper")
from comtypes.gen import ETABSv1 as Ev1
h=cc.CreateObject("ETABSv1.Helper").QueryInterface(Ev1.cHelper)
et=h.CreateObject(r"C:\Program Files\Computers and Structures\ETABS 19\ETABS.exe").QueryInterface(Ev1.cOAPI)
et.ApplicationStart()
try: et.Hide()
except: pass
open(r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\etabs\tracer\etabs_ready.flag","w").write("ready")
print("ETABS VIVO (oculto). Esperando 120s...", flush=True)
time.sleep(120)
