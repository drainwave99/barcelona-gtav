"""Dibuja una vista previa del mapa (relieve + límite de Badalona + lugares) en docs/vista_previa.png."""
import xml.etree.ElementTree as ET

import numpy as np
import rasterio
from PIL import Image, ImageDraw

import config

TAM = 1024


def gta_a_px(x, y):
    return (x + config.MITAD) / config.LADO * (TAM - 1), (config.MITAD - y) / config.LADO * (TAM - 1)


def main():
    with rasterio.open(config.DATOS / "elevacion" / "relieve_gta.tif") as f:
        h = f.read(1)
    h = np.asarray(Image.fromarray(h).resize((TAM, TAM), Image.BILINEAR))

    # Sombreado simple + color por altura
    gy, gx = np.gradient(h)
    luz = np.clip(0.75 - (gx - gy) * 0.08, 0.3, 1.0)
    t = np.clip(h / max(h.max(), 1), 0, 1)
    rgb = np.stack([90 + 120 * t, 150 + 60 * t, 80 + 90 * t], -1) * luz[..., None]
    mar = h <= 0
    rgb[mar] = (40, 90, 160)
    img = Image.fromarray(rgb.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)

    # Límite municipal (vías de la relación, en el orden en que vienen)
    raiz = ET.parse(config.DATOS / "osm" / "limite_badalona.osm").getroot()
    nodos = {n.get("id"): (float(n.get("lon")), float(n.get("lat"))) for n in raiz.iter("node")}
    for via in raiz.iter("way"):
        refs = [nd.get("ref") for nd in via.iter("nd")]
        lon = np.array([nodos[r][0] for r in refs])
        lat = np.array([nodos[r][1] for r in refs])
        x, y = config.wgs_a_gta(lon, lat)
        d.line([gta_a_px(a, b) for a, b in zip(x, y)], fill=(255, 220, 0), width=2)

    for nombre, (lon, lat) in config.LUGARES.items():
        px, py = gta_a_px(*(float(v) for v in config.wgs_a_gta(lon, lat)))
        d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(230, 30, 30), outline=(255, 255, 255))
        d.text((px + 8, py - 6), nombre, fill=(255, 255, 255))

    # Rejilla cada 1000 unidades GTA
    for v in range(-3000, 3001, 1000):
        a, _ = gta_a_px(v, 0)
        d.line([(a, 0), (a, TAM)], fill=(255, 255, 255, 60), width=1)
        _, b = gta_a_px(0, v)
        d.line([(0, b), (TAM, b)], fill=(255, 255, 255, 60), width=1)

    salida = config.RAIZ / "docs" / "vista_previa.png"
    img.save(salida)
    print(f"Guardado {salida}")


if __name__ == "__main__":
    main()
