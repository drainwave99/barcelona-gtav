"""Bocas de metro en 3D: el hueco en la acera, la escalera que baja de verdad y un vestíbulo abajo.

Cada boca (railway=subway_entrance de OSM, la coloca calles_v alineada con la calle más cercana) es, en sus ejes
u (a lo largo, la escalera baja hacia +u) y v (a lo ancho):
  hueco      u -L/2..L/2, v -W/2..W/2 en la acera: sin terreno ni acera, con barandilla (calles_v) en tres lados
  escalera   PELDANOS de TABICA x HUELLA desde la acera (u = -L/2) hasta el vestíbulo; pasado el hueco, bajo techo
  vestíbulo  VEST_L x VEST_W y VEST_H de alto, con azulejo, suelo de terrazo, luces y la entrada a los andenes
El terreno de la casilla es una malla de PASO m: se quitan los triángulos que tocan el hueco y lo que sobra entre
ellos y el hueco se tapa con una losa de acera (marco), con su colisión. La colisión de la escalera es una rampa
lisa (el jugador y los peatones suben mejor que por escalones); lo que se ve son los escalones.
bcn_metro.asi abre el panel de líneas cuando el jugador está abajo, en el vestíbulo.

hueco(v, tris, bocas, centro) -> (máscara de triángulos que se quedan, marco: Polygon UTM o None)
construir(bocas, marco, centro) -> (malla {textura: arrays}, colisión (v, tris)) en coordenadas locales
"""
import numpy as np
import shapely
from shapely.geometry import Polygon

import fachadas_v

L, W = 5.0, 2.2                 # hueco en la acera (m)
TABICA, HUELLA = 0.17, 0.30     # peldaño
PELDANOS = 25                   # 4,25 m de bajada
HONDO = TABICA * PELDANOS
LOSA = 0.35                     # techo sobre la escalera, bajo la acera
VEST_L, VEST_W, VEST_H = 8.0, 6.0, 3.0
BLANCO = (255, 255, 255, 255)


def rectangulo(b, margen=0.0):
    """Planta del hueco (UTM)."""
    o, e, la = np.array([b["x"], b["y"]]), b["eje"], b["lat"]
    a, w = L / 2 + margen, W / 2 + margen
    return Polygon([o - e * a - la * w, o + e * a - la * w, o + e * a + la * w, o - e * a + la * w])


def hueco(v, tris, bocas, centro):
    """v: vértices del terreno en coordenadas locales (centro de la casilla), tris: índices. Fuera los triángulos
    que tocan algún hueco; marco = lo que esos triángulos cubrían menos los huecos (se tapa con acera)."""
    keep = np.ones(len(tris), bool)
    if not bocas:
        return keep, None
    c = np.asarray(centro, float)
    t2 = v[tris][:, :, :2] + c
    huecos = [rectangulo(b) for b in bocas]
    quitados = []
    for h in huecos:
        x0, y0, x1, y1 = h.bounds
        cerca = np.flatnonzero((t2[:, :, 0].max(1) >= x0) & (t2[:, :, 0].min(1) <= x1) &
                               (t2[:, :, 1].max(1) >= y0) & (t2[:, :, 1].min(1) <= y1))
        if not len(cerca):
            continue
        polis = shapely.polygons(t2[cerca])
        toca = shapely.intersects(polis, h)
        keep[cerca[toca]] = False
        quitados += list(polis[toca])
    if not quitados:
        return keep, None
    marco = shapely.union_all(quitados).difference(shapely.union_all(huecos)).buffer(0)
    return keep, (None if marco.is_empty else marco)


