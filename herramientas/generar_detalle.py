"""Árboles y mobiliario urbano con modelos del juego original (siguen en gta3.img).

  - plátanos en las aceras de las calles con coches, palmeras en los paseos marítimos
  - árboles en parques y jardines, pinos en el bosque de la Serralada
  - farolas a lo largo de las calles, bancos en las calles peatonales
Nada cae dentro de un edificio ni encima de la calzada.

Salida: mod/data/maps/badalona/detalle.ipl (instalar_en_juego.py lo añade a gta.dat).
El juego admite unos 13.000 edificios (los árboles cuentan como tales) y 2.500 objetos con física
(farolas, bancos): de ahí los máximos.
"""
import math
import random

import numpy as np
from shapely import STRtree, points
from shapely.geometry import LineString, Polygon

import config
from procesar_osm import ANCHO_CALLE, PEATONAL, contornos_multipoligono, leer_osm, linea
import json

SALIDA = config.RAIZ / "mod" / "data" / "maps" / "badalona" / "detalle.ipl"
POR_ARCHIVO = 3000  # con más de ~4000 líneas en un mismo .ipl el juego se cierra al cargar
# (id, nombre) de los IDE del juego (vegepart.ide, dynamic.ide)
PLATANOS = [(669, "sm_veg_tree4"), (672, "sm_veg_tree5"), (700, "sm_veg_tree6")]
PARQUE = [(615, "veg_tree3"), (616, "veg_treea1"), (617, "veg_treeb1"), (691, "sm_veg_tree4_big")]
PALMERAS = [(620, "veg_palm04"), (621, "veg_palm02"), (622, "veg_palm03"), (648, "veg_palm01")]
PINOS = [(654, "pinetree08"), (656, "pinetree05"), (658, "pinetree04"), (661, "pinetree07"), (659, "pinetree01")]
FAROLA = (1294, "mlamppost")
FAROLA_PARQUE = (1226, "lamppost3")
BANCO = (1280, "parkbench1")
PAPELERA = (1359, "CJ_BIN1")
MOBILIARIO = {FAROLA, FAROLA_PARQUE, BANCO, PAPELERA}
ARBUSTOS = [(647, "new_bushsm"), (671, "sm_bushytree"), (762, "new_bushtest")]
# Turismos corrientes del juego para los coches aparcados
COCHES = [401, 404, 405, 410, 419, 421, 426, 436, 445, 458, 466, 467, 474, 479, 491, 492, 496, 516, 517, 518,
          526, 527, 529, 540, 542, 546, 547, 549, 550, 551, 585, 589, 600]
MAX_ARBOLES = 11000
MAX_OBJETOS = 2300
MAX_COCHES = 450  # el juego admite 500 generadores de coches aparcados
# Zona con más detalle: Llefià (Sant Joan, Sant Antoni, Sant Mori), La Salut y el Turó d'en Caritg
DETALLE = [(-2150.0, -850.0, 650.0), (-1500.0, -850.0, 450.0)]  # círculos (x, y, radio)


def en_detalle(x, y):
    return any((x - cx) ** 2 + (y - cy) ** 2 < r * r for cx, cy, r in DETALLE)
CALLES_CON_ARBOLES = {"primary", "secondary", "tertiary", "residential", "unclassified", "living_street"}
CALLES_CON_FAROLAS = CALLES_CON_ARBOLES | {"trunk", "motorway_link", "trunk_link", "primary_link"}

h = np.load(config.DATOS / "elevacion" / "relieve_gta.npy")
N = h.shape[0] - 1


def altura(x, y):
    fx = (x + config.MITAD) / config.LADO * N
    fy = (config.MITAD - y) / config.LADO * N
    c, f = min(max(int(fx), 0), N - 1), min(max(int(fy), 0), N - 1)
    dx, dy = fx - c, fy - f
    return float(h[f, c] * (1 - dx) * (1 - dy) + h[f, c + 1] * dx * (1 - dy)
                 + h[f + 1, c] * (1 - dx) * dy + h[f + 1, c + 1] * dx * dy)


def puntos_a_lo_largo(pts, paso, desplazamiento):
    """Puntos cada `paso` m a la izquierda y derecha de la polilínea, con la dirección de la calle."""
    salida, resto = [], paso / 2
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        largo = math.hypot(x1 - x0, y1 - y0)
        if largo < 1e-6:
            continue
        ux, uy = (x1 - x0) / largo, (y1 - y0) / largo
        t = resto
        while t < largo:
            x, y = x0 + ux * t, y0 + uy * t
            for lado in (1, -1):
                salida.append((x - uy * desplazamiento * lado, y + ux * desplazamiento * lado, math.atan2(uy, ux), lado))
            t += paso
        resto = t - largo
    return salida


