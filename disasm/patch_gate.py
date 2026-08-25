r"""CRACK del gate v19: en RVA 0x156e11 (cmp eax,0x63 ... ret en 0x156e1f) fuerza eax=0
=> el gate FUN nativo siempre 'desbloquea' => CaseSetToRun marca el flag => Run computa.
Sin etabs.exe. Patch en memoria (VirtualProtect)."""
import os, clr, ctypes, sys, functools
sys.stdout.reconfigure(encoding="utf-8"); print = functools.partial(print, flush=True)
E = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
MODEL = sys.argv[1]
os.add_dll_directory(E)
clr.AddReference(os.path.join(E, 'CSI.SAPFire.Common.dll')); clr.AddReference(os.path.join(E, 'CSI.SAPFire.dll'))
import CSI.SAPFire as SF
import System
from System.Diagnostics import Process

cs = SF.cServer
cs.ProgramLabel = "ETABS Ultimate 64-bit 19.1.0 Build 2420"
cs.ProgramLevel = cs.eProgramLevel.Advanced; cs.ProgramType = cs.eProgramType.Etabs; cs.IsProgramForRelease = True
cs.OutFileName = os.path.join(os.path.dirname(MODEL), "o.txt")
am = cs.CreateAnalysisModel(); am.FileName = MODEL; am.ReadSelf()
am.SetSchedulerSerial().CanLogRunTime = False
am.TypeProcess = am.eTypeProcess.GUI; am.TypeThread = am.eTypeThread.GUI; am.TypeMode = am.eTypeMode.Auto
am.SaveAfterRun = False
job = am.Job


class Cb(SF.ICallback):
    __namespace__ = "P"
    def AdviseBegin(s, t): pass
    def AdviseFinalize(s, t, k): print("  Run kComplete=", k)
    def AdviseUpdateMax(s, t, m): pass
    def AdviseUpdateAndCheckCancel(s, t, c, m, km, kc):
        if m and km and km >= 1: print("  [solver]", m)
        return False
    def AdvisePostMessage(s, t, m, km):
        if m and km and km >= 1: print("  [solver]", m)
    def AdviseEnd(s, t, k, m, km):
        if m: print("  END:", m)
    def AdviseCheckCancel(s, t, kc): return False
    def HandleError(s, t, m, km): print("  ERR:", m)


am.RegisterIntraProcessCallback(Cb())
job.CaseGetStatus(-1, 0, 0, 0)  # fuerza carga CsiGo2

base = None
for m in Process.GetCurrentProcess().Modules:
    if m.ModuleName.lower().startswith("csigo2"):
        base = m.BaseAddress.ToInt64(); break
print("CsiGo2 base = 0x%x" % base)

GATE_RVA = 0x156e11
addr = base + GATE_RVA
orig = bytes((ctypes.c_ubyte * 15).from_address(addr))
print("gate ANTES:", orig.hex(' '))
k32 = ctypes.windll.kernel32
old = ctypes.c_ulong()
k32.VirtualProtect(ctypes.c_void_p(addr), ctypes.c_size_t(15), 0x40, ctypes.byref(old))
# 0x156e11..0x156e1e -> xor eax,eax + nops ; 0x156e1f queda 'c3' ret (no tocar)
newbytes = [0x31, 0xC0] + [0x90] * 12   # xor eax,eax ; nop*12  (14 bytes, hasta antes del ret)
for i, b in enumerate(newbytes):
    (ctypes.c_ubyte).from_address(addr + i).value = b
print("gate DESPUES:", bytes((ctypes.c_ubyte * 15).from_address(addr)).hex(' '))

print("IsSetToRun DEAD pre:", job.CaseIsSetToRun(-1)[0])
job.CaseDeleteAllResults()
job.CaseSetAllToRun()
print("IsSetToRun DEAD tras SetAllToRun (con CRACK):", job.CaseIsSetToRun(-1)[0])
print(">>> Run() ...")
am.Run()
print("estado DEAD tras Run:", job.CaseGetStatus(-1, 0, 0, 0)[-3], "(10005=COMPUTO!!!)")

# leer U si computo
if job.CaseGetStatus(-1, 0, 0, 0)[-1] == 10005 or True:
    from System import Array, Int32, Double
    KT = SF.cConstant.TypeRequestStep; NJ = am.NumNode
    ai = lambda n: Array[Int32]([0]*(n+2)); ad = lambda n: Array[Double]([0.0]*(n+2))
    NR = NJ*6+16; rRes = ad(NR); kResp = ai(8); jElem = ai(NJ+2); rAng = ad(NR)
    i2 = ai(4); kT = ai(4); jC = ai(4); j1 = ai(4); j2 = ai(4); rP = ad(4)
    kTc = ai(4); i2c = ai(4); kCc = ai(4); jCc = ai(4); j1c = ai(4); j2c = ai(4); rMc = ad(4)
    for k in range(1, 7): kResp[k] = 10+k
    for e in range(1, NJ+1): jElem[e] = e
    i2[1] = 1; kT[1] = KT; jC[1] = -1; j1[1] = 1; j2[1] = 1
    try:
        r = job.JointResponse(rRes, kResp, jElem, rAng, i2, kT, jC, j1, j2, rP, kTc, i2c, kCc, jCc, j1c, j2c, rMc, 6, NJ, NJ, 1, 0, 0, 0)
        print("  DEAD nResult=%s" % r[1])
        for e in range(r[2]):
            u = [rRes[1+e*r[0]+c] for c in range(6)]
            print("     joint %s U=%s" % (jElem[1+e], ['%.6g' % v for v in u]))
    except Exception as ex:
        print("  lectura:", str(ex)[:100])
