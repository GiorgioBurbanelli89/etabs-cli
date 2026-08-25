#!/usr/bin/env python3
"""Reconstruye K/F/U desde los volcados binarios del ojeador (dump/callNNN_*.bin).
Uso:  python read_dump.py 1            # call#1
      python read_dump.py 1 --dense    # imprime K densa (solo si n es chico)
PARDISO usa CSR base-1 (Fortran). mtype<0 o {2,-2,6} => solo triangulo (simetrica).
"""
import sys, os, struct, argparse
import numpy as np

DUMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dump")

def load_int(path):
    with open(path, "rb") as f: b = f.read()
    return np.frombuffer(b, dtype=np.int32)

def load_dbl(path):
    with open(path, "rb") as f: b = f.read()
    return np.frombuffer(b, dtype=np.float64)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("call", type=int)
    ap.add_argument("--dense", action="store_true")
    ap.add_argument("--csv", action="store_true", help="exporta K_callN.csv (i,j,v)")
    a = ap.parse_args()
    c = a.call
    pj = lambda w: os.path.join(DUMP, f"call{c:03d}_{w}.bin")

    if os.path.exists(pj("ia")):
        ia = load_int(pj("ia")); ja = load_int(pj("ja")); av = load_dbl(pj("a"))
        n = len(ia) - 1; nnz = len(av)
        print(f"K: n={n}  nnz={nnz}  (CSR base-1)")
        # a CSR base-0 scipy
        from scipy.sparse import csr_matrix
        K = csr_matrix((av, ja - 1, ia - 1), shape=(n, n))
        print("  primeros 10 no-ceros:")
        coo = K.tocoo()
        for k in range(min(10, nnz)):
            print(f"    K[{coo.row[k]},{coo.col[k]}] = {coo.data[k]:.6g}")
        if a.csv:
            out = os.path.join(DUMP, f"K_call{c}.csv")
            with open(out, "w") as f:
                f.write("i,j,value\n")
                for k in range(nnz):
                    f.write(f"{coo.row[k]},{coo.col[k]},{coo.data[k]!r}\n")
            print("  CSV:", out)
        if a.dense and n <= 100:
            Kd = K.toarray()
            # simetrizar si solo hay triangulo
            Kd = Kd + Kd.T - np.diag(np.diag(Kd))
            np.set_printoptions(precision=4, suppress=True, linewidth=200)
            print(Kd)
    if os.path.exists(pj("b")):
        b = load_dbl(pj("b")); print(f"F: len={len(b)}  {b[:10]}")
    if os.path.exists(pj("x")):
        x = load_dbl(pj("x")); print(f"U: len={len(x)}  {x[:10]}")

if __name__ == "__main__":
    main()
