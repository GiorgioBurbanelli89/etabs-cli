#!/usr/bin/env python3
r"""
etabs-cli — el CLI que ETABS no trae (analogo a Calcpad.Cli.exe).

Envuelve el OAPI de CSI (la unica interfaz headless real) + las utilidades
del puente Hekatan<->ETABS. ETABS corre de fondo y se oculta; tu solo usas comandos.

  etabs-cli version  modelo.EDB
  etabs-cli convert  v19.EDB out.EDB --to 22
  etabs-cli run      modelo.EDB --ver 19 --results react,modal --json out.json
  etabs-cli export   modelo.EDB out.e2k --ver 22          # ETABS -> texto e2k
  etabs-cli import   modelo.e2k out.EDB --ver 22          # e2k -> ETABS (.EDB)
  etabs-cli capture  modelo.EDB --ver 19 --out cap1      # K/F/U del solver (PARDISO)
  etabs-cli solve    --dump cap1                          # re-resolver SIN ETABS
"""
import argparse, json, os, shutil, sys, tempfile
# En modo PyInstaller (frozen) los recursos viven en sys._MEIPASS.
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", ".."))   # para hekatan_edb (modo .py)

UNITS=6
# Modelos de TEXTO de ETABS. OpenFile los abre igual que un .EDB, pero el modelo
# queda "sin guardar" y el solver se niega a correr hasta que exista el .EDB.
TEXT_EXT=(".e2k",".$et")
# File.ExportFile(path, tipo) -> eFileTypeIO:  1 = TextFile (.e2k)   2 = Excel
FT_TEXT=1
EXE={"19":r"C:\Program Files\Computers and Structures\ETABS 19\ETABS.exe",
     "22":r"C:\Program Files\Computers and Structures\ETABS 22\ETABS.exe"}

def _oapi(ver, model=None, hide=True, edb_out=None):
    import comtypes.client as cc
    cc.CreateObject('ETABSv1.Helper'); from comtypes.gen import ETABSv1 as E
    h=cc.CreateObject('ETABSv1.Helper').QueryInterface(E.cHelper)
    et=h.CreateObject(EXE[ver]).QueryInterface(E.cOAPI)
    et.ApplicationStart()
    if hide:
        try: et.Hide()
        except Exception: pass
    sm=et.SapModel
    if model:
        p=os.path.abspath(model)
        sm.File.OpenFile(p)
        if os.path.splitext(p)[1].lower() in TEXT_EXT:
            # ETABS exige el modelo GUARDADO como .EDB antes de analizar: si abres
            # un .e2k y llamas RunAnalysis() sin esto, devuelve 1 y todo sale en cero.
            dst=os.path.abspath(edb_out) if edb_out else os.path.splitext(p)[0]+".EDB"
            r=sm.File.Save(dst)
            if r!=0: print("aviso: File.Save('%s') retorno %d"%(dst,r), file=sys.stderr)
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
        if "modalmass" in want:
            # OAPI: (n, case[], stepType[], stepNum[], T[], UX,UY,UZ, SumUX,SumUY,SumUZ,
            #        RX,RY,RZ, SumRX,SumRY,SumRZ, ret)
            r=sm.Results.ModalParticipatingMassRatios(); n=r[0]
            col=dict(zip(["T","UX","UY","UZ","SumUX","SumUY","SumUZ",
                          "RX","RY","RZ","SumRX","SumRY","SumRZ"], r[4:17]))
            out["modalmass"]=[dict([("mode",i+1)]+[(k,v[i]) for k,v in col.items()])
                              for i in range(n)]
        if "disp" in want:
            # JointDispl(name, itemType): r[0]=n, r[1]=obj, r[3]=case,
            # r[6..11] = U1 U2 U3 R1 R2 R3.  itemType 2 = grupo -> "All" = todos.
            r=sm.Results.JointDispl("All", 2); n=r[0]
            best={}
            for i in range(n):
                c=str(r[3][i]); b=best.setdefault(c, {})
                for j,k in enumerate(["U1","U2","U3"]):
                    v=r[6+j][i]
                    if abs(v) > abs(b.get(k,(0,None))[0]): b[k]=(v, str(r[1][i]))
            out["disp_max"]=[dict([("case",c)]+[(k,{"v":v,"joint":j}) for k,(v,j) in sorted(b.items())])
                             for c,b in sorted(best.items())]
        if "react" in want:
            r=sm.Results.BaseReact()
            out["react"]=[{"case":r[1][i],"Fx":r[4][i],"Fy":r[5][i],"Fz":r[6][i],
                           "Mx":r[7][i],"My":r[8][i],"Mz":r[9][i]} for i in range(r[0])]
    finally:
        try: et.ApplicationExit(False)
        except Exception: pass
    s=json.dumps(out, indent=2, ensure_ascii=False); print(s)
    if a.json: open(a.json,"w",encoding="utf-8").write(s)

