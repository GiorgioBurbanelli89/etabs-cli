#!/usr/bin/env python3
r"""etabs-coldsolve — el "etabs.exe replicable" en modo CLI: RESUELVE un modelo de
análisis SAPFire (.Y_) SIN abrir etabs.exe, usando CSI.SAPFire.Driver.exe en frío.

Recuperado/rearmado 2026-06-08 (ver NATIVE_SOLVE_RECETA.md). El Driver es el binario
que la propia ETABS lanza como proceso separado para correr el análisis: lee el .Y_
(ReadSelf) y resuelve (Run) montando su propio contexto nativo — no necesita etabs.exe.

Uso:
  etabs-coldsolve solve  modelo.Y_            # resuelve en frío (mode 0)
  etabs-coldsolve print  modelo.Y_            # vuelca el modelo a *_GOMODEL.txt (mode 1)
  etabs-coldsolve check  modelo.Y_            # valida que el fileset esté completo

NOTA: si el .Y_ ya viene de un run previo, su estado es "resuelto" y Run() hace
corto-circuito (no recomputa; ~0.01 s). Para cómputo fresco hace falta un .Y_ recién
ESCRITO y aún NO corrido. No borres los .Y## a mano: en muchos modelos ReadSelf también
los necesita (se rompe con "Go_Model_Read() failed").

REQUISITO: junto al .Y_ deben estar sus compañeros (mismo basename):
  <base>.Y  (≈KB, base del modelo — imprescindible)  <base>.msh  <base>.K_0/.K_I/.K_J/.K_M
El Driver.exe + sus DLLs viven en engine_etabs19/ (autodetección abajo).
"""
import argparse, json, os, sys, subprocess, glob, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.abspath(os.path.join(HERE, "..", ".."))   # hekatan-etabs-bridge/

# eProgramType.Etabs=4  eProgramLevel.Advanced=7  (cServer.cs)
PROG_TYPE = {"etabs": 4, "sap2000": 1, "safe": 2, "csibridge": 3}
PROG_LEVEL_ADVANCED = 7
ENGINE_DIRS = {  # label -> carpeta del Driver+DLLs dentro del bridge
    "etabs": os.path.join(BRIDGE, "engine_etabs19"),
    "sap2000": os.path.join(BRIDGE, "engine_sap24"),
    "safe": os.path.join(BRIDGE, "engine_safe20"),
}
# fallback a la instalación local si el Driver no está en el engine aislado
INSTALL_DRIVER = r"C:\Program Files\Computers and Structures\ETABS 19\CSI.SAPFire.Driver.exe"

# vectores de resultado que se pueden borrar para forzar recompute (NUNCA borrar <base>.Y)
RESULT_EXTS = [".Y00", ".Y01", ".Y02", ".Y03", ".Y04", ".Y05", ".Y$$", ".Y_1"]
# compañeros que ReadSelf necesita presentes
REQUIRED_EXTS = [".Y_", ".Y", ".msh"]


def find_driver(prog):
    eng = ENGINE_DIRS.get(prog, ENGINE_DIRS["etabs"])
    drv = os.path.join(eng, "CSI.SAPFire.Driver.exe")
    if os.path.isfile(drv):
        return drv, eng
    if os.path.isfile(INSTALL_DRIVER):
        return INSTALL_DRIVER, os.path.dirname(INSTALL_DRIVER)
    sys.exit(f"[error] no encuentro CSI.SAPFire.Driver.exe en {eng} ni en la instalación.")


def fileset(model):
    base = os.path.splitext(os.path.abspath(model))[0]
    return base, {ext: base + ext for ext in REQUIRED_EXTS}


def cmd_check(a):
    base, req = fileset(a.model)
    missing = [ext for ext, p in req.items() if not os.path.isfile(p)]
    present = sorted(os.path.basename(p) for p in glob.glob(base + ".*"))
    info = {"model": a.model, "fileset_ok": not missing,
            "faltan": missing, "presentes": present}
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0 if not missing else 1


def _run_driver(prog, mode, out_txt, model_y, extra):
    drv, eng = find_driver(prog)
    model_y = os.path.abspath(model_y)
    out_txt = os.path.abspath(out_txt)
    args = [drv, str(mode), out_txt, model_y] + extra
    print(f"[coldsolve] {os.path.basename(drv)} mode={mode}  (cwd={eng})", file=sys.stderr)
    print("            " + " ".join(f'"{x}"' if " " in x else x for x in args), file=sys.stderr)
    r = subprocess.run(args, cwd=eng, capture_output=True, text=True)
    sys.stderr.write(r.stdout)
    if r.stderr.strip():
        sys.stderr.write(r.stderr)
    r.combined = (r.stdout or "") + (r.stderr or "")   # el Driver escribe a stdout Y stderr
    return r


def cmd_print(a):
    base, req = fileset(a.model)
    if not os.path.isfile(req[".Y"]):
        sys.exit(f"[error] falta el compañero {base}.Y (imprescindible para ReadSelf).")
    out = a.out or (base + "_print.txt")
    r = _run_driver(a.prog, 1, out, a.model, [])
    gomodel = base + "_GOMODEL.txt"
    ok = "Go_Model_Read() failed" not in r.combined and r.returncode == 0
    print(json.dumps({"ok": ok, "exit": r.returncode,
                      "gomodel": gomodel if os.path.isfile(gomodel) else None,
                      "out": out}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def cmd_solve(a):
    base, req = fileset(a.model)
    miss = [ext for ext in REQUIRED_EXTS if not os.path.isfile(req[ext])]
    if miss:
        sys.exit(f"[error] fileset incompleto, faltan: {miss}. Corré 'check' primero.")
    out = a.out or (base + "_solve.txt")
    extra = ["SAPFire", "", str(PROG_TYPE[a.prog]), str(PROG_LEVEL_ADVANCED), "false"]
    r = _run_driver(a.prog, 0, out, a.model, extra)
    crashed = "Analysis crashed" in r.combined
    readfail = "Go_Model_Read() failed" in r.combined
    ok = r.returncode == 0 and not crashed and not readfail
    info = {"ok": ok, "exit": r.returncode, "read_failed": readfail,
            "crashed": crashed, "sin_etabs_exe": True, "out": out}
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(prog="etabs-coldsolve",
        description="Resuelve un .Y_ SAPFire en frío, sin etabs.exe (CSI.SAPFire.Driver.exe).")
    ap.add_argument("--prog", choices=list(PROG_TYPE), default="etabs",
                    help="motor: etabs (def) / sap2000 / safe")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("solve", help="resolver en frío (Driver mode 0)")
    s.add_argument("model"); s.add_argument("--out")
    s.set_defaults(fn=cmd_solve)
    p = sub.add_parser("print", help="volcar el modelo a *_GOMODEL.txt (Driver mode 1)")
    p.add_argument("model"); p.add_argument("--out"); p.set_defaults(fn=cmd_print)
    c = sub.add_parser("check", help="validar fileset")
    c.add_argument("model"); c.set_defaults(fn=cmd_check)
    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
