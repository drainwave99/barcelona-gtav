"""Calles a pie de calle: calzada, aceras con bordillo, aparcamientos con sus plazas, pasos de cebra
y líneas de carril, pegados al terreno de la casilla con texturas de detalle (bcn_obra).

Trazado y tipo: OpenStreetMap (ODbL). Ancho de calzada: 'width' si lo hay; si no, carriles ('lanes'
o lo típico de su tipo) por 3,1 m más una banda de aparcamiento en las calles urbanas. Los edificios
del Catastro recortan calzada y aceras. Acera: la franja de 5 m alrededor de la calzada que no es
edificio, más las aceras dibujadas (footway=sidewalk), calles peatonales y plazas.
Aparcamientos en superficie (amenity=parking) y el contorno de cada plaza (amenity=parking_space).
Pasos de cebra en los nodos highway=crossing marcados, de lado a lado de la calzada.

Alcorques (el cuadro de tierra de 1,2 m con su marco) bajo cada árbol de OSM que cae en la acera, y tapas
de registro en la calzada cada ~35 m (deterministas por posición).

Cada polígono se corta por los triángulos del terreno (malla de 2 m) y se pone sobre su plano, unos
centímetros por encima: así no se hunde ni flota aunque el suelo tenga pendiente.

construir(osm, edificios, z, e0, n0, lado, paso) -> {textura: dict(v, n, uv, color, i)} en coordenadas
locales (centro de la casilla), con z la rejilla del terreno de terreno() en prototipo.py.
"""
import zlib

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import substring

CARRILES = {"motorway": 2, "trunk": 2, "primary": 4, "secondary": 2, "tertiary": 2, "residential": 2,
            "unclassified": 2, "living_street": 1, "service": 1, "motorway_link": 1, "trunk_link": 1,
            "primary_link": 1, "secondary_link": 1, "tertiary_link": 1, "road": 2, "busway": 1}
CARRIL = 3.1
APARCAMIENTO = {"primary", "secondary", "tertiary", "residential", "unclassified"}  # una banda de 2,2 m
CON_LINEAS = {"motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link",
              "primary_link", "secondary_link", "tertiary_link", "residential", "unclassified"}
PEATONALES = {"pedestrian"}
SUBE = dict(vi_asfalto=0.04, vi_aparcamiento=0.04, vi_acera=0.13, vi_linea=0.055)  # sobre el terreno (m)
BORDILLO = 0.13
ESCALA = dict(vi_asfalto=4.0, vi_aparcamiento=4.0, vi_acera=2.0, vi_linea=1.0)  # m por repetición de textura


def _num(texto):
    try:
        return float(str(texto).split(";")[0].replace(",", ".").replace("m", "").strip())
    except (TypeError, ValueError):
        return None


def ancho_calzada(t):
    hw = t.get("highway")
    w = _num(t.get("width"))
    if w and 2.5 <= w <= 40:
        return w
    unico = t.get("oneway") in ("yes", "1", "-1") or hw in ("motorway", "motorway_link", "trunk_link")
    carriles = _num(t.get("lanes")) or CARRILES[hw] / (2 if unico and CARRILES[hw] > 1 else 1)
    if hw == "service":
        return 6.0 if t.get("service") == "parking_aisle" else 3.6
    if hw == "living_street":
        return 4.5
    return carriles * CARRIL + (2.2 if hw in APARCAMIENTO else 0.0)


def _a_nivel(t, largo=0.0):
    """Vía en superficie. Un 'túnel' corto (< 120 m) es una calle que pasa bajo un viaducto ancho o un
    edificio (en Sant Roc, las de debajo de la C-31): también se dibuja."""
    tunel = t.get("tunnel") not in (None, "no")
    if tunel and not (largo < 120 and (_num(t.get("layer")) or 0) >= -1):
        return False
    return t.get("bridge") in (None, "no") and (_num(t.get("layer")) or 0) >= -1


EN_TUNEL = set()  # extremos de las vías que van en un tubo de tuneles_v (no se dibujan a nivel)


def vias_coche(osm, caja):
    """[(LineString, tags, ancho)] de las vías con calzada a nivel que tocan la caja."""
    out = []
    for v in osm["vias"]:
        t = v["tags"]
        if t.get("highway") not in CARRILES or t.get("area") == "yes" or len(v["xy"]) < 2:
            continue
        xy = v["xy"]
        if EN_TUNEL and (round(float(xy[0][0]), 1), round(float(xy[0][1]), 1),
                         round(float(xy[-1][0]), 1), round(float(xy[-1][1]), 1)) in EN_TUNEL:
            continue
        if not _a_nivel(t, float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum())):
            continue
        if xy[:, 0].max() < caja[0] or xy[:, 0].min() > caja[2] or xy[:, 1].max() < caja[1] or xy[:, 1].min() > caja[3]:
            continue
        out.append((LineString(xy), t, ancho_calzada(t)))
    return out


