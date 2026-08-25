#!/usr/bin/env python3
r"""cold_build — CONSTRUIR un modelo NUEVO in-process y CALCULARLO con SAPFire, SIN etabs.exe.

Sigue la receta autoritativa de CSI.QuickAnalysis (cQuickAnalysis + cJoistInternalForcesCalc):
  server init (ProgramLevel.Advanced -> abre el gate de licencia) -> CreateAnalysisModel
  -> build (nodos/joint+restraint/material/seccion/frame) -> AddLoadPatternStruct + carga de junta
  -> CaseInit + CaseLoadSet + CaseStaticLin (DEFINE el caso) -> CaseLoadAss01 (asigna la carga al caso)
  -> SetDumpStiffCase(0) + CaseSetAllToRun -> Run()  [in-process, dispara PARDISO]
  -> JointResponse (lee U) y compara con la teoria de viga.

Sonda Frida (mismo PID) cuenta llamadas reales a PARDISO = prueba de que CALCULÓ.

Voladizo: n1(0,0,0) empotrado, n2(L,0,0) libre, carga Fz=-P en n2. Uz_teorico = -P·L³/(3·E·I).
Interop sobre software licenciado en esta máquina. NO redistribuir DLLs de CSI.
"""
import os, sys, clr, time
sys.stdout.reconfigure(encoding="utf-8")

ENGINE = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
WORKDIR_OUT = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\coldbuild_out"
os.makedirs(WORKDIR_OUT, exist_ok=True)
LIC_OFFSET = 0x18241d2e8 - 0x180000000
L, P, E, NU = 4.0, 10.0, 2.1e8, 0.3
G = E / (2.0 * (1.0 + NU))
B, H = 0.3, 0.3
A, I = B * H, B * H**3 / 12.0
As = 5.0 / 6.0 * A
J = 0.1406 * B**4
Uz_teo = -P * L**3 / (3.0 * E * I)

# ------------------------------------------------------------------ Frida
_JS = r"""
'use strict';
var m = Process.findModuleByName('CsiGo2.dll');
var lic = m ? m.base.add(%OFF%) : null;
send({type:'license', level: lic ? lic.readS32() : null});
var n = 0;
['CsiGo2_n.dll','CsiGo2.dll','CsiGo2_a.dll','CsiGo2_d.dll','CsiGo2_f.dll'].forEach(function(mn){
  var mod = Process.findModuleByName(mn); if(!mod) return;
  try { mod.enumerateExports().forEach(function(e){
    if (e.name.toLowerCase().indexOf('pardiso') >= 0) {
      try { Interceptor.attach(e.address, {onEnter:function(){ n++; send({type:'pardiso', sym: mn+'!'+e.name, n:n}); }}); } catch(x){}
    }
  }); } catch(x){}
});

// Traza amplia SOLO durante Run(): Python manda 'runstart' justo antes de am.Run().
var runphase = false, ord = 0;
recv('runstart', function(){ runphase = true; });
var seen = {};
if (m) {
  // BACKTRACE en Go_Server_GetBuild: revela la dirección de cb (su llamador en CSI.SAPFire nativo).
  try {
    var gb = Process.findModuleByName('CsiGo2.dll').enumerateExports().filter(function(e){return e.name==='Go_Server_GetBuild';})[0];
    if (gb) Interceptor.attach(gb.address, { onEnter: function () {
      var bt = Thread.backtrace(this.context, Backtracer.ACCURATE);
      var frames = bt.map(function(a){
        var m = Process.findModuleByAddress(a);
        return m ? (m.name + '+0x' + a.sub(m.base).toString(16)) : a.toString();
      });
      send({type:'backtrace', frames: frames});
    }});
  } catch(e){ send({type:'log', m:'bt hook err '+e}); }

  // Hook al worker de CaseSetAllToRun (FUN_1813e7550): al SALIR, caminar la lista de casos del modelo
  // (modelo+0x180, next +0x23c8) y volcar jcase(+0x100) bSetToRun(+0x108) bSetToRunNow(+0x10c).
  try {
    Interceptor.attach(m.base.add(0x13e7550), {
      onEnter: function(a){ this.p1 = a[0]; },
      onLeave: function(){
        try {
          var model = this.p1.readPointer();
          var node = model.add(0x180).readPointer();
          var i = 0;
          while (!node.isNull() && i < 12) {
            send({type:'casenode',
                  jcase: node.add(0x100).readS32(),
                  bSetToRun: node.add(0x108).readS32(),
                  bSetToRunNow: node.add(0x10c).readS32()});
            node = node.add(0x23c8).readPointer(); i++;
          }
        } catch(e){ send({type:'casenode', err: e.message}); }
      }
    });
  } catch(e){}
}

// Hook al gate de capacidad FUN_180156e00 (RVA 0x156e00). Tallar retornos 0 vs !=0.
var gate0 = 0, gateNZ = 0, gateRep = 0;
if (m) {
  try {
    Interceptor.attach(m.base.add(0x156e00), {
      onEnter: function (a) {
        try { this.f18 = a[0].readPointer().add(0x18).readS32(); } catch(e){ this.f18 = null; }
      },
      onLeave: function (ret) {
        var r = ret.toInt32();
        if (r === 0) { gate0++; }
        else { gateNZ++; if (gateRep < 10) { gateRep++; send({type:'gate', ret:r, f18:this.f18}); } }
      }
    });
  } catch(e){}
}
"""

