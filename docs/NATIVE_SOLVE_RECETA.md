# SAPFire cold (sin etabs.exe) — RECETA RECUPERADA (2026-06-08)

## EL HALLAZGO QUE FALTABA EN LA BITÁCORA: `cQuickAnalysis.InitializeAnalysis()`
La bitácora decía "cServer NO tiene método de init". **SÍ lo tiene** — está en
`etabs/decompiled/CSI.QuickAnalysis/CSI.QuickAnalysis/cQuickAnalysis.cs` (InitializeAnalysis,
OpenQuickAnalysis, RunQuickAnalysis). La init del servidor = setear estas props ANTES de
`CreateAnalysisModel()`:

```python
cs = CSI.SAPFire.cServer
cs.ProgramType  = cs.eProgramType.Etabs
cs.ExePathx32   = <engine_dir>/CSI.SAPFire.Driver.exe   # cs.ExeName = "CSI.SAPFire.Driver.exe"
cs.ExePathx64   = <engine_dir>/CSI.SAPFire.Driver.exe
cs.ProgramLabel = "SAPFire"
cs.ProgramLevel = cs.eProgramLevel.Advanced
cs.OutFileName  = <engine_dir>/CSIout.txt
cs.IsInitialized = True
```
Luego config del modelo (de OpenQuickAnalysis): `VersionGUIGo=8470`, `TypeSolver=ParallelOnly`,
`TypeProcess=GUI`, `TypeThread=GUI`, `TypeOptimization=All`, `SaveAfterRun=False`,
`FilesInCore=True`, `FileName=tmp.Y_`, `ForceToKN/LengthToM/TemperatureToC=1`.

**RESULTADO:** con esto, `am.Run()` cold YA COMPLETA: `am.Job.Response(ref a,ref b,ref c)` →
`(timestamp, kFatal=0, nWarning=0)`. **Superado el bloqueador "0 cómputo" de la bitácora.**
(Hace falta copiar `CSI.SAPFire.Driver.exe` al engine_etabs19 — está en el ETABS19 install.)

## LO QUE FALTA (2 pasos claros)
1. **Definir el CASO de análisis** (sin esto no hay U que leer). Secuencia de la bitácora
   (vía `am.Job`): `CaseInit` → `CaseLoadSet(nLoadPatterns)` → `CaseStaticLin(acase)` →
   `CaseLoadAss01(jcase, iLoadAss=1, kLoad=101, iLoad=1)` → `CaseSetAllToRun`. **kLoad=101**
   (no 1/2/5). jcase negativo (-2..) es válido.
2. **Leer U con `cJob.JointResponse`** (firma exacta en `cJob.cs:3767`; nativo pasa `ref array[1]`
   = ARRAYS 1-BASED). Ejemplo canónico en `CSI.SAPModel/cReadSAPBase.cs:695`. Requiere:
   `nElem>0` (nº joints a leer), `nResult>0`, `nRequest>0`; llenar `jElem[1..nElem]`=tags,
   `kResp[1..6]=1..6`, y el request (`jCaseRequest`, `kTypeRequest`, etc.) con el jcase del caso.
   Antes de leer: el `cReadSAPBase` llama `model.OpenAnalysis()` sobre el `cElementModel` interno.

## Estado
- ✅ Motor carga sin etabs.exe / construye modelo / **Run() cold completa (kFatal=0)**.
- ⏳ Falta: caso de análisis (kLoad=101) + lectura JointResponse (1-based, nElem>0).
- Script de trabajo: `native_solve.py` (esta carpeta).

## Continuación (2026-06-08, sesión 2) — avance + límite confirmado
AVANCE real: con `InitializeAnalysis` (arriba) el **Run() cold completa** (Job.Response kFatal=0).
Implementé la secuencia de caso completa (CaseInit→CaseLoadSet(1)→CaseStaticLin→CaseLoadAss01(kLoad=101)→CaseSetAllToRun) en `native_solve.py`.

PROBADO sin éxito para el registro del modelo:
- `am.WriteSelf()` (línea 19391 de cAnalysisModel) — corre OK pero **NO registra** el modelo nativo.
- `am.Refresh()` — la bitácora ya lo descartó (hace ReadSelf y falla).

LÍMITE CONFIRMADO (idéntico a la bitácora): `CaseStaticLin` cold devuelve **jcase=-1** (el OAPI da -2).
jcase=-1 = caso NO creado porque el modelo no está en la tabla nativa `DAT_181cced58` (Go_Model_Create).
→ `CaseLoadAss01` → "Bad load assignment number for jCase".
Ni `WriteSelf` ni la init del servidor registran el modelo en la tabla nativa heap. Eso lo hace la
cañería interna de etabs.exe/cWriteSAP (cientos de FUN_ internas no exportadas). Confirmado: **el
registro nativo del modelo es el muro real**, alcanzable solo con x64dbg/WinDbg interactivo (como ya
concluía la bitácora). El script `native_solve.py` deja todo listo hasta ese punto.