def _poligonos(osm, caja, condicion):
    out = []
    for a in osm["areas"]:
        xy = a["xy"]
        if xy[:, 0].max() < caja[0] or xy[:, 0].min() > caja[2] or xy[:, 1].max() < caja[1] or xy[:, 1].min() > caja[3]:
            continue
        if condicion(a["tags"]):
            p = Polygon(xy)
            if not p.is_valid:
                p = p.buffer(0)
            out.append(p)
    return out


def _lineas_acera(osm, caja):
    out = []
    for v in osm["vias"]:
        t = v["tags"]
        hw = t.get("highway")
        if len(v["xy"]) < 2 or not _a_nivel(t, float(np.linalg.norm(np.diff(v["xy"], axis=0), axis=1).sum())):
            continue
        xy = v["xy"]
        if xy[:, 0].max() < caja[0] or xy[:, 0].min() > caja[2] or xy[:, 1].max() < caja[1] or xy[:, 1].min() > caja[3]:
            continue
        if hw == "footway" and t.get("footway") == "sidewalk":
            out.append(LineString(xy).buffer(1.4, cap_style="flat"))
        elif hw in PEATONALES and t.get("area") != "yes":
            out.append(LineString(xy).buffer((_num(t.get("width")) or 7.0) / 2))
        elif hw in ("footway", "path") and t.get("footway") != "crossing":  # paseos y caminos pavimentados
            if t.get("surface") in (None, "paved", "paving_stones", "concrete", "asphalt", "sett", "concrete:plates"):
                out.append(LineString(xy).buffer((_num(t.get("width")) or 2.6) / 2))
    return out


def _carriles_bici(osm, caja):
    out = []
    for v in osm["vias"]:
        t = v["tags"]
        if t.get("highway") != "cycleway" or len(v["xy"]) < 2 or t.get("bridge") not in (None, "no"):
            continue
        xy = v["xy"]
        if xy[:, 0].max() < caja[0] or xy[:, 0].min() > caja[2] or xy[:, 1].max() < caja[1] or xy[:, 1].min() > caja[3]:
            continue
        out.append(LineString(xy).buffer((_num(t.get("width")) or 2.2) / 2, cap_style="flat"))
    return out


def _vias_tren(osm, caja):
    out = []
    for v in osm["vias"]:
        t = v["tags"]
        if t.get("railway") in ("rail", "light_rail", "tram", "narrow_gauge") and len(v["xy"]) > 1:
            xy = v["xy"]
            if xy[:, 0].max() < caja[0] or xy[:, 0].min() > caja[2] or xy[:, 1].max() < caja[1] or xy[:, 1].min() > caja[3]:
                continue
            out.append(LineString(xy).buffer(3.0))
    return out


def _cruces(vias):
    """Puntos donde se cruzan calles (grado 3 o más: un extremo cuenta 1, un nodo de paso 2); ahí no se
    pintan líneas de carril. Un tramo que solo sigue en el siguiente (grado 2) no corta las líneas."""
    grado = {}
    for linea, _, _ in vias:
        q = linea.coords
        for k, p in enumerate(q):
            clave = (round(p[0], 1), round(p[1], 1))
            grado[clave] = grado.get(clave, 0) + (1 if k in (0, len(q) - 1) else 2)
    puntos = [k for k, g in grado.items() if g >= 3]
    return shapely.points(np.array(puntos)) if puntos else np.array([])


def _discontinua(linea, trazo, hueco):
    largo = linea.length
    out, d = [], hueco / 2
    while d < largo:
        out.append(substring(linea, d, min(d + trazo, largo)))
        d += trazo + hueco
    return out


