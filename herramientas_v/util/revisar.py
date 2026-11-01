"""Revisión automática de las hojas generadas (mod_v/prototipo/<hoja>/xml), sin abrir el juego.

Busca en cada hoja:
  textura   geometrías que piden una textura que no está en su .ytd (se verían en blanco/rosa)
  estirado  triángulos con la textura muy estirada o encogida respecto a los demás de su textura (manchas,
            rayas) o con UV/posiciones no numéricas
  pinchos   vértices muy fuera de su casilla (triángulos gigantes que cruzan el mapa)
  hueco     edificios (fachadas + tejados) con aristas abiertas: paredes o tejados con agujeros por los que se
            ve el interior (no cuenta el borde de abajo de las paredes, que va contra el suelo)
  atraviesa paredes y tejados visibles sin colisión a menos de 1 m: se podrían atravesar andando
  colision  terreno visible sin colisión debajo (se caería al vacío)

Uso: python util/revisar.py [hojas...]      (sin hojas: todas)
Escribe el resumen en pantalla y el detalle (con coordenadas del juego, para ir a mirarlas) en
datos_v/revision/<hoja>.txt
"""
import pickle
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config_v  # noqa: E402

RAIZ = config_v.MOD / "prototipo"
SALIDA = config_v.DATOS / "revision"
GEOM = re.compile(r"<ShaderIndex value=\"(\d+)\" />(.*?)</Item>\s*(?=<Item>|</Geometries>)", re.S)
TEX = re.compile(r'name="DiffuseSampler" type="Texture"><Name>([^<]+)</Name>')


def leer_ydr(ruta):
    """[(textura, v (n,3) local, uv (n,2), tris (m,3))]"""
    s = ruta.read_text(encoding="utf-8")
    texs = TEX.findall(s)
    out = []
    for g in GEOM.finditer(s):
        k = int(g.group(1))
        vb = re.search(r"<VertexBuffer>.*?<Data>(.*?)</Data>", g.group(2), re.S)
        ib = re.search(r"<IndexBuffer>.*?<Data>(.*?)</Data>", g.group(2), re.S)
        if not vb or not ib:
            continue
        d = np.array(vb.group(1).split(), np.float64).reshape(-1, 12)
        t = np.array(ib.group(1).split(), np.int64).reshape(-1, 3)
        out.append((texs[k] if k < len(texs) else "?", d[:, :3], d[:, 10:12], t))
    return out


def leer_ybn(ruta):
    """(v (n,3) en coordenadas del juego, tris (m,3))"""
    s = ruta.read_text(encoding="utf-8")
    vs, ts, base = [], [], 0
    for b in re.finditer(r'<Item type="GeometryBVH">(.*?)</Polygons>', s, re.S):
        c = re.search(r'<GeometryCenter x="([-\d.]+)" y="([-\d.]+)" z="([-\d.]+)"', b.group(1))
        cen = np.array([float(c.group(i)) for i in (1, 2, 3)])
        vt = re.search(r"<Vertices>(.*?)</Vertices>", b.group(1), re.S).group(1)
        v = np.array(vt.replace(",", " ").split(), np.float64).reshape(-1, 3) + cen
        t = np.array(re.findall(r'v1="(\d+)" v2="(\d+)" v3="(\d+)"', b.group(1)), np.int64).reshape(-1, 3)
        vs.append(v)
        ts.append(t + base)
        base += len(v)
    if not vs:
        return np.zeros((0, 3)), np.zeros((0, 3), np.int64)
    return np.concatenate(vs), np.concatenate(ts)


def muestras(v, t, paso=0.7):
    """Puntos repartidos por los triángulos (uno cada ~paso m) y el triángulo de cada uno."""
    p = v[t]
    a = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    n = np.clip(np.ceil(a / (paso * paso)), 1, 400).astype(int)
    idx = np.repeat(np.arange(len(t)), n)
    r1, r2 = np.random.rand(len(idx)), np.random.rand(len(idx))
    s1 = np.sqrt(r1)
    q = p[idx]
    pts = (1 - s1)[:, None] * q[:, 0] + (s1 * (1 - r2))[:, None] * q[:, 1] + (s1 * r2)[:, None] * q[:, 2]
    return pts, idx


