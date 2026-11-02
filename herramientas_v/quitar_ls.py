"""Quita Los Santos sin taparlo: el juego deja de montar los RPF de su mapa. Es la técnica del mod "Empty Map"
(gta5-mods.com): images.meta lista los RPF que se montan al arrancar y los content.xml de los parches y DLC los
que añaden ellos; se sacan de esas listas los de _citye, _cityw y _hills (y caminos, navmesh, luces lejanas,
radar en 3D, metro y destrucciones de misiones). Los ficheros se generan a partir de los del juego instalado (no
se copian los del mod, que son de una versión anterior) y van a la copia de update.rpf de la carpeta mods, que
se restaura antes desde la copia de seguridad: así se puede volver a ejecutar sin acumular cambios.

  mods/update/update.rpf/common/data/levels/gta5/images.meta   sin RPF del mapa
  mods/update/update.rpf/common/data/levels/gta5/gta5.meta     sin sus ityp permanentes, luces lejanas, zonas...
  mods/update/update.rpf/common/data/levels/gta5/popzone.ipl   sin zonas de población (gente de Los Santos)
  mods/update/update.rpf/x64/levels/gta5/sp_manifest.ymt       sin puntos de escenario
  mods/update/update.rpf/dlc_patch/<pack>/content.xml          parches y DLC sin sus RPF del mapa
  mods/update/update.rpf/common/data/levels/gta5/water.xml     el mar de Barcelona (costa real) y agua donde no
                                                               hay mapa (en vez de caer al vacío)
  mods/update/update.rpf/common/data/levels/gta5/traintracks.xml  sin las vías de Los Santos (trenes fantasma)
  mods/update/update.rpf/x64/models/farlods.ydd                vacío: sin las montañas lejanas de San Andreas
                                                               (sustituye al de x64a.rpf, como plantsmgr.ydd)

Deshacer: python quitar_ls.py --deshacer   (vuelve a poner la copia de seguridad de update.rpf)
"""
import re
import shutil
import sys

import config_v
import empaquetar_v
import rage

GTA = empaquetar_v.GTA
DESTINO = GTA / "mods" / "update" / "update.rpf"
COPIA = config_v.MOD / "update_antes_de_vaciar.rpf"
OBRA = config_v.MOD / "quitar_ls"

# RPF del mapa de Los Santos (y lo que solo tiene sentido con él)
MAPA = re.compile(r"levels/gta5/(?:_citye|_cityw|_hills)/|levels/gta5/(?:navmeshes\d+|paths|waypointrec|lodlights"
                  r"|minimap)\.rpf|levels/gta5/destruction/|levels/gta5/interiors/(?:v_int_metro|v_metro|v_tunnels)",
                  re.I)
# entradas de gta5.meta que dependen del mapa
META = re.compile(r"_citye/|_cityw/|_hills/|distantlights|slownesszones|mapzones\.xml|heightmap\.dat"
                  r"|waterheight\.dat|vfxfogvolumeinfo", re.I)
POPZONE = "zone\nend\n"
SP_MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<CScenarioPointManifest>
  <VersionNumber value="0" />
  <RegionDefs />
  <Groups />
  <InteriorNames />
