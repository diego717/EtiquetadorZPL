@echo off
setlocal EnableExtensions
title Instalar runtime API - PC B

cd /d "%~dp0"

echo ==========================================
echo  EtiquetadorZPL - Instalacion Runtime PC B
echo ==========================================
echo.

set "PY_CMD="
where python >nul 2>&1
if %errorlevel%==0 set "PY_CMD=python"
if not defined PY_CMD (
    where py >nul 2>&1
    if %errorlevel%==0 set "PY_CMD=py -3"
)

if not defined PY_CMD (
    echo [ERROR] No se encontro Python.
    echo Instala Python 3.10+ y vuelve a ejecutar este script.
    echo Sugerido:
    echo   winget install --id Python.Python.3.10 -e
    pause
    exit /b 1
)

echo [1/4] Instalando dependencias Python...
%PY_CMD% -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Fallo actualizando pip.
    pause
    exit /b 1
)

%PY_CMD% -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo instalando requirements.
    pause
    exit /b 1
)

echo [2/4] Instalando Chromium de Playwright...
%PY_CMD% -m playwright install chromium
if errorlevel 1 (
    echo [WARN] No se pudo instalar Playwright Chromium. Se puede continuar con cookies.
)

echo [3/4] Abriendo puerto 8002 en Firewall (si aplica)...
netsh advfirewall firewall add rule name="EtiquetadorZPL API 8002" dir=in action=allow protocol=TCP localport=8002 >nul 2>&1

echo [4/4] Reiniciando API...
call "%~dp0restart_api_server.bat"
if errorlevel 1 (
    echo [ERROR] La API no inicio correctamente.
    pause
    exit /b 1
)

for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /i "IPv4"') do (
    set "IP=%%A"
    goto :ip_done
)

:ip_done
set "IP=%IP: =%"
if not defined IP set "IP=IP_DE_PC_B"

echo.
echo ==========================================
echo [OK] Runtime instalado y API levantada.
echo Dashboard local: http://localhost:8002/web/config.html#administrado
echo Dashboard red:   http://%IP%:8002/web/config.html#administrado
echo Cloud login:     http://%IP%:8002/web/cloud.html
echo ==========================================
echo.
pause
exit /b 0

