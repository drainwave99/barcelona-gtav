"""Calcula el centro y la escala máxima para que Badalona y los lugares obligatorios quepan en el mapa GTA.

El resultado (CENTRO_E, CENTRO_N, escala máxima) se copia a config.py.
"""
import math
import xml.etree.ElementTree as ET

import numpy as np
from pyproj import Transformer

import config

MARGEN = 200  # metros alrededor de cada lugar obligatorio

t = Transformer.from_crs(4326, config.EPSG_UTM, always_xy=True)
raiz = ET.parse(config.DATOS / "osm" / "limite_badalona.osm").getroot()
pts = [t.transform(float(n.get("lon")), float(n.get("lat"))) for n in raiz.iter("node")]
for lon, lat in config.LUGARES.values():
    e, n = t.transform(lon, lat)
    pts += [(e + dx, n + dy) for dx in (-MARGEN, MARGEN) for dy in (-MARGEN, MARGEN)]
P = np.array(pts)

r = math.radians(config.ANGULO)
R = np.array([[math.cos(r), -math.sin(r)], [math.sin(r), math.cos(r)]])
Q = P @ R.T
tam = Q.max(0) - Q.min(0)
centro_girado = (Q.max(0) + Q.min(0)) / 2
centro = R.T @ centro_girado

print(f"Giro {config.ANGULO}°: caja {tam[0]:.0f} x {tam[1]:.0f} m")
print(f"Escala máxima: {config.LADO / tam.max():.3f}")
print(f"CENTRO_E = {centro[0]:.1f}")
print(f"CENTRO_N = {centro[1]:.1f}")
