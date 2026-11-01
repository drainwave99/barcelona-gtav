"""Árboles y mobiliario urbano con los props del propio juego, en su sitio real.

Posiciones: OpenStreetMap (ODbL): natural=tree (30 000 en las hojas, casi todos del inventario municipal),
highway=street_lamp, traffic_signals y bus_stop, amenity=bench, waste_basket, recycling, post_box,
bicycle_parking y drinking_water. Árboles de parques y montes que OSM no tiene: máximos locales de la
copa en el LiDAR (clases 3-5). Altura de cada árbol: LiDAR (copa menos suelo); el prop se escala a ella.

Los props son del GTA V (no van en nuestro paquete). Qué nombres existen lo comprueba el plugin de
diagnóstico (líneas PROP del registro, copiadas a datos_v/props_validos.txt); de cada lista se usa el
primero que exista.

construir(osm, capas, e0h, n1h) -> lista de entidades (modelo, (x, y, z, rumbo, escala), distancia) en
coordenadas del juego, para el ymap HD de la hoja.
"""
import zlib

import numpy as np
import shapely
from shapely.geometry import LineString, Point

import calles_v
import config_v

# papel -> props candidatos (por orden de preferencia) y su altura nominal (m) para escalar los árboles
PROPS = {
    "farola": ["prop_streetlight_01", "prop_streetlight_03", "prop_streetlight_01b"],
    "semaforo": ["prop_traffic_01a", "prop_traffic_03a", "prop_traffic_01b"],
    "banco": ["prop_bench_01a", "prop_bench_05", "prop_bench_02"],
    "papelera": ["prop_bin_07a", "prop_bin_01a", "prop_bin_05a"],
    "contenedor": ["prop_recyclebin_04a", "prop_dumpster_01a", "prop_recyclebin_01a"],
    "parada": ["prop_busstop_05", "prop_busstop_02", "prop_busstop_04"],
    "buzon": ["prop_postbox_01a"],
    "bicis": ["prop_bikerack_1a"],
    "fuente": ["prop_fountain2", "prop_bollard_04"],
    "palmera": ["prop_palm_med_01b", "prop_palm_med_01a", "prop_palm_sm_01a"],
    "pino": ["prop_tree_pine_01", "prop_tree_pine_02", "prop_tree_cedar_02"],
    "cipres": ["prop_tree_cedar_03", "prop_tree_cedar_02", "prop_tree_pine_02"],
    # árboles de calle: arces (lo más parecido al plátano de sombra) y abedules; sin robles ni ficus, de tronco
    # enorme, ni jacarandas en flor salvo donde OSM dice que lo son
    "frondoso": ["prop_tree_maple_02", "prop_tree_maple_03", "prop_tree_birch_01", "prop_tree_birch_03"],
    "jacaranda": ["prop_tree_jacada_01", "prop_tree_jacada_02"],
}
ALTURA_PROP = {"palmera": 9.0, "pino": 14.0, "cipres": 11.0, "frondoso": 13.0, "jacaranda": 12.0}
DIST = {"arbol": 350.0, "farola": 250.0, "semaforo": 200.0, "otro": 120.0}
SUBE_ACERA = 0.13  # como la acera de calles_v


def validos():
    ruta = config_v.DATOS / "props_validos.txt"
    if not ruta.exists():
        return None
    return {l.split()[0] for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()}


def _elegir(papel, ok, semilla=0):
    lista = [m for m in PROPS[papel] if ok is None or m in ok]
    if not lista:
        return None
    if papel in ("frondoso", "jacaranda"):  # variedad entre los que existen, fija por árbol
        return lista[semilla % len(lista)]
    return lista[0]


def _tipo_arbol(t):
    texto = " ".join(str(t.get(k, "")) for k in ("species", "genus", "taxon", "species:ca", "leaf_type")).lower()
    if any(p in texto for p in ("phoenix", "palmera", "washingtonia", "chamaerops", "trachycarpus", "palm")):
        return "palmera"
    if any(p in texto for p in ("pinus", "pi ", "pi\t", "needleleaved")) or texto.strip() == "pi":
        return "pino"
    if any(p in texto for p in ("cupressus", "xiprer", "thuja")):
        return "cipres"
    if "jacaranda" in texto:
        return "jacaranda"
    return "frondoso"