class _Pieza:
    """Una boca: pasa de sus ejes (u, v, z) a coordenadas locales de la casilla y junta malla y colisión."""

    def __init__(self, b, c3, malla, col):
        self.o = np.array([b["x"], b["y"], 0.0]) - c3
        self.e = np.r_[b["eje"], 0.0]
        self.la = np.r_[b["lat"], 0.0]
        self.z0 = b["z"]
        self.m, self.col = malla, col

    def p(self, u, v, z):
        return self.o + self.e * u + self.la * v + np.array([0, 0, self.z0 + z])

    def cara(self, tex, esq, uv, hacia, choca=True):
        """esq: 4 puntos (u, v, z) en orden; la cara mira hacia 'hacia' (vector en ejes u, v, z)."""
        P = [self.p(*q) for q in esq]
        h = self.e * hacia[0] + self.la * hacia[1] + np.array([0, 0, hacia[2]])
        nrm = np.cross(P[1] - P[0], P[2] - P[0])
        if np.dot(nrm, h) < 0:
            P, uv = [P[1], P[0], P[3], P[2]], [uv[1], uv[0], uv[3], uv[2]]
            nrm = -nrm
        nrm = nrm / (np.linalg.norm(nrm) + 1e-12)
        self.m.quad(tex, P, nrm, uv, BLANCO)
        if choca:
            base = len(self.col[0])
            self.col[0].extend(P)
            self.col[1].extend([(base, base + 1, base + 2), (base, base + 2, base + 3)])


def _boca(pz):
    u0 = -L / 2                        # primer peldaño, a ras de acera
    u1 = u0 + PELDANOS * HUELLA        # pie de la escalera = principio del vestíbulo
    w = W / 2
    techo_esc = -LOSA                  # techo sobre la escalera pasado el hueco
    # peldaños (solo se ven; la colisión es la rampa de abajo)
    for k in range(PELDANOS):
        ua, ub = u0 + k * HUELLA, u0 + (k + 1) * HUELLA
        z = -(k + 1) * TABICA
        pz.cara("vi_metro_peldano", [(ua, -w, z), (ub, -w, z), (ub, w, z), (ua, w, z)],
                [(0, 0), (0, 1), (W / 1.2, 1), (W / 1.2, 0)], (0, 0, 1), choca=False)
        pz.cara("vi_metro_peldano", [(ua, -w, z + TABICA), (ua, w, z + TABICA), (ua, w, z), (ua, -w, z)],
                [(0, 0.5), (W / 1.2, 0.5), (W / 1.2, 1), (0, 1)], (-1, 0, 0), choca=False)
    pz.cara("vi_metro_peldano", [(u0, -w, 0), (u1, -w, -HONDO), (u1, w, -HONDO), (u0, w, 0)],
            [(0, 0), (0, 0), (0, 0), (0, 0)], (0, 0, 1))  # rampa: colisión (se ve justo bajo los escalones)
    # paredes de la escalera: del borde del hueco (acera) o del techo hasta los peldaños
    for lado in (-1, 1):
        for k in range(PELDANOS):
            ua, ub = u0 + k * HUELLA, u0 + (k + 1) * HUELLA
            arriba = 0.0 if ub <= L / 2 else techo_esc
            zb = -(k + 1) * TABICA
            pz.cara("vi_metro_azulejo", [(ua, lado * w, arriba), (ub, lado * w, arriba), (ub, lado * w, zb), (ua, lado * w, zb)],
                    [(ua / 1.5, 0), (ub / 1.5, 0), (ub / 1.5, (arriba - zb) / VEST_H), (ua / 1.5, (arriba - zb) / VEST_H)],
                    (0, -lado, 0))
    # techo de la escalera bajo la acera (del final del hueco al vestíbulo) y su frente sobre el hueco
    pz.cara("vi_tunel_techo", [(L / 2, -w, techo_esc), (u1, -w, techo_esc), (u1, w, techo_esc), (L / 2, w, techo_esc)],
            [(0, 0), (2, 0), (2, 1), (0, 1)], (0, 0, -1))
    pz.cara("vi_hormigon", [(L / 2, -w, 0), (L / 2, w, 0), (L / 2, w, techo_esc), (L / 2, -w, techo_esc)],
            [(0, 0), (1, 0), (1, 0.2), (0, 0.2)], (-1, 0, 0))
    # vestíbulo
    fondo = -HONDO
    va, vb = -VEST_W / 2, VEST_W / 2
    ua, ub = u1, u1 + VEST_L
    alto = fondo + VEST_H
    pz.cara("vi_metro_suelo", [(ua, va, fondo), (ub, va, fondo), (ub, vb, fondo), (ua, vb, fondo)],
            [(0, 0), (VEST_L / 2, 0), (VEST_L / 2, VEST_W / 2), (0, VEST_W / 2)], (0, 0, 1))
    pz.cara("vi_tunel_techo", [(ua, va, alto), (ub, va, alto), (ub, vb, alto), (ua, vb, alto)],
            [(0, 0), (2, 0), (2, 2), (0, 2)], (0, 0, -1))
    for k in range(3):  # tres tiras de luz en el techo
        vv = va + (k + 1) * VEST_W / 4
        pz.cara("vi_luz", [(ua + 0.8, vv - 0.15, alto - 0.02), (ub - 0.8, vv - 0.15, alto - 0.02),
                           (ub - 0.8, vv + 0.15, alto - 0.02), (ua + 0.8, vv + 0.15, alto - 0.02)],
                [(0, 0), (1, 0), (1, 1), (0, 1)], (0, 0, -1), choca=False)
    uvp = lambda a, b, h: [(a / 1.5, 0), (b / 1.5, 0), (b / 1.5, h / VEST_H), (a / 1.5, h / VEST_H)]
    for lado, vv in ((-1, va), (1, vb)):  # paredes largas
        pz.cara("vi_metro_azulejo", [(ua, vv, alto), (ub, vv, alto), (ub, vv, fondo), (ua, vv, fondo)],
                uvp(0, VEST_L, VEST_H), (0, -lado, 0))
    # pared del lado de la escalera, con su paso (de -w a w) y el dintel encima
    for a, b in ((va, -w), (w, vb)):
        pz.cara("vi_metro_azulejo", [(ua, a, alto), (ua, b, alto), (ua, b, fondo), (ua, a, fondo)],
                uvp(a, b, VEST_H), (1, 0, 0))
    pz.cara("vi_metro_azulejo", [(ua, -w, alto), (ua, w, alto), (ua, w, techo_esc), (ua, -w, techo_esc)],
            uvp(-w, w, alto - techo_esc), (1, 0, 0))
    # pared del fondo: la entrada a los andenes (vano oscuro) con el rombo de la M encima
    pz.cara("vi_metro_azulejo", [(ub, va, alto), (ub, vb, alto), (ub, vb, fondo), (ub, va, fondo)],
            uvp(va, vb, VEST_H), (-1, 0, 0))
    pz.cara("vi_tunel_techo", [(ub - 0.02, -1.6, fondo + 2.3), (ub - 0.02, 1.6, fondo + 2.3),
                               (ub - 0.02, 1.6, fondo + 0.01), (ub - 0.02, -1.6, fondo + 0.01)],
            [(0, 0), (1, 0), (1, 1), (0, 1)], (-1, 0, 0), choca=False)
    pz.cara("vi_metro_m_alfa", [(ub - 0.03, -0.35, fondo + 2.95), (ub - 0.03, 0.35, fondo + 2.95),
                                (ub - 0.03, 0.35, fondo + 2.4), (ub - 0.03, -0.35, fondo + 2.4)],
            [(0, 0), (1, 0), (1, 1), (0, 1)], (-1, 0, 0), choca=False)


