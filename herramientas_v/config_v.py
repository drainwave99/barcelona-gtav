"""Configuración del mapa de GTA V: Barcelona, Badalona, Sant Adrià y Santa Coloma a escala 1:1.

Coordenadas del juego = ETRS89 UTM 31N (EPSG:25831) menos ORIGEN, sin giro (norte arriba).
Las alturas son las ortométricas del LiDAR (metros sobre el nivel del mar), como el Z del juego.
Los Santos se desactiva: el mapa ocupa aproximadamente de -10,5 a +10,5 km en X e Y.
"""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos_v"
MOD = RAIZ / "mod_v"

ORIGEN_E, ORIGEN_N = 430500.0, 4585000.0

# Municipios: código del Catastro -> nombre
MUNICIPIOS = {"08015": "Badalona", "08193": "Sant Adrià de Besòs", "08245": "Santa Coloma de Gramenet",
              "08900": "Barcelona", "08124": "Montcada i Reixac", "08125": "Montgat",
              "08100": "L'Hospitalet de Llobregat"}

# Solo para pruebas mientras Los Santos sigue en el juego: desplaza el mapa (p. ej. al mar del oeste)
# BCN_DESPLAZAMIENTO="-12000,-2500"
DESP_X, DESP_Y = (float(v) for v in os.environ.get("BCN_DESPLAZAMIENTO", "0,0").split(","))

PREFIJO = "bcn_"  # nombres de modelos y texturas


def utm_a_juego(e, n):
    return e - ORIGEN_E + DESP_X, n - ORIGEN_N + DESP_Y


def juego_a_utm(x, y):
    return x + ORIGEN_E - DESP_X, y + ORIGEN_N - DESP_Y
