"""Baja algunas fotos de calle de Mapillary (licencia CC BY-SA) como referencia de fachadas por barrio.

Token en datos/mapillary_token.txt (no se sube a ningún sitio). Salida: docs/referencias/<barrio>_N.jpg
Solo son referencia para dibujar las texturas a mano; no se meten en el juego.
"""
import requests

import config

BARRIOS = {  # (lon, lat) aproximados
    "centre": (2.2470, 41.4505), "dalt_la_vila": (2.2488, 41.4525), "progres": (2.2390, 41.4470),
    "llefia": (2.2195, 41.4515), "sant_roc": (2.2090, 41.4425), "gorg": (2.2290, 41.4390),
    "la_salut": (2.2270, 41.4520), "canyet": (2.2348, 41.4757), "casagemes": (2.2440, 41.4470),
}
POR_BARRIO = 3


def main():
    token = (config.DATOS / "mapillary_token.txt").read_text().strip()
    salida = config.RAIZ / "docs" / "referencias"
    salida.mkdir(parents=True, exist_ok=True)
    for nombre, (lon, lat) in BARRIOS.items():
        d = 0.0015
        r = requests.get("https://graph.mapillary.com/images", timeout=60, params={
            "access_token": token, "fields": "id,thumb_1024_url,is_pano,captured_at",
            "bbox": f"{lon - d},{lat - d},{lon + d},{lat + d}", "limit": 40})
        if r.status_code != 200:
            print(nombre, "error", r.status_code, r.text[:200])
            continue
        fotos = [f for f in r.json().get("data", []) if not f.get("is_pano") and f.get("thumb_1024_url")]
        fotos.sort(key=lambda f: -f.get("captured_at", 0))  # las más recientes
        for i, f in enumerate(fotos[:POR_BARRIO]):
            (salida / f"{nombre}_{i}.jpg").write_bytes(requests.get(f["thumb_1024_url"], timeout=60).content)
        print(f"{nombre}: {len(fotos)} fotos, guardadas {min(len(fotos), POR_BARRIO)}")


if __name__ == "__main__":
    main()
