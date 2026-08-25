#!/usr/bin/env python3
r"""Extrae resultados REALES de ETABS (caso Live) por OAPI, headless:
   - FrameForce de columnas (verticales) y vigas (horizontales)
   - AreaForceShell de la losa (M11,M22,M12)
Guarda JSON para comparar con Hekatan.  python etabs_live_results.py
"""
import os, json, comtypes.client as cc
V19=r"C:\Program Files\Computers and Structures\ETABS 19\ETABS.exe"
MODEL=r"C:\Tools\re\models\mesa.EDB"

def start():
    cc.CreateObject('ETABSv1.Helper'); from comtypes.gen import ETABSv1 as E
    o=cc.CreateObject('ETABSv1.Helper').QueryInterface(E.cHelper).CreateObject(V19).QueryInterface(E.cOAPI)
    o.ApplicationStart(); sm=o.SapModel
    try: o.Hide()
    except: pass
    sm.File.OpenFile(MODEL); sm.SetPresentUnits(6)
    return o,sm

def main():
    o,sm=start()
    try: sm.SetModelIsLocked(False)
    except: pass
    sm.Analyze.RunAnalysis()
    sm.Results.Setup.DeselectAllCasesAndCombosForOutput()
    sm.Results.Setup.SetCaseSelectedForOutput("Live")

    # clasificar frames por geometria
    fr=sm.FrameObj.GetNameList(); names=fr[1]
    cols=[]; beams=[]
    for nm in names:
        p=sm.FrameObj.GetPoints(nm,"","")   # (p1,p2,ret)
        p1,p2=p[0],p[1]
        z1=sm.PointObj.GetCoordCartesian(p1,0,0,0); z2=sm.PointObj.GetCoordCartesian(p2,0,0,0)
        dz=abs(z1[2]-z2[2]); dxy=abs(z1[0]-z2[0])+abs(z1[1]-z2[1])
        (cols if dz>dxy else beams).append(nm)

    def frame_pick(group):
        agg={"P":0,"V2":0,"V3":0,"T":0,"M2":0,"M3":0}
        for nm in group:
            r=sm.Results.FrameForce(nm,0)
            nb=r[0]
            if nb==0: continue
            P,V2,V3,T,M2,M3=r[7],r[8],r[9],r[10],r[11],r[12]
            for i in range(nb):
                agg["P"]=max(agg["P"],abs(P[i])); agg["V2"]=max(agg["V2"],abs(V2[i]))
                agg["V3"]=max(agg["V3"],abs(V3[i])); agg["T"]=max(agg["T"],abs(T[i]))
                agg["M2"]=max(agg["M2"],abs(M2[i])); agg["M3"]=max(agg["M3"],abs(M3[i]))
        return agg

    out={"case":"Live","units":"kN, kN·m",
         "columns":frame_pick(cols), "beams":frame_pick(beams),
         "n_cols":len(cols),"n_beams":len(beams)}

    # losa shell
    ar=sm.AreaObj.GetNameList(); anames=ar[1]
    sh={"M11":0,"M22":0,"M12":0,"F11":0,"F22":0}
    for nm in anames:
        try: r=sm.Results.AreaForceShell(nm,0)
        except Exception: continue
        nb=r[0]
        if nb==0: continue
        # AreaForceShell: ...F11,F22,F12,FMax,FMin,FAngle,FVM,M11,M22,M12,...
        # indices tipicos: F11=9,F22=10,F12=11, M11=17,M22=18,M12=19 (varia por version)
        try:
            F11,F22=r[9],r[10]; M11,M22,M12=r[17],r[18],r[19]
            for i in range(nb):
                sh["F11"]=max(sh["F11"],abs(F11[i])); sh["F22"]=max(sh["F22"],abs(F22[i]))
                sh["M11"]=max(sh["M11"],abs(M11[i])); sh["M22"]=max(sh["M22"],abs(M22[i]))
                sh["M12"]=max(sh["M12"],abs(M12[i]))
        except Exception as e:
            sh["_err"]=str(e); break
    out["slab_shell"]=sh; out["n_areas"]=len(anames)

    try: o.ApplicationExit(False)
    except: pass
    print(json.dumps(out,indent=2,ensure_ascii=False))
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"etabs_live.json"),"w",encoding="utf-8") as f:
        json.dump(out,f,indent=2,ensure_ascii=False)

if __name__=="__main__":
    main()
