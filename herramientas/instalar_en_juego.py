"""Instala (o quita) el mapa de Badalona en el juego.

  python herramientas/instalar_en_juego.py            instala
  python herramientas/instalar_en_juego.py quitar     deja el juego como estaba

Antes de tocar nada guarda los originales en copia_juego/ (dentro del proyecto). Cambios:
  - data/gta.dat: quita los .ipl del mapa original (deja las zonas) y añade badalona.img/.ide/.ipl
  - data/water.dat: agua solo donde Badalona tiene mar
  - copia models/badalona.img y data/maps/badalona/
"""
import json
import shutil
import struct
import sys
from pathlib import Path

import numpy as np

import config

JUEGO = Path(r"C:\Program Files (x86)\DODI-Repacks\Grand Theft Auto San Andreas")
MOD = config.RAIZ / "mod"
COPIA = config.RAIZ / "copia_juego"
# El juego original ya usa casi todos los modelos de objeto que admite (~14.000): Badalona
# reutiliza los IDs de edificios de Los Santos de estos IDE (sin sus IPL ya no se usan).
IDE_PRESTADOS = ["data/maps/LA/LAe.ide", "data/maps/LA/LAe2.ide", "data/maps/LA/LAhills.ide"]
# Además se desactivan todos los modelos de otros barrios de Los Santos: el juego solo admite 10.150
# colisiones cargadas y el original ya usa ~9.700; esto deja margen para Badalona, coches y peatones.
IDE_LIBERADOS = ["data/maps/LA/LAn.ide", "data/maps/LA/LAn2.ide", "data/maps/LA/LAs.ide", "data/maps/LA/LAs2.ide"]
# El main.scm original espera el mapa de Los Santos y la carga se cuelga: se pone el de
# generar_main_scm.py (sin misiones, CJ aparece en la Rambla).
GUION = ["data/script/main.scm", "data/script/script.img"]
# Nombres de zona: info.zon de generar_zonas.py y sus textos en los .gxt
TEXTOS = ["text/american.gxt", "text/spanish.gxt"]
ORIGINALES = ["data/gta.dat", "data/water.dat", "data/info.zon"] + IDE_PRESTADOS + IDE_LIBERADOS + GUION + TEXTOS
CELDA = 50  # tamaño de las celdas de agua (múltiplo de 2)


def copia_seguridad():
    for rel in ORIGINALES:
        destino = COPIA / rel
        if not destino.exists():  # nunca se sobrescribe la copia del original
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(JUEGO / rel, destino)
    print(f"Copia de seguridad en {COPIA}")


def gta_dat():
    original = (COPIA / "data/gta.dat").read_text(encoding="latin-1").splitlines()
    nuevo = []
    for linea in original:
        partes = linea.split()
        if partes and partes[0].upper() == "IPL" and not partes[1].upper().endswith(".ZON"):
            nuevo.append("# (mapa original quitado) " + linea)
        else:
            nuevo.append(linea)
    # El IMG tiene que ir antes que los IDE, y el IDE antes del primer IPL: al llegar al primer IPL
    # el juego carga todas las colisiones y solo las asigna a los modelos que ya conoce.
    primero_ide = next(i for i, l in enumerate(nuevo) if l.upper().startswith("IDE "))
    nuevo.insert(primero_ide, "IMG MODELS\\BADALONA.IMG")
    primero_ipl = next(i for i, l in enumerate(nuevo) if l.upper().startswith("IPL "))
    nuevo.insert(primero_ipl, "IDE DATA\\MAPS\\BADALONA\\BADALONA.IDE")
    nuevo.append("")
    nuevo.append("# Mapa de Badalona")
    nuevo.append("IPL DATA\\MAPS\\BADALONA\\BADALONA.IPL")
    for detalle in sorted((MOD / "data" / "maps" / "badalona").glob("*.ipl")):
        if detalle.name == "badalona.ipl":
            continue
        nuevo.append(f"IPL DATA\\MAPS\\BADALONA\\{detalle.name.upper()}")
    (JUEGO / "data/gta.dat").write_text("\r\n".join(nuevo) + "\r\n", encoding="latin-1", newline="")


