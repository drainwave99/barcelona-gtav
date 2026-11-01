"""Empaqueta el mapa para el juego a partir de lo exportado por blender_exportar.py.

Genera en mod/:
  modelos/*.txd                   texturas: un TXD por trozo de terreno + bdn_edificios.txd
  models/badalona.img             todos los .dff, .txd y .col
  data/maps/badalona/badalona.ide definiciones de modelos (IDs prestados de Los Santos)
  data/maps/badalona/badalona.ipl colocación (posiciones de datos/generado/posiciones.json)
"""
import json
import struct
import sys

import numpy as np

from PIL import Image, ImageFilter

import config
from instalar_en_juego import ids_prestados
from rw_formatos import escribir_img, escribir_txd

DISTANCIA_TERRENO = 299  # sin LOD, el máximo razonable
DISTANCIA_EDIFICIOS = 250
PX_SUELO = 512
# Para pruebas: "python generar_mapa.py bdn_ter" coloca en el .ipl solo los modelos con ese prefijo
SOLO = sys.argv[1] if len(sys.argv) > 1 else ""
MOD = config.RAIZ / "mod"
MODELOS = MOD / "modelos"
GENERADO = config.DATOS / "generado"


def txds():
    hechos = []
    for nombre in sorted(p.stem for p in MODELOS.glob("bdn_ter_*.dff")):
        f, c = nombre.split("_")[2:4]
        ruta = MODELOS / f"{nombre}.txd"
        # La ortofoto (descargar_orto.py) si está; si no, el suelo pintado con OSM
        orto = GENERADO / "suelo_orto" / f"suelo_{f}_{c}.png"
        imagen = orto if orto.exists() else GENERADO / "suelo" / f"suelo_{f}_{c}.png"
        # 512 px: el juego solo tiene ~50 MB para lo que carga alrededor (las calles ya llevan sus texturas)
        suelo = Image.open(imagen).convert("RGB").resize((PX_SUELO, PX_SUELO), Image.LANCZOS)
        escribir_txd(ruta, [(f"suelo_{f}_{c}", reverdecer(suelo, int(f), int(c)))])
        hechos.append(ruta)
    ruta = MODELOS / "bdn_edificios.txd"
    escribir_txd(ruta, [(p.stem, Image.open(p)) for p in sorted((GENERADO / "texturas").glob("??_*.png"))])
    hechos.append(ruta)
    # Radar: radar00..radar143.txd sustituyen a los del juego (instalar_en_juego.py los mete en gta3.img)
    radar = MOD / "radar"
    radar.mkdir(parents=True, exist_ok=True)
    for i in range(144):
        escribir_txd(radar / f"radar{i:02d}.txd", [(f"radar{i:02d}", Image.open(GENERADO / "radar" / f"radar{i:02d}.png"))],
                     mipmaps=False)
    print(f"TXD: {len(hechos)} + 144 del radar")


def ide_ipl():
    """Escribe el .ide/.ipl y devuelve {nombre de modelo: ID}."""
    with open(GENERADO / "posiciones.json", encoding="utf-8") as fh:
        posiciones = json.load(fh)
    nombres = sorted(posiciones, key=lambda n: (not n.startswith("bdn_ter"), n))
    ids, _ = ids_prestados(len(nombres))

    carpeta = MOD / "data" / "maps" / "badalona"
    carpeta.mkdir(parents=True, exist_ok=True)
    with open(carpeta / "badalona.ide", "w", encoding="ascii", newline="\r\n") as ide, \
         open(carpeta / "badalona.ipl", "w", encoding="ascii", newline="\r\n") as ipl:
        ide.write("# Mapa de Badalona - generado por herramientas/generar_mapa.py\nobjs\n")
        ipl.write("# Mapa de Badalona - generado por herramientas/generar_mapa.py\ninst\n")
        for ident, nombre in zip(ids, nombres):
            terreno = nombre.startswith("bdn_ter")
            txd = nombre if terreno else "bdn_edificios"
            ide.write(f"{ident}, {nombre}, {txd}, {DISTANCIA_TERRENO if terreno else DISTANCIA_EDIFICIOS}, 0\n")
            x, y, z = posiciones[nombre]
            if SOLO and not nombre.startswith(SOLO):
                continue
            ipl.write(f"{ident}, {nombre}, 0, {x:.3f}, {y:.3f}, {z:.3f}, 0, 0, 0, 1, -1\n")
        ide.write("end\n")
        # El terreno usa también las texturas de calle (asfalto, panot...) de bdn_edificios.txd
        ide.write("txdp\n")
        for nombre in nombres:
            if nombre.startswith("bdn_ter"):
                ide.write(f"{nombre}, bdn_edificios\n")
        ide.write("end\n")
        ipl.write("end\n")
    print(f"IDE/IPL: {len(nombres)} modelos (IDs prestados {min(ids)}-{max(ids)})")
    return dict(zip(nombres, ids))


