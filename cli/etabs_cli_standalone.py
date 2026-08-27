#!/usr/bin/env python3
r"""etabs-cli (autonomo) — el CLI que ETABS no trae. Todo inline para empaquetar a .exe.
  etabs-cli version  modelo.EDB
  etabs-cli convert  v19.EDB out.EDB --to 22
  etabs-cli run      modelo.EDB --ver 19 --results react,modal --json out.json
  etabs-cli export   modelo.EDB out.e2k --ver 22   # ETABS -> texto e2k
  etabs-cli import   modelo.e2k out.EDB --ver 22   # e2k -> ETABS (.EDB)
  etabs-cli solve    --dump cap1 --rhs 5        # re-resuelve K capturada SIN ETABS
"""
import argparse, json, os, sys, re, glob, tempfile, shutil

EXE={"19":r"C:\Program Files\Computers and Structures\ETABS 19\ETABS.exe",
     "22":r"C:\Program Files\Computers and Structures\ETABS 22\ETABS.exe"}
UNITS=6
# Modelos de TEXTO de ETABS: OpenFile los abre igual que un .EDB, pero el modelo
# queda "sin guardar" y el solver no corre hasta que exista el .EDB.
TEXT_EXT=(".e2k",".$et")
FT_TEXT=1          # File.ExportFile(path,tipo) -> eFileTypeIO: 1=TextFile, 2=Excel
_FMT2FAM={"19.04":"19","23.01":"22"}

# ---------- version (sin ETABS) ----------
def read_version(path, nbytes=512):
    head=open(path,"rb").read(nbytes).decode("latin1","ignore")
    prog=next(iter(re.findall(r"ETABS|SAP2000|SAFE",head)),None)
    toks=re.findall(r"\b\d{1,2}\.\d{1,2}(?:\.\d+)?\b",head)
    fmt=toks[0] if toks else None
    pv=next((t for t in toks if t.count(".")==2),None)
    fam=_FMT2FAM.get(fmt) or (pv.split(".")[0] if pv else None)
    return {"program":prog,"format":fmt,"program_version":pv,"family":fam,"raw":toks[:6],"path":path}

# ---------- OAPI ----------
def oapi_start(ver, model=None, hide=True, edb_out=None):
    import comtypes.client as cc
    cc.CreateObject('ETABSv1.Helper'); from comtypes.gen import ETABSv1 as E
    h=cc.CreateObject('ETABSv1.Helper').QueryInterface(E.cHelper)
    et=h.CreateObject(EXE[ver]).QueryInterface(E.cOAPI); et.ApplicationStart()
    if hide:
        try: et.Hide()
        except Exception: pass
    sm=et.SapModel
    if model:
        p=os.path.abspath(model); sm.File.OpenFile(p)
        if os.path.splitext(p)[1].lower() in TEXT_EXT:
            # sin este Save, RunAnalysis() sobre un .e2k devuelve 1 y todo sale en cero
            dst=os.path.abspath(edb_out) if edb_out else os.path.splitext(p)[0]+".EDB"
            r=sm.File.Save(dst)
            if r!=0: print("aviso: File.Save('%s') retorno %d"%(dst,r),file=sys.stderr)
    sm.SetPresentUnits(UNITS); return et,sm

# ---------- convert ----------
def convert(src,out,target,via_e2k=False):
    src_fam=read_version(src)["family"]; target=str(target)
    info={"src":src,"src_family":src_fam,"target":target,"out":out}
    if int(target)>=int(src_fam) and not via_e2k:
        et,sm=oapi_start(target,src); sm.File.Save(os.path.abspath(out))
        et.ApplicationExit(False); info["mode"]="upgrade_native" if target!=src_fam else "resave"
    else:
        with tempfile.TemporaryDirectory() as td:
            et,sm=oapi_start(src_fam,src); w=os.path.join(td,"w.EDB"); sm.File.Save(w)
            et.ApplicationExit(False)
            etx=os.path.splitext(w)[0]+".$et"
            et2,sm2=oapi_start(target,etx); sm2.File.Save(os.path.abspath(out)); et2.ApplicationExit(False)
        info["mode"]="downgrade_via_e2k"
    info["out_version"]=read_version(out)["program_version"]; return info

# ---------- export / import e2k ----------
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
    et,sm=oapi_start(a.ver,a.model)
    try: info=_export_text(sm,a.out,a.model)
    finally:
        try: et.ApplicationExit(False)
        except Exception: pass
    print(json.dumps(info,indent=2,ensure_ascii=False))

def cmd_import(a):
    """.e2k -> ETABS (.EDB). El Save lo hace oapi_start al ver que el modelo es texto."""
    out=os.path.abspath(a.out)
    et, sm = oapi_start(a.ver, a.model, hide=not (a.show or a.keep), edb_out=out)
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

