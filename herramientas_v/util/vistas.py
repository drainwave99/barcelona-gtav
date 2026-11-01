"""Escribe bcn_vistas.txt (carpeta del juego) para que bcn_diag haga capturas en esos sitios (con bcn_auto.txt).

Uso: vistas.py entrada.txt     cada línea: E N altura rumbo cabeceo nombre
     altura '+12' = sobre el suelo (LiDAR), '40' = cota absoluta; rumbo en grados (0 norte, 90 este)
     vistas.py --borrar         quita bcn_vistas.txt (el plugin vuelve a sus vistas fijas)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config_v
import puentes_v

GTA = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V")

if sys.argv[1] == "--borrar":
    (GTA / "bcn_vistas.txt").unlink(missing_ok=True)
    sys.exit()
relieve = puentes_v.Relieve()
salida = []
for linea in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if not linea.strip() or linea.startswith("#"):
        continue
    e, n, alt, rumbo, cabeceo, *nombre = linea.split()
    e, n = float(e), float(n)
    z = float(relieve.valor("suelo", e, n)) + float(alt[1:]) if alt.startswith("+") else float(alt)
    x, y = config_v.utm_a_juego(e, n)
    salida.append(f"{x:.1f} {y:.1f} {z:.1f} {float(cabeceo):.1f} {-float(rumbo):.1f} {' '.join(nombre)}")
(GTA / "bcn_vistas.txt").write_text("\n".join(salida) + "\n", encoding="ascii", errors="replace")
print(len(salida), "vistas")
