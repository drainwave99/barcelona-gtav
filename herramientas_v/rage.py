"""Escritura de los formatos de GTA V en el XML de CodeWalker (cwtool lo pasa luego a binario).

  ydr  modelo: geometrías con posición, normal, color de vértice y UV          escribir_ydr
  ybn  colisión: malla BVH con material por triángulo                         escribir_ybn
  ytd  diccionario de texturas: DDS DXT1/DXT5 con mipmaps                     escribir_ytd
  ytyp / ymap  arquetipos y colocación: con szio (la librería de Sollumz)     escribir_ytyp, escribir_ymap

Las plantillas de referencia, exportadas con Sollumz, están en plantillas/.
Coordenadas: metros, X este, Y norte, Z arriba (como el mapa de GTA V).
"""
import shutil
import io
import struct
import subprocess
import zlib
import sys
from pathlib import Path

import numpy as np
from PIL import Image

AQUI = Path(__file__).resolve().parent
SZIO = Path.home() / "AppData/Roaming/Blender Foundation/Blender/5.2/extensions/.user/user_default/sollumz/lib/python3.13/site-packages"
DOTNET = Path.home() / "AppData/Local/Microsoft/dotnet/dotnet.exe"
if not DOTNET.exists():  # instalado para todo el equipo o en el PATH
    DOTNET = Path(shutil.which("dotnet") or "dotnet")
CWTOOL = AQUI / "cwtool" / "bin" / "cwtool.dll"

# Materiales de colisión (índices de la lista de Sollumz / CodeWalker)
MAT_DEFAULT, MAT_CONCRETE, MAT_TARMAC, MAT_ROCK, MAT_STONE, MAT_BRICK, MAT_PAVING = 0, 1, 4, 9, 11, 13, 15
MAT_DIRT_TRACK, MAT_SOIL, MAT_GRASS_LONG, MAT_GRASS, MAT_GRASS_SHORT, MAT_BUSHES = 35, 43, 46, 47, 48, 50
MAT_ROOF_TILE, MAT_ROOF_FELT, MAT_PLASTER, MAT_WATER, MAT_PAVEMENT = 82, 83, 101, 125, 174


def _num(a, fmt):
    return "\n".join(" ".join(fmt % v for v in fila) for fila in a)


def _caja(v):
    lo, hi = v.min(axis=0), v.max(axis=0)
    centro = (lo + hi) / 2
    radio = float(np.linalg.norm(v - centro, axis=1).max())
    return lo, hi, centro, radio


def _vec(nombre, v, sangria):
    return f'{sangria}<{nombre} x="{v[0]:.4f}" y="{v[1]:.4f}" z="{v[2]:.4f}" />'


