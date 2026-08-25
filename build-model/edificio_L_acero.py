#!/usr/bin/env python3
r"""edificio_L_acero — Construye un edificio de acero en planta L irregular (3 pisos)
usando ETABS OAPI headless y exporta el modelo a .EDB.

Planta L:
  Ala 1: 6m x 4m (3 vanos de 2m en X, 2 vanos de 2m en Y)
  Ala 2: 4m x 6m (2 vanos de 2m en X, 3 vanos de 2m en Y)
  Union en esquina (0,0)

Pisos: 3 (+ roof)
  H1 = 3.5m, H2 = 3.0m, H3 = 3.0m

Columnas: W10x33 (acero A992)
Vigas:    W14x22 (acero A992)

Cargas:
  - Peso propio (auto)
  - Dead adicional: 2.0 kN/m2 (losa)
  - Live: 2.5 kN/m2 (oficina)

Sismo: ELF (opcional)

Uso:
  python edificio_L_acero.py
  python edificio_L_acero.py --show          # ver ETABS
  python edificio_L_acero.py --out mi_modelo.EDB
"""
import os, sys, json, tempfile, argparse
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cli"))

try:
    from etabs_cli import _oapi
except ImportError:
    from etabs_cli_standalone import oapi_start as _oapi_fn
    def _oapi(ver, model=None, hide=True):
        return _oapi_fn(ver, model, hide)

# ── Geometria ──────────────────────────────────────────────────────────────
DX = 2.0          # vano en X [m]
DY = 2.0          # vano en Y [m]
NX1 = 3           # vanos en X del ala 1 (6m)
NY1 = 2           # vanos en Y del ala 1 (4m)
NX2 = 2           # vanos en X del ala 2 (4m)
NY2 = 3           # vanos en Y del ala 2 (6m)
PISOS = 3
ALTURAS = [3.5, 3.0, 3.0]   # H1, H2, H3

# ── Materiales y secciones ────────────────────────────────────────────────
E_ACERO = 200000000.0   # kN/m2 (200 GPa)
NU = 0.3
FY = 344750.0           # kN/m2 (50 ksi = 344.75 MPa)

# ── Cargas ────────────────────────────────────────────────────────────────
Q_DEAD = 2.0    # kN/m2 (losa + acabados)
Q_LIVE = 2.5    # kN/m2 (oficina)

# ── Nodos de la planta L ─────────────────────────────────────────────────
def generar_nodos_planta():
    """Genera coordenadas (x,y) de nodos en planta L."""
    nodos = set()
    # Ala 1: x=[0..NX1*DX], y=[0..NY1*DY]
    for i in range(NX1 + 1):
        for j in range(NY1 + 1):
            nodos.add((round(i * DX, 6), round(j * DY, 6)))
    # Ala 2: x=[0..NX2*DX], y=[0..NY2*DY]
    for i in range(NX2 + 1):
        for j in range(NY2 + 1):
            nodos.add((round(i * DX, 6), round(j * DY, 6)))
    return sorted(nodos)

# ── Viga en L: segmentos rectos ─────────────────────────────────────────
def segmentos_planta():
    """Lista de segmentos [(x1,y1,x2,y2)] en planta."""
    segs = []
    # Ala 1: vigas en X
    for j in range(NY1 + 1):
        for i in range(NX1):
            x1, y1 = round(i * DX, 6), round(j * DY, 6)
            x2, y2 = round((i+1) * DX, 6), round(j * DY, 6)
            segs.append((x1, y1, x2, y2))
    # Ala 1: vigas en Y
    for i in range(NX1 + 1):
        for j in range(NY1):
            x1, y1 = round(i * DX, 6), round(j * DY, 6)
            x2, y2 = round(i * DX, 6), round((j+1) * DY, 6)
            segs.append((x1, y1, x2, y2))
    # Ala 2: vigas en X (excepto las que ya estan en ala 1)
    for j in range(NY2 + 1):
        for i in range(NX2):
            x1, y1 = round(i * DX, 6), round(j * DY, 6)
            x2, y2 = round((i+1) * DX, 6), round(j * DY, 6)
            if (x1, y1, x2, y2) not in segs:
                segs.append((x1, y1, x2, y2))
    # Ala 2: vigas en Y (excepto las que ya estan en ala 1)
    for i in range(NX2 + 1):
        for j in range(NY2):
            x1, y1 = round(i * DX, 6), round(j * DY, 6)
            x2, y2 = round(i * DX, 6), round((j+1) * DY, 6)
            if (x1, y1, x2, y2) not in segs:
                segs.append((x1, y1, x2, y2))
    return segs


