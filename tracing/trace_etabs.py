#!/usr/bin/env python3
"""
Ojeador del solver de ETABS (Hekatan RE).
Engancha Intel MKL PARDISO dentro de CsiGo2_n.dll mientras ETABS corre un analisis
y vuelca K (CSR), F y U numero por numero a ./dump/.

Uso:
    # 1) atacar un ETABS ya abierto:
    python trace_etabs.py --attach ETABS.exe
    # 2) lanzar un exe y atacar desde el arranque:
    python trace_etabs.py --spawn "C:\\Program Files\\Computers and Structures\\ETABS 22\\ETABS.exe"

Luego en ETABS: Analyze -> Run. Cada llamada a PARDISO se vuelca.
Ctrl+C para terminar.
"""
import argparse, os, sys, struct, datetime, time
import frida

DUMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dump")
os.makedirs(DUMP, exist_ok=True)

# buffers pendientes por (call, what) hasta recibir su blob binario
_pending = {}

def _stamp():
    return datetime.datetime.now().strftime("%H:%M:%S")

def _save(call, what, data):
    path = os.path.join(DUMP, f"call{call:03d}_{what}.bin")
    with open(path, "wb") as f:
        f.write(data)
    return path

def on_message(message, data):
    if message["type"] == "error":
        print("[JS-ERROR]", message.get("description")); return
    p = message["payload"]
    tag = p.get("tag")
    if tag == "info":
        print(f"[{_stamp()}] {p['msg']}")
    elif tag == "call":
        print(f"[{_stamp()}] PARDISO call#{p['call']} phase={p['phase']} "
              f"mtype={p['mtype']} n={p['n']} nrhs={p['nrhs']}")
    elif tag == "matrix":
        print(f"    K  (call#{p['call']}): n={p['n']} nnz={p['nnz']} mtype={p['mtype']}")
        for e in p.get("preview", []):
            print(f"      a[col {e['j']}] = {e['v']:.6g}")
    elif tag == "rhs":
        print(f"    F  (call#{p['call']}): len={p['len']}  primeros: "
              + ", ".join(f"{v:.6g}" for v in p["preview"]))
    elif tag == "sol":
        print(f"    U  (call#{p['call']}): len={p['len']}  primeros: "
              + ", ".join(f"{v:.6g}" for v in p["preview"]))
    elif tag == "blob":
        if data is not None:
            path = _save(p["call"], p["what"], data)
            print(f"      -> volcado {p['what']}  ({len(data)} bytes)  {path}")
    elif tag == "err":
        print(f"    [hook-err {p.get('where')}] {p.get('msg')}")

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--attach", help="nombre o PID del proceso ETABS ya abierto")
    g.add_argument("--spawn",  help="ruta del exe a lanzar y atacar desde el arranque")
    args = ap.parse_args()

    js = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pardiso_hook.js")
    with open(js, "r", encoding="utf-8") as f:
        src = f.read()

    if args.spawn:
        pid = frida.spawn(args.spawn)
        session = frida.attach(pid)
        script = session.create_script(src)
        script.on("message", on_message)
        script.load()
        frida.resume(pid)
        print(f"[{_stamp()}] lanzado y atacado pid={pid}")
    else:
        target = int(args.attach) if args.attach.isdigit() else args.attach
        session = frida.attach(target)
        script = session.create_script(src)
        script.on("message", on_message)
        script.load()
        print(f"[{_stamp()}] atacado {args.attach}")

    print("Corre el analisis en ETABS (Analyze > Run). Ctrl+C para salir.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
