"""Blender: importa bcn_p_prueba.ydr.xml (Sollumz) con un suelo del LiDAR y renderiza desde un punto.

blender -b --python vista_puente.py -- <carpeta_xml> <salida.png> cx,cy,cz mx,my,mz [lente]
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
xml, salida = Path(args[0]), args[1]
cam_pos = Vector([float(x) for x in args[2].split(",")])
mira = Vector([float(x) for x in args[3].split(",")])
lente = float(args[4]) if len(args) > 4 else 24
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
bpy.ops.sollumz.import_assets(directory=str(xml), files=[{"name": "bcn_p_prueba.ydr.xml"}])
dds = {p.stem: p for p in xml.glob("*.ytd/*.dds")}
for img in bpy.data.images:
    nombre = img.name.split(".")[0]
    if nombre in dds:
        img.filepath = str(dds[nombre])
        img.source = "FILE"
        img.reload()
# suelo
d = np.load(xml / "suelo.npz")
e, n, z = d["e"], d["n"], np.nan_to_num(d["z"], nan=float(np.nanmedian(d["z"])))
ge, gn = np.meshgrid(e, n)
verts = list(zip(ge.ravel(), gn.ravel(), z.ravel()))
w = len(e)
caras = [(f * w + c, f * w + c + 1, (f + 1) * w + c + 1, (f + 1) * w + c) for f in range(len(n) - 1) for c in range(w - 1)]
malla = bpy.data.meshes.new("suelo")
malla.from_pydata(verts, [], caras)
suelo = bpy.data.objects.new("suelo", malla)
bpy.context.scene.collection.objects.link(suelo)
mat = bpy.data.materials.new("suelo")
mat.diffuse_color = (0.35, 0.33, 0.3, 1)
suelo.data.materials.append(mat)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
bpy.context.scene.collection.objects.link(cam)
cam.location = cam_pos
cam.rotation_euler = (mira - cam_pos).to_track_quat("-Z", "Y").to_euler()
cam.data.lens = lente
cam.data.clip_end = 6000
sc = bpy.context.scene
sc.camera = cam
sc.render.engine = "BLENDER_EEVEE"
sol = bpy.data.objects.new("sol", bpy.data.lights.new("sol", "SUN"))
sol.data.energy = 4
sol.rotation_euler = (math.radians(40), 0, math.radians(140))
sc.collection.objects.link(sol)
sc.world = bpy.data.worlds.new("w")
sc.world.color = (0.55, 0.65, 0.8)
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
sc.render.filepath = salida
bpy.ops.render.render(write_still=True)
print("RENDER", salida)