</CScenarioPointManifest>
"""


def sacar(patron):
    """{ruta en el juego: texto} de los archivos de texto que casan con el patrón (sin los de la carpeta mods)."""
    tmp = OBRA / "sacar"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    rage.subprocess.run([str(rage.DOTNET), str(rage.CWTOOL), "sacar", str(GTA), patron, str(tmp / "c")],
                        capture_output=True, text=True)
    out = {}
    for f in tmp.glob("c_*.txt"):
        ruta, texto = f.read_text(encoding="utf-8", errors="replace").split("\n", 1)
        ruta = ruta.strip().replace("\\", "/")
        if not ruta.lower().startswith("mods/"):
            out[ruta] = texto.lstrip("\ufeff")
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def sin_items(texto, malo):
    """Quita los <Item>...</Item> (de bloque o de una línea) cuyo contenido case con 'malo'. Devuelve (texto, n)."""
    n = 0

    def fuera(m):
        nonlocal n
        if malo.search(m.group(0)):
            n += 1
            return ""
        return m.group(0)
    # primero los de una línea (changesets: <Item>dlc_x:/.../a.rpf</Item>), luego los bloques sin Item dentro
    texto = re.sub(r"[ \t]*<Item>[^<]*</Item>[ \t]*\r?\n?", fuera, texto)
    texto = re.sub(r"[ \t]*<Item>(?:(?!<Item>).)*?</Item>[ \t]*\r?\n?", fuera, texto, flags=re.S)
    return texto, n


TRAINTRACKS = """<?xml version="1.0" encoding="UTF-8"?>
<train_tracks version="1">
</train_tracks>
"""
AGUA_PASO = 20.0      # m: rejilla del agua
AGUA_LADO = 15900.0   # m: el agua llega hasta aquí desde el origen (el juego no va mucho más allá de 16 km)
QUAD = """  <Item>
   <minX value="{x0:.0f}" />
   <maxX value="{x1:.0f}" />
   <minY value="{y0:.0f}" />
   <maxY value="{y1:.0f}" />
   <Type value="0" />
   <IsInvisible value="false" />
   <HasLimitedDepth value="false" />
   <z value="0.000000" />
   <a1 value="26" />
   <a2 value="26" />
   <a3 value="26" />
   <a4 value="26" />
   <NoStencil value="false" />
  </Item>"""


def agua():
    """water.xml: agua a cota 0 en el mar (costa de OSM, 20 m hacia tierra para que no queden huecos junto al
    terreno recortado) y en todo lo que no cubren las hojas del mapa. Rectángulos de una rejilla de 20 m:
    tramos de cada fila y se juntan las filas con el mismo tramo."""
    import numpy as np
    import shapely
    import costa_v
    mar = costa_v.mar().buffer(20)
    shapely.prepare(mar)
    hojas = [h.name for h in (config_v.MOD / "prototipo").iterdir() if re.fullmatch(r"\d{6}", h.name)]
    xs = np.arange(-AGUA_LADO, AGUA_LADO, AGUA_PASO) + AGUA_PASO / 2
    X, Y = np.meshgrid(xs, xs)
    E, N = config_v.juego_a_utm(X, Y)
    hay = shapely.contains_xy(mar, E.ravel(), N.ravel()).reshape(X.shape)
    cubierto = np.zeros_like(hay)
    for h in hojas:
        e0, n0 = int(h[:3]) * 1000, (4000 + int(h[3:])) * 1000
        cubierto |= (E >= e0) & (E < e0 + 1000) & (N >= n0) & (N < n0 + 1000)
    hay |= ~cubierto
    rect, abiertos = [], {}
    for j in range(hay.shape[0] + 1):
        nuevos = {}
        if j < hay.shape[0]:
            d = np.diff(np.r_[0, hay[j].astype(np.int8), 0])
            for a, b in zip(np.where(d == 1)[0], np.where(d == -1)[0]):
                nuevos[(a, b)] = abiertos.pop((a, b), j)
        rect += [(a, b, j0, j) for (a, b), j0 in abiertos.items()]
        abiertos = nuevos
    x = lambda i: -AGUA_LADO + i * AGUA_PASO
    items = "\n".join(QUAD.format(x0=x(a), x1=x(b), y0=x(j0), y1=x(j1)) for a, b, j0, j1 in rect)
    print(f"water.xml: {len(rect)} rectángulos de agua, {hay.mean() * 100:.0f} % de la zona")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<WaterData>
 <WaterQuads>
{items}
 </WaterQuads>
 <CalmingQuads />
 <WaveQuads />
</WaterData>
"""