COL_MAX = 2_000_000  # el archivo más grande del juego original ocupa 2,6 MB; más grande, la carga se cuelga


LUZ_SUELO = 0x6F  # luz de las caras de colisión: día 15 (bits bajos), noche 6 (bits altos)
TAM_TROZO = config.LADO / 16  # trozos de terreno de blender_terreno.py, con el origen en su centro
# Superficies de data/surfinfo.dat: el juego pinta hierba (plants.dat) y planta matorrales y árboles
# (procobj.dat) según la superficie de la colisión que hay cerca de la cámara
BOSQUE, HIERBA, HIERBA_SECA, MATORRAL = 128, 10, 13, 111  # P_FORESTSTUMPS, GRASS_MEDIUM_LUSH, GRASS_MEDIUM_DRY, P_BUSHY


_VERDE = []


def zona_verde():
    """Máscara de parques, bosque y monte del radar (procesar_osm.py), 1536 px de lado (~4 m): fuera
    de ella no hay hierba, para que no atraviese calles y patios."""
    if not _VERDE:
        radar = np.zeros((1536, 1536, 3), dtype=np.float32)
        for i in range(144):
            f, c = divmod(i, 12)
            radar[f * 128:(f + 1) * 128, c * 128:(c + 1) * 128] = np.asarray(
                Image.open(GENERADO / "radar" / f"radar{i:02d}.png").convert("RGB"), dtype=np.float32)
        _VERDE.append(radar[..., 1] - (radar[..., 0] + radar[..., 2]) / 2 > 20)
    return _VERDE[0]


