"""Prototipo: una hoja LiDAR de 1 km² (terreno + edificios) en XML de CodeWalker, para probar la
cadena completa en GTA V antes de generar las cuatro ciudades.

Por casilla de 250 m:
  bcn_t_<E>_<N>.ydr/.ybn   terreno: malla de 2 m del LiDAR con la ortofoto de 12,5 cm (2048 px)
  bcn_e_<E>_<N>.ydr/.ybn   edificios: cada parte del Catastro a la altura de su tejado en el LiDAR;
                           tejado con la ortofoto, fachadas con la foto del Catastro si la hay
  bcn_t_<E>_<N>.ytd        texturas de la casilla (ortofoto + fachadas)
y para toda la hoja bcn_<hoja>.ytyp (arquetipos) y bcn_<hoja>.ymap (colocación).

Uso: python prototipo.py 434589
"""
import json
import pickle
import shutil
import sys

import numpy as np
import shapely
from PIL import Image, ImageDraw, ImageOps
from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient

import config_v
import edificios_v
import calles_v
import monumentos_v
import puentes_v
import rage
import tuneles_v
import andenes_v

CASILLA = 250
PASO = 2.0  # malla del terreno
PX_SUELO = 2048
PX_FACHADA = 512
DIST_TERRENO, DIST_EDIFICIOS = 1500.0, 800.0
HUNDIR = 0.20  # m que baja el terreno visible bajo calles y aceras (la colisión se queda)
# LOD de la casilla (bcn_l_): terreno de 10 m, edificios como prismas y la ortofoto en pequeño.
# Por debajo de DIST_HIJOS se ve el detalle (terreno, tejados, fachadas, puentes), más lejos el LOD.
PASO_LOD, PX_LOD, DIST_LOD, DIST_HIJOS = 10.0, 512, 8000.0, 800.0
SALIDA = config_v.MOD / "prototipo"


def cargar_hoja(hoja):
    capas = puentes_v.hoja_corregida(hoja)  # sin el tablero de los viaductos metido en el suelo
    e0, n1 = int(hoja[:3]) * 1000, (4000 + int(hoja[3:]) + 1) * 1000
    return capas, e0, n1


def muestrear(rej, e0, n1, e, n):
    """Valor de una rejilla de 0,5 m de la hoja en coordenadas UTM (vecino más cercano)."""
    m = rej.shape[0]
    c = np.clip(((np.asarray(e) - e0) / 0.5).astype(int), 0, m - 1)
    f = np.clip(((n1 - np.asarray(n)) / 0.5).astype(int), 0, m - 1)
    return rej[f, c]


def mosaico(e0, n0, lado, px):
    """Ortofoto de la ventana [e0, e0+lado] x [n0, n0+lado] a px x px."""
    t, px_t = 125, 1000
    lienzo_px = int(lado / t * px_t) + 2048
    lienzo = Image.new("RGB", (lienzo_px, lienzo_px), (110, 110, 110))
    ea, na = e0 - e0 % t, n0 - n0 % t
    for e in range(ea, e0 + lado, t):
        for n in range(na, n0 + lado, t):
            ruta = config_v.DATOS / "orto" / f"{e}_{n}.jpg"
            if ruta.exists():
                x = (e - ea) * px_t // t
                y = lienzo_px - (n - na + t) * px_t // t
                lienzo.paste(Image.open(ruta).convert("RGB"), (x, y))
    x0 = (e0 - ea) * px_t / t
    y1 = lienzo_px - (n0 - na) * px_t / t
    caja = (int(x0), int(y1 - lado * px_t / t), int(x0 + lado * px_t / t), int(y1))
    return lienzo.crop(caja).resize((px, px), Image.LANCZOS)


