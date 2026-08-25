r"""Usa el OAPI para que ETABS FORME el modelo de analisis (.Y_) SIN resolver
(Analyze.CreateAnalysisModel), captura el fileset formado, y lo deja para darselo
al Driver standalone. Asi aislamos: el Driver computa un .Y_ bien-formado por ETABS?"""
import os, sys, shutil, glob, time, functools
sys.stdout.reconfigure(encoding="utf-8")
print = functools.partial(print, flush=True)
EXE = r"C:\Program Files\Computers and Structures\ETABS 19\ETABS.exe"
EDB = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\cant_model\cant.EDB"
DST = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\cant_formed"

import comtypes.client as cc
cc.CreateObject("ETABSv1.Helper")
from comtypes.gen import ETABSv1 as Ev1
h = cc.CreateObject("ETABSv1.Helper").QueryInterface(Ev1.cHelper)
et = h.CreateObject(EXE).QueryInterface(Ev1.cOAPI); et.ApplicationStart()
try: et.Hide()
except Exception: pass
sm = et.SapModel
sm.InitializeNewModel(6)
sm.File.OpenFile(EDB)
try: sm.SetModelIsLocked(False)
except Exception: pass
# borrar resultados previos y FORMAR el modelo de analisis (sin resolver)
try: print("DeleteResults:", sm.Analyze.DeleteResults("", True))
except Exception as e: print("DeleteResults err", e)
print("CreateAnalysisModel (forma .Y_ sin resolver):", sm.Analyze.CreateAnalysisModel())
# localizar el .Y_ formado (junto al EDB o en Temp raiz; SIN glob recursivo)
time.sleep(1)
cands = sorted(glob.glob(os.path.join(os.path.dirname(EDB), "*.Y_")) +
               glob.glob(os.path.join(os.environ["LOCALAPPDATA"], "Temp", "cant*.Y_")),
               key=lambda p: os.path.getmtime(p), reverse=True)
print("\n.Y_ recientes:")
for c in cands[:6]:
    print("  ", c, time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(c))))
if cands:
    src = cands[0]; base = os.path.splitext(src)[0]
    shutil.rmtree(DST, ignore_errors=True); os.makedirs(DST)
    for f in glob.glob(base + ".*"):
        shutil.copy(f, DST)
    print("-> fileset formado copiado a", DST, "base:", os.path.basename(base))

try: et.ApplicationExit(False)
except Exception: pass
