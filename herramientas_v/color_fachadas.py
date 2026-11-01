"""Color y material de la pared de cada edificio a partir de su foto de fachada del Catastro.

Se mira la parte central de la foto (el edificio está centrado), por encima de la franja de los coches,
y se descartan cielo, vegetación y sombras. El color dominante es el de la pared; si es rojizo o
anaranjado, saturado y con mucho contraste de juntas, se toma como ladrillo caravista.

Salida: datos_v/texturas/colores.json  {referencia: {"rgb": [r, g, b], "material": "ladrillo_rojo"|...}}
"""
import json

import numpy as np
from PIL import Image

import config_v


def analizar(ruta):
    im = Image.open(ruta).convert("RGB")
    w, h = im.size
    a = np.asarray(im.crop((int(w * 0.3), int(h * 0.12), int(w * 0.7), int(h * 0.58))).resize((120, 120)),
                   np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    v = a.max(-1)
    s = (v - a.min(-1)) / (v + 1e-6)
    cielo = (b > r + 25) & (b > 120)
    verde = (g > r + 12) & (g > b + 8)
    util = ~cielo & ~verde & (v > 45) & (v < 248)
    if util.mean() < 0.25:
        return None
    # la pared al sol: se descarta la mitad más oscura (sombras, portales, cristales)
    util &= v >= np.percentile(v[util], 50)
    p = a[util]
    # color dominante: la celda más poblada de un histograma de 8 niveles por canal
    q = (p // 32).astype(int)
    claves, inversa, cuentas = np.unique(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2], return_inverse=True,
                                         return_counts=True)
    dom = p[inversa == np.argmax(cuentas)]
    rgb = np.median(dom, axis=0)
    # contraste de alta frecuencia (juntas del ladrillo) dentro de la zona útil
    gris = a.mean(-1)
    detalle = np.abs(np.diff(gris, axis=0))[util[1:]].mean()
    sat = float(np.median(s[util]))
    rr, gg, bb = rgb
    if rr > gg * 1.12 and rr > bb * 1.3 and sat > 0.28 and detalle > 9:
        material = "ladrillo_marron" if rr < 130 else "ladrillo_rojo"
    elif rr > bb * 1.25 and gg > bb * 1.12 and sat > 0.25 and detalle > 9:
        material = "ladrillo_amarillo"
    elif detalle > 14:
        material = "revoque_rugoso"
    else:
        material = "revoque_liso"
    return dict(rgb=[int(c) for c in rgb], material=material)


def main():
    salida = {}
    fotos = sorted((config_v.DATOS / "fachadas").glob("*/*.jpg"))
    for f in fotos:
        try:
            res = analizar(f)
        except OSError:
            continue
        if res:
            salida[f.stem] = res
    (config_v.DATOS / "texturas").mkdir(parents=True, exist_ok=True)
    (config_v.DATOS / "texturas" / "colores.json").write_text(json.dumps(salida))
    mats = {}
    for v in salida.values():
        mats[v["material"]] = mats.get(v["material"], 0) + 1
    print(f"Colores: {len(salida)} de {len(fotos)} fotos; materiales {mats}")


if __name__ == "__main__":
    main()
