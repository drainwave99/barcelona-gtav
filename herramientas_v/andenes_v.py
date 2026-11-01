"""Andenes de las estaciones de Renfe/Rodalies, FGC y paradas del tranvía (railway=platform de OSM).

Plataforma de hormigón a 0,68 m sobre la vía (0,25 m en el tranvía), losa de baldosa por arriba con la
línea amarilla de seguridad a 0,6 m del borde, y la marquesina (covered=yes): cubierta a 3,4 m sobre el andén
con pilares cada 10 m por el eje. Los subterráneos no se dibujan.

construir(osm, casilla, suelo, centro) -> (arrays por textura, colisión (v, tris) en coordenadas locales)
"""
import numpy as np
import shapely
from shapely.geometry import LineString, Polygon

import calles_v
import fachadas_v

ALTO_TREN, ALTO_TRANVIA = 0.68, 0.25
MARQUESINA = 3.4
BLANCO = (255, 255, 255, 255)


def _poligono(v):
    t = v["tags"]
    xy = np.asarray(v["xy"], float)
    if len(xy) > 3 and np.allclose(xy[0], xy[-1]):
        p = Polygon(xy).buffer(0)
    else:
        ancho = calles_v._num(t.get("width")) or (2.5 if t.get("tram") == "yes" else 4.0)
        p = LineString(xy).buffer(ancho / 2, cap_style="flat")
    return p if p.is_valid and p.area > 2 else None


def _triangulos(geom):
    tri = shapely.get_parts(shapely.constrained_delaunay_triangles(geom))
    return np.array([np.asarray(t.exterior.coords)[:3] for t in tri if t.area > 1e-4]).reshape(-1, 3, 2)


def _plano(m, tex, geom, z, centro, escala, abajo=False):
    """Superficie horizontal de geom a la cota z (mirando arriba, o abajo si abajo)."""
    for parte in shapely.get_parts(geom):
        if parte.geom_type != "Polygon" or parte.is_empty:
            continue
        for a, b, c in _triangulos(parte):
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) < 0:
                b, c = c, b
            if abajo:
                b, c = c, b
            q = [np.r_[p - centro, z] for p in (a, b, c)]
            uv = [tuple(p / escala) for p in (a, b, c)]
            g = m.g.setdefault(tex, dict(v=[], n=[], uv=[], color=[], i=[]))
            base = len(g["v"])
            g["v"] += [tuple(x) for x in q]
            g["n"] += [(0, 0, -1.0 if abajo else 1.0)] * 3
            g["uv"] += uv
            g["color"] += [BLANCO] * 3
            g["i"].append((base, base + 1, base + 2))


def _paredes(m, tex, poli, z0, z1, centro):
    anillos = [poli.exterior] + list(poli.interiors)
    for k, anillo in enumerate(anillos):
        q = np.asarray(anillo.coords)
        if anillo.is_ccw == (k > 0):  # exterior antihorario, huecos horarios: la cara vista hacia fuera
            q = q[::-1]
        u = 0.0
        for a, b in zip(q[:-1], q[1:]):
            largo = float(np.linalg.norm(b - a))
            if largo < 0.02:
                continue
            d = (b - a) / largo
            nrm = (d[1], -d[0], 0.0)
            m.quad(tex, [np.r_[a - centro, z0], np.r_[b - centro, z0], np.r_[b - centro, z1], np.r_[a - centro, z1]],
                   nrm, [(u / 2, z0 / 2), ((u + largo) / 2, z0 / 2), ((u + largo) / 2, z1 / 2), (u / 2, z1 / 2)], BLANCO)
            u += largo


