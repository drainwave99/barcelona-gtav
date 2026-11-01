# Abre el juego, hace capturas de pantalla cada pocos segundos y avisa si se cierra (con la direcciÃ³n del fallo).
# Uso: powershell -File herramientas\probar_juego.ps1 [-Segundos 60] [-Teclas "ENTER,ENTER"]
param([int]$Segundos = 60, [string]$Teclas = "")

$juego = "C:\Program Files (x86)\DODI-Repacks\Grand Theft Auto San Andreas"
$capturas = Join-Path $PSScriptRoot "..\docs\pruebas"
New-Item -ItemType Directory -Force $capturas | Out-Null
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

function Captura($nombre) {
    $pantalla = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bmp = New-Object System.Drawing.Bitmap $pantalla.Width, $pantalla.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($pantalla.Location, [System.Drawing.Point]::Empty, $pantalla.Size)
    $pequena = New-Object System.Drawing.Bitmap $bmp, 960, ([int](960 * $pantalla.Height / $pantalla.Width))
    $pequena.Save((Join-Path $capturas "$nombre.png"), [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose(); $pequena.Dispose()
}

Get-Process gta_sa -ErrorAction SilentlyContinue | Stop-Process -Force
# Sin otras ventanas delante (si no, el juego no recibe el foco y se queda en pausa) y sin que se apague la pantalla
(New-Object -ComObject Shell.Application).MinimizeAll()
Add-Type -Name Energia -Namespace W -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);'
[W.Energia]::SetThreadExecutionState([uint32]2147483651) | Out-Null
Start-Sleep -Seconds 1
$inicio = Get-Date
$p = Start-Process -FilePath "$juego\gta_sa.exe" -WorkingDirectory $juego -PassThru
$shell = New-Object -ComObject WScript.Shell
# (no con "$x = if ...": PowerShell desenrolla la cola y deja un string)
$pendientes = [System.Collections.Queue]::new()
if ($Teclas) { $Teclas.Split(",") | ForEach-Object { $pendientes.Enqueue($_) } }

for ($t = 0; $t -lt $Segundos; $t += 5) {
    Start-Sleep -Seconds 5
    if ($p.HasExited) {
        Start-Sleep -Seconds 2
        $ev = Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Application Error'; StartTime=$inicio} -ErrorAction SilentlyContinue | Select-Object -First 1
        $off = if ($ev) { ($ev.Message -split "`n" | Select-String 'Desplazamiento').Line } else { "sin evento de error" }
        "CERRADO a los $t s, codigo $($p.ExitCode). $off"
        exit 1
    }
    Captura ("t{0:D3}" -f $t)
    if ($pendientes.Count -gt 0) {
        $tecla = $pendientes.Dequeue()
        $shell.AppActivate($p.Id) | Out-Null
        Start-Sleep -Milliseconds 300
        $shell.SendKeys("{$tecla}")
        "t=$t s: tecla $tecla"
    }
}
"SIGUE ABIERTO tras $Segundos s"

