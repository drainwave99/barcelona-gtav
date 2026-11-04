"""Túneles de carretera (Rondas de Dalt, Litoral y del Mig, Glòries, la Rovira...) bajo el terreno.

Trazado y sección: OpenStreetMap (tunnel=*, de 120 m o más; los más cortos los dibuja calles_v a nivel).
Altura: la de las bocas, donde la vía sale al aire (el fondo de la trinchera en el LiDAR); por dentro, la
interpolación a lo largo de la cadena de túneles (una boca puede estar a kilómetros de la otra).
Tubo: calzada con sus marcas, hastiales y techo de hormigón con luces cada 12 m. Colisión de suelo, paredes y
techo. El terreno que se mete en el tubo (la pared de la boca, una cubierta fina) se quita: fuera(...).

preparar(osm, relieve) -> lista de túneles con su perfil
construir(tuneles, centro, caja) -> (arrays por textura, colisión, n)
fuera(v, tris, tuneles) -> máscara de los triángulos del terreno que se quedan
"""
from pathlib import Path

import numpy as np
import shapely
from scipy import ndimage
from shapely.geometry import LineString

import calles_v
import puentes_v
import rage

LARGO_MIN = 120.0
GALIBO = 5.6  # altura libre del tubo (m)


def _clave(p):
    return (round(float(p[0]), 1), round(float(p[1]), 1))


