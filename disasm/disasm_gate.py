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
for m in Process.GetCurrentProcess().Modules:
    if m.ModuleName.lower().startswith("csigo2"): base=m.BaseAddress.ToInt64();size=m.ModuleMemorySize;break
data=bytes((ctypes.c_ubyte*size).from_address(base))
HIT=0x156e11
# buscar inicio de funcion: hacia atras hasta padding cc cc o int3
start=HIT
for k in range(HIT, HIT-400, -1):
    if data[k-2:k]==b"\xcc\xcc" or data[k-1:k]==b"\xcc":
        start=k; break
print("funcion gate: inicio~RVA 0x%x  (hit cmp99 @0x%x)"%(start,HIT))
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
for ins in md.disasm(data[start:HIT+30], base+start):
    rva=ins.address-base
    mark=" <== cmp 99" if rva==HIT else ""
    print("  0x%06x: %-22s %s%s"%(rva," ".join("%02x"%b for b in ins.bytes), ins.mnemonic+" "+ins.op_str, mark))
