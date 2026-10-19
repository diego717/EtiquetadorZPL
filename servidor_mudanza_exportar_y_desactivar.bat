@echo off
setlocal EnableExtensions
title EtiquetadorZPL - Mudanza: exportar y desactivar esta PC

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

echo Esto DESACTIVA el servidor en ESTA PC y exporta su configuracion a un ZIP en el Escritorio.
echo Usarlo en la PC VIEJA, justo antes de instalar en la nueva.
echo (Si el servidor corre en dos PCs a la vez, las etiquetas de Odoo salen duplicadas.)
echo.
choice /C SN /M "Continuar"
if errorlevel 2 exit /b 0
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\servidor.ps1" -Accion Desactivar -NoPausar
if errorlevel 1 (pause & exit /b 1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\servidor.ps1" -Accion Exportar
