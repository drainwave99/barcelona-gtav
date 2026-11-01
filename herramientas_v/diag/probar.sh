#!/bin/sh
# Abre GTA V (Steam -> Legacy -> modo individual) con bcn_auto.txt puesto: el plugin hace sus pruebas, saca
# capturas de Steam y cierra el juego. Escribe al final AUTO FIN, CERRADO (se cayó) o TIEMPO (sigue abierto).
# Las coordenadas de los clics son las de una pantalla de 1920x1080.
G="/c/Program Files (x86)/Steam/steamapps/common/Grand Theft Auto V"
AQUI="$(cd "$(dirname "$0")" && pwd)"
pantalla() { powershell -NoProfile -ExecutionPolicy Bypass -File "$AQUI/pantalla.ps1" "$@"; }

: > "$G/bcn_diag.log"
echo auto > "$G/bcn_auto.txt"
cmd //c start "" "steam://rungameid/271590"
sleep 25
pantalla clic 1244 720          # Steam: «Jugar» con «Grand Theft Auto V Legacy» marcado
for i in $(seq 1 40); do        # espera a que arranque GTA5.exe
    sleep 5
    tasklist | grep -qi gta5.exe && break
done
sleep 60
pantalla clic 1750 1027         # página de inicio: «MODO INDIVIDUAL»
for i in $(seq 1 120); do
    sleep 5
    if grep -q "AUTO FIN" "$G/bcn_diag.log"; then echo "AUTO FIN a los $((i * 5)) s"; break; fi
    if ! tasklist | grep -qi gta5.exe; then echo "CERRADO a los $((i * 5)) s"; break; fi
done
[ "$i" = 120 ] && echo TIEMPO
sleep 5
cat "$G/bcn_diag.log"
