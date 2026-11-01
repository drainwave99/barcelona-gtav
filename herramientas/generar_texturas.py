"""Genera las texturas de los edificios (datos/generado/texturas/).

Fachadas (fa_*) y bajos (ba_*): 4 m de ancho x 1 planta de alto (256 x 256 px).
Tejados (te_*): 10 x 10 m.
Los UV de blender_edificios.py ya están pensados para estas medidas. Los colores de las paredes son
claros y neutros: blender_edificios.py tiñe cada edificio con su color (en el prelight).
"""
import numpy as np
from PIL import Image, ImageDraw

import config

SALIDA = config.DATOS / "generado" / "texturas"
T = 256
P = T / 4  # píxeles por metro de ancho

FACHADAS = ["fa_balcon", "fa_ladrillo", "fa_moderno", "fa_obrero", "fa_casa", "fa_nave", "fa_hormigon",
            "fa_ladrillo2", "fa_gres", "fa_estuco", "fa_terraza"]
BAJOS = ["ba_tienda", "ba_persiana", "ba_portal", "ba_nave", "ba_bar", "ba_farmacia"]
TEJADOS = ["te_terrado", "te_teja", "te_nave"]
# Calle (procesar_calles.py): asfalto 4 x 4 m, panot 1 x 1 m, bordillo, línea blanca, paso de cebra
CALLE = ["as_asfalto", "ac_panot", "ac_bordillo", "as_linea", "as_cebra", "ba_balcon"]


def acabar(img, fuerza=5, semilla=0):
    rng = np.random.default_rng(semilla)
    arr = np.asarray(img, dtype=np.float32) + rng.normal(0, fuerza, (T, T, 1))
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8))


def m(x):
    return int(round(x * P))


def ventana(d, x0, y0, x1, y1, persiana=0.4, marco=(225, 220, 210), vidrio=(55, 68, 80), lamas=(150, 125, 90)):
    d.rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], fill=marco)
    d.rectangle([x0, y0, x1, y1], fill=vidrio)
    # reflejo
    d.polygon([(x0, y1), (x0 + (x1 - x0) * 0.4, y0), (x0 + (x1 - x0) * 0.55, y0), (x0 + (x1 - x0) * 0.15, y1)], fill=tuple(c + 25 for c in vidrio))
    if persiana:
        yp = y0 + int((y1 - y0) * persiana)
        d.rectangle([x0, y0, x1, yp], fill=lamas)
        for y in range(y0, yp, 5):
            d.line([x0, y, x1, y], fill=tuple(int(c * 0.8) for c in lamas))
    d.line([(x0 + x1) // 2, yp if persiana else y0, (x0 + x1) // 2, y1], fill=marco, width=3)


def barandilla(d, x0, x1, y0, y1, color=(40, 40, 42)):
    d.rectangle([x0 - 6, y1, x1 + 6, y1 + 8], fill=(165, 160, 152))  # losa del balcón
    d.line([x0 - 6, y0, x1 + 6, y0], fill=color, width=4)
    for x in range(x0 - 4, x1 + 6, 9):
        d.line([x, y0, x, y1], fill=color, width=2)


def fa_balcon():
    img = Image.new("RGB", (T, T), (214, 206, 192))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, T, 10], fill=(190, 182, 168))
    ventana(d, m(1.3), 40, m(2.7), 236, persiana=0.45)
    barandilla(d, m(1.0), m(3.0), 170, 238)
    return acabar(img, 4, 1)


def fa_ladrillo():
    img = Image.new("RGB", (T, T), (176, 96, 62))  # ladrillo naranja-rojizo de los pisos de Badalona
    d = ImageDraw.Draw(img)
    for fila, y in enumerate(range(0, T, 8)):
        d.line([0, y, T, y], fill=(185, 170, 150), width=2)
        for x in range((fila % 2) * 12, T, 24):
            d.line([x, y, x, y + 8], fill=(185, 170, 150), width=2)
    d.rectangle([0, 0, T, 12], fill=(170, 165, 158))
    ventana(d, m(0.6), 60, m(1.8), 200, persiana=0.3, marco=(190, 190, 192), lamas=(200, 200, 195))
    d.rectangle([m(2.3), 40, m(3.6), 250], fill=(60, 58, 55))  # terraza hundida
    barandilla(d, m(2.3), m(3.6), 170, 246, color=(205, 205, 200))
    return acabar(img, 7, 2)


