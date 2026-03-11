@echo off
setlocal EnableExtensions
title EtiquetadorZPL - Armar paquete PC B (prueba)

cd /d "%~dp0"
set "OUT_DIR=%~dp0release\pc_b_test"

echo ==========================================
echo  Armando paquete de prueba para PC B
echo ==========================================
echo Destino: %OUT_DIR%
echo.

if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%"
mkdir "%OUT_DIR%" >nul 2>&1

echo [1/3] Copiando carpetas...
if exist "api" robocopy "api" "%OUT_DIR%\api" /E /NFL /NDL /NJH /NJS /NC /NS >nul
if exist "src" robocopy "src" "%OUT_DIR%\src" /E /NFL /NDL /NJH /NJS /NC /NS >nul
if exist "web" robocopy "web" "%OUT_DIR%\web" /E /NFL /NDL /NJH /NJS /NC /NS >nul
if exist "config" robocopy "config" "%OUT_DIR%\config" /E /NFL /NDL /NJH /NJS /NC /NS >nul
if exist "poppler" robocopy "poppler" "%OUT_DIR%\poppler" /E /NFL /NDL /NJH /NJS /NC /NS >nul
if exist "docs" robocopy "docs" "%OUT_DIR%\docs" /E /NFL /NDL /NJH /NJS /NC /NS >nul

echo [2/3] Copiando archivos runtime...
for %%F in (
    requirements.txt
    start_api_simple.py
    start_api_server.bat
    restart_api_server.bat
    install_runtime_pc_b.bat
    enable_autostart_pc_b.bat
    start_public_web_quick.bat
    launcher_modern.py
    config.py
    poppler_manager.py
    get_writable_path.py
) do (
    if exist "%%F" copy /Y "%%F" "%OUT_DIR%\%%F" >nul
)

echo [3/3] Listo.
echo.
echo [OK] Paquete de prueba creado.
echo Carpeta: %OUT_DIR%
echo.
echo En PC B:
echo   1) Copiar carpeta pc_b_test completa
echo   2) Ejecutar install_runtime_pc_b.bat
echo   3) (Opcional) Ejecutar start_public_web_quick.bat
echo.
exit /b 0
