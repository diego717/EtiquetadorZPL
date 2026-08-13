@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name RecortadorFotosModerno --collect-data cv2 --collect-data customtkinter recortador_fotos_moderno.py
if errorlevel 1 pause
