"""Barrios: el nombre de la zona que pone el juego (mapa del menú de pausa, GET_NAME_OF_ZONE) es el barrio real.

El juego saca el nombre de zona de popzone.ipl: rectángulos con una etiqueta de texto (GXT) cada uno. Sin zonas
pone "Océano Pacífico". Aquí:
  - de OpenStreetMap (ODbL), los límites administrativos: barrio (admin_level 10 y 11), si no el distrito con nombre
    propio (9, como los de Sant Adrià), si no el municipio (8); fuera de todos, el mar;
  - una rejilla de CELDA m sobre todo el mapa, y las celdas iguales se juntan en rectángulos (popzone solo acepta
    cajas). El juego trae unas 1300 zonas; no pasamos de MAX_CAJAS (si hace falta, la celda crece);
  - los nombres van como textos nuevos en global.gxt2 (español e inglés) de x64/patch/data/lang de update.rpf.
Las cajas se llaman Z_BCNxxxx: no tienen entrada en zonebind, igual que la zona única que había antes (Z_BCN), así
que la gente y el tráfico siguen como estaban.

-> mod_v/barrios/popzone.ipl y nombres.json. quitar_ls.py los mete en el juego (meter_en).
Uso: python barrios_v.py
"""
import json
import re
import struct
import sys

import numpy as np
import osmium
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon, MultiPolygon

import config_v
from osm_v import PBF

CAJA = (2.05, 41.30, 2.32, 41.52)
LADO = 8192.0          # el mapa: de -LADO a +LADO en X e Y (como la zona única de antes)
CELDA = 100.0
MAX_CAJAS = 1250
GRUESO = 8         # fuera de las hojas, bloques de GRUESO x CELDA
SALIDA = config_v.MOD / "barrios"
MAR = "Mar Mediterrani"
SIERRA = "Serra de Collserola"
IDIOMAS = ("spanish_rel", "american_rel")


