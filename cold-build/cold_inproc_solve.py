#!/usr/bin/env python3
r"""Cold-solve IN-PROCESS + lectura de resultados, sin etabs.exe.
Replica el Driver (b.cs) pero se queda en proceso para LEER U/reacciones:
  server init -> CreateAnalysisModel -> ReadSelf(.Y_ in-place, registra el modelo)
  -> CaseSetAllToNotRun -> Run() (computa) -> BaseResponse / JointResponse.
Uso: cold_inproc_solve.py <ruta\modelo.Y_>
"""
import os, sys, clr
sys.stdout.reconfigure(encoding="utf-8")

MODEL = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else
        r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\coldtest\voladizo_cli.Y_")
WORKDIR = os.path.dirname(MODEL)
ENGINE = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"

os.add_dll_directory(ENGINE)
clr.AddReference(os.path.join(ENGINE, "CSI.SAPFire.Common.dll"))
clr.AddReference(os.path.join(ENGINE, "CSI.SAPFire.dll"))
import CSI.SAPFire as SF
import System
from System import Array, Int32, Double


class Cb(SF.ICallback):
    __namespace__ = "ColdInproc"
    def AdviseBegin(self, t): pass
    def AdviseFinalize(self, t, k): print(f"  [cb] Finalize kComplete={k}")
    def AdviseUpdateMax(self, t, m): pass
    def AdviseUpdateAndCheckCancel(self, t, c, msg, km, kc):
        if msg and km and km >= 1: print("  [cb]", msg)
        return False
    def AdvisePostMessage(self, t, msg, km):
        if msg and km and km >= 1: print("  [cb]", msg)
    def AdviseEnd(self, t, k, msg, km):
        if msg: print("  [cb] END:", msg)
    def AdviseCheckCancel(self, t, kc): return False
    def HandleError(self, t, msg, km): print("  [cb] ERROR:", msg)


# --- server init (receta del Driver b.cs) ---
cs = SF.cServer
cs.ProgramLabel = "SAPFire"
cs.ProgramLevel = cs.eProgramLevel.Advanced
cs.ProgramType = cs.eProgramType.Etabs
cs.IsProgramForRelease = False
cs.OutFileName = os.path.join(WORKDIR, "coldinproc_server.txt")

am = cs.CreateAnalysisModel()
am.FileName = MODEL
print(">>> ReadSelf()", MODEL)
am.ReadSelf()
print(f"    OK  NumNode={am.NumNode} NumFrame={am.NumFrame} NumJoint={am.NumJoint}")

am.SetSchedulerSerial().CanLogRunTime = False
am.TypeMode = am.eTypeMode.Auto
am.TypeProcess = am.eTypeProcess.GUI
am.TypeThread = am.eTypeThread.GUI
am.RunningInSeparateProcess = False
am.SaveAfterRun = False
am.RegisterIntraProcessCallback(Cb())

job = am.Job
RECOMPUTE = os.environ.get("COLD_RECOMPUTE", "0") == "1"
if RECOMPUTE:
    try:
        job.CaseSetAllToNotRun(); print(">>> CaseSetAllToNotRun OK (fuerza recompute)")
    except Exception as e:
        print(">>> CaseSetAllToNotRun err:", str(e)[:120])
    try:
        job.CaseSetAllToRun()
    except Exception as e:
        print(">>> CaseSetAllToRun err:", str(e)[:120])
    print(">>> Run() in-process ...")
    am.Run()
    print("    Job.Response ->", job.Response(0, 0, 0))
else:
    print(">>> (sin recompute: leo los resultados YA presentes en el .Y_)")

# --- abrir analisis para leer ---
elemModel = None
for attr in ("ElementModel", "Model", "get_ElementModel"):
    try:
        elemModel = getattr(am, attr)
        if callable(elemModel): elemModel = elemModel()
        if elemModel is not None: break
    except Exception:
        pass
if elemModel is not None:
    try:
        ok = elemModel.OpenAnalysis()
        print("    OpenAnalysis ->", ok)
    except Exception as e:
        print("    OpenAnalysis err:", str(e)[:120])

# --- helpers de arrays 1-based ---
ai = lambda n: Array[Int32]([0] * (n + 2))
ad = lambda n: Array[Double]([0.0] * (n + 2))

NJ = am.NumNode

# --- enumerar casos REALES (jcase + steps) en vez de adivinar ---
print("\n=== Casos de analisis (CaseGetNumber/Handle/Name/Status) ===")
cases = []
try:
    nCase = job.CaseGetNumber(0)[-1] if not isinstance(job.CaseGetNumber(0), int) else job.CaseGetNumber(0)
except Exception as e:
    nCase = 0; print("  CaseGetNumber err:", str(e)[:120])
print("  nCase =", nCase)
for icase in range(1, (nCase or 0) + 1):
    try:
        jcase = job.CaseGetHandle(icase, 0)[-1]
        name = job.CaseGetName(jcase)
        st = job.CaseGetStatus(jcase, 0, 0, 0)   # ret: kStatus, j1Step, j2Step
        kStatus, j1, j2 = st[-3], st[-2], st[-1]
        ktype = job.CaseGetType(jcase, 0)[-1]
        cases.append((jcase, name, kStatus, j1, j2, ktype))
        print(f"  icase={icase}: jcase={jcase} name={name!r} kStatus={kStatus} steps=[{j1}..{j2}] kTypeCase={ktype}")
    except Exception as e:
        print(f"  icase={icase}: err {str(e)[:120]}")