def escribir_ydr(ruta, nombre, geometrias, distancia=500.0):
    """geometrias: lista de dict con
         textura  nombre de la textura (en el .ytd del arquetipo)
         v        (n, 3) posiciones         n  (n, 3) normales
         uv       (n, 2) UV (v hacia arriba, como en Blender)
         color    (n, 4) uint8 color de vértice (luz horneada / tinte)
         i        (m, 3) índices de triángulo
         recorte  (opcional) True: shader cutout_fence, con transparencia por alfa (barandillas, rejas)
    Si no, shader "default". Máximo 65535 vértices por geometría."""
    todos = np.concatenate([g["v"] for g in geometrias])
    lo, hi, centro, radio = _caja(todos)
    s = ['<?xml version="1.0" encoding="UTF-8"?>', "<Drawable>", f"  <Name>{nombre}</Name>",
         _vec("BoundingSphereCenter", centro, "  "), f'  <BoundingSphereRadius value="{radio:.4f}" />',
         _vec("BoundingBoxMin", lo, "  "), _vec("BoundingBoxMax", hi, "  ")]
    for nivel in ("High", "Med", "Low", "Vlow"):
        s.append(f'  <LodDist{nivel} value="{distancia if nivel == "High" else 9998}" />')
    s += ['  <FlagsHigh value="1" />', '  <FlagsMed value="0" />', '  <FlagsLow value="0" />', '  <FlagsVlow value="0" />',
          "  <ShaderGroup>", "    <Shaders>"]
    for g in geometrias:
        if g.get("recorte"):
            s += ["      <Item>", "        <Name>cutout_fence</Name>", "        <FileName>cutout_fence.sps</FileName>",
                  '        <RenderBucket value="3" />', "        <Parameters>",
                  f'          <Item name="DiffuseSampler" type="Texture"><Name>{g["textura"]}</Name></Item>',
                  '          <Item name="HardAlphaBlend" type="Vector" x="1.0" y="0.0" z="0.0" w="0.0" />',
                  '          <Item name="useTessellation" type="Vector" x="0.0" y="0.0" z="0.0" w="0.0" />',
                  "        </Parameters>", "      </Item>"]
            continue
        s += ["      <Item>", "        <Name>default</Name>", "        <FileName>default.sps</FileName>",
              '        <RenderBucket value="0" />', "        <Parameters>",
              f'          <Item name="DiffuseSampler" type="Texture"><Name>{g["textura"]}</Name></Item>',
              '          <Item name="matMaterialColorScale" type="Vector" x="1.0" y="0.0" z="0.0" w="1.0" />',
              '          <Item name="HardAlphaBlend" type="Vector" x="1.0" y="0.0" z="0.0" w="0.0" />',
              '          <Item name="useTessellation" type="Vector" x="0.0" y="0.0" z="0.0" w="0.0" />',
              '          <Item name="wetnessMultiplier" type="Vector" x="1.0" y="0.0" z="0.0" w="0.0" />',
              '          <Item name="globalAnimUV1" type="Vector" x="0.0" y="1.0" z="0.0" w="0.0" />',
              '          <Item name="globalAnimUV0" type="Vector" x="1.0" y="0.0" z="0.0" w="0.0" />',
              "        </Parameters>", "      </Item>"]
    s += ["    </Shaders>", "  </ShaderGroup>", "  <DrawableModelsHigh>", "    <Item>",
          '      <RenderMask value="255" />', '      <Flags value="0" />', '      <HasSkin value="0" />',
          '      <BoneIndex value="0" />', '      <Unknown1 value="0" />', "      <Geometries>"]
    for k, g in enumerate(geometrias):
        v = np.asarray(g["v"], dtype=np.float64)
        if len(v) > 65535:
            raise ValueError(f"{nombre}: {len(v)} vértices en una geometría (máx. 65535)")
        glo, ghi, _, _ = _caja(v)
        uv = np.asarray(g["uv"], dtype=np.float64).copy()
        uv[:, 1] = 1 - uv[:, 1]  # el juego tiene la v hacia abajo
        col = np.asarray(g["color"], dtype=np.int64)
        datos = "\n".join(
            f"{a[0]:.4f} {a[1]:.4f} {a[2]:.4f}   {b[0]:.4f} {b[1]:.4f} {b[2]:.4f}   {c[0]} {c[1]} {c[2]} {c[3]}   {d[0]:.5f} {d[1]:.5f}"
            for a, b, c, d in zip(v, np.asarray(g["n"], dtype=np.float64), col, uv))
        indices = np.asarray(g["i"]).ravel()
        s += ["        <Item>", f'          <ShaderIndex value="{k}" />', _vec("BoundingBoxMin", glo, "          "),
              _vec("BoundingBoxMax", ghi, "          "), "          <VertexBuffer>", '            <Flags value="0" />',
              '            <Layout type="GTAV1">', "              <Position />", "              <Normal />",
              "              <Colour0 />", "              <TexCoord0 />", "            </Layout>",
              "            <Data>", datos, "            </Data>", "          </VertexBuffer>",
              "          <IndexBuffer>", "            <Data>",
              "\n".join(" ".join(map(str, indices[j:j + 24])) for j in range(0, len(indices), 24)),
              "            </Data>", "          </IndexBuffer>", "        </Item>"]
    s += ["      </Geometries>", "    </Item>", "  </DrawableModelsHigh>", "</Drawable>"]
    Path(ruta).write_text("\n".join(s), encoding="utf-8")


