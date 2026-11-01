# Clic en el juego en coordenadas de una captura de 960x540 y captura después.
# Uso: powershell -File herramientas\clic_juego.ps1 -X 480 -Y 216 [-Espera 3] [-Captura manual]
# El juego no recibe las teclas simuladas (DirectInput), pero sí el ratón.
param([int]$X, [int]$Y, [int]$Espera = 3, [string]$Captura = "manual", [switch]$Despertar)
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type -Name Raton -Namespace J -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern void mouse_event(uint f, uint x, uint y, uint d, System.IntPtr e);
[DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr h, int c);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(System.IntPtr h);
'@
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
if ($Despertar) {
    # Si el juego arrancó sin foco se queda congelado: minimizar y restaurar lo despierta
    $h = (Get-Process gta_sa).MainWindowHandle
    [J.Raton]::ShowWindow($h, 6) | Out-Null; Start-Sleep 2
    [J.Raton]::ShowWindow($h, 9) | Out-Null; [J.Raton]::SetForegroundWindow($h) | Out-Null; Start-Sleep 2
}
if ($X -or $Y) {
    [J.Raton]::SetCursorPos([int]($X * $b.Width / 960), [int]($Y * $b.Height / 540)) | Out-Null
    Start-Sleep -Milliseconds 400
    [J.Raton]::mouse_event(2, 0, 0, 0, [IntPtr]::Zero); Start-Sleep -Milliseconds 120
    [J.Raton]::mouse_event(4, 0, 0, 0, [IntPtr]::Zero)
}
Start-Sleep -Seconds $Espera
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
(New-Object System.Drawing.Bitmap $bmp, 960, 540).Save((Join-Path $PSScriptRoot "..\docs\pruebas\$Captura.png"))
"RAM juego: $([math]::Round((Get-Process gta_sa).WorkingSet64/1MB)) MB"