def fa_moderno():
    img = Image.new("RGB", (T, T), (228, 228, 224))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, T, 22], fill=(200, 200, 198))
    d.rectangle([0, 70, T, 200], fill=(170, 172, 175))
    d.rectangle([4, 76, T - 4, 194], fill=(70, 90, 110))
    for x in range(0, T, m(1.0)):
        d.line([x, 76, x, 194], fill=(170, 172, 175), width=4)
    d.line([0, 150, T, 150], fill=(150, 152, 155), width=3)
    return acabar(img, 3, 3)


def fa_obrero():
    img = Image.new("RGB", (T, T), (200, 195, 180))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, T, 8], fill=(175, 170, 158))
    ventana(d, m(0.5), 70, m(1.5), 190, persiana=0.55, lamas=(110, 95, 70))
    ventana(d, m(2.3), 60, m(3.6), 200, persiana=0.25, lamas=(205, 205, 200))
    # tendedero con ropa
    d.line([m(2.2), 210, m(3.7), 210], fill=(90, 90, 90), width=2)
    for x, color in ((m(2.4), (180, 40, 40)), (m(2.8), (40, 80, 160)), (m(3.2), (230, 230, 230))):
        d.rectangle([x, 210, x + 18, 236], fill=color)
    return acabar(img, 6, 4)


def fa_casa():
    img = Image.new("RGB", (T, T), (236, 232, 222))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, T, 6], fill=(205, 200, 190))
    x0, x1 = m(1.4), m(2.6)
    ventana(d, x0, 60, x1, 200, persiana=0)
    verde = (60, 105, 70)
    for xa, xb in ((x0 - 44, x0 - 6), (x1 + 6, x1 + 44)):  # porticones abiertos
        d.rectangle([xa, 56, xb, 204], fill=verde)
        for y in range(62, 200, 8):
            d.line([xa + 3, y, xb - 3, y], fill=(45, 80, 52), width=2)
    d.rectangle([x0 - 8, 204, x1 + 8, 214], fill=(190, 180, 165))
    return acabar(img, 4, 5)


def fa_nave():
    img = Image.new("RGB", (T, T), (175, 178, 180))
    d = ImageDraw.Draw(img)
    for x in range(0, T, 16):
        d.rectangle([x, 0, x + 7, T], fill=(160, 163, 166))
    d.rectangle([0, 30, T, 60], fill=(90, 105, 115))
    for x in range(0, T, 32):
        d.line([x, 30, x, 60], fill=(140, 140, 140), width=3)
    return acabar(img, 5, 6)