def construir Modelo(show=False, out_path=None):
    et, sm = _oapi("19", None, hide=not show)
    try:
        # ── Unidades: kN, m, C ────────────────────────────────────────────
        sm.InitializeNewModel(6)
        sm.File.NewBlank()

        # ── Material acero A992 ───────────────────────────────────────────
        sm.PropMaterial.SetMaterial("A992", 1)  # 1=Steel
        sm.PropMaterial.SetMPIsotropic("A992", E_ACERO, NU, 1.2e-5)
        sm.PropMaterial.SetWeightAndMass("A992", 1, 76.8195, 7.849)  # kN/m3, ton/m3

        # ── Secciones W ───────────────────────────────────────────────────
        # W10x33: d=259mm, bf=254mm, tw=5.8mm, tf=10.9mm
        sm.PropFrame.SetWShape("W10x33", "A992", 0.259, 0.254, 0.0109, 0.0058, 0.0109, 0.0058)
        # W14x22: d=349mm, bf=127mm, tw=5.8mm, tf=7.5mm
        sm.PropFrame.SetWShape("W14x22", "A992", 0.349, 0.127, 0.0075, 0.0058, 0.0075, 0.0058)

        # ── Nodos en planta L ─────────────────────────────────────────────
        nodos_xy = generar_nodos_planta()
        alturas = [0.0]
        h = 0.0
        for dh in ALTURAS:
            h += dh
            alturas.append(round(h, 6))

        # mapa: (x, y, z) -> nombre del nodo ETABS
        nodo_map = {}
        for iz, z in enumerate(alturas):
            for (x, y) in nodos_xy:
                name = f"N_{iz}_{x}_{y}".replace(".", "p")
                sm.PointObj.AddByCoord(x, y, z, name)
                nodo_map[(x, y, z)] = name

        # ── Columnas (W10x33) ─────────────────────────────────────────────
        frame_id = [0]
        def add_frame(x, y, z1, z2, sec, prefix="C"):
            n1 = nodo_map.get((x, y, z1))
            n2 = nodo_map.get((x, y, z2))
            if n1 and n2:
                name = f"{prefix}_{frame_id[0]}"
                sm.FrameObj.AddByPoint(n1, n2, name, sec, name)
                frame_id[0] += 1

        for iz in range(len(alturas) - 1):
            z1, z2 = alturas[iz], alturas[iz + 1]
            for (x, y) in nodos_xy:
                add_frame(x, y, z1, z2, "W10x33", "Col")

        # ── Vigas (W14x22) ────────────────────────────────────────────────
        segs = segmentos_planta()
        for iz in range(1, len(alturas)):
            z = alturas[iz]
            for (x1, y1, x2, y2) in segs:
                n1 = nodo_map.get((x1, y1, z))
                n2 = nodo_map.get((x2, y2, z))
                if n1 and n2:
                    name = f"V_{iz}_{frame_id[0]}"
                    sm.FrameObj.AddByPoint(n1, n2, name, "W14x22", name)
                    frame_id[0] += 1

        # ── Restricciones: base empotrada ─────────────────────────────────
        for (x, y) in nodos_xy:
            name = nodo_map.get((x, y, 0.0))
            if name:
                sm.PointObj.SetRestraint(name, [True, True, True, True, True, True])

        # ── Patrones de carga ─────────────────────────────────────────────
        sm.LoadPatterns.Add("Dead", 1, 0.0, True)    # 1=Dead (peso propio auto)
        sm.LoadPatterns.Add("Live", 3, 0.0, True)    # 3=Live
        sm.LoadPatterns.Add("Ex", 5, 0.0, False)     # 5=Seismic X
        sm.LoadPatterns.Add("Ey", 6, 0.0, False)     # 6=Seismic Y

        # ── Carga Dead adicional (losa) como carga uniforme en vigas ──────
        # Repartir Q_DEAD sobre las vigas del borde
        w_dead = Q_DEAD * DY  # kN/m (carga por metro de viga en direccion Y)
        w_dead_x = Q_DEAD * DX
        for iz in range(1, len(alturas)):
            z = alturas[iz]
            for (x1, y1, x2, y2) in segs:
                n1 = nodo_map.get((x1, y1, z))
                n2 = nodo_map.get((x2, y2, z))
                if not (n1 and n2):
                    continue
                # buscar el frame que conecta n1-n2
                frames = sm.PointObj.GetConnectingFrames(n1, 0)
                if frames and frames[0] > 0:
                    for fn in frames[1]:
                        end2 = sm.FrameObj.GetPoint2(fn)
                        if end2 == n2:
                            is_horizontal = abs(y2 - y1) > 0.01 or abs(x2 - x1) > 0.01
                            if is_horizontal:
                                sm.FrameObj.SetLoadDistributed(fn, "Dead", 1, -Q_DEAD, -Q_DEAD, 0, 0)
                            break

        # ── Carga Live (patio / reparto) ──────────────────────────────────
        for iz in range(1, len(alturas)):
            z = alturas[iz]
            for (x1, y1, x2, y2) in segs:
                n1 = nodo_map.get((x1, y1, z))
                n2 = nodo_map.get((x2, y2, z))
                if not (n1 and n2):
                    continue
                frames = sm.PointObj.GetConnectingFrames(n1, 0)
                if frames and frames[0] > 0:
                    for fn in frames[1]:
                        end2 = sm.FrameObj.GetPoint2(fn)
                        if end2 == n2:
                            sm.FrameObj.SetLoadDistributed(fn, "Live", 1, -Q_LIVE, -Q_LIVE, 0, 0)
                            break

        # ── Guardar ───────────────────────────────────────────────────────
        if out_path is None:
            out_path = os.path.join(tempfile.gettempdir(), "edificio_L_acero.EDB")
        sm.File.Save(out_path)

        # ── Correr analisis ───────────────────────────────────────────────
        try:
            sm.Analyze.SetRunCaseFlag("Modal", False, False)
        except Exception:
            pass
        sm.Analyze.RunAnalysis()

        # ── Resultados ────────────────────────────────────────────────────
        sm.Results.Setup.DeselectAllCasesAndCombosForOutput()
        for nm in sm.LoadCases.GetNameList()[1]:
            try:
                sm.Results.Setup.SetCaseSelectedForOutput(nm)
            except Exception:
                pass

        out = {"model": out_path, "nodos_xy": len(nodos_xy), "alturas": alturas}

        # Modal
        try:
            r = sm.Results.ModalPeriod()
            out["modal"] = [{"mode": i+1, "T": round(r[4][i], 4), "f_hz": round(r[5][i], 4)}
                            for i in range(min(r[0], 6))]
        except Exception as e:
            out["modal"] = {"error": str(e)[:80]}

        # Reacciones
        try:
            rr = sm.Results.BaseReact()
            out["base_react"] = [{"case": rr[1][i],
                                   "Fz": round(rr[6][i], 2),
                                   "Mx": round(rr[7][i], 2),
                                   "My": round(rr[8][i], 2)}
                                  for i in range(rr[0])]
        except Exception as e:
            out["base_react"] = {"error": str(e)[:80]}

        return out

    finally:
        try:
            et.ApplicationExit(False)
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description="Construir edificio L de acero en ETABS")
    ap.add_argument("--show", action="store_true", help="Mostrar ventana de ETABS")
    ap.add_argument("--out", default=None, help="Ruta del .EDB de salida")
    a = ap.parse_args()

    print("=== Construyendo edificio L de acero (3 pisos, irregular en planta) ===")
    print(f"  Ala 1: {NX1*DX}m x {NY1*DY}m  |  Ala 2: {NX2*DX}m x {NY2*DY}m")
    print(f"  Pisos: {PISOS}  |  Alturas: {ALTURAS}")
    print(f"  Columnas: W10x33  |  Vigas: W14x22  |  Material: A992")
    print(f"  Cargas: Dead={Q_DEAD} kN/m2  |  Live={Q_LIVE} kN/m2")
    print()

    out = construir(show=a.show, out_path=a.out)

    print(f"\n=== Modelo guardado en: {out['model']} ===")
    print(f"  Nodos en planta: {out['nodos_xy']}")
    print(f"  Niveles: {out['alturas']}")

    if "modal" in out and isinstance(out["modal"], list):
        print("\n--- Modos naturales ---")
        for m in out["modal"]:
            print(f"  Modo {m['mode']}: T={m['T']}s  f={m['f_hz']}Hz")

    if "base_react" in out and isinstance(out["base_react"], list):
        print("\n--- Reacciones en la base ---")
        for r in out["base_react"]:
            print(f"  {r['case']}: Fz={r['Fz']} kN  Mx={r['Mx']} kN.m  My={r['My']} kN.m")

    print(f"\nArchivo EDB: {out['model']}")
    print("Puedes abrirlo en ETABS 19/22 directamente.")


if __name__ == "__main__":
    main()