def bajo_puentes(img, capas, e0h, n1h, e0, n0):
    """La ortofoto ve el tablero de los puentes, no lo que hay debajo: ahí se pinta suelo de tierra y
    hormigón en sombra (las calles y aparcamientos de debajo los pone calles_v encima)."""
    m = int(CASILLA / 0.5)
    f0, c0 = int((n1h - n0 - CASILLA) / 0.5), int((e0 - e0h) / 0.5)
    puente = ~np.isnan(capas["puente"][f0:f0 + m, c0:c0 + m])
    if not puente.any():
        return img
    from scipy import ndimage
    puente = ndimage.binary_dilation(puente, iterations=2)
    mascara = Image.fromarray((puente * 255).astype(np.uint8)).resize(img.size, Image.BILINEAR)
    r = np.random.default_rng(e0 + n0)
    base = np.full((img.size[1], img.size[0], 3), (92, 88, 82), np.float32)
    grueso = np.asarray(Image.fromarray(r.normal(0, 1, (64, 64)).astype(np.float32)).resize(img.size, Image.BICUBIC))
    base += 10 * grueso[..., None] + r.normal(0, 7, base.shape[:2])[..., None]
    suelo = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    return Image.composite(suelo, img, mascara)


_MURO = []


def textura_muro():
    """Muro de contención de hormigón (2,5 m por repetición), con juntas de encofrado y manchas de agua."""
    if not _MURO:
        r = np.random.default_rng(5)
        a = np.full((512, 512, 3), (150, 148, 142), np.float32)
        a += r.normal(0, 7, (512, 512))[..., None]
        manchas = np.asarray(Image.fromarray(r.normal(0, 1, (16, 16)).astype(np.float32)).resize((512, 512), Image.BICUBIC))
        a += 10 * manchas[..., None]
        a[:, ::128] -= 18  # juntas entre paneles de encofrado (62,5 cm)
        a[::205] -= 14
        chorreo = np.convolve(r.normal(0, 1, 512), np.ones(9) / 9, mode="same")
        a -= (6 * np.abs(chorreo))[None, :, None] * np.linspace(1, 0.2, 512)[:, None, None]
        _MURO.append(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)))
    return _MURO[0]


def separar_muros(v, n, tris, rango=1.8):
    """Triángulos del terreno casi verticales (suben más de 'rango' m en 2 m: muros de contención,
    taludes de la C-31): la ortofoto se estiraba en ellos. Se devuelven aparte, con UV vertical para la
    textura de muro. -> (índices llanos, geometría de muro o None)."""
    z = v[tris][:, :, 2]
    empinado = np.ptp(z, axis=1) > rango
    if not empinado.any():
        return tris, None
    t = tris[empinado]
    p = v[t].reshape(-1, 3)
    nn = n[t].reshape(-1, 3)
    horiz = np.hypot(nn[:, 0], nn[:, 1]) + 1e-9
    # u a lo largo del muro (perpendicular a su normal horizontal), v en altura
    dx, dy = -nn[:, 1] / horiz, nn[:, 0] / horiz
    uv = np.c_[(p[:, 0] * dx + p[:, 1] * dy) / 2.5, p[:, 2] / 2.5]
    gris = np.full(len(p), 235)
    muro = dict(v=p, n=nn, uv=uv, color=np.c_[gris, gris, gris, np.full(len(p), 255)],
                i=np.arange(len(p)).reshape(-1, 3))
    return tris[~empinado], muro


def mascara_edificios(partes, centros, e0h, n1h, m):
    """Plantas del Catastro en la rejilla de 0,5 m de la hoja (los patios, fuera)."""
    img = Image.new("1", (m, m), 0)
    dib = ImageDraw.Draw(img)
    cerca = (centros[:, 0] > e0h - 100) & (centros[:, 0] < e0h + 1100) & (centros[:, 1] > n1h - 1100) &             (centros[:, 1] < n1h + 100)
    for k in np.flatnonzero(cerca):
        anillos = partes[k]["anillos"]
        for j, a in enumerate(anillos):
            q = [((x - e0h) / 0.5, (n1h - y) / 0.5) for x, y in a]
            if len(q) >= 3:
                dib.polygon(q, fill=0 if j else 1)
    return np.asarray(img, bool)


