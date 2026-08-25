#!/usr/bin/env python3
r"""
etabs_cli_full — corre un modelo ETABS headless (sin ventana) Y captura tambien
lo que ETABS NO muestra: la matriz de rigidez global K, los RHS F y la solucion U
del solver (MKL PARDISO), enganchando el proceso con Frida.

  python etabs_cli_full.py "C:\Tools\re\models\mesa.EDB" --dumpdir dump_cli

Salida:
  - resultados estandar (modal, reacciones) por OAPI -> stdout/JSON
  - K/F/U crudos del solver -> <dumpdir>/  (.bin reconstruibles con read_dump.py)

Fuerza Solver=Multi-threaded (PARDISO) + Process=GUI para que el solve corra
DENTRO del ETABS.exe headless, donde el hook esta puesto (sin carrera).
"""
import argparse, json, os, sys, time, threading
import comtypes.client as cc
import frida

UNITS = 6
HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "pardiso_hook.js"), encoding="utf-8") as f:
    HOOK = f.read()

def etabs_pids():
    dev = frida.get_local_device()
    return {p.pid for p in dev.enumerate_processes() if p.name.lower() == "etabs.exe"}

def attach_hook(pid, dumpdir, log):
    os.makedirs(dumpdir, exist_ok=True)
    dev = frida.get_local_device()
    session = dev.attach(pid)
    script = session.create_script(HOOK)
    def on_msg(message, data):
        if message["type"] == "error":
            log.append(("err", message.get("description"))); return
        p = message["payload"]; tag = p.get("tag")
        if tag in ("info","call","matrix","rhs","sol"):
            log.append((tag, p))
        elif tag == "blob" and data is not None:
            with open(os.path.join(dumpdir, f"call{p['call']:03d}_{p['what']}.bin"),"wb") as fo:
                fo.write(data)
    script.on("message", on_msg)
    script.load()
    return session, script

EXE = {
    "19": r"C:\Program Files\Computers and Structures\ETABS 19\ETABS.exe",
    "22": r"C:\Program Files\Computers and Structures\ETABS 22\ETABS.exe",
}

def start(model, visible, exe=None):
    helper = cc.CreateObject('ETABSv1.Helper')
    from comtypes.gen import ETABSv1 as E
    helper = helper.QueryInterface(E.cHelper)
    before = etabs_pids()
    if exe:                       # lanzar version explicita por ruta del .exe
        etabs = helper.CreateObject(exe)
    else:                         # default registrado (suele ser v19)
        etabs = helper.CreateObjectProgID("CSI.ETABS.API.ETABSObject")
    etabs = etabs.QueryInterface(E.cOAPI)        # interfaz tipada (ApplicationStart, SapModel)
    etabs.ApplicationStart()                     # esta typelib: SIN argumentos
    sm = etabs.SapModel
    if not visible:
        try: etabs.Hide()
        except Exception: pass
    sm.File.OpenFile(model)
    sm.SetPresentUnits(UNITS)
    # PID del ETABS.exe recien nacido
    new = etabs_pids() - before
    pid = max(new) if new else (max(etabs_pids()) if etabs_pids() else None)
    return etabs, sm, pid

