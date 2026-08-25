#!/usr/bin/env python3
r"""build_coupled_capture — genera un voladizo con nudo libre (DOF acoplados) y captura su `.K_*`.

OBJETIVO: cerrar el caso CON ACOPLE del decode `.K_0` (factor LDLᵀ del solver columna activa).
Los modelos existentes son todos diagonales (3 rotaciones); este deja el nudo 2 TOTALMENTE LIBRE
⇒ la rigidez reducida 6×6 tiene 2 bloques 2×2 acoplados (uy-rz por I33, uz-ry por I22) ⇒ L≠I.

Estrategia de validación (sin PARDISO): `.K_0` es la factorización LDLᵀ. Calculo la K analítica
Timoshenko reducida del MISMO modelo (leo props del `.$et` generado, no asumo unidades), saco su
LDLᵀ esperada, y la comparo con los f64 que aparecen en `.K_0`. Eso revela el intercalado de L.

Uso:  python build_coupled_capture.py
"""
import os, sys, shutil, struct
import numpy as np
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from etabs_cli_standalone import oapi_start

BRIDGE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(BRIDGE, "coupled_capture")
EDB = os.path.join(OUT, "coupled.EDB")
L, P = 4000.0, 10000.0          # mm, N   (se confirma leyendo el .$et)
Dh, Bw = 500.0, 300.0           # sección rect D×B (mm)
E, NU = 210000.0, 0.3           # N/mm²


def build_and_run():
    os.makedirs(OUT, exist_ok=True)
    et, sm = oapi_start("19", None, hide=True)
    try:
        sm.InitializeNewModel(9)              # 9 = N_mm_C  (forzar N-mm)
        sm.File.NewBlank()
        sm.PropMaterial.SetMaterial("ST", 1)  # Steel
        sm.PropMaterial.SetMPIsotropic("ST", E, NU, 1.2e-5)
        sm.PropFrame.SetRectangle("V", "ST", Dh, Bw)   # (name, mat, depth=D, width=B)
        # COLUMNA VERTICAL: base fija, tope libre (sway) -> UX acoplado con RY (activos en ETABS)
        sm.PointObj.AddCartesian(0.0, 0.0, 0.0, "n1", "n1")
        sm.PointObj.AddCartesian(0.0, 0.0, L, "n2", "n2")
        sm.PointObj.SetRestraint("n1", [True, True, True, True, True, True])
        # n2: SIN restraint -> DOF de sway activos -> acople
        sm.FrameObj.AddByPoint("n1", "n2", "C1", "V", "C1")
        sm.LoadPatterns.Add("Q", 8, 0.0, True)         # 8 = Other
        sm.PointObj.SetLoadForce("n2", "Q", [P, 0.0, 0.0, 0.0, 0.0, 0.0], True, "Global", 0)  # Fx lateral
        sm.File.Save(EDB)
        try: sm.Analyze.SetRunCaseFlag("", True, True)
        except Exception: pass
        try: sm.Analyze.SetRunCaseFlag("Modal", False, False)
        except Exception: pass
        sm.Analyze.RunAnalysis()
    finally:
        try: et.ApplicationExit(False)
        except Exception: pass
    return EDB


def show_out(base):
    p = base + ".OUT"
    if os.path.exists(p):
        print("\n=== .OUT (DOF activos) ===")
        txt = open(p, errors="ignore").read()
        i = txt.find("JOINTS")
        print(txt[i:i+200] if i >= 0 else txt[-300:])


def dump_K0(base):
    b = open(base + ".K_0", "rb").read()
    print(f"\n=== .K_0 ({len(b)} B) HEX ===")
    for o in range(0, len(b), 16):
        ch = b[o:o+16]
        print(f"{o:04x}  " + " ".join(f"{x:02x}" for x in ch))
    print("\n--- f64 (todos, |v|>1e-9) ---")
    for o in range(0, len(b)-7):
        v = struct.unpack_from("<d", b, o)[0]
        if 1e-9 < abs(v) < 1e16:
            print(f"  @0x{o:02x} = {v:.9g}")


def analytic_LDL(et_path):
    import re
    if not os.path.exists(et_path):
        print("[!] no .$et"); return
    txt = open(et_path, errors="ignore").read()
    m = re.search(r'MATERIAL\s+"ST".*?E\s+(\S+)\s+U\s+(\S+)', txt, re.S)
    s = re.search(r'FRAMESECTION\s+"V".*?D\s+(\S+)\s+B\s+(\S+)', txt, re.S)
    pts = {p: float(x) for p, x, y in re.findall(r'POINT\s+"(\w+)"\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)', txt)}
    Ee, nu = float(m.group(1)), float(m.group(2))
    D, Bb = float(s.group(1)), float(s.group(2))
    Ll = abs(pts.get("n2", pts.get("2", L)) - pts.get("n1", pts.get("1", 0.0)))
    G = Ee/(2*(1+nu)); A = Bb*D; I33 = Bb*D**3/12; I22 = D*Bb**3/12; As = 5/6*A
    print(f"\n=== props del .$et: E={Ee} nu={nu} D={D} B={Bb} L={Ll} ===")
    def blk(I):
        Phi = 12*Ee*I/(G*As*Ll*Ll)
        c = Ee*I/(Ll**3*(1+Phi))
        return 12*c, 6*Ll*c, (4+Phi)*Ll*Ll*c   # k_tt, k_tr, k_rr (Timoshenko)
    # reducida 6x6 n2: [ux,uy,uz,rx,ry,rz]
    K = np.zeros((6, 6))
    K[0, 0] = Ee*A/Ll
    a, bb = max(D, Bb), min(D, Bb); J = a*bb**3*(1/3-0.21*(bb/a)*(1-bb**4/(12*a**4)))
    K[3, 3] = G*J/Ll
    ktt, ktr, krr = blk(I33)           # uy(1)-rz(5): signo -ktr
    K[1, 1] = ktt; K[1, 5] = -ktr; K[5, 1] = -ktr; K[5, 5] = krr
    ktt2, ktr2, krr2 = blk(I22)        # uz(2)-ry(4): signo +ktr
    K[2, 2] = ktt2; K[2, 4] = ktr2; K[4, 2] = ktr2; K[4, 4] = krr2
    print("K reducida 6x6 (n2) [ux,uy,uz,rx,ry,rz]:")
    for r in K: print("   " + "  ".join(f"{v: .4e}" for v in r))
    # LDL^T
    Lm = np.eye(6); Dg = np.zeros(6)
    for j in range(6):
        Dg[j] = K[j, j] - sum(Lm[j, k]**2*Dg[k] for k in range(j))
        for i in range(j+1, 6):
            Lm[i, j] = (K[i, j] - sum(Lm[i, k]*Lm[j, k]*Dg[k] for k in range(j)))/Dg[j]
    print("\nLDL^T esperada — D (diag):", "  ".join(f"{v:.6e}" for v in Dg))
    print("LDL^T esperada — L off-diag (i>j):")
    for j in range(6):
        for i in range(j+1, 6):
            if abs(Lm[i, j]) > 1e-9:
                print(f"   L[{i},{j}] = {Lm[i,j]:.6f}")


def main():
    print("=== construyendo + corriendo (ETABS 19 oculto) ===")
    base = os.path.splitext(build_and_run())[0]
    print("OK ->", base)
    show_out(base)
    if os.path.exists(base + ".K_0"):
        dump_K0(base)
    else:
        print("[!] no se generó .K_0")
    analytic_LDL(base + ".$et")


if __name__ == "__main__":
    main()
