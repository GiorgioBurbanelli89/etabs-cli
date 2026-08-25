# etabs-cli

**El CLI que ETABS no trae.** Headless OAPI, Frida hooks, capture/solve offline.

## Estructura

```
etabs-cli/
├── cli/              # CLI principal
│   ├── etabs_cli.py              # Subcommands: version, convert, run, capture, solve
│   ├── etabs_cli_standalone.py   # Todo inline → PyInstaller .exe
│   └── etabs_cli_full.py         # Headless OAPI + Frida capture de K/F/U
├── frida/            # Hooks Frida
│   └── pardiso_hook.js           # Hook para CsiGo2_n.dll!PARDISO + BLAS
├── solver/           # Solver offline (sin ETABS)
│   ├── hekatan_solve.py          # CLI capture/solve/readk
│   ├── solve_offline.py          # Resolve K·U=F con scipy
│   ├── read_dump.py              # Reconstruir K/F/U desde .bin dumps
│   ├── hekatan_solver.py         # Hekatan FEM solver
│   ├── native_solve.py           # Solve a nivel DLL
│   ├── native_solve_v2.py        # v2
│   └── etabs_coldsolve.py        # Cold solve
├── cold-build/       # Workflow cold-build (sin ETABS GUI)
│   ├── cold_build.py
│   ├── cold_cli.py
│   ├── cold_build_runnow.py
│   ├── cold_build_trace.py
│   ├── cold_compute_pipe.py
│   ├── cold_inproc_solve.py
│   └── cold_kform_min.py
├── tracing/          # Observadores/tracing de ETABS
│   ├── trace_etabs.py
│   ├── trace_v19.py
│   ├── trace_driver.py
│   ├── trace_driver_piped.py
│   ├── etabs_hidden.py           # ETABS oculto via OAPI
│   ├── etabs_quiet.py
│   ├── etabs_live_results.py
│   ├── keep_etabs.py
│   └── watch_solver.py           # Ojeador de PARDISO
├── build-model/      # Construccion de modelos
│   ├── build_and_validate.py
│   ├── build_coupled_capture.py
│   ├── build_single_shell.py
│   ├── build_3x3_walls.py
│   ├── make_cantilever.py
│   ├── make_formed.py
│   └── make_notrun.py
├── disasm/           # Ingenieria inversa (documentacion)
│   ├── disasm_full_settorun.py
│   ├── disasm_gate.py
│   ├── disasm_setter_v19.py
│   ├── find_gate_pattern.py
│   ├── find_servicewire.py
│   ├── patch_gate.py
│   └── crack_v19.py
├── torsion/          # Analisis de torsion
│   ├── torsion_compat_iter.py
│   ├── torsion_debug.py
│   ├── torsion_twist_check.py
│   └── torsion_v30.py
├── tests/            # Tests y QA
│   ├── test_run_computes.py
│   ├── test_run_spawn.py
│   ├── test_serialrun.py
│   ├── test_torun.py
│   ├── qa_control.py
│   └── validar_vs_sapfire.py
└── docs/
    └── NATIVE_SOLVE_RECETA.md    # Receta para native solve
```

## Uso rapido

```bash
# Version de un modelo
etabs-cli version modelo.EDB

# Convertir v19 -> v22
etabs-cli convert v19.EDB out.EDB --to 22

# Correr analisis y extraer resultados
etabs-cli run modelo.EDB --ver 19 --results react,modal --json out.json

# Re-resolver K capturada SIN ETABS
etabs-cli solve --dump cap1 --rhs 5
```

## Standalone (.exe)

```bash
# Compilar a .exe con PyInstaller
pyinstaller --onefile cli/etabs_cli_standalone.py --name etabs-cli
```

## Requisitos

- Python 3.8+
- `comtypes` (para OAPI de ETABS)
- ETABS 19 o 22 instalado (para `run`, `convert`)
- Frida (para `frida/pardiso_hook.js`)

## Licencia

MIT
