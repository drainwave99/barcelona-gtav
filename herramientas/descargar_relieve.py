"""Descarga el relieve del mapa y lo convierte a coordenadas GTA (girado y escalado según config.py).

Fuente: teselas Terrarium de AWS (Mapzen), sin clave. Zoom 15 = ~3,6 m/píxel en Badalona.
Salidas en datos/elevacion/:
  relieve_gta.tif        float32 (unidades GTA) de -3000 a +3000, fila 0 = arriba del mapa
  relieve_gta_2049.png   heightmap 16 bits 2049x2049 con lo mismo
  relieve_gta.npy        lo mismo en formato numpy (lo leen los scripts de Blender)
  relieve_gta.txt        altura mínima/máxima para reescalar el PNG
"""
import io
import math
import time

import numpy as np
import rasterio
import requests
from PIL import Image
from rasterio.transform import from_bounds

import config

ZOOM = 15
URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
CACHE = config.DATOS / "elevacion" / "teselas"
SALIDA = config.DATOS / "elevacion"
RESOLUCION = 2049  # píxeles por lado del heightmap GTA (~2,9 m/píxel)


def lonlat_a_tesela(lon, lat, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def lonlat_a_tesela_np(lon, lat, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * n
    return x, y


def muestrear_bilineal(img, px, py):
    x0 = np.clip(np.floor(px).astype(int), 0, img.shape[1] - 2)
    y0 = np.clip(np.floor(py).astype(int), 0, img.shape[0] - 2)
    fx = np.clip(px - x0, 0, 1)
    fy = np.clip(py - y0, 0, 1)
    arriba = img[y0, x0] * (1 - fx) + img[y0, x0 + 1] * fx
    abajo = img[y0 + 1, x0] * (1 - fx) + img[y0 + 1, x0 + 1] * fx
    return (arriba * (1 - fy) + abajo * fy).astype(np.float32)


def bajar_tesela(x, y):
    ruta = CACHE / f"{ZOOM}_{x}_{y}.png"
    if not ruta.exists():
        for intento in range(4):
            r = requests.get(URL.format(z=ZOOM, x=x, y=y), timeout=60)
            if r.status_code == 200:
                ruta.write_bytes(r.content)
                break
            time.sleep(2 * (intento + 1))
        else:
            raise RuntimeError(f"Tesela {x},{y}: HTTP {r.status_code}")
    rgb = np.asarray(Image.open(io.BytesIO(ruta.read_bytes())).convert("RGB"), dtype=np.float32)
    return rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    sur, oeste, norte, este = config.bbox_wgs(margen=0.003)
    x0, y0 = (int(v) for v in lonlat_a_tesela(oeste, norte, ZOOM))
    x1, y1 = (int(v) for v in lonlat_a_tesela(este, sur, ZOOM))
    nx, ny = x1 - x0 + 1, y1 - y0 + 1
    print(f"Descargando {nx * ny} teselas de elevación (zoom {ZOOM})...")

    mosaico = np.zeros((ny * 256, nx * 256), dtype=np.float32)
    for j in range(ny):
        for i in range(nx):
            mosaico[j * 256:(j + 1) * 256, i * 256:(i + 1) * 256] = bajar_tesela(x0 + i, y0 + j)

    # Para cada píxel del mapa GTA (fila 0 = arriba del mapa): coordenadas reales -> píxel del mosaico
    paso = config.LADO / (RESOLUCION - 1)
    gx = -config.MITAD + np.arange(RESOLUCION) * paso
    gy = config.MITAD - np.arange(RESOLUCION) * paso
    GX, GY = np.meshgrid(gx, gy)
    lon, lat = config.gta_a_wgs(GX.ravel(), GY.ravel())
    tx, ty = lonlat_a_tesela_np(np.asarray(lon), np.asarray(lat), ZOOM)
    px = (tx - x0) * 256 - 0.5
    py = (ty - y0) * 256 - 0.5
    destino = muestrear_bilineal(mosaico, px, py).reshape(RESOLUCION, RESOLUCION)

    # Cerca del nivel del mar los datos oscilan y el agua del juego parpadearía con el suelo:
    # lo que está por debajo de 0,5 m pasa a fondo marino (-3 m) y la orilla queda al menos a 0,8 m.
    destino = np.where(destino < 0.5, -3.0, np.maximum(destino, 0.8)).astype(np.float32)
    # Las alturas también se escalan, para que las pendientes no sean más empinadas que las reales
    destino *= config.ESCALA

    tif = SALIDA / "relieve_gta.tif"
    t_dst = from_bounds(-config.MITAD, -config.MITAD, config.MITAD, config.MITAD, RESOLUCION, RESOLUCION)
    with rasterio.open(tif, "w", driver="GTiff", width=RESOLUCION, height=RESOLUCION, count=1,
                       dtype="float32", transform=t_dst) as f:
        f.write(destino, 1)
    # Blender trae numpy pero no rasterio: copia en .npy para los scripts de Blender
    np.save(SALIDA / "relieve_gta.npy", destino)

    hmin, hmax = float(destino.min()), float(destino.max())
    png16 = ((destino - hmin) / (hmax - hmin) * 65535).round().astype(np.uint16)
    Image.fromarray(png16).save(SALIDA / f"relieve_gta_{RESOLUCION}.png")
    (SALIDA / "relieve_gta.txt").write_text(
        f"altura_min_m={hmin:.2f}\naltura_max_m={hmax:.2f}\n"
        f"cubre_gta_x=-{config.MITAD:.0f}..{config.MITAD:.0f}\ncubre_gta_y=-{config.MITAD:.0f}..{config.MITAD:.0f}\n"
        f"pixel_m={config.LADO / (RESOLUCION - 1):.3f}\n", encoding="utf-8")

    print(f"Guardado {tif}")
    print(f"Altura mínima {hmin:.1f} m, máxima {hmax:.1f} m")
    for nombre, (lon, lat) in config.LUGARES.items():
        x, y = config.wgs_a_gta(lon, lat)
        col = int((x + config.MITAD) / config.LADO * (RESOLUCION - 1))
        fila = int((config.MITAD - y) / config.LADO * (RESOLUCION - 1))
        print(f"  {nombre}: {destino[fila, col]:.1f} m")


if __name__ == "__main__":
    main()