def water_dat():
    """Una celda de agua donde el relieve tiene mar; las celdas seguidas de una fila se juntan."""
    h = np.load(config.DATOS / "elevacion" / "relieve_gta.npy")
    n = h.shape[0] - 1
    celdas = int(config.LADO // CELDA)
    px = n / celdas
    lineas = ["processed"]
    vertice = "{:.1f} {:.1f} 0.00000 0.00000 0.00000 0.05100 0.10200"
    for fila in range(celdas):
        y1 = config.MITAD - fila * CELDA
        y0 = y1 - CELDA
        inicio = None
        for col in range(celdas + 1):
            agua = False
            if col < celdas:
                trozo = h[int(fila * px):int((fila + 1) * px) + 1, int(col * px):int((col + 1) * px) + 1]
                agua = (trozo < 0).any()
            if agua and inicio is None:
                inicio = col
            elif not agua and inicio is not None:
                x0 = -config.MITAD + inicio * CELDA
                x1 = -config.MITAD + col * CELDA
                esquinas = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
                lineas.append("    ".join(vertice.format(x, y) for x, y in esquinas) + "  1")
                inicio = None
    (JUEGO / "data/water.dat").write_text("\n".join(lineas) + "\n", encoding="ascii")
    print(f"water.dat: {len(lineas) - 1} zonas de agua")


def ids_prestados(necesarios):
    """IDs de modelos de Los Santos que usará Badalona y el texto de los IDE con esos modelos comentados.

    Siempre se lee el IDE original (de la copia de seguridad si ya existe), así generar_mapa.py y
    la instalación eligen exactamente los mismos IDs."""
    ids, textos = [], {}
    for rel in IDE_PRESTADOS + IDE_LIBERADOS:
        original = COPIA / rel if (COPIA / rel).exists() else JUEGO / rel
        lineas = original.read_text(encoding="latin-1").splitlines()
        if any(l.startswith("# (badalona)") for l in lineas):
            raise SystemExit(f"{original} ya está modificado: falta la copia de seguridad del original")
        seccion = None
        for i, linea in enumerate(lineas):
            limpia = linea.split("#")[0].strip()
            if limpia.lower() in ("objs", "tobj", "anim", "2dfx", "txdp", "end"):
                seccion = None if limpia.lower() == "end" else limpia.lower()
                continue
            partes = [p.strip() for p in limpia.split(",")]
            if seccion != "objs" or len(partes) < 5:
                continue
            # Todos los modelos se desactivan; los primeros que no son LOD se prestan a Badalona
            lineas[i] = "# (badalona) " + linea
            if rel in IDE_PRESTADOS and not partes[1].lower().startswith("lod") and len(ids) < necesarios:
                ids.append(int(partes[0]))
        textos[rel] = "\r\n".join(lineas) + "\r\n"
    if len(ids) < necesarios:
        raise SystemExit(f"Solo hay {len(ids)} IDs para prestar y hacen falta {necesarios}")
    return ids, textos


def copiar_mapa():
    """Copia badalona.ide/.ipl (ya con los IDs prestados) y comenta esos modelos en los IDE de Los Santos."""
    origen = MOD / "data" / "maps" / "badalona"
    necesarios = sum(1 for l in (origen / "badalona.ide").read_text(encoding="ascii").splitlines() if l[:1].isdigit())
    ids, textos = ids_prestados(necesarios)
    for rel, texto in textos.items():
        (JUEGO / rel).write_text(texto, encoding="latin-1", newline="")
    shutil.copytree(origen, JUEGO / "data" / "maps" / "badalona", dirs_exist_ok=True)
    print(f"{necesarios} modelos con IDs prestados de Los Santos ({min(ids)}-{max(ids)})")


def cabecera_img(ruta):
    with open(ruta, "rb") as fh:
        tipo, n = struct.unpack("<4sI", fh.read(8))
        return fh.read(32 * n) if tipo == b"VER2" else None, n


IMG_CON_IPL = ["gta3.img", "gta_int.img"]
# Colisiones de los barrios desactivados (IDE_PRESTADOS + IDE_LIBERADOS): se ocultan para dejar huecos
# de archivos .col (máximo 255) a Badalona.
COL_OCULTAS = ("lae_", "lae2_", "lahills_", "lan_", "lan2_", "las_", "las2_")


def modelos_desactivados():
    """Nombres de .dff de los modelos comentados en los IDE de Los Santos. Un .dff sin modelo va a la
    lista de "objetos extra" del juego (550 huecos); si se llena, no encuentra player.dff y se cuelga."""
    nombres = set()
    for rel in IDE_PRESTADOS + IDE_LIBERADOS:
        original = COPIA / rel if (COPIA / rel).exists() else JUEGO / rel
        seccion = None
        for linea in original.read_text(encoding="latin-1").splitlines():
            limpia = linea.split("#")[0].strip()
            if limpia.lower() in ("objs", "tobj", "anim", "2dfx", "txdp", "end"):
                seccion = None if limpia.lower() == "end" else limpia.lower()
                continue
            partes = [p.strip() for p in limpia.split(",")]
            if seccion == "objs" and len(partes) >= 5:
                nombres.add(partes[1].lower() + ".dff")
    return nombres


def ocultar_ipl_binarios():
    """Los .ipl binarios de los .img (p. ej. lae_stream0.ipl, int_la_stream0.ipl) se cargan siempre
    aunque gta.dat ya no cargue el mapa original, y sin su .ipl de texto el juego se cuelga. Se renombran
    a .ip_ solo en el índice del .img (el contenido no se toca); el índice original queda en copia_juego/.
    Igual con las colisiones de COL_OCULTAS y los .dff de modelos_desactivados()."""
    sin_modelo = modelos_desactivados()
    for nombre_img in IMG_CON_IPL:
        img = JUEGO / "models" / nombre_img
        copia = COPIA / f"{nombre_img}_indice.bin"
        indice, n = cabecera_img(img)
        if not copia.exists():
            copia.write_bytes(indice)
        nuevo = bytearray(copia.read_bytes())
        cambiados = 0
        for i in range(n):
            nombre = nuevo[32 * i + 8:32 * i + 32]
            fin = nombre.find(b"\0")
            texto = bytes(nombre[:fin]).decode("latin-1").lower()
            if (texto.endswith(".ipl") or texto in sin_modelo
                    or (texto.endswith(".col") and texto.startswith(COL_OCULTAS))):
                nuevo[32 * i + 8 + fin - 1] = ord("_")
                cambiados += 1
        with open(img, "r+b") as fh:
            fh.seek(8)
            fh.write(nuevo)
        print(f"{nombre_img}: {cambiados} IPL binarios, colisiones y modelos del mapa original desactivados")


def gxt_con_zonas():
    """Añade los nombres de barrio (mod/text/zonas.json) a la tabla MAIN de los textos del juego.
    Claves: JAMCRC del nombre, ordenadas. Los textos nuevos van al final de MAIN y las demás tablas
    se desplazan."""
    import zlib
    zonas = json.loads((MOD / "text" / "zonas.json").read_text(encoding="ascii"))
    for rel in TEXTOS:
        d = bytearray((COPIA / rel).read_bytes())
        n = struct.unpack_from("<I", d, 8)[0] // 12
        tablas = [list(struct.unpack_from("<8sI", d, 12 + 12 * i)) for i in range(n)]
        main = tablas[0][1]
        tam_claves = struct.unpack_from("<I", d, main + 4)[0]
        claves = [struct.unpack_from("<II", d, main + 8 + 8 * i) for i in range(tam_claves // 8)]
        tdat = main + 8 + tam_claves
        tam_tdat = struct.unpack_from("<I", d, tdat + 4)[0]
        fin_main = tdat + 8 + tam_tdat
        nuevos = b""
        for clave, texto in zonas.items():
            claves.append((tam_tdat + len(nuevos), zlib.crc32(clave.encode()) ^ 0xFFFFFFFF))
            nuevos += texto.encode("ascii") + b"\0"
        nuevos += b"\0" * (-len(nuevos) % 4)
        claves.sort(key=lambda c: c[1])
        cuerpo = (b"TKEY" + struct.pack("<I", 8 * len(claves)) + b"".join(struct.pack("<II", *c) for c in claves)
                  + b"TDAT" + struct.pack("<I", tam_tdat + len(nuevos)) + d[tdat + 8:fin_main] + nuevos)
        desplazamiento = len(cuerpo) - (fin_main - main)
        for i, (nombre, off) in enumerate(tablas):
            if i:
                struct.pack_into("<8sI", d, 12 + 12 * i, nombre, off + desplazamiento)
        (JUEGO / rel).write_bytes(bytes(d[:main]) + cuerpo + bytes(d[fin_main:]))
    print(f"Textos: {len(zonas)} nombres de barrio en {', '.join(TEXTOS)}")


def tamano_original_gta3():
    """Tamaño de gta3.img sin nada añadido (se apunta la primera vez, antes de añadir el radar)."""
    nota = COPIA / "gta3.img_tamano.txt"
    if not nota.exists():
        nota.write_text(str((JUEGO / "models" / "gta3.img").stat().st_size))
    return int(nota.read_text())


def poner_radar():
    """Añade los radarNN.txd de Badalona al final de gta3.img y apunta a ellos las entradas del
    índice (las texturas originales siguen dentro, sin usar)."""
    img = JUEGO / "models" / "gta3.img"
    original = tamano_original_gta3()
    indice, n = cabecera_img(img)
    indice = bytearray(indice)
    with open(img, "r+b") as fh:
        fh.truncate(original)
        sector = original // 2048
        puestos = 0
        for i in range(n):
            nombre = bytes(indice[32 * i + 8:32 * i + 32]).split(b"\0")[0].decode("latin-1").lower()
            nuevo = MOD / "radar" / nombre
            if nombre.startswith("radar") and nuevo.exists():
                datos = nuevo.read_bytes()
                tam = (len(datos) + 2047) // 2048
                fh.seek(sector * 2048)
                fh.write(datos + b"\0" * (tam * 2048 - len(datos)))
                struct.pack_into("<IHH", indice, 32 * i, sector, tam, 0)
                sector += tam
                puestos += 1
        fh.seek(8)
        fh.write(indice)
    print(f"gta3.img: radar de Badalona ({puestos} casillas)")


def restaurar_ipl_binarios():
    for nombre_img in IMG_CON_IPL:
        copia = COPIA / f"{nombre_img}_indice.bin"
        if copia.exists():
            with open(JUEGO / "models" / nombre_img, "r+b") as fh:
                fh.seek(8)
                fh.write(copia.read_bytes())
    if (COPIA / "gta3.img_tamano.txt").exists():
        with open(JUEGO / "models" / "gta3.img", "r+b") as fh:
            fh.truncate(tamano_original_gta3())


def instalar():
    copia_seguridad()
    shutil.copy2(MOD / "models" / "badalona.img", JUEGO / "models" / "badalona.img")
    copiar_mapa()
    gta_dat()
    water_dat()
    ocultar_ipl_binarios()
    poner_radar()
    shutil.copy2(MOD / "data" / "info.zon", JUEGO / "data" / "info.zon")
    gxt_con_zonas()
    for rel in GUION:
        shutil.copy2(MOD / rel, JUEGO / rel)
    print("Instalado. Para quitarlo: python herramientas/instalar_en_juego.py quitar")


def quitar():
    for rel in ORIGINALES:
        shutil.copy2(COPIA / rel, JUEGO / rel)
    restaurar_ipl_binarios()
    (JUEGO / "models" / "badalona.img").unlink(missing_ok=True)
    shutil.rmtree(JUEGO / "data" / "maps" / "badalona", ignore_errors=True)
    print("Juego restaurado al original")


if __name__ == "__main__":
    quitar() if sys.argv[1:] == ["quitar"] else instalar()
