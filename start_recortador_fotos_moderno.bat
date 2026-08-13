@echo off
cd /d "%~dp0"
python recortador_fotos_moderno.py
if errorlevel 1 pause
