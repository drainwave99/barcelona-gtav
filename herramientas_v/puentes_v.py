"""Puentes y viaductos (autopistas, enlaces, calles, tren y pasarelas) a su altura real.

Trazado, tipo, carriles y sentido: OpenStreetMap (bridge=*).
Altura del tablero: LiDAR del ICGC, clase 17 (puente), mediana a lo ancho y perfil suavizado; donde
falta, se interpola entre los tramos medidos y los estribos (que se apoyan en el terreno).
Sección según el tipo de vía:
  autopista / enlace  tablero de cajón con voladizos, arcenes, marcas viales y barreras New Jersey
  calle               calzada, aceras de panot y pretil de hormigón
  tren                balasto con traviesas, dos carriles y pretil
  pasarela            losa con barandilla
Pilas cada ~30 m donde hay gálibo, apartadas de las calles que pasan por debajo.

construir(vias, relieve, calles, centro) -> (malla {textura: arrays}, colisión (v, tris, mats))
"""
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from shapely.geometry import LineString, Point

import config_v
import fachadas_v
import rage
import texturas_fachada

PASO = 2.0  # muestreo del eje (m)
ENTRE_PILAS = 30.0
ASFALTO = 0.04  # el asfalto de calles_v va 4 cm sobre el terreno (SUBE["vi_asfalto"])
LLEGADA = 12.0  # m en que el tablero se acerca a la calle a la que llega
GALIBO_BAJO = 5.0  # de la calzada de abajo a la cara inferior del puente que la cruza por encima
RAPIDAS = {"motorway", "trunk"}
ENLACES = {"motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}
URBANAS = {"primary", "secondary", "tertiary", "residential", "unclassified", "living_street", "service", "road"}
PEATONES = {"footway", "cycleway", "path", "pedestrian", "steps", "bridleway", "track"}
TRENES = {"rail", "light_rail", "subway", "narrow_gauge", "tram"}
SUPERFICIES = {"vi_asfalto", "vi_acera", "vi_balasto"}  # lo que se pisa (colisión de calzada)


def _huella_puentes(clave):
    """Máscara (2000, 2000) de la hoja con la planta de los puentes de OSM (ancho + 3 m a cada lado)."""
    import pickle
    with open(config_v.DATOS / "osm.pkl", "rb") as fh:
        osm = pickle.load(fh)
    e0, n1 = int(clave[:3]) * 1000, (4000 + int(clave[3:]) + 1) * 1000
    img = Image.new("L", (2000, 2000), 0)
    dib = ImageDraw.Draw(img)
    for v in vias_puente(osm, (e0 - 200, n1 - 1200, e0 + 1200, n1 + 200)):
        if v["tags"].get("railway") or v["s"]["tipo"] == "pasarela":
            continue
        # autopistas: +8 m (tableros gemelos con mediana y voladizos más anchos que la sección de OSM)
        margen = 8.0 if v["s"]["tipo"] == "autopista" else 3.0
        ancho = int(round((v["s"]["ancho"] / 2 + margen) / 0.5))
        pts = [((x - e0) / 0.5, (n1 - y) / 0.5) for x, y in v["xy"]]
        dib.line(pts, fill=255, width=2 * ancho, joint="curve")
    # menos las vías rápidas que no son puente (ramales y tronco en terraplén: ese terreno es de verdad)
    for v in osm["vias"]:
        t = v["tags"]
        if t.get("highway") not in RAPIDAS | {"motorway_link", "trunk_link"} or t.get("bridge") not in (None, "no"):
            continue
        if len(v["xy"]) >= 2 and _clave_via(v["xy"]) in inferidos(osm):
            continue
        xy = np.asarray(v["xy"], float)
        if len(xy) < 2 or xy[:, 0].max() < e0 - 50 or xy[:, 0].min() > e0 + 1050 or \
                xy[:, 1].max() < n1 - 1050 or xy[:, 1].min() > n1 + 50:
            continue
        s = seccion(t)
        ancho = int(round((s["ancho"] / 2 + 2.0) / 0.5))
        dib.line([((x - e0) / 0.5, (n1 - y) / 0.5) for x, y in xy], fill=0, width=2 * ancho, joint="curve")
    return np.asarray(img) > 0


def _estribos(clave):
    """Máscara (2000, 2000) de los estribos: círculos de ancho/2 + 1 m en los extremos de puente donde empieza una
    calzada a nivel. Ahí el terraplén de la rampa es suelo de verdad aunque sobresalga del terreno de los lados
    (en el Pont dels Passadors la corrección lo bajaba 1,7 m y la calle se hundía en un hoyo al llegar al puente)."""
    import pickle
    import calles_v
    with open(config_v.DATOS / "osm.pkl", "rb") as fh:
        osm = pickle.load(fh)
    e0, n1 = int(clave[:3]) * 1000, (4000 + int(clave[3:]) + 1) * 1000
    finales = set()
    extra = inferidos(osm)
    for w in osm["vias"]:
        t = w["tags"]
        if t.get("highway") in calles_v.CARRILES and len(w["xy"]) >= 2 and calles_v._a_nivel(t) and                 t.get("tunnel") in (None, "no") and _clave_via(w["xy"]) not in extra:
            for q in (w["xy"][0], w["xy"][-1]):
                finales.add((round(float(q[0]), 1), round(float(q[1]), 1)))
    img = Image.new("L", (2000, 2000), 0)
    dib = ImageDraw.Draw(img)
    for v in vias_puente(osm, (e0 - 200, n1 - 1200, e0 + 1200, n1 + 200)):
        if v["tags"].get("railway") or v["s"]["tipo"] == "pasarela":
            continue
        for q in (v["xy"][0], v["xy"][-1]):
            if (round(float(q[0]), 1), round(float(q[1]), 1)) in finales:
                r = (v["s"]["ancho"] / 2 + 1.0) / 0.5
                c, f = (q[0] - e0) / 0.5, (n1 - q[1]) / 0.5
                dib.ellipse([c - r, f - r, c + r, f + r], fill=255)
    return np.asarray(img) > 0


def hoja_corregida(clave):
    """Capas LiDAR de la hoja con el tablero de los viaductos sacado del suelo. En Sant Roc el ICGC
    clasificó parte del tablero de la C-31 como suelo (13 m sobre un suelo real de 7 m): el terreno salía
    como un terraplén que tapaba las calles de debajo, y el puente, creyendo que el suelo era el tablero,
    se ponía 6,5 m más arriba. Dentro de la planta de los puentes, el 'suelo' que sobresale más de 2,5 m
    del terreno de alrededor pasa a la capa de puente y el hueco se rellena con el terreno de los lados.
    Se guarda en hojas/<clave>_c.npz."""
    base = config_v.DATOS / "lidar" / "hojas" / f"{clave}.npz"
    ruta = base.with_name(f"{clave}_c.npz")
    osm = config_v.DATOS / "osm.pkl"
    if ruta.exists() and ruta.stat().st_mtime > max(base.stat().st_mtime, osm.stat().st_mtime, VERSION_CORRECCION):
        d = np.load(ruta)
        return {k: d[k] for k in d.files}
    d = np.load(base)
    capas = {k: d[k] for k in d.files}
    suelo = capas["suelo"].astype(np.float32)
    huella = _huella_puentes(clave)
    if huella.any():
        # terreno de alrededor: fuera de la huella, relleno hacia dentro por difusión en una rejilla de 2 m
        f = 4
        h, w = suelo.shape[0] // f, suelo.shape[1] // f
        s4 = suelo[:h * f, :w * f].reshape(h, f, w, f)
        hu4 = huella[:h * f, :w * f].reshape(h, f, w, f).any(axis=(1, 3))
        g = np.nanmin(s4, axis=(1, 3)) if np.isnan(s4).any() else s4.min(axis=(1, 3))
        fijo = ~hu4 & ~np.isnan(g)
        rell = np.where(fijo, g, np.nan)
        _, (ii, jj) = ndimage.distance_transform_edt(~fijo, return_indices=True)
        rell = rell[ii, jj]  # arranque: el vecino exterior más cercano
        for _ in range(300):
            media = ndimage.uniform_filter(rell, 3, mode="nearest")
            rell = np.where(fijo, rell, media)
        alrededor = np.kron(rell, np.ones((f, f), np.float32))
        alrededor = np.pad(alrededor, ((0, suelo.shape[0] - alrededor.shape[0]), (0, suelo.shape[1] - alrededor.shape[1])), mode="edge")
        alto = huella & (suelo - alrededor > 2.5) & ~_estribos(clave)
        alto = ndimage.binary_opening(alto, iterations=2)  # nada de píxeles sueltos
        if alto.any():
            puente = capas["puente"].astype(np.float32)
            puente[alto] = np.fmax(puente[alto], suelo[alto])
            # el borde del tablero falso (los 2 px del talud vertical) también baja
            borde = ndimage.binary_dilation(alto, iterations=3) & huella & (suelo - alrededor > 1.0) & ~_estribos(clave)
            suelo[alto | borde] = alrededor[alto | borde]
            capas["suelo"], capas["puente"] = suelo, puente
    capas["suelo"] = _sin_picos(_calles_sin_muros(capas["suelo"].astype(np.float32), clave))
    tmp = ruta.with_name(f"{clave}_c.{config_v.os.getpid()}.tmp.npz")  # atómico: otro proceso puede estar leyendo
    np.savez_compressed(tmp, **capas)
    config_v.os.replace(tmp, ruta)
    return capas


def _sin_picos(suelo):
    """Puntos de fachada o de muro que el ICGC dejó como suelo: crestas de menos de 3,5 m de ancho que
    sobresalen más de 1 m de la mediana de alrededor (salían pirámides junto a los edificios). Los
    escalones y taludes de verdad, más anchos, no cambian."""
    hueco = np.isnan(suelo)
    s = np.where(hueco, np.nanmedian(suelo), suelo)
    mediana = ndimage.median_filter(s, size=7, mode="nearest")
    pico = (s - mediana > 1.0) & ~hueco
    if pico.any():
        suelo = suelo.copy()
        suelo[pico] = mediana[pico]
    return suelo


def _calles_sin_muros(suelo, clave):
    """Bajo las calles a nivel, el 'suelo' que forma una meseta más de 2 m por encima de la calle a los dos
    lados (un pasaje bajo un edificio, la pasarela del Màgic o un tablero que el ICGC dejó como suelo) es
    un muro falso que cortaba la calzada: se baja a la rasante de la calle."""
    import pickle
    import calles_v
    with open(config_v.DATOS / "osm.pkl", "rb") as fh:
        osm = pickle.load(fh)
    e0, n1 = int(clave[:3]) * 1000, (4000 + int(clave[3:]) + 1) * 1000
    m = suelo.shape[0]
    tocados = 0
    for linea, t, w in calles_v.vias_coche(osm, (e0, n1 - 1000, e0 + 1000, n1)):
        largo = linea.length
        if largo < 2:
            continue
        xy = np.asarray(linea.coords)
        t0 = (xy[1] - xy[0]) / (np.linalg.norm(xy[1] - xy[0]) + 1e-9)
        t1 = (xy[-1] - xy[-2]) / (np.linalg.norm(xy[-1] - xy[-2]) + 1e-9)
        d = np.arange(-12.0, largo + 12.0, 1.0)  # con 12 m de más por cada punta, recto
        p = np.array([linea.interpolate(min(max(x, 0), largo)).coords[0] for x in d])
        p[d < 0] += t0 * d[d < 0, None]
        p[d > largo] += t1 * (d[d > largo, None] - largo)
        c = np.clip(((p[:, 0] - e0) / 0.5).astype(int), 0, m - 1)
        f = np.clip(((n1 - p[:, 1]) / 0.5).astype(int), 0, m - 1)
        z = suelo[f, c].astype(np.float64)
        if np.isnan(z).any():
            continue
        k = 12
        zp = np.pad(z, k, mode="edge")
        izq = np.array([zp[i:i + k].min() for i in range(len(z))])
        der = np.array([zp[i + k + 1:i + 2 * k + 1].min() for i in range(len(z))])
        malo = (z > np.maximum(izq, der) + 2.0) & (d >= 0) & (d <= largo)
        if not malo.any():
            continue
        bueno = ~malo
        rasante = np.interp(np.arange(len(z)), np.nonzero(bueno)[0], z[bueno])
        r = int(np.ceil((w / 2 + 1.0) / 0.5))
        for i in np.nonzero(malo)[0]:
            f0, f1, c0, c1 = max(f[i] - r, 0), min(f[i] + r + 1, m), max(c[i] - r, 0), min(c[i] + r + 1, m)
            trozo = suelo[f0:f1, c0:c1]
            alto = trozo > rasante[i] + 1.0
            trozo[alto] = rasante[i]
            tocados += int(alto.sum())
    if tocados:
        print(f"{clave}: {tocados} píxeles de muro falso bajo calles", flush=True)
    return suelo


VERSION_CORRECCION = 1793743271  # sube si cambia hoja_corregida (fecha unix): rehace las _c.npz


class Relieve:
    """Rejillas de 0,5 m del LiDAR de todas las hojas bajadas, consultables en UTM (NaN si falta)."""

    def __init__(self):
        self.hojas = {}

    def _hoja(self, clave):
        if clave not in self.hojas:
            ruta = config_v.DATOS / "lidar" / "hojas" / f"{clave}.npz"
            if ruta.exists():
                d = hoja_corregida(clave)
                self.hojas[clave] = {k: d[k] for k in ("suelo", "puente")}
            else:
                self.hojas[clave] = None
        return self.hojas[clave]

    def valor(self, capa, e, n):
        e, n = np.asarray(e, float), np.asarray(n, float)
        out = np.full(e.shape, np.nan, np.float32)
        ke, kn = np.floor(e / 1000).astype(int), np.floor(n / 1000).astype(int)
        for a, b in set(zip(ke.ravel().tolist(), kn.ravel().tolist())):
            h = self._hoja(f"{a}{b % 1000:03d}")
            if h is None:
                continue
            m = (ke == a) & (kn == b)
            c = np.clip(((e[m] - a * 1000) / 0.5).astype(int), 0, 1999)
            f = np.clip((((b + 1) * 1000 - n[m]) / 0.5).astype(int), 0, 1999)
            out[m] = h[capa][f, c]
        return out


def _numero(texto, defecto):
    try:
        return float(str(texto).split(";")[0].replace(",", ".").replace("m", "").strip())
    except ValueError:
        return defecto


def seccion(t):
    """Medidas de la sección transversal de una vía (m)."""
    hw, rw = t.get("highway"), t.get("railway")
    sentido_unico = t.get("oneway") in ("yes", "1", "-1") or hw in RAPIDAS | ENLACES and t.get("oneway") != "no"
    carriles = int(_numero(t.get("lanes"), 0))
    if rw in TRENES:
        s = dict(tipo="tren", ancho=4.6, canto=1.6, barrera="pretil", carriles=0)
    elif hw in RAPIDAS:
        carriles = carriles or (2 if sentido_unico else 4)
        s = dict(tipo="autopista", carril=3.5, arcen_izq=1.0, arcen_der=2.5, canto=2.0, barrera="jersey")
    elif hw in ENLACES:
        carriles = carriles or 1
        s = dict(tipo="autopista", carril=3.5, arcen_izq=1.0, arcen_der=1.5, canto=1.6, barrera="jersey")
    elif hw in URBANAS:
        carriles = carriles or (1 if sentido_unico else 2)
        s = dict(tipo="calle", carril=3.2, acera=2.2, canto=1.2, barrera="pretil")
    elif hw in PEATONES:
        s = dict(tipo="pasarela", ancho=_numero(t.get("width"), 3.0), canto=0.7, barrera="barandilla", carriles=0)
    else:
        return None
    if s["tipo"] in ("autopista", "calle"):
        s["carriles"] = carriles
        s["doble_sentido"] = not sentido_unico
        bordes = s["arcen_izq"] + s["arcen_der"] if s["tipo"] == "autopista" else 2 * s["acera"]
        s["ancho"] = carriles * s["carril"] + bordes
        if t.get("width") and s["tipo"] == "calle":  # en autopistas 'width' suele ser solo una calzada parcial
            s["ancho"] = max(_numero(t["width"], s["ancho"]), carriles * s["carril"] + 1.0)
    return s


def _clave_via(xy):
    return (round(float(xy[0][0]), 1), round(float(xy[0][1]), 1), round(float(xy[-1][0]), 1), round(float(xy[-1][1]), 1))


_INFERIDOS = None
VERSION_INFERIDOS = 1  # sube si cambia la regla de _inferidos


def inferidos(osm=None):
    """Puentes sin bridge=yes en OSM: calzadas 'a nivel' de menos de 120 m que empalman con un puente y que en el
    LiDAR (sin corregir) van al menos en un 30 % de su largo más de 3 m por encima del suelo, sobre el tablero.
    En la Ronda Litoral sobre la trinchera de Manuel Fernández Márquez la calzada se pegaba al terreno y bajaba al
    fondo; en el Nus de la Trinitat, igual. Devuelve {clave_via: tags}; se guarda en datos_v/puentes_inferidos.pkl."""
    global _INFERIDOS
    if _INFERIDOS is not None:
        return _INFERIDOS
    import pickle
    import calles_v
    ruta = config_v.DATOS / "puentes_inferidos.pkl"
    fuente = config_v.DATOS / "osm.pkl"
    if ruta.exists() and ruta.stat().st_mtime > fuente.stat().st_mtime:
        with open(ruta, "rb") as fh:
            guardado = pickle.load(fh)
        if guardado.get("version") == VERSION_INFERIDOS:
            _INFERIDOS = guardado["vias"]
            return _INFERIDOS
    with open(fuente, "rb") as fh:  # siempre con el OSM entero (a veces llega uno recortado a la hoja)
        osm = pickle.load(fh)
    extremos = set()
    for v in vias_puente(osm, con_inferidos=False):
        for p in (v["xy"][0], v["xy"][-1]):
            extremos.add((round(float(p[0]), 1), round(float(p[1]), 1)))
    hojas = {}

    def bruto(capa, e, n):
        out = np.full(len(e), np.nan)
        for i, (x, y) in enumerate(zip(e, n)):
            k = f"{int(x // 1000)}{int(y // 1000) - 4000:03d}"
            if k not in hojas:
                r = config_v.DATOS / "lidar" / "hojas" / f"{k}.npz"
                hojas[k] = {c: d for c, d in np.load(r).items() if c in ("suelo", "puente")} if r.exists() else None
            h = hojas[k]
            if h is not None:
                out[i] = h[capa][int(((int(y // 1000) + 1) * 1000 - y) / 0.5), int((x - int(x // 1000) * 1000) / 0.5)]
        return out
    encontrados = {}
    for v in osm["vias"]:
        t = v["tags"]
        if t.get("highway") not in calles_v.CARRILES or not calles_v._a_nivel(t) or t.get("tunnel") not in (None, "no"):
            continue
        xy = np.asarray(v["xy"], float)
        if len(xy) < 2 or not any((round(float(p[0]), 1), round(float(p[1]), 1)) in extremos for p in (xy[0], xy[-1])):
            continue
        linea = LineString(xy)
        if linea.length > 120:
            continue
        d = np.arange(1, linea.length, 2.0)
        if len(d) < 3:
            continue
        p = np.array([linea.interpolate(x).coords[0] for x in d])
        su, pu = bruto("suelo", p[:, 0], p[:, 1]), bruto("puente", p[:, 0], p[:, 1])
        if (np.isfinite(pu) & (pu - su > 3.0)).mean() >= 0.3:
            encontrados[_clave_via(xy)] = dict(t, bridge="yes", bcn_inferido="1")
    tmp = ruta.with_suffix(f".{config_v.os.getpid()}.tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(dict(version=VERSION_INFERIDOS, vias=encontrados), fh)
    config_v.os.replace(tmp, ruta)
    _INFERIDOS = encontrados
    return encontrados


def vias_puente(osm, caja=None, con_inferidos=True):
    """Vías de OSM que son puente (con su sección), opcionalmente dentro de caja (e0, n0, e1, n1). Con
    con_inferidos, también los puentes sin etiqueta que se ven en el LiDAR (inferidos)."""
    out = []
    extra = inferidos(osm) if con_inferidos else {}
    for v in osm["vias"]:
        t = v["tags"]
        if extra and len(v["xy"]) >= 2 and t.get("bridge") in (None, "no"):
            t = extra.get(_clave_via(v["xy"]), t)
        if t.get("bridge") in (None, "no") or len(v["xy"]) < 2:
            continue
        if t.get("name") == "Pont del Petroli":
            continue  # lo hace monumentos_v
        if t.get("highway") == "footway" and np.hypot(*(np.asarray(v["xy"], float).mean(0) - (436790.4, 4587840.9))) < 5:
            continue  # la pasarela roja sobre las vías junto al Petroli: monumentos_v
        s = seccion(t)
        if s is None:
            continue
        xy = np.asarray(v["xy"], float)
        if caja is not None:
            c = xy.mean(0)
            if not (caja[0] <= c[0] < caja[2] and caja[1] <= c[1] < caja[3]):
                continue
        out.append(dict(xy=xy, tags=t, s=s))
    return out


def extremos_internos(vias, osm=None):
    """Para cada vía, si su inicio / final empalma con otra vía de puente (entonces no apoya en el suelo).
    Con osm: si en ese extremo empieza también una calzada a nivel, el puente sí llega al suelo aunque lo toque
    otro puente (en la Ronda Litoral de Sant Adrià el tronco y el ramal se juntan justo donde la Ronda sigue a
    nivel: el tablero se quedaba a 2 m y las barreras cruzaban la calzada)."""
    cuenta = {}
    for v in vias:
        for p in v["xy"]:
            k = (round(p[0], 1), round(p[1], 1))
            cuenta[k] = cuenta.get(k, 0) + 1
    suelo = set()
    if osm is not None:
        import calles_v
        extra = inferidos(osm)
        for w in osm["vias"]:
            t = w["tags"]
            if t.get("highway") in calles_v.CARRILES and len(w["xy"]) >= 2 and calles_v._a_nivel(t) and                     t.get("tunnel") in (None, "no") and _clave_via(w["xy"]) not in extra:
                for p in (w["xy"][0], w["xy"][-1]):
                    suelo.add((round(float(p[0]), 1), round(float(p[1]), 1)))

    def interno(p):
        k = (round(float(p[0]), 1), round(float(p[1]), 1))
        return cuenta[k] > 1 and k not in suelo
    for v in vias:
        v["internos"] = (interno(v["xy"][0]), interno(v["xy"][-1]))


def _sin_islas(ds, medida, suelo, isla=25.0, hueco_min=20.0, sobre=3.0):
    """Quita las medidas sueltas (menos de isla m) con huecos largos a los dos lados y más de sobre m por encima del
    suelo de los dos bordes: son otro puente que cruza por encima (el LiDAR ve el de arriba), no el tablero propio
    (un vano corto propio tiene el suelo subiendo a su encuentro)."""
    m = medida.copy()
    hay = ~np.isnan(m)
    i, n = 0, len(ds)
    while i < n:
        if not hay[i]:
            i += 1
            continue
        j = i
        while j < n and hay[j]:
            j += 1
        a0 = i - 1
        while a0 >= 0 and not hay[a0]:
            a0 -= 1
        b0 = j
        while b0 < n and not hay[b0]:
            b0 += 1
        hueco_antes = ds[i - 1] - ds[a0 + 1] if i > 0 else 0.0
        hueco_despues = ds[b0 - 1] - ds[j] if j < n else 0.0
        alto = i > 0 and j < n and np.nanmedian(m[i:j]) - max(suelo[i - 1], suelo[j]) > sobre
        if ds[j - 1] - ds[i] < isla and hueco_antes >= hueco_min and hueco_despues >= hueco_min and alto:
            m[i:j] = np.nan
        i = j
    return m


def _tramos_a_ras(ds, medida, suelo, largo_min=30.0):
    """Puntos (d, z) a ras de suelo en los huecos sin tablero medido donde la vía va por el suelo: OSM dice puente
    en todo el tramo, pero el LiDAR solo ve tablero en los vanos de verdad (la C-31 en Badalona va en trinchera
    entre viaductos; al interpolar en línea recta entre los dos vanos quedaba flotando hasta 7 m sobre el suelo y
    se comía el puente del carrer del General Weyler que pasa por encima). Es suelo si en los dos bordes del hueco
    el terreno llega al tablero medido, por dentro no tiene escalones y no se hunde (si se hunde, es un vano tapado
    por otro puente de encima y se interpola como antes)."""
    out = []
    medida = _sin_islas(ds, medida, suelo)
    hueco = np.isnan(medida)
    i, n = 0, len(ds)
    while i < n:
        if not hueco[i]:
            i += 1
            continue
        j = i
        while j < n and hueco[j]:
            j += 1
        if i > 0 and j < n and ds[j - 1] - ds[i] >= largo_min:  # entre dos tramos medidos
            za, zb = medida[i - 1], medida[j]
            # el suelo llega al tablero en los primeros / últimos borde m del hueco (antes aún pasa bajo el vano)
            borde = 12.0
            ini = [k for k in range(i, j) if ds[k] - ds[i] <= borde and abs(suelo[k] - za) < 1.5]
            fin = [k for k in range(i, j) if ds[j - 1] - ds[k] <= borde and abs(suelo[k] - zb) < 1.5]
            if ini and fin and fin[-1] > ini[0]:
                k0, k1 = ini[0], fin[-1] + 1
                dentro = suelo[k0:k1]
                if np.abs(np.diff(dentro)).max(initial=0) < 0.8 and dentro.min() > min(za, zb) - 3.0:
                    out += [(d, zz + 0.05) for d, zz in zip(ds[k0:k1], dentro)]
        i = j
    return out


def perfil(via, relieve, por_suelo=True, encima=None):
    """Eje muestreado: puntos (N, 2), derecha (N, 2), distancia (N), z del tablero (N), suelo (N).
    encima: [(planta, puntos, z, canto)] de los puentes de capa superior que lo cruzan: debajo de ellos el tablero
    va al menos GALIBO_BAJO m por debajo del suyo (el LiDAR solo ve el de arriba: el Ramal Besòs bajo la Ronda
    Litoral salía a la altura de la Ronda, con los pretiles cruzando la calzada)."""
    linea = LineString(via["xy"])
    largo = linea.length
    if largo < 3:
        return None
    ds = np.unique(np.r_[np.arange(0, largo, PASO), [linea.project(Point(p)) for p in via["xy"]], largo])
    ds = ds[np.r_[True, np.diff(ds) > 0.3]]
    ds[-1] = largo
    pts = np.array([linea.interpolate(d).coords[0] for d in ds])
    tan = np.gradient(pts, axis=0)
    tan /= np.linalg.norm(tan, axis=1, keepdims=True) + 1e-9
    der = np.c_[tan[:, 1], -tan[:, 0]]
    suelo = relieve.valor("suelo", pts[:, 0], pts[:, 1])
    if np.isnan(suelo).any():
        return None  # parte del puente fuera de las hojas bajadas
    off = np.linspace(-0.35, 0.35, 5) * via["s"]["ancho"]
    z = relieve.valor("puente", pts[:, 0, None] + der[:, 0, None] * off, pts[:, 1, None] + der[:, 1, None] * off)
    z[~(z > suelo[:, None] + 1.0)] = np.nan
    cuenta = (~np.isnan(z)).sum(1)
    medida = np.where(cuenta >= 2, np.nanmedian(np.where(cuenta[:, None] >= 2, z, 0), axis=1), np.nan)
    # donde otro puente cruza por encima (la B-10 sobre el Ramal Besòs) el LiDAR ve el de arriba: fuera las
    # medidas más de 2,5 m por encima de las más bajas de alrededor (±15 m; una rampa sube mucho menos)
    if (~np.isnan(medida)).sum() >= 3:
        bajo = ndimage.minimum_filter1d(np.where(np.isnan(medida), np.inf, medida), max(int(15 / PASO), 1) * 2 + 1)
        medida[medida > bajo + 2.5] = np.nan
    anclas_d, anclas_z = list(ds[~np.isnan(medida)]), list(medida[~np.isnan(medida)])
    if por_suelo:
        for d, zz in _tramos_a_ras(ds, medida, suelo):
            anclas_d.append(d)
            anclas_z.append(zz)
    for k, interno in zip((0, -1), via["internos"]):
        if not interno and np.isnan(medida[k]):  # estribo: la calzada llega al terreno
            anclas_d.append(ds[k])
            anclas_z.append(suelo[k] + 0.05)
    if not anclas_d:  # ni medida ni estribos: gálibo según la capa
        capa = max(_numero(via["tags"].get("layer"), 1), 1)
        z = ndimage.uniform_filter1d(suelo + 6.5 * capa, 15, mode="nearest")
    else:
        orden = np.argsort(anclas_d)
        z = np.interp(ds, np.asarray(anclas_d)[orden], np.asarray(anclas_z)[orden])
        if len(z) >= 5:  # quita coches y saltos del LiDAR sin mover los extremos
            extremos = z[[0, -1]]
            rapida = via["s"]["tipo"] == "autopista"  # rasante de autopista: curvas verticales de cientos de m
            z = ndimage.median_filter(z, 15 if rapida else 7, mode="nearest")
            z = ndimage.uniform_filter1d(z, 13 if rapida else 5, mode="nearest")
            if rapida:
                z = ndimage.uniform_filter1d(z, 9, mode="nearest")
            z[[0, -1]] = extremos
    # donde OSM dice puente pero la vía va sobre terraplén (el LiDAR no ve tablero), el terreno llega a la
    # rasante: el tablero va justo encima del terreno de todo su ancho, no enterrado
    lados = relieve.valor("suelo", pts[:, 0, None] + der[:, 0, None] * off, pts[:, 1, None] + der[:, 1, None] * off)
    minimo = np.nanmax(lados, axis=1) + 0.12
    if len(z) >= 5 and (minimo > z).any():  # envolvente suave por encima (sin escalones donde manda el terreno)
        minimo = ndimage.uniform_filter1d(ndimage.maximum_filter1d(minimo, 9, mode="nearest"), 9, mode="nearest")
    z = np.maximum(z, minimo)
    if len(z) >= 9 and via["s"]["tipo"] == "autopista":  # sin escalones donde se juntan rasante y terreno
        extremos = z[[0, -1]]
        z = np.maximum(ndimage.uniform_filter1d(z, 11, mode="nearest"), minimo - 0.1)
        z[[0, -1]] = extremos
    if encima:
        import shapely
        techo = np.full(len(z), np.inf)
        puntos = shapely.points(pts)
        for planta, p_o, z_o, canto_o in encima:
            dentro = shapely.contains(planta, puntos)
            for i in np.flatnonzero(dentro):
                k = np.argmin(((p_o - pts[i]) ** 2).sum(1))
                techo[i] = min(techo[i], z_o[k] - canto_o - GALIBO_BAJO)
        if np.isfinite(techo).any():  # rampa del 8 % hasta el tramo de debajo, sin escalones
            env = (np.where(np.isfinite(techo), techo, 1e6)[None, :] + 0.08 * np.abs(ds[:, None] - ds[None, :])).min(1)
            z = np.minimum(z, env)
    # estribos: el tablero acaba justo a la altura del asfalto de la calle a la que llega (suelo + SUBE de calles_v)
    # y se acerca a ella en LLEGADA m sin escalón; la envolvente del terreno de los lados lo subía hasta 0,6 m y
    # quedaba un bordillo de tablero en mitad de la calzada (marcas 191029 y 182625)
    for k, interno in zip((0, -1), via["internos"]):
        if interno or not np.isnan(medida[k]):
            continue
        # el suelo de la calle 3 m más allá del extremo (en el propio extremo el terreno corregido puede ser el
        # hoyo de debajo del tablero: en Carrer Argentina quedaba 4,9 m por debajo de la calle)
        fuera = pts[0] - (pts[1] - pts[0]) if k == 0 else pts[-1] + (pts[-1] - pts[-2])
        t_ = fuera - pts[k]
        q = pts[k] + t_ / (np.linalg.norm(t_) + 1e-9) * 3.0
        s_fuera = float(relieve.valor("suelo", q[0], q[1]))
        objetivo = (s_fuera if np.isfinite(s_fuera) else suelo[k]) + ASFALTO
        lejos = ds - ds[0] if k == 0 else ds[-1] - ds
        peso = np.clip(lejos / LLEGADA, 0.0, 1.0)
        peso = peso * peso * (3 - 2 * peso)  # suave en los dos lados
        cerca = lejos < LLEGADA
        z[cerca] = objetivo + (z[cerca] - objetivo) * peso[cerca]
    return pts, der, ds, z, suelo


def plantas_bajas(vias, caja, alto=2.5):
    """Planta (UTM) de los tramos de tablero de calzada que van a menos de alto m del suelo, dentro de caja: ahí
    no puede haber además calle a nivel ni terreno a la vista (se cruzaban con el tablero: saltos, parpadeo y el
    tablero 'fundido' con el terreno). Necesita los perfiles hechos (perfiles())."""
    import shapely
    from shapely.geometry import box
    zona = box(*caja)
    trozos = []
    for via in vias:
        r = _PERFILES.get(id(via))
        if r is None or via["s"]["tipo"] not in ("autopista", "calle"):
            continue
        pts, der, ds, z, suelo = r
        if pts[:, 0].max() < caja[0] - 30 or pts[:, 0].min() > caja[2] + 30 or pts[:, 1].max() < caja[1] - 30 or                 pts[:, 1].min() > caja[3] + 30:
            continue
        bajo = z - suelo < alto
        if not bajo.any():
            continue
        w = via["s"]["ancho"] / 2
        lab, n = ndimage.label(bajo)
        for k in range(1, n + 1):
            idx = np.flatnonzero(lab == k)
            i0, i1 = max(idx[0] - 1, 0), min(idx[-1] + 1, len(pts) - 1)
            if i1 <= i0:
                continue
            trozos.append(LineString(pts[i0:i1 + 1]).buffer(w, cap_style="flat"))
    if not trozos:
        return None
    g = shapely.union_all(trozos).intersection(zona.buffer(5))
    return None if g.is_empty else g


class Obra:
    """Acumula la geometría de los puentes de una casilla en una Malla (coordenadas locales)."""

    def __init__(self, centro):
        self.m = fachadas_v.Malla()
        self.c = np.asarray(centro, float)

    def cara(self, tex, p, uv, hacia):
        """Quad orientado para que su cara vista mire hacia 'hacia'."""
        p = [np.asarray(q, float) for q in p]
        normal = np.cross(p[1] - p[0], p[2] - p[0])
        if np.linalg.norm(normal) < 1e-9:
            normal = np.cross(p[2] - p[0], p[3] - p[0])
        if np.dot(normal, hacia) < 0:
            p, uv, normal = [p[1], p[0], p[3], p[2]], [uv[1], uv[0], uv[3], uv[2]], -normal
        self.m.quad(tex, p, normal / (np.linalg.norm(normal) + 1e-12), uv, (255, 255, 255, 255))

    def punto(self, eje, i, o, h):
        pts, der, _, z = eje
        return np.array([pts[i, 0] + der[i, 0] * o - self.c[0], pts[i, 1] + der[i, 1] * o - self.c[1], z[i] + h])

    def extruir(self, eje, tex, perfil, lados=None, escala=2.0, rango=None, quitar=None):
        """Perfil antihorario [(o, h)] (o hacia la derecha, h hacia arriba) a lo largo del eje.
        lados: índices de los lados a emitir (por defecto todos, cerrando el polígono).
        quitar: máscara por tramo (len(ds) - 1) de los tramos que no se emiten."""
        pts, der, ds, z = eje
        n = len(perfil)
        lados = range(n) if lados is None else lados
        i0, i1 = rango or (0, len(ds) - 1)
        for k in lados:
            (oa, ha), (ob, hb) = perfil[k], perfil[(k + 1) % n]
            no, nh = hb - ha, -(ob - oa)
            u0, u1 = 0.0, np.hypot(ob - oa, hb - ha) / escala
            for i in range(i0, i1):
                if quitar is not None and quitar[i]:
                    continue
                hacia = np.r_[der[i] * no, nh]
                v0, v1 = ds[i] / escala, ds[i + 1] / escala
                self.cara(tex, [self.punto(eje, i, oa, ha), self.punto(eje, i, ob, hb),
                                self.punto(eje, i + 1, ob, hb), self.punto(eje, i + 1, oa, ha)],
                          [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], hacia)

    def banda(self, eje, tex, o0, o1, h=0.0, escala_u=4.0, escala_v=4.0, u_desde=None):
        """Superficie horizontal entre las distancias laterales o0 < o1 (mirando arriba)."""
        pts, der, ds, z = eje
        ua = ((o0 if u_desde is None else o0 - u_desde) / escala_u)
        ub = ua + (o1 - o0) / escala_u
        for i in range(len(ds) - 1):
            v0, v1 = ds[i] / escala_v, ds[i + 1] / escala_v
            self.cara(tex, [self.punto(eje, i, o0, h), self.punto(eje, i, o1, h),
                            self.punto(eje, i + 1, o1, h), self.punto(eje, i + 1, o0, h)],
                      [(ua, v0), (ub, v0), (ub, v1), (ua, v1)], np.array([0, 0, 1.0]))

    def linea(self, eje, o, ancho, discontinua):
        self.banda(eje, "vi_linea_disc" if discontinua else "vi_linea", o - ancho / 2, o + ancho / 2, 0.012,
                   escala_u=ancho, escala_v=12.5 if discontinua else 4.0)

    def caja(self, centro, eje_x, ax, ay, z0, z1, tex="vi_hormigon"):
        """Prisma vertical (pila) de ax x ay m con el lado ax según eje_x (2D)."""
        ex = np.r_[eje_x / np.linalg.norm(eje_x), 0.0]
        ey = np.array([-ex[1], ex[0], 0.0])
        base = np.r_[centro - self.c, 0.0]
        esquinas = [base + ex * sx * ax / 2 + ey * sy * ay / 2 for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        for k in range(4):
            a, b = esquinas[k], esquinas[(k + 1) % 4]
            largo = np.linalg.norm(b - a)
            fuera = (a + b) / 2 - base
            self.cara(tex, [a + [0, 0, z0], b + [0, 0, z0], b + [0, 0, z1], a + [0, 0, z1]],
                      [(0, z0 / 2), (largo / 2, z0 / 2), (largo / 2, z1 / 2), (0, z1 / 2)], fuera)


def _tablero(obra, eje, s):
    w = s["ancho"]
    canto = s["canto"]
    if s["tipo"] == "autopista":  # cajón central con voladizos
        borde, caj = 0.45, 0.28 * w
        seccion_ = [(w / 2, 0), (-w / 2, 0), (-w / 2, -borde), (-caj, -canto), (caj, -canto), (w / 2, -borde)]
    else:
        seccion_ = [(w / 2, 0), (-w / 2, 0), (-w / 2, -canto), (w / 2, -canto)]
    obra.extruir(eje, "vi_hormigon", seccion_, lados=range(1, len(seccion_)))


def _barreras(obra, eje, s, otras=None):
    """otras: función (xy (N, 2), fuera (N, 2), z (N)) -> máscara de los tramos de barrera que sobran: los que
    caen en el tablero de otra vía o los que tienen justo por fuera más calzada a su altura (otro tablero al lado
    o la calle a nivel donde el puente arranca del suelo; salían New Jersey cruzando los carriles)."""
    w = s["ancho"] / 2
    for lado in (-1, 1):  # perfil desde el borde exterior hacia dentro, a la izquierda (-1) o derecha (+1)
        quitar = None
        if otras is not None and s["barrera"] in ("jersey", "pretil"):
            pts, der, ds, z = eje
            m_pts, m_der = (pts[:-1] + pts[1:]) / 2, (der[:-1] + der[1:]) / 2
            quitar = otras(m_pts + m_der * lado * (w - 0.3), m_pts + m_der * lado * (w + 0.8), (z[:-1] + z[1:]) / 2)
            if quitar.any():  # sin trocitos de barrera sueltos
                quitar = ndimage.binary_closing(quitar, iterations=2) | quitar
                trozos, n = ndimage.label(~quitar)  # y los cachitos de menos de 6 m que quedan en las puntas
                for k in range(1, n + 1):
                    if (trozos == k).sum() * PASO < 6.0:
                        quitar[trozos == k] = True
        if s["barrera"] == "jersey":
            hacia_dentro = [(0, 0.81), (0.15, 0.81), (0.23, 0.33), (0.38, 0.08), (0.6, 0.0)]
            frente = [(0.0, 0.0)] + hacia_dentro
        elif s["barrera"] == "pretil":
            frente = [(0.0, 0.0), (0.0, 1.05), (0.3, 1.05), (0.3, 0.0)]
        else:
            frente = [(0.0, 0.0), (0.0, 0.25), (0.25, 0.25), (0.25, 0.0)]
        perfil_ = [(lado * (w - d), h) for d, h in frente]
        if lado < 0:  # antihorario visto con o a la derecha
            perfil_ = perfil_[::-1]
        n = len(perfil_)
        lados = [k for k in range(n) if not (perfil_[k][1] == 0 and perfil_[(k + 1) % n][1] == 0)]
        obra.extruir(eje, "vi_hormigon", perfil_, lados=lados, escala=2.0, quitar=quitar)
        if s["barrera"] == "barandilla":  # barandilla metálica sobre el murete (dos caras, con alfa)
            o = lado * (w - 0.12)
            pts, der, ds, z = eje
            for i in range(len(ds) - 1):
                p = [obra.punto(eje, i, o, 0.25), obra.punto(eje, i + 1, o, 0.25),
                     obra.punto(eje, i + 1, o, 1.1), obra.punto(eje, i, o, 1.1)]
                uv = [(ds[i] / 2, 0), (ds[i + 1] / 2, 0), (ds[i + 1] / 2, 1), (ds[i] / 2, 1)]
                for signo in (1, -1):
                    obra.cara("vi_barandilla_alfa", p, uv, np.r_[der[i] * signo, 0])


def _calzada(obra, eje, s):
    w = s["ancho"] / 2
    if s["tipo"] == "autopista":
        dentro = 0.6  # pie de la New Jersey
        obra.banda(eje, "vi_asfalto", -w + dentro, w - dentro)
        izq, der = -w + s["arcen_izq"], w - s["arcen_der"]
        obra.linea(eje, izq + 0.08, 0.15, False)
        obra.linea(eje, der - 0.15, 0.30, False)
        for k in range(1, s["carriles"]):
            o = izq + k * (der - izq) / s["carriles"]
            centro = s["doble_sentido"] and k == s["carriles"] // 2
            obra.linea(eje, o, 0.15, not centro)
    elif s["tipo"] == "calle":
        a = s["acera"]
        obra.banda(eje, "vi_asfalto", -w + a, w - a)
        for lado in (-1, 1):  # acera elevada 15 cm con su bordillo
            o0, o1 = sorted((lado * (w - 0.3), lado * (w - a)))
            obra.banda(eje, "vi_acera", o0, o1, 0.15, escala_u=2.0, escala_v=2.0)
            bord = lado * (w - a)
            perfil_ = [(bord, 0.0), (bord, 0.15)] if lado < 0 else [(bord, 0.15), (bord, 0.0)]
            obra.extruir(eje, "vi_hormigon", perfil_ + [(bord - lado * 0.01, 0.0)], lados=[0], escala=2.0)
        izq, der = -w + a, w - a
        for k in range(1, s["carriles"]):
            o = izq + k * (der - izq) / s["carriles"]
            obra.linea(eje, o, 0.12, not (s["doble_sentido"] and k == s["carriles"] // 2))
    elif s["tipo"] == "tren":
        obra.banda(eje, "vi_balasto", -w + 0.3, w - 0.3, 0.0, escala_u=w * 2 - 0.6, escala_v=3.0, u_desde=-w + 0.3)
        for o in (-0.72, 0.72):  # carriles UIC 54 de ancho ibérico/internacional (aprox.)
            perfil_ = [(o + 0.035, 0.24), (o - 0.035, 0.24), (o - 0.07, 0.06), (o + 0.07, 0.06)]
            obra.extruir(eje, "vi_hierro", perfil_, lados=[0, 1, 3], escala=1.0)
    else:
        obra.banda(eje, "vi_acera", -w + 0.25, w - 0.25, 0.0, escala_u=2.0, escala_v=2.0)


def _pilas(obra, eje, suelo, s, calles, caja=None):
    pts, der, ds, z = eje
    largo = ds[-1]
    if largo < 2 * ENTRE_PILAS * 0.6:
        return []
    n = max(1, int(round(largo / ENTRE_PILAS)) - 1)
    puestas = []
    for k in range(1, n + 1):
        d = k * largo / (n + 1)
        for desp in (0, 6, -6, 12, -12):
            i = int(np.clip(np.searchsorted(ds, d + desp), 1, len(ds) - 1))
            centro = pts[i]
            if calles is None or not len(calles.query(Point(*centro).buffer(5.0), predicate="intersects")):
                break
        else:
            continue
        if caja is not None and not (caja[0] <= centro[0] < caja[2] and caja[1] <= centro[1] < caja[3]):
            continue  # la pone la casilla vecina
        techo = z[i] - s["canto"] + 0.05
        if techo - suelo[i] < 3.0:
            continue
        tan = np.array([-der[i, 1], der[i, 0]])
        if s["ancho"] > 11:
            lat = [-0.22 * s["ancho"], 0.22 * s["ancho"]]
            ax, ay = 1.3, 1.6
        else:
            lat = [0.0]
            ax, ay = 1.4, min(2.6, 0.3 * s["ancho"] + 0.6)
        for o in lat:
            c = centro + der[i] * o
            obra.caja(c, tan, ax, ay, suelo[i] - 0.5, techo)
            obra.caja(c, tan, ax + 0.6, ay + 1.2, techo - 0.9, techo)  # capitel
        puestas.append(centro)
    return puestas


_PERFILES = {}


def tramos(pts, caja):
    """Rangos [i0, i1] de muestras consecutivas del eje cuyos segmentos caen en la caja (por su punto medio)."""
    medio = (pts[:-1] + pts[1:]) / 2
    dentro = (medio[:, 0] >= caja[0]) & (medio[:, 0] < caja[2]) & (medio[:, 1] >= caja[1]) & (medio[:, 1] < caja[3])
    out, k = [], 0
    while k < len(dentro):
        if dentro[k]:
            j = k
            while j + 1 < len(dentro) and dentro[j + 1]:
                j += 1
            out.append((k, j + 1))
            k = j + 1
        else:
            k += 1
    return out


def cerca(vias, caja, margen=600.0):
    """Las vías puente con algún punto a menos de margen m de la caja (e0, n0, e1, n1): las que pueden tocar la hoja
    o pasar por encima de alguna que la toca. Calcular los perfiles de todas cargaría el LiDAR de todo el mapa."""
    out = []
    for v in vias:
        xy = v["xy"]
        if xy[:, 0].max() >= caja[0] - margen and xy[:, 0].min() < caja[2] + margen and                 xy[:, 1].max() >= caja[1] - margen and xy[:, 1].min() < caja[3] + margen:
            out.append(v)
    return out


def perfiles(vias, relieve):
    """Perfil de cada vía (en _PERFILES, por id) con los puentes de capa más alta que la cruzan por encima: primero
    los de arriba, que los de debajo miran. Lo usan construir y las farolas de mobiliario_v (mismo tablero)."""
    capa = {id(v): _numero(v["tags"].get("layer"), 1) for v in vias}
    for via in sorted(vias, key=lambda v: -capa[id(v)]):
        clave = id(via)
        if clave not in _PERFILES:
            encima = []
            linea = LineString(via["xy"])
            for otra in vias:
                r = _PERFILES.get(id(otra))
                if capa[id(otra)] > capa[clave] and r is not None and otra["s"]["tipo"] != "pasarela":
                    planta = LineString(r[0]).buffer(otra["s"]["ancho"] / 2 + 1.0, cap_style="flat")
                    if planta.intersects(linea):
                        encima.append((planta, r[0], r[3], otra["s"]["canto"]))
            _PERFILES[clave] = perfil(via, relieve, encima=encima)
    return [_PERFILES[id(v)] for v in vias]


def construir(vias, relieve, calles, centro, caja=None, a_nivel=None):
    """vias: de vias_puente (con 'internos'); calles: STRtree de calles a nivel (o None); a_nivel: [(LineString,
    ancho)] de las calzadas a nivel cercanas (para quitar las barreras donde la calle sigue al lado del puente);
    centro: UTM del centro de la casilla; caja (e0, n0, e1, n1): solo el trozo de cada puente que cae
    dentro (un viaducto largo se reparte entre las casillas que cruza, para que cada trozo cambie de
    detalle con su casilla y no se corte). Devuelve (arrays por textura, (v, tris, mats) o None, n_puentes)."""
    obra = Obra(centro)
    hechos = 0
    # el perfil se calcula con el puente entero, una vez; primero los de capa más alta (los de debajo los miran)
    perfiles(vias, relieve)
    # tableros de todas las vías, para que las barreras no se metan en el de al lado
    import shapely
    tableros, enteros, alturas = [], [], []
    for via in vias:
        r = _PERFILES[id(via)]
        if r is not None and via["s"]["tipo"] in ("autopista", "calle"):
            tableros.append(LineString(r[0]).buffer(via["s"]["ancho"] / 2 - 0.4, cap_style="flat"))
            enteros.append(LineString(r[0]).buffer(via["s"]["ancho"] / 2, cap_style="flat"))
            alturas.append((r[0], r[3], via))
    arbol = shapely.STRtree(tableros) if tableros else None
    arbol_e = shapely.STRtree(enteros) if enteros else None
    calzadas = [l.buffer(w / 2, cap_style="flat") for l, w in (a_nivel or []) if l.length > 0]
    arbol_n = shapely.STRtree(calzadas) if calzadas else None

    def otras_de(propia):
        def z_de(b, xy):
            p_o, z_o, _ = alturas[b]
            return z_o[np.argmin(((p_o - xy) ** 2).sum(1))]

        def otras(xy, fuera_xy, z):
            quitar = np.zeros(len(xy), bool)
            # a ras de suelo (menos de 1 m sobre el terreno) se mira más lejos: entre dos tableros bajos con 1-3 m
            # de terreno en medio tampoco hace falta barrera (OSM parte una calzada sola en tronco y ramal)
            hacia = (fuera_xy - xy) / (np.linalg.norm(fuera_xy - xy, axis=1, keepdims=True) + 1e-9)
            bajo = z - relieve.valor("suelo", xy[:, 0], xy[:, 1]) < 1.0
            lejos_xy = np.where(bajo[:, None], xy + hacia * 3.3, fuera_xy)
            if arbol is not None:  # la barrera cae en el tablero de otra vía
                ip, it = arbol.query(shapely.points(xy), predicate="within")
                for a, b in zip(ip, it):
                    if alturas[b][2] is not propia and not quitar[a]:
                        quitar[a] = abs(z_de(b, xy[a]) - z[a]) < 1.5
            if arbol_e is not None:  # justo por fuera, otro tablero a la misma altura: es la misma calzada
                for punto in (fuera_xy, lejos_xy):
                    ip, it = arbol_e.query(shapely.points(punto), predicate="within")
                    for a, b in zip(ip, it):
                        if alturas[b][2] is not propia and not quitar[a]:
                            quitar[a] = abs(z_de(b, punto[a]) - z[a]) < 0.6
            if arbol_n is not None:  # justo por fuera, la calle a nivel a la altura del tablero
                ip = np.unique(arbol_n.query(shapely.points(fuera_xy), predicate="within")[0])
                if len(ip):
                    zs = relieve.valor("suelo", fuera_xy[ip, 0], fuera_xy[ip, 1])
                    quitar[ip] |= np.abs(z[ip] - zs) < 0.6
            return quitar
        return otras if (arbol is not None or arbol_n is not None) else None

    for via in vias:
        r = _PERFILES[id(via)]
        if r is None:
            continue
        pts, der, ds, z, suelo = r
        s = via["s"]
        if via["tags"].get("highway") in ENLACES:  # el enlace, 4 cm por debajo del tronco donde se solapan
            z = z - 0.04
        rangos = [(0, len(ds) - 1)] if caja is None else tramos(pts, caja)
        otras = otras_de(via)
        for i0, i1 in rangos:
            sl = slice(i0, i1 + 1)
            eje = (pts[sl], der[sl], ds[sl], z[sl])
            _tablero(obra, eje, s)
            _calzada(obra, eje, s)
            _barreras(obra, eje, s, otras)
        if rangos:
            _pilas(obra, (pts, der, ds, z), suelo, s, calles, caja)
            hechos += 1
    arrays = obra.m.arrays()
    v, t, mats = [], [], []
    for tex, g in arrays.items():
        if tex.startswith("vi_linea") or tex.endswith("_alfa"):
            continue
        base = sum(len(x) for x in v)
        v.append(g["v"])
        t.append(g["i"] + base)
        mat = rage.MAT_TARMAC if tex == "vi_asfalto" else (rage.MAT_PAVING if tex == "vi_acera" else (
            rage.MAT_STONE if tex == "vi_balasto" else rage.MAT_CONCRETE))
        mats.append(np.full(len(g["i"]), mat))
    colision = None
    if v:
        colision = (np.concatenate(v), np.concatenate(t), np.concatenate(mats))
    return arrays, colision, hechos


# --------------------------------------------------------------------------- texturas

def texturas():
    """Texturas de obra (diccionario bcn_obra): {nombre: (imagen, alfa)}."""
    T, rng = 512, np.random.default_rng(31)
    ruido = texturas_fachada.ruido
    asf = np.full((T, T, 3), (74, 74, 76), np.float32)
    asf += ruido(T, 64, 6)[..., None] + ruido(T, 4, 7)[..., None]
    asf += rng.normal(0, 9, (T, T))[..., None]
    piedras = rng.random((T, T)) > 0.985  # árido claro
    asf[piedras] += 40
    out = {"vi_asfalto": asf}
    lin = np.full((256, 64, 3), (226, 226, 220), np.float32) + ruido(256, 8, 6)[:, :64, None]
    lin -= (rng.random((256, 64)) > 0.9)[..., None] * 35  # desgaste
    out["vi_linea"] = lin
    disc = np.repeat(np.repeat(asf[:32, :32].mean((0, 1))[None, None], 1024, 0), 32, 1).copy()
    disc += rng.normal(0, 8, (1024, 32))[..., None]
    trazo = int(1024 * 3.5 / 12.5)
    disc[:trazo] = lin[:1].mean() + rng.normal(0, 5, (trazo, 32))[..., None]
    out["vi_linea_disc"] = disc
    out["vi_hormigon"] = texturas_fachada.hormigon()
    # panot de Barcelona: losetas de 20 cm con cuatro pastillas (512 px = 2 m)
    acera = Image.new("RGB", (T, T), (150, 148, 144))
    d = ImageDraw.Draw(acera)
    lado = T // 10
    for y in range(0, T, lado):
        for x in range(0, T, lado):
            g = int(rng.normal(176, 6))
            d.rectangle([x + 1, y + 1, x + lado - 2, y + lado - 2], fill=(g, g - 2, g - 6))
            for cx in (0.3, 0.7):
                for cy in (0.3, 0.7):
                    r = lado * 0.13
                    d.ellipse([x + lado * cx - r, y + lado * cy - r, x + lado * cx + r, y + lado * cy + r],
                              fill=(g - 22, g - 24, g - 28))
    out["vi_acera"] = np.asarray(acera, np.float32) + ruido(T, 32, 8)[..., None]
    # balasto con traviesas cada 0,6 m (u: ancho de la vía, v: 3 m = 5 traviesas)
    bal = np.full((T, T, 3), (122, 114, 104), np.float32) + rng.normal(0, 22, (T, T))[..., None]
    bal += ruido(T, 3, 14)[..., None]
    ancho_u = 2.6 / 4.0
    u0, u1 = int(T * (0.5 - ancho_u / 2)), int(T * (0.5 + ancho_u / 2))
    for k in range(5):
        y = int((k + 0.5) * T / 5)
        bal[y - 13:y + 13, u0:u1] = (138, 134, 128)
        bal[y - 13:y + 13, u0:u1] += rng.normal(0, 6, (26, u1 - u0))[..., None]
    out["vi_balasto"] = bal
    out["vi_hierro"] = np.full((64, 64, 3), (92, 84, 78), np.float32) + rng.normal(0, 8, (64, 64))[..., None]
    bar = np.zeros((128, 512, 4), np.float32)
    bar[:, :, :3] = 48
    bar[:10, :, 3] = bar[-6:, :, 3] = 255
    for x in range(0, 512, 32):
        bar[:, x:x + 5, 3] = 255
    out["vi_barandilla_alfa"] = bar
    # aparcamiento: asfalto más gastado y claro, con manchas de aceite
    ap = asf * 0.95 + 14 + ruido(T, 16, 8)[..., None]
    manchas = ruido(T, 48, 1)[..., None] > 0.55
    out["vi_aparcamiento"] = np.where(manchas, ap - 18, ap)
    # bordillo de granito: gris claro con grano (u: 2 m de largo, v: los 13 cm de alto)
    bo = np.full((64, 256, 3), (168, 166, 160), np.float32) + rng.normal(0, 14, (64, 256))[..., None]
    bo[:, ::64] -= 30  # juntas entre piezas de 50 cm
    out["vi_bordillo"] = bo
    # alcorque: tierra con hojas dentro de un marco de hormigón (la textura es el cuadro entero de 1,2 m)
    al = np.full((256, 256, 3), (96, 74, 54), np.float32) + rng.normal(0, 16, (256, 256))[..., None]
    al += ruido(256, 12, 10)[..., None]
    hojas = rng.random((256, 256)) > 0.97
    al[hojas] = (118, 98, 52)
    marco = 22  # ~10 cm de bordillo de hormigón
    al[:marco], al[-marco:], al[:, :marco], al[:, -marco:] = 168, 168, 168, 168
    out["vi_alcorque"] = al
    # tapa de registro de fundición de 80 cm: círculo con dibujo de rombos sobre su marco cuadrado
    T2 = 256
    yy, xx = np.mgrid[:T2, :T2] - T2 / 2 + 0.5
    r = np.hypot(xx, yy) / (T2 / 2)
    tapa = np.full((T2, T2, 3), (80, 80, 82), np.float32) + rng.normal(0, 6, (T2, T2))[..., None]
    rombo = ((np.abs((xx + yy) % 16) < 3) | (np.abs((xx - yy) % 16) < 3)) & (r < 0.86)
    tapa[rombo] += 26
    tapa[(r > 0.86) & (r < 0.93)] = (52, 50, 50)  # junta
    tapa[(r >= 0.93) & (r < 0.99)] = (96, 94, 92)  # aro del marco
    tapa[r >= 0.99] = (74, 74, 76)  # fuera del aro, asfalto: que no se vea el cuadrado
    out["vi_tapa"] = tapa
    # boca de metro: escalones que bajan hacia la oscuridad (v = 0 arriba, 1 al fondo), con zócalo de granito
    esc = np.zeros((512, 128, 3), np.float32)
    for k in range(16):
        y0, y1 = k * 32, (k + 1) * 32
        luz = 1.0 - k / 18
        esc[y0:y1] = np.array([150, 146, 140]) * luz
        esc[y0:y0 + 5] = np.array([196, 190, 182]) * luz  # canto del escalón (más claro)
        esc[y1 - 6:y1] = np.array([70, 68, 66]) * luz  # sombra de la contrahuella
    esc += rng.normal(0, 5, esc.shape[:2])[..., None]
    esc[:, :10] = esc[:, -10:] = (120, 118, 114)
    out["vi_metro_esc"] = esc
    # rombo rojo con la M blanca (el cartel de las bocas de metro)
    T3 = 256
    yy, xx = np.mgrid[:T3, :T3] - T3 / 2 + 0.5
    mm = np.zeros((T3, T3, 4), np.float32)
    rombo_m = (np.abs(xx) + np.abs(yy)) < T3 * 0.47
    mm[rombo_m] = (214, 18, 32, 255)
    img_m = Image.fromarray(mm.astype(np.uint8), "RGBA")
    dm = ImageDraw.Draw(img_m)
    a, b, g_ = 0.30 * T3, 0.70 * T3, int(T3 * 0.07)
    trazo_m = [(a, b), (a, 0.32 * T3), (T3 / 2, 0.56 * T3), (b, 0.32 * T3), (b, b)]
    dm.line(trazo_m, fill=(255, 255, 255, 255), width=g_, joint="curve")
    out["vi_metro_m_alfa"] = np.asarray(img_m).astype(np.float32)
    # túnel: hastial de paneles claros (3 m de largo por textura) con zócalo oscuro y franja reflectante
    tu = np.full((256, 256, 3), (176, 172, 160), np.float32) + rng.normal(0, 6, (256, 256))[..., None]
    tu += ruido(256, 32, 6)[..., None]
    tu[:, ::85] -= 30  # juntas entre paneles
    tu[200:] = np.array([70, 68, 64]) + rng.normal(0, 8, (56, 256))[..., None]  # zócalo con suciedad
    tu[188:194] = (210, 190, 60)
    out["vi_tunel"] = tu
    te = np.full((128, 128, 3), (58, 58, 60), np.float32) + rng.normal(0, 6, (128, 128))[..., None]
    out["vi_tunel_techo"] = te
    out["vi_luz"] = np.full((32, 32, 3), (255, 244, 214), np.float32)
    out["vi_baliza"] = np.full((64, 64, 3), (230, 30, 24), np.float32)  # torre de referencia de las pruebas
    # andenes: baldosa gris clara de 40 cm (256 px = 2 m), línea amarilla de seguridad y chapa de marquesina
    an = np.full((256, 256, 3), (168, 166, 160), np.float32) + rng.normal(0, 6, (256, 256))[..., None]
    an += ruido(256, 24, 6)[..., None]
    an[::51] -= 30
    an[:, ::51] -= 30
    out["vi_anden"] = an
    out["vi_amarillo"] = np.full((32, 32, 3), (226, 188, 40), np.float32) + rng.normal(0, 8, (32, 32))[..., None]
    cu = np.full((256, 256, 3), (196, 198, 200), np.float32) + rng.normal(0, 4, (256, 256))[..., None]
    cu[:, ::32] -= 26  # grecas de la chapa cada 0,5 m
    out["vi_cubierta"] = cu
    # bocas de metro en 3D (bocas_v): peldaño de granito con canto antideslizante (u a lo ancho, v = 1 peldaño),
    # azulejo blanco de 15 cm con la franja roja de TMB (v = 0 arriba, 1 en el suelo: 3 m) y suelo de terrazo
    pe = np.full((128, 128, 3), (172, 168, 160), np.float32) + rng.normal(0, 7, (128, 128))[..., None]
    pe += ruido(128, 16, 5)[..., None]
    pe[:14] = np.array([64, 62, 60]) + rng.normal(0, 5, (14, 128))[..., None]  # banda antideslizante del canto
    out["vi_metro_peldano"] = pe
    az = np.full((512, 256, 3), (232, 232, 226), np.float32) + rng.normal(0, 3, (512, 256))[..., None]
    az[::26] = (196, 196, 190)  # juntas (26 px = 15 cm con 3 m en 512 px)
    az[:, ::26] = (196, 196, 190)
    az[300:322] = (200, 28, 38)  # franja roja a 1,2 m del suelo
    az[440:] = np.array([84, 82, 80]) + rng.normal(0, 5, (72, 256))[..., None]  # zócalo de granito oscuro
    out["vi_metro_azulejo"] = az
    su = np.full((256, 256, 3), (150, 148, 144), np.float32) + rng.normal(0, 9, (256, 256))[..., None]
    su += ruido(256, 8, 8)[..., None]
    su[::64] -= 22
    su[:, ::64] -= 22
    out["vi_metro_suelo"] = su
    res = {}
    for k, a in out.items():
        modo = "RGBA" if a.shape[2] == 4 else "RGB"
        res[k] = (Image.fromarray(a.clip(0, 255).astype(np.uint8), modo), modo == "RGBA")
    return res
