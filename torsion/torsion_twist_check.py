#!/usr/bin/env python3
r"""torsion_twist_check — PRUEBA DEFINITIVA equilibrio vs compatibilidad.

En torsion de EQUILIBRIO:  T = G·J·(theta'/L)  -> T fijo, pero al agrietar J el GIRO
torsional theta crece ~1/J. En COMPATIBILIDAD: al bajar J, T baja y el giro casi no cambia.

Corre Mesa torsionT (v22) a 3 niveles de Jmod (1.0, 0.1, 0.01); en cada uno lee:
  - Tu de la viga gobernante (FrameForce r[10])
  - el giro de sus 2 nudos extremos (JointDispl R1,R2,R3)
Si Tu=cte y el giro crece ~10x por cada /10 de J  => EQUILIBRIO confirmado y ETABS
re-analiza de verdad (no hay caching).

  python torsion_twist_check.py
"""
import os, sys, shutil, glob, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from etabs_cli_standalone import oapi_start, read_version

SRC_DIR = r"C:\Users\j-b-j\Downloads\Etabs Torsion"
WORK = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "out_torsion"))
EDB = os.path.join(WORK, "twist.EDB")
COMBO = "UDCon2"
UNITS = 12   # Tonf, m, C


def prep(pattern="*T.EDB"):
    os.system("taskkill /F /IM ETABS.exe >nul 2>&1")
    os.makedirs(WORK, exist_ok=True)
    src = max(glob.glob(os.path.join(SRC_DIR, pattern)), key=os.path.getmtime)
    ver = read_version(src)["family"]
    shutil.copy2(src, EDB)
    print(f"[prep] {os.path.basename(src)} (ETABS {ver})", file=sys.stderr)
    return ver


def run(sm):
    try: sm.SetModelIsLocked(False)
    except Exception: pass
    sm.Analyze.RunAnalysis()
    sm.Results.Setup.DeselectAllCasesAndCombosForOutput()
    sm.Results.Setup.SetComboSelectedForOutput(COMBO)


def read_T(sm):
    r = sm.Results.FrameForce("All", 2)
    n, obj, T = r[0], r[1], r[10]
    mx = {}
    for i in range(n):
        mx[obj[i]] = max(mx.get(obj[i], 0.0), abs(T[i]))
    return mx


def joint_rot(sm, pt):
    """devuelve (R1,R2,R3) del nudo pt para el combo seleccionado."""
    r = sm.Results.JointDispl(pt, 0)
    # JointDispl: [n,obj,elm,lc,stepType,stepNum,U1,U2,U3,R1,R2,R3]
    return r[9][0], r[10][0], r[11][0]


def main():
    ver = prep()
    et = sm = None
    for _ in range(5):
        try: et, sm = oapi_start(ver, EDB, hide=True); break
        except Exception as e:
            print("retry start:", str(e)[:50], file=sys.stderr)
            os.system("taskkill /F /IM ETABS.exe >nul 2>&1"); time.sleep(5)
    if sm is None: sys.exit("no arranco ETABS")
    try:
        sm.SetPresentUnits(UNITS)
        try: sm.Analyze.SetRunCaseFlag("Modal", False, False)
        except Exception: pass

        run(sm)
        mx = read_T(sm)
        gob = max(mx, key=mx.get)
        p = sm.FrameObj.GetPoints(gob)        # (pt_i, pt_j, ret)
        pti, ptj = p[0], p[1]
        print(f"viga gobernante={gob}  nudos=({pti},{ptj})  Tu0={mx[gob]:.4f} ton·m\n")
        print(f"{'Jmod':>8} {'Tu(ton·m)':>11} {'|R|max_i(rad)':>14} {'|R|max_j(rad)':>14}")

        for jmod in (1.0, 0.1, 0.01):
            sm.SetModelIsLocked(False)
            val = [1.0]*8; val[3] = jmod
            sm.FrameObj.SetModifiers(gob, val)
            run(sm)
            Tu = read_T(sm).get(gob, 0.0)
            ri = max(abs(v) for v in joint_rot(sm, pti))
            rj = max(abs(v) for v in joint_rot(sm, ptj))
            print(f"{jmod:>8.2f} {Tu:>11.4f} {ri:>14.6e} {rj:>14.6e}")

        print("\nLectura: si Tu≈cte y |R| crece ~10x por cada /10 de J => TORSION DE EQUILIBRIO")
        print("(y ETABS re-analiza de verdad). Si Tu baja y |R| casi no cambia => COMPATIBILIDAD.")
    finally:
        try: et.ApplicationExit(False)
        except Exception: pass


if __name__ == "__main__":
    main()
