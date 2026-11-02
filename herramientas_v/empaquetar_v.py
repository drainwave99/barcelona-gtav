"""Empaqueta hojas ya generadas (mod_v/prototipo/<hoja>/xml) en el DLC del mapa y lo instala en la carpeta
mods del juego (la que lee OpenIV.asi; los archivos originales no se tocan).

  dlc.rpf
    content.xml, setup2.xml
    x64/levels/gta5/bcn.rpf            modelos (.ydr), colisiones (.ybn), texturas (.ytd)
    x64/levels/gta5/bcn_metadata.rpf   .ymap, .ytyp y _manifest.ymf (qué ytyp necesita cada ymap)
La entrada dlcpacks:/bcn/ de dlclist.xml la pone 'cwtool dlclist' en mods/update/update.rpf.

Uso: python empaquetar_v.py 434589 435587
     python empaquetar_v.py --cambiadas    todas las hojas, pero solo rehace los paquetes (bcn, bcn2...) con alguna
                                           hoja regenerada después de su dlc.rpf (un arreglo: ~25-80 min, no 4 h)
Después de empaquetar, con el juego cerrado: python quitar_ls.py (vuelve a poner la lista de IPL al día).
"""
import pickle
import shutil
import sys

import numpy as np

import config_v
import puentes_v
import rage

GTA = config_v.Path(r"C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V")
PACK = "bcn"
OBRA = config_v.MOD / "dlc"
SOLO_PRUEBA = config_v.os.environ.get("BCN_SOLO_PRUEBA") == "1"
PLANTILLAS = config_v.RAIZ / "herramientas_v" / "plantillas"

# Como el parche del juego patch2026_01, que añade mapa también al modo historia: los modelos en un RPF y los
# ymap/ytyp/_manifest.ymf en otro "_metadata" con CONTENTS_DLC_MAP_DATA y loadCompletely, activados en
# GROUP_UPDATE_STREAMING de un paquete de nivel (EXTRACONTENT_LEVEL_PACK). Probado en el juego (2026-10-31):
# - todo en un RPF, paquete COMPAT en GROUP_STARTUP: los ymap no se dibujan nunca;
# - con _manifest.ymf en GROUP_STARTUP: el juego se cierra al montarlo (se monta tarde, al cargar la partida);
# - GROUP_MAP/MO_JIM_L11 (los DLC de Online): no se carga en el modo historia.
CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<CDataFileMgr__ContentsOfDataFileXml>
  <disabledFiles />
  <includedXmlFiles />
  <includedDataFiles />
  <dataFiles>
{rpfs}
    <Item>
      <filename>dlc_{p}:/%PLATFORM%/levels/gta5/{p}_metadata.rpf</filename>
      <fileType>RPF_FILE</fileType>
      <overlay value="false" />
      <disabled value="true" />
      <persistent value="true" />
      <loadCompletely value="true" />
      <contents>CONTENTS_DLC_MAP_DATA</contents>
    </Item>
  </dataFiles>
  <contentChangeSets>
    <Item>
      <changeSetName>{P}_MAPA</changeSetName>
      <filesToEnable>
{activar}
        <Item>dlc_{p}:/%PLATFORM%/levels/gta5/{p}_metadata.rpf</Item>
      </filesToEnable>
    </Item>
  </contentChangeSets>
  <patchFiles />
