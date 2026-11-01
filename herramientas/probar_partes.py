"""Instala solo algunas partes del mod para encontrar cuál cuelga el juego.

Uso: python herramientas/probar_partes.py gta_dat ipl_binarios ide guion agua
(las partes no nombradas se dejan como en el juego original)
"""
import shutil
import sys

import instalar_en_juego as inst

PARTES = {
    "gta_dat": inst.gta_dat,
    "agua": inst.water_dat,
    "ipl_binarios": inst.ocultar_ipl_binarios,
    "ide": inst.copiar_mapa,
    "guion": lambda: [shutil.copy2(inst.MOD / r, inst.JUEGO / r) for r in inst.GUION],
}


def main():
    inst.quitar()
    inst.copia_seguridad()
    shutil.copy2(inst.MOD / "models" / "badalona.img", inst.JUEGO / "models" / "badalona.img")
    for nombre in sys.argv[1:]:
        PARTES[nombre]()
        print("parte instalada:", nombre)


if __name__ == "__main__":
    main()
