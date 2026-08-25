r"""ReadSelf + CaseDeleteAllResults + WriteSelf -> deja el .Y_ en estado NotRun (sin resultados)
para probar si el Driver.exe REAL lo computa desde cero."""
import os, clr, sys, glob
sys.stdout.reconfigure(encoding="utf-8")
ENGINE = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
MODEL = sys.argv[1]
os.add_dll_directory(ENGINE)
clr.AddReference(os.path.join(ENGINE, 'CSI.SAPFire.Common.dll'))
clr.AddReference(os.path.join(ENGINE, 'CSI.SAPFire.dll'))
import CSI.SAPFire as SF
cs = SF.cServer; cs.ProgramLabel = "SAPFire"; cs.ProgramLevel = cs.eProgramLevel.Advanced
cs.ProgramType = cs.eProgramType.Etabs; cs.IsProgramForRelease = False
cs.OutFileName = os.path.join(os.path.dirname(MODEL), "srv.txt")
am = cs.CreateAnalysisModel(); am.FileName = MODEL; am.ReadSelf()
job = am.Job
print("estado DEAD pre:", job.CaseGetStatus(-1, 0, 0, 0)[-3])
job.CaseDeleteAllResults()
job.CaseSetAllToRun()
print("estado DEAD tras delete:", job.CaseGetStatus(-1, 0, 0, 0)[-3])
am.SaveAfterRun = False
sz_pre = os.path.getsize(MODEL)
am.WriteSelf()
print("WriteSelf OK")
base = os.path.splitext(MODEL)[0]
print("fileset tras WriteSelf:")
for f in sorted(glob.glob(base + ".*")):
    print(f"   {os.path.basename(f):22s} {os.path.getsize(f):>10d}")
