#!/usr/bin/env python3
r"""CONTROL Sherlock: correr la Calculate() COMPILADA de CSI (cJoistInternalForcesCalc) in-process,
sin GUI, sobre el motor consistente de SAP2000 24. Si calcula -> el motor SI computa sin etabs/sap.exe
y tenemos un run KNOWN-GOOD para diffear contra cold_build.py.
"""
import os, sys, clr
sys.stdout.reconfigure(encoding="utf-8")
ENG = r"C:\Program Files\Computers and Structures\SAP2000 24"
os.add_dll_directory(ENG)
clr.AddReference(os.path.join(ENG, "CSI.SAPFire.dll"))
clr.AddReference(os.path.join(ENG, "CSI.QuickAnalysis.dll"))
import System
from System import Array, Double
from System.Collections.Generic import List
import CSI.QuickAnalysis as QA

JIF = QA.cJoistInternalForcesCalc
JDL = JIF.JoistDistributedVerticalLoad

# --- parametros minimos de una vigueta Warren ---
span, depth, nPanels, warren = 6.0, 0.6, 4, True
nu, G = 0.3, 8.077e7
tcA, tcI, tcAs = 0.01, 1e-4, 0.008
bcA, bcI, bcAs = 0.01, 1e-4, 0.008
strA = 0.005
nLP = 1

# TopChordLineLoads = List<JDL>[nPanels+1]; carga UDL en cada panel (cuerda superior)
ListJDL = List[JDL]
lineLoads = Array[ListJDL]([ListJDL() for _ in range(nPanels + 1)])
for p in range(1, nPanels + 1):
    sm = Array[Double]([0.0] * (nLP + 1)); em = Array[Double]([0.0] * (nLP + 1))
    sm[1] = -10.0; em[1] = -10.0                       # -10 kN/m en patron 1
    lineLoads[p].Add(JDL(0.0, 1.0, sm, em))            # de x=0 a x=1 (relativo), todo el tramo

# TopJointLoads = double[,] (cargas en nudos superiores); ceros
topJoint = Array.CreateInstance(Double, nPanels + 2, nLP + 2)

# out arrays (ref double[,]); se rellenan/realocan por Calculate
def d2(): return Array.CreateInstance(Double, 1, 1)
tcAx, tcBm, tcDisp = d2(), d2(), d2()
bcAx, bcBm = d2(), d2()
strAx = d2()

print(">>> llamando cJoistInternalForcesCalc.Calculate() (codigo COMPILADO de CSI), in-process, sin GUI...")
try:
    r = JIF.Calculate(span, depth, nPanels, warren, nu, G,
                      tcA, tcI, tcAs, bcA, bcI, bcAs, strA, nLP,
                      lineLoads, topJoint,
                      tcAx, tcBm, tcDisp, bcAx, bcBm, strAx, None)
    # pythonnet: ref params vuelven en la tupla tras el bool de retorno
    ok = r[0] if isinstance(r, tuple) else r
    print(">>> Calculate retorno =", ok)
    if isinstance(r, tuple):
        outs = r[1:]
        names = ["TopChordAxial", "TopChordMoment", "TopChordDispl", "BottomChordAxial", "BottomChordMoment", "StrutsAxial"]
        for nm, arr in zip(names, outs):
            try:
                rows = arr.GetLength(0); cols = arr.GetLength(1)
                vals = [round(arr[i, j], 5) for i in range(rows) for j in range(cols)]
                nz = any(abs(v) > 1e-9 for v in vals)
                print(f"   {nm}: [{rows}x{cols}] nz={nz}  {vals[:8]}")
            except Exception as e:
                print(f"   {nm}: err {str(e)[:60]}")
    if ok:
        print("\n   >>> ✅ EL MOTOR CSI CALCULA IN-PROCESS SIN GUI (control KNOWN-GOOD).")
    else:
        print("\n   >>> Calculate devolvio False (revisar inputs).")
except Exception as e:
    print(">>> EXCEPCION:", str(e)[:300])
