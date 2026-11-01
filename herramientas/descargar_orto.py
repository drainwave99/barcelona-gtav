"""Textura del suelo a partir de la ortofoto del ICGC (foto aérea, licencia CC BY 4.0).

Descarga las teselas de la ortofoto (zoom 18, ~0,45 m por píxel) que cubren el mapa y las
remuestrea al mapa girado del juego: un PNG por trozo de terreno.

Salida: datos/generado/suelo_orto/suelo_FF_CC.png (generar_mapa.py las usa si existen) y docs/mapa_orto.png
Caché de teselas: datos/orto/18/x_y.jpg
"""
import io
import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests
from PIL import Image

import config

URL = "https://geoserveis.icgc.cat/servei/catalunya/mapa-base/wmts/orto/MON3857NW/{z}/{x}/{y}.png"
Z = 18
TROZOS = 16
PX_TROZO = 1024  # ~0,37 m por píxel
CACHE = config.DATOS / "orto" / str(Z)
SALIDA = config.DATOS / "generado" / "suelo_orto"


def a_tesela(lon, lat):
    """Coordenadas de píxel globales (tesela * 256) en Web Mercator."""
    n = 2 ** Z * 256
    x = (np.asarray(lon) + 180) / 360 * n
    lat_r = np.radians(lat)
    y = (1 - np.log(np.tan(lat_r) + 1 / np.cos(lat_r)) / math.pi) / 2 * n
    return x, y


def bajar(xy):
    x, y = xy
    ruta = CACHE / f"{x}_{y}.jpg"
    if ruta.exists():
        return
    for _ in range(4):
        try:
            r = requests.get(URL.format(z=Z, x=x, y=y), timeout=30)
            if r.status_code == 200:
                Image.open(io.BytesIO(r.content)).convert("RGB").save(ruta, quality=92)
                return
        except requests.RequestException:
            pass
    print("no se pudo bajar", x, y)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    SALIDA.mkdir(parents=True, exist_ok=True)
    # Teselas que cubren las esquinas del mapa girado
    esquinas = np.array([(-1, -1), (-1, 1), (1, -1), (1, 1)]) * (config.MITAD + 50)
    lon, lat = config.gta_a_wgs(esquinas[:, 0], esquinas[:, 1])
    px, py = a_tesela(lon, lat)
    xs = range(int(px.min() // 256), int(px.max() // 256) + 1)
    ys = range(int(py.min() // 256), int(py.max() // 256) + 1)
    lista = [(x, y) for x in xs for y in ys]
    print(f"{len(lista)} teselas de la ortofoto")
    with ThreadPoolExecutor(8) as pool:
        for i, _ in enumerate(pool.map(bajar, lista)):
            if i % 500 == 0:
                print(f"  {i}/{len(lista)}")

    cache_img = {}

    def tesela(x, y):
        if (x, y) not in cache_img:
            ruta = CACHE / f"{x}_{y}.jpg"
            cache_img[(x, y)] = np.asarray(Image.open(ruta), dtype=np.float32) if ruta.exists() \
                else np.full((256, 256, 3), 90, np.float32)
        return cache_img[(x, y)]

    tam = config.LADO / TROZOS
    vista = Image.new("RGB", (TROZOS * 64, TROZOS * 64))
    for f in range(TROZOS):
        cache_img.clear()  # cada fila usa sus teselas: no llenar la memoria
        for c in range(TROZOS):
            # Centro de cada píxel de este trozo en coordenadas del juego
            t = (np.arange(PX_TROZO) + 0.5) / PX_TROZO * tam
            gx = -config.MITAD + c * tam + t[None, :].repeat(PX_TROZO, 0)
            gy = config.MITAD - f * tam - t[:, None].repeat(PX_TROZO, 1)
            lo, la = config.gta_a_wgs(gx.ravel(), gy.ravel())
            mx, my = a_tesela(lo, la)
            tx, ty = (mx // 256).astype(int), (my // 256).astype(int)
            salida = np.zeros((PX_TROZO * PX_TROZO, 3), np.float32)
            for (a, b) in set(zip(tx.tolist(), ty.tolist())):
                sel = (tx == a) & (ty == b)
                img = tesela(a, b)
                u = np.clip(mx[sel] - a * 256, 0, 255.0)
                v = np.clip(my[sel] - b * 256, 0, 255.0)
                u0, v0 = np.minimum(u.astype(int), 254), np.minimum(v.astype(int), 254)
                du, dv = (u - u0)[:, None], (v - v0)[:, None]
                salida[sel] = (img[v0, u0] * (1 - du) * (1 - dv) + img[v0, u0 + 1] * du * (1 - dv)
                               + img[v0 + 1, u0] * (1 - du) * dv + img[v0 + 1, u0 + 1] * du * dv)
            trozo = Image.fromarray(salida.reshape(PX_TROZO, PX_TROZO, 3).clip(0, 255).astype(np.uint8))
            trozo.save(SALIDA / f"suelo_{f:02d}_{c:02d}.png")
            vista.paste(trozo.resize((64, 64), Image.LANCZOS), (c * 64, f * 64))
        print(f"fila {f + 1}/{TROZOS}")
    vista.save(config.RAIZ / "docs" / "mapa_orto.png")
    print(f"Suelo con ortofoto en {SALIDA}")


if __name__ == "__main__":
    main()
