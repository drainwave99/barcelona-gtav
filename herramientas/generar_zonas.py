"""Nombres de zona del juego (el texto que sale abajo a la derecha al entrar en un barrio).

Toma los barrios de OSM (place=suburb/quarter/neighbourhood y pueblos vecinos), reparte el mapa en
casillas de 200 m con el barrio más cercano y junta las casillas seguidas de cada fila.

Salidas:
  mod/data/info.zon          zonas (sustituye las de Los Santos, San Fierro y Las Venturas)
  mod/text/zonas.json        {clave GXT: nombre} que instalar_en_juego.py añade a los .gxt
"""
import json
import unicodedata

import numpy as np
import osmium

import config

CASILLA = 200
LUGARES_OSM = {"suburb", "quarter", "neighbourhood", "town", "village", "city"}
MAX_ZONAS = 380  # las que tiene el info.zon original


def sin_acentos(texto):
    # Las fuentes del juego no tienen todos los acentos: se dejan solo letras ASCII
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if ord(c) < 128)


def barrios():
    """Nodos place=* con nombre dentro del mapa (del extracto de Cataluña: badalona.osm solo tiene
    los nodos de calles y edificios)."""
    nombres, xs, ys = [], [], []
    for nodo in osmium.FileProcessor(str(config.DATOS / "osm" / "cataluna-latest.osm.pbf"), osmium.osm.NODE) \
            .with_filter(osmium.filter.TagFilter(*[("place", v) for v in LUGARES_OSM])):
        if "name" not in nodo.tags or nodo.tags["name"] == "Badalona":  # dentro de Badalona, los barrios
            continue
        x, y = config.wgs_a_gta(nodo.location.lon, nodo.location.lat)
        if abs(x) < config.MITAD + 500 and abs(y) < config.MITAD + 500:
            nombres.append(sin_acentos(nodo.tags["name"]))
            xs.append(float(x))
            ys.append(float(y))
    return nombres, np.array(xs), np.array(ys)


def main():
    nombres, bx, by = barrios()
    print(f"{len(nombres)} barrios: {', '.join(sorted(set(nombres)))}")
    h = np.load(config.DATOS / "elevacion" / "relieve_gta.npy")
    n = h.shape[0] - 1
    celdas = int(config.LADO // CASILLA)
    claves = {}
    lineas = ["zone"]
    for fila in range(celdas):
        y1 = config.MITAD - fila * CASILLA
        y0 = y1 - CASILLA
        actual, inicio = None, 0
        for col in range(celdas + 1):
            barrio = None
            if col < celdas:
                x0 = -config.MITAD + col * CASILLA
                cx, cy = x0 + CASILLA / 2, y0 + CASILLA / 2
                trozo = h[int((config.MITAD - y1) / config.LADO * n):int((config.MITAD - y0) / config.LADO * n) + 1,
                          int((x0 + config.MITAD) / config.LADO * n):int((x0 + CASILLA + config.MITAD) / config.LADO * n) + 1]
                if (trozo > 0).mean() > 0.3:  # en el mar no hay nombre
                    barrio = nombres[int(np.argmin((bx - cx) ** 2 + (by - cy) ** 2))]
            if barrio != actual:
                if actual is not None:
                    clave = claves.setdefault(actual, f"BDN{len(claves):02d}")
                    xa, xb = -config.MITAD + inicio * CASILLA, -config.MITAD + col * CASILLA
                    lineas.append(f"{clave}, 0, {xa:.1f}, {y0:.1f}, -50.0, {xb:.1f}, {y1:.1f}, 500.0, 1, {clave}")
                actual, inicio = barrio, col
    lineas.append("end")
    if len(lineas) - 2 > MAX_ZONAS:
        raise SystemExit(f"{len(lineas) - 2} zonas: más de {MAX_ZONAS}, usa casillas más grandes")
    (config.RAIZ / "mod" / "data").mkdir(parents=True, exist_ok=True)
    (config.RAIZ / "mod" / "data" / "info.zon").write_text("\r\n".join(lineas) + "\r\n", encoding="ascii", newline="")
    (config.RAIZ / "mod" / "text").mkdir(parents=True, exist_ok=True)
    with open(config.RAIZ / "mod" / "text" / "zonas.json", "w", encoding="ascii") as fh:
        json.dump({clave: nombre for nombre, clave in claves.items()}, fh, indent=1)
    print(f"info.zon: {len(lineas) - 2} zonas, {len(claves)} nombres")


if __name__ == "__main__":
    main()
