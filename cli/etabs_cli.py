#!/usr/bin/env python3
r"""
etabs-cli — el CLI que ETABS no trae (analogo a Calcpad.Cli.exe).

Envuelve el OAPI de CSI (la unica interfaz headless real) + las utilidades
del puente Hekatan<->ETABS. ETABS corre de fondo y se oculta; tu solo usas comandos.

  etabs-cli version  modelo.EDB
  etabs-cli convert  v19.EDB out.EDB --to 22
  etabs-cli run      modelo.EDB --ver 19 --results react,modal --json out.json
  etabs-cli capture  modelo.EDB --ver 19 --out cap1      # K/F/U del solver (PARDISO)
  etabs-cli solve    --dump cap1                          # re-resolver SIN ETABS
"""
import argparse, json, os, sys
# En modo PyInstaller (frozen) los recursos viven en sys._MEIPASS.
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", ".."))   # para hekatan_edb (modo .py)

UNITS=6
EXE={"19":r"C:\Program Files\Computers and Structures\ETABS 19\ETABS.exe",
     "22":r"C:\Program Files\Computers and Structures\ETABS 22\ETABS.exe"}

def _oapi(ver, model=None, hide=True):
    import comtypes.client as cc
    cc.CreateObject('ETABSv1.Helper'); from comtypes.gen import ETABSv1 as E
    h=cc.CreateObject('ETABSv1.Helper').QueryInterface(E.cHelper)
    et=h.CreateObject(EXE[ver]).QueryInterface(E.cOAPI)
    et.ApplicationStart()
    if hide:
        try: et.Hide()
        except Exception: pass
    sm=et.SapModel
    if model: sm.File.OpenFile(os.path.abspath(model))
    sm.SetPresentUnits(UNITS)
    return et, sm

def cmd_version(a):
    from hekatan_edb import read_version
    print(json.dumps(read_version(a.model), indent=2, ensure_ascii=False))

def cmd_convert(a):
    from hekatan_edb import convert
    print(json.dumps(convert(a.src, a.out, a.to, force_via_e2k=a.via_e2k), indent=2, ensure_ascii=False))

def cmd_run(a):
    et, sm = _oapi(a.ver, a.model, hide=not a.show)
    try:
        try: sm.SetModelIsLocked(False)
        except Exception: pass
        sm.Analyze.RunAnalysis()
        want=set(s.strip() for s in a.results.split(","))
        out={"model":a.model,"ver":sm.GetVersion()[0]}
        sm.Results.Setup.DeselectAllCasesAndCombosForOutput()
        for nm in sm.LoadCases.GetNameList()[1]:
            try: sm.Results.Setup.SetCaseSelectedForOutput(nm)
            except Exception: pass
        if "modal" in want:
            r=sm.Results.ModalPeriod()
            out["modal"]=[{"mode":i+1,"T":r[4][i],"f":r[5][i]} for i in range(r[0])]
        if "react" in want:
            r=sm.Results.BaseReact()
            out["react"]=[{"case":r[1][i],"Fx":r[4][i],"Fy":r[5][i],"Fz":r[6][i],
                           "Mx":r[7][i],"My":r[8][i],"Mz":r[9][i]} for i in range(r[0])]
    finally:
        try: et.ApplicationExit(False)
        except Exception: pass
    s=json.dumps(out, indent=2, ensure_ascii=False); print(s)
    if a.json: open(a.json,"w",encoding="utf-8").write(s)

def cmd_capture(a):
    import runpy
    sys.argv=["etabs_cli_full.py", a.model, "--ver", a.ver, "--dumpdir", a.out]
    runpy.run_path(os.path.join(HERE,"etabs_cli_full.py"), run_name="__main__")

def cmd_solve(a):
    import runpy
    sys.argv=["hekatan_solve.py","solve","--dump",a.dump]+(["--rhs",str(a.rhs)] if a.rhs else [])+(["--out",a.out] if a.out else [])
    runpy.run_path(os.path.join(HERE,"hekatan_solve.py"), run_name="__main__")

def main():
    ap=argparse.ArgumentParser(prog="etabs-cli", description="El CLI headless para ETABS (via OAPI).")
    sub=ap.add_subparsers(dest="cmd", required=True)
    v=sub.add_parser("version"); v.add_argument("model"); v.set_defaults(fn=cmd_version)
    c=sub.add_parser("convert"); c.add_argument("src"); c.add_argument("out")
    c.add_argument("--to",required=True,choices=["19","22"]); c.add_argument("--via-e2k",action="store_true"); c.set_defaults(fn=cmd_convert)
    r=sub.add_parser("run"); r.add_argument("model"); r.add_argument("--ver",choices=["19","22"],default="19")
    r.add_argument("--results",default="react,modal"); r.add_argument("--json"); r.add_argument("--show",action="store_true"); r.set_defaults(fn=cmd_run)
    cap=sub.add_parser("capture"); cap.add_argument("model"); cap.add_argument("--ver",choices=["19","22"],default="19")
    cap.add_argument("--out",default="cap"); cap.set_defaults(fn=cmd_capture)
    so=sub.add_parser("solve"); so.add_argument("--dump",default="cap"); so.add_argument("--rhs",type=int); so.add_argument("--out"); so.set_defaults(fn=cmd_solve)
    a=ap.parse_args(); a.fn(a)

if __name__=="__main__":
    main()
