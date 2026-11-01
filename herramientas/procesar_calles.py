"""Calzadas, aceras con bordillo, calles peatonales, líneas y pasos de cebra como geometría propia.

Como en el juego original: la calle es una malla encima del terreno con texturas que se repiten
(asfalto cada 4 m, panot cada metro), no la foto del suelo estirada.
  - calzada: unión de las calles con coches (ancho de procesar_osm.ANCHO_CALLE), a +0,15 m
  - acera: franja alrededor de la calzada (sin entrar en otras calzadas), a +0,30 m, con bordillo
  - calles peatonales: panot a +0,18 m
  - línea discontinua en el centro de las calles anchas y pasos de cebra (nodos highway=crossing)
Todo partido en casillas de 10 m para que siga la pendiente del terreno.

Salida: datos/generado/calles/calle_FF_CC.npz (blender_edificios.py lo añade a cada trozo de terreno)
  v: vértices (n, 3) en coordenadas del juego; t: triángulos (m, 3); uv: (m, 3, 2); mat: (m,) índice en MATERIALES
"""
import math
import xml.etree.ElementTree as ET

import numpy as np
import shapely
from shapely import STRtree
from shapely.geometry import LineString, box

import config
from procesar_osm import ANCHO_CALLE, PEATONAL, leer_osm, linea

MATERIALES = ["as_asfalto", "ac_panot", "ac_bordillo", "as_linea", "as_cebra"]
ASF, PAN, BOR, LIN, CEB = range(5)
TROZOS = 16
TAM = config.LADO / TROZOS
CASILLA = 10.0  # la malla del terreno tiene un vértice cada ~11,7 m
Z_ASF, Z_ACERA, Z_PEATONAL, Z_MARCA = 0.15, 0.30, 0.18, 0.17
SALIDA = config.DATOS / "generado" / "calles"
E = config.ESCALA

h = np.load(config.DATOS / "elevacion" / "relieve_gta.npy")
N = h.shape[0] - 1


def altura(x, y):
    fx = np.clip((np.asarray(x) + config.MITAD) / config.LADO * N, 0, N - 1e-6)
    fy = np.clip((config.MITAD - np.asarray(y)) / config.LADO * N, 0, N - 1e-6)
    c, f = fx.astype(int), fy.astype(int)
    dx, dy = fx - c, fy - f
    return (h[f, c] * (1 - dx) * (1 - dy) + h[f, np.minimum(c + 1, N)] * dx * (1 - dy)
            + h[np.minimum(f + 1, N), c] * (1 - dx) * dy + h[np.minimum(f + 1, N), np.minimum(c + 1, N)] * dx * dy)


def ancho_acera(tipo):
    return {"primary": 4.0, "secondary": 3.5, "trunk": 2.5, "tertiary": 3.0}.get(tipo, 2.5) * E


def cruces():
    ids = set()
    for _, el in ET.iterparse(config.DATOS / "osm" / "badalona.osm"):
        if el.tag == "node":
            if any(t.get("k") == "highway" and t.get("v") == "crossing" for t in el.iter("tag")):
                ids.add(el.get("id"))
            el.clear()
        elif el.tag in ("way", "relation"):
            el.clear()
    return ids


class Malla:
    def __init__(self):
        self.v, self.t, self.uv, self.mat = [], [], [], []

    def triangulos(self, geom, z, mat, escala_uv):
        """Triangula un (multi)polígono plano a la altura del terreno + z; UV planas en el mundo."""
        if geom.is_empty:
            return
        tri = shapely.constrained_delaunay_triangles(geom)
        for t in shapely.get_parts(tri):
            if t.is_empty or t.area < 1e-4:
                continue
            pts = np.array(t.exterior.coords[:3])
            zs = altura(pts[:, 0], pts[:, 1]) + z
            base = len(self.v)
            self.v += [(x, y, zz) for (x, y), zz in zip(pts, zs)]
            # orden antihorario (normal hacia arriba)
            (x0, y0), (x1, y1), (x2, y2) = pts
            orden = [0, 1, 2] if (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0) > 0 else [0, 2, 1]
            self.t.append([base + i for i in orden])
            self.uv.append([(pts[i][0] / escala_uv, pts[i][1] / escala_uv) for i in orden])
            self.mat.append(mat)

    def quad(self, a, b, c, d, uvs, mat):
        """Cuadrilátero a-b-c-d (vértices 3D) en dos triángulos."""
        base = len(self.v)
        self.v += [a, b, c, d]
        self.t += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
        self.uv += [[uvs[0], uvs[1], uvs[2]], [uvs[0], uvs[2], uvs[3]]]
        self.mat += [mat, mat]

    def guardar(self, ruta):
        if not self.t:
            return False
        np.savez_compressed(ruta, v=np.array(self.v, np.float32), t=np.array(self.t, np.int32),
                            uv=np.array(self.uv, np.float32), mat=np.array(self.mat, np.int8))
        return True


