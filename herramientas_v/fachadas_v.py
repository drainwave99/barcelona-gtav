"""Fachadas en 3D de cada edificio a partir de sus datos (Catastro, LiDAR, foto, OSM).

Cada pared exterior se clasifica (calle, patio o medianera) y se construye pieza a pieza:
  - plantas reales: planta baja más alta y el resto repartido en la altura del LiDAR
  - ventanas y balconeras hundidas en la pared (con sus jambas), tantas por planta como el ancho permite
  - balcones (losa + barandilla) según la época del edificio, iguales en todo el edificio
  - planta baja a la calle: portal, tiendas (escaparate o persiana metálica) o garaje según el uso
  - medianeras sin ventanas, de ladrillo o revoque gris
  - peto de 1 m en las azoteas
El color de cada edificio va en su textura de pared (paleta de colores reales de las fotos), que se repite
cada 2 m; el color de vértice solo oscurece jambas y bajos de losa, y las piezas salen del atlas de texturas_fachada.py.
"""
import hashlib
import json

import numpy as np

import config_v
import texturas_fachada

CASILLAS = json.loads((config_v.DATOS / "texturas" / "fachadas_casillas.json").read_text())
_ruta_paleta = config_v.DATOS / "texturas" / "paleta.json"
PALETA = json.loads(_ruta_paleta.read_text()) if _ruta_paleta.exists() else []
METROS_TEXTURA = 2.0
HUNDIDO = 0.16


def semilla(texto):
    return int(hashlib.md5(texto.encode()).hexdigest()[:8], 16)


class Malla:
    """Geometría acumulada por textura: {textura: dict(v, n, uv, color, i)} (listas)."""

    def __init__(self):
        self.g = {}

    def quad(self, tex, p, normal, uv, color):
        """p: 4 esquinas (abajo-izq, abajo-der, arriba-der, arriba-izq) vistas desde fuera."""
        g = self.g.setdefault(tex, dict(v=[], n=[], uv=[], color=[], i=[]))
        base = len(g["v"])
        g["v"] += [tuple(q) for q in p]
        g["n"] += [tuple(normal)] * 4
        g["uv"] += [tuple(q) for q in uv]
        g["color"] += [tuple(color)] * 4
        g["i"] += [(base, base + 1, base + 2), (base, base + 2, base + 3)]

    def arrays(self):
        out = {}
        for tex, g in self.g.items():
            out[tex] = dict(v=np.array(g["v"], float), n=np.array(g["n"], float), uv=np.array(g["uv"], float),
                            color=np.array(g["color"], int), i=np.array(g["i"], int))
        return out


def estilo(ref, anyo, uso, foto):
    """Rasgos de un edificio: iguales en todas sus paredes y partes, deterministas por referencia."""
    r = np.random.default_rng(semilla(ref))
    if foto:
        material, rgb = foto["material"], np.array(foto["rgb"], float)
    else:
        if anyo and anyo < 1985 and r.random() < 0.08:  # en las fotos sale un 2,4 %
            material = r.choice(["ladrillo_rojo", "ladrillo_amarillo", "ladrillo_marron"], p=[0.55, 0.3, 0.15])
        else:
            material = r.choice(["revoque_liso", "revoque_rugoso"], p=[0.7, 0.3])
        rgb = None
    color = np.array([255, 255, 255]) * r.uniform(0.9, 1.0)  # el color va en la textura
    if material.startswith("revoque") and PALETA:
        rgbs = np.array([c for c, _ in PALETA], float)
        if rgb is None:  # sin foto: un color de la zona, con la frecuencia con que sale en las fotos
            pesos = np.array([w for _, w in PALETA], float)
            j = int(r.choice(len(PALETA), p=pesos / pesos.sum()))
        else:
            j = int(np.argmin(((rgbs - texturas_fachada.albedo(rgb)[0]) ** 2).sum(1)))
        material = f"{material}_c{j:02d}"
    if anyo and anyo < 1955:
        ventanas = r.choice(["madera", "verde"], p=[0.5, 0.5])
    elif anyo and anyo < 1990:
        ventanas = r.choice(["pvc", "aluminio", "verde"], p=[0.6, 0.3, 0.1])
    else:
        ventanas = r.choice(["aluminio", "cristal", "pvc"], p=[0.45, 0.35, 0.2])
    balcones = bool(anyo and 1900 < anyo < 2010 and r.random() < (0.75 if anyo < 1980 else 0.5))
    barandilla = "barandilla_hierro" if (not anyo or anyo < 1975 or r.random() < 0.5) else "barandilla_obra"
    comercial = uso in ("3_industrial", "4_1_office", "4_2_retail", "4_3_publicServices") or r.random() < 0.45
    return dict(material=f"pa_{material}", color=color.astype(int), ventanas=ventanas, balcones=balcones,
                barandilla=barandilla, comercial=comercial, r=r, modulo=r.uniform(2.9, 3.6))