def aristas_abiertas(v, t):
    """Aristas de un solo triángulo tras soldar vértices a 2 cm, sin las de abajo de las paredes."""
    clave = np.round(v / 0.02).astype(np.int64)
    _, uni = np.unique(clave, axis=0, return_inverse=True)
    tt = uni.ravel()[t]
    e = np.concatenate([tt[:, [0, 1]], tt[:, [1, 2]], tt[:, [2, 0]]])
    otro = np.concatenate([tt[:, 2], tt[:, 0], tt[:, 1]])
    tri = np.tile(np.arange(len(t)), 3)
    es = np.sort(e, axis=1)
    _, inv, cuenta = np.unique(es, axis=0, return_inverse=True, return_counts=True)
    sola = cuenta[inv.ravel()] == 1
    # posición de cada vértice soldado
    pos = np.zeros((uni.max() + 1, 3))
    pos[uni.ravel()] = v
    a, b, c = pos[e[sola, 0]], pos[e[sola, 1]], pos[otro[sola]]
    p = v[t[tri[sola]]]
    nz = np.abs(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]))
    nz = nz[:, 2] / (np.linalg.norm(nz, axis=1) + 1e-9)
    pared = nz < 0.3
    abajo = (c[:, 2] > np.maximum(a[:, 2], b[:, 2]) + 0.05)  # el tercer vértice está por encima: borde inferior
    ok = ~(pared & abajo)
    a, b = a[ok], b[ok]
    if not len(a):
        return a, b
    # no es hueco si el borde pasa pegado a otra cara del edificio: uniones en T (pared partida en trozos junto
    # a otra entera) y cajas apoyadas en la pared (ventanas, balcones) sin cara de atrás. Se mira cada 0,25 m
    # del borde contra puntos repartidos por las caras (cada 0,2 m) que no sean del triángulo del propio borde.
    propio = tri[sola][ok]
    largo = np.linalg.norm(b - a, axis=1)
    n = np.clip(np.ceil(largo / 0.25).astype(int), 1, 2000)
    eid = np.repeat(np.arange(len(a)), n)
    f = (np.arange(len(eid)) - np.repeat(np.cumsum(n) - n, n) + 0.5) / n[eid]
    pts = a[eid] + (b - a)[eid] * f[:, None]
    caras, de = muestras(v, t, 0.2)
    arbol = cKDTree(caras)
    vecinos = arbol.query_ball_point(pts, 0.15)
    tapado = np.array([any(de[k] != propio[e] for k in vk) for vk, e in zip(vecinos, eid)], bool)
    libre = np.bincount(eid, weights=~tapado, minlength=len(a)) / n
    ok = libre > 0.5
    return a[ok], b[ok]


