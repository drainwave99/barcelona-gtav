"""Escritura de formatos de GTA SA que DragonFF no genera: diccionarios de texturas (.txd) y archivos .img (v2).

TXD: RenderWare 3.6 (0x1803FFFF), plataforma D3D9 de PC, texturas DXT1 con mipmaps.
IMG: versión 2 de SA ("VER2"), bloques de 2048 bytes.
"""
import struct

import numpy as np
from PIL import Image

RW_VERSION = 0x1803FFFF
SECTOR = 2048


# ---------------------------------------------------------------- DXT1

def _a565(c):
    c = c.astype(np.uint32)
    return ((c[..., 0] >> 3) << 11) | ((c[..., 1] >> 2) << 5) | (c[..., 2] >> 3)


def _de565(v):
    r = (v >> 11) & 31
    g = (v >> 5) & 63
    b = v & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], -1).astype(np.float32)


def dxt1(rgb):
    """Comprime una imagen RGB (alto, ancho, 3) uint8, lados múltiplos de 4, a DXT1."""
    h, w, _ = rgb.shape
    bloques = rgb.reshape(h // 4, 4, w // 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 3)
    c0 = _a565(bloques.max(1))
    c1 = _a565(bloques.min(1))
    # Modo de 4 colores exige c0 > c1
    iguales = c0 == c1
    c0, c1 = np.maximum(c0, c1), np.minimum(c0, c1)
    p0, p1 = _de565(c0), _de565(c1)
    paleta = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1)  # (n, 4, 3)
    dist = ((bloques[:, :, None, :].astype(np.float32) - paleta[:, None, :, :]) ** 2).sum(-1)
    idx = dist.argmin(-1).astype(np.uint32)
    idx[iguales] = 0
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1, dtype=np.uint64).astype(np.uint32)
    salida = np.zeros(len(bloques), dtype=[("c0", "<u2"), ("c1", "<u2"), ("i", "<u4")])
    salida["c0"], salida["c1"], salida["i"] = c0, c1, bits
    return salida.tobytes()


# ---------------------------------------------------------------- TXD

def _chunk(tipo, datos):
    return struct.pack("<III", tipo, len(datos), RW_VERSION) + datos


def _textura_nativa(nombre, img, mipmaps=True):
    img = img.convert("RGB")
    ancho, alto = img.size
    niveles = []
    while True:
        niveles.append(dxt1(np.asarray(img, dtype=np.uint8)))
        if not mipmaps or min(img.size) <= 4:
            break
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
    cabecera = struct.pack(
        "<IBBH32s32sIIHHBBBB",
        9,                           # plataforma D3D9
        0x06 if mipmaps else 0x01, 0x11, 0,  # filtro trilineal (o lineal sin mipmaps), repetir en U y V
        nombre.encode("ascii"), b"",
        0x0200 | (0x8000 if mipmaps else 0),  # formato 565 (+ mipmaps)
        0x31545844,                  # 'DXT1'
        ancho, alto, 16, len(niveles),
        4,                           # raster de textura
        0x08,                        # comprimida
    )
    cuerpo = cabecera + b"".join(struct.pack("<I", len(n)) + n for n in niveles)
    return _chunk(0x15, _chunk(0x01, cuerpo) + _chunk(0x03, b""))


def escribir_txd(ruta, texturas, mipmaps=True):
    """texturas: lista de (nombre, PIL.Image). Lados potencia de 2 y >= 4."""
    nativas = b""
    for nombre, img in texturas:
        if len(nombre) > 31:
            raise ValueError(f"Nombre de textura demasiado largo: {nombre}")
        nativas += _textura_nativa(nombre, img, mipmaps)
    datos = _chunk(0x01, struct.pack("<HH", len(texturas), 2)) + nativas + _chunk(0x03, b"")
    with open(ruta, "wb") as fh:
        fh.write(_chunk(0x16, datos))


# ---------------------------------------------------------------- IMG v2

def escribir_img(ruta, archivos):
    """archivos: lista de rutas (Path). Los nombres dentro del .img son el nombre de cada archivo."""
    entradas = []
    cabecera = 8 + 32 * len(archivos)
    sector = (cabecera + SECTOR - 1) // SECTOR
    for a in archivos:
        nombre = a.name.lower()
        if len(nombre) > 23:
            raise ValueError(f"Nombre demasiado largo para el .img: {nombre}")
        tam = (a.stat().st_size + SECTOR - 1) // SECTOR
        entradas.append((a, nombre, sector, tam))
        sector += tam
    with open(ruta, "wb") as fh:
        fh.write(b"VER2" + struct.pack("<I", len(archivos)))
        for _, nombre, inicio, tam in entradas:
            fh.write(struct.pack("<IHH24s", inicio, tam, 0, nombre.encode("ascii")))
        for a, _, inicio, tam in entradas:
            fh.seek(inicio * SECTOR)
            datos = a.read_bytes()
            fh.write(datos + b"\0" * (tam * SECTOR - len(datos)))
