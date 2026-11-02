"""Radar y mapa de Barcelona: plano dibujado desde OSM (calles, vías, parques, playas) y el Catastro (edificios),
con el mar de la costa real; el plugin bcn_radar.asi lo pinta en lugar del radar del juego (que solo tiene Los
Santos) y abre el mapa grande con la tecla M.

  bcnradar_<bx>_<by>.ytd   un bloque de 2048 m: 4 x 4 texturas t<i><j> de 512 m (256 px, 2 m/px)
  bcnradar_mapa.ytd        el plano entero: m_<bx>_<by> de 2048 m (256 px, 8 m/px), la flecha del jugador
  (y en mod_v/mapa_pausa, las texturas del mapa del menú de pausa: mapa_pausa_v.py; las mete quitar_ls)
  bcn_radar.txt            (carpeta del juego) la rejilla y los bloques que existen, para el plugin
  bcn_calles.bin           (carpeta del juego) tramos de calle con nombre (OSM) y el municipio de cada cuadro
                           de 100 m (Catastro), para el nombre de la calle bajo el radar

También lleva los caminos de coches (nodes<N>.ynd, trafico_v.py) para el tráfico.
Se empaqueta como el DLC 'bcnradar' (mods/update/x64/dlcpacks/bcnradar), aparte de los del mapa: rehacerlo no
toca bcn, bcn2, bcn3.
Uso: python radar_v.py [--sin-instalar]   (con el juego cerrado para instalar)
"""
import pickle
import shutil
import sys

import numpy as np
import shapely
from PIL import Image, ImageDraw
from shapely.strtree import STRtree

import config_v
import empaquetar_v
import rage

PACK = "bcnradar"
OBRA = config_v.MOD / "radar"
X0, Y0 = -4608.0, -8192.0     # esquina suroeste de la rejilla, en coordenadas del juego
BLOQUE, NBX, NBY = 2048.0, 7, 9
TESELA, PX = 512.0, 256       # 2 m/px
SS = 2                        # supermuestreo al dibujar

MAR = (38, 64, 90)
TIERRA = (60, 65, 62)
VERDE = (56, 84, 56)
ARENA = (118, 110, 86)
PEATONAL = (88, 92, 89)
EDIFICIO = (98, 102, 99)
BORDE_EDIF = (78, 82, 80)
CALLE = (176, 178, 174)
BORDE_CALLE = (40, 43, 42)
AUTOPISTA = (204, 172, 96)
CAMINO = (112, 116, 112)
VIA = (30, 32, 34)
AGUA = (44, 74, 102)

VERDES = {("leisure", "park"), ("leisure", "garden"), ("landuse", "grass"), ("leisure", "pitch"),
          ("natural", "scrub"), ("landuse", "meadow"), ("natural", "grassland"), ("natural", "heath"),
          ("natural", "wood"), ("landuse", "forest"), ("landuse", "allotments"), ("landuse", "flowerbed"),
          ("landuse", "village_green"), ("landuse", "recreation_ground"), ("landuse", "cemetery"),
          ("landuse", "farmland"), ("landuse", "orchard"), ("landuse", "vineyard"), ("leisure", "golf_course"),
          ("natural", "shrubbery"), ("leisure", "dog_park"), ("landuse", "greenfield")}
ARENAS = {("natural", "sand"), ("natural", "beach")}
PEATONALES = {("place", "square"), ("area:highway", "pedestrian"), ("highway", "pedestrian"),
              ("leisure", "playground"), ("amenity", "parking")}
# ancho en metros y si es vía rápida
ANCHOS = {"motorway": (16, 1), "trunk": (14, 1), "motorway_link": (8, 1), "trunk_link": (8, 1),
          "primary": (12, 0), "secondary": (11, 0), "tertiary": (10, 0), "primary_link": (7, 0),
          "secondary_link": (7, 0), "tertiary_link": (7, 0), "residential": (8, 0), "unclassified": (8, 0),
          "living_street": (7, 0), "service": (4.5, 0), "pedestrian": (5, 2), "busway": (7, 0)}