class Limites(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.a_utm = Transformer.from_crs(4326, 25831, always_xy=True)
        self.areas = []  # (nivel, nombre, geometría UTM)

    def area(self, a):
        t = a.tags
        if t.get("boundary") != "administrative" or t.get("admin_level") not in ("8", "9", "10", "11"):
            return
        nombre = t.get("name")
        nivel = int(t.get("admin_level"))
        if not nombre or (nivel == 9 and re.match(r"Districte\b", nombre)):
            return
        polis = []
        try:
            for ext in a.outer_rings():
                pts = [(n.lon, n.lat) for n in ext]
                if len(pts) < 4:
                    continue
                huecos = [[(n.lon, n.lat) for n in h] for h in a.inner_rings(ext)]
                polis.append((pts, huecos))
        except osmium.InvalidLocationError:
            return
        if not polis or not any(CAJA[0] < x < CAJA[2] and CAJA[1] < y < CAJA[3] for p, _ in polis for x, y in p[:50]):
            return
        geo = []
        for pts, huecos in polis:
            e, n = self.a_utm.transform(*zip(*pts))
            hs = [list(zip(*self.a_utm.transform(*zip(*h)))) for h in huecos if len(h) >= 4]
            g = Polygon(list(zip(e, n)), hs).buffer(0)
            if not g.is_empty:
                geo.append(g)
        if geo:
            self.areas.append((nivel, nombre, shapely.union_all(geo)))


def nombre_juego(nombre):
    """El tipo de letra del juego no tiene el punto volado (l·l)."""
    return nombre.replace("·", ".").replace("’", "'")


def rejilla(areas, celda):
    """Matriz de índices de nombre por celda (fila 0 = sur) y la lista de nombres."""
    n = int(round(2 * LADO / celda))
    c = -LADO + (np.arange(n) + 0.5) * celda
    gx, gy = np.meshgrid(c + config_v.ORIGEN_E, c + config_v.ORIGEN_N)
    # sin límite administrativo: mar si cae en el mar de OSM (costa_v) o al este de la costa; si no, la sierra
    # (los municipios del otro lado de Collserola quedan fuera de CAJA)
    import costa_v
    nombres = [MAR, SIERRA]
    mar = shapely.contains_xy(costa_v.mar(), gx, gy)
    idx = np.where(mar | (gx - config_v.ORIGEN_E > 2000), 0, 1).astype(np.int16)
    nivel = np.zeros(gx.shape, np.int8)  # el más concreto gana: 11 > 10 > 9 > 8
    for niv, nombre, g in sorted(areas, key=lambda a: a[0]):
        dentro = shapely.contains_xy(g, gx, gy)
        dentro &= niv >= nivel
        if not dentro.any():
            continue
        if nombre not in nombres:
            nombres.append(nombre)
        idx[dentro] = nombres.index(nombre)
        nivel[dentro] = niv
    # fuera de las hojas del mapa sobra el detalle: ahí cada bloque de GRUESO celdas toma el valor de su centro
    # (los bordes en escalera entre barrios son los que gastan cajas)
    jugable = np.zeros(gx.shape, bool)
    for h in config_v.hojas():
        e0, n0 = int(h[:3]) * 1000 - 300, (4000 + int(h[3:])) * 1000 - 300
        jugable |= (gx >= e0) & (gx < e0 + 1600) & (gy >= n0) & (gy < n0 + 1600)
    g = GRUESO
    for f in range(0, n, g):
        for c in range(0, n, g):
            bloque = (slice(f, f + g), slice(c, c + g))
            if not jugable[bloque].any():
                idx[bloque] = idx[min(f + g // 2, n - 1), min(c + g // 2, n - 1)]
    return idx, nombres


def cajas(idx):
    """Rectángulos [(c0, f0, c1, f1, valor)] (celdas, fin exclusivo) que cubren la matriz sin solaparse. Desde cada
    celda libre se toma el rectángulo del mismo valor de más área (probando todas las alturas)."""
    nf, nc = idx.shape
    hecho = np.zeros(idx.shape, bool)
    out = []
    for f in range(nf):
        for c in range(nc):
            if hecho[f, c]:
                continue
            v = idx[f, c]
            mejor, ancho, ff = (1, c + 1, f + 1), nc, f
            while ff < nf and idx[ff, c] == v and not hecho[ff, c]:
                fila = (idx[ff, c:ancho] == v) & ~hecho[ff, c:ancho]
                w = int(np.argmin(fila)) if not fila.all() else len(fila)
                ancho = c + w
                area = (ancho - c) * (ff - f + 1)
                if area > mejor[0]:
                    mejor = (area, ancho, ff + 1)
                ff += 1
            _, c1, f1 = mejor
            hecho[f:f1, c:c1] = True
            out.append((c, f, c1, f1, int(v)))
    return out


def joaat(s):
    h = 0
    for ch in s.lower().encode("utf-8"):
        h = (h + ch) & 0xFFFFFFFF
        h = (h + (h << 10)) & 0xFFFFFFFF
        h ^= h >> 6
    h = (h + (h << 3)) & 0xFFFFFFFF
    h ^= h >> 11
    return (h + (h << 15)) & 0xFFFFFFFF


def leer_gxt2(datos):
    if datos[:4] != b"2TXG":
        raise ValueError("no es un gxt2")
    n = struct.unpack_from("<I", datos, 4)[0]
    out = {}
    for i in range(n):
        h, o = struct.unpack_from("<II", datos, 8 + 8 * i)
        out[h] = datos[o:datos.index(b"\0", o)].decode("utf-8")
    return out


def escribir_gxt2(textos):
    claves = sorted(textos)
    cuerpo = b""
    tabla = []
    base = 8 + 8 * len(claves) + 8
    for h in claves:
        tabla.append((h, base + len(cuerpo)))
        cuerpo += textos[h].encode("utf-8") + b"\0"
    cab = b"2TXG" + struct.pack("<I", len(claves)) + b"".join(struct.pack("<II", h, o) for h, o in tabla)
    total = len(cab) + 8 + len(cuerpo)
    return cab + b"2TXG" + struct.pack("<I", total) + cuerpo


def main():
    lim = Limites()
    lim.apply_file(str(PBF), locations=True, idx="flex_mem")
    print(len(lim.areas), "límites:", {n: sum(1 for a in lim.areas if a[0] == n) for n in (8, 9, 10, 11)})
    celda = CELDA
    while True:
        idx, nombres = rejilla(lim.areas, celda)
        rect = cajas(idx)
        print(f"celda {celda:.0f} m: {len(rect)} cajas, {len(nombres)} nombres")
        if len(rect) <= MAX_CAJAS:
            break
        celda *= 1.25
    # etiquetas cortas (las del juego son de 4-7 letras): BCN000...
    etiquetas = {nombre: f"BCN{i:03d}" for i, nombre in enumerate(nombres)}
    lineas = ["zone"]
    for k, (c0, f0, c1, f1, v) in enumerate(rect):
        x0, y0 = -LADO + c0 * celda, -LADO + f0 * celda
        x1, y1 = -LADO + c1 * celda, -LADO + f1 * celda
        lineas.append(f"Z_BCN{k:04d}, {x0:.1f}, {y0:.1f}, -300.0, {x1:.1f}, {y1:.1f}, 1500.0, "
                      f"{etiquetas[nombres[v]]}, 0")
    lineas.append("end")
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "popzone.ipl").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    (SALIDA / "nombres.json").write_text(json.dumps({etiquetas[n]: nombre_juego(n) for n in nombres}, indent=1,
                                                    ensure_ascii=False), encoding="utf-8")
    print("Escrito", SALIDA / "popzone.ipl")


def meter_en(raiz, gta, copia):
    """Para quitar_ls: popzone.ipl de los barrios y sus nombres en global.gxt2 de cada idioma (el lang/<idioma>.rpf
    de x64/patch de update.rpf, sacado de la copia sin tocar, con los textos nuevos)."""
    import shutil
    import rage
    if not (SALIDA / "popzone.ipl").exists():
        print("barrios: sin mod_v/barrios/popzone.ipl (python barrios_v.py); se deja la zona única")
        return False
    shutil.copy2(SALIDA / "popzone.ipl", raiz / "common" / "data" / "levels" / "gta5" / "popzone.ipl")
    nombres = json.loads((SALIDA / "nombres.json").read_text(encoding="utf-8"))
    for idioma in IDIOMAS:
        destino = raiz / "x64" / "patch" / "data" / "lang" / f"{idioma}.rpf"
        r = rage.subprocess.run([str(rage.DOTNET), str(rage.CWTOOL), "abrir", str(gta), str(copia), str(destino),
                                 "solo:" + "\\".join([copia.name, "x64", "patch", "data", "lang", f"{idioma}.rpf"])],
                                capture_output=True, text=True)
        gxt = destino / "global.gxt2"
        if r.returncode != 0 or not gxt.exists():
            raise RuntimeError(f"no se pudo sacar {idioma}.rpf: " + r.stdout[-300:] + r.stderr[-500:])
        textos = leer_gxt2(gxt.read_bytes())
        for etiqueta, nombre in nombres.items():
            textos[joaat(etiqueta)] = nombre
        gxt.write_bytes(escribir_gxt2(textos))
        print(f"{idioma}: {len(nombres)} nombres de barrio en global.gxt2")
    return True


if __name__ == "__main__":
    main()
