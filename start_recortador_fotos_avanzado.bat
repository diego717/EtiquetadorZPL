@echo off
cd /d "%~dp0"
python recortador_fotos_avanzado.py
if errorlevel 1 pause