def marcas(vias, calzada, osm, caja):
    """Polígonos de pintura blanca: líneas de carril, pasos de cebra y plazas de aparcamiento."""
    trazos = []
    cruces = _cruces(vias)
    zona_cruce = shapely.union_all(shapely.buffer(cruces, 9.0)) if len(cruces) else Polygon()
    for linea, t, w in vias:
        hw = t.get("highway")
        if hw not in CON_LINEAS:
            continue
        unico = t.get("oneway") in ("yes", "1", "-1") or hw in ("motorway", "motorway_link", "trunk_link")
        carriles = int(round(_num(t.get("lanes")) or CARRILES[hw] / (2 if unico and CARRILES[hw] > 1 else 1)))
        util = carriles * CARRIL
        for k in range(1, carriles):
            o = -util / 2 + k * util / carriles
            centro = not unico and k == carriles // 2
            try:
                guia = linea.offset_curve(o) if abs(o) > 0.01 else linea
            except Exception:
                continue
            if guia.is_empty or guia.geom_type != "LineString":
                continue
            continua = centro and hw in ("primary", "trunk", "motorway")
            partes = [guia] if continua else _discontinua(guia, 3.0 if hw in ("motorway", "trunk") else 2.0,
                                                          9.0 if hw in ("motorway", "trunk") else 4.0)
            ancho = 0.15 if hw in ("motorway", "trunk") else 0.12
            trazos += [p.buffer(ancho / 2, cap_style="flat") for p in partes if p.length > 0.2]
    pintura = shapely.union_all(trazos).difference(zona_cruce) if trazos else Polygon()
    # pasos de cebra: franjas de 0,5 m cada metro a lo ancho, de 4 m en el sentido de la marcha
    cebras = []
    arbol = shapely.STRtree([v[0] for v in vias]) if vias else None
    for nd in osm["nodos"]:
        t = nd["tags"]
        if t.get("highway") != "crossing" or arbol is None:
            continue
        if t.get("crossing") in ("unmarked", "no") or t.get("crossing:markings") == "no":
            continue
        x, y = nd["xy"]
        if not (caja[0] - 10 <= x < caja[2] + 10 and caja[1] - 10 <= y < caja[3] + 10):
            continue
        p = Point(x, y)
        k = arbol.nearest(p)
        linea, tv, w = vias[k]
        if linea.distance(p) > 2.0:
            continue
        d = linea.project(p)
        a, b = linea.interpolate(max(d - 1, 0)), linea.interpolate(min(d + 1, linea.length))
        tan = np.array([b.x - a.x, b.y - a.y])
        if np.linalg.norm(tan) < 1e-6:
            continue
        tan /= np.linalg.norm(tan)
        nor = np.array([-tan[1], tan[0]])
        c = np.array([x, y])
        for o in np.arange(-w / 2 + 0.5, w / 2 - 0.2, 1.0):
            q = c + nor * o
            esquinas = [q + tan * s * 2.0 + nor * r * 0.25 for s, r in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            cebras.append(Polygon(esquinas))
    if cebras:
        pintura = pintura.union(shapely.union_all(cebras).intersection(calzada.buffer(-0.2)))
    plazas = _poligonos(osm, caja, lambda t: t.get("amenity") == "parking_space")
    if plazas:
        contornos = [shapely.buffer(p.exterior, 0.05) for p in plazas if not p.is_empty]
        pintura = pintura.union(shapely.union_all(contornos))
    return pintura.intersection(calzada.union(shapely.union_all(plazas) if plazas else Polygon()).buffer(0.3))


class Suelo:
    """El terreno de la casilla como función: z exacta sobre los triángulos de terrain()."""

    def __init__(self, z, e0, n0, lado, paso):
        self.z, self.e0, self.n0, self.lado, self.paso = z, e0, n0, lado, paso
        k = z.shape[0] - 1
        c, f = np.meshgrid(np.arange(k), np.arange(k))
        x0, x1 = e0 + c.ravel() * paso, e0 + (c.ravel() + 1) * paso
        yt, yb = n0 + lado - f.ravel() * paso, n0 + lado - (f.ravel() + 1) * paso
        sup = np.stack([np.c_[x0, yt], np.c_[x0, yb], np.c_[x1, yt]], 1)  # a, c, b
        inf = np.stack([np.c_[x1, yt], np.c_[x0, yb], np.c_[x1, yb]], 1)  # b, c, d
        self.tris = shapely.polygons(np.concatenate([sup, inf]))
        a, b = z[:-1, :-1].ravel(), z[:-1, 1:].ravel()
        cc, d = z[1:, :-1].ravel(), z[1:, 1:].ravel()
        rango = np.r_[np.ptp(np.stack([a, cc, b]), axis=0), np.ptp(np.stack([b, cc, d]), axis=0)]
        self.empinado = self.tris[rango > 1.2]
        self.arbol = shapely.STRtree(self.tris)

    def altura(self, x, y):
        k = self.z.shape[0] - 1
        fx = np.clip((np.asarray(x) - self.e0) / self.paso, 0, k - 1e-6)
        fy = np.clip((self.n0 + self.lado - np.asarray(y)) / self.paso, 0, k - 1e-6)
        c, f = fx.astype(int), fy.astype(int)
        u, v = fx - c, fy - f
        za, zb = self.z[f, c], self.z[f, c + 1]
        zc, zd = self.z[f + 1, c], self.z[f + 1, c + 1]
        arriba = za + u * (zb - za) + v * (zc - za)
        abajo = zd + (1 - u) * (zc - zd) + (1 - v) * (zb - zd)
        return np.where(u + v <= 1, arriba, abajo)

    def pegar(self, geom):
        """Triángulos (m, 3, 2) de geom cortados por la malla del terreno."""
        if geom.is_empty:
            return np.zeros((0, 3, 2))
        # cortar por bloques cada vez más pequeños: la intersección con una geometría grande es lenta
        trozos = np.array([geom])
        for celda in (50.0, 10.0):
            k = int(np.ceil(self.lado / celda))
            x = self.e0 + np.arange(k) * celda
            y = self.n0 + np.arange(k) * celda
            gx, gy = np.meshgrid(x, y)
            cajas = shapely.box(gx.ravel(), gy.ravel(), gx.ravel() + celda, gy.ravel() + celda)
            i, j = shapely.STRtree(cajas).query(trozos, predicate="intersects")
            trozos = shapely.intersection(trozos[i], cajas[j])
            trozos = trozos[~shapely.is_empty(trozos)]
        i, j = self.arbol.query(trozos, predicate="intersects")
        if not len(i):
            return np.zeros((0, 3, 2))
        trozos = shapely.intersection(trozos[i], self.tris[j])
        trozos = trozos[~shapely.is_empty(trozos)]
        partes = shapely.get_parts(trozos)
        partes = partes[np.isin(shapely.get_type_id(partes), (3, 6))]  # (multi)polígonos
        tri = shapely.get_parts(shapely.constrained_delaunay_triangles(partes))
        tri = tri[shapely.area(tri) > 1e-4]
        if not len(tri):
            return np.zeros((0, 3, 2))
        p = shapely.get_coordinates(shapely.get_exterior_ring(tri)).reshape(-1, 4, 2)[:, :3]
        giro = (p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1]) - (p[:, 1, 1] - p[:, 0, 1]) * (p[:, 2, 0] - p[:, 0, 0])
        p[giro < 0] = p[giro < 0][:, ::-1]
        return p


