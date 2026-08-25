#!/usr/bin/env python3
r"""Prep UNICO con OAPI: voladizo que SI deflecta. Corre (etabs.exe escribe el .Y_ y
computa) y deja el fileset para LEER/RE-RESOLVER en frio sin etabs.exe.
Voladizo horizontal: n1(0,0,0) empotrado, n2(L,0,0) libre, carga Fz=-P en n2.
"""
import os, sys, shutil, glob
sys.stdout.reconfigure(encoding="utf-8")

EXE = r"C:\Program Files\Computers and Structures\ETABS 19\ETABS.exe"
OUTDIR = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\cant_model"
os.makedirs(OUTDIR, exist_ok=True)
EDB = os.path.join(OUTDIR, "cant.EDB")
L, P, E = 4.0, 10.0, 2.1e8
b_, hh = 0.3, 0.3
Ireal = b_ * hh**3 / 12.0

import comtypes.client as cc
cc.CreateObject("ETABSv1.Helper")
from comtypes.gen import ETABSv1 as Ev1
h = cc.CreateObject("ETABSv1.Helper").QueryInterface(Ev1.cHelper)
et = h.CreateObject(EXE).QueryInterface(Ev1.cOAPI)
et.ApplicationStart()
try: et.Hide()
except Exception: pass
sm = et.SapModel
sm.InitializeNewModel(6)            # kN_m_C
sm.File.NewBlank()
sm.PropMaterial.SetMaterial("ST", 1)
sm.PropMaterial.SetMPIsotropic("ST", E, 0.3, 1.17e-5)
sm.PropFrame.SetRectangle("R30", "ST", hh, b_)
print("AddCart n1:", sm.PointObj.AddCartesian(0.0, 0.0, 0.0, "n1", "n1"))
print("AddCart n2:", sm.PointObj.AddCartesian(L, 0.0, 0.0, "n2", "n2"))
print("SetRestraint n1:", sm.PointObj.SetRestraint("n1", [True, True, True, True, True, True]))
print("AddByPoint f1:", sm.FrameObj.AddByPoint("n1", "n2", "f1", "R30", "f1"))
print("Points:", sm.PointObj.Count(), " Frames:", sm.FrameObj.Count())
print("AddLoadPat PL:", sm.LoadPatterns.Add("PL", 8, 0.0, True))
print("SetLoadForce n2:", sm.PointObj.SetLoadForce("n2", "PL", [0.0, 0.0, -P, 0.0, 0.0, 0.0], True, "Global", 0))
sm.File.Save(EDB)
print("SetRunCase PL:", sm.Analyze.SetRunCaseFlag("PL", True))
print("RunAnalysis:", sm.Analyze.RunAnalysis())

print("=== Internos viga (FrameForce All,2) ===")
ff = sm.Results.FrameForce("All", 2)
if ff[0]:
    M3 = max(abs(v) for v in ff[12]); V2 = max(abs(v) for v in ff[8])
    print(f"  M3_max={M3:.5g} kN.m  V2_max={V2:.5g} kN  (esperado M=P*L={P*L}, V=P={P})")

sm.Results.Setup.DeselectAllCasesAndCombosForOutput()
print("  SetCaseSel PL:", sm.Results.Setup.SetCaseSelectedForOutput("PL"))
br = sm.Results.BaseReact()
if br and br[0]:
    print(f"=== BaseReact PL: Fz={br[6][0]:.5g} (esperado +{P}) My={br[8][0]:.5g} ===")
else:
    print("=== BaseReact vacio:", br[0] if br else None, "===")
print("=== Desplazamiento n2 (referencia ETABS) ===")
r = sm.Results.JointDispl("n2", 0)
for i in range(r[0]):
    print(f"  n2 case={r[3][i]}: Uz={r[8][i]:.6g}  Ry={r[10][i]:.6g}")
print(f"  Uz2 teorico = {-P*L**3/(3*E*Ireal):.6g} m")

try: et.ApplicationExit(False)
except Exception: pass

print("\n=== Copiando fileset .Y_ ===")
cands = sorted(glob.glob(os.path.join(OUTDIR, "*.Y_")) +
               glob.glob(os.path.join(os.environ["LOCALAPPDATA"], "Temp", "cant*.Y_")),
               key=lambda p: os.path.getmtime(p), reverse=True)
if cands:
    src = cands[0]; sbase = os.path.splitext(src)[0]
    dst = os.path.join(OUTDIR, "solved"); shutil.rmtree(dst, ignore_errors=True); os.makedirs(dst)
    for f in glob.glob(sbase + ".*"):
        shutil.copy(f, dst)
    print("  ->", dst, "base:", os.path.basename(sbase))
