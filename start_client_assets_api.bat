@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "%APPDATA%\EtiquetadorZPL\client_assets_config.json" (
    echo No existe la configuracion de Client Assets.
    echo Se abrira el configurador para crearla.
    call "%~dp0configure_client_assets_api.bat"
)

set "LOG_DIR=%APPDATA%\EtiquetadorZPL\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
set "LOG_FILE=%LOG_DIR%\client_assets_api_startup.log"
set "CLIENT_ASSETS_API_HOST=127.0.0.1"
set "CLIENT_ASSETS_API_PORT=8003"

if exist "%~dp0EtiquetadorZPL_ClientAssets_API.exe" (
    echo [%date% %time%] Iniciando Client Assets API con EtiquetadorZPL_ClientAssets_API.exe >> "%LOG_FILE%"
    start "" cmd /c "\"%~dp0EtiquetadorZPL_ClientAssets_API.exe\" >> \"%LOG_FILE%\" 2>&1"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        echo [%date% %time%] Iniciando Client Assets API con python api\client_assets_api_server.py >> "%LOG_FILE%"
        start "" cmd /c "python api\client_assets_api_server.py >> \"%LOG_FILE%\" 2>&1"
    ) else (
        where py >nul 2>&1
        if %errorlevel%==0 (
            echo [%date% %time%] Iniciando Client Assets API con py -3 api\client_assets_api_server.py >> "%LOG_FILE%"
            start "" cmd /c "py -3 api\client_assets_api_server.py >> \"%LOG_FILE%\" 2>&1"
        ) else (
            echo ERROR: No se encontro el ejecutable ni Python.
            echo Revisar %LOG_FILE%
            pause
            exit /b 1
        )
    )
)

echo Esperando que la API inicie...
timeout /t 4 /nobreak >nul

start "" "http://127.0.0.1:8003/docs#/client-assets"
