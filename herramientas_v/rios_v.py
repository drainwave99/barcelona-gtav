"""Ríos de OSM (multipolígonos natural=water + water=river / waterway=riverbank) en la zona del mapa, que osm_v
no saca (solo lee vías sueltas): el Besòs. -> datos_v/rios.pkl: lista de shapely Polygon en UTM 31N.
Uso: python rios_v.py"""
import pickle

import osmium
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon

import config_v
from osm_v import PBF

CAJA = (2.10, 41.33, 2.30, 41.50)  # lon/lat: Barcelona, Sant Adrià, Badalona, Santa Coloma


class Rios(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.a_utm = Transformer.from_crs(4326, 25831, always_xy=True)
        self.polis = []

    def area(self, a):
        t = a.tags
        rio = (t.get("natural") == "water" and t.get("water") in ("river", "canal")) or \
            t.get("waterway") == "riverbank"
        if not rio:
            return
        for anillo in a.outer_rings():
            ll = [(n.lon, n.lat) for n in anillo]
            if not any(CAJA[0] < x < CAJA[2] and CAJA[1] < y < CAJA[3] for x, y in ll):
                continue
            ext = list(zip(*self.a_utm.transform(*zip(*ll))))
            huecos = [list(zip(*self.a_utm.transform(*zip(*[(n.lon, n.lat) for n in h]))))
                      for h in a.inner_rings(anillo)]
            p = shapely.make_valid(Polygon(ext, huecos))
            if p.area > 500:
                self.polis.append((t.get("name", ""), p))


def main():
    r = Rios()
    r.apply_file(str(PBF), locations=True, idx="flex_mem")
    with open(config_v.DATOS / "rios.pkl", "wb") as fh:
        pickle.dump([p for _, p in r.polis], fh)
    for n, p in r.polis:
        c = p.centroid
        print(f"río {n or '?'}: {p.area / 1e4:.1f} ha en {c.x:.0f} {c.y:.0f}")


if __name__ == "__main__":
    main()
