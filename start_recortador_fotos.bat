@echo off
cd /d "%~dp0"
python recortador_fotos.py
if errorlevel 1 pause
