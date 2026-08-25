r"""Forzar cómputo cold replicando la vía oficial: el scheduler lanza CSI.SAPFire.Driver.exe.
TypeProcess=Analysis + cServer.ExePathx64=Driver -> Run() spawnea el Driver que computa.
Borra resultados (CaseDeleteAllResults) para forzar recálculo real y luego lee DEAD."""
import os, clr, sys
sys.stdout.reconfigure(encoding="utf-8")
ENGINE = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
MODEL = sys.argv[1]
DRIVER = os.path.join(ENGINE, "CSI.SAPFire.Driver.exe")
os.add_dll_directory(ENGINE)
clr.AddReference(os.path.join(ENGINE, 'CSI.SAPFire.Common.dll'))
clr.AddReference(os.path.join(ENGINE, 'CSI.SAPFire.dll'))
import CSI.SAPFire as SF
import System
from System import Array, Int32, Double

cs = SF.cServer
cs.ProgramLabel = "SAPFire"; cs.ProgramLevel = cs.eProgramLevel.Advanced
cs.ProgramType = cs.eProgramType.Etabs; cs.IsProgramForRelease = False
cs.OutFileName = os.path.join(os.path.dirname(MODEL), "srv.txt")
cs.ExePathx64 = DRIVER; cs.ExePathx32 = DRIVER       # <-- el scheduler spawnea ESTO
print("ExePathx64 =", cs.ExePathx64, "existe:", os.path.exists(DRIVER))

am = cs.CreateAnalysisModel(); am.FileName = MODEL; am.ReadSelf()
print("ReadSelf OK NumNode=%d" % am.NumNode)
am.SetSchedulerSerial().CanLogRunTime = False
am.TypeMode = am.eTypeMode.Auto
am.TypeProcess = am.eTypeProcess.Analysis    # <-- Analysis = spawnea el Driver (no in-process)
am.TypeThread = am.eTypeThread.GUI
am.SaveAfterRun = True


class Cb(SF.ICallback):
    __namespace__ = "Sp"
    def AdviseBegin(s, t): print("   [cb] Begin")
    def AdviseFinalize(s, t, k): print("   [cb] Finalize k=", k)
    def AdviseUpdateMax(s, t, m): pass
    def AdviseUpdateAndCheckCancel(s, t, c, m, km, kc):
        if m and km and km >= 1: print("   [cb]", m)
        return False
    def AdvisePostMessage(s, t, m, km):
        if m and km and km >= 1: print("   [cb]", m)
    def AdviseEnd(s, t, k, m, km):
        if m: print("   [cb] END:", m)
    def AdviseCheckCancel(s, t, kc): return False
    def HandleError(s, t, m, km): print("   [cb] ERR:", m)


am.RegisterIntraProcessCallback(Cb())
job = am.Job


def status(tag):
    st = job.CaseGetStatus(-1, 0, 0, 0)
    print(f"  estado DEAD {tag}: kStatus={st[-3]} (10002=NotRun 10005=Complete)")


status("inicial")
job.CaseDeleteAllResults(); print("CaseDeleteAllResults OK")
status("tras delete")
job.CaseSetAllToRun()
# forzar TypeProcess=Analysis tambien en el scheduler directo + leer back
sched = am.SetSchedulerSerial()
am.TypeProcess = am.eTypeProcess.Analysis
am.TypeThread = am.eTypeThread.Analysis
am.TypeMode = am.eTypeMode.x64bit
print("  am.TypeProcess =", am.TypeProcess, " sched.TypeProcess =", sched.TypeProcess)
print("  cServer.ExePathx64 =", cs.ExePathx64)
print(">>> Run() (debe spawnear Driver) ...")
am.Run()
status("tras Run")

KT = SF.cConstant.TypeRequestStep
NJ = am.NumNode
ai = lambda n: Array[Int32]([0]*(n+2)); ad = lambda n: Array[Double]([0.0]*(n+2))
NR = NJ*6+16
rRes = ad(NR); kResp = ai(8); jElem = ai(NJ+2); rAng = ad(NR)
i2 = ai(4); kT = ai(4); jC = ai(4); j1 = ai(4); j2 = ai(4); rP = ad(4)
kTc = ai(4); i2c = ai(4); kCc = ai(4); jCc = ai(4); j1c = ai(4); j2c = ai(4); rMc = ad(4)
for k in range(1, 7): kResp[k] = 10+k
for e in range(1, NJ+1): jElem[e] = e
i2[1] = 1; kT[1] = KT; jC[1] = -1; j1[1] = 1; j2[1] = 1
try:
    r = job.JointResponse(rRes, kResp, jElem, rAng, i2, kT, jC, j1, j2, rP, kTc, i2c, kCc, jCc, j1c, j2c, rMc, 6, NJ, NJ, 1, 0, 0, 0)
    print(f"  DEAD nResult={r[1]}")
    for e in range(r[2]):
        u = [rRes[1+e*r[0]+c] for c in range(6)]
        print(f"     joint {jElem[1+e]}: {['%.6g'%v for v in u]}")
except Exception as e:
    print("  lectura err:", str(e)[:120])
