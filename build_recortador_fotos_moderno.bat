@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name RecortadorFotosModerno --collect-data cv2 --collect-data customtkinter --collect-all mediapipe --add-data "models/face_detection_yunet_2023mar.onnx;models" --add-data "models/blaze_face_short_range.tflite;models" recortador_fotos_moderno.py
if errorlevel 1 pause
