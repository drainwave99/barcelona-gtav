"""Recorta el área del mapa del extracto de Cataluña de Geofabrik (más fiable que Overpass).

Entrada: datos/osm/cataluna-latest.osm.pbf
  (https://download.geofabrik.de/europe/spain/cataluna-latest.osm.pbf)
Salida:  datos/osm/badalona.osm

Se guardan las vías con algún nodo dentro del área, con todos sus nodos, y las relaciones
multipolígono (edificios, parques, bosques...) que usan esas vías. Las relaciones de límites
y rutas no se guardan: abarcan media Cataluña y no hacen falta.
"""
import time

import osmium

import config

ENTRADA = config.DATOS / "osm" / "cataluna-latest.osm.pbf"
SALIDA = config.DATOS / "osm" / "badalona.osm"
TIPOS_RELACION = {"multipolygon", "building"}


def main():
    sur, oeste, norte, este = config.bbox_wgs(margen=0.002)
    t0 = time.time()

    dentro = set()
    for n in osmium.FileProcessor(str(ENTRADA), osmium.osm.NODE):
        loc = n.location
        if loc.valid() and sur <= loc.lat <= norte and oeste <= loc.lon <= este:
            dentro.add(n.id)
    print(f"1/4 nodos dentro: {len(dentro)} ({time.time() - t0:.0f} s)")

    vias, nodos = set(), set()
    relaciones, vias_extra = set(), set()
    for o in osmium.FileProcessor(str(ENTRADA), osmium.osm.WAY | osmium.osm.RELATION):
        if o.is_way():
            refs = [nd.ref for nd in o.nodes]
            if any(r in dentro for r in refs):
                vias.add(o.id)
                nodos.update(refs)
        elif o.tags.get("type") in TIPOS_RELACION:
            miembros = [m.ref for m in o.members if m.type == "w"]
            if any(m in vias for m in miembros):
                relaciones.add(o.id)
                vias_extra.update(m for m in miembros if m not in vias)
    print(f"2/4 vías: {len(vias)}, relaciones: {len(relaciones)}, vías de relaciones: {len(vias_extra)} ({time.time() - t0:.0f} s)")

    if vias_extra:
        for w in osmium.FileProcessor(str(ENTRADA), osmium.osm.WAY):
            if w.id in vias_extra:
                nodos.update(nd.ref for nd in w.nodes)
        vias |= vias_extra
    print(f"3/4 nodos necesarios: {len(nodos)} ({time.time() - t0:.0f} s)")

    if SALIDA.exists():
        SALIDA.unlink()
    escritor = osmium.SimpleWriter(str(SALIDA))
    try:
        for o in osmium.FileProcessor(str(ENTRADA)):
            if (o.is_node() and o.id in nodos) or (o.is_way() and o.id in vias) or (o.is_relation() and o.id in relaciones):
                escritor.add(o)
    finally:
        escritor.close()
    print(f"4/4 guardado {SALIDA} ({SALIDA.stat().st_size / 1e6:.1f} MB, {time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
