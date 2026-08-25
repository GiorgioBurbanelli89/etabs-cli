#!/usr/bin/env python3
r"""Frida-spawn del Driver + hook a los exports de CsiGo2 (que YA decompilamos) para ver
EN QUE funcion del motor aborta el Driver standalone. Usa el modelo fresco de cold_build."""
import os, sys, time, frida
sys.stdout.reconfigure(encoding="utf-8")
ENG = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\engine_etabs19"
DRV = os.path.join(ENG, "CSI.SAPFire.Driver.exe")
OUT = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\coldbuild_out\drv_trace_out.txt"
MODEL = r"C:\Users\j-b-j\Documents\Hekatan Calc 1.0.0\hekatan-etabs-bridge\coldbuild_out\cold_build.Y_"
# args como ETABS (label completo) pero sin pipe (GUID vacio) -> bail rapido, justo lo que queremos trazar
ARGV = [DRV, "0", OUT, MODEL, "ETABS Ultimate 64-bit 19.1.0 Build 2420", "", "4", "7", "True"]

JS = r"""
'use strict';
var hits = [];
function hookByName(names){
  var m = Process.findModuleByName('CsiGo2.dll'); if(!m) { send({t:'log',m:'CsiGo2 not loaded yet'}); return 0; }
  var n = 0;
  m.enumerateExports().forEach(function(e){
    if (e.type!=='function') return;
    var low = e.name.toLowerCase();
    if (names.some(function(k){return low.indexOf(k)>=0;})){
      try { Interceptor.attach(e.address,{onEnter:function(){ send({t:'call', fn:e.name}); }}); n++; } catch(x){}
    }
  });
  return n;
}
// esperar a que CsiGo2 cargue, luego hookear run/solve/gate/build/case
var tries=0;
var iv = setInterval(function(){
  tries++;
  var m = Process.findModuleByName('CsiGo2.dll');
  if (m){
    clearInterval(iv);
    var n = hookByName(['jobrun','model_run','modelrun','serialrun','getbuild','license','setallto','settorun','issetto','jobcompute','run','solve','analy','formk','stiff']);
    // gate de capacidad por RVA
    
    send({t:'log', m:'hooked '+n+' exports en CsiGo2'});
  } else if (tries>200){ clearInterval(iv); send({t:'log',m:'CsiGo2 nunca cargo'}); }
}, 5);
"""

dev = frida.get_local_device()
pid = dev.spawn(ARGV, cwd=ENG)
ses = dev.attach(pid)
scr = ses.create_script(JS)
seq = []
def on_msg(msg, data):
    if msg.get("type")=="send":
        p = msg["payload"]
        if p.get("t")=="call": seq.append(p["fn"])
        elif p.get("t")=="gate": seq.append(f"<GATE ret={p['ret']}>")
        elif p.get("t")=="log": print("  [js]", p["m"])
scr.on("message", on_msg)
scr.load()
dev.resume(pid)
time.sleep(4)
try: ses.detach()
except Exception: pass
print(f"\n=== secuencia de llamadas al motor (CsiGo2) del Driver ({len(seq)}) ===")
for i,s in enumerate(seq[:200]): print(f"  {i+1:3} {s}")
