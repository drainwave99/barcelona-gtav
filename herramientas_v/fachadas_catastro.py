"""Descarga la foto de fachada que el Catastro publica para cada edificio (fuente: Dirección General
del Catastro). Una petición cada PAUSA segundos para no cargar el servicio; se puede cortar y
volver a lanzar, salta las ya bajadas.

Entrada: datos_v/catastro/A.ES.SDGC.BU.<muni>/A.ES.SDGC.BU.<muni>.building.gml
Salida:  datos_v/fachadas/<muni>/<referencia catastral>.jpg  (sin_foto.txt: las que no tienen)
Uso: python fachadas_catastro.py 08015 [08245 08193 08900]
"""
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
URL = ("http://ovc.catastro.meh.es/OVCServWeb/OVCWcfLibres/OVCFotoFachada.svc/"
       "RecuperarFotoFachadaGet?ReferenciaCatastral={}")
PAUSA = 0.5
HILOS = 4  # peticiones a la vez


def referencias(muni):
    gml = RAIZ / "datos_v" / "catastro" / f"A.ES.SDGC.BU.{muni}" / f"A.ES.SDGC.BU.{muni}.building.gml"
    return re.findall(r"<base:localId>([^<]+)</base:localId>", gml.read_text(encoding="utf-8"))


def bajar(rc, carpeta, sin_foto, cerrojo):
    """Devuelve True si bajó la foto."""
    for intento in range(3):
        try:
            with urllib.request.urlopen(URL.format(rc), timeout=60) as r:
                datos = r.read()
                tipo = r.headers.get("Content-Type", "")
            break
        except Exception as e:
            if intento == 2:
                print(f"{rc}: {e}", flush=True)
                return False
            time.sleep(10)
    time.sleep(PAUSA)
    if tipo.startswith("image/") and len(datos) > 2000:
        (carpeta / f"{rc}.jpg").write_bytes(datos)
        return True
    with cerrojo, open(sin_foto, "a") as fh:
        fh.write(rc + "\n")
    return False


def main():
    for muni in sys.argv[1:]:
        carpeta = RAIZ / "datos_v" / "fachadas" / muni
        carpeta.mkdir(parents=True, exist_ok=True)
        sin_foto = carpeta / "sin_foto.txt"
        vistas = set(sin_foto.read_text().split()) if sin_foto.exists() else set()
        pendientes = [rc for rc in referencias(muni) if rc not in vistas and not (carpeta / f"{rc}.jpg").exists()]
        cerrojo = threading.Lock()
        hechas = 0
        with ThreadPoolExecutor(HILOS) as pool:
            for i, ok in enumerate(pool.map(lambda rc: bajar(rc, carpeta, sin_foto, cerrojo), pendientes)):
                hechas += ok
                if i % 500 == 0:
                    print(f"{muni}: {i}/{len(pendientes)} pendientes ({hechas} fotos)", flush=True)
        print(f"{muni}: terminado, {hechas} fotos nuevas", flush=True)


if __name__ == "__main__":
    main()