## ✅✅ DESBLOQUEO (2026-06-08, sesión 3) — `CSI.SAPFire.Driver.exe` RESUELVE COLD, sin etabs.exe
El muro de arriba (registro nativo in-process) se **SORTEA por completo** usando el path que la
propia ETABS usa: **el `.Y_` se escribe a disco y un PROCESO SEPARADO `CSI.SAPFire.Driver.exe`
lo lee (`ReadSelf`) y lo resuelve (`Run`)**. No hay que registrar nada in-process — el Driver
monta su propio contexto nativo al arrancar (ctors de las DLLs).

### El Driver = el CLI que buscábamos (decompilado en `decompiled/CSI.SAPFire.Driver/b.cs`)
`Main(args)` modo 0 = **Run GoModel**. Args (8): `0 <outFile> <model.Y_> <label> <cbServer> <progType> <progLevel> <forRelease>`
```
cServer.ProgramLabel/Level/Type/IsProgramForRelease/OutFileName  (setea servidor)
am = cServer.CreateAnalysisModel(); am.FileName=.Y_; am.ReadSelf()
am.SetSchedulerSerial().CanLogRunTime=false; TypeMode.Auto; TypeProcess/Thread=GUI
am.RunningInSeparateProcess=true; am.SaveAfterRun=true
cbServer=="" -> am.RegisterIntraProcessCallback(consoleCb)   (resuelve EN ESTE proceso)
am.Run()
```
Modo 1 = Print GoModel (vuelca el modelo a `<base>_GOMODEL.txt`), args (3): `1 <outFile> <model.Y_>`.
Enums: `eProgramType.Etabs=4`, `eProgramLevel.Advanced=7`.

### Comando probado (FUNCIONA, sin ningún etabs.exe en tasklist)
```
cd engine_etabs19
./CSI.SAPFire.Driver.exe 0 <out.txt> <ruta\modelo.Y_> SAPFire "" 4 7 false
# -> "CSI.SAPFire.Driver: Run GoModel (GUI)" / "cCallback::AdviseBegin()" / Exit Code = 0
```
- **Mode 1 (Print) cold = Exit 0** y genera `_GOMODEL.txt` de 138 KB (modelo leído entero). ✅
- **Mode 0 (Run) cold = Exit 0, AdviseBegin, sin etabs.exe**. ✅

### REQUISITO CRÍTICO (por esto fallaba read_solve.py / native_solve)
`ReadSelf` necesita el **FILESET COMPLETO co-ubicado** junto al `.Y_`, NO solo el `.Y_`:
`<base>.Y_` + `<base>.Y` (≈5 KB, base del modelo — **imprescindible**, sin él `Go_Model_Read failed`)
+ `<base>.msh` + `<base>.K_0/.K_I/.K_J/.K_M`. `read_solve.py` copiaba SOLO el `.Y_` a otro dir →
`ReadSelf` perdía los compañeros → "Go_Model_Read() failed". Con el fileset junto, lee OK.
- Las DLLs (CSI.SAPFire*, CsiGo2*, libif*) resuelven desde el dir del `Driver.exe` (engine_etabs19).
- `SaveAfterRun=true` → reescribe el `.Y_` con resultados. Si el caso ya está marcado "run", `Run()`
  hace corto-circuito (0.02 s, no recomputa). Para forzar: `CaseSetAllToNotRun`/borrar vectores
  resultado — PERO **NO borrar `<base>.Y`** (es input, su borrado rompe ReadSelf).

## ✅✅✅ COLD SOLVE + LECTURA DE RESULTADOS IN-PROCESS (2026-06-08, sesión 4)
**Se rompió el muro de la bitácora** *"am.Run() no dispara cómputo in-process"*. La clave:
**`ReadSelf` SÍ registra el modelo nativamente** (por eso el Driver resuelve). Entonces, en UN
proceso pythonnet (script `cold_inproc_solve.py`): server init (receta Driver/b.cs) → `ReadSelf`
(in-place, fileset completo) → `Run()` completa cold (kComplete=0, kFatal=0) → **se LEEN resultados**.

### Lectura de resultados COLD — receta exacta (lo que faltaba en la bitácora)
`am.Job` expone enumeración + lectura:
- `CaseGetNumber()`, `CaseGetHandle(icase)→jcase`, `CaseGetName(jcase)`, `CaseGetStatus(jcase)→(kStatus,j1,j2)`,
  `CaseGetType(jcase)→kTypeCase`. **jcase es NEGATIVO** (DEAD=-1, LIVE=-2, MODAL=-3, ...).
