#!/usr/bin/env python3
r"""validar_vs_sapfire — compara NUESTRO motor (ensamblaje + solve) contra el SAPFire/CsiGo2
REAL de ETABS, número por número, con error relativo y cifras significativas.

CASO 1 (voladizo frame): corre voladizo_cli.EDB en ETABS headless (CsiGo2 = ORÁCULO),
lee sección/material EXACTOS del modelo, arma nuestro elemento frame de Timoshenko en
numpy, resuelve, y compara la flecha de punta + reacciones.

Criterio (acordado): "igual" = coincidencia en cifras significativas (err_rel ≤ 1e-9).
Si Timoshenko no cierra pero Euler-Bernoulli sí (o viceversa), el harness LO DICE
(revela empíricamente qué formulación usa SAPFire para el frame).

Uso:  python validar_vs_sapfire.py            # voladizo, caso Q (carga puntual en punta)
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from etabs_cli_standalone import oapi_start

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.abspath(os.path.join(HERE, "..", ".."))
MODEL = os.path.join(BRIDGE, "coldtest", "voladizo_cli.EDB")
CASE = "Q"   # carga puntual en la punta (reacción Fz=10, My=-40)


def sigfigs_agree(a, b):
    """nº de cifras significativas que coinciden entre a y b."""
    if a == b: return 16
    if b == 0: return 0.0
    rel = abs(a - b) / abs(b)
    return max(0.0, -np.log10(rel)) if rel > 0 else 16


# ----------------------------------------------------------------- ORÁCULO (CsiGo2)
def oraculo_etabs():
    et, sm = oapi_start("19", MODEL, hide=True)
    o = {}
    try:
        try: sm.SetModelIsLocked(False)
        except Exception: pass
        sm.Analyze.RunAnalysis()
        sm.Results.Setup.DeselectAllCasesAndCombosForOutput()
        sm.Results.Setup.SetCaseSelectedForOutput(CASE)

        # nodo de punta = máximo X
        pn = sm.PointObj.GetNameList(); names = list(pn[1])
        tip, xmax = None, -1e30
        for nm in names:
            c = sm.PointObj.GetCoordCartesian(nm, 0.0, 0.0, 0.0)
            if c[0] > xmax: xmax, tip = c[0], nm
        o["tip_node"], o["L"] = tip, xmax

        # desplazamiento de punta (U3 vertical, R2 giro)
        d = sm.Results.JointDispl(tip, 0)
        # tupla: n,Obj,Elm,Case,StepType,StepNum,U1,U2,U3,R1,R2,R3,ret
        o["tip_U3"] = d[8][0]
        o["tip_R2"] = d[10][0]

        # reacción en la base (estática)
        r = sm.Results.BaseReact()
        o["base_Fz"] = r[6][0]; o["base_My"] = r[8][0]

        # sección + material EXACTOS — robusto a gotchas de comtypes (SAFEARRAY strings)
        def namelist(obj):
            for args in ((), (0, []), (0, None)):
                try:
                    r = obj.GetNameList(*args)
                    return list(r[1])
                except Exception:
                    continue
            raise RuntimeError("GetNameList falló en todas las variantes")
        # ir directo a las propiedades de sección (evita FrameObj)
        props = namelist(sm.PropFrame)
        prop = props[0]
        rect = sm.PropFrame.GetRectangle(prop)   # (File,Mat,T3,T2,Color,Notes,GUID,ret)
        mat = rect[1]; t3 = rect[2]; t2 = rect[3]
        iso = sm.PropMaterial.GetMPIsotropic(mat)  # (E,U,A,G,ret) o similar
        E = iso[0]; nu = iso[1]
        o.update(dict(prop=prop, mat=mat, t3=t3, t2=t2, E=E, nu=nu))
    finally:
        try: et.ApplicationExit(False)
        except Exception: pass
    return o


# ----------------------------------------------------------------- NUESTRO MOTOR
def k_frame2d(EA, EI, L, GAs=None):
    """rigidez 6x6 (u1,w1,th1,u2,w2,th2). GAs=None -> Euler-Bernoulli; si no, Timoshenko."""
    Phi = 0.0 if GAs in (None, 0) else 12.0 * EI / (GAs * L * L)
    K = np.zeros((6, 6))
    # axial
    ka = EA / L
    for (i, j, s) in [(0, 0, 1), (0, 3, -1), (3, 0, -1), (3, 3, 1)]:
        K[i, j] += ka * s
    # flexión (Timoshenko / Euler segun Phi)
    c = EI / (L**3 * (1.0 + Phi))
    Kb = c * np.array([
        [12,      6*L,            -12,     6*L],
        [6*L,  (4+Phi)*L*L,       -6*L, (2-Phi)*L*L],
        [-12,    -6*L,             12,    -6*L],
        [6*L,  (2-Phi)*L*L,       -6*L, (4+Phi)*L*L],
    ])
    idx = [1, 2, 4, 5]
    for a in range(4):
        for b in range(4):
            K[idx[a], idx[b]] += Kb[a, b]
    return K


def nuestro_motor(o, P, modelo="Timoshenko"):
    L = o["L"]; E = o["E"]; nu = o["nu"]
    t2, t3 = o["t2"], o["t3"]            # ancho(local2), peralte(local3)
    A = t2 * t3
    # carga vertical global Z -> flexión en plano X-Z -> inercia del peralte vertical
    # (sección cuadrada: indistinto). I de flexión vertical:
    I = t2 * t3**3 / 12.0
    G = E / (2.0 * (1.0 + nu))
    As = (5.0 / 6.0) * A                 # rectángulo: factor de corte k=5/6
    GAs = G * As if modelo == "Timoshenko" else None
    K = k_frame2d(E*A, E*I, L, GAs)
    # empotrado en nodo1 (DOF 0,1,2), libres nodo2 (3,4,5); carga Fz=-P en w2 (DOF 4)
    free = [3, 4, 5]
    f = np.array([0.0, -P, 0.0])
    Kff = K[np.ix_(free, free)]
    d = np.linalg.solve(Kff, f)
    uX2, w2, th2 = d
    # reacciones en la base: R = K[fixed,free] @ d
    fixed = [0, 1, 2]
    R = K[np.ix_(fixed, free)] @ d
    return dict(modelo=modelo, A=A, I=I, G=G, As=As,
                tip_U3=w2, tip_R2=th2,
                base_Fz=R[1], base_My=R[2])  # R[2] ~ momento en theta1


def fmt_cmp(label, ours, ref):
    s = sigfigs_agree(ours, ref)
    rel = abs(ours - ref) / abs(ref) if ref != 0 else float('nan')
    ok = "OK" if s >= 9 else ("~" if s >= 4 else "XX")
    return f"  [{ok}] {label:10s} nuestro={ours: .8e}  sapfire={ref: .8e}  err_rel={rel:.2e}  cifras≈{s:.1f}"


def main():
    print("=== ORÁCULO: ETABS headless (CsiGo2/SAPFire real) ===")
    o = oraculo_etabs()
    P = abs(o["base_Fz"])   # carga de punta = cortante en la base (caso Q)
    print(json.dumps({k: o[k] for k in ("tip_node","L","E","nu","t2","t3",
                                        "tip_U3","tip_R2","base_Fz","base_My")},
                     indent=2, default=float))
    print(f"\ncarga de punta P (= |base_Fz|) = {P}")

    for modelo in ("Timoshenko", "Euler"):
        n = nuestro_motor(o, P, modelo)
        print(f"\n=== NUESTRO MOTOR ({modelo}) vs SAPFire ===")
        print(f"   A={n['A']:.6g}  I={n['I']:.6g}  G={n['G']:.6g}  As={n['As']:.6g}")
        print(fmt_cmp("tip_U3", n["tip_U3"], o["tip_U3"]))
        print(fmt_cmp("tip_R2", n["tip_R2"], o["tip_R2"]))
        print(fmt_cmp("base_Fz", n["base_Fz"], o["base_Fz"]))
        print(fmt_cmp("base_My", n["base_My"], o["base_My"]))


if __name__ == "__main__":
    main()
