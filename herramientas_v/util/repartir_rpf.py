"""Reparte por peso (empaquetar_v.repartir) los modelos de un dlc.rpf ya sacado con 'cwtool abrir' en varios RPF
anidados, rehace content.xml, empaqueta y deja el resultado en <salida>.
Uso: repartir_rpf.py <carpeta_sacada> <pack> <salida.rpf>"""
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\danny\Desktop\GTA SAN ANDREAS MOD CON ISMA\herramientas_v")
import empaquetar_v as ev
import rage

raiz, pack, salida = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
niveles = raiz / "x64" / "levels" / "gta5"
mapa = niveles / f"{pack}.rpf"
for otro in sorted(niveles.glob(f"{pack}_[0-9]*.rpf")):  # todo de vuelta al primero
    for f in otro.iterdir():
        f.rename(mapa / f.name)
    otro.rmdir()
hojas = sorted({m.group(1) for f in (niveles / f"{pack}_metadata.rpf").glob("*.ymap")
                if (m := re.match(rf"{pack}_(\d{{6}})", f.name))})
grupos = ev.repartir(mapa, hojas)
nombres_rpf = [pack] + [f"{pack}_{k + 1}" for k in range(1, max(grupos.values(), default=0) + 1)]
for k in range(1, len(nombres_rpf)):
    carpeta = niveles / f"{nombres_rpf[k]}.rpf"
    carpeta.mkdir()
    for f in list(mapa.iterdir()):
        if f.is_file() and grupos.get(ev._hoja(f.name), 0) == k:
            f.rename(carpeta / f.name)
for r in nombres_rpf:
    mb = sum(f.stat().st_size for f in (niveles / f"{r}.rpf").iterdir()) / 2**20
    print(r, round(mb), "MB")
(raiz / "content.xml").write_text(ev.CONTENT.format(
    p=pack, P=pack.upper(), rpfs="\n".join(ev.RPF_ITEM.format(p=pack, r=r) for r in nombres_rpf),
    activar="\n".join(f"        <Item>dlc_{pack}:/%PLATFORM%/levels/gta5/{r}.rpf</Item>" for r in nombres_rpf)),
    encoding="utf-8")
rage.empaquetar_rpf(raiz, salida)
