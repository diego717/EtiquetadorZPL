@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "LOG_DIR=%APPDATA%\EtiquetadorZPL\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
set "LOG_FILE=%LOG_DIR%\api_startup.log"

set "ETIQUETADOR_API_HOST=0.0.0.0"

rem Preferir ejecutable dedicado si existe (escenario sin Python)
if exist "%~dp0EtiquetadorZPL_API.exe" (
    echo [%date% %time%] Iniciando API con EtiquetadorZPL_API.exe >> "%LOG_FILE%"
    "%~dp0EtiquetadorZPL_API.exe" >> "%LOG_FILE%" 2>&1
    exit /b %errorlevel%
)

where python >nul 2>&1
if %errorlevel%==0 (
    echo [%date% %time%] Iniciando API con python start_api_simple.py >> "%LOG_FILE%"
    python start_api_simple.py >> "%LOG_FILE%" 2>&1
    exit /b %errorlevel%
)

where py >nul 2>&1
if %errorlevel%==0 (
    echo [%date% %time%] Iniciando API con py -3 start_api_simple.py >> "%LOG_FILE%"
    py -3 start_api_simple.py >> "%LOG_FILE%" 2>&1
    exit /b %errorlevel%
)

echo [%date% %time%] ERROR: No se encontro Python ni EtiquetadorZPL_API.exe >> "%LOG_FILE%"
echo ERROR: No se encontro Python instalado. Instala Python 3.10+ o usa instalador completo.
pause
exit /b 1
