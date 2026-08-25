#!/usr/bin/env python3
r"""Corre ETABS en un ESCRITORIO Windows OCULTO -> nunca se ve la ventana.
Lanza ETABS.exe con CreateProcess en un desktop aparte y se adjunta por OAPI
(GetObject / AttachToInstance). Cero destello en TU pantalla.

  from etabs_hidden import start_hidden, stop
  etabs, sm, proc = start_hidden("19")
"""
import ctypes, time, os
from ctypes import wintypes
import comtypes.client as cc

EXE = {"19": r"C:\Program Files\Computers and Structures\ETABS 19\ETABS.exe",
       "22": r"C:\Program Files\Computers and Structures\ETABS 22\ETABS.exe"}

u32=ctypes.windll.user32; k32=ctypes.windll.kernel32
GENERIC_ALL=0x10000000
CREATE_NEW_CONSOLE=0x00000010

class STARTUPINFO(ctypes.Structure):
    _fields_=[("cb",wintypes.DWORD),("lpReserved",wintypes.LPWSTR),
        ("lpDesktop",wintypes.LPWSTR),("lpTitle",wintypes.LPWSTR),
        ("dwX",wintypes.DWORD),("dwY",wintypes.DWORD),("dwXSize",wintypes.DWORD),
        ("dwYSize",wintypes.DWORD),("dwXCountChars",wintypes.DWORD),
        ("dwYCountChars",wintypes.DWORD),("dwFillAttribute",wintypes.DWORD),
        ("dwFlags",wintypes.DWORD),("wShowWindow",wintypes.WORD),
        ("cbReserved2",wintypes.WORD),("lpReserved2",ctypes.c_void_p),
        ("hStdInput",wintypes.HANDLE),("hStdOutput",wintypes.HANDLE),
        ("hStdError",wintypes.HANDLE)]
class PROCESS_INFORMATION(ctypes.Structure):
    _fields_=[("hProcess",wintypes.HANDLE),("hThread",wintypes.HANDLE),
        ("dwProcessId",wintypes.DWORD),("dwThreadId",wintypes.DWORD)]

DESKTOP="HekatanHidden"

def _make_desktop():
    h=u32.CreateDesktopW(DESKTOP, None, None, 0, GENERIC_ALL, None)
    if not h: raise ctypes.WinError(ctypes.get_last_error())
    return h

def _launch_on_desktop(exe):
    si=STARTUPINFO(); si.cb=ctypes.sizeof(si)
    si.lpDesktop=DESKTOP                # <-- ETABS nace en el desktop oculto
    pi=PROCESS_INFORMATION()
    ok=k32.CreateProcessW(exe,None,None,None,False,CREATE_NEW_CONSOLE,None,
                          os.path.dirname(exe),ctypes.byref(si),ctypes.byref(pi))
    if not ok: raise ctypes.WinError(ctypes.get_last_error())
    return pi

def start_hidden(ver="19", timeout=60):
    _make_desktop()
    pi=_launch_on_desktop(EXE[ver])
    cc.CreateObject('ETABSv1.Helper'); from comtypes.gen import ETABSv1 as E
    helper=cc.CreateObject('ETABSv1.Helper').QueryInterface(E.cHelper)
    etabs=None; t0=time.time()
    while time.time()-t0<timeout:
        try:
            obj=helper.GetObject("CSI.ETABS.API.ETABSObject")
            if obj:
                etabs=obj.QueryInterface(E.cOAPI)
                if etabs.SapModel: break
        except Exception:
            pass
        time.sleep(0.5)
    if not etabs: raise RuntimeError("no pude adjuntarme al ETABS oculto")
    return etabs, etabs.SapModel, pi.dwProcessId

def stop(etabs):
    try: etabs.ApplicationExit(False)
    except Exception: pass

if __name__=="__main__":
    import sys
    ver=sys.argv[1] if len(sys.argv)>1 else "19"
    et,sm,pid=start_hidden(ver)
    print("ETABS oculto pid:", pid, " version:", sm.GetVersion()[0])
    time.sleep(2)
    stop(et)