class Probe:
    def __init__(self):
        import frida
        self.session = frida.attach(os.getpid())
        self.script = self.session.create_script(_JS.replace("%OFF%", hex(LIC_OFFSET)))
        self.level = None
        self.pardiso = []
        self.gate_nz = []
        self.script.on("message", self._m)
        self.script.load(); time.sleep(0.3)
    def _m(self, msg, data):
        if msg.get("type") == "send":
            p = msg["payload"]
            if not isinstance(p, dict): return
            if p.get("type") == "license": self.level = p.get("level")
            elif p.get("type") == "pardiso":
                self.pardiso.append(p["sym"]); print(f"   [PARDISO] {p['sym']}  (#{p['n']})")
            elif p.get("type") == "gate":
                self.gate_nz.append(p); print(f"   [GATE!=0] ret={p['ret']} obj+0x18={p['f18']}")
            elif p.get("type") == "trace":
                print(f"   [{p.get('ord','?'):>3}] {p['fn']}")
            elif p.get("type") == "backtrace":
                print("   === BACKTRACE de Go_Server_GetBuild (cb está acá) ===")
                for fr in p["frames"][:12]:
                    print("      ", fr)
            elif p.get("type") == "casenode":
                if p.get("err"): print(f"   [CASENODE err] {p['err']}")
                else: print(f"   [CASENODE] jcase={p['jcase']} bSetToRun={p['bSetToRun']} bSetToRunNow={p['bSetToRunNow']}")
    def n(self): return len(self.pardiso)