def lista_ipl():
    """bcn_ipl_fuera.txt en la carpeta del juego: todos los ymap del juego (menos los nuestros), para que el plugin
    bcn_sandbox.asi apague los que los scripts del juego activen por nombre (IPL: props sueltos, interiores,
    cambios de misiones...), que con los RPF del mapa fuera se quedan flotando sobre el mar."""
    r = rage.subprocess.run([str(rage.DOTNET), str(rage.CWTOOL), "listar", str(GTA), ".ymap"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    nombres = set()
    for linea in r.stdout.splitlines():
        if linea.strip():
            n = re.split(r"[\\/]", linea.split()[0])[-1].lower()
            # los nuestros son bcn_, bcn2_, bcn3_... (los ymap de cada paquete llevan su nombre)
            if n.endswith(".ymap") and not re.match(r"bcn\d*_", n):
                nombres.add(n[:-5])
    (GTA / "bcn_ipl_fuera.txt").write_text("\n".join(sorted(nombres)) + "\n", encoding="utf-8")
    print(f"bcn_ipl_fuera.txt: {len(nombres)} ymap del juego")


def main():
    if empaquetar_v._juego_abierto():
        sys.exit("Juego abierto: ciérralo antes")
    if not COPIA.exists():
        shutil.copy2(DESTINO, COPIA)
    shutil.copy2(COPIA, DESTINO)
    if "--deshacer" in sys.argv:
        print("update.rpf de mods restaurado")
        return
    shutil.rmtree(OBRA, ignore_errors=True)
    raiz = OBRA / "update_rpf"
    datos = raiz / "common" / "data" / "levels" / "gta5"
    datos.mkdir(parents=True)

    metas = sacar("*images.meta")
    texto, n = sin_items(metas["update/update.rpf/common/data/levels/gta5/images.meta"], MAPA)
    (datos / "images.meta").write_text(texto, encoding="utf-8")
    print(f"images.meta: {n} RPF del mapa fuera")
    metas = sacar("*gta5.meta")
    texto, n = sin_items(metas["update/update.rpf/common/data/levels/gta5/gta5.meta"], META)
    (datos / "gta5.meta").write_text(texto, encoding="utf-8")
    print(f"gta5.meta: {n} entradas fuera")
    (datos / "popzone.ipl").write_text(POPZONE, encoding="utf-8")
    (datos / "water.xml").write_text(agua(), encoding="utf-8")
    (datos / "traintracks.xml").write_text(TRAINTRACKS, encoding="utf-8")
    (raiz / "x64" / "levels" / "gta5").mkdir(parents=True)
    xml = OBRA / "farlods_xml"
    xml.mkdir()
    (xml / "farlods.ydd.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<DrawableDictionary>\n'
                                         '</DrawableDictionary>\n', encoding="utf-8")
    rage.a_binario(xml, raiz / "x64" / "models")
    (raiz / "x64" / "levels" / "gta5" / "sp_manifest.ymt").write_text(SP_MANIFEST, encoding="utf-8")

    # content.xml: el de dlc_patch de update.rpf manda sobre el del propio paquete
    contenidos = {}
    for ruta, texto in sacar("*content.xml").items():
        m = (re.match(r"update/update\.rpf/dlc_patch/([^/]+)/content\.xml$", ruta, re.I)
             or re.match(r"update/x64/dlcpacks/([^/]+)/dlc\.rpf/content\.xml$", ruta, re.I))
        if not m or m.group(1).lower().startswith("bcn"):
            continue
        pack = m.group(1).lower()
        if pack not in contenidos or "dlc_patch" in ruta:
            contenidos[pack] = texto
    total = 0
    for pack, texto in sorted(contenidos.items()):
        nuevo, n = sin_items(texto, MAPA)
        if n:
            d = raiz / "dlc_patch" / pack
            d.mkdir(parents=True, exist_ok=True)
            (d / "content.xml").write_text(nuevo, encoding="utf-8")
            total += n
            print(f"  {pack}: {n} entradas fuera")
    print(f"content.xml: {total} entradas del mapa fuera")

    r = rage.subprocess.run([str(rage.DOTNET), str(rage.CWTOOL), "meter", str(GTA), str(DESTINO), str(raiz)],
                            capture_output=True, text=True)
    print(r.stdout.strip(), r.stderr.strip()[-2000:])
    lista_ipl()


if __name__ == "__main__":
    main()