def _ruido(x, y, semilla, celda=7.0):
    """Ruido de valor suave en coordenadas UTM (manchas del asfalto, sin repetir)."""
    gx, gy = x / celda, y / celda
    i, j = np.floor(gx), np.floor(gy)
    fx, fy = gx - i, gy - j
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)

    def h(a, b):
        return np.modf(np.sin(a * 127.1 + b * 311.7 + semilla * 74.7) * 43758.5453)[0] % 1.0

    return (h(i, j) * (1 - fx) * (1 - fy) + h(i + 1, j) * fx * (1 - fy) + h(i, j + 1) * (1 - fx) * fy
            + h(i + 1, j + 1) * fx * fy)


def _malla(tris, suelo, sube, escala, centro, tono):
    if not len(tris):
        return None
    xy = tris.reshape(-1, 2)
    z = suelo.altura(xy[:, 0], xy[:, 1]) + sube
    v = np.c_[xy - centro, z]
    a, b, c = v[0::3], v[1::3], v[2::3]
    nrm = np.cross(b - a, c - a)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    uv = (xy % 4000.0) / escala  # continua de casilla a casilla
    luz = tono[0] + tono[1] * _ruido(xy[:, 0], xy[:, 1], 1) + tono[2] * _ruido(xy[:, 0], xy[:, 1], 2, 1.7)
    gris = np.clip(luz * 255, 0, 255).astype(int)
    return dict(v=v, n=np.repeat(nrm, 3, 0), uv=uv, color=np.c_[gris, gris, gris, np.full(len(v), 255)],
                i=np.arange(len(v)).reshape(-1, 3))


def _bordillos(calzada, acera, suelo, centro):
    """Caras verticales del bordillo donde la acera toca la calzada (mirando a la calzada)."""
    # solo la parte de polígonos: una colección con líneas o puntos sueltos no tiene contorno
    calzada = shapely.union_all([g for g in shapely.get_parts(calzada) if g.geom_type in ("Polygon", "MultiPolygon")])
    if calzada.is_empty:
        return None
    borde = calzada.boundary.intersection(acera.buffer(0.2))
    lineas = [g for g in shapely.get_parts(shapely.segmentize(borde, 2.0)) if g.geom_type == "LineString"]
    v, uv = [], []
    for g in lineas:
        q = np.asarray(g.coords)
        for (ax, ay), (bx, by) in zip(q[:-1], q[1:]):
            largo = np.hypot(bx - ax, by - ay)
            if largo < 0.05:
                continue
            v.append(((ax, ay), (bx, by)))
            uv.append(largo)
    if not v:
        return None
    s = np.array(v)  # (m, 2, 2)
    za = suelo.altura(s[:, 0, 0], s[:, 0, 1])
    zb = suelo.altura(s[:, 1, 0], s[:, 1, 1])
    d = s[:, 1] - s[:, 0]
    izq = np.c_[-d[:, 1], d[:, 0]] / np.linalg.norm(d, axis=1, keepdims=True)
    medio = s.mean(1)
    hacia_calzada = shapely.contains_xy(calzada, medio[:, 0] + izq[:, 0] * 0.3, medio[:, 1] + izq[:, 1] * 0.3)
    nrm = np.where(hacia_calzada[:, None], izq, -izq)
    lo, hi = SUBE["vi_asfalto"] - 0.02, BORDILLO
    p0 = np.c_[s[:, 0] - centro, za + lo]
    p1 = np.c_[s[:, 1] - centro, zb + lo]
    p2 = np.c_[s[:, 1] - centro, zb + hi]
    p3 = np.c_[s[:, 0] - centro, za + hi]
    quads = np.stack([p0, p1, p2, p3], 1)
    # orientar: la cara vista hacia la normal
    cruz = np.cross(quads[:, 1] - quads[:, 0], quads[:, 2] - quads[:, 0])[:, :2]
    al_reves = np.einsum("ij,ij->i", cruz, nrm) < 0
    quads[al_reves] = quads[al_reves][:, [1, 0, 3, 2]]
    largo = np.array(uv)
    u = np.stack([np.zeros_like(largo), largo, largo, np.zeros_like(largo)], 1) / 2.0
    u[al_reves] = u[al_reves][:, [1, 0, 3, 2]]
    vv = np.tile([0.0, 0.0, 1.0, 1.0], (len(quads), 1))
    m = len(quads)
    base = np.arange(m)[:, None] * 4
    idx = np.concatenate([base + [0, 1, 2], base + [0, 2, 3]])
    return dict(v=quads.reshape(-1, 3), n=np.repeat(np.c_[nrm, np.zeros(m)], 4, 0),
                uv=np.c_[u.ravel(), vv.ravel()], color=np.full((4 * m, 4), 235), i=idx)


