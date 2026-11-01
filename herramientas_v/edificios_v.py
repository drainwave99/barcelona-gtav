"""Edificios de una casilla: volumen real (Catastro + LiDAR), tejado con ortofoto y fachadas en 3D.

alturas(partes, capas, ...)    suelo y techo de cada parte (mediana del LiDAR dentro de la planta)
construir(...)                 geometría de tejados (textura de ortofoto) y de fachadas (fachadas_v)
"""
import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.strtree import STRtree

import fachadas_v

DIST_CALLE = 14.0  # una pared libre a menos de esto del eje de una calle da a la calle


def muestrear(rej, e0, n1, e, n):
    m = rej.shape[0]
    c = np.clip(((np.asarray(e) - e0) / 0.5).astype(int), 0, m - 1)
    f = np.clip(((n1 - np.asarray(n)) / 0.5).astype(int), 0, m - 1)
    return rej[f, c]


def volumenes(partes, capas, e0h, n1h):
    """Lista de dict(p, poli, suelo, techo) de las partes con volumen."""
    out = []
    for p in partes:
        anillos = p["anillos"]
        poli = Polygon(anillos[0], anillos[1:]).buffer(0)
        if poli.is_empty or poli.geom_type != "Polygon" or poli.area < 4:
            continue
        poli = orient(poli, 1.0)  # exterior antihorario: las paredes miran hacia fuera
        ext = np.asarray(poli.exterior.coords)
        suelo = float(np.min(muestrear(capas["suelo"], e0h, n1h, ext[:, 0], ext[:, 1])))
        lo, hi = ext.min(0), ext.max(0)
        es, ns = np.arange(lo[0] + 0.25, hi[0], 0.5), np.arange(lo[1] + 0.25, hi[1], 0.5)
        vals = np.array([])
        if len(es) and len(ns):
            ge, gn = np.meshgrid(es, ns)
            dentro = shapely.contains_xy(poli, ge.ravel(), gn.ravel())
            vals = muestrear(capas["edificio"], e0h, n1h, ge.ravel()[dentro], gn.ravel()[dentro])
            vals = vals[~np.isnan(vals)]
        if len(vals) >= 4 and np.median(vals) > suelo + 2:
            techo = float(np.median(vals))
        elif p["plantas"] > 0:
            techo = suelo + 3.0 * p["plantas"] + 0.5
        else:
            continue
        out.append(dict(p=p, poli=poli, suelo=suelo, techo=techo))
    return out


def pasajes(vols, pasos, capas, e0h, n1h, galibo=4.5):
    """Calles que cruzan por debajo de un edificio (tunnel=building_passage o túneles cortos que se dibujan a
    nivel, como la avinguda d'en Caritg bajo la plaza del Màgic): la parte del edificio sobre la calle se
    separa y su base sube al gálibo sobre la calzada; queda un pasaje con techo de hormigón."""
    if pasos is None or pasos.is_empty:
        return vols
    out = []
    for vol in vols:
        poli = vol["poli"]
        if not poli.intersects(pasos):
            out.append(vol)
            continue
        dentro = poli.intersection(pasos)
        fuera = poli.difference(pasos)
        if dentro.area < 4:
            out.append(vol)
            continue
        for g in shapely.get_parts(fuera):
            if g.geom_type == "Polygon" and g.area >= 2:
                out.append(dict(vol, poli=orient(g, 1.0)))
        for g in shapely.get_parts(dentro):
            if g.geom_type != "Polygon" or g.area < 2:
                continue
            q = shapely.get_coordinates(shapely.segmentize(g.buffer(-0.5) if g.buffer(-0.5).area > 0.5 else g, 1.0))
            calle = float(np.nanmin(muestrear(capas["suelo"], e0h, n1h, q[:, 0], q[:, 1])))
            base = calle + galibo
            if vol["techo"] - base < 1.5:  # cubierta más baja que el gálibo: no se adivina el pasaje
                out.append(dict(vol, poli=orient(g, 1.0)))
                continue
            out.append(dict(vol, poli=orient(g, 1.0), suelo=base, sobre_paso=True))
    return out


def triangular(poligono):
    tris = []
    for t in shapely.constrained_delaunay_triangles(poligono).geoms:
        if t.area <= 1e-4:
            continue
        q = np.asarray(t.exterior.coords)[:3]
        if (q[1, 0] - q[0, 0]) * (q[2, 1] - q[0, 1]) - (q[1, 1] - q[0, 1]) * (q[2, 0] - q[0, 0]) < 0:
            q = q[::-1]
        tris.append(q)
    return tris


