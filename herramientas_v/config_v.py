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
# carpeta del juego (GTA V Legacy); otra instalación: variable de entorno GTA_V_DIR
GTA = Path(os.environ.get("GTA_V_DIR", r"C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V"))

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


# Hojas generadas que se dejan fuera del mapa (2026-11-02): Montcada y la sierra de encima, la vertiente del Vallès
# de Collserola (el Tibidabo, 426585, se queda), la Zona Franca pasado el puerto y Montgat. Siguen en
# mod_v/prototipo: quitarlas de aquí las vuelve a meter.
HOJAS_FUERA = set("""
429589 429590 429594 430590 430591 430592 430593 430594 431591 431592 431593 431594 432591 432592 432593 432594
433591 433592 433593 433594 434591 434594 435594
426586 426587 426588 427588 427589 428589
426578 427578
438591
""".split())


def hojas(con_colocacion=False):
    """Las hojas del mapa (mod_v/prototipo/<EEENNN>, sin HOJAS_FUERA), ordenadas."""
    base = MOD / "prototipo"
    return sorted(h.name for h in base.iterdir() if len(h.name) == 6 and h.name.isdigit() and h.name not in HOJAS_FUERA
                  and (not con_colocacion or (h / "colocacion.pkl").exists()))
