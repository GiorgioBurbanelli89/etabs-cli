#!/usr/bin/env python3
r"""Arranque de ETABS por OAPI SIN destello: un hilo Win32 oculta la ventana
de ETABS en el instante en que nace, en paralelo con ApplicationStart()
(que en v19 no tiene parametro de visibilidad). Resultado: nunca se ve la GUI.

  from etabs_quiet import start_quiet, stop
  etabs, sm = start_quiet("19")   # o "22"
"""
import threading, time, ctypes
from ctypes import wintypes
import comtypes.client as cc

EXE = {"19": r"C:\Program Files\Computers and Structures\ETABS 19\ETABS.exe",
       "22": r"C:\Program Files\Computers and Structures\ETABS 22\ETABS.exe"}

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32
SW_HIDE = 0
GetWindowThreadProcessId = u32.GetWindowThreadProcessId
EnumWindows = u32.EnumWindows
ShowWindow = u32.ShowWindow
IsWindowVisible = u32.IsWindowVisible
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

def _hide_windows_of(pid):
    """Oculta TODAS las ventanas top-level del proceso pid. Devuelve cuantas ocultó."""
    hidden = [0]
    def cb(hwnd, lparam):
        wpid = wintypes.DWORD()
        GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and IsWindowVisible(hwnd):
            ShowWindow(hwnd, SW_HIDE); hidden[0]+=1
        return True
    EnumWindows(WNDENUMPROC(cb), 0)
    return hidden[0]

class _Hider(threading.Thread):
    """Vigila el pid y oculta su ventana apenas aparezca, por unos segundos."""
    def __init__(self, get_pid, seconds=8):
        super().__init__(daemon=True); self.get_pid=get_pid; self.seconds=seconds
        self.flashes=0; self.stop_flag=False
    def run(self):
        t0=time.time()
        while time.time()-t0 < self.seconds and not self.stop_flag:
            pid=self.get_pid()
            if pid:
                n=_hide_windows_of(pid)
                self.flashes+=n
            time.sleep(0.004)   # ~4 ms: oculta antes de que el ojo lo note

def _etabs_pid():
    # pid del ETABS.exe mas reciente
    import os
    out=os.popen('tasklist /FI "IMAGENAME eq ETABS.exe" /FO CSV /NH').read()
    pids=[int(l.split(',')[1].strip('"')) for l in out.splitlines() if 'ETABS.exe' in l]
    return max(pids) if pids else None

def start_quiet(ver="19"):
    cc.CreateObject('ETABSv1.Helper'); from comtypes.gen import ETABSv1 as E
    helper=cc.CreateObject('ETABSv1.Helper').QueryInterface(E.cHelper)
    etabs=helper.CreateObject(EXE[ver]).QueryInterface(E.cOAPI)
    # lanzar hider ANTES de ApplicationStart (que crea la ventana)
    hider=_Hider(_etabs_pid); hider.start()
    etabs.ApplicationStart()        # bloqueante; el hider trabaja en paralelo
    try: etabs.Hide()               # ademas, oculta via OAPI
    except Exception: pass
    time.sleep(0.3); hider.stop_flag=True
    sm=etabs.SapModel
    try: sm.SetPresentUnits(6)
    except Exception: pass
    start_quiet.last_flashes=hider.flashes
    return etabs, sm

def stop(etabs):
    try: etabs.ApplicationExit(False)
    except Exception: pass

if __name__=="__main__":
    import sys
    ver=sys.argv[1] if len(sys.argv)>1 else "19"
    et,sm=start_quiet(ver)
    print("version:", sm.GetVersion()[0])
    print("ventanas ocultadas por el hider:", getattr(start_quiet,'last_flashes',0))
    time.sleep(1.0)
    stop(et)
