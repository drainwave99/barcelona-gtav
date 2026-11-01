"""Render rápido de blender/badalona.blend para ver el resultado (docs/render_*.png).

Uso: blender --background --python herramientas/blender_render.py
"""
import math
from pathlib import Path

import bpy
from mathutils import Vector

RAIZ = Path(__file__).resolve().parent.parent

# nombre: (posición de la cámara, punto al que mira), en coordenadas GTA
VISTAS = {
    "centre": ((-700, -2650, 160), (-50, -1500, 10)),        # desde el mar hacia Dalt la Vila
    "canyet": ((600, -200, 380), (1700, 1300, 150)),        # hacia Canyet y Can Ruti
    "xemeneies": ((-1700, -2950, 60), (-2315, -2693, 80)),  # Tres Xemeneies desde la playa
}


def main():
    bpy.ops.wm.open_mainfile(filepath=str(RAIZ / "blender" / "badalona.blend"))
    escena = bpy.context.scene
    escena.render.engine = "BLENDER_WORKBENCH"
    escena.display.shading.light = "STUDIO"
    escena.display.shading.color_type = "TEXTURE"
    escena.display.shading.show_shadows = True
    escena.render.resolution_x, escena.render.resolution_y = 1600, 900
    escena.world = escena.world or bpy.data.worlds.new("Mundo")
    escena.world.color = (0.55, 0.7, 0.9)

    # Mar plano a nivel 0
    bpy.ops.mesh.primitive_plane_add(size=6000, location=(0, 0, 0.0))
    mar = bpy.context.object
    mat = bpy.data.materials.new("mar")
    mat.diffuse_color = (0.12, 0.3, 0.5, 1)
    mar.data.materials.append(mat)

    cam_datos = bpy.data.cameras.new("cam")
    cam_datos.lens = 28
    cam_datos.clip_end = 10000
    cam = bpy.data.objects.new("cam", cam_datos)
    escena.collection.objects.link(cam)
    escena.camera = cam

    for nombre, (pos, mira) in VISTAS.items():
        cam.location = pos
        cam.rotation_euler = (Vector(mira) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
        escena.render.filepath = str(RAIZ / "docs" / f"render_{nombre}.png")
        bpy.ops.render.render(write_still=True)
        print(f"RENDER: {escena.render.filepath}")


main()