- `eStatus` (cAnalysisCase.cs): NotDefined=10001, NotRun=10002, CouldNotStart=10003, NotComplete=10004,
  **Complete=10005**. `kTypeCase`: 501=static-lin, 503=modal.
- `cJob.JointResponse(rResult, kResp, jElem, rAngle, i2Req, kTypeReq, jCaseReq, j1Req, j2Req, rPhase,
  <6 arrays comb>, ref nResp, nResult, nElem, nRequest, nComb, nCombass, jMode)`. **Arrays 1-BASED**.
  - **`kResp = [11,12,13,14,15,16]`** = Ux,Uy,Uz,Rx,Ry,Rz (NO 1..6). (de cReadSAP.cs:30687)
  - **`kTypeRequest = cConstant.TypeRequestStep = 701`** (valor nativo, NO 0..16). Leíble vía
    `SF.cConstant.TypeRequestStep` en pythonnet. (de cReadSAP.cs:24152)
  - `i2ResultRequest[1]=1, jCaseRequest[1]=jcase, j1StepRequest[1]=j1, j2StepRequest[1]=j2, rPhase=0`.
  - nResp=6, nElem=NJ, nRequest=1, nComb=nCombass=0, jMode=0.
- Pythonnet devuelve los `ref int` finales como TUPLA. Resultado en `rResult[1 + e*nResp + c]`.
- Análogos: `FrameResponse`, `ShellResponse`, `BaseResponse` (mismas firmas, otros kResp).

### RESULTADO CONFIRMADO (voladizo cant_model, sin etabs.exe)
`cold_inproc_solve.py cant_model/solved/cant.Y_` lee **DEAD joint2 Ry = -6.60162e-05 rad** (rotación
por peso propio) — número REAL, leído cold. Cruza con el OAPI (mismo quirk: el caso de carga puntual
PL recupera reacciones —BaseReact Fz=10, My=-40— pero su displacement de junta sale 0 en ETABS Y en cold
→ consistencia lector-cold == ETABS). Pendiente menor: mapear el caso con U≠0 limpio + forzar recompute
real (Run hace corto-circuito si el caso está Complete).

## 🧱 SESIÓN 6 — MAPA COMPLETO DECOMPILADO + 5 VÍAS DE COMPUTO PROBADAS (todas fallan cold)
Decompilado con `ilspycmd` el stack REAL (v3.0.0.0) en `etabs/decompiled_v3/`:
- **ETABSv1.dll** (API/OAPI) = wrapper COM/Remoting (`Marshal.GetActiveObject`, `GetObjectHostPort`) que
  **lanza+maneja etabs.exe**. NO computa — es la vía dependiente de etabs.exe.
- **CSI.SAPFire.dll** = modelo de análisis + scheduler (Analysis=spawn Driver / GUI=in-process `am.e()`).
- **CSI.SAPFire.Go.dll** = P/Invoke a CsiGo2.dll. El run nativo = `Go_JobCaseSerialRunGet`.
- **CsiGo2.dll** = solver NATIVO C++ (SAPFire/SAP IV). NO decompilable a C# legible (solo asm). El cómputo real.

**5 vías de cómputo cold probadas — TODAS corren sin error pero NINGUNA computa (estado sigue NotRun):**
1. `am.Run()` ❌  2. Driver.exe standalone ❌  3. Driver + mi WCF pipe (engaño, conecta OK) ❌
4. `job.CaseSerialRunGet(0)` (run nativo DIRECTO) ❌  5. `am.e()` (solve in-process por reflexión) ❌

**VEREDICTO FINAL:** el muro NO está en la capa managed (la decompilé entera y puedo llamar cada entry
point). Está en **CsiGo2.dll nativo**, que necesita un contexto que SOLO el arranque completo de etabs.exe
inicializa (probable: validación de licencia + registro de servidor nativo + estado compartido). Replicar
el transporte managed (WCF pipe) NO basta — el solve nativo no dispara igual. Llegar al cómputo cold real
= RE a nivel x64dbg de la init nativa de CsiGo2 (trazar qué monta etabs.exe al arrancar). Comparar con IDEA:
su solver `k2fem64.exe` es file-based y auto-contenido (pipe opcional, licencia en el host) → por eso SÍ
corre standalone. SAPFire es server-based → no.

## 🔬 SESIÓN 6 (2026-06-09): el "engaño" del pipe NO basta — el muro es NATIVO
- **Mismatch de versiones detectado:** `etabs/decompiled/` era CSI.SAPFire **v13.8** (usa ServiceWire);
  el engine real `engine_etabs19` es **v3.0.0.0** (usa **WCF/System.ServiceModel**). Re-decompilado el
  real con `ilspycmd` → `etabs/decompiled_v3/`.
