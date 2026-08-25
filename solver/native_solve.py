#!/usr/bin/env python3
r"""SAPFire cold (sin etabs.exe): init servidor (cQuickAnalysis) + build + caso + run + lectura U.
Voladizo: nodo1 empotrado, nodo2 a 4m con Fz=-10."""
import os, sys, clr
sys.stdout.reconfigure(encoding='utf-8')
d = r"C:/Users/j-b-j/Documents/Hekatan Calc 1.0.0/hekatan-etabs-bridge/engine_etabs19"
os.add_dll_directory(d); os.chdir(d)
clr.AddReference(os.path.join(d, 'CSI.SAPFire.dll'))
import CSI.SAPFire as SF
import System

cs = SF.cServer
cs.ProgramType = cs.eProgramType.Etabs
cs.ExePathx32 = os.path.join(d, cs.ExeName)
cs.ExePathx64 = os.path.join(d, cs.ExeName)
cs.ProgramLabel = 'SAPFire'
cs.ProgramLevel = cs.eProgramLevel.Advanced
cs.OutFileName = os.path.join(d, 'CSIout.txt')
cs.IsInitialized = True

am = cs.CreateAnalysisModel()
am.VersionGUIGo = 8470
am.TypeOptimization = am.eTypeOptimization.All
am.TypeSolver = am.eTypeSolver.ParallelOnly
am.TypeProcess = am.eTypeProcess.GUI
am.TypeThread = am.eTypeThread.GUI
am.SaveAfterRun = False
am.FilesInCore = True
am.FileName = os.path.join(d, 'tmp.Y_')
am.ForceToKN = 1.0; am.LengthToM = 1.0; am.TemperatureToC = 1.0

n1 = am.AddNode(1); n1.set_Coord(1,0.0); n1.set_Coord(2,0.0); n1.set_Coord(3,0.0)
n2 = am.AddNode(2); n2.set_Coord(1,4.0); n2.set_Coord(2,0.0); n2.set_Coord(3,0.0)
m = am.AddPropMaterial(1); r = m.AddRecPropMatElastic()
r.YoungsModulus = 2.1e8; r.PoissonRatio = 0.3; r.ShearModulus = 2.1e8/2.6
s = am.AddPropFramePrism(1); s.TagPropMaterial = 1
for i, v in enumerate([0.15, 0.125, 0.125, 0.0025, 0.001125, 0.003125], 1): s.set_Property(i, v)
fr = am.AddFrame(1); fr.set_TagNode(1, 1); fr.set_TagNode(2, 2); fr.TagPropFrame = 1
j1 = am.AddJoint(1); j1.set_TagNode(1, 1); j1.IsRestrained = True
am.AddLoadPatternStruct(1)
j2 = am.AddJoint(2); j2.set_TagNode(1, 2); el = j2.AddElemloadStructForce(); el.Value = -10.0
print("modelo: NumNode=%d NumFrame=%d" % (am.NumNode, am.NumFrame))

# ---- FORMAR/REGISTRAR el modelo (lo que faltaba: WriteSelf, no Refresh) ----
try:
    am.WriteSelf()
    print("WriteSelf() OK -> modelo formado/registrado")
except Exception as e:
    print("WriteSelf err:", str(e)[:120])

job = am.Job
job.CaseInit()
print("CaseLoadSet ->", job.CaseLoadSet(1))
rs = job.CaseStaticLin("LIVE", "", 0, 0)
jcase = rs[-1]
print("CaseStaticLin -> jcase =", jcase, " full:", rs)
ra = job.CaseLoadAss01(jcase, 1, 101, 1, 0, 0, 0, 0, False, 1.0, 0.0, 1.0, 0.0, 0.0, 100.0)
print("CaseLoadAss01 ok")
job.CaseSetAllToRun()
print(">>> Run() ...")
am.Run()
print("Job.Response =", job.Response(0, 0, 0))

NJ = am.NumNode
ai = lambda n: System.Array[System.Int32]([0]*(n+2))
ad = lambda n: System.Array[System.Double]([0.0]*(n+2))
NR = NJ*6 + 8
rResult = ad(NR*2); kResp = ai(8); jElem = ai(NJ+2); rAngle = ad(NR*2)
i2Req = ai(8); kTypeReq = ai(8); jCaseReq = ai(8); j1Req = ai(8); j2Req = ai(8); rPhase = ad(8)
kTypeC = ai(8); i2C = ai(8); kCaseC = ai(8); jCaseC = ai(8); j1C = ai(8); j2C = ai(8); rMultC = ad(8)
for k in range(1, 7): kResp[k] = k
for e in range(1, NJ+1): jElem[e] = e
i2Req[1] = 1; kTypeReq[1] = 1; jCaseReq[1] = jcase; j1Req[1] = 1; j2Req[1] = 1
try:
    ret = job.JointResponse(rResult, kResp, jElem, rAngle, i2Req, kTypeReq, jCaseReq, j1Req, j2Req, rPhase,
                            kTypeC, i2C, kCaseC, jCaseC, j1C, j2C, rMultC, 6, NJ, NJ, 1, 0, 0, 0)
    nResp, nResult, nElem = ret[0], ret[1], ret[2]
    print("JointResponse: nResp=%s nResult=%s nElem=%s" % (nResp, nResult, nElem))
    for e in range(nElem):
        u = [rResult[1 + e*nResp + c] for c in range(min(6, nResp))]
        print("   joint %s: U =" % jElem[1+e], ["%.6g" % v for v in u])
    print("   Uz2 analitico voladizo =", -10.0*4.0**3/(3*2.1e8*0.003125))
except Exception as e:
    print("lectura U err:", str(e)[:200])
