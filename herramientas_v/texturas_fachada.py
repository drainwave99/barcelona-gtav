"""Biblioteca de materiales y piezas de fachada (atlas de 2048 px) para los edificios de GTA V.

No son fachadas enteras: son materiales que se repiten en metros reales (ladrillo, revoque...) y piezas
sueltas (una ventana, una persiana, un escaparate) que fachadas_v.py coloca una a una según los datos
de cada edificio. El color de cada revoque va en la propia textura: una paleta de N_PALETA colores
sacados de las fotos reales (paleta.json), cada uno en liso y rugoso (pa_revoque_liso_cNN...).

Atlas 4 x 4 casillas de 512 px:
  fila 0  materiales de pared (512 px = 2 m): ladrillo rojo, ladrillo amarillo, ladrillo marrón, revoque liso
  fila 1  revoque rugoso, aplacado de piedra, gres, hormigón
  fila 2  ventanas (256 px cada una, 4 por casilla): persiana PVC, persiana verde, aluminio, reja |
          balconeras: persiana, cristal, madera, PVC | bajos: persiana metálica, escaparate, portal, garaje
  fila 3  barandilla de hierro (alfa), barandilla de obra, marco de puerta, (libre)
Salida: datos_v/texturas/fachadas.png (+ fachadas_casillas.json con las UV de cada pieza)
"""
import json

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import config_v

T = 512
N_PALETA = 48
rng = np.random.default_rng(2026)


