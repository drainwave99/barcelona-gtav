"""Levanta los edificios de OSM sobre el terreno y los agrupa por trozo del mapa.

Uso (después de blender_terreno.py y procesar_osm.py):
  blender --background --factory-startup --python herramientas/blender_edificios.py

Abre blender/terreno.blend, añade la colección "Edificios" (un objeto "bdn_edi_FF_CC" por trozo,
con el origen en el centro del trozo) y asigna a cada trozo de terreno su textura de suelo.
"""
import json
import math
import random
from pathlib import Path

import bmesh
import bpy
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
LADO = 6000.0
MITAD = LADO / 2
TROZOS = 16
TAM = LADO / TROZOS


def altura_terreno(h, x, y):
    n = h.shape[0] - 1
    col = int(round((x + MITAD) / LADO * n))
    fila = int(round((MITAD - y) / LADO * n))
    return float(h[min(max(fila, 0), n), min(max(col, 0), n)])


def trozo_de(x, y):
    c = int((x + MITAD) // TAM)
    f = int((MITAD - y) // TAM)
    return min(max(f, 0), TROZOS - 1), min(max(c, 0), TROZOS - 1)


def dentro_planta(pts, x, y):
    dentro = False
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            dentro = not dentro
    return dentro


def es_antihorario(pts):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1])) > 0


def material_con_textura(nombre, ruta):
    """Material con la textura en el Principled BSDF: DragonFF toma de ahí el nombre de textura."""
    mat = bpy.data.materials.new(nombre)
    mat.use_nodes = True
    nodos = mat.node_tree.nodes
    tex = nodos.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(ruta))
    mat.node_tree.links.new(tex.outputs["Color"], nodos["Principled BSDF"].inputs["Base Color"])
    return mat


# Texturas de generar_texturas.py; el orden es el índice de material
TEXTURAS = ["fa_balcon", "fa_ladrillo", "fa_moderno", "fa_obrero", "fa_casa", "fa_nave", "fa_hormigon",
            "ba_tienda", "ba_persiana", "ba_portal", "ba_nave", "te_terrado", "te_teja", "te_nave",
            "fa_ladrillo2", "fa_gres", "fa_estuco", "fa_terraza", "ba_bar", "ba_farmacia", "ba_balcon"]
MAT = {n: i for i, n in enumerate(TEXTURAS)}
# Materiales de las calles (mismo orden que procesar_calles.MATERIALES)
CALLE = ["as_asfalto", "ac_panot", "ac_bordillo", "as_linea", "as_cebra"]
# Zona con más detalle (igual que generar_detalle.DETALLE): Llefià, La Salut y el Turó d'en Caritg
DETALLE = [(-2150.0, -850.0, 650.0), (-1500.0, -850.0, 450.0)]
FACHADAS_CON_BALCON = {"fa_balcon", "fa_gres", "fa_estuco", "fa_ladrillo", "fa_obrero"}
MAX_BALCONES = 40  # por edificio
LIMITE_ESQUINAS = 60000  # esquinas de triángulo por modelo (cota de los vértices del .dff, máx. 65.535)


def en_detalle(x, y):
    return any((x - cx) ** 2 + (y - cy) ** 2 < r * r for cx, cy, r in DETALLE)
PLANTA = 3.2 * 0.95  # alto de una planta en unidades del juego (escala del mapa)
CASAS = {"house", "detached", "semidetached_house", "terrace", "bungalow", "villa", "farm", "garage", "shed", "hut"}
NAVES = {"industrial", "warehouse", "factory", "manufacture", "hangar", "service", "storage_tank", "roof"}
SIN_VENTANAS = {"chimney", "tower", "silo", "wall", "bunker"}
# Colores de pared (se multiplican por la textura en el prelight)
TINTES_PISO = [(1.0, 0.96, 0.88), (1.0, 0.88, 0.70), (1.0, 0.80, 0.70), (1.0, 1.0, 1.0), (0.88, 0.88, 0.86),
               (1.0, 0.95, 0.75), (0.88, 0.92, 1.0), (0.95, 0.85, 0.80), (0.90, 0.95, 0.85),
               (1.0, 0.75, 0.60), (0.95, 0.90, 0.70), (1.0, 0.85, 0.85), (0.80, 0.85, 0.80), (1.0, 0.92, 0.60),
               (0.92, 0.80, 0.68), (0.85, 0.88, 0.95)]
