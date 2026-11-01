"""Monumentos de Barcelona con su forma real sacada del modelo de superficie del LiDAR (ICGC, 0,5 m).

Las torres de la Sagrada Família, la cúpula del MNAC, la columna de Colom o la Torre Glòries no son el
prisma de tejado plano que sale del Catastro: aquí se levantan en 2,5D desde la altura máxima de los
tejados del LiDAR (clases 6 y 77) en celdas de 1 m, con paredes verticales entre celdas de distinta altura.
Arriba, la ortofoto; en las paredes, la textura del material de cada monumento.

La planta es la unión de las partes del Catastro a menos de 'radio' del centro (o el círculo, si el
Catastro no tiene el monumento); esas partes se quitan del modelo normal de edificios.

registrar(monumentos) añade los monumentos a la lista de monumentos_v.
"""
import pickle

import numpy as np
import shapely
from PIL import Image
from shapely.geometry import Point, Polygon

import config_v

CELDA = 1.0
# nombre: centro UTM, radio de la planta (m), material de las paredes
LISTA = {
    "sagrada_familia": ((430987.4, 4583894.3), 75.0, "piedra_arenisca"),
    "torre_glories": ((432261.1, 4583856.7), 26.0, "vidrio_glories"),
    "mnac": ((429197.4, 4580020.0), 105.0, "piedra"),
    "castell_montjuic": ((430270.9, 4579445.5), 120.0, "piedra"),
    "monument_colom": ((431241.5, 4580805.3), 9.0, "piedra"),
    "catedral": ((431117.9, 4581705.8), 62.0, "piedra"),
    "arc_triomf": ((431498.3, 4582491.6), 16.0, "ladrillo"),
    "hotel_arts": ((432797.1, 4581984.2), 36.0, "acero_vidrio"),
    "torre_mapfre": ((432913.4, 4582078.6), 32.0, "vidrio"),
    "hotel_w": ((432283.2, 4579965.0), 45.0, "vidrio"),
    "hospital_sant_pau": ((431007.5, 4584767.9), 0.0, "ladrillo"),  # 0: solo si se pide (recinto grande)
}


def _capa(clave, nombre):
    import puentes_v
    ruta = config_v.DATOS / "lidar" / "hojas" / f"{clave}.npz"
    if not ruta.exists():
        return None
    return puentes_v.hoja_corregida(clave)[nombre]


def _valor(capas_cache, nombre, e, n):
    """Valor de una capa del LiDAR (corregido) en UTM; NaN donde no hay hoja."""
    e, n = np.asarray(e, float), np.asarray(n, float)
    out = np.full(e.shape, np.nan, np.float32)
    ke, kn = np.floor(e / 1000).astype(int), np.floor(n / 1000).astype(int)
    for a, b in set(zip(ke.ravel().tolist(), kn.ravel().tolist())):
        clave = f"{a}{b % 1000:03d}"
        if (clave, nombre) not in capas_cache:
            capas_cache[(clave, nombre)] = _capa(clave, nombre)
        h = capas_cache[(clave, nombre)]
        if h is None:
            continue
        m = (ke == a) & (kn == b)
        c = np.clip(((e[m] - a * 1000) / 0.5).astype(int), 0, 1999)
        f = np.clip((((b + 1) * 1000 - n[m]) / 0.5).astype(int), 0, 1999)
        out[m] = h[f, c]
    return out


