@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name RecortadorFotos --collect-data cv2 recortador_fotos.py
if errorlevel 1 pause