</CDataFileMgr__ContentsOfDataFileXml>
"""

RPF_ITEM = """    <Item>
      <filename>dlc_{p}:/%PLATFORM%/levels/gta5/{r}.rpf</filename>
      <fileType>RPF_FILE</fileType>
      <overlay value="false" />
      <disabled value="true" />
      <persistent value="true" />
    </Item>"""
# Límites de cada RPF de modelos. El que de verdad cerraba el juego al cargar (2026-10-31): en un RPF7 el sitio
# del nombre de cada archivo va en 16 bits, así que la tabla de nombres no puede pasar de 64 KB (~2700 archivos);
# pasados, los nombres se pisan ("0_458300.ydr") y el juego se cierra al abrir el RPF. El peso, por si acaso.
MAX_RPF = 1500 * 2**20
MAX_NOMBRES = 56000  # bytes de la tabla de nombres (nombre + 0 de cada archivo)


def _hoja(nombre):
    """Hoja de un archivo por la casilla de su nombre (EEEEE_NNNNNN = UTM / 10); None si no es de una casilla
    (texturas compartidas, monumentos: van al primer RPF)."""
    import re
    m = re.search(r"_(\d{5})_(\d{6})", nombre)
    if not m:
        return None
    return f"{int(m.group(1)) // 100}{(int(m.group(2)) // 100) % 1000:03d}"


def repartir(mapa, hojas):
    """{hoja: índice del RPF de modelos}, llenando cada RPF hasta MAX_RPF y MAX_NOMBRES en el orden de 'hojas'."""
    peso, nombres = {}, {}
    for f in mapa.iterdir():
        if f.is_file():
            h = _hoja(f.name)
            peso[h] = peso.get(h, 0) + f.stat().st_size
            nombres[h] = nombres.get(h, 0) + len(f.name.encode()) + 1
    grupos, k, lleno, letras = {}, 0, peso.get(None, 0), nombres.get(None, 0)
    for h in hojas:
        if (lleno or letras) and (lleno + peso.get(h, 0) > MAX_RPF or letras + nombres.get(h, 0) > MAX_NOMBRES):
            k, lleno, letras = k + 1, 0, 0
        grupos[h] = k
        lleno += peso.get(h, 0)
        letras += nombres.get(h, 0)
    return grupos


# _manifest.ymf: dice al juego qué ytyp necesita cada ymap; sin él sus entidades no salen. Formato copiado de
# los del juego (los itemType hacen falta).
MANIFIESTO = """<?xml version="1.0" encoding="UTF-8"?>
<CPackFileMetaData>
 <MapDataGroups itemType="CMapDataGroup" />
 <HDTxdBindingArray itemType="CHDTxdAssetBinding" />
 <imapDependencies itemType="CImapDependency" />
 <imapDependencies_2 itemType="CImapDependencies">
{deps}
 </imapDependencies_2>
 <itypDependencies_2 itemType="CItypDependencies" />
 <Interiors itemType="CInteriorBoundsFiles" />
</CPackFileMetaData>
"""
DEP = """  <Item>
   <imapName>{n}</imapName>
   <manifestFlags />
   <itypDepArray>
    <Item>{t}</Item>
   </itypDepArray>
  </Item>"""


SETUP = """<?xml version="1.0" encoding="UTF-8"?>
<SSetupData>
  <deviceName>dlc_{p}</deviceName>
  <datFile>content.xml</datFile>
  <timeStamp>10/30/2026 00:00:00</timeStamp>
  <nameHash>{p}</nameHash>
  <contentChangeSets />
  <contentChangeSetGroups>
    <Item>
      <NameHash>GROUP_UPDATE_STREAMING</NameHash>
      <ContentChangeSets>
        <Item>{P}_MAPA</Item>
      </ContentChangeSets>
    </Item>
  </contentChangeSetGroups>
  <startupScript />
  <scriptCallstackSize value="0" />
  <type>EXTRACONTENT_LEVEL_PACK</type>
  <order value="80" />
  <minorOrder value="0" />
  <isLevelPack value="true" />
  <dependencyPackHash />
  <requiredVersion />
  <subPackCount value="0" />
