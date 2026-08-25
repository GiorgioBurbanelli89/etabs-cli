#!/usr/bin/env python3
r"""
Watcher robusto del solver de ETABS.
Engancha PARDISO/BLAS tanto si el analisis corre dentro de ETABS.exe como si
ETABS lo lanza en proceso separado (CSI.SAPFire.Driver.exe).

Usa spawn-gating: atrapa CUALQUIER proceso nuevo en el instante de nacer
(suspendido), y si es el driver/ETABS le inyecta el hook ANTES de que resuelva.
Tambien adjunta de una a los ETABS.exe ya abiertos.

Uso:  python watch_solver.py
Luego en ETABS: Analyze > Run (desbloquea el candado / Delete Results si hace falta).
Ctrl+C para salir.
"""
import os, sys, time, datetime
import frida

HERE = os.path.dirname(os.path.abspath(__file__))
DUMP = os.path.join(HERE, "dump")
os.makedirs(DUMP, exist_ok=True)
with open(os.path.join(HERE, "pardiso_hook.js"), encoding="utf-8") as f:
    JS = f.read()

# procesos cuyo solver queremos vigilar
TARGETS = ("etabs", "sapfire", "csigo")
_sessions = {}   # pid -> (session, script)

def stamp():
    return datetime.datetime.now().strftime("%H:%M:%S")

def on_message(message, data, pid=None):
    if message["type"] == "error":
        print(f"[JS-ERR pid{pid}]", message.get("description")); return
    p = message["payload"]; tag = p.get("tag")
    if tag == "info":
        print(f"[{stamp()}][{pid}] {p['msg']}")
    elif tag == "blas":
        extra = (f" m={p.get('m')} n={p.get('n')}" if p.get('m') or p.get('n') else "")
        print(f"[{stamp()}][{pid}] BLAS {p['fn']} #{p['count']}{extra}")
    elif tag == "call":
        print(f"[{stamp()}][{pid}] PARDISO call#{p['call']} phase={p['phase']} "
              f"mtype={p['mtype']} n={p['n']} nrhs={p['nrhs']}")
    elif tag == "matrix":
        print(f"   K call#{p['call']}: n={p['n']} nnz={p['nnz']} mtype={p['mtype']}")
        for e in p.get("preview", []):
            print(f"     a[col {e['j']}]={e['v']:.6g}")
    elif tag == "rhs":
        print(f"   F call#{p['call']}: len={p['len']} " +
              ", ".join(f"{v:.6g}" for v in p["preview"]))
    elif tag == "sol":
        print(f"   U call#{p['call']}: len={p['len']} " +
              ", ".join(f"{v:.6g}" for v in p["preview"]))
    elif tag == "blob" and data is not None:
        path = os.path.join(DUMP, f"pid{pid}_call{p['call']:03d}_{p['what']}.bin")
        with open(path, "wb") as fo: fo.write(data)
        print(f"     -> {p['what']} {len(data)}B -> {os.path.basename(path)}")
    elif tag == "err":
        print(f"   [hook-err {p.get('where')}] {p.get('msg')}")

def inject(device, pid, label=""):
    if pid in _sessions: return
    try:
        session = device.attach(pid)
        script = session.create_script(JS)
        script.on("message", lambda m, d, _pid=pid: on_message(m, d, _pid))
        script.load()
        _sessions[pid] = (session, script)
        session.on("detached", lambda *a, _pid=pid: _sessions.pop(_pid, None))
        print(f"[{stamp()}] INYECTADO en pid {pid} {label}")
    except Exception as e:
        print(f"[{stamp()}] no pude inyectar en {pid} {label}: {e}")

def main():
    device = frida.get_local_device()

    # 1) adjuntar a ETABS ya abiertos
    for p in device.enumerate_processes():
        if "etabs" in p.name.lower():
            inject(device, p.pid, f"({p.name} ya abierto)")

    # 2) poll rapido: detectar driver/ETABS nuevos apenas aparezcan (spawn-gating
    #    no esta soportado en Windows). Inyectamos en cuanto el PID existe.
    print(f"[{stamp()}] poll-attach ON (30ms). Vigilando {TARGETS}.")
    print("Corre el analisis en ETABS (desbloquea el candado / Delete Results). Ctrl+C para salir.")
    seen = set(_sessions.keys())
    try:
        while True:
            try:
                for p in device.enumerate_processes():
                    if p.pid in seen:
                        continue
                    if any(t in p.name.lower() for t in TARGETS):
                        seen.add(p.pid)
                        print(f"[{stamp()}] NUEVO {p.name} pid={p.pid} -> inyectando")
                        inject(device, p.pid, f"({p.name})")
            except Exception:
                pass
            time.sleep(0.03)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
