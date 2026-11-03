"""Comprueba el mapa generado y los datos de partida, para que cualquiera pueda ver si su mapa sale bien.

Revisa, hoja por hoja (rápido, solo mira archivos):
  - que la generación acabó sin errores (datos_v/gen_<hoja>.log);
  - que cada casilla de 250 m tiene terreno con su colisión (un modelo sin colisión = te caes al vacío);
  - que cada modelo de edificios, puentes y pasos tiene su colisión;
  - que el LiDAR de la hoja no tiene huecos ni alturas imposibles;
  - que está en un paquete y el paquete instalado es más nuevo que lo generado (si no, falta empaquetar);
  - huecos en el mapa: un km² sin hoja rodeado de hojas (y que no se quitó a propósito).
Con --a-fondo, además, edificios que empiezan muy por encima del suelo (flotando), recalculando sus volúmenes.

Y los datos (VERSIONES_DATOS.json, en la raíz del repositorio):
  --huella     apunta la versión de los datos y programas de este ordenador (lo hace quien genera la versión buena)
  (siempre)    compara este ordenador con ese archivo y avisa si algo es distinto: con otros datos el mapa
               puede salir distinto.

Uso: python comprobar_v.py [hojas...] [--a-fondo] [--huella]
Sale con código 1 si encuentra fallos (avisos no cuentan).
"""
import hashlib
import json
import re
import sys
from importlib import metadata
from pathlib import Path

import numpy as np

import config_v

PROTO = config_v.MOD / "prototipo"
HUELLA = config_v.RAIZ / "VERSIONES_DATOS.json"
PAQUETES = ["numpy", "scipy", "shapely", "pillow", "pyproj", "osmium", "laspy", "lazrs"]
CASILLAS = 16  # 4 x 4 de 250 m por hoja

fallos, avisos = [], []


def fallo(hoja, texto):
    fallos.append(f"{hoja}: {texto}")


def aviso(hoja, texto):
    avisos.append(f"{hoja}: {texto}")


# ---- hojas ----
def comprobar_log(hoja):
    log = config_v.DATOS / f"gen_{hoja}.log"
    if not log.exists():
        aviso(hoja, "sin registro de generación (gen_<hoja>.log); no se puede saber si acabó bien")
        return
    texto = log.read_text(encoding="utf-8", errors="replace")
    if "Traceback" in texto:
        fallo(hoja, "la generación falló (Traceback en el registro)")
    elif "Alturas:" not in texto[-2000:]:
        fallo(hoja, "la generación no llegó al final (falta la línea 'Alturas:' del registro)")


def comprobar_archivos(hoja):
    xml = PROTO / hoja / "xml"
    if not xml.is_dir():
        fallo(hoja, "no está generada (falta mod_v/prototipo/<hoja>/xml)")
        return
    nombres = {p.name for p in xml.iterdir()}
    vacios = [n for n in nombres if (xml / n).is_file() and (xml / n).stat().st_size == 0]
    if vacios:
        fallo(hoja, f"{len(vacios)} archivos vacíos, p. ej. {vacios[0]}")
    # las texturas van en carpetas <nombre>.ytd/ con sus .dds: una carpeta sin imágenes es un modelo sin textura
    sin_tex = [n for n in nombres if (xml / n).is_dir() and not any((xml / n).glob("*.dds"))]
    if sin_tex:
        fallo(hoja, f"{len(sin_tex)} diccionarios de texturas sin imágenes, p. ej. {sin_tex[0]}")
    modelos = {re.sub(r"\.ydr\.xml$", "", n) for n in nombres if n.endswith(".ydr.xml")}
    colisiones = {re.sub(r"\.ybn\.xml$", "", n) for n in nombres if n.endswith(".ybn.xml")}
    terreno = sorted(m for m in modelos if m.startswith("bcn_t_"))
    if len(terreno) < CASILLAS:
        aviso(hoja, f"solo {len(terreno)} de {CASILLAS} casillas con terreno (normal si el resto es mar)")
    # terreno (t), edificios (e), puentes (p), pasos (u), andenes (a): el modelo sin su colisión no se pisa
    for m in sorted(modelos):
        tipo = m.split("_")[1]
        if tipo in "tepuam" and len(tipo) == 1 and m not in colisiones:
            fallo(hoja, f"{m} no tiene colisión: ahí se cae al vacío")
    for c in sorted(colisiones - modelos):
        aviso(hoja, f"colisión {c} sin modelo (pared invisible)")


