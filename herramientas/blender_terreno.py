"""Genera el terreno del mapa en Blender, dividido en trozos listos para exportar a GTA con DragonFF.

Uso (sin abrir la interfaz):
  blender --background --factory-startup --python herramientas/blender_terreno.py

Lee datos/elevacion/relieve_gta.npy y guarda blender/terreno.blend.
Cada trozo es un objeto "bdn_ter_FF_CC" con el origen en su centro (las posiciones van luego al .ipl).
"""
from pathlib import Path

import bmesh
import bpy
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
LADO = 6000.0
MITAD = LADO / 2
TROZOS = 16  # 16x16 trozos de 375 m
PASO_PX = 4  # 1 vértice cada 4 píxeles del heightmap (~11,7 m), parecido al terreno original de SA


def crear_trozo(h, fila, col, paso_m, px_trozo, material):
    f0, c0 = fila * px_trozo, col * px_trozo
    sub = h[f0:f0 + px_trozo + 1:PASO_PX, c0:c0 + px_trozo + 1:PASO_PX]
    n = sub.shape[0]
    tam = LADO / TROZOS
    cx = -MITAD + (col + 0.5) * tam
    cy = MITAD - (fila + 0.5) * tam

    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    verts = [[None] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            x = -tam / 2 + j * paso_m * PASO_PX
            y = tam / 2 - i * paso_m * PASO_PX
            verts[i][j] = bm.verts.new((x, y, float(sub[i, j])))
    for i in range(n - 1):
        for j in range(n - 1):
            cara = bm.faces.new((verts[i + 1][j], verts[i + 1][j + 1], verts[i][j + 1], verts[i][j]))
            for loop in cara.loops:
                # textura repetida cada 20 m, en coordenadas del mundo para que no haya cortes entre trozos
                co = loop.vert.co
                loop[uv].uv = ((co.x + cx) / 20.0, (co.y + cy) / 20.0)

    nombre = f"bdn_ter_{fila:02d}_{col:02d}"
    malla = bpy.data.meshes.new(nombre)
    bm.to_mesh(malla)
    bm.free()
    malla.materials.append(material)
    obj = bpy.data.objects.new(nombre, malla)
    obj.location = (cx, cy, 0.0)
    return obj


def main():
    h = np.load(RAIZ / "datos" / "elevacion" / "relieve_gta.npy")
    px_total = h.shape[0] - 1  # 2048
    px_trozo = px_total // TROZOS
    paso_m = LADO / px_total

    bpy.ops.wm.read_factory_settings(use_empty=True)
    col = bpy.data.collections.new("Terreno")
    bpy.context.scene.collection.children.link(col)

    mat = bpy.data.materials.new("bdn_suelo")
    mat.diffuse_color = (0.35, 0.45, 0.25, 1.0)

    for fila in range(TROZOS):
        for c in range(TROZOS):
            col.objects.link(crear_trozo(h, fila, c, paso_m, px_trozo, mat))

    salida = RAIZ / "blender" / "terreno.blend"
    salida.parent.mkdir(exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(salida))
    tris = sum(len(o.data.polygons) * 2 for o in col.objects)
    print(f"TERRENO: {len(col.objects)} trozos, {tris} triángulos -> {salida}")


main()