def ruido(n, escala, sigma):
    base = rng.normal(0, 1, (n // escala + 2, n // escala + 2)).astype(np.float32)
    im = Image.fromarray(((base - base.min()) / (np.ptp(base) + 1e-6) * 255).astype(np.uint8))
    im = im.resize((n + 2 * escala, n + 2 * escala), Image.BICUBIC).crop((escala, escala, n + escala, n + escala))
    return (np.asarray(im, np.float32) / 255 - 0.5) * 2 * sigma


def grano(a, sigma):
    return a + rng.normal(0, sigma, a.shape[:2])[..., None]


def ladrillo(color, junta, variacion):
    """Caravista: ladrillo de 29 x 5 cm con junta de 1 cm -> 512 px = 2 m, 7 hiladas de 6 cm por 42 px."""
    a = np.zeros((T, T, 3), np.float32)
    a[:] = junta
    alto, largo = 15, 75  # px de una hilada (6 cm) y un ladrillo (30 cm)
    for f, y in enumerate(range(0, T, alto)):
        desp = (largo // 2) * (f % 2)
        for x in range(-largo, T + largo, largo):
            c = np.array(color, np.float32) * (1 + rng.normal(0, variacion)) + rng.normal(0, 6, 3)
            x0, x1 = max(x + desp + 2, 0), min(x + desp + largo - 2, T)
            if x1 > x0:
                a[y + 2:y + alto - 1, x0:x1] = c
    a += ruido(T, 8, 10)[..., None]
    return grano(a, 7)


def revoque(base, rugoso):
    a = np.full((T, T, 3), base, np.float32)
    a += ruido(T, 64, 6)[..., None] + ruido(T, 16, 4)[..., None]
    if rugoso:
        a += ruido(T, 2, 14)[..., None]
    # suciedad que baja de los vierteaguas: manchas verticales suaves
    for _ in range(12):
        x = rng.integers(0, T)
        a[:, max(x - 6, 0):x + 6] -= np.linspace(0, 10, T)[:, None, None] * rng.random()
    return grano(a, 3 if not rugoso else 6)


def piedra():
    a = np.zeros((T, T, 3), np.float32)
    y = 0
    while y < T:
        h = int(rng.integers(60, 110))
        x = -int(rng.integers(0, 100))
        while x < T:
            w = int(rng.integers(90, 200))
            c = np.array([178, 168, 150], np.float32) * (1 + rng.normal(0, 0.06))
            a[y + 3:y + h - 3, max(x + 3, 0):min(x + w - 3, T)] = c
            x += w
        y += h
    a[a.sum(-1) == 0] = (120, 114, 104)
    return grano(a + ruido(T, 6, 9)[..., None], 6)


def gres():
    """Plaqueta de los 60-70: piezas de 12 x 6 cm, un poco brillantes y de tono variable."""
    a = np.full((T, T, 3), (150, 140, 128), np.float32)
    for y in range(0, T, 16):
        for x in range(0, T, 31):
            c = np.array([196, 150, 112], np.float32) * (1 + rng.normal(0, 0.07))
            a[y + 1:y + 15, x + 1:x + 30] = c
    return grano(a + ruido(T, 4, 5)[..., None], 4)


def hormigon():
    a = np.full((T, T, 3), (162, 160, 154), np.float32)
    a += ruido(T, 32, 12)[..., None] + ruido(T, 3, 6)[..., None]
    for y in range(0, T, 128):  # juntas de encofrado
        a[y:y + 2] -= 25
    return grano(a, 4)


def ventana(tipo, w=256, h=256):
    """Una ventana (o balconera) de frente, con su marco y su hueco."""
    im = Image.new("RGB", (w, h), (70, 70, 72))
    d = ImageDraw.Draw(im)
    marco = {"pvc": (232, 232, 228), "verde": (64, 98, 70), "aluminio": (170, 172, 174), "reja": (52, 52, 54),
             "madera": (110, 74, 46)}[tipo]
    d.rectangle([0, 0, w - 1, h - 1], fill=(90, 88, 86))
    d.rectangle([10, 10, w - 11, h - 11], fill=marco)
    # cristal con reflejo del cielo
    vid = np.zeros((h - 40, w - 40, 3), np.float32)
    vid[:] = (112, 128, 146)  # refleja el cielo: claro arriba, más oscuro abajo (interior)
    vid += np.linspace(40, -45, h - 40)[:, None, None]
    vid += ruido(max(w, h), 16, 8)[:h - 40, :w - 40, None]
    im.paste(Image.fromarray(vid.clip(0, 255).astype(np.uint8)), (20, 20))
    d.line([w // 2, 20, w // 2, h - 20], fill=marco, width=8)
    if tipo in ("pvc", "madera"):  # persiana enrollable bajada a una altura distinta en cada pieza
        baja = int(h * rng.uniform(0.25, 0.7))
        col = (218, 214, 204) if tipo == "pvc" else (150, 112, 74)
        d.rectangle([18, 18, w - 19, baja], fill=col)
        for y in range(22, baja, 7):
            d.line([18, y, w - 19, y], fill=tuple(int(c * 0.82) for c in col), width=1)
        d.rectangle([12, 12, w - 13, 26], fill=tuple(int(c * 0.9) for c in col))  # cajón
    if tipo == "verde":  # persiana de lamas (alicantina) medio abierta
        for y in range(20, h // 2, 9):
            d.line([20, y, w - 21, y], fill=(52, 84, 58), width=6)
    if tipo == "reja":
        for x in range(30, w - 20, 26):
            d.line([x, 14, x, h - 14], fill=(40, 40, 42), width=5)
        d.line([14, h // 2, w - 14, h // 2], fill=(40, 40, 42), width=5)
    d.rectangle([4, h - 14, w - 5, h - 4], fill=(198, 194, 186))  # vierteaguas
    return np.asarray(im.filter(ImageFilter.GaussianBlur(0.6)), np.float32)


def bajo(tipo, w=256, h=256):
    im = Image.new("RGB", (w, h), (90, 88, 84))
    d = ImageDraw.Draw(im)
    if tipo == "persiana":
        base = np.array([150, 152, 154]) * rng.uniform(0.8, 1.1)
        d.rectangle([6, 6, w - 7, h - 1], fill=tuple(base.astype(int)))
        for y in range(10, h, 6):
            d.line([6, y, w - 7, y], fill=tuple((base * 0.78).astype(int)), width=2)
        d.rectangle([6, 6, w - 7, 30], fill=(110, 110, 112))
    elif tipo == "escaparate":
        d.rectangle([0, 0, w - 1, 52], fill=(int(rng.integers(40, 200)), int(rng.integers(40, 160)), int(rng.integers(40, 160))))
        d.rectangle([8, 60, w - 9, h - 1], fill=(48, 56, 64))
        for x in range(20, w - 20, 40):  # género tras el cristal
            d.rectangle([x, h - 90, x + 26, h - 20], fill=tuple(int(c) for c in rng.integers(60, 200, 3)))
        d.line([w // 2, 60, w // 2, h], fill=(150, 150, 152), width=6)
    elif tipo == "portal":
        d.rectangle([40, 20, w - 41, h - 1], fill=(56, 48, 40))
        d.rectangle([64, 44, w - 65, h - 60], fill=(70, 84, 96))
        for x in range(76, w - 70, 22):
            d.line([x, 44, x, h - 60], fill=(40, 40, 40), width=4)
        d.rectangle([30, 10, w - 31, 22], fill=(190, 186, 176))
    elif tipo == "garaje":
        d.rectangle([10, 30, w - 11, h - 1], fill=(120, 122, 118))
        for y in range(40, h, 20):
            d.line([10, y, w - 11, y], fill=(96, 98, 94), width=3)
    a = np.asarray(im, np.float32) + ruido(w, 8, 5)[:h, :w, None]
    return grano(a, 3)


def barandilla(hierro):
    a = np.zeros((T // 2, T, 4), np.float32)
    if hierro:
        a[0:10, :, :3], a[0:10, :, 3] = 40, 255
        a[-8:, :, :3], a[-8:, :, 3] = 40, 255
        for x in range(0, T, 22):
            a[:, x:x + 5, :3], a[:, x:x + 5, 3] = 46, 255
    else:
        a[..., :3] = 214
        a[..., 3] = 255
        a[:12, :, :3] = 188
        a[..., :3] += ruido(T, 16, 6)[:T // 2, :, None]
    return a


def albedo(x):
    """Color de foto -> color de la pintura. Muchas fotos tienen la fachada en sombra (oscura y azulada
    por la luz del cielo): se conserva el tono, se lleva la luminosidad a 150-235 y se quita el azul."""
    x = np.atleast_2d(np.asarray(x, np.float32))
    gris = x.mean(-1, keepdims=True)
    croma = x - gris
    azul = croma[:, 2:3] > 0  # pintura azul casi no hay: es la sombra
    croma = np.where(azul, croma * 0.35, croma * 1.5)
    lum = 150 + np.clip((gris - 70) / 170, 0, 1) * 85
    return np.clip(lum + croma, 0, 245)


def paleta():
    """k-medias de los colores de revoque de las fotos -> [(rgb, peso)] ordenada por frecuencia."""
    ruta = config_v.DATOS / "texturas" / "colores.json"
    datos = json.loads(ruta.read_text()) if ruta.exists() else {}
    x = np.array([v["rgb"] for v in datos.values() if v["material"].startswith("revoque")], np.float32)
    x = albedo(x)
    if len(x) < N_PALETA:
        x = np.array([(214, 196, 170), (226, 214, 196), (196, 178, 160), (220, 206, 180)], np.float32)
    r = np.random.default_rng(7)
    c = x[r.choice(len(x), min(N_PALETA, len(x)), replace=False)]
    for _ in range(40):
        k = np.argmin(((x[:, None] - c[None]) ** 2).sum(-1), 1)
        c = np.array([x[k == j].mean(0) if np.any(k == j) else c[j] for j in range(len(c))])
    k = np.argmin(((x[:, None] - c[None]) ** 2).sum(-1), 1)
    pesos = np.bincount(k, minlength=len(c))
    orden = np.argsort(-pesos)
    return [([int(v) for v in c[j]], int(pesos[j])) for j in orden if pesos[j] > 0]


def main():
    atlas = np.zeros((4 * T, 4 * T, 4), np.float32)
    atlas[..., 3] = 255
    casillas = {}

    def poner(nombre, a, fila, col, w=T, h=T, dx=0, dy=0):
        y, x = fila * T + dy, col * T + dx
        atlas[y:y + h, x:x + w, :a.shape[2]] = a[:h, :w]
        # UV (v hacia arriba, origen abajo a la izquierda del atlas)
        casillas[nombre] = [x / (4 * T), 1 - (y + h) / (4 * T), (x + w) / (4 * T), 1 - y / (4 * T)]

    paredes = [("ladrillo_rojo", ladrillo((158, 96, 74), (176, 168, 156), 0.07)),
               ("ladrillo_amarillo", ladrillo((200, 172, 128), (190, 182, 166), 0.06)),
               ("ladrillo_marron", ladrillo((120, 80, 64), (150, 140, 128), 0.06)),
               ("revoque_liso", revoque((236, 234, 230), False)),
               ("revoque_rugoso", revoque((232, 230, 226), True)),
               ("revoque_gris", revoque((176, 172, 166), True)),
               ("piedra", piedra()), ("gres", gres()), ("hormigon", hormigon())]
    salida = config_v.DATOS / "texturas"
    salida.mkdir(parents=True, exist_ok=True)
    # Cada material de pared va en su propia textura (se repite por la pared: no puede ir en el atlas)
    for k, (nombre, a) in enumerate(paredes):
        if k < 8:  # muestra en el atlas (solo de referencia)
            poner(nombre, a, k // 4, k % 4)
        Image.fromarray(a.clip(0, 255).astype(np.uint8)).save(salida / f"pa_{nombre}.png")
    for vieja in salida.glob("pa_revoque_*_c*.png"):
        vieja.unlink()
    colores = paleta()
    for j, (rgb, _) in enumerate(colores):
        for rugoso in (False, True):
            a = revoque(rgb, rugoso)
            nombre = f"pa_revoque_{'rugoso' if rugoso else 'liso'}_c{j:02d}.png"
            Image.fromarray(a.clip(0, 255).astype(np.uint8)).save(salida / nombre)
    (salida / "paleta.json").write_text(json.dumps(colores))
    print(f"Paleta: {len(colores)} colores de revoque")
    piezas = [("ventana_pvc", ventana("pvc")), ("ventana_verde", ventana("verde")),
              ("ventana_aluminio", ventana("aluminio")), ("ventana_reja", ventana("reja")),
              ("balconera_pvc", ventana("pvc", 256, 512)[::2]), ("balconera_cristal", ventana("aluminio", 256, 512)[::2]),
              ("balconera_madera", ventana("madera", 256, 512)[::2]), ("balconera_verde", ventana("verde", 256, 512)[::2]),
              ("bajo_persiana", bajo("persiana")), ("bajo_escaparate", bajo("escaparate")),
              ("bajo_portal", bajo("portal")), ("bajo_garaje", bajo("garaje"))]
    for k, (nombre, a) in enumerate(piezas):
        casilla, sub = divmod(k, 4)
        poner(nombre, a, 2, casilla, 256, 256, (sub % 2) * 256, (sub // 2) * 256)
    poner("barandilla_hierro", barandilla(True), 3, 0, T, T // 2)
    poner("barandilla_obra", barandilla(False), 3, 1, T, T // 2)

    Image.fromarray(atlas.clip(0, 255).astype(np.uint8), "RGBA").save(salida / "fachadas.png")
    (salida / "fachadas_casillas.json").write_text(json.dumps(casillas, indent=1))
    print(f"Atlas de fachadas: {len(casillas)} piezas en {salida / 'fachadas.png'}")


if __name__ == "__main__":
    main()