def fa_hormigon():
    """Pared sin ventanas (chimeneas, torres, muros)."""
    img = Image.new("RGB", (T, T), (185, 182, 175))
    d = ImageDraw.Draw(img)
    d.line([0, T - 2, T, T - 2], fill=(160, 157, 150), width=3)
    d.line([T // 2, 0, T // 2, T], fill=(172, 169, 162), width=2)
    return acabar(img, 7, 15)


def ba_tienda():
    img = Image.new("RGB", (T, T), (120, 112, 104))
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(11)
    d.rectangle([0, 18, T, 70], fill=(170, 40, 40))  # rótulo
    for i in range(6):
        x = 30 + i * 32
        d.rectangle([x, 34, x + 20, 54], fill=(240, 235, 220))
    d.rectangle([12, 82, T - 12, 248], fill=(60, 60, 62))
    d.rectangle([18, 88, T - 18, 248], fill=(95, 120, 135))
    for _ in range(14):  # productos del escaparate
        x, y = rng.integers(24, T - 40), rng.integers(150, 230)
        d.rectangle([x, y, x + 16, y + 18], fill=tuple(int(v) for v in rng.integers(60, 230, 3)))
    d.line([T // 2, 88, T // 2, 248], fill=(60, 60, 62), width=4)
    return acabar(img, 4, 7)


def ba_persiana():
    img = Image.new("RGB", (T, T), (110, 104, 98))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 18, T, 60], fill=(40, 90, 150))
    d.rectangle([10, 70, T - 10, 250], fill=(150, 152, 150))
    for y in range(70, 250, 6):
        d.line([10, y, T - 10, y], fill=(120, 122, 120), width=2)
    # pintadas
    for x0, color in ((40, (200, 60, 150)), (120, (60, 170, 80)), (170, (230, 200, 40))):
        d.line([x0, 200, x0 + 30, 140, x0 + 60, 210], fill=color, width=10)
    return acabar(img, 6, 8)


def ba_portal():
    img = Image.new("RGB", (T, T), (150, 140, 128))
    d = ImageDraw.Draw(img)
    for y in range(0, T, 32):
        d.line([0, y, T, y], fill=(130, 120, 110), width=3)
    d.rectangle([m(1.2), 60, m(2.8), 252], fill=(80, 62, 45))
    d.rectangle([m(1.35), 75, m(2.65), 180], fill=(60, 75, 85))
    for x in range(m(1.35), m(2.65), 14):
        d.line([x, 75, x, 180], fill=(30, 30, 30), width=3)
    d.rectangle([m(1.9), 200, m(2.1), 210], fill=(200, 180, 80))
    return acabar(img, 5, 9)


def ba_nave():
    img = Image.new("RGB", (T, T), (170, 172, 172))
    d = ImageDraw.Draw(img)
    d.rectangle([16, 40, T - 16, 256], fill=(130, 135, 140))
    for y in range(40, 256, 10):
        d.line([16, y, T - 16, y], fill=(105, 110, 115), width=3)
    d.rectangle([0, 0, T, 20], fill=(200, 160, 40))
    return acabar(img, 5, 10)


def te_terrado():
    img = Image.new("RGB", (T, T), (176, 120, 95))
    d = ImageDraw.Draw(img)
    paso = T // 16
    for i in range(0, T, paso):
        d.line([i, 0, i, T], fill=(150, 100, 80))
        d.line([0, i, T, i], fill=(150, 100, 80))
    d.rectangle([40, 40, 80, 70], fill=(200, 200, 205))  # depósito / antena
    d.ellipse([170, 150, 200, 180], fill=(220, 220, 225))
    return acabar(img, 8, 12)


def te_teja():
    img = Image.new("RGB", (T, T), (170, 85, 55))
    d = ImageDraw.Draw(img)
    for fila, y in enumerate(range(0, T, 16)):
        d.line([0, y, T, y], fill=(120, 55, 35), width=3)
        for x in range((fila % 2) * 8, T, 16):
            d.arc([x, y - 8, x + 16, y + 8], 0, 180, fill=(140, 65, 40), width=2)
    return acabar(img, 10, 13)


def te_nave():
    img = Image.new("RGB", (T, T), (150, 155, 158))
    d = ImageDraw.Draw(img)
    for x in range(0, T, 12):
        d.line([x, 0, x, T], fill=(125, 130, 134), width=4)
    return acabar(img, 5, 14)


def fa_ladrillo2():
    """Ladrillo oscuro de las torres de Llefià (años 60-70) con ventana de aluminio y terraza."""
    img = Image.new("RGB", (T, T), (132, 70, 50))
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(21)
    for fila, y in enumerate(range(0, T, 8)):
        d.line([0, y, T, y], fill=(160, 150, 135), width=2)
        for x in range((fila % 2) * 12, T, 24):
            d.line([x, y, x, y + 8], fill=(160, 150, 135), width=2)
            if rng.random() < 0.25:  # ladrillos de otro tono
                d.rectangle([x + 2, y + 2, x + 22, y + 7], fill=tuple(int(v) for v in rng.integers(100, 150, 3) * [1.0, 0.55, 0.4]))
    d.rectangle([0, 0, T, 14], fill=(150, 148, 140))
    ventana(d, m(0.4), 64, m(1.9), 196, persiana=0.5, marco=(170, 170, 172), lamas=(190, 190, 185))
    d.rectangle([m(2.3), 40, m(3.7), 250], fill=(55, 50, 48))
    d.rectangle([m(2.3), 175, m(3.7), 250], fill=(150, 148, 140))  # antepecho de obra
    return acabar(img, 8, 22)


def fa_gres():
    """Fachada aplacada de gres cerámico beige (típica de los 70) con persiana enrollable."""
    img = Image.new("RGB", (T, T), (205, 190, 160))
    d = ImageDraw.Draw(img)
    for y in range(0, T, 16):
        d.line([0, y, T, y], fill=(185, 170, 140), width=1)
    for x in range(0, T, 32):
        d.line([x, 0, x, T], fill=(185, 170, 140), width=1)
    ventana(d, m(1.0), 50, m(3.0), 205, persiana=0.6, marco=(200, 200, 200), lamas=(215, 210, 195))
    barandilla(d, m(0.8), m(3.2), 175, 236, color=(70, 70, 70))
    return acabar(img, 4, 23)


def fa_estuco():
    """Estuco liso con porticones verdes de librillo (casas antiguas de La Salut)."""
    img = Image.new("RGB", (T, T), (230, 222, 205))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, T, 12], fill=(210, 200, 182))
    x0, x1 = m(1.5), m(2.5)
    d.rectangle([x0 - 8, 40, x1 + 8, 222], fill=(215, 205, 188))  # recercado
    ventana(d, x0, 48, x1, 214, persiana=0)
    for xa, xb in ((x0 - 34, x0 - 4), (x1 + 4, x1 + 34)):
        d.rectangle([xa, 48, xb, 214], fill=(70, 110, 85))
        for y in range(54, 210, 7):
            d.line([xa + 2, y, xb - 2, y], fill=(50, 85, 62), width=2)
    barandilla(d, x0 - 10, x1 + 10, 180, 228)
    return acabar(img, 4, 24)


