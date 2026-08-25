#!/usr/bin/env python3
r"""torsion_v30 — iteracion de torsion por compatibilidad apuntando a la SECCION DE VIGA
(V30x50), que es la que agrieta el Excel. El modelo guardado ya trae V30x50 pre-agrietado,
asi que PARTIMOS reseteando su modificador torsional a J=1.0 (Tu bruto) y bajamos:
   factor = OTcr/Tu ;  Jmod_acumulado *= factor ;  PropFrame.SetModifiers(V30x50, J=Jmod)
hasta Tu = OTcr. Lista la seccion+torsion de cada frame para ver la viga real.
"""
import os, sys, shutil, glob, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from etabs_cli_standalone import oapi_start, read_version

SRC_DIR = r"C:\Users\j-b-j\Downloads\Etabs Torsion"
WORK = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "out_torsion"))
EDB = os.path.join(WORK, "v30.EDB")
COMBO = "UDCon2"
OTCR = 1.9394
BEAM_SEC = "V30x50"


def run(sm):
    sm.SetModelIsLocked(False)
    sm.Analyze.RunAnalysis()
    sm.Results.Setup.DeselectAllCasesAndCombosForOutput()
    sm.Results.Setup.SetComboSelectedForOutput(COMBO)


def frame_T(sm):
    r = sm.Results.FrameForce("All", 2)
    n, obj, T = r[0], r[1], r[10]
    mx = {}
    for i in range(n):
        mx[obj[i]] = max(mx.get(obj[i], 0.0), abs(T[i]))
    return mx


def main():
    os.system("taskkill /F /IM ETABS.exe >nul 2>&1")
    os.makedirs(WORK, exist_ok=True)
    src = max(glob.glob(os.path.join(SRC_DIR, "*T.EDB")), key=os.path.getmtime)
    ver = read_version(src)["family"]
    shutil.copy2(src, EDB)
    print(f"modelo {os.path.basename(src)} ETABS {ver}  beam_sec={BEAM_SEC}  OTcr={OTCR}")

    et = sm = None
    for _ in range(5):
        try: et, sm = oapi_start(ver, EDB, hide=True); break
        except Exception as e:
            print("retry start", str(e)[:40]); os.system("taskkill /F /IM ETABS.exe >nul 2>&1"); time.sleep(6)
    if sm is None: sys.exit("no arranco")
    try:
        sm.SetPresentUnits(12)
        try: sm.Analyze.SetRunCaseFlag("Modal", False, False)
        except Exception: pass

        # mapa frame->seccion
        objs = list(sm.FrameObj.GetNameList()[1])
        sec_of = {}
        for f in objs:
            try: sec_of[f] = sm.FrameObj.GetSection(f)[0]
            except Exception: sec_of[f] = "?"
        beams = [f for f in objs if sec_of[f] == BEAM_SEC]
        print(f"frames={objs}")
        print(f"secciones={ {f:sec_of[f] for f in objs} }")
        print(f"vigas {BEAM_SEC} = {beams}")

        # RESET: V30x50 a J=1.0 (Tu bruto)
        sm.SetModelIsLocked(False)
        val = [1.0]*8
        sm.PropFrame.SetModifiers(BEAM_SEC, val)
        run(sm)
        mx = frame_T(sm)
        print("\ntorsion por frame (J_viga=1.0 BRUTO):",
              "  ".join(f"{f}({sec_of[f]})={mx.get(f,0):.3f}" for f in objs))
        track = beams if beams else [max(mx, key=mx.get)]
        Tu = max(mx.get(f, 0.0) for f in track)
        print(f"\nTu bruto (viga) = {Tu:.4f} ton·m   (seguimiento: {track})")
        print(f"\n{'Paso':>4} {'Jmod V30':>9} {'Jread':>8} {'Tu(ton·m)':>11} {'OTcr/Tu':>9}")
        jmod = 1.0
        print(f"{1:>4} {jmod:>9.4f} {'1.000':>8} {Tu:>11.4f} {OTCR/Tu:>9.4f}")
        for step in range(2, 13):
            jmod *= OTCR / Tu
            sm.SetModelIsLocked(False)
            val = [1.0]*8; val[3] = jmod
            sm.PropFrame.SetModifiers(BEAM_SEC, val)
            jread = sm.PropFrame.GetModifiers(BEAM_SEC)[0][3]
            run(sm)
            mx = frame_T(sm)
            Tu = max(mx.get(f, 0.0) for f in track)
            print(f"{step:>4} {jmod:>9.4f} {jread:>8.3f} {Tu:>11.4f} {OTCR/Tu:>9.4f}")
            if abs(Tu - OTCR)/OTCR < 0.02:
                print(f"\nCONVERGIO paso {step}: Tu={Tu:.4f}~OTcr={OTCR}, J_viga al {jmod*100:.1f}% del bruto")
                break
    finally:
        try: et.ApplicationExit(False)
        except Exception: pass


if __name__ == "__main__":
    main()
