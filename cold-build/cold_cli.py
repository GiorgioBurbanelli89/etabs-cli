#!/usr/bin/env python3
r"""cold_cli — CALCULAR un modelo con el motor SAPFire IN-PROCESS, SIN etabs.exe.

A diferencia de leer un .Y_ ya resuelto, este CLI FUERZA el cómputo:
  carga motor -> ReadSelf -> CaseDeleteAllResults + CaseSetAllToRun (NotRun) -> Run()
y PRUEBA que computó de verdad con dos evidencias independientes:
  (1) hook a PARDISO (CsiGo2_n.dll) cuenta las llamadas reales al solver lineal,
  (2) el kStatus del caso pasa de NotRun(10002) a Complete(10005).
Además lee el candado de licencia DAT_18241d2e8 (nivel de producto) EN NUESTRO PROPIO
proceso para confirmar si el gate del solver se abre sin etabs.exe (escenario A) o no (B).

Uso:
  python cold_cli.py solve  <modelo.Y_>        # fuerza recompute + verifica PARDISO + lee U
  python cold_cli.py license <modelo.Y_>       # solo lee el candado de licencia in-process
  python cold_cli.py read   <modelo.Y_>        # lee U de los casos ya Complete (sin recomputar)

Interop sobre software licenciado en esta máquina. NO redistribuir DLLs de CSI.
"""
import os, sys, clr, threading, time
sys.stdout.reconfigure(encoding="utf-8")

ENGINE = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
# RVA del candado de licencia dentro de CsiGo2.dll (base de imagen 0x180000000).
LIC_OFFSET   = 0x18241d2e8 - 0x180000000      # = 0x241d2e8
LEVELS = {0: "(sin licencia)", 1: "Display", 2: "Basic", 3: "PLUS", 4: "Nonlinear",
          5: "Educational", 6: "Student", 7: "Advanced", 8: "Ultimate"}

# ---------------------------------------------------------------- Frida sonda
_FRIDA_JS = r"""
'use strict';
// frida 17: usar Process.findModuleByName (Module.findBaseAddress fue removido).
var csigo2mod = Process.findModuleByName('CsiGo2.dll');
var csigo2 = csigo2mod ? csigo2mod.base : null;
var lic = csigo2 ? csigo2.add(%LIC_OFFSET%) : null;

// Leer el candado al cargar y mandarlo por mensaje (RPC en self-attach es frágil).
function reportLicense() {
  send({type: 'license', base: csigo2 ? csigo2.toString() : null,
        level: lic ? lic.readS32() : null});
}
reportLicense();
recv('readlicense', function () { reportLicense(); });   // permite re-leer on-demand

// Hook a PARDISO: cualquier export que contenga 'pardiso' en los CsiGo2_*.dll.
var hits = {};
['CsiGo2_n.dll','CsiGo2.dll','CsiGo2_a.dll','CsiGo2_d.dll','CsiGo2_f.dll'].forEach(function (mn) {
  var mod = Process.findModuleByName(mn);
  if (!mod) return;
  try {
    mod.enumerateExports().forEach(function (e) {
      if (e.name.toLowerCase().indexOf('pardiso') >= 0) {
        try {
          Interceptor.attach(e.address, {
            onEnter: function () {
              var k = mn + '!' + e.name;
              hits[k] = (hits[k] || 0) + 1;
              send({type: 'pardiso', sym: k, n: hits[k]});
            }
          });
        } catch (err) {}
      }
    });
  } catch (err) {}
});
"""

class Probe:
    """Encapsula frida.attach(self-pid) + RPC para leer licencia y contar PARDISO."""
    def __init__(self):
        import frida
        self.session = frida.attach(os.getpid())
        js = _FRIDA_JS.replace("%LIC_OFFSET%", hex(LIC_OFFSET))
        self.script = self.session.create_script(js)
        self.pardiso_hits = []
        self.license = {"base": None, "level": None}
        self.script.on("message", self._on_msg)
        self.script.load()
        time.sleep(0.3)   # dejar que llegue el mensaje de licencia inicial

    def _on_msg(self, message, data):
        if message.get("type") == "send":
            p = message["payload"]
            if not isinstance(p, dict):
                return
            if p.get("type") == "license":
                self.license = {"base": p.get("base"), "level": p.get("level")}
            elif p.get("type") == "pardiso":
                self.pardiso_hits.append(p["sym"])
                print(f"   [PARDISO] {p['sym']}  (llamada #{p['n']})")

    def read_license(self):
        try:
            self.script.post({"type": "readlicense"})
            time.sleep(0.2)
        except Exception:
            pass
        return self.license

    def pardiso_count(self):
        return len(self.pardiso_hits)


# ------------------------------------------------------------- carga del motor
def load_engine():
    os.add_dll_directory(ENGINE)
    clr.AddReference(os.path.join(ENGINE, "CSI.SAPFire.Common.dll"))
    clr.AddReference(os.path.join(ENGINE, "CSI.SAPFire.dll"))
    import CSI.SAPFire as SF
    return SF


class Cb:
    """ICallback del motor (progreso + errores del Run)."""
    def __init__(self, SF):
        self.SF = SF
    def AdviseBegin(self, t): pass
    def AdviseFinalize(self, t, k): print(f"   [cb] Finalize kComplete={k}")
    def AdviseUpdateMax(self, t, m): pass
    def AdviseUpdateAndCheckCancel(self, t, c, msg, km, kc):
        if msg and km and km >= 1: print("   [cb]", msg)
        return False
    def AdvisePostMessage(self, t, msg, km):
        if msg and km and km >= 1: print("   [cb]", msg)
    def AdviseEnd(self, t, k, msg, km):
        if msg: print("   [cb] END:", msg)
    def AdviseCheckCancel(self, t, kc): return False
    def HandleError(self, t, msg, km): print("   [cb] ERROR:", msg)