def _pieza(tipo_ventana, balconera):
    if balconera:
        return {"pvc": "balconera_pvc", "verde": "balconera_verde", "madera": "balconera_madera"}.get(
            tipo_ventana, "balconera_cristal")
    return {"pvc": "ventana_pvc", "verde": "ventana_verde", "madera": "ventana_pvc", "cristal": "ventana_aluminio"}.get(
        tipo_ventana, "ventana_aluminio")


def _uv_pieza(nombre):
    u0, v0, u1, v1 = CASILLAS[nombre]
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


class Pared:
    """Una pared recta de a a b (2D, coordenadas locales), con la normal exterior hacia la derecha."""

    def __init__(self, malla, a, b, est):
        self.m, self.est = malla, est
        self.a, self.b = np.asarray(a, float), np.asarray(b, float)
        d = self.b - self.a
        self.largo = float(np.hypot(*d))
        self.d = d / self.largo
        self.normal = np.array([self.d[1], -self.d[0], 0.0])
        self.s0 = 0.0  # posición de a en metros a lo largo del perímetro (continuidad de la textura)

    def punto(self, s, z, fuera=0.0):
        p = self.a + self.d * s
        return np.array([p[0] + self.normal[0] * fuera, p[1] + self.normal[1] * fuera, z])

    def liso(self, s0, s1, z0, z1, fuera=0.0, tono=1.0, material=None):
        if s1 - s0 < 0.01 or z1 - z0 < 0.01:
            return
        p = [self.punto(s0, z0, fuera), self.punto(s1, z0, fuera), self.punto(s1, z1, fuera), self.punto(s0, z1, fuera)]
        u0, u1 = (self.s0 + s0) / METROS_TEXTURA, (self.s0 + s1) / METROS_TEXTURA
        uv = [(u0, z0 / METROS_TEXTURA), (u1, z0 / METROS_TEXTURA), (u1, z1 / METROS_TEXTURA), (u0, z1 / METROS_TEXTURA)]
        self.m.quad(material or self.est["material"], p, self.normal, uv, (*(self.est["color"] * tono).astype(int), 255))

    def hueco(self, s0, s1, z0, z1, pieza):
        """Hueco hundido HUNDIDO m con la pieza al fondo y las cuatro jambas."""
        h = -HUNDIDO
        fondo = [self.punto(s0, z0, h), self.punto(s1, z0, h), self.punto(s1, z1, h), self.punto(s0, z1, h)]
        self.m.quad("fa_piezas", fondo, self.normal, _uv_pieza(pieza), (255, 255, 255, 255))
        t = 0.72  # las jambas en sombra
        mat, col = self.est["material"], (*(self.est["color"] * t).astype(int), 255)
        dn = np.r_[self.d, 0.0]
        uvj = [(0, 0), (HUNDIDO / 2, 0), (HUNDIDO / 2, (z1 - z0) / 2), (0, (z1 - z0) / 2)]
        self.m.quad(mat, [self.punto(s0, z0), self.punto(s0, z0, h), self.punto(s0, z1, h), self.punto(s0, z1)], dn, uvj, col)
        self.m.quad(mat, [self.punto(s1, z0, h), self.punto(s1, z0), self.punto(s1, z1), self.punto(s1, z1, h)], -dn, uvj, col)
        uvh = [(0, 0), ((s1 - s0) / 2, 0), ((s1 - s0) / 2, HUNDIDO / 2), (0, HUNDIDO / 2)]
        self.m.quad(mat, [self.punto(s0, z1, h), self.punto(s1, z1, h), self.punto(s1, z1), self.punto(s0, z1)],
                    np.array([0, 0, -1.0]), uvh, col)
        self.m.quad(mat, [self.punto(s0, z0), self.punto(s1, z0), self.punto(s1, z0, h), self.punto(s0, z0, h)],
                    np.array([0, 0, 1.0]), uvh, (*(self.est["color"] * 0.9).astype(int), 255))

    def banda(self, z0, z1, huecos):
        """Pared entre z0 y z1 con huecos [(s0, s1, h0, h1, pieza)] (h relativas a z0)."""
        s = 0.0
        for s0, s1, h0, h1, pieza in sorted(huecos):
            self.liso(s, s0, z0, z1)
            self.liso(s0, s1, z0, z0 + h0)
            self.liso(s0, s1, z0 + h1, z1)
            self.hueco(s0, s1, z0 + h0, z0 + h1, pieza)
            s = s1
        self.liso(s, self.largo, z0, z1)

    def balcon(self, s0, s1, z, barandilla):
        """Losa de 0,85 m de vuelo y barandilla de 1 m (las dos caras)."""
        vuelo, grueso = 0.85, 0.14
        mat, col = self.est["material"], (*(self.est["color"] * 0.95).astype(int), 255)
        a0, a1 = s0 - 0.3, s1 + 0.3
        arriba = [self.punto(a0, z, 0), self.punto(a1, z, 0), self.punto(a1, z, vuelo), self.punto(a0, z, vuelo)]
        self.m.quad(mat, [arriba[3], arriba[2], arriba[1], arriba[0]], np.array([0, 0, 1.0]),
                    [(0, 0), ((a1 - a0) / 2, 0), ((a1 - a0) / 2, 0.4), (0, 0.4)], col)
        self.m.quad(mat, [self.punto(a0, z - grueso, vuelo), self.punto(a1, z - grueso, vuelo),
                          self.punto(a1, z, vuelo), self.punto(a0, z, vuelo)], self.normal,
                    [(0, 0), ((a1 - a0) / 2, 0), ((a1 - a0) / 2, 0.07), (0, 0.07)], col)
        self.m.quad(mat, [self.punto(a0, z - grueso, 0), self.punto(a1, z - grueso, 0),
                          self.punto(a1, z - grueso, vuelo), self.punto(a0, z - grueso, vuelo)],
                    np.array([0, 0, -1.0]), [(0, 0), ((a1 - a0) / 2, 0), ((a1 - a0) / 2, 0.4), (0, 0.4)],
                    (*(self.est["color"] * 0.6).astype(int), 255))
        uv = _uv_pieza(barandilla)
        frente = [self.punto(a0, z, vuelo), self.punto(a1, z, vuelo), self.punto(a1, z + 1.0, vuelo),
                  self.punto(a0, z + 1.0, vuelo)]
        blanco = (255, 255, 255, 255)
        self.m.quad("fa_piezas_alfa", frente, self.normal, uv, blanco)
        self.m.quad("fa_piezas_alfa", [frente[1], frente[0], frente[3], frente[2]], -self.normal,
                    [uv[1], uv[0], uv[3], uv[2]], blanco)
        dn = np.r_[self.d, 0.0]
        for s, sentido in ((a0, -1), (a1, 1)):  # laterales de la barandilla
            lado = [self.punto(s, z, 0), self.punto(s, z, vuelo), self.punto(s, z + 1.0, vuelo), self.punto(s, z + 1.0, 0)]
            if sentido > 0:
                lado = [lado[1], lado[0], lado[3], lado[2]]
            self.m.quad("fa_piezas_alfa", lado, dn * sentido, uv, blanco)


