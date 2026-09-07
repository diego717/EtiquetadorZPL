@echo off
setlocal EnableExtensions EnableDelayedExpansion
title EtiquetadorZPL - Verificacion PC B

cd /d "%~dp0"

set "ORDER_PRINTER_IP=192.168.49.225"
set "ORDER_PRINTER_PORT=9100"
set "APP_CFG_DIR=%APPDATA%\EtiquetadorZPL"
set "ORDER_PRINTER="
set "LABEL_PRINTER="
set "PY_EXE="
set "PY_ARGS="
set /a CHECK_OK=0
set /a CHECK_WARN=0
set /a CHECK_FAIL=0

echo ==========================================
echo  EtiquetadorZPL - Verificacion rapida PC B
echo ==========================================
echo Carpeta actual: %CD%
echo Config esperada: %APP_CFG_DIR%
echo Impresora orden IP esperada: %ORDER_PRINTER_IP%
echo.

echo ------------------------------------------
echo [Python instalado (3.10+)]
call :check_py_version

echo ------------------------------------------
echo [Dependencias Python clave]
call :check_py_deps

echo ------------------------------------------
echo [Servicio Spooler de Windows]
call :check_spooler

echo ------------------------------------------
echo [API local en puerto 8002]
call :check_api

echo ------------------------------------------
echo [Regla Firewall puerto 8002]
call :check_firewall

echo ------------------------------------------
echo [Conectividad impresora orden (ping)]
call :check_order_ping

echo ------------------------------------------
echo [Conectividad impresora orden (TCP 9100)]
call :check_order_tcp

echo ------------------------------------------
echo [Configuracion APPDATA presente]
call :check_config_files

echo ------------------------------------------
echo [Impresoras configuradas existen en Windows]
call :check_configured_printers

echo ------------------------------------------
echo [Tarea inicio automatico (opcional)]
call :check_autostart_task

echo.
echo ==========================================
echo  Resumen
echo ==========================================
echo   OK    : %CHECK_OK%
echo   WARN  : %CHECK_WARN%
echo   FAIL  : %CHECK_FAIL%
echo ==========================================

if %CHECK_FAIL% GTR 0 (
    echo.
    echo [RESULTADO] Hay validaciones criticas fallidas.
    echo Sugerido:
    echo   1^) Ejecutar install_runtime_pc_b.bat
    echo   2^) Ejecutar restart_api_server.bat
    echo   3^) Revisar config en web/config.html#administrado
    echo.
    pause
    exit /b 1
)

echo.
echo [RESULTADO] Verificacion finalizada sin fallos criticos.
echo.
pause
exit /b 0

:ok
set /a CHECK_OK+=1
echo   [OK] %~1
exit /b 0

:warn
set /a CHECK_WARN+=1
echo   [WARN] %~1
exit /b 0

:fail
set /a CHECK_FAIL+=1
echo   [FAIL] %~1
exit /b 0

:check_py_version
where python >nul 2>&1
if %errorlevel%==0 (
    set "PY_EXE=python"
    set "PY_ARGS="
) else (
    where py >nul 2>&1
    if %errorlevel%==0 (
        set "PY_EXE=py"
        set "PY_ARGS=-3"
    )
)

if not defined PY_EXE (
    call :fail "No se encontro Python. Instala Python 3.10+."
    exit /b 0
)

set "PY_VER="
for /f "tokens=2 delims= " %%V in ('"%PY_EXE%" %PY_ARGS% --version 2^>^&1') do (
    set "PY_VER=%%V"
)

if not defined PY_VER (
    call :fail "No se pudo leer la version de Python."
    exit /b 0
)

powershell -NoProfile -Command "try { if([version]'%PY_VER%' -ge [version]'3.10'){ exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    call :fail "Version detectada %PY_VER%. Se requiere Python 3.10 o superior."
) else (
    call :ok "Python %PY_VER% detectado."
)
exit /b 0

:check_py_deps
if not defined PY_EXE (
    call :fail "No se puede validar dependencias porque Python no esta disponible."
    exit /b 0
)

set "MISSING_MODS="
call :check_py_module fastapi
call :check_py_module uvicorn
call :check_py_module requests
call :check_py_module playwright
call :check_py_module win32print

if defined MISSING_MODS (
    call :fail "Faltan modulos: %MISSING_MODS%"
    exit /b 0
)

call :ok "Dependencias clave presentes (fastapi, uvicorn, requests, playwright, win32print)."
exit /b 0

:check_py_module
set "MOD_NAME=%~1"
"%PY_EXE%" %PY_ARGS% -c "import %MOD_NAME%" >nul 2>&1
if errorlevel 1 (
    if defined MISSING_MODS (
        set "MISSING_MODS=%MISSING_MODS%,%MOD_NAME%"
    ) else (
        set "MISSING_MODS=%MOD_NAME%"
    )
)
exit /b 0

:check_spooler
sc query Spooler | findstr /I "RUNNING" >nul 2>&1
if errorlevel 1 (
    call :fail "El servicio Spooler no esta en RUNNING."
) else (
    call :ok "Servicio Spooler en ejecucion."
)
exit /b 0

:check_api
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8002/api/status' -TimeoutSec 3; if($r.StatusCode -eq 200){ exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    call :fail "La API no responde en http://localhost:8002/api/status"
) else (
    call :ok "API responde correctamente en puerto 8002."
)
exit /b 0

