# Mod GTA San Andreas: Badalona

Conversión total del mapa de GTA SA por el municipio de Badalona.

## Encaje del mapa (decidido)

Tiene que estar **todo Badalona + Tres Xemeneies + Canyet + Can Ruti**. Norte arriba no cabe (7,5 km de norte a sur),
así que el mapa está **girado 316°**: la costa queda horizontal, **el mar abajo (sur del juego) y la Serralada arriba**.

- Escala 0,95 (1 unidad GTA = 1,05 m reales). Las alturas también se escalan.
- Mapa de -3000 a +3000. Detalles y fórmula en `herramientas/config.py`.

| Lugar | Coordenadas GTA (x, y) | Altura |
|---|---|---|
| Tres Xemeneies | (-2315, -2693) | 13 |
| Pont del Petroli | (-387, -2192) | 0 |
| Ajuntament | (-27, -1451) | 23 |
| Dalt la Vila | (9, -1324) | 25 |
| Canyet | (1249, 1036) | 136 |
| Can Ruti (hospital) | (1814, 1294) | 196 |

Vista previa: `docs/vista_previa.png`

## Pasos (scripts en `herramientas/`)

Python: `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`
Blender: `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`

| # | Comando | Resultado |
|---|---|---|
| 1 | `python herramientas/descargar_relieve.py` | `datos/elevacion/relieve_gta.*` |
| 2 | Bajar `cataluna-latest.osm.pbf` de Geofabrik a `datos/osm/` y `python herramientas/recortar_osm.py` | `datos/osm/badalona.osm` |
| 3 | `python herramientas/procesar_osm.py` | texturas de suelo + `datos/generado/edificios.json` |
| 4 | `blender --background --factory-startup --python herramientas/blender_terreno.py` | `blender/terreno.blend` (256 trozos de 375 m) |
| 5 | `blender --background --factory-startup --python herramientas/blender_edificios.py` | `blender/badalona.blend` |
| 6 | `python herramientas/generar_texturas.py` (antes del paso 5) | texturas de fachada y terrado |
| 7 | `blender --background --python herramientas/blender_exportar.py` (con DragonFF instalado) | `mod/modelos/*.dff`, `bdn_col_FF.col`, `datos/generado/posiciones.json` |
| 8 | `python herramientas/generar_mapa.py` | TXD, `mod/models/badalona.img`, `badalona.ide/.ipl` (450 modelos, IDs 18631-19080) |
| 9 | Doble clic en `INSTALAR_BADALONA.bat` (pide administrador) | copia al juego, cambia gta.dat y water.dat |

Pasos añadidos (antes del 5 / del 8):

| Comando | Resultado |
|---|---|
| `python herramientas/descargar_orto.py` | suelo con la ortofoto del ICGC (`datos/generado/suelo_orto/`) |
| `python herramientas/procesar_calles.py` | calzada, aceras con bordillo, peatonales, líneas y pasos de cebra (`datos/generado/calles/`) |
| `python herramientas/generar_detalle.py` | árboles, farolas, bancos, papeleras y coches aparcados (`detalle_N.ipl`, `aparcados.ipl`) |
| `python herramientas/generar_zonas.py` | nombres de barrio (`info.zon` + textos en los `.gxt`) |
| `python herramientas/generar_main_scm.py` | guion sin misiones; CJ aparece en la Plaça de Trafalgar (Llefià) |
| `python herramientas/referencias_mapillary.py` | fotos de referencia de fachadas (solo para dibujar texturas) |

**Zona de detalle: Llefià, La Salut y el Turó d'en Caritg** (círculos `DETALLE` en `generar_detalle.py` y
`blender_edificios.py`): balcones volados, casetas y depósitos en los terrados, árboles cada 7 m, farolas a los dos
lados, bancos y papeleras en plazas y parques, coches aparcados.

Límites del juego encontrados (exe RGL): 255 archivos .col; ~4000 líneas por `.ipl` (se reparte en archivos de 3000);
550 "objetos extra" (por eso se ocultan los .dff de Los Santos sin IDE); 500 coches aparcados; ~2500 objetos con física.

Para dejar el juego como estaba: `QUITAR_BADALONA.bat`. Los originales se guardan en `copia_juego/`.

Otros: `encaje.py` (calcula centro/escala), `vista_previa.py`, `blender_render.py` (renders en `docs/`), `instalar_addons.py`.

Estado (2026-10-29): 256 trozos de terreno (524k triángulos) con textura de suelo de OSM, 21.958 edificios
(821k triángulos) en 194 trozos. Las Tres Xemeneies salen con sus partes 3D de OSM.

## Juego

`C:\Program Files (x86)\DODI-Repacks\Grand Theft Auto San Andreas` — exe de 2019 (versión Rockstar Games Launcher),
**no es la 1.0 US** que necesitan casi todas las herramientas de modding.

## Instalado

- Python 3.12 + numpy, requests, shapely, pyproj, pillow, osmium, rasterio
- Blender 5.2
- Descargado (sin instalar): DragonFF y BlenderGIS en `descargas/addons`, modloader y CLEO 5 en `descargas/herramientas_gta`

## Falta (a mano)

- **GTA San Andreas 1.0 US** (comprado; si es de Steam, downgrade). La Definitive Edition no vale.
- Activar DragonFF en Blender: Edit → Preferences → Add-ons → Install from Disk → `descargas/addons/dragonff-master.zip`
- fastman92 Limit Adjuster, Open Limit Adjuster, MEd, Alci's IMG Editor (no están en GitHub)

## Fuentes de datos

- OpenStreetMap (calles, edificios, parques): extracto de Cataluña de Geofabrik. Los servidores Overpass van saturados
  y arrastran relaciones enormes; solo se usan para consultas pequeñas (`maps.mail.ru`).
- Relieve: teselas Terrarium de AWS (~3,6 m). Mejorable con el MET 2 m del ICGC (icgc.cat).
- Suelo: ortofoto © Institut Cartogràfic i Geològic de Catalunya (ICGC), CC BY 4.0.
- Referencias de fachadas: fotos de Mapillary (CC BY-SA), solo como guía; no van dentro del juego.
- Mapa © colaboradores de OpenStreetMap (ODbL).

## Fases

1. **Prototipo** en el juego: terreno + edificios básicos de una zona (Centre / Pont del Petroli)
2. Mapa completo con colisión, agua (water.dat) y radar
3. Lugares emblemáticos a mano: Pont del Petroli, Tres Xemeneies, Dalt la Vila / Baetulo, Can Ruti, Sant Jeroni de la Murtra, Palau Olímpic, puerto, Montigalà
4. Rutas de coches/peatones, nombres de zonas (Gorg, La Salut, Llefià, Sant Roc, Artigues, Bufalà, Pomar, Montigalà, Centre, Progrés, Canyet…)
5. Detalles: mobiliario, vehículos, peatones, radio