def comprobar_lidar(hoja):
    f = config_v.DATOS / "lidar" / "hojas" / f"{hoja}.npz"
    if not f.exists():
        fallo(hoja, "falta su LiDAR (datos_v/lidar/hojas/<hoja>.npz): python lidar.py " + hoja)
        return
    suelo = np.load(f)["suelo"]
    nan = float(np.isnan(suelo).mean())
    if nan > 0.001:
        fallo(hoja, f"el suelo del LiDAR tiene huecos ({nan:.1%} sin dato)")
    v = suelo[~np.isnan(suelo)]
    if len(v) and (v.min() < -20 or v.max() > 700):
        fallo(hoja, f"alturas del suelo imposibles ({v.min():.0f} .. {v.max():.0f} m)")


def comprobar_paquetes(hojas):
    import empaquetar_v
    if not empaquetar_v.REPARTO.exists():
        aviso("paquetes", "no hay mod_v/paquetes.json: todavía no se ha empaquetado nada")
        return
    rep = json.loads(empaquetar_v.REPARTO.read_text(encoding="utf-8"))
    de = {h: p for p, hs in rep.items() for h in hs}
    for hoja in hojas:
        p = de.get(hoja)
        if p is None:
            fallo(hoja, "no está en ningún paquete: python empaquetar_v.py --cambiadas")
            continue
        rpf = config_v.GTA / "mods" / "update" / "x64" / "dlcpacks" / p / "dlc.rpf"
        xml = PROTO / hoja / "xml"
        if not rpf.exists():
            fallo(hoja, f"su paquete {p} no está instalado en el juego")
        elif xml.is_dir():
            nuevo = max((x.stat().st_mtime for x in xml.iterdir()), default=0)
            if nuevo > rpf.stat().st_mtime:
                aviso(hoja, f"generada después de instalar {p}: en el juego se ve la versión vieja (empaqueta)")