TINTES_CASA = [(1.0, 1.0, 1.0), (1.0, 0.95, 0.85), (1.0, 0.90, 0.75), (1.0, 0.85, 0.80)]
SOL = (-0.45, -0.55, 0.70)  # dirección hacia el sol (sureste, alto): da relieve a fachadas y montaña
BRILLO = 0.72  # con 0,85 las fachadas salían quemadas en el juego


def luz(normal, sombra_min=0.5):
    """Factor de luz de una cara según su normal (difusa + ambiente)."""
    lx, ly, lz = SOL
    n = math.sqrt(lx * lx + ly * ly + lz * lz)
    d = (normal[0] * lx + normal[1] * ly + normal[2] * lz) / n
    return sombra_min + (1 - sombra_min) * max(d, 0.0)


def estilo(e, indice):
    """Elige fachada, bajos posibles, tejado y color de cada edificio (repetible: depende del índice)."""
    azar = random.Random(indice)
    tipo = e["tipo"]
    if tipo in SIN_VENTANAS or e.get("base", 0) > 0 or "xemeneie" in e["nombre"].lower():
        return "fa_hormigon", None, "te_nave", (0.95, 0.95, 0.95)
    if tipo in NAVES:
        return "fa_nave", ["ba_nave"], "te_nave", azar.choice([(1, 1, 1), (0.9, 0.95, 1.0), (1.0, 0.95, 0.85)])
    if tipo in CASAS or e["altura"] < 2.5 * PLANTA:
        return "fa_casa", ["ba_portal"], azar.choice(["te_teja", "te_teja", "te_terrado"]), azar.choice(TINTES_CASA)
    # Proporciones según fotos de calle (Mapillary): en Llefià, Gorg y Centre domina el ladrillo visto;
    # las torres altas de Llefià son de ladrillo oscuro
    opciones = ["fa_balcon", "fa_ladrillo", "fa_moderno", "fa_obrero", "fa_ladrillo2", "fa_gres", "fa_estuco", "fa_terraza"]
    if e["altura"] > 8 * PLANTA:
        pesos = [1, 3, 1, 1, 5, 2, 0, 1]
    elif e["altura"] < 4 * PLANTA:
        pesos = [3, 2, 0, 2, 0, 1, 4, 0]
    else:
        pesos = [3, 5, 1, 3, 2, 3, 1, 2]
    fachada = azar.choices(opciones, pesos)[0]
    if fachada in ("fa_ladrillo", "fa_ladrillo2"):
        tinte = azar.choice([(1.0, 0.97, 0.95), (0.95, 0.9, 0.88), (1.0, 1.0, 1.0), (0.9, 0.85, 0.85)])
    else:
        tinte = azar.choice(TINTES_PISO)
    bajos = ["ba_tienda", "ba_persiana", "ba_portal", "ba_tienda", "ba_bar", "ba_farmacia"] \
        if tipo in {"yes", "apartments", "residential", "commercial", "retail"} else ["ba_portal"]
    return fachada, bajos, "te_terrado", tinte


