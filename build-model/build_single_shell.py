#!/usr/bin/env python3
r"""build_single_shell — UN solo elemento shell (membrana) para AISLAR el drilling (theta_z)
de ETABS y compararlo con Hughes-Brezzi (gamma = G*t).

Idea: shell tipo MEMBRANA (solo u,v,theta_z por nudo). Restringimos UX,UY,UZ,RX,RY en los 4
nudos y dejamos SOLO RZ libre -> la matriz de rigidez ACTIVA (4x4) es EXACTAMENTE la rigidez de
drilling que ETABS le pone al theta_z. Si ETABS factoriza sin instabilidad, PRUEBA que anade
drilling; el valor extraido (del PARDISO capturado) se contrasta con gamma*integral(N N^T).

Material igual al lab Drilling_Gauss_lab.m:  E=24850000 kN/m2, nu=0.2, t=0.1 m, elem 1.2x1.2 m.
En unidades ETABS N_mm_C:  E=24850 N/mm2,  t=100 mm,  lado=1200 mm.

Uso:  python build_single_shell.py                 # restringe u,v -> solo RZ (drilling puro)
      python build_single_shell.py --inplane       # deja u,v libres (membrana+drilling acoplado)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from etabs_cli_standalone import oapi_start

BRIDGE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
INPLANE = "--inplane" in sys.argv
OUT = os.path.join(BRIDGE, "out_shell" + ("_inplane" if INPLANE else ""))
EDB = os.path.join(OUT, "shell1.EDB")

E, NU, T, LADO = 24850.0, 0.2, 100.0, 1200.0      # N/mm2, -, mm, mm
PTS = [(0.0, 0.0), (LADO, 0.0), (LADO, LADO), (0.0, LADO)]


def build():
    os.makedirs(OUT, exist_ok=True)
    et, sm = oapi_start("19", None, hide=True)
    try:
        sm.InitializeNewModel(9)                       # 9 = N_mm_C
        sm.File.NewBlank()
        sm.PropMaterial.SetMaterial("CONC", 2)         # Concrete
        sm.PropMaterial.SetMPIsotropic("CONC", E, NU, 9.9e-6)
        # SetSlab(name, slabtype, shelltype, mat, thick) ; shelltype 3 = Membrane
        sm.PropArea.SetSlab("MEM", 0, 3, "CONC", T)
        names = []
        for k, (x, y) in enumerate(PTS):
            nm = f"N{k+1}"
            sm.PointObj.AddCartesian(x, y, 0.0, nm, nm)
            names.append(nm)
        sm.AreaObj.AddByPoint(4, names, "", "MEM", "S1")
        # Restraint: fijar todo menos RZ  -> [UX,UY,UZ,RX,RY,RZ]
        if INPLANE:
            rest = [False, False, True, True, True, False]   # u,v,RZ libres ; UZ,RX,RY fijos
        else:
            rest = [True, True, True, True, True, False]      # SOLO RZ libre (drilling puro)
        for nm in names:
            sm.PointObj.SetRestraint(nm, rest)
        # Carga: momento Mz en cada nudo libre para forzar un RHS no trivial
        sm.LoadPatterns.Add("DR", 8, 0.0, True)        # 8 = Other
        for nm in names:
            sm.PointObj.SetLoadForce(nm, "DR", [0, 0, 0, 0, 0, 1.0e6], True, "Global", 0)
        sm.File.Save(EDB)
        try: sm.Analyze.SetRunCaseFlag("Modal", False, False)
        except Exception: pass
        sm.Analyze.RunAnalysis()
        # imprimir desplazamientos RZ para ver que NO es singular
        try:
            sm.Results.Setup.DeselectAllCasesAndCombosForOutput()
            sm.Results.Setup.SetCaseSelectedForOutput("DR")
            for nm in names:
                r = sm.Results.JointDispl(nm, 0)
                print(f"  {nm}: RZ = {r[9][0]:.6e} rad")
        except Exception as e:
            print("  [!] sin desplazamientos:", e)
    finally:
        try: et.ApplicationExit(False)
        except Exception: pass
    return os.path.splitext(EDB)[0]


if __name__ == "__main__":
    print(f"=== shell 1 elem MEMBRANA, {'u,v libres + drilling' if INPLANE else 'SOLO RZ (drilling puro)'} ===")
    base = build()
    print("OK ->", base)
