#!/usr/bin/env python3
r"""
hekatan-solve — CLI unico del puente Hekatan<->ETABS.

Tres subcomandos:

  capture   abre un modelo .EDB headless (OAPI) + engancha PARDISO y vuelca K/F/U
            >>> NECESITA ETABS una sola vez (es quien sabe armar K) <<<
              python hekatan_solve.py capture modelo.EDB --ver 19 --out cap1

  solve     resuelve K*U=F con scipy a partir de una K ya capturada — SIN ETABS.
            Puedes pasar cargas nuevas (--loads csv) o reusar las capturadas.
              python hekatan_solve.py solve --dump cap1 --rhs 5 --out U.csv

  readk     reconstruye/exporta la K capturada a CSV (i,j,valor) y muestra info.
              python hekatan_solve.py readk --dump cap1 --matrix 1 --csv K.csv

Filosofia: ETABS arma K una vez (lo que la GUI no muestra); despues todo es
Python (cambiar cargas, re-resolver, comparar con Hekatan) sin abrir el .exe.
"""
import argparse, os, sys, glob, json
import numpy as np
from scipy.sparse import csr_matrix, triu
from scipy.sparse.linalg import spsolve

HERE = os.path.dirname(os.path.abspath(__file__))

def _f(dumpdir, call, what):
    for pat in (f"call{call:03d}_{what}.bin", f"pid*_call{call:03d}_{what}.bin"):
        g = glob.glob(os.path.join(dumpdir, pat))
        if g: return g[0]
    return None
_I = lambda p: np.frombuffer(open(p,'rb').read(), dtype=np.int32)
_D = lambda p: np.frombuffer(open(p,'rb').read(), dtype=np.float64)

def load_K(dumpdir, matrix):
    ia=_I(_f(dumpdir,matrix,"ia")); ja=_I(_f(dumpdir,matrix,"ja")); av=_D(_f(dumpdir,matrix,"a"))
    n=len(ia)-1
    Ku=csr_matrix((av,ja-1,ia-1),shape=(n,n))   # PARDISO mtype=-2: triangulo superior
    return Ku + triu(Ku,1).T, n

# ---------------- capture ----------------
def cmd_capture(a):
    # delega en etabs_cli_full.py (mismo dir)
    import runpy
    sys.argv = ["etabs_cli_full.py", a.model, "--ver", a.ver, "--dumpdir", a.out]
    if a.show: sys.argv.append("--show")
    runpy.run_path(os.path.join(HERE,"etabs_cli_full.py"), run_name="__main__")

# ---------------- solve ----------------
def cmd_solve(a):
    D = a.dump if os.path.isabs(a.dump) else os.path.join(HERE, a.dump)
    K,n = load_K(D, a.matrix)
    print(f"[solve] K de ETABS: n={n} nnz={K.nnz}  (SIN ETABS)", file=sys.stderr)
    if a.loads:
        B = np.loadtxt(a.loads, delimiter=",").reshape(-1, n).T
        print(f"[solve] cargas nuevas desde {a.loads}: {B.shape[1]} casos", file=sys.stderr)
    else:
        b=_D(_f(D,a.rhs,"b")); nrhs=len(b)//n; B=b.reshape(nrhs,n).T
        print(f"[solve] cargas capturadas call#{a.rhs}: {nrhs} casos", file=sys.stderr)
    U = spsolve(K.tocsc(), B)
    if U.ndim==1: U=U.reshape(-1,1)
    # comparacion opcional con U capturada
    xp=_f(D,a.rhs,"x") if not a.loads else None
    if xp:
        x=_D(xp).reshape(B.shape[1],n).T
        rel=np.linalg.norm(U-x)/np.linalg.norm(x)
        print(f"[solve] ||U_mio - U_etabs||/||U_etabs|| = {rel:.3e}", file=sys.stderr)
    if a.out:
        np.savetxt(a.out, U, delimiter=",")
        print(f"[solve] U -> {a.out}  ({U.shape[0]} dof x {U.shape[1]} casos)", file=sys.stderr)
    else:
        print(json.dumps({"n":n,"cases":U.shape[1],
                          "U_case0_first8":[float(v) for v in U[:8,0]]}, indent=2))

# ---------------- readk ----------------
def cmd_readk(a):
    D = a.dump if os.path.isabs(a.dump) else os.path.join(HERE, a.dump)
    K,n = load_K(D, a.matrix)
    coo=K.tocoo()
    print(f"K: n={n}  nnz(sym)={K.nnz}  ||K||_max={abs(K.data).max():.4e}")
    print("diag[0:8]:", np.round(K.diagonal()[:8],3))
    if a.csv:
        out = a.csv if os.path.isabs(a.csv) else os.path.join(D, a.csv)
        with open(out,"w") as f:
            f.write("i,j,value\n")
            for k in range(K.nnz): f.write(f"{coo.row[k]},{coo.col[k]},{coo.data[k]!r}\n")
        print("CSV ->", out)

def main():
    ap=argparse.ArgumentParser(prog="hekatan-solve",
        description="Puente Hekatan<->ETABS: captura K una vez, resuelve sin ETABS.")
    sub=ap.add_subparsers(dest="cmd", required=True)

    c=sub.add_parser("capture", help="abrir .EDB headless + capturar K/F/U")
    c.add_argument("model"); c.add_argument("--ver",choices=["19","22"],default="19")
    c.add_argument("--out",default="cap"); c.add_argument("--show",action="store_true")
    c.set_defaults(fn=cmd_capture)

    s=sub.add_parser("solve", help="resolver K*U=F con scipy (sin ETABS)")
    s.add_argument("--dump",default="cap"); s.add_argument("--matrix",type=int,default=1)
    s.add_argument("--rhs",type=int,default=3); s.add_argument("--loads")
    s.add_argument("--out"); s.set_defaults(fn=cmd_solve)

    r=sub.add_parser("readk", help="exportar K capturada a CSV")
    r.add_argument("--dump",default="cap"); r.add_argument("--matrix",type=int,default=1)
    r.add_argument("--csv"); r.set_defaults(fn=cmd_readk)

    a=ap.parse_args(); a.fn(a)

if __name__=="__main__":
    main()
