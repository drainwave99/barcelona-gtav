"""Prepara el guion del juego (main.scm) para pasear por Badalona.

El main.scm original espera el mapa de Los Santos y la carga se queda colgada. Se usa el main.scm
"stripped" de Sanny Builder (sin misiones: crea a CJ y deja pasear) y se cambian sus coordenadas
de Grove Street por puntos de Badalona.

Entrada: descargas/sannybuilder/extraido/data/sa_sbl/stripped scm/{main.scm,script.img}
Salida:  mod/data/script/{main.scm,script.img}
"""
import shutil
import struct

import config

ORIGEN = config.RAIZ / "descargas" / "sannybuilder" / "extraido" / "data" / "sa_sbl" / "stripped scm"
SALIDA = config.RAIZ / "mod" / "data" / "script"

# Coordenada del main.scm original -> coordenada en Badalona (calculadas con punto_salida.py)
CAMBIOS = {
    # Salida de CJ: Grove Street -> Plaça de Trafalgar (Llefià, la zona con más detalle)
    2488.56: -2549.34, -1666.84: -938.35, 13.38: 25.6,
    # Hospital (reaparecer al morir): -> Carretera de Canyet, subiendo a Can Ruti
    2027.77: 862.77, -1420.52: 760.50, 15.99: 117.92,
    # Comisaría (al ser arrestado): -> Plaça de Trafalgar
    1550.68: -2545.0, -1675.49: -935.0, 14.51: 25.6,
}


def main():
    datos = bytearray((ORIGEN / "main.scm").read_bytes())
    for viejo, nuevo in CAMBIOS.items():
        patron = b"\x06" + struct.pack("<f", viejo)  # 0x06 = parámetro float en el formato SCM
        veces = datos.count(patron)
        if veces == 0:
            raise SystemExit(f"No encuentro {viejo} en main.scm")
        datos = datos.replace(patron, b"\x06" + struct.pack("<f", nuevo))
        print(f"{viejo} -> {nuevo} ({veces} veces)")
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "main.scm").write_bytes(datos)
    shutil.copy2(ORIGEN / "script.img", SALIDA / "script.img")
    print(f"Guardado en {SALIDA}")


if __name__ == "__main__":
    main()