def recortar(osm, caja):
    """Lo de OSM que toca la caja (e0, n0, e1, n1): para no recorrer todo el mapa en cada casilla."""
    def toca(xy):
        xy = np.asarray(xy).reshape(-1, 2)
        return not (xy[:, 0].max() < caja[0] or xy[:, 0].min() > caja[2] or xy[:, 1].max() < caja[1]
                    or xy[:, 1].min() > caja[3])
    return {k: [it for it in osm[k] if toca(it["xy"])] for k in ("vias", "areas", "nodos")}


def _placas(centros, ejes, lado, suelo, sube, centro_casilla):
    """Cuadrados pequeños (alcorques, tapas) apoyados en el terreno por sus cuatro esquinas, con la textura
    entera en cada uno. ejes: dirección (2,) de un lado de cada cuadrado."""
    if not len(centros):
        return None
    c = np.asarray(centros, float)
    ex = np.asarray(ejes, float)
    ex /= np.linalg.norm(ex, axis=1, keepdims=True) + 1e-9
    ey = np.c_[-ex[:, 1], ex[:, 0]]
    h = lado / 2
    esquinas = np.stack([c - ex * h - ey * h, c + ex * h - ey * h, c + ex * h + ey * h, c - ex * h + ey * h], 1)
    xy = esquinas.reshape(-1, 2)
    z = suelo.altura(xy[:, 0], xy[:, 1]) + sube
    v = np.c_[xy - centro_casilla, z]
    m = len(c)
    base = np.arange(m)[:, None] * 4
    idx = np.concatenate([base + [0, 1, 2], base + [0, 2, 3]])
    uv = np.tile([[0, 0], [1, 0], [1, 1], [0, 1]], (m, 1)).astype(float)
    return dict(v=v, n=np.tile([0.0, 0.0, 1.0], (4 * m, 1)), uv=uv, color=np.full((4 * m, 4), 255), i=idx)


def _alcorques(osm, acera, vias, casilla):
    centros, ejes = [], []
    arbol = shapely.STRtree([v[0] for v in vias]) if vias else None
    for nd in osm["nodos"]:
        if nd["tags"].get("natural") != "tree":
            continue
        x, y = nd["xy"]
        if not shapely.contains_xy(casilla, x, y) or not shapely.contains_xy(acera, x, y):
            continue
        eje = np.array([1.0, 0.0])
        if arbol is not None:  # alineado con la calle más cercana
            linea = vias[arbol.nearest(Point(x, y))][0]
            d = linea.project(Point(x, y))
            a, b = linea.interpolate(max(d - 1, 0)), linea.interpolate(min(d + 1, linea.length))
            eje = np.array([b.x - a.x, b.y - a.y]) + 1e-9
        centros.append((x, y))
        ejes.append(eje)
    return centros, ejes


def _tapas(vias, calzada, casilla):
    centros, ejes = [], []
    for linea, t, w in vias:
        if t.get("highway") in ("motorway", "trunk", "motorway_link", "trunk_link"):
            continue
        semilla = zlib.crc32(f"{linea.coords[0][0]:.1f},{linea.coords[0][1]:.1f}".encode())
        for k, d in enumerate(np.arange(8.0 + semilla % 20, linea.length - 4, 35.0)):
            q = linea.interpolate(d)
            a = linea.interpolate(min(d + 1, linea.length))
            tan = np.array([a.x - q.x, a.y - q.y]) + 1e-9
            tan /= np.linalg.norm(tan)
            lateral = ((semilla >> (k % 16)) % 3 - 1) * min(w / 4, 1.6)  # en el eje o en un carril
            p = np.array([q.x, q.y]) + np.array([-tan[1], tan[0]]) * lateral
            if shapely.contains_xy(casilla, *p) and shapely.contains_xy(calzada, *p):
                centros.append(p)
                ejes.append(tan)
    return centros, ejes


