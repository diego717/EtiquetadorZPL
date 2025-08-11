@echo off
echo === EtiquetadorZPL Service (Fixed) ===
echo Iniciando servicio con paths corregidos...
echo.

cd /d "%~dp0"
python api/simple_service.py
pause