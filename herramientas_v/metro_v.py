"""Metro: estaciones, bocas y líneas de OSM para el plugin bcn_metro.asi (andén genérico: entras por una boca, eliges
destino, fundido a negro y sales por la boca de la otra estación).

Del PBF local: relaciones route=subway (TMB L1-L11 y las de FGC que lo son) con sus paradas en orden; nodos
railway=subway_entrance (las bocas); las bocas van con la estación más cercana de su nombre (o la más cercana a
menos de 250 m). Solo lo que cae en las hojas del mapa.

-> bcn_metro.txt (carpeta del juego):
   S <id> <x> <y> <nombre>                 estación (coordenadas del juego)
   B <id_estación> <x> <y> <z> <rumbo>      boca (z del suelo LiDAR; rumbo hacia fuera de la estación)
   L <ref> <r> <g> <b> <id> <id> ...        línea con sus estaciones en orden
Uso: python metro_v.py [--sin-instalar]
"""
import math
import re
import sys
import unicodedata

import numpy as np
import osmium
from pyproj import Transformer

import config_v
import empaquetar_v
from osm_v import PBF
from trafico_v import Alturas

CAJA = (2.05, 41.30, 2.32, 41.52)
COLORES = {"L1": "#E2001A", "L2": "#9B2C98", "L3": "#00A03C", "L4": "#FFC20E", "L5": "#0072BC",
           "L9N": "#F38B00", "L9S": "#F38B00", "L10N": "#00A6D6", "L10S": "#00A6D6", "L11": "#89B94C"}


class Metro(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.rutas, self.nodos, self.bocas = [], {}, []

    def node(self, n):
        t = n.tags
        if not (CAJA[0] < n.location.lon < CAJA[2] and CAJA[1] < n.location.lat < CAJA[3]):
            return
        if t.get("railway") == "subway_entrance":
            self.bocas.append((n.location.lon, n.location.lat, t.get("name", "")))
        if t.get("public_transport") in ("stop_position", "station", "platform") or t.get("railway") in (
                "stop", "station", "halt") or t.get("station") == "subway":
            self.nodos[n.id] = (n.location.lon, n.location.lat, t.get("name", ""))

    def relation(self, r):
        t = r.tags
        if t.get("route") != "subway" or not t.get("ref"):
            return
        paradas = [m.ref for m in r.members if m.type == "n" and m.role.startswith("stop")]
        self.rutas.append((t.get("ref"), t.get("colour", ""), paradas))


def _clave(nombre):
    s = unicodedata.normalize("NFD", nombre.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s)


def main():
    m = Metro()
    m.apply_file(str(PBF), locations=True, idx="flex_mem")
    a_utm = Transformer.from_crs(4326, 25831, always_xy=True)
    hojas = set(config_v.hojas())

    def juego(lon, lat):
        e, n = a_utm.transform(lon, lat)
        dentro = f"{int(e // 1000)}{int(n // 1000) - 4000}" in hojas
        return (e, n, *config_v.utm_a_juego(e, n)) if dentro else None

    # estaciones: por nombre; cada línea con su recorrido más largo (las dos direcciones son la misma lista)
    estaciones, por_clave, lineas = [], {}, {}
    for ref, colour, paradas in sorted(m.rutas, key=lambda r: -len(r[2])):
        if ref in lineas:
            continue
        ids = []
        for nid in paradas:
            if nid not in m.nodos:
                continue
            lon, lat, nombre = m.nodos[nid]
            p = juego(lon, lat)
            if p is None or not nombre:
                continue
            k = _clave(nombre)
            if k not in por_clave:
                por_clave[k] = len(estaciones)
                estaciones.append(dict(nombre=nombre, e=p[0], n=p[1], x=p[2], y=p[3], lineas=[]))
            i = por_clave[k]
            if not ids or ids[-1] != i:
                ids.append(i)
                estaciones[i]["lineas"].append(ref)
        if len(ids) >= 2:
            lineas[ref] = (colour or COLORES.get(ref, "#888888"), ids)
    if not estaciones:
        sys.exit("sin estaciones de metro en el PBF")
    # bocas: a la estación de su nombre, o a la más cercana a menos de 250 m
    alt = Alturas(hojas)
    pos = np.array([(s["e"], s["n"]) for s in estaciones])
    bocas = []
    for lon, lat, nombre in m.bocas:
        p = juego(lon, lat)
        if p is None:
            continue
        d = np.hypot(pos[:, 0] - p[0], pos[:, 1] - p[1])
        i = por_clave.get(_clave(nombre)) if nombre else None
        if i is None or d[i] > 600:
            i = int(np.argmin(d))
            if d[i] > 250:
                continue
        z = alt.z(p[0], p[1], False)
        if z is None:
            continue
        rumbo = math.degrees(math.atan2(-(p[0] - estaciones[i]["e"]), p[1] - estaciones[i]["n"]))  # GTA: 0 = norte
        bocas.append((i, p[2], p[3], float(z), rumbo))
    con_boca = {b[0] for b in bocas}
    # estaciones sin boca en OSM: una en el punto de la estación
    for i, s in enumerate(estaciones):
        if i not in con_boca:
            z = alt.z(s["e"], s["n"], False)
            if z is not None:
                bocas.append((i, s["x"], s["y"], float(z), 0.0))
    lineas = {ref: (c, [i for i in ids if any(b[0] == i for b in bocas)]) for ref, (c, ids) in lineas.items()}
    lineas = {ref: v for ref, v in lineas.items() if len(v[1]) >= 2}
    usadas = {i for _, ids in lineas.values() for i in ids}
    out = []
    for i, s in enumerate(estaciones):
        if i in usadas:
            out.append(f"S {i} {s['x']:.1f} {s['y']:.1f} {s['nombre']}")
    for i, x, y, z, r in bocas:
        if i in usadas:
            out.append(f"B {i} {x:.1f} {y:.1f} {z:.2f} {r:.0f}")
    for ref in sorted(lineas, key=lambda r: (len(r), r)):
        c, ids = lineas[ref]
        rgb = tuple(int(c.lstrip("#")[k:k + 2], 16) for k in (0, 2, 4)) if re.fullmatch(r"#?[0-9A-Fa-f]{6}", c) else (136, 136, 136)
        out.append(f"L {ref} {rgb[0]} {rgb[1]} {rgb[2]} " + " ".join(map(str, ids)))
        print(f"{ref}: {len(ids)} estaciones ({estaciones[ids[0]]['nombre']} - {estaciones[ids[-1]]['nombre']})")
    print(f"{len(usadas)} estaciones, {sum(1 for b in bocas if b[0] in usadas)} bocas")
    destino = config_v.MOD / "metro" / "bcn_metro.txt"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(out) + "\n", encoding="utf-8")
    if "--sin-instalar" not in sys.argv:
        (empaquetar_v.GTA / "bcn_metro.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
        print("Instalado", empaquetar_v.GTA / "bcn_metro.txt")


if __name__ == "__main__":
    main()
