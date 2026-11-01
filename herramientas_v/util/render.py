"""Vista en perspectiva de los modelos generados (ydr.xml), sin el juego: pintor por triángulos con el color
de su textura en el centro del triángulo y sombreado por la normal.

Uso: render.py salida.png E N Z rumbo cabeceo [radio] [tipos]
  E N Z      cámara en UTM (m), rumbo en grados (0 = norte, 90 = este), cabeceo (+ arriba)
  tipos      letras de los modelos: t terreno, c calles, p puentes, u túneles, e fachadas, r tejados (def. tcpuer)
"""
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

RAIZ = Path(r"C:\Users\danny\Desktop\GTA SAN ANDREAS MOD CON ISMA\mod_v\prototipo")
W, H, FOV = 1280, 720, 70.0

salida = sys.argv[1]
if sys.argv[4].startswith("+"):  # altura sobre el terreno (LiDAR corregido)
    sys.path.insert(0, r"C:\Users\danny\Desktop\GTA SAN ANDREAS MOD CON ISMA\herramientas_v")
    import puentes_v
    _s = float(puentes_v.Relieve().valor("suelo", float(sys.argv[2]), float(sys.argv[3])))
    cam = np.array([float(sys.argv[2]), float(sys.argv[3]), _s + float(sys.argv[4][1:])])
    print("suelo", round(_s, 1))
else:
    cam = np.array([float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])])
rumbo, cabeceo = np.radians(float(sys.argv[5])), np.radians(float(sys.argv[6]))
radio = float(sys.argv[7]) if len(sys.argv) > 7 else 400.0
tipos = sys.argv[8] if len(sys.argv) > 8 else "tcpuerma"

adelante = np.array([np.sin(rumbo) * np.cos(cabeceo), np.cos(rumbo) * np.cos(cabeceo), np.sin(cabeceo)])
derecha = np.array([np.cos(rumbo), -np.sin(rumbo), 0.0])
arriba = np.cross(derecha, adelante)
f = (W / 2) / np.tan(np.radians(FOV / 2))
luz = np.array([0.4, -0.5, 0.75]); luz /= np.linalg.norm(luz)

_tex = {}


def textura(carpetas, nombre):
    if nombre not in _tex:
        img = None
        for c in carpetas:
            for r in c.glob(f"*/{nombre}.dds"):
                try:
                    img = np.asarray(Image.open(r).convert("RGB").resize((64, 64)), np.float32)
                except Exception:
                    pass
                break
            if img is not None:
                break
        _tex[nombre] = img if img is not None else np.full((64, 64, 3), 200, np.float32)
    return _tex[nombre]


def modelos():
    patron = re.compile(r"bcn_([" + tipos + r"])_(\d{5})_(\d{6})\.ydr\.xml$")
    import pickle
    sys.path.insert(0, r"C:\Users\danny\Desktop\GTA SAN ANDREAS MOD CON ISMA\herramientas_v")
    import config_v
    for hoja in RAIZ.iterdir():
        xml = hoja / "xml"
        if not xml.is_dir():
            continue
        if "m" in tipos and (hoja / "colocacion.pkl").exists():  # monumentos: posición de su entidad
            col = pickle.load(open(hoja / "colocacion.pkl", "rb"))
            for ent in col["entidades"]:
                if ent[0].startswith("bcn_m_") and (xml / f"{ent[0]}.ydr.xml").exists():
                    e, n = config_v.juego_a_utm(ent[1][0], ent[1][1])
                    if np.hypot(e - cam[0], n - cam[1]) < radio + 300:
                        yield xml / f"{ent[0]}.ydr.xml", np.array([e, n, ent[1][2]]), xml
        for ruta in xml.glob("bcn_*_*_*.ydr.xml"):
            m = patron.search(ruta.name)
            if not m:
                continue
            ce, cn = int(m.group(2)) * 10 + 125, int(m.group(3)) * 10 + 125
            if np.hypot(ce - cam[0], cn - cam[1]) > radio + 180:
                continue
            yield ruta, np.array([ce, cn, 0.0]), xml


tris_p, colores, prof = [], [], []
for ruta, centro, xml in modelos():
    s = ruta.read_text(encoding="utf-8")
    texs = re.findall(r'name="DiffuseSampler" type="Texture"><Name>([^<]+)</Name>', s)
    for g in re.finditer(r"<ShaderIndex value=\"(\d+)\" />(.*?)</Item>\s*(?=<Item>|</Geometries>)", s, re.S):
        tex = texs[int(g.group(1))] if int(g.group(1)) < len(texs) else "?"
        cuerpo = g.group(2)
        vb = re.search(r"<VertexBuffer>.*?<Data>(.*?)</Data>", cuerpo, re.S)
        ib = re.search(r"<IndexBuffer>.*?<Data>(.*?)</Data>", cuerpo, re.S)
        if not vb or not ib:
            continue
        d = np.array(vb.group(1).split(), np.float32).reshape(-1, 12)
        idx = np.array(ib.group(1).split(), np.int64).reshape(-1, 3)
        v = d[:, :3] + centro
        uv = d[:, 10:12]
        p = v[idx]  # (n, 3, 3)
        c = p.mean(1)
        rel = c - cam
        z = rel @ adelante
        ok = (z > 1.0) & (np.linalg.norm(rel[:, :2], axis=1) < radio)
        if not ok.any():
            continue
        p, idx2, z = p[ok], idx[ok], z[ok]
        n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
        img = textura([xml], tex)
        u = uv[idx2].mean(1)
        tx = (np.mod(u[:, 0], 1) * 63).astype(int)
        ty = (np.mod(u[:, 1], 1) * 63).astype(int)
        col = img[ty, tx] * (0.55 + 0.45 * np.clip(np.abs(n @ luz), 0, 1))[:, None]
        col = col * d[:, 6:9][idx2].mean(1) / 255  # color de vértice (tinte)
        if tex.startswith("vi_linea"):
            col = np.full_like(col, 235)
        relp = p - cam
        zc = relp @ adelante
        if (zc <= 0.3).any():
            bien = (zc > 0.3).all(1)
            relp, col, z, zc = relp[bien], col[bien], z[bien], zc[bien]
        sx = W / 2 + f * (relp @ derecha) / zc
        sy = H / 2 - f * (relp @ arriba) / zc
        tris_p.append(np.stack([sx, sy], -1))
        colores.append(col)
        prof.append(z)

img = Image.new("RGB", (W, H), (160, 190, 225))
if tris_p:
    P = np.concatenate(tris_p); C = np.concatenate(colores); Z = np.concatenate(prof)
    dib = ImageDraw.Draw(img)
    for k in np.argsort(-Z):
        q = P[k]
        if np.abs(q).max() > 1e5:
            continue
        dib.polygon([tuple(x) for x in q], fill=tuple(int(a) for a in C[k]))
    print(len(Z), "triángulos")
img.save(salida)
