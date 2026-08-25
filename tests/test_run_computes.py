import os, clr, sys
sys.stdout.reconfigure(encoding="utf-8")
ENGINE = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
MODEL  = sys.argv[1]
os.add_dll_directory(ENGINE)
clr.AddReference(os.path.join(ENGINE, 'CSI.SAPFire.Common.dll'))
clr.AddReference(os.path.join(ENGINE, 'CSI.SAPFire.dll'))
import CSI.SAPFire as SF
cs = SF.cServer; cs.ProgramLabel = "SAPFire"; cs.ProgramLevel = cs.eProgramLevel.Advanced
cs.ProgramType = cs.eProgramType.Etabs; cs.IsProgramForRelease = False
cs.OutFileName = os.path.join(os.path.dirname(MODEL), "srv.txt")
am = cs.CreateAnalysisModel(); am.FileName = MODEL; am.ReadSelf()
am.SetSchedulerSerial().CanLogRunTime = False
am.TypeMode = am.eTypeMode.Auto; am.TypeProcess = am.eTypeProcess.GUI; am.TypeThread = am.eTypeThread.GUI
am.RunningInSeparateProcess = False; am.SaveAfterRun = False


class Cb(SF.ICallback):
    __namespace__ = "T"
    def AdviseBegin(s, t): pass
    def AdviseFinalize(s, t, k): print("   [Run] kComplete=", k)
    def AdviseUpdateMax(s, t, m): pass
    def AdviseUpdateAndCheckCancel(s, t, c, m, km, kc):
        if m and km and km >= 2: print("   [solver]", m)
        return False
    def AdvisePostMessage(s, t, m, km):
        if m and km and km >= 2: print("   [solver]", m)
    def AdviseEnd(s, t, k, m, km): pass
    def AdviseCheckCancel(s, t, kc): return False
    def HandleError(s, t, m, km): print("   [err]", m)


am.RegisterIntraProcessCallback(Cb())
job = am.Job


def status(tag):
    st = job.CaseGetStatus(-1, 0, 0, 0)   # DEAD jcase=-1
    print(f"  estado DEAD {tag}: kStatus={st[-3]} (10002=NotRun, 10005=Complete)")


status("inicial (post ReadSelf)")
try:
    job.CaseDeleteAllResults()
    print("  CaseDeleteAllResults() OK")
except Exception as e:
    print("  CaseDeleteAllResults err:", str(e)[:100])
status("tras CaseDeleteAllResults")
try:
    job.CaseSetAllToRun()
    print("  CaseSetAllToRun() OK")
except Exception as e:
    print("  CaseSetAllToRun err:", str(e)[:100])
print(">>> Run() ...")
am.Run()
status("tras Run()")

# leer DEAD para ver si recomputo
import System
from System import Array, Int32, Double
KT = SF.cConstant.TypeRequestStep
NJ = am.NumNode
ai = lambda n: Array[Int32]([0]*(n+2)); ad = lambda n: Array[Double]([0.0]*(n+2))
NR = NJ*6+16
rRes=ad(NR); kResp=ai(8); jElem=ai(NJ+2); rAng=ad(NR)
i2=ai(4); kT=ai(4); jC=ai(4); j1=ai(4); j2=ai(4); rP=ad(4)
kTc=ai(4); i2c=ai(4); kCc=ai(4); jCc=ai(4); j1c=ai(4); j2c=ai(4); rMc=ad(4)
for k in range(1,7): kResp[k]=10+k
for e in range(1,NJ+1): jElem[e]=e
i2[1]=1; kT[1]=KT; jC[1]=-1; j1[1]=1; j2[1]=1
try:
    r=job.JointResponse(rRes,kResp,jElem,rAng,i2,kT,jC,j1,j2,rP,kTc,i2c,kCc,jCc,j1c,j2c,rMc,6,NJ,NJ,1,0,0,0)
    nResp,nResult,nElem=r[0],r[1],r[2]
    print(f"  DEAD leido: nResult={nResult}")
    for e in range(nElem):
        u=[rRes[1+e*nResp+c] for c in range(6)]
        print(f"     joint {jElem[1+e]}: {['%.6g'%v for v in u]}")
except Exception as e:
    print("  lectura err:", str(e)[:120])
