"""Configuración común del mapa: zona de Badalona y conversión de coordenadas reales a coordenadas GTA.

Encaje elegido: todo el municipio de Badalona + Tres Xemeneies + Canyet + Can Ruti, girado para que
la costa quede horizontal con el mar al sur del mapa y la montaña al norte, a escala 0,95.
Coordenadas GTA: X hacia la derecha, Y hacia arriba del mapa, (0, 0) en el centro. Mapa de -3000 a +3000.

  GTA = ESCALA * Giro(ANGULO) * (UTM - CENTRO)
"""
import math
from pathlib import Path

import numpy as np
from pyproj import Transformer

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"

# Proyección métrica oficial en Catalunya: ETRS89 / UTM 31N
EPSG_UTM = 25831

LADO = 6000.0
MITAD = LADO / 2

# Giro de 316° (antihorario): la costa (rumbo ~45°) queda horizontal y el mar abajo.
ANGULO = 316.0
# 0,962 sería el máximo; se deja margen para que nada quede pegado al borde del mapa.
ESCALA = 0.95

_a_utm = Transformer.from_crs(4326, EPSG_UTM, always_xy=True)
_a_wgs = Transformer.from_crs(EPSG_UTM, 4326, always_xy=True)

_r = math.radians(ANGULO)
_ROT = np.array([[math.cos(_r), -math.sin(_r)], [math.sin(_r), math.cos(_r)]])

# Centro de la caja que contiene Badalona y los lugares obligatorios (calculado con herramientas/encaje.py)
CENTRO_E = 435921.6
CENTRO_N = 4590151.4

# Lugares que tienen que quedar dentro del mapa sí o sí
LUGARES = {
    "Tres Xemeneies": (2.2357, 41.4268),
    "Pont del Petroli": (2.2486, 41.4430),
    "Ajuntament": (2.2453, 41.4504),
    "Dalt la Vila": (2.2445, 41.4515),
    "Canyet": (2.2348, 41.4757),
    "Can Ruti (hospital)": (2.2376, 41.4812),
}


def utm_a_gta(e, n):
    e = np.asarray(e, dtype=float) - CENTRO_E
    n = np.asarray(n, dtype=float) - CENTRO_N
    x = ESCALA * (_ROT[0, 0] * e + _ROT[0, 1] * n)
    y = ESCALA * (_ROT[1, 0] * e + _ROT[1, 1] * n)
    return x, y


def gta_a_utm(x, y):
    x = np.asarray(x, dtype=float) / ESCALA
    y = np.asarray(y, dtype=float) / ESCALA
    # inversa de un giro = traspuesta
    e = _ROT[0, 0] * x + _ROT[1, 0] * y + CENTRO_E
    n = _ROT[0, 1] * x + _ROT[1, 1] * y + CENTRO_N
    return e, n


def wgs_a_gta(lon, lat):
    return utm_a_gta(*_a_utm.transform(lon, lat))


def gta_a_wgs(x, y):
    return _a_wgs.transform(*gta_a_utm(x, y))


def bbox_wgs(margen=0.0):
    """(sur, oeste, norte, este) en lat/lon que cubre todo el mapa girado, con margen en grados."""
    esquinas = [gta_a_wgs(x, y) for x in (-MITAD, MITAD) for y in (-MITAD, MITAD)]
    lons = [float(c[0]) for c in esquinas]
    lats = [float(c[1]) for c in esquinas]
    return min(lats) - margen, min(lons) - margen, max(lats) + margen, max(lons) + margen


if __name__ == "__main__":
    s, w, n, e = bbox_wgs()
    print(f"Giro {ANGULO}°, escala {ESCALA}")
    print(f"Bbox WGS84 a descargar: sur {s:.5f} oeste {w:.5f} norte {n:.5f} este {e:.5f}")
    for nombre, (lon, lat) in LUGARES.items():
        x, y = wgs_a_gta(lon, lat)
        dentro = abs(x) <= MITAD and abs(y) <= MITAD
        print(f"{nombre:22s} GTA ({float(x):8.1f}, {float(y):8.1f})  {'dentro' if dentro else 'FUERA'}")