def construir(osm, edificios, z, e0, n0, lado, paso, cubierto=None):
    """edificios: lista de Polygon (UTM) del Catastro alrededor de la casilla. cubierto: si es una lista, se le
    añade lo que tapan calzada, aceras y aparcamientos (para hundir ahí el terreno que se ve)."""
    marco = 30.0
    caja = (e0 - marco, n0 - marco, e0 + lado + marco, n0 + lado + marco)
    casilla = box(e0, n0, e0 + lado, n0 + lado)
    centro = np.array([e0 + lado / 2, n0 + lado / 2])
    vias = vias_coche(osm, caja)
    construido = shapely.union_all([p for p in edificios if p.is_valid]) if edificios else Polygon()
    calzada = shapely.union_all([linea.buffer(w / 2, quad_segs=4) for linea, _, w in vias]) if vias else Polygon()
    calzada = calzada.difference(construido)
    aparc = _poligonos(osm, caja, lambda t: t.get("amenity") == "parking" and t.get("parking") in
                       (None, "surface", "street_side", "lane", "yes") and (_num(t.get("layer")) or 0) >= -1)
    aparc = shapely.union_all(aparc).difference(construido).difference(calzada) if aparc else Polygon()
    plazas = _poligonos(osm, caja, lambda t: t.get("area:highway") in ("pedestrian", "footway")
                        or t.get("place") == "square" or (t.get("highway") == "pedestrian" and t.get("area") == "yes"))
    # acera: el espacio público entre la calzada y las fachadas (hasta 12 m), sin autopistas ni vías de tren
    urbanas = [linea.buffer(w / 2 + 12.0, quad_segs=4) for linea, t, w in vias
               if t.get("highway") not in ("motorway", "trunk", "motorway_link", "trunk_link")]
    calzada = calzada.union(shapely.union_all(_carriles_bici(osm, caja)).difference(construido))
    acera = shapely.union_all(urbanas + _lineas_acera(osm, caja) + plazas)
    verde = _poligonos(osm, caja, lambda t: t.get("leisure") in ("park", "garden", "pitch", "playground")
                       or t.get("landuse") in ("grass", "forest", "meadow") or t.get("natural") in ("water", "beach", "sand", "scrub", "wood"))
    acera = acera.difference(construido).difference(calzada).difference(aparc)
    trenes = _vias_tren(osm, caja)
    if trenes:
        acera = acera.difference(shapely.union_all(trenes))
    if verde:
        acera = acera.difference(shapely.union_all(verde).buffer(-0.5).difference(shapely.union_all(plazas) if plazas else Polygon()))
    pintura = marcas(vias, calzada, osm, caja) if vias else Polygon()
    suelo = Suelo(z, e0, n0, lado, paso)
    if len(suelo.empinado):  # muros y taludes: sin calle pegada encima (salían pirámides de acera)
        empinado = shapely.union_all(suelo.empinado).buffer(0.2)
        calzada, aparc, acera, pintura = (g.difference(empinado) for g in (calzada, aparc, acera, pintura))
    if cubierto is not None:
        cubierto.append(shapely.union_all([calzada, aparc, acera]).intersection(casilla.buffer(paso)))
    out = {}
    capas = (("vi_asfalto", calzada, (0.80, 0.16, 0.06)), ("vi_aparcamiento", aparc, (0.86, 0.10, 0.05)),
             ("vi_acera", acera, (0.88, 0.10, 0.04)), ("vi_linea", pintura, (0.88, 0.08, 0.06)))
    for tex, geom, tono in capas:
        geom = shapely.make_valid(geom).intersection(casilla) if not geom.is_empty else geom
        g = _malla(suelo.pegar(geom), suelo, SUBE[tex], ESCALA[tex], centro, tono)
        if g is not None:
            out[tex] = g
    b = _bordillos(calzada.intersection(casilla), acera.intersection(casilla), suelo, centro)
    if b is not None:
        out["vi_bordillo"] = b
    shapely.prepare(acera)
    shapely.prepare(calzada)
    g = _placas(*_alcorques(osm, acera, vias, casilla), 1.2, suelo, SUBE["vi_acera"] + 0.012, centro)
    if g is not None:
        out["vi_alcorque"] = g
    g = _placas(*_tapas(vias, calzada, casilla), 0.8, suelo, SUBE["vi_linea"] + 0.004, centro)
    if g is not None:
        out["vi_tapa"] = g
    for tex, g in list(_bocas_metro(osm, vias, construido, casilla, suelo, centro).items()) + \
            list(_vias_a_nivel(osm, casilla, suelo, centro).items()):
        if tex in out:  # se suma a lo que ya hay con esa textura
            base = len(out[tex]["v"])
            out[tex] = {k: np.concatenate([out[tex][k], g[k] + (base if k == "i" else 0)]) for k in g}
        else:
            out[tex] = g
    return out