def construir(osm, casilla, suelo, centro):
    m = fachadas_v.Malla()
    centro = np.asarray(centro, float)
    col_v, col_t = [], []
    railes = [r for r in osm["vias"] if r["tags"].get("railway") in ("rail", "light_rail", "tram", "narrow_gauge")
              and len(r["xy"]) > 1]
    for v in osm["vias"] + osm["areas"]:
        t = v["tags"]
        if t.get("railway") != "platform" or len(v["xy"]) < 2:
            continue
        if t.get("tunnel") not in (None, "no") or t.get("location") == "underground" or \
                (calles_v._num(t.get("layer")) or 0) < 0 or (calles_v._num(t.get("level")) or 0) < 0 or \
                t.get("subway") == "yes":
            continue
        poli = _poligono(v)
        if poli is None:
            continue
        c = poli.centroid
        if not shapely.contains_xy(casilla, c.x, c.y):
            continue  # cada andén entero en la casilla de su centro
        tranvia = t.get("tram") == "yes" and t.get("train") != "yes"
        # la vía: lo más bajo del terreno junto al andén; el LiDAR ya trae el andén como suelo, así que la cota
        # es la mayor entre lo medido encima y la altura reglamentaria sobre la vía
        borde = shapely.get_coordinates(shapely.segmentize(poli.buffer(2.0).boundary, 2.0))
        x0, y0, x1, y1 = poli.bounds
        gx, gy = np.meshgrid(np.arange(x0, x1, 1.0) + 0.5, np.arange(y0, y1, 1.0) + 0.5)
        ok = shapely.contains_xy(poli.buffer(-0.5), gx, gy)
        dentro = np.c_[gx[ok], gy[ok]] if ok.any() else np.array([[c.x, c.y]])
        # la cota de la vía, sobre las vías de OSM junto al andén (al otro lado puede haber un paso inferior)
        cerca = poli.buffer(6.0)
        sobre = [shapely.get_coordinates(shapely.segmentize(LineString(r["xy"]).intersection(cerca), 1.0))
                 for r in railes if cerca.intersects(LineString(r["xy"]))]
        sobre = np.concatenate(sobre) if sobre and sum(len(q) for q in sobre) else borde
        z_via = float(np.percentile(suelo.altura(sobre[:, 0], sobre[:, 1]), 30))
        z_med = float(np.percentile(suelo.altura(dentro[:, 0], dentro[:, 1]), 75))
        alto = ALTO_TRANVIA if tranvia else ALTO_TREN
        z_top = max(z_med + 0.03, z_via + alto)
        if z_top - z_via > 2.5:  # el andén está sobre un muro o en otro nivel: no se adivina
            continue
        partes = [p for p in shapely.get_parts(poli) if p.geom_type == "Polygon"]
        for p in partes:
            _plano(m, "vi_anden", p, z_top, centro, 2.0)
            _paredes(m, "vi_hormigon", p, z_via - 0.3, z_top, centro)
            seguridad = p.buffer(-0.5).difference(p.buffer(-0.6))
            if not seguridad.is_empty:
                _plano(m, "vi_amarillo", seguridad, z_top + 0.006, centro, 1.0)
        # colisión: la losa de arriba y las paredes
        for p in partes:
            for a, b, cc in _triangulos(p):
                base = len(col_v)
                col_v += [np.r_[q - centro, z_top] for q in (a, b, cc)]
                col_t.append((base, base + 1, base + 2))
            q = np.asarray(p.exterior.coords)
            for a, b in zip(q[:-1], q[1:]):
                base = len(col_v)
                col_v += [np.r_[a - centro, z_via - 0.3], np.r_[b - centro, z_via - 0.3],
                          np.r_[b - centro, z_top], np.r_[a - centro, z_top]]
                col_t += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
        if t.get("covered") == "yes" or t.get("shelter") == "yes":
            _marquesina(m, poli, z_top, centro, col_v, col_t)
    if not m.g:
        return {}, None
    return m.arrays(), (np.array(col_v, float), np.array(col_t, int))


def _marquesina(m, poli, z_top, centro, col_v, col_t):
    """Cubierta 0,4 m más pequeña que el andén por cada lado, a MARQUESINA m, con pilares por el eje largo."""
    techo = poli.buffer(-0.4)
    if techo.is_empty or techo.area < 4:
        return
    z = z_top + MARQUESINA
    _plano(m, "vi_cubierta", techo, z + 0.15, centro, 4.0)
    _plano(m, "vi_cubierta", techo, z, centro, 4.0, abajo=True)
    for p in shapely.get_parts(techo):
        if p.geom_type == "Polygon":
            _paredes(m, "vi_hierro", p, z, z + 0.15, centro)
    r = np.asarray(techo.minimum_rotated_rectangle.exterior.coords)[:4]
    lados = [np.linalg.norm(r[(k + 1) % 4] - r[k]) for k in range(4)]
    k = int(np.argmax(lados[:2]))
    a = (r[k] + r[(k + 3) % 4]) / 2  # eje largo por el medio del rectángulo
    b = (r[(k + 1) % 4] + r[(k + 2) % 4]) / 2
    largo = float(np.linalg.norm(b - a))
    eje = (b - a) / (largo + 1e-9)
    lat = np.array([-eje[1], eje[0]])
    for d in np.arange(min(2.0, largo / 2), largo, 10.0):
        c = a + eje * d
        if not shapely.contains_xy(techo, c[0], c[1]):
            continue
        esq = [c + eje * sx * 0.12 + lat * sy * 0.12 for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        for j in range(4):
            p0, p1 = esq[j], esq[(j + 1) % 4]
            d2 = p1 - p0
            nrm = (d2[1] / 0.24, -d2[0] / 0.24, 0.0)
            m.quad("vi_hierro", [np.r_[p0 - centro, z_top], np.r_[p1 - centro, z_top], np.r_[p1 - centro, z],
                                 np.r_[p0 - centro, z]], nrm,
                   [(0, 0), (0.24, 0), (0.24, MARQUESINA), (0, MARQUESINA)], BLANCO)
            base = len(col_v)
            col_v += [np.r_[p0 - centro, z_top], np.r_[p1 - centro, z_top], np.r_[p1 - centro, z], np.r_[p0 - centro, z]]
            col_t += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
