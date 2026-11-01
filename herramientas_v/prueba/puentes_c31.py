"""Prueba: genera los puentes de la zona de Sant Roc (C-31) en un solo .ydr.xml para verlos en Blender.

Uso: python prueba/puentes_c31.py <carpeta_xml>
"""
import pickle
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config_v
import edificios_v
import puentes_v
import prototipo
import rage

CAJA = (434500, 4586000, 437000, 4589500)


def main():
    xml = Path(sys.argv[1])
    shutil.rmtree(xml, ignore_errors=True)
    xml.mkdir(parents=True)
    with open(config_v.DATOS / "osm.pkl", "rb") as fh:
        osm = pickle.load(fh)
    todas = puentes_v.vias_puente(osm)
    puentes_v.extremos_internos(todas)
    vias = [v for v in todas if CAJA[0] <= v["xy"].mean(0)[0] < CAJA[2] and CAJA[1] <= v["xy"].mean(0)[1] < CAJA[3]]
    calles = edificios_v.arbol_calles(osm)
    relieve = puentes_v.Relieve()
    centro = ((CAJA[0] + CAJA[2]) / 2, (CAJA[1] + CAJA[3]) / 2)
    arrays, colision, hechos = puentes_v.construir(vias, relieve, calles, centro)
    print(f"{hechos} de {len(vias)} vías de puente construidas; texturas {sorted(arrays)}")
    rage.escribir_ytd(xml / "bcn_obra.ytd.xml", puentes_v.texturas())
    geos = [dict(textura=t, recorte=t.endswith("_alfa"), **trozo) for t, g in arrays.items()
            for trozo in prototipo.partir(g)]
    rage.escribir_ydr(xml / "bcn_p_prueba.ydr.xml", "bcn_p_prueba", geos, 1500.0)
    print("triángulos", sum(len(g["i"]) for g in geos), "colisión", len(colision[1]))
    # Suelo de referencia para la vista: terreno del LiDAR a 4 m alrededor de los puentes
    e = np.arange(CAJA[0], CAJA[2], 4.0)
    n = np.arange(CAJA[1], CAJA[3], 4.0)
    ge, gn = np.meshgrid(e, n)
    z = relieve.valor("suelo", ge, gn)
    np.savez(xml / "suelo.npz", e=e - centro[0], n=n - centro[1], z=z)


if __name__ == "__main__":
    main()
