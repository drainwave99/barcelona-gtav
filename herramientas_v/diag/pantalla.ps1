# Utilidades para probar el mapa sin nadie delante:
#   pantalla.ps1 captura <archivo.png>     guarda lo que se ve en la pantalla principal
#   pantalla.ps1 clic <x> <y>              mueve el ratón y hace clic izquierdo
#   pantalla.ps1 tecla <codigo_vk>         pulsa y suelta una tecla (códigos virtuales de Windows)
param([string]$orden, [string]$a, [string]$b)
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Entrada {
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint x, uint y, uint d, IntPtr e);
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint f, IntPtr e);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[Entrada]::SetProcessDPIAware() | Out-Null
switch ($orden) {
    "captura" {
        $r = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bmp = New-Object System.Drawing.Bitmap $r.Width, $r.Height
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($r.Location, [System.Drawing.Point]::Empty, $r.Size)
        $bmp.Save($a, [System.Drawing.Imaging.ImageFormat]::Png)
        "$($r.Width)x$($r.Height)"
    }
    "clic" {
        [Entrada]::SetCursorPos([int]$a, [int]$b) | Out-Null
        Start-Sleep -Milliseconds 150
        [Entrada]::mouse_event(2, 0, 0, 0, [IntPtr]::Zero)
        Start-Sleep -Milliseconds 80
        [Entrada]::mouse_event(4, 0, 0, 0, [IntPtr]::Zero)
    }
    "tecla" {
        [Entrada]::keybd_event([byte][int]$a, 0, 0, [IntPtr]::Zero)
        Start-Sleep -Milliseconds 80
        [Entrada]::keybd_event([byte][int]$a, 0, 2, [IntPtr]::Zero)
    }
}
