# Barcelona en GTA V — guía para Claude

Lee también `README.md`. Responde en español: el equipo habla español.

## Qué es

Barcelona, Badalona, Sant Adrià y Santa Coloma a escala 1:1 en **GTA V Legacy (Steam), solo modo historia**.
Todo se genera con datos abiertos (LiDAR y ortofoto del ICGC, Catastro, OpenStreetMap) mediante los scripts de
`herramientas_v/`. El repositorio lleva solo código: los datos (`datos/`, `datos_v/`), lo generado (`mod_v/`) y las
herramientas descargadas (`descargas/`) no se suben; cada uno los regenera en su ordenador.

## Normas (no negociables)

- **Nunca** subas a git ni publiques archivos de Rockstar (rpf, ytd, ydr del juego, `copia_juego/`,
  `mod_v/update_antes_de_vaciar.rpf`) ni los paquetes generados. Solo código y textos (ver `.gitignore`).
- **Nunca** subas ni muestres tokens: `datos/mapillary_token.txt` es personal de cada uno.
- Solo modo historia. Nada para GTA Online, nada que salte protecciones, nada de ejecutables crackeados.
- Si un servicio de datos responde 403/401 o limita peticiones, no lo esquives: para y avisa.
- El juego se abre con `steam://rungameid/271590`, nunca ejecutando `PlayGTAV.exe` directamente.
- Antes de empaquetar/instalar, el juego tiene que estar cerrado. No cierres una partida que no hayas abierto tú.
- Las descargas grandes y las colas de generación van en segundo plano y por hojas; no edites el generador mientras
  una cola está generando, o vuelve a generar después las hojas afectadas.
- Commits pequeños, en español, explicando el porqué. Cada uno trabaja en su rama y abre pull request.

## Conceptos

- **Coordenadas del juego** = UTM ETRS89 31N (EPSG:25831) − (430500, 4585000), sin giro. Alturas = LiDAR (m s.n.m.).
- **Hoja** = 1 × 1 km con nombre `EEENNN` (km UTM: 431583 = E 431 km, N 4583 km). La lista sale de
  `config_v.hojas()`; las que se quitaron a propósito están en `config_v.HOJAS_FUERA`.
- **Casilla** = trozo de una hoja dentro de su generación.
- La carpeta del juego se toma de la variable de entorno `GTA_V_DIR` (por defecto la de Steam en `C:\Program Files (x86)`).

## Montarlo desde cero (Windows)

1. **Programas**: Python 3.12 (`pip install -r requirements.txt`), .NET 8 SDK, y en `descargas/gtav/`:
   - el código de **CodeWalker** en `descargas/gtav/codewalker_src/CodeWalker-master/` (lo usa `herramientas_v/cwtool`);
   - **zig** (compilador de C) para los plugins `.asi`;
   - el SDK de **ScriptHookV** en `descargas/gtav/shv_sdk/`.
   Compila cwtool: `cd herramientas_v/cwtool && dotnet build -c Release -o bin`.
2. **En el juego**: ScriptHookV + un cargador de ASI (`dinput8.dll`) y la carpeta `mods/` (OpenIV o equivalente).
   Los descarga cada uno de su web oficial.
3. **Datos** (en este orden; todos se pueden cortar y volver a lanzar):
   - OpenStreetMap: `datos/osm/cataluna-latest.osm.pbf` de Geofabrik; luego `python osm_v.py E0 E1 N0 N1`
     (y `costa_v.py`, `rios_v.py`, `tuneles_v.py`).
   - Catastro: los GML INSPIRE de edificios de cada municipio (08900, 08015, 08193, 08245…) descomprimidos en
     `datos_v/catastro/A.ES.SDGC.BU.<muni>/`; luego `python catastro.py`.
   - LiDAR del ICGC por hojas: `python lidar.py zona E0 E1 N0 N1` (cientos de MB por hoja; tarda horas).
   - Ortofoto del ICGC: `python orto.py E0 E1 N0 N1`.
   - Opcional: fotos de fachada (`fachadas_catastro.py`, despacio a propósito) y `color_fachadas.py`.
   Si un script se queja de que falta un archivo de `datos_v/`, busca con grep qué script lo escribe.
4. **Generar y probar**: `python prototipo.py 431583` genera una hoja; `python empaquetar_v.py --cambiadas`
   empaqueta e instala las hojas cambiadas; `python radar_v.py` (radar, plano y mapa del menú de pausa);
   `python quitar_ls.py` quita Los Santos (deshacer: `--deshacer`); `fondo_v.py`, `metro_v.py`.
5. **Plugins** (`herramientas_v/diag/*.c`): `zig cc -target x86_64-windows-gnu -shared -O2 -Wall -o X.asi X.c -luser32`
   y copia el `.asi` a la carpeta del juego. bcn_radar (minimapa y mapa con M), bcn_metro (bocas, E para entrar),
   bcn_sandbox, bcn_diag (F9 guarda la posición en `bcn_marcas.txt`).

Para probar un cambio no hace falta el mapa entero: genera y empaqueta solo las hojas afectadas.

## Cosas aprendidas (para no repetir errores)

- Los scripts de ScriptHookV no se ejecutan con el menú de pausa abierto: no se puede dibujar encima.
- El mapa del menú de pausa son texturas `minimap_sea_<fila>_<col>` dentro de
  `update.rpf/x64/data/cdimages/scaleform_generic.rpf` + `minimap.ymt` (2×3 teselas; más teselas cuelga el menú).
- El fundido a negro del juego (`DO_SCREEN_FADE_OUT`) tapa también lo que dibujan los scripts.
- Si GTA se queda colgado sin ventana, `taskkill` puede fallar: `wmic process where processid=N call terminate`.
