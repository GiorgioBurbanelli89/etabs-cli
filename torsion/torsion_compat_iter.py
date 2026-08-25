#!/usr/bin/env python3
r"""torsion_compat_iter — AUTOMATIZA la iteracion de torsion por COMPATIBILIDAD (ACI 318)
que el usuario hacia A MANO en 'Modelo Correccion de Torsion.xlsx'.

Idea (igual que el Excel, pero el bucle lo hace Python manejando ETABS por OAPI):
  1. Correr ETABS LINEAL con el combo UDCon2.
  2. Leer la torsion Tu de la viga gobernante (la de mas torsion).
  3. factor = OTcr / Tu ; modificador_J_acumulado *= factor.
  4. Aplicar el modificador de la CONSTANTE TORSIONAL (J) a esa viga y re-correr.
  5. Repetir hasta que Tu -> OTcr (factor -> 1).  => la viga "agrietada" en torsion
     queda con J reducido al ~7% y solo carga Tcr (torsion de agrietamiento).

OJO: esto es una SECUENCIA DE ANALISIS LINEALES que IMITA el ablandamiento no lineal
(reduccion de rigidez torsional al agrietar). NO es analisis no lineal real -> ese es el
paso siguiente (hook Frida sobre el solver no lineal de ETABS).

  python torsion_compat_iter.py            # itera con OTcr del Excel (1.9394 ton·m)
  python torsion_compat_iter.py --otcr X   # otro objetivo phi*Tcr
"""
import os, sys, shutil, argparse, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from etabs_cli_standalone import oapi_start

SRC_DIR = r"C:\Users\j-b-j\Downloads\Etabs Torsion"
WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "out_torsion")
WORK = os.path.abspath(WORK)
EDB = os.path.join(WORK, "iter.EDB")   # sin acento -> ETABS abre limpio
COMBO = "UDCon2"
UNITS_TONF_M = 12     # Tonf, m, C  -> Tu en ton·m (como el Excel)


def prep(pattern):
    # regla de oro de la guia: matar TODO ETABS antes de correr (un ETABS suelto
    # secuestra el OAPI por la ROT -> RPC 0x800706BE / crash).
    os.system("taskkill /F /IM ETABS.exe >nul 2>&1")
    os.makedirs(WORK, exist_ok=True)
    # localizar el EDB por patron (evita problemas con el acento del nombre)
    cands = glob.glob(os.path.join(SRC_DIR, pattern))
    if not cands:
        sys.exit(f"[!] no encontre {pattern} en {SRC_DIR}")
    src = max(cands, key=os.path.getmtime)
    from etabs_cli_standalone import read_version
    ver = read_version(src)["family"]          # auto-detectar v19 / v22
    print(f"[prep] {os.path.basename(src)} (ETABS {ver}) -> {EDB}", file=sys.stderr)
    shutil.copy2(src, EDB)
    et = os.path.splitext(src)[0] + ".$et"
    if os.path.exists(et):
        shutil.copy2(et, os.path.splitext(EDB)[0] + ".$et")
    if not os.path.exists(EDB):
        sys.exit("[!] la copia fallo")
    return ver


def run_and_read(sm, target=None):
    """Corre el modelo y devuelve {frame: maxT}. Si target dado, devuelve su maxT."""
    try: sm.SetModelIsLocked(False)
    except Exception: pass
    sm.Analyze.RunAnalysis()
    sm.Results.Setup.DeselectAllCasesAndCombosForOutput()
    sm.Results.Setup.SetComboSelectedForOutput(COMBO)
    r = sm.Results.FrameForce("All", 2)   # 2 = ItemTypeElm (All)
    n, obj, T = r[0], r[1], r[10]          # T = torsion (indice 10)
    maxT = {}
    for i in range(n):
        maxT[obj[i]] = max(maxT.get(obj[i], 0.0), abs(T[i]))
    if target is not None:
        return maxT.get(target, 0.0)
    return maxT


