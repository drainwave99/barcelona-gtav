"""Descarga y procesa el LiDAR territorial del ICGC (2021-2023, CC BY 4.0) por hojas de 1 x 1 km.

Cada hoja (LAZ de 250-1000 MB, ETRS89 UTM 31N, altitudes ortométricas) se reduce a rejillas de
0,5 m en datos_v/lidar/hojas/EEENNN.npz y el LAZ se borra (se puede volver a bajar):
  suelo     altura del terreno (clases 2 y 8; huecos rellenados)            float32
  edificio  altura máxima de los tejados (6 y 77), NaN fuera                 float32
  puente    altura máxima de los tableros de puente (17), NaN fuera         float32
  veg       altura máxima de la vegetación (3, 4, 5), NaN fuera             float32
  color     color medio del punto más alto (ortofoto 15 cm), RGB            uint8
  fachada   puntos de fachada (76) por celda                                uint8
Fila 0 = norte. La celda (f, c) cubre E0 + c*0,5 .. E0 + (c+1)*0,5, N1 - (f+1)*0,5 .. N1 - f*0,5.

Uso: python lidar.py EEENNN [EEENNN ...]   o   python lidar.py zona E0 E1 N0 N1   (en km)
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import laspy
import numpy as np
from scipy import ndimage

RAIZ = Path(__file__).resolve().parent.parent
LAZ = RAIZ / "datos_v" / "lidar" / "laz"
HOJAS = RAIZ / "datos_v" / "lidar" / "hojas"
URL = ("https://datacloud.icgc.cat/datacloud/lidar-territorial/laz_unzip/full10km{d10}/"
       "lidar-territorial-v3r1-full1km{hoja}-2021-2023.laz")
CELDA = 0.5
N = int(1000 / CELDA)


def url(hoja):
    e, n = int(hoja[:3]), 4000 + int(hoja[3:])
    return URL.format(d10=f"{e // 10}{n // 10 % 100:02d}", hoja=hoja)


def descargar(hoja):
    destino = LAZ / f"{hoja}.laz"
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    LAZ.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(".part")
    r = subprocess.run(["curl", "-s", "-f", "-C", "-", "--retry", "5", "-o", str(temporal), url(hoja)])
    if r.returncode not in (0, 33):
        raise RuntimeError(f"{hoja}: curl {r.returncode}")
    temporal.rename(destino)
    return destino


TROZO = 4_000_000  # puntos por lectura: un LAZ entero (hasta 80 M puntos) no cabe en memoria


def acumular(rej, idx, z, mascara):
    """Z máxima por celda de los puntos de la máscara (rej empieza a -inf)."""
    np.maximum.at(rej, idx[mascara], z[mascara])


def rejilla(rej):
    rej = rej.copy()
    rej[np.isinf(rej)] = np.nan
    return rej.reshape(N, N)


def procesar(hoja):
    salida = HOJAS / f"{hoja}.npz"
    if salida.exists():
        return
    ruta = descargar(hoja)
    e0, n1 = int(hoja[:3]) * 1000, (4000 + int(hoja[3:]) + 1) * 1000
    capas = {k: np.full(N * N, -np.inf, dtype=np.float32) for k in ("suelo", "edificio", "puente", "veg", "alto")}
    color = np.zeros((N * N, 3), dtype=np.uint8)
    fachada = np.zeros(N * N, dtype=np.int64)
    with laspy.open(ruta) as lector:
        for las in lector.chunk_iterator(TROZO):
            z = np.asarray(las.z, dtype=np.float32)
            clase = np.asarray(las.classification)
            c = np.clip(((np.asarray(las.x) - e0) / CELDA).astype(np.int32), 0, N - 1)
            f = np.clip(((n1 - np.asarray(las.y)) / CELDA).astype(np.int32), 0, N - 1)
            idx = f * N + c
            del c, f
            acumular(capas["suelo"], idx, z, np.isin(clase, (2, 8)))
            acumular(capas["edificio"], idx, z, np.isin(clase, (6, 77)))
            acumular(capas["puente"], idx, z, clase == 17)
            acumular(capas["veg"], idx, z, np.isin(clase, (3, 4, 5)))
            fachada += np.bincount(idx[clase == 76], minlength=N * N)
            # Color del punto más alto de cada celda (lo que se ve desde arriba: tejado, copa, asfalto)
            util = np.flatnonzero(~np.isin(clase, (7, 12, 18)))
            orden = util[np.lexsort((z[util], idx[util]))]
            ultimo = orden[np.r_[idx[orden][1:] != idx[orden][:-1], True]]
            celdas = idx[ultimo]
            mejor = z[ultimo] > capas["alto"][celdas]
            celdas, ultimo = celdas[mejor], ultimo[mejor]
            capas["alto"][celdas] = z[ultimo]
            rgb = np.stack([np.asarray(las.red)[ultimo], np.asarray(las.green)[ultimo],
                            np.asarray(las.blue)[ultimo]], axis=1)
            color[celdas] = (rgb >> 8 if rgb.max(initial=0) > 255 else rgb).astype(np.uint8)
            del las, z, clase, idx, util, orden, ultimo
    suelo = rejilla(capas["suelo"])
    edificio, puente, veg = (rejilla(capas[k]) for k in ("edificio", "puente", "veg"))
    fachada = fachada.clip(0, 255).astype(np.uint8)
    huecos = np.isnan(suelo)
    if huecos.all():  # hoja de mar
        suelo[:] = 0
    elif huecos.any():  # bajo los edificios: el valor del vecino de suelo más cercano
        _, (fi, ci) = ndimage.distance_transform_edt(huecos, return_indices=True)
        suelo = suelo[fi, ci]

    HOJAS.mkdir(parents=True, exist_ok=True)
    tmp = Path(salida).with_name(Path(salida).stem + ".tmp.npz")  # atómico: las colas leen las hojas a la vez
    np.savez_compressed(tmp, suelo=suelo, edificio=edificio, puente=puente, veg=veg,
                        color=color.reshape(N, N, 3), fachada=fachada.reshape(N, N))
    os.replace(tmp, salida)
    ruta.unlink()


def main():
    args = sys.argv[1:]
    if args and args[0] == "zona":
        e0, e1, n0, n1 = map(int, args[1:5])
        hojas = [f"{e}{n % 1000:03d}" for n in range(n1 - 1, n0 - 1, -1) for e in range(e0, e1)]
    else:
        hojas = args
    for i, hoja in enumerate(hojas):
        t = time.time()
        try:
            procesar(hoja)
            print(f"[{i + 1}/{len(hojas)}] {hoja} en {time.time() - t:.0f} s", flush=True)
        except Exception as e:  # una hoja que falla no para las demás
            print(f"[{i + 1}/{len(hojas)}] {hoja} FALLO: {e}", flush=True)


if __name__ == "__main__":
    main()
