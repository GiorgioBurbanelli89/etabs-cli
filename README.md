# etabs-cli

**El CLI que ETABS no trae.** Ejecuta ETABS desde la terminal, captura la matriz de rigidez del solver, y re-resuelve sin ETABS.

```
etabs-cli version modelo.EDB
etabs-cli run modelo.EDB --results react,modal
etabs-cli capture modelo.EDB --out cap1
etabs-cli solve --dump cap1
```

## Que es esto

ETABS es un programa de analisis estructural que **solo funciona con interfaz grafica**. No trae un CLI, no tiene batch mode, no puedes correrlo desde un script.

**etabs-cli** resuelve eso: ejecuta ETABS headless (sin ventana), extrae resultados via OAPI, y opcionalmente captura lo que el solver (PARDISO) hace por dentro.

## Instalacion

### Requisitos

- Windows 10/11
- Python 3.8+
- ETABS 19 o 22 instalado
- `pip install comtypes frida-tools` (solo si usas `capture`)

### Instalar como CLI

```bash
pip install -e .
# o compilar a .exe:
pyinstaller --onefile cli/etabs_cli_standalone.py --name etabs-cli
```

### Sin instalar

```bash
python cli/etabs_cli.py version modelo.EDB
```

## Comandos

### `version` — Leer version de un modelo

No abre ETABS. Lee los primeros bytes del archivo `.EDB`.

```bash
etabs-cli version modelo.EDB
```

Salida:
```json
{
  "program": "ETABS",
  "format": "19.04",
  "program_version": "19.2.0",
  "family": "19"
}
```

### `convert` — Convertir entre versiones de ETABS

Convierte un modelo de ETABS 19 a 22 (o viceversa).

```bash
# v19 -> v22 (upgrade directo)
etabs-cli convert modelo_v19.EDB modelo_v22.EDB --to 22

# v22 -> v19 (downgrade via E2K)
etabs-cli convert modelo_v22.EDB modelo_v19.EDB --to 19 --via-e2k
```

### `run` — Correr analisis y extraer resultados

Abre ETABS en background, corre el analisis, y extrae resultados a JSON.

```bash
# Reacciones base + modos
etabs-cli run modelo.EDB --ver 19 --results react,modal

# Guardar a archivo
etabs-cli run modelo.EDB --ver 19 --results react,modal --json resultados.json

# Ver ETABS mientras corre (debug)
etabs-cli run modelo.EDB --ver 19 --results react --show
```

Resultados disponibles:
- `react` — Reacciones en la base (Fx, Fy, Fz, Mx, My, Mz)
- `modal` — Periodos y frecuencias naturales
- `frames` — Fuerzas en barras (P, V2, V3, T, M2, M3)
- `shells` — Fuerzas en placas (M11, M22, M12)

Salida:
```json
{
  "model": "modelo.EDB",
  "ver": "19.2.0",
  "modal": [
    {"mode": 1, "T": 1.234, "f": 0.810},
    {"mode": 2, "T": 0.876, "f": 1.141}
  ],
  "react": [
    {"case": "Dead", "Fx": 0.0, "Fy": 0.0, "Fz": -150.0, "Mx": 0.0, "My": 0.0, "Mz": 0.0}
  ]
}
```

### `capture` — Capturar K/F/U del solver (avanzado)

Este es el comando "power user". No solo corre el analisis — **engancha PARDISO con Frida** y captura:

- **K** — Matriz de rigidez global (en formato CSR: ia, ja, a)
- **F** — Vector de fuerzas (RHS)
- **U** — Vector de desplazamientos (solucion)

```bash
etabs-cli capture modelo.EDB --ver 19 --out dump_cap1
```

Esto crea una carpeta `dump_cap1/` con archivos `.bin` que puedes re-resolver offline.

### `solve` — Re-resolver SIN ETABS

Toma los dumps capturados y resuelve `K * U = F` con scipy. **No necesita ETABS instalado.**

```bash
etabs-cli solve --dump dump_cap1
```

Para cambiar el RHS (carga):
```bash
etabs-cli solve --dump dump_cap1 --rhs 5
```

## Arquitectura

