"""Quita Los Santos: paquete DLC "bcn_vacio" que tapa cada ymap y cada colisión (.ybn) del mapa del juego con uno
vacío del mismo nombre, en un RPF con la misma ruta y overlay, como hacen los parches de Rockstar (patchday2ng
tapa levels/gta5/_citye/downtown_01/downtown_01_metadata.rpf así). Los modelos (.ydr, .ytyp) no se tocan: los
props siguen existiendo, solo desaparece dónde estaban puestos. Los archivos originales del juego no se tocan
(todo va a la carpeta mods y se quita borrando mods/update/x64/dlcpacks/bcn_vacio).

  ymap vacío: sin entidades y sin extensión de carga, así no se carga nunca.
  ybn vacío: un triángulo de 1 m a 4 km bajo tierra (el juego solo lo carga si el jugador está allí).

Uso: python vaciar_ls.py            lista los archivos del juego (cwtool listar) y hace e instala el paquete
"""
import collections
import json
import re
import shutil
import sys

import config_v
import empaquetar_v
import rage

PACK = "bcn_vacio"
OBRA = config_v.MOD / "dlc_vacio"
LISTA = config_v.DATOS / "mapa_ls.json"
# ymap/ybn del mapa: en los RPF base (x64*.rpf), en update.rpf o en los parches patchday (que pisan los base)
RUTA = re.compile(r"(?:mods/)?(?:update/update\.rpf/|update/x64/dlcpacks/patchday\w+/dlc\.rpf/|x64\w?\.rpf/)"
                  r"(?:x64/)?(levels/gta5/.*\.rpf)/([^/]+\.(?:ymap|ybn))$", re.I)

YMAP = """<?xml version="1.0" encoding="UTF-8"?>
<CMapData>
 <name>{n}</name>
 <parent />
 <flags value="0" />
 <contentFlags value="0" />
 <streamingExtentsMin x="0" y="0" z="0" />
 <streamingExtentsMax x="0" y="0" z="0" />
 <entitiesExtentsMin x="0" y="0" z="0" />
 <entitiesExtentsMax x="0" y="0" z="0" />
 <entities />
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
  <name>{n}</name>
  <exportedBy>bcn</exportedBy>
  <owner />
  <time />
 </block>
</CMapData>
"""

ITEM = """    <Item>
      <filename>dlc_{p}:/%PLATFORM%/{r}</filename>
      <fileType>RPF_FILE</fileType>
      <locked value="true" />
      <disabled value="true" />
      <persistent value="true" />
      <overlay value="true" />{extra}
    </Item>"""
MAPA = """
      <loadCompletely value="true" />
      <contents>CONTENTS_DLC_MAP_DATA</contents>"""


def listar():
    """{ruta del RPF contenedor: [archivos]} de todos los ymap/ybn del mapa del juego (y guarda la lista)."""
    gta = str(empaquetar_v.GTA)
    cont = collections.defaultdict(set)
    for ext in (".ymap", ".ybn"):
        r = rage.subprocess.run([str(rage.DOTNET), str(rage.CWTOOL), "listar", gta, ext], capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        for linea in r.stdout.splitlines():
            if not linea.strip():
                continue
            m = RUTA.match(linea.split()[0].replace("\\", "/"))
            if m and not m.group(2).lower().startswith("bcn"):
                cont[m.group(1).lower()].add(m.group(2).lower())
    cont = {r: sorted(v) for r, v in sorted(cont.items())}
    LISTA.write_text(json.dumps(cont, indent=0), encoding="utf-8")
    return cont


def tapados(cont):
    """RPF que los parches (y DLC) de Rockstar ya ponen con overlay en la misma ruta que los nuestros. Con dos
    overlays en la misma ruta ganaba el suyo (probado: el centro y Vespucci seguían): se apagan con filesToDisable."""
    tmp = OBRA.parent / "contents_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    rage.subprocess.run([str(rage.DOTNET), str(rage.CWTOOL), "sacar", str(empaquetar_v.GTA), "*content.xml",
                         str(tmp / "c")], capture_output=True, text=True)
    fuera = set()
    for f in tmp.glob("c_*.txt"):
        t = f.read_text(encoding="utf-8", errors="replace")
        if t.split("\n", 1)[0].lower().startswith("mods\\") or "dlc_bcn" in t:
            continue
        for it in re.findall(r"<Item>(.*?)</Item>", t, re.S):
            fn = re.search(r"<filename>(dlc_\w+):/%PLATFORM%/(levels/gta5/[^<]+\.rpf)</filename>", it, re.I)
            if fn and 'overlay value="true"' in it and fn.group(2).lower() in cont:
                fuera.add(f"{fn.group(1)}:/%PLATFORM%/{fn.group(2)}")
    shutil.rmtree(tmp, ignore_errors=True)
    return sorted(fuera)


