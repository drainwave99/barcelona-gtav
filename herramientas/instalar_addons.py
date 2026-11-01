"""Instala los addons de Blender del proyecto (DragonFF, BlenderGIS) en la carpeta de usuario de Blender.

Uso: python herramientas/instalar_addons.py <version_blender>   (p. ej. 5.2)
"""
import os
import shutil
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESCARGAS = RAIZ / "descargas" / "addons"

# zip descargado -> (carpeta dentro del zip, nombre de módulo final)
ADDONS = {
    "dragonff-master.zip": ("DragonFF-master", "DragonFF"),
    "blendergis-master.zip": ("BlenderGIS-master", "BlenderGIS"),
}


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "5.2"
    destino = Path(os.environ["APPDATA"]) / "Blender Foundation" / "Blender" / version / "scripts" / "addons"
    destino.mkdir(parents=True, exist_ok=True)

    for zip_nombre, (carpeta_zip, modulo) in ADDONS.items():
        final = destino / modulo
        if final.exists():
            shutil.rmtree(final)
        with zipfile.ZipFile(DESCARGAS / zip_nombre) as z:
            prefijo = carpeta_zip + "/"
            for item in z.infolist():
                if not item.filename.startswith(prefijo) or item.is_dir():
                    continue
                relativo = item.filename[len(prefijo):]
                ruta = final / relativo
                ruta.parent.mkdir(parents=True, exist_ok=True)
                with z.open(item) as src, open(ruta, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        print(f"Instalado {modulo} en {final}")


if __name__ == "__main__":
    main()