def _export_text(sm, out, src):
    """Deja el modelo abierto como texto e2k en `out`. Devuelve el dict de info.

    Dos caminos, porque no todas las versiones sirven el primero:
      1) File.ExportFile(out, 1)  -> ETABS 22 lo hace bien.
         ETABS 19 revienta con RPC_E_SERVERFAULT: su OAPI v1 no lo expone.
      2) Fallback universal: al hacer File.Save(x.EDB) ETABS escribe SIEMPRE un
         `x.$et` al lado, que es el MISMO texto e2k (byte a byte). Se copia.
    NUNCA se escribe sobre el .EDB de origen: guardarlo con un motor mas nuevo
    lo convertiria de version a espaldas del usuario. Si hiciera falta, el .EDB
    de trabajo va a un temporal.
    """
    out=os.path.abspath(out); src=os.path.abspath(src)
    info={"model":src,"e2k":out}
    edb=os.path.splitext(out)[0]+".EDB"
    tmp=None
    if os.path.normcase(edb)==os.path.normcase(src):
        tmp=tempfile.mkdtemp(prefix="etabscli_")
        edb=os.path.join(tmp,"work.EDB")
    try:
        r=sm.File.Save(edb)
        if r!=0: print("aviso: File.Save('%s') retorno %d"%(edb,r), file=sys.stderr)
        try: ret=sm.File.ExportFile(out, FT_TEXT)
        except Exception as e: ret=-1; info["ExportFile_error"]=str(e)[:120]
        if ret==0 and os.path.exists(out) and os.path.getsize(out)>0:
            info["via"]="ExportFile"
        else:
            et_txt=os.path.splitext(edb)[0]+".$et"
            if not os.path.exists(et_txt):
                raise RuntimeError("ExportFile retorno %d y no hay '%s' de respaldo"%(ret,et_txt))
            shutil.copyfile(et_txt, out); info["via"]="$et"
        info["edb"]=None if tmp else edb
        info["bytes"]=os.path.getsize(out)
        return info
    finally:
        if tmp: shutil.rmtree(tmp, ignore_errors=True)

def cmd_export(a):
    """ETABS -> .e2k (texto). Ver _export_text: ExportFile, o el .$et del Save."""
    et, sm = _oapi(a.ver, a.model)
    try: info=_export_text(sm, a.out, a.model)
    finally:
        try: et.ApplicationExit(False)
        except Exception: pass
    print(json.dumps(info, indent=2, ensure_ascii=False))

def cmd_import(a):
    """.e2k -> ETABS (.EDB). El Save lo hace _oapi al ver que el modelo es texto."""
    out=os.path.abspath(a.out)
    et, sm = _oapi(a.ver, a.model, hide=not (a.show or a.keep), edb_out=out)
    info={"e2k":a.model,"edb":out}
    try:
        if os.path.splitext(os.path.abspath(a.model))[1].lower() not in TEXT_EXT:
            sm.File.Save(out)
        if a.run:
            try: sm.SetModelIsLocked(False)
            except Exception: pass
            info["analyze_ret"]=sm.Analyze.RunAnalysis(); sm.File.Save(out)
        if a.keep:
            try: et.Unhide()      # que la ventana quede a la vista para revisarlo
            except Exception: pass
    finally:
        if not a.keep:
            try: et.ApplicationExit(False)
            except Exception: pass
    info["bytes"]=os.path.getsize(out) if os.path.exists(out) else 0
    info["etabs"]="abierto (no lo cerre)" if a.keep else "cerrado"
    print(json.dumps(info, indent=2, ensure_ascii=False))

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
    e=sub.add_parser("export"); e.add_argument("model"); e.add_argument("out")
    e.add_argument("--ver",choices=["19","22"],default="19"); e.set_defaults(fn=cmd_export)
    i=sub.add_parser("import"); i.add_argument("model"); i.add_argument("out")
    i.add_argument("--ver",choices=["19","22"],default="19")
    i.add_argument("--run",action="store_true",help="correr el analisis y guardar el .EDB resuelto")
    i.add_argument("--show",action="store_true",help="mostrar la ventana de ETABS")
    i.add_argument("--keep",action="store_true",help="dejar ETABS abierto al terminar (implica --show)")
    i.set_defaults(fn=cmd_import)
    cap=sub.add_parser("capture"); cap.add_argument("model"); cap.add_argument("--ver",choices=["19","22"],default="19")
    cap.add_argument("--out",default="cap"); cap.set_defaults(fn=cmd_capture)
    so=sub.add_parser("solve"); so.add_argument("--dump",default="cap"); so.add_argument("--rhs",type=int); so.add_argument("--out"); so.set_defaults(fn=cmd_solve)
    a=ap.parse_args(); a.fn(a)

if __name__=="__main__":
    main()
