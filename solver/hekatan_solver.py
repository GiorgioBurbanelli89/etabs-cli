#!/usr/bin/env python3
r"""hekatan_solver — el solver de SAPFire REARMADO como código propio + compare rápido vs ETABS.

SAPFire = SAP IV (ver [[reference-sapfire-csigo2-lineage]]): solver de COLUMNA ACTIVA (skyline),
factorización LDLᵀ, back-substitution. Aquí está reimplementado el `COLSOL` de Bathe & Wilson
(*Numerical Methods in FE Analysis*, 1976 — el mismo `SESOL`/`COLSOL` de SAP IV) SIN llamar a
scipy/LAPACK: es NUESTRA matemática. Se valida contra la K y la U que ETABS dejó (ground-truth).

Flujo de comparación rápida:
  1. cargar K (CSR simétrica) + F + U_etabs desde un dump ground-truth (dump_gt de Frida, o captura CLI)
  2. factorizar K con COLSOL propio (skyline LDLᵀ)  -> L, D
  3. resolver K·U=F por sustitución  -> U_hekatan
  4. reportar ‖U_hekatan - U_etabs‖/‖U_etabs‖   (objetivo ~1e-13)

Uso:
  python hekatan_solver.py --dump ../../out_3x3/dump_gt --matrix 1 --rhs 3
"""
import argparse, os, glob, struct
import numpy as np


# ─────────────────────────────  E/S del ground-truth  ─────────────────────────────
def _find(d, call, what):
    for pat in (f"call{call:03d}_{what}.bin", f"pid*_call{call:03d}_{what}.bin", f"*call{call:03d}_{what}.bin"):
        g = glob.glob(os.path.join(d, pat))
        if g:
            return g[0]
    return None

def _i32(p): return np.frombuffer(open(p, "rb").read(), dtype=np.int32)
def _f64(p): return np.frombuffer(open(p, "rb").read(), dtype=np.float64)

def load_K(dumpdir, call):
    """K ensamblada por CSI (CSR triángulo superior, PARDISO mtype=-2) -> densa simétrica (numpy)."""
    ia, ja, a = _i32(_find(dumpdir, call, "ia")), _i32(_find(dumpdir, call, "ja")), _f64(_find(dumpdir, call, "a"))
    n = len(ia) - 1
    K = np.zeros((n, n))
    for i in range(n):
        for p in range(ia[i] - 1, ia[i + 1] - 1):      # PARDISO es 1-based
            j = ja[p] - 1
            K[i, j] = a[p]
            K[j, i] = a[p]                              # simetrizar
    return K, n


# ────────────────────────  perfil skyline (columna activa)  ────────────────────────
def skyline_maxa(K):
    """maxa[j] = altura de columna activa. Convención SAP IV: para cada columna j (triáng. superior),
    la primera fila no-nula i_min define la altura mk = j - i_min. Devuelve maxa (1-based, len n+1)."""
    n = K.shape[0]
    colht = np.zeros(n, dtype=np.int64)
    for j in range(n):
        i_min = j
        for i in range(j + 1):
            if K[i, j] != 0.0:
                i_min = i
                break
        colht[j] = j - i_min
    maxa = np.zeros(n + 1, dtype=np.int64)
    maxa[0] = 1
    for j in range(n):
        maxa[j + 1] = maxa[j] + colht[j] + 1           # +1 por el término diagonal
    return maxa, colht


def to_skyline(K, maxa, colht):
    """Empaqueta el triángulo superior de K en el vector activo A (col-major, estilo SAP IV/COLSOL)."""
    n = K.shape[0]
    A = np.zeros(maxa[n] - 1)
    for j in range(n):
        kn = maxa[j] - 1                               # base 0-based del A para la columna j
        for m in range(colht[j] + 1):                  # m=0 -> diagonal, hacia arriba
            i = j - m
            A[kn + m] = K[i, j]
    return A


