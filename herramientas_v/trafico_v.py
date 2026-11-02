"""Caminos de coches (nodes<N>.ynd) desde las calles de OSM, para que haya tráfico en Barcelona.

Sin los paths.rpf de Los Santos (quitar_ls) el juego no tiene por dónde llevar coches. Aquí:
  - calles por las que se circula (OSM highway, sin aparcamientos, accesos privados ni túneles largos);
  - los cruces son los nodos que comparten las vías de OSM; un nodo cada 15 m como mucho;
  - altura del LiDAR (suelo, o el tablero en los puentes), carriles y sentido de OSM (lanes, oneway);
  - repartidos en las áreas de 512 m del juego (32 x 32 sobre -8192..8192): nodes<y * 32 + x>.ynd.
Los .ynd van en el DLC bcnradar (radar_v.py los escribe con el radar); el juego los carga por nombre.
Uso suelto (para ver números): python trafico_v.py
"""
import math
import pickle
from collections import defaultdict

import numpy as np

import config_v

PASO = 15.0
CLASES = {  # densidad (0-15), velocidad (0 lenta - 3 muy rápida), carriles por sentido por defecto, autopista
    "motorway": (4, 3, 2, True), "motorway_link": (3, 2, 1, True), "trunk": (5, 2, 2, True),
    "trunk_link": (3, 1, 1, True), "primary": (6, 1, 2, False), "primary_link": (3, 1, 1, False),
    "secondary": (5, 1, 1, False), "secondary_link": (3, 1, 1, False), "tertiary": (4, 1, 1, False),
    "tertiary_link": (2, 1, 1, False), "residential": (3, 1, 1, False), "unclassified": (2, 1, 1, False),
    "living_street": (1, 0, 1, False), "service": (1, 0, 1, False),
}
SERVICIO_FUERA = {"parking_aisle", "driveway", "drive-through", "emergency_access"}


def _entero(v, defecto):
    try:
        return max(0, int(float(str(v).split(";")[0])))
    except (TypeError, ValueError):
        return defecto


class Alturas:
    """Suelo y tableros de puente del LiDAR de las hojas (rejillas de 0,5 m), cargadas según hagan falta."""
    def __init__(self, hojas):
        self.hojas, self.cache = set(hojas), {}

    def _hoja(self, e, n):
        h = f"{int(e // 1000)}{int(n // 1000) - 4000}"
        if h not in self.hojas:
            return None, None
        if h not in self.cache:
            base = config_v.DATOS / "lidar" / "hojas"
            f = base / f"{h}_c.npz" if (base / f"{h}_c.npz").exists() else base / f"{h}.npz"
            if not f.exists():
                self.cache[h] = None
            else:
                d = np.load(f)
                self.cache[h] = (d["suelo"], d["puente"])
            if len(self.cache) > 12:  # memoria: las más viejas fuera
                self.cache.pop(next(iter(self.cache)))
        return h, self.cache.get(h)

    def z(self, e, n, puente):
        h, capas = self._hoja(e, n)
        if capas is None:
            return None
        suelo, tablero = capas
        e0, n1 = int(h[:3]) * 1000, (4000 + int(h[3:]) + 1) * 1000
        c, f = int((e - e0) / 0.5), int((n1 - n) / 0.5)
        c, f = min(max(c, 0), 1999), min(max(f, 0), 1999)
        if puente:
            v = tablero[max(f - 3, 0):f + 4, max(c - 3, 0):c + 4]
            if np.isfinite(v).any():
                return float(np.nanmax(v))
        s = suelo[max(f - 1, 0):f + 2, max(c - 1, 0):c + 2]
        return float(np.nanmedian(s)) if np.isfinite(s).any() else None