def comprobar_huecos(hojas):
    hechas = set(hojas) | config_v.HOJAS_FUERA
    vistos = set()
    for h in hojas:
        e, n = int(h[:3]), int(h[3:])
        for de, dn in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            k = f"{e + de}{n + dn}"
            if k in hechas or k in vistos:
                continue
            ke, kn = e + de, n + dn
            lados = sum(f"{ke + a}{kn + b}" in hechas for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if lados >= 3:
                vistos.add(k)
                aviso(k, f"hueco en el mapa: no hay hoja y tiene hojas en {lados} lados (¿mar, o falta generarla?)")


def comprobar_flotantes(hoja, partes):
    """Volúmenes con la base más de 3 m por encima del terreno (sin contar los que van sobre un pasaje)."""
    import pickle
    import calles_v
    import edificios_v
    import prototipo
    capas, e0, n1 = prototipo.cargar_hoja(hoja)
    caja = (e0, n1 - 1000, e0 + 1000, n1)
    dentro = [p for p in partes if caja[0] <= p["anillos"][0][:, 0].mean() < caja[2]
              and caja[1] <= p["anillos"][0][:, 1].mean() < caja[3]]
    osm = pickle.load(open(config_v.DATOS / "osm.pkl", "rb"))
    pasos = prototipo.pasajes(calles_v.recortar(osm, (e0 - 300, n1 - 1300, e0 + 1300, n1 + 300)))
    vols = edificios_v.pasajes(edificios_v.volumenes(dentro, capas, e0, n1), pasos, capas, e0, n1)
    malos = 0
    for v in vols:
        if v.get("sobre_paso"):
            continue
        c = np.asarray(v["poli"].representative_point().coords[0])
        g = float(edificios_v.muestrear(capas["suelo"], e0, n1, np.array([c[0]]), np.array([c[1]]))[0])
        if v["suelo"] - g > 3:
            malos += 1
            if malos <= 3:
                fallo(hoja, f"edificio {v['p'].get('ref')} flotando {v['suelo'] - g:.1f} m sobre el suelo en "
                            f"{c[0] - config_v.ORIGEN_E:.0f},{c[1] - config_v.ORIGEN_N:.0f} (coordenadas del juego)")
    if malos > 3:
        fallo(hoja, f"... y {malos - 3} edificios flotando más")


# ---- datos ----
def _sha(path, trozo=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(trozo):
            h.update(b)
    return h.hexdigest()[:16]


def huella_actual():
    d = {"paquetes_python": {}, "osm": None, "catastro": {}, "lidar_hojas": 0, "orto_teselas": 0}
    for p in PAQUETES:
        try:
            d["paquetes_python"][p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            d["paquetes_python"][p] = None
    import osm_v
    if osm_v.PBF.exists():
        import osmium
        r = osmium.io.Reader(str(osm_v.PBF), osmium.osm.osm_entity_bits.NOTHING)
        fecha = r.header().get("osmosis_replication_timestamp")
        r.close()
        d["osm"] = {"archivo": osm_v.PBF.name, "fecha": fecha, "sha256": _sha(osm_v.PBF)}
    for carpeta in sorted((config_v.DATOS / "catastro").glob("A.ES.SDGC.BU.*")):
        if not carpeta.is_dir():
            continue
        md = next(carpeta.glob("A.ES.SDGC.BU.MD.*.xml"), None)
        fecha = None
        if md:
            m = re.search(r"<gco:Date>([^<]+)</gco:Date>", md.read_text(encoding="utf-8", errors="replace"))
            fecha = m.group(1) if m else None
        gml = next(carpeta.glob("*.buildingpart.gml"), None)
        d["catastro"][carpeta.name.split(".")[-1]] = {"fecha": fecha, "sha256": _sha(gml) if gml else None}
    d["lidar_hojas"] = len(list((config_v.DATOS / "lidar" / "hojas").glob("[0-9]" * 6 + ".npz")))
    d["orto_teselas"] = len(list((config_v.DATOS / "orto").glob("*.jpg")))
    return d


def comparar_huella(actual):
    if not HUELLA.exists():
        aviso("datos", "no hay VERSIONES_DATOS.json: no se puede comparar con la versión buena")
        return
    buena = json.loads(HUELLA.read_text(encoding="utf-8"))
    for p, v in buena.get("paquetes_python", {}).items():
        if actual["paquetes_python"].get(p) != v:
            aviso("python", f"{p} {actual['paquetes_python'].get(p)} (la versión buena usa {v}): "
                            "pip install -r requirements.txt")
    o, ob = actual.get("osm"), buena.get("osm")
    if ob and (not o or o["sha256"] != ob["sha256"]):
        aviso("osm", f"OpenStreetMap distinto: aquí {o['fecha'] if o else 'no está'}, la versión buena es del "
                     f"{ob['fecha']}. Las calles cambiadas desde entonces pueden salir distintas.")
    for muni, v in buena.get("catastro", {}).items():
        a = actual["catastro"].get(muni)
        if not a:
            aviso("catastro", f"falta el municipio {muni}")
        elif a["sha256"] != v["sha256"]:
            aviso("catastro", f"{muni} distinto: aquí del {a['fecha']}, la versión buena del {v['fecha']}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    a_fondo = "--a-fondo" in sys.argv
    if "--huella" in sys.argv:
        d = huella_actual()
        HUELLA.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print("Escrito", HUELLA)
        return
    hojas = args or config_v.hojas()
    print(f"Comprobando {len(hojas)} hojas{' a fondo' if a_fondo else ''}...")
    partes = []
    if a_fondo:
        import pickle
        for muni in config_v.MUNICIPIOS:
            f = config_v.DATOS / "catastro" / f"{muni}.pkl"
            if f.exists():
                partes += pickle.load(open(f, "rb"))["partes"]
    for i, hoja in enumerate(hojas):
        comprobar_log(hoja)
        comprobar_archivos(hoja)
        comprobar_lidar(hoja)
        if a_fondo:
            comprobar_flotantes(hoja, partes)
            print(f"  {i + 1}/{len(hojas)} {hoja}", flush=True)
    comprobar_paquetes(hojas)
    if not args:
        comprobar_huecos(hojas)
    comparar_huella(huella_actual())
    for a in avisos:
        print("aviso:", a)
    for f in fallos:
        print("FALLO:", f)
    print(f"\n{len(fallos)} fallos, {len(avisos)} avisos en {len(hojas)} hojas")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
