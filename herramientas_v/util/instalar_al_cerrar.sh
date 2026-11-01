G="/c/Program Files (x86)/Steam/steamapps/common/Grand Theft Auto V"
M="/c/Users/danny/Desktop/GTA SAN ANDREAS MOD CON ISMA/mod_v"
H="/c/Users/danny/Desktop/GTA SAN ANDREAS MOD CON ISMA/herramientas_v"
ASI="$H/diag/bcn_diag.asi"
DOTNET="$HOME/AppData/Local/Microsoft/dotnet/dotnet.exe"
while true; do
  if ! tasklist | grep -qi gta5.exe; then
    for SRC in "$M"/dlc/dlc.rpf "$M"/dlc_bcn*/dlc.rpf; do
      [ -f "$SRC" ] || continue
      d=$(basename "$(dirname "$SRC")"); P=${d#dlc_}; [ "$d" = dlc ] && P=bcn
      DST="$G/mods/update/x64/dlcpacks/$P/dlc.rpf"
      # que no se esté escribiendo: sin cambios en el último minuto
      if [ "$SRC" -nt "$DST" ] && [ $(( $(date +%s) - $(stat -c %Y "$SRC") )) -gt 60 ]; then
        mkdir -p "$(dirname "$DST")"
        cp "$SRC" "$DST" && echo "$(date +%H:%M) instalado $P $(du -m "$SRC" | cut -f1) MB"
        [ "$P" != bcn ] && "$DOTNET" "$H/cwtool/bin/cwtool.dll" dlclist "$G" "$G/mods/update/update.rpf" "$P"
      fi
    done
    if [ "$ASI" -nt "$G/bcn_diag.asi" ]; then cp "$ASI" "$G/bcn_diag.asi" && echo "$(date +%H:%M) instalado plugin"; fi
  fi
  sleep 60
done
