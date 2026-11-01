import bpy, sys
from pathlib import Path
salida = Path(sys.argv[-1])
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
from bl_ext.user_default.sollumz.ydr.shader_materials import create_shader
from bl_ext.user_default.sollumz.tools.boundhelper import convert_obj_to_composite
from bl_ext.user_default.sollumz.ybn.collision_materials import create_collision_material_from_index
from bl_ext.user_default.sollumz.sollumz_properties import SollumType
bpy.ops.mesh.primitive_cube_add(size=4)
cubo = bpy.context.active_object
cubo.name = "bdn_prueba"
cubo.data.uv_layers[0].name = "UVMap 0"
cubo.data.color_attributes.new("Color 1", "BYTE_COLOR", "CORNER")
mat = create_shader("default.sps")
img = bpy.data.images.new("bdn_prueba_tex", 64, 64)
img.pixels = [0.8, 0.3, 0.2, 1.0] * 64 * 64
img.filepath_raw = str(salida.parent / "bdn_prueba_tex.png"); img.file_format = "PNG"; img.save()
for n in mat.node_tree.nodes:
    if n.type == "TEX_IMAGE" and n.name == "DiffuseSampler":
        n.image = img
cubo.data.materials.append(mat)
col = cubo.copy(); col.data = cubo.data.copy(); bpy.context.collection.objects.link(col); col.name = "bdn_prueba_col"
col.data.materials.clear(); col.data.materials.append(create_collision_material_from_index(28))
bpy.context.view_layer.objects.active = cubo
bpy.ops.sollumz.converttodrawable()
comp = convert_obj_to_composite(col, SollumType.BOUND_GEOMETRYBVH)
comp.parent = None
for o in bpy.data.objects: o.select_set(o.parent is None)
r = bpy.ops.sollumz.export_assets(directory=str(salida), direct_export=True, use_custom_settings=True, target_formats={"CWXML"}, target_versions={"GEN8"})
print("EXPORT", r, sorted(str(p.relative_to(salida)) for p in salida.rglob("*")))