def main():
    gta, vias, relaciones = leer_osm()
    with open(config.DATOS / "generado" / "edificios.json", encoding="utf-8") as fh:
        plantas = [Polygon(e["planta"]) for e in json.load(fh)]
    plantas = [p if p.is_valid else p.buffer(0) for p in plantas]
    arbol_edificios = STRtree(plantas)

    calles = []
    for refs, tags in vias.values():
        tipo = tags.get("highway")
        pts = linea(gta, refs)
        if tipo in ANCHO_CALLE and len(pts) >= 2 and tags.get("tunnel") != "yes" and tags.get("bridge") != "yes":
            calles.append((pts, tipo, tags.get("name", "")))
    lineas_calle = [LineString(p) for p, tipo, _ in calles]
    anchos = np.array([ANCHO_CALLE[tipo] * config.ESCALA / 2 for _, tipo, _ in calles])
    arbol_calles = STRtree(lineas_calle)

    def libre(candidatos, margen_calle=1.0):
        """Filtra (x, y, ...) que no caen en un edificio, en la calzada, en el mar ni fuera del mapa."""
        if not candidatos:
            return []
        geo = points(np.array([(c[0], c[1]) for c in candidatos]))
        en_edificio = set(arbol_edificios.query(geo, predicate="intersects")[0])
        cerca = arbol_calles.query(geo, predicate="dwithin", distance=float(anchos.max()) + margen_calle)
        en_calle = set()
        for i, j in zip(*cerca):
            if i not in en_calle and lineas_calle[j].distance(geo[i]) < anchos[j] + margen_calle:
                en_calle.add(i)
        return [c for i, c in enumerate(candidatos)
                if i not in en_edificio and i not in en_calle
                and abs(c[0]) < config.MITAD - 5 and abs(c[1]) < config.MITAD - 5 and altura(c[0], c[1]) > 0.5]

    azar = random.Random(42)
    # Dos listas por tipo: [0] zona de detalle (Llefià / La Salut, va primero) y [1] el resto del mapa
    arboles, objetos, coches = ([], []), ([], []), []

    def zona(x, y):
        return 0 if en_detalle(x, y) else 1

    for pts, tipo, nombre in calles:
        medio = ANCHO_CALLE[tipo] * config.ESCALA / 2
        paseo = "passeig mar" in nombre.lower() or "rambla" in nombre.lower()
        z = zona(*pts[len(pts) // 2])
        # Árboles en la acera (cada 7 m en la zona de detalle, 9 m en el resto)
        if tipo in CALLES_CON_ARBOLES or (paseo and tipo in PEATONAL):
            modelos = PALMERAS if paseo else PLATANOS
            for x, y, _, _ in libre(puntos_a_lo_largo(pts, 7.0 if z == 0 else 9.0, medio + 1.8), 0.5):
                arboles[zona(x, y)].append((azar.choice(modelos), x, y, azar.uniform(0, 2 * math.pi)))
        # Farolas: en la zona de detalle a los dos lados cada 18 m; en el resto cada 60 m alternando
        if tipo in CALLES_CON_FAROLAS:
            puestos = libre(puntos_a_lo_largo(pts, 18.0 if z == 0 else 30.0, medio + 0.8), 0.2)
            for x, y, rumbo, lado in (puestos if z == 0 else puestos[::2]):
                objetos[zona(x, y)].append((FAROLA, x, y, rumbo + (math.pi / 2 if lado > 0 else -math.pi / 2)))
        # Coches aparcados en los dos lados de las calles de la zona de detalle
        if z == 0 and tipo in {"residential", "tertiary", "secondary", "unclassified"}:
            for x, y, rumbo, lado in puntos_a_lo_largo(pts, 6.5, max(medio - 1.3, 1.0)):
                if azar.random() < 0.55:
                    coches.append((x, y, math.degrees(rumbo) - 90 + (180 if lado < 0 else 0)))
        # Bancos y papeleras en calles peatonales, plazas y caminos de parque
        if tipo in {"pedestrian", "living_street", "footway", "path"} and (z == 0 or tipo != "footway"):
            paso = 12.0 if z == 0 else 25.0
            for k, (x, y, rumbo, lado) in enumerate(libre(puntos_a_lo_largo(pts, paso, medio + 0.6), 0.0)):
                if z == 1 and k % 3:
                    continue
                modelo = PAPELERA if k % 4 == 3 else BANCO
                objetos[zona(x, y)].append((modelo, x, y, rumbo + (0 if lado > 0 else math.pi)))
            if z == 0 and tipo in {"footway", "path", "pedestrian"}:
                for x, y, rumbo, lado in libre(puntos_a_lo_largo(pts, 22.0, medio + 0.9), 0.0)[::2]:
                    objetos[0].append((FAROLA_PARQUE, x, y, rumbo))

    # Parques y bosque: puntos al azar dentro de cada zona (más densos en la zona de detalle)
    zonas = []
    for clave, valores, densidad, modelos in (
            ("leisure", {"park", "garden"}, 120.0, PARQUE),
            ("place", {"square"}, 250.0, PARQUE),
            ("landuse", {"forest"}, 900.0, PINOS),
            ("natural", {"wood"}, 900.0, PINOS)):
        for refs, tags in vias.values():
            if tags.get(clave) in valores and len(refs) > 3:
                zonas.append((linea(gta, refs), densidad, modelos))
        for miembros, tags in relaciones:
            if tags.get(clave) in valores:
                zonas += [(a, densidad, modelos) for a in contornos_multipoligono(gta, vias, miembros) if len(a) > 3]
    for anillo, densidad, modelos in zonas:
        try:
            poli = Polygon(anillo)
            poli = poli if poli.is_valid else poli.buffer(0)
        except ValueError:
            continue
        z = zona(poli.centroid.x, poli.centroid.y)
        if z == 0:
            densidad /= 2.5
        cuantos = int(poli.area / densidad)
        if cuantos == 0:
            continue
        x0, y0, x1, y1 = poli.bounds
        cand = [(azar.uniform(x0, x1), azar.uniform(y0, y1)) for _ in range(cuantos * 3)]
        dentro = poli.contains(points(np.array(cand)))
        cand = [c for c, d in zip(cand, dentro) if d][:cuantos]
        for x, y in libre(cand, 1.5):
            # en la zona de detalle, uno de cada tres es un arbusto
            modelo = azar.choice(ARBUSTOS) if z == 0 and modelos is PARQUE and azar.random() < 0.33 else azar.choice(modelos)
            arboles[z].append((modelo, x, y, azar.uniform(0, 2 * math.pi)))

    for lista in arboles + objetos:
        azar.shuffle(lista)
    print(f"Zona de detalle: {len(arboles[0])} árboles, {len(objetos[0])} objetos, {len(coches)} coches; "
          f"resto: {len(arboles[1])} árboles, {len(objetos[1])} objetos")
    arboles = (arboles[0] + arboles[1])[:MAX_ARBOLES]
    objetos = (objetos[0] + objetos[1])[:MAX_OBJETOS]
    azar.shuffle(coches)
    coches = coches[:MAX_COCHES]
    lineas = []
    for (ident, nombre), x, y, giro in arboles + objetos:
        z = altura(x, y) - (0.3 if (ident, nombre) not in MOBILIARIO else 0.0)
        lineas.append(f"{ident}, {nombre}, 0, {x:.2f}, {y:.2f}, {z:.2f}, 0, 0, {math.sin(giro / 2):.4f}, {math.cos(giro / 2):.4f}, -1\n")
    with open(SALIDA.parent / "aparcados.ipl", "w", encoding="ascii", newline="\r\n") as ipl:
        ipl.write("# Coches aparcados - generado por herramientas/generar_detalle.py\ncars\n")
        for x, y, angulo in coches:
            ipl.write(f"{x:.2f}, {y:.2f}, {altura(x, y) + 0.6:.2f}, {angulo % 360:.1f}, {azar.choice(COCHES)}, -1, -1, 1, 0, 0, 0, 0\n")
        ipl.write("end\n")
    for viejo in SALIDA.parent.glob("detalle_*.ipl"):
        viejo.unlink()
    for i in range(0, len(lineas), POR_ARCHIVO):
        with open(SALIDA.parent / f"detalle_{i // POR_ARCHIVO}.ipl", "w", encoding="ascii", newline="\r\n") as ipl:
            ipl.write("# Arboles y mobiliario - generado por herramientas/generar_detalle.py\ninst\n")
            ipl.writelines(lineas[i:i + POR_ARCHIVO])
            ipl.write("end\n")
    print(f"detalle_N.ipl: {len(arboles)} árboles, {len(objetos)} farolas y bancos en "
          f"{-(-len(lineas) // POR_ARCHIVO)} archivos; aparcados.ipl: {len(coches)} coches")


if __name__ == "__main__":
    main()
