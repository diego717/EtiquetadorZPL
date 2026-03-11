@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Reiniciar API EtiquetadorZPL

set "PORT=8002"
set "PROJECT_DIR=%~dp0"
set "START_BAT=%PROJECT_DIR%start_api_server.bat"

echo ==========================================
echo  Reinicio API EtiquetadorZPL (puerto %PORT%)
echo ==========================================
echo.

if not exist "%START_BAT%" (
    echo [ERROR] No se encontro: %START_BAT%
    pause
    exit /b 1
)

echo [1/4] Buscando procesos en puerto %PORT%...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    set "PID=%%P"
    if not "!PID!"=="" (
        echo    - Cerrando PID !PID!...
        taskkill /PID !PID! /F >nul 2>&1
    )
)

echo [2/4] Esperando liberacion del puerto...
timeout /t 2 /nobreak >nul

echo [3/4] Iniciando API...
start "" /MIN cmd /c ""%START_BAT%""

echo [4/4] Verificando estado /api/status...
set "OK=0"
for /L %%I in (1,1,12) do (
    powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%PORT%/api/status' -TimeoutSec 2; if($r.StatusCode -eq 200){ exit 0 } else { exit 1 } } catch { exit 1 }"
    if !errorlevel! equ 0 (
        set "OK=1"
        goto :done
    )
    timeout /t 1 /nobreak >nul
)

:done
if "%OK%"=="1" (
    echo.
    echo [OK] API reiniciada correctamente.
    echo      Dashboard: http://localhost:%PORT%/web/config.html#administrado
    exit /b 0
) else (
    echo.
    echo [ERROR] La API no respondio luego del reinicio.
    echo         Revisa logs en %%APPDATA%%\EtiquetadorZPL\logs\
    pause
    exit /b 1
)