def reverdecer(suelo, f, c):
    """La ortofoto es de verano y el monte sale pardo: en parques y monte se acerca el pardo al verde
    (con la máscara suavizada para que no se note el borde)."""
    lado = 1536 // 16
    mascara = Image.fromarray(zona_verde()[f * lado:(f + 1) * lado, c * lado:(c + 1) * lado].astype(np.uint8) * 255)
    k = np.asarray(mascara.resize(suelo.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(6)),
                   dtype=np.float32)[..., None] / 255 * 0.6
    a = np.asarray(suelo, dtype=np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    gris = (r + g + b) / 3
    verde = np.stack([gris * 0.72, gris * 0.92 + 4, gris * 0.50], axis=-1)
    k = k * np.clip((170 - gris) / 50, 0, 1)[..., None]  # los caminos y la roca clara se quedan como están
    return Image.fromarray((a * (1 - k) + verde * k).clip(0, 255).astype(np.uint8))


def superficie(rgb, i):
    """Superficie según el color medio de la ortofoto bajo la cara (gris = calle o edificio, sin hierba)."""
    r, g, b = rgb
    verde = g - (r + b) / 2
    if verde > 3 and g < 95:
        return BOSQUE if i % 3 else MATORRAL
    if verde > 3:
        return HIERBA
    if r - b > 18 and r > 70:
        return HIERBA_SECA if i % 4 else MATORRAL
    return 0


def luz_caras(datos, pos, nombre):
    """Los peatones y coches toman la luz de la cara de colisión que pisan; DragonFF la deja a 0 y CJ
    sale negro. En el terreno pone además la superficie según la ortofoto. Cabecera COL2/3: tras el
    nombre, ID y los límites (40 bytes) van los contadores y los desplazamientos (relativos a pos + 4).
    Cada vértice: x, y, z (i16 / 128); cada cara: a, b, c (u16), material (u8), luz (u8)."""
    # u16 esferas, u16 cajas, u16 caras, u8 ruedas, u8 relleno, u32 flags, desplazamientos de esferas,
    # cajas, ruedas, vértices y caras
    base = pos + 32 + 40
    caras = struct.unpack_from("<H", datos, base + 4)[0]
    desp_verts, desp_caras = struct.unpack_from("<2I", datos, base + 24)
    inicio = pos + 4 + desp_caras
    if inicio + 8 * caras > pos + 8 + struct.unpack_from("<I", datos, pos + 4)[0]:
        raise SystemExit(f"Colisión rara en {pos}: {caras} caras en {desp_caras}")
    orto = None
    if nombre.startswith("bdn_ter"):
        f, c = nombre.split("_")[2:4]
        verde = zona_verde()
        # centro del trozo en el mapa
        cx, cy = -config.MITAD + (int(c) + 0.5) * TAM_TROZO, config.MITAD - (int(f) + 0.5) * TAM_TROZO
        ruta = GENERADO / "suelo_orto" / f"suelo_{f}_{c}.png"
        if ruta.exists():
            # Color medio en casillas de ~3 m para que una sombra o un coche no decidan la superficie
            orto = np.asarray(Image.open(ruta).convert("RGB").resize((128, 128), Image.BOX), dtype=np.float32)
    for i in range(caras):
        cara = inicio + 8 * i
        if orto is not None:
            a, b, c = struct.unpack_from("<3H", datos, cara)
            x = y = 0.0
            for v in (a, b, c):
                vx, vy, _ = struct.unpack_from("<3h", datos, pos + 4 + desp_verts + 6 * v)
                x += vx / 384
                y += vy / 384
            px = min(max(int((x / TAM_TROZO + 0.5) * 128), 0), 127)
            py = min(max(int((0.5 - y / TAM_TROZO) * 128), 0), 127)
            mx = min(max(int((cx + x + config.MITAD) / config.LADO * 1536), 0), 1535)
            my = min(max(int((config.MITAD - cy - y) / config.LADO * 1536), 0), 1535)
            datos[cara + 6] = superficie(orto[py, px], i) if verde[my, mx] else 0
        datos[cara + 7] = LUZ_SUELO


def colisiones(ids):
    """Agrupa las colisiones de las filas del mapa en archivos badalona_NN.col de hasta COL_MAX bytes,
    poniendo en cada cabecera el ID de su modelo (DragonFF lo deja a 0 y el juego asigna por ese ID).
    Hay pocos huecos de archivos .col (255 en total), por eso se agrupan filas."""
    for viejo in MODELOS.glob("badalona*.col"):
        viejo.unlink()
    grupos, actual = [], bytearray()
    for fila in sorted(MODELOS.glob("bdn_col_*.col")):
        datos = bytearray(fila.read_bytes())
        pos = 0
        while pos < len(datos):
            tipo, tam = struct.unpack_from("<4sI", datos, pos)
            if tipo[:3] != b"COL":
                raise SystemExit(f"{fila.name}: cabecera rara en {pos}: {tipo}")
            nombre = bytes(datos[pos + 8:pos + 30]).split(b"\0")[0].decode("ascii")
            struct.pack_into("<H", datos, pos + 30, ids[nombre])
            luz_caras(datos, pos, nombre)
            pos += 8 + tam
        if actual and len(actual) + len(datos) > COL_MAX:
            grupos.append(actual)
            actual = bytearray()
        actual += datos
    grupos.append(actual)
    rutas = []
    for i, datos in enumerate(grupos):
        ruta = MODELOS / f"badalona_{i:02d}.col"
        ruta.write_bytes(datos)
        rutas.append(ruta)
    print(f"COL: {len(rutas)} archivos, el mayor de {max(len(g) for g in grupos) / 1e6:.2f} MB")
    return rutas


def img(colisiones_mapa):
    archivos = sorted(p for ext in ("dff", "txd") for p in MODELOS.glob(f"*.{ext}")) + colisiones_mapa
    (MOD / "models").mkdir(parents=True, exist_ok=True)
    ruta = MOD / "models" / "badalona.img"
    escribir_img(ruta, archivos)
    print(f"IMG: {len(archivos)} archivos, {ruta.stat().st_size / 1e6:.1f} MB -> {ruta}")


def main():
    txds()
    img(colisiones(ide_ipl()))


if __name__ == "__main__":
    main()