def _en_hoja(xy, e0h, n1h):
    return e0h <= xy[0] < e0h + 1000 and n1h - 1000 <= xy[1] < n1h


def construir(osm, capas, e0h, n1h):
    ok = validos()
    suelo, veg, edif = capas["suelo"], capas["veg"], capas["edificio"]

    def celda(x, y):
        c = int(np.clip((x - e0h) / 0.5, 0, 1999))
        f = int(np.clip((n1h - y) / 0.5, 0, 1999))
        return f, c

    def z_suelo(x, y):
        return float(suelo[celda(x, y)])

    def copa(x, y, r=2.5):
        f, c = celda(x, y)
        k = int(r / 0.5)
        v = veg[max(f - k, 0):f + k + 1, max(c - k, 0):c + k + 1]
        return float(np.nanmax(v)) if np.isfinite(v).any() else np.nan

    # viaductos: la planta de los puentes de OSM y el tablero del LiDAR, con margen. Nada de árboles que
    # atraviesen el tablero ni farolas o semáforos de la calle de abajo saliendo por la calzada de arriba
    from scipy import ndimage
    import puentes_v
    clave = f"{e0h // 1000}{(n1h // 1000 - 1) % 1000:03d}"
    tablero = puentes_v._huella_puentes(clave) | np.isfinite(capas["puente"])
    cerca_tablero = ndimage.binary_dilation(tablero, iterations=8)  # 4 m: lo que cuelga o sobresale
    # vías de tren a nivel (calles_v las dibuja con balasto): nada a menos de 3 m del eje
    tren = np.zeros_like(tablero)
    for v in osm["vias"]:
        if v["tags"].get("railway") not in ("rail", "light_rail", "narrow_gauge") or len(v["xy"]) < 2:
            continue
        xy = np.asarray(v["xy"], float)
        if xy[:, 0].max() < e0h - 10 or xy[:, 0].min() > e0h + 1010 or xy[:, 1].max() < n1h - 1010 or \
                xy[:, 1].min() > n1h + 10:
            continue
        linea = LineString(xy)
        for d in np.arange(0, linea.length, 0.5):
            p = linea.interpolate(d)
            if e0h <= p.x < e0h + 1000 and n1h - 1000 < p.y <= n1h:
                tren[celda(p.x, p.y)] = True
    cerca_tablero |= ndimage.binary_dilation(tren, iterations=6)

    def libre(x, y, r_extra=0):
        f, c = celda(x, y)
        if r_extra:
            k = r_extra
            return not cerca_tablero[max(f - k, 0):f + k + 1, max(c - k, 0):c + k + 1].any()
        return not cerca_tablero[f, c]

    caja = (e0h - 50, n1h - 1050, e0h + 1050, n1h + 50)
    vias = calles_v.vias_coche(osm, caja)
    arbol_vias = shapely.STRtree([v[0] for v in vias]) if vias else None
    out = []

    def poner(papel, x, y, z, rumbo, dist, escala=1.0, semilla=0):
        modelo = _elegir(papel, ok, semilla)
        if modelo is None:
            return
        if not libre(x, y, 6 if papel in ALTURA_PROP else 0):  # árboles: copa de ~3 m más de radio
            return
        gx, gy = config_v.utm_a_juego(x, y)
        out.append((modelo, (gx, gy, z, rumbo, escala), dist))

    def via_cercana(x, y, maximo=25.0):
        if arbol_vias is None:
            return None
        k = arbol_vias.nearest(Point(x, y))
        linea, t, w = vias[k]
        p = Point(x, y)
        if linea.distance(p) > maximo:
            return None
        d = linea.project(p)
        q = linea.interpolate(d)
        a, b = linea.interpolate(max(d - 1, 0)), linea.interpolate(min(d + 1, linea.length))
        tan = np.array([b.x - a.x, b.y - a.y])
        tan /= np.linalg.norm(tan) + 1e-9
        return np.array([q.x, q.y]), tan, w, t

    def rumbo_hacia(x, y, objetivo):
        """Grados para que el frente (+Y del prop) mire hacia el objetivo."""
        dx, dy = objetivo[0] - x, objetivo[1] - y
        return float(np.degrees(np.arctan2(-dx, dy)))

    # árboles de OSM
    puestos = []
    for nd in osm["nodos"]:
        t, (x, y) = nd["tags"], nd["xy"]
        if not _en_hoja((x, y), e0h, n1h):
            continue
        if t.get("natural") == "tree":
            zs = z_suelo(x, y)
            h = copa(x, y) - zs
            if not np.isfinite(h) or h < 2.5:
                h = 6.0
            tipo = _tipo_arbol(t)
            semilla = zlib.crc32(f"{x:.1f},{y:.1f}".encode())
            escala = float(np.clip(h / ALTURA_PROP[tipo], 0.4, 1.3))
            poner(tipo, x, y, zs, semilla % 360, DIST["arbol"], escala, semilla)
            puestos.append((x, y))
    # árboles del LiDAR que OSM no tiene (parques, solares, montaña): máximos locales de la copa
    altura = np.nan_to_num(veg - suelo, nan=0.0)
    altura[np.isfinite(edif)] = 0.0
    maximos = (altura == ndimage.maximum_filter(altura, size=17)) & (altura > 5.0)
    f, c = np.nonzero(maximos)
    if len(f):
        xs, ys = e0h + (c + 0.5) * 0.5, n1h - (f + 0.5) * 0.5
        if puestos:
            cerca = shapely.STRtree(shapely.points(np.array(puestos)))
            libres = np.array([not len(cerca.query(Point(x, y).buffer(6.0))) for x, y in zip(xs, ys)])
        else:
            libres = np.ones(len(xs), bool)
        if vias:  # una copa que vuela sobre la calzada no es un árbol plantado en ella
            calzada = shapely.union_all([linea.buffer(w / 2 + 0.5) for linea, _, w in vias])
            libres &= ~shapely.contains_xy(calzada, xs, ys)
        for x, y, fi, ci in zip(xs[libres], ys[libres], f[libres], c[libres]):
            h = float(altura[fi, ci])
            semilla = zlib.crc32(f"{x:.1f},{y:.1f}".encode())
            tipo = "pino" if h > 9 and semilla % 3 == 0 else "frondoso"  # en la sierra de Marina abundan los pinos
            poner(tipo, x, y, z_suelo(x, y), semilla % 360, DIST["arbol"],
                  float(np.clip(h / ALTURA_PROP[tipo], 0.4, 1.3)), semilla)
    # farolas de los viaductos: en el borde derecho del tablero cada 40 m, mirando a la calzada
    rel = puentes_v.Relieve()
    vias_p = [v for v in puentes_v.vias_puente(osm) if v["s"]["tipo"] in ("autopista", "calle")]
    puentes_v.extremos_internos(vias_p)
    for via in vias_p:
        xy = via["xy"]
        if not any(_en_hoja(q, e0h, n1h) for q in xy[:: max(1, len(xy) // 8)]) and not _en_hoja(xy[-1], e0h, n1h):
            continue
        r = puentes_v.perfil(via, rel)
        if r is None:
            continue
        pts, der, ds, z, sz = r
        w = via["s"]["ancho"] / 2
        semilla = zlib.crc32(f"{xy[0][0]:.1f},{xy[0][1]:.1f}".encode())
        for d in np.arange(8.0 + semilla % 25, ds[-1] - 5, 40.0):
            i = int(np.searchsorted(ds, d))
            if z[i] - sz[i] < 3.0:  # tramo en terraplén: ya las pone la calle si las hay
                continue
            x, y = pts[i] + der[i] * (w - 0.35)
            if not _en_hoja((x, y), e0h, n1h):
                continue
            modelo = _elegir("farola", ok)
            if modelo:
                gx, gy = config_v.utm_a_juego(x, y)
                out.append((modelo, (gx, gy, float(z[i]) + 0.8, rumbo_hacia(x, y, pts[i]), 1.0), DIST["farola"]))
    # farolas que OSM no tiene (en el centro de Barcelona casi ninguna está mapeada): cada 30 m al
    # tresbolillo en el borde de la acera; a los dos lados en las avenidas anchas
    lamparas = [nd["xy"] for nd in osm["nodos"] if nd["tags"].get("highway") == "street_lamp"]
    arbol_l = shapely.STRtree(shapely.points(np.array(lamparas))) if lamparas else None
    calzadas = shapely.union_all([linea.buffer(w / 2 + 0.3) for linea, _, w in vias]) if vias else None
    if calzadas is not None:
        shapely.prepare(calzadas)
    hechas = set()
    con_farola = {"primary", "secondary", "tertiary", "residential", "unclassified", "living_street", "trunk",
                  "primary_link", "secondary_link", "tertiary_link"}
    for linea, t, w in vias:
        if t.get("highway") not in con_farola or t.get("bridge") not in (None, "no") or \
                t.get("tunnel") not in (None, "no"):
            continue
        for k, d in enumerate(np.arange(12.0, linea.length - 5.0, 30.0)):
            a, b = linea.interpolate(max(d - 1, 0)), linea.interpolate(min(d + 1, linea.length))
            tan = np.array([b.x - a.x, b.y - a.y])
            tan /= np.linalg.norm(tan) + 1e-9
            q = np.array(linea.interpolate(d).coords[0])
            nor = np.array([-tan[1], tan[0]])
            for lado in ((-1, 1) if w >= 12 else ((-1,) if k % 2 else (1,))):
                x, y = q + nor * lado * (w / 2 + 0.7)
                celda10 = (int(x // 10), int(y // 10))
                if not _en_hoja((x, y), e0h, n1h) or celda10 in hechas:
                    continue
                if arbol_l is not None and len(arbol_l.query(Point(x, y).buffer(18.0))):
                    continue  # ya hay farolas de OSM en esta calle
                if np.isfinite(edif[celda(x, y)]) or (calzadas is not None and calzadas.contains(Point(x, y))):
                    continue
                hechas.add(celda10)
                poner("farola", x, y, z_suelo(x, y) + SUBE_ACERA, rumbo_hacia(x, y, q), DIST["farola"])
    # mobiliario
    for nd in osm["nodos"]:
        t, (x, y) = nd["tags"], nd["xy"]
        if not _en_hoja((x, y), e0h, n1h):
            continue
        hw, am = t.get("highway"), t.get("amenity")
        zs = z_suelo(x, y) + SUBE_ACERA
        if hw == "street_lamp":
            v = via_cercana(x, y)
            poner("farola", x, y, zs, rumbo_hacia(x, y, v[0]) if v else 0.0, DIST["farola"])
        elif hw == "traffic_signals":
            v = via_cercana(x, y, 6.0)
            if v is None:
                continue
            q, tan, w, tv = v
            der = np.array([tan[1], -tan[0]])
            doble = tv.get("oneway") not in ("yes", "1", "-1")
            for sentido in ((1, -1) if doble else (1,)):
                # el poste a la derecha de quien llega, antes del cruce, mirando hacia él
                p = q - tan * sentido * 3.0 + der * sentido * (w / 2 + 0.6)
                poner("semaforo", p[0], p[1], z_suelo(*p) + SUBE_ACERA, rumbo_hacia(p[0], p[1], p - tan * sentido * 10),
                      DIST["semaforo"])
        elif hw == "bus_stop" or am in ("bench", "waste_basket", "recycling", "post_box", "bicycle_parking",
                                        "drinking_water"):
            papel = {"bench": "banco", "waste_basket": "papelera", "recycling": "contenedor", "post_box": "buzon",
                     "bicycle_parking": "bicis", "drinking_water": "fuente"}.get(am, "parada")
            v = via_cercana(x, y)
            rumbo = 0.0
            if v is not None:
                q, tan, w, _ = v
                dist_eje = np.hypot(x - q[0], y - q[1])
                if papel in ("parada", "contenedor") and dist_eje < w / 2 + 0.8:  # el nodo está en la calzada
                    lado = np.sign(tan[0] * (y - q[1]) - tan[1] * (x - q[0])) or -1.0
                    nor = np.array([-tan[1], tan[0]]) * lado
                    off = w / 2 + (1.8 if papel == "parada" else 0.2)
                    x, y = q + nor * off
                    zs = z_suelo(x, y) + (SUBE_ACERA if papel == "parada" else 0.04)
                rumbo = rumbo_hacia(x, y, q)
            poner(papel, x, y, zs, rumbo, DIST["otro"])
    return out
