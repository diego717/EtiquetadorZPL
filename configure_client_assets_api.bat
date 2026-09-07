@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "TARGET_DIR=%APPDATA%\EtiquetadorZPL"
set "TARGET_FILE=%TARGET_DIR%\client_assets_config.json"
set "SOURCE_FILE=%~dp0config\client_assets_config.example.json"

if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%" >nul 2>&1

if not exist "%TARGET_FILE%" (
    copy /Y "%SOURCE_FILE%" "%TARGET_FILE%" >nul
    echo Se creo la configuracion inicial en:
    echo %TARGET_FILE%
) else (
    echo La configuracion ya existe en:
    echo %TARGET_FILE%
)

echo.
echo Edita "root_folder" con la carpeta principal de clientes en esta PC.
echo Si quieres usar preview de CDR, esta PC debe tener CorelDRAW instalado.
echo.
notepad "%TARGET_FILE%"
