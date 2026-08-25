#!/usr/bin/env python3
r"""build_3x3_walls — edificio 1 piso, 3x3 vanos (9 paños) con muros de corte en ALGUNOS lados.
Prueba el formato `.K_0` con n GRANDE (¿sigue denso col-major o aparece compresión por bloques?).

Geometría (N, mm): grid 4x4 nudos, vano 5000, altura 3000. Columnas en los 16 nudos (base empotrada),
vigas en todo el piso. Muros de corte (shell, 250mm) en 2 vanos perimetrales; resto libre (pórtico).
Fase 1: SIN diafragma (cada nudo 6 DOF). Fase 2 (--diaph): + losa 9 paños con diafragma rígido.

Uso:  python build_3x3_walls.py            # sin diafragma
      python build_3x3_walls.py --diaph    # con losa + diafragma rígido
"""
import os, sys, struct
import numpy as np
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from etabs_cli_standalone import oapi_start

BRIDGE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DIAPH = "--diaph" in sys.argv
OUT = os.path.join(BRIDGE, "out_3x3" + ("_diaph" if DIAPH else ""))
EDB = os.path.join(OUT, "m3x3.EDB")

NB, S, H = 3, 5000.0, 3000.0          # 3 vanos, 5 m, alt 3 m
XS = [i*S for i in range(NB+1)]       # 0,5000,10000,15000
# muros de corte (lista de vanos perimetrales): (eje, i, j) -> panel entre nudos consecutivos
#   ("Y0", i)  = borde sur (y=0) vano i..i+1   ;  ("X0", j) = borde oeste (x=0) vano j..j+1
WALLS = [("Y0", 0), ("X0", 1)]        # muro sur vano 0, muro oeste vano 1; resto libre


def pname(i, j, lvl): return f"P_{i}_{j}_{lvl}"   # lvl: b(ase) / t(op)


def build():
    os.makedirs(OUT, exist_ok=True)
    et, sm = oapi_start("19", None, hide=True)
    cnt = {}
    try:
        sm.InitializeNewModel(9)                      # N_mm_C
        sm.File.NewBlank()
        # material concreto
        sm.PropMaterial.SetMaterial("CONC", 2)        # 2 = Concrete
        sm.PropMaterial.SetMPIsotropic("CONC", 24855.58, 0.2, 9.9e-6)
        sm.PropFrame.SetRectangle("COL", "CONC", 400.0, 400.0)
        sm.PropFrame.SetRectangle("VIG", "CONC", 500.0, 300.0)
        sm.PropArea.SetWall("MUR", 1, 1, "CONC", 250.0)     # WallType=Specified, ShellThin
        if DIAPH:
            sm.PropArea.SetSlab("LOSA", 1, 1, "CONC", 200.0)  # Slab, ShellThin
        # nudos base + piso
        for i in range(NB+1):
            for j in range(NB+1):
                sm.PointObj.AddCartesian(XS[i], XS[j], 0.0, pname(i, j, "b"), pname(i, j, "b"))
                sm.PointObj.AddCartesian(XS[i], XS[j], H,   pname(i, j, "t"), pname(i, j, "t"))
                sm.PointObj.SetRestraint(pname(i, j, "b"), [True]*6)   # base empotrada
        # columnas
        nc = 0
        for i in range(NB+1):
            for j in range(NB+1):
                sm.FrameObj.AddByPoint(pname(i, j, "b"), pname(i, j, "t"), f"C{i}{j}", "COL", f"C{i}{j}"); nc += 1
        # vigas piso (X e Y)
        nv = 0
        for i in range(NB+1):
            for j in range(NB+1):
                if i < NB:
                    sm.FrameObj.AddByPoint(pname(i, j, "t"), pname(i+1, j, "t"), f"BX{i}{j}", "VIG", f"BX{i}{j}"); nv += 1
                if j < NB:
                    sm.FrameObj.AddByPoint(pname(i, j, "t"), pname(i, j+1, "t"), f"BY{i}{j}", "VIG", f"BY{i}{j}"); nv += 1
        # muros de corte (panel vertical base->piso entre 2 columnas)
        nm = 0
        for axis, k in WALLS:
            if axis == "Y0":   # borde y=0, vano X k..k+1
                p = [pname(k, 0, "b"), pname(k+1, 0, "b"), pname(k+1, 0, "t"), pname(k, 0, "t")]
            else:              # X0: borde x=0, vano Y k..k+1
                p = [pname(0, k, "b"), pname(0, k+1, "b"), pname(0, k+1, "t"), pname(0, k, "t")]
            ret = sm.AreaObj.AddByPoint(4, p, "", "MUR", f"W_{axis}_{k}")
            nm += 1
        # losa (9 paños) + diafragma, solo fase 2
        if DIAPH:
            sm.Diaphragm.SetDiaphragm("D1", False) if hasattr(sm, "Diaphragm") else None
            for i in range(NB):
                for j in range(NB):
                    p = [pname(i, j, "t"), pname(i+1, j, "t"), pname(i+1, j+1, "t"), pname(i, j+1, "t")]
                    sm.AreaObj.AddByPoint(4, p, "", "LOSA", f"S_{i}_{j}")
            # asignar diafragma rígido a los nudos del piso
            try:
                sm.Diaphragm.SetDiaphragm("D1", True)
            except Exception: pass
            for i in range(NB+1):
                for j in range(NB+1):
                    try: sm.PointObj.SetDiaphragm(pname(i, j, "t"), 3, "D1")  # 3 = rigid
                    except Exception: pass
        cnt = {"cols": nc, "vigas": nv, "muros": nm,
               "puntos": sm.PointObj.Count(), "areas": sm.AreaObj.Count()}
        # carga lateral + gravedad
        sm.LoadPatterns.Add("Q", 8, 0.0, True)
        sm.PointObj.SetLoadForce(pname(NB, NB, "t"), "Q", [100000.0, 50000.0, -100000.0, 0, 0, 0], True, "Global", 0)
        sm.File.Save(EDB)
        try: sm.Analyze.SetRunCaseFlag("", True, True)
        except Exception: pass
        try: sm.Analyze.SetRunCaseFlag("Modal", False, False)
        except Exception: pass
        sm.Analyze.RunAnalysis()
    finally:
        try: et.ApplicationExit(False)
        except Exception: pass
    return os.path.splitext(EDB)[0], cnt


