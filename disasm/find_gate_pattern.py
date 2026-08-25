r"""Escanea CsiGo2.dll CARGADO buscando la funcion-gate por su patron distintivo:
mov eax,[rax+0x18] ... cmp eax,0x63(99) ... test byte[r+0x14],1 ... xor eax,eax.
Devuelve candidatos con su direccion de inicio de funcion."""
import os, clr, ctypes, sys, functools
sys.stdout.reconfigure(encoding="utf-8")
print = functools.partial(print, flush=True)
import capstone

E = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
os.add_dll_directory(E)
clr.AddReference(os.path.join(E, 'CSI.SAPFire.Common.dll'))
clr.AddReference(os.path.join(E, 'CSI.SAPFire.dll'))
import CSI.SAPFire as SF
cs = SF.cServer; cs.ProgramLabel = "x"; cs.ProgramLevel = cs.eProgramLevel.Advanced; cs.ProgramType = cs.eProgramType.Etabs
cs.OutFileName = os.path.join(os.path.dirname(sys.argv[1]), "o.txt")
am = cs.CreateAnalysisModel(); am.FileName = sys.argv[1]; am.ReadSelf()
am.Job.CaseGetStatus(-1, 0, 0, 0)   # fuerza carga de CsiGo2

from System.Diagnostics import Process
base = size = None
for m in Process.GetCurrentProcess().Modules:
    if m.ModuleName.lower().startswith("csigo2"):
        base = m.BaseAddress.ToInt64(); size = m.ModuleMemorySize
        print("CsiGo2 base=0x%x size=0x%x" % (base, size)); break

# leer toda la imagen cargada
buf = (ctypes.c_ubyte * size).from_address(base)
data = bytes(buf)
print("imagen leida:", len(data), "bytes")

# escanear: cmp eax,0x63 = 83 F8 63 ; cerca test byte[r+0x14],1 = F6 (40|41|42|43|44..) 14 01 ; xor eax,eax = 33 C0 o 31 C0
hits = []
i = 0
while True:
    j = data.find(b"\x83\xf8\x63", i)   # cmp eax, 0x63
    if j < 0: break
    win = data[max(0, j - 40):j + 40]
    has_test14 = (b"\x14\x01" in win)    # ...,[r+0x14],1
    has_xor = (b"\x33\xc0" in win or b"\x31\xc0" in win)
    has_off18 = (b"\x40\x18" in win or b"\x18" in data[j-12:j])  # mov eax,[rax+0x18] heuristico
    if has_test14 and has_xor:
        hits.append((j, has_off18))
    i = j + 1
print("candidatos cmp eax,0x63 con test[+0x14] y xor:", len(hits))
for off, o18 in hits[:20]:
    va = base + off
    print("  @RVA 0x%x (VA 0x%x)  off18=%s  bytes: %s" % (off, va, o18, data[off-3:off+12].hex(' ')))
