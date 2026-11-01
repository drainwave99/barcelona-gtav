@echo off
rem Instala el mapa de Badalona en el juego (pide permisos de administrador porque el juego está en Program Files)
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%~dp0herramientas\instalar_en_juego.py"
pause
