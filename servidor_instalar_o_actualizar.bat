@echo off
setlocal EnableExtensions
title EtiquetadorZPL - Instalar o actualizar servidor

rem Pedir permisos de Administrador si hace falta.
net session >nul 2>&1
if errorlevel 1 (
    if "%~1"=="" (
        powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    ) else (
        powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '\"%~1\"' -Verb RunAs"
    )
    exit /b
)

echo Instala (o actualiza) el servidor en C:\EtiquetadorZPL y lo deja arrancando solo.
echo Si junto a este archivo hay un EtiquetadorZPL_config_*.zip, importa esa configuracion.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\servidor.ps1" -Accion Instalar
