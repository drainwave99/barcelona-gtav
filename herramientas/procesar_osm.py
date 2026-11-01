"""Convierte datos/osm/badalona.osm en datos listos para Blender/GTA (en coordenadas GTA).

Salidas:
  datos/generado/edificios.json          plantas de edificios con altura
  datos/generado/suelo/suelo_FF_CC.png   textura del suelo de cada trozo de terreno (calles, parques, playa...)
  datos/generado/radar/radarNN.png       radar del juego: 12 x 12 casillas de 500 m (radar00 = esquina noroeste)
  docs/mapa_suelo.png                    vista de todo el suelo en pequeño
"""
import json
import math
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from shapely import STRtree, points
from shapely.geometry import Polygon

import config

TROZOS = 16  # igual que blender_terreno.py
PX_TROZO = 512  # resolución de la textura de cada trozo (~0,7 m por píxel)
PX_TOTAL = TROZOS * PX_TROZO
ALTURA_PLANTA = 3.2

GENERADO = config.DATOS / "generado"

# Ancho real (m) de cada tipo de calle
ANCHO_CALLE = {
    "motorway": 24, "trunk": 20, "primary": 16, "secondary": 13, "tertiary": 11,
    "motorway_link": 8, "trunk_link": 8, "primary_link": 8, "secondary_link": 7, "tertiary_link": 7,
    "residential": 9, "unclassified": 8, "living_street": 7, "service": 5,
    "pedestrian": 8, "footway": 3, "path": 2, "cycleway": 3, "steps": 3, "track": 3,
}
PEATONAL = {"pedestrian", "footway", "path", "steps", "cycleway", "track"}

COLORES = {
    "base": (120, 118, 105), "acera": (175, 170, 160), "asfalto": (60, 60, 64), "peatonal": (190, 180, 160),
    "parque": (80, 120, 55), "bosque": (55, 85, 45), "arena": (220, 205, 160), "agua": (40, 80, 120),
    "industrial": (130, 125, 120), "tren": (95, 85, 75), "campo": (140, 140, 80), "linea": (225, 225, 215),
}

USO_SUELO = [  # (etiqueta, valores, color); se pinta en este orden
    ("landuse", {"industrial", "railway", "port"}, "industrial"),
    ("landuse", {"farmland", "meadow", "grass", "orchard", "vineyard"}, "campo"),
    ("natural", {"scrub", "heath", "grassland"}, "campo"),
    ("landuse", {"forest"}, "bosque"),
    ("natural", {"wood"}, "bosque"),
    ("leisure", {"park", "garden", "pitch", "golf_course"}, "parque"),
    ("landuse", {"recreation_ground", "village_green", "cemetery"}, "parque"),
    ("natural", {"beach", "sand"}, "arena"),
    ("natural", {"water"}, "agua"),
    ("waterway", {"riverbank"}, "agua"),
]


def leer_osm():
    nodos, vias, relaciones = {}, {}, []
    for _, el in ET.iterparse(config.DATOS / "osm" / "badalona.osm"):
        if el.tag == "node":
            nodos[el.get("id")] = (float(el.get("lon")), float(el.get("lat")))
        elif el.tag == "way":
            vias[el.get("id")] = ([nd.get("ref") for nd in el.iter("nd")], {t.get("k"): t.get("v") for t in el.iter("tag")})
        elif el.tag == "relation":
            miembros = [(m.get("type"), m.get("ref"), m.get("role")) for m in el.iter("member")]
            tags = {t.get("k"): t.get("v") for t in el.iter("tag")}
            tags["_id"] = el.get("id")
            relaciones.append((miembros, tags))
        if el.tag in ("way", "relation"):
            el.clear()
    # Pasar todos los nodos a coordenadas GTA de una vez
    ids = list(nodos)
    lon = np.array([nodos[i][0] for i in ids])
    lat = np.array([nodos[i][1] for i in ids])
    x, y = config.wgs_a_gta(lon, lat)
    gta = {i: (float(a), float(b)) for i, a, b in zip(ids, x, y)}
    return gta, vias, relaciones


def linea(gta, refs):
    return [gta[r] for r in refs if r in gta]


def a_px(pts):
    k = PX_TOTAL / config.LADO
    return [((x + config.MITAD) * k, (config.MITAD - y) * k) for x, y in pts]


