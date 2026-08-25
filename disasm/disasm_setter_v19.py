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
settorun=k32.GetProcAddress(ctypes.c_void_p(hmod),b"Go_JobCaseSetToRun")
# leer el rel32 del call setter @ off 0x2202e36 (= settorun_rva + 0x96)
str_off=(settorun-base)+0x96
rel=int.from_bytes(data[str_off+1:str_off+5],'little',signed=True)
setter_rva=(str_off+5)+rel
print("SETTER de v19 @ RVA 0x%x"%setter_rva)
print("=== disasm setter (busca cmp/test/call que gatea el flag) ===")
n=0; gate_calls=[]
for ins in md.disasm(data[setter_rva:setter_rva+700], base+setter_rva):
    rva=ins.address-base; tag=""
    if ins.mnemonic=='call' and ins.op_str.startswith('0x'):
        t=int(ins.op_str,16); gate_calls.append(t-base); tag=" *CALL rva=0x%x*"%(t-base)
    if ins.mnemonic in ('cmp','test'): tag+=" <CMP"
    if ins.mnemonic.startswith('cmov'): tag+=" <CMOV"
    print("  0x%06x: %-20s %s%s"%(rva," ".join("%02x"%b for b in ins.bytes),ins.mnemonic+" "+ins.op_str,tag))
    n+=1
    if n>120 or ins.mnemonic=='ret' and n>40: break
