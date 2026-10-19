@echo off
title EtiquetadorZPL - Estado del servidor
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\servidor.ps1" -Accion Estado
