#!/usr/bin/env python3
r"""torsion_debug — POR QUE Tu no cambia al reducir J. Imprime el estado de lock,
nombres de objeto reales, readback de modifiers y rc de RunAnalysis en cada paso.
Parte del Tu BRUTO (J=1.0) y baja J; cualquier paso donde el lock o el re-run no
ocurra explica el bug.
"""
import os, sys, shutil, glob, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from etabs_cli_standalone import oapi_start, read_version

SRC_DIR = r"C:\Users\j-b-j\Downloads\Etabs Torsion"
WORK = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "out_torsion"))
EDB = os.path.join(WORK, "dbg.EDB")
COMBO = "UDCon2"


def Tu_of(sm, name):
    sm.Results.Setup.DeselectAllCasesAndCombosForOutput()
    sm.Results.Setup.SetComboSelectedForOutput(COMBO)
    r = sm.Results.FrameForce("All", 2)
    n, obj, T = r[0], r[1], r[10]
    mx = {}
    for i in range(n):
        mx[obj[i]] = max(mx.get(obj[i], 0.0), abs(T[i]))
    return mx.get(name, 0.0), mx


def main():
    os.system("taskkill /F /IM ETABS.exe >nul 2>&1")
    os.makedirs(WORK, exist_ok=True)
    src = max(glob.glob(os.path.join(SRC_DIR, "*T.EDB")), key=os.path.getmtime)
    ver = read_version(src)["family"]
    shutil.copy2(src, EDB)
    print(f"modelo {os.path.basename(src)} ETABS {ver}")

    et = sm = None
    for _ in range(5):
        try: et, sm = oapi_start(ver, EDB, hide=True); break
        except Exception as e:
            print("retry:", str(e)[:40]); os.system("taskkill /F /IM ETABS.exe >nul 2>&1"); time.sleep(5)
    try:
        sm.SetPresentUnits(12)
        try: sm.Analyze.SetRunCaseFlag("Modal", False, False)
        except Exception: pass

        # nombres de objeto frame reales
        objs = list(sm.FrameObj.GetNameList()[1])
        print(f"frame OBJETOS ({len(objs)}): {objs[:12]}{'...' if len(objs)>12 else ''}")

        print(f"locked inicial = {sm.GetModelIsLocked()}")
        rc_unlock = sm.SetModelIsLocked(False)
        print(f"SetModelIsLocked(False) rc={rc_unlock}  locked={sm.GetModelIsLocked()}")
        rc_run = sm.Analyze.RunAnalysis()
        print(f"RunAnalysis rc={rc_run}  locked={sm.GetModelIsLocked()}")

        Tu0, mx = Tu_of(sm, None) if False else (None, None)
        mx = Tu_of(sm, "___")[1]
        gob = max(mx, key=mx.get)
        en_objs = gob in objs
        print(f"\ngobernante (de FrameForce) = '{gob}'  ¿es OBJETO? {en_objs}")
        print(f"top Tu: " + "  ".join(f"{k}={v:.3f}" for k,v in sorted(mx.items(),key=lambda x:-x[1])[:6]))

        # si el gobernante NO es objeto, mapear: aplicar a TODOS los objetos
        targets = [gob] if en_objs else objs
        print(f"\n--- bajando J en {('objeto '+gob) if en_objs else 'TODOS los objetos'} ---")
        print(f"{'Jmod':>6} {'unlock_rc':>9} {'locked_post':>11} {'Jread':>7} {'run_rc':>7} {'Tu':>10}")
        for jmod in (1.0, 0.5, 0.05, 0.005):
            ru = sm.SetModelIsLocked(False)
            lpost = sm.GetModelIsLocked()
            jread = None
            for t in targets:
                val = [1.0]*8; val[3] = jmod
                sm.FrameObj.SetModifiers(t, val)
            gm = sm.FrameObj.GetModifiers(targets[0])
            jread = gm[0][3] if gm and gm[0] else None
            rr = sm.Analyze.RunAnalysis()
            Tu, _ = Tu_of(sm, gob)
            jr = f"{jread:.3f}" if jread is not None else "?"
            print(f"{jmod:>6.3f} {str(ru):>9} {str(lpost):>11} {jr:>7} {str(rr):>7} {Tu:>10.4f}")
    finally:
        try: et.ApplicationExit(False)
        except Exception: pass


if __name__ == "__main__":
    main()
