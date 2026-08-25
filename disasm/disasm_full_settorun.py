import os,clr,ctypes,sys,functools
sys.stdout.reconfigure(encoding="utf-8"); print=functools.partial(print,flush=True)
import capstone
E=r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
os.add_dll_directory(E);clr.AddReference(os.path.join(E,'CSI.SAPFire.Common.dll'));clr.AddReference(os.path.join(E,'CSI.SAPFire.dll'))
import CSI.SAPFire as SF
cs=SF.cServer;cs.ProgramLabel="x";cs.ProgramLevel=cs.eProgramLevel.Advanced;cs.ProgramType=cs.eProgramType.Etabs
cs.OutFileName=os.path.join(os.path.dirname(sys.argv[1]),"o.txt")
am=cs.CreateAnalysisModel();am.FileName=sys.argv[1];am.ReadSelf();am.Job.CaseGetStatus(-1,0,0,0)
from System.Diagnostics import Process
k32=ctypes.windll.kernel32
k32.GetProcAddress.restype=ctypes.c_void_p;k32.GetProcAddress.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
k32.GetModuleHandleW.restype=ctypes.c_void_p;k32.GetModuleHandleW.argtypes=[ctypes.c_wchar_p]
for m in Process.GetCurrentProcess().Modules:
    if m.ModuleName.lower().startswith("csigo2"): base=m.BaseAddress.ToInt64();size=m.ModuleMemorySize;break
data=bytes((ctypes.c_ubyte*size).from_address(base))
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
hmod=k32.GetModuleHandleW("CsiGo2.dll")
va=k32.GetProcAddress(ctypes.c_void_p(hmod),b"Go_JobCaseSetToRun")
off=va-base
print("Go_JobCaseSetToRun RVA=0x%x — disasm COMPLETO (sin cortar en ret) ==="%off)
n=0
for ins in md.disasm(data[off:off+500],va):
    rva=ins.address-base
    tag=""
    if ins.mnemonic=='call' and ins.op_str.startswith('0x'): tag=" *CALL*"
    if ins.mnemonic in ('cmp','test') : tag=" <"
    print("  0x%06x: %-22s %s%s"%(rva," ".join("%02x"%b for b in ins.bytes),ins.mnemonic+" "+ins.op_str,tag))
    n+=1
    if n>110: break
