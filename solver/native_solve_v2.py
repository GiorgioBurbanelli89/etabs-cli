import os,sys,clr
sys.stdout.reconfigure(encoding='utf-8')
d=r"C:/Users/j-b-j/Documents/Hekatan Calc 1.0.0/hekatan-etabs-bridge/engine_etabs19"
os.add_dll_directory(d); os.chdir(d)
clr.AddReference(os.path.join(d,'CSI.SAPFire.dll'))
import CSI.SAPFire as SF
import System
cs=SF.cServer
# --- InitializeAnalysis (receta cQuickAnalysis, lo que faltaba) ---
cs.ProgramType = cs.eProgramType.Etabs
cs.ExePathx32 = os.path.join(d, cs.ExeName)
cs.ExePathx64 = os.path.join(d, cs.ExeName)   # driver en el root del engine
cs.ProgramLabel = 'SAPFire'
cs.ProgramLevel = cs.eProgramLevel.Advanced
cs.OutFileName = os.path.join(d,'CSIout.txt')
cs.IsInitialized = True
am=cs.CreateAnalysisModel()
am.VersionGUIGo=8470
am.TypeOptimization=am.eTypeOptimization.All
am.TypeSolver=am.eTypeSolver.ParallelOnly
am.TypeProcess=am.eTypeProcess.GUI
am.TypeThread=am.eTypeThread.GUI
am.SaveAfterRun=False
am.FilesInCore=True
am.FileName=os.path.join(d,'tmp.Y_')
am.ForceToKN=1.0; am.LengthToM=1.0; am.TemperatureToC=1.0
# --- build cantilever (igual que hekatan_console, que SI construye) ---
n1=am.AddNode(1); n1.set_Coord(1,0.0); n1.set_Coord(2,0.0); n1.set_Coord(3,0.0)
n2=am.AddNode(2); n2.set_Coord(1,4.0); n2.set_Coord(2,0.0); n2.set_Coord(3,0.0)
m=am.AddPropMaterial(1); r=m.AddRecPropMatElastic(); r.YoungsModulus=2.1e8; r.PoissonRatio=0.3; r.ShearModulus=2.1e8/2.6
s=am.AddPropFramePrism(1); s.TagPropMaterial=1
for i,v in enumerate([0.15,0.125,0.125,0.0025,0.001125,0.003125],1): s.set_Property(i,v)
fr=am.AddFrame(1); fr.set_TagNode(1,1); fr.set_TagNode(2,2); fr.TagPropFrame=1
j=am.AddJoint(1); j.set_TagNode(1,1); j.IsRestrained=True
am.AddLoadPatternStruct(1)
j2=am.AddJoint(2); j2.set_TagNode(1,2); el=j2.AddElemloadStructForce(); el.Value=-10.0
print('modelo construido. NumNode=',am.NumNode,' NumFrame=',am.NumFrame)
print('>>> Run() ...')
am.Run()
print('Run() retorno.')
i1=System.Int32(0); i2=System.Int32(0); i3=System.Int32(0)
try:
    ret=am.Job.Response(i1,i2,i3)
    print('Job.Response ret=', ret)
except Exception as e:
    print('Response err:', str(e)[:120])

# ===== intento de lectura de U (cReadSAPBase: OpenAnalysis + JointResponse 1-based) =====
print(">>> leyendo desplazamientos...")
try:
    try: am.OpenAnalysis()
    except Exception as e: print('  OpenAnalysis:', str(e)[:60])
    NJ=am.NumNode; N=max(64, NJ*8)
    ai=lambda n: System.Array[System.Int32]([0]*(n+1))   # 1-based
    ad=lambda n: System.Array[System.Double]([0.0]*(n+1))
    rResult=ad(N*4); kResp=ai(8); jElem=ai(N); rAngle=ad(N*4)
    i2Req=ai(N); kTypeReq=ai(N); jCaseReq=ai(N); j1Req=ai(N); j2Req=ai(N); rPhase=ad(N)
    kTypeC=ai(N); i2C=ai(N); kCaseC=ai(N); jCaseC=ai(N); j1C=ai(N); j2C=ai(N); rMultC=ad(N)
    for k in range(1,7): kResp[k]=k
    jCaseReq[1]=1; kTypeReq[1]=1; i2Req[1]=1; j1Req[1]=1; j2Req[1]=1
    z=System.Int32(0)
    ret=am.Job.JointResponse(rResult,kResp,jElem,rAngle,i2Req,kTypeReq,jCaseReq,j1Req,j2Req,rPhase,
        kTypeC,i2C,kCaseC,jCaseC,j1C,j2C,rMultC, 6,0,0,1,0,0,0)
    print('  JointResponse ret(nResp,nResult,nElem,...) =', ret)
    nResp,nResult,nElem = ret[0],ret[1],ret[2]
    print('  nResp=%s nElem=%s' % (nResp,nElem))
    for e in range(nElem):
        tag=jElem[1+e]
        u=[rResult[1+e*nResp+c] for c in range(min(6,nResp))]
        print('   joint tag %s: U='%tag, ['%.6g'%v for v in u])
except Exception as e:
    print('  lectura U err:', str(e)[:160])