:check_firewall
set "TMP_FW=%TEMP%\etiquetador_fw_%RANDOM%.txt"
netsh advfirewall firewall show rule name="EtiquetadorZPL API 8002" >"%TMP_FW%" 2>&1
findstr /I /C:"EtiquetadorZPL API 8002" "%TMP_FW%" >nul 2>&1
if errorlevel 1 (
    call :warn "No se encontro regla de firewall 'EtiquetadorZPL API 8002'."
) else (
    call :ok "Regla de firewall para puerto 8002 encontrada."
)
if exist "%TMP_FW%" del /f /q "%TMP_FW%" >nul 2>&1
exit /b 0

:check_order_ping
ping -n 1 -w 1500 %ORDER_PRINTER_IP% >nul 2>&1
if errorlevel 1 (
    call :warn "No responde ping a %ORDER_PRINTER_IP% (puede estar bloqueado por firewall)."
    exit /b 0
)
call :ok "Ping OK a %ORDER_PRINTER_IP%."
exit /b 0

:check_order_tcp
powershell -NoProfile -Command "try { $ok = Test-NetConnection -ComputerName '%ORDER_PRINTER_IP%' -Port %ORDER_PRINTER_PORT% -InformationLevel Quiet -WarningAction SilentlyContinue; if($ok){ exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    call :fail "Sin conexion TCP a %ORDER_PRINTER_IP%:%ORDER_PRINTER_PORT%."
) else (
    call :ok "Conexion TCP disponible a %ORDER_PRINTER_IP%:%ORDER_PRINTER_PORT%."
)
exit /b 0

:check_config_files
if not exist "%APP_CFG_DIR%" (
    call :fail "No existe carpeta de configuracion: %APP_CFG_DIR%"
    exit /b 0
)

set "HAS_CONFIG=0"
if exist "%APP_CFG_DIR%\config.ini" set "HAS_CONFIG=1"
if exist "%APP_CFG_DIR%\odoo_config.json" set "HAS_CONFIG=1"
if exist "%APP_CFG_DIR%\administrado_config.json" set "HAS_CONFIG=1"

if "%HAS_CONFIG%"=="0" (
    call :fail "No se encontraron archivos de configuracion esperados en APPDATA."
    exit /b 0
)

if exist "%APP_CFG_DIR%\config.ini" (
    call :ok "Config detectada: %APP_CFG_DIR%\config.ini"
) else (
    call :warn "No existe %APP_CFG_DIR%\config.ini"
)

if exist "%APP_CFG_DIR%\odoo_config.json" (
    call :ok "Config detectada: %APP_CFG_DIR%\odoo_config.json"
) else (
    call :warn "No existe %APP_CFG_DIR%\odoo_config.json"
)

if exist "%APP_CFG_DIR%\administrado_config.json" (
    call :ok "Config detectada: %APP_CFG_DIR%\administrado_config.json"
) else (
    call :warn "No existe %APP_CFG_DIR%\administrado_config.json"
)
exit /b 0

:check_configured_printers
set "ORDER_PRINTER="
set "LABEL_PRINTER="

for /f "usebackq tokens=1,* delims==" %%A in (`powershell -NoProfile -Command ^
    "$cfg = Join-Path $env:APPDATA 'EtiquetadorZPL';" ^
    "$order=''; $label='';" ^
    "$odooPath = Join-Path $cfg 'odoo_config.json';" ^
    "if (Test-Path $odooPath) { try { $od = Get-Content $odooPath -Raw | ConvertFrom-Json; $order = [string]$od.default_order_printer; $label = [string]$od.default_label_printer } catch {} };" ^
    "if (-not $label) { $admPath = Join-Path $cfg 'administrado_config.json'; if (Test-Path $admPath) { try { $ad = Get-Content $admPath -Raw | ConvertFrom-Json; $label = [string]$ad.default_printer } catch {} } };" ^
    "if (-not $label) { $iniPath = Join-Path $cfg 'config.ini'; if (Test-Path $iniPath) { $line = Get-Content $iniPath | Where-Object { $_ -match '^\s*impresora\s*=' } | Select-Object -First 1; if ($line) { $label = (($line -split '=',2)[1]).Trim() } } };" ^
    "Write-Output ('ORDER=' + ($order -as [string]));" ^
    "Write-Output ('LABEL=' + ($label -as [string]));"` ) do (
    if /I "%%A"=="ORDER" set "ORDER_PRINTER=%%B"
    if /I "%%A"=="LABEL" set "LABEL_PRINTER=%%B"
)

if not defined ORDER_PRINTER (
    call :warn "No hay impresora de orden configurada en odoo_config.json."
) else (
    powershell -NoProfile -Command "$n=$env:ORDER_PRINTER; $list=Get-Printer -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name; if($list -contains $n){ exit 0 } else { exit 1 }" >nul 2>&1
    if errorlevel 1 (
        call :fail "Impresora de orden no encontrada en Windows: %ORDER_PRINTER%"
    ) else (
        call :ok "Impresora de orden detectada: %ORDER_PRINTER%"
    )
)

if not defined LABEL_PRINTER (
    call :warn "No hay impresora de etiqueta configurada (odoo/administrado/config.ini)."
    exit /b 0
)

powershell -NoProfile -Command "$n=$env:LABEL_PRINTER; $list=Get-Printer -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name; if($list -contains $n){ exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 (
    call :fail "Impresora de etiqueta no encontrada en Windows: %LABEL_PRINTER%"
) else (
    call :ok "Impresora de etiqueta detectada: %LABEL_PRINTER%"
)
exit /b 0

:check_autostart_task
schtasks /Query /TN "EtiquetadorZPL_API_Autostart" >nul 2>&1
if errorlevel 1 (
    call :warn "No existe tarea de inicio automatico (opcional): EtiquetadorZPL_API_Autostart"
) else (
    call :ok "Tarea de inicio automatico detectada."
)
exit /b 0
