#!/usr/bin/env python3
r"""Harness MINIMO para Pin/DrillTrace: solo ReadSelf + Run() (forma la K de elementos),
luego sale LIMPIO con os._exit(0) para no tocar la fase de lectura que crashea.
Asi Pin ejecuta Fini y flushea el CSV de DrillTrace.
Uso: cold_kform_min.py <modelo.Y_>
"""
import os, sys, clr
sys.stdout.reconfigure(encoding="utf-8")

MODEL = os.path.abspath(sys.argv[1])
WORKDIR = os.path.dirname(MODEL)
ENGINE = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"

os.add_dll_directory(ENGINE)
clr.AddReference(os.path.join(ENGINE, "CSI.SAPFire.Common.dll"))
clr.AddReference(os.path.join(ENGINE, "CSI.SAPFire.dll"))
import CSI.SAPFire as SF


class Cb(SF.ICallback):
    __namespace__ = "ColdKform"
    def AdviseBegin(self, t): pass
    def AdviseFinalize(self, t, k): print(f"  [cb] Finalize kComplete={k}")
    def AdviseUpdateMax(self, t, m): pass
    def AdviseUpdateAndCheckCancel(self, t, c, msg, km, kc):
        if msg and km and km >= 1: print("  [cb]", msg)
        return False
    def AdvisePostMessage(self, t, msg, km):
        if msg and km and km >= 1: print("  [cb]", msg)
    def AdviseEnd(self, t, k, msg, km):
        if msg: print("  [cb] END:", msg)
    def AdviseCheckCancel(self, t, kc): return False
    def HandleError(self, t, msg, km): print("  [cb] ERROR:", msg)


cs = SF.cServer
cs.ProgramLabel = "SAPFire"
cs.ProgramLevel = cs.eProgramLevel.Advanced
cs.ProgramType = cs.eProgramType.Etabs
cs.IsProgramForRelease = False
cs.OutFileName = os.path.join(WORKDIR, "coldkform_server.txt")

am = cs.CreateAnalysisModel()
am.FileName = MODEL
print(">>> ReadSelf()", MODEL)
am.ReadSelf()
print(f"    OK  NumNode={am.NumNode} NumFrame={am.NumFrame} NumJoint={am.NumJoint}")

am.SetSchedulerSerial().CanLogRunTime = False
am.TypeMode = am.eTypeMode.Auto
am.TypeProcess = am.eTypeProcess.GUI
am.TypeThread = am.eTypeThread.GUI
am.RunningInSeparateProcess = False
am.SaveAfterRun = False
am.RegisterIntraProcessCallback(Cb())

job = am.Job
try:
    job.CaseSetAllToNotRun(); print(">>> CaseSetAllToNotRun OK")
except Exception as e:
    print(">>> CaseSetAllToNotRun err:", str(e)[:120])
try:
    job.CaseSetAllToRun()
except Exception as e:
    print(">>> CaseSetAllToRun err:", str(e)[:120])
print(">>> Run() in-process (forma K) ...")
am.Run()
print("    Job.Response ->", job.Response(0, 0, 0))
print(">>> salida limpia os._exit(0)")
sys.stdout.flush()
os._exit(0)
