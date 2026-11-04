# Estado del proyecto (2026-11-04, aparcado)

El proyecto se deja aquí. Este archivo explica cómo queda, para quien lo retome. Cómo montarlo desde cero está en
`CLAUDE.md` y `README.md`. Este repositorio solo guarda código: los datos (LiDAR, ortofoto, Catastro, OSM) y el mapa
generado hay que volver a bajarlos y generarlos (unas 10-15 h de descargas y 4-6 h de generación con 16 GB de RAM).

## Lo que funciona

- 121 hojas de 1 km² (Barcelona, Badalona, Sant Adrià y Santa Coloma) generadas con el LiDAR, la ortofoto y el
  Catastro, y empaquetadas en 13 DLC (`bcn`, `bcn2` ... `bcn13`). `comprobar_v.py` da 0 fallos en todas.
- Terreno, calles con aceras y marcas viales, edificios con fachadas, puentes y viaductos, túneles, playa y mar.
- Metro: bocas en 3D con escalera y vestíbulo (`bocas_v.py`), entrada con E (`diag/bcn_metro.c`).
- Mobiliario de OSM: árboles (en la ciudad, 3 de cada 40), farolas, semáforos, señales de STOP y ceda el paso,
  bancos, papeleras, paradas de bus...
- Radar y mapa del menú de pausa propios, barrios con nombre (`radar_v.py`, `diag/bcn_radar.c`).
- Monumentos a medida (`monumentos_v.py`): Tres Xemeneies, bola del Màgic, Pont del Petroli y una pasarela.

## Lo que queda a medias

- **Viaductos en Sant Adrià y Badalona** (lo último en que se trabajaba). Donde un tablero llega a la calle o pasa
  pegado a ella había escalones, huecos y tableros fundidos con el terreno (marcas F9 de las capturas). El último
  commit arregla la causa en el código: los extremos acaban a la altura del asfalto con una transición de 12 m, y
  donde el tablero va a menos de 2,5 m del suelo se quita la calle a nivel y se hunde el terreno
  (`puentes_v.plantas_bajas`). Una medida sobre cinco hojas (434585, 434586, 435586, 435587, 436588) da 0 saltos en
  los extremos (antes había 34 solo en dos de ellas). Se generaron 434586 y 435585 con ese código, pero **no se llegó
  a empaquetarlas ni a verlas en el juego**. Siguiente paso: empaquetar esas dos (`python empaquetar_v.py 434586
  435585`), mirar el nudo de la Ronda Litoral y el Pont dels Passadors, y si está bien, regenerar las 93 hojas con
  puentes.
- **Farolas**: el brazo de `prop_streetlight_*` sale hacia −Y (medido con `bcn_diag`). El código ya las gira 180°,
  pero el mapa instalado es de antes de ese cambio.
- **Ideas no empezadas**: Sagrada Família, Torre Glòries y Colón en `monumentos_v.py` (no hay modelos libres en la
  red: se harían con el LiDAR, como las Xemeneies), vallas y barandillas de OSM, más señales de tráfico, rutas de
  bus y tranvía (Trambesòs y Trambaix).

## Cosas que conviene saber

- No lances más de un `prototipo.py` a la vez con 16 GB de RAM (con dos y el juego abierto se queda sin memoria).
  Una cola con `xargs -P` no se para cortando el proceso de arriba: hay que matar el `xargs` y sus hijos.
- `datos_v/props_validos.txt` lo escribe `bcn_diag` (líneas PROP del registro). Con `bcn_modelos.txt` en la carpeta
  del juego, `bcn_diag` apunta además la caja de cada modelo (`CAJA ...`): así se sabe hacia dónde mira un prop.
- `bcn_auto.txt` + `bcn_vistas.txt` en la carpeta del juego: al entrar en el modo historia, `bcn_diag` hace una
  captura por vista y cierra el juego. Desde el menú principal no arranca: hay que entrar en el modo historia.
