r"""EL ENGAÑO: hosteo yo el callback service WCF (vía StartCallbackService por reflexion),
lanzo el Driver apuntando a ESE pipe, el Driver computa creyendo que soy ETABS. Sin etabs.exe.
"""
import os, clr, sys, subprocess
sys.stdout.reconfigure(encoding="utf-8")
ENGINE = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
MODEL = sys.argv[1]
DRIVER = os.path.join(ENGINE, "CSI.SAPFire.Driver.exe")
os.add_dll_directory(ENGINE)
clr.AddReference(os.path.join(ENGINE, 'CSI.SAPFire.Common.dll'))
clr.AddReference(os.path.join(ENGINE, 'CSI.SAPFire.dll'))
import CSI.SAPFire as SF
import System
from System.Reflection import BindingFlags

cs = SF.cServer
cs.ProgramLabel = "ETABS Ultimate 64-bit 19.1.0 Build 2420"
cs.ProgramLevel = cs.eProgramLevel.Advanced
cs.ProgramType = cs.eProgramType.Etabs
cs.IsProgramForRelease = True
cs.OutFileName = os.path.join(os.path.dirname(MODEL), "out.txt")
cs.ExePathx64 = DRIVER; cs.ExePathx32 = DRIVER

am = cs.CreateAnalysisModel(); am.FileName = MODEL; am.ReadSelf()
job = am.Job
print("estado DEAD inicial:", job.CaseGetStatus(-1, 0, 0, 0)[-3])
job.CaseDeleteAllResults(); job.CaseSetAllToRun()
print("estado DEAD tras delete:", job.CaseGetStatus(-1, 0, 0, 0)[-3])
am.WriteSelf()


class Cb(SF.ICallback):
    __namespace__ = "Pipe"
    def AdviseBegin(s, t): print("   [pipe-cb] Begin", t)
    def AdviseFinalize(s, t, k): print("   [pipe-cb] Finalize k=", k)
    def AdviseUpdateMax(s, t, m): pass
    def AdviseUpdateAndCheckCancel(s, t, c, m, km, kc):
        if m and km and km >= 1: print("   [pipe-cb]", m)
        return False
    def AdvisePostMessage(s, t, m, km):
        if m and km and km >= 1: print("   [pipe-cb]", m)
    def AdviseEnd(s, t, k, m, km):
        if m: print("   [pipe-cb] END:", m)
    def AdviseCheckCancel(s, t, kc): return False
    def HandleError(s, t, m, km): print("   [pipe-cb] ERR:", m)


sched = am.SetSchedulerSerial()
cb = Cb()
# invocar StartCallbackService(int nRun, ICallback) por reflexion (protected)
mi = sched.GetType().GetMethod("StartCallbackService",
        BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Instance)
print("StartCallbackService method:", mi)
guid = mi.Invoke(sched, System.Array[System.Object]([System.Int32(1), cb]))
print("PIPE GUID hosteado =", guid)

# lanzar el Driver apuntando a NUESTRO pipe
args = [DRIVER, "0", cs.OutFileName, os.path.abspath(MODEL),
        cs.ProgramLabel, str(guid), "4", "7", "True"]
print(">>> lanzando Driver con nuestro pipe ...")
r = subprocess.run(args, cwd=ENGINE, capture_output=True, text=True)
print(r.stdout[:500])
if r.stderr.strip(): print("STDERR:", r.stderr[:300])

# detener servicio + releer estado/resultados
try:
    ms = sched.GetType().GetMethod("StopCallbackService", BindingFlags.NonPublic | BindingFlags.Instance)
    ms.Invoke(sched, None)
except Exception as e:
    print("stop err:", str(e)[:80])
am.ClearSelf(); am.FileName = MODEL; am.ReadSelf()
print("estado DEAD tras Driver:", job.CaseGetStatus(-1, 0, 0, 0)[-3], "(10005=Complete=COMPUTO!)")
