"""Descarga la ortofoto vigente del ICGC (WMS, CC BY 4.0) en teselas de 125 m a 1000 px (12,5 cm/px),
directamente en ETRS89 UTM 31N.

Salida: datos_v/orto/<E>_<N>.jpg con E, N la esquina suroeste en metros.
Uso: python orto.py E0 E1 N0 N1   (en km; p. ej. 429 440 4584 4595)
"""
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import config_v

URL = ("https://geoserveis.icgc.cat/servei/catalunya/orto-territorial/wms?SERVICE=WMS&VERSION=1.3.0"
       "&REQUEST=GetMap&LAYERS=ortofoto_color_vigent&STYLES=&CRS=EPSG:25831&BBOX={e},{n},{e2},{n2}"
       "&WIDTH=1000&HEIGHT=1000&FORMAT=image/jpeg")
TESELA = 125  # 8 por km: las teselas encajan con las hojas LiDAR
HILOS = 2
CARPETA = config_v.DATOS / "orto"


def ruta(e, n):
    return CARPETA / f"{e}_{n}.jpg"


def bajar(en):
    e, n = en
    destino = ruta(e, n)
    if destino.exists():
        return True
    for intento in range(4):
        try:
            with urllib.request.urlopen(URL.format(e=e, n=n, e2=e + TESELA, n2=n + TESELA), timeout=60) as r:
                datos = r.read()
                if not r.headers.get("Content-Type", "").startswith("image/"):
                    raise RuntimeError(datos[:200])
            destino.write_bytes(datos)
            return True
        except Exception as ex:
            if intento == 3:
                print(f"{e}_{n}: {ex}", flush=True)
                return False
            time.sleep(15)


def main():
    e0, e1, n0, n1 = (int(a) * 1000 for a in sys.argv[1:5])
    CARPETA.mkdir(parents=True, exist_ok=True)
    teselas = [(e, n) for n in range(n0, n1, TESELA) for e in range(e0, e1, TESELA)]
    hechas = 0
    with ThreadPoolExecutor(HILOS) as pool:
        for i, ok in enumerate(pool.map(bajar, teselas)):
            hechas += ok
            if i % 200 == 0:
                print(f"{i}/{len(teselas)} ({hechas} bien)", flush=True)
    print(f"Ortofoto: {hechas}/{len(teselas)} teselas en {CARPETA}", flush=True)


if __name__ == "__main__":
    main()
