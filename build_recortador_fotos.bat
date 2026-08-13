@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name RecortadorFotos --collect-data cv2 --add-data "models/face_detection_yunet_2023mar.onnx;models" recortador_fotos.py
if errorlevel 1 pause