def en_casillas(geom, caja):
    """Parte la geometría en casillas de CASILLA m (para que cada triángulo siga el terreno)."""
    x0, y0, x1, y1 = caja.bounds
    xs = np.arange(x0, x1, CASILLA)
    ys = np.arange(y0, y1, CASILLA)
    cajas = shapely.box(*np.meshgrid(xs, ys), *np.meshgrid(np.minimum(xs + CASILLA, x1), np.minimum(ys + CASILLA, y1)))
    cajas = cajas.ravel()
    cajas = cajas[shapely.intersects(cajas, geom)]
    trozos = shapely.intersection(cajas, geom)
    return [g for g in trozos if not g.is_empty and g.area > 1e-3]


def bordillos(m, acera, calzada):
    """Cara vertical del bordillo donde la acera toca la calzada."""
    borde = shapely.intersection(acera.boundary, calzada.buffer(0.05))
    for parte in shapely.get_parts(borde):
        if parte.geom_type != "LineString":
            continue
        coords = list(parte.coords)
        for (xa, ya), (xb, yb) in zip(coords, coords[1:]):
            largo = math.hypot(xb - xa, yb - ya)
            pasos = max(1, int(largo // CASILLA) + 1)
            for k in range(pasos):
                p0 = (xa + (xb - xa) * k / pasos, ya + (yb - ya) * k / pasos)
                p1 = (xa + (xb - xa) * (k + 1) / pasos, ya + (yb - ya) * (k + 1) / pasos)
                z0, z1 = float(altura(*p0)), float(altura(*p1))
                u0, u1 = 0.0, math.hypot(p1[0] - p0[0], p1[1] - p0[1])
                # dos caras (no se sabe hacia qué lado mira): el juego no pinta la cara de atrás
                for a, b in ((p0, p1), (p1, p0)):
                    za, zb = (z0, z1) if a is p0 else (z1, z0)
                    m.quad((a[0], a[1], za + Z_ASF - 0.05), (b[0], b[1], zb + Z_ASF - 0.05),
                           (b[0], b[1], zb + Z_ACERA), (a[0], a[1], za + Z_ACERA),
                           [(u0, 0), (u1, 0), (u1, 1), (u0, 1)], BOR)


def marcas(m, calles_trozo, cruces_trozo, calzada):
    # Línea discontinua: 3 m pintados, 6 m sin pintar, 15 cm de ancho
    for pts, tipo in calles_trozo:
        if tipo in PEATONAL or ANCHO_CALLE[tipo] < 9:
            continue
        recorrido = 0.0
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            largo = math.hypot(xb - xa, yb - ya)
            if largo < 1e-6:
                continue
            ux, uy = (xb - xa) / largo, (yb - ya) / largo
            t = (-recorrido) % 9.0
            while t + 3.0 <= largo:
                ax, ay = xa + ux * t, ya + uy * t
                bx, by = ax + ux * 3.0, ay + uy * 3.0
                if calzada.contains(shapely.Point((ax + bx) / 2, (ay + by) / 2)):
                    nx, ny = -uy * 0.08, ux * 0.08
                    za, zb = float(altura(ax, ay)) + Z_MARCA, float(altura(bx, by)) + Z_MARCA
                    m.quad((ax - nx, ay - ny, za), (bx - nx, by - ny, zb), (bx + nx, by + ny, zb), (ax + nx, ay + ny, za),
                           [(0, 0), (1, 0), (1, 1), (0, 1)], LIN)
                t += 9.0
            recorrido += largo
    # Pasos de cebra: 3 m a lo largo de la calle, todo el ancho; franjas de 50 cm
    for x, y, ux, uy, ancho in cruces_trozo:
        nx, ny = -uy * ancho / 2, ux * ancho / 2
        ax, ay, bx, by = x - ux * 1.5, y - uy * 1.5, x + ux * 1.5, y + uy * 1.5
        pts = [(ax - nx, ay - ny), (bx - nx, by - ny), (bx + nx, by + ny), (ax + nx, ay + ny)]
        zs = [float(altura(px, py)) + Z_MARCA + 0.005 for px, py in pts]
        franjas = ancho / 1.0
        m.quad(*[(p[0], p[1], z) for p, z in zip(pts, zs)], [(0, 0), (0, 1), (franjas, 1), (franjas, 0)], CEB)


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    gta, vias, _ = leer_osm()
    ids_cruce = cruces()
    coches, peatonales = [], []
    cruces_lista = []
    for refs, tags in vias.values():
        tipo = tags.get("highway")
        if tipo not in ANCHO_CALLE or tags.get("tunnel") == "yes" or tags.get("bridge") == "yes" or tags.get("area") == "yes":
            continue
        pts = linea(gta, refs)
        if len(pts) < 2:
            continue
        if tipo in {"pedestrian", "living_street"}:
            peatonales.append((pts, tipo))
        elif tipo not in PEATONAL:
            coches.append((pts, tipo))
            presentes = [r for r in refs if r in gta]
            for i, r in enumerate(presentes):
                if r in ids_cruce and 0 < i < len(presentes) - 1:
                    (xa, ya), (xb, yb) = gta[presentes[i - 1]], gta[presentes[i + 1]]
                    largo = math.hypot(xb - xa, yb - ya) or 1
                    x, y = gta[r]
                    cruces_lista.append((x, y, (xb - xa) / largo, (yb - ya) / largo, ANCHO_CALLE[tipo] * E))
    lineas = [LineString(p) for p, _ in coches]
    calzadas = shapely.buffer(lineas, [ANCHO_CALLE[t] * E / 2 for _, t in coches], cap_style="flat")
    aceras = shapely.buffer(lineas, [ANCHO_CALLE[t] * E / 2 + ancho_acera(t) for _, t in coches], cap_style="round")
    zonas_peat = shapely.buffer([LineString(p) for p, _ in peatonales], [ANCHO_CALLE[t] * E / 2 for _, t in peatonales])
    arbol = STRtree(aceras)
    arbol_peat = STRtree(zonas_peat)
    cruces_xy = np.array([(c[0], c[1]) for c in cruces_lista]) if cruces_lista else np.zeros((0, 2))
    print(f"{len(coches)} calles con coches, {len(peatonales)} peatonales, {len(cruces_lista)} pasos de cebra")

    for f in range(TROZOS):
        for c in range(TROZOS):
            caja = box(-config.MITAD + c * TAM, config.MITAD - (f + 1) * TAM,
                       -config.MITAD + (c + 1) * TAM, config.MITAD - f * TAM)
            idx = arbol.query(caja.buffer(30))
            m = Malla()
            calzada = shapely.Polygon()
            if len(idx):
                calzada = shapely.union_all(calzadas[idx])
                acera = shapely.difference(shapely.union_all(aceras[idx]), calzada)
                calzada_t, acera_t = calzada.intersection(caja), acera.intersection(caja)
                for g in en_casillas(calzada_t, caja):
                    m.triangulos(g, Z_ASF, ASF, 4.0)
                for g in en_casillas(acera_t, caja):
                    m.triangulos(g, Z_ACERA, PAN, 1.0)
                bordillos(m, acera_t, calzada_t)
                dentro = [(p, t) for (p, t), i in zip(coches, range(len(coches))) if i in set(idx.tolist())]
                sel = (np.abs(cruces_xy[:, 0] - caja.centroid.x) < TAM / 2) & (np.abs(cruces_xy[:, 1] - caja.centroid.y) < TAM / 2) \
                    if len(cruces_xy) else []
                marcas(m, dentro, [cruces_lista[i] for i in np.nonzero(sel)[0]] if len(cruces_xy) else [], calzada_t)
            ip = arbol_peat.query(caja)
            if len(ip):
                peat = shapely.difference(shapely.union_all(zonas_peat[ip]), calzada).intersection(caja)
                for g in en_casillas(peat, caja):
                    m.triangulos(g, Z_PEATONAL, PAN, 1.0)
            m.guardar(SALIDA / f"calle_{f:02d}_{c:02d}.npz")
        print(f"fila {f + 1}/{TROZOS}")
    print(f"Calles en {SALIDA}")


if __name__ == "__main__":
    main()