def force_solver(sm):
    # Solver: 0 std, 1 advanced, 2 multi-threaded(PARDISO) | Process: 0 auto,1 GUI(in-process),2 sep
    # CLAVE: Process=1 (GUI/in-process) para que CsiGo2_n.dll cargue DENTRO del ETABS.exe
    # enganchado por Frida. Con Process=2 (separado) el solve corre en otro proceso y el
    # hook PARDISO nunca dispara.
    #   SetSolverOption_3(SolverType, ProcessType, NumberParallelRuns, RespFileMaxMB, NumThreads, StiffCase)
    #   SetSolverOption_2(SolverType, ProcessType, Force32Bit, StiffCase)
    #   SetSolverOption_1(SolverType, ProcessType)
    # rc==0 => OK en la OAPI de CSI; cualquier otro valor = rechazado. Probar varias
    # firmas/ordenes y QUEDARSE solo con la que devuelva 0.
    candidates = [
        ("SetSolverOption_3", (2, 1, 0, 0, 0, "")),
        ("SetSolverOption_3", (2, 1, 0, 0, 0)),
        ("SetSolverOption_2", (2, 1, False, "")),
        ("SetSolverOption_2", (2, 1, 0, "")),
        ("SetSolverOption_2", (2, 1, 0)),
        ("SetSolverOption_2", (2, 1)),
        ("SetSolverOption_1", (2, 1)),
    ]
    first_nothrow = None
    for setter, args in candidates:
        fn = getattr(sm.Analyze, setter, None)
        if fn is None:
            continue
        try:
            rc = fn(*args)
        except Exception as e:
            print(f"[cli]   {setter}{args} EXC: {e}", file=sys.stderr)
            continue
        print(f"[cli]   {setter}{args} -> rc={rc}", file=sys.stderr)
        if rc == 0 or rc is None:
            return f"{setter}{args} -> rc={rc}"
        if first_nothrow is None:
            first_nothrow = f"{setter}{args} -> rc={rc}"
    return first_nothrow

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--dumpdir", default=os.path.join(HERE,"dump_cli"))
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--ver", choices=["19","22"], default="19",
                    help="version de ETABS (default 19: igual al modelo Mesa torsion)")
    a = ap.parse_args()
    model = os.path.abspath(a.model)

    etabs, sm, pid = start(model, a.show, exe=EXE[a.ver])
    print(f"[cli] ETABS headless pid={pid}", file=sys.stderr)
    # El .EDB ya analizado viene BLOQUEADO; SetSolverOption falla (rc=1) si el modelo
    # esta locked -> desbloquear ANTES de forzar el solver.
    try:
        sm.SetModelIsLocked(False)
        print("[cli] modelo desbloqueado (pre force_solver)", file=sys.stderr)
    except Exception as e:
        print(f"[cli] no pude desbloquear: {e}", file=sys.stderr)
    used = force_solver(sm)
    print(f"[cli] solver forzado via {used} (multi-threaded/PARDISO, GUI process)", file=sys.stderr)

    log = []
    session = script = None
    if pid:
        try:
            session, script = attach_hook(pid, a.dumpdir, log)
            print(f"[cli] ojeador PARDISO enganchado a {pid} -> {a.dumpdir}", file=sys.stderr)
        except Exception as e:
            print(f"[cli] no pude enganchar Frida: {e}", file=sys.stderr)

    try:
        sm.SetModelIsLocked(False)
    except Exception: pass
    sm.Analyze.RunAnalysis()
    time.sleep(1.0)  # dar tiempo a que lleguen los blobs

    # resultados estandar
    out = {"model": a.model, "pid": pid, "solver_setter": used}
    try:
        r = sm.Results.ModalPeriod()
        out["modal"] = [{"mode":i+1,"period_s":r[4][i],"freq_hz":r[5][i]} for i in range(r[0])]
    except Exception as e: out["modal"] = {"error": str(e)}
    try:
        sm.Results.Setup.DeselectAllCasesAndCombosForOutput()
        names = sm.LoadCases.GetNameList()[1]
        for nm in names:
            try: sm.Results.Setup.SetCaseSelectedForOutput(nm)
            except Exception: pass
        # BaseReact: [0]N [1]case [2]stepType [3]stepNum [4]Fx [5]Fy [6]Fz [7]Mx [8]My [9]Mz
        rr = sm.Results.BaseReact()
        out["react"] = [{"case":rr[1][i],"Fx":rr[4][i],"Fy":rr[5][i],"Fz":rr[6][i],
                         "Mx":rr[7][i],"My":rr[8][i],"Mz":rr[9][i]} for i in range(rr[0])]
    except Exception as e: out["react"] = {"error": str(e)}

    # resumen de lo capturado por el ojeador
    cap = {"calls": [], "matrices": [], "solves": []}
    for tag, p in log:
        if tag == "call": cap["calls"].append({"call":p["call"],"phase":p["phase"],"n":p["n"],"nnz?":None})
        elif tag == "matrix": cap["matrices"].append({"call":p["call"],"n":p["n"],"nnz":p["nnz"],"mtype":p["mtype"]})
        elif tag == "sol": cap["solves"].append({"call":p["call"],"len":p["len"]})
    out["solver_capture"] = cap

    try: etabs.ApplicationExit(False)
    except Exception: pass

    print(json.dumps(out, indent=2, ensure_ascii=False))
    files = sorted(os.listdir(a.dumpdir)) if os.path.isdir(a.dumpdir) else []
    print(f"\n[cli] {len(files)} archivos en {a.dumpdir} (K/F/U crudos)", file=sys.stderr)

if __name__ == "__main__":
    main()
