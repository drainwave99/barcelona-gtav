"""Exporta blender/badalona.blend a modelos de GTA SA con DragonFF.

Uso (sin --factory-startup, para que cargue DragonFF):
  blender --background --python herramientas/blender_exportar.py

Salidas en mod/modelos/:
  <modelo>.dff                 un modelo por trozo de terreno / edificios
  bdn_col_FF.col               colisiones de cada fila de trozos (varios modelos COL3 por archivo)
y datos/generado/posiciones.json con la posición de cada modelo para el .ipl.

En la colisión de SA los vértices se guardan en enteros de 1/128 m: solo caben ±256 m alrededor del
origen del modelo. Por eso cada modelo lleva el origen a media altura de su trozo.
"""
import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "mod" / "modelos"
LIMITE_COL = 255.0
LUZ_DIA = (0.75, 0.75, 0.75, 1.0)  # color de vértices (prelight) para que el juego no lo pinte negro


def cargar_dragonff():
    import addon_utils

    for nombre in ("bl_ext.user_default.dragonff", "DragonFF"):
        try:
            if nombre not in bpy.context.preferences.addons:
                addon_utils.enable(nombre, default_set=False)
            return __import__(nombre + ".ops.col_exporter", fromlist=["export_col"])
        except ImportError:
            continue
    sys.exit("ERROR: DragonFF no está instalado en Blender")


def preparar(obj):
    malla = obj.data
    zs = [v.co.z for v in malla.vertices]
    zc = (min(zs) + max(zs)) / 2
    malla.transform(Matrix.Translation((0, 0, -zc)))
    obj.location.z += zc
    if (max(zs) - min(zs)) / 2 > 250:
        print(f"AVISO: {obj.name} mide {max(zs) - min(zs):.0f} m de alto, la colisión puede cortarse")
    if "prelight" not in malla.color_attributes:
        attr = malla.color_attributes.new("prelight", "BYTE_COLOR", "CORNER")
        attr.data.foreach_set("color", LUZ_DIA * len(attr.data))
    obj.dff.type = "OBJ"
    obj.dff.day_cols = True


def exportar_dff(obj):
    posicion = obj.location.copy()
    obj.location = (0, 0, 0)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_dff.scene(filepath=str(SALIDA / f"{obj.name}.dff"), directory=str(SALIDA),
                             only_selected=True, export_coll=False, export_version="0x36003")
    obj.location = posicion


def colision(col_exporter, obj):
    """Devuelve el modelo COL3 (bytes) del objeto, con el mismo nombre que el .dff."""
    coleccion = bpy.data.collections.new(obj.name)
    bpy.context.scene.collection.children.link(coleccion)
    malla = obj.data
    fuera = [v.index for v in malla.vertices if max(abs(c) for c in v.co) > LIMITE_COL]
    if fuera:
        # Caras fuera del rango de la colisión (edificios enormes en el borde del trozo): sin colisión
        bm = bmesh.new()
        bm.from_mesh(malla)
        indices = set(fuera)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if any(v.index in indices for v in f.verts)], context="FACES")
        malla = bpy.data.meshes.new(obj.name + "_col")
        bm.to_mesh(malla)
        bm.free()
        print(f"AVISO: {obj.name}: {len(fuera)} vértices fuera de ±{LIMITE_COL} m sin colisión")
    copia = bpy.data.objects.new(obj.name + "_col", malla)
    copia.dff.type = "COL"
    coleccion.objects.link(copia)
    coleccion.dff.auto_bounds = True
    datos = col_exporter.export_col({
        "file_name": None, "version": 3, "collection": coleccion, "apply_transformations": False,
        "only_selected": False, "clean_mesh": True, "export_face_groups": False,
    })
    bpy.data.objects.remove(copia)
    bpy.data.collections.remove(coleccion)
    return datos


def main():
    col_exporter = cargar_dragonff()
    bpy.ops.wm.open_mainfile(filepath=str(RAIZ / "blender" / "badalona.blend"))
    SALIDA.mkdir(parents=True, exist_ok=True)

    objetos = [o for nombre in ("Terreno", "Edificios") for o in bpy.data.collections[nombre].objects]
    objetos.sort(key=lambda o: o.name)
    posiciones, filas = {}, {}
    for i, obj in enumerate(objetos):
        preparar(obj)
        exportar_dff(obj)
        fila = obj.name.split("_")[2]
        filas.setdefault(fila, []).append(colision(col_exporter, obj))
        posiciones[obj.name] = [round(v, 3) for v in obj.location]
        if i % 50 == 0:
            print(f"EXPORT: {i + 1}/{len(objetos)} {obj.name}")

    for fila, modelos in filas.items():
        (SALIDA / f"bdn_col_{fila}.col").write_bytes(b"".join(modelos))
    with open(RAIZ / "datos" / "generado" / "posiciones.json", "w", encoding="utf-8") as fh:
        json.dump(posiciones, fh, indent=0)
    print(f"EXPORT: {len(objetos)} modelos .dff y {len(filas)} archivos .col en {SALIDA}")


main()