def escribir_ybn(ruta, v, tris, materiales, mats_tri):
    """Colisión de una malla: v (n, 3), tris (m, 3), materiales: lista de índices de material de
    colisión, mats_tri (m,) índice en esa lista para cada triángulo."""
    v = np.asarray(v, dtype=np.float64)
    tris = np.asarray(tris).reshape(-1, 3)
    mats_tri = np.asarray(mats_tri).reshape(-1)
    lo, hi, centro, radio = _caja(v)
    s = ['<?xml version="1.0" encoding="UTF-8"?>', "<BoundsFile>", '  <Bounds type="Composite">']
    margen = np.array([0.04, 0.04, 0.04])

    def cabecera(sangria, lo, hi, centro, radio, margin):
        return [_vec("BoxMin", lo, sangria), _vec("BoxMax", hi, sangria), _vec("BoxCenter", centro, sangria),
                _vec("SphereCenter", centro, sangria), f'{sangria}<SphereRadius value="{radio:.4f}" />',
                f'{sangria}<Margin value="{margin}" />', f'{sangria}<Volume value="1" />',
                f'{sangria}<Inertia x="1.0" y="1.0" z="1.0" />', f'{sangria}<MaterialIndex value="0" />',
                f'{sangria}<MaterialColourIndex value="0" />', f'{sangria}<ProceduralID value="0" />',
                f'{sangria}<RoomID value="0" />', f'{sangria}<PedDensity value="0" />',
                f'{sangria}<UnkFlags value="0" />', f'{sangria}<PolyFlags value="0" />', f'{sangria}<UnkType value="1" />']
    s += cabecera("    ", lo - margen, hi + margen, centro, radio + 0.07, 0)
    s += ["    <Children>"]
    for pv, pt, pm in _trozos_colision(v, tris, mats_tri):
        s += _hijo_bvh(cabecera, pv, pt, pm, materiales, margen)
    s += ["    </Children>", "  </Bounds>", "</BoundsFile>"]
    Path(ruta).write_text("\n".join(s), encoding="utf-8")


MAX_VERTICES_BVH = 32000  # los índices de vértice de los polígonos de colisión son de 15 bits


