"""Versiones de los paquetes instalados en el juego (los dlc.rpf pesan GB: van aparte de git, en mod_v/versiones).

Cada versión es una carpeta mod_v/versiones/<fecha>_<commit>[_nota]/<pack>/dlc.rpf con los paquetes que había
instalados en ese momento. empaquetar_v guarda la versión instalada antes de sustituirla.

python versiones_v.py                 lista las versiones
python versiones_v.py guardar [nota]  guarda lo instalado ahora
python versiones_v.py volver <carpeta>  vuelve a instalar esa versión (con el juego cerrado)
"""
import shutil
import subprocess
import sys
import time

import config_v

GTA = config_v.Path(r"C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V")
DLCPACKS = GTA / "mods" / "update" / "x64" / "dlcpacks"
VERSIONES = config_v.MOD / "versiones"
GUARDAR = 4  # las más viejas se borran (cada una pesa lo que todos los paquetes juntos)


def _commit():
    r = subprocess.run(["git", "-C", str(config_v.RAIZ), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "sin-git"


def instalados():
    return sorted(p.parent.name for p in DLCPACKS.glob("bcn*/dlc.rpf"))


def guardar(nota=""):
    paquetes = instalados()
    if not paquetes:
        return None
    nombre = time.strftime("%Y%m%d-%H%M") + "_" + _commit() + (f"_{nota}" if nota else "")
    destino = VERSIONES / nombre
    for p in paquetes:
        (destino / p).mkdir(parents=True, exist_ok=True)
        shutil.copy2(DLCPACKS / p / "dlc.rpf", destino / p / "dlc.rpf")
    for vieja in sorted(VERSIONES.iterdir())[:-GUARDAR]:
        shutil.rmtree(vieja, ignore_errors=True)
    print("Versión guardada:", nombre, "(" + ", ".join(paquetes) + ")")
    return destino


def volver(nombre):
    origen = VERSIONES / nombre
    for p in sorted(d.name for d in origen.iterdir() if (d / "dlc.rpf").exists()):
        (DLCPACKS / p).mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen / p / "dlc.rpf", DLCPACKS / p / "dlc.rpf")
        print("Instalado", p, "de", nombre)
    for p in instalados():  # paquetes que esa versión no tenía: se apagan (sin borrarlos)
        if not (origen / p / "dlc.rpf").exists():
            (DLCPACKS / p / "dlc.rpf").rename(DLCPACKS / p / "dlc.rpf.off")
            print("Desactivado", p)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "guardar":
        guardar(sys.argv[2] if len(sys.argv) > 2 else "")
    elif len(sys.argv) > 2 and sys.argv[1] == "volver":
        volver(sys.argv[2])
    else:
        for v in sorted(VERSIONES.glob("*")) if VERSIONES.exists() else []:
            print(v.name, " ".join(d.name for d in v.iterdir()))
