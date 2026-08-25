import os,clr,sys
sys.stdout.reconfigure(encoding="utf-8")
E=r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
os.add_dll_directory(E);clr.AddReference(os.path.join(E,'CSI.SAPFire.Common.dll'));clr.AddReference(os.path.join(E,'CSI.SAPFire.dll'))
import CSI.SAPFire as SF
cs=SF.cServer;cs.ProgramLabel="ETABS Ultimate 64-bit 19.1.0 Build 2420";cs.ProgramLevel=cs.eProgramLevel.Advanced
cs.ProgramType=cs.eProgramType.Etabs;cs.IsProgramForRelease=True
cs.OutFileName=os.path.join(os.path.dirname(sys.argv[1]),"o.txt")
am=cs.CreateAnalysisModel();am.FileName=sys.argv[1];am.ReadSelf()
am.SetSchedulerSerial().CanLogRunTime=False
am.TypeProcess=am.eTypeProcess.GUI;am.TypeThread=am.eTypeThread.GUI;am.TypeMode=am.eTypeMode.Auto
am.SaveAfterRun=False
class Cb(SF.ICallback):
    __namespace__="T"
    def AdviseBegin(s,t):pass
    def AdviseFinalize(s,t,k):print("  Run kComplete=",k)
    def AdviseUpdateMax(s,t,m):pass
    def AdviseUpdateAndCheckCancel(s,t,c,m,km,kc):
        if m and km and km>=1:print("  [solver]",m)
        return False
    def AdvisePostMessage(s,t,m,km):
        if m and km and km>=1:print("  [solver]",m)
    def AdviseEnd(s,t,k,m,km):pass
    def AdviseCheckCancel(s,t,kc):return False
    def HandleError(s,t,m,km):print("  ERR:",m)
am.RegisterIntraProcessCallback(Cb())
job=am.Job
print("IsSetToRun DEAD inicial:", job.CaseIsSetToRun(-1)[0])
job.CaseDeleteAllResults()
print("=== CaseSetAllToRun ===")
job.CaseSetAllToRun()
print("IsSetToRun DEAD tras SetAllToRun:", job.CaseIsSetToRun(-1)[0])
# si sigue False, intentar por-caso
if not job.CaseIsSetToRun(-1)[0]:
    print("  -> probando CaseSetToRun por jcase")
    for jc in (-1,-2,-4,-5):
        try: job.CaseSetToRun(jc)
        except Exception as e: print(f"   SetToRun {jc} err:",str(e)[:50])
    print("IsSetToRun DEAD tras CaseSetToRun:", job.CaseIsSetToRun(-1)[0])
print(">>> Run() ...")
am.Run()
print("estado DEAD tras Run:", job.CaseGetStatus(-1,0,0,0)[-3],"(10005=COMPUTO!)")
