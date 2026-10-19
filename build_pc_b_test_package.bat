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
if exist "models" robocopy "models" "%OUT_DIR%\models" /E /NFL /NDL /NJH /NJS /NC /NS >nul
if exist "scripts" robocopy "scripts" "%OUT_DIR%\scripts" /E /XD __pycache__ /NFL /NDL /NJH /NJS /NC /NS >nul
if exist "gui" robocopy "gui" "%OUT_DIR%\gui" /E /XD __pycache__ /NFL /NDL /NJH /NJS /NC /NS >nul
for /d /r "%OUT_DIR%" %%D in (__pycache__) do if exist "%%D" rmdir /s /q "%%D"

echo [2/3] Copiando archivos runtime...
for %%F in (
    requirements.txt
    start_api_simple.py
    start_api_server.bat
    restart_api_server.bat
    servidor_instalar_o_actualizar.bat
    servidor_importar_config.bat
    servidor_desactivar.bat
    servidor_estado.bat
    verificar_pc_b.bat
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
echo En la PC nueva:
echo   1) Copiar la carpeta pc_b_test (y el EtiquetadorZPL_config_*.zip adentro)
echo   2) Ejecutar servidor_instalar_o_actualizar.bat
echo.
exit /b 0