def textura_material(material, semilla=1, lado=512):
    r = np.random.default_rng(semilla)
    base = {"piedra_arenisca": (184, 164, 132), "piedra": (176, 166, 150), "ladrillo": (150, 76, 56),
            "vidrio": (88, 104, 120), "vidrio_glories": (150, 60, 50), "acero_vidrio": (120, 128, 134)}[material]
    a = np.full((lado, lado, 3), base, np.float32) + r.normal(0, 7, (lado, lado))[..., None]
    gr = np.asarray(Image.fromarray(r.normal(0, 1, (32, 32)).astype(np.float32)).resize((lado, lado), Image.BICUBIC))
    a += 9 * gr[..., None]
    if material.startswith("piedra"):
        a[::32] -= 22  # hiladas de sillares de 0,25 m (la textura cubre 4 m)
        for f0 in range(0, lado, 32):
            desp = 0 if (f0 // 32) % 2 else 24
            a[f0:f0 + 32, desp::48] -= 16
        a -= 14 * np.clip(np.linspace(-0.5, 1, lado), 0, 1)[:, None, None] * (r.random(lado) > 0.6)[None, :, None]
    elif material == "ladrillo":
        for f0 in range(0, lado, 16):
            a[f0:f0 + 2] = (200, 190, 175)  # llagas de mortero
            desp = 0 if (f0 // 16) % 2 else 16
            a[f0:f0 + 16, desp::32] = (200, 190, 175)
    else:  # muro cortina: montantes cada 1,5 m y forjados cada 3,5 m
        cielo = np.linspace(1.15, 0.85, lado)[:, None, None]
        a *= cielo
        a[:, ::192] = (60, 62, 66)
        a[::448] = (60, 62, 66)
        if material == "vidrio_glories":  # las lamas de colores de la Torre Glòries
            tonos = np.array([(170, 50, 40), (200, 90, 50), (80, 90, 150), (60, 70, 120), (190, 160, 160)], float)
            filas = r.integers(0, len(tonos), (lado // 8, lado // 8))
            a = 0.5 * a + 0.5 * np.kron(tonos[filas], np.ones((8, 8, 1)))
        elif material == "acero_vidrio":  # celosía blanca del Hotel Arts por fuera
            for k in range(-lado, lado, 96):
                idx = np.arange(lado)
                for d in (0, 1, 2, 3):
                    j = np.clip(idx + k + d, 0, lado - 1)
                    a[idx, j] = (226, 228, 230)
                    a[idx, np.clip(lado - 1 - idx + k + d, 0, lado - 1)] = (226, 228, 230)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _planta(nombre, centro, radio):
    if radio <= 0:
        return None
    partes = []
    for muni in config_v.MUNICIPIOS:
        ruta = config_v.DATOS / "catastro" / f"{muni}.pkl"
        if not ruta.exists():
            continue
        with open(ruta, "rb") as fh:
            for p in pickle.load(fh)["partes"]:
                c = p["anillos"][0].mean(0)
                if np.hypot(c[0] - centro[0], c[1] - centro[1]) < radio:
                    pol = Polygon(p["anillos"][0])
                    if pol.is_valid and pol.area > 1:
                        partes.append(pol)
    if partes:
        return shapely.union_all(partes).buffer(0.6).buffer(-0.3)
    return Point(centro).buffer(radio, 24)


def construir_dsm(nombre, centro, radio, material, relieve_suelo):
    """-> (origen, texturas, geometrías, colisión) como los demás monumentos."""
    import prototipo
    planta = _planta(nombre, centro, radio)
    lo, hi = np.floor(np.array(planta.bounds[:2]) - 2), np.ceil(np.array(planta.bounds[2:]) + 2)
    xs = np.arange(lo[0], hi[0], CELDA) + CELDA / 2
    ys = np.arange(hi[1], lo[1], -CELDA) - CELDA / 2
    X, Y = np.meshgrid(xs, ys)
    cache = {}
    # máximo de las cuatro celdas de 0,5 m de cada celda de 1 m
    d = np.array([-0.25, 0.25])
    alto = np.nanmax(np.stack([_valor(cache, "edificio", X + a, Y + b) for a in d for b in d]), axis=0)
    suelo = _valor(cache, "suelo", X, Y)
    dentro = shapely.contains_xy(planta, X, Y)
    alto = np.where(dentro & np.isfinite(alto) & (alto > suelo + 1.5), alto, np.nan)
    if not np.isfinite(alto).any():
        return None
    base = float(np.nanmin(np.where(dentro, suelo, np.nan))) - 1.0
    origen = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2])
    tejado, pared = [], []  # quads: (4 esquinas, normal, uv)
    fy, fx = alto.shape
    ancho_t = hi[0] - lo[0]
    alto_t = hi[1] - lo[1]

    def esq(x, y, z):
        return (x - origen[0], y - origen[1], z)

    for j in range(fy):
        for i in range(fx):
            h = alto[j, i]
            if not np.isfinite(h):
                continue
            x0, x1 = xs[i] - CELDA / 2, xs[i] + CELDA / 2
            y1, y0 = ys[j] + CELDA / 2, ys[j] - CELDA / 2
            uv = [((x - lo[0]) / ancho_t, (hi[1] - y) / alto_t) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
            tejado.append(([esq(x0, y0, h), esq(x1, y0, h), esq(x1, y1, h), esq(x0, y1, h)], (0, 0, 1), uv))
            # paredes hacia los vecinos más bajos (o sin monumento)
            for di, dj, a, b, nrm in ((1, 0, (x1, y0), (x1, y1), (1, 0, 0)), (-1, 0, (x0, y1), (x0, y0), (-1, 0, 0)),
                                      (0, -1, (x1, y1), (x0, y1), (0, 1, 0)), (0, 1, (x0, y0), (x1, y0), (0, -1, 0))):
                ii, jj = i + di, j + dj
                vecino = alto[jj, ii] if 0 <= ii < fx and 0 <= jj < fy else np.nan
                pie = vecino if np.isfinite(vecino) else base
                if h - pie < 0.25:
                    continue
                u0 = (a[0] + a[1]) / 4.0
                pared.append(([esq(*a, pie), esq(*b, pie), esq(*b, h), esq(*a, h)], nrm,
                              [(u0, pie / 4), (u0 + CELDA / 4, pie / 4), (u0 + CELDA / 4, h / 4), (u0, h / 4)]))

    def malla(quads, sombra):
        n = len(quads)
        v = np.array([q[0] for q in quads], float).reshape(-1, 3)
        nn = np.repeat(np.array([q[1] for q in quads], float), 4, axis=0)
        uv = np.array([q[2] for q in quads], float).reshape(-1, 2)
        luz = np.clip(0.75 + 0.25 * (v[:, 2] - base) / max(np.nanmax(alto) - base, 1), 0, 1) if sombra else np.ones(len(v))
        g = (luz * 255).astype(int)
        color = np.c_[g, g, g, np.full(len(v), 255)]
        base_i = np.arange(n)[:, None] * 4
        i = np.concatenate([base_i + [0, 1, 2], base_i + [0, 2, 3]])
        return dict(v=v, n=nn, uv=uv, color=color, i=i)

    tex_t, tex_p = f"mo_{nombre}_t", f"mo_{nombre}_p"
    lado = int(max(ancho_t, alto_t))
    mosaico = prototipo.mosaico(int(lo[0]), int(lo[1]), lado, 1024)
    # la ortofoto cubre un cuadrado de 'lado': los uv del tejado van sobre ese cuadrado
    for q in tejado:
        q[2][:] = [((x + origen[0] - lo[0]) / lado, (lo[1] + lado - (y + origen[1])) / lado) for x, y, _ in q[0]]
    geos, texturas = [], {tex_t: mosaico, tex_p: textura_material(material)}
    enteras = []
    if tejado:
        enteras.append(dict(textura=tex_t, **malla(tejado, False)))
    if pared:
        enteras.append(dict(textura=tex_p, **malla(pared, True)))
    cv = np.concatenate([g["v"] for g in enteras])
    ct = np.concatenate([g["i"] + sum(len(x["v"]) for x in enteras[:k]) for k, g in enumerate(enteras)])
    geos = [dict(textura=g["textura"], **t) for g in enteras
            for t in prototipo.partir({k: g[k] for k in ("v", "n", "uv", "color", "i")})]
    return tuple(origen), texturas, geos, (cv, ct)


def registrar(monumentos):
    for nombre, (centro, radio, material) in LISTA.items():
        if radio <= 0:
            continue
        monumentos.append(dict(
            nombre=nombre, ancla=np.array(centro), radio_excluir=[(centro, radio)],
            construir=lambda rs, n=nombre, c=centro, r=radio, m=material: construir_dsm(n, c, r, m, rs)))