def preparar_cacheado(osm, relieve):
    """preparar() de toda la red, guardado en datos_v/tuneles.pkl (lo comparten todas las hojas)."""
    import pickle
    import config_v
    ruta = config_v.DATOS / "tuneles.pkl"
    fuentes = [config_v.DATOS / "osm.pkl", Path(__file__)] +         list((config_v.DATOS / "lidar" / "hojas").glob("*.npz"))  # una hoja nueva puede medir otra boca
    if ruta.exists() and all(ruta.stat().st_mtime > f.stat().st_mtime for f in fuentes) and             ruta.stat().st_mtime > puentes_v.VERSION_CORRECCION:
        with open(ruta, "rb") as fh:
            return pickle.load(fh)
    tuneles = preparar(osm, relieve)
    tmp = ruta.with_suffix(f".{config_v.os.getpid()}.tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(tuneles, fh)
    config_v.os.replace(tmp, ruta)
    return tuneles


def _bajo_tierra(xy, relieve, cubierta=3.5):
    """Túnel corto bajo tierra de verdad (la Ronda Litoral bajo la plaça de Monterrey, 68 m): el suelo de encima,
    en la mitad central, está más de 'cubierta' m por encima de las dos bocas. Los cortos bajo un viaducto o un
    edificio (Sant Roc, bajo la C-31) tienen encima el suelo a la cota de la calle y siguen a nivel."""
    linea = LineString(xy)
    L = linea.length
    medio = np.array([linea.interpolate(d).coords[0] for d in np.linspace(0.3 * L, 0.7 * L, 9)])
    arriba = relieve.valor("suelo", medio[:, 0], medio[:, 1])
    bocas = []
    for extremo, interior in ((0, 1), (-1, -2)):
        p, q = xy[extremo], xy[interior]
        fuera_dir = (p - q) / (np.linalg.norm(p - q) + 1e-9)
        m = np.array([p + fuera_dir * d for d in (2.0, 6.0, 10.0)])
        bocas.append(relieve.valor("suelo", m[:, 0], m[:, 1]))
    bocas = np.concatenate(bocas)
    if not np.isfinite(arriba).sum() >= 5 or not np.isfinite(bocas).any():
        return False
    return float(np.nanmedian(arriba)) > float(np.nanmax(bocas)) + cubierta


def preparar(osm, relieve, caja=None):
    """Túneles de coche de OSM con su eje muestreado y la z de la calzada."""
    tuneles, nodos_fuera = [], set()
    for v in osm["vias"]:
        t = v["tags"]
        if t.get("highway") not in calles_v.CARRILES or len(v["xy"]) < 2:
            continue
        xy = np.asarray(v["xy"], float)
        if t.get("tunnel") in (None, "no"):
            nodos_fuera.update(_clave(p) for p in (xy[0], xy[-1]))
            continue
        if t.get("tunnel") == "building_passage" or t.get("highway") == "service":
            continue  # pasajes bajo edificios y rampas de aparcamientos subterráneos
        if caja is not None and (xy[:, 0].max() < caja[0] or xy[:, 0].min() > caja[2] or
                                 xy[:, 1].max() < caja[1] or xy[:, 1].min() > caja[3]):
            continue
        s = puentes_v.seccion(t)
        if s is None:
            continue
        tuneles.append(dict(xy=xy, tags=t, s=s))
    # cadenas: los túneles cortos que siguen a uno largo van con él (si no, el corto se queda a nivel)
    grado = {}
    for tu in tuneles:
        for p in (tu["xy"][0], tu["xy"][-1]):
            grado[_clave(p)] = grado.get(_clave(p), 0) + 1
    largos = []
    for tu in tuneles:
        L = LineString(tu["xy"]).length
        sigue = any(grado.get(_clave(p), 0) > 1 for p in (tu["xy"][0], tu["xy"][-1]))
        if L >= LARGO_MIN or (sigue and L >= 20) or (L >= 20 and _bajo_tierra(tu["xy"], relieve)):
            largos.append(tu)
    tuneles = largos
    # z en los vértices: en las bocas, el suelo de la trinchera; dentro, interpolación por la red de túneles
    z, vecinos, fijo = {}, {}, {}
    for tu in tuneles:
        xy = tu["xy"]
        claves = [_clave(p) for p in xy]
        for a, b, pa, pb in zip(claves[:-1], claves[1:], xy[:-1], xy[1:]):
            w = 1.0 / max(float(np.linalg.norm(pb - pa)), 0.5)
            vecinos.setdefault(a, []).append((b, w))
            vecinos.setdefault(b, []).append((a, w))
        for extremo, interior in ((0, 1), (-1, -2)):
            k = claves[extremo]
            if grado.get(k, 0) > 1 and k not in nodos_fuera:
                continue  # sigue en otro túnel
            p, q = xy[extremo], xy[interior]
            fuera_dir = (p - q) / (np.linalg.norm(p - q) + 1e-9)
            muestras = np.array([p + fuera_dir * d for d in (0.0, 4.0, 8.0, 12.0)])
            suelo = relieve.valor("suelo", muestras[:, 0], muestras[:, 1])
            if np.isfinite(suelo).any():
                fijo[k] = float(np.nanmin(suelo)) + 0.05
    if not fijo:
        return []
    # cada red de túneles conectados necesita al menos una boca medida (si no, falta su LiDAR: se deja)
    comp, n_comp = {}, 0
    for k0 in vecinos:
        if k0 in comp:
            continue
        pila = [k0]
        comp[k0] = n_comp
        while pila:
            a = pila.pop()
            for b, _ in vecinos[a]:
                if b not in comp:
                    comp[b] = n_comp
                    pila.append(b)
        n_comp += 1
    medidas = {}
    for k, zk in fijo.items():
        medidas.setdefault(comp[k], []).append(zk)
    for k in vecinos:
        if comp[k] in medidas:
            z[k] = fijo.get(k, float(np.mean(medidas[comp[k]])))
    claves = list(vecinos)
    for _ in range(3000):  # media ponderada por la distancia: interpolación lineal a lo largo de cada cadena
        cambio = 0.0
        for k in claves:
            if k in fijo or k not in z:
                continue
            nuevo = sum(z[b] * w for b, w in vecinos[k]) / sum(w for _, w in vecinos[k])
            cambio = max(cambio, abs(nuevo - z[k]))
            z[k] = nuevo
        if cambio < 0.005:
            break
    out = []
    for tu in tuneles:
        if any(_clave(p) not in z for p in tu["xy"]):
            continue
        linea = LineString(tu["xy"])
        largo = linea.length
        ds = np.unique(np.r_[np.arange(0, largo, puentes_v.PASO), largo])
        pts = np.array([linea.interpolate(d).coords[0] for d in ds])
        dv = np.r_[0, np.cumsum(np.linalg.norm(np.diff(tu["xy"], axis=0), axis=1))]
        zv = np.array([z[_clave(p)] for p in tu["xy"]])
        zz = np.interp(ds, dv, zv)
        # trincheras cubiertas (Ronda del Mig, Lesseps...): si la boca se midió a la cota de la calle, el tubo
        # salía por encima de la plaza. Bajo tierra, al menos 1 m de cubierta sobre el techo, con una rampa
        # del 6 % desde cada boca medida (la del tramo que sigue en otro túnel no cuenta)
        sup = relieve.valor("suelo", pts[:, 0], pts[:, 1]).astype(np.float64)
        if np.isfinite(sup).sum() > 1:
            bien = np.isfinite(sup)
            sup = np.interp(ds, ds[bien], sup[bien])
            # percentil 75 en 60 m: la losa o la plaza de encima, no las rejillas de ventilación abiertas
            sup = ndimage.percentile_filter(sup, 75, size=31, mode="nearest")
            # en los extremos, la misma cota para las dos vías que se juntan allí (si no, un escalón)
            for extremo, idx in ((tu["xy"][0], slice(0, 10)), (tu["xy"][-1], slice(-10, None))):
                g = np.linspace(-8, 8, 5)
                gx, gy = np.meshgrid(g, g)
                nodo = relieve.valor("suelo", extremo[0] + gx.ravel(), extremo[1] + gy.ravel())
                if np.isfinite(nodo).any():
                    peso = np.linspace(1, 0, 10) if idx.start == 0 else np.linspace(0, 1, 10)
                    sup[idx] = peso * float(np.nanmedian(nodo)) + (1 - peso) * sup[idx] if len(sup) >= 10 else sup[idx]
            hasta_boca = np.full(len(ds), np.inf)
            if _clave(tu["xy"][0]) in fijo:
                hasta_boca = np.minimum(hasta_boca, ds)
            if _clave(tu["xy"][-1]) in fijo:
                hasta_boca = np.minimum(hasta_boca, largo - ds)
            # envolvente por debajo con pendiente máxima del 6 %: sin baches aunque la superficie suba y baje
            req = sup - (GALIBO + 1.0)
            envolvente = (req[None, :] + 0.06 * np.abs(ds[:, None] - ds[None, :])).min(1)
            zz = np.minimum(zz, np.maximum(envolvente, zz - 0.06 * hasta_boca))
        tan = np.gradient(pts, axis=0)
        tan /= np.linalg.norm(tan, axis=1, keepdims=True) + 1e-9
        der = np.c_[tan[:, 1], -tan[:, 0]]
        tu.update(pts=pts, der=der, ds=ds, z=zz)
        out.append(tu)
    return out


def construir(tuneles, centro, caja):
    obra = puentes_v.Obra(centro)
    hechos = 0
    for tu in tuneles:
        s = tu["s"]
        w = s["ancho"] / 2 + 0.5
        for i0, i1 in puentes_v.tramos(tu["pts"], caja):
            sl = slice(i0, i1 + 1)
            eje = (tu["pts"][sl], tu["der"][sl], tu["ds"][sl], tu["z"][sl])
            puentes_v._calzada(obra, eje, s)
            # aceras del tubo a la altura de la calzada (las de calle llevan bordillo, aquí no hace falta)
            obra.extruir(eje, "vi_tunel", [(-w, 0.0), (-w, GALIBO), (w, GALIBO), (w, 0.0)], lados=[0, 2], escala=3.0)
            obra.extruir(eje, "vi_tunel_techo", [(-w, GALIBO), (w, GALIBO)], lados=[0], escala=4.0)
            # losa de cubierta por fuera (se ve donde la cubierta real es más fina que el tubo)
            obra.extruir(eje, "vi_hormigon", [(w, GALIBO + 0.05), (-w, GALIBO + 0.05)], lados=[0], escala=4.0)
            obra.banda(eje, "vi_hormigon", -w, -s["ancho"] / 2 + 0.6, 0.0)
            obra.banda(eje, "vi_hormigon", s["ancho"] / 2 - 0.6, w, 0.0)
            pts, der, ds, z = eje
            for d in np.arange(np.ceil(ds[0] / 12) * 12, ds[-1], 12.0):  # luces en el techo
                i = int(np.clip(np.searchsorted(ds, d), 0, len(ds) - 1))
                for o in (-w * 0.5, w * 0.5):
                    c = np.r_[pts[i] + der[i] * o - obra.c, z[i] + GALIBO - 0.02]
                    t2 = np.r_[-der[i, 1], der[i, 0], 0] * 0.6
                    l2 = np.r_[der[i], 0] * 0.15
                    obra.cara("vi_luz", [c - t2 - l2, c + t2 - l2, c + t2 + l2, c - t2 + l2],
                              [(0, 0), (1, 0), (1, 1), (0, 1)], np.array([0, 0, -1.0]))
            hechos += 1
    arrays = obra.m.arrays()
    v, t, mats = [], [], []
    for tex, g in arrays.items():
        if tex.startswith("vi_linea") or tex == "vi_luz":
            continue
        base = sum(len(x) for x in v)
        v.append(g["v"])
        t.append(g["i"] + base)
        mats.append(np.full(len(g["i"]), rage.MAT_TARMAC if tex == "vi_asfalto" else rage.MAT_CONCRETE))
    col = (np.concatenate(v), np.concatenate(t), np.concatenate(mats)) if v else None
    return arrays, col, hechos


def fuera(v_utm, tris, tuneles):
    """Máscara de los triángulos del terreno que se quedan: fuera los que caen sobre un tubo por debajo de su
    techo (la pared de la boca o una cubierta más fina que el gálibo)."""
    keep = np.ones(len(tris), bool)
    if not tuneles:
        return keep
    c = v_utm[tris].mean(1)
    zmin = v_utm[tris][:, :, 2].min(1)
    lo, hi = c[:, :2].min(0) - 20, c[:, :2].max(0) + 20
    for tu in tuneles:
        pts = tu["pts"]
        if pts[:, 0].max() < lo[0] or pts[:, 0].min() > hi[0] or pts[:, 1].max() < lo[1] or pts[:, 1].min() > hi[1]:
            continue
        franja = LineString(pts).buffer(tu["s"]["ancho"] / 2 + 1.5, cap_style="flat")
        dentro = shapely.contains_xy(franja, c[:, 0], c[:, 1])
        if not dentro.any():
            continue
        idx = np.flatnonzero(dentro)
        cerca = np.argmin(((c[idx, None, :2] - pts[None, :, :]) ** 2).sum(-1), axis=1)
        techo = tu["z"][cerca] + GALIBO - 0.3  # se tolera que el terreno roce el techo
        keep[idx[zmin[idx] < techo]] = False
    return keep