def _trozos_colision(v, tris, mats_tri):
    """Vértices repetidos fundidos y la malla partida en trozos de < 32768 vértices (por franjas
    espaciales, para que cada trozo tenga una caja pequeña). Si no, el juego no choca con nada."""
    clave = np.round(v, 3)
    unicos, inv = np.unique(clave, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    t = inv[tris]
    if len(unicos) <= MAX_VERTICES_BVH:
        return [(unicos, t, mats_tri)]
    centros = unicos[t].mean(1)
    eje = int(np.argmax(np.ptp(centros[:, :2], axis=0)))
    orden = np.argsort(centros[:, eje], kind="stable")
    out, ini = [], 0
    while ini < len(orden):
        # el trozo más largo que cabe: como mucho 3 vértices nuevos por triángulo
        fin = min(len(orden), ini + MAX_VERTICES_BVH // 3)
        while True:
            sel = orden[ini:fin]
            usados, local = np.unique(t[sel], return_inverse=True)
            if len(usados) <= MAX_VERTICES_BVH or fin - ini <= 1:
                break
            fin = ini + (fin - ini) * 9 // 10
        siguiente = fin
        while siguiente < len(orden):  # se alarga mientras quepa
            prueba = min(len(orden), siguiente + 2000)
            u2 = np.unique(t[orden[ini:prueba]])
            if len(u2) > MAX_VERTICES_BVH:
                break
            siguiente = prueba
        sel = orden[ini:siguiente]
        usados, local = np.unique(t[sel], return_inverse=True)
        out.append((unicos[usados], local.reshape(-1, 3), mats_tri[sel]))
        ini = siguiente
    return out


def _hijo_bvh(cabecera, v, tris, mats_tri, materiales, margen):
    lo, hi, centro, radio = _caja(v)
    centro_geo = (lo + hi) / 2
    s = ['      <Item type="GeometryBVH">']
    s += cabecera("        ", lo - margen, hi + margen, centro, radio, 0.04)
    s += ["        <CompositeTransform>", "          1 0 0 0", "          0 1 0 0", "          0 0 1 0",
          "          0 0 0 1", "        </CompositeTransform>",
          # con qué choca (los mismos que la colisión del mapa del juego): sin esto el juego la ignora
          "        <CompositeFlags1>MAP_WEAPON, MAP_DYNAMIC, MAP_ANIMAL, MAP_COVER, MAP_VEHICLE</CompositeFlags1>",
          "        <CompositeFlags2>VEHICLE_NOT_BVH, VEHICLE_BVH, PED, RAGDOLL, ANIMAL, ANIMAL_RAGDOLL, OBJECT, PLANT, "
          "PROJECTILE, EXPLOSION, FORKLIFT_FORKS, TEST_WEAPON, TEST_CAMERA, TEST_AI, TEST_SCRIPT, TEST_VEHICLE_WHEEL, "
          "GLASS</CompositeFlags2>",
          _vec("GeometryCenter", centro_geo, "        "),
          "        <Materials>"]
    for m in materiales:
        s += ["          <Item>", f'            <Type value="{m}" />', '            <ProceduralID value="0" />',
              '            <RoomID value="0" />', '            <PedDensity value="0" />', "            <Flags>NONE</Flags>",
              '            <MaterialColourIndex value="0" />', '            <Unk value="0" />', "          </Item>"]
    s += ["        </Materials>", "        <Vertices>",
          "\n".join(f"          {a:.4f}, {b:.4f}, {c:.4f}" for a, b, c in v - centro_geo),
          "        </Vertices>", "        <Polygons>"]
    s += [f'          <Triangle m="{m}" v1="{a}" v2="{b}" v3="{c}" f1="0" f2="0" f3="0" />'
          for (a, b, c), m in zip(np.asarray(tris), np.asarray(mats_tri))]
    s += ["        </Polygons>", "      </Item>"]
    return s


def dds_con_mips(imagen, ruta, alfa=False):
    """DDS DXT1 (o DXT5 con alfa) con toda la cadena de mipmaps; lado potencia de 2."""
    imagen = imagen.convert("RGBA" if alfa else "RGB")
    niveles, w, h = [], *imagen.size
    while True:
        b = io.BytesIO()
        imagen.resize((w, h), Image.LANCZOS).save(b, format="DDS", pixel_format="DXT5" if alfa else "DXT1")
        niveles.append(b.getvalue())
        if w == 1 and h == 1 or w < 4 and h < 4:
            break
        w, h = max(w // 2, 1), max(h // 2, 1)
    cab = bytearray(niveles[0][:128])
    struct.pack_into("<I", cab, 8, struct.unpack_from("<I", cab, 8)[0] | 0x20000)  # DDSD_MIPMAPCOUNT
    struct.pack_into("<I", cab, 28, len(niveles))
    struct.pack_into("<I", cab, 108, struct.unpack_from("<I", cab, 108)[0] | 0x400008)  # COMPLEX | MIPMAP
    Path(ruta).write_bytes(bytes(cab) + b"".join(n[128:] for n in niveles))


def escribir_ytd(ruta_xml, texturas):
    """texturas: {nombre: (imagen PIL, alfa)}. Los .dds van en una carpeta con el nombre del ytd."""
    ruta_xml = Path(ruta_xml)
    carpeta = ruta_xml.with_name(ruta_xml.name[:-len(".xml")])
    carpeta.mkdir(parents=True, exist_ok=True)
    s = ['<?xml version="1.0" encoding="UTF-8"?>', "<TextureDictionary>"]
    for nombre, (imagen, alfa) in texturas.items():
        dds_con_mips(imagen, carpeta / f"{nombre}.dds", alfa)
        w, h = imagen.size
        s += ["  <Item>", f"    <Name>{nombre}</Name>", '    <Unk32 value="128" />', "    <Usage>DEFAULT</Usage>",
              "    <UsageFlags>UNK19</UsageFlags>", '    <ExtraFlags value="0" />', f'    <Width value="{w}" />',
              f'    <Height value="{h}" />', '    <MipLevels value="1" />',
              f"    <Format>D3DFMT_{'DXT5' if alfa else 'DXT1'}</Format>", f"    <FileName>{nombre}.dds</FileName>", "  </Item>"]
    s.append("</TextureDictionary>")
    ruta_xml.write_text("\n".join(s), encoding="utf-8")


def _szio():
    if str(SZIO) not in sys.path:
        sys.path.append(str(SZIO))
    import szio.gta5 as g
    return g


def a_binario(carpeta_xml, carpeta_bin):
    r = subprocess.run([str(DOTNET), str(CWTOOL), "xml", str(carpeta_xml), str(carpeta_bin)],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode:
        raise SystemExit(r.stderr)


def empaquetar_rpf(carpeta, archivo):
    r = subprocess.run([str(DOTNET), str(CWTOOL), "rpf", str(carpeta), str(archivo)], capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode:
        raise SystemExit(r.stderr)


def caja_ydr(ruta_xml):
    """BoundingBoxMin/Max del primer bloque de un .ydr.xml escrito por escribir_ydr."""
    import re
    texto = Path(ruta_xml).read_text(encoding="utf-8")[:2000]
    lo = re.search(r'<BoundingBoxMin x="([^"]+)" y="([^"]+)" z="([^"]+)"', texto).groups()
    hi = re.search(r'<BoundingBoxMax x="([^"]+)" y="([^"]+)" z="([^"]+)"', texto).groups()
    return np.array(lo, float), np.array(hi, float)


def _xyz(etiqueta, v):
    return f'<{etiqueta} x="{v[0]:.4f}" y="{v[1]:.4f}" z="{v[2]:.4f}" />'


# Con el formato exacto de los ymap/ytyp del juego exportados por CodeWalker (patch2026_01): los que escribía
# szio no llevaban instancedData, containerLods, extensions... y el juego no los cargaba.
YTYP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<CMapTypes>
 <extensions />
 <archetypes>
{arquetipos}
 </archetypes>
 <name>{nombre}</name>
 <dependencies />
 <compositeEntityTypes itemType="CCompositeEntityType" />
</CMapTypes>
"""
ARQUETIPO_XML = """  <Item type="CBaseArchetypeDef">
   <lodDist value="{dist}" />
   <flags value="{flags}" />
   <specialAttribute value="0" />
   {bbmin}
   {bbmax}
   {bscentre}
   <bsRadius value="{radio:.4f}" />
   <hdTextureDist value="{hd}" />
   <name>{modelo}</name>
   <textureDictionary>{ytd}</textureDictionary>
   <clipDictionary />
   <drawableDictionary />
   <physicsDictionary>{fisica}</physicsDictionary>
   <assetType>ASSET_TYPE_DRAWABLE</assetType>
   <assetName>{modelo}</assetName>
   <extensions />
  </Item>"""
YMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<CMapData>
 <name>{nombre}</name>
 {padre}
 <flags value="{flags}" />
 <contentFlags value="{contenido}" />
 {smin}
 {smax}
 {emin}
 {emax}
 <entities>
{entidades}
 </entities>
 <containerLods itemType="rage__fwContainerLodDef" />
 <boxOccluders itemType="BoxOccluder" />
 <occludeModels itemType="OccludeModel" />
 <physicsDictionaries />
 <instancedData>
  <ImapLink />
  <PropInstanceList itemType="rage__fwPropInstanceListDef" />
  <GrassInstanceList itemType="rage__fwGrassInstanceListDef" />
 </instancedData>
 <timeCycleModifiers itemType="CTimeCycleModifier" />
 <carGenerators itemType="CCarGen" />
 <LODLightsSOA>
  <direction itemType="FloatXYZ" />
  <falloff />
  <falloffExponent />
  <timeAndStateFlags />
  <hash />
  <coneInnerAngle />
  <coneOuterAngleOrCapExt />
  <coronaIntensity />
 </LODLightsSOA>
 <DistantLODLightsSOA>
  <position itemType="FloatXYZ" />
  <RGBI />
  <numStreetLights value="0" />
  <category value="0" />
 </DistantLODLightsSOA>
 <block>
  <version value="0" />
  <flags value="0" />
  <name>{nombre}</name>
  <exportedBy>bcn</exportedBy>
  <owner />
  <time />
 </block>
</CMapData>
"""
ENTIDAD_XML = """  <Item type="CEntityDef">
   <archetypeName>{modelo}</archetypeName>
   <flags value="{flags}" />
   <guid value="{guid}" />
   {pos}
   {rot}
   <scaleXY value="{escala:.3f}" />
   <scaleZ value="{escala:.3f}" />
   <parentIndex value="{padre}" />
   <lodDist value="{dist}" />
   <childLodDist value="{dist_hijos}" />
   <lodLevel>{nivel}</lodLevel>
   <numChildren value="{hijos}" />
   <priorityLevel>PRI_REQUIRED</priorityLevel>
   <extensions />
   <ambientOcclusionMultiplier value="255" />
   <artificialAmbientOcclusion value="255" />
   <tintValue value="0" />
  </Item>"""


def escribir_mapa(carpeta, nombre, arquetipos, entidades, lods=()):
    """arquetipos: lista de (modelo, ytd, distancia, caja_min, caja_max[, flags, ybn]) -> <nombre>.ytyp.xml
    entidades: lista de (modelo, (x, y, z[, rumbo[, escala]]), distancia[, k]) -> <nombre>.ymap.xml; rumbo en
      grados alrededor de Z (antihorario, 0 = sin girar), escala 1 si no se da; con k, la entidad es HD hija
      del LOD k.
    lods: lista de (modelo, (x, y, z), distancia, distancia_hijos) -> <nombre>_lod.ymap.xml, padre del ymap HD
      (como en el juego: dt1_02_long_0 -> dt1_02)."""
    tipos = []
    for modelo, ytd, dist, lo, hi, *extra in arquetipos:
        flags, fisica = (extra + [0, ""][len(extra):])[:2]
        centro = (lo + hi) / 2
        tipos.append(ARQUETIPO_XML.format(
            dist=dist, flags=flags, bbmin=_xyz("bbMin", lo), bbmax=_xyz("bbMax", hi), bscentre=_xyz("bsCentre", centro),
            radio=float(np.linalg.norm(hi - centro)), hd=dist / 3, modelo=modelo, ytd=ytd, fisica=fisica))
    Path(carpeta, f"{nombre}.ytyp.xml").write_text(YTYP_XML.format(arquetipos="\n".join(tipos), nombre=nombre),
                                                   encoding="utf-8")
    cajas = {a[0]: (a[3], a[4]) for a in arquetipos}
    hijos = [0] * len(lods)
    hd = []  # (modelo, pos, dist, padre, dist_hijos, nivel, n_hijos)
    for modelo, pos, dist, *padre in entidades:
        if padre:
            hijos[padre[0]] += 1
            hd.append((modelo, pos, dist, padre[0], 0, "LODTYPES_DEPTH_HD", 0))
        else:
            hd.append((modelo, pos, dist, -1, 0, "LODTYPES_DEPTH_ORPHANHD", 0))
    # (nombre, entidades, sufijo, flags, contentFlags): el ymap de LOD va con flags 2 / contentFlags 2, como dt1_lod
    planos = [(nombre, [(m, p, d, -1, dh, "LODTYPES_DEPTH_LOD", hijos[k]) for k, (m, p, d, dh) in enumerate(lods)],
               "_lod", 2, 2)] if lods else []
    planos.append((nombre, hd, "", 0, 1))
    for base, lista, sufijo, flags, contenido in planos:
        ents, lo_e, hi_e, lo_s, hi_s = [], [], [], [], []
        for k, (modelo, pos, dist, padre, dist_hijos, nivel, n_hijos) in enumerate(lista):
            p = np.asarray(pos[:3], float)
            rumbo = np.radians(pos[3]) if len(pos) > 3 else 0.0
            escala = pos[4] if len(pos) > 4 else 1.0
            # los ymap guardan la rotación inversa (como CodeWalker): z = -sen(rumbo / 2)
            rot = f'<rotation x="0" y="0" z="{-np.sin(rumbo / 2):.6f}" w="{np.cos(rumbo / 2):.6f}" />'
            lo, hi = cajas.get(modelo, (np.array([-10.0, -10.0, 0.0]), np.array([10.0, 10.0, 60.0])))  # del juego
            lo_e.append(p + lo); hi_e.append(p + hi)
            lo_s.append(p + lo - dist); hi_s.append(p + hi + dist)
            guid = zlib.crc32(f"{base}{sufijo}:{k}".encode()) or 1
            # bit 8: el padre está en el ymap padre (en el juego lo llevan todas las HD de dt1_02_long_0)
            flags = 1572864 | (8 if nivel == "LODTYPES_DEPTH_HD" else 0)
            ents.append(ENTIDAD_XML.format(modelo=modelo, guid=guid, flags=flags, pos=_xyz("position", p), dist=dist,
                                           rot=rot, escala=escala,
                                           padre=padre,
                                           dist_hijos=dist_hijos, nivel=nivel, hijos=n_hijos))
        padre_xml = f"<parent>{nombre}_lod</parent>" if lods and not sufijo else "<parent />"
        Path(carpeta, f"{base}{sufijo}.ymap.xml").write_text(YMAP_XML.format(
            nombre=f"{base}{sufijo}", padre=padre_xml, flags=flags, contenido=contenido,
            smin=_xyz("streamingExtentsMin", np.min(lo_s, 0)), smax=_xyz("streamingExtentsMax", np.max(hi_s, 0)),
            emin=_xyz("entitiesExtentsMin", np.min(lo_e, 0)), emax=_xyz("entitiesExtentsMax", np.max(hi_e, 0)),
            entidades="\n".join(ents)), encoding="utf-8")