def analyze_K0(base):
    p = base + ".K_0"
    if not os.path.exists(p):
        print("[!] no se generó .K_0"); return
    b = open(p, "rb").read()
    n = struct.unpack_from("<i", b, 0x11)[0]
    Lstart = 0x35 + 4*n
    need = Lstart + 8*(n*n + 2*n)
    print(f"\n.K_0 = {len(b)} B   n(@0x11) = {n}   denso-colmajor requiere {need} B  "
          f"-> {'CABE (sigue denso)' if need <= len(b) else 'NO CABE -> formato comprimido/bloques!'}")
    if need <= len(b):
        fl = lambda s: struct.unpack_from("<d", b, Lstart+8*s)[0]
        L = np.array([[fl(c*n+r) for c in range(n)] for r in range(n)])
        D = np.array([fl(n*n+2*k) for k in range(n)])
        K = L @ np.diag(D) @ L.T
        sym = np.linalg.norm(K-K.T)/max(np.linalg.norm(K), 1e-30)
        eig = np.linalg.eigvalsh(K)
        print(f"  L diag todos 1.0: {bool(np.allclose(np.diag(L),1.0))}   "
              f"K simétrica: {sym:.1e}   PD: {bool(np.all(eig>1e-6*max(abs(eig))))}")
        print(f"  rango D: [{D.min():.4g}, {D.max():.4g}]   off-diag L no triviales: "
              f"{int(np.sum(np.abs(np.tril(L,-1))>1e-9))}")


def main():
    print(f"=== construyendo 3x3 {'CON' if DIAPH else 'SIN'} diafragma (ETABS 19 oculto) ===")
    base, cnt = build()
    print("OK ->", base, "\n   conteos:", cnt)
    out = base + ".OUT"
    if os.path.exists(out):
        txt = open(out, errors="ignore").read()
        na = txt.count("   A")
        print(f"   .OUT existe; aprox DOF activos (conteo 'A'): {na}")
    analyze_K0(base)


if __name__ == "__main__":
    main()
