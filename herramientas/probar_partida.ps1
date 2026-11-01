# Abre el juego, empieza una partida nueva con clics (el juego no recibe teclas simuladas) y hace
# capturas en docs/pruebas/pNNN.png. Informa si el juego se cierra.
# Uso: powershell -File herramientas\probar_partida.ps1 [-Segundos 90]
param([int]$Segundos = 90)
$juego = "C:\Program Files (x86)\DODI-Repacks\Grand Theft Auto San Andreas"
$aqui = $PSScriptRoot
Get-Process gta_sa -ErrorAction SilentlyContinue | Stop-Process -Force
(New-Object -ComObject Shell.Application).MinimizeAll()
Start-Sleep 1
$inicio = Get-Date
$p = Start-Process -FilePath "$juego\gta_sa.exe" -WorkingDirectory $juego -PassThru
Start-Sleep 18
# Menú: Start new game -> New game -> Yes (coordenadas en una captura de 960x540)
foreach ($c in @(@(480, 216), @(235, 192), @(480, 301))) {
    & "$aqui\clic_juego.ps1" -X $c[0] -Y $c[1] -Espera 3 -Captura "menu" | Out-Null
}
for ($t = 0; $t -lt $Segundos; $t += 10) {
    Start-Sleep 10
    if ($p.HasExited) {
        Start-Sleep 2
        $ev = Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Application Error'; StartTime=$inicio} -ErrorAction SilentlyContinue | Select-Object -First 1
        $off = if ($ev) { ($ev.Message -split "`n" | Select-String 'Desplazamiento').Line } else { "sin evento de error" }
        "CERRADO a los $t s de la partida. $off"
        exit 1
    }
    & "$aqui\clic_juego.ps1" -Espera 0 -Captura ("p{0:D3}" -f $t) | Out-Null
}
"SIGUE ABIERTO tras $Segundos s de partida"