# ───────────────────  COLSOL: LDLᵀ de columna activa (Bathe & Wilson)  ───────────────────
# Traducción fiel del COLSOL de SAP IV (Bathe, *Finite Element Procedures*). MAXA es 1-based
# (dirección del término diagonal de cada columna); A(P) del Fortran = A[P-1] en Python 0-based.
def colsol_factor(A, maxa, n):
    """Factoriza K = L·D·Lᵀ en sitio sobre el skyline A. Tras esto A[maxa[k]-1]=D[k] y los off-diag
    guardan Lᵀ reducido. Traducción 1:1 del bucle de reducción de COLSOL."""
    A = A.copy()
    for N in range(n):                                 # Fortran col N+1 ; aquí índice N (0-based)
        KN = maxa[N]                                   # dirección 1-based del diagonal
        KL = KN + 1
        KU = maxa[N + 1] - 1
        KH = KU - KL
        if KH > 0:
            K = N - KH                                 # primera columna activa (0-based)
            IC = 0
            KLT = KU
            for _ in range(KH):                        # DO J=1,KH
                IC += 1
                KLT -= 1
                KI = maxa[K]
                ND = maxa[K + 1] - KI - 1
                if ND > 0:
                    KK = min(IC, ND)
                    C = 0.0
                    for L in range(1, KK + 1):
                        C += A[KI + L - 1] * A[KLT + L - 1]
                    A[KLT - 1] -= C
                K += 1
        if KH >= 0:
            K = N
            B = 0.0
            for KKaddr in range(KL, KU + 1):           # DO KK=KL,KU
                K -= 1
                KI = maxa[K]
                C = A[KKaddr - 1] / A[KI - 1]
                B += C * A[KKaddr - 1]
                A[KKaddr - 1] = C
            A[KN - 1] -= B
        if A[KN - 1] == 0.0:
            raise ZeroDivisionError(f"pivote nulo en columna {N} (matriz singular / no def-pos)")
    return A


def colsol_solve(A, maxa, n, R):
    """Sustitución (REDBAK de SAP IV): forward reduce, dividir por D, back-substitute. A factorizado."""
    V = R.copy().astype(float)
    for N in range(n):                                 # V = L⁻¹ R
        KL = maxa[N] + 1
        KU = maxa[N + 1] - 1
        if KU - KL >= 0:
            K = N
            C = 0.0
            for KKaddr in range(KL, KU + 1):
                K -= 1
                C += A[KKaddr - 1] * V[K]
            V[N] -= C
    for N in range(n):                                 # V = D⁻¹ V
        V[N] /= A[maxa[N] - 1]
    for N in range(n - 1, 0, -1):                      # U = L⁻ᵀ V
        KL = maxa[N] + 1
        KU = maxa[N + 1] - 1
        if KU - KL >= 0:
            K = N
            for KKaddr in range(KL, KU + 1):
                K -= 1
                V[K] -= A[KKaddr - 1] * V[N]
    return V


def solve(K, F):
    """Resuelve K·U=F con el COLSOL propio. F puede ser (n,) o (n, nrhs). Devuelve U mismo shape."""
    n = K.shape[0]
    maxa, colht = skyline_maxa(K)
    A = to_skyline(K, maxa, colht)
    Af = colsol_factor(A, maxa, n)
    if F.ndim == 1:
        return colsol_solve(Af, maxa, n, F)
    U = np.zeros_like(F, dtype=float)
    for c in range(F.shape[1]):
        U[:, c] = colsol_solve(Af, maxa, n, F[:, c])
    return U, maxa


# ─────────────────────────────────  compare  ─────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default="../../out_3x3/dump_gt")
    ap.add_argument("--matrix", type=int, default=1)
    ap.add_argument("--rhs", type=int, default=3)
    a = ap.parse_args()
    D = a.dump if os.path.isabs(a.dump) else os.path.join(os.path.dirname(os.path.abspath(__file__)), a.dump)

    K, n = load_K(D, a.matrix)
    print(f"K de CSI: n={n}  nnz(dense)={int((K!=0).sum())}   simétrica={np.allclose(K,K.T)}")
    maxa, colht = skyline_maxa(K)
    print(f"perfil skyline: nº términos activos = {maxa[n]-1}  (denso sería {n*(n+1)//2})")

    bpath, xpath = _find(D, a.rhs, "b"), _find(D, a.rhs, "x")
    F = _f64(bpath); nrhs = len(F) // n
    F = F.reshape(nrhs, n).T
    print(f"F: {nrhs} casos × {n} DOF")

    U, _ = solve(K, F)
    print("\n=== COLSOL propio (SAP IV rearmado, SIN scipy) ===")
    if xpath:
        X = _f64(xpath).reshape(nrhs, n).T
        rel = np.linalg.norm(U - X) / np.linalg.norm(X)
        print(f"  ‖U_hekatan - U_etabs‖ / ‖U_etabs‖ = {rel:.3e}   max|dif|={np.abs(U-X).max():.2e}")
        # chequeo cruzado contra numpy.solve (sanity del propio COLSOL)
        Unp = np.linalg.solve(K, F)
        print(f"  (sanity) ‖U_hekatan - U_numpy‖/‖U_numpy‖ = {np.linalg.norm(U-Unp)/np.linalg.norm(Unp):.3e}")
        print(f"  -> {'✅ REPRODUCE ETABS' if rel < 1e-10 else '⚠ revisar'}  con nuestro propio solver")
        for i in range(min(6, n)):
            print(f"    dof {i:3d}: hekatan {U[i,0]: .6e}   etabs {X[i,0]: .6e}")
    else:
        print("  (sin ground-truth x para comparar)  U shape:", U.shape)


if __name__ == "__main__":
    main()