def contornos_multipoligono(gta, vias, miembros):
    """Une los trozos 'outer' de una relación en anillos cerrados (simplificado)."""
    trozos = [list(vias[ref][0]) for tipo, ref, rol in miembros if tipo == "way" and rol == "outer" and ref in vias]
    anillos = []
    while trozos:
        anillo = trozos.pop()
        cambiado = True
        while anillo[0] != anillo[-1] and cambiado:
            cambiado = False
            for t in trozos:
                if t[0] == anillo[-1]:
                    anillo += t[1:]
                elif t[-1] == anillo[-1]:
                    anillo += t[-2::-1]
                elif t[-1] == anillo[0]:
                    anillo = t[:-1] + anillo
                elif t[0] == anillo[0]:
                    anillo = t[:0:-1] + anillo
                else:
                    continue
                trozos.remove(t)
                cambiado = True
                break
        anillos.append(linea(gta, anillo))
    return anillos


def pintar_suelo(gta, vias, relaciones):
    img = Image.new("RGB", (PX_TOTAL, PX_TOTAL), COLORES["base"])
    d = ImageDraw.Draw(img)
    k = PX_TOTAL / config.LADO * config.ESCALA  # metros reales -> píxeles

    # Mar: todo lo que el relieve tiene por debajo de 0
    h = np.load(config.DATOS / "elevacion" / "relieve_gta.npy")
    mar = Image.fromarray(((h <= 0) * 255).astype(np.uint8)).resize((PX_TOTAL, PX_TOTAL), Image.NEAREST)
    img.paste(COLORES["agua"], mask=mar)

    for clave, valores, color in USO_SUELO:
        for refs, tags in vias.values():
            if tags.get(clave) in valores and len(refs) > 3:
                d.polygon(a_px(linea(gta, refs)), fill=COLORES[color])
        for miembros, tags in relaciones:
            if tags.get(clave) in valores:
                for anillo in contornos_multipoligono(gta, vias, miembros):
                    if len(anillo) > 3:
                        d.polygon(a_px(anillo), fill=COLORES[color])

    calles = [(refs, tags["highway"]) for refs, tags in vias.values() if tags.get("highway") in ANCHO_CALLE]
    # Aceras primero (más anchas), luego el asfalto encima
    for refs, tipo in calles:
        if tipo not in PEATONAL:
            d.line(a_px(linea(gta, refs)), fill=COLORES["acera"], width=max(1, round((ANCHO_CALLE[tipo] + 6) * k)), joint="curve")
    for refs, tipo in calles:
        color = COLORES["peatonal"] if tipo in PEATONAL else COLORES["asfalto"]
        d.line(a_px(linea(gta, refs)), fill=color, width=max(1, round(ANCHO_CALLE[tipo] * k)), joint="curve")
    # Línea discontinua blanca en el centro de las calles anchas (3 m pintados, 6 m sin pintar)
    for refs, tipo in calles:
        if tipo not in PEATONAL and ANCHO_CALLE[tipo] >= 9:
            for tramo in discontinua(a_px(linea(gta, refs)), 3 * k, 6 * k):
                d.line(tramo, fill=COLORES["linea"], width=max(1, round(0.3 * k)))
    for refs, tags in vias.values():
        if tags.get("railway") in {"rail", "tram", "light_rail"} and tags.get("tunnel") != "yes":
            d.line(a_px(linea(gta, refs)), fill=COLORES["tren"], width=max(1, round(6 * k)))

    # Variación suave de tono de un sitio a otro (manchas de unos 50 m), continua entre trozos
    rng = np.random.default_rng(7)
    manchas = Image.fromarray((rng.normal(128, 40, (TROZOS * 8, TROZOS * 8))).clip(0, 255).astype(np.uint8))
    manchas = manchas.filter(ImageFilter.GaussianBlur(1.5)).resize((PX_TOTAL // 8, PX_TOTAL // 8), Image.BICUBIC)
    carpeta = GENERADO / "suelo"
    carpeta.mkdir(parents=True, exist_ok=True)
    for f in range(TROZOS):
        for c in range(TROZOS):
            trozo = np.asarray(img.crop((c * PX_TROZO, f * PX_TROZO, (c + 1) * PX_TROZO, (f + 1) * PX_TROZO)), dtype=np.float32)
            m = PX_TROZO // 8
            mancha = manchas.crop((c * m, f * m, (c + 1) * m, (f + 1) * m)).resize((PX_TROZO, PX_TROZO), Image.BICUBIC)
            factor = 1 + (np.asarray(mancha, dtype=np.float32)[..., None] - 128) / 128 * 0.10
            factor = factor * (1 + rng.normal(0, 0.05, (PX_TROZO, PX_TROZO, 1)))  # grano del asfalto/tierra
            Image.fromarray((trozo * factor).clip(0, 255).astype(np.uint8)).save(carpeta / f"suelo_{f:02d}_{c:02d}.png")
    img.resize((1024, 1024), Image.LANCZOS).save(config.RAIZ / "docs" / "mapa_suelo.png")
    print(f"Suelo: {TROZOS * TROZOS} texturas de {PX_TROZO}px en {carpeta}")


def discontinua(pts, pintado, hueco):
    """Trozos [(x, y), ...] de una línea discontinua a lo largo de la polilínea pts (en píxeles)."""
    tramos, actual, pos, ciclo = [], [], 0.0, pintado + hueco
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        largo = math.hypot(x1 - x0, y1 - y0)
        t = 0.0
        while t < largo:
            fase = pos % ciclo
            paso = min((pintado - fase) if fase < pintado else (ciclo - fase), largo - t)
            if fase < pintado:
                if not actual:
                    actual = [(x0 + (x1 - x0) * t / largo, y0 + (y1 - y0) * t / largo)]
                actual.append((x0 + (x1 - x0) * (t + paso) / largo, y0 + (y1 - y0) * (t + paso) / largo))
            elif actual:
                tramos.append(actual)
                actual = []
            t += max(paso, 1e-6)
            pos += max(paso, 1e-6)
    if len(actual) > 1:
        tramos.append(actual)
    return tramos


RADAR_PX = 256  # se dibuja a 256 px por casilla y se reduce a 128 (lo que usa el juego)
COLORES_RADAR = {
    "tierra": (196, 190, 170), "agua": (110, 150, 190), "parque": (150, 185, 120), "bosque": (120, 160, 100),
    "arena": (230, 215, 170), "industrial": (180, 172, 165), "edificio": (160, 150, 140),
    "calle": (250, 250, 248), "borde": (120, 120, 120), "tren": (110, 100, 95),
}


def pintar_radar(gta, vias, relaciones, edificios):
    """Radar y mapa del menú: 144 casillas de 500 m, del noroeste (radar00) al sureste (radar143)."""
    total = 12 * RADAR_PX
    k = total / config.LADO

    def px(pts):
        return [((x + config.MITAD) * k, (config.MITAD - y) * k) for x, y in pts]

    img = Image.new("RGB", (total, total), COLORES_RADAR["tierra"])
    d = ImageDraw.Draw(img)
    h = np.load(config.DATOS / "elevacion" / "relieve_gta.npy")
    mar = Image.fromarray(((h <= 0) * 255).astype(np.uint8)).resize((total, total), Image.NEAREST)
    img.paste(COLORES_RADAR["agua"], mask=mar)
    for clave, valores, color in USO_SUELO:
        color = color if color in COLORES_RADAR else "parque"
        for refs, tags in vias.values():
            if tags.get(clave) in valores and len(refs) > 3:
                d.polygon(px(linea(gta, refs)), fill=COLORES_RADAR[color])
        for miembros, tags in relaciones:
            if tags.get(clave) in valores:
                for anillo in contornos_multipoligono(gta, vias, miembros):
                    if len(anillo) > 3:
                        d.polygon(px(anillo), fill=COLORES_RADAR[color])
    for e in edificios:
        d.polygon(px(e["planta"]), fill=COLORES_RADAR["edificio"])
    calles = [(refs, tags["highway"]) for refs, tags in vias.values()
              if tags.get("highway") in ANCHO_CALLE and tags["highway"] not in PEATONAL]
    # Calles blancas con borde gris, algo más anchas que en la realidad para que se lean en el radar
    for color, extra in (("borde", 6), ("calle", 0)):
        for refs, tipo in calles:
            d.line(px(linea(gta, refs)), fill=COLORES_RADAR[color],
                   width=max(2, round((ANCHO_CALLE[tipo] * 1.6 + extra) * k)), joint="curve")
    for refs, tags in vias.values():
        if tags.get("railway") in {"rail", "light_rail"} and tags.get("tunnel") != "yes":
            d.line(px(linea(gta, refs)), fill=COLORES_RADAR["tren"], width=2)

    carpeta = GENERADO / "radar"
    carpeta.mkdir(parents=True, exist_ok=True)
    for f in range(12):
        for c in range(12):
            casilla = img.crop((c * RADAR_PX, f * RADAR_PX, (c + 1) * RADAR_PX, (f + 1) * RADAR_PX))
            casilla.resize((128, 128), Image.LANCZOS).save(carpeta / f"radar{f * 12 + c:02d}.png")
    img.resize((1024, 1024), Image.LANCZOS).save(config.RAIZ / "docs" / "mapa_radar.png")
    print(f"Radar: 144 casillas en {carpeta}")


def metros(tags, *claves):
    for clave in claves:
        try:
            return float(tags[clave].replace("m", "").strip())
        except (KeyError, ValueError):
            pass
    return None


def altura_edificio(tags):
    h = metros(tags, "height", "building:height")
    if h is not None:
        return h
    try:
        return float(tags["building:levels"]) * ALTURA_PLANTA + 1
    except (KeyError, ValueError):
        pass
    # Por defecto: casas bajas 2 plantas, pisos 5 plantas (lo típico en Badalona)
    if tags.get("building") in {"house", "detached", "semidetached_house", "garage", "shed", "hut"}:
        return 2 * ALTURA_PLANTA
    return 5 * ALTURA_PLANTA


def extraer_edificios(gta, vias, relaciones):
    """Edificios normales y partes 3D (building:part, con altura mínima). Si un edificio está
    modelado por partes (relación type=building, p. ej. las Tres Xemeneies), se usan las partes
    y no el contorno."""
    edificios = []

    def anadir(pts, tags):
        if len(pts) < 4:
            return
        if all(abs(x) > config.MITAD or abs(y) > config.MITAD for x, y in pts):
            return
        if pts[0] == pts[-1]:
            pts = pts[:-1]
        minimo = metros(tags, "min_height") or 0.0
        if minimo == 0 and "building:min_level" in tags:
            minimo = (metros(tags, "building:min_level") or 0) * ALTURA_PLANTA
        alto = altura_edificio(tags) - minimo
        if alto <= 0:
            return
        edificios.append({
            "planta": [[round(x, 2), round(y, 2)] for x, y in pts],
            "altura": round(alto * config.ESCALA, 2),
            "base": round(minimo * config.ESCALA, 2),
            "tipo": tags.get("building", tags.get("building:part", "yes")),
            "nombre": tags.get("name", ""),
        })

    # Las partes sueltas del Catastro (cada edificio partido por número de plantas) se ignoran:
    # duplicarían paredes y triplicarían los triángulos. Solo se usan las partes de los edificios
    # modelados en 3D con relación type=building.
    contornos, partes_vias, partes_rel = set(), set(), set()
    for miembros, tags in relaciones:
        if tags.get("type") == "building" and any(rol == "part" for _, _, rol in miembros):
            contornos.update(ref for tipo, ref, rol in miembros if tipo == "way" and rol == "outline")
            partes_vias.update(ref for tipo, ref, rol in miembros if tipo == "way" and rol == "part")
            partes_rel.update(ref for tipo, ref, rol in miembros if tipo == "relation" and rol == "part")

    # Las partes sueltas sí dan la altura: el edificio sin altura propia toma las plantas de la
    # parte más alta que tiene dentro (el Catastro pone building:levels en las partes, no en el contorno).
    centros, plantas_parte = [], []
    for ident, (refs, tags) in vias.items():
        if "building:part" in tags and ident not in partes_vias and "building:levels" in tags:
            pts = linea(gta, refs)
            try:
                plantas = float(tags["building:levels"])
            except ValueError:
                continue
            if len(pts) >= 3 and plantas > 0:
                centros.append((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)))
                plantas_parte.append(plantas)
    arbol = STRtree(points(np.array(centros))) if centros else None

    def con_altura_catastro(pts, tags):
        if arbol is None or any(c in tags for c in ("height", "building:height", "building:levels")) or len(pts) < 4:
            return tags
        try:
            dentro = arbol.query(Polygon(pts), predicate="contains")
        except Exception:  # planta inválida
            return tags
        if len(dentro):
            tags = dict(tags, **{"building:levels": str(max(plantas_parte[i] for i in dentro))})
        return tags

    for ident, (refs, tags) in vias.items():
        if ident in partes_vias or ("building" in tags and tags["building"] != "no" and ident not in contornos):
            pts = linea(gta, refs)
            anadir(pts, tags if ident in partes_vias else con_altura_catastro(pts, tags))
    for miembros, tags in relaciones:
        if tags.get("type") != "multipolygon":
            continue
        if "building" in tags or tags.get("_id") in partes_rel:
            for anillo in contornos_multipoligono(gta, vias, miembros):
                anadir(anillo, con_altura_catastro(anillo, tags))

    GENERADO.mkdir(parents=True, exist_ok=True)
    with open(GENERADO / "edificios.json", "w", encoding="utf-8") as f:
        json.dump(edificios, f, ensure_ascii=False)
    alturas = np.array([e["altura"] for e in edificios])
    print(f"Edificios: {len(edificios)}; {len(centros)} partes del Catastro con plantas; "
          f"alturas: mediana {np.median(alturas):.1f} m, {np.sum(alturas > 20)} de más de 20 m")
    return edificios


def main():
    gta, vias, relaciones = leer_osm()
    print(f"Leído: {len(gta)} nodos, {len(vias)} vías, {len(relaciones)} relaciones")
    edificios = extraer_edificios(gta, vias, relaciones)
    pintar_radar(gta, vias, relaciones, edificios)
    pintar_suelo(gta, vias, relaciones)


if __name__ == "__main__":
    main()
