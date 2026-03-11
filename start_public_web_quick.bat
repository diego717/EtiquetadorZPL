@echo off
setlocal EnableExtensions
title EtiquetadorZPL - Web publica rapida

cd /d "%~dp0"

echo ==========================================
echo  Publicacion web rapida (Cloudflare Tunnel)
echo ==========================================
echo.

set "CLOUDFLARED_CMD="
call :resolve_cloudflared

if not defined CLOUDFLARED_CMD (
    echo [INFO] cloudflared no encontrado. Intentando instalar con winget...
    winget install --id Cloudflare.cloudflared -e
    call :resolve_cloudflared
)

if not defined CLOUDFLARED_CMD (
    echo [ERROR] No se pudo instalar/encontrar cloudflared.
    echo Instalar manualmente: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
    pause
    exit /b 1
)

echo [OK] cloudflared detectado: %CLOUDFLARED_CMD%

echo [1/2] Reiniciando API local...
call "%~dp0restart_api_server.bat"
if errorlevel 1 (
    echo [ERROR] API no disponible en puerto 8002.
    pause
    exit /b 1
)

echo [2/2] Iniciando tunnel temporal...
echo.
echo Cuando aparezca la URL trycloudflare.com, comparti esa URL.
echo URLs utiles:
echo   /web/cloud.html
echo   /web/config.html#administrado
echo.
echo Intento 1: modo compatible (HTTP2 + IPv4)...
"%CLOUDFLARED_CMD%" tunnel --url http://localhost:8002 --protocol http2 --edge-ip-version 4
if %errorlevel%==0 exit /b 0

echo.
echo [WARN] Fallo modo compatible. Reintentando modo estandar...
"%CLOUDFLARED_CMD%" tunnel --url http://localhost:8002
if %errorlevel%==0 exit /b 0

echo.
echo [ERROR] No se pudo abrir el tunnel.
echo Revisa conectividad DNS/firewall de esta red.
pause

exit /b 0

:resolve_cloudflared
set "CLOUDFLARED_CMD="
for /f "delims=" %%I in ('where cloudflared 2^>nul') do (
    set "CLOUDFLARED_CMD=%%I"
    goto :eof
)

cloudflared --version >nul 2>&1
if %errorlevel%==0 (
    set "CLOUDFLARED_CMD=cloudflared"
    goto :eof
)

if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe" (
    set "CLOUDFLARED_CMD=%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe"
    goto :eof
)

if exist "%ProgramFiles%\cloudflared\cloudflared.exe" (
    set "CLOUDFLARED_CMD=%ProgramFiles%\cloudflared\cloudflared.exe"
    goto :eof
)

if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" (
    set "CLOUDFLARED_CMD=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
    goto :eof
)

if exist "%LOCALAPPDATA%\cloudflared\cloudflared.exe" (
    set "CLOUDFLARED_CMD=%LOCALAPPDATA%\cloudflared\cloudflared.exe"
    goto :eof
)

for /f "delims=" %%I in ('dir /b /s "%LOCALAPPDATA%\Microsoft\WinGet\Packages\Cloudflare.cloudflared_*\cloudflared.exe" 2^>nul') do (
    set "CLOUDFLARED_CMD=%%I"
    goto :eof
)

for /f "delims=" %%I in ('dir /b /s "%ProgramFiles%\Cloudflare\*\cloudflared.exe" 2^>nul') do (
    set "CLOUDFLARED_CMD=%%I"
    goto :eof
)
goto :eof
