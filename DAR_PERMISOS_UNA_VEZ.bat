@echo off
rem Da a tu usuario permiso para modificar la carpeta del juego, para que Claude pueda instalar y probar el mod
rem sin pedir administrador cada vez. Solo hace falta ejecutarlo una vez.
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%USERNAME%' -Verb RunAs"
    exit /b
)
set USUARIO=%1
if "%USUARIO%"=="" set USUARIO=%USERNAME%
icacls "C:\Program Files (x86)\DODI-Repacks\Grand Theft Auto San Andreas" /grant "%USUARIO%":(OI)(CI)M /T /Q
echo.
echo Listo: %USUARIO% ya puede modificar la carpeta del juego.
pause
