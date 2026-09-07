@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel%==0 (
    python build_client_assets_api.py
    goto :end
)

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 build_client_assets_api.py
    goto :end
)

echo ERROR: No se encontro Python para construir el paquete.

:end
pause