def terreno(capas, e0h, n1h, e0, n0):
    k = int(CASILLA / PASO) + 1
    xs = np.linspace(0, CASILLA, k)
    gx, gy = np.meshgrid(xs, xs[::-1])
    if "suelo_2m" not in capas:  # media de 2,5 m: un píxel suelto de 0,5 m cada 2 m daba dientes de sierra en taludes
        from scipy import ndimage
        s = capas["suelo"].astype(np.float32)
        if "mascara_edif" in capas:
            # dentro de los edificios del Catastro, el suelo más bajo de 2 m alrededor: una plaza sobre un
            # podio o el suelo interpolado bajo el edificio sacaban dientes de sierra delante de la fachada
            m = capas["mascara_edif"]
            bajo = ndimage.grey_erosion(np.where(np.isnan(s), np.inf, s), size=9, mode="nearest")
            s = np.where(m & np.isfinite(bajo), np.fmin(s, bajo), s)
        hueco = np.isnan(s)
        media = ndimage.uniform_filter(np.where(hueco, 0, s), 5, mode="nearest")
        peso = ndimage.uniform_filter((~hueco).astype(np.float32), 5, mode="nearest")
        capas["suelo_2m"] = np.where(peso > 0, media / np.maximum(peso, 1e-6), np.nan)
    z = muestrear(capas["suelo_2m"], e0h, n1h, e0 + gx, n0 + gy).astype(np.float64)
    dzdx = np.gradient(z, PASO, axis=1)
    dzdy = -np.gradient(z, PASO, axis=0)
    n = np.dstack([-dzdx, -dzdy, np.ones_like(z)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    centro = CASILLA / 2
    v = np.dstack([gx - centro, gy - centro, z]).reshape(-1, 3)
    uv = np.dstack([gx / CASILLA, gy / CASILLA]).reshape(-1, 2)
    i = np.arange(k * k).reshape(k, k)
    a, b, c, d = i[:-1, :-1].ravel(), i[:-1, 1:].ravel(), i[1:, :-1].ravel(), i[1:, 1:].ravel()
    tris = np.concatenate([np.stack([a, c, b], 1), np.stack([b, c, d], 1)])
    return v, n.reshape(-1, 3), uv, tris


def superficie(capas):
    """Suelo con los tableros de los puentes encima: el terreno del LOD (los edificios van aparte)."""
    return np.fmax(capas["suelo"], capas["puente"])


MAR = []  # [mar de costa_v recortado a la hoja y preparado] (vacío: sin costa)


def fuera_del_mar(v_utm, tris):
    """Máscara de los triángulos que se quedan: fuera los del mar que están a menos de 1 m (el relleno del
    LiDAR sobre el agua); los muelles y espigones más altos se quedan aunque OSM los ponga en el mar."""
    if not MAR or MAR[0] is None or not len(tris):
        return np.ones(len(tris), bool)
    p = v_utm[tris]
    c = p.mean(1)
    return ~(shapely.contains_xy(MAR[0], c[:, 0], c[:, 1]) & (p[:, :, 2].max(1) < 1.0))


def lod(sup, e0h, n1h, e0, n0, vols):
    """LOD de la casilla: terreno de PASO_LOD m y cada volumen del Catastro como prisma de planta
    simplificada con el tejado a su altura. Todo con la ortofoto vista desde arriba; las paredes, más oscuras."""
    k = int(CASILLA / PASO_LOD) + 1
    xs = np.linspace(0, CASILLA, k)
    gx, gy = np.meshgrid(xs, xs[::-1])
    z = muestrear(sup, e0h, n1h, e0 + gx, n0 + gy).astype(np.float64)
    c = CASILLA / 2
    v = list(np.dstack([gx - c, gy - c, z]).reshape(-1, 3))
    n = [(0.0, 0.0, 1.0)] * len(v)
    luz = [1.0] * len(v)
    i = np.arange(k * k).reshape(k, k)
    a, b, cc, d = i[:-1, :-1].ravel(), i[:-1, 1:].ravel(), i[1:, :-1].ravel(), i[1:, 1:].ravel()
    tris = np.concatenate([np.stack([a, cc, b], 1), np.stack([b, cc, d], 1)])
    tris = list(tris[fuera_del_mar(np.array(v) + [e0 + c, n0 + c, 0], tris)])
    for vol in vols:
        poli = vol["poli"].simplify(1.0)
        if poli.is_empty or poli.geom_type != "Polygon":
            continue
        poli = orient(poli, 1.0)  # exterior antihorario: paredes hacia fuera
        suelo, techo = vol["suelo"] - 1.0, vol["techo"]
        for tri in triangular(poli):
            base = len(v)
            v += [(x - e0 - c, y - n0 - c, techo) for x, y in tri]
            n += [(0.0, 0.0, 1.0)] * 3
            luz += [1.0] * 3
            tris.append((base, base + 1, base + 2))
        for anillo in [poli.exterior] + list(poli.interiors):
            q = np.asarray(anillo.coords)
            for (ax, ay), (bx, by) in zip(q[:-1], q[1:]):
                largo = np.hypot(bx - ax, by - ay)
                if largo < 1e-3:
                    continue
                base = len(v)
                v += [(ax - e0 - c, ay - n0 - c, suelo), (bx - e0 - c, by - n0 - c, suelo),
                      (bx - e0 - c, by - n0 - c, techo), (ax - e0 - c, ay - n0 - c, techo)]
                n += [((by - ay) / largo, -(bx - ax) / largo, 0.0)] * 4
                luz += [0.62] * 4
                tris += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    if not len(tris):  # casilla de mar: el LOD es padre de las HD y no puede quedar vacío; un triángulo bajo el agua
        base = len(v)
        v += [(0.0, 0.0, -20.0), (0.1, 0.0, -20.0), (0.0, 0.1, -20.0)]
        n += [(0.0, 0.0, 1.0)] * 3
        luz += [1.0] * 3
        tris.append((base, base + 1, base + 2))
    v = np.array(v, float)
    uv = (v[:, :2] + c) / CASILLA
    gris = (255 * np.array(luz)).astype(int)
    return dict(v=v, n=np.array(n, float), uv=uv, color=np.c_[gris, gris, gris, np.full(len(v), 255)],
                i=np.array(tris, int))


def triangular(poligono):
    """Triángulos (lista de (3, 2)) que cubren el polígono con sus huecos."""
    trozos = shapely.constrained_delaunay_triangles(poligono)
    tris = []
    for t in trozos.geoms:
        if t.area <= 1e-4:
            continue
        p = np.asarray(t.exterior.coords)[:3]
        # antihorario visto desde arriba: si no, el juego no pinta la cara (se ve negra o falta)
        if (p[1, 0] - p[0, 0]) * (p[2, 1] - p[0, 1]) - (p[1, 1] - p[0, 1]) * (p[2, 0] - p[0, 0]) < 0:
            p = p[::-1]
        tris.append(p)
    return tris


def partir(g, maximo=60000):
    """Divide una geometría en trozos de menos de 65535 vértices (por triángulos). Sin triángulos no da nada;
    los vértices que no usa ningún triángulo (los quitados por el mar o un túnel) se quitan."""
    if not len(g["i"]):
        return
    if len(g["v"]) <= maximo:
        usados = np.unique(g["i"])
        if len(usados) < len(g["v"]):
            nuevo = np.full(len(g["v"]), -1, np.int64)
            nuevo[usados] = np.arange(len(usados))
            g = {**{k: g[k][usados] for k in ("v", "n", "uv", "color") if k in g}, "i": nuevo[g["i"]]}
        yield g
        return
    tris = g["i"]
    paso = maximo // 3
    for k in range(0, len(tris), paso):
        t = tris[k:k + paso]
        usados, nuevos = np.unique(t, return_inverse=True)
        yield {**{k: g[k][usados] for k in ("v", "n", "uv", "color") if k in g}, "i": nuevos.reshape(-1, 3)}


def fachadas_ytd(xml):
    """Diccionario compartido por todos los edificios: materiales de pared y atlas de piezas."""
    carpeta = config_v.DATOS / "texturas"
    texturas = {r.stem: (Image.open(r), False) for r in sorted(carpeta.glob("pa_*.png"))}
    texturas["fa_piezas"] = (Image.open(carpeta / "fachadas.png"), True)
    rage.escribir_ytd(xml / "bcn_fachadas.ytd.xml", texturas)


def pasajes(osm):
    """Planta de las calles y caminos que pasan por debajo de un edificio y se dibujan a nivel (los túneles
    largos van en tubo, tuneles_v): pasajes de OSM y túneles cortos bajo plazas y edificios."""
    trozos = []
    for v in osm["vias"]:
        t = v["tags"]
        if t.get("tunnel") not in ("yes", "building_passage") or "highway" not in t or len(v["xy"]) < 2:
            continue
        if (calles_v._num(t.get("layer")) or 0) <= -2:
            continue  # rampas de aparcamientos subterráneos
        xy = v["xy"]
        if (round(float(xy[0][0]), 1), round(float(xy[0][1]), 1), round(float(xy[-1][0]), 1),
                round(float(xy[-1][1]), 1)) in calles_v.EN_TUNEL:
            continue
        coche = t["highway"] in calles_v.CARRILES and t["highway"] != "service"
        ancho = calles_v._num(t.get("width")) or ((calles_v._num(t.get("lanes")) or 2) * 3.3 + 1.5 if coche else 3.5)
        trozos.append(shapely.LineString(xy).buffer(ancho / 2 + 0.5, cap_style="flat"))
    return shapely.union_all(trozos) if trozos else None


def colision_edificios(vols, origen, casilla, mundo):
    """Colisión sencilla: tejado y paredes lisas de cada volumen (los balcones no hacen falta)."""
    e0, n0 = origen
    c = casilla / 2
    v, t = [], []
    for vol in vols:
        poli, suelo, techo = vol["poli"], vol["suelo"], vol["techo"]
        for tri in edificios_v.triangular(poli):
            base = len(v)
            v += [(x - e0 - c, y - n0 - c, techo) for x, y in tri]
            t.append((base, base + 1, base + 2))
        for anillo in [poli.exterior] + list(poli.interiors):
            q = np.asarray(anillo.coords)
            for (ax, ay), (bx, by) in zip(q[:-1], q[1:]):
                base = len(v)
                v += [(ax - e0 - c, ay - n0 - c, suelo), (bx - e0 - c, by - n0 - c, suelo),
                      (bx - e0 - c, by - n0 - c, techo), (ax - e0 - c, ay - n0 - c, techo)]
                t += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    return np.array(v) + mundo, np.array(t)


def main():
    global SALIDA
    hoja = sys.argv[1]
    SALIDA = config_v.MOD / "prototipo" / hoja  # cada hoja en su carpeta
    capas, e0h, n1h = cargar_hoja(hoja)
    partes, info = [], {}
    for muni in config_v.MUNICIPIOS:  # una hoja puede caer entre dos municipios (Llefià y el Fondo)
        if not (config_v.DATOS / "catastro" / f"{muni}.pkl").exists():
            continue
        with open(config_v.DATOS / "catastro" / f"{muni}.pkl", "rb") as fh:
            d = pickle.load(fh)
        partes += d["partes"]
        info.update(d["edificios"])
    partes = [p for p in partes if not monumentos_v.excluido(p["anillos"][0].mean(0))]  # los hace monumentos_v
    centros = np.array([p["anillos"][0].mean(0) for p in partes])
    capas["mascara_edif"] = mascara_edificios(partes, centros, e0h, n1h, capas["suelo"].shape[0])
    import costa_v
    mar = costa_v.mar()
    if mar is not None:
        mar = mar.intersection(shapely.box(e0h - 10, n1h - 1010, e0h + 1010, n1h + 10))
        mar = None if mar.is_empty else mar
        if mar is not None:
            shapely.prepare(mar)
    MAR[:] = [mar]
    ruta_colores = config_v.DATOS / "texturas" / "colores.json"
    colores = json.loads(ruta_colores.read_text()) if ruta_colores.exists() else {}
    ruta_osm = config_v.DATOS / "osm.pkl"
    calles, puentes, osm_hoja, tuneles, pasos = None, [], None, [], None
    if ruta_osm.exists():
        with open(ruta_osm, "rb") as fh:
            osm = pickle.load(fh)
        calles = edificios_v.arbol_calles(osm)
        osm_hoja = calles_v.recortar(osm, (e0h - 300, n1h - 1300, e0h + 1300, n1h + 300))
        # recintos de obra vista según OSM (p. ej. la fábrica de Anís del Mono): sus edificios, de ladrillo
        ladrillo = [Polygon(a["xy"]).buffer(0) for a in osm_hoja["areas"]
                    if a["tags"].get("wall") == "brick_wall" or a["tags"].get("building:material") == "brick"]
        for z in ladrillo:
            for k in np.flatnonzero(shapely.contains_xy(z, centros[:, 0], centros[:, 1])):
                colores[partes[k]["ref"]] = dict(material="ladrillo_rojo", rgb=[150, 74, 54])
        tuneles = tuneles_v.preparar_cacheado(osm, puentes_v.Relieve())
        calles_v.EN_TUNEL.update((round(float(t["xy"][0][0]), 1), round(float(t["xy"][0][1]), 1),
                                  round(float(t["xy"][-1][0]), 1), round(float(t["xy"][-1][1]), 1)) for t in tuneles)
        pasos = pasajes(osm_hoja)
        puentes = puentes_v.vias_puente(osm)
        puentes_v.extremos_internos(puentes)  # con todos: un tramo que sigue en otra vía no baja al suelo
        del osm
    relieve = puentes_v.Relieve()
    xml = SALIDA / "xml"
    shutil.rmtree(SALIDA, ignore_errors=True)
    xml.mkdir(parents=True)
    fachadas_ytd(xml)
    rage.escribir_ytd(xml / "bcn_obra.ytd.xml", puentes_v.texturas())
    arquetipos, entidades, lods = [], [], []
    sup = superficie(capas)
    todas_alturas, n_tris = [], 0
    for e0 in range(e0h, e0h + 1000, CASILLA):
        for n0 in range(n1h - 1000, n1h, CASILLA):
            nombre = f"{e0 // 10}_{n0 // 10}"
            # Las colisiones del mapa se cargan solas y van en coordenadas del mundo
            gx, gy = config_v.utm_a_juego(e0 + CASILLA / 2, n0 + CASILLA / 2)
            mundo = np.array([gx, gy, 0.0])
            orto = f"bcn_o_{nombre}"
            rage.escribir_ytd(xml / f"{orto}.ytd.xml",
                              {orto: (bajo_puentes(mosaico(e0, n0, CASILLA, PX_SUELO), capas, e0h, n1h, e0, n0), False),
                               "bcn_muro": (textura_muro(), False)})
            v, n, uv, tris = terreno(capas, e0h, n1h, e0, n0)
            # túneles: fuera el terreno que se mete en el tubo (la pared de la boca)
            cerca_t = [t for t in tuneles if t["pts"][:, 0].max() >= e0 - 10 and t["pts"][:, 0].min() < e0 + CASILLA + 10
                       and t["pts"][:, 1].max() >= n0 - 10 and t["pts"][:, 1].min() < n0 + CASILLA + 10]
            if cerca_t:
                tris = tris[tuneles_v.fuera(v + [e0 + CASILLA / 2, n0 + CASILLA / 2, 0], tris, cerca_t)]
            tris = tris[fuera_del_mar(v + [e0 + CASILLA / 2, n0 + CASILLA / 2, 0], tris)]
            cubierto = []  # lo que tapan calles y aceras: ahí el terreno que se ve baja (el terreno se escribe después)
            # Partes de la casilla y, para las medianeras, las de 40 m alrededor
            m = 40
            en_casilla = (centros[:, 0] >= e0) & (centros[:, 0] < e0 + CASILLA) & \
                         (centros[:, 1] >= n0) & (centros[:, 1] < n0 + CASILLA)
            cerca = (centros[:, 0] >= e0 - m) & (centros[:, 0] < e0 + CASILLA + m) & \
                    (centros[:, 1] >= n0 - m) & (centros[:, 1] < n0 + CASILLA + m)
            vecinos = edificios_v.pasajes(edificios_v.volumenes([partes[i] for i in np.flatnonzero(cerca)], capas, e0h, n1h),
                                          pasos, capas, e0h, n1h)
            propios = [vv for vv in vecinos if en_casilla[0] is not None and
                       e0 <= vv["p"]["anillos"][0][:, 0].mean() < e0 + CASILLA and
                       n0 <= vv["p"]["anillos"][0][:, 1].mean() < n0 + CASILLA]
            todas_alturas += [vv["techo"] - vv["suelo"] for vv in propios]
            if osm_hoja is not None:  # calzada, aceras, aparcamientos y marcas viales sobre el terreno
                k = int(CASILLA / PASO) + 1
                suelo_calles = calles_v.construir(osm_hoja, [vv["poli"] for vv in vecinos], v[:, 2].reshape(k, k),
                                                  e0, n0, CASILLA, PASO, cubierto)
                if suelo_calles:
                    rage.escribir_ydr(xml / f"bcn_c_{nombre}.ydr.xml", f"bcn_c_{nombre}",
                                      [dict(textura=t, recorte=t.endswith("_alfa"), **trozo) for t, g in suelo_calles.items() for trozo in partir(g)],
                                      DIST_EDIFICIOS)
                    arquetipos.append((f"bcn_c_{nombre}", "bcn_obra", DIST_EDIFICIOS))
                # andenes de las estaciones y paradas de tranvía, con su colisión
                andenes, col_a = andenes_v.construir(osm_hoja, box(e0, n0, e0 + CASILLA, n0 + CASILLA),
                                                     calles_v.Suelo(v[:, 2].reshape(k, k), e0, n0, CASILLA, PASO),
                                                     (e0 + CASILLA / 2, n0 + CASILLA / 2))
                if andenes:
                    rage.escribir_ydr(xml / f"bcn_a_{nombre}.ydr.xml", f"bcn_a_{nombre}",
                                      [dict(textura=t, **trozo) for t, g in andenes.items() for trozo in partir(g)],
                                      DIST_EDIFICIOS)
                    rage.escribir_ybn(xml / f"bcn_a_{nombre}.ybn.xml", col_a[0] + mundo, col_a[1], [rage.MAT_CONCRETE],
                                      np.zeros(len(col_a[1]), int))
                    arquetipos.append((f"bcn_a_{nombre}", "bcn_obra", DIST_EDIFICIOS))
            # El terreno que se ve baja HUNDIR m bajo calles y aceras: a 4 cm por debajo del asfalto, en las cuestas
            # el juego no sabía cuál va delante y el terreno asomaba a dientes de sierra. La colisión no cambia.
            v_ver = v
            if cubierto and not cubierto[0].is_empty:
                dentro = shapely.contains_xy(cubierto[0], v[:, 0] + e0 + CASILLA / 2, v[:, 1] + n0 + CASILLA / 2)
                v_ver = v.copy()
                v_ver[dentro, 2] -= HUNDIR
            llano, muro = separar_muros(v_ver, n, tris)
            geos_t = [dict(textura=orto, color=np.full((len(t["v"]), 4), 255), **t)
                      for t in partir(dict(v=v_ver, n=n, uv=uv, i=llano))] + \
                     ([dict(textura="bcn_muro", **t) for t in partir(muro)] if muro else [])
            if geos_t:  # una casilla toda de mar no lleva terreno: se ve el agua del juego
                rage.escribir_ydr(xml / f"bcn_t_{nombre}.ydr.xml", f"bcn_t_{nombre}", geos_t, DIST_TERRENO)
                rage.escribir_ybn(xml / f"bcn_t_{nombre}.ybn.xml", v + mundo, tris, [rage.MAT_PAVEMENT],
                                  np.zeros(len(tris), int))
                arquetipos.append((f"bcn_t_{nombre}", orto, DIST_TERRENO))
            modelo_lod = f"bcn_l_{nombre}"
            rage.escribir_ytd(xml / f"{modelo_lod}.ytd.xml", {modelo_lod: (mosaico(e0, n0, CASILLA, PX_LOD), False)})
            rage.escribir_ydr(xml / f"{modelo_lod}.ydr.xml", modelo_lod,
                              [dict(textura=modelo_lod, **t) for t in partir(lod(sup, e0h, n1h, e0, n0, propios))],
                              DIST_LOD)
            tejados, fachadas = edificios_v.construir(propios, vecinos, info, colores, calles, (e0, n0), CASILLA)
            if tejados is not None:
                rage.escribir_ydr(xml / f"bcn_r_{nombre}.ydr.xml", f"bcn_r_{nombre}",
                                  [dict(textura=orto, color=np.full((len(t["v"]), 4), 255), **t)
                                   for t in partir(tejados)], DIST_EDIFICIOS)
                arquetipos.append((f"bcn_r_{nombre}", orto, DIST_EDIFICIOS))
                cv, ct = colision_edificios(propios, (e0, n0), CASILLA, mundo)
                rage.escribir_ybn(xml / f"bcn_e_{nombre}.ybn.xml", cv, ct, [rage.MAT_PLASTER], np.zeros(len(ct), int))
            lista = []
            for tex, geo in fachadas.items():
                for trozo in partir(geo):
                    n_tris += len(trozo["i"])
                    lista.append(dict(textura="fa_piezas" if tex.startswith("fa_piezas") else tex,
                                      recorte=tex == "fa_piezas_alfa", **trozo))
            if lista:
                rage.escribir_ydr(xml / f"bcn_e_{nombre}.ydr.xml", f"bcn_e_{nombre}", lista, DIST_EDIFICIOS)
                arquetipos.append((f"bcn_e_{nombre}", "bcn_fachadas", DIST_EDIFICIOS))
            # Puentes y viaductos: el trozo de cada uno que cruza la casilla
            caja = (e0, n0, e0 + CASILLA, n0 + CASILLA)
            aqui = [v for v in puentes if v["xy"][:, 0].max() >= e0 - 5 and v["xy"][:, 0].min() < e0 + CASILLA + 5
                    and v["xy"][:, 1].max() >= n0 - 5 and v["xy"][:, 1].min() < n0 + CASILLA + 5]
            if aqui:
                obra, col, hechos = puentes_v.construir(aqui, relieve, calles, (e0 + CASILLA / 2, n0 + CASILLA / 2),
                                                        caja)
                if hechos:
                    geos = [dict(textura=t, recorte=t.endswith("_alfa"), **trozo) for t, g in obra.items()
                            for trozo in partir(g)]
                    rage.escribir_ydr(xml / f"bcn_p_{nombre}.ydr.xml", f"bcn_p_{nombre}", geos, DIST_TERRENO)
                    mats, cual = np.unique(col[2], return_inverse=True)
                    rage.escribir_ybn(xml / f"bcn_p_{nombre}.ybn.xml", col[0] + mundo, col[1], mats.tolist(), cual)
                    arquetipos.append((f"bcn_p_{nombre}", "bcn_obra", DIST_TERRENO))
            if cerca_t:
                obra_t, col_t, hechos_t = tuneles_v.construir(cerca_t, (e0 + CASILLA / 2, n0 + CASILLA / 2), caja)
                if hechos_t and col_t is not None:
                    rage.escribir_ydr(xml / f"bcn_u_{nombre}.ydr.xml", f"bcn_u_{nombre}",
                                      [dict(textura=t, **trozo) for t, g in obra_t.items() for trozo in partir(g)],
                                      DIST_EDIFICIOS)
                    mats, cual = np.unique(col_t[2], return_inverse=True)
                    rage.escribir_ybn(xml / f"bcn_u_{nombre}.ybn.xml", col_t[0] + mundo, col_t[1], mats.tolist(), cual)
                    arquetipos.append((f"bcn_u_{nombre}", "bcn_obra", DIST_EDIFICIOS))
            arquetipos.append((modelo_lod, modelo_lod, DIST_LOD))
            lods.append((modelo_lod, (gx, gy, 0.0), DIST_LOD, DIST_HIJOS))
            for modelo, ytd, dist in arquetipos[-12:]:
                if modelo.endswith(nombre) and modelo != modelo_lod and all(e[0] != modelo for e in entidades):
                    entidades.append((modelo, (gx, gy, 0.0), DIST_HIJOS, len(lods) - 1))
            print(f"Casilla {nombre}: {len(propios)} volúmenes, {sum(len(x['i']) for x in lista)} triángulos de fachada",
                  flush=True)
    monumentos_v.escribir(xml, e0h, n1h, lambda e, n: float(muestrear(capas["suelo"], e0h, n1h, e, n)),
                          arquetipos, entidades)
    with open(SALIDA / "colocacion.pkl", "wb") as fh:
        pickle.dump(dict(arquetipos=arquetipos, entidades=entidades, lods=lods), fh)
    todas_alturas = todas_alturas or [0.0]  # hoja de mar
    print(f"Alturas: mediana {np.median(todas_alturas):.1f} m, máx {max(todas_alturas):.1f} m; "
          f"{n_tris} triángulos de fachada en la hoja")


if __name__ == "__main__":
    main()