PARCHE = re.compile(r"update/x64/dlcpacks/(patchday\w+)/dlc\.rpf/x64/(levels/gta5/.*\.rpf)/([^/]+\.ymap)$", re.I)


def parches():
    """Los ymap del mapa que traen los parches de Rockstar (patchday*), que ganan a cualquier DLC nuestro (probado:
    el centro y Vespucci seguían con overlay, filesToDisable y nombres repetidos). Se tapan como tapa Rockstar sus
    propios parches: en mods/update/update.rpf/dlc_patch/<parche>/ va un RPF con la misma ruta, que sustituye al
    del parche, con todos sus ymap vacíos. Devuelve {parche: {ruta RPF: [ymaps]}}."""
    r = rage.subprocess.run([str(rage.DOTNET), str(rage.CWTOOL), "listar", str(empaquetar_v.GTA), ".ymap"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for linea in r.stdout.splitlines():
        m = PARCHE.match(linea.split()[0].replace("\\", "/")) if linea.strip() else None
        if m:
            out[m.group(1).lower()][m.group(2).lower()].append(m.group(3).lower())
    return out


def meter_parches(binario):
    """Pone los RPF vacíos de parches() en dlc_patch de la copia de update.rpf de la carpeta mods."""
    destino = empaquetar_v.GTA / "mods" / "update" / "update.rpf"
    copia = OBRA.parent / "update_antes_de_vaciar.rpf"
    if not copia.exists():
        shutil.copy2(destino, copia)
    carpeta = OBRA / "dlc_patch_obra"
    shutil.rmtree(carpeta, ignore_errors=True)
    n = 0
    for parche, rpfs in sorted(parches().items()):
        for r, v in rpfs.items():
            d = carpeta / "dlc_patch" / parche / "x64" / r
            d.mkdir(parents=True, exist_ok=True)
            for m in v:
                shutil.copy2(binario / m, d / m)
                n += 1
            print(f"  {parche}: {r} ({len(v)} ymap)")
    if not n:
        return
    r = rage.subprocess.run([str(rage.DOTNET), str(rage.CWTOOL), "meter", str(empaquetar_v.GTA), str(destino),
                             str(carpeta)], capture_output=True, text=True)
    print(r.stdout.strip(), r.stderr.strip()[-2000:])
    shutil.rmtree(carpeta, ignore_errors=True)


def main():
    cont = json.loads(LISTA.read_text(encoding="utf-8")) if "--lista" in sys.argv and LISTA.exists() else listar()
    for ext in ("ymap", "ybn"):  # --solo-ymap / --solo-ybn: para buscar qué cierra el juego
        if f"--solo-{ext}" in sys.argv:
            cont = {r: [n for n in v if n.endswith("." + ext)] for r, v in cont.items()}
            cont = {r: v for r, v in cont.items() if v}
    print(f"{len(cont)} RPF, {sum(len(v) for v in cont.values())} archivos")
    shutil.rmtree(OBRA, ignore_errors=True)
    xml, binario, dlc = OBRA / "xml", OBRA / "bin", OBRA / "dlc"
    xml.mkdir(parents=True)
    # cada nombre una vez (vacío es igual en cualquier RPF) y luego se copia a sus RPF
    nombres = sorted({n for v in cont.values() for n in v})
    for n in nombres:
        base, ext = n.rsplit(".", 1)
        if ext == "ymap":
            (xml / f"{n}.xml").write_text(YMAP.format(n=base), encoding="utf-8")
        else:
            rage.escribir_ybn(xml / f"{n}.xml", [[0, 0, -4000], [1, 0, -4000], [0, 1, -4000]], [[0, 1, 2]],
                              [rage.MAT_CONCRETE], [0])
    rage.a_binario(xml, binario)
    for r, v in cont.items():
        carpeta = dlc / "x64" / r
        carpeta.mkdir(parents=True, exist_ok=True)
        for n in v:
            shutil.copy2(binario / n, carpeta / n)
    rutas = [f"x64/{r}" for r in cont]
    items = "\n".join(ITEM.format(p=PACK, r=r, extra=MAPA if r.endswith("_metadata.rpf") else "") for r in rutas)
    # además todos los ymap vacíos en RPF de mapa propios (sin overlay): por si el juego decide por el nombre
    # y no por la ruta (con solo overlays, el centro y Vespucci seguían)
    ymaps = [n for n in nombres if n.endswith(".ymap")]
    grupo, k, letras = [], 0, 0
    for n in ymaps + [None]:
        if n is None or letras + len(n) + 1 > empaquetar_v.MAX_NOMBRES:
            r = f"x64/levels/gta5/{PACK}_nombres{k}.rpf"
            for m in grupo:
                (dlc / r).mkdir(parents=True, exist_ok=True)
                shutil.copy2(binario / m, dlc / r / m)
            if grupo:
                rutas.append(r)
                items += "\n" + ITEM.format(p=PACK, r=r, extra=MAPA).replace('<overlay value="true" />',
                                                                          '<overlay value="false" />')
            grupo, k, letras = [], k + 1, 0
        if n is not None:
            grupo.append(n)
            letras += len(n) + 1
    activar = "\n".join(f"        <Item>dlc_{PACK}:/%PLATFORM%/{r}</Item>" for r in rutas)
    tapar = tapados(cont)
    print(len(tapar), "RPF de parches de Rockstar apagados")
    apagar = "\n".join(f"        <Item>{r}</Item>" for r in tapar)
    (dlc / "content.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<CDataFileMgr__ContentsOfDataFileXml>
  <disabledFiles />
  <includedXmlFiles />
  <includedDataFiles />
  <dataFiles>
{items}
  </dataFiles>
  <contentChangeSets>
    <Item>
      <changeSetName>BCN_VACIO_MAPA</changeSetName>
      <filesToEnable>
{activar}
      </filesToEnable>
      <filesToDisable>
{apagar}
      </filesToDisable>
    </Item>
  </contentChangeSets>
  <patchFiles />
</CDataFileMgr__ContentsOfDataFileXml>
""".replace("%PLATFORM%/x64/", "%PLATFORM%/"), encoding="utf-8")
    # después de los parches de Rockstar (para pisar lo que ellos pisan)
    (dlc / "setup2.xml").write_text(empaquetar_v.SETUP.format(p=PACK, P="BCN_VACIO")
                                    .replace('<order value="80" />', '<order value="99" />'), encoding="utf-8")
    archivo = OBRA / "dlc.rpf"
    rage.empaquetar_rpf(dlc, archivo)
    if empaquetar_v._juego_abierto():
        print("Juego abierto: sin instalar", archivo)
        return
    meter_parches(binario)
    shutil.rmtree(xml, ignore_errors=True)
    shutil.rmtree(binario, ignore_errors=True)
    instalado = empaquetar_v.GTA / "mods" / "update" / "x64" / "dlcpacks" / PACK / "dlc.rpf"
    instalado.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archivo, instalado)
    print(f"Instalado {instalado} ({archivo.stat().st_size / 1e6:.1f} MB)")
    r = rage.subprocess.run([str(rage.DOTNET), str(rage.CWTOOL), "dlclist", str(empaquetar_v.GTA),
                             str(empaquetar_v.GTA / "mods" / "update" / "update.rpf"), PACK],
                            capture_output=True, text=True)
    print(r.stdout.strip(), r.stderr.strip())


if __name__ == "__main__":
    main()