# --- BaseResponse: reaccion total en la base (la mas simple de validar) ---
# void BaseResponse(rResultBaseRA4, kRespRA1, rOriginRA1, rCosRA2, i2ResultRequestRA1,
#   kTypeRequestRA1, jCaseRequestRA1, j1StepRequestRA1, j2StepRequestRA1, rPhaseRequestRA1,
#   kTypeCombRA1, i2CombassCombRA1, kCaseCombassRA1, jCaseCombassRA1, j1StepCombassRA1,
#   j2StepCombassRA1, rMultCombassRA1, ref nResp, ref nResult, ref nRequest, ref nComb,
#   ref nCombass, ref jMode)
def try_base(jcase, ktype):
    NR = 64
    rRes = ad(NR); kResp = ai(8); rOrigin = ad(4); rCos = ad(16)
    i2Req = ai(4); kTypeReq = ai(4); jCaseReq = ai(4); j1Req = ai(4); j2Req = ai(4); rPhase = ad(4)
    kTypeC = ai(4); i2C = ai(4); kCaseC = ai(4); jCaseC = ai(4); j1C = ai(4); j2C = ai(4); rMultC = ad(4)
    for k in range(1, 7): kResp[k] = k
    i2Req[1] = 1; kTypeReq[1] = ktype; jCaseReq[1] = jcase; j1Req[1] = 1; j2Req[1] = 1
    r = job.BaseResponse(rRes, kResp, rOrigin, rCos, i2Req, kTypeReq, jCaseReq, j1Req, j2Req, rPhase,
                         kTypeC, i2C, kCaseC, jCaseC, j1C, j2C, rMultC, 6, 1, 1, 0, 0, 0)
    nResp, nResult, nRequest, nComb, nCombass, jMode = r
    vals = [rRes[1 + i] for i in range(min(6, nResp))]
    return nResp, nResult, vals

def try_joint(jcase, ktype, j1, j2):
    NR = NJ * 6 + 16
    rRes = ad(NR); kResp = ai(8); jElem = ai(NJ + 2); rAngle = ad(NR)
    i2Req = ai(4); kTypeReq = ai(4); jCaseReq = ai(4); j1Req = ai(4); j2Req = ai(4); rPhase = ad(4)
    kTypeC = ai(4); i2C = ai(4); kCaseC = ai(4); jCaseC = ai(4); j1C = ai(4); j2C = ai(4); rMultC = ad(4)
    for k in range(1, 7): kResp[k] = 10 + k     # desplazamiento de junta: Ux=11..Rz=16
    for e in range(1, NJ + 1): jElem[e] = e
    i2Req[1] = 1; kTypeReq[1] = ktype; jCaseReq[1] = jcase; j1Req[1] = j1; j2Req[1] = j2
    r = job.JointResponse(rRes, kResp, jElem, rAngle, i2Req, kTypeReq, jCaseReq, j1Req, j2Req, rPhase,
                          kTypeC, i2C, kCaseC, jCaseC, j1C, j2C, rMultC, 6, NJ, NJ, 1, 0, 0, 0)
    nResp, nResult, nElem = r[0], r[1], r[2]
    out = []
    for e in range(nElem):
        u = [rRes[1 + e * nResp + c] for c in range(min(6, nResp))]
        out.append((jElem[1 + e], u))
    if os.environ.get("COLD_RAW"):
        raw = [round(rRes[k], 9) for k in range(1, 2 + nResp * max(nElem, 1))]
        print(f"     [raw rRes 1..{nResp*nElem}] = {raw}")
    return nResp, nResult, nElem, out

# kTypeRequest correcto = cConstant.TypeRequestStep (valor nativo, no 0..16)
KT_STEP = SF.cConstant.TypeRequestStep
print(f"\n=== Lectura COLD (kTypeRequest=TypeRequestStep={KT_STEP}); todos los casos estaticos completos ===")
WANT = os.environ.get("COLD_CASE")   # opcional: leer solo este caso por nombre
read_any = False
for (jc, nm, ks, j1, j2, ktc) in cases:
    name = str(nm[0]) if isinstance(nm, tuple) else str(nm)
    if ktc != 501 or ks != 10005:    # solo estatico lineal + Complete
        continue
    if WANT and WANT.upper() not in name.upper():
        continue
    try:
        nResp, nResult, nElem, out = try_joint(jc, KT_STEP, j1, j2)
    except Exception as e:
        print(f"  caso {name} (jcase={jc}): ERR {str(e)[:80]}"); continue
    nz = any(abs(v) > 1e-12 for _, u in out for v in u)
    flag = "  <-- U != 0" if nz else ""
    print(f"  caso {name} (jcase={jc}): nResult={nResult} nElem={nElem}{flag}")
    for t, u in out:
        print(f"     joint {t}: U[Ux,Uy,Uz,Rx,Ry,Rz] = {['%.6g' % v for v in u]}")
    read_any = True
if not read_any:
    print("  (ningun caso estatico completo)")
print("\nDONE")
