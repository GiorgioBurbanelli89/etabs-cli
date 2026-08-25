#!/usr/bin/env python3
r"""build_and_validate — CASO 1 limpio: construyo un voladizo en ETABS con propiedades
EXACTAS que yo fijo (sin ambigüedad), lo resuelvo con CsiGo2/SAPFire real (headless),
y comparo la flecha de punta contra NUESTRO motor (Timoshenko y Euler).

Inputs controlados: acero E=2.1e8 kN/m², ν=0.3 ; sección 0.30×0.30 m ; L=4 m ;
carga puntual vertical P=10 kN en la punta. Empotrado-libre.
"""
import os, sys, json
import numpy as np
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from etabs_cli_standalone import oapi_start

E, NU = 2.1e8, 0.3          # kN/m², -
B, H = 0.30, 0.30           # ancho(t2), peralte(t3)  [m]
L, P = 4.0, 10.0            # m, kN
G = E / (2.0 * (1.0 + NU))
A = B * H
I = B * H**3 / 12.0         # flexión vertical (cuadrada: indistinto)
As = (5.0 / 6.0) * A        # rectángulo k=5/6


def sigfigs(a, b):
    if a == b: return 16.0
    if b == 0: return 0.0
    rel = abs(a - b) / abs(b)
    return max(0.0, -np.log10(rel)) if rel > 0 else 16.0


def oraculo():
    et, sm = oapi_start("19", None, hide=True)
    o = {}
    try:
        sm.InitializeNewModel(6)                 # kN, m, C
        sm.File.NewBlank()
        sm.PropMaterial.SetMaterial("MAT", 1)    # 1 = Steel
        sm.PropMaterial.SetMPIsotropic("MAT", E, NU, 1.2e-5)
        sm.PropFrame.SetRectangle("SEC", "MAT", H, B)   # (name, mat, depth t3, width t2)
        # frame por coordenadas (crea los 2 nodos)
        r = sm.FrameObj.AddByCoord(0, 0, 0, L, 0, 0, "", "SEC", "F1")
        # nodos
        names = list(sm.PointObj.GetNameList()[1])
        n1 = min(names, key=lambda nm: sm.PointObj.GetCoordCartesian(nm, 0.0, 0.0, 0.0)[0])
        n2 = max(names, key=lambda nm: sm.PointObj.GetCoordCartesian(nm, 0.0, 0.0, 0.0)[0])
        sm.PointObj.SetRestraint(n1, [True, True, True, True, True, True])
        sm.LoadPatterns.Add("PUSH", 8, 0.0, True)   # 8 = Other, sin peso propio
        sm.PointObj.SetLoadForce(n2, "PUSH", [0.0, 0.0, -P, 0.0, 0.0, 0.0])
        # ETABS escribe el fileset de análisis junto al .EDB -> hay que GUARDAR primero
        import tempfile
        savep = os.path.join(tempfile.gettempdir(), "hk_voladizo.EDB")
        sm.File.Save(savep); o["saved"] = savep
        try: sm.Analyze.SetRunCaseFlag("", True, True)      # correr todos
        except Exception as e: o["runflag_err"] = str(e)[:50]
        try: sm.Analyze.SetRunCaseFlag("Modal", False, False)  # Modal molesta, apagar
        except Exception: pass
        sm.Analyze.RunAnalysis()
        sm.Results.Setup.DeselectAllCasesAndCombosForOutput()
        sm.Results.Setup.SetCaseSelectedForOutput("PUSH")
        # --- DEBUG: confirmar que sección/material se aplicaron y ver el tuple completo ---
        try:
            sp = sm.PropFrame.GetSectProps("SEC")
            o["dbg_sectprops"] = [round(x, 8) if isinstance(x, float) else x for x in sp][:7]
        except Exception as e: o["dbg_sectprops_err"] = str(e)[:50]
        try:
            iso = sm.PropMaterial.GetMPIsotropic("MAT")
            o["dbg_mat"] = [round(x, 4) if isinstance(x, float) else x for x in iso]
        except Exception as e: o["dbg_mat_err"] = str(e)[:50]
        try:
            o["dbg_frame_sec"] = list(sm.FrameObj.GetSection("F1"))
        except Exception as e: o["dbg_frame_sec_err"] = str(e)[:50]
        d = sm.Results.JointDispl(n2, 0)
        def arr(x): return list(x) if hasattr(x, "__len__") else x
        o["dbg_jd_n2"] = {"len": len(d), "nres": d[0], "Obj": arr(d[1]), "Case": arr(d[3]),
                          "U1": arr(d[6]), "U2": arr(d[7]), "U3": arr(d[8]),
                          "R1": arr(d[9]), "R2": arr(d[10]), "R3": arr(d[11])}
        o["nres"] = d[0]; o["U3"] = d[8][0] if d[0] else None; o["R2"] = d[10][0] if d[0] else None
        try:
            rb = sm.Results.BaseReact()
            o["base_len"] = len(rb)
            o["base_Fz"] = rb[6][0]; o["base_My"] = rb[8][0]
        except Exception as e:
            o["base_err"] = str(e)[:60]
        o["n1"], o["n2"] = n1, n2
    finally:
        try: et.ApplicationExit(False)
        except Exception: pass
    return o


def nuestro(modelo):
    Phi = 0.0 if modelo == "Euler" else 12.0 * E * I / (G * As * L * L)
    c = E * I / (L**3 * (1.0 + Phi))
    # DOFs libres en punta (w2, th2); empotrado en la base
    Kff = np.array([[12*c, -6*L*c],
                    [-6*L*c, (4+Phi)*L*L*c]])
    f = np.array([-P, 0.0])
    w2, th2 = np.linalg.solve(Kff, f)
    return dict(modelo=modelo, U3=w2, R2=th2)


def line(lbl, ours, ref):
    if ref is None: return f"  [??] {lbl}: sin oráculo"
    s = sigfigs(ours, ref); rel = abs(ours-ref)/abs(ref) if ref else float('nan')
    tag = "OK" if s >= 9 else ("~ " if s >= 4 else "XX")
    return f"  [{tag}] {lbl:7s} nuestro={ours: .9e}  CsiGo2={ref: .9e}  err_rel={rel:.2e}  cifras≈{s:.1f}"


def main():
    print("=== ORÁCULO: ETABS headless (CsiGo2/SAPFire real), modelo construido por OAPI ===")
    o = oraculo()
    print(json.dumps(o, indent=2, default=float))
    print(f"\n(teoría: δ_Euler = PL³/3EI = {P*L**3/(3*E*I):.9e}  +shear PL/GAs = {P*L/(G*As):.3e})")
    for modelo in ("Timoshenko", "Euler"):
        n = nuestro(modelo)
        print(f"\n=== NUESTRO MOTOR ({modelo}) vs CsiGo2 ===")
        print(line("U3", n["U3"], o["U3"]))
        print(line("R2", n["R2"], o["R2"]))


if __name__ == "__main__":
    main()