CAMINOS = {"footway", "path", "cycleway", "steps", "track", "corridor"}
VIAS = {"rail", "subway", "tram", "narrow_gauge", "light_rail", "funicular"}


def _tiene(tags, claves):
    return any((k, tags.get(k)) in claves for k, _ in claves)


def calles_y_municipios(osm, hojas):
    """bcn_calles.bin: 'BCNC', n nombres, n tramos, rejilla de municipios (x0, y0, paso, ancho, alto); nombres
    en UTF-8 con 0 al final; tramos float32 x0 y0 x1 y1 + int32 nombre (bit 30: puente, cuenta 15 m más lejos); rejilla uint8 (0 nada, k municipio k)."""
    import struct
    nombres, idx, tramos = [], {}, []
    for v in osm["vias"]:
        t = v["tags"]
        nom = t.get("name:ca") or t.get("name")
        if t.get("highway") not in ANCHOS or not nom or len(v["xy"]) < 2:
            continue
        if t.get("tunnel") not in (None, "no"):  # el túnel va por debajo: en la calle de arriba no se nombra
            continue
        puente = t.get("bridge") not in (None, "no")
        if nom not in idx:
            idx[nom] = len(nombres)
            nombres.append(nom)
        c = _a_juego(v["xy"])
        for a, b in zip(c[:-1], c[1:]):
            tramos.append((*a, *b, idx[nom] | (0x40000000 if puente else 0)))  # bit 30: puente
    tramos = [t for t in tramos if X0 <= t[0] < X0 + NBX * BLOQUE and Y0 <= t[1] < Y0 + NBY * BLOQUE]
    # municipio de cada cuadro de 100 m: el de más edificios del Catastro dentro
    paso, ancho, alto = 100.0, int(NBX * BLOQUE / 100), int(NBY * BLOQUE / 100)
    cuenta = np.zeros((len(config_v.MUNICIPIOS) + 1, alto, ancho), np.int32)
    munis = list(config_v.MUNICIPIOS)
    for k, muni in enumerate(munis, 1):
        f = config_v.DATOS / "catastro" / f"{muni}.pkl"
        if not f.exists():
            continue
        with open(f, "rb") as fh:
            c = np.array([p["anillos"][0].mean(0) for p in pickle.load(fh)["partes"]])
        g = _a_juego(c)
        i = ((g[:, 0] - X0) // paso).astype(int)
        j = ((g[:, 1] - Y0) // paso).astype(int)
        ok = (i >= 0) & (i < ancho) & (j >= 0) & (j < alto)
        np.add.at(cuenta[k], (j[ok], i[ok]), 1)
    rej = cuenta.argmax(0).astype(np.uint8)
    # los cuadros sin edificios (parques, calles anchas) toman el del vecino más cercano con edificios
    from scipy import ndimage
    vacio = rej == 0
    if vacio.any() and (~vacio).any():
        _, (jj, ii) = ndimage.distance_transform_edt(vacio, return_indices=True)
        cerca = ndimage.distance_transform_edt(vacio) <= 10
        rej = np.where(vacio & cerca, rej[jj, ii], rej)
    datos = [b"BCNC", struct.pack("<iifffii", len(nombres) + len(munis), len(tramos), X0, Y0, paso, ancho, alto)]
    for n in nombres + [config_v.MUNICIPIOS[m] for m in munis]:
        datos.append(n.encode("utf-8") + bytes(1))
    datos.append(np.array([t[:4] for t in tramos], np.float32).tobytes())
    datos.append(np.array([t[4] for t in tramos], np.int32).tobytes())
    # la rejilla apunta a los nombres de municipio (tras los de calles); 0 = nada
    m = np.where(rej > 0, rej.astype(np.int32) - 1 + len(nombres), -1).astype(np.int32)
    datos.append(m.tobytes())  # fila 0 = sur
    (OBRA / "bcn_calles.bin").write_bytes(b"".join(datos))
    print(f"bcn_calles.bin: {len(nombres)} calles, {len(tramos)} tramos")


def cargar():
    with open(config_v.DATOS / "osm.pkl", "rb") as fh:
        osm = pickle.load(fh)
    import prototipo
    edificios = []
    for muni in config_v.MUNICIPIOS:
        f = config_v.DATOS / "catastro" / f"{muni}.pkl"
        if f.exists():
            with open(f, "rb") as fh:
                edificios += [p["anillos"][0] for p in pickle.load(fh)["partes"]
                              if not prototipo.construccion_gigante(p)]
    hojas = config_v.hojas()
    import costa_v
    return osm, edificios, hojas, costa_v.mar()


def _a_juego(xy):
    xy = np.asarray(xy, np.float64)
    return np.c_[config_v.utm_a_juego(xy[:, 0], xy[:, 1])]


class Capa:
    """Elementos (coordenadas del juego) con su caja, para sacar los de un bloque rápido."""
    def __init__(self, items):
        self.items = items
        self.arbol = STRtree([shapely.box(*c.min(0), *c.max(0)) for c, _ in items]) if items else None

    def en(self, x0, y0, x1, y1):
        if not self.arbol:
            return []
        return [self.items[i] for i in self.arbol.query(shapely.box(x0, y0, x1, y1))]


def preparar(osm, edificios):
    verdes, arenas, peatonales, agua = [], [], [], []
    for a in osm["areas"]:
        t = a["tags"]
        if len(a["xy"]) < 3:
            continue
        c = _a_juego(a["xy"])
        if _tiene(t, ARENAS):
            arenas.append((c, None))
        elif _tiene(t, VERDES):
            verdes.append((c, None))
        elif _tiene(t, PEATONALES):
            peatonales.append((c, None))
        elif t.get("natural") == "water":
            agua.append((c, None))
    calles, caminos, vias, puentes = [], [], [], []
    for v in osm["vias"]:
        t = v["tags"]
        if len(v["xy"]) < 2:
            continue
        hw, rw = t.get("highway"), t.get("railway")
        tunel = t.get("tunnel") not in (None, "no") or t.get("layer", "0").startswith("-")
        if hw in ANCHOS and not (hw == "pedestrian" and t.get("area") == "yes"):
            ancho, tipo = ANCHOS[hw]
            item = (_a_juego(v["xy"]), (ancho, tipo, tunel))
            (puentes if t.get("bridge") not in (None, "no") else calles).append(item)
        elif hw in CAMINOS and not tunel and t.get("indoor") != "yes":
            caminos.append((_a_juego(v["xy"]), None))
        elif rw in VIAS and not tunel:
            vias.append((_a_juego(v["xy"]), t.get("bridge") not in (None, "no")))
    edif = [(_a_juego(a), None) for a in edificios]
    return {k: Capa(v) for k, v in dict(verdes=verdes, arenas=arenas, peatonales=peatonales, agua=agua,
                                         calles=calles, caminos=caminos, vias=vias, puentes=puentes,
                                         edificios=edif).items()}


def dibujar_bloque(bx, by, capas, tierra):
    """Imagen RGB del bloque (BLOQUE m a 2 m/px). tierra: geometría (juego) de lo que no es mar."""
    x0, y0 = X0 + bx * BLOQUE, Y0 + by * BLOQUE
    x1, y1 = x0 + BLOQUE, y0 + BLOQUE
    lado = int(BLOQUE / TESELA * PX) * SS
    k = lado / BLOQUE
    img = Image.new("RGB", (lado, lado), TIERRA)
    d = ImageDraw.Draw(img)
    mascara = Image.new("L", (lado, lado), 0)   # tierra: lo de fuera (mar, hojas que no hay) se pinta de mar
    dm = ImageDraw.Draw(mascara)

    def px(c):
        return [((x - x0) * k, (y1 - y) * k) for x, y in c]

    caja = shapely.box(x0 - 20, y0 - 20, x1 + 20, y1 + 20)
    t = tierra.intersection(caja)
    if t.is_empty:
        return None
    for g in shapely.get_parts(t):
        if g.geom_type != "Polygon":
            continue
        dm.polygon(px(g.exterior.coords), fill=255)
        for h in g.interiors:
            dm.polygon(px(h.coords), fill=0)
    m = 30  # margen: lo que sale un poco del bloque
    q = (x0 - m, y0 - m, x1 + m, y1 + m)
    for nombre, color in (("peatonales", PEATONAL), ("verdes", VERDE), ("arenas", ARENA), ("agua", AGUA)):
        for c, _ in capas[nombre].en(*q):
            d.polygon(px(c), fill=color)
    for c, _ in capas["caminos"].en(*q):
        d.line(px(c), fill=CAMINO, width=max(1, int(1.6 * k)))
    for c, _ in capas["edificios"].en(*q):
        d.polygon(px(c), fill=EDIFICIO, outline=BORDE_EDIF)
    for c, puente in capas["vias"].en(*q):
        if not puente:
            d.line(px(c), fill=VIA, width=max(1, int(2.2 * k)))

    def calles(items, borde=True):
        orden = sorted(items, key=lambda it: (it[1][1] == 1, it[1][0]))
        if borde:
            for c, (ancho, tipo, tunel) in orden:
                if not tunel:
                    d.line(px(c), fill=BORDE_CALLE, width=int((ancho + 2.4) * k), joint="curve")
        for c, (ancho, tipo, tunel) in orden:
            color = AUTOPISTA if tipo == 1 else PEATONAL if tipo == 2 else CALLE
            if tunel:  # túneles: más finos y apagados
                color = tuple(int(0.55 * a + 0.45 * b) for a, b in zip(color, TIERRA))
                d.line(px(c), fill=color, width=max(1, int(ancho * 0.5 * k)))
            else:
                d.line(px(c), fill=color, width=int(ancho * k), joint="curve")
    calles(capas["calles"].en(*q))
    for c, puente in capas["vias"].en(*q):
        if puente:
            d.line(px(c), fill=VIA, width=max(1, int(2.2 * k)))
    calles(capas["puentes"].en(*q))
    img = Image.composite(img, Image.new("RGB", img.size, MAR), mascara)
    return img.resize((lado // SS, lado // SS), Image.LANCZOS)


def flecha(lado=64):
    """Flecha del jugador (punta arriba), blanca con borde negro."""
    img = Image.new("RGBA", (lado * 4, lado * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = lado * 4
    pts = [(s * 0.5, s * 0.06), (s * 0.86, s * 0.92), (s * 0.5, s * 0.72), (s * 0.14, s * 0.92)]
    d.polygon(pts, fill=(0, 0, 0, 255))
    c = np.array([s * 0.5, s * 0.6])
    d.polygon([tuple(c + (np.array(p) - c) * 0.72) for p in pts], fill=(255, 255, 255, 255))
    return img.resize((lado, lado), Image.LANCZOS)


def main():
    osm, edificios, hojas, mar = cargar()
    capas = preparar(osm, edificios)
    # tierra: las hojas del mapa (fuera, el juego tiene agua) menos el mar
    cuadros = []
    for h in hojas:
        e0, n0 = int(h[:3]) * 1000, (4000 + int(h[3:])) * 1000
        x, y = config_v.utm_a_juego(e0, n0)
        cuadros.append(shapely.box(x, y, x + 1000, y + 1000))
    tierra = shapely.union_all(cuadros)
    if mar is not None:
        mar_j = shapely.transform(mar, lambda c: _a_juego(c))
        tierra = tierra.difference(mar_j)
    shapely.prepare(tierra)
    shutil.rmtree(OBRA, ignore_errors=True)
    xml = OBRA / "xml"
    xml.mkdir(parents=True)
    general = {}
    bloques = []
    enteros = {}
    n = int(BLOQUE / TESELA)
    for bx in range(NBX):
        for by in range(NBY):
            img = dibujar_bloque(bx, by, capas, tierra)
            if img is None:
                continue
            bloques.append((bx, by))
            tex = {}
            for i in range(n):          # i: columna (este), j: fila desde el sur
                for j in range(n):
                    caja = (i * PX, (n - 1 - j) * PX, (i + 1) * PX, (n - j) * PX)
                    tex[f"t{i}{j}"] = (img.crop(caja), False)
            rage.escribir_ytd(xml / f"{PACK}_{bx}_{by}.ytd.xml", tex)
            general[f"m_{bx}_{by}"] = (img.resize((PX, PX), Image.LANCZOS), False)
            enteros[(bx, by)] = img
            print(f"bloque {bx},{by}", flush=True)
    import mapa_pausa_v  # el mismo plano en el mapa del menú de pausa (texturas minimap_sea_*)
    mapa_pausa_v.teselas(enteros)
    del enteros
    general["flecha"] = (flecha(), True)
    general["mar"] = (Image.new("RGB", (8, 8), MAR), False)        # fondo: el mismo color que el mar comprimido
    general["blanco"] = (Image.new("RGB", (8, 8), (255, 255, 255)), False)  # se tiñe al dibujar (marco, barras)
    rage.escribir_ytd(xml / f"{PACK}_mapa.ytd.xml", general)
    vista = Image.new("RGB", (NBX * PX, NBY * PX), MAR)  # vista previa del plano entero
    for bx, by in bloques:
        vista.paste(general[f"m_{bx}_{by}"][0], (bx * PX, (NBY - 1 - by) * PX))
    vista.save(OBRA / "plano.png")
    info = [f"{X0:.0f} {Y0:.0f} {BLOQUE:.0f} {TESELA:.0f} {NBX} {NBY}"] + [f"{bx} {by}" for bx, by in bloques]
    (OBRA / "bcn_radar.txt").write_text("\n".join(info) + "\n", encoding="utf-8")
    calles_y_municipios(osm, hojas)
    if config_v.os.environ.get("BCN_TRAFICO", "1") != "0":  # BCN_TRAFICO=0: sin caminos de coches
        import trafico_v  # los caminos de coches van en el mismo DLC
        trafico_v.escribir(xml, osm, hojas)
    empaquetar(xml)


CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<CDataFileMgr__ContentsOfDataFileXml>
  <disabledFiles />
  <includedXmlFiles />
  <includedDataFiles />
  <dataFiles>
    <Item>
      <filename>dlc_{p}:/%PLATFORM%/levels/gta5/{p}.rpf</filename>
      <fileType>RPF_FILE</fileType>
      <overlay value="false" />
      <disabled value="true" />
      <persistent value="true" />
    </Item>
  </dataFiles>
  <contentChangeSets>
    <Item>
      <changeSetName>{P}_MAPA</changeSetName>
      <filesToEnable>
        <Item>dlc_{p}:/%PLATFORM%/levels/gta5/{p}.rpf</Item>
      </filesToEnable>
    </Item>
  </contentChangeSets>
  <patchFiles />
</CDataFileMgr__ContentsOfDataFileXml>
"""


def empaquetar(xml):
    dlc = OBRA / "dlc"
    rage.a_binario(xml, dlc / "x64" / "levels" / "gta5" / f"{PACK}.rpf")
    (dlc / "content.xml").write_text(CONTENT.format(p=PACK, P=PACK.upper()), encoding="utf-8")
    (dlc / "setup2.xml").write_text(empaquetar_v.SETUP.format(p=PACK, P=PACK.upper()), encoding="utf-8")
    archivo = OBRA / "dlc.rpf"
    rage.empaquetar_rpf(dlc, archivo)
    print(f"{archivo}: {archivo.stat().st_size / 1e6:.0f} MB")
    if "--sin-instalar" in sys.argv:
        return
    if empaquetar_v._juego_abierto():
        sys.exit("Juego abierto: ciérralo para instalar")
    gta = empaquetar_v.GTA
    destino = gta / "mods" / "update" / "x64" / "dlcpacks" / PACK / "dlc.rpf"
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archivo, destino)
    shutil.copy2(OBRA / "bcn_radar.txt", gta / "bcn_radar.txt")
    shutil.copy2(OBRA / "bcn_calles.bin", gta / "bcn_calles.bin")
    r = rage.subprocess.run([str(rage.DOTNET), str(rage.CWTOOL), "dlclist", str(gta),
                             str(gta / "mods" / "update" / "update.rpf"), PACK], capture_output=True, text=True)
    print(r.stdout.strip(), r.stderr.strip())
    print("Instalado", destino)


if __name__ == "__main__":
    main()
