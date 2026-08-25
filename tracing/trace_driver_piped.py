#!/usr/bin/env python3
r"""Hostea el callback service (como ETABS) + frida-spawn del Driver con el GUID real, sobre un modelo
COMPLETO reseteado a NotRun, y traza las llamadas a CsiGo2 del Driver para ver DONDE aborta el run con pipe."""
import os, sys, time, clr, threading, frida
sys.stdout.reconfigure(encoding="utf-8")
ENG = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
DRV = os.path.join(ENG, "CSI.SAPFire.Driver.exe")
MODEL = os.path.abspath(sys.argv[1] if len(sys.argv)>1 else r"coldtest_pipe\voladizo_cli.Y_")
OUT = os.path.join(os.path.dirname(MODEL), "drvpipe_out.txt")
os.add_dll_directory(ENG)
clr.AddReference(os.path.join(ENG,'CSI.SAPFire.Common.dll')); clr.AddReference(os.path.join(ENG,'CSI.SAPFire.dll'))
import CSI.SAPFire as SF, System
from System.Reflection import BindingFlags
LABEL = "ETABS Ultimate 64-bit 19.1.0 Build 2420"
cs=SF.cServer; cs.ProgramLabel=LABEL; cs.ProgramLevel=cs.eProgramLevel.Advanced
cs.ProgramType=cs.eProgramType.Etabs; cs.IsProgramForRelease=True
cs.OutFileName=OUT; cs.ExePathx64=DRV; cs.ExePathx32=DRV
am=cs.CreateAnalysisModel(); am.FileName=MODEL; am.ReadSelf()
job=am.Job
print("estado inicial:", job.CaseGetStatus(-1,0,0,0)[-3])
job.CaseDeleteAllResults(); job.CaseSetAllToRun(); am.WriteSelf()
print("estado tras reset:", job.CaseGetStatus(-1,0,0,0)[-3])
class Cb(SF.ICallback):
    __namespace__="TP"
    def AdviseBegin(s,t): print("   [cb] Begin",t)
    def AdviseFinalize(s,t,k): print("   [cb] Finalize k=",k)
    def AdviseUpdateMax(s,t,m): pass
    def AdviseUpdateAndCheckCancel(s,t,c,m,km,kc):
        if m and km and km>=1: print("   [cb]",m)
        return False
    def AdvisePostMessage(s,t,m,km):
        if m and km and km>=1: print("   [cb]",m)
    def AdviseEnd(s,t,k,m,km):
        if m: print("   [cb] END:",m)
    def AdviseCheckCancel(s,t,kc): return False
    def HandleError(s,t,m,km): print("   [cb] ERR:",m)
sched=am.SetSchedulerSerial()
mi=sched.GetType().GetMethod("StartCallbackService", BindingFlags.NonPublic|BindingFlags.Public|BindingFlags.Instance)
guid=mi.Invoke(sched, System.Array[System.Object]([System.Int32(1), Cb()]))
print("PIPE GUID =", guid)
ARGV=[DRV,"0",OUT,MODEL,LABEL,str(guid),"4","7","True"]
JS=r"""
'use strict';
var tries=0, iv=setInterval(function(){
  tries++; var m=Process.findModuleByName('CsiGo2.dll');
  if(m){ clearInterval(iv); var n=0;
    m.enumerateExports().forEach(function(e){ if(e.type!=='function')return;
      try{Interceptor.attach(e.address,{onEnter:function(){ send({t:'c',fn:e.name}); }}); n++;}catch(x){} });
    send({t:'log',m:'hooked '+n+' exports'});
  } else if(tries>400){clearInterval(iv); send({t:'log',m:'no CsiGo2'});}
},5);
"""
dev=frida.get_local_device(); pid=dev.spawn(ARGV,cwd=ENG); ses=dev.attach(pid); scr=ses.create_script(JS)
seq=[]
def onm(m,d):
    if m.get("type")=="send":
        p=m["payload"]
        if p.get("t")=="c": seq.append(p["fn"])
        elif p.get("t")=="log": print("  [js]",p["m"])
scr.on("message",onm); scr.load(); dev.resume(pid); time.sleep(6)
try: ses.detach()
except: pass
# dedup consecutivos, mostrar secuencia
print(f"\n=== llamadas CsiGo2 del Driver CON pipe ({len(seq)}) ===")
last=None; 
for s in seq:
    if s!=last: print("  ",s); last=s
