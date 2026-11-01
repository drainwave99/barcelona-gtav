"""Monumentos hechos a medida: los que el Catastro no tiene como edificio o que piden más detalle.

Cada monumento tiene un ancla (UTM), una zona donde se quitan las partes del Catastro que se le
solapan, y su propio modelo bcn_m_<nombre> (.ydr + .ybn + .ytd) que prototipo.py coloca en la hoja
donde cae el ancla.

Tres Xemeneies (Central Tèrmica de Sant Adrià): perfil medido en el LiDAR del ICGC 2021-2023
(puntos de clase 1, que lidar.py no guarda): centros por ajuste de círculo al fuste, radios por
el percentil 95 de la distancia al eje menos el ruido. Tambor de 18,3 m de radio hasta 93,5 m y
fuste de 5,8 m a 2,9 m hasta 199,9 m, iguales en las tres.

Màgic Badalona: la bola naranja de la plaza (LiDAR clase 6, ajuste de esfera con 0,05 m de error
mediano): centro 435634,15 4588265,13 a z 27,21 y radio 16,09 m; asienta en la plaza (z 18,5).
Ocho nervios blancos de meridiano que no llegan a la cima (ortofoto ICGC).

Pont del Petroli: planta del pantalán (pasarela y plataforma final) de OSM (man_made=pier, ODbL),
tablero de madera a z 6,3 (LiDAR), barandilla de 1,1 m y pilotes de hormigón por parejas cada 12 m.
"""
import numpy as np
import shapely
from PIL import Image, ImageFilter
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

import config_v
import rage

SEGMENTOS = 64
DIST = 4000.0  # se ven desde toda la costa

# (r, z) de abajo arriba; z sobre el nivel del mar. El primer punto se baja al suelo.
PERFIL_XEMENEIA = [(18.3, 93.5), (5.8, 93.5), (5.0, 110.0), (3.9, 130.0), (3.5, 150.0), (3.1, 170.0),
                   (2.9, 199.9), (2.3, 199.9), (2.3, 196.0)]
XEMENEIES = [(436123.14, 4586467.08), (436083.30, 4586430.82), (436036.27, 4586388.33)]


def torno(perfil, cx, cy, segmentos, tramo_uv=8.0):
    """Superficie de revolución por tramos del perfil: normales suaves alrededor y vivas entre tramos.
    Devuelve v, n, uv, i con el eje en (cx, cy)."""
    a = np.linspace(0, 2 * np.pi, segmentos + 1)
    ca, sa = np.cos(a), np.sin(a)
    v, n, uv, tris = [], [], [], []
    for (r0, z0), (r1, z1) in zip(perfil, perfil[1:]):
        dr, dz = r1 - r0, z1 - z0
        largo = np.hypot(dr, dz)
        nr, nz = dz / largo, -dr / largo  # normal hacia fuera del tramo (en el plano radial)
        base = len(v)
        for r, z in ((r0, z0), (r1, z1)):
            for k in range(segmentos + 1):
                v.append((cx + r * ca[k], cy + r * sa[k], z))
                n.append((nr * ca[k], nr * sa[k], nz))
                # u por longitud de arco del radio mayor del tramo; v por altura (o radio en las tapas)
                u = a[k] * max(r0, r1) / tramo_uv
                uv.append((u, (z if abs(dz) > 1e-6 else r) / tramo_uv))
        for k in range(segmentos):
            p, q = base + k, base + k + 1
            s, t = p + segmentos + 1, q + segmentos + 1
            tris += [(p, q, t), (p, t, s)]
    v, n, uv, tris = np.array(v), np.array(n), np.array(uv), np.array(tris)
    # orientar los triángulos según la normal (el juego descarta las caras traseras)
    cruz = np.cross(v[tris[:, 1]] - v[tris[:, 0]], v[tris[:, 2]] - v[tris[:, 0]])
    al_reves = np.einsum("ij,ij->i", cruz, n[tris[:, 0]]) < 0
    tris[al_reves] = tris[al_reves][:, ::-1]
    return v, n, uv, tris


