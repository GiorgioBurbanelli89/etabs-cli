r"""Busca ServiceWire embebido en CSI.SAPFire.dll (recursos manifest) y lo extrae si esta comprimido."""
import os, clr, sys
sys.stdout.reconfigure(encoding="utf-8")
ENGINE = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
os.add_dll_directory(ENGINE)
clr.AddReference(os.path.join(ENGINE, 'CSI.SAPFire.dll'))
import System
from System.Reflection import Assembly
from System.IO import Compression, MemoryStream, File

asm = Assembly.LoadFrom(os.path.join(ENGINE, 'CSI.SAPFire.dll'))
print("=== recursos manifest de CSI.SAPFire.dll ===")
names = list(asm.GetManifestResourceNames())
for n in names:
    print("  ", n)

# extraer los que parezcan ensamblados (costura.*.dll / *.compressed)
outdir = os.path.join(ENGINE, "_embedded")
os.makedirs(outdir, exist_ok=True)
for n in names:
    low = n.lower()
    if "servicewire" in low or "costura" in low or low.endswith(".dll") or low.endswith(".dll.compressed"):
        st = asm.GetManifestResourceStream(n)
        ms = MemoryStream(); st.CopyTo(ms); data = ms.ToArray()
        raw = bytes(data)
        # si es .compressed -> deflate
        if low.endswith(".compressed") or "costura" in low:
            import zlib
            try:
                raw = zlib.decompress(bytes(data), -15)
            except Exception:
                try: raw = zlib.decompress(bytes(data))
                except Exception: pass
        fn = n.replace("costura.", "").replace(".compressed", "")
        if not fn.lower().endswith(".dll"): fn += ".bin"
        outp = os.path.join(outdir, os.path.basename(fn))
        File.WriteAllBytes(outp, System.Array[System.Byte](raw))
        print(f"  -> extraido {os.path.basename(outp)} ({len(raw)} bytes)")
