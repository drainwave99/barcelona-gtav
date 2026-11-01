"""Importa con Sollumz unos .ydr.xml del prototipo y renderiza una vista (comprobación sin el juego)."""
import bpy, sys, math
from pathlib import Path
args = sys.argv[sys.argv.index("--") + 1:]
xml, salida, casillas = Path(args[0]), args[1], args[2].split(",")
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
archivos = [f"bcn_{t}_{c}.ydr.xml" for c in casillas for t in ("t", "r", "e", "p") if (xml / f"bcn_{t}_{c}.ydr.xml").exists()]
bpy.ops.sollumz.import_assets(directory=str(xml), files=[{"name": f} for f in archivos])
dds = {p.stem: p for p in xml.glob("*.ytd/*.dds")}
for img in bpy.data.images:
    nombre = img.name.split(".")[0]
    if nombre in dds or nombre == "fa_piezas":
        img.filepath = str(dds.get(nombre, xml / "bcn_fachadas.ytd" / "fa_piezas.dds")); img.source = "FILE"; img.reload()
        print("IMG", nombre, tuple(img.size), img.has_data)
for m in bpy.data.materials:
    if m.node_tree and "DiffuseSampler" in m.node_tree.nodes:
        m.node_tree.nodes.active = m.node_tree.nodes["DiffuseSampler"]
# Colocar cada casilla en su sitio (los modelos están centrados en su casilla de 250 m)
for o in bpy.data.objects:
    if o.parent is None and o.name.startswith("bcn_"):
        e, n = o.name.split(".")[0].split("_")[2:4]
        o.location = (int(e) * 10, int(n) * 10, 0)
xs = [o.location.x for o in bpy.data.objects if o.parent is None]
ys = [o.location.y for o in bpy.data.objects if o.parent is None]
cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
bpy.context.scene.collection.objects.link(cam)
cam.location = (cx - 40, cy - 60, 72)
cam.rotation_euler = (math.radians(80), 0, math.radians(-30))
cam.data.lens = 24
cam.data.clip_end = 5000
sc = bpy.context.scene
sc.camera = cam
sc.render.engine = "BLENDER_EEVEE"
sun = bpy.data.objects.new("sol", bpy.data.lights.new("sol", "SUN")); sun.data.energy = 4; sun.rotation_euler = (0.7, 0.2, 0.9); sc.collection.objects.link(sun)
sc.world = bpy.data.worlds.new("w"); sc.world.color = (0.6, 0.7, 0.85)
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "TEXTURE"
sc.display.shading.show_shadows = True
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
sc.render.filepath = salida
bpy.ops.render.render(write_still=True)
print("RENDER", salida, len(bpy.data.objects))
