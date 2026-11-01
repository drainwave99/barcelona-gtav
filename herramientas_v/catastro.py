"""Lee los GML INSPIRE del Catastro (edificios y partes de edificio) a un formato compacto.

Salida: datos_v/catastro/<muni>.pkl con
  edificios {referencia: dict(anyo, uso, viviendas, plantas, contorno)}
  partes    lista de dict(ref, plantas, bajo_rasante, anillos [exterior, huecos...])  coordenadas UTM
Uso: python catastro.py [08015 ...]  (sin argumentos: los cuatro municipios)
"""
import pickle
import re
import sys

import numpy as np

import config_v

RE_EDIFICIO = re.compile(r"<bu-ext2d:Building gml:id=\"ES\.SDGC\.BU\.([^\"]+)\">(.*?)</bu-ext2d:Building>", re.S)
RE_PARTE = re.compile(r"<bu-ext2d:BuildingPart gml:id=\"ES\.SDGC\.BU\.([^\"]+)\">(.*?)</bu-ext2d:BuildingPart>", re.S)
RE_EXTERIOR = re.compile(r"<gml:exterior>.*?<gml:posList[^>]*>([^<]+)</gml:posList>", re.S)
RE_INTERIOR = re.compile(r"<gml:interior>.*?<gml:posList[^>]*>([^<]+)</gml:posList>", re.S)


def campo(texto, etiqueta):
    m = re.search(rf"<{etiqueta}[^>]*>([^<]*)</", texto)
    return m.group(1).strip() if m else ""


def anillo(lista):
    return np.array(lista.split(), dtype=np.float64).reshape(-1, 2)


def leer(muni):
    carpeta = config_v.DATOS / "catastro" / f"A.ES.SDGC.BU.{muni}"
    edificios = {}
    texto = (carpeta / f"A.ES.SDGC.BU.{muni}.building.gml").read_text(encoding="utf-8")
    for ref, cuerpo in RE_EDIFICIO.findall(texto):
        anyo = campo(cuerpo, "bu-core2d:beginning")[:4]
        plantas = campo(cuerpo, "bu-ext2d:numberOfFloorsAboveGround")
        ext = RE_EXTERIOR.search(cuerpo)
        edificios[ref] = dict(
            anyo=int(anyo) if anyo.isdigit() else 0,
            uso=campo(cuerpo, "bu-ext2d:currentUse"),
            viviendas=int(campo(cuerpo, "bu-ext2d:numberOfDwellings") or 0),
            plantas=int(plantas) if plantas.isdigit() else 0,
            contorno=anillo(ext.group(1)) if ext else None)
    partes = []
    texto = (carpeta / f"A.ES.SDGC.BU.{muni}.buildingpart.gml").read_text(encoding="utf-8")
    for ident, cuerpo in RE_PARTE.findall(texto):
        ext = RE_EXTERIOR.search(cuerpo)
        if not ext:
            continue
        sobre = campo(cuerpo, "bu-ext2d:numberOfFloorsAboveGround")
        bajo = campo(cuerpo, "bu-ext2d:numberOfFloorsBelowGround")
        partes.append(dict(ref=ident.split("_")[0], plantas=int(sobre) if sobre.isdigit() else 0,
                           bajo_rasante=int(bajo) if bajo.isdigit() else 0,
                           anillos=[anillo(ext.group(1))] + [anillo(m) for m in RE_INTERIOR.findall(cuerpo)]))
    return edificios, partes


def main():
    for muni in sys.argv[1:] or list(config_v.MUNICIPIOS):
        edificios, partes = leer(muni)
        with open(config_v.DATOS / "catastro" / f"{muni}.pkl", "wb") as fh:
            pickle.dump(dict(edificios=edificios, partes=partes), fh)
        anyos = [e["anyo"] for e in edificios.values() if e["anyo"]]
        print(f"{config_v.MUNICIPIOS[muni]}: {len(edificios)} edificios, {len(partes)} partes, "
              f"años {min(anyos)}-{max(anyos)} (mediana {int(np.median(anyos))})")


if __name__ == "__main__":
    main()
