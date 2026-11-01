"""Extrae de OpenStreetMap (ODbL) lo que usa el mapa, en ETRS89 UTM 31N.

Entrada: datos/osm/cataluna-latest.osm.pbf
Salida:  datos_v/osm.pkl con
  vias      lista de dict(tags, xy (n, 2))  carreteras, calles, caminos, vías de tren y tranvía
  areas     lista de dict(tags, xy)         parques, plazas, zonas verdes, agua, aparcamientos...
  nodos     lista de dict(tags, xy (2,))    árboles, farolas, bancos, semáforos, pasos de cebra, paradas...
Uso: python osm_v.py E0 E1 N0 N1  (en km)
"""
import pickle
import sys

import numpy as np
import osmium
from pyproj import Transformer

import config_v

PBF = config_v.RAIZ / "datos" / "osm" / "cataluna-latest.osm.pbf"
CLAVES_AREA = ("leisure", "landuse", "natural", "amenity", "place", "area:highway", "man_made", "waterway")
NODOS = {"natural": {"tree"}, "highway": {"street_lamp", "traffic_signals", "crossing", "bus_stop", "stop",
                                          "give_way"},
         "amenity": {"bench", "waste_basket", "recycling", "fountain", "drinking_water", "bicycle_parking",
                     "post_box", "telephone", "parking_entrance"},
         "leisure": {"playground", "picnic_table"}, "man_made": {"street_cabinet"},
         "railway": {"level_crossing", "station", "subway_entrance", "tram_stop"},
         "public_transport": {"stop_position", "platform"}}


class Lector(osmium.SimpleHandler):
    def __init__(self, caja):
        super().__init__()
        self.caja = caja
        self.a_utm = Transformer.from_crs(4326, 25831, always_xy=True)
        self.vias, self.areas, self.nodos = [], [], []

    def dentro(self, lon, lat):
        w, s, e, n = self.caja
        return w <= lon <= e and s <= lat <= n

    def node(self, n):
        t = dict(n.tags)
        if not any(t.get(k) in v for k, v in NODOS.items()):
            return
        if self.dentro(n.location.lon, n.location.lat):
            self.nodos.append(dict(tags=t, xy=np.array(self.a_utm.transform(n.location.lon, n.location.lat))))

    def way(self, w):
        t = dict(w.tags)
        es_via = "highway" in t or "railway" in t
        es_area = any(k in t for k in CLAVES_AREA)
        if not (es_via or es_area) or "building" in t:
            return
        try:
            lonlat = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if not any(self.dentro(*p) for p in lonlat):
            return
        xy = np.array(self.a_utm.transform(*np.array(lonlat).T)).T
        cerrado = len(lonlat) > 3 and w.nodes[0].ref == w.nodes[-1].ref
        if es_area and cerrado and t.get("area") != "no" and not ("highway" in t and t.get("area") != "yes"):
            self.areas.append(dict(tags=t, xy=xy))
        elif es_via:
            self.vias.append(dict(tags=t, xy=xy))


def main():
    e0, e1, n0, n1 = (float(a) * 1000 for a in sys.argv[1:5])
    a_wgs = Transformer.from_crs(25831, 4326, always_xy=True)
    lons, lats = a_wgs.transform([e0, e1, e0, e1], [n0, n0, n1, n1])
    lector = Lector((min(lons) - 0.005, min(lats) - 0.005, max(lons) + 0.005, max(lats) + 0.005))
    lector.apply_file(str(PBF), locations=True, idx="flex_mem")
    with open(config_v.DATOS / "osm.pkl", "wb") as fh:
        pickle.dump(dict(vias=lector.vias, areas=lector.areas, nodos=lector.nodos), fh)
    puentes = sum(1 for v in lector.vias if v["tags"].get("bridge"))
    print(f"OSM: {len(lector.vias)} vías ({puentes} puentes), {len(lector.areas)} áreas, {len(lector.nodos)} nodos")


if __name__ == "__main__":
    main()