def revisar(hoja):
    xml = RAIZ / hoja / "xml"
    col = pickle.load(open(RAIZ / hoja / "colocacion.pkl", "rb"))
    ytd_de = {m: t for m, t, _ in col["arquetipos"]}
    pos_de = {e[0]: np.asarray(e[1][:3], np.float64) for e in col["entidades"]}
    texturas = {}
    for y in xml.glob("*.ytd.xml"):
        texturas[y.name[:-8]] = set(re.findall(r"<Name>([^<]+)</Name>", y.read_text(encoding="utf-8",
                                                                                     errors="ignore")))
    fallos = defaultdict(list)   # tipo -> [(x, y, z, texto)]
    for ruta in sorted(xml.glob("bcn_*.ydr.xml")):
        nombre = ruta.name[:-8]
        if nombre not in pos_de:
            continue
        geoms = leer_ydr(ruta)
        base = pos_de[nombre]
        disp = texturas.get(ytd_de.get(nombre), set())
        for tex, v, uv, t in geoms:
            w = v + base
            if tex not in disp and ytd_de.get(nombre) in texturas:
                c = w.mean(0)
                fallos["textura"].append((*c, f"{nombre}: falta la textura {tex} en {ytd_de.get(nombre)}"))
            if not (np.isfinite(v).all() and np.isfinite(uv).all()):
                fallos["estirado"].append((*w[np.isfinite(w).all(1)].mean(0), f"{nombre}: valores no numéricos"))
                continue
            lejos = np.abs(v[:, :2]).max(1) > 400
            if lejos.any():
                fallos["pinchos"].append((*w[lejos][0], f"{nombre}: {lejos.sum()} vértices a >400 m del centro"))
            p, q = v[t], uv[t]
            a3 = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
            d1, d2 = q[:, 1] - q[:, 0], q[:, 2] - q[:, 0]
            a2 = 0.5 * np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0])
            grandes = a3 > 0.5
            if grandes.sum() >= 20:
                esc = np.sqrt(a2[grandes] / a3[grandes])
                med = np.median(esc[esc > 0]) if (esc > 0).any() else 0
                if med > 0:
                    raro = (esc < med / 12) | (esc > med * 12)
                    if raro.sum():
                        cs = (p[grandes][raro].mean(1) + base)
                        for c in cs[:: max(1, len(cs) // 5)][:5]:
                            fallos["estirado"].append((*c, f"{nombre} ({tex}): {raro.sum()} triángulos con la "
                                                            "textura estirada"))
    # edificios: fachadas (e) + tejados (r) de cada casilla; colisión de fachadas en bcn_e_*.ybn
    for ruta in sorted(xml.glob("bcn_e_*.ydr.xml")):
        casilla = ruta.name[len("bcn_e_"):-8]
        partes = []
        for tipo in ("e", "r"):
            r = xml / f"bcn_{tipo}_{casilla}.ydr.xml"
            n = f"bcn_{tipo}_{casilla}"
            if r.exists() and n in pos_de:
                partes += [(v + pos_de[n], t) for _, v, _, t in leer_ydr(r)]
        if not partes:
            continue
        vv, tt, base = [], [], 0
        for v, t in partes:
            vv.append(v)
            tt.append(t + base)
            base += len(v)
        v, t = np.concatenate(vv), np.concatenate(tt)
        a, b = aristas_abiertas(v, t)
        if len(a):
            largo = np.linalg.norm(b - a, axis=1)
            if largo.sum() > 2:
                # agrupa por celdas de 10 m: cada grupo es un sitio a mirar
                celdas = Counter()
                for m, l in zip(np.floor((a + b)[:, :2] / 20).astype(int), largo):
                    celdas[tuple(m)] += l
                for (cx, cy), l in celdas.most_common(8):
                    if l > 1.5:
                        sel = (np.floor((a + b)[:, :2] / 20).astype(int) == (cx, cy)).all(1)
                        c = ((a + b)[sel] / 2).mean(0)
                        fallos["hueco"].append((*c, f"bcn_e_{casilla}: {l:.0f} m de borde abierto"))
        cb = xml / f"bcn_e_{casilla}.ybn.xml"
        cv, ct = leer_ybn(cb) if cb.exists() else (np.zeros((0, 3)), np.zeros((0, 3), np.int64))
        pts, _ = muestras(v, t)
        if len(ct):
            cp, _ = muestras(cv, ct, 0.5)
            d, _ = cKDTree(cp).query(pts, distance_upper_bound=1.0)
            sin = ~np.isfinite(d)
        else:
            sin = np.ones(len(pts), bool)
        if sin.mean() > 0.02:
            celdas = Counter(map(tuple, np.floor(pts[sin][:, :2] / 20).astype(int)))
            for (cx, cy), n in celdas.most_common(6):
                if n >= 30:
                    sel = (np.floor(pts[:, :2] / 20).astype(int) == (cx, cy)).all(1) & sin
                    c = pts[sel].mean(0)
                    fallos["atraviesa"].append((*c, f"bcn_e_{casilla}: pared/tejado sin colisión "
                                                    f"({sin.mean() * 100:.0f} % de la casilla)"))
    # terreno: bcn_t_*.ydr con su bcn_t_*.ybn
    for ruta in sorted(xml.glob("bcn_t_*.ydr.xml")):
        n = ruta.name[:-8]
        if n not in pos_de:
            continue
        cb = xml / f"{n}.ybn.xml"
        partes = [(v + pos_de[n], t) for _, v, _, t in leer_ydr(ruta)]
        if not partes:
            continue
        v = np.concatenate([p[0] for p in partes])
        pts = v[np.random.rand(len(v)) < min(1.0, 20000 / max(1, len(v)))]
        if not cb.exists():
            fallos["colision"].append((*pts.mean(0), f"{n}: terreno sin archivo de colisión"))
            continue
        cv, ct = leer_ybn(cb)
        cp, _ = muestras(cv, ct, 1.5)
        d, _ = cKDTree(cp[:, :2]).query(pts[:, :2], distance_upper_bound=4.0)
        sin = ~np.isfinite(d)
        if sin.mean() > 0.01:
            fallos["colision"].append((*pts[sin].mean(0), f"{n}: {sin.mean() * 100:.0f} % del terreno sin "
                                                          "colisión debajo"))
    SALIDA.mkdir(parents=True, exist_ok=True)
    with open(SALIDA / f"{hoja}.txt", "w", encoding="utf-8") as f:
        for tipo, lista in fallos.items():
            for x, y, z, texto in lista:
                f.write(f"{tipo}\t{x:.0f} {y:.0f} {z:.0f}\t{texto}\n")
    return {k: len(v) for k, v in fallos.items()}


def main():
    hojas = sys.argv[1:] or sorted(h.name for h in RAIZ.iterdir() if re.fullmatch(r"\d{6}", h.name)
                                   and (h / "colocacion.pkl").exists())
    total = Counter()
    for h in hojas:
        r = revisar(h)
        total.update(r)
        print(h, " ".join(f"{k}={v}" for k, v in sorted(r.items())) or "sin fallos", flush=True)
    print("TOTAL", " ".join(f"{k}={v}" for k, v in sorted(total.items())))


if __name__ == "__main__":
    main()
