import os,clr,ctypes,sys,functools
sys.stdout.reconfigure(encoding="utf-8"); print=functools.partial(print,flush=True)
E=r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
MODEL=sys.argv[1]
os.add_dll_directory(E);clr.AddReference(os.path.join(E,'CSI.SAPFire.Common.dll'));clr.AddReference(os.path.join(E,'CSI.SAPFire.dll'))
import CSI.SAPFire as SF
from System.Diagnostics import Process
cs=SF.cServer;cs.ProgramLabel="ETABS Ultimate 64-bit 19.1.0 Build 2420";cs.ProgramLevel=cs.eProgramLevel.Advanced
cs.ProgramType=cs.eProgramType.Etabs;cs.IsProgramForRelease=True
cs.OutFileName=os.path.join(os.path.dirname(MODEL),"o.txt")
am=cs.CreateAnalysisModel();am.FileName=MODEL;am.ReadSelf()
am.SetSchedulerSerial().CanLogRunTime=False
am.TypeProcess=am.eTypeProcess.GUI;am.TypeThread=am.eTypeThread.GUI;am.TypeMode=am.eTypeMode.Auto;am.SaveAfterRun=False
job=am.Job; job.CaseGetStatus(-1,0,0,0)
for m in Process.GetCurrentProcess().Modules:
    if m.ModuleName.lower().startswith("csigo2"): base=m.BaseAddress.ToInt64();break
k32=ctypes.windll.kernel32
def patch(rva,bs):
    a=base+rva; old=ctypes.c_ulong()
    k32.VirtualProtect(ctypes.c_void_p(a),ctypes.c_size_t(len(bs)),0x40,ctypes.byref(old))
    for i,b in enumerate(bs): (ctypes.c_ubyte).from_address(a+i).value=b
# 1) GATE 0x156e00 -> return 0 SIEMPRE: xor eax,eax ; ret  (en el inicio mismo)
print("gate inicio ANTES:", bytes((ctypes.c_ubyte*4).from_address(base+0x156e00)).hex(' '))
patch(0x156e00,[0x31,0xC0,0xC3])  # xor eax,eax; ret  AL INICIO de la funcion
print("gate inicio DESPUES:", bytes((ctypes.c_ubyte*4).from_address(base+0x156e00)).hex(' '))
# 2) ALSO set global @0x258ca68 = 99 (por si la lee otra ruta)
ga=base+0x258ca68; old=ctypes.c_ulong()
k32.VirtualProtect(ctypes.c_void_p(ga),ctypes.c_size_t(4),0x40,ctypes.byref(old))
print("global@0x258ca68 ANTES=",ctypes.c_int32.from_address(ga).value)
ctypes.c_int32.from_address(ga).value=99
print("global DESPUES=",ctypes.c_int32.from_address(ga).value)

print("IsSetToRun DEAD pre:",job.CaseIsSetToRun(-1)[0])
job.CaseDeleteAllResults()
for jc in (-1,-2,-4):
    try: job.CaseSetToRun(jc); print(f"  CaseSetToRun({jc}) OK")
    except Exception as e: print(f"  CaseSetToRun({jc}) EXC:",str(e)[:70])
print("IsSetToRun DEAD tras CaseSetToRun:",job.CaseIsSetToRun(-1)[0])
print(">>> Run() ...")
am.Run()
print("estado DEAD tras Run:",job.CaseGetStatus(-1,0,0,0)[-3],"(10005=COMPUTO!!)")
