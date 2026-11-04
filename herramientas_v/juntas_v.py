"""Medida de los fallos de enlace entre viaductos y calles a nivel en unas hojas.
python juntas_v.py 434586 [...]  -> por hoja: (1) extremos de puente que llegan a una calle con salto >0,3 m entre
tablero y suelo; (2) tramos de calle a nivel que pasan por la planta de un tablero a menos de 2,5 m de él
(choque: el tablero y la calle se cruzan o se tocan)."""
import pickle, sys
import numpy as np
import shapely
from shapely.geometry import LineString, Point
sys.path.insert(0, r"C:\Users\danny\Desktop\GTA SAN ANDREAS MOD CON ISMA\herramientas_v")
import config_v, puentes_v, calles_v
osm = pickle.load(open(config_v.DATOS / "osm.pkl", "rb"))
rel = puentes_v.Relieve()
todas = puentes_v.vias_puente(osm); puentes_v.extremos_internos(todas, osm)
for hoja in sys.argv[1:]:
    e0, n0 = int(hoja[:3]) * 1000, (4000 + int(hoja[3:])) * 1000
    caja = (e0, n0, e0 + 1000, n0 + 1000)
    puentes_v._PERFILES.clear()
    vp = puentes_v.cerca(todas, caja); per = puentes_v.perfiles(vp, rel)
    tapado = puentes_v.plantas_bajas(vp, caja)
    saltos, choques = [], []
    plantas, zs = [], []
    for v, r in zip(vp, per):
        if r is None or v["s"]["tipo"] not in ("autopista", "calle"):
            continue
        pts, der, ds, z, sz = r
        plantas.append(LineString(pts).buffer(v["s"]["ancho"] / 2, cap_style="flat")); zs.append((pts, z))
        for k, interno in zip((0, -1), v["internos"]):
            p = pts[k]
            if interno or not (caja[0] <= p[0] < caja[2] and caja[1] <= p[1] < caja[3]):
                continue
            t = pts[1] - pts[0] if k == 0 else pts[-1] - pts[-2]
            t = t / (np.linalg.norm(t) + 1e-9) * (-1 if k == 0 else 1)
            q = p + t * 3.0
            s = float(rel.valor("suelo", q[0], q[1])) + 0.04
            if abs(z[k] - s) > 0.3:
                saltos.append((round(z[k] - s, 1), round(p[0] - 430500), round(p[1] - 4585000), v["tags"].get("name", v["tags"].get("highway"))))
    arbol = shapely.STRtree(plantas) if plantas else None
    for linea, t, w in calles_v.vias_coche(osm, caja):
        for d in np.arange(0, linea.length, 4.0):
            p = linea.interpolate(d)
            if not (caja[0] <= p.x < caja[2] and caja[1] <= p.y < caja[3]):
                continue
            if tapado is not None and tapado.contains(p):
                continue  # ahí ya no hay calle a nivel
            for b in arbol.query(p, predicate="intersects") if arbol is not None else []:
                pts, z = zs[b]
                i = np.argmin(((pts - [p.x, p.y]) ** 2).sum(1))
                s = float(rel.valor("suelo", p.x, p.y))
                if -1.0 < z[i] - s < 2.5:
                    choques.append((round(z[i] - s, 1), round(p.x - 430500), round(p.y - 4585000), t.get("name", t.get("highway"))))
    print(f"{hoja}: {len(saltos)} saltos en extremos, {len(choques)} puntos de choque calle/tablero")
    for s in sorted(saltos, key=lambda x: -abs(x[0]))[:8]:
        print("   salto", s)
    vistos = set()
    for c in choques:
        k = (c[1] // 25, c[2] // 25)
        if k not in vistos:
            vistos.add(k); print("   choque", c)