def construir_pared(malla, a, b, s0, suelo, techo, tipo, est, plantas, cubierto=0.0, ultima_ref=""):
    """tipo: 'calle', 'patio' o 'medianera'. cubierto: altura sobre el suelo tapada por el vecino."""
    p = Pared(malla, a, b, est)
    p.s0 = s0
    alto = techo - suelo
    if p.largo < 0.3 or alto < 0.5:
        return
    if tipo == "medianera" or p.largo < 2.2:
        z0 = suelo + cubierto
        mat = est["material"] if tipo != "medianera" else (
            "pa_ladrillo_rojo" if est["material"].startswith("pa_ladrillo") or est["r"].random() < 0.25 else "pa_revoque_gris")
        if z0 < techo:
            tono = 1.0 if tipo != "medianera" else 0.8
            p.liso(0, p.largo, z0, techo, tono=tono, material=mat)
        return
    r = est["r"]
    plantas = max(1, plantas or round(alto / 3.0))
    pb = min(alto, 3.8 if (tipo == "calle" and plantas > 1) else (3.0 if plantas > 1 else alto))
    resto = (alto - pb) / max(plantas - 1, 1) if plantas > 1 else 0
    # Planta baja
    if tipo == "calle":
        n = max(1, int(p.largo // 3.4))
        ancho = p.largo / n
        portal = n // 2 if est.get("portal", True) else -1
        huecos = []
        for k in range(n):
            if k == portal:
                pieza = "bajo_portal"
            elif est["comercial"]:
                pieza = "bajo_escaparate" if r.random() < 0.55 else "bajo_persiana"
            else:
                pieza = r.choice(["bajo_garaje", "ventana_reja", "bajo_persiana"], p=[0.3, 0.5, 0.2])
            w = min(ancho - 0.5, 1.6 if pieza == "bajo_portal" else (1.3 if pieza == "ventana_reja" else 3.0))
            h = 2.6 if pieza != "ventana_reja" else 1.4
            h0 = 0.02 if pieza != "ventana_reja" else 0.9
            c = (k + 0.5) * ancho
            if w > 0.6 and h0 + h < pb - 0.3:
                huecos.append((c - w / 2, c + w / 2, h0, h0 + h, pieza))
        p.banda(suelo, suelo + pb, huecos)
    else:
        p.liso(0, p.largo, suelo, suelo + pb)
    # Plantas de pisos
    if plantas > 1 and resto > 2.2:
        n = max(1, round(p.largo / (est["modulo"] if tipo == "calle" else 2.8)))
        ancho = p.largo / n
        balcon = tipo == "calle" and est["balcones"]
        for f in range(1, plantas):
            z0 = suelo + pb + (f - 1) * resto
            huecos = []
            for k in range(n):
                c = (k + 0.5) * ancho
                if balcon:
                    w, h0, h1 = min(1.3, ancho - 0.5), 0.03, 2.25
                else:
                    w, h0, h1 = min(1.45, ancho - 0.5), 0.85, 2.3
                if w > 0.5 and h1 < resto - 0.2:
                    huecos.append((c - w / 2, c + w / 2, h0, h1, _pieza(est["ventanas"], balcon)))
            p.banda(z0, z0 + resto, huecos)
            if balcon and huecos:
                for s0_, s1_, *_ in huecos:
                    p.balcon(s0_, s1_, z0, est["barandilla"])
        cima = suelo + pb + (plantas - 1) * resto
        if techo - cima > 0.01:
            p.liso(0, p.largo, cima, techo)
    elif plantas > 1:
        p.liso(0, p.largo, suelo + pb, techo)


def peto(malla, a, b, s0, techo, est, alto=0.95):
    """Peto de la azotea: cara exterior, cara interior y remate."""
    p = Pared(malla, a, b, est)
    p.s0 = s0
    if p.largo < 0.05:
        return
    p.liso(0, p.largo, techo, techo + alto)
    q = Pared(malla, b, a, est)  # cara interior, mirando hacia la azotea
    q.liso(0, q.largo, techo, techo + alto, fuera=0.18, tono=0.9)
    arriba = [p.punto(0, techo + alto), p.punto(p.largo, techo + alto), p.punto(p.largo, techo + alto, -0.18),
              p.punto(0, techo + alto, -0.18)]
    malla.quad(est["material"], arriba, np.array([0, 0, 1.0]),
               [(0, 0), (p.largo / 2, 0), (p.largo / 2, 0.09), (0, 0.09)], (*(est["color"] * 0.92).astype(int), 255))
