import os, clr, sys
sys.stdout.reconfigure(encoding="utf-8")
ENGINE = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
MODEL = sys.argv[1]
os.add_dll_directory(ENGINE)
clr.AddReference(os.path.join(ENGINE,'CSI.SAPFire.Common.dll')); clr.AddReference(os.path.join(ENGINE,'CSI.SAPFire.dll'))
import CSI.SAPFire as SF
from System.Reflection import BindingFlags
import System
cs=SF.cServer; cs.ProgramLabel="ETABS Ultimate 64-bit 19.1.0 Build 2420"; cs.ProgramLevel=cs.eProgramLevel.Advanced
cs.ProgramType=cs.eProgramType.Etabs; cs.IsProgramForRelease=True
cs.OutFileName=os.path.join(os.path.dirname(MODEL),"o.txt")
am=cs.CreateAnalysisModel(); am.FileName=MODEL; am.ReadSelf()
am.SetSchedulerSerial().CanLogRunTime=False
am.TypeProcess=am.eTypeProcess.GUI; am.TypeThread=am.eTypeThread.GUI; am.TypeMode=am.eTypeMode.Auto
job=am.Job
print("DEAD pre:", job.CaseGetStatus(-1,0,0,0)[-3])
job.CaseDeleteAllResults(); job.CaseSetAllToRun()
print("DEAD tras delete:", job.CaseGetStatus(-1,0,0,0)[-3])
# 1) CaseSerialRunGet directo
try:
    r=job.CaseSerialRunGet(0); print("CaseSerialRunGet ->", r)
except Exception as e: print("SerialRunGet err:", str(e)[:100])
print("DEAD tras SerialRunGet:", job.CaseGetStatus(-1,0,0,0)[-3])
# 2) am.e() por reflexion (solve in-process ofuscado)
try:
    mi=am.GetType().GetMethod("e", BindingFlags.NonPublic|BindingFlags.Public|BindingFlags.Instance)
    print("metodo e():", mi)
    if mi: mi.Invoke(am, None); print("e() invocado")
except Exception as e: print("e() err:", str(e)[:120])
print("DEAD tras e():", job.CaseGetStatus(-1,0,0,0)[-3], "(10005=COMPUTO)")