def caja(bm, uv, color_capa, x0, y0, x1, y1, z0, z1, mat_lados, mat_techo, tinte, escala_v=PLANTA):
    """Prisma rectangular alineado con los ejes (casetas de escalera, depósitos)."""
    v = [bm.verts.new(p) for p in ((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                                   (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))]
    caras = [((0, 1, 5, 4), (0, -1, 0)), ((1, 2, 6, 5), (1, 0, 0)), ((2, 3, 7, 6), (0, 1, 0)), ((3, 0, 4, 7), (-1, 0, 0))]
    for indices, normal in caras:
        cara = bm.faces.new([v[i] for i in indices])
        cara.material_index = MAT[mat_lados]
        largo = math.dist(v[indices[0]].co.xy, v[indices[1]].co.xy) / 4.0
        for loop, coord in zip(cara.loops, ((0, 0), (largo, 0), (largo, (z1 - z0) / escala_v), (0, (z1 - z0) / escala_v))):
            loop[uv].uv = coord
        pintar(cara, color_capa, tinte, luz(normal))
    techo = bm.faces.new([v[i] for i in (4, 5, 6, 7)])
    techo.material_index = MAT[mat_techo]
    for loop in techo.loops:
        loop[uv].uv = (loop.vert.co.x / 10.0, loop.vert.co.y / 10.0)
    pintar(techo, color_capa, (1, 1, 1), luz((0, 0, 1)))


def balcones(bm, uv, color_capa, a, b, normal, desde, hasta, tinte, factor, limite, recorrido):
    """Balcones volados en una pared a-b (2D, coordenadas locales): uno por tramo de 4 m y planta,
    centrados en la ventana de la textura (a 2 m del inicio de cada repetición), con losa y
    barandilla. Devuelve cuántos ha puesto."""
    largo = math.dist(a, b)
    ux, uy = (b[0] - a[0]) / largo, (b[1] - a[1]) / largo
    nx, ny = normal[0], normal[1]
    inicio = (2.0 - recorrido) % 4.0 - 1.2
    if inicio < 0:
        inicio += 4.0
    puestos = 0
    planta = desde
    while planta + PLANTA * 0.9 < hasta and puestos < limite:
        t = inicio
        while t + 2.4 <= largo and puestos < limite:
            x0, y0 = a[0] + ux * t, a[1] + uy * t
            x1, y1 = x0 + ux * 2.4, y0 + uy * 2.4
            fx0, fy0, fx1, fy1 = x0 + nx * 0.9, y0 + ny * 0.9, x1 + nx * 0.9, y1 + ny * 0.9
            z, zl = planta, planta + 0.15
            # losa: arriba, abajo y canto
            for quad, mat, n in ((((x0, y0, zl), (x1, y1, zl), (fx1, fy1, zl), (fx0, fy0, zl)), "fa_hormigon", (0, 0, 1)),
                                 (((x0, y0, z), (fx0, fy0, z), (fx1, fy1, z), (x1, y1, z)), "fa_hormigon", (0, 0, -1))):
                cara = bm.faces.new([bm.verts.new(p) for p in quad])
                cara.material_index = MAT[mat]
                for loop, coord in zip(cara.loops, ((0, 0), (0.6, 0), (0.6, 0.2), (0, 0.2))):
                    loop[uv].uv = coord
                pintar(cara, color_capa, (1, 1, 1), luz(n) * (0.7 if n[2] < 0 else 1.0))
            # barandilla delantera (desde el canto de la losa hasta 1 m)
            cara = bm.faces.new([bm.verts.new(p) for p in ((fx0, fy0, z), (fx1, fy1, z), (fx1, fy1, z + 1.0), (fx0, fy0, z + 1.0))])
            cara.material_index = MAT["ba_balcon"]
            for loop, coord in zip(cara.loops, ((0, 0), (0.6, 0), (0.6, 0.33), (0, 0.33))):
                loop[uv].uv = coord
            pintar(cara, color_capa, tinte, factor)
            puestos += 1
            t += 4.0
        planta += PLANTA
    return puestos


def materiales():
    texturas = RAIZ / "datos" / "generado" / "texturas"
    return [material_con_textura(n, texturas / f"{n}.png") for n in TEXTURAS]


def pintar(cara, color_capa, tinte, factor):
    c = (tinte[0] * factor * BRILLO, tinte[1] * factor * BRILLO, tinte[2] * factor * BRILLO, 1.0)
    for loop in cara.loops:
        loop[color_capa] = c


def anadir_edificio(bm, uv, color_capa, e, h, cx, cy, indice):
    pts = [tuple(p) for p in e["planta"]]
    if not es_antihorario(pts):
        pts.reverse()
    fachada, bajos, tejado_tex, tinte = estilo(e, indice)
    azar = random.Random(indice * 7 + 1)
    # Base: la altura más baja del terreno bajo la planta (en cuestas el edificio se mete en el suelo).
    # Las partes 3D que empiezan en alto (e.g. el fuste de una chimenea) llevan "base" sobre el suelo.
    alturas = [altura_terreno(h, x, y) for x, y in pts]
    suelo, suelo_alto = min(alturas), max(alturas)
    elevado = e.get("base", 0.0)
    base = suelo + elevado if elevado > 0 else suelo - 0.5
    techo = suelo + elevado + e["altura"]
    # Planta baja (bajos con tiendas/portales) hasta una planta por encima del punto más alto del suelo
    corte = suelo_alto + PLANTA * 1.15 if bajos else None
    if corte is not None and techo - corte < PLANTA * 0.8:
        corte = None

    abajo = [bm.verts.new((x - cx, y - cy, base)) for x, y in pts]
    medio = [bm.verts.new((x - cx, y - cy, corte)) for x, y in pts] if corte else None
    arriba = [bm.verts.new((x - cx, y - cy, techo)) for x, y in pts]
    # Peto del terrado (pisos y naves): la pared sigue 0,9 m por encima del tejado
    peto = [bm.verts.new((x - cx, y - cy, techo + 0.9)) for x, y in pts] if tejado_tex == "te_terrado" else None
    tejado = bm.faces.new(arriba)
    tejado.material_index = MAT[tejado_tex]
    for loop in tejado.loops:
        loop[uv].uv = (loop.vert.co.x / 10.0, loop.vert.co.y / 10.0)
    pintar(tejado, color_capa, (1.0, 1.0, 1.0), luz((0, 0, 1)))

    detalle = en_detalle(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    quedan_balcones = MAX_BALCONES if detalle and fachada in FACHADAS_CON_BALCON else 0
    recorrido = 0.0
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        largo = math.dist(pts[i], pts[j])
        dx, dy = pts[j][0] - pts[i][0], pts[j][1] - pts[i][1]
        normal = (dy / max(largo, 1e-6), -dx / max(largo, 1e-6), 0.0)  # hacia fuera (planta antihoraria)
        factor = luz(normal)
        u0, u1 = recorrido / 4.0, (recorrido + largo) / 4.0  # textura de fachada cada 4 m
        if medio:
            # bajos: la textura acaba arriba en el corte y se repite hacia abajo si el suelo baja
            baja = bm.faces.new((abajo[i], abajo[j], medio[j], medio[i]))
            baja.material_index = MAT[azar.choice(bajos)]
            v0 = 1.0 - (corte - base) / (PLANTA * 1.15)
            for loop, coord in zip(baja.loops, ((u0, v0), (u1, v0), (u1, 1.0), (u0, 1.0))):
                loop[uv].uv = coord
            pintar(baja, color_capa, (1.0, 1.0, 1.0), factor * 0.9)
        pared = bm.faces.new((medio or abajo)[i:i + 1] + (medio or abajo)[j:j + 1] + [arriba[j], arriba[i]])
        pared.material_index = MAT[fachada]
        inicio = corte if medio else base
        v1 = (techo - inicio) / PLANTA  # una planta por repetición
        for loop, coord in zip(pared.loops, ((u0, 0), (u1, 0), (u1, v1), (u0, v1))):
            loop[uv].uv = coord
        pintar(pared, color_capa, tinte, factor)
        if peto:
            remate = bm.faces.new((arriba[i], arriba[j], peto[j], peto[i]))
            remate.material_index = MAT["fa_hormigon"]
            for loop, coord in zip(remate.loops, ((u0, 0), (u1, 0), (u1, 0.3), (u0, 0.3))):
                loop[uv].uv = coord
            pintar(remate, color_capa, tinte, factor * 0.95)
        if quedan_balcones and largo >= 6.0:
            a = (pts[i][0] - cx, pts[i][1] - cy)
            b = (pts[j][0] - cx, pts[j][1] - cy)
            primera = (corte if medio else base + PLANTA) + PLANTA * 0.05
            quedan_balcones -= balcones(bm, uv, color_capa, a, b, normal, primera, techo - 0.3, tinte, factor,
                                        quedan_balcones, recorrido)
        recorrido += largo

    # Caseta de escalera en el terrado de los pisos de la zona de detalle
    if detalle and peto and e["altura"] > 3 * PLANTA:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        if (max(xs) - min(xs)) > 8 and (max(ys) - min(ys)) > 8 and dentro_planta(pts, mx, my):
            caja(bm, uv, color_capa, mx - cx - 1.6, my - cy - 1.6, mx - cx + 1.6, my - cy + 1.6,
                 techo, techo + 2.6, "fa_hormigon", "te_terrado", tinte)
            if azar.random() < 0.6:  # depósito de agua
                caja(bm, uv, color_capa, mx - cx + 1.8, my - cy - 0.6, mx - cx + 3.0, my - cy + 0.6,
                     techo, techo + 1.3, "fa_hormigon", "fa_hormigon", (0.95, 0.95, 0.95))


def anadir_calles(obj, mats_calle, ruta):
    """Añade al trozo de terreno la calzada, aceras, bordillos y marcas de procesar_calles.py."""
    if not ruta.exists():
        return
    datos = np.load(ruta)
    malla = obj.data
    primero = len(malla.materials)
    for m in mats_calle:
        malla.materials.append(m)
    bm = bmesh.new()
    bm.from_mesh(malla)
    uv = bm.loops.layers.uv["Suelo"]
    ox, oy = obj.location.x, obj.location.y
    verts = [bm.verts.new((x - ox, y - oy, z)) for x, y, z in datos["v"]]
    for tri, uvs, mat in zip(datos["t"], datos["uv"], datos["mat"]):
        try:
            cara = bm.faces.new([verts[i] for i in tri])
        except ValueError:  # triángulo repetido
            continue
        cara.material_index = primero + int(mat)
        for loop, coord in zip(cara.loops, uvs):
            loop[uv].uv = (float(coord[0]), float(coord[1]))
    # procesar_calles.py repite los vértices en cada triángulo: se juntan (las UV van por esquina)
    bmesh.ops.remove_doubles(bm, verts=verts, dist=0.001)
    bm.to_mesh(malla)
    bm.free()


def luz_terreno(malla):
    """Prelight del terreno: sombreado por la pendiente según el sol, y roca en las cuestas fuertes."""
    n = len(malla.polygons)
    normales = np.zeros(n * 3, dtype=np.float32)
    malla.polygons.foreach_get("normal", normales)
    normales = normales.reshape(n, 3)
    sol = np.array(SOL) / np.linalg.norm(SOL)
    factor = 0.45 + 0.55 * np.clip(normales @ sol, 0, 1) / max(sol[2], 1e-6) * 0.75
    factor = np.clip(factor, 0.35, 1.0)
    color = np.stack([factor, factor, factor], 1)
    cuesta = normales[:, 2] < 0.85
    color[cuesta] *= np.array([0.92, 0.85, 0.75])
    color *= BRILLO
    totales = np.zeros(n, dtype=np.int32)
    malla.polygons.foreach_get("loop_total", totales)
    por_loop = np.repeat(np.concatenate([color, np.ones((n, 1))], 1), totales, axis=0)
    attr = malla.color_attributes.get("prelight") or malla.color_attributes.new("prelight", "BYTE_COLOR", "CORNER")
    # "color_srgb" guarda el valor tal cual en el byte (con "color" se aplica gamma y sale casi blanco)
    attr.data.foreach_set("color_srgb", por_loop.astype(np.float32).ravel())


def main():
    bpy.ops.wm.open_mainfile(filepath=str(RAIZ / "blender" / "terreno.blend"))
    h = np.load(RAIZ / "datos" / "elevacion" / "relieve_gta.npy")
    with open(RAIZ / "datos" / "generado" / "edificios.json", encoding="utf-8") as f:
        edificios = json.load(f)

    # Agrupar por trozo según el centro de la planta
    grupos = {}
    for indice, e in enumerate(edificios):
        xs = [p[0] for p in e["planta"]]
        ys = [p[1] for p in e["planta"]]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        if abs(cx) < MITAD and abs(cy) < MITAD:
            grupos.setdefault(trozo_de(cx, cy), []).append((indice, e))

    if "Edificios" in bpy.data.collections:
        bpy.data.collections.remove(bpy.data.collections["Edificios"])
    col = bpy.data.collections.new("Edificios")
    bpy.context.scene.collection.children.link(col)
    mats = materiales()

    def guardar_trozo(bm, nombre, cx, cy):
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.01)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        malla = bpy.data.meshes.new(nombre)
        bm.to_mesh(malla)
        bm.free()
        for mat in mats:
            malla.materials.append(mat)
        obj = bpy.data.objects.new(nombre, malla)
        obj.location = (cx, cy, 0.0)
        col.objects.link(obj)

    def nuevo_bm():
        bm = bmesh.new()
        return bm, bm.loops.layers.uv.new("UVMap"), bm.loops.layers.color.new("prelight")

    hechos = fallidos = 0
    for (f, c), lista in sorted(grupos.items()):
        cx = -MITAD + (c + 0.5) * TAM
        cy = MITAD - (f + 0.5) * TAM
        bm, uv, color_capa = nuevo_bm()
        esquinas, parte = 0, 0
        for indice, e in lista:
            antes = len(bm.faces)
            try:
                anadir_edificio(bm, uv, color_capa, e, h, cx, cy, indice)
                hechos += 1
            except ValueError:  # planta con puntos repetidos
                fallidos += 1
            bm.faces.ensure_lookup_table()
            esquinas += sum(3 * (len(bm.faces[k].verts) - 2) for k in range(antes, len(bm.faces)))
            # Un modelo del juego admite 65.535 vértices: se parte el trozo antes de llegar
            if esquinas > LIMITE_ESQUINAS:
                guardar_trozo(bm, f"bdn_edi_{f:02d}_{c:02d}" + (f"_{parte}" if parte else ""), cx, cy)
                bm, uv, color_capa = nuevo_bm()
                esquinas, parte = 0, parte + 1
        if len(bm.faces):
            guardar_trozo(bm, f"bdn_edi_{f:02d}_{c:02d}" + (f"_{parte}" if parte else ""), cx, cy)
        else:
            bm.free()

    # Textura de suelo de cada trozo de terreno, más sus calles (procesar_calles.py)
    texturas = RAIZ / "datos" / "generado" / "texturas"
    mats_calle = [material_con_textura(n, texturas / f"{n}.png") for n in CALLE]
    suelo = RAIZ / "datos" / "generado" / "suelo"
    for obj in bpy.data.collections["Terreno"].objects:
        f, c = obj.name.split("_")[2:4]
        ruta = suelo / f"suelo_{f}_{c}.png"
        if not ruta.exists():
            continue
        mat = material_con_textura(f"bdn_suelo_{f}_{c}", ruta)
        # El suelo usa UV propias de 0 a 1 en cada trozo
        malla = obj.data
        uvsuelo = malla.uv_layers.get("Suelo") or malla.uv_layers.new(name="Suelo")
        for loop in malla.loops:
            co = malla.vertices[loop.vertex_index].co
            uvsuelo.data[loop.index].uv = (co.x / TAM + 0.5, co.y / TAM + 0.5)
        malla.uv_layers.active = uvsuelo
        # Solo una capa UV: el juego usa la primera y la de blender_terreno.py repite la textura
        for capa in [c for c in malla.uv_layers if c.name != "Suelo"]:
            malla.uv_layers.remove(capa)
        malla.materials.clear()
        malla.materials.append(mat)
        anadir_calles(obj, mats_calle, RAIZ / "datos" / "generado" / "calles" / f"calle_{f}_{c}.npz")
        luz_terreno(malla)

    bpy.ops.wm.save_as_mainfile(filepath=str(RAIZ / "blender" / "badalona.blend"))
    tris = sum(len(o.data.polygons) for o in col.objects)
    print(f"EDIFICIOS: {hechos} levantados, {fallidos} descartados, {len(col.objects)} trozos, {tris} triángulos")


main()
