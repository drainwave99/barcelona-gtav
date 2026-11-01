import re, sys
from pathlib import Path
xml = Path(r"C:\Users\danny\Desktop\GTA SAN ANDREAS MOD CON ISMA\mod_v\prototipo") / sys.argv[1] / "xml"
dic = {}
for y in xml.glob("*.ytd.xml"):
    s = y.read_text(encoding="utf-8", errors="ignore")
    dic[y.name[:-8]] = set(re.findall(r"<Name>([^<]+)</Name>", s))
import pickle
col = pickle.load(open(xml.parent / "colocacion.pkl", "rb"))
ytd_de = {m: t for m, t, _ in col["arquetipos"]}
falta = {}
for d in xml.glob("*.ydr.xml"):
    nombre = d.name[:-8]
    s = d.read_text(encoding="utf-8", errors="ignore")
    texs = set(re.findall(r'name="DiffuseSampler" type="Texture"><Name>([^<]+)</Name>', s))
    t = ytd_de.get(nombre)
    if t is None:
        falta.setdefault("(sin arquetipo)", set()).add(nombre); continue
    disp = dic.get(t, set())
    for x in texs - disp:
        falta.setdefault(t, set()).add(x)
for k, v in falta.items():
    print(k, sorted(v)[:20], len(v))
print("ok" if not falta else "")
