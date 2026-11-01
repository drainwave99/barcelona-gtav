"""Hojas generadas antes del último cambio que les afecta (código del generador, túneles, costa)."""
import os, pickle, sys
from pathlib import Path
import numpy as np
H = Path(r"C:\Users\danny\Desktop\GTA SAN ANDREAS MOD CON ISMA\herramientas_v")
sys.path.insert(0, str(H))
import config_v, shapely
P = config_v.MOD / "prototipo"
general = max(os.path.getmtime(H / f) for f in ("prototipo.py", "calles_v.py", "edificios_v.py", "andenes_v.py",
                                                "fachadas_v.py", "monumentos_v.py", "monumentos_bcn.py"))
t_tun = os.path.getmtime(H / "tuneles_v.py")
tuneles = pickle.load(open(config_v.DATOS / "tuneles.pkl", "rb"))
out = []
for h in sorted(os.listdir(P)):
    c = P / h / "colocacion.pkl"
    if not c.exists():
        continue
    t = os.path.getmtime(c)
    e0, n0 = int(h[:3]) * 1000, (4000 + int(h[3:])) * 1000
    tiene_tunel = any((tu["pts"][:, 0] >= e0).any() and (tu["pts"][:, 0] < e0 + 1000).any() and
                      ((tu["pts"][:, 1] >= n0) & (tu["pts"][:, 1] < n0 + 1000)).any() for tu in tuneles)
    if t < general or (tiene_tunel and t < t_tun):
        out.append(h)
print(" ".join(out))
