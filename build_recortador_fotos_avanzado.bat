@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name RecortadorFotosAvanzado --collect-data cv2 --collect-data customtkinter --collect-data fitz recortador_fotos_avanzado.py
if errorlevel 1 pause
