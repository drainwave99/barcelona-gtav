"""Vista cenital de una casilla generada: ortofoto de fondo y encima las geometrías de calles (bcn_c) y los muros
del terreno (bcn_t: bcn_muro, bcn_hormigon) pintadas por textura, para revisar bordes y taludes sin abrir el juego.
Uso: python util/vista_casilla.py <hoja> <casilla, p. ej. 43500_458550> [salida.png]"""
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config_v  # noqa: E402
import prototipo  # noqa: E402

COLOR = {"vi_asfalto": (0, 220, 0, 110), "vi_acera": (60, 140, 255, 150), "vi_linea": (255, 255, 255, 220),
         "vi_aparcamiento": (120, 60, 160, 150), "vi_bordillo": (255, 255, 0, 255), "bcn_muro": (255, 120, 0, 170),
         "bcn_hormigon": (255, 0, 0, 170), "vi_hormigon": (255, 0, 255, 120)}
PX = 1000


def geometrias(ruta):
    s = ruta.read_text(encoding="utf-8")
    shaders = re.findall(r'name="DiffuseSampler" type="Texture"><Name>([^<]+)</Name>', s)
    for g in re.finditer(r"<ShaderIndex value=\"(\d+)\" />.*?<VertexBuffer>.*?<Data>(.*?)</Data>.*?<IndexBuffer>\s*<Data>(.*?)</Data>",
                         s, re.S):
        tex = shaders[int(g.group(1))]
        v = np.array([list(map(float, l.split()[:2])) for l in g.group(2).strip().splitlines()])
        i = np.array(g.group(3).split(), int).reshape(-1, 3)
        yield tex, v, i


def main():
    hoja, cas = sys.argv[1], sys.argv[2]
    salida = Path(sys.argv[3]) if len(sys.argv) > 3 else config_v.DATOS / "revision" / f"vista_{cas}.png"
    e0, n0 = (int(x) * 10 for x in cas.split("_"))
    fondo = prototipo.mosaico(e0, n0, prototipo.CASILLA, PX).convert("RGBA")
    capa = Image.new("RGBA", fondo.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    xml = config_v.MOD / "prototipo" / hoja / "xml"
    a_px = lambda p: ((p[0] + prototipo.CASILLA / 2) / prototipo.CASILLA * PX,
                      (prototipo.CASILLA / 2 - p[1]) / prototipo.CASILLA * PX)
    for pre in ("bcn_t", "bcn_c", "bcn_p", "bcn_r"):
        f = xml / f"{pre}_{cas}.ydr.xml"
        if not f.exists():
            continue
        for tex, v, i in geometrias(f):
            if tex not in COLOR:
                continue
            for t in i:
                d.polygon([a_px(v[k]) for k in t], fill=COLOR[tex])
    Image.alpha_composite(fondo, capa).convert("RGB").save(salida)
    print(salida)


if __name__ == "__main__":
    main()