def _vias_a_nivel(osm, casilla, suelo, centro):
    """Vías de tren a nivel (Renfe, FGC, tranvía): balasto con traviesas, talud y dos carriles sobre el
    terreno; las del tranvía, solo los carriles embebidos en la calle o el césped. Las de puente y túnel van
    aparte (puentes_v, y el metro no se ve)."""
    import puentes_v
    obra = puentes_v.Obra(centro)
    caja = casilla.bounds
    for v in osm["vias"]:
        t = v["tags"]
        rw = t.get("railway")
        if rw not in ("rail", "light_rail", "tram", "narrow_gauge") or len(v["xy"]) < 2:
            continue
        if t.get("bridge") not in (None, "no") or t.get("tunnel") not in (None, "no") or \
                t.get("covered") in ("yes",) or (_num(t.get("layer")) or 0) < 0:
            continue
        xy = np.asarray(v["xy"], float)
        if xy[:, 0].max() < caja[0] - 5 or xy[:, 0].min() > caja[2] + 5 or \
                xy[:, 1].max() < caja[1] - 5 or xy[:, 1].min() > caja[3] + 5:
            continue
        linea = LineString(xy)
        ds = np.unique(np.r_[np.arange(0, linea.length, puentes_v.PASO), linea.length])
        pts = np.array([linea.interpolate(d).coords[0] for d in ds])
        tan = np.gradient(pts, axis=0)
        tan /= np.linalg.norm(tan, axis=1, keepdims=True) + 1e-9
        der = np.c_[tan[:, 1], -tan[:, 0]]
        tranvia = rw == "tram"
        w = 1.0 if tranvia else 2.0
        # la cota más alta de la sección: que el balasto no quede enterrado en una ladera
        zs = np.max([suelo.altura(pts[:, 0] + der[:, 0] * o, pts[:, 1] + der[:, 1] * o) for o in (-w, 0, w)], 0)
        zs = zs + (SUBE["vi_asfalto"] + 0.01 if tranvia else 0.10)
        for i0, i1 in puentes_v.tramos(pts, caja):
            sl = slice(i0, i1 + 1)
            eje = (pts[sl], der[sl], ds[sl], zs[sl])
            if tranvia:
                for o in (-0.72, 0.72):
                    obra.extruir(eje, "vi_hierro", [(o + 0.04, 0.03), (o - 0.04, 0.03), (o - 0.04, 0.0), (o + 0.04, 0.0)],
                                 lados=[0], escala=1.0)
                continue
            obra.banda(eje, "vi_balasto", -w, w, 0.0, escala_u=2 * w, escala_v=3.0, u_desde=-w)
            obra.extruir(eje, "vi_balasto", [(w + 0.7, -0.5), (w, 0.0), (-w, 0.0), (-w - 0.7, -0.5)],
                         lados=[0, 2], escala=2.0)  # talud del balasto
            for o in (-0.72, 0.72):
                obra.extruir(eje, "vi_hierro", [(o + 0.035, 0.18), (o - 0.035, 0.18), (o - 0.07, 0.0), (o + 0.07, 0.0)],
                             lados=[0, 1, 3], escala=1.0)
            if rw in ("rail", "light_rail") and t.get("electrified") not in ("no",):
                _catenaria(obra, eje)
    return obra.m.arrays()


def _catenaria(obra, eje, entre=50.0):
    """Postes de la catenaria cada 'entre' m a la derecha de la vía (perfil de 0,25 m y 7 m de alto) con la
    ménsula hasta encima del carril a 6,2 m y el hilo de contacto a 5,5 m entre poste y poste."""
    pts, der, ds, z = eje
    altos = []
    for d in np.arange(np.ceil(ds[0] / entre) * entre, ds[-1], entre):
        i = int(np.clip(np.searchsorted(ds, d), 0, len(ds) - 1))
        base = np.r_[pts[i] + der[i] * 2.9 - obra.c, z[i] - 0.3]
        lat = np.r_[der[i], 0.0]
        tan = np.r_[-der[i, 1], der[i, 0], 0.0]
        a, b = lat * 0.125, tan * 0.125
        esq = [base - a - b, base + a - b, base + a + b, base - a + b]
        for k in range(4):
            p0, p1 = esq[k], esq[(k + 1) % 4]
            fuera = (p0 + p1) / 2 - base
            obra.cara("vi_hierro", [p0, p1, p1 + [0, 0, 7.3], p0 + [0, 0, 7.3]], [(0, 0), (0.25, 0), (0.25, 7), (0, 7)], fuera)
        # ménsula: viga de 0,12 m desde el poste hasta 0,3 m más allá del eje de la vía
        m0 = base + [0, 0, 6.5] - lat * 0.1
        m1 = m0 - lat * 3.2
        for h0, h1, hacia in ((0.0, 0.0, np.array([0, 0, -1.0])), (0.12, 0.12, np.array([0, 0, 1.0]))):
            obra.cara("vi_hierro", [m0 - b * 0.5 + [0, 0, h0], m1 - b * 0.5 + [0, 0, h0], m1 + b * 0.5 + [0, 0, h1],
                                    m0 + b * 0.5 + [0, 0, h1]], [(0, 0), (3, 0), (3, 0.1), (0, 0.1)], hacia)
        for s in (-1, 1):
            obra.cara("vi_hierro", [m0 + b * 0.5 * s, m1 + b * 0.5 * s, m1 + b * 0.5 * s + [0, 0, 0.12],
                                    m0 + b * 0.5 * s + [0, 0, 0.12]], [(0, 0), (3, 0), (3, 0.1), (0, 0.1)], tan * s)
        altos.append(np.r_[pts[i] - obra.c, z[i] + 5.5])
    # hilo de contacto entre ménsulas: tira de 3 cm vista desde abajo y de lado
    for p0, p1 in zip(altos[:-1], altos[1:]):
        d = p1[:2] - p0[:2]
        n = np.r_[-d[1], d[0], 0.0] / (np.linalg.norm(d) + 1e-9) * 0.015
        obra.cara("vi_hierro", [p0 - n, p1 - n, p1 + n, p0 + n], [(0, 0), (1, 0), (1, 1), (0, 1)], np.array([0, 0, -1.0]))
        obra.cara("vi_hierro", [p0, p1, p1 + [0, 0, 0.03], p0 + [0, 0, 0.03]], [(0, 0), (1, 0), (1, 1), (0, 1)],
                  np.r_[n[:2], 0.0])