def make_model(SF, model_path, workdir):
    cs = SF.cServer
    cs.ProgramLabel = "SAPFire"
    cs.ProgramLevel = cs.eProgramLevel.Advanced
    cs.ProgramType = cs.eProgramType.Etabs
    cs.IsProgramForRelease = False
    cs.OutFileName = os.path.join(workdir, "cold_cli_server.txt")
    am = cs.CreateAnalysisModel()
    am.FileName = model_path
    am.ReadSelf()
    am.SetSchedulerSerial().CanLogRunTime = False
    am.TypeMode = am.eTypeMode.Auto
    am.TypeProcess = am.eTypeProcess.GUI
    am.TypeThread = am.eTypeThread.GUI
    am.RunningInSeparateProcess = False
    am.SaveAfterRun = False
    cb = Cb(SF)
    # ICallback es interface .NET: subclasear vía pythonnet
    class _Cb(SF.ICallback):
        __namespace__ = "ColdCli"
        AdviseBegin = cb.AdviseBegin
        AdviseFinalize = cb.AdviseFinalize
        AdviseUpdateMax = cb.AdviseUpdateMax
        AdviseUpdateAndCheckCancel = cb.AdviseUpdateAndCheckCancel
        AdvisePostMessage = cb.AdvisePostMessage
        AdviseEnd = cb.AdviseEnd
        AdviseCheckCancel = cb.AdviseCheckCancel
        HandleError = cb.HandleError
    am.RegisterIntraProcessCallback(_Cb())
    return am


def case_status(job, jcase=-1):
    st = job.CaseGetStatus(jcase, 0, 0, 0)
    return st[-3]   # kStatus


def cmd_license(model_path):
    SF = load_engine()
    workdir = os.path.dirname(os.path.abspath(model_path))
    am = make_model(SF, model_path, workdir)
    print(f">>> motor cargado in-process (PID {os.getpid()}), SIN etabs.exe")
    probe = Probe()
    info = probe.read_license()
    lvl = info.get("level")
    print(f"\n=== CANDADO DE LICENCIA (DAT_18241d2e8) ===")
    print(f"   base CsiGo2.dll = {info.get('base')}")
    print(f"   nivel = {lvl}  -> {LEVELS.get(lvl, '???')}")
    if lvl is not None and 2 <= lvl <= 8:
        print("   >>> ESCENARIO A: el gate del solver ESTÁ ABIERTO sin etabs.exe. Puede calcular.")
    elif lvl in (0, 1):
        print("   >>> ESCENARIO B: gate CERRADO (0/1). El solver se saltaría. Falta setear el nivel.")
    else:
        print("   >>> valor inesperado; revisar offset/base.")
    return lvl


def cmd_solve(model_path):
    SF = load_engine()
    workdir = os.path.dirname(os.path.abspath(model_path))
    am = make_model(SF, model_path, workdir)
    job = am.Job
    print(f">>> motor cargado in-process (PID {os.getpid()}), SIN etabs.exe")
    print(f"    NumNode={am.NumNode} NumFrame={am.NumFrame} NumJoint={am.NumJoint}")

    probe = Probe()
    info = probe.read_license()
    lvl = info.get("level")
    print(f">>> candado de licencia = {lvl} ({LEVELS.get(lvl, '???')})")

    # --- FORZAR recompute: borrar resultados y marcar todo a correr ---
    print(">>> estado inicial caso(-1):", case_status(job))
    try:
        job.CaseDeleteAllResults()
    except Exception as e:
        print("   CaseDeleteAllResults err:", str(e)[:100])
    try:
        job.CaseSetAllToNotRun()
    except Exception as e:
        print("   CaseSetAllToNotRun err:", str(e)[:100])
    try:
        job.CaseSetAllToRun()
    except Exception as e:
        print("   CaseSetAllToRun err:", str(e)[:100])
    print(">>> estado tras forzar NotRun/ToRun:", case_status(job))

    n0 = probe.pardiso_count()
    print(">>> Run() in-process (debe disparar PARDISO) ...")
    t0 = time.time()
    am.Run()
    dt = time.time() - t0
    n1 = probe.pardiso_count()

    print(f"\n=== VEREDICTO ===")
    print(f"   tiempo Run()      = {dt:.3f} s")
    print(f"   llamadas PARDISO  = {n1 - n0}")
    print(f"   estado caso final = {case_status(job)}  (10005=Complete=COMPUTÓ)")
    if n1 - n0 > 0 and case_status(job) == 10005:
        print("   >>> ✅ CALCULÓ DE VERDAD sin etabs.exe (PARDISO disparó + caso Complete).")
    elif case_status(job) == 10005 and dt > 0.05:
        print("   >>> ⚠ caso Complete pero PARDISO no hookeado; revisar export. Probable cómputo.")
    else:
        print("   >>> ❌ NO computó (PARDISO no disparó / caso no Complete).")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("solve", "license", "read"):
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1]
    model = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else \
        r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\cant_model\solved\cant.Y_"
    if not os.path.exists(model):
        print("modelo no existe:", model); sys.exit(2)
    if cmd == "license":
        cmd_license(model)
    elif cmd == "solve":
        cmd_solve(model)
    elif cmd == "read":
        os.environ["COLD_RECOMPUTE"] = "0"
        import runpy
        sys.argv = [sys.argv[0], model]
        runpy.run_path(os.path.join(os.path.dirname(__file__), "cold_inproc_solve.py"), run_name="__main__")


if __name__ == "__main__":
    main()
