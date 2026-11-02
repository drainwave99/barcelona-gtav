"""Fondo: alrededor del mapa, el terreno lejano de las hojas que se quitaron (config_v.HOJAS_FUERA: Montcada, la
vertiente del Vallès de Collserola, Zona Franca, Montgat), para que el mapa no se corte de golpe en el mar.

De cada hoja solo van sus mallas de lejos (bcn_l_<casilla>, con su textura de ortofoto bcn_l_<casilla>.ytd), ya
hechas por prototipo.py: sin colisión, edificios, calles ni árboles. Se ven desde lejos como el resto del mapa
visto de lejos; no se puede ir (debajo sigue el agua de quitar_ls). Va en su propio DLC, 'bcnfondo'.

Uso: python fondo_v.py [--sin-instalar]   (con el juego cerrado para instalar)
"""
import pickle
import shutil
import sys

import config_v
import empaquetar_v
import rage

PACK = "bcnfondo"
OBRA = config_v.MOD / "fondo"
DISTANCIA = 8000.0


def main():
    shutil.rmtree(OBRA, ignore_errors=True)
    xml = OBRA / "xml"
    xml.mkdir(parents=True)
    nombres, n = [], 0
    for hoja in sorted(config_v.HOJAS_FUERA):
        base = config_v.MOD / "prototipo" / hoja
        if not (base / "colocacion.pkl").exists():
            print(hoja, "sin generar: fuera del fondo")
            continue
        with open(base / "colocacion.pkl", "rb") as fh:
            col = pickle.load(fh)
        lods = list(col.get("lods", ()))
        tipos = {m: (ytd, d) for m, ytd, d in col["arquetipos"]}
        arquetipos, entidades = [], []
        for modelo, pos, _dist, _hijos in lods:
            fuente = base / "xml" / f"{modelo}.ydr.xml"
            if not fuente.exists():
                continue
            ytd = tipos.get(modelo, (modelo, 0))[0]
            shutil.copy2(fuente, xml / fuente.name)
            for t in (base / "xml").glob(f"{ytd}.ytd*"):
                (shutil.copytree(t, xml / t.name, dirs_exist_ok=True) if t.is_dir() else shutil.copy2(t, xml / t.name))
            arquetipos.append((modelo, ytd, DISTANCIA, *rage.caja_ydr(fuente)))
            entidades.append((modelo, pos, DISTANCIA))
        if not entidades:
            continue
        nombre = f"{PACK}_{hoja}"
        rage.escribir_mapa(xml, nombre, arquetipos, entidades)
        nombres.append(nombre)
        n += len(entidades)
    print(f"fondo: {len(nombres)} hojas, {n} mallas")
    (xml / "_manifest.ymf.pso.xml").write_text(empaquetar_v.MANIFIESTO.format(
        deps="\n".join(empaquetar_v.DEP.format(n=x, t=x) for x in nombres)), encoding="utf-8")
    niveles = OBRA / "dlc" / "x64" / "levels" / "gta5"
    mapa, meta = niveles / f"{PACK}.rpf", niveles / f"{PACK}_metadata.rpf"
    rage.a_binario(xml, mapa)
    meta.mkdir()
    for f in list(mapa.glob("*.ymap")) + list(mapa.glob("*.ytyp")) + list(mapa.glob("*.ymf")):
        f.rename(meta / f.name)
    dlc = OBRA / "dlc"
    (dlc / "content.xml").write_text(empaquetar_v.CONTENT.format(
        p=PACK, P=PACK.upper(), rpfs=empaquetar_v.RPF_ITEM.format(p=PACK, r=PACK),
        activar=f"        <Item>dlc_{PACK}:/%PLATFORM%/levels/gta5/{PACK}.rpf</Item>"), encoding="utf-8")
    (dlc / "setup2.xml").write_text(empaquetar_v.SETUP.format(p=PACK, P=PACK.upper()), encoding="utf-8")
    archivo = OBRA / "dlc.rpf"
    rage.empaquetar_rpf(dlc, archivo)
    print(f"{archivo}: {archivo.stat().st_size / 1e6:.0f} MB")
    shutil.rmtree(xml, ignore_errors=True)
    if "--sin-instalar" in sys.argv:
        return
    if empaquetar_v._juego_abierto():
        sys.exit("Juego abierto: ciérralo para instalar")
    gta = empaquetar_v.GTA
    destino = gta / "mods" / "update" / "x64" / "dlcpacks" / PACK / "dlc.rpf"
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archivo, destino)
    r = rage.subprocess.run([str(rage.DOTNET), str(rage.CWTOOL), "dlclist", str(gta),
                             str(gta / "mods" / "update" / "update.rpf"), PACK], capture_output=True, text=True)
    print(r.stdout.strip(), r.stderr.strip())
    print("Instalado", destino)


if __name__ == "__main__":
    main()