def construir(bocas, marco, centro):
    """Malla (texturas de bcn_obra) y colisión (v, tris) en coordenadas locales de la casilla."""
    m = fachadas_v.Malla()
    col = ([], [])
    c3 = np.r_[np.asarray(centro, float), 0.0]
    for b in bocas:
        _boca(_Pieza(b, c3, m, col))
    if marco is not None and bocas:  # losa de acera entre el hueco y el terreno que se quedó
        import prototipo
        z = max(b["z"] for b in bocas)
        for parte in shapely.get_parts(marco):
            if parte.geom_type != "Polygon" or parte.area < 0.01:
                continue
            for t in prototipo.triangular(parte):  # antihorario visto desde arriba
                q = [np.r_[p, z] - c3 for p in t]
                g = m.g.setdefault("vi_acera", dict(v=[], n=[], uv=[], color=[], i=[]))
                base = len(g["v"])
                g["v"] += [tuple(x) for x in q]
                g["n"] += [(0.0, 0.0, 1.0)] * 3
                g["uv"] += [(x[0] / 2, x[1] / 2) for x in q]
                g["color"] += [BLANCO] * 3
                g["i"].append((base, base + 1, base + 2))
                cb = len(col[0])
                col[0].extend(q)
                col[1].append((cb, cb + 1, cb + 2))
    if not col[0]:
        return None, None
    return m.arrays(), (np.asarray(col[0], float), np.asarray(col[1], int))
