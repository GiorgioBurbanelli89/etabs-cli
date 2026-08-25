#!/usr/bin/env python3
r"""
solve_offline — resultados SIN abrir ETABS.
Usa la K y F ya capturadas del solver (dump/) y resuelve K*U=F con scipy.
Demuestra que, una vez capturada la rigidez, ETABS ya no hace falta:
puedes cambiar F y re-resolver libremente, cero .exe.

  python solve_offline.py --dump dump_cli            # usa el run del CLI
  python solve_offline.py --dump dump --matrix 1 --rhs 5
"""
import argparse, os, numpy as np
from scipy.sparse import csr_matrix, triu
from scipy.sparse.linalg import spsolve

def loadI(p): return np.frombuffer(open(p,'rb').read(),dtype=np.int32)
def loadD(p): return np.frombuffer(open(p,'rb').read(),dtype=np.float64)

def find(dumpdir, call, what):
    for pat in (f"call{call:03d}_{what}.bin", f"pid*_call{call:03d}_{what}.bin"):
        import glob
        g = glob.glob(os.path.join(dumpdir, pat))
        if g: return g[0]
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default="dump_cli")
    ap.add_argument("--matrix", type=int, default=1, help="nº de call con la K (factorizacion)")
    ap.add_argument("--rhs", type=int, default=3, help="nº de call de solve con F/U a comparar")
    a = ap.parse_args()
    D = a.dump if os.path.isabs(a.dump) else os.path.join(os.path.dirname(os.path.abspath(__file__)), a.dump)

    ia = loadI(find(D,a.matrix,"ia")); ja = loadI(find(D,a.matrix,"ja")); av = loadD(find(D,a.matrix,"a"))
    n = len(ia)-1
    Ku = csr_matrix((av, ja-1, ia-1), shape=(n,n))     # PARDISO: triangulo superior (mtype=-2)
    K  = Ku + triu(Ku,1).T                              # simetrizar
    print(f"K cargada de ETABS: n={n}, nnz(sym)={K.nnz}  (SIN ETABS abierto)")

    bpath = find(D,a.rhs,"b"); xpath = find(D,a.rhs,"x")
    if not bpath:
        print("no hay RHS en ese call; solo cargue K."); return
    b = loadD(bpath); nrhs = len(b)//n
    B = b.reshape(nrhs, n).T                            # columnas = casos
    print(f"F (cargas) cargada: {nrhs} casos x {n} dof")

    U = spsolve(K.tocsc(), B)                           # <<< SOLVE PROPIO, sin ETABS
    if U.ndim==1: U=U.reshape(-1,1)

    if xpath:
        x = loadD(xpath).reshape(nrhs, n).T
        err = np.abs(U - x)
        den = np.abs(x); den[den<1e-30]=1e-30
        rel = err/den
        print("\n=== U (mio, scipy) vs U (ETABS real) — caso 0 ===")
        for i in range(min(8,n)):
            print(f"  dof {i:3d}: mio {U[i,0]: .6e}   ETABS {x[i,0]: .6e}")
        print(f"\n  max |dif| = {err.max():.3e}")
        print(f"  ||U_mio - U_etabs|| / ||U_etabs|| = {np.linalg.norm(U-x)/np.linalg.norm(x):.3e}")
        print("\n  -> si ~1e-12, REPRODUJE EXACTO el solve de ETABS sin abrir ETABS.")
    else:
        print("U calculada (sin ground-truth para comparar). shape:", U.shape)

if __name__ == "__main__":
    main()