def construir(vols, vecinos, info, colores, calles, origen, casilla):
    """vols: volúmenes de la casilla; vecinos: volúmenes de la casilla y alrededores (para medianeras).
    info: {ref: dict(anyo, uso, ...)} del Catastro; colores: {ref: foto analizada};
    calles: STRtree de LineString de calles (o None). origen: esquina SO de la casilla (UTM).
    Devuelve (tejados {v, n, uv, i}, fachadas {textura: arrays})."""
    e0, n0 = origen
    centro = casilla / 2
    arbol = STRtree([v["poli"] for v in vecinos])
    malla = fachadas_v.Malla()
    tv, tuv = [], []
    con_portal = set()
    estilos = {}
    for vol in vols:
        p, poli, suelo, techo = vol["p"], vol["poli"], vol["suelo"], vol["techo"]
        ref = p["ref"]
        if ref not in estilos:
            datos = info.get(ref, {})
            estilos[ref] = fachadas_v.estilo(ref, datos.get("anyo", 0), datos.get("uso", ""), colores.get(ref))
        est = estilos[ref]
        # Tejado (azotea) con la ortofoto de la casilla
        for t in triangular(poli):
            tv.append(np.c_[t[:, 0] - e0 - centro, t[:, 1] - n0 - centro, np.full(3, techo)])
            tuv.append(np.c_[(t[:, 0] - e0) / casilla, (t[:, 1] - n0) / casilla])
        if vol.get("sobre_paso"):  # techo del pasaje: hormigón visto mirando abajo
            for t in triangular(poli):
                q = np.c_[t[::-1, 0] - e0 - centro, t[::-1, 1] - n0 - centro, np.full(3, suelo)]
                g = malla.g.setdefault("pa_hormigon", dict(v=[], n=[], uv=[], color=[], i=[]))
                base = len(g["v"])
                g["v"] += [tuple(x) for x in q]
                g["n"] += [(0, 0, -1.0)] * 3
                g["uv"] += [(x / 3.0, y / 3.0) for x, y in t[::-1]]
                g["color"] += [(200, 200, 200, 255)] * 3
                g["i"].append((base, base + 1, base + 2))
        # Paredes
        anillos = [(np.asarray(poli.exterior.coords), False)] + [(np.asarray(h.coords), True) for h in poli.interiors]
        for anillo, es_patio in anillos:
            s = 0.0
            for a, b in zip(anillo[:-1], anillo[1:]):
                largo = float(np.hypot(*(b - a)))
                if largo < 0.05:
                    continue
                d = (b - a) / largo
                normal = np.array([d[1], -d[0]])
                medio = (a + b) / 2
                sonda = Point(*(medio + normal * 0.6))
                altura_vecino = 0.0
                for k in arbol.query(sonda, predicate="intersects"):
                    otro = vecinos[k]
                    if otro is not vol and not otro.get("sobre_paso"):  # lo que va sobre un pasaje no tapa
                        # la pared de abajo
                        altura_vecino = max(altura_vecino, otro["techo"] - suelo)
                la, lb = a - [e0 + centro, n0 + centro], b - [e0 + centro, n0 + centro]
                if altura_vecino > 0:
                    if altura_vecino < techo - suelo - 0.3:
                        fachadas_v.construir_pared(malla, la, lb, s, suelo, techo, "medianera", est, p["plantas"],
                                                   cubierto=altura_vecino)
                        fachadas_v.peto(malla, la, lb, s, techo, est)
                else:
                    tipo = "patio"
                    if not es_patio and calles is not None:
                        cerca = calles.query(sonda.buffer(DIST_CALLE), predicate="intersects")
                        tipo = "calle" if len(cerca) else "patio"
                    elif not es_patio:
                        tipo = "calle"
                    est["portal"] = tipo == "calle" and ref not in con_portal
                    if est["portal"]:
                        con_portal.add(ref)
                    fachadas_v.construir_pared(malla, la, lb, s, suelo, techo, tipo, est, p["plantas"])
                    fachadas_v.peto(malla, la, lb, s, techo, est)
                s += largo
    tejados = None
    if tv:
        v = np.concatenate(tv)
        tejados = dict(v=v, n=np.tile([0, 0, 1.0], (len(v), 1)), uv=np.concatenate(tuv),
                       i=np.arange(len(v)).reshape(-1, 3))
    return tejados, malla.arrays()


def arbol_calles(osm):
    """STRtree de las calles por donde se anda o circula (no autopistas elevadas ni caminos de monte)."""
    tipos = {"primary", "secondary", "tertiary", "residential", "living_street", "pedestrian", "unclassified",
             "service", "trunk", "primary_link", "secondary_link", "tertiary_link", "footway"}
    lineas = [LineString(v["xy"]) for v in osm["vias"]
              if v["tags"].get("highway") in tipos and not v["tags"].get("bridge") and len(v["xy"]) > 1]
    return STRtree(lineas) if lineas else None
