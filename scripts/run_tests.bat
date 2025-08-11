@echo off
echo === Tests EtiquetadorZPL ===

echo.
echo 1. Tests del Sistema
echo 2. Tests de Rendimiento  
echo 3. Ambos
echo.

set /p choice="Selecciona opcion (1-3): "

if "%choice%"=="1" (
    echo.
    echo === TESTS DEL SISTEMA ===
    python test_system.py
) else if "%choice%"=="2" (
    echo.
    echo === TESTS DE RENDIMIENTO ===
    python test_performance.py
) else if "%choice%"=="3" (
    echo.
    echo === TESTS DEL SISTEMA ===
    python test_system.py
    echo.
    echo === TESTS DE RENDIMIENTO ===
    python test_performance.py
) else (
    echo Opcion invalida
)

echo.
pause