def set_section_torsion_modifier(sm, sections, jmod):
    """Aplica el modificador de la constante torsional (J) a las SECCIONES (como en el
    dialogo 'Frame Section Property Data -> Property/Stiffness Modification Factors').
    Es el modificador de SECCION (PropFrame.SetModifiers), NO el de objeto: en ETABS
    object_mod * section_mod se MULTIPLICAN. Para reproducir el Excel hay que tocar el
    de la seccion (V30x50).  value[8]=[Area,As2,As3,Torsion(J),I22,I33,Mass,Weight].
    OJO: desbloquear ANTES o se ignora en silencio."""
    try: sm.SetModelIsLocked(False)
    except Exception: pass
    applied = {}
    for sec in sections:
        val = [1.0]*8
        val[3] = jmod
        sm.PropFrame.SetModifiers(sec, val)
        back = sm.PropFrame.GetModifiers(sec)     # leer de vuelta para confirmar
        applied[sec] = back[0][3] if back and back[0] else None
    return applied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--otcr", type=float, default=1.9394, help="objetivo phi*Tcr (ton·m)")
    ap.add_argument("--tol", type=float, default=0.02, help="tolerancia |Tu-OTcr|/OTcr")
    ap.add_argument("--maxit", type=int, default=12)
    ap.add_argument("--model", default="Mesa torsi*n.EDB",
                    help="patron glob del EDB (default = el original del Excel, v19)")
    a = ap.parse_args()

    ver = prep(a.model)
    # arranque robusto: ciclos rapidos dan RPC 0x800706BE intermitente.
    et = sm = None
    import time
    for intento in range(1, 6):
        try:
            et, sm = oapi_start(ver, EDB, hide=True)
            break
        except Exception as e:
            print(f"[start] intento {intento} fallo ({str(e)[:60]}); limpio y reintento",
                  file=sys.stderr)
            os.system("taskkill /F /IM ETABS.exe >nul 2>&1")
            time.sleep(5)
    if sm is None:
        sys.exit("[!] no pude arrancar ETABS 22 tras 5 intentos")
    try:
        sm.SetPresentUnits(UNITS_TONF_M)
        # desactivar Modal para ir mas rapido (solo estaticos + combos)
        try: sm.Analyze.SetRunCaseFlag("Modal", False, False)
        except Exception: pass

        # --- paso 0: PARTIR DEL Tu BRUTO: modificador de seccion J=1.0 ---
        # descubrir vigas mas torsionadas y sus SECCIONES
        maxT = run_and_read(sm)
        gobern = max(maxT, key=maxT.get)
        Tmax = maxT[gobern]
        torsion_members = [f for f, v in maxT.items() if v >= 0.5*Tmax]
        secs = set()
        for f in torsion_members:
            try: secs.add(sm.FrameObj.GetSection(f)[0])
            except Exception: pass
        secs = sorted(s for s in secs if s) or ["V30x50"]
        print(f"=== TORSION POR COMPATIBILIDAD (auto-iteracion, VIA C OAPI) ===")
        print(f"combo={COMBO}  OTcr objetivo={a.otcr} ton·m  unidades=Tonf,m")
        top = sorted(maxT.items(), key=lambda kv: -kv[1])[:8]
        print("top torsiones:", "  ".join(f"{k}={v:.3f}" for k, v in top))
        print(f"vigas de torsion={torsion_members}  SECCIONES a modificar={secs}")
        print(f"\n{'Paso':>4} {'Jmod sec.':>10} {'Jmod leido':>11} {'Tu (ton·m)':>12} {'OTcr/Tu':>10}")

        # paso 1: forzar J=1.0 en la seccion -> Tu BRUTO real (sin modificador previo)
        jmod = 1.0
        set_section_torsion_modifier(sm, secs, 1.0)
        mt = run_and_read(sm)
        Tu = max(mt.get(f, 0.0) for f in torsion_members)
        print(f"{1:>4} {jmod:>10.4f} {'1.0000':>11} {Tu:>12.4f} {a.otcr/Tu:>10.4f}")

        for step in range(2, a.maxit + 1):
            factor = a.otcr / Tu                 # ratio del paso (OTcr/Tu)
            jmod *= factor                       # modificador ACUMULADO (como G_n del Excel)
            applied = set_section_torsion_modifier(sm, secs, jmod)
            jread = list(applied.values())[0]
            mt = run_and_read(sm)
            Tu = max(mt.get(f, 0.0) for f in torsion_members)
            ratio = a.otcr / Tu
            jr = f"{jread:.4f}" if jread is not None else "?"
            print(f"{step:>4} {jmod:>10.4f} {jr:>11} {Tu:>12.4f} {ratio:>10.4f}")
            if abs(Tu - a.otcr) / a.otcr < a.tol:
                print(f"\nCONVERGIO en paso {step}: Tu={Tu:.4f} ~ OTcr={a.otcr}  "
                      f"con Jmod_seccion={jmod:.4f} (J agrietado al {jmod*100:.1f}% del bruto)")
                break
        else:
            print("\n[!] no convergio en maxit.")
    finally:
        try: et.ApplicationExit(False)
        except Exception: pass


if __name__ == "__main__":
    main()