def textura_hormigon(semilla=7, lado=512):
    """Hormigón de encofrado deslizante: gris claro, juntas horizontales cada 1/8 del tramo y churretes."""
    r = np.random.default_rng(semilla)
    img = np.full((lado, lado), 186.0)
    img += r.normal(0, 6, (lado, lado))
    gruesa = np.array(Image.fromarray(r.normal(0, 1, (lado // 16, lado // 16)).astype(np.float32)).resize(
        (lado, lado), Image.BICUBIC))
    img += 9 * gruesa
    for f in range(0, lado, lado // 8):  # juntas de las tongadas
        img[f:f + 2] -= 22
    churretes = r.normal(0, 1, lado)
    churretes = np.convolve(churretes, np.ones(5) / 5, mode="same")
    img += 10 * churretes[None, :] * np.linspace(0.3, 1, lado)[:, None]
    gris = np.clip(img, 0, 255).astype(np.uint8)
    rgb = np.dstack([gris, gris, (gris * 0.97).astype(np.uint8)])
    return Image.fromarray(rgb).filter(ImageFilter.GaussianBlur(0.6))


def _tres_xemeneies(relieve_suelo):
    geo_v, geo_n, geo_uv, geo_i, cols = [], [], [], [], []
    col_v, col_i = [], []
    ox, oy = np.mean(XEMENEIES, axis=0)
    for e, n in XEMENEIES:
        suelo = relieve_suelo(e, n)
        perfil = [(PERFIL_XEMENEIA[0][0], suelo - 1.0)] + PERFIL_XEMENEIA
        v, nn, uv, t = torno(perfil, e - ox, n - oy, SEGMENTOS)
        z = v[:, 2]
        # hollín en lo alto del fuste y suciedad al pie del tambor
        luz = np.clip(1.0 - 0.45 * np.clip((z - 188.0) / 12.0, 0, 1) - 0.12 * np.clip((suelo + 6 - z) / 6, 0, 1), 0, 1)
        c = np.c_[np.repeat((luz * 255).astype(int)[:, None], 3, 1), np.full(len(v), 255)]
        base = sum(len(x) for x in geo_v)
        geo_v.append(v); geo_n.append(nn); geo_uv.append(uv); geo_i.append(t + base); cols.append(c)
        cv, _, _, ct = torno(perfil[:-2], e - ox, n - oy, 24)  # colisión sin el borde interior
        col_i.append(ct + sum(len(x) for x in col_v)); col_v.append(cv)
    geo = dict(v=np.concatenate(geo_v), n=np.concatenate(geo_n), uv=np.concatenate(geo_uv),
               color=np.concatenate(cols), i=np.concatenate(geo_i))
    return (ox, oy), {"mo_hormigon": textura_hormigon()}, [dict(textura="mo_hormigon", **geo)], \
        (np.concatenate(col_v), np.concatenate(col_i))


MAGIC = dict(c=(435634.15, 4588265.13), z=27.21, r=16.09)


def esfera(cx, cy, cz, r, z_base, anillos, segmentos):
    """Casquete esférico desde la cota z_base hasta la cima, con normales suaves.
    uv: u en vueltas (0-1 alrededor), v de 0 (base) a 1 (cima)."""
    t0 = np.arcsin(np.clip((z_base - cz) / r, -1, 1))
    lat = np.linspace(t0, np.pi / 2, anillos + 1)
    a = np.linspace(0, 2 * np.pi, segmentos + 1)
    L, A = np.meshgrid(lat, a, indexing="ij")
    nrm = np.dstack([np.cos(L) * np.cos(A), np.cos(L) * np.sin(A), np.sin(L)]).reshape(-1, 3)
    v = nrm * r + [cx, cy, cz]
    uv = np.dstack([A / (2 * np.pi), (L - t0) / (np.pi / 2 - t0)]).reshape(-1, 2)
    i = np.arange((anillos + 1) * (segmentos + 1)).reshape(anillos + 1, segmentos + 1)
    p, q, s_, t = i[:-1, :-1].ravel(), i[:-1, 1:].ravel(), i[1:, :-1].ravel(), i[1:, 1:].ravel()
    tris = np.concatenate([np.stack([p, q, t], 1), np.stack([p, t, s_], 1)])
    cruz = np.cross(v[tris[:, 1]] - v[tris[:, 0]], v[tris[:, 2]] - v[tris[:, 0]])
    al_reves = np.einsum("ij,ij->i", cruz, nrm[tris].mean(1)) < 0
    tris[al_reves] = tris[al_reves][:, ::-1]
    return v, nrm, uv, tris


def textura_bola(nervios=8, ancho=128, alto=512, semilla=3):
    """Un gajo de la bola (se repite 'nervios' veces): chapa naranja con el nervio blanco en el borde."""
    r = np.random.default_rng(semilla)
    img = np.zeros((alto, ancho, 3)) + (206, 96, 38)
    img += r.normal(0, 4, (alto, ancho, 1))
    img += np.linspace(14, -10, alto)[:, None, None]  # más claro arriba (sol y desgaste)
    nervio = max(2, ancho // 40)
    hasta = int(alto * 0.1)  # los nervios acaban a ~2 m de la cima (fila 0 = cima)
    img[hasta:, :nervio] = (236, 232, 222)
    img[hasta:, -nervio:] = (236, 232, 222)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).resize((ancho, alto)).filter(ImageFilter.GaussianBlur(0.5))


def _magic(relieve_suelo):
    cx, cy = MAGIC["c"]
    suelo = relieve_suelo(cx, cy + MAGIC["r"] + 4)  # la plaza, fuera de la bola
    v, n, uv, t = esfera(0.0, 0.0, MAGIC["z"], MAGIC["r"], suelo - 1.0, 40, 96)
    uv = uv * [8, 1]
    z = v[:, 2]
    luz = np.clip(0.8 + 0.2 * (z - suelo) / (MAGIC["z"] + MAGIC["r"] - suelo), 0, 1)  # el pie, en sombra
    gris = (luz * 255).astype(int)
    color = np.c_[gris, gris, gris, np.full(len(v), 255)]
    cv, _, _, ct = esfera(0.0, 0.0, MAGIC["z"], MAGIC["r"], suelo - 1.0, 12, 24)
    return (cx, cy), {"mo_bola": textura_bola()}, [dict(textura="mo_bola", v=v, n=n, uv=uv, color=color, i=t)], (cv, ct)


PETROLI = [(437057.75, 4588027.66), (437058.14, 4588027.44), (437255.62, 4587898.8), (437258.3, 4587902.74),
           (437266.93, 4587897.1), (437259.52, 4587886.45), (437251.29, 4587891.93), (437253.76, 4587896.13),
           (437056.83, 4588024.24), (437056.2, 4588024.66), (437057.0, 4588026.17)]
PETROLI_Z, PETROLI_CANTO, PETROLI_FONDO = 6.3, 0.9, -4.0


def textura_tablones(lado=512, semilla=11):
    """Tarima de madera tropical gastada: tablones de 14 cm con junta, 512 px = 2 m a lo largo de u."""
    r = np.random.default_rng(semilla)
    ancho = lado * 0.14 / 2.0
    x = np.arange(lado)
    tablon = (x // ancho).astype(int)
    tono = r.normal(0, 1, tablon.max() + 1)
    veta = r.normal(0, 1, (lado // 4, lado)).astype(np.float32)
    veta = np.asarray(Image.fromarray(veta).resize((lado, lado), Image.BICUBIC))
    img = np.array([138.0, 120.0, 98.0]) + 10 * tono[tablon][None, :, None] + 7 * veta[..., None]
    img[:, (x % ancho) < 2] *= 0.45  # junta entre tablones
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def textura_barandilla():
    """Barandilla de acero galvanizado: pasamanos, travesaño y barrotes cada 12 cm (con alfa)."""
    a = np.zeros((128, 256, 4), np.uint8)
    a[..., :3] = (150, 154, 156)
    a[:8, :, 3] = 255  # pasamanos
    a[60:64, :, 3] = 255
    a[-4:, :, 3] = 255
    for x in range(0, 256, 30):
        a[:, x:x + 3, 3] = 255
    return Image.fromarray(a, "RGBA")


class _Lista:
    """Geometría acumulada a mano: quads con normal fija."""

    def __init__(self):
        self.v, self.n, self.uv, self.i = [], [], [], []

    def cara(self, p, normal, quv):
        base = len(self.v)
        self.v += [tuple(q) for q in p]
        self.n += [tuple(normal)] * len(p)
        self.uv += [tuple(q) for q in quv]
        self.i += [(base, base + 1, base + 2), (base, base + 2, base + 3)]

    def geo(self, tex, **extra):
        v, n, i = np.array(self.v, float), np.array(self.n, float), np.array(self.i)
        cruz = np.cross(v[i[:, 1]] - v[i[:, 0]], v[i[:, 2]] - v[i[:, 0]])
        mal = np.einsum("ij,ij->i", cruz, n[i[:, 0]]) < 0  # cara vista hacia la normal
        i[mal] = i[mal][:, ::-1]
        return dict(textura=tex, v=v, n=n, uv=np.array(self.uv, float), i=i, color=np.full((len(v), 4), 255), **extra)


def _petroli(relieve_suelo):
    poli = orient(Polygon(PETROLI), 1.0)
    ox, oy = np.asarray(poli.exterior.coords).mean(0)
    a0, a1 = np.array([437057.0, 4588026.17]), np.array([437255.0, 4587896.5])
    eje = (a1 - a0) / np.linalg.norm(a1 - a0)
    nor = np.array([-eje[1], eje[0]])
    z, abajo = PETROLI_Z, PETROLI_Z - PETROLI_CANTO
    madera, hormigon, barandilla = _Lista(), _Lista(), _Lista()
    col_v, col_i = [], []
    # tablero: tarima arriba (tablones de través), hormigón debajo
    tris = []
    for t in shapely.get_parts(shapely.constrained_delaunay_triangles(poli)):
        q = np.asarray(t.exterior.coords)[:3]
        if (q[1, 0] - q[0, 0]) * (q[2, 1] - q[0, 1]) - (q[1, 1] - q[0, 1]) * (q[2, 0] - q[0, 0]) < 0:
            q = q[::-1]
        tris.append(q)
        base = len(madera.v)
        for x, y in q:
            d = np.array([x, y]) - a0
            madera.v.append((x - ox, y - oy, z))
            madera.n.append((0.0, 0.0, 1.0))
            madera.uv.append((d @ eje / 2.0, d @ nor / 2.0))
        madera.i.append((base, base + 1, base + 2))
        base = len(hormigon.v)
        for x, y in q[::-1]:
            hormigon.v.append((x - ox, y - oy, abajo))
            hormigon.n.append((0.0, 0.0, -1.0))
            hormigon.uv.append((x / 2.0, y / 2.0))
        hormigon.i.append((base, base + 1, base + 2))
        col_i.append((len(col_v), len(col_v) + 1, len(col_v) + 2))
        col_v += [(x - ox, y - oy, z) for x, y in q]
    anillo = np.asarray(poli.exterior.coords)
    for (ax, ay), (bx, by) in zip(anillo[:-1], anillo[1:]):
        largo = np.hypot(bx - ax, by - ay)
        if largo < 0.05:
            continue
        fuera = np.array([(by - ay) / largo, -(bx - ax) / largo])  # exterior antihorario: fuera a la derecha
        pa, pb = np.array([ax - ox, ay - oy]), np.array([bx - ox, by - oy])
        hormigon.cara([(*pa, abajo), (*pb, abajo), (*pb, z), (*pa, z)], (*fuera, 0.0),
                      [(0, 0), (largo / 2, 0), (largo / 2, 0.45), (0, 0.45)])
        col_i += [(len(col_v), len(col_v) + 1, len(col_v) + 2), (len(col_v), len(col_v) + 2, len(col_v) + 3)]
        col_v += [(*pa, abajo), (*pb, abajo), (*pb, z), (*pa, z)]
        if np.hypot(ax - a0[0], ay - a0[1]) < 4 and np.hypot(bx - a0[0], by - a0[1]) < 4:
            continue  # por donde se entra desde el paseo no hay barandilla
        qa, qb = pa - 0.08 * fuera, pb - 0.08 * fuera
        p4 = [(*qa, z), (*qb, z), (*qb, z + 1.1), (*qa, z + 1.1)]
        quv = [(0, 0), (largo / 0.96, 0), (largo / 0.96, 1), (0, 1)]
        barandilla.cara(p4, (*fuera, 0.0), quv)
        barandilla.cara(p4, (*(-fuera), 0.0), quv)
        col_i += [(len(col_v), len(col_v) + 1, len(col_v) + 2), (len(col_v), len(col_v) + 2, len(col_v) + 3)]
        col_v += p4
    # pilotes: parejas cada 12 m bajo la pasarela y una cuadrícula bajo la plataforma
    largo_eje = float(np.linalg.norm(a1 - a0))
    puntos = [a0 + eje * d + nor * o for d in np.arange(8.0, largo_eje - 4, 12.0) for o in (-1.2, 1.2)]
    c = np.asarray(Polygon(PETROLI[3:7]).centroid.coords[0])
    puntos += [c + eje * i + nor * j for i in (-3.5, 3.5) for j in (-4.0, 0.0, 4.0)]
    m = 0.35
    for p in puntos:
        if relieve_suelo(*p) > 1.0:  # sobre la playa no hacen falta
            continue
        centro = p - [ox, oy]
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            ex, ey = np.array([dx, dy]) * m, np.array([-dy, dx]) * m
            pa, pb = centro + ex - ey, centro + ex + ey
            hormigon.cara([(*pa, PETROLI_FONDO), (*pb, PETROLI_FONDO), (*pb, abajo), (*pa, abajo)], (dx, dy, 0.0),
                          [(0, PETROLI_FONDO / 2), (0.35, PETROLI_FONDO / 2), (0.35, abajo / 2), (0, abajo / 2)])
    geos = [madera.geo("mo_tablones"), hormigon.geo("mo_hormigon"), barandilla.geo("mo_barandilla", recorte=True)]
    texturas = {"mo_tablones": textura_tablones(), "mo_hormigon": textura_hormigon(),
                "mo_barandilla": textura_barandilla()}
    return (ox, oy), texturas, geos, (np.array(col_v, float), np.array(col_i))


MONUMENTOS = [
    dict(nombre="pont_petroli", ancla=np.asarray(PETROLI).mean(0), radio_excluir=[], construir=_petroli),
    dict(nombre="magic_bola", ancla=np.array(MAGIC["c"]), radio_excluir=[(MAGIC["c"], MAGIC["r"] - 0.5)],
         construir=_magic),
    dict(nombre="tres_xemeneies", ancla=np.mean(XEMENEIES, axis=0), radio_excluir=[(c, 20.0) for c in XEMENEIES],
         construir=_tres_xemeneies),
]


import monumentos_bcn  # noqa: E402  (Sagrada Família, MNAC, Colom... desde el LiDAR)

monumentos_bcn.registrar(MONUMENTOS)


def excluido(punto):
    """True si el punto (UTM) cae dentro de la zona de algún monumento (se quita la parte del Catastro)."""
    for m in MONUMENTOS:
        for c, r in m["radio_excluir"]:
            if np.hypot(punto[0] - c[0], punto[1] - c[1]) < r:
                return True
    return False


def escribir(xml, e0h, n1h, relieve_suelo, arquetipos, entidades):
    """Escribe los monumentos cuya ancla cae en la hoja [e0h, e0h+1000] x [n1h-1000, n1h]."""
    for m in MONUMENTOS:
        e, n = m["ancla"]
        if not (e0h <= e < e0h + 1000 and n1h - 1000 <= n < n1h):
            continue
        modelo = f"bcn_m_{m['nombre']}"
        hecho = m["construir"](relieve_suelo)
        if hecho is None:  # sin LiDAR todavía
            continue
        (ox, oy), texturas, geos, (cv, ct) = hecho
        gx, gy = config_v.utm_a_juego(ox, oy)
        rage.escribir_ytd(xml / f"{modelo}.ytd.xml", {k: (img, img.mode == "RGBA") for k, img in texturas.items()})
        rage.escribir_ydr(xml / f"{modelo}.ydr.xml", modelo, geos, DIST)
        rage.escribir_ybn(xml / f"{modelo}.ybn.xml", cv + np.array([gx, gy, 0.0]), ct, [rage.MAT_CONCRETE],
                          np.zeros(len(ct), int))
        arquetipos.append((modelo, modelo, DIST))
        entidades.append((modelo, (gx, gy, 0.0), DIST))
        print(f"Monumento {m['nombre']}: {sum(len(g['i']) for g in geos)} triángulos")
