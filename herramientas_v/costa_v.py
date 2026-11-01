"""El mar según la línea de costa de OpenStreetMap (natural=coastline: tierra a la izquierda del sentido de la
vía). Donde el LiDAR no tiene suelo (el agua), lidar.py rellena con la cota de la playa y el terreno salía como
un plano a 0,2 m sobre el agua del juego, con la foto del mar, por el que se podía andar: el terreno que cae en
el mar se quita y se ve el agua de GTA (a cota 0). Los espigones, muelles y rompeolas son tierra en OSM.

mar() -> Polygon/MultiPolygon del mar en UTM (cacheado en datos_v/costa.pkl)
Uso para regenerar la caché: python costa_v.py
"""
import pickle

import numpy as np
import shapely
from shapely.geometry import LineString, box
from shapely.ops import linemerge, polygonize, unary_union

import config_v

CAJA = (410000.0, 4565000.0, 450000.0, 4605000.0)  # UTM: toda la zona del mapa con margen
_MAR = []


def _lineas_costa():
    import osmium
    from pyproj import Transformer
    import osm_v
    a_utm = Transformer.from_crs(4326, 25831, always_xy=True)
    a_wgs = Transformer.from_crs(25831, 4326, always_xy=True)
    lons, lats = a_wgs.transform([CAJA[0], CAJA[2]], [CAJA[1], CAJA[3]])

    class Lector(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.lineas = []

        def way(self, w):
            if w.tags.get("natural") != "coastline":
                return
            try:
                ll = [(n.lon, n.lat) for n in w.nodes]
            except osmium.InvalidLocationError:
                return
            if not any(lons[0] - 0.05 <= x <= lons[1] + 0.05 and lats[0] - 0.05 <= y <= lats[1] + 0.05 for x, y in ll):
                return
            self.lineas.append(np.array(a_utm.transform(*np.array(ll).T)).T)

    lector = Lector()
    lector.apply_file(str(osm_v.PBF), locations=True, idx="flex_mem")
    return lector.lineas


def _construir(lineas):
    """Caras de la caja cortada por la costa; es mar la que queda a la derecha de un tramo de costa."""
    caja = box(*CAJA)
    trozos = [LineString(q).intersection(caja) for q in lineas if len(q) > 1]
    trozos = [t for t in trozos if not t.is_empty]
    red = unary_union([caja.exterior] + trozos)
    caras = list(polygonize(red))
    mar = []
    for cara in caras:
        votos = 0
        p = cara.representative_point()
        # el tramo de costa más cercano decide: a su derecha (sentido de la vía) es mar
        mejor, dmin = None, np.inf
        for q in lineas:
            ls = LineString(q)
            d = ls.distance(p)
            if d < dmin:
                mejor, dmin = ls, d
        if mejor is None:
            continue
        s = mejor.project(p)
        a = np.array(mejor.interpolate(max(s - 0.5, 0)).coords[0])
        b = np.array(mejor.interpolate(min(s + 0.5, mejor.length)).coords[0])
        c = np.array(mejor.interpolate(s).coords[0])
        t = b - a
        v = np.array([p.x, p.y]) - c
        votos = t[0] * v[1] - t[1] * v[0]  # > 0: a la izquierda (tierra)
        if votos < 0:
            mar.append(cara)
    return shapely.union_all(mar) if mar else None


def mar():
    if _MAR:
        return _MAR[0]
    ruta = config_v.DATOS / "costa.pkl"
    if ruta.exists():
        with open(ruta, "rb") as fh:
            _MAR.append(pickle.load(fh))
    else:
        _MAR.append(None)
    return _MAR[0]


if __name__ == "__main__":
    lineas = _lineas_costa()
    print(len(lineas), "tramos de costa")
    m = _construir(lineas)
    with open(config_v.DATOS / "costa.pkl", "wb") as fh:
        pickle.dump(m, fh)
    print("mar:", None if m is None else round(m.area / 1e6, 1), "km2")
