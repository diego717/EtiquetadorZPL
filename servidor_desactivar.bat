@echo off
setlocal EnableExtensions
title EtiquetadorZPL - Desactivar servidor en esta PC

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

choice /C SN /M "Quitar el inicio automatico y detener el servidor en ESTA PC"
if errorlevel 2 exit /b 0
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\servidor.ps1" -Accion Desactivar
