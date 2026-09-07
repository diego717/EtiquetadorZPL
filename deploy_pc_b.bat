@echo off
setlocal EnableExtensions
title EtiquetadorZPL - Deploy PC B (1-click)

cd /d "%~dp0"

set "RELEASE_DIR=%~dp0release"
set "OUT_DIR=%RELEASE_DIR%\pc_b_test"
set "ZIP_FILE=%RELEASE_DIR%\pc_b_test.zip"

echo ==========================================
echo  EtiquetadorZPL - Deploy PC B (1-click)
echo ==========================================
echo.

if not exist "%~dp0build_pc_b_test_package.bat" (
    echo [ERROR] No se encontro build_pc_b_test_package.bat
    exit /b 1
)

echo [1/3] Armando carpeta de runtime para PC B...
call "%~dp0build_pc_b_test_package.bat"
if errorlevel 1 (
    echo [ERROR] Fallo al crear el paquete base.
    exit /b 1
)

echo.
echo [2/3] Generando ZIP para transferencia...
if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%" >nul 2>&1
if exist "%ZIP_FILE%" del /f /q "%ZIP_FILE%" >nul 2>&1

powershell -NoProfile -Command ^
    "if (!(Test-Path '%OUT_DIR%')) { exit 1 }; Compress-Archive -Path '%OUT_DIR%\\*' -DestinationPath '%ZIP_FILE%' -Force"

if errorlevel 1 (
    echo [WARN] No se pudo generar ZIP automaticamente.
    echo        Usa la carpeta: %OUT_DIR%
) else (
    echo [OK] ZIP generado: %ZIP_FILE%
)

echo.
echo [3/3] Listo.
echo.
echo Archivos para mover a PC B:
echo   - Carpeta: %OUT_DIR%
echo   - ZIP:     %ZIP_FILE%
echo.
echo En PC B ejecutar:
echo   1) install_runtime_pc_b.bat
echo   2) enable_autostart_pc_b.bat  (opcional, recomendado)
echo.

start "" "%RELEASE_DIR%"
exit /b 0