def fa_terraza():
    """Terraza corrida acristalada (pisos de los 80-90)."""
    img = Image.new("RGB", (T, T), (225, 218, 205))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, T, 26], fill=(205, 200, 190))  # canto del forjado
    d.rectangle([0, 26, T, 180], fill=(80, 95, 105))
    for x in range(0, T, 64):
        d.line([x, 26, x, 180], fill=(200, 200, 200), width=4)
    d.rectangle([0, 180, T, T], fill=(150, 175, 185))  # barandilla de vidrio
    d.line([0, 182, T, 182], fill=(210, 210, 210), width=4)
    return acabar(img, 3, 25)


def ba_bar():
    img = Image.new("RGB", (T, T), (90, 70, 55))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 14, T, 64], fill=(30, 110, 60))  # toldo verde
    for x in range(0, T, 32):
        d.rectangle([x, 14, x + 16, 64], fill=(230, 230, 220))
    d.rectangle([14, 80, T - 14, 250], fill=(150, 120, 80))
    d.rectangle([22, 88, T - 22, 200], fill=(200, 170, 110))  # luz de dentro
    d.rectangle([T // 2 - 20, 120, T // 2 + 20, 250], fill=(60, 45, 35))
    return acabar(img, 5, 26)


def ba_farmacia():
    img = Image.new("RGB", (T, T), (200, 200, 198))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 14, T, 64], fill=(240, 240, 240))
    d.rectangle([T // 2 - 22, 18, T // 2 + 22, 60], fill=(20, 160, 60))  # cruz verde
    d.rectangle([T // 2 - 8, 22, T // 2 + 8, 56], fill=(240, 240, 240))
    d.rectangle([T // 2 - 18, 32, T // 2 + 18, 46], fill=(240, 240, 240))
    d.rectangle([12, 80, T - 12, 250], fill=(90, 120, 130))
    d.line([T // 2, 80, T // 2, 250], fill=(200, 200, 198), width=6)
    return acabar(img, 3, 27)


def ba_balcon():
    """Frente del balcón (barandilla de forja delante de la pared)."""
    img = Image.new("RGB", (T, T), (205, 198, 185))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, T, 18], fill=(50, 50, 52))
    for x in range(4, T, 14):
        d.line([x, 18, x, T], fill=(45, 45, 47), width=3)
    d.line([0, T - 6, T, T - 6], fill=(50, 50, 52), width=6)
    return acabar(img, 4, 28)


def as_asfalto():
    """Asfalto con grava a dos escalas, parches y manchas (4 x 4 m)."""
    rng = np.random.default_rng(31)
    base = np.full((T, T, 3), 74.0)
    grano = rng.normal(0, 9, (T, T, 1)) + rng.normal(0, 5, (T // 2, T // 2, 1)).repeat(2, 0).repeat(2, 1)
    arr = base + grano
    img = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    # un parche de asfalto nuevo y alguna mancha de aceite, suaves (se repiten cada 4 m)
    x, y = rng.integers(0, T - 60, 2)
    d.rectangle([x, y, x + 50, y + 30], fill=(68, 68, 70))
    for _ in range(2):
        x, y = rng.integers(0, T - 30, 2)
        d.ellipse([x, y, x + rng.integers(8, 18), y + rng.integers(6, 12)], fill=(64, 64, 66))
    for _ in range(2):  # grietas
        pts = [tuple(rng.integers(0, T, 2))]
        for _ in range(6):
            pts.append((pts[-1][0] + rng.integers(-25, 25), pts[-1][1] + rng.integers(-25, 25)))
        d.line(pts, fill=(40, 40, 40), width=1)
    return acabar(img, 4, 32)


def ac_panot():
    """Panot de flor (baldosa de 20 x 20 cm de las aceras de Barcelona y Badalona), 1 x 1 m."""
    img = Image.new("RGB", (T, T), (150, 146, 138))
    d = ImageDraw.Draw(img)
    lado = T // 5
    rng = np.random.default_rng(33)
    for i in range(5):
        for j in range(5):
            x, y = i * lado, j * lado
            tono = int(rng.integers(-8, 8))
            d.rectangle([x, y, x + lado - 1, y + lado - 1], fill=(150 + tono, 146 + tono, 138 + tono))
            c = lado / 2
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):  # los cuatro pétalos
                cx, cy = x + c + dx * c / 2.2, y + c + dy * c / 2.2
                d.ellipse([cx - c / 3, cy - c / 3, cx + c / 3, cy + c / 3], outline=(140 + tono, 136 + tono, 128 + tono), width=3)
            d.rectangle([x, y, x + lado - 1, y + lado - 1], outline=(120, 116, 110), width=2)
    return acabar(img, 6, 34)


def ac_bordillo():
    img = Image.new("RGB", (T, T), (150, 150, 148))
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(35)
    for _ in range(900):  # granito moteado
        x, y = rng.integers(0, T, 2)
        g = int(rng.integers(90, 210))
        d.point((int(x), int(y)), fill=(g, g, g))
    for x in range(0, T, T // 2):  # juntas cada 50 cm
        d.line([x, 0, x, T], fill=(100, 100, 100), width=3)
    return acabar(img, 6, 36)


def as_linea():
    img = Image.new("RGB", (T, T), (225, 225, 215))
    return acabar(img, 12, 37)


def as_cebra():
    """Paso de cebra: una franja blanca de 50 cm y 50 cm de asfalto por cada repetición en U."""
    img = as_asfalto()
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, T // 2, T], fill=(225, 225, 218))
    return acabar(img, 8, 38)


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    for nombre in FACHADAS + BAJOS + TEJADOS + CALLE:
        globals()[nombre]().save(SALIDA / f"{nombre}.png")
    print(f"{len(FACHADAS + BAJOS + TEJADOS + CALLE)} texturas en {SALIDA}")


if __name__ == "__main__":
    main()
