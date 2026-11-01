"""Busca en OSM el centro de una calle y da su posición en coordenadas GTA con la altura del terreno.

Uso: python herramientas/punto_salida.py "La Rambla"
"""
import sys
import xml.etree.ElementTree as ET

import numpy as np

import config


def altura(h, x, y):
    n = h.shape[0] - 1
    return float(h[int(round((config.MITAD - y) / config.LADO * n)), int(round((x + config.MITAD) / config.LADO * n))])


def main():
    buscado = sys.argv[1] if len(sys.argv) > 1 else "La Rambla"
    nodos, vias = {}, []
    for _, el in ET.iterparse(config.DATOS / "osm" / "badalona.osm"):
        if el.tag == "node":
            nodos[el.get("id")] = (float(el.get("lon")), float(el.get("lat")))
        elif el.tag == "way":
            tags = {t.get("k"): t.get("v") for t in el.iter("tag")}
            if tags.get("name") == buscado and "highway" in tags:
                vias.append([nd.get("ref") for nd in el.iter("nd")])
            el.clear()
    if not vias:
        sys.exit(f"No hay ninguna calle llamada {buscado!r}")
    puntos = [nodos[r] for v in vias for r in v if r in nodos]
    # Solo los puntos dentro del mapa (hay calles con el mismo nombre en Barcelona)
    puntos = [p for p in puntos if all(abs(float(c)) < config.MITAD - 50 for c in config.wgs_a_gta(*p))]
    if not puntos:
        sys.exit(f"{buscado!r} no está dentro del mapa")
    lon, lat = np.mean([p[0] for p in puntos]), np.mean([p[1] for p in puntos])
    # El nodo de la calle más cercano al centro (para caer encima de la calle, no en un edificio)
    cerca = min(puntos, key=lambda p: (p[0] - lon) ** 2 + (p[1] - lat) ** 2)
    x, y = (float(v) for v in config.wgs_a_gta(*cerca))
    h = np.load(config.DATOS / "elevacion" / "relieve_gta.npy")
    print(f"{buscado}: {len(vias)} tramos; salida GTA ({x:.2f}, {y:.2f}, {altura(h, x, y) + 1.5:.2f})")


if __name__ == "__main__":
    main()
