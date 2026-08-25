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
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64); md.detail=False
def rng(va,n): off=va-base; return data[off:off+n]
def follow_calls(va,maxins=80):
    calls=[]
    for ins in md.disasm(rng(va,maxins*6),va):
        if ins.mnemonic=='call' and ins.op_str.startswith('0x'):
            calls.append(int(ins.op_str,16))
        if ins.mnemonic=='ret': break
    return calls
hmod=k32.GetModuleHandleW("CsiGo2.dll")
settorun=k32.GetProcAddress(ctypes.c_void_p(hmod),b"Go_JobCaseSetToRun")
print("Go_JobCaseSetToRun VA=0x%x RVA=0x%x"%(settorun,settorun-base))
print("=== disasm Go_JobCaseSetToRun ===")
for ins in md.disasm(rng(settorun,300),settorun):
    print("  0x%06x: %-20s %s"%(ins.address-base," ".join("%02x"%b for b in ins.bytes),ins.mnemonic+" "+ins.op_str))
    if ins.mnemonic=='ret': break
print("CALLS:", [hex(c-base) for c in follow_calls(settorun)])