- **Mecanismo real v3 (WCF):** `StartCallbackService(nRun, ICallback)` = `ServiceHost(typeof(cCallbackService))`
  en `net.pipe://localhost/<guid>` (NetNamedPipeBinding None) + `ax4.a(guid, cb)`; el Driver
  `ConnectToServer(guid)` = `ChannelFactory<ICallbackService>.CreateChannel(...)` + `InitializeService(guid)`.
- **Espiado el Driver real:** ETABS spawnea `CSI.SAPFire.Driver.exe 0 <out> <model.Y_> "<label>" "<pipeGUID>" 4 7 True`.
- **ENGAÑO REPLICADO (cold_compute_pipe.py):** hosteé el WCF (StartCallbackService por reflexión) +
  lancé el Driver con MI pipe. **El Driver SE CONECTÓ a mi servicio y reportó callbacks** (Begin/Finalize
  por el pipe). PERO el estado siguió **NotRun** → **el Driver NO computó igual.**
- **CONCLUSIÓN:** el callback WCF NO es la cerradura del cómputo. El Driver corre, conecta el callback,
  pero el solve nativo no dispara cold. El muro es el **contexto de servidor NATIVO (CsiGo2)** que
  etabs.exe mantiene VIVO mientras el Driver corre (memoria/IPC compartida nativa), no la capa managed.
  Replicar eso = RE a nivel x64dbg del init/IPC nativo de CsiGo2 — el muro que la bitácora ya señalaba.

## ⛔ HALLAZGO DEFINITIVO (2026-06-08, sesión 5): COLD COMPUTE bloqueado; COLD READ OK
Probado rigurosamente con `CaseDeleteAllResults()` (borra resultados → estado pasa a NotRun=10002):
- **In-process `am.Run()` NO computa cold**: tras delete+`CaseSetAllToRun`+`Run()`, el estado SIGUE en
  NotRun (10002), `.Y$$`=0 bytes, lectura da "Other error". `Run()` completa (kComplete=0) pero NO resuelve.
- **`CSI.SAPFire.Driver.exe` TAMPOCO computa cold** un `.Y_` NotRun (hecho con ReadSelf+CaseDeleteAllResults
  +WriteSelf): corre 0.016s, estado sigue NotRun. El "solve" del Driver que veíamos era CORTO-CIRCUITO
  (modelo ya Complete del run OAPI original).
- `RunQuickAnalysis` (CSI.QuickAnalysis) = solo `goModel.Run()` → mismo resultado. `cScheduler` con
  `TypeProcess=Analysis` spawnea el Driver con callback INTER-proceso que conecta a un SERVIDOR
  (`ConnectToServer`) — ese servidor lo monta etabs.exe. Cold (callback intra-proceso) el solve no dispara.
- `eStatus`: NotDefined=10001, **NotRun=10002**, CouldNotStart=10003, NotComplete=10004, **Complete=10005**.

**CONCLUSIÓN:** el motor cold (in-process o Driver) **CONSTRUYE + REGISTRA (ReadSelf) + LEE resultados
existentes**, pero **NO COMPUTA resultados nuevos** — el solve nativo exige el contexto de SERVIDOR
SAPFire que solo arma el arranque de etabs.exe. Confirma la conclusión más profunda de la bitácora.

LO QUE SÍ FUNCIONA cold (sin etabs.exe): leer geometría del `.edb` (`edb/edb_model.py`), leer resultados
de un `.Y_` ya resuelto (`cold_inproc_solve.py`, JointResponse kResp=11-16/kTypeRequest=701), redibujar
(`edb/draw_edb.py`). LO QUE NO: computar un modelo nuevo cold.
VÍA REALISTA para resultados NUEVOS: OAPI con etabs.exe OCULTO (ya funciona, da números correctos —
ver "etabs_run" en Calcpad Lab). El cold-compute verdadero exigiría replicar el init del servidor
nativo (x64dbg-level, la idea del "engaño"/spy) — alta dificultad, incierto.

### LO QUE FALTA para independencia TOTAL (de dónde sale el `.Y_`)
El solve cold ya está. La pieza abierta es **producir el `.Y_` sin etabs.exe**:
- Hoy el `.Y_` lo escribió un run OAPI (usa etabs.exe oculto). Re-solverlo = cold. ← ya logrado.
- Path A (build cold + `am.WriteSelf()` → `.Y_` → Driver): bloqueado por la definición de caso cold
  (jcase=-1, el `.Y_` saldría sin caso válido). Habría que cablear el caso en el `.Y_` directo.
- Path B (EDB → `.Y_`): reimplementar cWriteSAP (EDB→modelo de análisis). Trabajo grande pero el
  EDB ya lo leemos (edb/). Es el camino a independencia real.
- Mientras tanto: **etabs (OAPI) escribe el `.Y_` UNA vez; Driver re-solve cold N veces** = el solver
  ya NO es etabs.exe. Útil para variantes/optimización sobre la misma topología.
