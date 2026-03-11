@echo off
setlocal EnableExtensions
title EtiquetadorZPL - Activar inicio automatico API

cd /d "%~dp0"
set "TASK_NAME=EtiquetadorZPL_API_Autostart"
set "TARGET=%~dp0restart_api_server.bat"

echo ==========================================
echo  Activar inicio automatico API (PC B)
echo ==========================================
echo.

if not exist "%TARGET%" (
    echo [ERROR] No se encontro: %TARGET%
    pause
    exit /b 1
)

schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
schtasks /Create /TN "%TASK_NAME%" /SC ONLOGON /RL HIGHEST /TR "\"%TARGET%\"" /F
if errorlevel 1 (
    echo [ERROR] No se pudo crear la tarea programada.
    echo Ejecuta este script como Administrador.
    pause
    exit /b 1
)

echo.
echo [OK] Tarea creada: %TASK_NAME%
echo Se ejecutara en cada inicio de sesion de Windows.
echo.
pause
exit /b 0