def main():
    os.add_dll_directory(ENGINE)
    clr.AddReference(os.path.join(ENGINE, "CSI.SAPFire.Common.dll"))
    clr.AddReference(os.path.join(ENGINE, "CSI.SAPFire.dll"))
    import CSI.SAPFire as SF
    import System
    from System import Array, Int32, Double

    # --- server init (receta cQuickAnalysis.InitializeAnalysis) ---
    cs = SF.cServer
    cs.ProgramType = cs.eProgramType.Etabs
    cs.ExePathx32 = os.path.join(ENGINE, cs.ExeName)
    cs.ExePathx64 = os.path.join(ENGINE, cs.ExeName)
    cs.ProgramLabel = "SAPFire"
    cs.ProgramLevel = cs.eProgramLevel.Advanced          # <- abre el gate de licencia (=7)
    cs.IsProgramForRelease = False
    cs.OutFileName = os.path.join(ENGINE, "cold_build_srv.txt")
    cs.IsInitialized = True

    am = cs.CreateAnalysisModel()
    am.VersionGUIGo = 8470                                # igual que cQuickAnalysis (el build no era el muro)
    am.TypeOptimization = am.eTypeOptimization.All
    am.TypeSolver = am.eTypeSolver.ParallelOnly
    am.TypeProcess = am.eTypeProcess.GUI                # in-process (para leer los log items directo)
    am.TypeThread = am.eTypeThread.GUI
    am.SaveAfterRun = False
    am.FilesInCore = True
    am.LogToFile = True                                 # <-- LOGGING ON: que el motor escriba qué hace
    am.LogToMonitor = True
    am.FileName = os.path.join(WORKDIR_OUT, "cold_build.Y_")
    try:
        cs.LogToFile(os.path.join(WORKDIR_OUT, "engine.log"))
    except Exception as e:
        print("   cs.LogToFile err:", str(e)[:80])
    am.ForceToKN = 1.0; am.LengthToM = 1.0; am.TemperatureToC = 1.0
    try:
        am.SetSchedulerSerial().CanLogRunTime = False   # scheduler serial in-process
    except Exception as e:
        print("   SetSchedulerSerial err:", str(e)[:80])

    # --- GDL activos del modelo + mass source (receta cJoistInternalForcesCalc, lo que faltaba) ---
    for k in range(1, 7): am.set_IsActiveDofStruct(k, True)   # 3D: Ux,Uy,Uz,Rx,Ry,Rz
    ms = am.AddMassSource(1); ms.set_Factor(0, 1.0)
    am.TagMassSourceDefault = 1

    # --- build: nodos ---
    for tag, (x, y, z) in [(1, (0, 0, 0)), (2, (L, 0, 0))]:
        nd = am.AddNode(tag); nd.set_Coord(1, float(x)); nd.set_Coord(2, float(y)); nd.set_Coord(3, float(z))
    # joint 1 empotrado (n2 queda libre, se crea luego para la carga)
    jt1 = am.AddJoint(1); jt1.set_TagNode(1, 1)
    for k in range(1, 7): jt1.set_IsRestrained(k, True)

    # --- material (receta AddBasicElasticMaterial) ---
    mat = am.AddPropMaterial(1)
    mat.TypeSymmetry = mat.eTypeSymmetry.Isotropic
    rm = mat.AddRecPropMatElastic()
    rm.Temperature = 0.0; rm.Mass = 0.0; rm.Weight = 0.0
    for k in range(1, 4): rm.set_YoungsModulus(k, E); rm.set_ShearModulus(k, G)
    for k in range(1, 4): rm.set_PoissonRatio(k, NU)
    for k in range(4, 16): rm.set_PoissonRatio(k, 0.0)
    for k in range(1, 7): rm.set_Alpha(k, 0.0)

    # --- seccion prism (receta EXACTA cQuickAnalysis.AddFramePoperties: 21 props + modifiers + TypeSource) ---
    sec = am.AddPropFramePrism(1)
    sec.TagPropMaterial = 1
    sec.TypeSource = sec.eTypeSource.Frame
    props = [0.0] * 22                 # 1-based: [1]=A [3]=As2 [6]=As3 [10]=1.0 [15]=I22 [21]=I33
    props[1] = A; props[3] = As; props[6] = As; props[10] = 1.0; props[15] = I; props[21] = I
    for k in range(1, 22): sec.set_Property(k, props[k])
    for k in range(1, 9): sec.set_Modifier(k, 1.0)
    sec.Mass = 0.0; sec.Weight = 0.0

    # --- frame (setup COMPLETO receta cQuickAnalysis.AddFrameElement: releases, ejes locales 2D...) ---
    fr = am.AddFrame(1)
    fr.set_TagNode(1, 1); fr.set_TagNode(2, 2)
    fr.TagPropFrame = 1
    fr.TypeMirrored = fr.eTypeMirrored.MirrorNone
    rel_none = getattr(fr.eTypeRelease, "None")
    for k in range(1, 7): fr.set_Release(k, rel_none)
    fr.NumSegmentOutput = 2
    fr.OffsetI = 0.0; fr.OffsetJ = 0.0; fr.FactorRigid = 0.0
    la = fr.AddLocalAxes2D()
    la.DirPlaneLocal = la.eDirPlaneLocal.Local12
    la.set_TagNodePlane(1, 0); la.set_TagNodePlane(2, 0)
    for k in range(1, 4): la.set_VectorPlane(k, 0.0)
    la.TagCoordSysPlane = 0
    la.set_DirCoordSysPlane(1, la.eDirCoordSys.Zpos)
    la.set_DirCoordSysPlane(2, la.eDirCoordSys.Xpos)
    fr.AngleLocalAxes = 0.0
    fr.PLimitCompression = 0.0

    # --- load pattern + carga de junta Fz=-P en n2 (receta TagLoadPattern) ---
    lp = am.AddLoadPatternStruct(1); lp.Label = "1"
    for k in range(1, 4): lp.set_Gravity(k, 0.0)
    jt2 = am.AddJoint(2); jt2.set_TagNode(1, 2)
    for k in range(1, 7): jt2.set_IsRestrained(k, False)
    el = jt2.AddElemloadStructForce()
    el.TagLoadPattern = 1; el.TagCoordSys = 0
    el.Component = SF.cElemloadForce.eComponent.FixedFZ
    el.Value = -P
    print(f">>> modelo construido: NumNode={am.NumNode} NumFrame={am.NumFrame} NumJoint={am.NumJoint}")

    # --- sonda frida ANTES de definir/encolar el caso (captura el gate en SetToRun) ---
    probe = Probe()
    print(f">>> candado de licencia in-process = {probe.level} (7=Advanced)")

    # --- DEFINIR el caso estatico-lineal (lo que faltaba) ---
    job = am.Job
    job.CaseInit()
    nLoad = job.CaseLoadSet(1)
    nLoad = nLoad[-1] if not isinstance(nLoad, int) else nLoad
    r = job.CaseStaticLin("STAT1", "", 1, 0)        # ref nLoadDim, ref jcase
    jcase = r[-1]
    print(f">>> caso STAT1 definido: jcase={jcase} (nLoadDim={r[0]})")

    # --- asignar el load pattern al caso ---
    kLoad = SF.cConstant.TypeLoadApplyLoad
    job.CaseLoadAss01(jcase, 1, kLoad, 1, 0, 0, 0, 0, False, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0)
    job.SetDumpStiffCase(0)
    job.CaseSetAllToRun()
    print(">>> CaseLoadAss01 + SetDumpStiffCase(0) + CaseSetAllToRun OK")

    # --- callback de progreso ---
    class _Cb(SF.ICallback):
        __namespace__ = "ColdBuild"
        def AdviseBegin(s, t): pass
        def AdviseFinalize(s, t, k): print(f"   [cb] Finalize kComplete={k}")
        def AdviseUpdateMax(s, t, m): pass
        def AdviseUpdateAndCheckCancel(s, t, c, m, km, kc):
            if m and km and km >= 1: print("   [cb]", m)
            return False
        def AdvisePostMessage(s, t, m, km):
            if m and km and km >= 1: print("   [cb]", m)
        def AdviseEnd(s, t, k, m, km):
            if m: print("   [cb] END:", m)
        def AdviseCheckCancel(s, t, kc): return False
        def HandleError(s, t, m, km): print("   [cb] ERROR:", m)
    am.RegisterIntraProcessCallback(_Cb())

    # --- commit del modelo antes de correr (forma el modelo in-core/disco) ---
    try:
        am.WriteSelf(); print(">>> WriteSelf() OK")
    except Exception as e:
        print(">>> WriteSelf err:", str(e)[:100])

    # --- RUN ---
    print(">>> Run() in-process (sin etabs.exe) ...")
    try: probe.script.post({"type": "runstart"})
    except Exception: pass
    time.sleep(0.2)
    n0 = probe.n(); t0 = time.time()
    am.Run()
    dt = time.time() - t0
    iDate, kFatal, nWarn = job.Response(0, 0, 0)[-3:]
    npar = probe.n() - n0
    st = job.CaseGetStatus(jcase, 0, 0, 0)[-3]
    print(f"\n=== VEREDICTO ===")
    print(f"   tiempo Run()     = {dt:.3f} s")
    print(f"   PARDISO llamadas = {npar}")
    print(f"   kFatalLastRun    = {kFatal}  (0 = sin error fatal)")
    print(f"   kStatus caso     = {st}  (10005=Complete)")

    # --- LOG ITEMS del motor (la explicacion del propio engine de que paso) ---
    print("\n=== LOG ITEMS del motor ===")
    try:
        nlog = am.NumLogItem
        print(f"   NumLogItem = {nlog}")
        lst = am.ListLogItem
        for i in range(nlog):
            it = None
            for getter in ("GetItem", "Item", "get_Item"):
                try:
                    it = getattr(lst, getter)(i + 1)
                    if it is not None: break
                except Exception:
                    pass
            if it is None:
                try: it = lst[i + 1]
                except Exception: pass
            if it is None:
                continue
            msg = getattr(it, "Message", "?"); op = getattr(it, "Operation", "?")
            ty = getattr(it, "Type", "?"); lc = getattr(it, "LoadCase", "?")
            print(f"   [{i+1}] type={ty} case={lc} op={op!r} msg={msg!r}")
    except Exception as e:
        print("   log dump err:", str(e)[:160])

    # --- leer U en n2 ---
    NJ = am.NumNode
    ai = lambda n: Array[Int32]([0] * (n + 2))
    ad = lambda n: Array[Double]([0.0] * (n + 2))
    KT = SF.cConstant.TypeRequestStep
    rRes = ad(NJ * 6 + 16); kResp = ai(8); jElem = ai(NJ + 2); rAngle = ad(NJ * 6 + 16)
    i2Req = ai(4); kTypeReq = ai(4); jCaseReq = ai(4); j1Req = ai(4); j2Req = ai(4); rPhase = ad(4)
    kTypeC = ai(4); i2C = ai(4); kCaseC = ai(4); jCaseC = ai(4); j1C = ai(4); j2C = ai(4); rMultC = ad(4)
    for k in range(1, 7): kResp[k] = 10 + k          # Ux=11..Rz=16
    for e in range(1, NJ + 1): jElem[e] = e
    i2Req[1] = 1; kTypeReq[1] = KT; jCaseReq[1] = jcase; j1Req[1] = 1; j2Req[1] = 1
    try:
        rr = job.JointResponse(rRes, kResp, jElem, rAngle, i2Req, kTypeReq, jCaseReq, j1Req, j2Req, rPhase,
                               kTypeC, i2C, kCaseC, jCaseC, j1C, j2C, rMultC, 6, NJ, NJ, 1, 0, 0, 0)
        nResp, nResult, nElem = rr[0], rr[1], rr[2]
        print(f"\n   JointResponse: nResp={nResp} nElem={nElem}")
        for e in range(nElem):
            tag = jElem[1 + e]
            u = [rRes[1 + e * nResp + c] for c in range(min(6, nResp))]
            print(f"   joint {tag}: U[Ux,Uy,Uz,Rx,Ry,Rz] = {['%.6g' % v for v in u]}")
        print(f"\n   Uz teorico n2 = {Uz_teo:.6g} m")
    except Exception as ex:
        print("   lectura U err:", str(ex)[:160])

    if npar > 0 and st == 10005:
        print("\n   >>> ✅ CALCULÓ DE VERDAD un modelo NUEVO sin etabs.exe (PARDISO + Complete).")
    else:
        print("\n   >>> ❌ aún no computa; revisar receta.")


if __name__ == "__main__":
    main()
