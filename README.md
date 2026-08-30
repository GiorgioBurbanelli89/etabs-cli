# etabs-cli

**El CLI que ETABS no trae.** Ejecuta ETABS desde la terminal, captura la matriz de rigidez del solver, y re-resuelve sin ETABS.

```
etabs-cli version modelo.EDB
etabs-cli run modelo.EDB --results react,modal
etabs-cli export modelo.EDB modelo.e2k --ver 22
etabs-cli import modelo.e2k modelo.EDB --ver 22
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

### `export` — ETABS -> `.e2k` (texto)

Saca el modelo a texto E2K sin abrir la interfaz. Es lo que en la GUI es
`File > Export > ETABS .e2k Text File`.

```bash
etabs-cli export modelo.EDB modelo.e2k --ver 22
```

Salida:
```json
{
  "model": "...\CHONE PROPUESTA.EDB",
  "e2k":   "...\chone.e2k",
  "via":   "ExportFile",
  "bytes": 680150
}
```

**Dos caminos, y el CLI elige solo** (`via` te dice cuál usó):

| `via` | qué hace | cuándo |
|---|---|---|
| `ExportFile` | `File.Save(.EDB)` y luego `File.ExportFile(out, 1)` (`1 = eFileTypeIO_TextFile`, `2` = Excel) | ETABS 22 |
| `$et` | copia el `.$et` que ETABS escribe **siempre** al guardar: es el mismo texto e2k, byte a byte | ETABS 19, cuya OAPI v1 revienta con `RPC_E_SERVERFAULT` al llamar `ExportFile` |

**Por qué el `File.Save` va antes:** `ExportFile` escribe a partir del modelo
*guardado*, no del que está en memoria. Sin ese Save devuelve ≠0 o sale vacío.

**No toca tu modelo:** el CLI nunca guarda sobre el `.EDB` de origen — hacerlo
con un motor más nuevo te lo convertiría de versión sin avisar. Si el destino
choca con el origen, el `.EDB` de trabajo se va a un temporal.

### `import` — `.e2k` -> ETABS (`.EDB`)

```bash
etabs-cli import modelo.e2k modelo.EDB --ver 22

# importar y dejarlo ya resuelto
etabs-cli import modelo.e2k modelo.EDB --ver 22 --run
```

**El detalle que hace falta saber:** `OpenFile` abre un `.e2k` igual que un
`.EDB` — la OAPI no distingue. Pero el modelo queda *sin guardar*, y así el
solver no corre: `RunAnalysis()` devuelve 1 y **todos los resultados salen en
cero**. Por eso el CLI hace `File.Save(<.EDB>)` apenas detecta que abrió texto.
Eso vale también para `run`, así que **`run` acepta un `.e2k` directo**:

```bash
etabs-cli run modelo.e2k --ver 22 --results react,modal
```

### Validación del round-trip (medido, ETABS 22)

`edb/CHONE PROPUESTA.EDB` exportado a `.e2k` y vuelto a analizar, contra el
`.EDB` original analizado directo:

| | EDB original | .e2k exportado | dif |
|---|---:|---:|---:|
| T1 [s] | 0.579925 | 0.579916 | 9.0e-06 |
| T2 [s] | 0.522720 | 0.522714 | 6.4e-06 |
| T3 [s] | 0.520561 | 0.520529 | 3.2e-05 |
| Fz Dead [kN] | 3510.1274 | 3510.1273 | 9.6e-05 |
| Fz Live [kN] | 1057.1569 | 1057.1569 | 2.1e-05 |
| Fz Super Dead [kN] | 1792.1653 | 1792.1653 | 6.5e-05 |

La diferencia (1e-5) es el redondeo del texto: el `.e2k` escribe las
coordenadas con menos cifras que el binario. El modelo no pierde nada.

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
│   ├── etabs_cli.py              # 7 subcommands: version, convert, export, import, run, capture, solve
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

---

## Lo que ETABS trae de fábrica (medido con `cli/defaults_csi.py`)

```bash
python cli/defaults_csi.py etabs      # o sin argumento: los tres motores
```

| ajuste | ETABS 22.6 | SAP2000 24.1 | SAFE 20 |
|---|---|---|---|
| **end length offset** | **auto** | manual (0,0,0) | auto |
| **edge constraint** (área) | **True** | False | — |
| releases | ninguno | ninguno | ninguno |
| modificadores de barra | 8 × 1.0 | (vacío) | 8 × 1.0 |
| insertion point | 10 (centroide) | 10 | 10 |
| output stations | viga cada **0.5 m** · columna 3 | igual | igual |
| materiales de serie | 4 | 2 | 4 |
| patrones / casos | Dead, Live / + Modal | DEAD / + MODAL | Dead, Live |
| diafragmas | D1 | no tiene | D1 |

Y el detalle que descuadra pesos: el hormigón de serie es **imperial**,
`4000Psi` a **23.563122 kN/m³** (150 lb/ft³). `SetMaterial` + `SetMPIsotropic`
definen módulo y Poisson pero **no el peso**.

⚠️ Y hay un **segundo hormigón**: ETABS crea `4000Psi` por su cuenta y es el que
usa el **DECK**, porque `SetDeckFilled` reemplaza el material que le pasas en
`SetDeck`. Hay que fijar el peso de **todos** los materiales de hormigón, y
después de crear las áreas.

## Cinco gotchas de la OAPI, todos medidos

**1. ETABS OCULTO + un cuadro de diálogo = cuelgue eterno.** `obj.Hide()` y un
aviso modal (`Error saving mesh information.`) dejan la llamada COM esperando
para siempre — medido: Python con 1.1 s de CPU en media hora, sin error ni
timeout. Arrancar visible, o dejar un cierra-diálogos que pulse Aceptar:
`SendMessage(hBoton, BM_CLICK = 0x00F5)` sobre la ventana cuyo título es
exactamente `ETABS`.

**2. Un caso de carga que NO existe se pide igual que uno que sí.** Devuelve
CERO resultados con todos los casos en OK:

```
estado: Modal=OK, Dead=OK, Live=OK, SDL=OK, Lroof=OK, ...
Uz max = 0.00 mm    Suma Rz = 0.0 kN
```

Para una COMBINACIÓN es `SetComboSelectedForOutput`, no
`SetCaseSelectedForOutput`.

**3. `File.Save` antes de `RunAnalysis` + `ApplicationExit(False)` = `.EDB` sin
resultados.** Los ficheros del solver (`.Y`, `.K_0`, `.OUT`) quedan en disco pero
ETABS no los da por buenos al reabrir el modelo. Guardar DESPUÉS de analizar.

**4. Los offsets automáticos no se leen con `GetEndLengthOffset`**: con
`auto = True` devuelve 0 en las longitudes. Están en la tabla
`Frame Assignments - End Length Offsets`, vía `DatabaseTables`. Su regla:

```
viga que llega a una COLUMNA  ->  medio ancho de la columna     0.075
columna que llega a una VIGA  ->  el canto de la viga           0.25
resto                         ->  0        (Rigid Factor = 0 en todas)
```

Con `rz = 0` el brazo **no rigidiza** — `Lf = L − rz·(offI+offJ)` da `Lf = L` —
pero ETABS **no pesa** el tramo de VIGA que cae dentro (el de columna sí).

**5. La masa manda sobre el peso.** `SetWeightAndMass` guarda la MASA y ETABS
deriva el peso con **g = 9.80665**. Si le das la masa como `γ/9.81`, el peso
efectivo sale 23.9918 en vez de 24.0.
