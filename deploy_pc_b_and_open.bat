@echo off
setlocal EnableExtensions

title EtiquetadorZPL - Deploy PC B + Copia automatica
cd /d "%~dp0"

set "RELEASE_DIR=%~dp0release"
set "ZIP_FILE=%RELEASE_DIR%\pc_b_test.zip"
set "AUTO_DEST="
set "DEST_INPUT=%~1"

echo ==========================================
echo  EtiquetadorZPL - Deploy + Copia automatica
echo ==========================================
echo.

if not exist "%~dp0deploy_pc_b.bat" goto :ERR_NO_DEPLOY

echo [1/4] Ejecutando deploy base...
call "%~dp0deploy_pc_b.bat"
if errorlevel 1 goto :ERR_DEPLOY

if not exist "%ZIP_FILE%" goto :ERR_NO_ZIP

echo.
echo [2/4] Resolviendo destino de copia...

if not "%DEST_INPUT%"=="" goto :DEST_FROM_PARAM

goto :DEST_AUTODETECT

:DEST_FROM_PARAM
set "AUTO_DEST=%DEST_INPUT%"
echo Destino recibido por parametro: %AUTO_DEST%
goto :DEST_READY

:DEST_AUTODETECT
set "TMP_DEST_FILE=%TEMP%\etq_usb_dest.txt"
if exist "%TMP_DEST_FILE%" del /f /q "%TMP_DEST_FILE%" >nul 2>&1

powershell -NoProfile -Command "$d=''; foreach($x in Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=2'){ $d=$x.DeviceID; break }; if($d){ Set-Content -LiteralPath '%TMP_DEST_FILE%' -Encoding ascii -Value $d }"

if exist "%TMP_DEST_FILE%" set /p AUTO_DEST=<"%TMP_DEST_FILE%"
if exist "%TMP_DEST_FILE%" del /f /q "%TMP_DEST_FILE%" >nul 2>&1

if defined AUTO_DEST goto :DEST_AUTO_FOUND

echo [WARN] No se detecto pendrive.
goto :NO_DEST

:DEST_AUTO_FOUND
echo Destino automatico (pendrive): %AUTO_DEST%

:DEST_READY
echo.
echo [3/4] Copiando ZIP al destino...

set "DEST_FILE="
echo %AUTO_DEST% | findstr /i /r "\.zip$" >nul
if not errorlevel 1 set "DEST_FILE=%AUTO_DEST%"
if errorlevel 1 set "DEST_FILE=%AUTO_DEST%\pc_b_test.zip"

powershell -NoProfile -Command "$dst = '%DEST_FILE%'; $dir = Split-Path -Parent $dst; if(!(Test-Path $dir)){ New-Item -ItemType Directory -Path $dir -Force | Out-Null }; Copy-Item -LiteralPath '%ZIP_FILE%' -Destination $dst -Force"
if errorlevel 1 goto :ERR_COPY

echo [OK] ZIP copiado a: %DEST_FILE%
echo.
echo [4/4] Abriendo destino...
for %%I in ("%DEST_FILE%") do start "" "%%~dpI"

echo.
echo Listo. En PC B ejecutar:
echo   1) install_runtime_pc_b.bat
echo   2) enable_autostart_pc_b.bat  (opcional, recomendado)
exit /b 0

:NO_DEST
echo.
echo [3/4] Sin destino automatico.
echo Puedes copiar manualmente:
echo   %ZIP_FILE%
echo.
echo [4/4] Abriendo carpeta release...
start "" "%RELEASE_DIR%"
exit /b 0

:ERR_NO_DEPLOY
echo [ERROR] No se encontro deploy_pc_b.bat
exit /b 1

:ERR_DEPLOY
echo [ERROR] Fallo el deploy base.
exit /b 1

:ERR_NO_ZIP
echo [ERROR] No se genero el ZIP: %ZIP_FILE%
exit /b 1

:ERR_COPY
echo [ERROR] No se pudo copiar a: %DEST_FILE%
echo Copia manual sugerida:
echo   %ZIP_FILE%
exit /b 1
