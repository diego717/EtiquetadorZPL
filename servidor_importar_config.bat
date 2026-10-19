@echo off
setlocal EnableExtensions
title EtiquetadorZPL - Importar configuracion

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

rem Uso: arrastrar el EtiquetadorZPL_config_*.zip sobre este archivo.
if "%~1"=="" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\servidor.ps1" -Accion Importar
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\servidor.ps1" -Accion Importar -ZipPath "%~1"
)
