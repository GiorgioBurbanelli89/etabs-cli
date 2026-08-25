// Ojeador del solver de ETABS: engancha Intel MKL PARDISO dentro de CsiGo2_n.dll
// y vuelca K (CSR), F (RHS) y U (solucion) numero por numero.
// Interfaz publica oneMKL PARDISO (LP64), todos los args por puntero (Fortran):
//   pardiso(pt, maxfct, mnum, mtype, phase, n, a, ia, ja, perm, nrhs, iparm, msglvl, b, x, error)
//   arg idx:  0    1      2     3      4    5  6  7   8    9    10    11     12   13 14   15

const MODULE = 'CsiGo2_n.dll';
const MAX_PREVIEW = 12;   // cuantos numeros mostrar en consola por matriz/vector

function resolveExport(mod, name) {
  // Frida 17: el modulo expone find/getExportByName; ademas API global.
  let m = null;
  try { m = Process.findModuleByName(mod); } catch (e) {}
  if (m) {
    try { if (m.findExportByName) { const a = m.findExportByName(name); if (a) return a; } } catch (e) {}
    try { if (m.getExportByName)  { const a = m.getExportByName(name);  if (a) return a; } } catch (e) {}
  }
  try { if (Module.getGlobalExportByName) { const a = Module.getGlobalExportByName(name); if (a) return a; } } catch (e) {}
  try { if (Module.findExportByName) { const a = Module.findExportByName(mod, name); if (a) return a; } } catch (e) {}
  return null;
}

function waitForExport(mod, name, cb) {
  let ticks = 0;
  const tryFind = () => {
    const addr = resolveExport(mod, name);
    if (addr) { cb(addr); return; }
    if (++ticks % 10 === 0) {
      const m = Process.findModuleByName(mod);
      send({tag: 'info', msg: 'esperando ' + name + ' en ' + mod
            + ' (modulo ' + (m ? 'CARGADO' : 'no cargado') + ', tick ' + ticks + ')'});
    }
    setTimeout(tryFind, 200);
  };
  tryFind();
}

// --- Vigilancia ligera de primitivas BLAS (las usa TAMBIEN el solver Standard) ---
// dgetrf(m,n,a,lda,ipiv,info)  dpotrf(uplo,n,a,lda,info)  dgemm(...)
function watchBlas(name, argfmt) {
  const addr = resolveExport(MODULE, name);
  if (!addr) return;
  let cnt = 0;
  Interceptor.attach(addr, {
    onEnter(args) {
      cnt++;
      if (cnt === 1 || cnt % 5000 === 0) {
        let info = {tag: 'blas', fn: name, count: cnt};
        try {
          if (name === 'dgetrf') { info.m = args[0].readInt(); info.n = args[1].readInt(); }
          else if (name === 'dpotrf') { info.n = args[1].readInt(); }
        } catch (e) {}
        send(info);
      }
    }
  });
  send({tag: 'info', msg: 'vigilando BLAS ' + name + ' @ ' + addr});
}
['dgetrf', 'dpotrf', 'dgemm', 'dtrsm', 'dsyrk'].forEach(n => watchBlas(n));

waitForExport(MODULE, 'PARDISO', function (pardisoAddr) {
  send({tag: 'info', msg: 'PARDISO encontrado en ' + pardisoAddr});
  let callNo = 0;

  Interceptor.attach(pardisoAddr, {
    onEnter(args) {
      this.phase = args[4].readInt();
      this.mtype = args[3].readInt();
      this.n     = args[5].readInt();
      this.nrhs  = args[10].readInt();
      this.a  = args[6];
      this.ia = args[7];
      this.ja = args[8];
      this.b  = args[13];
      this.x  = args[14];
      this.call = ++callNo;

      const ph = this.phase;
      send({tag: 'call', call: this.call, phase: ph, mtype: this.mtype,
            n: this.n, nrhs: this.nrhs});

      // Fase de factorizacion (11,12,13,22,23) -> la matriz A=K esta disponible
      if (ph === 11 || ph === 12 || ph === 13 || ph === 22 || ph === 23) {
        try {
          const n = this.n;
          const nnz = this.ia.add(n * 4).readInt() - 1; // ia[n]-1 (1-based)
          // Volcar CSR: ia (n+1 int), ja (nnz int), a (nnz double)
          const iaArr = [], preview = [];
          for (let i = 0; i <= n; i++) iaArr.push(this.ia.add(i * 4).readInt());
          const payload = {tag: 'matrix', call: this.call, phase: ph,
                           mtype: this.mtype, n: n, nnz: nnz};
          // muestra: primeras filas
          for (let i = 0; i < Math.min(MAX_PREVIEW, nnz); i++) {
            preview.push({j: this.ja.add(i * 4).readInt(),
                          v: this.a.add(i * 8).readDouble()});
          }
          payload.preview = preview;
          // bytes crudos para volcado completo a archivo en Python
          send(payload, null);
          send({tag: 'blob', what: 'ia', call: this.call},
               this.ia.readByteArray((n + 1) * 4));
          send({tag: 'blob', what: 'ja', call: this.call},
               this.ja.readByteArray(nnz * 4));
          send({tag: 'blob', what: 'a', call: this.call},
               this.a.readByteArray(nnz * 8));
        } catch (e) { send({tag: 'err', where: 'matrix', msg: '' + e}); }
      }

      // Fase de solve (33, 13, 23) -> RHS b disponible a la entrada
      if (ph === 33 || ph === 13 || ph === 23) {
        try {
          const len = this.n * this.nrhs;
          const prev = [];
          for (let i = 0; i < Math.min(MAX_PREVIEW, len); i++)
            prev.push(this.b.add(i * 8).readDouble());
          send({tag: 'rhs', call: this.call, phase: ph, len: len, preview: prev});
          send({tag: 'blob', what: 'b', call: this.call},
               this.b.readByteArray(len * 8));
        } catch (e) { send({tag: 'err', where: 'rhs', msg: '' + e}); }
      }
    },

    onLeave(retval) {
      const ph = this.phase;
      if (ph === 33 || ph === 13 || ph === 23) {
        try {
          const len = this.n * this.nrhs;
          const prev = [];
          for (let i = 0; i < Math.min(MAX_PREVIEW, len); i++)
            prev.push(this.x.add(i * 8).readDouble());
          send({tag: 'sol', call: this.call, phase: ph, len: len, preview: prev});
          send({tag: 'blob', what: 'x', call: this.call},
               this.x.readByteArray(len * 8));
        } catch (e) { send({tag: 'err', where: 'sol', msg: '' + e}); }
      }
    }
  });
});