def grafo(osm, hojas):
    """(posiciones juego (n, 3), {(a, b): atributos}, clase de cada nodo)."""
    alt = Alturas(hojas)
    clave_id, pos, clase_de = {}, [], []
    aristas = {}

    def vertice(e, n, puente, cl):
        k = (round(e, 2), round(n, 2), puente)
        if k not in clave_id:
            z = alt.z(e, n, puente)
            if z is None:
                return None
            x, y = config_v.utm_a_juego(e, n)
            if not (-8190 < x < 8190 and -8190 < y < 8190):
                return None
            clave_id[k] = len(pos)
            pos.append((x, y, z))
            clase_de.append(cl)
        return clave_id[k]

    for v in osm["vias"]:
        t = v["tags"]
        cl = t.get("highway")
        if cl not in CLASES or t.get("area") == "yes" or len(v["xy"]) < 2:
            continue
        if t.get("access") in ("no", "private") or t.get("motor_vehicle") in ("no", "private"):
            continue
        if cl == "service" and t.get("service") in SERVICIO_FUERA:
            continue
        tunel = t.get("tunnel") not in (None, "no")
        xy = np.asarray(v["xy"], np.float64)
        largo = float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum())
        if tunel and largo >= 120:  # los túneles largos van en tubo bajo tierra: sin coches de momento
            continue
        puente = t.get("bridge") not in (None, "no")
        sentido = t.get("oneway", "")
        unico = sentido in ("yes", "true", "1", "-1") or t.get("junction") in ("roundabout", "circular") or \
            (cl in ("motorway", "motorway_link") and sentido != "no")
        if sentido == "-1":
            xy = xy[::-1]
        dens, vel, por_sentido, _ = CLASES[cl]
        total = _entero(t.get("lanes"), 0)
        if unico:
            ida, vuelta = (_entero(t.get("lanes:forward"), total) or (total or por_sentido)), 0
        else:
            ida = _entero(t.get("lanes:forward"), 0) or (max(1, total // 2) if total else por_sentido)
            vuelta = _entero(t.get("lanes:backward"), 0) or (max(1, total - total // 2) if total else por_sentido)
        ida, vuelta = min(ida, 7), min(vuelta, 7)
        ids = []
        for (e0, n0), (e1, n1) in zip(xy[:-1], xy[1:]):
            d = math.hypot(e1 - e0, n1 - n0)
            m = max(1, int(math.ceil(d / PASO)))
            for k in range(m):
                f = k / m
                ids.append(vertice(e0 + (e1 - e0) * f, n0 + (n1 - n0) * f, puente, cl))
        ids.append(vertice(*xy[-1], puente, cl))
        for a, b in zip(ids[:-1], ids[1:]):
            if a is None or b is None or a == b or (a, b) in aristas or (b, a) in aristas:
                continue
            aristas[(a, b)] = dict(ida=ida, vuelta=vuelta, clase=cl, tunel=tunel)
    return np.array(pos), aristas, clase_de


def area(x, y):
    return int((y + 8192) // 512) * 32 + int((x + 8192) // 512)


def escribir(carpeta, osm=None, hojas=None):
    """nodes<N>.ynd.xml en 'carpeta'. Devuelve el número de nodos."""
    if osm is None:
        with open(config_v.DATOS / "osm.pkl", "rb") as fh:
            osm = pickle.load(fh)
    if hojas is None:
        hojas = [h.name for h in (config_v.MOD / "prototipo").iterdir() if h.name.isdigit()]
    pos, aristas, clase_de = grafo(osm, hojas)
    vecinos = defaultdict(list)  # nodo -> [(otro, carriles hacia él, carriles desde él)]
    for (a, b), at in aristas.items():
        vecinos[a].append((b, at["ida"], at["vuelta"], at["tunel"]))
        vecinos[b].append((a, at["vuelta"], at["ida"], at["tunel"]))
    usados = [i for i in range(len(pos)) if vecinos[i]]
    por_area = defaultdict(list)
    for i in usados:
        por_area[area(pos[i][0], pos[i][1])].append(i)
    ident = {}
    for a, lista in por_area.items():
        for k, i in enumerate(lista):
            ident[i] = (a, k)
    carpeta.mkdir(parents=True, exist_ok=True)
    for a, lista in por_area.items():
        s = ['<?xml version="1.0" encoding="UTF-8"?>', "<NodeDictionary>",
             f' <VehicleNodeCount value="{len(lista)}" />', ' <PedNodeCount value="0" />', " <Nodes>"]
        for i in lista:
            x, y, z = pos[i]
            cl = clase_de[i]
            dens, vel, _, autopista = CLASES[cl]
            enl = vecinos[i][:31]
            tunel = any(v[3] for v in enl)
            f0 = 2 | (32 if cl in ("service", "living_street") else 0)
            s += ["  <Item>", f'   <AreaID value="{a}" />', f'   <NodeID value="{ident[i][1]}" />', "   <StreetName />",
                  f'   <Position x="{round(x * 4) / 4}" y="{round(y * 4) / 4}" z="{round(z * 32) / 32}" />',
                  f'   <Flags0 value="{f0}" />', '   <Flags1 value="0" />',
                  f'   <Flags2 value="{64 if autopista else 0}" />', f'   <Flags3 value="{1 if tunel else 0}" />',
                  f'   <Flags4 value="{dens}" />', f'   <Flags5 value="{vel << 1}" />', "   <Links>"]
            for otro, ida, vuelta, _ in enl:
                d = float(np.linalg.norm(pos[otro] - pos[i]))
                s += ["    <Item>", f'     <ToAreaID value="{ident[otro][0]}" />',
                      f'     <ToNodeID value="{ident[otro][1]}" />', '     <Flags0 value="0" />',
                      '     <Flags1 value="0" />', f'     <Flags2 value="{(ida << 5) | (vuelta << 2)}" />',
                      f'     <LinkLength value="{min(255, max(1, round(d)))}" />', "    </Item>"]
            s += ["   </Links>", "  </Item>"]
        s += [" </Nodes>", " <Junctions />", " <JunctionRefs />", "</NodeDictionary>"]
        (carpeta / f"nodes{a}.ynd.xml").write_text("\n".join(s) + "\n", encoding="utf-8")
    print(f"tráfico: {len(usados)} nodos, {len(aristas)} tramos, {len(por_area)} áreas", flush=True)
    return len(usados)


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    escribir(Path(tempfile.mkdtemp()))