</SSetupData>
"""


def balizas(xml, hojas, alto=250.0):
    """Torre roja de 6 x 6 m y 'alto' m a 30 m de la esquina NE de cada hoja, para encontrar el mapa de
    prueba desde la costa (no tiene colisión)."""
    obra = puentes_v.Obra((0.0, 0.0))
    obra.caja(np.zeros(2), np.array([1.0, 0.0]), 6.0, 6.0, -5.0, alto, tex="vi_baliza")
    geo = obra.m.arrays()["vi_baliza"]
    rage.escribir_ydr(xml / "bcn_baliza.ydr.xml", "bcn_baliza", [dict(textura="vi_baliza", **geo)], 4000.0)
    # pruebas: la misma torre con distancias normales, y el cubo de la plantilla de Sollumz tal cual
    rage.escribir_ydr(xml / "bcn_baliza2.ydr.xml", "bcn_baliza2", [dict(textura="vi_baliza", **geo)], 9998.0)
    cubo = (config_v.RAIZ / "herramientas_v" / "plantillas" / "ejemplo.ydr.xml").read_text(encoding="utf-8")
    cubo = cubo.replace("<Name>drawable</Name>", "<Name>bcn_baliza3</Name>").replace("bdn_prueba_tex", "vi_baliza")
    (xml / "bcn_baliza3.ydr.xml").write_text(cubo, encoding="utf-8")
    # copias exactas de modelos del juego con nombre nuestro (sacados con 'cwtool extraer'): si salen y las
    # torres no, el fallo está en nuestros .ydr; si tampoco salen, en el DLC
    copias = []
    for original, copia, ytd, lod, flags, ybn in (("plg_01_arm_00", "bcn_copia_valla", "plg_01_armco", 300.0, 0, ""),
                                                  ("prop_mp_cone_01", "bcn_copia_cono", "prop_mp_barrier", 300.0,
                                                   0x20020000, "prop_mp_barrier")):
        texto = (PLANTILLAS / f"{original}.ydr.xml").read_text(encoding="utf-8")
        (xml / f"{copia}.ydr.xml").write_text(texto.replace(f"<Name>{original}.#dr</Name>", f"<Name>{copia}</Name>", 1),
                                             encoding="utf-8")
        copias.append((copia, ytd, lod, *rage.caja_ydr(xml / f"{copia}.ydr.xml"), flags, ybn))
    entidades = []
    for hoja in hojas:
        e1, n1 = (int(hoja[:3]) + 1) * 1000, (4000 + int(hoja[3:]) + 1) * 1000
        x, y = config_v.utm_a_juego(e1 + 30, n1 + 30)
        entidades.append(("bcn_baliza", (x, y, 0.0), 4000.0))
        print(f"Baliza de {hoja}: X {x:.0f}, Y {y:.0f}")
        # control: molinos del propio juego entre el muelle de Del Perro y la torre (si salen, el ymap carga)
        for k in range(3):
            entidades.append(("prop_windmill_01", (x + 150 + 150 * k, y, 0.0), 1500.0))
        entidades.append(("bcn_baliza2", (x + 75, y, 0.0), 300.0))
        entidades.append(("bcn_baliza3", (x + 225, y + 15, 3.0), 300.0))
        entidades.append(("plg_01_arm_00", (x + 300, y + 40, 1.0), 218.0))  # edificio del juego, sin colisión propia
        entidades.append(("bcn_copia_valla", (x + 300, y + 80, 1.0), 300.0))
        for k in range(3):
            entidades.append(("bcn_copia_cono", (x + 229 + 2 * k, y + 15, 1.5), 300.0))
    solo = config_v.os.environ.get("BCN_ENTIDADES")  # pruebas: sólo estas entidades (nombres separados por comas)
    if solo:
        entidades = [e for e in entidades if e[0] in solo.split(",")]
    nombre = f"{PACK}_balizas"
    arq = [("bcn_baliza", "bcn_obra", 4000.0, *rage.caja_ydr(xml / "bcn_baliza.ydr.xml")),
           ("bcn_baliza2", "bcn_obra", 300.0, *rage.caja_ydr(xml / "bcn_baliza2.ydr.xml")),
           ("bcn_baliza3", "bcn_obra", 300.0, *rage.caja_ydr(xml / "bcn_baliza3.ydr.xml"))] + copias
    rage.escribir_mapa(xml, nombre, arq, entidades)
    return nombre


_OSM = []


def mobiliario(xml, nombre, hoja):
    """Árboles y mobiliario (props del juego) de la hoja en un ymap por casilla de 250 m, sin ytyp propio:
    así cada trozo se carga solo cuando el jugador está cerca."""
    import calles_v
    import mobiliario_v
    import prototipo
    if not _OSM:
        with open(config_v.DATOS / "osm.pkl", "rb") as fh:
            _OSM.append(pickle.load(fh))
    capas, e0h, n1h = prototipo.cargar_hoja(hoja)
    osm = calles_v.recortar(_OSM[0], (e0h - 300, n1h - 1300, e0h + 1300, n1h + 300))
    grupos = {}
    for ent in mobiliario_v.construir(osm, capas, e0h, n1h):
        e, n = config_v.juego_a_utm(ent[1][0], ent[1][1])
        grupos.setdefault((int((e - e0h) // 250), int((n1h - n) // 250)), []).append(ent)
    for (i, j), ents in sorted(grupos.items()):
        nom = f"{nombre}_m{i}{j}"
        rage.escribir_mapa(xml, nom, [], ents)
        (xml / f"{nom}.ytyp.xml").unlink()
    print(f"{hoja}: {sum(len(g) for g in grupos.values())} árboles y piezas de mobiliario", flush=True)


HOJAS_POR_PACK = 10  # paquetes pequeños (2026-11-02): un arreglo en una hoja rehace ~1 GB en ~20 min, no 4 GB en 75 min


HOJAS_NUEVAS_POR_PACK = 10  # las hojas que se añadan, igual
REPARTO = config_v.MOD / "paquetes.json"


def reparto(hojas):
    """{paquete: [hojas]} fijo: cada hoja se queda en su paquete aunque se añadan otras (si no, al añadir una
    se movían todas y había que rehacer todos los paquetes). Las nuevas llenan el último o abren otro."""
    import json
    if REPARTO.exists():
        rep = json.loads(REPARTO.read_text(encoding="utf-8"))
    else:  # el reparto de antes (de 40 en 40 en orden); se escribió el 2026-11-02 con las 94 hojas de entonces
        hechas = sorted(hojas)
        rep = {("bcn" if k == 0 else f"bcn{k + 1}"): hechas[i:i + HOJAS_POR_PACK]
               for k, i in enumerate(range(0, len(hechas), HOJAS_POR_PACK))}
    puestas = {h for v in rep.values() for h in v}
    for h in sorted(hojas):
        if h in puestas:
            continue
        ultimo = list(rep)[-1] if rep else None
        if ultimo is None or len(rep[ultimo]) >= (HOJAS_POR_PACK if ultimo == "bcn" else HOJAS_NUEVAS_POR_PACK):
            ultimo = "bcn" if not rep else f"bcn{len(rep) + 1}"
            rep[ultimo] = []
        rep[ultimo].append(h)
        puestas.add(h)
    REPARTO.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return rep


def main():
    """Las hojas se reparten en paquetes DLC bcn, bcn2, bcn3... (cada uno con sus propios diccionarios
    compartidos) según mod_v/paquetes.json. Los paquetes a partir del segundo necesitan su línea en dlclist.xml.
    Con hojas en la línea se rehacen los paquetes que las contienen (enteros); con --cambiadas, todos los que
    tengan alguna hoja regenerada después de su dlc.rpf."""
    global PACK, OBRA
    cambiadas = "--cambiadas" in sys.argv  # todas las hojas, pero solo se rehacen los paquetes con alguna cambiada
    hojas = sorted(a for a in sys.argv[1:] if not a.startswith("-"))
    todas = config_v.hojas(con_colocacion=True)
    rep = reparto(todas if cambiadas and not hojas else hojas)
    if not _juego_abierto():  # lo instalado ahora, para poder volver si lo nuevo falla
        import versiones_v
        versiones_v.guardar("antes")
    for k, (pack, trozo) in enumerate(rep.items()):
        if not cambiadas and not set(trozo) & set(hojas):
            continue
        PACK = pack
        OBRA = config_v.MOD / ("dlc" if pack == "bcn" else f"dlc_{pack}")
        if cambiadas and not _paquete_viejo(trozo):
            print(f"{PACK}: sin cambios ({trozo[0]}..{trozo[-1]})", flush=True)
            continue
        empaquetar(trozo)
        (OBRA / "hojas.txt").write_text(" ".join(trozo), encoding="utf-8")
        if pack != "bcn" and not _juego_abierto():
            r = rage.subprocess.run([str(rage.DOTNET), str(rage.CWTOOL), "dlclist", str(GTA),
                                     str(GTA / "mods" / "update" / "update.rpf"), PACK], capture_output=True, text=True)
            print(r.stdout.strip(), r.stderr.strip())
    print(f"PAQUETES: {len(rep)}")


def _paquete_viejo(trozo):
    """True si alguna hoja del paquete (su colocacion.pkl o sus modelos) es más nueva que el dlc.rpf hecho, o si
    no hay dlc.rpf. Los ymap/ytyp que escribe el propio empaquetado no cuentan."""
    hecho = OBRA / "dlc.rpf"
    if not hecho.exists():
        return True
    lista = OBRA / "hojas.txt"  # hecho con otras hojas
    if lista.exists() and lista.read_text(encoding="utf-8").split() != list(trozo):
        return True
    t = hecho.stat().st_mtime
    for hoja in trozo:
        base = config_v.MOD / "prototipo" / hoja
        if (base / "colocacion.pkl").stat().st_mtime > t:
            return True
        for f in (base / "xml").iterdir():
            if not f.name.startswith("bcn") or f.name.startswith("bcn_"):  # modelos y texturas (no bcn2_<hoja>.ymap...)
                if f.stat().st_mtime > t:
                    return True
    return False


def _juego_abierto():
    import subprocess
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq GTA5.exe"], capture_output=True, text=True)
    return "GTA5.exe" in r.stdout


def empaquetar(hojas):
    shutil.rmtree(OBRA, ignore_errors=True)
    todo_xml = OBRA / "xml"
    todo_xml.mkdir(parents=True)
    nombres = []
    for hoja in hojas:
        base = config_v.MOD / "prototipo" / hoja
        xml = base / "xml"
        with open(base / "colocacion.pkl", "rb") as fh:
            col = pickle.load(fh)
        arquetipos = [(m, ytd, dist, *rage.caja_ydr(xml / f"{m}.ydr.xml")) for m, ytd, dist in col["arquetipos"]]
        nombre = f"{PACK}_{hoja}"
        import re
        for viejo in xml.glob("bcn*.y*.xml"):  # de un empaquetado anterior en otro paquete (bcn2_<hoja>...)
            if re.fullmatch(rf"bcn\d*_{hoja}(_.*)?\.(ymap|ytyp)\.xml", viejo.name):
                viejo.unlink()
        rage.escribir_mapa(xml, nombre, arquetipos, col["entidades"], col.get("lods", ()))
        if config_v.os.environ.get("BCN_MOBILIARIO", "1") != "0" and not SOLO_PRUEBA:
            mobiliario(xml, nombre, hoja)
        if SOLO_PRUEBA:  # sólo los modelos de la hoja, sin su ymap ni su ytyp (para aislar fallos)
            (xml / f"{nombre}.ymap.xml").unlink()
            (xml / f"{nombre}.ytyp.xml").unlink()
        else:
            nombres.append(nombre)
            if col.get("lods"):
                nombres.append(f"{nombre}_lod")
        for f in xml.iterdir():  # todo junto (los diccionarios compartidos se suman: hojas viejas pueden tener menos)
            destino = todo_xml / f.name
            if f.is_dir():
                shutil.copytree(f, destino, dirs_exist_ok=True)
            else:
                shutil.copy2(f, destino)
    if config_v.os.environ.get("BCN_BALIZAS"):  # pruebas del DLC: torre roja y objetos de control junto a cada hoja
        nombres.append(balizas(todo_xml, hojas))
    niveles = OBRA / "dlc" / "x64" / "levels" / "gta5"
    deps = "\n".join(DEP.format(n=n, t=n.removesuffix("_lod")) for n in nombres)  # el LOD usa el ytyp de su hoja
    (todo_xml / "_manifest.ymf.pso.xml").write_text(MANIFIESTO.format(deps=deps), encoding="utf-8")
    mapa, meta = niveles / f"{PACK}.rpf", niveles / f"{PACK}_metadata.rpf"
    rage.a_binario(todo_xml, mapa)
    meta.mkdir()
    for f in list(mapa.glob("*.ymap")) + list(mapa.glob("*.ytyp")) + list(mapa.glob("*.ymf")):
        f.rename(meta / f.name)
    # modelos repartidos en varios RPF si no caben en uno
    grupos = repartir(mapa, hojas)
    nombres_rpf = [PACK] + [f"{PACK}_{k + 1}" for k in range(1, max(grupos.values(), default=0) + 1)]
    for k in range(1, len(nombres_rpf)):
        carpeta = niveles / f"{nombres_rpf[k]}.rpf"
        carpeta.mkdir()
        for f in list(mapa.iterdir()):
            if f.is_file() and grupos.get(_hoja(f.name), 0) == k:
                f.rename(carpeta / f.name)
    dlc = OBRA / "dlc"
    (dlc / "content.xml").write_text(CONTENT.format(
        p=PACK, P=PACK.upper(), rpfs="\n".join(RPF_ITEM.format(p=PACK, r=r) for r in nombres_rpf),
        activar="\n".join(f"        <Item>dlc_{PACK}:/%PLATFORM%/levels/gta5/{r}.rpf</Item>" for r in nombres_rpf)),
        encoding="utf-8")
    (dlc / "setup2.xml").write_text(SETUP.format(p=PACK, P=PACK.upper()), encoding="utf-8")
    archivo = OBRA / "dlc.rpf"
    rage.empaquetar_rpf(dlc, archivo)
    shutil.rmtree(todo_xml, ignore_errors=True)  # cientos de GB con todas las hojas: solo queda el dlc.rpf
    shutil.rmtree(dlc, ignore_errors=True)
    instalado = GTA / "mods" / "update" / "x64" / "dlcpacks" / PACK / "dlc.rpf"
    instalado.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(archivo, instalado)
        print(f"Instalado {instalado} ({archivo.stat().st_size / 1e6:.0f} MB)")
    except PermissionError:  # el juego lo tiene abierto: se copia al cerrarlo
        print(f"Juego abierto: {archivo} ({archivo.stat().st_size / 1e6:.0f} MB) sin instalar")


if __name__ == "__main__":
    main()