```
┌─────────────────────────────────────────────────┐
│  etabs-cli (Python)                             │
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐ │
│  │ version  │  │   run    │  │   capture     │ │
│  │ convert  │  │          │  │               │ │
│  └────┬─────┘  └────┬─────┘  └───────┬───────┘ │
│       │              │                │         │
│       ▼              ▼                ▼         │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐ │
│  │  bytes   │  │  OAPI    │  │  OAPI + Frida │ │
│  │  reader  │  │  (headless)│  │  (PARDISO hook)│ │
│  └──────────┘  └──────────┘  └───────┬───────┘ │
│                                      │         │
└──────────────────────────────────────┼─────────┘
                                       │
                              ┌────────▼────────┐
                              │  ETABS.exe      │
                              │  (headless)     │
                              │                 │
                              │  CsiGo2_n.dll   │
                              │  └─ PARDISO     │
                              └─────────────────┘
```

## Estructura del repo

```
etabs-cli/
├── cli/                    # CLI principal
│   ├── etabs_cli.py              # 5 subcommands: version, convert, run, capture, solve
│   ├── etabs_cli_standalone.py   # Todo inline (sin imports) → PyInstaller .exe
│   └── etabs_cli_full.py         # Headless OAPI + Frida capture de K/F/U
├── frida/                  # Hooks Frida
│   └── pardiso_hook.js           # Intercepta PARDISO en CsiGo2_n.dll
├── solver/                 # Solver offline (sin ETABS)
│   ├── hekatan_solve.py          # CLI: capture/solve/readk
│   ├── solve_offline.py          # K*U=F con scipy
│   ├── read_dump.py              # Reconstruir K desde .bin
│   └── hekatan_solver.py         # FEM solver propio
├── cold-build/             # Workflow headless completo
│   ├── cold_build.py             # Construir modelo sin ETABS
│   ├── cold_cli.py               # CLI del cold-build
│   └── cold_build_runnow.py      # Build + solve de una
├── tracing/                # Observadores de ETABS
│   ├── etabs_hidden.py           # ETABS oculto via OAPI
│   ├── watch_solver.py           # Monitorear PARDISO
│   └── keep_etabs.py             # Mantener ETABS vivo
├── build-model/            # Construccion de modelos
├── disasm/                 # Documentacion de ingenieria inversa
├── torsion/                # Analisis de torsion
├── tests/                  # Tests y QA
└── docs/
    └── NATIVE_SOLVE_RECETA.md    # Receta para native solve
```

## Ejemplo completo: validar un modelo

```bash
# 1. Verificar que el modelo es v19
etabs-cli version modelo.EDB

# 2. Correr analisis y guardar resultados
etabs-cli run modelo.EDB --ver 19 --results react,modal --json resultados.json

# 3. Capturar la matriz de rigidez
etabs-cli capture modelo.EDB --ver 19 --out dump_validacion

# 4. Re-resolver offline para verificar
etabs-cli solve --dump dump_validacion
```

## Compilar a .exe (standalone)

El `etabs_cli_standalone.py` tiene **todo el codigo inline** (cero imports locales) para que PyInstaller lo compile a un solo `.exe`:

```bash
pyinstaller --onefile cli/etabs_cli_standalone.py --name etabs-cli
# El .exe queda en dist/etabs-cli.exe
```

El `.exe` funciona en cualquier PC con ETABS instalado, sin necesidad de Python.

## FAQ

### ETABS no abre / falla el OAPI

- Verifica que ETABS este instalado en la ruta por defecto
- Prueba con `--show` para ver la ventana de ETABS
- Revisa que no haya otra instancia de ETABS corriendo

### Frida no engancha PARDISO

- Verifica que `frida-tools` este instalado: `pip install frida-tools`
- Asegurate de que `CsiGo2_n.dll` este en la carpeta de ETABS
- El solver debe estar en modo "Multi-threaded (PARDISO)" + "GUI (in-process)"

### No se generan archivos .bin en capture

- Verifica que el modelo tenga analisis pendiente
- Revisa el stderr para ver si Frida se enganch correctamente
- El modelo debe tener al menos un caso de carga

## Legalidad

Este repositorio contiene **solo codigo del autor** (Python, JavaScript, Markdown). No contiene binarios de CSI, ETABS ni ningun archivo propietario.

La ingenieria inversa de software es legal en la mayoria de jurisdicciones cuando:
- Se realiza sobre software que el usuario adquirio legalmente
- El objetivo es interoperabilidad, educacion o investigacion
- No se redistribuye el codigo propietario original

Referencias: DMCA 1201(f) (EE.UU.), Decision 351 CAN (Ecuador/Colombia/Peru), Directive 2009/24/EC (UE).

## Licencia

MIT