def _bocas_metro(osm, vias, construido, casilla, suelo, centro):
    """Bocas de metro (railway=subway_entrance de OSM): el hueco de la escalera en la acera, barandilla en
    tres lados y el poste con el rombo rojo de la M, alineadas con la calle más cercana."""
    import fachadas_v
    m = fachadas_v.Malla()
    arbol = shapely.STRtree([v[0] for v in vias]) if vias else None
    c3 = np.r_[centro, 0.0]
    blanco = (255, 255, 255, 255)
    for nd in osm["nodos"]:
        if nd["tags"].get("railway") != "subway_entrance":
            continue
        x, y = nd["xy"]
        if not shapely.contains_xy(casilla, x, y) or shapely.contains_xy(construido, x, y):
            continue  # las de dentro de un edificio o estación no se ven desde la calle
        eje = np.array([1.0, 0.0])
        if arbol is not None:
            linea = vias[arbol.nearest(Point(x, y))][0]
            d = linea.project(Point(x, y))
            a, b = linea.interpolate(max(d - 1, 0)), linea.interpolate(min(d + 1, linea.length))
            eje = np.array([b.x - a.x, b.y - a.y])
        eje /= np.linalg.norm(eje) + 1e-9
        lat = np.array([-eje[1], eje[0]])
        L, W = 5.0, 1.9  # hueco de la escalera
        esq = [np.array([x, y]) + eje * su * L / 2 + lat * sv * W / 2 for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        z = float(np.max(suelo.altura(np.array([q[0] for q in esq]), np.array([q[1] for q in esq])))) + SUBE["vi_acera"] + 0.02
        P = [np.r_[q, z] - c3 for q in esq]
        m.quad("vi_metro_esc", P, (0, 0, 1), [(0, 0), (0, 1), (1, 1), (1, 0)], blanco)
        # barandilla: los dos lados largos y el fondo (la boca se abre por -eje)
        for a, b in ((P[0], P[1]), (P[1], P[2]), (P[2], P[3])):
            largo = float(np.linalg.norm(b - a))
            arriba = np.array([0, 0, 1.0])
            q = [a, b, b + arriba, a + arriba]
            nrm = np.cross(b - a, arriba)
            nrm /= np.linalg.norm(nrm) + 1e-9
            uv = [(0, 1), (largo / 2, 1), (largo / 2, 0), (0, 0)]
            m.quad("vi_barandilla_alfa", q, nrm, uv, blanco)
            m.quad("vi_barandilla_alfa", [q[1], q[0], q[3], q[2]], -nrm, [uv[1], uv[0], uv[3], uv[2]], blanco)
        # poste junto a la boca, con el rombo a 3 m
        base = np.r_[np.array([x, y]) - eje * (L / 2 + 0.4) + lat * (W / 2 + 0.2), z] - c3
        for k in range(4):
            ang = np.pi / 2 * k
            d0 = np.array([np.cos(ang), np.sin(ang), 0]) * 0.05
            d1 = np.array([np.cos(ang + np.pi / 2), np.sin(ang + np.pi / 2), 0]) * 0.05
            q = [base + d0 - d1 + 0, base + d0 + d1, base + d0 + d1 + [0, 0, 3.0], base + d0 - d1 + [0, 0, 3.0]]
            m.quad("vi_hierro", q, d0 / 0.05, [(0, 0), (0.1, 0), (0.1, 3), (0, 3)], blanco)
        for dirx in (eje, lat):  # dos rombos cruzados: se ve desde la calle y desde la acera
            h = np.r_[dirx, 0] * 0.45
            q = [base - h + [0, 0, 2.6], base + h + [0, 0, 2.6], base + h + [0, 0, 3.5], base - h + [0, 0, 3.5]]
            nrm = np.cross(np.r_[dirx, 0], [0, 0, 1.0])
            m.quad("vi_metro_m_alfa", q, nrm, [(0, 1), (1, 1), (1, 0), (0, 0)], blanco)
            m.quad("vi_metro_m_alfa", [q[1], q[0], q[3], q[2]], -nrm, [(0, 1), (1, 1), (1, 0), (0, 0)], blanco)
    return m.arrays()