# ---------- run (incluye mesa: frames + shells via grupo "All") ----------
G=9.80665
def cmd_run(a):
    import collections
    et,sm=oapi_start(a.ver,a.model,hide=not a.show)
    try:
        try: sm.SetModelIsLocked(False)
        except Exception: pass
        sm.Analyze.RunAnalysis()
        want=set(s.strip() for s in a.results.split(","))
        out={"model":a.model,"ver":sm.GetVersion()[0]}
        sm.Results.Setup.DeselectAllCasesAndCombosForOutput()
        cases=list(sm.LoadCases.GetNameList()[1])
        sel=[a.case] if a.case else cases
        for nm in sel:
            try: sm.Results.Setup.SetCaseSelectedForOutput(nm)
            except Exception: pass
        out["case"]= a.case or "todos"
        if "modal" in want:
            try:
                r=sm.Results.ModalPeriod(); out["modal"]=[{"mode":i+1,"T":r[4][i],"f":r[5][i]} for i in range(r[0])]
            except Exception as e: out["modal"]={"error":str(e)[:80]}
        if "react" in want:
            try:
                r=sm.Results.BaseReact()
                out["react"]=[{"case":r[1][i],"Fz":r[6][i],"Mx":r[7][i],"My":r[8][i],"Mz":r[9][i]} for i in range(r[0])]
            except Exception as e: out["react"]={"error":str(e)[:80]}
        if "frames" in want:
            try:
                r=sm.Results.FrameForce("All",2); nb=r[0]; obj=r[1]
                P,V2,V3,T,M2,M3=r[7],r[8],r[9],r[10],r[11],r[12]
                agg=collections.defaultdict(lambda:dict(P=0,V2=0,V3=0,T=0,M2=0,M3=0))
                for i in range(nb):
                    g=agg[obj[i]]
                    for k,val in [("P",P[i]),("V2",V2[i]),("V3",V3[i]),("T",T[i]),("M2",M2[i]),("M3",M3[i])]:
                        g[k]=max(g[k],abs(val))
                out["frames"]={k:{c:round(v/G,4) for c,v in g.items()} for k,g in agg.items()}
            except Exception as e: out["frames"]={"error":str(e)[:80]}
        if "shells" in want:
            try:
                r=sm.Results.AreaForceShell("All",2); nb=r[0]
                M11,M22,M12=r[14],r[15],r[16]
                out["shells"]={"Mxx_max":round(max(abs(M11[i]) for i in range(nb))/G,4),
                               "Myy_max":round(max(abs(M22[i]) for i in range(nb))/G,4),
                               "Mxy_max":round(max(abs(M12[i]) for i in range(nb))/G,4),
                               "n_shells":nb}
            except Exception as e: out["shells"]={"error":str(e)[:80]}
    finally:
        try: et.ApplicationExit(False)
        except Exception: pass
    s=json.dumps(out,indent=2,ensure_ascii=False); print(s)
    if a.json: open(a.json,"w",encoding="utf-8").write(s)

# ---------- solve (SIN ETABS) ----------
def cmd_solve(a):
    import numpy as np
    from scipy.sparse import csr_matrix, triu
    from scipy.sparse.linalg import spsolve
    D=a.dump
    def f(c,w):
        for p in (f"call{c:03d}_{w}.bin",f"pid*_call{c:03d}_{w}.bin"):
            g=glob.glob(os.path.join(D,p))
            if g: return g[0]
    I=lambda p: np.frombuffer(open(p,'rb').read(),dtype=np.int32)
    Dd=lambda p: np.frombuffer(open(p,'rb').read(),dtype=np.float64)
    ia=I(f(1,"ia")); ja=I(f(1,"ja")); av=Dd(f(1,"a")); n=len(ia)-1
    Ku=csr_matrix((av,ja-1,ia-1),shape=(n,n)); K=(Ku+triu(Ku,1).T).tocsc()
    b=Dd(f(a.rhs,"b")); nc=len(b)//n; B=b.reshape(nc,n).T
    U=spsolve(K,B)
    if U.ndim==1: U=U.reshape(-1,1)
    xp=f(a.rhs,"x")
    info={"n":n,"cases":U.shape[1]}
    if xp:
        X=Dd(xp).reshape(nc,n).T
        info["rel_err_vs_etabs"]=float(np.linalg.norm(U-X)/np.linalg.norm(X))
    info["U_case0_first6"]=[float(v) for v in U[:6,0]]
    print(json.dumps(info,indent=2,ensure_ascii=False))
    if a.out: np.savetxt(a.out,U,delimiter=","); print(f"-> {a.out}",file=sys.stderr)

def main():
    ap=argparse.ArgumentParser(prog="etabs-cli",description="CLI headless para ETABS (OAPI) + puente Hekatan.")
    sub=ap.add_subparsers(dest="cmd",required=True)
    v=sub.add_parser("version"); v.add_argument("model")
    v.set_defaults(fn=lambda a:print(json.dumps(read_version(a.model),indent=2,ensure_ascii=False)))
    c=sub.add_parser("convert"); c.add_argument("src"); c.add_argument("out"); c.add_argument("--to",required=True,choices=["19","22"]); c.add_argument("--via-e2k",action="store_true")
    c.set_defaults(fn=lambda a:print(json.dumps(convert(a.src,a.out,a.to,a.via_e2k),indent=2,ensure_ascii=False)))
    r=sub.add_parser("run"); r.add_argument("model"); r.add_argument("--ver",choices=["19","22"],default="19"); r.add_argument("--results",default="react,modal"); r.add_argument("--case"); r.add_argument("--json"); r.add_argument("--show",action="store_true"); r.set_defaults(fn=cmd_run)
    e=sub.add_parser("export"); e.add_argument("model"); e.add_argument("out"); e.add_argument("--ver",choices=["19","22"],default="19"); e.set_defaults(fn=cmd_export)
    i=sub.add_parser("import"); i.add_argument("model"); i.add_argument("out"); i.add_argument("--ver",choices=["19","22"],default="19")
    i.add_argument("--run",action="store_true",help="correr el analisis y guardar el .EDB resuelto")
    i.add_argument("--show",action="store_true",help="mostrar la ventana de ETABS")
    i.add_argument("--keep",action="store_true",help="dejar ETABS abierto al terminar (implica --show)"); i.set_defaults(fn=cmd_import)
    so=sub.add_parser("solve"); so.add_argument("--dump",required=True); so.add_argument("--rhs",type=int,default=3); so.add_argument("--out"); so.set_defaults(fn=cmd_solve)
    a=ap.parse_args(); a.fn(a)

if __name__=="__main__":
    main()
